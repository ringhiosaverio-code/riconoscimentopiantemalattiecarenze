"""Classe dei lettori (malattie o insetti) a partire da un testo: didascalia, titolo di una foto, pagina.

Serve per le foto di pubblicazioni, bollettini e schede, dove la diagnosi è scritta accanto alla foto.
Si cercano:
- nomi scientifici (genere specie, anche abbreviati: "X. fastidiosa") delle classi, dei loro agenti
  (configs/difesa/agenti_classi.yaml), dei soggetti Bugwood e delle specie del quiz, con i sinonimi;
- nomi italiani di uso tecnico, alcuni solo insieme alla coltura (es. "lebbra" con "olivo").
Se il testo porta a più classi diverse, la risposta è vuota: meglio nessuna etichetta che una sbagliata.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]

# sinonimi e nomi vecchi frequenti nella letteratura italiana -> classe
SINONIMI = {
    "spilocaea oleaginea": ("disease", "inat:venturia_oleaginea"),
    "cycloconium oleaginum": ("disease", "inat:venturia_oleaginea"),
    "fusicladium oleagineum": ("disease", "inat:venturia_oleaginea"),
    "venturia oleaginea": ("disease", "inat:venturia_oleaginea"),
    "phoma tracheiphila": ("disease", "lit:plenodomus_tracheiphilus"),
    "deuterophoma tracheiphila": ("disease", "lit:plenodomus_tracheiphilus"),
    "plenodomus tracheiphilus": ("disease", "lit:plenodomus_tracheiphilus"),
    "dacus oleae": ("pest", "inat:bactrocera_oleae"),
    "tuta absoluta": ("pest", "inat:phthorimaea_absoluta"),
    "stigmina carpophila": ("disease", "inat:wilsonomyces_carpophilus"),
    "coryneum beijerinckii": ("disease", "inat:wilsonomyces_carpophilus"),
    "endothia parasitica": ("disease", "bw:cryphonectria_parasitica"),
    "peronospora schleideni": ("disease", "bw:peronospora_destructor"),
    "uncinula necator": ("disease", "powdery_mildew_grapevine"),
    "phaeoacremonium minimum": ("disease", "grapevine_esca"),
    "phaeoacremonium aleophilum": ("disease", "grapevine_esca"),
    "fomitiporia mediterranea": ("disease", "grapevine_esca"),
    "phaeomoniella chlamydospora": ("disease", "grapevine_esca"),
}
# nomi italiani: (espressione, classe, coltura richiesta nel testo o None)
OLIVO, VITE, AGRUMI = r"oliv|olea", r"\bvit[ei]\b|vigne|vitis|grapevine", r"agrum|citrus|limon|lemon|aranc|orange|mandarin|clementin|bergamott|cedro"
ITALIANI = [
    (r"occhio di pavone|cicloconio", ("disease", "inat:venturia_oleaginea"), None),
    (r"rogna", ("disease", "inat:pseudomonas_savastanoi"), OLIVO),
    (r"mal secco", ("disease", "lit:plenodomus_tracheiphilus"), AGRUMI),
    (r"lebbra|antracnosi", ("disease", "inat:colletotrichum"), OLIVO),
    (r"fumaggine", ("disease", "agml_lemon:Sooty Mould"), None),
    (r"mosca (dell[e']\s*)?oliv", ("pest", "inat:bactrocera_oleae"), None),
    (r"tignola dell'?\s*olivo", ("pest", "inat:prays_oleae"), None),
    (r"mezzo grano di pepe", ("pest", "inat:saissetia_oleae"), None),
    (r"cotonello dell'?\s*olivo|psilla dell'?\s*olivo", ("pest", "inat:euphyllura_olivina"), None),
    (r"margaronia", ("pest", "inat:palpita_vitrealis"), None),
    (r"rodilegno giallo", ("pest", "inat:zeuzera_pyrina"), None),
    (r"mosca mediterranea della frutta", ("pest", "inat:ceratitis_capitata"), None),
    (r"minatrice serpentina", ("pest", "inat:phyllocnistis_citrella"), None),
    (r"aleurodide fioccoso", ("pest", "inat:aleurothrixus_floccosus"), None),
    (r"aleurodide spinoso", ("pest", "inat:aleurocanthus_spiniferus"), None),
    (r"cocciniglia rossa forte", ("pest", "inat:aonidiella_aurantii"), None),
    (r"cotonello degli agrumi", ("pest", "inat:planococcus_citri"), None),
    (r"peronospora", ("disease", "grapevine_downy_mildew"), VITE),
    (r"oidio|mal bianco", ("disease", "powdery_mildew_grapevine"), VITE),
    (r"mal dell'?\s*esca|\besca\b", ("disease", "grapevine_esca"), VITE),
    (r"accartocciamento fogliare", ("disease", "plantwild:grapevine leafroll disease"), VITE),
    (r"cancro batterico dell'?\s*actinidia", ("disease", "inat:pseudomonas_syringae"), None),
    (r"(?-i:\bPsa\b)", ("disease", "inat:pseudomonas_syringae"), r"actinidi|kiwi"),
    (r"colpo di fuoco", ("disease", "inat:erwinia_amylovora"), None),
    (r"bolla del pesco", ("disease", "peach_leaf_curl"), None),
    (r"corineo", ("disease", "inat:wilsonomyces_carpophilus"), None),
    (r"sharka|vaiolatura delle drupacee", ("disease", "peach_plum_pox"), None),
    (r"ticchiolatura del melo", ("disease", "apple_scab"), None),
    (r"tignola del pomodoro", ("pest", "inat:phthorimaea_absoluta"), None),
    (r"peronospora della cipolla", ("disease", "bw:peronospora_destructor"), None),
    (r"verticilli?osi", ("disease", "bw:verticillium_dahliae"), None),
    (r"cancro della corteccia del castagno|cancro corticale del castagno", ("disease", "bw:cryphonectria_parasitica"), None),
    (r"disseccamento rapido dell'?\s*olivo|co\.?\s*di\.?\s*r\.?\s*o", ("disease", "inat:xylella_fastidiosa"), None),
    (r"cimice asiatica", ("pest", "inat:halyomorpha_halys"), None),
    (r"moscerino dei piccoli frutti", ("pest", "inat:drosophila_suzukii"), None),
    (r"tignoletta della vite", ("pest", "inat:lobesia_botrana"), None),
    (r"carpocapsa", ("pest", "inat:cydia_pomonella"), None),
]
# classi di antracnosi per coltura (il genere Colletotrichum da solo va in inat:colletotrichum)
ANTRACNOSI = {"plantwild:strawberry anthracnose", "citrus_anthracnose", "plantwild:peach anthracnose",
              "plantwild:banana anthracnose", "agml_vegleaf:Anthracnose lesions"}
ANTRACNOSI_COLTURA = [(r"fragol|strawberr", "plantwild:strawberry anthracnose"), (r"pesc|peach", "plantwild:peach anthracnose"),
                      (r"banan", "plantwild:banana anthracnose"), (r"oliv|olea", "inat:colletotrichum"),
                      (AGRUMI, "citrus_anthracnose")]
# generi che bastano da soli (classi a livello di genere)
GENERI = {"colletotrichum": ("disease", "inat:colletotrichum")}


@lru_cache(maxsize=1)
def _scientifici() -> dict[str, tuple[str, str]]:
    """binomio minuscolo -> (lettore, classe), da tutte le configurazioni del progetto."""
    out: dict[str, tuple[str, str]] = {}

    def add(name, head, label):
        parts = re.findall(r"[A-Za-z][a-z-]+", name or "")
        if len(parts) >= 2 and parts[0][0].isupper() and parts[1].islower():
            out.setdefault(f"{parts[0].lower()} {parts[1]}", (head, label))

    agenti = yaml.safe_load(open(ROOT / "configs/difesa/agenti_classi.yaml", encoding="utf-8"))
    for label, names in (agenti.get("agenti") or {}).items():
        for n in names:
            add(n, "disease", label)
    bw = yaml.safe_load(open(ROOT / "configs/bugwood.yaml", encoding="utf-8"))
    for e in bw["malattie"]:
        add(e["sci"], "disease", e["classe"])
    quiz = yaml.safe_load(open(ROOT / "configs/quiz_calabria.yaml", encoding="utf-8"))
    for e in quiz.get("addestramento_malattie", []):
        add(e["taxon"], "disease", e["classe"])
    for p in quiz["parassiti"]:
        add(p["taxon"], "pest", "inat:" + re.sub(r"[^a-z0-9]+", "_", p["taxon"].lower()).strip("_"))
    readers = ROOT / "app/data/readers.json"
    if readers.exists():
        r = json.load(open(readers, encoding="utf-8"))
        for head in ("disease", "pest"):
            for c in r.get(head, {}).get("classes", []):
                for inside in re.findall(r"\(([^)]*)\)", c.get("name", "")):
                    add(inside, head, c["label"])
    out.update(SINONIMI)
    return out


# parole delle colture, per scartare un'etichetta se il testo parla di un'altra coltura
COLTURE_TESTO = {
    "malus_domestica": r"\bappl|\bmel[oai]\b|malus", "vitis_vinifera": r"grape|\bvit[ei]\b|vigne|vitis|vineyard",
    "olea_europaea": r"\boliv|olea\b", "prunus_persica": r"peach|\bpesc[oh]", "solanum_lycopersicum": r"tomat|pomodor",
    "pyrus_communis": r"\bpear|\bper[oi]\b|pyrus", "prunus_avium": r"cherr|cilieg", "actinidia_chinensis": r"kiwi|actinidi",
    "citrus": AGRUMI, "capsicum_annuum": r"pepper|peperon|capsicum", "solanum_tuberosum": r"potat|patat",
    "fragaria_ananassa": r"strawberr|fragol", "solanum_melongena": r"eggplant|melanzan|aubergine",
}


@lru_cache(maxsize=1)
def _colture_classi() -> dict[str, set[str]]:
    readers = ROOT / "app/data/readers.json"
    if not readers.exists():
        return {}
    r = json.load(open(readers, encoding="utf-8"))
    out = {}
    for head in ("disease", "pest"):
        for c in r.get(head, {}).get("classes", []):
            crops = {("citrus" if x.startswith("citrus_") else x) for x in c.get("crops") or []}
            if crops and all(k in COLTURE_TESTO for k in crops):
                out[c["label"]] = crops
    return out


def coltura_coerente(label: str, testo: str) -> bool:
    """Falso se la classe vale per colture precise e il testo nomina solo altre colture."""
    crops = _colture_classi().get(label)
    if not crops:
        return True
    citate = {k for k, pat in COLTURE_TESTO.items() if re.search(pat, testo, re.I)}
    return not citate or bool(citate & crops)


def classi_da_testo(testo: str) -> set[tuple[str, str]]:
    """Classi citate nel testo (insieme vuoto se nessuna)."""
    if not testo:
        return set()
    t = re.sub(r"\s+", " ", testo)
    low = t.lower()
    found: set[tuple[str, str]] = set()
    sci = _scientifici()
    for m in re.finditer(r"\b([A-Z][a-z]+)\s+([a-z][a-z-]{2,})\b", t):
        k = f"{m.group(1).lower()} {m.group(2)}"
        if k in sci:
            found.add(sci[k])
    for m in re.finditer(r"\b([A-Z])\.\s?([a-z][a-z-]{3,})\b", t):  # forma abbreviata "X. fastidiosa"
        cands = {v for k, v in sci.items() if k.split()[1] == m.group(2) and k[0] == m.group(1).lower()}
        if len(cands) == 1:
            found |= cands
    for g, v in GENERI.items():
        if re.search(rf"\b{g}\b", low):
            found.add(v)
    for pat, cls, crop in ITALIANI:
        if re.search(pat, t, re.I) and (crop is None or re.search(crop, t, re.I)):
            found.add(cls)
    # antracnosi: il genere Colletotrichum va nella classe della coltura citata, se c'è
    anthr = {c for c in found if c[1] in ANTRACNOSI}
    if ("disease", "inat:colletotrichum") in found:
        crop = next((lab for pat, lab in ANTRACNOSI_COLTURA if re.search(pat, t, re.I)), "inat:colletotrichum")
        found = (found - anthr - {("disease", "inat:colletotrichum")}) | {("disease", crop)}
    return {c for c in found if coltura_coerente(c[1], t)}


def classe_unica(testo: str) -> tuple[str, str] | None:
    """La classe se il testo ne cita una sola, altrimenti None."""
    f = classi_da_testo(testo)
    return next(iter(f)) if len(f) == 1 else None
