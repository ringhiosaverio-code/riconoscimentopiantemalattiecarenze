"""Inferenza: da una foto a un referto con probabilità, astensione, schede e avvertenze.

Regole:
- mai una risposta come certezza: si restituiscono le prime k ipotesi con probabilità;
- sotto soglia di confidenza la testa risponde "non determinabile";
- ogni ipotesi collegata alla tassonomia porta la sua scheda per l'agronomo;
- per virosi, viroidi, batteri e nematodi la conferma di laboratorio è obbligatoria nel referto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from PIL import Image

from plantcare.kb import KnowledgeBase
from plantcare.model import MultiTaskNet
from plantcare.train import make_transforms

MODEL_NAME_KEY = "model_version"

DISCLAIMER = (
    "Strumento di supporto alla decisione. Il risultato descrive sintomi visivi e non sostituisce "
    "la diagnosi di un tecnico abilitato. Per virus, viroidi, batteri e nematodi è necessaria la conferma di laboratorio."
)
UNDETERMINED = "non determinabile"


class Predictor:
    def __init__(
        self,
        checkpoint: Path | str,
        device: str = "cpu",
        abstain_threshold: float = 0.5,
        top_k: int = 3,
        kb: KnowledgeBase | None = None,
        label_map: dict[str, Any] | None = None,
    ):
        ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
        self.label_maps: dict[str, dict[str, int]] = ckpt["label_maps"]
        self.idx_to_label = {h: {i: v for v, i in m.items()} for h, m in self.label_maps.items()}
        self.image_size: int = ckpt["image_size"]
        self.device = torch.device(device)
        self.abstain_threshold = abstain_threshold
        self.top_k = top_k
        self.kb = kb
        self.label_map = label_map or {}
        self.version = str(Path(checkpoint).parent.name) + "/" + str(Path(checkpoint).name)
        self.model = MultiTaskNet(ckpt["backbone"], ckpt["head_sizes"], pretrained=False)
        self.model.load_state_dict(ckpt["model_state"])
        self.model.to(self.device).eval()
        self.transform = make_transforms(self.image_size, train=False)

    # ---- mappatura verso la tassonomia ----
    def _taxonomy_link(self, head: str, raw: str, organ: str | None) -> tuple[str | None, dict[str, Any] | None]:
        source = "plantvillage"
        if head == "plant":
            tax_id = (self.label_map.get("plantvillage_crops") or {}).get(raw)
            card = self.kb.plant_name(tax_id) if (self.kb and tax_id) else None
            return tax_id, ({"name": card} if card else None)
        if head == "disease":
            tax_id = (self.label_map.get(source) or {}).get(raw)
            card = self.kb.disease_card(tax_id, organ=organ) if (self.kb and tax_id) else None
            return tax_id, card
        if head == "pest":
            return None, None  # IP102 non è ancora collegata alla tassonomia degli insetti
        return None, None

    @torch.no_grad()
    def predict(self, image: Image.Image, organ: str | None = None) -> dict[str, Any]:
        x = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        logits = self.model(x)
        heads: dict[str, Any] = {}
        for head, out in logits.items():
            probs = F.softmax(out[0], dim=0).cpu()
            top_p, top_i = probs.topk(min(self.top_k, probs.numel()))
            candidates = []
            for p, i in zip(top_p, top_i):
                raw = self.idx_to_label[head][int(i)]
                tax_id, card = self._taxonomy_link(head, raw, organ)
                candidates.append({
                    "label": raw,
                    "taxonomy_id": tax_id,
                    "probability": round(float(p), 4),
                    "card": card,
                })
            top = candidates[0]
            confident = top["probability"] >= self.abstain_threshold
            heads[head] = {
                "answer": top["label"] if confident else UNDETERMINED,
                "taxonomy_id": top["taxonomy_id"] if confident else None,
                "card": top["card"] if confident else None,
                "candidates": candidates,
            }
        return {
            "heads": heads,
            "organ": organ,
            "warnings": self._warnings(heads),
            "disclaimer": DISCLAIMER,
            MODEL_NAME_KEY: self.version,
            "abstain_threshold": self.abstain_threshold,
        }

    @staticmethod
    def _warnings(heads: dict[str, Any]) -> list[str]:
        out: list[str] = []
        disease = heads.get("disease", {})
        card = disease.get("card")
        if card and card.get("lab_confirmation_required"):
            out.append(
                f"«{card['name']}»: agente {card['pathogen_type']['label'].lower()}. Conferma di laboratorio consigliata prima di intervenire."
            )
        if card and card.get("organ_note"):
            out.append(card["organ_note"])
        if any(h.get("answer") == UNDETERMINED for h in heads.values()):
            out.append("Per una o più risposte la confidenza è insufficiente: serve una foto più nitida, ravvicinata e a fuoco.")
        return out
