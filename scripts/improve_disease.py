"""Esperimenti per migliorare il lettore delle malattie, sulle caratteristiche in cache.

Varianti (parametri scelti sulla validazione, misura finale sul test):
  insieme    : insieme calibrato di 5 lettori (models/ensemble_disease.pt), il modello attuale
  coltura    : p(malattia) moltiplicata per la probabilità che la coltura riconosciuta
               ospiti quella malattia (compatibilità coltura-malattia dal train)
  vicini     : fusione con i k vicini più simili tra le foto di addestramento (coseno)
  entrambi   : coltura + vicini
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
from improve_readers import load  # noqa: E402

from plantcare import readers as rd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNIVERSAL = {"healthy", "disturbo_nutrizionale"}


def ens_probs(path: Path, X: torch.Tensor, dim: int) -> torch.Tensor:
    e = torch.load(path, map_location="cpu", weights_only=False)
    ms = []
    for st in e["models"]:
        m = rd.Reader(dim, len(e["classes"]), hidden=1024)
        m.load_state_dict(st)
        ms.append(m.eval())
    with torch.no_grad():
        p = torch.stack([F.softmax(m(X), 1) for m in ms]).mean(0)
    return F.softmax(p.clamp_min(1e-9).log() / e["temperature"], 1), e["classes"]


def compat_matrix(rows, plant_classes, disease_classes) -> torch.Tensor:
    pi = {c: i for i, c in enumerate(plant_classes)}
    di = {c: i for i, c in enumerate(disease_classes)}
    C = torch.zeros(len(plant_classes), len(disease_classes))
    for r in rows:
        if r["split"] == "train" and r["plant"] in pi and r["disease"] in di:
            C[pi[r["plant"]], di[r["disease"]]] = 1
    for u in UNIVERSAL & set(di):
        C[:, di[u]] = 1
    # malattie senza coltura nota nel train: nessun vincolo
    C[:, C.sum(0) == 0] = 1
    return C


def knn_probs(Xtr, ytr, Xq, n_classes, k=10, tau=0.05, chunk=2048):
    Xtr = F.normalize(Xtr, dim=1)
    out = torch.zeros(len(Xq), n_classes)
    for i in range(0, len(Xq), chunk):
        q = F.normalize(Xq[i:i + chunk], dim=1)
        s, j = (q @ Xtr.T).topk(k, dim=1)
        w = (s / tau).softmax(1)
        out[i:i + chunk].scatter_add_(1, ytr[j], w)
    return out


def combine(p, pc, pk, alpha, beta):
    logp = (1 - beta) * p.clamp_min(1e-9).log() + beta * pk.clamp_min(1e-9).log()
    if alpha:
        logp = logp + alpha * pc.clamp_min(1e-9).log()
    return logp.softmax(1)


def acc(p, y, src=None, only=None):
    pred = p.argmax(1)
    if only is not None:
        m = torch.tensor([s == only for s in src])
        return float((pred[m] == y[m]).float().mean())
    return float((pred == y).float().mean())


def main():
    rows, feats = load()
    dim = feats.shape[1]
    hd = rd.prepare_head(rows, feats, "disease")
    feats_t = None  # noqa: F841
    p = {s: None for s in ("val", "test")}
    pc, pk = {}, {}
    pl_classes = None
    for s in ("val", "test"):
        p[s], dcls = ens_probs(ROOT / "models/ensemble_disease.pt", hd.X[s], dim)
        pp, pl_classes = ens_probs(ROOT / "models/ensemble_plant.pt", hd.X[s], dim)
        if s == "val":
            C = compat_matrix(rows, pl_classes, dcls)
        pc[s] = pp @ C
        pk[s] = {k: knn_probs(hd.X["train"], hd.y["train"], hd.X[s], len(dcls), k=k) for k in (5, 10, 20)}
    assert dcls == hd.classes
    y, src = hd.y, hd.sources

    def score(split, a, b, k):
        q = combine(p[split], pc[split], pk[split][k], a, b)
        return acc(q, y[split]), acc(q, y[split], src[split], "plantdoc"), q

    base_val = score("val", 0, 0, 10)[:2]
    print(f"validazione insieme: tutte={base_val[0]:.4f} plantdoc={base_val[1]:.4f}")
    grid = [(a, b, k) for a in (0, 0.5, 1, 2) for b in (0, 0.2, 0.35, 0.5) for k in (5, 10, 20)]
    res = {}
    for name, allowed in (("insieme", lambda a, b: a == 0 and b == 0), ("coltura", lambda a, b: b == 0),
                          ("vicini", lambda a, b: a == 0), ("entrambi", lambda a, b: True)):
        best = None
        for a, b, k in grid:
            if not allowed(a, b) or (b == 0 and k != 10):
                continue
            va, vpd, _ = score("val", a, b, k)
            if va < base_val[0] - 0.003:  # non perdere sul complesso
                continue
            if best is None or vpd > best[0] + 1e-9:
                best = (vpd, a, b, k)
        _, a, b, k = best
        ta, tpd, q = score("test", a, b, k)
        res[name] = {"alpha": a, "beta": b, "k": k, "acc": ta, "plantdoc": tpd}
        print(f"  {name:9s} alpha={a} beta={b} k={k}  test={ta:.4f} plantdoc={tpd:.4f}", flush=True)
    # errori più frequenti su PlantDoc con il modello attuale
    m = [i for i, s in enumerate(src["test"]) if s == "plantdoc"]
    pred = p["test"].argmax(1)
    errs = Counter((dcls[int(y["test"][i])], dcls[int(pred[i])]) for i in m if pred[i] != y["test"][i])
    print("errori più frequenti su PlantDoc (vero -> previsto):")
    for (t, pr), n in errs.most_common(12):
        print(f"  {n:3d}  {t} -> {pr}")
    json.dump(res, open(ROOT / "models/improve_disease.json", "w"), indent=2)


if __name__ == "__main__":
    main()
