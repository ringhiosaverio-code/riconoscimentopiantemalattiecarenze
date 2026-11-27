"""Foto di danni da insetti e acari per il lettore delle malattie (classi "danno:..." con causa insetto o acaro).

Il lettore degli insetti riconosce l'insetto; molti sintomi però si vedono senza l'insetto (galle, mine,
cotonosità, erinosi, colonie lanose, fori nei frutti). Fonti, solo per l'addestramento:
- Bugwood Images (Università della Georgia, CC BY-NC 3.0 US): foto marcate "Damage", "Symptoms" o
  "Infestation" degli insetti scelti, identificate da specialisti;
- iNaturalist (licenze aperte): foto già scaricate per il lettore degli insetti (data/external/images/
  inat_calabria) che mostrano il danno, scelte a vista (configs/verificate_danni_inat.json);
- erinosi della vite (Colomerus vitis), Mendeley Data 79f2wmdpmr, CC BY 4.0.
Le foto si salvano ridotte a 800 px in data/external/images/danni/<classe>/; l'elenco va in
data/external/danni/manifest.json (importers.import_danni).

Uso: python scripts/import_danni.py [--max 120]
"""
import argparse
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "danni"
IMG = ROOT / "data" / "external" / "images" / "danni"
HEAD = {"User-Agent": "PlantCare-dataset/1.0 (progetto accademico)"}
BW = "https://api.bugwoodcloud.org/v2"

# classe -> (specie Bugwood, viste ammesse, specie iNaturalist già scaricate e verificate, coltura)
CLASSI = {
    "danno:galle_cinipide_castagno": (["Dryocosmus kuriphilus"], ("damage", "symptom"), ["dryocosmus_kuriphilus"], "castanea_sativa"),
    "danno:cotonosita_psilla_olivo": (["Euphyllura olivina"], ("infestation", "symptom", "damage"), ["euphyllura_olivina"], "olea_europaea"),
    "danno:afide_lanigero": (["Eriosoma lanigerum"], ("damage", "infestation"), [], "malus_domestica"),
    "danno:afidi": (["Myzus persicae", "Aphis gossypii", "Aphis spiraecola", "Hyalopterus pruni", "Dysaphis plantaginea"],
                    ("damage", "infestation", "symptom"), [], ""),
    "danno:tripidi": (["Frankliniella occidentalis", "Thrips tabaci", "Thrips palmi"], ("damage", "symptom"), [], ""),
    "danno:carpocapsa_tortrici": (["Cydia pomonella", "Grapholita molesta", "Anarsia lineatella"], ("damage",), [], ""),
    "danno:cimici": (["Nezara viridula", "Halyomorpha halys"], ("damage",), [], ""),
    "danno:piralide": (["Ostrinia nubilalis"], ("damage",), [], ""),
    "agml_citrusuat:Citrus_leafminer": (["Phyllocnistis citrella"], ("damage", "symptom"), [], "citrus_sinensis"),
}
ERINOSI = ("danno:erinosi_vite", "79f2wmdpmr", "vitis_vinifera")


def get(url, pause=0.4):
    for k in range(4):
        try:
            time.sleep(pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=90) as r:
                return r.read()
        except Exception:
            if k == 3:
                raise
            time.sleep(5 * (k + 1))


def save(data, dest):
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


def slug(c):
    return c.split(":", 1)[1].replace(" ", "_").lower()


def bugwood(cls, species, views, n):
    ids = []
    for sci in species:
        g, s = sci.split()[0], sci.split()[1]
        ids += [x["subjectid"] for x in json.loads(get(f"{BW}/subject?search={urllib.parse.quote(sci)}"))
                if x["namepart1"].lower() == g.lower() and (x.get("namepart2") or "").lower() == s.lower()]
    out, page = [], 1
    while ids and len(out) < n:
        d = json.loads(get(f"{BW}/image?subject={','.join(map(str, sorted(set(ids))))}&page={page}&pagesize=50"))
        for im in d.get("data", []):
            v = ((im.get("imageview") or "") + " " + (im.get("descriptorname") or "")).lower()
            if not any(w in v for w in views):
                continue
            num = im["imagenumber"]
            dest = IMG / slug(cls) / f"bw{num}.jpg"
            if dest.exists() or save(get(f"https://bugwoodcloud.org/images/768x512/{num}.jpg", 0.3), dest):
                out.append({"path": str(dest.relative_to(ROOT / "data")), "classe": cls, "fonte": "bugwood",
                            "credito": f"{(im.get('photographer') or '').strip()}, Bugwood.org (CC BY-NC 3.0 US)",
                            "documento": f"https://www.ipmimages.org/browse/detail.cfm?imgnum={num}"})
            if len(out) >= n:
                break
        if not d.get("data") or page * 50 >= d.get("totalrows", 0):
            break
        page += 1
    return out


def inat(cls, species, scelte):
    out = []
    for sp in species:
        for name in scelte.get(sp, []):
            p = ROOT / "data" / "external" / "images" / "inat_calabria" / sp / name
            if p.exists():
                out.append({"path": str(p.relative_to(ROOT / "data")), "classe": cls, "fonte": "inaturalist",
                            "documento": f"iNaturalist, {sp}/{name}"})
    return out


def erinosi(n):
    cls, ds, _ = ERINOSI
    meta = json.loads(get(f"https://data.mendeley.com/public-api/datasets/{ds}"))
    out = []
    for f in sorted(meta["files"], key=lambda f: f["filename"])[:n]:
        if not f["filename"].lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        dest = IMG / slug(cls) / f"{f['id']}.jpg"
        if dest.exists() or save(get(f["content_details"]["download_url"], 0.2), dest):
            out.append({"path": str(dest.relative_to(ROOT / "data")), "classe": cls, "fonte": "mendeley",
                        "credito": "Vineyard Leaf Scab (Eriophyes vitis) Damage, Mendeley Data (CC BY 4.0)",
                        "documento": f"10.17632/{ds}.{meta['version']}"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=120)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    scelte = json.load(open(ROOT / "configs" / "verificate_danni_inat.json"))
    rows = []
    for cls, (bw_sp, views, inat_sp, coltura) in CLASSI.items():
        r = bugwood(cls, bw_sp, views, args.max) + inat(cls, inat_sp, scelte)
        for x in r:
            x["pianta"] = coltura
        print(f"  {cls}: {len(r)} foto", flush=True)
        rows += r
    r = erinosi(args.max * 2)
    for x in r:
        x["pianta"] = ERINOSI[2]
    print(f"  {ERINOSI[0]}: {len(r)} foto", flush=True)
    rows += r
    json.dump(rows, open(OUT / "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("totale", len(rows))


if __name__ == "__main__":
    main()
