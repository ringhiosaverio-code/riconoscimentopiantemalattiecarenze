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
    "eulia", "psilla", "capnode", "lebbra", "rogna", "occhio", "piombatura", "carie", "escoriosi", "black",
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
            k = f"{g.lower()} *"
            out.add(syn.get(k, k))
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


def disciplinari() -> list[Path]:
    """File dei Disciplinari della Calabria (configs/difesa/disciplinare_calabria_*.json), dal più vecchio al più
    recente per anno e data di pubblicazione: l'ultimo è quello in vigore, gli altri servono per i confronti."""
    files = []
    for p in DIFESA.glob("disciplinare_calabria_*.json"):
        d = json.load(open(p, encoding="utf-8"))
        files.append(((d["anno"], d.get("pubblicato") or ""), p))
    return [p for _, p in sorted(files)]


def etichetta_versione(d: dict) -> str:
    """Nome breve della versione del Disciplinare: anno, con il mese di pubblicazione se è noto ('agosto 2026')."""
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
            "novembre", "dicembre"]
    pub = d.get("pubblicato") or ""
    if re.match(r"\d{4}-\d{2}", pub) and int(pub[:4]) == int(d["anno"]):
        return f"{mesi[int(pub[5:7]) - 1]} {d['anno']}"
    return str(d["anno"])


def load_disciplinare(anno: int | None = None, path: Path | None = None) -> dict:
    """Disciplinare letto, con i nomi scientifici di ogni avversità. Senza argomenti: quello in vigore (il più
    recente); con anno: la versione più recente di quell'anno."""
    if path is None:
        files = disciplinari()
        if anno is not None:
            files = [f for f in files if json.load(open(f, encoding="utf-8"))["anno"] == anno]
        if not files:
            raise FileNotFoundError(f"nessun Disciplinare della Calabria in {DIFESA}")
        path = files[-1]
    d = json.load(open(path, encoding="utf-8"))
    d["file"] = path.name
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


STRAIN = re.compile(r"^(ceppo\s+)?[A-Z]{1,6}[ -]?[A-Z]?[0-9]{1,6}[A-Z]?$")  # sigle di ceppi: MBI600, M1, QST 713, D747


def tipo_sostanza(nome: str) -> str:
    n = nome.lower()
    if STRAIN.match(nome.strip()) or n.startswith("ceppo"):
        return "biologico"
    if any(k in n for k in BIOLOGICI):
        return "biologico"
    if any(k in n for k in NATURALI):
        return "naturale"
    return "sintesi"


def _scheletro(s: str) -> str:
    """Forma semplificata di un nome di sostanza, per confrontare nomi italiani e inglesi
    (tebuconazolo/tebuconazole, deltametrina/deltamethrin, exitiazox/hexythiazox)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("th", "t"), ("ph", "f"), ("ch", "c"), ("qu", "c"), ("y", "i"), ("k", "c"), ("x", "s"), ("z", "s"), ("h", "")):
        s = s.replace(a, b)
    return s[:-1] if len(s) > 4 and s[-1] in "aeiou" else s


_UE_INDEX: dict = {}


def stato_ue(nome: str, ue: dict | None = None) -> dict | None:
    """Stato nella banca dati UE dei pesticidi di una sostanza scritta in italiano (Disciplinare o etichetta):
    {"nome": nome UE, "stato": "Approved" | "Not approved" | "Pending", "scadenza": ...}. Per i microrganismi con
    più ceppi vale il ceppo approvato, se c'è. None se il nome non si riconosce con sicurezza."""
    import difflib
    ue = ue if ue is not None else load_ue()
    sost = ue.get("sostanze") or {}
    if not sost:
        return None
    key = id(sost)
    if _UE_INDEX.get("key") != key:
        idx = {}
        for n in sost:
            idx.setdefault(_scheletro(n), []).append(n)
        reg = _load_yaml(DIFESA / "sostanze.yaml") if (DIFESA / "sostanze.yaml").exists() else {}
        _UE_INDEX.update({"key": key, "idx": idx, "skel": sorted(idx), "reg": reg.get("sostanze") or {},
                          "manuali": {k.lower(): v for k, v in (reg.get("nomi_ue_disciplinare") or {}).items()}})
    I = _UE_INDEX
    low = re.sub(r"\(\s*\d*\s*\)?$", "", (nome or "").lower())
    low = re.sub(r"\b(esca|pure|puro|pura|con:|spp\.?|sp\.)", " ", low)
    low = re.sub(r"\s+", " ", low.replace("(", " ").replace(")", " ")).strip(" .*:")
    parts = [x.strip() for x in re.split(r"\s*\+\s*", low) if x.strip()]
    out = []
    for part in parts:
        names = None
        if part in I["manuali"]:
            if I["manuali"][part] is None:
                return None
            names = [I["manuali"][part]]
        if names is None:
            for v in I["reg"].values():
                if re.search(v["disciplinare"], part):
                    names = [v["ue"]]
                    break
        if names is None:
            sk = _scheletro(part)
            if len(sk) < 5:
                return None
            if sk in I["idx"]:
                names = I["idx"][sk]
            else:
                pref = [n for s2, ns in I["idx"].items() if s2.startswith(sk) and len(sk) >= 10 for n in ns]
                if pref:  # specie di microrganismo: tutti i ceppi
                    names = pref
                else:
                    close = difflib.get_close_matches(sk, I["skel"], n=1, cutoff=0.9)
                    if close and close[0][:3] == sk[:3]:
                        # nome scritto in modo un po' diverso: si accetta solo una sostanza approvata, perché
                        # un abbinamento incerto non deve far credere revocata una sostanza (fenexamid/fentrazamide)
                        names = [n for n in I["idx"][close[0]] if (sost.get(n) or {}).get("stato") == "Approved"]
        if not names:
            return None
        ents = [dict(sost[n], nome=n) for n in names if n in sost]
        if not ents:
            return None
        ok = [e for e in ents if e.get("stato") == "Approved"]
        out.append(ok[0] if ok else ents[0])
    bad = [e for e in out if e.get("stato") == "Not approved"]
    return bad[0] if bad else (out[0] if out else None)


