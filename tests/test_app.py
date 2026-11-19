"""Test di interfaccia: schede per agronomi, feedback e collegamento alla tassonomia."""

import io
import json

import pytest
from PIL import Image

pytest.importorskip("torch")
pytest.importorskip("timm")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from plantcare.api import create_app  # noqa: E402
from plantcare.data.pipeline import scan_plantvillage, write_manifest  # noqa: E402
from plantcare.train import train  # noqa: E402


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    base = tmp_path_factory.mktemp("app")
    root = base / "raw"
    pv = root / "plantvillage"
    for cls, col in {"Tomato___Late_blight": (120, 90, 30), "Tomato___healthy": (40, 160, 60)}.items():
        for i in range(8):
            d = pv / cls
            d.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), col).save(d / f"{i}.png")
    rows = scan_plantvillage(pv, seed=0)
    for r in rows:
        r.path = f"plantvillage/{r.path}"
    manifest = base / "m.csv"
    write_manifest(rows, manifest)
    cfg = {
        "manifest": str(manifest), "data_root": str(root), "output_dir": str(base / "out"),
        "backbone": "resnet18", "pretrained": False, "image_size": 32, "batch_size": 8,
        "epochs": 1, "heads": ["plant", "disease"], "device": "cpu", "num_workers": 0,
    }
    return train(cfg).checkpoint


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), (10, 200, 10)).save(buf, format="PNG")
    return buf.getvalue()


def test_disease_cards_and_lab_flag(tmp_path):
    client = TestClient(create_app(None))
    cards = client.get("/api/diseases").json()
    assert any(c["id"] == "tomato_late_blight" for c in cards)
    virus = client.get("/api/diseases/tomato_mosaic_virus").json()
    assert virus["lab_confirmation_required"] is True
    fungal = client.get("/api/diseases/tomato_late_blight").json()
    assert fungal["lab_confirmation_required"] is False
    assert client.get("/api/diseases/inesistente").status_code == 404


def test_insect_and_nutrient_endpoints():
    client = TestClient(create_app(None))
    insects = client.get("/api/insects").json()
    roles = {i["role"]["id"] for i in insects}
    assert {"phytophagous", "entomophagous", "pollinator"} <= roles
    nut = client.get("/api/nutrients").json()
    assert any(n["id"] == "Fe" for n in nut["micro"])


def test_priority_filter_on_plants():
    client = TestClient(create_app(None))
    p2 = client.get("/api/plants", params={"priority": 2}).json()
    assert {p["id"] for p in p2} >= {"citrus_bergamia", "persea_americana"}


def test_feedback_disabled_without_dir(monkeypatch):
    monkeypatch.delenv("PLANTCARE_FEEDBACK_DIR", raising=False)
    client = TestClient(create_app(None))
    r = client.post("/api/feedback", json={"verdict": "agree", "model_version": "x"})
    assert r.status_code == 503


def test_feedback_is_written_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTCARE_FEEDBACK_DIR", str(tmp_path / "fb"))
    client = TestClient(create_app(None))
    r = client.post("/api/feedback", json={
        "verdict": "disagree", "model_version": "m/v1",
        "predicted": {"disease": "Tomato___healthy"}, "comment": "carenza di ferro", "role": "agronomo",
    })
    assert r.status_code == 201
    lines = (tmp_path / "fb" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    assert rec["verdict"] == "disagree" and rec["comment"] == "carenza di ferro"
    assert "received_at" in rec
    bad = client.post("/api/feedback", json={"verdict": "forse", "model_version": "m"})
    assert bad.status_code == 422


def test_predict_links_disease_to_taxonomy(trained, monkeypatch):
    monkeypatch.delenv("PLANTCARE_FEEDBACK_DIR", raising=False)
    client = TestClient(create_app(trained, abstain_threshold=0.0))
    r = client.post("/predict", files={"file": ("leaf.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["model_version"].endswith("model.pt")
    cands = body["heads"]["disease"]["candidates"]
    # Il modello ha solo 2 classi: entrambe compaiono tra le ipotesi
    linked = [c for c in cands if c["label"] == "Tomato___Late_blight"]
    assert len(linked) == 1
    assert linked[0]["taxonomy_id"] == "tomato_late_blight"
    assert linked[0]["card"]["name"] == "Peronospora del pomodoro"


def test_index_page_contains_guide_and_feedback():
    client = TestClient(create_app(None))
    html = client.get("/").text
    assert "Come fotografare" in html and "Il risultato è corretto" in html
    assert 'name="viewport"' in html
