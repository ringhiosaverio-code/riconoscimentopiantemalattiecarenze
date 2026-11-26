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
PMC_OAI = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
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
    """Didascalie e nomi delle figure dal servizio OAI di PubMed Central (testo JATS dell'articolo)."""
    url = f"{PMC_OAI}?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmcid[3:]}&metadataPrefix=pmc"
    try:
        root = ET.fromstring(get(url))
    except Exception:
        return []
    def find(tag):
        return [e for e in root.iter() if e.tag.split("}")[-1] == tag]
    doi = next((testo(e) for e in find("article-id") if e.attrib.get("pub-id-type") == "doi"), "")
    lic = next((v for e in find("license") for k, v in e.attrib.items() if k.endswith("href")), "")
    title = testo(next(iter(find("article-title")), None))
    out = []
    for fig in find("fig"):
        cap = testo(next((c for c in fig.iter() if c.tag.split("}")[-1] == "caption"), None))
        g = next((c for c in fig.iter() if c.tag.split("}")[-1] == "graphic"), None)
        href = next((v for k, v in (g.attrib.items() if g is not None else []) if k.endswith("href")), None)
        if href:
            out.append({"pmcid": pmcid, "doi": doi, "didascalia": cap[:1500], "href": href, "licenza": lic[:200],
                        "articolo": title[:300]})
    return out


def url_immagine(f):
    """Indirizzo della figura sul sito dell'editore (MDPI, Springer Nature/BMC, Frontiers)."""
    doi, stem = f["doi"], re.sub(r"\.(jpe?g|png|gif|tif)$", "", f["href"])
    if doi.startswith("10.3390/"):
        base = re.sub(r"-g\d+[a-z]?$", "", stem)
        return f"https://mdpi-res.com/{base.split('-')[0]}/{base}/article_deploy/html/images/{stem}.png"
    if doi.startswith(("10.1038/", "10.1007/", "10.1186/")):
        return (f"https://media.springernature.com/lw685/springer-static/image/art%3A{urllib.parse.quote(doi, safe='')}"
                f"/MediaObjects/{stem}.png")
    if doi.startswith("10.3389/"):
        m = re.match(r"(.+-(\d+))-g\d+$", stem)
        if m:
            return f"https://www.frontiersin.org/files/Articles/{m.group(2)}/{m.group(1)}-HTML/image_m/{stem}.jpg"
    return None


def scarica(f):
    lab = classi_da_testo(f["didascalia"])
    if len(lab) != 1:
        return []
    head, cls = next(iter(lab))
    slug = f"{f['pmcid']}_{re.sub(r'[^A-Za-z0-9]+', '_', f['href'])[-40:]}"
    fatti = sorted(IMG.glob(f"{slug}_*.jpg"))
    if fatti:  # già scaricata in un giro precedente
        return [{**f, "path": str(p.relative_to(ROOT / "data")), "testa": head, "classe": cls,
                 "pannello": int(p.stem.rsplit("_", 1)[1])} for p in fatti]
    u = url_immagine(f)
    if not u:
        return []
    try:
        data = get(u, tries=2)
    except Exception:
        return []
    if not (data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG"):
        return []
    res = []
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.size[0] * im.size[1] > 40_000_000:  # figure enormi: si saltano (memoria)
                return []
            im.draft("RGB", (2400, 2400))
            for k, p in enumerate(pannelli(im.convert("RGB"))):
                p.thumbnail((800, 800))
                dest = IMG / f"{slug}_{k}.jpg"
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
    with ThreadPoolExecutor(2) as pool:
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
