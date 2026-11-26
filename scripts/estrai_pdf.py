"""Foto etichettate da PDF tecnici e scientifici (bollettini, vademecum, tesi, articoli).

Per ogni PDF: immagini di ogni pagina (pdfimages), testo della pagina (pdftotext). L'etichetta viene
dalla didascalia ("Fig.", "Figura", "Foto", "Figure", "Plate") se nomina una sola classe, altrimenti dal
testo della pagina se nomina una sola classe (src/plantcare/data/testo_classi.py). Poi filtro CLIP
(src/plantcare/data/filtro_foto.py) e controllo dei doppioni (loghi ripetuti). Il risultato è un elenco
di candidate da verificare a vista (scripts/foglio_contatti.py) prima dell'addestramento.

Uso: python scripts/estrai_pdf.py elenco.json fonte
elenco.json: lista di {"url": ..., "id": ..., "titolo": ...}; le candidate vanno in
data/external/<fonte>/candidate_pdf.json, le immagini in data/external/images/<fonte>_pdf/.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from plantcare.data.testo_classi import classi_da_testo  # noqa: E402

CAPTION = re.compile(r"(?im)^\s*(fig\.?|figura|figure|foto|photo|plate|tav\.?)\s*[\d\.IVX]*[a-z]?[\.:\-–)]?\s.{0,400}")
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico)"}
FILI = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--fili=")), 4))
PAUSA = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--pausa=")), 0))


def pagine_testo(pdf: Path) -> list[str]:
    try:
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=300).stdout
    except Exception:
        return []
    return txt.split("\f")


def didascalie(page: str) -> str:
    out = []
    lines = page.splitlines()
    for i, l in enumerate(lines):
        if CAPTION.match(l):
            out.append(" ".join(x.strip() for x in lines[i:i + 3]))
    return " ".join(out)


def elabora(item, fonte):
    out_dir = ROOT / "data" / "external" / fonte / "pdf"
    img_dir = ROOT / "data" / "external" / "images" / f"{fonte}_pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"{item['id']}.pdf"
    fatto = out_dir / f"{item['id']}.fatto.json"
    if fatto.exists():  # già elaborato (il PDF è stato cancellato per spazio)
        return json.load(open(fatto, encoding="utf-8"))
    if not pdf.exists():
        url = urllib.parse.quote(item["url"], safe=":/?=&%#;~+,@!$'()*")
        data = None
        for k in range(5):  # con pause; se il sito risponde 429 (troppe richieste) si aspetta di più
            try:
                time.sleep(PAUSA)
                with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=180) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as ex:
                if ex.code != 429 or k == 4:
                    print("non scaricato", item["url"], ex, flush=True)
                    return []
                time.sleep(60 * (k + 1))
            except Exception as ex:
                print("non scaricato", item["url"], ex, flush=True)
                return []
        if not data or not data.startswith(b"%PDF"):
            return []
        pdf.write_bytes(data)
    pages = pagine_testo(pdf)
    if not pages:
        return []
    res = []
    with tempfile.TemporaryDirectory() as tmp:
        try:
            # PNG: poppler converte CMYK e altri spazi colore in RGB corretto (con -j i CMYK escono in negativo)
            subprocess.run(["pdfimages", "-p", "-png", str(pdf), f"{tmp}/i"], capture_output=True, timeout=900)
        except Exception:
            return []
        for f in sorted(Path(tmp).iterdir()):
            m = re.match(r"i-(\d+)-(\d+)\.(jpg|ppm|png|pbm|jp2|tif)", f.name)
            if not m or m.group(3) == "pbm" or f.stat().st_size < 15000:
                continue
            page = int(m.group(1))
            text = pages[page - 1] if page - 1 < len(pages) else ""
            cap = classi_da_testo(didascalie(text))
            lab, origine = (cap, "didascalia") if len(cap) == 1 else (classi_da_testo(text), "pagina")
            if len(lab) != 1:
                continue
            head, cls = next(iter(lab))
            try:
                from PIL import Image
                from plantcare.data.pannelli import pannelli
                with Image.open(f) as im:
                    if min(im.size) < 180:
                        continue
                    parts = pannelli(im.convert("RGB"))
                for k, part in enumerate(parts):  # figure composte: un file per pannello
                    part.thumbnail((800, 800))
                    dest = img_dir / f"{item['id']}_{m.group(1)}_{m.group(2)}_{k}.jpg"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    part.save(dest, quality=90)
                    res.append({"path": str(dest.relative_to(ROOT / "data")), "testa": head, "classe": cls,
                                "origine": origine, "pagina": page, "pdf": item["url"], "titolo": item.get("titolo", ""),
                                "md5": hashlib.md5(dest.read_bytes()).hexdigest()})
            except Exception:
                continue
    json.dump(res, open(fatto, "w", encoding="utf-8"), ensure_ascii=False)
    if "--tieni-pdf" not in sys.argv:
        pdf.unlink(missing_ok=True)
    return res


def main():
    elenco, fonte = json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2]
    out = ROOT / "data" / "external" / fonte / "candidate_pdf.json"
    with ThreadPoolExecutor(FILI) as pool:
        tutte = [r for rs in pool.map(lambda it: elabora(it, fonte), elenco) for r in rs]
    # doppioni (stessa immagine in più PDF, es. foto ripetute nei bollettini): si tiene la prima
    seen, uniche = set(), []
    for r in tutte:
        if r["md5"] not in seen:
            seen.add(r["md5"])
            uniche.append(r)
    from plantcare.data.filtro_foto import punteggi
    for r, (p, lab) in zip(uniche, punteggi([ROOT / "data" / r["path"] for r in uniche])):
        r["campo"], r["clip"] = round(p, 3), lab
    json.dump(uniche, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    buone = [r for r in uniche if r["campo"] >= 0.8]
    print(len(tutte), "immagini etichettate,", len(uniche), "uniche,", len(buone), "foto di campo")
    for k, v in Counter(r["classe"] for r in buone).most_common():
        print(f"{v:4d} {k}")


if __name__ == "__main__":
    main()
