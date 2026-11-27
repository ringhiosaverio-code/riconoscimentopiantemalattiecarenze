"""Altre foto per il quiz delle specie del Sud con poche foto su iNaturalist.

Fonti con uso consentito e autore citato sotto ogni foto:
- Bugwood Images (Università della Georgia, ipmimages.org): soggetti identificati da specialisti, licenza
  Creative Commons BY-NC 3.0 US salvo diversa indicazione sul sito;
- EPPO Global Database: «All photos included on this page can only be used for educational purposes»;
- figure di articoli ad accesso aperto con licenza CC BY 4.0, ritagliate a mano e verificate a vista
  (tripide dell'olivo: Vono et al., Insects 2020, Università Mediterranea; psilla del pero: Koßmann et al. 2025;
  lebbra dell'olivo: Moral et al., J. Fungi 2021, e Kolainis et al., PLoS ONE 2020).
Le foto vanno nella stessa classe del quiz delle foto di iNaturalist (etichetta "inat:<specie>"), così le
domande su queste specie diventano più numerose e varie. Si tengono solo foto di campo (sintomi, adulti,
forme giovanili, danni), non colture in piastra, microscopio o disegni.

Uso: python scripts/import_quiz_extra.py [--max 40]
"""
import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "quiz_extra"
IMG = ROOT / "data" / "external" / "images" / "quiz_extra"
HEAD = {"User-Agent": "PlantCare-quiz/1.0 (progetto accademico)"}
BUGWOOD = "https://api.bugwoodcloud.org/v2"
SCARTA = re.compile(r"(?i)cultur|spore|micro|conidi|mycel|slide|drawing|illustrat|diagram|map|museum|specimen|"
                    r"sem\b|section|asci|hyph|chart|lab|isolat|petri|herbarium|label|logo|trap|people|equipment")

# etichetta del quiz, nome, gruppo, testa, soggetti Bugwood (nomi scientifici), codice EPPO ed etichette delle foto EPPO
TARGETS = [
    {"label": "inat:liothrips_oleae", "head": "pest", "nome": "Tripide dell'olivo", "gruppo": "olivo", "taxon": "Liothrips oleae",
     "bugwood": ["Liothrips oleae"]},
    {"label": "inat:jacobiasca_lybica", "head": "pest", "nome": "Cicalina africana della vite", "gruppo": "vite",
     "taxon": "Jacobiasca lybica", "bugwood": ["Jacobiasca lybica"]},
    {"label": "inat:elsinoe_ampelina", "head": "disease", "nome": "Antracnosi della vite", "gruppo": "vite", "taxon": "Elsinoe ampelina",
     "causa": "fungo", "bugwood": ["Elsinoe ampelina"]},
    {"label": "inat:capnodium", "head": "disease", "nome": "Fumaggine", "gruppo": "agrumi", "taxon": "Capnodium", "causa": "fungo",
     "bugwood": ["Capnodium citri", "Capnodium citricola", "Fumago vagans", "Scorias spongiosa"], "bugwood_id": [10771]},
    {"label": "inat:cacopsylla_pyri", "head": "pest", "nome": "Psilla del pero", "gruppo": "melo", "taxon": "Cacopsylla pyri",
     "bugwood": ["Cacopsylla pyri"], "eppo": "PSYLPI", "eppo_tag": r"tag-(adult|larva|nymph|egg|damage)"},
    {"label": "inat:panonychus_citri", "head": "pest", "nome": "Ragnetto rosso degli agrumi", "gruppo": "agrumi",
     "taxon": "Panonychus citri", "bugwood": ["Panonychus citri"]},
    {"label": "inat:dialeurodes_citri", "head": "pest", "nome": "Aleurodide degli agrumi", "gruppo": "agrumi", "taxon": "Dialeurodes citri",
     "bugwood": ["Dialeurodes citri"], "eppo": "DIALCI", "eppo_tag": r"tag-(adult|pupa|larva|nymph|egg)"},
    {"label": "inat:venturia_pyrina", "head": "disease", "nome": "Ticchiolatura del pero", "gruppo": "melo", "taxon": "Venturia pyrina",
     "causa": "fungo", "bugwood": ["Venturia pyrina"], "eppo": "VENTPI", "eppo_tag": r"tag-symptoms"},
    {"label": "inat:alternaria_solani", "head": "disease", "nome": "Alternariosi del pomodoro", "gruppo": "pomodoro",
     "taxon": "Alternaria solani", "causa": "fungo", "bugwood": ["Alternaria solani"], "eppo": "ALTESO", "eppo_tag": r"tag-symptoms"},
    {"label": "inat:phloeotribus_scarabaeoides", "head": "pest", "nome": "Fleotribo dell'olivo", "gruppo": "olivo",
     "taxon": "Phloeotribus scarabaeoides", "bugwood": ["Phloeotribus scarabaeoides"]},
    # lebbra dell'olivo: nessuna foto aperta su iNaturalist, Bugwood o EPPO; solo figure di articoli CC BY
    # (Moral et al., J. Fungi 2021; Kolainis et al., PLoS ONE 2020) ritagliate a mano
    {"label": "inat:colletotrichum", "head": "disease", "nome": "Lebbra dell'olivo (antracnosi, Colletotrichum)",
     "gruppo": "olivo", "taxon": "Colletotrichum", "causa": "fungo", "bugwood": []},
    # mal secco: le foto EPPO sono già nel quiz (scripts/import_eppo_quiz.py); qui si aggiungono quelle di Bugwood
    {"label": "eppo:DEUTTR", "head": "disease", "nome": "Mal secco degli agrumi (Plenodomus tracheiphilus)", "gruppo": "agrumi",
     "taxon": "Plenodomus tracheiphilus", "causa": "fungo", "bugwood": ["Plenodomus tracheiphilus"]},
]


