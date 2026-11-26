"""Usi registrati dei prodotti Gowan Italia, dalle pagine prodotto del sito ufficiale (gowanitalia.it).

Per ogni prodotto: numero e data di registrazione, composizione, formulazione, gruppo di resistenza
(FRAC/IRAC), link all'etichetta e, per ogni coltura, avversità con dose a ettaro e a ettolitro,
intervallo di sicurezza e note (epoca, numero di trattamenti). Dalle etichette (PDF) si prende il
paragrafo sulla compatibilità nelle miscele. Le pagine si scaricano con --scarica (una richiesta ogni 2 secondi).

Uso: python scripts/import_gowan.py <cartella_pagine_html> [--etichette <cartella_pdf>]
     python scripts/import_gowan.py --scarica <cartella>   (scarica pagine ed etichette, poi le legge)
"""
import argparse
import html as H
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def txt(s):
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", H.unescape(s)).strip()


def field(text, label):
    m = re.search(label + r"\s*:?\s*([^\n]+)", text)
    return m.group(1).strip() if m else None


def parse_page(path):
    s = Path(path).read_text(encoding="utf-8", errors="ignore")
    plain = txt(re.sub(r"(?is)<(script|style).*?</\1>", " ", s))
    title = re.search(r"(?is)<title>(.*?)</title>", s)
    name = H.unescape(title.group(1)).split("|")[0].split(" - ")[0].strip() if title else Path(path).stem
    reg = re.search(r"numero di registrazione:\s*(\d+)\s*\(([\d/]+)\)", plain)
    comp = re.search(r"Composizione\s+(.*?)\s+Scarica Materiali", plain, re.S)
    form = re.search(r"formulazione:\s*([A-ZÀ-Ü ,\-/]+?)\s+Composizione", plain)
    frac = re.search(r"Gruppo (FRAC|IRAC|HRAC)\s*:\s*([^\n]{1,40}?)\s{2,}|Gruppo (FRAC|IRAC|HRAC)\s*:\s*(\S+)", plain)
    label = re.search(r'href="(https://gowanitalia\.it/\?ID_mat=\d+)"[^>]*>\s*Etichetta', s)
    uses = []
    for m in re.finditer(r'oxel_accordion__row__label"><span[^>]*>(.*?)</span></div>.*?<ul>(.*?)</ul>', s, re.S):
        head = txt(m.group(1))
        crop = re.sub(r"\s+difesa.*$", "", head).strip()
        amb = re.search(r"Ambito impiego:\s*([^-]+?)(?:\s+-|$)", head)
        modo = re.search(r"modo di coltivazione:\s*(.+)$", head)
        if "diserbo" in head.lower() or crop.lower().startswith("terreno destinato"):
            continue  # solo difesa delle colture: diserbo e trattamenti al terreno esclusi
        for li in re.findall(r"<li>(.*?)</li>", m.group(2), re.S):
            pest = re.search(r'principale_contenuto_accordion">(.*?)</span>', li, re.S)
            body = "\n".join(txt(x) for x in re.findall(r'contenuto_accordion">(.*?)</span>', li, re.S))
            pname = txt(pest.group(1)) if pest else ""
            uses.append({"coltura": crop, "ambito": amb.group(1).strip() if amb else None,
                         "modo": modo.group(1).strip() if modo else None, "avversita": pname,
                         "scientifici": [x.strip() for x in re.findall(r"\(([^()]+)\)", pname)],
                         "dose_ha": field(body, "Dose su ettaro"), "dose_hl": field(body, "Dose su ettolitro"),
                         "intervallo_sicurezza": field(body, "Intervallo di sicurezza"), "note": field(body, "Note")})
    return {"prodotto": name, "pagina": None, "registrazione": reg.group(1) if reg else None,
            "data_registrazione": reg.group(2) if reg else None,
            "composizione": re.sub(r"\s+", " ", comp.group(1)).strip() if comp else None,
            "formulazione": form.group(1).strip() if form else None,
            "gruppo_resistenza": (frac.group(2) or frac.group(4)).strip() if frac else None,
            "etichetta": label.group(1) if label else None, "usi": uses}


STOP = (r"(?=FITOTOSSICIT|ATTENZIONE|Etichetta autorizzata|INFORMAZIONI PER IL MEDICO|PREVENZIONE|CONSERVARE|"
        r"DA NON APPLICARE|RISCHI DI NOCIVIT|Gestione delle resistenze|Periodo di sicurezza|$)")


