"""Preparazione della botte: proporzioni verificabili a mano, controlli e regole."""

import pytest

from plantcare.sprayer import Product, SprayerError, as_dict, compute_tank


def amounts(res):
    return {p["name"]: (p["amount"]["value"], p["amount"]["unit"]) for p in res.products}


def test_dose_per_hectolitre():
    # 200 g/hl in 1000 l = 10 hl x 200 g = 2000 g = 2 kg
    res = compute_tank(1000, [Product("A", 200, "g/hl", "WG")])
    assert amounts(res)["A"] == (2.0, "kg")


def test_dose_per_hectare_and_area():
    # 2 kg/ha, 1000 l/ha, botte da 600 l: 0,6 ha e 1,2 kg
    res = compute_tank(600, [Product("B", 2, "kg/ha", "WP")], water_l_ha=1000)
    assert res.area_ha == 0.6
    assert amounts(res)["B"] == (1.2, "kg")


def test_percentage_dose():
    # 0,5% in 400 l = 2 l
    res = compute_tank(400, [Product("Olio", 0.5, "%", "EC", "olio_minerale")])
    assert amounts(res)["Olio"] == (2.0, "l")


def test_per_hectare_without_water_volume_is_an_error():
    res = compute_tank(500, [Product("C", 1, "l/ha", "SC")])
    assert res.errors and "volume d'acqua" in res.errors[0]
    assert res.products == []


def test_dose_above_label_maximum_is_blocked():
    res = compute_tank(1000, [Product("D", 300, "g/hl", "WG", label_max=250)])
    assert any("supera la dose massima" in e for e in res.errors)
    assert res.products[0]["over_label"] is True


def test_invalid_inputs_raise():
    with pytest.raises(SprayerError):
        compute_tank(0, [Product("E", 1, "g/hl")])
    with pytest.raises(SprayerError):
        compute_tank(100, [Product("E", -1, "g/hl")])
    with pytest.raises(SprayerError):
        compute_tank(100, [Product("E", 1, "g/m2")])


def test_copper_balance_against_disciplinare_limit():
    # 3 kg/ha di prodotto con 200 g di rame per kg = 0,6 kg Cu/ha; con 3,6 già fatti = 4,2 > 4
    res = compute_tank(1000, [Product("Rame", 3, "kg/ha", "WG", "rame", copper_g_per_unit=200)],
                       water_l_ha=1000, copper_already_kg_ha=3.6)
    assert res.copper_kg_ha == 0.6
    w = [x for x in res.warnings if "rame" in x["text"].lower()][0]
    assert w["level"] == "attenzione" and "disc_calabria_2023" in w["sources"]


def test_sulfur_and_mineral_oil_are_flagged():
    res = compute_tank(1000, [Product("Zolfo", 300, "g/hl", "WG", "zolfo"),
                              Product("Olio", 1, "%", "EC", "olio_minerale")])
    inc = [w for w in res.warnings if w["level"] == "incompatibile"]
    assert inc and "er_manuale_zolfo" in inc[0]["sources"]


def test_loading_order_and_fosetyl_rule():
    res = compute_tank(1000, [Product("Emulsionabile", 100, "ml/hl", "EC"),
                              Product("Fosetil", 250, "g/hl", "WG", "fosetil_al"),
                              Product("Sospensione", 100, "ml/hl", "SC")])
    names = [o["name"] for o in res.order]
    assert names[0] == "Sospensione"  # con fosetil-Al gli SC vanno per primi
    assert names.index("Fosetil") < names.index("Emulsionabile")  # secchi prima degli EC
    assert any(w["level"] == "ordine" for w in res.warnings)


def test_temperature_warning_for_sulfur():
    res = compute_tank(500, [Product("Zolfo", 300, "g/hl", "WG", "zolfo")], temperature_c=33)
    assert any("30" in w["text"] for w in res.warnings)
    assert as_dict(res)["legal_note"].startswith("Le dosi")


def test_tank_api():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from plantcare.api import create_app
    client = TestClient(create_app(None))
    opts = client.get("/api/botte/opzioni").json()
    assert "g/hl" in opts["units"] and opts["categories"]
    r = client.post("/api/botte", json={"tank_l": 1000, "products": [
        {"name": "A", "dose": 200, "unit": "g/hl", "formulation": "WG"}]})
    assert r.status_code == 200 and r.json()["products"][0]["amount"] == {"value": 2.0, "unit": "kg"}
    assert r.json()["sources"]
    bad = client.post("/api/botte", json={"tank_l": -5, "products": [{"name": "A", "dose": 1, "unit": "g/hl"}]})
    assert bad.status_code == 422
