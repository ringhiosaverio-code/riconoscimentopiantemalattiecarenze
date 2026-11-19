"""Inferenza: da una foto a un referto con probabilità, astensione, schede e avvertenze.

Supporta due tipi di modello:
- "multitask": rete addestrata end-to-end (es. PlantVillage, plantcare train);
- "readers"  : lettori ottici su caratteristiche pre-addestrate (plantcare train-readers),
               con probabilità calibrate per lettore.

Regole:
- mai una risposta come certezza: si restituiscono le prime k ipotesi con probabilità;
- sotto soglia di confidenza il lettore risponde "non determinabile";
- la probabilità è la media tra foto originale e foto specchiata (test-time augmentation);
- ogni ipotesi collegata alla tassonomia porta la sua scheda per l'agronomo;
- per virosi, viroidi, batteri e nematodi la conferma di laboratorio è obbligatoria nel referto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
import yaml
from PIL import Image, ImageOps

from plantcare.kb import KnowledgeBase

MODEL_NAME_KEY = "model_version"
ROOT = Path(__file__).resolve().parents[2]

DISCLAIMER = (
    "Strumento di supporto alla decisione. Il risultato descrive sintomi visivi e non sostituisce "
    "la diagnosi di un tecnico abilitato. Per virus, viroidi, batteri e nematodi è necessaria la conferma di laboratorio."
)
UNDETERMINED = "non determinabile"
READER_LABELS = {
    "plant": "Lettore della coltura",
    "disease": "Lettore della malattia",
    "pest": "Lettore di insetti e acari",
    "deficiency": "Lettore delle carenze",
}
NOT_TRAINED = {
    "deficiency": "Non addestrato: non esistono ancora dataset di immagini di carenze verificati da analisi di laboratorio.",
    "pest": "Non addestrato in questo modello.",
    "plant": "Non addestrato in questo modello.",
    "disease": "Non addestrato in questo modello.",
}


def _load_ip102_names() -> dict[str, str]:
    p = ROOT / "configs" / "ip102_classes.yaml"
    if not p.exists():
        return {}
    raw = yaml.safe_load(open(p, encoding="utf-8"))["classes"]
    return {f"ip102_{int(k):03d}": str(v) for k, v in raw.items()}


class Predictor:
    def __init__(
        self,
        checkpoint: Path | str,
        device: str = "cpu",
        abstain_threshold: float = 0.5,
        top_k: int = 3,
        kb: KnowledgeBase | None = None,
        label_map: dict[str, Any] | None = None,
        tta: bool = True,
    ):
        ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
        self.device = torch.device(device)
        self.abstain_threshold = abstain_threshold
        self.top_k = top_k
        self.kb = kb
        self.label_map = label_map or {}
        self.tta = tta
        self.version = str(Path(checkpoint).parent.name) + "/" + str(Path(checkpoint).name)
        self.ip102_names = _load_ip102_names()
        self.kind = ckpt.get("kind", "multitask")
        if self.kind == "readers":
            import timm
            from plantcare.readers import load_readers
            self.model, ck = load_readers(Path(checkpoint), device)
            self.idx_to_label = {h: dict(enumerate(r["classes"])) for h, r in ck["readers"].items()}
            self.metrics = ck.get("metrics", {})
            self.training_sources = ck.get("training_sources", [])
            cfg = dict(ck["data_config"])
            cfg["crop_pct"] = 1.0
            self.transform = timm.data.create_transform(**cfg)
        else:
            from plantcare.model import MultiTaskNet
            from plantcare.train import make_transforms
            label_maps: dict[str, dict[str, int]] = ckpt["label_maps"]
            self.idx_to_label = {h: {i: v for v, i in m.items()} for h, m in label_maps.items()}
            self.model = MultiTaskNet(ckpt["backbone"], ckpt["head_sizes"], pretrained=False)
            self.model.load_state_dict(ckpt["model_state"])
            self.transform = make_transforms(ckpt["image_size"], train=False)
            self.metrics = {}
            self.training_sources = ["plantvillage"]
        self.model.to(self.device).eval()

    # ---- descrizione dei lettori (per /api/readers e per il referto) ----
    def readers_status(self) -> dict[str, Any]:
        out = {}
        for head, label in READER_LABELS.items():
            if head in self.idx_to_label:
                m = self.metrics.get(head, {})
                test = m.get("test", {})
                out[head] = {
                    "label": label,
                    "trained": True,
                    "n_classes": len(self.idx_to_label[head]),
                    "test_accuracy": test.get("accuracy"),
                    "test_macro_f1": test.get("macro_f1"),
                    "calibration_error": test.get("ece"),
                    "by_source": test.get("by_source", {}),
                    "temperature": m.get("temperature"),
                }
            else:
                out[head] = {"label": label, "trained": False, "note": NOT_TRAINED[head]}
        return out

    # ---- mappatura verso la tassonomia ----
    def _taxonomy_link(self, head: str, raw: str, organ: str | None) -> tuple[str | None, dict[str, Any] | None, str]:
        """Restituisce (id tassonomia, scheda, nome leggibile)."""
        if head == "plant":
            tax_id = raw if (self.kb and raw in self.kb.tax.plants) else (self.label_map.get("plantvillage_crops") or {}).get(raw)
            if self.kb and tax_id:
                name = self.kb.plant_name(tax_id)
                return tax_id, {"name": name}, name
            return None, None, raw.replace("altro:", "")
        if head == "disease":
            if self.kb and raw in self.kb.tax.diseases:
                tax_id = raw
            else:
                tax_id = (self.label_map.get("plantvillage") or {}).get(raw)
            card = self.kb.disease_card(tax_id, organ=organ) if (self.kb and tax_id) else None
            return tax_id, card, (card["name"] if card else raw.replace("___", " - ").replace("_", " "))
        if head == "pest":
            name = self.ip102_names.get(raw, raw)
            return None, None, f"{name} (classe IP102)"
        return None, None, raw

    @torch.no_grad()
    def _probabilities(self, image: Image.Image) -> dict[str, torch.Tensor]:
        img = image.convert("RGB")
        views = [img, ImageOps.mirror(img)] if self.tta else [img]
        x = torch.stack([self.transform(v) for v in views]).to(self.device)
        logits = self.model(x)
        return {h: F.softmax(out, dim=1).mean(0).cpu() for h, out in logits.items()}

    @torch.no_grad()
    def predict(self, image: Image.Image, organ: str | None = None) -> dict[str, Any]:
        probs_by_head = self._probabilities(image)
        heads: dict[str, Any] = {}
        for head, probs in probs_by_head.items():
            top_p, top_i = probs.topk(min(self.top_k, probs.numel()))
            candidates = []
            for p, i in zip(top_p, top_i):
                raw = self.idx_to_label[head][int(i)]
                tax_id, card, name = self._taxonomy_link(head, raw, organ)
                candidates.append({
                    "label": raw,
                    "name": name,
                    "taxonomy_id": tax_id,
                    "probability": round(float(p), 4),
                    "card": card,
                })
            top = candidates[0]
            confident = top["probability"] >= self.abstain_threshold
            heads[head] = {
                "reader": READER_LABELS.get(head, head),
                "answer": top["name"] if confident else UNDETERMINED,
                "label": top["label"] if confident else None,
                "taxonomy_id": top["taxonomy_id"] if confident else None,
                "card": top["card"] if confident else None,
                "candidates": candidates,
            }
        return {
            "heads": heads,
            "readers": self.readers_status(),
            "organ": organ,
            "referto": self._referto(heads),
            "warnings": self._warnings(heads),
            "disclaimer": DISCLAIMER,
            MODEL_NAME_KEY: self.version,
            "abstain_threshold": self.abstain_threshold,
        }

    @staticmethod
    def _referto(heads: dict[str, Any]) -> dict[str, Any]:
        """Sintesi per l'agronomo: pianta, malattia, causa, origine e misure, dalle risposte confidenti."""
        def answered(head: str) -> dict[str, Any] | None:
            h = heads.get(head, {})
            return h if h.get("answer") not in (None, UNDETERMINED) else None
        plant = answered("plant")
        disease = answered("disease")
        pest = answered("pest")
        card = disease.get("card") if disease else None
        k = card.get("knowledge") if card else None
        return {
            "plant": plant["answer"] if plant else None,
            "disease": card["name"] if card else (disease["answer"] if disease else None),
            "pest": pest["answer"] if pest else None,
            "agent": card.get("agent") if card else None,
            "cause": k["cause"] if k else None,
            "caused_by": (
                [v["name"] for v in k["vectors"]] if k and k["vectors"]
                else ([card["pathogen_type"]["label"]] if card else [])
            ),
            "management": [m["text"] for m in k["management"]] if k else [],
            "management_status": (
                "fonti verificate" if k and k.get("sources_verified")
                else ("da completare con il tecnico" if not k else "fonti parziali")
            ),
            "lab_confirmation_required": bool(card and card.get("lab_confirmation_required")),
            "sources": k["sources"] if k else [],
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
