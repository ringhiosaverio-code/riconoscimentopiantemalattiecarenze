"""Esperimenti per migliorare i lettori sulle caratteristiche in cache (nessuna nuova estrazione).

Varianti confrontate sul test (complessivo e foto di campo):
  base      : un MLP, pesi di classe (come l'addestramento attuale)
  campo     : come base, con le foto di campo (PlantDoc, iNatAg) pesate di più
  insieme   : media di 5 MLP con semi diversi (e pesatura del campo)
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from plantcare import readers as rd
from plantcare.data.pipeline import read_manifest
from plantcare.metrics import expected_calibration_error, macro_f1

ROOT = Path(__file__).resolve().parents[1]
FIELD = {"plantdoc": 3.0, "inatag": 3.0, "plantwild": 3.0, "inat_calabria": 2.0, "fieldvitis": 3.0, "diamos": 2.0,
         "bugwood": 1.0, "observation": 1.0, "emiliaromagna": 1.0,
         "vinevirus": 2.0, "letteratura": 3.0, "verificate": 2.0, "aperti": 2.0, "danni": 2.0,
         # foto scattate con l'app nei campi del Sud e corrette da un agronomo (pulsante "Invia contributi"):
         # le più vicine all'uso reale, quindi il peso più alto
         "contributi": 5.0}


def load():
    rows = read_manifest(ROOT / "data/processed/manifest_v2.csv")
    paths = [ROOT / "data" / r["path"] for r in rows]
    feats = np.concatenate([rd.extract_features(paths, b, ROOT / f"data/processed/features_{b}_224")
                            for b in ("vit_small_patch14_dinov2.lvd142m", "efficientnet_b0")], axis=1)
    return rows, feats


def fit(hd, dim, seed, field_weight):
    torch.manual_seed(seed)
    r = rd.Reader(dim, len(hd.classes), hidden=1024)
    counts = torch.bincount(hd.y["train"], minlength=len(hd.classes)).float().clamp(min=1)
    cw = (counts.sum() / counts).sqrt(); cw = cw / cw.mean()
    sw = torch.tensor([field_weight.get(s, 1.0) for s in hd.sources["train"]])
    X, y = hd.X["train"], hd.y["train"]
    opt = torch.optim.AdamW(r.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=40)
    g = torch.Generator().manual_seed(seed)
    best, state, bad = -1, None, 0
    for _ in range(40):
        r.train(); perm = torch.randperm(len(X), generator=g)
        for i in range(0, len(X), 512):
            b = perm[i:i + 512]
            loss = (F.cross_entropy(r(X[b]), y[b], weight=cw, label_smoothing=0.05, reduction="none") * sw[b]).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step(); r.eval()
        with torch.no_grad():
            s = macro_f1(hd.y["val"].numpy(), r(hd.X["val"]).argmax(1).numpy())
        if s > best: best, state, bad = s, {k: v.clone() for k, v in r.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 6: break
    r.load_state_dict(state)
    return r


def probs(models, X):
    with torch.no_grad():
        return torch.stack([F.softmax(m(X), 1) for m in models]).mean(0)


def calibrate(p_val, y_val):
    """Temperature scaling sulle log-probabilità medie dell'insieme."""
    logp = p_val.clamp_min(1e-9).log()
    lt = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([lt], lr=0.1, max_iter=100)
    def closure():
        opt.zero_grad(); l = F.cross_entropy(logp / lt.exp(), y_val); l.backward(); return l
    opt.step(closure)
    return float(lt.exp().detach())


def report(name, p, hd):
    y = hd.y["test"].numpy(); pred = p.argmax(1).numpy(); src = np.array(hd.sources["test"])
    out = {"acc": float((pred == y).mean()), "f1": macro_f1(y, pred), "ece": expected_calibration_error(p.numpy(), y)}
    for s in ("plantdoc", "inatag", "plantwild", "inat_calabria"):
        m = src == s
        if m.any(): out[s] = float((pred[m] == y[m]).mean())
    print(f"  {name:10s} " + " ".join(f"{k}={v:.4f}" for k, v in out.items()), flush=True)
    return out


def main(heads, only_ensemble=False):
    rows, feats = load()
    dim = feats.shape[1]
    results = {}
    for head in heads:
        hd = rd.prepare_head(rows, feats, head)
        print(f"== {head}: {len(hd.classes)} classi", flush=True)
        res = {}
        if not only_ensemble:
            base = [fit(hd, dim, 0, {})]
            res["base"] = report("base", probs(base, hd.X["test"]), hd)
        field = [fit(hd, dim, 0, FIELD)]
        if not only_ensemble:
            res["campo"] = report("campo", probs(field, hd.X["test"]), hd)
        ens = field + [fit(hd, dim, s, FIELD) for s in (1, 2, 3, 4)]
        pv = probs(ens, hd.X["val"]); t = calibrate(pv, hd.y["val"])
        pt = F.softmax(probs(ens, hd.X["test"]).clamp_min(1e-9).log() / t, 1)
        res["insieme"] = report("insieme", pt, hd)
        results[head] = res
        torch.save({"models": [m.state_dict() for m in ens], "temperature": t, "classes": hd.classes},
                   ROOT / "models" / f"ensemble_{head}.pt")
    out = ROOT / "models" / "improve_results.json"
    old = json.load(open(out)) if out.exists() else {}
    old.update(results)
    json.dump(old, open(out, "w"), indent=2)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args or ["plant", "disease", "deficiency"], only_ensemble="--solo-insieme" in sys.argv)
