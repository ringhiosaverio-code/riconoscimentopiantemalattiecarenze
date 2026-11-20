"""Collegamento tra le diagnosi dei lettori e le indicazioni di difesa da fonti verificate.

- Disciplinare di produzione integrata della Regione Calabria (configs/difesa/disciplinare_calabria_<anno>.json,
  scripts/import_disciplinare.py): avversità, criteri di intervento, sostanze attive ammesse e limiti.
- Usi registrati dei prodotti Gowan Italia (configs/difesa/gowan_italia.json, scripts/import_gowan.py):
  dose a ettaro e a ettolitro, intervallo di sicurezza, note.

Il collegamento usa i nomi scientifici degli agenti (con i sinonimi di configs/difesa/agenti_classi.yaml)
e la coltura. Nessuna dose o sostanza viene scritta a mano: tutto viene dai documenti.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIFESA = ROOT / "configs" / "difesa"

# coltura del lettore -> sezioni del Disciplinare e nomi delle colture nelle registrazioni Gowan
CROPS = {
    "vitis_vinifera": (["VITE DA VINO", "VITE DA TAVOLA"], ["Vite", "Vite per uva da tavola", "Vite per uva da vino"]),
    "solanum_lycopersicum": (["POMODORO IN PIENO CAMPO", "POMODORO IN COLTURA PROTETTA"], ["Pomodoro"]),
    "citrus_limon": (["AGRUMI"], ["Agrumi", "Limone"]),
    "citrus_sinensis": (["AGRUMI"], ["Agrumi", "Arancio"]),
    "citrus_reticulata": (["AGRUMI"], ["Agrumi", "Mandarino", "Clementino"]),
    "olea_europaea": (["OLIVO"], ["Olivo"]),
    "malus_domestica": (["MELO"], ["Melo", "Pomacee"]),
    "pyrus_communis": (["PERO"], ["Pero", "Pomacee"]),
    "prunus_persica": (["PESCO"], ["Pesco-nettarine-percoche"]),
    "prunus_domestica": (["SUSINO"], ["Susino"]),
    "prunus_avium": (["CILIEGIO"], ["Ciliegio dolce e acido"]),
    "prunus_armeniaca": (["ALBICOCCO"], ["Albicocco"]),
    "prunus_dulcis": (["MANDORLO"], ["Mandorlo"]),
    "capsicum_annuum": (["PEPERONE"], ["Peperone"]),
    "solanum_melongena": (["MELANZANA"], ["Melanzana"]),
    "solanum_tuberosum": (["PATATA"], ["Patata"]),
    "allium_cepa_tropea": (["CIPOLLA"], ["Cipolla"]),
    "allium_sativum": ([], ["Aglio"]),
    "triticum_durum": (["FRUMENTO"], ["Frumento duro", "Frumento"]),
    "triticum_aestivum": (["FRUMENTO"], ["Frumento tenero", "Frumento"]),
    "zea_mays": (["MAIS"], ["Mais", "Mais dolce"]),
    "fragaria_ananassa": (["FRAGOLA UNIFERA E RIFIORENTE"], ["Fragola"]),
    "cucurbita_pepo": ([], ["Zucchino", "Cucurbitacee"]),
    "cucumis_sativus": ([], ["Cetriolo", "Cucurbitacee"]),
    "brassica_oleracea_italica": (["CAVOLO A INFIORESCENZA"], ["Cavolo broccolo", "Cavolfiore", "Cavoli"]),
    "actinidia_chinensis": (["ACTINIDIA"], ["Actinidia"]),
    "corylus_avellana": (["NOCCIOLO"], ["Nocciolo"]),
    "cynara_cardunculus": (["CARCIOFO"], ["Carciofo"]),
    "punica_granatum": (["MELOGRANO"], ["Melograno"]),
    "ficus_carica": (["FICO"], []),
}
BINOMIAL = re.compile(r"\b([A-Z][a-z]{2,})\s+(?:[a-z]\.\s+)?([a-z][a-z\-]{2,})\b")
NOT_SPECIES = {"spp", "sp", "pv", "var", "ceppo", "subsp", "complex", "group", "virus", "e", "ed", "o"}
# parole italiane che nei nomi comuni sembrano un "Genere specie" (es. "Marciume nero", "Oidio del")
ITALIAN_GENUS = {
    "marciume", "marciumi", "cladosporiosi", "oidio", "cocciniglia", "cancro", "cancri", "maculatura", "avvizzimento",
    "peronospora", "ruggine", "ruggini", "bozzacchioni", "septoriosi", "verticilliosi", "mosaico", "carbone", "accartocciamento",
    "alternariosi", "antracnosi", "batteriosi", "virosi", "danno", "danni", "bolla", "ticchiolatura", "muffa", "mal", "nebbia",
    "fumaggine", "macchia", "macchie", "striatura", "tignola", "tignoletta", "mosca", "mosche", "afide", "afidi", "ragnetto",
    "ragnetti", "nottua", "nottue", "piralide", "minatrice", "cimice", "cimicetta", "tripide", "tripidi", "aleurodide",
    "aleurodidi", "aleirode", "cicalina", "cicaline", "eriofide", "acaro", "acari", "nematodi", "elateridi", "dorifora",
    "carpocapsa", "cidia", "rodilegno", "cotonello", "margaronia", "fleotribo", "oziorrinco", "cecidomia", "tracheomicosi",
    "fusariosi", "botrite", "stemfiliosi", "corineo", "nerume", "sharka", "colpo", "litocollete", "cemiostoma", "orgia",
    "eulia", "psilla", "capnode", "metcalfa", "lebbra", "rogna", "occhio", "piombatura", "carie", "escoriosi", "black",
    "seccume", "disseccamento", "disseccamenti", "gommosi", "moria", "cancrena", "vaiolatura", "scopazzi", "giallumi",
    "flavescenza", "legno", "deperimento", "pianta", "piante", "foglie", "frutti", "prodotti", "interventi", "insetti",
    "virus", "fitoplasmi", "limacce", "lumache", "forficula", "miridi", "cicadellidi", "dittero", "lepidotteri",
}
ITALIAN_SPECIES = {"del", "della", "delle", "dei", "degli", "di", "da", "nero", "nera", "neri", "rosso", "rossa", "verde",
                   "bianco", "bianca", "grigio", "grigia", "batterico", "batterica", "molle", "comune", "secco", "secca",
                   "fogliare", "fogliari", "radicale", "radicali", "basale", "basali", "pedale", "rameali", "giallo", "gialla",
                   "farinoso", "lanigero", "asiatica", "mediterranea", "orientale", "americano", "occidentale", "minore",
                   "maggiore", "terricole", "carpofaghe", "spinoso", "fioccoso", "rugginoso", "serpentina", "bruno", "bruna"}


def _load_yaml(p: Path) -> dict:
    return yaml.safe_load(open(p, encoding="utf-8")) or {}


def _syn() -> dict:
    return {k.lower(): v.lower() for k, v in (_load_yaml(DIFESA / "agenti_classi.yaml").get("sinonimi") or {}).items()}


def keys_in(text: str, syn: dict | None = None) -> set[str]:
    """Nomi scientifici (genere specie, minuscolo, con i sinonimi risolti) presenti nel testo; per
    'Genere spp.' restituisce 'genere *'. Riconosce anche i nomi dei virus scritti per esteso."""
    syn = _syn() if syn is None else syn
    out = set()
    for g, s in BINOMIAL.findall(text or ""):
        if g.lower() in ITALIAN_GENUS or s in ITALIAN_SPECIES:
            continue
        if s in ("spp", "sp"):
            out.add(f"{g.lower()} *")
            continue
        if s in NOT_SPECIES:
            continue
        k = f"{g.lower()} {s}"
        out.add(syn.get(k, k))
    low = (text or "").lower()
    for v in re.findall(r"([a-z][a-z ]+? virus)\b", low):
        out.add(v.strip())
    for k, v in syn.items():
        if k in low:
            out.add(v)
    return out


def _match(a: set[str], b: set[str]) -> bool:
    if a & b:
        return True
    ga = {x.split()[0] for x in a if x.endswith(" *")}
    gb = {x.split()[0] for x in b if x.endswith(" *")}
    return any(x.split()[0] in gb for x in a) or any(x.split()[0] in ga for x in b)


def load_disciplinare(anno: int) -> dict:
    p = DIFESA / f"disciplinare_calabria_{anno}.json"
    d = json.load(open(p, encoding="utf-8"))
    syn = _syn()
    rows = []
    for r in d["righe"]:
        a = r["avversita"].strip()
        if not a or a.startswith(("(*", "*")) or "AVVERSIT" in a.upper() or not re.search(r"[A-Za-z]{4}", a) or a[0].islower():
            continue  # note a piè di pagina o intestazioni ripetute
        rows.append({**r, "chiavi": sorted(keys_in(a, syn))})
    d["righe"] = rows
    return d


def norm_substance(s: str) -> str:
    s = s.lower().replace("’", "'")
    s = re.sub(r"\b(ceppo|strain)\b.*$", "", s)
    s = re.sub(r"[^a-zàèéìòù0-9+ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


GENERIC_WORDS = {"prodotti", "rameici", "ceppo", "olio", "minerale", "paraffinico", "estratto", "nota", "note", "solo",
                 "impianti", "giovani", "interventi", "sostanze", "attive", "dispositivi", "attract", "kill", "esca",
                 "sali", "potassici", "acidi", "grassi", "fosfonato", "potassio", "disodio", "naturale", "naturali"}


def removed_since(old: dict, new: dict, crop_section: str, row_new: dict) -> list[str]:
    """Sostanze della stessa avversità e coltura nel Disciplinare precedente di cui nessuna parola
    significativa compare più in quello nuovo (confronto tollerante agli errori di battitura).
    Righe spezzate male nel PDF o voci generiche ('Prodotti rameici') non si segnalano."""
    import difflib
    words_new = set()
    for r in new["righe"]:
        for x in r["sostanze"]:
            words_new |= set(re.findall(r"[a-zàèéìòù]{5,}", norm_substance(x["sostanza"])))
    words_new = sorted(words_new)
    keys = set(row_new["chiavi"])
    first = row_new["avversita"].split("(")[0].strip().lower()[:20]
    out = []
    for r in old["righe"]:
        if r["coltura"] != crop_section:
            continue
        same = (keys and _match(keys, set(r["chiavi"]))) or r["avversita"].split("(")[0].strip().lower()[:20] == first
        if not same:
            continue
        for x in r["sostanze"]:
            words = [w for w in re.findall(r"[a-zàèéìòù]{5,}", norm_substance(x["sostanza"])) if w not in GENERIC_WORDS]
            if not words:
                continue
            if all(not difflib.get_close_matches(w, words_new, n=1, cutoff=0.85) for w in words):
                out.append(re.sub(r"\s*\(\d+\)?\s*$", "", x["sostanza"]).strip())
    return sorted(set(out))


def load_gowan() -> dict:
    p = DIFESA / "gowan_italia.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else {"prodotti": []}


def gowan_uses(keys: set[str], crop_names: list[str], gowan: dict, syn: dict | None = None) -> list[dict]:
    syn = _syn() if syn is None else syn
    crops = {c.lower() for c in crop_names}
    notes = gowan.get("note_testi") or []
    out = []
    for p in gowan.get("prodotti", []):
        for u in p.get("usi", []):
            if crops and u["coltura"].lower() not in crops:
                continue
            uk = keys_in(" ".join(u.get("scientifici") or []) + " " + (u.get("avversita") or ""), syn)
            if uk and _match(keys, uk):
                out.append({"prodotto": p["prodotto"], "composizione": p.get("composizione"),
                            "registrazione": p.get("registrazione"), "pagina": p.get("pagina"),
                            "coltura": u["coltura"], "ambito": u.get("ambito"), "avversita": u.get("avversita"),
                            "dose_ha": u.get("dose_ha"), "dose_hl": u.get("dose_hl"),
                            "intervallo_sicurezza": u.get("intervallo_sicurezza"),
                            "note": notes[u["note"]] if isinstance(u.get("note"), int) else u.get("note")})
    return out


def class_keys(label: str, name: str = "", agent: str | None = None, syn: dict | None = None) -> set[str]:
    syn = _syn() if syn is None else syn
    manual = (_load_yaml(DIFESA / "agenti_classi.yaml").get("agenti") or {}).get(label) or []
    keys = set()
    for a in manual:
        keys |= keys_in(a, syn) or {a.lower()}
    keys |= keys_in(name, syn)
    if agent:
        keys |= keys_in(agent, syn)
    return keys


# Raggruppamento indicativo dell'app (non del Disciplinare): agenti biologici e mezzi di origine
# naturale o minerale, distinti dalle sostanze di sintesi.
BIOLOGICI = ("bacillus", "trichoderma", "ampelomyces", "pythium oligandrum", "aureobasidium", "aerobasidium",
             "saccharomyces", "beauveria", "metarhizium", "paecilomyces", "purpureocillium", "coniothyrium",
             "streptomyces", "gliocladium", "granulovirus", "virus della granulosi", "cpgv", "isaria", "lecanicillium",
             "opius", "encarsia", "eretmocerus", "phytoseiulus", "amblyseius", "neoseiulus", "orius", "macrolophus",
             "chrysoperla", "anagyrus", "cryptolaemus", "aphytis", "leptomastix", "steinernema", "heterorhabditis",
             "feromon", "confusione", "disorientamento", "attract and kill", "trappol", "nucleopoliedrovirus",
             "pseudomonas chlororaphis", "cerevisane", "candida", "clonostachys", "ausiliar", "lanci")
NATURALI = ("rame", "rameic", "zolfo", "olio minerale", "olio paraffinico", "olio essenziale", "olio di arancio",
            "azadiractin", "piretr", "spinosad", "laminarin", "cos-oga", "eugenolo", "geraniolo", "timolo",
            "bicarbonato", "caolino", "zeolite", "silicato", "sali potassici", "acidi grassi", "polisolfuro",
            "lupinus", "fosfato ferrico", "ortofosfato", "estratto", "chitosano", "idrossido di calcio", "farina di",
            "terpeni", "sale potassico", "proteine idrolizzate", "aceto")


def tipo_sostanza(nome: str) -> str:
    n = nome.lower()
    if any(k in n for k in BIOLOGICI):
        return "biologico"
    if any(k in n for k in NATURALI):
        return "naturale"
    return "sintesi"


def build_app_data(readers: dict, crops_of: dict | None = None, anno: int = 2026, anno_prec: int = 2023) -> dict:
    """Dati di difesa per l'app (app/data/difesa.json), per le classi dei lettori di malattie e insetti."""
    syn = _syn()
    disc, old = load_disciplinare(anno), None
    if (DIFESA / f"disciplinare_calabria_{anno_prec}.json").exists():
        old = load_disciplinare(anno_prec)
    gw = load_gowan()
    righe, usi, classi = [], [], {}
    row_idx, use_idx = {}, {}

    def add_row(r):
        k = (r["coltura"], r["avversita"], r["pagina"])
        if k not in row_idx:
            row_idx[k] = len(righe)
            rem = removed_since(old, disc, r["coltura"], r) if old else []
            righe.append({"coltura": r["coltura"], "avversita": r["avversita"], "criteri": r["criteri"],
                          "sostanze": [{"s": s["sostanza"], "n": s["note"], "t": tipo_sostanza(s["sostanza"])} for s in r["sostanze"]],
                          "note": r["note"], "pagina": r["pagina"], "rimosse": rem})
        return row_idx[k]

    def add_use(u):
        k = (u["prodotto"], u["coltura"], u["avversita"], u.get("ambito"))
        if k not in use_idx:
            use_idx[k] = len(usi)
            usi.append(u)
        return use_idx[k]

    copper = {}
    for r in json.load(open(DIFESA / f"disciplinare_calabria_{anno}.json", encoding="utf-8"))["righe"]:
        if r["avversita"].startswith("(***)") and r["coltura"] not in copper:
            copper[r["coltura"]] = (r["avversita"] + " " + r["note"]).strip()
    for head in ("disease", "pest"):
        if head not in readers:
            continue
        for c in readers[head]["classes"]:
            name = c.get("name", "")
            paren = " ".join(re.findall(r"\(([^()]+)\)", name))
            agent = (c.get("card") or {}).get("agent")
            keys = class_keys(c["label"], paren, agent, syn)
            if not keys:
                continue
            plants = (c.get("crops") or (crops_of or {}).get(c["label"]) or [])
            per = {}
            for plant in (plants or ["*"]):
                secs, gcrops = CROPS.get(plant, ([], [])) if plant != "*" else (sorted({r["coltura"] for r in disc["righe"]}), [])
                rows = [add_row(r) for r in disc["righe"] if r["coltura"] in secs and _match(keys, set(r["chiavi"]))]
                uses = [add_use(u) for u in gowan_uses(keys, gcrops, gw, syn)] if gcrops else []
                if rows or uses:
                    per[plant] = {"r": rows, "u": uses}
            if per:
                classi[f"{head}|{c['label']}"] = per
    return {"fonti": {"disciplinare": {"titolo": disc["fonte"], "url": disc["url"], "anno": disc["anno"]},
                      "disciplinare_prec": ({"titolo": old["fonte"], "url": old["url"], "anno": old["anno"]} if old else None),
                      "gowan": {k: gw.get(k) for k in ("fonte", "consultato", "avvertenza")}},
            "righe": righe, "usi": usi, "classi": classi, "rame": copper}
