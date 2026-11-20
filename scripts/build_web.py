"""Costruisce l'app statica (GitHub Pages) in app/: dati JSON, modello ONNX, motore, foto del quiz.

Uso:
    PYTHONPATH=src python scripts/build_web.py --model <file .onnx quantizzato> --ort-dist <cartella dist di onnxruntime-web>

L'app gira interamente nel browser: la foto non lascia il dispositivo.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

import torch
import yaml
from PIL import Image

from plantcare.causes import cause_of, load_causes
from plantcare.kb import KnowledgeBase
from plantcare.quiz import DEFICIENCY_NAMES, display_name
from plantcare.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CKPT = ROOT / "models" / "readers_vit_small_patch14_dinov2+efficientnet_b0"
HEADS = ["plant", "disease", "deficiency"]
QUIZ_SOURCES = {  # solo fonti con licenza che consente la ripubblicazione con attribuzione
    "plantdoc": "PlantDoc (Singh et al. 2020), CC BY 4.0",
    "agml_lemon": "Project-AgML, lemon leaf disease, CC BY 4.0",
    "agml_eggplant": "Project-AgML, eggplant disease (Howlader et al.), CC BY 4.0",
    "agml_tom2024": "Project-AgML, TOM2024, CC BY 4.0",
    "agml_onion": "Project-AgML, COLD onion (Aishwarya e Reddy), CC BY 4.0",
    "agml_chili": "Project-AgML, COLD chili (Aishwarya e Reddy), CC BY 4.0",
    "agml_grape": "Project-AgML, grape leaf disease, CC BY 4.0",
    "agml_banana": "Project-AgML, banana leaf disease, CC BY 4.0",
    "agml_tuta": "Project-AgML, Tuta absoluta (Shehu et al. 2025), MIT",
    "agml_potato": "Project-AgML, potato leaf disease, CC BY 4.0",
    "agml_cauliflower": "Project-AgML, cauliflower leaf disease, CC BY 4.0",
    "agml_appleleaf9": "AppleLeaf9 (Yang et al. 2022), via Project-AgML, CC BY 4.0",
    "agml_citrusuat": "CitrusUAT (Gómez-Flores et al. 2024), via Project-AgML, CC BY 4.0",
    "agml_citrusfruit": "Citrus fruits and leaves (Rauf et al. 2019), via Project-AgML, CC BY 4.0",
    "agml_plum": "Plum leaf and fruit (Nayeem et al. 2025), via Project-AgML, CC BY 4.0",
    "agml_pomegranate": "Pomegranate disease (Mohammed et al. 2025), via Project-AgML, CC BY 4.0",
    "agml_fig": "Fig leaves (Hafi et al. 2024), via Project-AgML, CC BY 4.0",
}
QUIZ_PER_CLASS = 30  # foto per classe, da tutti gli split e alternando le fonti
QUIZ_PER_PEST = 20
QUIZ_PER_PEST_OTHER = 6  # insetti di IP102 non citati nelle norme di difesa della Calabria: poche foto
# IP102 (Wu et al. 2019): concesso solo per uso accademico; incluso su conferma dell'uso accademico del progetto
QUIZ_SOURCES_ACADEMIC = {"ip102": "IP102 (Wu et al. 2019, CVPR): solo per uso accademico"}
# gruppi di colture di IP102 (indici 1-based delle classi), come nell'articolo originale
IP102_GROUPS = [(1, 14, "riso"), (15, 27, "mais"), (28, 36, "frumento"), (37, 44, "barbabietola"),
                (45, 57, "erba medica"), (58, 73, "vite"), (74, 92, "agrumi"), (93, 102, "mango")]
QUIZ_SIDE = 288


GENERIC_CLASSES = {"healthy", "disturbo_nutrizionale"}  # non legate a una coltura


def load_yaml(p: Path) -> dict:
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def ip102_group(label: str) -> str:
    k = int(label.split("_")[-1])
    return next(g for a, b, g in IP102_GROUPS if a <= k <= b)


def build_quiz(ck, heads, names: dict) -> None:
    """Foto del quiz: fonti ripubblicabili (e IP102 per uso accademico), fonti alternate, nomi stabili."""
    import zlib
    qdir = APP / "quiz"
    qdir.mkdir(parents=True, exist_ok=True)
    sources = {**QUIZ_SOURCES, **QUIZ_SOURCES_ACADEMIC}
    rows = [r for r in csv.DictReader(open(ROOT / "data" / "processed" / "manifest_v2.csv", encoding="utf-8"))
            if r["source"] in sources]
    rng = random.Random(42)
    by_class = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for h in heads:
            if r.get(h) and h in ck["readers"] and r[h] in ck["readers"][h]["classes"]:
                by_class[(h, r[h])][r["source"]].append(r)
    # Calabria in primo piano: classi collegate al Disciplinare di difesa della Regione Calabria e colture
    # che vi compaiono (app/data/difesa.json, scritto prima del quiz)
    from plantcare import difesa as df
    dif_path = APP / "data" / "difesa.json"
    dif = json.load(open(dif_path, encoding="utf-8")) if dif_path.exists() else {"classi": {}}
    cal_classes = {tuple(k.split("|", 1)) for k, per in dif["classi"].items() if any(v["r"] for v in per.values())}
    cal_plants = {p for p, (secs, _) in df.CROPS.items() if secs}
    quiz, keep = [], set()
    for (h, lab), by_src in sorted(by_class.items()):
        for rs in by_src.values():
            rs.sort(key=lambda r: r["path"])
            rng.shuffle(rs)
        # prima le foto non di foglia (frutti, fusti...), poi a turno tra le fonti
        queues = sorted(by_src.values(), key=lambda rs: -sum(r.get("organ") not in ("", "leaf") for r in rs))
        cal = (h, lab) in cal_classes or (h == "plant" and lab in cal_plants)
        limit = (QUIZ_PER_PEST if cal else QUIZ_PER_PEST_OTHER) if h == "pest" else QUIZ_PER_CLASS
        picked = []
        while len(picked) < limit and any(queues):
            for q in queues:
                if q and len(picked) < limit:
                    picked.append(q.pop())
        for r in picked:
            name = f"q{zlib.crc32(r['path'].encode()):08x}.jpg"
            if not (qdir / name).exists():
                try:
                    with Image.open(ROOT / "data" / r["path"]) as im:
                        im = im.convert("RGB")
                        im.thumbnail((QUIZ_SIDE, QUIZ_SIDE))
                        im.save(qdir / name, quality=75)
                except OSError:
                    continue
            keep.add(name)
            item = {"img": name, "head": h, "label": lab, "name": names[h].get(lab, lab),
                    "plant": ip102_group(lab) if h == "pest" else r["plant"], "organ": r.get("organ", ""),
                    "credit": sources[r["source"]]}
            if cal or (h in ("disease", "deficiency") and r["plant"] in cal_plants):  # coltura calabrese
                item["cal"] = 1
            quiz.append(item)
    # foto di iNaturalist (licenze CC0, CC BY, CC BY-NC, autore citato): colture, insetti e malattie
    # della Calabria (configs/quiz_calabria.yaml, scripts/import_inat_quiz.py)
    man_path = ROOT / "data" / "external" / "inat_quiz" / "manifest.json"
    man = json.load(open(man_path, encoding="utf-8")) if man_path.exists() else {}
    plant_names = names.get("plant", {})
    disc = df.load_disciplinare(2026) if man else {"righe": []}
    syn = df._syn()
    for slug, e in sorted(man.items()):
        t = e.get("taxon_inat") or {}
        if e["head"] == "plant" and e.get("coltura_plant"):
            lab, nm = e["coltura_plant"], plant_names.get(e["coltura_plant"], e["nome"])
        else:
            lab, nm = f"inat:{slug}", e["nome"]
        summary = {k: t.get(k) for k in ("name", "ordine", "famiglia", "classe", "regno") if t.get(k)}
        if e.get("causa"):
            summary["causa"] = e["causa"]
        if e["head"] != "plant":  # dove compare nelle norme di difesa della Calabria
            keys = df.keys_in(f"({t.get('name', '')}) ({e['taxon']})", syn)
            hits = [f"{r['coltura'].capitalize()}: {r['avversita']}" for r in disc["righe"] if keys and df._match(keys, set(r["chiavi"]))]
            summary["disciplinare"] = list(dict.fromkeys(hits))[:5]
        for ph in e["foto"]:
            name = f"q{zlib.crc32(ph['path'].encode()):08x}.jpg"
            if not (qdir / name).exists():
                try:
                    with Image.open(ROOT / "data" / ph["path"]) as im:
                        im = im.convert("RGB")
                        im.thumbnail((QUIZ_SIDE, QUIZ_SIDE))
                        im.save(qdir / name, quality=75)
                except OSError:
                    continue
            keep.add(name)
            quiz.append({"img": name, "head": e["head"], "label": lab, "name": nm,
                         "plant": e.get("gruppo") or lab, "organ": "", "cal": 1, "sum": summary,
                         "credit": f"{ph['attribution']}, iNaturalist", "obs": ph["osservazione"]})
    for f in qdir.iterdir():
        if f.name not in keep:
            f.unlink()
    json.dump(quiz, open(APP / "data" / "quiz.json", "w", encoding="utf-8"), ensure_ascii=False)
    size = sum(p.stat().st_size for p in qdir.iterdir()) / 1e6
    print(f"quiz: {len(quiz)} foto, {size:.1f} MB")


def class_names(ck, kb, tax, label_map, heads) -> dict:
    ip_en = {int(k): str(v) for k, v in load_yaml(ROOT / "configs" / "ip102_classes.yaml")["classes"].items()}
    ip_it = {int(k): str(v) for k, v in load_yaml(ROOT / "configs" / "ip102_it.yaml")["names"].items()}
    out = {}
    for h in heads:
        if h not in ck["readers"]:
            continue
        d = {}
        for raw in ck["readers"][h]["classes"]:
            if h == "pest":
                k = int(raw.split("_")[-1])
                en = ip_en.get(k, raw)
                d[raw] = ip_it.get(k) or en[:1].upper() + en[1:]
            elif h == "deficiency":
                d[raw] = DEFICIENCY_NAMES.get(raw, raw)
            else:
                d[raw] = display_name(h, raw, kb, label_map, {})
        out[h] = d
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--ort-dist", default=None)
    ap.add_argument("--quiz-only", action="store_true", help="ricostruisce solo le foto e i dati del quiz")
    ap.add_argument("--with-pest", action="store_true",
                    help="include il lettore degli insetti (IP102: solo uso accademico, confermato dall'utente)")
    ap.add_argument("--ckpt-dir", default=str(CKPT), help="cartella con readers.pt e report.json")
    ap.add_argument("--disease-ft-results", default=None,
                    help="models/finetune_disease.json: metriche della fusione con il ramo riaddestrato")
    ap.add_argument("--improve-results", default=None,
                    help="models/improve_results.json: metriche dell'insieme di lettori, se il modello lo usa")
    ap.add_argument("--pest-ft-results", default=None,
                    help="models/finetune_pest.json: metriche della fusione con il ramo riaddestrato degli insetti")
    ap.add_argument("--hypotheses", default=None,
                    help="models/hypotheses.json (scripts/calibrate_hypotheses.py): soglie delle ipotesi al 95 e al 99%%")
    args = ap.parse_args()

    heads = HEADS + (["pest"] if args.with_pest else [])
    tax = load_taxonomy()
    kb = KnowledgeBase(tax, knowledge=load_yaml(ROOT / "configs" / "knowledge_base.yaml"),
                       sources=load_yaml(ROOT / "configs" / "sources.yaml"))
    label_map = load_yaml(ROOT / "configs" / "label_maps.yaml")
    ckpt_dir = Path(args.ckpt_dir)
    ck = torch.load(ckpt_dir / "readers.pt", map_location="cpu", weights_only=False)
    quiz_heads = HEADS + ["pest"]
    if args.quiz_only:
        build_quiz(ck, quiz_heads, class_names(ck, kb, tax, label_map, quiz_heads))
        return
    report = json.load(open(ckpt_dir / "report.json", encoding="utf-8"))
    improved = json.load(open(args.improve_results, encoding="utf-8")) if args.improve_results else None

    (APP / "data").mkdir(parents=True, exist_ok=True)
    (APP / "model").mkdir(parents=True, exist_ok=True)
    (APP / "ort").mkdir(parents=True, exist_ok=True)

    # --- classi dei lettori, nell'ordine delle uscite del modello ---
    ip_en = {int(k): str(v) for k, v in load_yaml(ROOT / "configs" / "ip102_classes.yaml")["classes"].items()}
    ip_it = {int(k): str(v) for k, v in load_yaml(ROOT / "configs" / "ip102_it.yaml")["names"].items()}
    cause_names, cause_labels = load_causes()
    lab = load_yaml(ROOT / "configs" / "lab_requirements.yaml")
    reg_of = {(h, lbl): i for i, o in enumerate(lab["organismi_regolamentati"])
              for h, lbls in o["classi"].items() for lbl in lbls}
    crops_of = defaultdict(set)  # colture viste per ogni malattia nell'addestramento (filtro "coltura indicata")
    for r in csv.DictReader(open(ROOT / "data" / "processed" / "manifest_v2.csv", encoding="utf-8")):
        if r["split"] == "train" and r.get("disease") and r.get("plant"):
            crops_of[r["disease"]].add(r["plant"])
    readers = {}
    for h in heads:
        classes = ck["readers"][h]["classes"]
        items = []
        for raw in classes:
            item = {"label": raw}
            if h == "plant":
                item["name"] = display_name("plant", raw, kb, label_map, {})
                item["taxonomy_id"] = raw if raw in tax.plants else None
                if raw in tax.plants and tax.plants[raw].get("family"):
                    item["family"] = tax.plants[raw]["family"]
            elif h == "disease":
                item["name"] = display_name("disease", raw, kb, label_map, {})
                tid = raw if raw in tax.diseases else (label_map.get("plantvillage") or {}).get(raw)
                item["taxonomy_id"] = tid
                item["cause"] = cause_of(raw, cause_labels, tax, label_map)
                if item["cause"] is None:
                    raise SystemExit(f"causa mancante per la classe {raw!r}: aggiungerla in configs/disease_causes.yaml")
                if tid:
                    item["card"] = kb.disease_card(tid)
                # classi valide per ogni coltura (pianta sana, disturbo nutrizionale): mai filtrate
                item["crops"] = [] if raw in GENERIC_CLASSES else sorted(crops_of.get(raw, ()))
            elif h == "pest":
                k = int(raw.split("_")[-1])
                en = ip_en.get(k, raw)
                item["name"] = ip_it.get(k) or en[:1].upper() + en[1:]
            else:
                item["name"] = DEFICIENCY_NAMES.get(raw, raw)
            if (h, raw) in reg_of:
                item["reg"] = reg_of[(h, raw)]
            items.append(item)
        t = report["readers"][h]["test"]
        field = {s: v for s, v in t["by_source"].items() if s in ("plantdoc", "inatag")}
        readers[h] = {"classes": items, "test_accuracy": t["accuracy"], "test_macro_f1": t["macro_f1"],
                      "calibration_error": t["ece"], "field": field}
        if improved and h in improved:
            e = improved[h]["insieme"]
            readers[h].update(test_accuracy=e["acc"], test_macro_f1=e["f1"], calibration_error=e["ece"],
                              field={s: {"n": field.get(s, {}).get("n"), "accuracy": e[s]} for s in ("plantdoc", "inatag") if s in e},
                              ensemble=5)
        if h == "disease" and args.disease_ft_results:
            e = json.load(open(args.disease_ft_results, encoding="utf-8"))["fusione"]
            readers[h].update(test_accuracy=e["acc"], test_macro_f1=e["f1"], calibration_error=e["ece"],
                              field={"plantdoc": {"n": field.get("plantdoc", {}).get("n"), "accuracy": e["plantdoc"]}},
                              finetuned_branch=True)
        if h == "pest" and args.pest_ft_results:
            e = json.load(open(args.pest_ft_results, encoding="utf-8"))["fusione"]
            readers[h].update(test_accuracy=e["acc"], test_macro_f1=e["f1"], calibration_error=e["ece"],
                              finetuned_branch=True)
    missing = [lbl for (h, lbl) in reg_of if h in readers and lbl not in {c["label"] for c in readers[h]["classes"]}]
    if missing:
        print(f"attenzione: classi di configs/lab_requirements.yaml assenti dai lettori: {missing}")
    json.dump(readers, open(APP / "data" / "readers.json", "w", encoding="utf-8"), ensure_ascii=False)

    # --- quando serve il laboratorio, organismi regolamentati (schede EPPO), ipotesi calibrate ---
    src = {x["id"]: x for x in load_yaml(ROOT / "configs" / "sources.yaml")["sources"]}
    unknown = [f for v in lab["analisi_per_causa"].values() for f in v["fonti"] if f not in src] + \
        [f for o in lab["organismi_regolamentati"] for f in o.get("fonti", []) if f not in src]
    if unknown:
        raise SystemExit(f"fonti sconosciute in configs/lab_requirements.yaml: {unknown}")
    json.dump({"analisi_per_causa": {c: {"quando": v["quando"], "testo": v["testo"],
                                         "fonti": [{"title": src[f]["title"], "url": src[f]["url"]} for f in v["fonti"]]}
                                     for c, v in lab["analisi_per_causa"].items()},
               "organismi_regolamentati": [{k: o[k] for k in ("organismo", "ue", "tipo", "lista_eppo", "eppo") if k in o}
                                           | ({"nota": o["nota"]} if o.get("nota") else {})
                                           | ({"analisi": o["analisi"], "fonti": [{"title": src[f]["title"], "url": src[f]["url"]}
                                                                                for f in o.get("fonti", [])]}
                                              if o.get("analisi") else {})
                                           | {"url": f"https://gd.eppo.int/taxon/{o['eppo']}/categorization"}
                                           for o in lab["organismi_regolamentati"]]},
              open(APP / "data" / "lab.json", "w", encoding="utf-8"), ensure_ascii=False)
    # difesa: Disciplinare Calabria (sostanze ammesse, limiti, sostanze uscite dall'elenco) e usi Gowan
    from plantcare import difesa as df
    json.dump(df.build_app_data(readers, {k: sorted(v) for k, v in crops_of.items()}),
              open(APP / "data" / "difesa.json", "w", encoding="utf-8"), ensure_ascii=False)
    if args.hypotheses:
        hyp = json.load(open(args.hypotheses, encoding="utf-8"))
        if "disease" in hyp:
            hyp["disease"].pop("colture_per_classe", None)
        json.dump(hyp, open(APP / "data" / "hypotheses.json", "w", encoding="utf-8"), ensure_ascii=False)

    json.dump(cause_names, open(APP / "data" / "causes.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(load_yaml(ROOT / "configs" / "quiz_tips.yaml"), open(APP / "data" / "quiz_tips.json", "w", encoding="utf-8"),
              ensure_ascii=False)

    # --- organi, regole della botte, fonti ---
    organs = [{"id": k, "label": v["label"]} for k, v in tax.plant_organs.items()]
    json.dump(organs, open(APP / "data" / "organs.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(load_yaml(ROOT / "configs" / "mixing_rules.yaml"), open(APP / "data" / "mixing_rules.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump({s["id"]: {"title": s["title"], "url": s["url"], "status": s["status"]}
               for s in load_yaml(ROOT / "configs" / "sources.yaml")["sources"]},
              open(APP / "data" / "sources.json", "w", encoding="utf-8"), ensure_ascii=False)

    build_quiz(ck, quiz_heads, class_names(ck, kb, tax, label_map, quiz_heads))

    # --- modello e motore ---
    shutil.copy(args.model, APP / "model" / "plantcare.onnx")
    dist = Path(args.ort_dist)
    for f in ("ort.wasm.min.js", "ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.mjs"):
        shutil.copy(dist / f, APP / "ort" / f)
    lic = next((c for c in (dist.parent / "LICENSE", dist / "LICENSE") if c.exists()), dist.parent / "LICENSE")
    if lic.exists():
        shutil.copy(lic, APP / "ort" / "LICENSE")
    size = sum(p.stat().st_size for p in APP.rglob("*") if p.is_file()) / 1e6
    print(f"app/ pronta: {size:.1f} MB")


if __name__ == "__main__":
    main()
