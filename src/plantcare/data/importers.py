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
import csv
import json
import random
import re
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np
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

# Etichette AgML che corrispondono a classi della tassonomia (il resto resta "<fonte>:<etichetta>").
# Chiave: (fonte, etichetta) oppure (fonte, etichetta, coltura) quando dipende dalla coltura.
AGML_DISEASE = {
    ("agml_tom2024", "alternaria-d", "solanum_lycopersicum"): "tomato_early_blight",
    ("agml_tom2024", "tomato-late-blight-d", "solanum_lycopersicum"): "tomato_late_blight",
    ("agml_tom2024", "tuta-absoluta-p", "solanum_lycopersicum"): "tomato_leafminer_damage",
    ("agml_tom2024", "rust-d", "zea_mays"): "maize_common_rust",
    ("agml_tom2024", "helminthosporiosis-d", "zea_mays"): "maize_northern_leaf_blight",
    ("agml_lemon", "Anthracnose"): "citrus_anthracnose",
    ("agml_chili", "powdery mildew"): "pepper_powdery_mildew",
    ("agml_grape", "Downy Mildew"): "grapevine_downy_mildew",
    ("agml_grape", "Powdery Mildew"): "powdery_mildew_grapevine",
    ("agml_banana", "segatoka"): "banana_black_sigatoka",
    ("agml_tuta", "infected"): "tomato_leafminer_damage",
    ("agml_potato", "Phytopthora"): "tomato_late_blight",
    ("agml_cauliflower", "Black Rot"): "broccoli_black_rot",
    # melo: stesse classi di PlantVillage e PlantDoc; la maculatura "a occhio di rana" è la fase
    # fogliare del marciume nero (Botryosphaeria obtusa)
    ("agml_appleleaf9", "Scab"): "apple_scab",
    ("agml_appleleaf9", "Rust"): "Apple___Cedar_apple_rust",
    ("agml_appleleaf9", "Frogeye leaf spot"): "Apple___Black_rot",
    # "pepper_disease_pest_classification" contiene foglie di MELO con le classi di ATLDSD
    # (verificato sulle foto): stesse etichette di AppleLeaf9, la ruggine è la ruggine del melo
    ("agml_pepperfield", "Alternaria_Boltch"): "agml_appleleaf9:Alternaria leaf spot",
    ("agml_pepperfield", "Brown_Spot"): "agml_appleleaf9:Brown spot",
    ("agml_pepperfield", "Grey_spot"): "agml_appleleaf9:Grey spot",
    ("agml_pepperfield", "Mosaic"): "agml_appleleaf9:Mosaic",
    ("agml_pepperfield", "Rust"): "Apple___Cedar_apple_rust",
    # agrumi: HLB come in PlantVillage; cocciniglia rossa e suoi esiti (macchie gialle) in una classe
    ("agml_citrusuat", "HLB"): "Orange___Haunglongbing_(Citrus_greening)",
    ("agml_citrusuat", "Red_scale_sequelae"): "agml_citrusuat:Red_scale",
    ("agml_citrusfruit", "greening"): "Orange___Haunglongbing_(Citrus_greening)",
    # foglie di arancio dolce (Bangladesh): "yellow dragon" è un altro nome dell'HLB
    ("agml_orange", "citrus_greening"): "Orange___Haunglongbing_(Citrus_greening)",
    ("agml_orange", "yellow_dragon"): "Orange___Haunglongbing_(Citrus_greening)",
    ("agml_orange", "citrus_canker"): "agml_lemon:Citrus Canker",
    ("agml_cucumber", "Downy_Mildew"): "cucurbit_downy_mildew",
    ("agml_watermelon", "Downy_Mildew"): "cucurbit_downy_mildew",
    ("agml_citrusfruit", "canker"): "agml_lemon:Citrus Canker",
    # ortaggi del Bangladesh (Hasan et al. 2024): etichette con la coltura
    ("agml_vegleaf", "Tomato Bacterial spot"): "pepper_bacterial_spot",  # come PlantVillage (Xanthomonas spp.)
    ("agml_vegleaf", "Tomato spotted wilt"): "tomato_spotted_wilt",
    ("agml_vegleaf", "Tomato Fresh leaf"): "healthy",
    ("agml_vegleaf", "Eggplant verticillium wilt"): "eggplant_verticillium",
    ("agml_vegleaf", "Eggplant fresh leaf"): "healthy",
    ("agml_vegleaf", "Downy mildew", "cucumis_sativus"): "cucurbit_downy_mildew",
    ("agml_vegleaf", "Downey mildew", "cucumis_sativus"): "cucurbit_downy_mildew",
    ("agml_vegleaf", "Black Rot", "brassica_oleracea_italica"): "broccoli_black_rot",
    # frutti di melanzana (BrinjalFruitX)
    ("agml_brinjalfruit", "Phomopsis Bright"): "eggplant_phomopsis_blight",
    ("agml_brinjalfruit", "Healty Brinjal"): "healthy",
    # patata (Laizer et al.): stesse classi di PlantVillage
    ("agml_potatoblight", "earlyblt"): "tomato_early_blight",
    ("agml_potatoblight", "lateblt"): "tomato_late_blight",
    # CCMT (Mensah et al. 2023): solo le classi con corrispondenza certa
    ("agml_ccmt", "septoria leaf spot", "solanum_lycopersicum"): "Tomato___Septoria_leaf_spot",
}
# Parte della pianta fotografata: dichiarata dal dataset (plant_part) o descritta nella sua scheda.
PLANT_PART = {0: "fruit", 1: "leaf"}  # citrus_fruit_leaf: 0 = fruit, 1 = leaf
AGML_ORGAN = {
    "agml_lemon": "leaf", "agml_grape": "leaf", "agml_banana": "leaf", "agml_onion": "leaf", "agml_chili": "leaf",
    "agml_potato": "leaf", "agml_cauliflower": "leaf", "agml_appleleaf9": "leaf", "agml_citrusuat": "leaf",
    "agml_fig": "leaf", "agml_tuta": "leaf", "agml_pomegranate": "fruit", "agml_brinjalfruit": "fruit",
    "agml_vegleaf": "leaf", "agml_potatoblight": "leaf", "agml_ccmt": "leaf", "agml_pepperfield": "leaf",
    ("agml_plum", "Healthy Fruit"): "fruit", ("agml_plum", "Healthy Leaf"): "leaf", ("agml_plum", "Insect Hole"): "leaf",
    ("agml_tom2024", "blossom-end-rot-d"): "fruit",
    "agml_orange": "leaf", "agml_cucumber": "leaf", ("agml_cucumber", "Fresh_Cucumber"): "fruit",
    ("agml_cucumber", "Belly_Rot"): "fruit", ("agml_cucumber", "Pythium_Fruit_Rot"): "fruit",
}
# Colture del dataset di ortaggi del Bangladesh (plant_type); le zucche asiatiche non sono in tassonomia.
PLANT_TYPE_CROPS = {"Tomato": "solanum_lycopersicum", "Eggplant": "solanum_melongena", "Cucumber": "cucumis_sativus",
                    "Cauliflower": "brassica_oleracea_italica", "tomato": "solanum_lycopersicum",
                    "Maize": "zea_mays", "maize": "zea_mays"}
