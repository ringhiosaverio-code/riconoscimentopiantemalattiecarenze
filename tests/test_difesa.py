"""Collegamento diagnosi -> norme di difesa (Disciplinare Calabria) e usi registrati dei prodotti."""
import json
from pathlib import Path

from plantcare import difesa as df

ROOT = Path(__file__).resolve().parents[1]


def test_nomi_scientifici_e_sinonimi():
    syn = df._syn()
    assert df.keys_in("Oidio (Uncinula necator – Oidium tuckeri)", syn) == {"erysiphe necator"}
    assert df.keys_in("Marciume nero della vite", syn) == set()  # parole italiane, non nomi latini
    assert "tomato yellow leaf curl virus" in df.keys_in("(CMV, PVY, ToMV TYLCV TSWV)", syn)
    assert df.keys_in("Afidi (Aphis spp.)", syn) == {"aphis *"}
    assert df._match({"aphis gossypii"}, {"aphis *"})


def test_tipo_sostanza():
    assert df.tipo_sostanza("Bacillus amyloliquefaciens") == "biologico"
    assert df.tipo_sostanza("Prodotti rameici") == "naturale"
    assert df.tipo_sostanza("Zolfo") == "naturale"
    assert df.tipo_sostanza("Mandipropamide") == "sintesi"


def test_disciplinare_letto():
    d = df.load_disciplinare(2026)
    olivo = [r for r in d["righe"] if r["coltura"] == "OLIVO"]
    assert any("bactrocera oleae" in r["chiavi"] for r in olivo)
    vite = [r for r in d["righe"] if r["coltura"] == "VITE DA VINO" and "plasmopara viticola" in r["chiavi"]]
    assert vite and any(s["sostanza"].lower().startswith("prodotti rameici") for s in vite[0]["sostanze"])


def test_dati_app_coerenti():
    p = ROOT / "app" / "data" / "difesa.json"
    if not p.exists():
        return
    d = json.load(open(p, encoding="utf-8"))
    for key, per in d["classi"].items():
        assert key.split("|")[0] in ("disease", "pest")
        for ent in per.values():
            assert all(0 <= i < len(d["righe"]) for i in ent["r"])
            assert all(0 <= i < len(d["usi"]) for i in ent["u"])
    assert all(u["prodotto"] and u["pagina"].startswith("https://gowanitalia.it/") for u in d["usi"])
