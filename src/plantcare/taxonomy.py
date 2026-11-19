"""Caricamento e validazione della tassonomia (configs/taxonomy.yaml).

La tassonomia è la fonte unica di verità per:
- le classi del modello (specie, malattie, insetti, carenze);
- le etichette mostrate all'utente;
- i riferimenti incrociati (una malattia deve puntare a specie e tipo di agente esistenti).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "configs" / "taxonomy.yaml"

INSECT_ROLES = {"phytophagous", "entomophagous", "pollinator", "neutral"}
PLANT_PRIORITIES = {1, 2, 3}
NUTRIENT_CLASSES = {"macro", "micro"}


class TaxonomyError(ValueError):
    """La tassonomia non è coerente."""


@dataclass
class Taxonomy:
    version: str
    plants: dict[str, dict[str, Any]]
    pathogen_types: dict[str, dict[str, Any]]
    diseases: dict[str, dict[str, Any]]
    insects: dict[str, dict[str, Any]]
    macro_nutrients: dict[str, dict[str, Any]]
    micro_nutrients: dict[str, dict[str, Any]]
    unknown_nutrient: dict[str, Any] = field(default_factory=dict)
    plant_organs: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- viste utili al modello ----
    def class_ids(self, group: str) -> list[str]:
        """Ids ordinati e stabili per un gruppo di classi (indice = output del modello)."""
        mapping = {
            "plants": self.plants,
            "diseases": self.diseases,
            "insects": self.insects,
            "pathogen_types": self.pathogen_types,
        }
        return sorted(mapping[group])

    def insects_by_role(self, role: str) -> list[str]:
        return sorted(i for i, v in self.insects.items() if v["role"] == role)


def _index(entries: list[dict[str, Any]], section: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if "id" not in entry:
            raise TaxonomyError(f"[{section}] voce senza 'id': {entry}")
        eid = entry["id"]
        if eid in out:
            raise TaxonomyError(f"[{section}] id duplicato: '{eid}'")
        out[eid] = entry
    return out


def load_taxonomy(path: Path | str = DEFAULT_TAXONOMY_PATH) -> Taxonomy:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    nutrients = raw.get("nutrients", {})
    tax = Taxonomy(
        version=str(raw.get("version", "0")),
        plants=_index(raw.get("plants", []), "plants"),
        pathogen_types=_index(raw.get("pathogen_types", []), "pathogen_types"),
        diseases=_index(raw.get("diseases", []), "diseases"),
        insects=_index(raw.get("insects", []), "insects"),
        macro_nutrients=_index(nutrients.get("macro", []), "nutrients.macro"),
        micro_nutrients=_index(nutrients.get("micro", []), "nutrients.micro"),
        unknown_nutrient=nutrients.get("unknown", {}),
        plant_organs=_index(raw.get("plant_organs", []), "plant_organs"),
    )
    validate(tax)
    return tax


def validate(tax: Taxonomy) -> None:
    """Controlla i riferimenti incrociati. Solleva TaxonomyError al primo problema raccolto."""
    errors: list[str] = []

    for dis_id, dis in tax.diseases.items():
        if dis.get("pathogen_type") not in tax.pathogen_types:
            errors.append(f"malattia '{dis_id}': pathogen_type sconosciuto '{dis.get('pathogen_type')}'")
        for host in dis.get("hosts", []):
            if host not in tax.plants:
                errors.append(f"malattia '{dis_id}': ospite sconosciuto '{host}'")

    for ins_id, ins in tax.insects.items():
        if ins.get("role") not in INSECT_ROLES:
            errors.append(f"insetto '{ins_id}': ruolo non valido '{ins.get('role')}'")

    for dis_id, dis in tax.diseases.items():
        organs = dis.get("organs", [])
        if tax.plant_organs:
            for o in organs:
                if o not in tax.plant_organs:
                    errors.append(f"malattia '{dis_id}': organo sconosciuto '{o}'")
            for o in dis.get("organ_symptoms", {}):
                if o not in organs:
                    errors.append(f"malattia '{dis_id}': sintomo su organo '{o}' non dichiarato in organs")
        if not organs:
            errors.append(f"malattia '{dis_id}': manca l'elenco degli organi colpiti")

    for plant_id, plant in tax.plants.items():
        if plant.get("priority") not in PLANT_PRIORITIES:
            errors.append(f"coltura '{plant_id}': priority deve essere 1, 2 o 3")

    # Ogni specie di malattia deve avere un agente o essere la classe 'sana'.
    for dis_id, dis in tax.diseases.items():
        if dis.get("agent") is None and dis.get("pathogen_type") != "healthy":
            errors.append(f"malattia '{dis_id}': manca l'agente causale")

    if errors:
        raise TaxonomyError("Tassonomia non valida:\n  - " + "\n  - ".join(errors))
