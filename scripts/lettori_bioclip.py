"""Lettori di malattie e insetti sulle caratteristiche attuali (DINOv2 + EfficientNet) affiancate a BioCLIP.

Foto: la selezione di scripts/estrai_bioclip.py (tutte le foto di campo, campione delle fonti numerose).
Malattie: tre gruppi da 5 lettori (più peso a PlantDoc e alle foto di campo, come nel giro M);
insetti: due gruppi da 5 (più peso alle foto della Calabria). Confronto con i lettori pubblicati (models/vM)
sulle stesse foto di prova, per fonte. Salva models/vN/ensemble_{disease,pest}.pt.

Uso: PYTHONPATH=src python scripts/lettori_bioclip.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import improve_readers as ir  # noqa: E402
import estrai_bioclip as eb  # noqa: E402
from plantcare import readers as rd  # noqa: E402

OUT = ROOT / "models" / "vN"
VARIANTI = {
    "disease": [{**ir.FIELD, "plantdoc": 6.0, "plantwild": 4.0, "aperti": 1.0},
                {**ir.FIELD, "plantdoc": 8.0, "plantwild": 4.0, "aperti": 0.7},
                {**ir.FIELD, "plantdoc": 6.0, "plantwild": 4.0}],
    "pest": [{**ir.FIELD, "inat_calabria": 4.0, "bugwood": 2.0, "observation": 2.0},
             {**ir.FIELD, "inat_calabria": 3.0}],
}
N_LETTORI = {"disease": 14, "pest": 10}  # limiti di dimensione del modello per il browser


def per_fonte(pred, y, src):
    out = {"tutte": round(float((pred == y).mean()), 4)}
    for s in sorted(set(src)):
        m = src == s
        if m.sum() >= 20:
            out[s] = round(float((pred[m] == y[m]).mean()), 4)
    return out


def main():
    rows, feats = ir.load()
    idx = eb.selezione(rows)
    sub = [rows[i] for i in idx]
    d = np.load(ROOT / "data/processed/features_bioclip_224.npz", allow_pickle=True)["d"].item()
    fb = np.stack([d[r["path"]] for r in sub]).astype(np.float32)
    fb = fb / np.linalg.norm(fb, axis=1, keepdims=True) * 10
    X = np.concatenate([feats[idx], fb], 1)
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for head in ("disease", "pest"):
        hd = rd.prepare_head(sub, X, head)
        dim = X.shape[1]
        ens = []
        for k, w in enumerate(VARIANTI[head]):
            ens += [ir.fit(hd, dim, 100 * k + s, w) for s in range(5)]
        ens = ens[:N_LETTORI[head]]
        pv = ir.probs(ens, hd.X["val"]); t = ir.calibrate(pv, hd.y["val"])
        pt = F.softmax(ir.probs(ens, hd.X["test"]).clamp_min(1e-9).log() / t, 1)
        y, src = hd.y["test"].numpy(), np.array(hd.sources["test"])
        nuovo = per_fonte(pt.argmax(1).numpy(), y, src)
        # lettori pubblicati (M) sulle stesse foto di prova, con le caratteristiche attuali
        ck = torch.load(ROOT / f"models/vM/ensemble_{head}.pt", map_location="cpu", weights_only=False)
        ms = []
        for st in ck["models"]:
            m = rd.Reader(st["net.0.weight"].shape[0], len(ck["classes"]), hidden=1024); m.load_state_dict(st); m.eval(); ms.append(m)
        Xt_cur = hd.X["test"][:, :feats.shape[1]]
        pm = ir.probs(ms, Xt_cur).argmax(1).numpy()
        lab_m = np.array(ck["classes"])[pm]
        lab_y = np.array(hd.classes)[y]
        vecchio = per_fonte(lab_m, lab_y, src)
        print(f"== {head}: {len(hd.classes)} classi, {len(ens)} lettori", flush=True)
        for s in nuovo:
            print(f"   {s:16s} M={vecchio.get(s)}  N={nuovo[s]}", flush=True)
        res[head] = {"N": nuovo, "M": vecchio}
        torch.save({"models": [m.state_dict() for m in ens], "temperature": t, "classes": hd.classes},
                   OUT / f"ensemble_{head}.pt")
    json.dump(res, open(OUT / "confronto.json", "w"), indent=1)


if __name__ == "__main__":
    main()
