"""Calibra le ipotesi dell'app (predizione conforme) sul modello web, come lo usa il browser.

Il modello ONNX gira come nell'app (quadrato centrale a 224 px e immagine specchiata, media delle
due probabilità). Le soglie si calcolano sulle foto di validazione (mai usate per i pesi) e si
verificano sulle foto di test:

  ipotesi al 95% e al 99%   elenco delle classi con probabilità >= 1 - q (Sadinle et al. 2019), q
                            quantile conforme dei punteggi 1 - p(classe giusta) sulla calibrazione
  con la coltura indicata   per le malattie: probabilità ristrette alle malattie viste su quella coltura
  cause                     stesso metodo sulle probabilità sommate per causa (fungo, batterio, ...)
  risposta sicura           soglia di confidenza oltre la quale, in validazione, le risposte sono
                            giuste almeno nel 99% dei casi

Calibrazione e test sono foto di campo (PlantDoc, PlantWild; per la coltura anche iNatAg) e IP102
per gli insetti: la garanzia vale per foto simili a queste.

Uso:
  PYTHONPATH=src python scripts/calibrate_hypotheses.py --model app/model/plantcare.onnx \
      --readers app/data/readers.json --out models/hypotheses.json
"""
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from plantcare import conformal as cf

ROOT = Path(__file__).resolve().parents[1]
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
FIELD = {"disease": ("plantdoc", "plantwild"), "plant": ("plantdoc", "plantwild", "inatag"), "pest": ("ip102", "inat_calabria")}
PEST_CAP = {"val": 30, "test": 50}  # foto IP102 per classe (sottoinsieme fisso)
LEVELS = (0.95, 0.99)
GENERIC_CLASSES = {"healthy", "disturbo_nutrizionale"}  # valide per ogni coltura: mai filtrate (come nell'app)


