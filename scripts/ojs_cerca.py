"""Articoli di riviste OJS ad accesso aperto (es. Phytopathologia Mediterranea, Firenze University Press).

Raccoglie i record con OAI-PMH, tiene quelli su malattie e insetti delle colture (stessi criteri di
scripts/iris_cerca.py) e trova il PDF di ogni articolo dalla pagina dell'articolo ("article/download").
L'elenco va poi a scripts/estrai_pdf.py.

Uso: python scripts/ojs_cerca.py https://oajournals.fupress.net/index.php/pm phytomed
"""
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iris_cerca import COLTURE, NS, ORGANISMI, get  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    base, nome = sys.argv[1].rstrip("/"), sys.argv[2]
    out_dir = ROOT / "data" / "external" / nome
    out_dir.mkdir(parents=True, exist_ok=True)
    recs, url = [], f"{base}/oai?verb=ListRecords&metadataPrefix=oai_dc"
    while url:
        root = ET.fromstring(get(url))
        for r in root.iterfind(".//oai:record", NS):
            md = r.find(".//oai:metadata", NS)
            if md is None:
                continue
            f = lambda tag: [e.text or "" for e in md.iter(f"{{{NS['dc']}}}{tag}")]
            recs.append({"titolo": " ".join(f("title")), "descrizione": " ".join(f("description"))[:3000],
                         "soggetti": " ".join(f("subject")), "identificatori": f("identifier"),
                         "diritti": " ".join(f("rights"))[:200], "data": " ".join(f("date"))[:10]})
        tok = root.findtext(".//oai:resumptionToken", namespaces=NS)
        url = f"{base}/oai?verb=ListRecords&resumptionToken={urllib.parse.quote(tok)}" if tok else None
    sel = [r for r in recs if ORGANISMI.search(r["titolo"] + " " + r["soggetti"] + " " + r["descrizione"][:1500])
           and COLTURE.search(r["titolo"] + " " + r["soggetti"] + " " + r["descrizione"][:1500])]
    print(len(recs), "articoli,", len(sel), "su malattie e insetti delle colture", flush=True)
    elenco = []
    for i, r in enumerate(sel):
        view = next((x for x in r["identificatori"] if "/article/view/" in x), None)
        if not view:
            continue
        try:
            page = get(view).decode("utf-8", "ignore")
        except Exception:
            continue
        galleys = re.findall(r'href="([^"]*/article/view/\d+/\d+)"[^>]*>\s*(?:<[^>]+>\s*)*(PDF|Pdf|pdf)', page)
        for k, g in enumerate(galleys[:1]):
            elenco.append({"url": g[0].replace("/article/view/", "/article/download/"), "id": f"{nome}_{i}",
                           "titolo": r["titolo"][:200], "licenza": r["diritti"], "pagina": view})
        if i % 50 == 0:
            print(f"  {i}/{len(sel)}, {len(elenco)} PDF", flush=True)
    json.dump(elenco, open(out_dir / "pdf_elenco.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("PDF:", len(elenco))


if __name__ == "__main__":
    main()
