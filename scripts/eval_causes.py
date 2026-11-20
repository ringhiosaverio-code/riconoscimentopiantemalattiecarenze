"""Valuta il lettore delle malattie per causa (insetti, acari, funghi, ...) e per coppie simili.

Uso: PYTHONPATH=src python scripts/eval_causes.py [--disease-probs file.pt]
Il file opzionale contiene {"p": probabilità sul test, "classes": [...]} di un altro modello.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from improve_disease import ens_probs  # noqa: E402
from improve_readers import load  # noqa: E402

from plantcare import readers as rd  # noqa: E402
from plantcare.causes import cause_of, load_causes  # noqa: E402
from plantcare.taxonomy import load_taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [("apple_scab", "Apple___Cedar_apple_rust"), ("tomato_early_blight", "tomato_late_blight"),
         ("maize_northern_leaf_blight", "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot"),
         ("tomato_mosaic_virus", "tomato_yellow_leaf_curl")]


def report(p, y, classes, src):
    tax = load_taxonomy()
    lm = yaml.safe_load(open(ROOT / "configs/label_maps.yaml", encoding="utf-8"))
    names, labs = load_causes()
    cause = [cause_of(c, labs, tax, lm) for c in classes]
    cats = sorted(set(cause))
    M = torch.zeros(len(classes), len(cats))
    for i, c in enumerate(cause):
        M[i, cats.index(c)] = 1
    pc = p @ M
    yc = torch.tensor([cats.index(cause[int(t)]) for t in y])
    pred_c = pc.argmax(1)
    print(f"causa corretta: {float((pred_c == yc).float().mean()):.4f} (classe corretta: "
          f"{float((p.argmax(1) == y).float().mean()):.4f})")
    for c in ("insetto", "acaro"):
        k = cats.index(c)
        m = yc == k
        rec = float((pred_c[m] == k).float().mean()) if m.any() else float("nan")
        prec = float((yc[pred_c == k] == k).float().mean()) if (pred_c == k).any() else float("nan")
        print(f"  {names[c]:8s} n={int(m.sum()):4d} riconosciuti={rec:.3f} precisione={prec:.3f}")
    ik = [cats.index("insetto"), cats.index("acaro")]
    m = (yc == ik[0]) | (yc == ik[1])
    both = (pred_c == ik[0]) | (pred_c == ik[1])
    print(f"  insetti o acari: riconosciuti={float(both[m].float().mean()):.3f}")
    pred = p.argmax(1)
    for a, b in PAIRS:
        if a not in classes or b not in classes:
            continue
        ia, ib = classes.index(a), classes.index(b)
        for t, o in ((ia, ib), (ib, ia)):
            mm = y == t
            by = defaultdict(lambda: [0, 0, 0])
            for i in torch.nonzero(mm).flatten().tolist():
                s = by[src[i]]
                s[0] += 1
                s[1] += int(pred[i] == t)
                s[2] += int(pred[i] == o)
            print(f"  {classes[t][:28]:28s}: " + "; ".join(f"{s} n={v[0]} giusti={v[1]} scambiati={v[2]}"
                                                         for s, v in by.items()))
    return pc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disease-probs", default=None)
    a = ap.parse_args()
    rows, feats = load()
    hd = rd.prepare_head(rows, feats, "disease")
    if a.disease_probs:
        d = torch.load(a.disease_probs, weights_only=False)
        p, classes, y, src = d["p"], d["classes"], d["y"], d["src"]
    else:
        p, classes = ens_probs(ROOT / "models/ensemble_disease.pt", hd.X["test"], feats.shape[1])
        y, src = hd.y["test"], hd.sources["test"]
    report(p, y, classes, src)
    print("per fonte (classe corretta):", {s: round(float(np.mean([int(p[i].argmax() == y[i]) for i in range(len(y))
                                                                  if src[i] == s])), 3)
                                         for s in sorted(Counter(src))})


if __name__ == "__main__":
    main()
