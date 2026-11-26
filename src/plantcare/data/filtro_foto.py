"""Filtro "foto di campo" con CLIP (zero-shot): tiene foto di piante, frutti, insetti e sintomi; scarta
grafici, alberi filogenetici, colture in piastra, microscopio, mappe, pagine di testo, loghi, locandine,
persone in aula. Serve per le immagini estratte da PDF, siti e articoli, prima della verifica a vista.

Uso: from plantcare.data.filtro_foto import punteggi; punteggi([percorsi]) -> lista di (p_campo, etichetta)
"""
from __future__ import annotations

from functools import lru_cache

import torch
from PIL import Image

CAMPO = [
    "a close-up photo of a plant leaf with disease symptoms",
    "a photo of diseased plant leaves",
    "a photo of a diseased fruit",
    "a photo of a tree branch or trunk with a canker",
    "a photo of an orchard or a vineyard",
    "a photo of a wilted or dying tree",
    "a photo of an insect on a plant",
    "a close-up photo of an insect",
    "a photo of insect larvae or caterpillars",
    "a photo of a bunch of grapes",
    "a photo of olives on a branch",
    "a photo of citrus fruits on a tree",
    "a photo of a cut branch showing discolored wood",
]
ALTRO = [
    "a microscope image of fungal spores",
    "a petri dish with a fungal culture",
    "a bar chart",
    "a line graph",
    "a phylogenetic tree diagram",
    "a map",
    "a page of text",
    "a table",
    "a logo",
    "a poster with text",
    "people in a meeting room",
    "a diagram or drawing",
    "laboratory equipment",
    "an electron microscope image",
    "a gel electrophoresis image",
    "a yellow sticky trap",
    "a pesticide bottle",
]


@lru_cache(maxsize=1)
def _model():
    import open_clip
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    tok = open_clip.get_tokenizer("ViT-B-32")
    model.eval()
    with torch.no_grad():
        t = model.encode_text(tok(CAMPO + ALTRO))
        t = t / t.norm(dim=-1, keepdim=True)
    return model, preprocess, t


def punteggi(paths, batch: int = 32) -> list[tuple[float, str]]:
    """Per ogni immagine: probabilità totale delle descrizioni "di campo" e descrizione più probabile."""
    model, preprocess, text = _model()
    labels = CAMPO + ALTRO
    out = []
    for i in range(0, len(paths), batch):
        ims, ok = [], []
        for p in paths[i:i + batch]:
            try:
                with Image.open(p) as im:
                    ims.append(preprocess(im.convert("RGB")))
                ok.append(True)
            except Exception:
                ok.append(False)
        probs = []
        if ims:
            with torch.no_grad():
                f = model.encode_image(torch.stack(ims))
                f = f / f.norm(dim=-1, keepdim=True)
                probs = (100.0 * f @ text.T).softmax(dim=-1)
        k = 0
        for good in ok:
            if not good:
                out.append((0.0, "illeggibile"))
                continue
            pr = probs[k]
            k += 1
            out.append((float(pr[:len(CAMPO)].sum()), labels[int(pr.argmax())]))
    return out
