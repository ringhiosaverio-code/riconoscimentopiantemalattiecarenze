"""Accordo tra l'etichetta del testo (didascalia, titolo) e il modello pubblicato, per molte candidate.

Per ogni foto: posizione della classe proposta tra le ipotesi del lettore (malattie o insetti) del
modello web (stessa preparazione della foto del browser: ritaglio centrale 224, specchio). Le candidate
in cui la classe è tra le prime --k ipotesi si tengono; un campione si verifica comunque a vista.

Uso: python scripts/accordo_modello.py candidate.json app/model/plantcare.onnx app/data/readers.json [--k 5]
Scrive candidate.json con il campo "rango" (1 = prima ipotesi; 0 = classe assente dal modello).
"""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def prep(p):
    im = Image.open(p).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((224, 224), Image.BILINEAR)
    a = ((np.asarray(im, np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)
    return np.stack([a, a[:, :, ::-1]])


def main():
    cand_p, model, readers = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
    cand = json.load(open(cand_p, encoding="utf-8"))
    labels = {h: [c["label"] for c in readers[h]["classes"]] for h in ("disease", "pest") if h in readers}
    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    from plantcare.modello_web import byte_modello
    sess = ort.InferenceSession(byte_modello(model), so)
    names = [o.name for o in sess.get_outputs()]
    for i, c in enumerate(cand):
        if "rango" in c:
            continue
        head = c["testa"]
        if head not in labels or c["classe"] not in labels[head]:
            c["rango"] = 0
            continue
        try:
            out = dict(zip(names, sess.run(None, {"image": prep(ROOT / "data" / c["path"])})))
        except Exception:
            c["rango"] = -1
            continue
        p = out[head].mean(0)
        order = np.argsort(-p)
        c["rango"] = int(np.where(order == labels[head].index(c["classe"]))[0][0]) + 1
        c["p_classe"] = round(float(p[labels[head].index(c["classe"])]), 4)
        if i % 200 == 0:
            print(i, len(cand), flush=True)
            json.dump(cand, open(cand_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cand, open(cand_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(Counter(min(c["rango"], 6) for c in cand))


if __name__ == "__main__":
    main()
