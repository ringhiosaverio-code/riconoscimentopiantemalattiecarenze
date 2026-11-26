"""Tesi di dottorato, articoli, libri e atti ad accesso aperto nei repository IRIS delle università.

Raccoglie i record con OAI-PMH (titolo, descrizione, soggetti), tiene quelli che parlano di malattie o
insetti delle colture del progetto, poi apre la pagina del record e prende i PDF pubblici (bitstream).
I PDF passano poi a scripts/estrai_pdf.py.

Uso: python scripts/iris_cerca.py https://iris.unirc.it unirc
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico)"}
NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "dc": "http://purl.org/dc/elements/1.1/"}
ORGANISMI = re.compile(
    r"(?i)phytophthora|colletotrichum|plenodomus|phoma tracheiphila|mal secco|xylella|pseudomonas (savastanoi|syringae)|"
    r"verticillium|venturia|spilocaea|olive leaf spot|occhio di pavone|bactrocera|prays oleae|saissetia|euphyllura|"
    r"zeuzera|palpita|ceratitis|aleurocanthus|aleurothrixus|phyllocnistis|planococcus|aonidiella|toxoptera|"
    r"botrytis|plasmopara|erysiphe|esca|phaeomoniella|grapevine trunk|leafroll|lobesia|scaphoideus|"
    r"erwinia amylovora|taphrina|monilinia|cryphonectria|castanea|dryocosmus|halyomorpha|tuta absoluta|"
    r"phthorimaea|helicoverpa|bemisia|psa\b|actinidia|kiwifruit|sooty mo|fumaggine|anthracnose|antracnosi|"
    r"lebbra|rogna|olive knot|citrus gummosis|gommosi|peronospora|downy mildew|powdery mildew|oidio|"
    r"canker|cancro|wilt|marciume|root rot|fruit rot|leaf spot|fitopatolog|plant patholog|plant disease|"
    r"phytopatholog|insect pest|parassit|entomolog|pest management|difesa (delle|integrata)")
COLTURE = re.compile(r"(?i)oliv|olea|citrus|agrum|lemon|limon|orange|aranc|mandarin|bergamot|grapevine|vitis|vite|"
                     r"kiwi|actinidia|tomato|pomodor|pepper|peperon|chestnut|castagn|hazelnut|nocciol|peach|pesc|"
                     r"apple|melo|pear|pero|fig|fico|almond|mandorl|cherry|cilieg|onion|cipoll|strawberr|fragol|"
                     r"cucurbit|zucchin|melanzan|eggplant|potato|patat|plant|piante|crop|coltur")
SETS = ["col_123456789_1", "com_20.500.12318_61419", "col_123456789_7", "col_123456789_14", "col_123456789_22"]


def get(url, tries=4):
    for k in range(tries):
        try:
            time.sleep(0.5)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=120) as r:
                return r.read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(10 * (k + 1))


def harvest(base, sets):
    import xml.etree.ElementTree as ET
    recs = []
    for s in sets:
        url = f"{base}/oai/request?verb=ListRecords&metadataPrefix=oai_dc&set={s}"
        while url:
            try:
                root = ET.fromstring(get(url))
            except Exception as ex:
                print("errore OAI", s, ex, flush=True)
                break
            for r in root.iterfind(".//oai:record", NS):
                md = r.find(".//oai:metadata", NS)
                if md is None:
                    continue
                f = lambda tag: [e.text or "" for e in md.iter(f"{{{NS['dc']}}}{tag}")]
                recs.append({"id": (r.findtext(".//oai:identifier", namespaces=NS) or ""),
                             "titolo": " ".join(f("title")), "descrizione": " ".join(f("description"))[:3000],
                             "soggetti": " ".join(f("subject")), "identificatori": f("identifier"),
                             "tipo": " ".join(f("type")), "data": " ".join(f("date"))[:10], "set": s})
            tok = root.findtext(".//oai:resumptionToken", namespaces=NS)
            url = f"{base}/oai/request?verb=ListRecords&resumptionToken={urllib.parse.quote(tok)}" if tok else None
        print(s, len(recs), flush=True)
    return recs


def pdf_links(base, rec):
    """PDF pubblici del record: link "bitstream" nella pagina del record."""
    handle = next((i for i in rec["identificatori"] if "/handle/" in i), None)
    if not handle:
        m = re.search(r"oai:[^:]+:(\S+)", rec["id"])
        handle = f"{base}/handle/{m.group(1)}" if m else None
    if not handle:
        return []
    try:
        page = get(handle).decode("utf-8", "ignore")
    except Exception:
        return []
    links = set(re.findall(r'href="([^"]*/(?:bitstream|retrieve)/[^"]+?\.pdf[^"]*)"', page, re.I))
    out = []
    for l in links:
        if "retrieve" in l and "isAllowed=n" in l:
            continue
        out.append(urllib.parse.urljoin(base, l.replace("&amp;", "&")))
    return out


PAROLE = ["Phytophthora", "Colletotrichum", "mal secco", "Plenodomus tracheiphilus", "Xylella fastidiosa",
          "olive quick decline", "Pseudomonas savastanoi", "Pseudomonas syringae actinidiae", "Verticillium olive",
          "olive leaf spot", "Venturia oleaginea", "Bactrocera oleae", "Prays oleae", "citrus pests", "citrus diseases",
          "Aleurocanthus spiniferus", "Ceratitis capitata", "grapevine trunk diseases", "esca grapevine",
          "Plasmopara viticola", "Tuta absoluta", "tomato pests", "Cryphonectria parasitica", "chestnut",
          "Botrytis cinerea", "Monilinia", "Erwinia amylovora", "kiwifruit canker", "Phytophthora capsici",
          "Peronospora destructor", "sooty mold", "Saissetia oleae", "olive pests", "malattie dell'olivo",
          "malattie degli agrumi", "fitopatologia", "entomologia agraria", "Halyomorpha halys", "Drosophila suzukii"]


def cerca_iris(base):
    """Ricerca semplice del repository (per gli archivi grandi): handle dei record trovati."""
    handles = {}
    for q in PAROLE:
        for start in (0, 100):
            url = f"{base}/simple-search?query={urllib.parse.quote(q)}&rpp=100&start={start}"
            try:
                page = get(url).decode("utf-8", "ignore")
            except Exception:
                break
            found = re.findall(r'href="(/handle/[0-9.]+/\d+)"[^>]*>([^<]{5,300})<', page)
            for h, t in found:
                handles.setdefault(h, t.strip())
            if len(found) < 50:
                break
        print(q, len(handles), flush=True)
    return [{"id": h, "titolo": t, "descrizione": "", "soggetti": "", "identificatori": [base + h],
             "tipo": "", "data": "", "set": "ricerca"} for h, t in handles.items()]


def main():
    base, nome = sys.argv[1].rstrip("/"), sys.argv[2]
    if "--cerca" in sys.argv:
        out_dir = ROOT / "data" / "external" / f"iris_{nome}"
        out_dir.mkdir(parents=True, exist_ok=True)
        rec_p = out_dir / "record.json"
        if not rec_p.exists():
            json.dump(cerca_iris(base), open(rec_p, "w", encoding="utf-8"), ensure_ascii=False)
        sys.argv = [a for a in sys.argv if a != "--cerca"]
    out_dir = ROOT / "data" / "external" / f"iris_{nome}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_p = out_dir / "record.json"
    if rec_p.exists():
        recs = json.load(open(rec_p, encoding="utf-8"))
    else:
        sets = SETS if nome == "unirc" else [s for s in sys.argv[3:]] or None
        if sets is None:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(get(f"{base}/oai/request?verb=ListSets"))
            names = {e.findtext("oai:setSpec", namespaces=NS): e.findtext("oai:setName", namespaces=NS) or ""
                     for e in root.iterfind(".//oai:set", NS)}
            sets = [k for k, v in names.items() if re.search(r"(?i)articolo in rivista|tesi di dottorato|contributo in volume|monografia|atti di convegno", v)]
            print("insiemi:", [names[s] for s in sets], flush=True)
        recs = harvest(base, sets)
        json.dump(recs, open(rec_p, "w", encoding="utf-8"), ensure_ascii=False)
    sel = [r for r in recs if r.get("set") == "ricerca" or (
        ORGANISMI.search(r["titolo"] + " " + r["soggetti"] + " " + r["descrizione"][:1500])
        and COLTURE.search(r["titolo"] + " " + r["soggetti"] + " " + r["descrizione"][:1500]))]
    print(len(recs), "record,", len(sel), "su malattie e insetti delle colture", flush=True)
    elenco = []
    for i, r in enumerate(sel):
        for k, l in enumerate(pdf_links(base, r)):
            elenco.append({"url": l, "id": f"{nome}_{i}_{k}", "titolo": r["titolo"][:200], "record": r["id"]})
        if i % 50 == 0:
            print(f"  {i}/{len(sel)} record, {len(elenco)} PDF aperti", flush=True)
    json.dump(elenco, open(out_dir / "pdf_elenco.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("PDF aperti:", len(elenco))


if __name__ == "__main__":
    main()
