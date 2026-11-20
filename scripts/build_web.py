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
# IP102 (Wu et al. 2019): concesso solo per uso accademico; incluso su conferma dell'uso accademico del progetto
QUIZ_SOURCES_ACADEMIC = {"ip102": "IP102 (Wu et al. 2019, CVPR): solo per uso accademico"}
# gruppi di colture di IP102 (indici 1-based delle classi), come nell'articolo originale
IP102_GROUPS = [(1, 14, "riso"), (15, 27, "mais"), (28, 36, "frumento"), (37, 44, "barbabietola"),
                (45, 57, "erba medica"), (58, 73, "vite"), (74, 92, "agrumi"), (93, 102, "mango")]
QUIZ_SIDE = 288


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
    quiz, keep = [], set()
    for (h, lab), by_src in sorted(by_class.items()):
        for rs in by_src.values():
            rs.sort(key=lambda r: r["path"])
            rng.shuffle(rs)
        # prima le foto non di foglia (frutti, fusti...), poi a turno tra le fonti
        queues = sorted(by_src.values(), key=lambda rs: -sum(r.get("organ") not in ("", "leaf") for r in rs))
        limit = QUIZ_PER_PEST if h == "pest" else QUIZ_PER_CLASS
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
            quiz.append(item)
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
            elif h == "pest":
                k = int(raw.split("_")[-1])
                en = ip_en.get(k, raw)
                item["name"] = ip_it.get(k) or en[:1].upper() + en[1:]
            else:
                item["name"] = DEFICIENCY_NAMES.get(raw, raw)
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
    json.dump(readers, open(APP / "data" / "readers.json", "w", encoding="utf-8"), ensure_ascii=False)

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
