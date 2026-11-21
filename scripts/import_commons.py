"""Foto da Wikimedia Commons per malattie senza altre foto aperte (licenze libere, autore salvato).

Per ogni malattia si leggono le categorie indicate (e le sottocategorie di primo livello), si tengono
le immagini JPEG/PNG e si salvano licenza, autore e pagina. Le foto vanno poi controllate a vista
(sintomo giusto, coltura giusta) con l'elenco in data/external/commons/manifest.json ("ok": true/false).

Uso: python scripts/import_commons.py
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "commons"
IMG = ROOT / "data" / "external" / "images" / "commons"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "PlantCareAcademic/1.0 (progetto accademico; riconoscimento malattie delle piante)"}
TARGETS = {
    "verticilliosi": ["Category:Verticillium dahliae", "Category:Verticillium wilt"],
    "lebbra_olivo": ["Category:Colletotrichum gloeosporioides", "Category:Colletotrichum acutatum", "Category:Olive anthracnose"],
    "fumaggine": ["Category:Sooty mold", "Category:Sooty moulds", "Category:Capnodium"],
    "mal_secco": ["Category:Plenodomus tracheiphilus", "Category:Phoma tracheiphila", "Category:Mal secco"],
    "gommosi_agrumi": ["Category:Phytophthora citrophthora", "Category:Phytophthora nicotianae", "Category:Citrus gummosis"],
    "phytophthora_capsici": ["Category:Phytophthora capsici"],
    "peronospora_cipolla": ["Category:Peronospora destructor"],
    "psa_actinidia": ["Category:Pseudomonas syringae pv. actinidiae", "Category:Kiwifruit bacterial canker"],
}
LIC_OK = re.compile(r"(?i)^(cc[- ]by|cc0|public domain|pd|cc-by-sa)")


def fetch(url):
    """GET con pause e nuovi tentativi se Wikimedia risponde 429 (troppe richieste)."""
    for k in range(6):
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or k == 5:
                raise
            time.sleep(30 * (k + 1))


def api(**params):
    return json.loads(fetch(API + "?" + urllib.parse.urlencode({**params, "format": "json"})))


def members(cat, depth=1):
    files, cont = [], {}
    while True:
        d = api(action="query", list="categorymembers", cmtitle=cat, cmlimit=200, **cont)
        for m in d.get("query", {}).get("categorymembers", []):
            if m["ns"] == 6:
                files.append(m["title"])
            elif m["ns"] == 14 and depth > 0:
                files += members(m["title"], depth - 1)
        if "continue" not in d:
            return files
        cont = {"cmcontinue": d["continue"]["cmcontinue"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {}
    for key, cats in TARGETS.items():
        titles = sorted({t for c in cats for t in members(c) if t.lower().endswith((".jpg", ".jpeg", ".png"))})
        items = []
        for i in range(0, len(titles), 40):
            d = api(action="query", prop="imageinfo", titles="|".join(titles[i:i + 40]), iiprop="url|extmetadata",
                    iiurlwidth=640)
            for p in d.get("query", {}).get("pages", {}).values():
                ii = (p.get("imageinfo") or [{}])[0]
                md = ii.get("extmetadata", {})
                lic = (md.get("LicenseShortName") or {}).get("value", "")
                if not LIC_OK.match(lic):
                    continue
                artist = re.sub(r"<[^>]+>", "", (md.get("Artist") or {}).get("value", "")).strip()
                f = IMG / key / (re.sub(r"[^A-Za-z0-9._-]+", "_", p["title"][5:])[:120])
                if not f.exists() and ii.get("thumburl"):
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(fetch(ii["thumburl"]))
                if f.exists():
                    items.append({"path": str(f.relative_to(ROOT / "data")), "titolo": p["title"], "licenza": lic,
                                  "autore": artist[:120], "pagina": ii.get("descriptionurl"), "ok": None})
        man[key] = items
        print(f"{key:22s} {len(items)} immagini", flush=True)
    json.dump(man, open(OUT / "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
