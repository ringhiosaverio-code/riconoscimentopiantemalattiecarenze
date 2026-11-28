"""Caratteristiche BioCLIP per l'addestramento dei lettori di malattie e insetti (modello completo).

Foto di campo tutte; delle fonti molto numerose (PlantVillage, IP102, dataset AgML) un campione per
classe (150 di addestramento, 40 di validazione, 30 di prova). Cache riprendibile in
data/processed/features_bioclip_224.npz (stessa di scripts/prova_estrattori.py).

Uso: PYTHONPATH=src python scripts/estrai_bioclip.py
"""
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prova_estrattori as pe  # noqa: E402
from plantcare.data.pipeline import read_manifest  # noqa: E402

CAP = {"train": 150, "val": 40, "test": 30}


def selezione(rows):
    rng = random.Random(0)
    keep, by = [], defaultdict(list)
    for i, r in enumerate(rows):
        if not (r.get("disease") or r.get("pest")):
            continue
        if r["source"] in pe.CAMPO:
            keep.append(i)
        else:
            by[(r["source"], r.get("disease") or r.get("pest"), r["split"])].append(i)
    for (_, _, split), v in by.items():
        n = CAP[split]
        keep += v if len(v) <= n else rng.sample(v, n)
    return sorted(keep)


if __name__ == "__main__":
    rows = read_manifest(ROOT / "data/processed/manifest_v2.csv")
    idx = selezione(rows)
    print("foto:", len(idx), flush=True)
    pe.bioclip_features([rows[i]["path"] for i in idx], ROOT / "data/processed/features_bioclip_224.npz")
    print("FATTO", flush=True)
