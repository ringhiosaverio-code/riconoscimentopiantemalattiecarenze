"""Foto per il quiz dall'EPPO Global Database (uso didattico consentito, autore citato).

Per malattie calabresi senza foto aperte altrove: mal secco degli agrumi, cancro batterico
dell'actinidia, peronospora della cipolla, rogna dell'olivo. Solo foto di sintomi (etichetta
"symptoms") e, se indicato, con la coltura giusta nella didascalia. L'EPPO scrive: "All photos
included on this page can only be used for educational purposes".

Uso: python scripts/import_eppo_quiz.py
"""
import html
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "eppo_quiz"
IMG = ROOT / "data" / "external" / "images" / "eppo_quiz"
TAXA = [
    {"eppo": "DEUTTR", "nome": "Mal secco degli agrumi (Plenodomus tracheiphilus)", "gruppo": "agrumi", "causa": "fungo",
     "sci": "Plenodomus tracheiphilus", "filtro": None},
    {"eppo": "PSDMAK", "nome": "Cancro batterico dell'actinidia (Pseudomonas syringae pv. actinidiae)", "gruppo": "actinidia",
     "causa": "batterio", "sci": "Pseudomonas syringae pv. actinidiae", "filtro": None},
    {"eppo": "PERODE", "nome": "Peronospora della cipolla (Peronospora destructor)", "gruppo": "cipolla", "causa": "fungo",
     "sci": "Peronospora destructor", "filtro": None},
    {"eppo": "PSDMSA", "nome": "Rogna dell'olivo (Pseudomonas savastanoi pv. savastanoi)", "gruppo": "olivo", "causa": "batterio",
     "sci": "Pseudomonas savastanoi pv. savastanoi", "filtro": r"(?i)oliv|olea"},
]


def get(url):
    time.sleep(1.0)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PlantCare-quiz/1.0 (progetto accademico)"}), timeout=60) as r:
        return r.read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {}
    for t in TAXA:
        page = get(f"https://gd.eppo.int/taxon/{t['eppo']}/photos").decode("utf-8", "ignore")
        photos = []
        for m in re.finditer(r'<div class="element ([^"]*)">\s*<a href="(/media/data/taxon/[^"]+/1024x0/(\d+)\.jpg)".*?'
                             r'<div class="pcap">(.*?)</div>', page, re.S):
            tags, url, pid, cap = m.groups()
            if "tag-symptoms" not in tags:
                continue
            text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cap))).strip()
            if t["filtro"] and not re.search(t["filtro"], text):
                continue
            court = re.search(r"Courtesy:\s*(.+)$", text)
            f = IMG / t["eppo"] / f"{pid}.jpg"
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(get("https://gd.eppo.int" + url))
            photos.append({"path": str(f.relative_to(ROOT / "data")), "didascalia": text.split("Courtesy:")[0].strip(),
                           "autore": court.group(1).strip() if court else "EPPO",
                           "pagina": f"https://gd.eppo.int/taxon/{t['eppo']}/photos"})
        man[t["eppo"]] = {**t, "foto": photos}
        print(t["eppo"], len(photos), "foto", flush=True)
    json.dump(man, open(OUT / "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
