"""Calendario dei trattamenti (app/calendario.js): limiti di etichetta e Disciplinare, carenze, rame, alternanza."""
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CAT = APP / "data" / "catalogo.json"
needs_node = pytest.mark.skipif(shutil.which("node") is None or not CAT.exists(), reason="node o catalogo non disponibili")
VITE = "Vite per uva da vino"


def run_js(body):
    script = (f"const C=require({json.dumps(str(APP / 'consigli.js'))});const K=require({json.dumps(str(APP / 'calendario.js'))});"
              f"const cat=require({json.dumps(str(CAT))});const ctx=C.prepara(cat);"
              "function adv(crop,re){return C.avversita(ctx,crop).find(e=>new RegExp(re,'i').test(e.nome));}"
              f"console.log(JSON.stringify((function(){{{body}}})()));")
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def piano(crop, re, fase, extra=""):
    return run_js(f"const e=adv('{crop}','{re}');return K.piano(ctx,Object.assign({{coltura:'{crop}',avversita:e.id,fase:'{fase}',"
                  f"situazione:'prevenzione',ambito:'campo',disciplinare:true,inizio:'2026-04-20',raccolta:'2026-09-15',pressione:'media',acqua:800}},{{{extra}}}));")


def gg(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


@needs_node
def test_peronospora_vite_rispetta_carenze_limiti_e_rame():
    r = piano(VITE, "^Peronospora", "p2")
    assert not r.get("errore") and len(r["interventi"]) >= 8
    for x in r["interventi"]:
        if x["phi"] is not None:
            assert gg(x["data"], "2026-09-15") >= x["phi"], x  # intervallo di sicurezza prima della raccolta
        if x["uso_max"] is not None:
            assert x["uso_n"] <= x["uso_max"], x
    for p in r["prodotti"]:
        if p["max"] is not None:
            assert p["usati"] <= p["max"]
    assert r["rame_kg_ha"] <= r["rame_max"] + 1e-6
    # in fioritura non solo rame: entrano i prodotti dei programmi per fase
    fior = [x for x in r["interventi"] if 60 <= x["bbch_stimato"] <= 75]
    assert any("FRAC M01" not in x["gruppi"] for x in fior)


@needs_node
def test_alternanza_dei_gruppi_di_resistenza():
    r = piano(VITE, "^Peronospora", "p2")
    prev = None
    for x in r["interventi"]:
        g = {c for c in x["gruppi"] if not c.startswith("FRAC M") and not c.startswith("FRAC BM")}
        if prev is not None and g & prev:
            assert x["alternanza"], x  # stesso gruppo di seguito solo se segnalato
        prev = g


@needs_node
def test_limite_comune_del_disciplinare():
    # oidio della vite: i limiti per gruppo (es. IBE) sono contati insieme per tutti i prodotti del gruppo
    r = piano(VITE, "^Oidio", "p2")
    for x in r["interventi"]:
        for t in x["limiti_comuni"]:
            usati, su = t.rsplit("(", 1)[1].rstrip(")").split(" su ")
            assert int(usati) <= int(su), t


@needs_node
def test_rame_massimo_scelto_dall_utente():
    r = piano(VITE, "^Peronospora", "p2", "rame_max:1.5")
    assert r["rame_kg_ha"] <= 1.5 + 1e-6


@needs_node
def test_senza_prodotti_gowan_mostra_il_disciplinare():
    r = run_js("const e=adv('Olivo','Mosca');return K.piano(ctx,{coltura:'Olivo',avversita:e.id,fase:'accrescimento',situazione:'primi_sintomi',"
               "disciplinare:true,inizio:'2026-07-01',raccolta:'2026-11-01'});")
    assert r["errore"] and r["disciplinare"] and r["disciplinare"][0]["sostanze"]


@needs_node
def test_carenza_di_ferro_dalla_scheda_gowan():
    r = run_js(f"const s=require({json.dumps(str(APP / 'data' / 'carenze.json'))});"
               "return K.pianoCarenza(s,{carenza:'carenza_di_ferro',inizio:'2026-05-01',raccolta:'2026-09-01',modo:'curativo'});")
    assert [x["data"] for x in r["interventi"]] == ["2026-05-01", "2026-05-08", "2026-05-15"]
    assert "SPRINFER" in r["interventi"][0]["prodotto"] and r["interventi"][0]["dose"]


@needs_node
def test_file_ics_per_il_calendario_del_telefono():
    r = run_js("return K.ics('Prova',[{n:1,data:'2026-05-01',prodotto:'X',phi:7}]);")
    assert r.startswith("BEGIN:VCALENDAR") and "DTSTART;VALUE=DATE:20260501" in r and r.rstrip().endswith("END:VCALENDAR")
