"""Lettori ottici: addestramento su caratteristiche, calibrazione, checkpoint e predizione."""

import io

import numpy as np
import pytest
import torch
from PIL import Image

pytest.importorskip("timm")

from plantcare import readers as rd  # noqa: E402


def _rows_and_feats(n_per_class=60, dim=32, seed=0):
    rng = np.random.default_rng(seed)
    rows, feats = [], []
    centers = {"olea_europaea": 0, "vitis_vinifera": 1, "citrus_limon": 2}
    for plant, c in centers.items():
        for i in range(n_per_class):
            split = "train" if i < 40 else ("val" if i < 50 else "test")
            v = rng.normal(0, 1, dim)
            v[c * 5:(c + 1) * 5] += 4.0
            rows.append({"split": split, "source": "sintetico" if i % 2 else "campo", "plant": plant,
                         "disease": "", "pest": "", "deficiency": ""})
            feats.append(v)
    return rows, np.array(feats, dtype=np.float16)


def test_reader_learns_separable_classes_and_is_calibrated():
    rows, feats = _rows_and_feats()
    hd = rd.prepare_head(rows, feats, "plant")
    assert hd.classes == ["citrus_limon", "olea_europaea", "vitis_vinifera"]
    reader, info = rd.train_reader(hd, feats.shape[1])
    assert info["test"]["accuracy"] > 0.9
    assert info["temperature"] > 0
    assert info["test"]["ece"] < 0.2
    assert set(info["test"]["by_source"]) == {"sintetico", "campo"}


def test_head_without_data_is_none():
    rows, feats = _rows_and_feats()
    assert rd.prepare_head(rows, feats, "deficiency") is None


def test_temperature_scaling_reduces_overconfidence():
    torch.manual_seed(0)
    reader = rd.Reader(8, 2)
    with torch.no_grad():
        reader.net[-1].weight.mul_(50)  # lettore volutamente troppo sicuro
    X = torch.randn(400, 8)
    y = torch.randint(0, 2, (400,))  # etichette casuali: la confidenza giusta è ~50%
    t = rd.calibrate_temperature(reader, X, y)
    assert t > 1.0
    with torch.no_grad():
        conf = torch.softmax(reader(X), 1).max(1).values.mean()
    assert conf < 0.75


def test_readers_checkpoint_roundtrip_and_predictor(tmp_path):
    import timm
    from plantcare.predict import Predictor

    rows, _ = _rows_and_feats(n_per_class=60)
    backbone = timm.create_model("resnet18", pretrained=False, num_classes=0)
    dim = backbone.num_features
    feats = np.random.default_rng(1).normal(size=(len(rows), dim)).astype(np.float16)
    hd = rd.prepare_head(rows, feats, "plant", min_train=2)
    reader, info = rd.train_reader(hd, dim)
    cfg = timm.data.resolve_data_config({"input_size": (3, 64, 64)}, model=backbone)
    ck = tmp_path / "readers.pt"
    rd.save_readers(ck, ["resnet18"], {"plant": reader}, {"plant": info}, cfg, ["sintetico"],
                    image_size=64, backbone_models=[backbone])
    net, meta = rd.load_readers(ck)
    out = net(torch.randn(2, 3, 64, 64))
    assert out["plant"].shape == (2, 3)

    pred = Predictor(ck, abstain_threshold=0.0)
    res = pred.predict(Image.new("RGB", (80, 80), (40, 160, 60)))
    probs = [c["probability"] for c in res["heads"]["plant"]["candidates"]]
    assert abs(sum(probs) - 1.0) < 0.02  # 3 classi, tutte nei candidati
    status = res["readers"]
    assert status["plant"]["trained"] is True
    assert status["deficiency"]["trained"] is False
    assert "carenze" in status["deficiency"]["note"]


def test_feature_cache_is_indexed_by_path(tmp_path):
    """Aggiungere immagini non sfasa le caratteristiche già calcolate."""
    from plantcare.readers import extract_features
    imgs = []
    for i, col in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (32, 32), col).save(p)
        imgs.append(p)
    out = tmp_path / "feats"
    a = extract_features(imgs[:2], "resnet18", out, chunk=1, batch_size=1, num_workers=0, image_size=32)
    b = extract_features([imgs[2], imgs[0], imgs[1]], "resnet18", out, chunk=1, batch_size=1, num_workers=0,
                         image_size=32)
    assert np.allclose(b[1], a[0]) and np.allclose(b[2], a[1])
    assert len(list(out.glob("block_*.npy"))) == 3  # una sola immagine nuova calcolata
