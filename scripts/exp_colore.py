"""Prova controllata: trasformazioni del colore e dello sfondo prima dell'estrattore.

Domanda: cambiare saturazione, colori o sfondo della foto aiuta il riconoscimento su foto di campo
(malattie, coltura) e sugli insetti? Si confrontano, a parità di tutto il resto (stessi estrattori
congelati DINOv2 ViT-S/14 + EfficientNet-B0, stesso lettore, stesse foto), queste varianti:

  base       foto originale
  sat150     saturazione aumentata del 50% (PIL ImageEnhance.Color 1,5)
  grigi      scala di grigi (come il confronto colore/grigi di Mohanty et al. 2016)
  grayworld  bilanciamento del bianco "gray world" (costanza del colore per luce variabile)
  clahe      equalizzazione locale del contrasto sulla luminosità (CLAHE sul canale L di Lab)
  sfondo     sfondo neutro con l'indice ExG-ExR (Meyer e Neto 2008): pixel vegetali > 0, buchi
             riempiti (le lesioni dentro la foglia restano), il resto grigio medio

Protocollo: lettore addestrato sulle foto originali (3 semi), variante applicata solo alle foto di
test, come farebbe l'app prima dell'analisi. Riaddestrare con le varianti richiederebbe di ricalcolare
le caratteristiche di tutte le foto; l'aumento dei colori (ColorJitter) è già nel ramo riaddestrato.

Sottoinsieme: foto di campo (PlantDoc, PlantWild, iNatAg) per malattia e coltura; IP102 (100 per
classe in addestramento, 20 in validazione, 40 nel test) per gli insetti.

Uso: PYTHONPATH=src python scripts/exp_colore.py   (risultati in models/exp_colore.json)
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageEnhance
from scipy import ndimage
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from plantcare import readers as rd  # noqa: E402
from plantcare.data.pipeline import read_manifest  # noqa: E402
import improve_readers as ir  # noqa: E402

BACKBONES = ("vit_small_patch14_dinov2.lvd142m", "efficientnet_b0")
VARIANTS = ("sat150", "grigi", "grayworld", "clahe", "sfondo")
IMAGENET_MEAN = np.array([124, 116, 104], dtype=np.float32)
OUT_DIR = ROOT / "data/processed/exp_colore"


# --------------------------------------------------------------------------- trasformazioni
def _sat150(im):
    return ImageEnhance.Color(im).enhance(1.5)


def _grigi(im):
    return im.convert("L").convert("RGB")


def _grayworld(im):
    a = np.asarray(im, dtype=np.float32)
    m = a.reshape(-1, 3).mean(0) + 1e-6
    return Image.fromarray(np.clip(a * (m.mean() / m), 0, 255).astype(np.uint8))


_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def _clahe(im):
    lab = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2LAB)
    lab[..., 0] = _CLAHE.apply(lab[..., 0])
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def vegetation_mask(im, side: int = 384):
    """Maschera della vegetazione con ExG-ExR > 0 (soglia fissa, Meyer e Neto 2008), buchi riempiti."""
    small = im.copy(); small.thumbnail((side, side))
    a = np.asarray(small, dtype=np.float32)
    s = a.sum(2) + 1e-6
    r, g, b = a[..., 0] / s, a[..., 1] / s, a[..., 2] / s
    m = ((2 * g - r - b) - (1.4 * r - g)) > 0
    m = ndimage.binary_closing(m, structure=np.ones((5, 5)), iterations=2)
    m = ndimage.binary_fill_holes(m)
    return m


def _sfondo(im):
    m = vegetation_mask(im)
    frac = m.mean()
    if frac < 0.05 or frac > 0.97:  # segmentazione non riuscita o tutta vegetazione: foto invariata
        return im
    full = cv2.resize(m.astype(np.uint8), im.size, interpolation=cv2.INTER_NEAREST).astype(bool)
    a = np.asarray(im, dtype=np.float32).copy()
    a[~full] = IMAGENET_MEAN
    return Image.fromarray(a.astype(np.uint8))


TRANSFORMS = {"sat150": _sat150, "grigi": _grigi, "grayworld": _grayworld, "clahe": _clahe, "sfondo": _sfondo}


class _Variant(Dataset):
    """Una lettura della foto per variante, preparata per entrambi gli estrattori."""
    def __init__(self, paths, fn, tfs):
        self.paths, self.fn, self.tfs = paths, fn, tfs

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        try:
            with Image.open(self.paths[i]) as im:
                im = im.convert("RGB")
                if max(im.size) > 1024:  # stesse dimensioni finali (224 px): si risparmia tempo
                    im.thumbnail((1024, 1024))
                t = self.fn(im)
                return tuple(tf(t) for tf in self.tfs) + (i,)
        except Exception:
            return tuple(torch.zeros(3, 224, 224) for _ in self.tfs) + (i,)


@torch.no_grad()
def variant_features(paths, variant):
    """Caratteristiche ViT-S + EfficientNet-B0 della variante (in cache su disco)."""
    out = OUT_DIR / f"{variant}.npy"
    if out.exists():
        return np.load(out)
    models, tfs = zip(*(rd.build_backbone(b) for b in BACKBONES))
    dl = DataLoader(_Variant(paths, TRANSFORMS[variant], tfs), batch_size=64, num_workers=2)
    feats = np.zeros((len(paths), sum(m.num_features for m in models)), dtype=np.float16)
    for k, batch in enumerate(dl):
        idx = batch[-1].numpy()
        feats[idx] = torch.cat([m(x) for m, x in zip(models, batch[:-1])], 1).float().numpy().astype(np.float16)
        if k % 50 == 0:
            print(f"    {variant}: {min((k + 1) * 64, len(paths))}/{len(paths)}", flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.save(out, feats)
    return feats


# --------------------------------------------------------------------------- sottoinsieme
def subset():
    rows = read_manifest(ROOT / "data/processed/manifest_v2.csv")
    rng = random.Random(0)
    field = [r for r in rows if r["source"] in ("plantdoc", "plantwild")]
    inat = defaultdict(list)  # iNatAg serve solo alla coltura: addestramento ridotto a 60 foto per coltura
    for r in rows:
        if r["source"] == "inatag":
            inat[(r["split"], r["plant"])].append(r)
    field += [x for (sp, _), v in sorted(inat.items()) for x in (rng.sample(v, min(60, len(v))) if sp == "train" else v)]
    cap = {"train": 100, "val": 20, "test": 40}
    by = defaultdict(list)
    for r in rows:
        if r["source"] == "ip102":
            by[(r["split"], r["pest"])].append(r)
    pest = [x for (sp, _), v in sorted(by.items()) for x in rng.sample(v, min(cap[sp], len(v)))]
    return field, pest


def evaluate(hd_train, hd_test, dim, seeds=(0, 1)):
    """Lettore addestrato su hd_train, accuratezza per fonte sul test di hd_test (stesse classi)."""
    accs = []
    for seed in seeds:
        m = ir.fit(hd_train, dim, seed, ir.FIELD)
        with torch.no_grad():
            p = m(hd_test.X["test"]).argmax(1).numpy()
        y = hd_test.y["test"].numpy(); src = np.array(hd_test.sources["test"])
        a = {s: float((p[src == s] == y[src == s]).mean()) for s in sorted(set(src))}
        a["tutto"] = float((p == y).mean())
        accs.append(a)
    return {k: round(float(np.mean([a[k] for a in accs])), 4) for k in accs[0]}


def main():
    """Protocollo B (variante applicata solo alla foto da analizzare, come farebbe l'app): le
    caratteristiche delle varianti servono solo per le foto di test. Il protocollo A/C (riaddestrare
    con le varianti) richiede le caratteristiche di tutte le foto: su CPU condivisa non è praticabile
    qui, e l'aumento dei colori (ColorJitter) è già usato nel ramo riaddestrato."""
    torch.set_num_threads(2)
    field, pest = subset()
    sub = field + pest
    paths = [ROOT / "data" / r["path"] for r in sub]
    test_idx = [i for i, r in enumerate(sub) if r["split"] == "test"]
    print(f"sottoinsieme: {len(field)} foto di campo, {len(pest)} foto di insetti; test {len(test_idx)}", flush=True)
    base = np.concatenate([rd.extract_features(paths, b, ROOT / f"data/processed/features_{b}_224")
                           for b in BACKBONES], axis=1).astype(np.float32)
    feats = {"base": base}
    for v in VARIANTS:
        f = base.copy()
        f[test_idx] = variant_features([paths[i] for i in test_idx], v).astype(np.float32)
        feats[v] = f
        print(f"  caratteristiche pronte: {v}", flush=True)
    dim = base.shape[1]
    groups = {"disease": list(range(len(field))), "plant": list(range(len(field))),
              "pest": list(range(len(field), len(sub)))}
    results = {}
    for head, idx in groups.items():
        rr = [sub[i] for i in idx]
        hd = {k: rd.prepare_head(rr, f[idx], head) for k, f in feats.items()}
        res = {"base": evaluate(hd["base"], hd["base"], dim, seeds=(0, 1, 2))}
        print(f"{head:8s} base               {res['base']}", flush=True)
        models = [ir.fit(hd["base"], dim, seed, ir.FIELD) for seed in (0, 1, 2)]
        for v in VARIANTS:
            accs = []
            for m in models:
                with torch.no_grad():
                    p = m(hd[v].X["test"]).argmax(1).numpy()
                y = hd[v].y["test"].numpy(); src = np.array(hd[v].sources["test"])
                a = {s: float((p[src == s] == y[src == s]).mean()) for s in sorted(set(src))}
                a["tutto"] = float((p == y).mean())
                accs.append(a)
            res[v] = {k: round(float(np.mean([a[k] for a in accs])), 4) for k in accs[0]}
            print(f"{head:8s} {v:18s} {res[v]}", flush=True)
        results[head] = res
        json.dump(results, open(ROOT / "models/exp_colore.json", "w"), indent=1, ensure_ascii=False)
    print("FATTO", flush=True)


if __name__ == "__main__":
    main()