def compat_from_label(pdf):
    """Paragrafo dell'etichetta su compatibilità e miscele, e data di validità dell'etichetta (testo letterale).
    Prima il titolo in maiuscolo (COMPATIBILITÀ, MISCIBILITÀ), poi 'Compatibilità' come titolo, infine la
    frase intera che contiene la parola."""
    try:
        t = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None, None
    t = re.sub(r"\s+", " ", t)
    m = (re.search(r"((?:COMPATIBILIT|MISCIBILIT)(?:[AÀ]'?|À)\s.{10,700}?)" + STOP, t)
         or re.search(r"((?:Compatibilità|Miscibilità)\s*:?\s+[A-ZÈ–-].{10,700}?)" + STOP, t))
    text = m.group(1).strip() if m else None
    if not text:
        sm = re.search(r"([^.]{0,300}compatibilit[aà][^.]{0,300}\.)", t, re.I)
        text = sm.group(1).strip() if sm else None
    if text and (re.match(r"(?i)compatibilit[aà]\s+periodo di sicurezza", text)
                 or re.search(r"Marchio registrato|Etichetta autorizzata|^\[", text)
                 or not re.search(r"(?i)compatib|miscel|miscib", text[:60])):
        text = None  # estrazione non affidabile (colonne mescolate nel PDF): meglio nulla
    v = re.search(r"(Etichetta autorizzata con [Dd]ecreto [Dd]irigenziale del [^,.]{4,30}(?:,[^.]{0,160}?con validità dal [0-9/]{8,10})?)", t)
    return text, (v.group(1).strip() if v else None)


def importa(pagine, etichette=None, out=ROOT / "configs" / "difesa" / "gowan_italia.json") -> dict:
    """Legge le pagine prodotto salvate (<slug>.html) e, se ci sono, le etichette (<slug>.pdf)."""
    prods = []
    for f in sorted(Path(pagine).glob("*.html")):
        p = parse_page(f)
        p["pagina"] = f"https://gowanitalia.it/agrofarmaco/{f.stem}/"
        if etichette and (Path(etichette) / f"{f.stem}.pdf").exists():
            p["compatibilita"], p["etichetta_validita"] = compat_from_label(Path(etichette) / f"{f.stem}.pdf")
        prods.append(p)
    notes = {}  # le note (spesso uguali per molte colture) si salvano una volta sola
    for p in prods:
        for u in p["usi"]:
            if u.get("note"):
                u["note"] = notes.setdefault(u["note"], len(notes))
    d = {"fonte": "Gowan Italia, pagine prodotto e etichette (gowanitalia.it)", "consultato": str(date.today()),
         "note_testi": list(notes),
         "avvertenza": "Dosi e usi come riportati dal produttore; prevale l'etichetta autorizzata dal Ministero della Salute.",
         "prodotti": prods}
    json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(len(prods), "prodotti,", sum(len(p["usi"]) for p in prods), "usi ->", out)
    return d


def scarica(dest, pausa=2.0):
    """Scarica dal sito Gowan Italia le pagine dei prodotti (dest/prod) e le etichette PDF (dest/etichette),
    una richiesta ogni `pausa` secondi. Le etichette passano da una pagina che reindirizza al PDF."""
    import time
    import urllib.request
    head = {"User-Agent": "PlantCare/1.0 (progetto accademico; aggiornamento norme)"}

    def get(url):
        time.sleep(pausa)
        with urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=120) as r:
            return r.read()

    dest = Path(dest)
    (dest / "prod").mkdir(parents=True, exist_ok=True)
    (dest / "etichette").mkdir(parents=True, exist_ok=True)
    elenco = get("https://gowanitalia.it/agrofarmaci/").decode("utf-8", "ignore")
    slugs = sorted(set(re.findall(r"https://gowanitalia\.it/agrofarmaco/([a-z0-9-]+)/", elenco)))
    if len(slugs) < 20:
        raise SystemExit(f"elenco dei prodotti Gowan sospetto ({len(slugs)} prodotti): aggiornamento interrotto")
    for slug in slugs:
        page = get(f"https://gowanitalia.it/agrofarmaco/{slug}/")
        (dest / "prod" / f"{slug}.html").write_bytes(page)
        m = re.search(rb'href="(https://gowanitalia\.it/\?ID_mat=\d+)"[^>]*>\s*Etichetta', page)
        if not m:
            continue
        try:
            red = get(m.group(1).decode()).decode("utf-8", "ignore")
            r = re.search(r'window\.location\.replace\("([^"]+)"\)', red)
            pdf = get(r.group(1)) if r else b""
            if pdf[:4] == b"%PDF":
                (dest / "etichette" / f"{slug}.pdf").write_bytes(pdf)
        except Exception as ex:  # un'etichetta non raggiungibile non blocca le altre
            print("etichetta non scaricata:", slug, ex)
    return dest / "prod", dest / "etichette"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pagine", nargs="?", default=None)
    ap.add_argument("--etichette", default=None, help="cartella con le etichette PDF (<slug>.pdf)")
    ap.add_argument("--scarica", default=None, help="cartella in cui scaricare pagine ed etichette dal sito Gowan")
    ap.add_argument("--out", default=str(ROOT / "configs" / "difesa" / "gowan_italia.json"))
    args = ap.parse_args()
    if args.scarica:
        args.pagine, args.etichette = scarica(args.scarica)
    if not args.pagine:
        raise SystemExit("indicare la cartella delle pagine o --scarica")
    importa(args.pagine, args.etichette, args.out)


if __name__ == "__main__":
    main()