def get(url, pause=0.5):
    for k in range(4):
        try:
            time.sleep(pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=60) as r:
                return r.read()
        except Exception:
            if k == 3:
                raise
            time.sleep(5 * (k + 1))


def bugwood(t, n):
    ids = list(t.get("bugwood_id", []))
    for sci in t.get("bugwood", []):
        g, s = sci.split()[0], (sci.split() + [""])[1]
        for x in json.loads(get(f"{BUGWOOD}/subject?search={urllib.parse.quote(sci)}")):
            if x["namepart1"].lower() == g.lower() and x["namepart2"].lower() == s.lower():
                ids.append(x["subjectid"])
    out, page = [], 1
    while ids and len(out) < n:
        d = json.loads(get(f"{BUGWOOD}/image?subject={','.join(map(str, sorted(set(ids))))}&page={page}&pagesize=50"))
        for im in d.get("data", []):
            if SCARTA.search((im.get("descriptorname") or "") + " " + (im.get("description") or "") + " " + (im.get("imageview") or "")):
                continue
            num = im["imagenumber"]
            out.append({"url": f"https://bugwoodcloud.org/images/768x512/{num}.jpg", "id": f"bw{num}",
                        "credit": f"{(im.get('photographer') or '').strip()}, Bugwood.org (CC BY-NC 3.0 US)",
                        "obs": f"https://www.ipmimages.org/browse/detail.cfm?imgnum={num}", "fonte": "bugwood"})
            if len(out) >= n:
                break
        if not d.get("data") or page * 50 >= d.get("totalrows", 0):
            break
        page += 1
    return out


def eppo(t, n):
    if not t.get("eppo"):
        return []
    page = get(f"https://gd.eppo.int/taxon/{t['eppo']}/photos", pause=1.0).decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r'<div class="element ([^"]*)">\s*<a href="(/media/data/taxon/[^"]+/1024x0/(\d+)\.jpg)".*?'
                         r'<div class="pcap">(.*?)</div>', page, re.S):
        tags, url, pid, cap = m.groups()
        if not re.search(t["eppo_tag"], tags):
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cap))).strip()
        court = re.search(r"Courtesy:\s*(.+)$", text)
        out.append({"url": "https://gd.eppo.int" + url, "id": f"eppo{pid}",
                    "credit": f"Courtesy: {court.group(1).strip() if court else 'EPPO'}, EPPO Global Database (uso didattico)",
                    "obs": f"https://gd.eppo.int/taxon/{t['eppo']}/photos", "fonte": "eppo"})
        if len(out) >= n:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    prima = json.load(open(OUT / "manifest.json", encoding="utf-8")) if (OUT / "manifest.json").exists() else {}
    man = {}
    for t in TARGETS:
        scartate = set(prima.get("_scartate", []))  # tolte dopo la verifica a vista
        photos = [p for p in eppo(t, args.max) + bugwood(t, args.max) if p["id"] not in scartate]
        saved = []
        for p in photos[:args.max]:
            f = IMG / t["label"].split(":")[1] / f"{p['id']}.jpg"
            if not f.exists():
                try:
                    data = get(p["url"], pause=0.3)
                    if data[:3] != b"\xff\xd8\xff":
                        continue
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(data)
                except Exception as ex:
                    print("  non scaricata", p["url"], ex, flush=True)
                    continue
            saved.append({**{k: v for k, v in p.items() if k != "url"}, "path": str(f.relative_to(ROOT / "data"))})
        # foto ritagliate a mano da articoli ad accesso aperto (CC BY): si conservano
        saved += [p for p in (prima.get(t["label"]) or {}).get("foto", []) if p.get("fonte") == "articolo"]
        man[t["label"]] = {**{k: v for k, v in t.items() if k not in ("bugwood", "bugwood_id", "eppo_tag")}, "foto": saved}
        print(f"{t['taxon']:30s} {len(saved):3d} foto (EPPO {sum(p['fonte'] == 'eppo' for p in saved)}, Bugwood "
              f"{sum(p['fonte'] == 'bugwood' for p in saved)})", flush=True)
    man["_scartate"] = sorted(prima.get("_scartate", []))
    json.dump(man, open(OUT / "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
