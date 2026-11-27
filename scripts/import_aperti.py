"""Dataset aperti di foto di campo (licenza CC BY 4.0) per malattie già conosciute dal lettore.

Scelti tra quelli trovati su Mendeley Data, Zenodo e Hugging Face perché fotografati in campo (non in
laboratorio), su colture del Sud e con classi che corrispondono a quelle del modello:

- ESCA-dataset (Università Politecnica delle Marche, Mendeley 89cnxc58kj): viti con mal dell'esca e sane;
- foglie di agrumi di campo a Fès, Marocco (Mendeley szsms728jf): macchia grassa, cocciniglia rossa forte,
  sintomi da greening, sane;
- foglie di limone (Bangladesh, Mendeley 8d9fv6kpt3): un campione per classe (cancro batterico, antracnosi,
  fumaggine, melanosi, ticchiolatura, macchia nera, greening, ragnetto, minatrice, sane);
- peronospora della vite su Merlot (Mendeley yxf2yv5ymt) e in vigneti di Spagna e Norvegia (Zenodo 17368692);
- peperone (Etiopia, progetto EU EWA-BELT, Zenodo 17087046): oidio (Leveillula taurica), maculatura
  batterica (Xanthomonas vesicatoria), sane.

Le foto si riducono a 800 px di lato e si salvano in data/external/images/aperti/<fonte>/; l'elenco con
classe, fonte, licenza e documento va in data/external/aperti/manifest.json (importers.import_aperti).

Uso: python scripts/import_aperti.py [--per-classe 250]
"""
import argparse
import hashlib
import io
import json
import random
import time
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "aperti"
IMG = ROOT / "data" / "external" / "images" / "aperti"
DL = Path("/home/user/dl_aperti")  # zip già scaricati da Zenodo/Mendeley
HEAD = {"User-Agent": "PlantCare-dataset/1.0 (progetto accademico)"}
MENDELEY = "https://data.mendeley.com/public-api/datasets"

# fonte Mendeley: cartella (nome) -> classe del lettore delle malattie ("" = si scarta)
MENDELEY_SETS = {
    "esca_marche": ("89cnxc58kj", {"esca": "grapevine_esca", "healthy": "healthy"}),
    "agrumi_fes": ("szsms728jf", {"Apparently_Healthy": "healthy",
                                   "California_Red_Scale-like_Signs": "agml_citrusuat:Red_scale",
                                   "Greasy_Spot-like_Symptoms": "agml_citrusuat:Greasy_spot",
                                   "Greening-like_Symptoms": "Orange___Haunglongbing_(Citrus_greening)"}),
    "limone_bd": ("8d9fv6kpt3", {"Citrus Canker": "agml_lemon:Citrus Canker", "Anthracnose": "citrus_anthracnose",
                                  "Lemon_Sooty_Mold": "agml_lemon:Sooty Mould", "Melanose": "agml_citrusfruit:melanose",
                                  "Citrus_Scab": "agml_citrusfruit:scab", "Black Spot": "agml_citrusfruit:black_spot",
                                  "Greening": "Orange___Haunglongbing_(Citrus_greening)",
                                  "Spider Mites": "agml_lemon:Spider Mites",
                                  "Citrus Leafminer": "agml_citrusuat:Citrus_leafminer",
                                  "Bacterial Blight": "agml_lemon:Bacterial Blight", "Dry Leaf": "agml_lemon:Dry Leaf",
                                  "Healthy": "healthy"}),
}
# zip: sottostringa del percorso nel file -> classe
ZIP_SETS = {
    "merlot_peronospora": ("downy_mildew_images.zip", "10.17632/yxf2yv5ymt", {".jpg": "grapevine_downy_mildew"})  # le .png sono maschere,
    "plasmopara_es_no": ("Plasmopara_Dataset.zip", "10.5281/zenodo.17368692",
                         {"healthy": "healthy", "plasmopara": "grapevine_downy_mildew"}),
    "peperone_et": ("CPSFR_LEVETA_Leveillula_taurica.zip", "10.5281/zenodo.17087046", {"": "pepper_powdery_mildew"}),
    "peperone_et_x": ("CPSFR_XANTAV_Xanthomonas_campestris_pv._vesicatoria.zip", "10.5281/zenodo.17087046",
                      {"": "pepper_bacterial_spot"}),
    "peperone_et_s": ("CPSFR_healthy_leaves.zip", "10.5281/zenodo.17087046", {"": "healthy"}),
}
PIANTA = {"esca_marche": "vitis_vinifera", "merlot_peronospora": "vitis_vinifera", "plasmopara_es_no": "vitis_vinifera",
          "agrumi_fes": "", "limone_bd": "citrus_limon", "peperone_et": "capsicum_annuum",
          "peperone_et_x": "capsicum_annuum", "peperone_et_s": "capsicum_annuum"}


