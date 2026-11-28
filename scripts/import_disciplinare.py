"""Legge le tabelle di difesa dei Disciplinari di produzione integrata della Regione Calabria.

Per ogni coltura e avversità: nome (con il nome scientifico tra parentesi), criteri di intervento,
sostanze attive e ausiliari ammessi, limitazioni d'uso e note. Il PDF usa un carattere senza tabella
Unicode: i codici "(cid:N)" corrispondono al carattere ASCII N.

Uso:
  python scripts/import_disciplinare.py <pdf> <anno> <url> [--out configs/difesa/disciplinare_calabria_<anno>.json]
      [--titolo T] [--pubblicato AAAA-MM-GG] [--aggiornamento]
Lo usa anche scripts/aggiorna_norme.py, che trova da solo i nuovi Disciplinari pubblicati da ARSAC.
"""
import argparse
import json
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
SECTION = re.compile(r"Difesa\s*:\s*(.+?)\s*\(\d+\s*/\s*\d+\)")
SCI = re.compile(r"\(([^()]{3,200})\)")
GROUP_WORDS = ("CRITTOGAME", "FITOFAGI", "BATTERIOSI", "VIROSI", "FISIOPATIE", "NEMATODI", "INSETTI", "ACARI", "FITOPLASMOSI")


def dec(s):
    return re.sub(r"\(cid:(\d+)\)", lambda m: chr(int(m.group(1))), s or "")


def clean(s):
    return re.sub(r"[ \t]+", " ", dec(s).replace(" ", " ")).strip()


def lines(cell):
    return [x for x in (clean(l) for l in dec(cell).split("\n")) if x]


def parse_substances(cell):
    """Righe della colonna S.A. unite quando continuano la voce precedente: riga che inizia in minuscolo
    ('dolce', 'germinati di Lupinus albus'), riga precedente che finisce con '+', ',', ' e', ' di' o con
    una parentesi aperta sulla stessa voce (al massimo una riga in più: nel PDF ci sono parentesi non chiuse)."""
    raw = lines(cell)
    out = []
    for ln in raw:
        prev = out[-1] if out else ""
        cont = bool(prev) and (ln[:1].islower() or prev.endswith(("+", ",", " e", " di", " del", " dei", " a", "-"))
                               or ln.startswith(("+", ")")) or (prev.count("(") > prev.count(")") and not prev.startswith("(")
                                                                and "\n" not in prev and len(prev) < 40))
        if cont:
            out[-1] = f"{prev} {ln}".strip()
        else:
            out.append(ln)
    res = []
    for s in out:
        refs = re.findall(r"\((\d+|\*+)\)", s)
        name = re.sub(r"\s*\((\d+|\*+)\)\s*", " ", s)
        name = re.sub(r"^\(\s*", "", name) if name.count("(") > name.count(")") else name  # parentesi non chiusa nel PDF
        name = re.sub(r"\s+", " ", name).strip(" *")
        if name and not re.fullmatch(r"[-–\s]*", name):
            res.append({"sostanza": name, "note": refs})
    return res


def quattro_colonne(raw):
    """Alcune pagine hanno tabelle a 6, 12 o più colonne con celle unite (None) o vuote: si riportano alle 4
    colonne (avversità, criteri, sostanze, note). Con un multiplo di 4 colonne ogni gruppo è una colonna."""
    if len(raw) % 4 == 0 and len(raw) >= 12:
        k = len(raw) // 4
        out = []
        for i in range(4):
            g = [c for c in raw[i * k:(i + 1) * k] if c is not None]
            out.append(next((c for c in g if c.strip()), g[0] if g else ""))
        return out
    piene = [c for c in raw if c is not None]
    if len(piene) > 4 and not any(c.strip() for c in piene[4:]):
        piene = piene[:4]  # colonne in più vuote
    if len(piene) != 4:
        piene = [c for c in piene if c.strip()]
    return piene if len(piene) == 4 else None


def leggi(pdf_path) -> list[dict]:
    """Righe di difesa (coltura, avversità, criteri, sostanze, note, pagina) del PDF del Disciplinare."""
    pdf = pdfplumber.open(pdf_path)
    rows, section = [], None
    for pno, page in enumerate(pdf.pages):
        text = dec(page.extract_text() or "")
        m = SECTION.search(text)
        if m:
            section = re.sub(r"\s+", " ", m.group(1)).strip().upper()
        else:
            section = None  # pagine non di difesa (diserbo, indici, premesse)
        if not section:
            continue
        for table in page.extract_tables():
            for raw in table:
                if not raw or len(raw) < 4:
                    continue
                joined = " ".join(dec(c or "") for c in raw).upper()
                if "AVVERSIT" in joined and "CRITERI" in joined:
                    continue  # intestazione
                if len(raw) > 4:
                    raw = quattro_colonne(raw)
                    if raw is None:
                        continue
                cells = [dec(c) for c in raw[:4]]
                adv = lines(cells[0])
                adv = [a for a in adv if a.upper() not in GROUP_WORDS]
                if not adv and rows and rows[-1]["coltura"] == section:  # riga che continua dalla pagina prima
                    r = rows[-1]
                    r["criteri"] += " " + " ".join(lines(cells[1]))
                    r["sostanze"] += parse_substances(cells[2])
                    r["note"] += " " + " ".join(lines(cells[3]))
                    continue
                if not adv:
                    continue
                name = " ".join(adv)
                rows.append({"coltura": section, "avversita": name,
                             "scientifici": [s.strip() for s in SCI.findall(name)],
                             "criteri": " ".join(lines(cells[1])), "sostanze": parse_substances(cells[2]),
                             "note": " ".join(lines(cells[3])), "pagina": pno + 1})
    for r in rows:
        r["criteri"] = r["criteri"].strip()
        r["note"] = r["note"].strip()
    return rows


def salva(rows, anno, url, out, titolo=None, pubblicato=None, aggiornamento=False):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    d = {"fonte": titolo or f"Disciplinari di produzione integrata {anno} - Difesa e controllo infestanti, "
                            "Regione Calabria (Allegato A)", "url": url, "anno": int(anno)}
    if pubblicato:
        d["pubblicato"] = pubblicato
    if aggiornamento:
        d["aggiornamento"] = True
    d["righe"] = rows
    json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("anno")
    ap.add_argument("url")
    ap.add_argument("--out", default=None)
    ap.add_argument("--titolo", default=None)
    ap.add_argument("--pubblicato", default=None, help="data di pubblicazione (AAAA-MM-GG)")
    ap.add_argument("--aggiornamento", action="store_true", help="versione aggiornata in corso d'anno")
    args = ap.parse_args()
    rows = leggi(args.pdf)
    out = salva(rows, args.anno, args.url, args.out or ROOT / "configs" / "difesa" / f"disciplinare_calabria_{args.anno}.json",
                args.titolo, args.pubblicato, args.aggiornamento)
    from collections import Counter
    print(f"{len(rows)} avversità in {len({r['coltura'] for r in rows})} colture -> {out}")
    print(Counter(r["coltura"] for r in rows).most_common(60))


if __name__ == "__main__":
    main()
