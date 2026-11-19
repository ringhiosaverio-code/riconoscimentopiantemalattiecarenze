"""Pipeline dei dati: da cartelle/file dei dataset pubblici a un manifest unico.

Il manifest (CSV) è l'unica interfaccia tra i dati grezzi e l'addestramento.
Una riga = un'immagine, con colonne per ogni testa del modello.
Le teste assenti per quella riga restano vuote.

Colonne del manifest:
    path, source, split, plant, disease, pest
"""

from __future__ import annotations

import csv
import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MANIFEST_COLUMNS = ["path", "source", "split", "plant", "disease", "pest"]
SPLITS = ("train", "val", "test")


@dataclass
class ManifestRow:
    path: str
    source: str
    split: str
    plant: str = ""
    disease: str = ""
    pest: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


# ---------------------------------------------------------------
# PlantVillage: cartelle "Coltura___Malattia" (layout di raw/color/)
# ---------------------------------------------------------------
def parse_plantvillage_folder(name: str) -> tuple[str, str]:
    """'Tomato___Late_blight' -> ('Tomato', 'Tomato___Late_blight').

    La malattia viene conservata con il nome completo della cartella:
    la mappatura verso la tassonomia avviene in configs/label_maps.yaml.
    """
    if "___" not in name:
        raise ValueError(f"Nome cartella non riconosciuto come PlantVillage: '{name}'")
    crop = name.split("___", 1)[0]
    return crop, name


def scan_plantvillage(root: Path, seed: int = 42, val_frac: float = 0.15, test_frac: float = 0.15) -> list[ManifestRow]:
    """Scansiona la cartella e assegna gli split in modo stratificato per classe.

    ATTENZIONE: PlantVillage non ha informazioni di località o di pianta.
    Lo split casuale può far finire nello stesso split foto quasi identiche
    (stessa foglia, angolo diverso). I risultati su questo split sono quindi
    ottimistici: è il motivo per cui serve un test di campo separato.
    """
    rng = random.Random(seed)
    by_class: dict[str, list[Path]] = defaultdict(list)
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if "___" not in folder.name:
            continue
        for img in sorted(folder.iterdir()):
            if img.suffix.lower() in IMAGE_EXTENSIONS:
                by_class[folder.name].append(img)

    rows: list[ManifestRow] = []
    for cls, files in sorted(by_class.items()):
        rng.shuffle(files)
        n = len(files)
        n_test = max(1, round(n * test_frac)) if n >= 3 else 0
        n_val = max(1, round(n * val_frac)) if n >= 3 else 0
        for i, f in enumerate(files):
            if i < n_test:
                split = "test"
            elif i < n_test + n_val:
                split = "val"
            else:
                split = "train"
            crop, disease = parse_plantvillage_folder(cls)
            rows.append(ManifestRow(
                path=str(f.relative_to(root)),
                source="plantvillage",
                split=split,
                plant=crop,
                disease=disease,
            ))
    return rows


# ---------------------------------------------------------------
# IP102: file di split "percorso etichetta" (split ufficiali)
# ---------------------------------------------------------------
def scan_ip102(root: Path, images_dir: str = "images", split_files: dict[str, str] | None = None) -> list[ManifestRow]:
    """Legge gli split ufficiali di IP102.

    `split_files` mappa split -> nome file (default: train.txt, val.txt, test.txt).
    Ogni riga del file: '<percorso_relativo_a_images_dir> <indice_intero>'.
    Il valore di pest è l'indice originale (stringa), non un nome: i nomi
    scientifici vanno aggiunti in configs/label_maps.yaml quando disponibili.
    """
    split_files = split_files or {"train": "train.txt", "val": "val.txt", "test": "test.txt"}
    rows: list[ManifestRow] = []
    for split, fname in split_files.items():
        list_path = root / fname
        if not list_path.exists():
            continue
        with open(list_path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) != 2:
                    continue
                rel, label = parts
                rows.append(ManifestRow(
                    path=str(Path(images_dir) / rel),
                    source="ip102",
                    split=split,
                    pest=f"ip102_{int(label):03d}",
                ))
    return rows


# ---------------------------------------------------------------
# Controlli di qualità
# ---------------------------------------------------------------
def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def find_cross_split_duplicates(root: Path, rows: list[ManifestRow]) -> list[list[str]]:
    """Gruppi di file identici (stesso hash) distribuiti su più split: fuga di dati."""
    by_hash: dict[str, list[ManifestRow]] = defaultdict(list)
    for r in rows:
        by_hash[file_sha256(root / r.path)].append(r)
    leaks: list[list[str]] = []
    for group in by_hash.values():
        if len({g.split for g in group}) > 1:
            leaks.append([f"{g.split}:{g.path}" for g in group])
    return leaks


def find_corrupt_images(root: Path, rows: list[ManifestRow]) -> list[str]:
    bad: list[str] = []
    for r in rows:
        try:
            with Image.open(root / r.path) as im:
                im.verify()
        except (UnidentifiedImageError, OSError, FileNotFoundError):
            bad.append(r.path)
    return bad


# ---------------------------------------------------------------
# Lettura/scrittura manifest
# ---------------------------------------------------------------
def write_manifest(rows: list[ManifestRow], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r.as_dict())


def read_manifest(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def summarize(rows: list[ManifestRow]) -> dict[str, dict[str, int]]:
    """Conteggi per split e per testa: utile per vedere sbilanciamenti prima di addestrare."""
    out: dict[str, dict[str, int]] = {s: defaultdict(int) for s in SPLITS}
    for r in rows:
        out[r.split]["images"] += 1
        for head in ("plant", "disease", "pest"):
            if getattr(r, head):
                out[r.split][head] += 1
    return {k: dict(v) for k, v in out.items()}
