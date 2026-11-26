"""Consigli di difesa: lettura delle etichette, catalogo Gowan, ordine dei prodotti e ricetta (app/consigli.js).

Le regole sono scritte in configs/difesa/consigli_regole.yaml; qui si controlla che facciano quello che dicono,
su casi verificabili a mano con le etichette e il Disciplinare della Calabria.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from plantcare import consigli as cs
from plantcare import difesa as df

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CAT = APP / "data" / "catalogo.json"


# ------------------------------------------------------------------ lettura dei documenti
def test_dosi_e_intervallo_di_sicurezza():
    assert cs.parse_dose("1,7-2,7 l/ha") == {"min": 1.7, "max": 2.7, "u": "l/ha"}
    assert cs.parse_dose("95-175 g/hl") == {"min": 95.0, "max": 175.0, "u": "g/hl"}
    assert cs.parse_dose("2,5 Kg/Ha")["u"] == "kg/ha"
    assert cs.parse_dose("max 1 kg/ha")["solo_max"] is True
    assert cs.parse_dose("vedi etichetta") is None
    assert cs.parse_phi("3 gg") == (3, None)
    assert cs.parse_phi("non necessario gg") == (0, None)
    assert cs.parse_phi("IF gg") == (None, "IF")  # sospendere a inizio fioritura


def test_note_d_etichetta():
    n = cs.leggi_nota("Applicare il prodotto (alla fase fenologica BBCH 93-03). Effettuare al massimo 2-3 trattamenti "
                      "all'anno rispettando un intervallo di 7-10 giorni.")
    assert n["bbch"] == [[93, 99], [0, 3]]  # a cavallo dell'inverno
    assert n["n_max"] == 3 and n["intervallo"] == [7, 10]
    n = cs.leggi_nota("I trattamenti sono consentiti a partire da inizio levata (BBCH 30) fino a fine fioritura (BBCH 69). "
                      "Massimo un trattamento per stagione. Trattare alla dose indicata in 400-600 l/Ha di acqua.")
    assert n["bbch"] == [[30, 69]] and n["n_max"] == 1 and n["acqua"] == [400, 600]
    assert cs.leggi_nota("Non distanziare i trattamenti tra loro meno di 10 o più di 14 giorni.")["intervallo"] == [10, 14]
    assert cs.leggi_nota("Intervenire alla dose indicata dalla terza foglia al tempo di carenza (BBCH 13-TC).")["bbch"] == [[13, 99]]


def test_rame_metallo_e_formulazione():
    assert cs.rame_g("Rame - idrossido di rame 10% (= 136g/L) Rame - ossicloruro di rame 10% (= 136g/L)") == 272.0
    assert cs.rame_g("Rame - ossicloruro di rame 35%") == 350.0
    assert cs.rame_g("Zoxamide 21.8% (= 240g/L)") is None
    assert cs.formulazione_id("GRANULI IDRODISPERSIBILI") == "WG"
    assert cs.formulazione_id("MICROGRANULI IDRODISPERSIBILI") == "WG"
    assert cs.formulazione_id("SOSPENSIONE CONCENTRATA") == "SC"
    assert cs.formulazione_id("POLVERE BAGNABILE") == "WP"
    assert cs.formulazione_id("CONCENTRATO EMULSIONABILE") == "EC"
    assert cs.formulazione_id("LIQUIDO SOLUBILE") == "SL"


def test_sostanze_solo_in_esche():
    out = cs._sostanze_riga([{"sostanza": s, "note": []} for s in
                             ("Dispositivi di:", "Attract and kill con deltametrina o", "Labdacialotrina", "Spinosad esca", "Acetamiprid")])
    assert [x.get("esca", 0) for x in out] == [1, 1, 1, 1, 0]


def test_stato_ue_senza_falsi_revocati():
    ue = df.load_ue()
    if not ue.get("sostanze"):
        pytest.skip("configs/difesa/sostanze_ue.json assente (scripts/aggiorna_norme.py --ue)")
    st = df.stato_ue("Fenpyraxamine", ue)  # errore di battitura del Disciplinare, sostanza non più approvata
    assert st["nome"] == "Fenpyrazamine" and st["stato"] == "Not approved"
    assert df.stato_ue("Fenaxamide", ue) is None  # incerto (fenexamid o fentrazamide?): nessun avviso
    assert df.stato_ue("Fenexamid", ue)["stato"] == "Approved"
    assert df.stato_ue("Baculovirus", ue) is None  # voce generica
    assert df.stato_ue("Prodotti rameici", ue)["nome"] == "Copper compounds"
    assert df.stato_ue("Metalaxil – M", ue)["nome"] == "Metalaxyl-M"


def test_versioni_del_disciplinare():
    files = df.disciplinari()
    assert files[-1].name == "disciplinare_calabria_2026_08.json"  # aggiornamento di agosto 2026, in vigore
    assert df.etichetta_versione(df.load_disciplinare()) == "agosto 2026"
    assert df.load_disciplinare(2023)["anno"] == 2023


def test_citazioni_delle_etichette():
    """Ogni frase citata in gowan_caratteristiche.yaml è nel testo dell'etichetta o della pagina prodotto
    (solo dove i PDF scaricati sono disponibili: PLANTCARE_ETICHETTE=<cartella con etichette e pagine>)."""
    import os
    import re
    base = os.environ.get("PLANTCARE_ETICHETTE")
    if not base or not shutil.which("pdftotext"):
        pytest.skip("etichette Gowan non disponibili")
    car = yaml.safe_load(open(ROOT / "configs/difesa/gowan_caratteristiche.yaml", encoding="utf-8"))["prodotti"]
    norm = lambda t: re.sub(r"\s+", " ", t.replace("’", "'").replace("®", "")).strip()
    for name, c in car.items():
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("ù", "u")).strip("-")
        pdf, page = Path(base) / "etichette" / f"{slug}.pdf", Path(base) / "prod" / f"{slug}.html"
        text = ""
        if pdf.exists():
            text += subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
        if page.exists():
            import html
            text += html.unescape(re.sub(r"<[^>]+>", " ", page.read_text(encoding="utf-8", errors="ignore")))
        if not text:
            continue
        for q in c.get("citazioni", []) + [c[k] for k in ("api", "dose", "api_sera") if c.get(k)]:
            assert norm(q) in norm(text), f"{name}: citazione non trovata: {q}"


# ------------------------------------------------------------------ catalogo
@pytest.fixture(scope="module")
def catalogo():
    if not CAT.exists():
        pytest.skip("app/data/catalogo.json non costruito")
    return json.load(open(CAT, encoding="utf-8"))


def test_catalogo_coerente(catalogo):
    c = catalogo
    n_p, n_u = len(c["prodotti"]), len(c["usi"])
    assert all(0 <= u["p"] < n_p and 0 <= u["c"] < len(c["colture"]) and 0 <= u["a"] < len(c["testi"]) for u in c["usi"])
    for crop, ents in c["avversita"].items():
        assert crop in {x["nome"] for x in c["colture"]}
        for e in ents:
            assert e["t"] in ("malattia", "insetto")
            assert all(0 <= i < n_u and c["colture"][c["usi"][i]["c"]]["nome"] == crop for i in e["u"])
            assert all(0 <= i < len(c["righe"]) for i in e["r"])
    for key, hits in c["classi"].items():
        for h in hits:
            assert any(e["id"] == h["id"] for e in c["avversita"][h["c"]])
    # dosi sempre dalle registrazioni: mai inventate
    for u in c["usi"]:
        for k in ("ha", "hl"):
            if k in u:
                assert u[k][0] <= u[k][1] and u[k][2].endswith("/" + k)
    # prodotti BIO = marchio BIO delle schede Gowan
    bio = set(yaml.safe_load(open(ROOT / "configs/difesa/gowan_programmi.yaml", encoding="utf-8"))["bio_gowan"])
    assert {p["nome"] for p in c["prodotti"] if p["bio"]} <= bio


# ------------------------------------------------------------------ motore JavaScript
def run_js(body):
    script = (f"const C=require({json.dumps(str(APP / 'consigli.js'))});"
              f"const S=require({json.dumps(str(APP / 'sprayer.js'))});"
              f"const R=require({json.dumps(str(APP / 'data' / 'mixing_rules.json'))});"
              f"const cat=require({json.dumps(str(CAT))});const ctx=C.prepara(cat);"
              "function adv(crop,re){return C.avversita(ctx,crop).find(e=>new RegExp(re,'i').test(e.nome));}"
              "function q(crop,re,fase,sit,x){const e=adv(crop,re);return Object.assign({coltura:crop,avversita:e.id,fase:fase,"
              "situazione:sit,disciplinare:true,ambito:'campo'},x||{});}"
              f"console.log(JSON.stringify((function(){{{body}}})()));")
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None or not CAT.exists(), reason="node o catalogo non disponibili")
VITE = "Vite per uva da vino"


@needs_node
def test_peronospora_vite_in_prevenzione_segue_il_programma_gowan():
    r = run_js(f"const r=C.ordina(ctx,q('{VITE}','^Peronospora','p5','prevenzione'));"
               "return {s:r.scelti.map(x=>[x.prodotto,x.punteggio,x.motivi.map(m=>m.testo)]),e:r.esclusi,f:r.fase.nome,alt:r.alternanza};")
    assert r["f"] == "Grappoli separati"
    top = r["s"][:5]
    assert all(any("posiziona in questa fase" in m for m in x[2]) for x in top)  # tutti nel programma per la fase 5
    assert [x[1] for x in r["s"]] == sorted((x[1] for x in r["s"]), reverse=True)
    assert len(r["alt"]) >= 2 and len(set(r["alt"])) == len(r["alt"])


@needs_node
def test_biologico_esclude_i_prodotti_non_bio():
    r = run_js(f"const r=C.ordina(ctx,q('{VITE}','^Peronospora','p5','prevenzione',{{bio:true}}));"
               "return {s:r.scelti.map(x=>cat.prodotti[x.p].bio),e:r.esclusi};")
    assert r["s"] and all(r["s"])
    assert any("biologica" in x["motivo"] for x in r["e"])


@needs_node
def test_alternanza_dopo_zoxamide():
    r = run_js(f"const a=C.ordina(ctx,q('{VITE}','^Peronospora','p5','prevenzione',{{ultimo:'ZOXIUM 240 SC'}}));"
               "const pen=a.scelti.filter(x=>x.motivi.some(m=>m.peso<=-3)).map(x=>x.prodotto);"
               "return {pen:pen, top:a.scelti[0].prodotto};")
    assert {"REBOOT", "ELECTIS R FLOW", "ZOXIUM 240 SC"} <= set(r["pen"])  # gruppo FRAC 22 come l'ultimo trattamento
    assert r["top"] not in r["pen"]


@needs_node
def test_giorni_alla_raccolta_e_api_in_fioritura():
    r = run_js(f"const a=C.ordina(ctx,q('{VITE}','^Peronospora','p12','prevenzione',{{giorni:20}}));"
               f"const b=C.ordina(ctx,q('{VITE}','Tignoletta','p7','attacco'));"
               "return {phi:a.scelti.map(x=>x.phi),bees:b.esclusi.map(x=>x.prodotto+': '+x.motivo)};")
    assert all(p is None or p <= 20 for p in r["phi"])
    assert any(x.startswith("GLORIAL 25 EC: in fioritura") for x in r["bees"])  # etichetta: non usare in fioritura


@needs_node
def test_disciplinare_deltametrina_solo_in_dispositivi_per_la_mosca_dell_olivo():
    r = run_js("const a=C.ordina(ctx,q('Olivo','Bactrocera','accrescimento','attacco'));"
               "return a.esclusi.map(x=>x.prodotto+': '+x.motivo);")
    assert any(x.startswith("GLORIAL 25 EC") and "attract and kill" in x for x in r)


@needs_node
def test_ricetta_dose_a_ettaro_rame_mago_e_botte():
    r = run_js(f"const qq=q('{VITE}','^Peronospora','p5','prevenzione');const a=C.ordina(ctx,qq);"
               "const s=a.scelti.find(x=>x.prodotto==='AIRONE LIQUIDO');"
               "const rc=C.ricetta(ctx,qq,s,{ettari:2,acqua:400,botte:600});"
               "const t=S.computeTank(600,rc.botte,400,null,null,R);"
               "return {d:rc.dose,cu:rc.rame_kg_ha,coad:rc.coadiuvanti.map(c=>[c.nome,c.per_ha,c.botte]),"
               "t:t.products.map(p=>[p.name,p.amount]),err:t.errors,nutri:rc.nutrizionali.map(n=>[n.nome,!!n.separato])};")
    # dose minima a ettaro (2 l/ha) con 400 l/ha di acqua: 500 ml/hl, 4 l per 2 ha, 3 l in 600 litri
    assert r["d"]["per_ha"] == {"valore": 2, "unita": "l"} and r["d"]["per_hl"] == {"valore": 500, "unita": "ml"}
    assert r["d"]["totale"] == {"valore": 4, "unita": "l"} and r["d"]["botte"] == {"valore": 3, "unita": "l"}
    assert r["cu"] == pytest.approx(2 * 272 / 1000)  # 2 l x 272 g/l di rame metallo
    assert r["coad"][0][0] == "MAGO" and r["coad"][0][1] == {"valore": 200, "unita": "ml"}  # 50 ml/hl x 4 hl
    assert r["t"] == [["AIRONE LIQUIDO", {"value": 3.0, "unit": "l"}], ["MAGO", {"value": 300.0, "unit": "ml"}]] and not r["err"]
    assert ["TAMARACK", True] in r["nutri"]  # mai in miscela con il rame fuori dall'olivo (scheda Gowan)


@needs_node
def test_tamarack_non_su_susino():
    r = run_js("const e=C.avversita(ctx,'Susino').find(x=>x.u.length);"
               "const qq={coltura:'Susino',avversita:e.id,fase:'accrescimento',situazione:'prevenzione',ambito:'campo'};"
               "const a=C.ordina(ctx,qq);if(!a.scelti.length)return [];"
               "return C.ricetta(ctx,qq,a.scelti[0],{acqua:1000}).nutrizionali.map(n=>n.nome);")
    assert "TAMARACK" not in r
