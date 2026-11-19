"""Importatori: convertono i dataset esterni in immagini su disco e righe di manifest unificate.

Etichette unificate (uguali per tutte le fonti):
- plant   : id della tassonomia (es. "solanum_lycopersicum"); colture fuori tassonomia "altro:<nome>"
- disease : id della tassonomia se mappato, altrimenti nome PlantVillage (così laboratorio e campo
            condividono la classe), altrimenti "<fonte>:<etichetta>"
- pest    : "ip102_NNN" (indice 1-based di classes.txt)

Le immagini estratte vanno in data/external/images/<fonte>/...; i percorsi del manifest sono
relativi a data/ (la radice comune).
"""

from __future__ import annotations

import io
import json
import random
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pyarrow.parquet as pq
import yaml
from PIL import Image

from plantcare.data.pipeline import ManifestRow

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
EXT = DATA / "external"
IMG = EXT / "images"
MAX_SIDE = 384  # le immagini vengono ridotte: il modello lavora a 160-224 px

# ---------------------------------------------------------------------------
# Mappature di etichette verificate a mano sui nomi delle categorie
# ---------------------------------------------------------------------------
PV_CROPS_FALLBACK = {"Blueberry": "altro:mirtillo", "Raspberry": "altro:lampone", "Soybean": "altro:soia"}

PLANTDOC = {
    # categoria PlantDoc: (pianta, malattia)
    "Apple Scab Leaf": ("malus_domestica", "apple_scab"),
    "Apple leaf": ("malus_domestica", "healthy"),
    "Apple rust leaf": ("malus_domestica", "Apple___Cedar_apple_rust"),
    "Bell_pepper leaf": ("capsicum_annuum", "healthy"),
    "Bell_pepper leaf spot": ("capsicum_annuum", "pepper_bacterial_spot"),
    "Blueberry leaf": ("altro:mirtillo", "healthy"),
    "Cherry leaf": ("prunus_avium", "healthy"),
    "Corn Gray leaf spot": ("zea_mays", "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot"),
    "Corn leaf blight": ("zea_mays", "maize_northern_leaf_blight"),
    "Corn rust leaf": ("zea_mays", "maize_common_rust"),
    "Peach leaf": ("prunus_persica", "healthy"),
    "Potato leaf": ("solanum_tuberosum", "healthy"),
    "Potato leaf early blight": ("solanum_tuberosum", "tomato_early_blight"),
    "Potato leaf late blight": ("solanum_tuberosum", "tomato_late_blight"),
    "Raspberry leaf": ("altro:lampone", "healthy"),
    "Soyabean leaf": ("altro:soia", "healthy"),
    "Squash Powdery mildew leaf": ("cucurbita_pepo", "zucchini_powdery_mildew"),
    "Strawberry leaf": ("fragaria_ananassa", "healthy"),
    "Tomato Early blight leaf": ("solanum_lycopersicum", "tomato_early_blight"),
    "Tomato Septoria leaf spot": ("solanum_lycopersicum", "Tomato___Septoria_leaf_spot"),
    "Tomato leaf": ("solanum_lycopersicum", "healthy"),
    "Tomato leaf bacterial spot": ("solanum_lycopersicum", "pepper_bacterial_spot"),
    "Tomato leaf late blight": ("solanum_lycopersicum", "tomato_late_blight"),
    "Tomato leaf mosaic virus": ("solanum_lycopersicum", "tomato_mosaic_virus"),
    "Tomato leaf yellow virus": ("solanum_lycopersicum", "tomato_yellow_leaf_curl"),
    "Tomato mold leaf": ("solanum_lycopersicum", "Tomato___Leaf_Mold"),
    "Tomato two spotted spider mites leaf": ("solanum_lycopersicum", "Tomato___Spider_mites Two-spotted_spider_mite"),
    "grape leaf": ("vitis_vinifera", "healthy"),
    "grape leaf black rot": ("vitis_vinifera", "Grape___Black_rot"),
}

