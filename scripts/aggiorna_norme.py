"""Aggiorna le norme usate dall'app e scrive un riepilogo delle novità da controllare.

- Disciplinare (--disciplinare): elenco dei PDF pubblicati da ARSAC (sito WordPress, /wp-json/wp/v2/media).
  Se c'è un documento "difesa e diserbo" più recente di quelli in configs/difesa, lo scarica, lo legge con
  scripts/import_disciplinare.py e lo salva come nuova versione (configs/difesa/disciplinare_calabria_*.json):
  l'app usa sempre la più recente e segnala le sostanze uscite rispetto alle versioni precedenti.
- Sostanze attive UE (--ue): banca dati dei pesticidi della Commissione europea (API pubblica): stato di
  approvazione, scadenza, candidate alla sostituzione, basso rischio -> configs/difesa/sostanze_ue.json.
- Gowan (--gowan): pagine prodotto ed etichette dal sito del produttore -> configs/difesa/gowan_italia.json.
- App (--app): ricostruisce app/data/difesa.json e app/data/catalogo.json senza il modello.

Senza opzioni fa --disciplinare --ue --app. Il riepilogo (--riepilogo FILE, in Markdown) elenca le novità:
il flusso di GitHub Actions (.github/workflows/aggiorna-norme.yml) lo usa come testo della pull request, che
una persona controlla prima di pubblicare. Le richieste rispettano i siti: poche e distanziate.

Uso: python scripts/aggiorna_norme.py [--disciplinare] [--ue] [--gowan] [--app] [--riepilogo riepilogo.md]
"""
import argparse
import html as H
import json
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from plantcare import difesa as df  # noqa: E402

DIFESA = ROOT / "configs" / "difesa"
HEAD = {"User-Agent": "PlantCare/1.0 (progetto accademico; aggiornamento norme)"}
ARSAC_MEDIA = "https://www.arsacweb.it/wp-json/wp/v2/media?search={q}&per_page=100&orderby=date&_fields=id,date,title,source_url,mime_type"
UE_API = "https://api.datalake.sante.service.ec.europa.eu/sante/pesticides/active-substances?format=json&api-version=v3.0"
UE_PAGINA = "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/start/screen/active-substances"


def get(url, tries=3, pausa=1.0):
    for k in range(tries):
        try:
            time.sleep(pausa)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=180) as r:
                return r.read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(10 * (k + 1))


# --------------------------------------------------------------------------- Disciplinare
def cerca_disciplinari() -> list[dict]:
    """PDF dei Disciplinari di difesa e diserbo pubblicati da ARSAC, dal più recente."""
    out, seen = [], set()
    for q in ("disciplinari", "difesa diserbo"):
        try:
            items = json.loads(get(ARSAC_MEDIA.format(q=urllib.parse.quote(q))))
        except Exception as ex:
            print("ARSAC non raggiungibile:", ex)
            continue
        for m in items:
            url = m.get("source_url") or ""
            title = H.unescape((m.get("title") or {}).get("rendered", ""))
            if m.get("mime_type") != "application/pdf" or url in seen:
                continue
            low = (url + " " + title).lower()
            if "disciplinar" in low and "difesa" in low and "delibera" not in low:
                seen.add(url)
                anno = re.findall(r"20\d\d", url.rsplit("/", 1)[-1]) or re.findall(r"20\d\d", title) or [m["date"][:4]]
                out.append({"url": url, "titolo": title, "pubblicato": m["date"][:10], "anno": int(anno[-1]),
                            "aggiornamento": bool(re.search(r"(?i)aggiornat|allegato[-_ ]?b", low))})
    return sorted(out, key=lambda x: x["pubblicato"], reverse=True)


def aggiorna_disciplinare(note: list[str]) -> bool:
    import import_disciplinare as imp
    noti = {}
    for f in df.disciplinari():
        d = json.load(open(f, encoding="utf-8"))
        noti[d["url"]] = d
    ultimo = df.load_disciplinare()
    nuovi = [x for x in cerca_disciplinari() if x["url"] not in noti
             and (x["anno"], x["pubblicato"]) > (ultimo["anno"], ultimo.get("pubblicato") or "")]
    if not nuovi:
        note.append(f"- Disciplinare Calabria: nessuna nuova versione (in uso: {df.etichetta_versione(ultimo)}).")
        return False
    x = nuovi[0]
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "disciplinare.pdf"
        pdf.write_bytes(get(x["url"]))
        rows = imp.leggi(pdf)
    if len(rows) < 200:  # lettura fallita (impaginazione cambiata): meglio non sostituire il Disciplinare
        note.append(f"- ⚠ Nuovo Disciplinare trovato ma letto male ({len(rows)} righe): {x['url']}. Da importare a mano.")
        return False
    suff = f"_{x['pubblicato'][5:7]}" if any(json.load(open(f, encoding='utf-8'))["anno"] == x["anno"] for f in df.disciplinari()) else ""
    out = DIFESA / f"disciplinare_calabria_{x['anno']}{suff}.json"
    titolo = (f"Disciplinari di produzione integrata {x['anno']} - Difesa e controllo infestanti, Regione Calabria"
              + (f" (versione aggiornata pubblicata da ARSAC il {x['pubblicato'][8:10]}/{x['pubblicato'][5:7]}/{x['pubblicato'][:4]})"
                 if suff or x["aggiornamento"] else ""))
    imp.salva(rows, x["anno"], x["url"], out, titolo, x["pubblicato"], bool(suff) or x["aggiornamento"])
    nuovo = df.load_disciplinare(path=out)
    note.append(f"- **Nuovo Disciplinare Calabria** ({df.etichetta_versione(nuovo)}): [{x['titolo'] or out.name}]({x['url']}), "
                f"{len(rows)} righe lette -> `{out.relative_to(ROOT)}`.")
    note.extend(differenze_disciplinare(ultimo, nuovo))
    return True


