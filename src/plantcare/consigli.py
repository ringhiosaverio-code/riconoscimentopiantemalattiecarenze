"""Catalogo Gowan per la Botte e per la sezione Consigli dell'app (app/data/catalogo.json).

Unisce documenti già letti, senza scrivere dosi a mano:
- usi registrati dei prodotti (configs/difesa/gowan_italia.json): dose a ettaro e a ettolitro, intervallo di
  sicurezza e note d'uso, da cui si leggono stadi BBCH, numero massimo di trattamenti e intervalli;
- caratteristiche dalle etichette (gowan_caratteristiche.yaml): gruppo FRAC/IRAC, tipo di azione, api;
- programmi di difesa per fase (gowan_programmi.yaml), nutrizionali (gowan_nutrizionali.yaml), coadiuvanti;
- Disciplinare di produzione integrata della Calabria (avversità, sostanze ammesse e limiti, per coltura);
- stato delle sostanze attive nella banca dati UE (sostanze_ue.json, scripts/aggiorna_norme.py).

L'ordine dei prodotti e la ricetta li calcola app/consigli.js con le regole di consigli_regole.yaml.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from plantcare import difesa as df

ROOT = Path(__file__).resolve().parents[2]
DIFESA = ROOT / "configs" / "difesa"

NUM = r"(\d+(?:[.,]\d+)?)"
DOSE = re.compile(rf"^\s*(max\.?\s*)?{NUM}(?:\s*[-–÷]\s*{NUM})?\s*(g|kg|ml|l|lt|cc)\s*/\s*(ha|hl)\s*$", re.I)
NUMERI = {"un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8}
N_PAROLA = r"(\d+|un|uno|una|due|tre|quattro|cinque|sei|sette|otto)"


def _yaml(name: str) -> dict:
    p = DIFESA / name
    return yaml.safe_load(open(p, encoding="utf-8")) or {} if p.exists() else {}


def _n(s: str) -> float:
    return float(s.replace(",", "."))


def _int(s: str) -> int:
    return NUMERI[s.lower()] if s.lower() in NUMERI else int(s)


def parse_dose(s: str | None) -> dict | None:
    """'1,7-2,7 l/ha' -> {'min': 1.7, 'max': 2.7, 'u': 'l/ha'}; 'max 1 kg/ha' -> solo il massimo."""
    if not s:
        return None
    m = DOSE.match(s)
    if not m:
        return None
    a = _n(m.group(2))
    b = _n(m.group(3)) if m.group(3) else a
    unit = {"lt": "l", "cc": "ml"}.get(m.group(4).lower(), m.group(4).lower())
    out = {"min": min(a, b), "max": max(a, b), "u": f"{unit}/{m.group(5).lower()}"}
    if m.group(1):
        out["solo_max"] = True
    return out


def parse_phi(s: str | None) -> tuple[int | None, str | None]:
    """Intervallo di sicurezza: giorni, oppure la sigla di fase scritta al suo posto (IF, FF, TB, ET)."""
    if not s:
        return None, None
    t = s.replace("gg", "").strip()
    if re.fullmatch(r"\d+", t):
        return int(t), None
    if t.lower().startswith("non necess"):
        return 0, None
    if re.fullmatch(r"[A-Z]{2}", t):
        return None, t
    return None, None


BBCH_RANGE = re.compile(r"BBCH\s*(\d{1,2})\s*[-–]\s*(\d{1,2}|PHI|TC|raccolta)\b", re.I)
BBCH_ONE = re.compile(r"BBCH\s*(\d{1,2})\b(?!\s*[-–])", re.I)


def bbch_finestre(text: str) -> list[list[int]]:
    """Stadi BBCH in cui la nota d'uso permette il trattamento: 'BBCH 13-61', 'BBCH 69-PHI' (fino alla
    raccolta = 99) e coppie 'da ... (BBCH 30) fino a ... (BBCH 69)'."""
    out = []
    for a, b in BBCH_RANGE.findall(text or ""):
        lo, hi = int(a), (99 if not b.isdigit() else int(b))
        if hi < lo:  # a cavallo dell'inverno, es. 'BBCH 93-03': dalla caduta foglie alla ripresa
            out += [[lo, 99], [0, hi]]
        else:
            out.append([lo, hi])
    ones = [(m.start(), int(m.group(1))) for m in BBCH_ONE.finditer(text or "")]
    for (p1, a), (p2, b) in zip(ones, ones[1:]):
        between = text[p1:p2]
        if p2 - p1 < 200 and re.search(r"\bfino\b|\bal\b|\balla\b|\ba\b", between) and b >= a:
            out.append([a, b])
    uniq = []
    for w in out:
        if w not in uniq:
            uniq.append(w)
    return uniq


NMAX = [re.compile(r"(?:al\s+)?massimo\s+(?:di\s+)?" + N_PAROLA + r"\s*(?:[-–]\s*(\d+)\s*)?(?:trattament|applicazion|intervent)", re.I),
        re.compile(r"\bmax\.?\s*(\d+)\s*(?:[-–]\s*(\d+)\s*)?(?:trattament|applicazion|intervent)", re.I),
        re.compile(r"autorizzato per\s+" + N_PAROLA + r"\s+trattamento", re.I),
        re.compile(r"fino a\s+" + N_PAROLA + r"\s+volte", re.I)]
NTIP = re.compile(r"(?:da\s+(\d+)\s+a\s+(\d+)|(\d+)\s*[-–]\s*(\d+))\s+(?:trattament|applicazion|intervent)", re.I)
INTERVALLO = [
    re.compile(r"intervall[oi]\s+(?:minimo\s+)?(?:(?:fra|tra) (?:essi|esse|loro|i trattamenti|le applicazioni)\s+|"
               r"tra un trattamento e l.altro\s+)?(?:di\s+)?(?:circa\s+|almeno\s+)?(\d+)\s*(?:[-–/\\]\s*(\d+))?\s*giorni", re.I),
    re.compile(r"meno di\s+(\d+)\s+o più di\s+(\d+)\s+giorni", re.I),
    re.compile(r"\bogni\s+(\d+)\s*(?:[-–/\\]\s*(\d+))?\s*giorni", re.I),
    re.compile(r"distanziat[ie]\s+(?:di\s+)?(?:almeno\s+|minimo\s+|non meno di\s+)?(\d+)\s*(?:[-–]\s*(\d+))?\s*giorni", re.I),
    re.compile(r"cadenzat[ie]\s+(?:a|di)\s+(\d+)\s*(?:[-–]\s*(\d+))?\s*giorni", re.I),
]
ACQUA = re.compile(r"(\d{2,4}(?:\.\d{3})?)\s*[-–]\s*(\d{2,4}(?:\.\d{3})?)\s*(?:l|lt|litri)\.?\s*(?:d.acqua\s+|di acqua\s+)?"
                   r"(?:/|per\s+)\s*(?:ha\b|ettaro)", re.I)


def leggi_nota(text: str | None) -> dict:
    """Indicazioni lette dalla nota d'uso dell'etichetta (testo intero sempre consultabile nell'app)."""
    t = re.sub(r"\s+", " ", text or "")
    out = {}
    w = bbch_finestre(t)
    if w:
        out["bbch"] = w
    nmax = []
    for rx in NMAX:
        for m in rx.finditer(t):
            g = [x for x in m.groups() if x]
            nmax.append(max(_int(x) for x in g))
    if nmax:
        out["n_max"] = min(nmax)
    m = NTIP.search(t)
    if m:
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if int(a) <= int(b) <= 20:
            out["n_tipico"] = [int(a), int(b)]
    for rx in INTERVALLO:
        m = rx.search(t)
        if m:
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            if 1 <= a <= 60 and a <= b <= 90:
                out["intervallo"] = [a, b]
                break
    for m in ACQUA.finditer(t):
        a, b = int(m.group(1).replace(".", "")), int(m.group(2).replace(".", ""))
        if 50 <= a <= b <= 3000:
            out["acqua"] = [a, b]
            break
    low = t.lower()
    if re.search(r"preventiv", low):
        out["preventivo"] = True
    if re.search(r"prim[ae]\s+(comparsa|sintom|manifestazion|macchie)|comparsa dei primi|primi sintomi|"
                 r"prime forme mobili|prime larve|inizio (dell')?infestazione|presenza (delle|dei) prim", low):
        out["ai_sintomi"] = True
    if "azione collaterale" in low or "attività collaterale" in low:
        out["collaterale"] = True
    return out


def rame_g(composizione: str | None) -> float | None:
    """Rame metallo nel formulato, g per kg (solidi) o per litro (liquidi), dalla composizione."""
    c = composizione or ""
    if not re.search(r"\brame\b", c, re.I):
        return None
    parts = re.findall(r"Rame\s*-[^%]*?(\d+(?:\.\d+)?)%\s*(?:\(=\s*(\d+(?:\.\d+)?)\s*g/L\))?", c, re.I)
    if not parts:
        parts = re.findall(r"Rame\s+(\d+(?:\.\d+)?)%\s*(?:\(=\s*(\d+(?:\.\d+)?)\s*g/L\))?", c, re.I)
    if not parts:
        return None
    if all(gl for _, gl in parts):
        return round(sum(float(gl) for _, gl in parts), 1)
    return round(sum(float(pc) for pc, _ in parts) * 10, 1)


FORMULAZIONI = [
    (r"microgranuli idrodispersibili|granuli idrodispersibili|granuli dispersibili", "WG"),
    (r"polvere bagnabile", "WP"),
    (r"polvere (idro)?solubile.*sacchetti|sacchetti idrosolubili", "WSB"),
    (r"polvere (idro)?solubile|granuli (idro)?solubili", "SG"),
    (r"sospensione concentrata", "SC"),
    (r"suspo-?emulsione", "SE"),
    (r"emulsione (acqua|olio in acqua)", "EW"),
    (r"microincapsulat", "CS"),
    (r"emulsione concentrata|concentrato emulsionabile|liquido emulsionabile|microemulsione", "EC"),
    (r"dispersione (in )?olio|dispersione oleosa", "OD"),
    (r"liquido solubile|concentrato solubile", "SL"),
]


def formulazione_id(formulazione: str | None) -> str:
    """Codice di formulazione delle regole della botte (configs/mixing_rules.yaml)."""
    f = (formulazione or "").lower()
    for rx, code in FORMULAZIONI:
        if re.search(rx, f):
            return code
    return "OTHER"


def sostanze_prodotto(composizione: str | None, reg: dict) -> list[str]:
    """Sostanze attive (chiavi di configs/difesa/sostanze.yaml) presenti nella composizione."""
    low = (composizione or "").lower()
    return [k for k, v in reg.items() if re.search(v["composizione"], low)]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("®", "").replace("™", "")).strip()


