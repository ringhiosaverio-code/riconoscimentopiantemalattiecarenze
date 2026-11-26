"""Preparazione della botte: proporzioni delle dosi, ordine di caricamento, compatibilità.

È un calcolatore deterministico, non una rete neurale: una dose deve essere esatta e ricondotta
all'etichetta del prodotto registrato, che prevale sempre. Le dosi le inserisce l'utente
dall'etichetta; la botte non suggerisce prodotti né dosi.

Unità di dose supportate:
    per ettolitro : "g/hl", "ml/hl"
    per ettaro    : "g/ha", "kg/ha", "ml/ha", "l/ha"   (serve il volume d'acqua per ettaro)
    percentuale   : "%"                              (concentrazione nella miscela)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).resolve().parents[2] / "configs" / "mixing_rules.yaml"
PER_HL = {"g/hl": "g", "ml/hl": "ml"}
PER_HA = {"g/ha": ("g", 1.0), "kg/ha": ("g", 1000.0), "ml/ha": ("ml", 1.0), "l/ha": ("ml", 1000.0)}
UNITS = set(PER_HL) | set(PER_HA) | {"%"}

LEGAL_NOTE = (
    "Le dosi, i limiti d'impiego, gli intervalli di sicurezza e le compatibilità sono quelli dell'etichetta "
    "autorizzata del prodotto, che prevale su qualunque calcolo. L'uso professionale di prodotti fitosanitari "
    "richiede il certificato di abilitazione (D.Lgs. 150/2012) e i dispositivi di protezione indicati in etichetta."
)


class SprayerError(ValueError):
    """Dati di input non validi."""


@dataclass
class Product:
    name: str
    dose: float
    unit: str
    formulation: str = "OTHER"
    category: str = "altro"
    label_max: float | None = None          # dose massima in etichetta, stessa unità di `unit`
    copper_g_per_unit: float | None = None  # g di rame metallo per kg o per L di prodotto
    label_max_ha: dict | None = None        # dose massima a ettaro in etichetta: {"value": 4, "unit": "l/ha"}


@dataclass
class TankResult:
    products: list[dict[str, Any]] = field(default_factory=list)
    order: list[dict[str, Any]] = field(default_factory=list)
    order_sources: list[str] = field(default_factory=list)
    area_ha: float | None = None
    copper_kg_ha: float | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    procedure: list[dict[str, Any]] = field(default_factory=list)
    legal_note: str = LEGAL_NOTE


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _fmt(value: float, unit: str) -> dict[str, Any]:
    """Quantità leggibile: grammi o millilitri, convertiti in kg o litri sopra i 1000."""
    if value >= 1000:
        return {"value": round(value / 1000, 3), "unit": "kg" if unit == "g" else "l"}
    return {"value": round(value, 1), "unit": unit}


def compute_tank(tank_l: float, products: list[Product], water_l_ha: float | None = None,
                 temperature_c: float | None = None, copper_already_kg_ha: float | None = None,
                 rules: dict | None = None) -> TankResult:
    rules = rules or load_rules()
    res = TankResult()
    if tank_l <= 0:
        raise SprayerError("Il volume della botte deve essere maggiore di zero.")
    if water_l_ha is not None and water_l_ha <= 0:
        raise SprayerError("Il volume d'acqua per ettaro deve essere maggiore di zero.")
    if not products:
        raise SprayerError("Inserire almeno un prodotto.")
    if water_l_ha:
        res.area_ha = round(tank_l / water_l_ha, 4)

    copper_g_ha = 0.0
    for p in products:
        if p.unit not in UNITS:
            raise SprayerError(f"{p.name}: unità di dose non valida ({p.unit}).")
        if p.dose <= 0:
            raise SprayerError(f"{p.name}: la dose deve essere maggiore di zero.")
        row: dict[str, Any] = {"name": p.name, "dose": p.dose, "unit": p.unit, "formulation": p.formulation,
                               "category": p.category}
        per_ha_amount = None  # quantità di prodotto per ettaro, in g o ml
        if p.unit in PER_HL:
            base = PER_HL[p.unit]
            amount = p.dose * tank_l / 100.0
            if water_l_ha:
                per_ha_amount = p.dose * water_l_ha / 100.0
        elif p.unit == "%":
            base = "ml" if p.formulation not in ("WG", "WP", "SG", "WSB") else "g"
            amount = p.dose / 100.0 * tank_l * 1000.0  # 1% di 1 L = 10 ml (o 10 g)
            if water_l_ha:
                per_ha_amount = p.dose / 100.0 * water_l_ha * 1000.0
        else:
            base, factor = PER_HA[p.unit]
            if not water_l_ha:
                res.errors.append(f"{p.name}: la dose è per ettaro, serve il volume d'acqua per ettaro per calcolarla.")
                continue
            per_ha_amount = p.dose * factor
            amount = per_ha_amount * tank_l / water_l_ha
        row["amount"] = _fmt(amount, base)
        if per_ha_amount is not None:
            row["per_ha"] = _fmt(per_ha_amount, base)
        if p.label_max is not None and p.dose > p.label_max:
            res.errors.append(f"{p.name}: la dose {p.dose} {p.unit} supera la dose massima di etichetta "
                              f"({p.label_max} {p.unit}). Non preparare la botte con questa dose.")
            row["over_label"] = True
        mh = p.label_max_ha
        if mh and per_ha_amount is not None and mh.get("unit") in PER_HA and PER_HA[mh["unit"]][0] == base:
            max_amount = mh["value"] * PER_HA[mh["unit"]][1]
            if per_ha_amount > max_amount * 1.0001:
                res.errors.append(f"{p.name}: con {water_l_ha:g} l/ha di acqua si distribuiscono {_fmt(per_ha_amount, base)['value']} "
                                  f"{_fmt(per_ha_amount, base)['unit']}/ha, più della dose massima di etichetta "
                                  f"({mh['value']:g} {mh['unit']}). Riduci la dose per ettolitro o il volume d'acqua.")
                row["over_label"] = True
        if p.category == "rame" and p.copper_g_per_unit and per_ha_amount is not None:
            copper_g_ha += per_ha_amount / 1000.0 * p.copper_g_per_unit  # kg (o L) di prodotto × g Cu/unità
        res.products.append(row)

    # rame
    if copper_g_ha:
        c = rules["copper"]
        res.copper_kg_ha = round(copper_g_ha / 1000.0, 3)
        total = res.copper_kg_ha + (copper_already_kg_ha or 0.0)
        msg = (f"Questo trattamento apporta {res.copper_kg_ha} kg/ha di rame metallo"
               + (f"; con quelli già fatti quest'anno si arriva a {round(total, 3)} kg/ha." if copper_already_kg_ha else ".")
               + " " + c["text"])
        level = "attenzione" if total > c["avg_year_kg_ha"] else "info"
        res.warnings.append({"level": level, "text": msg, "sources": c["sources"]})

    # compatibilità tra categorie
    cats = {p.category for p in products}
    for rule in rules["pairs"]:
        a, b = rule["categories"]
        if a in cats and b in cats:
            res.warnings.append({"level": "incompatibile", "text": rule["text"], "sources": rule["sources"]})

    # temperatura
    if temperature_c is not None:
        for t in rules["temperature"]:
            if t["category"] in cats and temperature_c >= t["max_c"]:
                res.warnings.append({"level": "attenzione", "text": t["text"], "sources": t["sources"]})

    # ordine di caricamento
    order_ids = [f["id"] for f in rules["formulation_order"]["order"]]
    labels = {f["id"]: f["label"] for f in rules["formulation_order"]["order"]}
    first: set[str] = set()
    for r in rules.get("order_rules", []):
        if r["when_category"] in cats:
            first |= set(r["move_first_formulations"])
            if any(p.formulation in first for p in products):
                res.warnings.append({"level": "ordine", "text": r["text"], "sources": r["sources"]})

    def key(p: Product):
        f = p.formulation if p.formulation in order_ids else "OTHER"
        return (0 if f in first else 1, order_ids.index(f))

    for i, p in enumerate(sorted(products, key=key), start=1):
        res.order.append({"step": i, "name": p.name, "formulation": labels.get(p.formulation, p.formulation)})
    res.order_sources = rules["formulation_order"]["sources"]
    res.procedure = rules["procedure"]
    return res


def as_dict(res: TankResult) -> dict[str, Any]:
    return {
        "products": res.products,
        "order": res.order,
        "order_sources": res.order_sources,
        "area_ha": res.area_ha,
        "copper_kg_ha": res.copper_kg_ha,
        "warnings": res.warnings,
        "errors": res.errors,
        "procedure": res.procedure,
        "legal_note": res.legal_note,
    }
