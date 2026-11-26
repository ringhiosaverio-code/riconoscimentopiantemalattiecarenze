"""Foto da Bugwood Images (ipmimages.org, Università della Georgia) per malattie e insetti del Sud Italia.

Soggetti identificati da specialisti; uso non commerciale con citazione dell'autore. Malattie da
configs/bugwood.yaml, insetti e acari dalla sezione "parassiti" di configs/quiz_calabria.yaml.
Si scaricano le foto 768x512, solo di campo: si scartano colture in piastra, microscopio, disegni.

Uso: python scripts/import_bugwood.py [--max 300] [--elenco]
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.bugwoodcloud.org/v2"
OUT = ROOT / "data" / "external" / "bugwood"
IMG = ROOT / "data" / "external" / "images" / "bugwood"
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico)"}
SCARTA = re.compile(r"(?i)cultur|spore|micro|conidi|mycel|slide|drawing|illustrat|diagram|map|museum|specimen|"
                    r"sem\b|cross.?section|asci|hyph|chart|lab|test|isolat|petri|herbarium|label|logo|trap|research|"
                    r"sampl|survey|people|equipment|display|management|graphic|control|inspection|greenhouse|n/a")


def get(url):
    for k in range(4):
        try:
            time.sleep(0.3)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=60) as r:
                return r.read()
        except Exception:
            if k == 3:
                raise
            time.sleep(5 * (k + 1))


def subjects(sci):
    """Id dei soggetti Bugwood con lo stesso nome (genere, specie e, se indicata, patovar o sottospecie)."""
    parts = sci.split()
    d = json.loads(get(f"{API}/subject?search={urllib.parse.quote(' '.join(parts[:2]))}"))
    rest = " ".join(parts[2:]).lower()
    out = []
    for x in d:
        if (x["namepart1"] + " " + x["namepart2"]).lower() != " ".join(parts[:2]).lower():
            continue
        if rest and x["namepart3"].lower() != rest:
            continue
        out.append(x["subjectid"])
    return out


def images(ids):
    res, page = [], 1
    while True:
        d = json.loads(get(f"{API}/image?subject={','.join(map(str, ids))}&page={page}&pagesize=50"))
        res += d.get("data", [])
        if not d.get("data") or len(res) >= d.get("totalrows", 0):
            return res
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--elenco", action="store_true", help="solo conteggi, nessuno scaricamento")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "configs" / "bugwood.yaml", encoding="utf-8"))
    quiz = yaml.safe_load(open(ROOT / "configs" / "quiz_calabria.yaml", encoding="utf-8"))
    targets = [dict(e, testa="disease") for e in cfg["malattie"]]
    for p in quiz["parassiti"]:
        slug = re.sub(r"[^a-z0-9]+", "_", p["taxon"].lower()).strip("_")
        targets.append({"sci": p["taxon"], "classe": f"inat:{slug}", "coltura": "", "testa": "pest"})
    OUT.mkdir(parents=True, exist_ok=True)
    man_p = OUT / "manifest.json"
    man = json.load(open(man_p, encoding="utf-8")) if man_p.exists() else {}
    for t in targets:
        key = t["sci"]
        if key in man and man[key].get("completo") and not args.elenco:
            continue
        try:
            ids = subjects(t["sci"])
            imgs = images(ids) if ids else []
        except Exception as ex:
            print("errore", key, ex, flush=True)
            continue
        keep = [i for i in imgs if not SCARTA.search((i.get("descriptorname") or "") + " " + (i.get("imageview") or ""))]
        if t.get("ospite"):  # solo foto sull'ospite indicato (es. gommosi: agrumi)
            keep = [i for i in keep if re.search(t["ospite"], (i.get("hostscientificname") or "") + " " + (i.get("hostname") or ""))]
        desc = Counter(i.get("descriptorname") for i in imgs)
        print(f"{key:45s} soggetti={len(ids)} foto={len(imgs)} tenute={len(keep)}  {dict(desc.most_common(6))}", flush=True)
        if args.elenco:
            continue
        keep = keep[:args.max]

        def fetch(i):
            f = IMG / re.sub(r"[^a-z0-9]+", "_", key.lower()) / f"{i['imagenumber']}.jpg"
            if not f.exists():
                try:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(get(f"https://bugwoodcloud.org/images/768x512/{i['imagenumber']}.jpg"))
                except Exception as ex:
                    print("  foto non scaricata", i["imagenumber"], ex, flush=True)
                    return None
            return {"path": str(f.relative_to(ROOT / "data")), "numero": i["imagenumber"],
                    "autore": (i.get("photographer") or "").strip(), "citazione": (i.get("citation") or "").strip(),
                    "tipo": i.get("descriptorname"), "ospite": i.get("hostscientificname") or ""}
        with ThreadPoolExecutor(4) as pool:
            saved = [x for x in pool.map(fetch, keep) if x]
        man[key] = {**t, "soggetti": ids, "foto": saved, "completo": True}
        json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False)
    print("FATTO", sum(len(v["foto"]) for v in man.values()), "foto")


if __name__ == "__main__":
    sys.exit(main())