INAT_SPECIES = {
    "olea_europaea": "olea_europaea", "vitis_vinifera": "vitis_vinifera", "citrus_limon": "citrus_limon",
    "citrus_reticulata": "citrus_reticulata", "citrus_sinensis": "citrus_sinensis",
    "actinidia_chinensis": "actinidia_chinensis", "allium_cepa": "allium_cepa_tropea",
    "allium_sativum": "allium_sativum", "annona_cherimola": "annona_cherimola",
    "capsicum_annuum": "capsicum_annuum", "corylus_avellana": "corylus_avellana",
    "cucumis_sativus": "cucumis_sativus", "cucurbita_pepo": "cucurbita_pepo",
    "cynara_cardunculus": "cynara_cardunculus", "cynara_scolymus": "cynara_cardunculus",
    "fragaria_ananassa": "fragaria_ananassa", "malus_domestica": "malus_domestica",
    "musa_acuminata": "musa_spp", "opuntia_ficus-indica": "opuntia_ficus_indica",
    "persea_americana": "persea_americana", "prunus_avium": "prunus_avium",
    "prunus_persica": "prunus_persica", "pyrus_communis": "pyrus_communis",
    "solanum_melongena": "solanum_melongena", "solanum_tuberosum": "solanum_tuberosum",
    "triticum_aestivum": "triticum_aestivum", "triticum_durum": "triticum_durum", "zea_mays": "zea_mays",
}

# Etichette AgML che corrispondono a classi della tassonomia (il resto resta "<fonte>:<etichetta>")
AGML_DISEASE = {
    ("agml_grape", "Downy Mildew"): "grapevine_downy_mildew",
    ("agml_grape", "Powdery Mildew"): "powdery_mildew_grapevine",
    ("agml_banana", "segatoka"): "banana_black_sigatoka",
    ("agml_tuta", "infected"): "tomato_leafminer_damage",
    ("agml_potato", "Phytopthora"): "tomato_late_blight",
    ("agml_cauliflower", "Black Rot"): "broccoli_black_rot",
}
HEALTHY_WORDS = ("healthy", "health", "sano", "normal", "fresh")


def _save(img_bytes: bytes, out: Path, box: tuple | None = None) -> bool:
    try:
        with Image.open(io.BytesIO(img_bytes)) as im:
            im = im.convert("RGB")
            if box is not None:
                x0, y0, x1, y1 = box
                if x1 - x0 < 24 or y1 - y0 < 24:
                    return False
                im = im.crop((x0, y0, x1, y1))
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            out.parent.mkdir(parents=True, exist_ok=True)
            im.save(out, quality=90)
        return True
    except Exception:
        return False


def _split_random(n_items: int, seed: int, val: float = 0.1, test: float = 0.1) -> list[str]:
    rng = random.Random(seed)
    idx = list(range(n_items))
    rng.shuffle(idx)
    out = ["train"] * n_items
    n_test, n_val = int(n_items * test), int(n_items * val)
    for k, i in enumerate(idx):
        out[i] = "test" if k < n_test else ("val" if k < n_test + n_val else "train")
    return out


def _rel(p: Path) -> str:
    return p.relative_to(DATA).as_posix()


def _label_names(repo: str) -> list[str] | None:
    """Nomi delle classi dalla scheda del dataset su Hugging Face (cardData)."""
    import urllib.request
    try:
        d = json.load(urllib.request.urlopen(f"https://huggingface.co/api/datasets/{repo}", timeout=60))
        feats = d["cardData"]["dataset_info"]["features"]
        for f in feats:
            cl = f.get("dtype", {})
            if isinstance(cl, dict) and "class_label" in cl:
                names = cl["class_label"]["names"]
                return [names[str(i)] for i in range(len(names))] if isinstance(names, dict) else list(names)
    except Exception:
        return None
    return None


def _parquet_rows(files: Iterable[Path], columns: list[str]):
    for f in files:
        pf = pq.ParquetFile(f)
        for batch in pf.iter_batches(batch_size=256, columns=columns):
            yield from batch.to_pylist()


# ---------------------------------------------------------------------------
def import_plantvillage(leaf_map_path: Path) -> list[ManifestRow]:
    """Righe PlantVillage con split per gruppo foglia ed etichette unificate (nessuna copia di immagini)."""
    from plantcare.data.pipeline import load_leaf_map, scan_plantvillage
    label_maps = yaml.safe_load(open(ROOT / "configs" / "label_maps.yaml", encoding="utf-8"))
    pv_dis, pv_crop = label_maps["plantvillage"], label_maps["plantvillage_crops"]
    root = DATA / "raw" / "plantvillage" / "raw" / "color"
    rows = scan_plantvillage(root, seed=42, leaf_map=load_leaf_map(leaf_map_path))
    out = []
    for r in rows:
        crop = pv_crop.get(r.plant) or PV_CROPS_FALLBACK.get(r.plant, f"altro:{r.plant}")
        dis = pv_dis.get(r.disease) or r.disease
        out.append(ManifestRow(path=_rel(root / r.path), source="plantvillage", split=r.split, plant=crop, disease=dis))
    return out


