"""Disciplinare: le sostanze degli insetti degli agrumi e dell'olivo (tabelle a 12 colonne nel PDF) sono lette."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = json.load(open(ROOT / "app" / "data" / "difesa.json"))


def sostanze(label):
    e = D["classi"]["pest|" + label]
    return {s["s"] for k in e for i in e[k]["r"] for s in D["righe"][i]["sostanze"]}


def test_aleurodidi_agrumi_hanno_sostanze_e_ausiliari():
    s = sostanze("inat:aleurothrixus_floccosus")
    assert {"Olio minerale", "Acetamiprid", "Flupyradifurone", "Cales noacki"} <= s
    assert {"Encarsia lahorensis", "Pyridaben"} <= sostanze("inat:dialeurodes_citri")


def test_ausiliari_classificati_come_biologici():
    e = D["classi"]["pest|inat:aleurothrixus_floccosus"]
    t = {s["s"]: s["t"] for k in e for i in e[k]["r"] for s in D["righe"][i]["sostanze"]}
    assert t["Cales noacki"] == "biologico" and t["Azadaractina"] == "naturale" and t["Acetamiprid"] == "sintesi"


def test_gruppi_irac_disponibili():
    assert any("acetamiprid" in k for k in D["irac"])