def get(url, pause=0.2):
    for k in range(4):
        try:
            time.sleep(pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=120) as r:
                return r.read()
        except Exception:
            if k == 3:
                raise
            time.sleep(5 * (k + 1))


def save(data: bytes, dest: Path) -> bool:
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return False
    if min(im.size) < 160:
        return False
    im.thumbnail((800, 800), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, quality=90)
    return True


def mendeley(name, ds, mapping, cap, rnd):
    meta = json.loads(get(f"{MENDELEY}/{ds}"))
    folders = {f["id"]: f["name"] for f in json.loads(get(f"{MENDELEY}/{ds}/folders/{meta['version']}"))}
    by_cls = {}
    for f in meta["files"]:
        cls = mapping.get(folders.get(f.get("folder_id"), ""), "")
        if cls and f["filename"].lower().endswith((".jpg", ".jpeg", ".png")):
            by_cls.setdefault(cls, []).append(f)
    out = []
    for cls, files in sorted(by_cls.items()):
        files.sort(key=lambda f: f["id"]); rnd.shuffle(files)
        n = 0
        for f in files:
            if n >= cap:
                break
            dest = IMG / name / f"{f['id']}.jpg"
            if dest.exists() or save(get(f["content_details"]["download_url"]), dest):
                n += 1
                out.append({"path": str(dest.relative_to(ROOT / "data")), "classe": cls, "fonte": name,
                            "documento": f"10.17632/{ds}.{meta['version']}", "licenza": "CC BY 4.0"})
        print(f"  {name} {cls}: {n} foto (su {len(files)})", flush=True)
    return out


def from_zip(name, fname, doi, mapping, cap, rnd):
    try:
        z = zipfile.ZipFile(DL / fname)
    except zipfile.BadZipFile:  # scaricamento non finito
        print(f"  {name}: {fname} incompleto", flush=True)
        return []
    by_cls = {}
    for i in z.infolist():
        low = i.filename.lower()
        if i.is_dir() or not low.endswith((".jpg", ".jpeg", ".png")) or "__macosx" in low:
            continue
        # la sottostringa più lunga che compare nel percorso decide la classe
        keys = [k for k in mapping if k in low]
        if keys:
            by_cls.setdefault(mapping[max(keys, key=len)], []).append(i)
    out = []
    for cls, items in sorted(by_cls.items()):
        items.sort(key=lambda i: i.filename); rnd.shuffle(items)
        n = 0
        for i in items:
            if n >= cap:
                break
            dest = IMG / name / f"{hashlib.md5(i.filename.encode()).hexdigest()[:16]}.jpg"
            if dest.exists() or save(z.read(i), dest):
                n += 1
                out.append({"path": str(dest.relative_to(ROOT / "data")), "classe": cls, "fonte": name,
                            "documento": doi, "licenza": "CC BY 4.0"})
        print(f"  {name} {cls}: {n} foto (su {len(items)})", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-classe", type=int, default=250)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(42)
    rows = []
    for name, (fname, doi, mapping) in ZIP_SETS.items():
        if (DL / fname).exists():
            rows += from_zip(name, fname, doi, mapping, args.per_classe, rnd)
        else:
            print(f"  {name}: manca {fname}", flush=True)
    for name, (ds, mapping) in MENDELEY_SETS.items():
        rows += mendeley(name, ds, mapping, args.per_classe, rnd)
    for r in rows:
        r["pianta"] = PIANTA[r["fonte"]]
    json.dump(rows, open(OUT / "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("totale", len(rows))


if __name__ == "__main__":
    main()
