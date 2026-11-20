"""App statica (GitHub Pages): coerenza tra dati, modello e calcolatore JavaScript."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
pytestmark = pytest.mark.skipif(not (APP / "data" / "readers.json").exists(), reason="app/ non costruita")


def test_index_loads_app_scripts_and_hides_hidden_elements():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    for src in ("app/ort/ort.wasm.min.js", "app/sprayer.js", "app/app.js"):
        assert src in html and (ROOT / src).exists()
    assert "[hidden]{display:none!important}" in html
    assert "onclick=" not in html


def test_reader_classes_match_model_outputs():
    ort = pytest.importorskip("onnxruntime")
    readers = json.load(open(APP / "data" / "readers.json", encoding="utf-8"))
    sess = ort.InferenceSession(str(APP / "model" / "plantcare.onnx"))
    outputs = {o.name: o.shape[1] for o in sess.get_outputs()}
    assert set(outputs) == {"plant", "disease", "deficiency"}  # niente lettore IP102 nella versione pubblica
    for head, n in outputs.items():
        assert len(readers[head]["classes"]) == n


def test_quiz_uses_only_republishable_sources():
    quiz = json.load(open(APP / "data" / "quiz.json", encoding="utf-8"))
    assert quiz and all(("PlantDoc" in q["credit"]) or ("Project-AgML" in q["credit"]) for q in quiz)
    assert all((APP / "quiz" / q["img"]).exists() for q in quiz)


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_js_sprayer_matches_python():
    from plantcare.sprayer import Product, as_dict, compute_tank
    cases = [
        (1000, None, None, None, [dict(name="A", dose=200, unit="g/hl", formulation="WG")]),
        (600, 1000, None, None, [dict(name="B", dose=2, unit="kg/ha", formulation="WP")]),
        (1000, 1000, 33, 3.6, [dict(name="Cu", dose=3, unit="kg/ha", formulation="WG", category="rame", copper_g_per_unit=200),
                               dict(name="Z", dose=300, unit="g/hl", formulation="WG", category="zolfo"),
                               dict(name="O", dose=1, unit="%", formulation="EC", category="olio_minerale")]),
    ]
    for tank, water, temp, cu, prods in cases:
        py = as_dict(compute_tank(tank, [Product(**p) for p in prods], water, temp, cu))
        js_prods = [{"formulation": "OTHER", "category": "altro", "label_max": None, "copper_g_per_unit": None, **p} for p in prods]
        script = (f"const S=require({json.dumps(str(APP / 'sprayer.js'))});"
                  f"const r=require({json.dumps(str(APP / 'data' / 'mixing_rules.json'))});"
                  f"console.log(JSON.stringify(S.computeTank({tank},{json.dumps(js_prods)},{json.dumps(water)},"
                  f"{json.dumps(temp)},{json.dumps(cu)},r)))")
        js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
        for key in ("products", "order", "area_ha", "copper_kg_ha", "warnings", "errors"):
            assert js[key] == py[key], key