# Dataset con le stesse etichette su colture diverse (es. "leaf blight" su mais e pomodoro): coltura nell'etichetta.
CROP_IN_LABEL = {"agml_ccmt"}
# Dataset con scatti in sequenza: split per blocchi di record consecutivi e tetto di foto per classe.
SPLIT_BLOCK = {"agml_pepperfield": 50}
PER_CLASS_CAP = {"agml_pepperfield": 1500, "agml_cucumber": 500}
# Classi senza una diagnosi univoca (es. "foglia morta", "frutto non sano"): non usate.
AGML_SKIP = {("agml_plum", "Dead Leaf"), ("agml_plum", "Yellow"), ("agml_plum", "Unhealthy Fruit"),
             # classi ATLDSD di AppleLeaf9: le stesse foto (e scatti vicini) sono in agml_pepperfield,
             # che ne ha di più e uno split per blocchi; tenerle in entrambe porterebbe copie nel test
             ("agml_appleleaf9", "Alternaria leaf spot"), ("agml_appleleaf9", "Brown spot"),
             ("agml_appleleaf9", "Grey spot"), ("agml_appleleaf9", "Mosaic")}
HEALTHY_WORDS = ("healthy", "health", "sano", "normal", "fresh")
TOM2024_CROPS = {"Tomato": "solanum_lycopersicum", "Onion": "allium_cepa_tropea", "Maize": "zea_mays"}

# Lettore delle carenze: etichette nutrizionali dichiarate dagli autori dei dataset (nutriente non indicato).
DEFICIENCY = {
    ("agml_lemon", "Deficiency Leaf"): "sintomi_di_carenza",
    ("agml_chili", "nutritional"): "sintomi_di_carenza",
    ("agml_tom2024", "excess-nitrogen-d"): "eccesso_di_azoto",
    # marciume apicale: sintomo della carenza di calcio indicato anche in configs/taxonomy.yaml (nutriente Ca)
    ("agml_tom2024", "blossom-end-rot-d"): "carenza_di_calcio",
    # CitrusUAT (Gómez-Flores et al. 2024): carenze dei singoli nutrienti su arancio
    ("agml_citrusuat", "Fe"): "carenza_di_ferro",
    ("agml_citrusuat", "Mg"): "carenza_di_magnesio",
    ("agml_citrusuat", "Mn"): "carenza_di_manganese",
    ("agml_citrusuat", "N"): "carenza_di_azoto",
    ("agml_citrusuat", "'N'"): "carenza_di_azoto",
    ("agml_citrusuat", "Zn"): "carenza_di_zinco",
}
DEFICIENCY_SOURCES = {"agml_lemon", "agml_chili", "agml_tom2024", "agml_citrusuat"}
NO_NUTRITIONAL_DISORDER = "nessun_disturbo_nutrizionale"


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


def _label_names(repo: str, config: str = "raw", feature: str = "label") -> list[str] | None:
    """Nomi delle classi dalla scheda del dataset su Hugging Face (cardData).

    Se la scheda descrive più configurazioni (es. raw e augmented) usa quella richiesta.
    """
    import urllib.request
    try:
        d = json.load(urllib.request.urlopen(f"https://huggingface.co/api/datasets/{repo}", timeout=60))
        info = d["cardData"]["dataset_info"]
    except Exception:
        return None
    infos = info if isinstance(info, list) else [info]
    chosen = next((i for i in infos if i.get("config_name") == config), infos[0])
    for f in chosen.get("features", []):
        if f.get("name") != feature:
            continue
        cl = f.get("dtype", {})
        if isinstance(cl, dict) and "class_label" in cl:
            names = cl["class_label"]["names"]
            return [names[str(i)] for i in range(len(names))] if isinstance(names, dict) else list(names)
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
        out.append(ManifestRow(path=_rel(root / r.path), source="plantvillage", split=r.split, plant=crop, disease=dis,
                               organ="leaf"))
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
                    rows.append(ManifestRow(path=_rel(out), source="plantdoc", split=split, plant=plant, disease=dis,
                                           organ="leaf"))
    return rows


