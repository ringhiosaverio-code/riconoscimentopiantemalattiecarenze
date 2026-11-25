"""Vine Virus Photo Dataset (MacDonald et al. 2025, CC BY 4.0, Project-AgML): foto di viti in vigneto con
lo stato virale verificato in laboratorio sui tessuti.

Si tengono l'accartocciamento fogliare (Leafroll 3, GLRaV-3, presente anche in Italia) e le viti senza
virus; "Red Blotch" e "Other Red" restano fuori. I file sono 23 pezzi da circa 500 MB: si scarica un
pezzo alla volta, si salvano le foto ridotte e il pezzo si cancella.

Uso: python scripts/import_vinevirus.py
"""
import io
import json
import math
import sys
import random
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = "Project-AgML/vine_virus_photo_dataset"
OUT = ROOT / "data" / "external" / "vinevirus"
IMG = ROOT / "data" / "external" / "images" / "vinevirus"
KEEP = {0: ("leafroll", 600), 1: ("no_virus", 400)}  # etichetta del dataset: (nome, foto al massimo)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    state_p = OUT / "stato.json"
    state = json.load(open(state_p)) if state_p.exists() else {"pezzi": [], "foto": []}
    tree = json.load(urllib.request.urlopen(f"https://huggingface.co/api/datasets/{REPO}/tree/main/data", timeout=60))
    shards = sorted(x["path"] for x in tree if x["path"].endswith(".parquet"))
    count = {v[0]: sum(1 for f in state["foto"] if f["classe"] == v[0]) for v in KEEP.values()}
    # le etichette di ogni pezzo si leggono a distanza (solo la colonna "label"): i pezzi sono ordinati per
    # classe, quindi la quota di ogni pezzo è proporzionale alle sue foto della classe
    sys.path.insert(0, str(ROOT / "scripts"))
    from import_diamos import HttpFile
    if "etichette" not in state:
        state["etichette"] = {sh: pq.ParquetFile(HttpFile(f"https://huggingface.co/datasets/{REPO}/resolve/main/{sh}"))
                              .read(columns=["label"]).column("label").to_pylist() for sh in shards}
        json.dump(state, open(state_p, "w"))
    tot = {lab: sum(v.count(lab) for v in state["etichette"].values()) for lab in KEEP}
    rnd = random.Random(42)
    for sh in shards:
        if sh in state["pezzi"]:
            continue
        if all(count[n] >= cap for n, cap in KEEP.values()):
            break
        if not any(lab in KEEP for lab in state["etichette"][sh]):
            state["pezzi"].append(sh)
            continue
        tmp = OUT / "pezzo.parquet"
        urllib.request.urlretrieve(f"https://huggingface.co/datasets/{REPO}/resolve/main/{sh}", tmp)
        rows = pq.read_table(tmp, columns=["label"]).column("label").to_pylist()
        idx = [i for i, lab in enumerate(rows) if lab in KEEP]
        rnd.shuffle(idx)
        per_shard = {KEEP[lab][0]: math.ceil(KEEP[lab][1] * rows.count(lab) / max(1, tot[lab])) for lab in KEEP}
        chosen, taken = [], {n: 0 for n in per_shard}
        for i in idx:
            n = KEEP[rows[i]][0]
            if taken[n] < per_shard[n] and count[n] + taken[n] < KEEP[rows[i]][1]:
                chosen.append(i)
                taken[n] += 1
        if chosen:
            table = pq.read_table(tmp, columns=["image"])
            for i in chosen:
                n = KEEP[rows[i]][0]
                f = IMG / n / f"{Path(sh).stem[-14:-9]}_{i:04d}.jpg"
                with Image.open(io.BytesIO(table.column("image")[i].as_py()["bytes"])) as im:
                    im = im.convert("RGB")
                    im.thumbnail((640, 640))
                    f.parent.mkdir(parents=True, exist_ok=True)
                    im.save(f, quality=90)
                state["foto"].append({"path": str(f.relative_to(ROOT / "data")), "classe": n, "pezzo": sh})
                count[n] += 1
        tmp.unlink()
        state["pezzi"].append(sh)
        json.dump(state, open(state_p, "w"))
        print(sh, count, flush=True)
    print("FATTO", count)


if __name__ == "__main__":
    main()
