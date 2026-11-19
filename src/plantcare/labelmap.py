"""Mappatura etichetta grezza del dataset -> id della tassonomia (configs/label_maps.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml

from plantcare.taxonomy import DEFAULT_TAXONOMY_PATH, Taxonomy

DEFAULT_MAP_PATH = Path(__file__).resolve().parents[2] / "configs" / "label_maps.yaml"


def load_label_map(path: Path | str = DEFAULT_MAP_PATH, taxonomy: Taxonomy | None = None) -> dict[str, dict[str, str]]:
    """Carica la mappatura e verifica che ogni id di destinazione esista nella tassonomia."""
    from plantcare.taxonomy import load_taxonomy

    tax = taxonomy or load_taxonomy(DEFAULT_TAXONOMY_PATH)
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    errors = []
    for source, mapping in raw.items():
        for raw_label, target in (mapping or {}).items():
            if target not in tax.diseases and target not in tax.insects:
                errors.append(f"{source}:{raw_label} -> '{target}' non presente in taxonomy")
    if errors:
        raise ValueError("Mappatura non valida:\n  - " + "\n  - ".join(errors))
    return raw


def map_label(source_map: dict[str, str], raw_label: str) -> str | None:
    """Restituisce l'id di tassonomia o None se la classe non è mappata."""
    return source_map.get(raw_label)
