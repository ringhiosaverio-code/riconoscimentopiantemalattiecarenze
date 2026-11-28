"""Modello per il browser diviso in parti (app/model/parti.json, scripts/build_web.py): lettura dei byte."""
import json
from pathlib import Path


def byte_modello(percorso) -> bytes:
    """Byte del modello ONNX: un file .onnx, oppure la cartella app/model (o un suo file) con parti.json."""
    p = Path(percorso)
    d = p if p.is_dir() else p.parent
    parti = d / "parti.json"
    if p.is_file() and p.suffix == ".onnx":
        return p.read_bytes()
    if parti.exists():
        return b"".join((d / f).read_bytes() for f in json.load(open(parti))["parti"])
    raise FileNotFoundError(f"modello non trovato: {p}")
