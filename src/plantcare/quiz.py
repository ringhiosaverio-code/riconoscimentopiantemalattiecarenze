"""Quiz a risposta multipla sulle immagini etichettate dei dataset.

Ogni domanda mostra una foto e 4 risposte, una corretta. Categorie:
    plant (coltura), disease (malattia o danno), pest (insetto o acaro), deficiency (carenza)

La risposta corretta resta sul server fino alla risposta dell'utente; l'immagine si ottiene
con il token della domanda, senza esporre il percorso del file.
"""

from __future__ import annotations

import csv
import random
import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from plantcare.kb import KnowledgeBase

CATEGORIES = {
    "plant": "Quale coltura è?",
    "disease": "Quale malattia o danno si vede?",
    "pest": "Quale insetto è?",
    "deficiency": "Che disturbo nutrizionale si vede?",
}
CATEGORY_LABELS = {"plant": "Colture", "disease": "Malattie", "pest": "Insetti e acari", "deficiency": "Carenze"}
DEFICIENCY_NAMES = {
    "sintomi_di_carenza": "Sintomi di carenza nutrizionale",
    "eccesso_di_azoto": "Eccesso di azoto",
    "carenza_di_calcio": "Carenza di calcio (marciume apicale)",
    "nessun_disturbo_nutrizionale": "Nessun disturbo nutrizionale",
}
SPECIAL_DISEASES = {"disturbo_nutrizionale": "Disturbo nutrizionale (non una malattia)"}
MIN_IMAGES_PER_CLASS = 3
_IT_NAMES: dict[str, str] | None = None


def italian_names() -> dict[str, str]:
    """Nomi italiani delle etichette dei dataset fuori tassonomia (configs/label_names_it.yaml)."""
    global _IT_NAMES
    if _IT_NAMES is None:
        p = Path(__file__).resolve().parents[2] / "configs" / "label_names_it.yaml"
        _IT_NAMES = yaml.safe_load(open(p, encoding="utf-8")) if p.exists() else {}
    return _IT_NAMES
TTL_SECONDS = 3600
MAX_PENDING = 5000


def display_name(head: str, raw: str, kb: KnowledgeBase | None, label_map: dict, ip102: dict[str, str]) -> str:
    """Nome leggibile in italiano per un'etichetta del manifest."""
    if head == "plant":
        if kb and raw in kb.tax.plants:
            return kb.plant_name(raw)
        return raw.replace("altro:", "").capitalize()
    if head == "disease":
        if raw in SPECIAL_DISEASES:
            return SPECIAL_DISEASES[raw]
        if kb and raw in kb.tax.diseases:
            return kb.tax.diseases[raw]["common"]
        tax_id = (label_map.get("plantvillage") or {}).get(raw)
        if kb and tax_id:
            return kb.tax.diseases[tax_id]["common"]
        if raw in italian_names():
            return italian_names()[raw]
        name = raw.split(":", 1)[-1] if ":" in raw else raw.split("___", 1)[-1]
        return name.replace("_", " ").replace("-d", "").strip().capitalize()
    if head == "pest":
        return ip102.get(raw, raw).capitalize()
    if head == "deficiency":
        return DEFICIENCY_NAMES.get(raw, raw)
    return raw


