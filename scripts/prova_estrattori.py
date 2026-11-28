"""Prova di estrattori di immagini più grandi per i lettori di malattie e insetti (sulle foto di campo).

Confronto, a parità di lettori e pesi di addestramento (scripts/improve_readers.py):
- attuale: DINOv2 ViT-S/14 + EfficientNet-B0 (caratteristiche già in cache);
- BioCLIP (ViT-B/16, Imageomics, licenza MIT): addestrato su 10 milioni di foto di organismi (TreeOfLife-10M);
- attuale + BioCLIP affiancati.
Si usano le foto di campo (PlantDoc, PlantWild, Calabria, dispense, dati aperti, danni, Bugwood,
Observation, vite, DiaMOS) e un campione delle altre fonti, per stare in poche ore su CPU.

Uso: PYTHONPATH=src python scripts/prova_estrattori.py [--estrattore bioclip]
"""
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import improve_readers as ir  # noqa: E402
from plantcare import readers as rd  # noqa: E402

CAMPO = {"plantdoc", "plantwild", "inat_calabria", "verificate", "aperti", "danni", "bugwood", "observation",
         "fieldvitis", "diamos", "vinevirus", "contributi", "inatag", "letteratura", "emiliaromagna"}
CAP = {"train": 20, "val": 8}  # foto per (fonte, classe): le foto di test delle fonti di campo restano tutte
TEST_ALTRE = 8


def sottoinsieme(rows):
    rng = random.Random(0)
    by = defaultdict(list)
    keep = []
    for i, r in enumerate(rows):
        if not (r.get("disease") or r.get("pest")):
            continue
        if r["split"] == "test" and r["source"] in CAMPO:
            keep.append(i)
        else:
            by[(r["source"], r.get("disease") or r.get("pest"), r["split"])].append(i)
    for (src, _, split), v in by.items():
        n = CAP.get(split, TEST_ALTRE)
        keep += v if len(v) <= n else rng.sample(v, n)
    return sorted(keep)


class _Imgs(torch.utils.data.Dataset):
    def __init__(self, paths, pre):
        self.paths, self.pre = paths, pre

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        try:
            return self.pre(Image.open(ROOT / "data" / self.paths[i]).convert("RGB"))
        except Exception:
            return torch.zeros(3, 224, 224)


def bioclip_features(paths, cache):
    import open_clip
    cache.parent.mkdir(parents=True, exist_ok=True)
    done = dict(np.load(cache, allow_pickle=True)["d"].item()) if cache.exists() else {}
    todo = [p for p in dict.fromkeys(paths) if p not in done]
    if todo:
        model, _, pre = open_clip.create_model_and_transforms("hf-hub:imageomics/bioclip")
        model.eval()
        torch.set_num_threads(4)
        dl = torch.utils.data.DataLoader(_Imgs(todo, pre), batch_size=64, num_workers=2)
        k = 0
        for x in dl:
            with torch.no_grad():
                f = model.encode_image(x).float().numpy()
            done.update(zip(todo[k:k + len(f)], f))
            k += len(f)
            if (k // 64) % 100 == 0:
                np.savez(cache, d=np.array(done, dtype=object))
                print(f"  bioclip {k}/{len(todo)} nuove", flush=True)
        np.savez(cache, d=np.array(done, dtype=object))
    return np.stack([done[p] for p in paths]).astype(np.float32)


def valuta(nome, rows, feats, head):
    hd = rd.prepare_head(rows, feats, head)
    dim = feats.shape[1]
    ens = [ir.fit(hd, dim, s, ir.FIELD) for s in range(3)]
    pv = ir.probs(ens, hd.X["val"]); t = ir.calibrate(pv, hd.y["val"])
    pt = F.softmax(ir.probs(ens, hd.X["test"]).clamp_min(1e-9).log() / t, 1)
    pred, y, src = pt.argmax(1).numpy(), hd.y["test"].numpy(), np.array(hd.sources["test"])
    out = {"tutte": float((pred == y).mean())}
    for s in sorted(set(src)):
        m = src == s
        if m.sum() >= 20:
            out[s] = round(float((pred[m] == y[m]).mean()), 4)
    print(f"{nome:22s} {head:8s}", {k: round(v, 4) for k, v in out.items()}, flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estrattore", default="bioclip")
    ap.add_argument("--manifest", default="data/processed/manifest_v2.csv")
    args = ap.parse_args()
    allrows, allfeats = ir.load()
    idx = sottoinsieme(allrows)
    rows = [allrows[i] for i in idx]
    print("foto nel sottoinsieme:", len(rows), flush=True)
    cur = allfeats[idx]
    nuovo = bioclip_features([r["path"] for r in rows], ROOT / "data/processed/features_bioclip_224.npz")
    nuovo = nuovo / np.linalg.norm(nuovo, axis=1, keepdims=True)
    res = {}
    for head in ("disease", "pest"):
        res[f"attuale_{head}"] = valuta("attuale", rows, cur, head)
        res[f"{args.estrattore}_{head}"] = valuta(args.estrattore, rows, nuovo, head)
        res[f"insieme_{head}"] = valuta("attuale+" + args.estrattore, rows, np.concatenate([cur, nuovo * 10], 1), head)
    json.dump(res, open(ROOT / f"models/prova_estrattori_{args.estrattore}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
