"""Metriche: per classe, macro-F1, calibrazione (ECE) e copertura vs accuratezza."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    labels = np.unique(y_true)
    return float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))


def per_class_report(y_true: np.ndarray, y_pred: np.ndarray, names: list[str]) -> dict:
    labels = list(range(len(names)))
    present = sorted(set(np.unique(y_true)) | set(np.unique(y_pred)))
    return classification_report(
        y_true, y_pred,
        labels=present,
        target_names=[names[i] for i in present],
        output_dict=True,
        zero_division=0,
    )


def confusion(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> np.ndarray:
    return confusion_matrix(y_true, y_pred, labels=list(range(n_classes)))


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> float:
    """ECE: differenza media tra confidenza e accuratezza, pesata per bin.

    probs: (N, C) probabilità; labels: (N,) indici veri.
    Un valore basso significa che una probabilità dell'80% corrisponde davvero a circa l'80% di risposte corrette.
    """
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == labels).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def coverage_accuracy(probs: np.ndarray, labels: np.ndarray, thresholds: list[float]) -> list[dict[str, float]]:
    """Per ogni soglia: quota di foto a cui il sistema risponde (copertura) e accuratezza su quelle.

    Sotto soglia il sistema risponde "non determinabile". Permette di scegliere la soglia
    in base al compromesso tra risposte date e affidabilità.
    """
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    out = []
    for t in thresholds:
        answered = conf >= t
        cov = float(answered.mean())
        acc = float((pred[answered] == labels[answered]).mean()) if answered.any() else float("nan")
        out.append({"threshold": t, "coverage": cov, "accuracy_on_answered": acc})
    return out
