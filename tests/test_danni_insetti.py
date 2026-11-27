"""La tabella danni/vettori/melata collega solo classi esistenti dei lettori."""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_collegamenti_classi_esistenti():
    links = yaml.safe_load(open(ROOT / "configs" / "danni_insetti.yaml", encoding="utf-8"))["collegamenti"]
    readers = json.load(open(ROOT / "app" / "data" / "readers.json", encoding="utf-8"))
    dis = {c["label"] for c in readers["disease"]["classes"]}
    pest = {c["label"] for c in readers["pest"]["classes"]}
    names = yaml.safe_load(open(ROOT / "configs" / "label_names_it.yaml", encoding="utf-8"))
    import re
    quiz = yaml.safe_load(open(ROOT / "configs" / "quiz_calabria.yaml", encoding="utf-8"))
    pest |= {"inat:" + re.sub(r"[^a-z0-9]+", "_", p["taxon"].lower()).strip("_") for p in quiz["parassiti"]}
    for d, e in links.items():
        # classi nuove (danni, malattie aggiunte): entrano nel lettore con il modello che le addestra,
        # ma devono avere già il nome italiano
        assert d in dis or d in names, d
        assert e["tipo"] in ("danno", "vettore", "melata"), d
        assert all(i in pest for i in e["insetti"]), d
        assert e.get("nota")