def import_agml(name: str, repo: str, crop: str, seed: int = 42) -> list[ManifestRow]:
    """Dataset AgML di classificazione: una sola partizione 'train' divisa 80/10/10 (casuale)."""
    src = EXT / name
    if name == "agml_potatoblight":
        return import_potatoblight(crop, seed=seed)
    files = sorted(src.rglob("*.parquet"))
    if not files:
        # file originali rimossi per spazio: si riusano le righe già importate (le foto sono in data/external/images)
        return _rows_from_manifest(name, crop)
    names = _label_names(repo)
    schema = pq.ParquetFile(files[0]).schema_arrow.names
    crop_feature = "plant_type" if "plant_type" in schema else ("crop" if "crop" in schema else None)
    plant_types = _label_names(repo, feature=crop_feature) if crop_feature else None
    has_part = "plant_part" in schema
    has_crop = "crop_type" in schema
    recs = list(_parquet_rows(files, ["image", "label"] + (["crop_type"] if has_crop else [])
                              + (["plant_part"] if has_part else []) + ([crop_feature] if crop_feature else [])))
    # split stratificato per classe
    by_label = defaultdict(list)
    for i, r in enumerate(recs):
        by_label[r["label"]].append(i)
    split_of = {}
    cap = PER_CLASS_CAP.get(name)
    for lab, idxs in by_label.items():
        lab_seed = seed + zlib.crc32(str(lab).encode()) % 1000
        if name in SPLIT_BLOCK:
            blocks = sorted({j // SPLIT_BLOCK[name] for j in idxs})
            bsplit = dict(zip(blocks, _split_random(len(blocks), lab_seed)))
            if cap and len(idxs) > cap:
                idxs = sorted(random.Random(lab_seed).sample(idxs, cap))
            for j in idxs:
                split_of[j] = bsplit[j // SPLIT_BLOCK[name]]
            continue
        for j, s in zip(idxs, _split_random(len(idxs), lab_seed)):
            split_of[j] = s
    dup = set()
    if name == "agml_appleleaf9":
        dup = _plantvillage_duplicates(recs)
        _same_split_for_duplicates(recs, split_of)
    rows = []
    for i, r in enumerate(recs):
        lab = names[r["label"]] if names and r["label"] < len(names) else f"label_{r['label']}"
        if (name, lab) in AGML_SKIP or i in dup or i not in split_of:
            continue
        row_crop = TOM2024_CROPS.get(r.get("crop_type"), crop) if has_crop else crop
        if crop_feature:  # coltura indicata per foto (indice nei nomi, oppure testo)
            v = r[crop_feature]
            row_crop = PLANT_TYPE_CROPS.get(plant_types[v] if plant_types and isinstance(v, int) else v)
            if row_crop is None:
                continue
        deficiency = ""
        if (name, lab) in DEFICIENCY:
            deficiency = DEFICIENCY[(name, lab)]
            dis = "disturbo_nutrizionale"
        elif lab.lower().startswith(HEALTHY_WORDS):
            dis = "healthy"
        else:
            raw = f"{name}:{row_crop}:{lab}" if name in CROP_IN_LABEL else f"{name}:{lab}"
            dis = AGML_DISEASE.get((name, lab, row_crop)) or AGML_DISEASE.get((name, lab)) or raw
        if not deficiency and name in DEFICIENCY_SOURCES:
            deficiency = NO_NUTRITIONAL_DISORDER
        plant = "capsicum_annuum" if row_crop == "capsicum_annuum_peperoncino" else row_crop  # stessa specie
        out = IMG / name / split_of[i] / f"{i:06d}.jpg"
        if out.exists() or _save(r["image"]["bytes"], out):
            part = PLANT_PART.get(r.get("plant_part")) if has_part else None
            organ = part or AGML_ORGAN.get((name, lab)) or AGML_ORGAN.get(name, "")
            rows.append(ManifestRow(path=_rel(out), source=name, split=split_of[i], plant=plant, disease=dis,
                                    deficiency=deficiency, organ=organ))
    return rows


def import_potatoblight(crop: str, seed: int = 42, per_class: int = 2500, block: int = 50) -> list[ManifestRow]:
    """Patata (Laizer et al.): zip con una cartella per classe; campione di `per_class` foto per classe.

    Le foto con numeri vicini sono scatti in sequenza della stessa pianta: lo split è fatto per
    blocchi di `block` numeri consecutivi, così la stessa pianta non finisce in train e in test.
    """
    import re
    z_path = EXT / "agml_potatoblight" / "potato_leaf_blight.zip"
    if not z_path.exists():
        # zip rimosso per spazio: righe dalle foto già salvate (<split>/<classe>/<n>.jpg)
        rows = []
        for f in sorted((IMG / "agml_potatoblight").glob("*/*/*.jpg")):
            split, lab = f.parent.parent.name, f.parent.name
            dis = "healthy" if lab == "healthy" else AGML_DISEASE.get(("agml_potatoblight", lab), f"agml_potatoblight:{lab}")
            rows.append(ManifestRow(path=_rel(f), source="agml_potatoblight", split=split, plant=crop, disease=dis,
                                    organ="leaf"))
        return rows
    rng = random.Random(seed)
    rows = []
    with zipfile.ZipFile(z_path) as zf:
        by_class = defaultdict(list)
        for m in zf.namelist():
            parts = m.split("/")
            if parts[0] == "images" and len(parts) == 3 and m.lower().endswith((".jpg", ".jpeg", ".png")):
                by_class[parts[1]].append(m)
        for lab, members in sorted(by_class.items()):
            groups = defaultdict(list)
            for m in members:
                num = re.findall(r"\d+", m.rsplit("/", 1)[-1])
                groups[int(num[-1]) // block if num else 0].append(m)
            keys = sorted(groups)
            rng.shuffle(keys)
            split_of_group = dict(zip(keys, _split_random(len(keys), seed + zlib.crc32(lab.encode()) % 1000)))
            members = sorted(members)
            rng.shuffle(members)
            for k, m in enumerate(members[:per_class]):
                num = re.findall(r"\d+", m.rsplit("/", 1)[-1])
                split = split_of_group[int(num[-1]) // block if num else 0]
                dis = "healthy" if lab == "healthy" else AGML_DISEASE.get(("agml_potatoblight", lab), f"agml_potatoblight:{lab}")
                out = IMG / "agml_potatoblight" / split / lab / f"{k:05d}.jpg"
                if out.exists() or _save(zf.read(m), out):
                    rows.append(ManifestRow(path=_rel(out), source="agml_potatoblight", split=split, plant=crop,
                                            disease=dis, organ="leaf"))
    return rows


# PlantWild v2 (Wei et al. 2024): classe -> (coltura, malattia). Coltura vuota quando la specie non è certa
# (cavolo, zucca, frumento tenero o duro, agrumi). Colture fuori tassonomia escluse.
_PW_CROPS = {"apple": "malus_domestica", "banana": "musa_spp", "bell pepper": "capsicum_annuum",
             "broccoli": "brassica_oleracea_italica", "cauliflower": "brassica_oleracea_italica", "cabbage": "",
             "cherry": "prunus_avium", "citrus": "", "corn": "zea_mays", "cucumber": "cucumis_sativus",
             "eggplant": "solanum_melongena", "garlic": "allium_sativum", "grape": "vitis_vinifera",
             "grapevine": "vitis_vinifera", "lettuce": "lactuca_sativa", "peach": "prunus_persica",
             "plum": "prunus_domestica", "potato": "solanum_tuberosum", "squash": "", "strawberry": "fragaria_ananassa",
             "tomato": "solanum_lycopersicum", "wheat": "", "zucchini": "cucurbita_pepo"}
_PW_DISEASE = {
    "apple black rot": "Apple___Black_rot", "apple mosaic virus": "agml_appleleaf9:Mosaic",
    "apple rust": "Apple___Cedar_apple_rust", "apple scab": "apple_scab",
    "banana black leaf streak": "banana_black_sigatoka", "banana panama disease": "banana_panama_disease",
    "bell pepper bacterial spot": "pepper_bacterial_spot", "bell pepper frogeye leaf spot": "agml_chili:cercospora",
    "bell pepper powdery mildew": "pepper_powdery_mildew",
    "broccoli alternaria leaf spot": "broccoli_alternaria", "cabbage alternaria leaf spot": "broccoli_alternaria",
    "cauliflower alternaria leaf spot": "broccoli_alternaria", "cabbage black rot": "broccoli_black_rot",
    "broccoli downy mildew": "agml_vegleaf:Downy mildew", "cabbage downy mildew": "agml_vegleaf:Downy mildew",
    "cherry leaf spot": "cherry_leaf_spot", "cherry powdery mildew": "Cherry_(including_sour)___Powdery_mildew",
    "citrus canker": "agml_lemon:Citrus Canker", "citrus greening disease": "Orange___Haunglongbing_(Citrus_greening)",
    "corn gray leaf spot": "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
    "corn northern leaf blight": "maize_northern_leaf_blight", "corn rust": "maize_common_rust",
    "cucumber angular leaf spot": "cucumber_angular_leaf_spot", "cucumber powdery mildew": "zucchini_powdery_mildew",
    "squash powdery mildew": "zucchini_powdery_mildew", "zucchini powdery mildew": "zucchini_powdery_mildew",
    "zucchini downy mildew": "cucurbit_downy_mildew",
    "eggplant cercospora leaf spot": "agml_vegleaf:Eggplant Cercopora leaf spot",
    "eggplant phomopsis fruit rot": "eggplant_phomopsis_blight", "garlic rust": "garlic_rust",
    "grape black rot": "Grape___Black_rot", "grape downy mildew": "grapevine_downy_mildew",
    "lettuce downy mildew": "lettuce_downy_mildew", "peach brown rot": "apple_brown_rot",
    "plum brown rot": "apple_brown_rot", "peach leaf curl": "peach_leaf_curl", "plum pox virus": "peach_plum_pox",
    "plum bacterial spot": "peach_bacterial_spot", "potato early blight": "tomato_early_blight",
    "potato late blight": "tomato_late_blight", "strawberry leaf scorch": "Strawberry___Leaf_scorch",
    "tomato bacterial leaf spot": "pepper_bacterial_spot", "tomato early blight": "tomato_early_blight",
    "tomato late blight": "tomato_late_blight", "tomato leaf mold": "Tomato___Leaf_Mold",
    "tomato mosaic virus": "tomato_mosaic_virus", "tomato septoria leaf spot": "Tomato___Septoria_leaf_spot",
    "tomato yellow leaf curl virus": "tomato_yellow_leaf_curl", "wheat leaf rust": "wheat_leaf_rust",
    "wheat septoria blotch": "wheat_septoria", "wheat powdery mildew": "wheat_powdery_mildew",
}
_PW_DEFICIENCY = {"bell pepper blossom end rot": "carenza_di_calcio"}
_PW_FRUIT = {"bell pepper blossom end rot", "eggplant phomopsis fruit rot", "peach brown rot", "plum brown rot",
             "plum pocket disease", "peach scab", "wheat head scab", "wheat loose smut", "corn smut",
             "banana cigar end rot", "carrot cavity spot"}


def _plantdoc_hashes() -> np.ndarray:
    """dhash di tutte le foto intere di PlantDoc, per escludere le copie presenti in altri dataset web."""
    out = []
    for f in sorted((EXT / "plantdoc").rglob("*.parquet")):
        for r in pq.read_table(f, columns=["image"]).to_pylist():
            try:
                out.append([int(b) for b in f"{_dhash(r['image']['bytes']):0256b}"])
            except Exception:
                pass
    return np.packbits(np.array(out, dtype=np.uint8), axis=1) if out else np.zeros((0, 32), np.uint8)


def import_plantwild(seed: int = 42, max_dist: int = 24) -> list[ManifestRow]:
    """PlantWild v2: foto di malattie 'in natura' (CC BY-NC-ND: uso non commerciale, solo addestramento)."""
    z_path = EXT / "plantwild" / "plantwild_v2.zip"
    if not z_path.exists():
        return _rows_from_manifest("plantwild")
    table = np.array([bin(x).count("1") for x in range(256)], dtype=np.uint16)
    pd_hash = _plantdoc_hashes()
    recs, n_pd = [], 0
    with zipfile.ZipFile(z_path) as zf:
        for m in sorted(zf.namelist()):
            parts = m.split("/")
            if len(parts) != 3 or "__MACOSX" in m or not m.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            cls = parts[1]
            crop_key = next((k for k in sorted(_PW_CROPS, key=len, reverse=True) if cls.startswith(k + " ")), None)
            if crop_key is None:
                continue
            data = zf.read(m)
            try:
                h = np.packbits(np.array([int(b) for b in f"{_dhash(data):0256b}"], dtype=np.uint8))
            except Exception:
                continue
            if len(pd_hash) and table[np.bitwise_xor(pd_hash, h)].sum(1).min() <= max_dist:
                n_pd += 1
                continue
            recs.append({"image": {"bytes": data}, "cls": cls, "crop": _PW_CROPS[crop_key]})
    by_cls = defaultdict(list)
    for i, r in enumerate(recs):
        by_cls[r["cls"]].append(i)
    split_of = {}
    for cls, idxs in by_cls.items():
        for j, sp in zip(idxs, _split_random(len(idxs), seed + zlib.crc32(cls.encode()) % 1000)):
            split_of[j] = sp
    _same_split_for_duplicates(recs, split_of)
    rows = []
    for i, r in enumerate(recs):
        cls = r["cls"]
        deficiency = _PW_DEFICIENCY.get(cls, "")
        dis = "disturbo_nutrizionale" if deficiency else _PW_DISEASE.get(cls, f"plantwild:{cls}")
        out = IMG / "plantwild" / split_of[i] / f"{i:06d}.jpg"
        if out.exists() or _save(r["image"]["bytes"], out):
            rows.append(ManifestRow(path=_rel(out), source="plantwild", split=split_of[i], plant=r["crop"], disease=dis,
                                    deficiency=deficiency, organ="fruit" if cls in _PW_FRUIT else ""))
    print(f"  plantwild: {n_pd} copie di PlantDoc escluse", flush=True)
    return rows


def _rows_from_manifest(source: str, crop: str | None = None) -> list[ManifestRow]:
    """Righe già importate, per quando i file originali sono stati rimossi per spazio.

    Si riapplicano AGML_SKIP e AGML_DISEASE alle etichette grezze ("<fonte>:<classe>") e, per i
    dataset di una sola coltura, la coltura del registro: così una correzione vale anche senza i file.
    """
    man = DATA / "processed" / "manifest_v2.csv"
    if not man.exists():
        return []
    with open(man, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["source"] == source and (DATA / r["path"]).exists()]
    single_crop = len({r["plant"] for r in rows}) == 1
    if crop == "capsicum_annuum_peperoncino":
        crop = "capsicum_annuum"
    out = []
    for r in rows:
        if r["disease"].startswith(source + ":"):
            raw = r["disease"][len(source) + 1:]
            if (source, raw) in AGML_SKIP:
                continue
            r["disease"] = AGML_DISEASE.get((source, raw)) or r["disease"]
        if crop and single_crop:
            r["plant"] = crop
        out.append(ManifestRow(**{k: r.get(k, "") for k in ManifestRow.__dataclass_fields__}))
    return out


def _dhash(img_bytes_or_path, size: int = 16) -> int:
    src = io.BytesIO(img_bytes_or_path) if isinstance(img_bytes_or_path, bytes) else img_bytes_or_path
    with Image.open(src) as im:
        a = np.asarray(im.convert("L").resize((size + 1, size), Image.BILINEAR), dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def _plantvillage_duplicates(recs, max_dist: int = 24) -> set[int]:
    """Indici delle foto che sono copie (anche ridimensionate) di foto di melo di PlantVillage.

    AppleLeaf9 include PlantVillage: senza questo controllo le stesse foglie finirebbero sia
    nell'addestramento sia nel test, gonfiando le misure.
    """
    pv = sorted((DATA / "raw" / "plantvillage" / "raw" / "color").glob("Apple___*/*"))
    ref = np.array([_dhash(p) for p in pv if p.suffix.lower() in (".jpg", ".jpeg", ".png")], dtype=object)
    if not len(ref):
        return set()
    ref_bits = np.array([[int(b) for b in f"{h:0256b}"] for h in ref], dtype=np.uint8)
    out = set()
    for i, r in enumerate(recs):
        try:
            h = _dhash(r["image"]["bytes"])
        except Exception:
            continue
        q = np.array([int(b) for b in f"{h:0256b}"], dtype=np.uint8)
        if (ref_bits != q).sum(1).min() <= max_dist:
            out.add(i)
    print(f"  agml_appleleaf9: {len(out)} copie di PlantVillage escluse", flush=True)
    return out


def _same_split_for_duplicates(recs, split_of: dict, max_dist: int = 24) -> None:
    """Copie della stessa foto nello stesso split (AppleLeaf9 unisce Plant Pathology 2020 e 2021)."""
    hashes = []
    for r in recs:
        try:
            hashes.append(_dhash(r["image"]["bytes"]))
        except Exception:
            hashes.append(None)
    ok = [i for i, h in enumerate(hashes) if h is not None]
    bits = np.array([[int(b) for b in f"{hashes[i]:0256b}"] for i in ok], dtype=np.uint8)
    packed = np.packbits(bits, axis=1)
    table = np.array([bin(x).count("1") for x in range(256)], dtype=np.uint16)
    moved = 0
    for a in range(len(ok)):
        d = table[np.bitwise_xor(packed[a + 1:], packed[a])].sum(1)
        for b in np.nonzero(d <= max_dist)[0] + a + 1:
            i, j = ok[a], ok[b]
            if split_of[j] != split_of[i]:
                split_of[j] = split_of[i]
                moved += 1
    print(f"  {len(recs)} foto: {moved} copie spostate nello split della prima", flush=True)


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


# ---------------------------------------------------------------------------
# Contributi dall'app (foto di campo etichettate da agronomi)
# ---------------------------------------------------------------------------
CONTRIB_CSV = DATA / "processed" / "contributi.csv"
CONTRIB_SCHEMA = "plantcare-contributi/1"


def _contrib_split(item_id: str) -> str:
    """Split stabile per contributo: 30% test di campo, 10% validazione, 60% addestramento."""
    h = zlib.crc32(item_id.encode()) % 100
    return "test" if h < 30 else ("val" if h < 40 else "train")


def import_contributions(files: list[Path]) -> tuple[int, int, list[str]]:
    """Legge i file esportati dall'app e aggiunge le foto a data/external/images/contributi/.

    Restituisce (nuovi, già presenti, avvisi). Le righe vanno in data/processed/contributi.csv,
    che import-external aggiunge al manifest unificato.
    """
    import base64
    from plantcare.data.pipeline import MANIFEST_COLUMNS

    existing = set()
    if CONTRIB_CSV.exists():
        with open(CONTRIB_CSV, newline="", encoding="utf-8") as fh:
            existing = {r["id"] for r in csv.DictReader(fh)}
    cols = ["id", "date", "province", "organ", "diagnosis_source", "note"] + MANIFEST_COLUMNS
    new_rows, skipped, warnings = [], 0, []
    for f in files:
        payload = json.loads(Path(f).read_text(encoding="utf-8"))
        if payload.get("schema") != CONTRIB_SCHEMA:
            warnings.append(f"{f}: schema non riconosciuto ({payload.get('schema')})")
            continue
        for it in payload.get("items", []):
            iid = str(it.get("id", ""))
            if not iid or not it.get("photo", "").startswith("data:image/jpeg;base64,"):
                warnings.append(f"{f}: contributo senza id o senza foto JPEG, ignorato")
                continue
            if iid in existing:
                skipped += 1
                continue
            c = it.get("correct", {})
            disease = c.get("disease", "")
            if disease.startswith("altro:"):
                disease = ""  # malattia non in elenco: resta nelle note, non è un'etichetta di addestramento
            if not (c.get("plant") or disease or c.get("deficiency")):
                warnings.append(f"{f}: contributo {iid} senza nessuna etichetta, ignorato")
                continue
            split = _contrib_split(iid)
            out = IMG / "contributi" / f"{iid}.jpg"
            out.parent.mkdir(parents=True, exist_ok=True)
            raw = base64.b64decode(it["photo"].split(",", 1)[1])
            if not _save(raw, out):
                warnings.append(f"{f}: foto del contributo {iid} non leggibile")
                continue
            new_rows.append({"id": iid, "date": it.get("date", ""), "province": it.get("province", ""),
                             "organ": it.get("organ", ""), "diagnosis_source": it.get("diagnosis_source", ""),
                             "note": it.get("note", "")[:300], "path": _rel(out), "source": "contributi", "split": split,
                             "plant": c.get("plant", ""), "disease": disease, "pest": "", "deficiency": c.get("deficiency", "")})
            existing.add(iid)
    if new_rows:
        write_header = not CONTRIB_CSV.exists()
        CONTRIB_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(CONTRIB_CSV, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            if write_header:
                w.writeheader()
            w.writerows(new_rows)
    return len(new_rows), skipped, warnings


def contribution_rows() -> list[ManifestRow]:
    if not CONTRIB_CSV.exists():
        return []
    with open(CONTRIB_CSV, newline="", encoding="utf-8") as fh:
        return [ManifestRow(path=r["path"], source="contributi", split=r["split"], plant=r["plant"],
                            disease=r["disease"], deficiency=r["deficiency"], organ=r.get("organ", ""))
                for r in csv.DictReader(fh)]


def import_inat_calabria(seed: int = 42) -> list[ManifestRow]:
    """Insetti e acari della Calabria da iNaturalist (scripts/import_inat_train.py) per il lettore
    degli insetti. Split per autore della foto (10% test, 10% validazione): lo stesso fotografo non
    finisce in due split, perché spesso riprende più volte lo stesso individuo."""
    man = EXT / "inat_calabria" / "manifest.json"
    if not man.exists():
        return []
    rows = []
    for key, e in sorted(json.load(open(man, encoding="utf-8")).items()):
        disease = e.get("tipo") == "malattia"
        for p in e.get("foto", []):
            if not (DATA / p["path"]).exists():
                continue
            h = zlib.crc32(f"{seed}:{p['user']}".encode()) % 100
            split = "test" if h < 10 else ("val" if h < 20 else "train")
            if disease:  # malattia: classe nuova o esistente, coltura solo se l'ospite è certo
                rows.append(ManifestRow(path=p["path"], source="inat_calabria", split=split, plant=e.get("coltura") or "",
                                        disease=e["classe"], pest="", deficiency="", organ=""))
            else:
                rows.append(ManifestRow(path=p["path"], source="inat_calabria", split=split, plant="", disease="",
                                        pest=f"inat:{key}", deficiency="", organ=""))
    return rows


def append_inat_calabria() -> int:
    """Aggiorna nel manifest le righe di inat_calabria senza rifare l'importazione di tutte le fonti."""
    from dataclasses import asdict
    from plantcare.data.pipeline import MANIFEST_COLUMNS
    path = DATA / "processed" / "manifest_v2.csv"
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["source"] != "inat_calabria"]
    new = [asdict(r) for r in import_inat_calabria()]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(rows)
        w.writerows({k: r.get(k, "") for k in MANIFEST_COLUMNS} for r in new)
    return len(new)


FIELDVITIS = {"Esca": "grapevine_esca", "Healthy": "healthy", "Black_rot": "Grape___Black_rot",
              "Leaf_blight": "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)"}


def import_fieldvitis(seed: int = 42, max_dist: int = 24) -> list[ManifestRow]:
    """FieldVitis (Zenodo 17307846, CC BY 4.0): foglie di vite in campo, con il mal dell'esca. Unisce foto
    di ESCA-dataset, PlantDoc e Grape Disease: le copie di PlantDoc si escludono (test di PlantDoc pulito),
    le copie interne vanno nello stesso split."""
    z_path = EXT / "fieldvitis" / "fieldvitis.zip"
    if not z_path.exists():
        return _rows_from_manifest("fieldvitis")
    table = np.array([bin(x).count("1") for x in range(256)], dtype=np.uint16)
    pd_hash = _plantdoc_hashes()
    recs, n_pd = [], 0
    with zipfile.ZipFile(z_path) as zf:
        for m in sorted(zf.namelist()):
            cls = m.split("/")[-2] if "/" in m else ""
            if cls not in FIELDVITIS or not m.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            data = zf.read(m)
            try:
                h = np.packbits(np.array([int(b) for b in f"{_dhash(data):0256b}"], dtype=np.uint8))
            except Exception:
                continue
            if len(pd_hash) and table[np.bitwise_xor(pd_hash, h)].sum(1).min() <= max_dist:
                n_pd += 1
                continue
            recs.append({"image": {"bytes": data}, "cls": cls})
    by = defaultdict(list)
    for i, r in enumerate(recs):
        by[r["cls"]].append(i)
    split_of = {}
    for cls, idxs in by.items():
        for j, s in zip(idxs, _split_random(len(idxs), seed + zlib.crc32(cls.encode()) % 1000)):
            split_of[j] = s
    _same_split_for_duplicates(recs, split_of)
    rows = []
    for i, r in enumerate(recs):
        out = IMG / "fieldvitis" / split_of[i] / f"{i:05d}.jpg"
        if out.exists() or _save(r["image"]["bytes"], out):
            rows.append(ManifestRow(path=_rel(out), source="fieldvitis", split=split_of[i], plant="vitis_vinifera",
                                    disease=FIELDVITIS[r["cls"]], organ="leaf"))
    print(f"  fieldvitis: {len(rows)} foto, {n_pd} copie di PlantDoc escluse", flush=True)
    return rows


def _hash_bits(data) -> np.ndarray | None:
    try:
        return np.packbits(np.array([int(b) for b in f"{_dhash(data):0256b}"], dtype=np.uint8))
    except Exception:
        return None


def import_plantseg(max_dist: int = 24) -> list[ManifestRow]:
    """PlantSeg (Wei et al. 2024, CC BY-NC-ND: uso non commerciale, solo addestramento): foto di malattie
    raccolte sul web, dagli stessi autori di PlantWild e con gli stessi nomi delle classi. Si escludono le
    copie di foto di PlantDoc e di PlantWild (le loro prove restano pulite); si tiene lo split originale."""
    files = sorted((EXT / "plantseg").glob("*.parquet"))
    if not files:
        return _rows_from_manifest("plantseg")
    table = np.array([bin(x).count("1") for x in range(256)], dtype=np.uint16)
    ref = [_plantdoc_hashes()]
    pw = [h for f in sorted((IMG / "plantwild").rglob("*.jpg")) if (h := _hash_bits(f)) is not None]
    if pw:
        ref.append(np.stack(pw))
    ref = np.concatenate([r for r in ref if len(r)]) if any(len(r) for r in ref) else np.zeros((0, 32), np.uint8)
    split_map = {"train": "train", "validation": "val", "test": "test"}
    rows, n_dup, seen, n_seen = [], 0, np.zeros((20000, 32), np.uint8), 0
    for f in files:
        for k, r in enumerate(_parquet_rows([f], ["image", "plant", "disease", "split"])):
            cls = r["disease"].strip()
            crop_key = next((c for c in sorted(_PW_CROPS, key=len, reverse=True) if cls.startswith(c + " ")), None)
            if crop_key is None:
                continue
            data = r["image"]["bytes"]
            h = _hash_bits(data)
            if h is None:
                continue
            if len(ref) and table[np.bitwise_xor(ref, h)].sum(1).min() <= max_dist:
                n_dup += 1
                continue
            if n_seen and table[np.bitwise_xor(seen[:n_seen], h)].sum(1).min() <= max_dist:
                n_dup += 1  # copia interna: si tiene solo la prima
                continue
            seen[n_seen] = h
            n_seen += 1
            split = split_map.get(r["split"], "train")
            deficiency = _PW_DEFICIENCY.get(cls, "")
            dis = "disturbo_nutrizionale" if deficiency else _PW_DISEASE.get(cls, f"plantwild:{cls}")
            out = IMG / "plantseg" / split / f"{f.stem[-14:-9]}_{k:05d}.jpg"
            if out.exists() or _save(data, out):
                rows.append(ManifestRow(path=_rel(out), source="plantseg", split=split, plant=_PW_CROPS[crop_key],
                                        disease=dis, deficiency=deficiency,
                                        organ="fruit" if cls in _PW_FRUIT else ""))
    print(f"  plantseg: {len(rows)} foto, {n_dup} copie di PlantDoc/PlantWild o interne escluse", flush=True)
    return rows


def import_letteratura() -> list[ManifestRow]:
    """Foto di sintomi da pubblicazioni e banche dati didattiche (configs/foto_letteratura.yaml): poche
    foto per malattie senza altre fonti aperte (mal secco degli agrumi), tutte nell'addestramento."""
    cfg = yaml.safe_load(open(ROOT / "configs" / "foto_letteratura.yaml", encoding="utf-8"))
    out = []
    for f in cfg["foto"]:
        if not (DATA / f["path"]).exists():
            continue
        pest = f.get("testa") == "pest"
        out.append(ManifestRow(path=f["path"], source="letteratura", split="train", plant=f.get("coltura") or "",
                               disease="" if pest else f["classe"], pest=f["classe"] if pest else "",
                               organ=f.get("organo", "")))
    return out


def _split_by(key: str, seed: int = 42) -> str:
    h = zlib.crc32(f"{seed}:{key}".encode()) % 100
    return "test" if h < 10 else ("val" if h < 20 else "train")


def _rows_from_targets(source: str, man_path: Path, author_key: str) -> list[ManifestRow]:
    """Righe da un manifest {obiettivo: {classe, testa, coltura, foto: [...]}}; split per autore.
    Le classi nuove (prefisso "bw:") si usano solo se hanno una causa in configs/disease_causes.yaml."""
    if not man_path.exists():
        return []
    from plantcare.causes import load_causes
    known = set(load_causes()[1])
    rows = []
    for e in json.load(open(man_path, encoding="utf-8")).values():
        pest = e.get("testa") == "pest"
        if e["classe"].startswith("bw:") and e["classe"] not in known:
            continue
        for p in e.get("foto", []):
            if not (DATA / p["path"]).exists():
                continue
            rows.append(ManifestRow(path=p["path"], source=source, split=_split_by(p.get(author_key) or p["path"]),
                                    plant=e.get("coltura") or "", disease="" if pest else e["classe"],
                                    pest=e["classe"] if pest else "", organ=""))
    return rows


def import_bugwood() -> list[ManifestRow]:
    """Bugwood Images (scripts/import_bugwood.py): soggetti identificati da specialisti; split per autore."""
    return _rows_from_targets("bugwood", EXT / "bugwood" / "manifest.json", "autore")


def import_observation() -> list[ManifestRow]:
    """Observation.org via GBIF (scripts/import_observation.py): solo identificazioni approvate; split per autore."""
    return _rows_from_targets("observation", EXT / "observation" / "manifest.json", "autore")


def import_emiliaromagna() -> list[ManifestRow]:
    """Schede del Servizio fitosanitario dell'Emilia-Romagna (scripts/import_emiliaromagna.py): tutte
    nell'addestramento (poche foto per scheda, spesso dello stesso focolaio)."""
    man = EXT / "emiliaromagna" / "manifest.json"
    if not man.exists():
        return []
    out = []
    for f in json.load(open(man, encoding="utf-8")):
        if not (DATA / f["path"]).exists():
            continue
        pest = f["testa"] == "pest"
        out.append(ManifestRow(path=f["path"], source="emiliaromagna", split="train", plant=f.get("coltura") or "",
                               disease="" if pest else f["classe"], pest=f["classe"] if pest else "", organ=""))
    return out


DIAMOS = {"healthy": "healthy", "slug": "diamos:pear_slug", "spot": "diamos:pear_leaf_spot"}


def import_diamos(seed: int = 42, block: int = 20) -> list[ManifestRow]:
    """DiaMOS Plant (Zenodo 5557313, CC BY 4.0): foglie di pero in campo in Sardegna (scripts/import_diamos.py).
    Gli scatti sono numerati in sequenza: split per blocchi di 20 numeri consecutivi (foglie vicine nello
    stesso split)."""
    rows = []
    for cls, dis in DIAMOS.items():
        for f in sorted((IMG / "diamos" / cls).glob("*.jpg")):
            num = int(re.sub(r"\D", "", f.stem) or 0)
            h = zlib.crc32(f"{seed}:{cls}:{num // block}".encode()) % 100
            split = "test" if h < 10 else ("val" if h < 20 else "train")
            rows.append(ManifestRow(path=_rel(f), source="diamos", split=split, plant="pyrus_communis", disease=dis,
                                    organ="leaf"))
    return rows


def import_vinevirus(seed: int = 42) -> list[ManifestRow]:
    """Vine Virus Photo Dataset (CC BY 4.0, scripts/import_vinevirus.py): viti in vigneto con lo stato virale
    verificato in laboratorio; accartocciamento fogliare (GLRaV-3) e viti senza virus. Split casuale."""
    man = EXT / "vinevirus" / "stato.json"
    if not man.exists():
        return []
    cls = {"leafroll": "plantwild:grapevine leafroll disease", "no_virus": "healthy"}
    rows = []
    for f in json.load(open(man, encoding="utf-8"))["foto"]:
        if not (DATA / f["path"]).exists():
            continue
        h = zlib.crc32(f"{seed}:{f['path']}".encode()) % 100
        split = "test" if h < 10 else ("val" if h < 20 else "train")
        rows.append(ManifestRow(path=f["path"], source="vinevirus", split=split, plant="vitis_vinifera",
                                disease=cls[f["classe"]], organ=""))
    return rows


def import_aperti(seed: int = 42) -> list[ManifestRow]:
    """Dataset aperti di foto di campo (CC BY 4.0, scripts/import_aperti.py): esca e peronospora della vite,
    agrumi del Marocco, limone, peperone. Split per fonte e foto: 10% test, 10% val."""
    man = EXT / "aperti" / "manifest.json"
    if not man.exists():
        return []
    rows = []
    for f in json.load(open(man, encoding="utf-8")):
        if not (DATA / f["path"]).exists():
            continue
        h = zlib.crc32(f"{seed}:{f['path']}".encode()) % 100
        split = "test" if h < 10 else ("val" if h < 20 else "train")
        rows.append(ManifestRow(path=f["path"], source="aperti", split=split, plant=f.get("pianta", ""),
                                disease=f["classe"], organ=""))
    return rows


def import_verificate() -> list[ManifestRow]:
    """Foto da bollettini, PDF, tesi e articoli verificate a vista una per una
    (data/external/verificate/*.json, una lista per fonte). Split per documento: un quarto dei documenti
    va nel test, come prova "esperti del Sud" (foto dello stesso documento sempre nello stesso split)."""
    out, hashes = [], []
    table = np.array([bin(x).count("1") for x in range(256)], dtype=np.uint16)
    for f in sorted((EXT / "verificate").glob("*.json")):
        for x in json.load(open(f, encoding="utf-8")):
            if not (DATA / x["path"]).exists():
                continue
            h = _hash_bits(DATA / x["path"])
            if h is None:
                continue
            # la stessa foto in due documenti (tesi e articolo, bollettini ripetuti): si tiene la prima
            if hashes and table[np.bitwise_xor(np.stack(hashes), h)].sum(1).min() <= 24:
                continue
            hashes.append(h)
            pest = x["testa"] == "pest"
            doc = x.get("documento") or x["path"]
            split = "test" if zlib.crc32(f"42:{doc}".encode()) % 100 < 25 else "train"
            out.append(ManifestRow(path=x["path"], source="verificate", split=split, plant=x.get("coltura") or "",
                                   disease="" if pest else x["classe"], pest=x["classe"] if pest else "", organ=""))
    return out


def append_source(name: str, rows: list[ManifestRow]) -> int:
    """Sostituisce nel manifest le righe di una fonte senza rifare l'importazione di tutte le altre."""
    from dataclasses import asdict
    from plantcare.data.pipeline import MANIFEST_COLUMNS
    import fcntl
    path = DATA / "processed" / "manifest_v2.csv"
    with open(path.with_suffix(".lock"), "w") as lock:  # più importazioni in parallelo
        fcntl.flock(lock, fcntl.LOCK_EX)
        keep = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["source"] != name]
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
            w.writeheader()
            w.writerows(keep)
            w.writerows({k: asdict(r).get(k, "") for k in MANIFEST_COLUMNS} for r in rows)
        tmp.replace(path)
    return len(rows)
