"""Prova con le foto del forum di giardinaggio.it (sezioni "Parassiti e Malattie" e "Orto e frutteto").

Il sito non vieta la raccolta automatica (robots.txt assente il 2026-11-26). Si va piano (una richiesta
al secondo), si leggono i titoli delle discussioni e si apre solo quella il cui titolo nomina una sola
classe dei lettori (src/plantcare/data/testo_classi.py). Si prendono le miniature delle foto del primo
messaggio. Non si salvano nomi utente né testi: solo la foto, la classe del titolo e il link.
L'etichetta è debole (è l'ipotesi di chi scrive): le foto servono solo se il modello è d'accordo
(scripts/forum_filtro.py) e la fonte si tiene solo se migliora le prove di campo.

Uso: python scripts/forum_giardinaggio.py [--pagine 911]
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from plantcare.data.testo_classi import classi_da_testo  # noqa: E402

BASE = "https://forum.giardinaggio.it"
SEZIONI = {"parassiti-e-malattie.29": 911, "orto-e-frutteto.21": 2000}
OUT = ROOT / "data" / "external" / "forum_giardinaggio"
IMG = ROOT / "data" / "external" / "images" / "forum_giardinaggio"
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico)"}


def get(url):
    time.sleep(1.0)
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pagine", type=int, default=0, help="massimo di pagine per sezione (0 = tutte)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tit_p = OUT / "titoli.json"
    titoli = json.load(open(tit_p, encoding="utf-8")) if tit_p.exists() else {}
    for sez, maxp in SEZIONI.items():
        n = min(maxp, args.pagine) if args.pagine else maxp
        for p in range(1, n + 1):
            key = f"{sez}/{p}"
            if key in titoli:
                continue
            try:
                html = get(f"{BASE}/forums/{sez}/page-{p}").decode("utf-8", "ignore")
            except Exception as ex:
                print("fine sezione o errore", sez, p, ex, flush=True)
                break
            found = re.findall(r'href="(/threads/[^"]+/)"[^>]*data-tp-primary="on"[^>]*>([^<]{3,200})<', html)
            titoli[key] = [[u, t.strip()] for u, t in found]
            if not found:
                break
            if p % 50 == 0:
                json.dump(titoli, open(tit_p, "w", encoding="utf-8"), ensure_ascii=False)
                print(sez, p, sum(len(v) for v in titoli.values()), flush=True)
        json.dump(titoli, open(tit_p, "w", encoding="utf-8"), ensure_ascii=False)
    sel = {}
    for v in titoli.values():
        for u, t in v:
            lab = classi_da_testo(t)
            if len(lab) == 1:
                sel[u] = (t, next(iter(lab)))
    print(len(sel), "discussioni con una sola classe nel titolo", flush=True)
    man_p = OUT / "manifest.json"
    man = json.load(open(man_p, encoding="utf-8")) if man_p.exists() else {}
    for i, (u, (t, (head, cls))) in enumerate(sorted(sel.items())):
        if u in man:
            continue
        try:
            html = get(BASE + u).decode("utf-8", "ignore")
        except Exception:
            man[u] = {"foto": []}
            continue
        first = html.split('<article class="message', 2)
        post = first[1] if len(first) > 1 else html
        srcs = re.findall(r'src="(https://forum\.giardinaggio\.it/data/attachments/[^"]+\.(?:jpe?g|png))"', post)
        foto = []
        for s in srcs[:6]:
            f = IMG / (hashlib.md5(s.encode()).hexdigest()[:16] + ".jpg")
            if not f.exists():
                try:
                    data = get(s)
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(data)
                except Exception:
                    continue
            foto.append(str(f.relative_to(ROOT / "data")))
        man[u] = {"titolo": t, "testa": head, "classe": cls, "foto": foto}
        if i % 25 == 0:
            json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"  {i}/{len(sel)} discussioni, {sum(len(v['foto']) for v in man.values())} foto", flush=True)
    json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False)
    print("FATTO", sum(len(v["foto"]) for v in man.values()), "foto")


if __name__ == "__main__":
    main()
