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
import json
import random
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MANIFEST_COLUMNS = ["path", "source", "split", "plant", "disease", "pest", "deficiency"]
SPLITS = ("train", "val", "test")


@dataclass
class ManifestRow:
    path: str
    source: str
    split: str
    plant: str = ""
    disease: str = ""
    pest: str = ""
    deficiency: str = ""

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


def leaf_identifier(file_name: str) -> str:
    """Identificatore della foglia dal nome file, come nel loader ufficiale di PlantVillage."""
    ident = file_name.replace("_final_masked", "")
    if "___" in ident:
        ident = ident.split("___")[-1]
    ident = ident.split("copy")[0]
    for ext in (".jpg", ".JPG", ".png", ".PNG"):
        ident = ident.replace(ext, "")
    return ident.strip().lower()


def resolve_leaf_id(file_name: str, class_name: str, leaf_map: dict[str, list[str]]) -> str:
    """Gruppo foglia di un'immagine, con la stessa logica del loader ufficiale.

    Immagini della stessa foglia condividono il gruppo e vanno nello stesso split.
    Se la mappa non le conosce, il gruppo è l'immagine stessa (nessuna garanzia).
    """
    ident = leaf_identifier(file_name)
    candidates = leaf_map.get(ident)
    if not candidates:
        return f"fallback_{ident}"
    if len(candidates) == 1:
        return candidates[0]
    for c in candidates:
        if class_name in c:
            return c
    return f"fallback_{ident}"


def load_leaf_map(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def scan_plantvillage(
    root: Path,
    seed: int = 42,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    leaf_map: dict[str, list[str]] | None = None,
) -> list[ManifestRow]:
    """Scansiona la cartella e assegna gli split per gruppo di foglia, stratificando per classe.

    Con `leaf_map` (leaf_grouping/leaf-map.json del dataset ufficiale) tutte le foto
    della stessa foglia finiscono nello stesso split: è la protezione contro la fuga
    di dati. Senza la mappa ogni foto è un gruppo a sé e lo split è ottimistico.
    """
    rng = random.Random(seed)
    leaf_map = leaf_map or {}
    by_class: dict[str, list[Path]] = defaultdict(list)
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if "___" not in folder.name:
            continue
        for img in sorted(folder.iterdir()):
            if img.suffix.lower() in IMAGE_EXTENSIONS:
                by_class[folder.name].append(img)

    rows: list[ManifestRow] = []
    for cls, files in sorted(by_class.items()):
        groups: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            gid = resolve_leaf_id(f.name, cls, leaf_map) if leaf_map else f"img_{f.as_posix()}"
            groups[gid].append(f)
        keys = sorted(groups)
        rng.shuffle(keys)
        n = len(files)
        split_of: dict[str, str] = {}
        filled = 0
        for k in keys:
            if filled < test_frac * n:
                split = "test"
            elif filled < (test_frac + val_frac) * n:
                split = "val"
            else:
                split = "train"
            split_of[k] = split
            filled += len(groups[k])
        crop, disease = parse_plantvillage_folder(cls)
        for gid, members in groups.items():
            for f in members:
                rows.append(ManifestRow(
                    path=str(f.relative_to(root)),
                    source="plantvillage",
                    split=split_of[gid],
                    plant=crop,
                    disease=disease,
                ))
    return rows


# ---------------------------------------------------------------
# IP102: file di split "percorso etichetta" (split ufficiali)
# ---------------------------------------------------------------
def scan_ip102(
    root: Path,
    images_dir: str = "images",
    split_files: dict[str, str] | None = None,
    label_base: int = 0,
) -> list[ManifestRow]:
    """Legge gli split ufficiali di IP102.

    Ogni riga del file: '<percorso_relativo_a_images_dir> <etichetta>'.
    `label_base` è la base degli indici nei file di split (0 o 1). Il valore
    salvato in `pest` è l'indice 1-based di classes.txt, così corrisponde ai nomi
    in configs/ip102_classes.yaml. Impostare label_base in modo errato sposta
    tutte le etichette di una posizione: va controllato sul file scaricato.
    """
    if label_base not in (0, 1):
        raise ValueError("label_base deve essere 0 o 1")
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
                official = int(label) - label_base + 1
                rows.append(ManifestRow(
                    path=str(Path(images_dir) / rel),
                    source="ip102",
                    split=split,
                    pest=f"ip102_{official:03d}",
                ))
    return rows


def load_ip102_classes(path: Path) -> dict[int, str]:
    """Nomi delle classi IP102 da configs/ip102_classes.yaml (indici 1-based)."""
    import yaml
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)["classes"]
    return {int(k): str(v) for k, v in raw.items()}


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
        for head in ("plant", "disease", "pest", "deficiency"):
            if getattr(r, head):
                out[r.split][head] += 1
    return {k: dict(v) for k, v in out.items()}