def differenze_disciplinare(a: dict, b: dict, massimo: int = 60) -> list[str]:
    """Sostanze aggiunte e tolte per coltura e avversità tra due versioni."""
    key = lambda r: (r["coltura"], re.sub(r"\s+", " ", r["avversita"].lower()))
    A, B = {key(r): r for r in a["righe"]}, {key(r): r for r in b["righe"]}
    out = []
    for k in sorted(set(A) & set(B)):
        sa = {s["sostanza"].strip() for s in A[k]["sostanze"]}
        sb = {s["sostanza"].strip() for s in B[k]["sostanze"]}
        if sa != sb:
            plus, minus = sorted(sb - sa), sorted(sa - sb)
            out.append(f"  - {k[0].capitalize()}, {B[k]['avversita']}: " + "; ".join(
                ([f"aggiunte {', '.join(plus)}"] if plus else []) + ([f"tolte {', '.join(minus)}"] if minus else [])))
    for k in sorted(set(B) - set(A)):
        out.append(f"  - nuova avversità: {k[0].capitalize()}, {B[k]['avversita']}")
    if len(out) > massimo:
        out = out[:massimo] + [f"  - ... e altre {len(out) - massimo} differenze"]
    return out


# --------------------------------------------------------------------------- UE
def regolamenti(htmltext: str | None) -> str:
    return "; ".join(H.unescape(t).strip() for t in re.findall(r">([^<>]{3,60})</a>", htmltext or ""))


