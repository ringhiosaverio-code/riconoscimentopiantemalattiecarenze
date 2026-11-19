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


def test_organs_endpoint_and_disease_filter():
    client = TestClient(create_app(None))
    organs = {o["id"] for o in client.get("/api/organs").json()}
    assert {"leaf", "fruit", "trunk", "root", "tuber", "bulb"} <= organs
    roots = client.get("/api/diseases", params={"organ": "root"}).json()
    assert any(c["id"] == "olive_armillaria_root_rot" for c in roots)
    assert all("root" in [o["id"] for o in c["organs"]] for c in roots)


def test_disease_card_reports_organ_mismatch():
    client = TestClient(create_app(None))
    ok = client.get("/api/diseases/olive_knot", params={"organ": "trunk"}).json()
    assert ok["organ_match"] is True
    assert ok["symptoms_for_organ"].startswith("Tumori sul tronco")
    miss = client.get("/api/diseases/olive_knot", params={"organ": "leaf"}).json()
    assert miss["organ_match"] is False
    assert "meno probabile" in miss["organ_note"]


def test_every_disease_has_organ_symptoms_for_its_organs():
    from plantcare.taxonomy import load_taxonomy
    tax = load_taxonomy()
    for dis_id, d in tax.diseases.items():
        if d["pathogen_type"] == "healthy":
            continue
        assert d["organs"], dis_id
        assert set(d.get("organ_symptoms", {})) <= set(d["organs"]), dis_id


def test_predict_rejects_unknown_organ():
    client = TestClient(create_app(None))
    r = client.post("/predict", data={"organ": "zampa"}, files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_every_crop_has_a_harmful_insect():
    from plantcare.taxonomy import load_taxonomy
    tax = load_taxonomy()
    harmful_hosts = {h for i in tax.insects.values() if i["role"] == "phytophagous" for h in i.get("hosts", [])}
    assert set(tax.plants) <= harmful_hosts, sorted(set(tax.plants) - harmful_hosts)


def test_olive_has_its_main_pests_and_api_filters_them():
    client = TestClient(create_app(None))
    olive = client.get("/api/insects", params={"plant": "olea_europaea", "role": "phytophagous"}).json()
    ids = {i["id"] for i in olive}
    assert {"bactrocera_oleae", "prays_oleae", "saissetia_oleae", "euphyllura_olivina"} <= ids
    assert all(i["role"]["id"] == "phytophagous" for i in olive)
    card = client.get("/api/insects/prays_oleae").json()
    assert card["scientific"] == "Prays oleae"
    assert client.get("/api/insects/inesistente").status_code == 404


def test_useful_insects_are_not_listed_as_pests():
    from plantcare.taxonomy import load_taxonomy
    tax = load_taxonomy()
    for useful in ("coccinella_septempunctata", "chrysoperla_carnea", "aphidius_colemani", "apis_mellifera"):
        assert tax.insects[useful]["role"] != "phytophagous"


def test_knowledge_references_are_consistent():
    import yaml
    from pathlib import Path
    from plantcare.taxonomy import load_taxonomy
    root = Path(__file__).resolve().parents[1] / "configs"
    kb = yaml.safe_load(open(root / "knowledge_base.yaml", encoding="utf-8"))
    src_ids = {s["id"] for s in yaml.safe_load(open(root / "sources.yaml", encoding="utf-8"))["sources"]}
    tax = load_taxonomy()
    for dis_id, entry in kb["diseases"].items():
        assert dis_id in tax.diseases, dis_id
        for v in entry.get("vectors", []):
            assert v in tax.insects, (dis_id, v)
        for m in entry.get("management", []):
            for s in m.get("sources", []):
                assert s in src_ids, (dis_id, s)
    for ins_id, entry in kb["insects"].items():
        assert ins_id in tax.insects, ins_id
        for m in entry.get("management", []):
            for s in m.get("sources", []):
                assert s in src_ids, (ins_id, s)


def test_olive_xylella_card_has_verified_knowledge():
    client = TestClient(create_app(None))
    card = client.get("/api/diseases/olive_xylella_quick_decline").json()
    k = card["knowledge"]
    assert "xilema" in k["cause"]
    assert k["vectors"][0]["id"] == "philaenus_spumarius"
    assert k["sources_verified"] is True
    assert any("eradicazione" in m["text"] for m in k["management"])
    assert all("dosi" not in m["text"].lower() for m in k["management"])
    sources = client.get("/api/sources").json()
    assert any(s["id"] == "efsa_xylella_2019" for s in sources)


def test_disease_without_knowledge_is_explicit_about_it():
    client = TestClient(create_app(None))
    card = client.get("/api/diseases/lettuce_downy_mildew").json()
    assert card["knowledge"] is None