def import_ip102() -> list[ManifestRow]:
    """IP102: etichette 0-101 nel mirror (verificato), convertite all'indice 1-based di classes.txt."""
    src = EXT / "ip102" / "data"
    rows = []
    for split_name, split in (("train", "train"), ("validation", "val"), ("test", "test")):
        files = sorted(src.glob(f"{split_name}-*.parquet"))
        for i, rec in enumerate(_parquet_rows(files, ["image", "label"])):
            official = int(rec["label"]) + 1
            out = IMG / "ip102" / split / f"{official:03d}" / f"{i:06d}.jpg"
            if out.exists() or _save(rec["image"]["bytes"], out):
                rows.append(ManifestRow(path=_rel(out), source="ip102", split=split, pest=f"ip102_{official:03d}"))
    return rows


def import_plantdoc(seed: int = 42) -> list[ManifestRow]:
    """PlantDoc: ritaglio di ogni riquadro come campione di classificazione.

    Le immagini di test ufficiali restano nel test; il train ufficiale è diviso in train/val
    per immagine (non per riquadro), così i ritagli della stessa foto non finiscono in split diversi.
    """
    src = EXT / "plantdoc" / "data"
    rows = []
    for official in ("train", "test"):
        files = sorted(src.glob(f"{official}-*.parquet"))
        recs = list(_parquet_rows(files, ["image_id", "image", "objects"]))
        splits = ["test"] * len(recs) if official == "test" else _split_random(len(recs), seed, val=0.15, test=0.0)
        for rec, split in zip(recs, splits):
            obj = rec["objects"]
            for k, (bbox, cat) in enumerate(zip(obj["bbox"], obj["category"])):
                if cat not in PLANTDOC:
                    continue
                plant, dis = PLANTDOC[cat]
                x, y, w, h = bbox  # formato COCO [x, y, larghezza, altezza]
                out = IMG / "plantdoc" / split / f"{rec['image_id']}_{k}.jpg"
                if out.exists() or _save(rec["image"]["bytes"], out, (x, y, x + w, y + h)):
                    rows.append(ManifestRow(path=_rel(out), source="plantdoc", split=split, plant=plant, disease=dis))
    return rows


def import_agml(name: str, repo: str, crop: str, seed: int = 42) -> list[ManifestRow]:
    """Dataset AgML di classificazione: una sola partizione 'train' divisa 80/10/10 (casuale)."""
    src = EXT / name
    files = sorted(src.rglob("*.parquet"))
    if not files:
        return []
    names = _label_names(repo)
    recs = list(_parquet_rows(files, ["image", "label"]))
    # split stratificato per classe
    by_label = defaultdict(list)
    for i, r in enumerate(recs):
        by_label[r["label"]].append(i)
    split_of = {}
    for lab, idxs in by_label.items():
        for j, s in zip(idxs, _split_random(len(idxs), seed + zlib.crc32(str(lab).encode()) % 1000)):
            split_of[j] = s
    rows = []
    for i, r in enumerate(recs):
        lab = names[r["label"]] if names and r["label"] < len(names) else f"label_{r['label']}"
        if lab.lower().startswith(HEALTHY_WORDS):
            dis = "healthy"
        else:
            dis = AGML_DISEASE.get((name, lab), f"{name}:{lab}")
        plant = "capsicum_annuum" if crop == "capsicum_annuum_peperoncino" else crop  # stessa specie
        out = IMG / name / split_of[i] / f"{i:06d}.jpg"
        if out.exists() or _save(r["image"]["bytes"], out):
            rows.append(ManifestRow(path=_rel(out), source=name, split=split_of[i], plant=plant, disease=dis))
    return rows


def import_inatag(seed: int = 42, max_per_species: int = 1200) -> list[ManifestRow]:
    """iNatAg-mini: una cartella zip per specie, solo la testa 'plant'."""
    src = EXT / "inatag_crops"
    rows = []
    for z in sorted(src.glob("*.zip")):
        species = z.stem
        plant = INAT_SPECIES.get(species)
        if plant is None:
            continue
        with zipfile.ZipFile(z) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith((".jpg", ".jpeg", ".png"))]
            random.Random(seed).shuffle(members)
            members = members[:max_per_species]
            splits = _split_random(len(members), seed)
            for k, (m, split) in enumerate(zip(members, splits)):
                out = IMG / "inatag" / split / species / f"{k:05d}.jpg"
                if out.exists() or _save(zf.read(m), out):
                    rows.append(ManifestRow(path=_rel(out), source="inatag", split=split, plant=plant))
    return rows
