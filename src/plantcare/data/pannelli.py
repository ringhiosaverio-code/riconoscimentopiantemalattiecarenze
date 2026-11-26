"""Divide le figure composte (pannelli A, B, C...) lungo le righe e colonne di separazione uniformi.

Le figure degli articoli uniscono spesso foto di campo, micrografie e colture: separando i pannelli il
filtro CLIP può scartare i pannelli che non sono foto di campo e tenere gli altri.
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def _gutters(profile_std, profile_mean, min_gap):
    """Intervalli [a, b) di righe (o colonne) quasi uniformi, larghi almeno min_gap."""
    flat = (profile_std < 6) & ((profile_mean > 225) | (profile_mean < 30))
    out, start = [], None
    for i, f in enumerate(flat):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_gap:
                out.append((start, i))
            start = None
    if start is not None and len(flat) - start >= min_gap:
        out.append((start, len(flat)))
    return out


def _split(a, axis, min_gap):
    g = a.mean(axis=2)
    prof_std = g.std(axis=1 - axis) if axis == 0 else g.std(axis=0)
    prof_mean = g.mean(axis=1 - axis) if axis == 0 else g.mean(axis=0)
    cuts = _gutters(prof_std, prof_mean, min_gap)
    segs, prev = [], 0
    for s, e in cuts:
        if s > prev:
            segs.append((prev, s))
        prev = e
    if prev < a.shape[axis]:
        segs.append((prev, a.shape[axis]))
    return segs


def pannelli(im: Image.Image, min_side: int = 160, min_gap: int = 3, depth: int = 3) -> list[Image.Image]:
    """Pannelli della figura (la figura intera se non ci sono separazioni)."""
    a = np.asarray(im.convert("RGB"), dtype=np.float32)

    def rec(x0, y0, x1, y1, d):
        sub = a[y0:y1, x0:x1]
        if d == 0 or sub.shape[0] < 2 * min_side and sub.shape[1] < 2 * min_side:
            return [(x0, y0, x1, y1)]
        rows = _split(sub, 0, min_gap)
        if len(rows) > 1:
            return [b for (r0, r1) in rows for b in rec(x0, y0 + r0, x1, y0 + r1, d - 1)]
        cols = _split(sub, 1, min_gap)
        if len(cols) > 1:
            return [b for (c0, c1) in cols for b in rec(x0 + c0, y0, x0 + c1, y1, d - 1)]
        return [(x0, y0, x1, y1)]

    boxes = rec(0, 0, a.shape[1], a.shape[0], depth)
    out = [im.crop(b) for b in boxes if (b[2] - b[0]) >= min_side and (b[3] - b[1]) >= min_side]
    return out or [im]