class QuizBank:
    def __init__(self, manifest: Path, data_root: Path, kb: KnowledgeBase | None = None,
                 label_map: dict | None = None, ip102_names: dict[str, str] | None = None, seed: int | None = None):
        self.data_root = data_root
        self.kb = kb
        self.label_map = label_map or {}
        self.ip102 = ip102_names or {}
        self.rng = random.Random(seed)
        self.pending: dict[str, dict[str, Any]] = {}
        # immagini per categoria e classe, e classi per coltura (per distrattori plausibili)
        self.images: dict[str, dict[str, list[str]]] = {h: defaultdict(list) for h in CATEGORIES}
        self.disease_by_plant: dict[str, set[str]] = defaultdict(set)
        with open(manifest, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                for head in CATEGORIES:
                    lab = r.get(head, "")
                    if lab:
                        self.images[head][lab].append(r["path"])
                if r.get("plant") and r.get("disease"):
                    self.disease_by_plant[r["plant"]].add(r["disease"])
        for head in CATEGORIES:
            self.images[head] = {k: v for k, v in self.images[head].items() if len(v) >= MIN_IMAGES_PER_CLASS}

    def available(self) -> dict[str, int]:
        """Numero di classi utilizzabili per categoria (servono almeno 4 classi)."""
        return {h: len(v) for h, v in self.images.items() if len(v) >= 4}

    def _name(self, head: str, raw: str) -> str:
        return display_name(head, raw, self.kb, self.label_map, self.ip102)

    def _cleanup(self) -> None:
        now = time.time()
        for t in [t for t, q in self.pending.items() if now - q["created"] > TTL_SECONDS]:
            del self.pending[t]
        while len(self.pending) > MAX_PENDING:
            self.pending.pop(next(iter(self.pending)))

    def new_question(self, category: str = "any") -> dict[str, Any]:
        self._cleanup()
        cats = list(self.available())
        if not cats:
            raise LookupError("Nessuna categoria con almeno 4 classi")
        head = self.rng.choice(cats) if category == "any" else category
        if head not in cats:
            raise LookupError(f"Categoria non disponibile: {category}")
        classes = list(self.images[head])
        answer = self.rng.choice(classes)
        path = self.rng.choice(self.images[head][answer])

        # distrattori: per le malattie preferire classi della stessa coltura
        pool = [c for c in classes if c != answer]
        if head == "disease":
            same_crop = {d for p, ds in self.disease_by_plant.items() if answer in ds for d in ds}
            near = [c for c in pool if c in same_crop]
            pool = near if len(near) >= 3 else pool
        names_seen = {self._name(head, answer)}
        distractors = []
        for c in self.rng.sample(pool, len(pool)):
            n = self._name(head, c)
            if n not in names_seen:  # niente opzioni con lo stesso nome
                distractors.append(c)
                names_seen.add(n)
            if len(distractors) == 3:
                break
        if len(distractors) < 3:
            raise LookupError("Classi insufficienti per creare 3 distrattori distinti")
        options = [answer] + distractors
        self.rng.shuffle(options)
        token = secrets.token_urlsafe(16)
        self.pending[token] = {"head": head, "answer": answer, "options": options, "path": path,
                               "created": time.time()}
        return {
            "token": token,
            "category": head,
            "category_label": CATEGORY_LABELS[head],
            "question": CATEGORIES[head],
            "image_url": f"/api/quiz/image/{token}",
            "options": [{"id": i, "text": self._name(head, o)} for i, o in enumerate(options)],
        }

    def image_path(self, token: str) -> Path:
        q = self.pending.get(token)
        if q is None:
            raise KeyError(token)
        p = (self.data_root / q["path"]).resolve()
        if self.data_root.resolve() not in p.parents:
            raise KeyError(token)  # mai fuori dalla cartella dei dati
        return p

    def answer(self, token: str, choice: int) -> dict[str, Any]:
        q = self.pending.pop(token, None)
        if q is None:
            raise KeyError(token)
        head, answer, options = q["head"], q["answer"], q["options"]
        correct_id = options.index(answer)
        return {
            "correct": choice == correct_id,
            "correct_id": correct_id,
            "correct_text": self._name(head, answer),
            "explanation": self._explain(head, answer),
        }

    def _explain(self, head: str, raw: str) -> dict[str, Any]:
        out: dict[str, Any] = {"text": None, "agent": None, "organs": [], "lab_note": None}
        if head == "disease" and self.kb:
            tax_id = raw if raw in self.kb.tax.diseases else (self.label_map.get("plantvillage") or {}).get(raw)
            card = self.kb.disease_card(tax_id) if tax_id else None
            if card:
                out.update(text=card["symptoms"], agent=card["agent"],
                           organs=[o["label"] for o in card["organs"]], lab_note=card["lab_note"])
                k = card.get("knowledge")
                if k and k.get("cause"):
                    out["text"] = k["cause"]
            elif raw == "disturbo_nutrizionale":
                out["text"] = "Sintomo nutrizionale, non causato da un patogeno: il nutriente coinvolto non è indicato dal dataset."
        elif head == "plant" and self.kb and raw in self.kb.tax.plants:
            p = self.kb.tax.plants[raw]
            out["text"] = f"Famiglia {p.get('family')}. Nome scientifico: {raw.replace('_', ' ').capitalize()}."
        elif head == "pest":
            out["text"] = "Classe del dataset IP102 di insetti dannosi (nome originale in inglese)."
        elif head == "deficiency":
            out["text"] = ("Etichetta degli autori del dataset: il nutriente specifico non è indicato. "
                           "La conferma richiede l'analisi fogliare.")
        return out


def load_ip102_names(root: Path) -> dict[str, str]:
    p = root / "configs" / "ip102_classes.yaml"
    if not p.exists():
        return {}
    raw = yaml.safe_load(open(p, encoding="utf-8"))["classes"]
    return {f"ip102_{int(k):03d}": str(v) for k, v in raw.items()}
