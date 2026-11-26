"""Foto per il quiz da iNaturalist: colture, insetti e malattie della Calabria (configs/quiz_calabria.yaml).

Solo osservazioni "research grade" (identificazione confermata dalla comunità) con foto in licenza
CC0, CC BY o CC BY-NC; per ogni foto si salvano autore, licenza e osservazione, mostrati nel quiz.
Al massimo 3 foto per autore e una per osservazione, per variare le immagini; prima le foto
scattate in Calabria, poi nel resto d'Italia, poi nel mondo. Per ogni organismo si
salvano anche ordine e famiglia secondo la tassonomia di iNaturalist (per le schede in sintesi).

Uso: python scripts/import_inat_quiz.py [--per-taxon 40]
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.inaturalist.org/v1"
OUT = ROOT / "data" / "external" / "inat_quiz"
IMG = ROOT / "data" / "external" / "images" / "inat_quiz"
LICENSES = ("cc0", "cc-by", "cc-by-nc")
HEADERS = {"User-Agent": "PlantCare-quiz/1.0 (progetto accademico)"}


def get(url, params=None, pause=1.1):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    time.sleep(pause)  # iNaturalist chiede al massimo circa una richiesta al secondo
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
        return r.read()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def taxon_info(name):
    """Taxon di iNaturalist con lo stesso nome (il segno degli ibridi '×' non conta), oppure di cui il
    nome cercato è sinonimo, ma solo se è una specie o un rango inferiore: un sinonimo che porta a un
    ibrido o a un genere (es. Citrus bergamia -> Citrus × limon) vuol dire foto di altro, e si scarta."""
    norm = lambda x: re.sub(r"\s+", " ", x.replace("×", " ")).strip().lower()
    res = json.loads(get(f"{API}/taxa", {"q": name, "per_page": 30}))["results"]
    exact = [t for t in res if norm(t["name"]) == norm(name)]
    if not exact:
        exact = [t for t in res if norm(t.get("matched_term") or "") == norm(name)
                 and t["rank"] in ("species", "subspecies", "variety", "form")]
    if not exact:
        return None
    t = json.loads(get(f"{API}/taxa/{exact[0]['id']}"))["results"][0]
    anc = {a["rank"]: a["name"] for a in t.get("ancestors", [])}
    return {"id": t["id"], "name": t["name"], "rank": t["rank"], "ordine": anc.get("order"),
            "famiglia": anc.get("family"), "regno": anc.get("kingdom"), "classe": anc.get("class"),
            "nome_comune_en": t.get("preferred_common_name")}


# prima le foto scattate in Calabria, poi nel resto d'Italia, poi nel mondo (luoghi di iNaturalist)
LUOGHI = ((9323, "Calabria"), (6973, "Italia"), (None, "mondo"))


def photos_for(taxon_id, n, gia=()):
    """Fino a n foto con licenza aperta: osservazioni della Calabria, poi dell'Italia, poi del resto del mondo.
    Al massimo 3 foto per autore e una per osservazione; gia = foto già salvate (si contano anche loro)."""
    out, per_user, seen_obs = [], Counter(), set()
    for g in gia:
        seen_obs.add(g["osservazione"])
        per_user[g.get("autore", "")] += 1
    for place, nome in LUOGHI:
        for page in (1, 2):
            if len(out) + len(gia) >= n:
                return out
            params = {"taxon_id": taxon_id, "quality_grade": "research", "photo_license": ",".join(LICENSES),
                      "per_page": 100, "page": page, "order_by": "votes", "photos": "true"}
            if place:
                params["place_id"] = place
            obs = json.loads(get(f"{API}/observations", params))["results"]
            for o in obs:
                url_obs = f"https://www.inaturalist.org/observations/{o['id']}"
                user = (o.get("user") or {}).get("login", "")
                if url_obs in seen_obs or per_user[user] >= 3:
                    continue
                ph = next((p for p in o.get("photos", []) if p.get("license_code") in LICENSES), None)
                if not ph or not ph.get("url"):
                    continue
                seen_obs.add(url_obs)
                per_user[user] += 1
                out.append({"photo_id": ph["id"], "url": ph["url"].replace("/square.", "/medium."),
                            "license": ph["license_code"], "attribution": ph.get("attribution", ""),
                            "osservazione": url_obs, "autore": user, "zona": nome,
                            "data": o.get("observed_on"), "luogo": o.get("place_guess") or ""})
                if len(out) + len(gia) >= n:
                    return out
            if len(obs) < 100:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-taxon", type=int, default=40)
    args = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "configs" / "quiz_calabria.yaml", encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.json"
    manifest = json.load(open(man_path, encoding="utf-8")) if man_path.exists() else {}
    for kind, head in (("colture", "plant"), ("parassiti", "pest"), ("malattie", "disease")):
        for e in cfg[kind]:
            key = slug(e["taxon"])
            prev = manifest.get(key)
            if prev and (len(prev["foto"]) >= args.per_taxon or prev.get("richieste", 25) >= args.per_taxon):
                continue  # già completo, o iNaturalist non ne ha di più
            try:
                info = (prev or {}).get("taxon_inat") or taxon_info(e["taxon"])
                if not info:
                    print("non trovato:", e["taxon"], flush=True)
                    continue
                gia = (prev or {}).get("foto", [])
                photos = gia + photos_for(info["id"], args.per_taxon, gia)
            except Exception as ex:  # rete: si riprova al prossimo avvio
                print("errore", e["taxon"], ex, flush=True)
                continue
            saved = []
            for p in photos:
                if p.get("path"):  # già scaricata
                    saved.append(p)
                    continue
                f = IMG / key / f"{p['photo_id']}.jpg"
                if not f.exists():
                    try:
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(get(p["url"], pause=0.3))
                    except Exception as ex:
                        print("  foto non scaricata", p["photo_id"], ex, flush=True)
                        continue
                saved.append({**p, "path": str(f.relative_to(ROOT / "data"))})
            manifest[key] = {**e, "head": head, "taxon_inat": info, "foto": saved, "disponibili": len(photos),
                             "richieste": args.per_taxon}
            json.dump(manifest, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"{head:7s} {e['taxon']:32s} {len(saved):3d} foto  ({info.get('ordine')}, {info.get('famiglia')})", flush=True)
    print("FATTO", sum(len(v["foto"]) for v in manifest.values()), "foto")


if __name__ == "__main__":
    main()
