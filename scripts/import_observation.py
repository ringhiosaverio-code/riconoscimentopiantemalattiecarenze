"""Foto di campo da Observation.org (letta tramite GBIF) per malattie e insetti del Sud Italia.

Observation.org è molto usata in Italia e in Europa; si tengono solo osservazioni con foto e con
identificazione approvata ("Approved"), prima dai paesi mediterranei. Licenze CC BY-NC o CC BY-NC-ND:
solo addestramento (uso non commerciale e accademico), mai nel quiz. Al massimo --max foto per specie e
10 per autore; lo split si fa per autore (scripts/import_inat_train.py fa lo stesso).

Obiettivi: malattie di configs/quiz_calabria.yaml (addestramento_malattie) e di configs/bugwood.yaml,
insetti e acari della sezione "parassiti".

Uso: python scripts/import_observation.py [--max 300]
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GBIF = "https://api.gbif.org/v1"
DATASET = "8a863029-f435-446a-821e-275f4f641165"  # Observation.org, Nature data from around the World
OUT = ROOT / "data" / "external" / "observation"
IMG = ROOT / "data" / "external" / "images" / "observation"
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico)"}
MEDITERRANEO = ["IT", "MT", "ES", "PT", "GR", "CY", "HR", "FR", "SI", "AL", "TR", "IL", "TN", "MA"]


def get(url):
    for k in range(4):
        try:
            time.sleep(0.2)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=60) as r:
                return r.read()
        except Exception:
            if k == 3:
                raise
            time.sleep(5 * (k + 1))


def taxon_key(name):
    d = json.loads(get(f"{GBIF}/species/match?name={urllib.parse.quote(name)}"))
    if d.get("matchType") in ("EXACT", "FUZZY") and d.get("canonicalName", "").lower() == name.lower():
        return d.get("usageKey")
    return None


def occurrences(key, n, per_user=10):
    out, users = [], Counter()
    for countries in (MEDITERRANEO, None):
        offset = 0
        while len(out) < n and offset < 3000:
            q = {"datasetKey": DATASET, "taxonKey": key, "mediaType": "StillImage", "limit": 300, "offset": offset}
            url = f"{GBIF}/occurrence/search?" + urllib.parse.urlencode(q)
            if countries:
                url += "".join(f"&country={c}" for c in countries)
            d = json.loads(get(url))
            for o in d.get("results", []):
                if "approved" not in (o.get("identificationVerificationStatus") or "").lower():
                    continue
                if countries is None and o.get("countryCode") in MEDITERRANEO:
                    continue  # già considerata nel primo giro
                m = next((m for m in o.get("media", []) if m.get("identifier", "").startswith("https://observation.org/")), None)
                user = (m or {}).get("rightsHolder") or o.get("recordedBy") or ""
                if not m or users[user] >= per_user or any(x["occ"] == o["key"] for x in out):
                    continue
                users[user] += 1
                out.append({"occ": o["key"], "url": m["identifier"], "autore": user, "licenza": m.get("license", ""),
                            "paese": o.get("countryCode", "")})
                if len(out) >= n:
                    break
            if d.get("endOfRecords", True):
                break
            offset += 300
        if len(out) >= n:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    args = ap.parse_args()
    quiz = yaml.safe_load(open(ROOT / "configs" / "quiz_calabria.yaml", encoding="utf-8"))
    bw = yaml.safe_load(open(ROOT / "configs" / "bugwood.yaml", encoding="utf-8"))
    targets, seen = [], set()
    for e in quiz.get("addestramento_malattie", []) + bw["malattie"]:
        name = " ".join((e.get("taxon") or e.get("sci")).split()[:2])
        if (name, e["classe"]) not in seen:
            seen.add((name, e["classe"]))
            targets.append({"nome": name, "classe": e["classe"], "coltura": e.get("coltura") or "", "testa": "disease"})
    for p in quiz["parassiti"]:
        slug = re.sub(r"[^a-z0-9]+", "_", p["taxon"].lower()).strip("_")
        targets.append({"nome": p["taxon"], "classe": f"inat:{slug}", "coltura": "", "testa": "pest"})
    OUT.mkdir(parents=True, exist_ok=True)
    man_p = OUT / "manifest.json"
    man = json.load(open(man_p, encoding="utf-8")) if man_p.exists() else {}
    for t in targets:
        k = f"{t['nome']}|{t['classe']}"
        if k in man and man[k].get("completo"):
            continue
        try:
            key = taxon_key(t["nome"])
            occ = occurrences(key, args.max) if key else []
        except Exception as ex:
            print("errore", k, ex, flush=True)
            continue

        def fetch(o):
            f = IMG / re.sub(r"[^a-z0-9]+", "_", t["nome"].lower()) / f"{o['occ']}.jpg"
            if not f.exists():
                try:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(get(o["url"]))
                except Exception as ex:
                    print("  foto non scaricata", o["url"], ex, flush=True)
                    return None
            return {**o, "path": str(f.relative_to(ROOT / "data"))}
        with ThreadPoolExecutor(4) as pool:
            saved = [x for x in pool.map(fetch, occ) if x]
        man[k] = {**t, "taxon_gbif": key, "foto": saved, "completo": True}
        json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False)
        it = sum(1 for x in saved if x["paese"] == "IT")
        print(f"{t['nome']:32s} {t['classe'][:30]:30s} {len(saved):4d} foto ({it} Italia)", flush=True)
    print("FATTO", sum(len(v["foto"]) for v in man.values()), "foto")


if __name__ == "__main__":
    main()
