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
    # agrumi: HLB come in PlantVillage; cocciniglia rossa e suoi esiti (macchie gialle) in una classe
    ("agml_citrusuat", "HLB"): "Orange___Haunglongbing_(Citrus_greening)",
    ("agml_citrusuat", "Red_scale_sequelae"): "agml_citrusuat:Red_scale",
}
# Classi senza una diagnosi univoca (es. "foglia morta", "frutto non sano"): non usate.
AGML_SKIP = {("agml_plum", "Dead Leaf"), ("agml_plum", "Yellow"), ("agml_plum", "Unhealthy Fruit")}
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


def _label_names(repo: str, config: str = "raw") -> list[str] | None:
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
        if f.get("name") != "label":
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
    has_crop = "crop_type" in pq.ParquetFile(files[0]).schema_arrow.names
    recs = list(_parquet_rows(files, ["image", "label"] + (["crop_type"] if has_crop else [])))
    # split stratificato per classe
    by_label = defaultdict(list)
    for i, r in enumerate(recs):
        by_label[r["label"]].append(i)
    split_of = {}
    for lab, idxs in by_label.items():
        for j, s in zip(idxs, _split_random(len(idxs), seed + zlib.crc32(str(lab).encode()) % 1000)):
            split_of[j] = s
    dup = set()
    if name == "agml_appleleaf9":
        dup = _plantvillage_duplicates(recs)
        _same_split_for_duplicates(recs, split_of)
    rows = []
    for i, r in enumerate(recs):
        lab = names[r["label"]] if names and r["label"] < len(names) else f"label_{r['label']}"
        if (name, lab) in AGML_SKIP or i in dup:
            continue
        row_crop = TOM2024_CROPS.get(r.get("crop_type"), crop) if has_crop else crop
        deficiency = ""
        if (name, lab) in DEFICIENCY:
            deficiency = DEFICIENCY[(name, lab)]
            dis = "disturbo_nutrizionale"
        elif lab.lower().startswith(HEALTHY_WORDS):
            dis = "healthy"
        else:
            dis = AGML_DISEASE.get((name, lab, row_crop)) or AGML_DISEASE.get((name, lab)) or f"{name}:{lab}"
        if not deficiency and name in DEFICIENCY_SOURCES:
            deficiency = NO_NUTRITIONAL_DISORDER
        plant = "capsicum_annuum" if row_crop == "capsicum_annuum_peperoncino" else row_crop  # stessa specie
        out = IMG / name / split_of[i] / f"{i:06d}.jpg"
        if out.exists() or _save(r["image"]["bytes"], out):
            rows.append(ManifestRow(path=_rel(out), source=name, split=split_of[i], plant=plant, disease=dis,
                                    deficiency=deficiency))
    return rows


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
                            disease=r["disease"], deficiency=r["deficiency"]) for r in csv.DictReader(fh)]
