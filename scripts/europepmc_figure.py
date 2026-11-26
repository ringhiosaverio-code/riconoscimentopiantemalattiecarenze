"""Figure di articoli ad accesso aperto (Europe PMC) su malattie e insetti delle colture del Sud Italia.

Al posto di Google Scholar (senza interfaccia per programmi): Europe PMC indicizza PubMed Central, con il
testo completo e le figure degli articoli aperti (MDPI, Frontiers, PLOS, Scientific Reports...).
Per ogni specie bersaglio si cercano articoli aperti; di ogni figura si legge la didascalia scritta dagli
autori: se nomina una sola classe dei lettori, la figura si divide in pannelli e i pannelli che il filtro
CLIP riconosce come foto di campo diventano candidate (da verificare a vista). Licenza salvata per figura.

Uso: python scripts/europepmc_figure.py [--per-specie 60]
"""
import argparse
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from plantcare.data.pannelli import pannelli  # noqa: E402
from plantcare.data.testo_classi import classi_da_testo, SINONIMI  # noqa: E402

API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
OUT = ROOT / "data" / "external" / "europepmc"
IMG = ROOT / "data" / "external" / "images" / "europepmc"
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico)"}


def get(url, tries=4):
    for k in range(tries):
        try:
            time.sleep(0.2)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=120) as r:
                return r.read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def specie():
    """Nomi scientifici delle classi del Sud Italia (quiz, Bugwood, iNaturalist) e sinonimi."""
    quiz = yaml.safe_load(open(ROOT / "configs/quiz_calabria.yaml", encoding="utf-8"))
    bw = yaml.safe_load(open(ROOT / "configs/bugwood.yaml", encoding="utf-8"))
    names = [p["taxon"] for p in quiz["parassiti"]] + [e["taxon"] for e in quiz.get("addestramento_malattie", [])]
    names += [" ".join(e["sci"].split()[:2]) for e in bw["malattie"]]
    names += [k.capitalize() for k in SINONIMI]
    names += ["Colletotrichum olive", "Phytophthora citrus", "grapevine leafroll", "Xylella olive"]
    return sorted(set(names))


def cerca(nome, n):
    q = f'"{nome}" AND OPEN_ACCESS:y'
    url = f"{API}/search?query={urllib.parse.quote(q)}&format=json&pageSize={min(n, 100)}&resultType=lite"
    try:
        d = json.loads(get(url))
    except Exception:
        return []
    return [r["pmcid"] for r in d.get("resultList", {}).get("result", []) if r.get("pmcid")][:n]


def testo(e):
    return re.sub(r"\s+", " ", "".join(e.itertext())).strip() if e is not None else ""


def figure(pmcid):
    try:
        root = ET.fromstring(get(f"{API}/{pmcid}/fullTextXML"))
    except Exception:
        return []
    lic = testo(root.find(".//license")) or ""
    lic_url = next((v for e in root.iter("license") for k, v in e.attrib.items() if k.endswith("href")), "")
    title = testo(root.find(".//article-title"))
    out = []
    for fig in root.iter("fig"):
        cap = testo(fig.find("caption"))
        g = fig.find(".//graphic")
        if g is None:
            continue
        href = next((v for k, v in g.attrib.items() if k.endswith("href")), None)
        if href:
            out.append({"pmcid": pmcid, "didascalia": cap[:1500], "href": href, "licenza": (lic_url or lic)[:200],
                        "articolo": title[:300]})
    return out


def scarica(f):
    lab = classi_da_testo(f["didascalia"])
    if len(lab) != 1:
        return []
    head, cls = next(iter(lab))
    base = f"https://europepmc.org/articles/{f['pmcid']}/bin/{f['href']}"
    data = None
    for u in ([base] if re.search(r"\.(jpe?g|png|gif)$", base, re.I) else [base + ".jpg", base + ".png", base]):
        try:
            data = get(u, tries=2)
            if data[:4] in (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\x89PNG") or data[:3] == b"\xff\xd8\xff":
                break
            data = None
        except Exception:
            data = None
    if not data:
        return []
    res = []
    try:
        with Image.open(io.BytesIO(data)) as im:
            for k, p in enumerate(pannelli(im.convert("RGB"))):
                p.thumbnail((800, 800))
                dest = IMG / f"{f['pmcid']}_{re.sub(r'[^A-Za-z0-9]+', '_', f['href'])[-40:]}_{k}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                p.save(dest, quality=90)
                res.append({**f, "path": str(dest.relative_to(ROOT / "data")), "testa": head, "classe": cls,
                            "pannello": k})
    except Exception:
        return []
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-specie", type=int, default=60)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    art_p = OUT / "articoli.json"
    if art_p.exists():
        arts = json.load(open(art_p))
    else:
        arts = {}
        for k, n in enumerate(specie()):
            for p in cerca(n, args.per_specie):
                arts.setdefault(p, []).append(n)
            print(f"  {k} {n}: {len(arts)} articoli", flush=True)
        json.dump(arts, open(art_p, "w"))
    print(len(arts), "articoli aperti", flush=True)
    fig_p = OUT / "figure.json"
    if fig_p.exists():
        figs = json.load(open(fig_p))
    else:
        with ThreadPoolExecutor(4) as pool:
            figs = [f for fs in pool.map(figure, sorted(arts)) for f in fs]
        json.dump(figs, open(fig_p, "w"), ensure_ascii=False)
    print(len(figs), "figure", flush=True)
    with ThreadPoolExecutor(4) as pool:
        cand = [c for cs in pool.map(scarica, figs) for c in cs]
    from plantcare.data.filtro_foto import punteggi
    for c, (p, l) in zip(cand, punteggi([ROOT / "data" / c["path"] for c in cand])):
        c["campo"], c["clip"] = round(p, 3), l
    json.dump(cand, open(OUT / "candidate.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    good = [c for c in cand if c["campo"] >= 0.8]
    print(len(cand), "pannelli con una sola classe,", len(good), "foto di campo")
    for k, v in Counter(c["classe"] for c in good).most_common():
        print(f"{v:4d} {k}")


if __name__ == "__main__":
    main()
