"""Ipotesi con garanzia di copertura (predizione conforme).

Al posto di una sola risposta si dà l'elenco più corto di ipotesi che, sulle foto di calibrazione
(mai usate per addestrare), contiene la risposta giusta almeno nella frazione 1 - alpha dei casi.
La garanzia vale per foto simili a quelle di calibrazione (scambiabilità): per foto molto diverse è
una stima, da verificare con le foto dei contributi.

Riferimenti:
  Sadinle, Lei, Wasserman (2019) JASA 114:223-234: soglia sulle probabilità (LAC), insiemi più corti.
  Romano, Sesia, Candès (2020) NeurIPS: insiemi adattivi (APS), più lunghi sulle foto difficili.
  Angelopoulos, Bates, Malik, Jordan (2021) ICLR, arXiv 2009.14193: RAPS e guida pratica.
"""
from __future__ import annotations

import numpy as np


def quantile(scores: np.ndarray, alpha: float) -> float:
    """Quantile conforme: il k-esimo punteggio con k = ceil((n+1)(1-alpha))."""
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    return float("inf") if k > n else float(np.sort(scores)[k - 1])


def lac_scores(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return 1.0 - p[np.arange(len(y)), y]


def lac_sets(p: np.ndarray, q: float) -> np.ndarray:
    s = p >= 1.0 - q
    s[np.arange(len(p)), p.argmax(1)] = True  # almeno la prima ipotesi
    return s


def aps_scores(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    order = np.argsort(-p, 1)
    cum = np.take_along_axis(p, order, 1).cumsum(1)
    rank = np.argmax(order == y[:, None], 1)
    return cum[np.arange(len(y)), rank]


def aps_sets(p: np.ndarray, q: float) -> np.ndarray:
    """Classi in ordine di probabilità finché la somma raggiunge q (inclusa quella che la supera)."""
    order = np.argsort(-p, 1)
    sp = np.take_along_axis(p, order, 1)
    keep = (sp.cumsum(1) - sp) < q
    keep[:, 0] = True
    s = np.zeros_like(p, dtype=bool)
    np.put_along_axis(s, order, keep, 1)
    return s


METHODS = {"lac": (lac_scores, lac_sets), "aps": (aps_scores, aps_sets)}


def calibrate(p_cal: np.ndarray, y_cal: np.ndarray, alpha: float, method: str) -> float:
    return quantile(METHODS[method][0](p_cal, y_cal), alpha)


def prediction_sets(p: np.ndarray, q: float, method: str) -> np.ndarray:
    return METHODS[method][1](p, q)


def set_report(sets: np.ndarray, y: np.ndarray) -> dict:
    size = sets.sum(1)
    covered = sets[np.arange(len(y)), y]
    single = size == 1
    return {"n": int(len(y)), "copertura": float(covered.mean()), "dimensione_media": float(size.mean()),
            "dimensione_mediana": float(np.median(size)), "una_sola_ipotesi": float(single.mean()),
            "giuste_quando_una_sola": float(covered[single].mean()) if single.any() else None}


def group_probs(p: np.ndarray, groups: list[str]) -> tuple[np.ndarray, list[str]]:
    """Somma le probabilità delle classi per gruppo (per esempio per causa: fungo, batterio, virus...)."""
    names = sorted(set(groups))
    idx = np.array([names.index(g) for g in groups])
    out = np.zeros((len(p), len(names)), dtype=p.dtype)
    for j in range(len(names)):
        out[:, j] = p[:, idx == j].sum(1)
    return out, names


def selective_threshold(p_val: np.ndarray, y_val: np.ndarray, target: float = 0.99, min_n: int = 50) -> float:
    """Soglia di confidenza più bassa per cui, sulla validazione, le risposte date sono giuste almeno
    nella frazione `target` (contando solo soglie con almeno `min_n` risposte)."""
    conf = p_val.max(1)
    ok = p_val.argmax(1) == y_val
    order = np.argsort(-conf)
    acc = np.cumsum(ok[order]) / np.arange(1, len(ok) + 1)
    good = np.nonzero(acc[min_n - 1:] >= target)[0]
    if not len(good):
        return 1.01  # nessuna soglia raggiunge l'obiettivo: mai "risposta sicura"
    return float(conf[order][min_n - 1 + good.max()])
