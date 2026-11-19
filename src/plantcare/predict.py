"""Inferenza: da una foto a un referto con probabilità, astensione e avvertenze.

Regole:
- mai una risposta come certezza: si restituiscono le prime k ipotesi con probabilità;
- sotto soglia di confidenza la testa risponde "non determinabile";
- per le classi di virosi e viroidi l'avvertenza di conferma di laboratorio è obbligatoria.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from PIL import Image

from plantcare.model import MultiTaskNet
from plantcare.train import make_transforms

DISCLAIMER = (
    "Strumento di supporto alla decisione. Il risultato descrive sintomi visivi e non sostituisce "
    "la diagnosi di un tecnico. Per virus e viroidi è necessaria la conferma di laboratorio."
)
LAB_CONFIRMATION_KEYWORDS = ("virus", "viroid", "phytoplasma", "fitoplasma")

UNDETERMINED = "non determinabile"


class Predictor:
    def __init__(self, checkpoint: Path | str, device: str = "cpu", abstain_threshold: float = 0.5, top_k: int = 3):
        ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
        self.label_maps: dict[str, dict[str, int]] = ckpt["label_maps"]
        self.idx_to_label = {h: {i: v for v, i in m.items()} for h, m in self.label_maps.items()}
        self.image_size: int = ckpt["image_size"]
        self.device = torch.device(device)
        self.abstain_threshold = abstain_threshold
        self.top_k = top_k
        self.model = MultiTaskNet(ckpt["backbone"], ckpt["head_sizes"], pretrained=False)
        self.model.load_state_dict(ckpt["model_state"])
        self.model.to(self.device).eval()
        self.transform = make_transforms(self.image_size, train=False)

    @torch.no_grad()
    def predict(self, image: Image.Image) -> dict[str, Any]:
        x = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        logits = self.model(x)
        heads: dict[str, Any] = {}
        for head, out in logits.items():
            probs = F.softmax(out[0], dim=0).cpu()
            top_p, top_i = probs.topk(min(self.top_k, probs.numel()))
            candidates = [
                {"label": self.idx_to_label[head][int(i)], "probability": round(float(p), 4)}
                for p, i in zip(top_p, top_i)
            ]
            top = candidates[0]
            answer = top["label"] if top["probability"] >= self.abstain_threshold else UNDETERMINED
            heads[head] = {"answer": answer, "candidates": candidates}
        warnings = self._warnings(heads)
        return {"heads": heads, "warnings": warnings, "disclaimer": DISCLAIMER}

    @staticmethod
    def _warnings(heads: dict[str, Any]) -> list[str]:
        out = []
        disease = heads.get("disease", {}).get("answer", "")
        if disease and any(k in disease.lower() for k in LAB_CONFIRMATION_KEYWORDS):
            out.append("Sintomi compatibili con agente virale/viroide/fitoplasma: conferma di laboratorio consigliata.")
        if any(h["answer"] == UNDETERMINED for h in heads.values()):
            out.append("Per una o più classi la confidenza è insufficiente: serve una foto più nitida o più ravvicinata.")
        return out
