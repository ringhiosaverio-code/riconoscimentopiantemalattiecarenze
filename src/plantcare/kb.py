"""Base di conoscenza per agronomi: schede di malattie, insetti e carenze.

Le schede sono costruite dalla tassonomia (configs/taxonomy.yaml), la fonte unica di verità.
Ogni scheda dichiara se la diagnosi richiede conferma di laboratorio.
"""

from __future__ import annotations

from typing import Any

from plantcare.taxonomy import Taxonomy

LAB_REQUIRED_TYPES = {"viral", "viroid", "bacterial", "nematode"}

LAB_NOTE = (
    "Agente virale, viroide, batterico o nematodico: il sintomo visivo non basta. "
    "Conferma con analisi di laboratorio (ELISA, RT-PCR, sequenziamento o coltura) prima di decidere."
)


class KnowledgeBase:
    def __init__(self, taxonomy: Taxonomy):
        self.tax = taxonomy

    def plant_name(self, plant_id: str) -> str:
        p = self.tax.plants.get(plant_id)
        return p["common"] if p else plant_id

    def disease_card(self, disease_id: str) -> dict[str, Any] | None:
        d = self.tax.diseases.get(disease_id)
        if d is None:
            return None
        ptype = self.tax.pathogen_types.get(d["pathogen_type"], {})
        return {
            "id": d["id"],
            "name": d["common"],
            "agent": d.get("agent"),
            "pathogen_type": {"id": d["pathogen_type"], "label": ptype.get("label", d["pathogen_type"])},
            "hosts": [{"id": h, "name": self.plant_name(h)} for h in d.get("hosts", [])],
            "symptoms": d.get("symptoms", ""),
            "lab_confirmation_required": d["pathogen_type"] in LAB_REQUIRED_TYPES,
            "lab_note": LAB_NOTE if d["pathogen_type"] in LAB_REQUIRED_TYPES else None,
        }

    def insect_card(self, insect_id: str) -> dict[str, Any] | None:
        i = self.tax.insects.get(insect_id)
        if i is None:
            return None
        role_labels = {
            "phytophagous": "Fitofago (dannoso)",
            "entomophagous": "Entomofago (utile: predatore o parassitoide)",
            "pollinator": "Impollinatore (utile, da proteggere)",
            "neutral": "Altro",
        }
        return {
            "id": i["id"],
            "name": i["common"],
            "order": i.get("order"),
            "family": i.get("family"),
            "role": {"id": i["role"], "label": role_labels.get(i["role"], i["role"])},
            "note": i.get("note"),
        }

    def list_diseases(self, plant_id: str | None = None) -> list[dict[str, Any]]:
        out = []
        for d in self.tax.diseases.values():
            if plant_id and plant_id not in d.get("hosts", []):
                continue
            out.append(self.disease_card(d["id"]))
        return sorted(out, key=lambda c: c["name"])

    def list_plants(self, priority: int | None = None) -> list[dict[str, Any]]:
        out = []
        for p in self.tax.plants.values():
            if priority is not None and p.get("priority") != priority:
                continue
            out.append({"id": p["id"], "name": p["common"], "family": p.get("family"),
                        "priority": p.get("priority"), "zone": p.get("zone")})
        return sorted(out, key=lambda c: c["name"])

    def list_nutrients(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "macro": list(self._nutrients(self.tax.macro_nutrients)),
            "micro": list(self._nutrients(self.tax.micro_nutrients)),
        }

    @staticmethod
    def _nutrients(source: dict[str, dict[str, Any]]):
        for n in source.values():
            yield {"id": n["id"], "name": n["name"], "symptoms": n.get("symptoms", "")}