def stato_ue() -> dict:
    p = DIFESA / "sostanze_ue.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else {"sostanze": {}}


def ammessa_disciplinare(sostanza: str, righe: list[dict], reg: dict) -> bool:
    rx = reg[sostanza]["disciplinare"]
    return any(re.search(rx, s["sostanza"].lower()) for r in righe for s in r["sostanze"])


def gruppi_colture(nome: str, regole: dict) -> str:
    low = nome.lower()
    for g, rx in regole["gruppi_colture"].items():
        if re.search(rx, low):
            return g
    return "orticole"


def build(readers: dict | None = None) -> dict:
    """Dati del catalogo per l'app."""
    gw = df.load_gowan()
    car = _yaml("gowan_caratteristiche.yaml").get("prodotti") or {}
    prog = _yaml("gowan_programmi.yaml")
    nutri = _yaml("gowan_nutrizionali.yaml")
    coad = _yaml("gowan_coadiuvanti.yaml")
    regole = _yaml("consigli_regole.yaml")
    sreg = _yaml("sostanze.yaml")["sostanze"]
    ue = stato_ue()
    syn = df._syn()
    disc = df.load_disciplinare()
    bio = set(prog.get("bio_gowan") or [])
    notes = gw.get("note_testi") or []

    prodotti, pidx = [], {}
    for p in gw["prodotti"]:
        if not p.get("usi") and p["prodotto"] not in ("MAGO",):
            continue  # confezioni multiple, erbicidi senza usi di difesa, prodotti per la botte (coadiuvanti a parte)
        c = car.get(p["prodotto"], {})
        ss = sostanze_prodotto(p.get("composizione"), sreg)
        stato = {}
        for s in ss:
            e = (ue.get("sostanze") or {}).get(sreg[s]["ue"])
            if e:
                stato[s] = {k: e.get(k) for k in ("stato", "scadenza", "candidata_sostituzione", "basso_rischio")}
                stato[s]["nome"] = sreg[s]["ue"]
        codici = c.get("codici")
        if codici is None:
            codici = [sreg[s]["gruppo"] for s in ss if sreg[s].get("gruppo")]
        cu = rame_g(p.get("composizione"))
        liquid = bool(re.search(r"g/L", p.get("composizione") or "")) or formulazione_id(p.get("formulazione")) in ("SC", "SE", "EW", "CS", "EC", "OD", "SL")
        item = {"nome": p["prodotto"], "pagina": p.get("pagina"), "etichetta": p.get("etichetta"),
                "registrazione": p.get("registrazione"), "composizione": p.get("composizione"),
                "formulazione": p.get("formulazione"), "form": formulazione_id(p.get("formulazione")),
                "categoria": "rame" if cu else "altro", "rame_g": cu, "liquido": liquid,
                "sostanze": [{"id": s, "nome": sreg[s]["nome"], "tipo": sreg[s]["tipo"]}
                             | ({"rischio": sreg[s]["rischio"]} if sreg[s].get("rischio") else {}) for s in ss],
                "ue": stato, "codici": codici, "codici_fonte": c.get("codici_fonte"),
                "tipo": c.get("tipo"), "azione": c.get("azione") or [], "citazioni": c.get("citazioni") or [],
                "dose_nota": c.get("dose"), "momento": c.get("momento"), "api": c.get("api"),
                "api_fioritura": c.get("api_fioritura"), "api_sera": c.get("api_sera"),
                "bio": p["prodotto"] in bio, "compatibilita": p.get("compatibilita"),
                "etichetta_validita": p.get("etichetta_validita")}
        pidx[p["prodotto"]] = len(prodotti)
        prodotti.append({k: v for k, v in item.items() if v not in (None, [], {}, "")} | {"bio": item["bio"]})

    # usi: forma compatta, con dosi e note lette
    usi, note_out, note_idx = [], [], {}
    for p in gw["prodotti"]:
        if p["prodotto"] not in pidx:
            continue
        for u in p["usi"]:
            if u.get("modo") and u["modo"] != "produzione":
                continue  # vivai e semenzai: fuori dallo scopo dei consigli
            nt = notes[u["note"]] if isinstance(u.get("note"), int) else (u.get("note") or "")
            phi, fase = parse_phi(u.get("intervallo_sicurezza"))
            e = {"p": pidx[p["prodotto"]], "c": u["coltura"], "s": "serra" if "serra" in (u.get("ambito") or "") else "campo",
                 "a": u.get("avversita") or "", "k": sorted(df.keys_in(" ".join(u.get("scientifici") or []) + " " + (u.get("avversita") or ""), syn))}
            for key, raw in (("ha", u.get("dose_ha")), ("hl", u.get("dose_hl"))):
                d = parse_dose(raw)
                if d:
                    e[key] = d
            if phi is not None:
                e["phi"] = phi
            if fase:
                e["phi_fase"] = fase
            if nt:
                if nt not in note_idx:
                    note_idx[nt] = len(note_out)
                    note_out.append(nt)
                e["n"] = note_idx[nt]
                e.update(leggi_nota(nt))
            usi.append(e)

    # colture: nomi delle registrazioni Gowan; sezioni del Disciplinare dalle corrispondenze di difesa.CROPS
    sez_di = {}
    for plant, (secs, gcrops) in df.CROPS.items():
        for gc in gcrops:
            sez_di.setdefault(gc, {"sezioni": set(), "plant": plant})["sezioni"].update(secs)
    extra = {"Lattuga": ["LATTUGA"], "Cocomero": ["COCOMERO"], "Melone": ["MELONE"], "Fagiolino": ["FAGIOLINO"],
             "Fagiolo": ["FAGIOLO"], "Rucola": ["RUCOLA"], "Finocchio": ["FINOCCHIO"], "Asparago": ["ASPARAGO"],
             "Cicoria": ["CICORIA"], "Radicchio": ["RADICCHIO"], "Scarola": ["INDIVIA RICCIA E SCAROLA"],
             "Indivia": ["INDIVIA RICCIA E SCAROLA"], "Pisello": ["PISELLO"], "Fava": ["FAVA"], "Orzo": ["ORZO"],
             "Riso": ["RISO"], "Farro": ["FARRO"], "Avena": ["AVENA-SEGALE-TRITICALE"], "Segale": ["AVENA-SEGALE-TRITICALE"],
             "Triticale": ["AVENA-SEGALE-TRITICALE"], "Cavolo cappuccio": ["CAVOLO A TESTA"], "Cavolo verza": ["CAVOLO A TESTA"],
             "Cavolo di Bruxelles": ["CAVOLO A TESTA"], "Cavolo rapa": ["CAVOLO RAPA"], "Cime di rapa": ["CAVOLO A FOGLIA"],
             "Cavolo nero": ["CAVOLO A FOGLIA"], "Albicocco": ["ALBICOCCO", "ALBICCCO"], "Arancio": ["AGRUMI"],
             "Limone": ["AGRUMI"], "Mandarino": ["AGRUMI"], "Clementino": ["AGRUMI"], "Agrumi": ["AGRUMI"],
             "Pompelmo": ["AGRUMI"], "Bergamotto": ["AGRUMI"], "Cedro": ["AGRUMI"], "Chinotto": ["AGRUMI"],
             "Vite": ["VITE DA VINO", "VITE DA TAVOLA"], "Vite per uva da vino": ["VITE DA VINO"],
             "Vite per uva da tavola": ["VITE DA TAVOLA"]}
    sezioni_disc = {r["coltura"] for r in disc["righe"]}
    nomi_colture = sorted({u["c"] for u in usi})
    colture = []
    for n in nomi_colture:
        secs = set(extra.get(n, [])) or (sez_di.get(n, {}).get("sezioni") or set())
        secs = sorted(s for s in secs if s in sezioni_disc)
        progr = next((k for k, v in (prog.get("programmi") or {}).items() if n in v.get("colture_gowan", [])), None)
        colture.append({"nome": n, "sezioni": secs, "plant": sez_di.get(n, {}).get("plant"), "programma": progr,
                        "gruppo": gruppi_colture(n, regole)})

    # righe del Disciplinare usate, con i limiti delle note numerate
    righe, ridx = [], {}

    def add_row(r):
        k = (r["coltura"], r["avversita"], r["pagina"])
        if k not in ridx:
            ridx[k] = len(righe)
            lim = {m.group(1): m.group(2).strip(" ;.") for m in re.finditer(r"\((\d+)\)\s*(.*?)(?=\(\d+\)|$)", r["note"] or "")}
            gen = re.split(r"\(\d+\)", r["note"] or "")[0].strip()
            righe.append({"coltura": r["coltura"], "avversita": r["avversita"], "criteri": r["criteri"],
                          "sostanze": _sostanze_riga(r["sostanze"]), "limiti": lim, "generale": gen, "pagina": r["pagina"]})
        return ridx[k]

    # avversità per coltura: righe del Disciplinare (nome ufficiale) e, per il resto, le avversità degli usi
    pest_rx = re.compile(r"(?i)afid|tignol|nottu|mosc|acar|ragnet|tripid|cimic|aleurod|cicalin|coccinigl|cotonell|"
                         r"minat|piralid|dorifor|elaterid|lepidott|carpocaps|cidia|cydia|psill|eriofid|forficul|mirid|"
                         r"oziorrinc|rodilegn|cecidomi|limacc|lumac|nematod|margaroni|fleotrib|eulia|ricamatric|tortric|"
                         r"ifantri|anarsi|metcalf|scafoide|tentredin|punteruol|curculion|tuta|bactrocer|ceratiti|"
                         r"drosophil|halyomorph|insett|larv|bruch|altica|agrili|maggiolin|cocciniglia|aleirod|"
                         r"cavolaia|pieride|plutella|spodopter|helicoverpa|heliothis|mamestra|autographa|ostrinia|"
                         r"sesamia|diabrotica|grillotalpa|oziorinco|zabro|lema|criocer|cecidomia|tingide|psille|"
                         r"capnode|scolit|xylebor|zeuzer|cossus|antonomo|balanin|cinipide|vespa|formic|grillo|"
                         r"locust|cavallett|mosca|thrips|frankliniel|tetranych|panonych|myzus|aphis|bemisia|trialeurod|"
                         r"fillosser|viteus|sfinge|sigaraio|cetonia|oziorrinco|tarlo|tignole|tortrice|nematod")
    by_crop = {}
    for i, u in enumerate(usi):
        by_crop.setdefault(u["c"], []).append(i)
    avv = {}
    for c in colture:
        rows = [r for r in disc["righe"] if r["coltura"] in c["sezioni"]]
        ents = []
        covered = set()
        for r in rows:
            keys = set(r["chiavi"])
            match = [i for i in by_crop.get(c["nome"], []) if keys and usi[i]["k"] and df._match(keys, set(usi[i]["k"]))]
            ents.append({"nome": r["avversita"], "k": sorted(keys), "r": [add_row(r)], "u": match,
                         "t": "insetto" if pest_rx.search(r["avversita"]) else "malattia"})
            covered.update(match)
        # avversità registrate che il Disciplinare non elenca per questa coltura: una voce per nome comune
        groups = {}
        for i in by_crop.get(c["nome"], []):
            if i in covered:
                continue
            u = usi[i]
            common = re.sub(r"\s*\(.*$", "", u["a"]).strip() or u["a"]
            g = groups.setdefault(common.lower(), {"nome": common, "u": [], "k": set(), "sci": []})
            g["u"].append(i)
            g["k"].update(u["k"])
            for x in re.findall(r"\(([^()]+)\)", u["a"]):
                for y in re.split(r",\s*", x):
                    if y and y not in g["sci"]:
                        g["sci"].append(y)
        for key, g in sorted(groups.items()):
            sci = ", ".join(g["sci"][:4]) + (", …" if len(g["sci"]) > 4 else "")
            ents.append({"nome": f"{g['nome']} ({sci})" if sci else g["nome"], "k": sorted(g["k"]), "r": [], "u": g["u"],
                         "t": "insetto" if pest_rx.search(g["nome"] + " " + sci) else "malattia"})
        # voci con lo stesso nome: si uniscono
        merged, seen = [], {}
        for e in ents:
            key = e["nome"].lower()
            if key in seen:
                m = merged[seen[key]]
                for f in ("u", "k", "r"):
                    m[f] = sorted(set(m[f]) | set(e[f]))
            else:
                seen[key] = len(merged)
                merged.append(e)
        for e in merged:  # se i prodotti registrati sono insetticidi o acaricidi, l'avversità è un parassita animale
            kinds = {_insetticida(prodotti[usi[i]["p"]]) for i in e["u"]}
            if kinds == {True}:
                e["t"] = "insetto"
            elif kinds == {False}:
                e["t"] = "malattia"
        merged.sort(key=lambda e: (e["t"], e["nome"].lower()))
        for n, e in enumerate(merged):
            e["id"] = f"a{n}"
        avv[c["nome"]] = merged

    # classi dei lettori -> voci di Consigli (coltura Gowan e avversità), per il pulsante "Prepara la ricetta"
    classi = {}
    for head in ("disease", "pest"):
        for cl in (readers or {}).get(head, {}).get("classes", []):
            name = cl.get("name", "")
            paren = " ".join(re.findall(r"\(([^()]+)\)", name))
            keys = df.class_keys(cl["label"], paren, (cl.get("card") or {}).get("agent"), syn)
            if not keys:
                continue
            hits = []
            for plant in cl.get("crops") or []:
                for gc in df.CROPS.get(plant, ([], []))[1]:
                    for e in avv.get(gc, []):
                        if e["k"] and df._match(keys, set(e["k"])) and e["u"]:
                            hits.append({"plant": plant, "c": gc, "id": e["id"]})
            if hits:
                classi[f"{head}|{cl['label']}"] = hits

    # programmi: solo i campi che servono all'app
    programmi = {}
    for k, v in (prog.get("programmi") or {}).items():
        programmi[k] = {"titolo": v["titolo"], "url": v["url"], "fasi": v.get("fasi"), "voci": v.get("voci"),
                        "epoche": v.get("epoche"), "complementi": v.get("complementi"),
                        "complementi_testo": v.get("complementi_testo")}

    # forma compatta: colture e avversità registrate per indice, senza i nomi scientifici (servivano solo qui)
    cidx = {c["nome"]: i for i, c in enumerate(colture)}
    testi, tidx = [], {}
    for u in usi:
        u["c"] = cidx[u["c"]]
        if u["a"] not in tidx:
            tidx[u["a"]] = len(testi)
            testi.append(u["a"])
        u["a"] = tidx[u["a"]]
        u.pop("k", None)
        for key in ("ha", "hl"):
            if key in u:
                d = u[key]
                u[key] = [d["min"], d["max"], d["u"]] + ([1] if d.get("solo_max") else [])
    for ents in avv.values():
        for e in ents:
            e.pop("k", None)

    return {
        "versione": 1,
        "fonti": {"gowan": {k: gw.get(k) for k in ("fonte", "consultato", "avvertenza")},
                  "programmi": prog.get("fonte"),
                  "disciplinare": {"titolo": disc["fonte"], "url": disc["url"], "anno": disc["anno"],
                                   "versione": df.etichetta_versione(disc), "pubblicato": disc.get("pubblicato")},
                  "ue": {k: ue.get(k) for k in ("fonte", "url", "scaricato") if ue.get(k)},
                  "nutrizionali": nutri.get("fonte"), "coadiuvanti": coad.get("fonte"),
                  "norme": _norme_stato()},
        "prodotti": prodotti, "usi": usi, "testi": testi, "note": note_out, "colture": colture, "avversita": avv,
        "righe": righe, "classi": classi, "rame": _rame(), "programmi": programmi, "avversita_programmi": prog.get("avversita"),
        "nutrizionali": nutri, "coadiuvanti": coad.get("prodotti") or [],
        "sostanze_disciplinare": {k: v["disciplinare"] for k, v in sreg.items()},
        "regole": {k: regole[k] for k in ("punteggi", "gruppi_basso_rischio", "situazioni", "gruppi_colture",
                                           "fasi_generiche", "epoche_fasi", "fioritura_bbch", "limiti_fase", "avvertenza")},
    }


