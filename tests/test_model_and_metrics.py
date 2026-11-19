import numpy as np
import torch

from plantcare.metrics import coverage_accuracy, expected_calibration_error, macro_f1
from plantcare.model import IGNORE_INDEX, MultiTaskNet, multitask_loss


def test_masked_loss_ignores_absent_labels():
    outputs = {"plant": torch.randn(4, 3), "pest": torch.randn(4, 5)}
    # pest è assente in tutte le righe: non deve contribuire alla perdita
    targets = {
        "plant": torch.tensor([0, 1, 2, 0]),
        "pest": torch.full((4,), IGNORE_INDEX),
    }
    loss, parts = multitask_loss(outputs, targets)
    assert "pest" not in parts
    assert "plant" in parts
    assert torch.isfinite(loss)


def test_loss_is_zero_tensor_when_no_labels():
    outputs = {"plant": torch.randn(2, 3)}
    targets = {"plant": torch.full((2,), IGNORE_INDEX)}
    loss, parts = multitask_loss(outputs, targets)
    assert float(loss) == 0.0 and parts == {}


def test_multitask_net_returns_one_output_per_head():
    net = MultiTaskNet("resnet18", {"plant": 4, "disease": 7}, pretrained=False)
    out = net(torch.randn(2, 3, 64, 64))
    assert set(out) == {"plant", "disease"}
    assert out["plant"].shape == (2, 4)
    assert out["disease"].shape == (2, 7)


def test_macro_f1_perfect_and_imperfect():
    y = np.array([0, 1, 2, 2])
    assert macro_f1(y, y) == 1.0
    assert macro_f1(y, np.array([0, 1, 2, 0])) < 1.0


def test_ece_is_zero_for_perfectly_calibrated_confident_predictions():
    probs = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
    labels = np.array([0, 1, 0])
    assert expected_calibration_error(probs, labels) == 0.0


def test_coverage_accuracy_trades_answers_for_precision():
    probs = np.array([[0.9, 0.1], [0.6, 0.4], [0.55, 0.45]])
    labels = np.array([0, 1, 0])
    rows = coverage_accuracy(probs, labels, [0.5, 0.8])
    assert rows[0]["coverage"] == 1.0
    assert rows[1]["coverage"] == 1 / 3
    assert rows[1]["accuracy_on_answered"] == 1.0
