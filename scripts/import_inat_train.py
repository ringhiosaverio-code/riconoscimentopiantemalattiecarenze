"""Foto di addestramento da iNaturalist per insetti e acari della Calabria (lettore degli insetti).

IP102 non ha le specie mediterranee (mosca delle olive, cocciniglie degli agrumi...). Per ogni specie di
configs/quiz_calabria.yaml (sezione "parassiti") si scaricano fino a --per-taxon foto di osservazioni
"research grade" con licenza CC0, CC BY o CC BY-NC (uso non commerciale e accademico, autore salvato),
al massimo 5 per autore. La divisione addestramento/validazione/test si fa per autore (hash del nome):
lo stesso fotografo, che spesso riprende lo stesso individuo più volte, non finisce in due split.

Uso: python scripts/import_inat_train.py [--per-taxon 200]
     poi: python -c "from plantcare.data.importers import append_inat_calabria; append_inat_calabria()"
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_inat_quiz import API, HEADERS, LICENSES, get, slug, taxon_info  # noqa: E402

OUT = ROOT / "data" / "external" / "inat_calabria"
IMG = ROOT / "data" / "external" / "images" / "inat_calabria"


def observations(taxon_id, n, per_user=5):
    out, users, page = [], Counter(), 1
    while len(out) < n and page <= 5:
        params = {"taxon_id": taxon_id, "quality_grade": "research", "photo_license": ",".join(LICENSES),
                  "per_page": 200, "page": page, "order_by": "id", "order": "desc", "photos": "true"}
        res = json.loads(get(f"{API}/observations", params))["results"]
        if not res:
            break
        for o in res:
            user = (o.get("user") or {}).get("login", "")
            if users[user] >= per_user:
                continue
            ph = next((p for p in o.get("photos", []) if p.get("license_code") in LICENSES), None)
            if not ph or not ph.get("url"):
                continue
            users[user] += 1
            out.append({"photo_id": ph["id"], "url": ph["url"].replace("/square.", "/medium."), "user": user,
                        "license": ph["license_code"], "attribution": ph.get("attribution", ""),
                        "osservazione": o["id"]})
            if len(out) >= n:
                break
        page += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-taxon", type=int, default=200)
    args = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "configs" / "quiz_calabria.yaml", encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.json"
    man = json.load(open(man_path, encoding="utf-8")) if man_path.exists() else {}
    for e in cfg["parassiti"]:
        key = slug(e["taxon"])
        if key in man and man[key].get("completo"):
            continue
        try:
            info = taxon_info(e["taxon"])
            if not info:
                print("non trovato:", e["taxon"], flush=True)
                continue
            obs = observations(info["id"], args.per_taxon)
        except Exception as ex:
            print("errore", e["taxon"], ex, flush=True)
            continue
        def fetch(p):
            # le foto vengono dall'archivio aperto di iNaturalist su AWS, non dall'API: 4 alla volta
            f = IMG / key / f"{p['photo_id']}.jpg"
            if not f.exists():
                try:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(get(p["url"], pause=0.1))
                except Exception as ex:
                    print("  foto non scaricata", p["photo_id"], ex, flush=True)
                    return None
            return {**p, "path": str(f.relative_to(ROOT / "data"))}
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(4) as pool:
            saved = [x for x in pool.map(fetch, obs) if x]
        man[key] = {**e, "taxon_inat": info, "foto": saved, "completo": True}
        json.dump(man, open(man_path, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"{e['taxon']:32s} {len(saved):4d} foto", flush=True)
    print("FATTO", sum(len(v["foto"]) for v in man.values()), "foto")


if __name__ == "__main__":
    main()
