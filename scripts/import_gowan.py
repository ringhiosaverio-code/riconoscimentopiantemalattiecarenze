"""Usi registrati dei prodotti Gowan Italia, dalle pagine prodotto del sito ufficiale (gowanitalia.it).

Per ogni prodotto: numero e data di registrazione, composizione, formulazione, gruppo di resistenza
(FRAC/IRAC), link all'etichetta e, per ogni coltura, avversità con dose a ettaro e a ettolitro,
intervallo di sicurezza e note (epoca, numero di trattamenti). Dalle etichette (PDF) si prende il
paragrafo sulla compatibilità nelle miscele. Le pagine si scaricano con scripts a parte o con
--scarica (una richiesta ogni 2 secondi).

Uso: python scripts/import_gowan.py <cartella_pagine_html> [--etichette <cartella_pdf>]
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


def compat_from_label(pdf):
    """Paragrafo dell'etichetta su compatibilità e miscele (testo dell'etichetta, non riassunto)."""
    try:
        t = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    t = re.sub(r"[ \t]+", " ", t)
    m = re.search(r"(?is)(COMPATIBILIT[AÀ]'?.{0,900}?)(?:\n\s*\n|ATTENZIONE|FITOTOSSICIT)", t)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pagine")
    ap.add_argument("--etichette", default=None, help="cartella con le etichette PDF (<slug>.pdf)")
    ap.add_argument("--out", default=str(ROOT / "configs" / "difesa" / "gowan_italia.json"))
    args = ap.parse_args()
    prods = []
    for f in sorted(Path(args.pagine).glob("*.html")):
        p = parse_page(f)
        p["pagina"] = f"https://gowanitalia.it/agrofarmaco/{f.stem}/"
        if args.etichette and (Path(args.etichette) / f"{f.stem}.pdf").exists():
            p["compatibilita"] = compat_from_label(Path(args.etichette) / f"{f.stem}.pdf")
        prods.append(p)
    notes = {}  # le note (spesso uguali per molte colture) si salvano una volta sola
    for p in prods:
        for u in p["usi"]:
            if u.get("note"):
                u["note"] = notes.setdefault(u["note"], len(notes))
    json.dump({"fonte": "Gowan Italia, pagine prodotto e etichette (gowanitalia.it)", "consultato": str(date.today()),
               "note_testi": list(notes),
               "avvertenza": "Dosi e usi come riportati dal produttore; prevale l'etichetta autorizzata dal Ministero della Salute.",
               "prodotti": prods}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(len(prods), "prodotti,", sum(len(p["usi"]) for p in prods), "usi ->", args.out)


if __name__ == "__main__":
    main()
