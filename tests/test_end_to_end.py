"""Test di integrazione su un dataset sintetico: pipeline -> addestramento -> inferenza -> API.

Non richiede dati reali né pesi pre-addestrati (pretrained=False, immagini 32px).
"""

import io
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("torch")
pytest.importorskip("timm")

from plantcare.data.pipeline import scan_plantvillage, write_manifest  # noqa: E402
from plantcare.predict import UNDETERMINED, Predictor  # noqa: E402
from plantcare.train import train  # noqa: E402


@pytest.fixture
def tiny_dataset(tmp_path):
    root = tmp_path / "data" / "raw"
    pv = root / "plantvillage"
    colors = {"Tomato___healthy": (40, 160, 60), "Tomato___Late_blight": (120, 90, 30), "Grape___healthy": (60, 200, 120)}
    for cls, col in colors.items():
        for i in range(8):
            d = pv / cls
            d.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), col).save(d / f"{i}.png")
    rows = scan_plantvillage(pv, seed=0)
    for r in rows:
        r.path = f"plantvillage/{r.path}"
    manifest = tmp_path / "manifest.csv"
    write_manifest(rows, manifest)
    return root, manifest


def test_train_then_predict_and_api(tiny_dataset, tmp_path):
    root, manifest = tiny_dataset
    cfg = {
        "manifest": str(manifest),
        "data_root": str(root),
        "output_dir": str(tmp_path / "out"),
        "backbone": "resnet18",
        "pretrained": False,
        "image_size": 32,
        "batch_size": 8,
        "epochs": 2,
        "lr": 1e-3,
        "heads": ["plant", "disease"],
        "device": "cpu",
        "num_workers": 0,
        "seed": 1,
    }
    result = train(cfg)
    assert result.checkpoint.exists()
    assert result.report.exists()

    pred = Predictor(result.checkpoint, abstain_threshold=0.0)
    out = pred.predict(Image.new("RGB", (64, 64), (40, 160, 60)))
    assert set(out["heads"]) == {"plant", "disease"}
    assert out["disclaimer"]
    assert len(out["heads"]["disease"]["candidates"]) <= 3

    # Soglia 1.01: nessuna risposta è possibile, quindi deve astenersi.
    strict = Predictor(result.checkpoint, abstain_threshold=1.01)
    out2 = strict.predict(Image.new("RGB", (64, 64)))
    assert out2["heads"]["disease"]["answer"] == UNDETERMINED


def test_api_predict_endpoint(tiny_dataset, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from plantcare.api import create_app

    root, manifest = tiny_dataset
    cfg = {
        "manifest": str(manifest), "data_root": str(root), "output_dir": str(tmp_path / "api"),
        "backbone": "resnet18", "pretrained": False, "image_size": 32, "batch_size": 8,
        "epochs": 1, "heads": ["plant"], "device": "cpu", "num_workers": 0,
    }
    ckpt = train(cfg).checkpoint
    client = TestClient(create_app(ckpt))

    assert client.get("/").status_code == 200
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), (10, 200, 10)).save(buf, format="PNG")
    r = client.post("/predict", files={"file": ("leaf.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    assert "heads" in r.json()

    bad = client.post("/predict", files={"file": ("x.txt", b"not an image", "text/plain")})
    assert bad.status_code == 400


def test_api_without_model_returns_503():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from plantcare.api import create_app

    client = TestClient(create_app(None))
    r = client.post("/predict", files={"file": ("x.png", b"", "image/png")})
    assert r.status_code == 503