def prep(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((224, 224), Image.BILINEAR)
    a = ((np.asarray(im, np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)
    return np.stack([a, a[:, :, ::-1]])


def run_model(model, paths, heads):
    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    from plantcare.modello_web import byte_modello
    sess = ort.InferenceSession(byte_modello(model), so)
    names = [o.name for o in sess.get_outputs()]
    out = {h: [] for h in heads}
    for k, p in enumerate(paths):
        res = dict(zip(names, sess.run(None, {"image": prep(p)})))
        for h in heads:
            out[h].append(res[h].mean(0))
        if k % 500 == 0:
            print(f"  {k}/{len(paths)}", flush=True)
    return {h: np.array(v, dtype=np.float64) for h, v in out.items()}


def level_report(p_cal, y_cal, p_test, y_test):
    out = {}
    for lev in LEVELS:
        q = cf.calibrate(p_cal, y_cal, 1 - lev, "lac")
        r = cf.set_report(cf.prediction_sets(p_test, q, "lac"), y_test)
        out[f"{round(lev * 100)}"] = {"soglia_probabilita": round(max(0.0, 1 - q), 6), "n_calibrazione": int(len(y_cal)),
                                      **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}}
    tau = cf.selective_threshold(p_cal, y_cal, 0.99)
    ans = p_test.max(1) >= tau
    out["sicura"] = {"soglia": round(tau, 6), "risponde": round(float(ans.mean()), 4),
                     "giuste": round(float((p_test.argmax(1)[ans] == y_test[ans]).mean()), 4) if ans.any() else None}
    return out


def crop_mask(p, crops, class_crops):
    """Probabilità ristrette alle malattie viste sulla coltura indicata (classi senza coltura: sempre)."""
    out = p.copy()
    for k, c in enumerate(crops):
        if not c:
            continue
        m = np.array([(not cc) or (c in cc) for cc in class_crops])
        if m.any():
            out[k] = np.where(m, out[k], 0)
            out[k] /= out[k].sum()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "app/model/plantcare.onnx"))
    ap.add_argument("--readers", default=str(ROOT / "app/data/readers.json"))
    ap.add_argument("--out", default=str(ROOT / "models/hypotheses.json"))
    ap.add_argument("--limit", type=int, default=0, help="solo per prove: foto per gruppo")
    args = ap.parse_args()
    readers = json.load(open(args.readers, encoding="utf-8"))
    heads = [h for h in ("plant", "disease", "pest") if h in readers]
    labels = {h: [c["label"] for c in readers[h]["classes"]] for h in heads}
    rows = list(csv.DictReader(open(ROOT / "data/processed/manifest_v2.csv", encoding="utf-8")))
    rng = random.Random(0)
    sel = {}
    for sp in ("val", "test"):
        field = [r for r in rows if r["split"] == sp and r["source"] in FIELD["plant"]]
        by = defaultdict(list)
        for r in rows:
            if r["split"] == sp and r["source"] in ("ip102", "inat_calabria"):
                by[r["pest"]].append(r)
        pest = [x for _, v in sorted(by.items()) for x in rng.sample(v, min(PEST_CAP[sp], len(v)))] if "pest" in heads else []
        if args.limit:
            field, pest = field[:args.limit], pest[:args.limit]
        sel[sp] = field + pest
    probs = {sp: run_model(args.model, [ROOT / "data" / r["path"] for r in sel[sp]], heads) for sp in sel}

    class_crops = defaultdict(set)  # colture viste per ogni malattia nell'addestramento
    for r in rows:
        if r["split"] == "train" and r.get("disease") and r.get("plant") and r["disease"] not in GENERIC_CLASSES:
            class_crops[r["disease"]].add(r["plant"])
    result = {"metodo": "predizione conforme, soglia sulle probabilità (LAC); calibrazione = validazione, verifica = test",
              "fonti_calibrazione": {h: list(FIELD[h]) for h in heads}}
    for h in heads:
        idx = {c: i for i, c in enumerate(labels[h])}
        pick = {sp: [k for k, r in enumerate(sel[sp]) if r["source"] in FIELD[h] and r.get(h) in idx] for sp in sel}
        if not pick["val"] or not pick["test"]:
            continue
        y = {sp: np.array([idx[sel[sp][k][h]] for k in pick[sp]]) for sp in sel}
        p = {sp: probs[sp][h][pick[sp]] for sp in sel}
        res = {"top1_test": round(float((p["test"].argmax(1) == y["test"]).mean()), 4),
               "livelli": level_report(p["val"], y["val"], p["test"], y["test"])}
        if h == "disease":
            cc = [sorted(class_crops.get(c, ())) for c in labels[h]]
            crops = {sp: [sel[sp][k].get("plant", "") for k in pick[sp]] for sp in sel}
            pm = {sp: crop_mask(p[sp], crops[sp], [set(x) for x in cc]) for sp in sel}
            res["con_coltura"] = {"top1_test": round(float((pm["test"].argmax(1) == y["test"]).mean()), 4),
                                  "livelli": level_report(pm["val"], y["val"], pm["test"], y["test"])}
            res["colture_per_classe"] = dict(zip(labels[h], cc))
            causes = [c.get("cause") or "non_specificato" for c in readers[h]["classes"]]
            g = {sp: cf.group_probs(p[sp], causes)[0] for sp in sel}
            names = cf.group_probs(p["val"][:1], causes)[1]
            yc = {sp: np.array([names.index(causes[i]) for i in y[sp]]) for sp in sel}
            res["cause"] = {"ordine": names, "top1_test": round(float((g["test"].argmax(1) == yc["test"]).mean()), 4),
                            "livelli": level_report(g["val"], yc["val"], g["test"], yc["test"])}
        result[h] = res
        print(h, json.dumps({k: v for k, v in res.items() if k != "colture_per_classe"}, ensure_ascii=False)[:1500], flush=True)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("salvato", args.out)


if __name__ == "__main__":
    main()
