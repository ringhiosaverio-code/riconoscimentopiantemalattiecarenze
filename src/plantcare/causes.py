"""Causa (fungo, batterio, virus, insetto, acaro, ...) di ogni classe del lettore delle malattie."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATHOGEN_TO_CAUSE = {"fungal": "fungo", "bacterial": "batterio", "viral": "virus", "viroid": "viroide",
                     "insect_induced": "insetto", "healthy": "sano"}


def load_causes(path: Path | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """(etichette della causa, causa per classe)."""
    d = yaml.safe_load(open(path or ROOT / "configs" / "disease_causes.yaml", encoding="utf-8"))
    return d["causes"], d["labels"]


def cause_of(label: str, labels: dict[str, str], taxonomy=None, label_map: dict | None = None) -> str | None:
    if label in labels:
        return labels[label]
    tid = label if taxonomy is not None and label in taxonomy.diseases else (
        ((label_map or {}).get("plantvillage") or {}).get(label))
    if taxonomy is not None and tid in taxonomy.diseases:
        if tid in labels:
            return labels[tid]
        return PATHOGEN_TO_CAUSE.get(taxonomy.diseases[tid].get("pathogen_type"))
    return None