def aggiorna_ue(note: list[str]) -> bool:
    url, rows, pagine = UE_API, [], 0
    while url and pagine < 200:
        d = json.loads(get(url, pausa=0.5))
        rows += d.get("value") or []
        url = d.get("nextLink")
        pagine += 1
    if len(rows) < 1000:
        note.append(f"- ⚠ Banca dati UE: risposta incompleta ({len(rows)} righe), stato delle sostanze non aggiornato.")
        return False
    sost = {}
    for r in rows:
        n = (r.get("substance_name") or "").strip()
        if not n:
            continue
        e = {"stato": r.get("substance_status"), "approvazione": r.get("approval_date"), "scadenza": r.get("expiry_date"),
             "candidata_sostituzione": r.get("candidate_for_substitution") == "Yes",
             "basso_rischio": r.get("low_risk_active_substance") == "Yes", "base": r.get("basic_substance") == "Yes",
             "regolamenti": regolamenti(r.get("legislations_actives")), "id": r.get("substance_id")}
        sost.setdefault(n, e)
    p = DIFESA / "sostanze_ue.json"
    old = json.load(open(p, encoding="utf-8")).get("sostanze", {}) if p.exists() else {}
    json.dump({"fonte": "EU Pesticides Database, sostanze attive (Commissione europea, DG SANTE)", "url": UE_PAGINA,
               "scaricato": str(date.today()), "sostanze": dict(sorted(sost.items()))},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    usate = sostanze_usate()
    cambi = []
    for n in sorted(usate):
        a, b = old.get(n), sost.get(n)
        if not b:
            cambi.append(f"  - {n}: non più nella banca dati UE")
        elif a and (a.get("stato"), a.get("scadenza")) != (b.get("stato"), b.get("scadenza")):
            cambi.append(f"  - {n}: {a.get('stato')} (scad. {a.get('scadenza')}) -> **{b.get('stato')}** (scad. {b.get('scadenza')})")
    non_app = sorted(n for n in usate if (sost.get(n) or {}).get("stato") == "Not approved")
    note.append(f"- Banca dati UE: {len(sost)} sostanze attive scaricate; {len(cambi)} cambiamenti per le sostanze usate dall'app.")
    note.extend(cambi)
    if non_app:
        note.append("  - ⚠ Sostanze del Disciplinare o dei prodotti Gowan **non approvate** nell'UE: " + ", ".join(non_app))
    return bool(cambi) or not old


def sostanze_usate() -> set[str]:
    """Nomi UE delle sostanze dei prodotti Gowan e del Disciplinare in vigore."""
    ue = df.load_ue()
    out = set()
    reg = df._load_yaml(DIFESA / "sostanze.yaml").get("sostanze") or {}
    out |= {v["ue"] for v in reg.values()}
    for r in df.load_disciplinare()["righe"]:
        for s in r["sostanze"]:
            st = df.stato_ue(s["sostanza"], ue)
            if st:
                out.add(st["nome"])
    return out


# --------------------------------------------------------------------------- Gowan
def aggiorna_gowan(note: list[str]) -> bool:
    import import_gowan as ig
    p = DIFESA / "gowan_italia.json"
    old = json.load(open(p, encoding="utf-8")) if p.exists() else {"prodotti": []}
    with tempfile.TemporaryDirectory() as tmp:
        pagine, etichette = ig.scarica(tmp)
        new = ig.importa(pagine, etichette, p)
    a = {x["prodotto"]: x for x in old["prodotti"]}
    b = {x["prodotto"]: x for x in new["prodotti"]}
    righe = [f"  - nuovo prodotto: {n}" for n in sorted(set(b) - set(a))]
    righe += [f"  - prodotto non più sul sito: {n}" for n in sorted(set(a) - set(b))]
    for n in sorted(set(a) & set(b)):
        if a[n].get("etichetta_validita") != b[n].get("etichetta_validita") and b[n].get("etichetta_validita"):
            righe.append(f"  - {n}: nuova etichetta ({b[n]['etichetta_validita']})")
        if len(a[n].get("usi", [])) != len(b[n].get("usi", [])):
            righe.append(f"  - {n}: usi registrati {len(a[n].get('usi', []))} -> {len(b[n].get('usi', []))}")
    strip = lambda d: json.dumps({k: v for k, v in d.items() if k != "consultato"}, sort_keys=True, ensure_ascii=False)
    altro = strip(old) != strip(new)
    if altro and not righe:
        righe.append("  - modifiche a dosi, note o intervalli di sicurezza di prodotti già presenti (vedi il confronto dei file)")
    note.append(f"- Gowan Italia: {len(b)} prodotti letti; {len(righe)} cambiamenti.")
    note.extend(righe)
    return altro


# --------------------------------------------------------------------------- app
def aggiorna_app():
    from plantcare import consigli
    app = ROOT / "app" / "data"
    readers = json.load(open(app / "readers.json", encoding="utf-8"))
    cp = DIFESA / "colture_per_classe.json"
    crops_of = json.load(open(cp, encoding="utf-8")) if cp.exists() else None
    json.dump(df.build_app_data(readers, crops_of), open(app / "difesa.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(consigli.build(readers), open(app / "catalogo.json", "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    print("app/data/difesa.json e app/data/catalogo.json ricostruiti")


def main():
    ap = argparse.ArgumentParser()
    for o in ("disciplinare", "ue", "gowan", "app"):
        ap.add_argument(f"--{o}", action="store_true")
    ap.add_argument("--riepilogo", default=None)
    ap.add_argument("--esito", default=None, help="file in cui scrivere cambiato=true|false (per GitHub Actions)")
    args = ap.parse_args()
    if not (args.disciplinare or args.ue or args.gowan or args.app):
        args.disciplinare = args.ue = args.app = True
    note = [f"Controllo del {date.today().strftime('%d/%m/%Y')}.", ""]
    cambiato = False
    if args.disciplinare:
        cambiato |= aggiorna_disciplinare(note)
    if args.ue:
        cambiato |= aggiorna_ue(note)
    if args.gowan:
        cambiato |= aggiorna_gowan(note)
    sp = DIFESA / "norme_stato.json"
    prima = json.load(open(sp, encoding="utf-8")) if sp.exists() else {}
    controllo = args.disciplinare or args.ue or args.gowan
    stato = {"controllato": str(date.today()) if controllo else prima.get("controllato"), "disciplinare": {}, "ue": {}, "gowan": {}}
    d = df.load_disciplinare()
    stato["disciplinare"] = {"versione": df.etichetta_versione(d), "url": d["url"], "file": d["file"]}
    ue = df.load_ue()
    stato["ue"] = {"scaricato": ue.get("scaricato"), "sostanze": len(ue.get("sostanze") or {})}
    stato["gowan"] = {"consultato": df.load_gowan().get("consultato")}
    json.dump(stato, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if args.app:
        aggiorna_app()
    note += ["", "Prima di unire questa proposta: controllare le differenze del Disciplinare sul PDF ufficiale e lo",
             "stato delle sostanze nella banca dati UE; l'etichetta autorizzata del prodotto prevale sempre."]
    testo = "\n".join(note)
    print(testo)
    if args.riepilogo:
        Path(args.riepilogo).write_text(testo + "\n", encoding="utf-8")
    print("novità trovate" if cambiato else "nessuna novità")
    if args.esito:
        with open(args.esito, "a", encoding="utf-8") as f:
            f.write(f"cambiato={'true' if cambiato else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