def load_ue() -> dict:
    p = DIFESA / "sostanze_ue.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else {"sostanze": {}}


def build_app_data(readers: dict, crops_of: dict | None = None) -> dict:
    """Dati di difesa per l'app (app/data/difesa.json), per le classi dei lettori di malattie e insetti.
    Disciplinare in vigore = il più recente; per ogni sostanza uscita dall'elenco si indica l'ultima versione
    precedente che la conteneva; le sostanze non più approvate nell'UE sono segnalate."""
    syn = _syn()
    files = disciplinari()
    disc = load_disciplinare(path=files[-1])
    prev = [load_disciplinare(path=f) for f in reversed(files[:-1])]  # dalla più recente alla più vecchia
    ue = load_ue()
    gw = load_gowan()
    righe, usi, classi = [], [], {}
    row_idx, use_idx = {}, {}

    def sost(x):
        out = {"s": x["sostanza"], "n": x["note"], "t": tipo_sostanza(x["sostanza"])}
        st = stato_ue(x["sostanza"], ue)
        if st and st.get("stato") == "Not approved":
            out["ue"] = {"nome": st["nome"], "stato": st["stato"], "scadenza": st.get("scadenza")}
        return out

    def add_row(r):
        k = (r["coltura"], r["avversita"], r["pagina"])
        if k not in row_idx:
            row_idx[k] = len(righe)
            rem, seen = [], set()
            for old in prev:
                for x in removed_since(old, disc, r["coltura"], r):
                    if x.lower() not in seen:
                        seen.add(x.lower())
                        rem.append({"s": x, "v": etichetta_versione(old)})
            righe.append({"coltura": r["coltura"], "avversita": r["avversita"], "criteri": r["criteri"],
                          "sostanze": [sost(x) for x in r["sostanze"]],
                          "note": r["note"], "pagina": r["pagina"], "rimosse": rem})
        return row_idx[k]

    def add_use(u):
        k = (u["prodotto"], u["coltura"], u["avversita"], u.get("ambito"))
        if k not in use_idx:
            use_idx[k] = len(usi)
            usi.append(u)
        return use_idx[k]

    copper = {}
    for r in json.load(open(files[-1], encoding="utf-8"))["righe"]:
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
                cand = [r for r in disc["righe"] if r["coltura"] in secs and _match(keys, set(r["chiavi"]))]
                exact = [r for r in cand if keys & set(r["chiavi"])]  # stessa specie
                rows = [add_row(r) for r in (exact or cand)]  # le righe che citano solo il genere, se manca la specie
                uses = [add_use(u) for u in gowan_uses(keys, gcrops, gw, syn)] if gcrops else []
                if rows or uses:
                    per[plant] = {"r": rows, "u": uses}
            if per:
                classi[f"{head}|{c['label']}"] = per
    coad = _load_yaml(DIFESA / "gowan_coadiuvanti.yaml") if (DIFESA / "gowan_coadiuvanti.yaml").exists() else {}
    used = {u["prodotto"] for u in usi}
    info = {p["prodotto"]: {k: p.get(k) for k in ("compatibilita", "etichetta_validita", "etichetta") if p.get(k)}
            for p in gw.get("prodotti", []) if p["prodotto"] in used or p["prodotto"] in ("MAGO",)}
    fonte = lambda d: {"titolo": d["fonte"], "url": d["url"], "anno": d["anno"], "versione": etichetta_versione(d),
                       "pubblicato": d.get("pubblicato")}
    return {"coadiuvanti": coad, "prodotti_info": info,
            "fonti": {"disciplinare": fonte(disc), "disciplinare_prec": [fonte(d) for d in prev],
                      "gowan": {k: gw.get(k) for k in ("fonte", "consultato", "avvertenza")},
                      "ue": {k: ue.get(k) for k in ("fonte", "url", "scaricato") if ue.get(k)}},
            "righe": righe, "usi": usi, "classi": classi, "rame": copper}
