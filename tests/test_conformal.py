"""Ipotesi calibrate (predizione conforme) e indicazioni sul laboratorio."""
from pathlib import Path

import numpy as np
import yaml

from plantcare import conformal as cf

ROOT = Path(__file__).resolve().parents[1]


def _toy(n, k=12, seed=0):
    """Probabilità rumorose ma informative: la classe giusta ha in media più probabilità."""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, k, n)
    logits = rng.normal(0, 1.0, (n, k))
    logits[np.arange(n), y] += 1.8
    p = np.exp(logits)
    return p / p.sum(1, keepdims=True), y


def test_quantile_conforme():
    s = np.arange(1, 101) / 100.0
    assert cf.quantile(s, 0.1) == s[int(np.ceil(101 * 0.9)) - 1]
    assert cf.quantile(s[:10], 0.01) == float("inf")  # troppo poche foto per il 99%


def test_copertura_garantita_lac_e_aps():
    p_cal, y_cal = _toy(3000, seed=1)
    p_test, y_test = _toy(3000, seed=2)
    for method in ("lac", "aps"):
        for alpha in (0.1, 0.05):
            q = cf.calibrate(p_cal, y_cal, alpha, method)
            rep = cf.set_report(cf.prediction_sets(p_test, q, method), y_test)
            assert rep["copertura"] >= 1 - alpha - 0.02, (method, alpha, rep)
            assert rep["dimensione_media"] >= 1


def test_insiemi_contengono_sempre_la_prima_ipotesi():
    p, _ = _toy(200)
    for method in ("lac", "aps"):
        sets = cf.prediction_sets(p, 0.0, method)
        assert sets[np.arange(len(p)), p.argmax(1)].all()


def test_probabilita_per_causa():
    p = np.array([[0.5, 0.2, 0.3]])
    g, names = cf.group_probs(p, ["fungo", "virus", "fungo"])
    assert names == ["fungo", "virus"]
    assert np.allclose(g, [[0.8, 0.2]])


def test_risposta_sicura_rispetta_l_obiettivo_in_calibrazione():
    p, y = _toy(4000, seed=3)
    tau = cf.selective_threshold(p, y, target=0.95, min_n=50)
    ans = p.max(1) >= tau
    assert ans.sum() >= 50
    assert (p.argmax(1)[ans] == y[ans]).mean() >= 0.95


def test_laboratorio_fonti_e_organismi():
    lab = yaml.safe_load(open(ROOT / "configs" / "lab_requirements.yaml", encoding="utf-8"))
    sources = {s["id"] for s in yaml.safe_load(open(ROOT / "configs" / "sources.yaml", encoding="utf-8"))["sources"]}
    causes = yaml.safe_load(open(ROOT / "configs" / "disease_causes.yaml", encoding="utf-8"))["causes"]
    for c, v in lab["analisi_per_causa"].items():
        assert c in causes, c
        assert v["quando"] in ("sempre", "se_dubbio")
        assert v["fonti"] and all(f in sources for f in v["fonti"]), c
    for o in lab["organismi_regolamentati"]:
        assert o["tipo"] in ("quarantena", "rnqp", "eppo")
        assert o["eppo"].isupper() and 5 <= len(o["eppo"]) <= 6
        assert set(o["classi"]) <= {"disease", "pest"} and all(o["classi"].values())
        if o["tipo"] == "quarantena":
            assert "2019/2072" in o["ue"]
