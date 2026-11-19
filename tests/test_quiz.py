"""Quiz a risposta multipla: domande, risposte, sicurezza dei percorsi e API."""

import csv

import pytest
from PIL import Image

from plantcare.data.pipeline import MANIFEST_COLUMNS
from plantcare.kb import KnowledgeBase
from plantcare.quiz import QuizBank
from plantcare.taxonomy import load_taxonomy

PLANTS = ["olea_europaea", "vitis_vinifera", "citrus_limon", "malus_domestica", "prunus_persica"]
DISEASES = ["olive_peacock_spot", "grapevine_downy_mildew", "citrus_anthracnose", "apple_scab", "peach_leaf_curl"]


@pytest.fixture
def bank_files(tmp_path):
    root = tmp_path / "data"
    rows = []
    for i, (plant, dis) in enumerate(zip(PLANTS, DISEASES)):
        for k in range(4):
            rel = f"img/{plant}_{k}.jpg"
            (root / "img").mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (20, 20), (i * 40, 100, k * 50)).save(root / rel)
            rows.append({"path": rel, "source": "test", "split": "test", "plant": plant, "disease": dis,
                         "pest": "", "deficiency": ""})
    manifest = tmp_path / "m.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return manifest, root


def test_question_has_four_distinct_options_and_one_answer(bank_files):
    manifest, root = bank_files
    bank = QuizBank(manifest, root, kb=KnowledgeBase(load_taxonomy()), seed=1)
    assert set(bank.available()) == {"plant", "disease"}  # pest e carenze senza dati
    for _ in range(10):
        q = bank.new_question("disease")
        texts = [o["text"] for o in q["options"]]
        assert len(texts) == 4 and len(set(texts)) == 4
        assert "token" in q and "answer" not in q  # la risposta non viene inviata al browser
        res = bank.answer(q["token"], 0)
        assert texts[res["correct_id"]] == res["correct_text"]
        assert res["correct"] == (res["correct_id"] == 0)


def test_explanation_uses_taxonomy_card(bank_files):
    manifest, root = bank_files
    bank = QuizBank(manifest, root, kb=KnowledgeBase(load_taxonomy()), seed=3)
    q = bank.new_question("disease")
    res = bank.answer(q["token"], 0)
    assert res["explanation"]["agent"]
    assert res["explanation"]["organs"]


def test_token_is_single_use_and_image_stays_in_data_root(bank_files):
    manifest, root = bank_files
    bank = QuizBank(manifest, root, seed=2)
    q = bank.new_question("plant")
    p = bank.image_path(q["token"])
    assert root.resolve() in p.parents and p.exists()
    bank.answer(q["token"], 1)
    with pytest.raises(KeyError):
        bank.answer(q["token"], 1)
    bank.pending["x"] = {"head": "plant", "answer": "a", "options": ["a"], "path": "../../etc/passwd", "created": 0}
    with pytest.raises(KeyError):
        bank.image_path("x")


def test_unavailable_category_is_rejected(bank_files):
    manifest, root = bank_files
    bank = QuizBank(manifest, root, seed=0)
    with pytest.raises(LookupError):
        bank.new_question("pest")


def test_quiz_api_flow(bank_files):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from plantcare.api import create_app

    manifest, root = bank_files
    client = TestClient(create_app(None, quiz_manifest=manifest, quiz_data_root=root))
    cats = client.get("/api/quiz/categories").json()
    assert cats["enabled"] and "plant" in cats["categories"]
    q = client.get("/api/quiz/question", params={"category": "plant"}).json()
    img = client.get(q["image_url"])
    assert img.status_code == 200 and img.headers["content-type"].startswith("image/")
    a = client.post("/api/quiz/answer", json={"token": q["token"], "choice": 2}).json()
    assert {"correct", "correct_id", "correct_text", "explanation"} <= set(a)
    again = client.post("/api/quiz/answer", json={"token": q["token"], "choice": 2})
    assert again.status_code == 404
    assert client.post("/api/quiz/answer", json={"token": "x", "choice": 9}).status_code == 422


def test_quiz_disabled_without_manifest():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from plantcare.api import create_app
    client = TestClient(create_app(None))
    assert client.get("/api/quiz/categories").json()["enabled"] is False
    assert client.get("/api/quiz/question").status_code == 503
