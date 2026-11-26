"""Foto delle schede delle avversità del Servizio fitosanitario della Regione Emilia-Romagna.

Le schede sono scritte e illustrate dai tecnici del servizio: l'etichetta (la scheda in cui sta la foto) è
affidabile. Si legge l'elenco con l'interfaccia dati del sito (Plone REST, "++api++") e si scaricano le
foto delle schede che corrispondono a classi dei lettori. Si escludono cartelle e foto di mappe,
lanci di insetti utili, trappole e difesa. Foto protette da diritto d'autore della Regione: solo
addestramento a fini di ricerca (art. 70-ter L. 633/1941), mai nel quiz. Tutte nell'addestramento.

Uso: python scripts/import_emiliaromagna.py
"""
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://agricoltura.regione.emilia-romagna.it"
OUT = ROOT / "data" / "external" / "emiliaromagna"
IMG = ROOT / "data" / "external" / "images" / "emiliaromagna"
# scheda -> (lettore, classe, coltura)
SCHEDE = {
    "colpo-di-fuoco": ("disease", "inat:erwinia_amylovora", ""),
    "batteriosi-psa": ("disease", "inat:pseudomonas_syringae", "actinidia_chinensis"),
    "peronospora-patata-pomodoro": ("disease", "tomato_late_blight", ""),
    "sharka": ("disease", "peach_plum_pox", ""),
    "cancro-della-corteccia-del-castagno": ("disease", "bw:cryphonectria_parasitica", ""),
    "peronospora-delle-liliacee": ("disease", "bw:peronospora_destructor", ""),
    "peronospora-della-lattuga": ("disease", "lettuce_downy_mildew", "lactuca_sativa"),
    "monilia-fructicola": ("disease", "apple_brown_rot", ""),
    "xylella": ("disease", "inat:xylella_fastidiosa", ""),
    "cancro-batterico-o-maculatura-batterica-delle-drupacee": ("disease", "peach_bacterial_spot", ""),
    "cimice-asiatica": ("pest", "inat:halyomorpha_halys", ""),
    "aleurocanthus-spiniferus": ("pest", "inat:aleurocanthus_spiniferus", ""),
    "moscerino-della-frutta": ("pest", "inat:drosophila_suzukii", ""),
    "capnodio": ("pest", "inat:capnodis_tenebrionis", ""),
    "tignoletta-della-vite": ("pest", "inat:lobesia_botrana", ""),
    "tignola-del-pomodoro": ("pest", "inat:phthorimaea_absoluta", ""),
    "tignola-orientale-del-pesco": ("pest", "inat:grapholita_molesta", ""),
    "carpocapsa_scheda": ("pest", "inat:cydia_pomonella", ""),
    "bactrocera-dorsalis": ("pest", "ip102_085", ""),
}
SCARTA = re.compile(r"(?i)mapp|lanci|trappol|difesa|grafic|logo|non-confondere|diffusione|banner|1920x200|schema|tabella")


def main():
    items = json.load(open(OUT / "elenco.json", encoding="utf-8"))
    man = []
    for x in items:
        if x["@type"] != "Image" or "/avversita-per-nome/" not in x["@id"]:
            continue
        rel = x["@id"].split("/avversita-per-nome/")[1]
        scheda = rel.split("/")[0]
        if scheda not in SCHEDE or SCARTA.search(rel + " " + (x.get("title") or "")):
            continue
        head, cls, crop = SCHEDE[scheda]
        f = IMG / scheda / re.sub(r"[^A-Za-z0-9._-]+", "_", rel.split("/")[-1])[:100]
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            f = f.with_suffix(".jpg")
        if not f.exists():
            try:
                time.sleep(0.3)
                req = urllib.request.Request(x["@id"] + "/@@images/image/large", headers={"User-Agent": "PlantCare/1.0 (progetto accademico)"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
            except Exception as ex:
                print("non scaricata", x["@id"], ex, flush=True)
                continue
        man.append({"path": str(f.relative_to(ROOT / "data")), "testa": head, "classe": cls, "coltura": crop,
                    "titolo": x.get("title", ""), "pagina": x["@id"], "scheda": scheda})
    json.dump(man, open(OUT / "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    for k, v in Counter(m["scheda"] for m in man).most_common():
        print(f"{v:4d} {k}")
    print("FATTO", len(man))


if __name__ == "__main__":
    main()