ESCA = re.compile(r"(?i)attract|\besca\b|esche|trappol|dispositiv|decis trap")


def _sostanze_riga(sostanze: list[dict]) -> list[dict]:
    """Sostanze di una riga del Disciplinare; 'esca' = ammessa solo in esche, trappole o dispositivi attract and
    kill (es. 'Dispositivi di: Attract and kill con deltametrina o Lambdacialotrina'), non in trattamenti alla chioma."""
    out, prev_q, prev_cont = [], False, False
    for x in sostanze:
        name = x["sostanza"]
        q = bool(ESCA.search(name)) or (prev_q and prev_cont)
        e = {"s": name, "n": x["note"]}
        if q:
            e["esca"] = 1
        out.append(e)
        prev_cont = bool(re.search(r"(?:\s(?:o|e|con)|:)\s*$", name))
        prev_q = q
    return out


def _rame() -> dict:
    """Limite del rame del Disciplinare in vigore per sezione (riga '(***)' delle tabelle)."""
    out = {}
    for r in json.load(open(df.disciplinari()[-1], encoding="utf-8"))["righe"]:
        if r["avversita"].startswith("(***)") and r["coltura"] not in out:
            out[r["coltura"]] = (r["avversita"] + " " + r["note"]).strip()
    return out


def _insetticida(p: dict) -> bool:
    return any(c.startswith("IRAC") for c in p.get("codici") or []) or bool(re.search(r"(?i)insettic|acaric", p.get("tipo") or ""))


def _norme_stato() -> dict | None:
    p = DIFESA / "norme_stato.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else None
