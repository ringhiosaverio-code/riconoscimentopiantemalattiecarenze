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
}
QUIZ_PER_CLASS = 4


def load_yaml(p: Path) -> dict:
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ort-dist", required=True)
    ap.add_argument("--improve-results", default=None,
                    help="models/improve_results.json: metriche dell'insieme di lettori, se il modello lo usa")
    args = ap.parse_args()

    tax = load_taxonomy()
    kb = KnowledgeBase(tax, knowledge=load_yaml(ROOT / "configs" / "knowledge_base.yaml"),
                       sources=load_yaml(ROOT / "configs" / "sources.yaml"))
    label_map = load_yaml(ROOT / "configs" / "label_maps.yaml")
    ck = torch.load(CKPT / "readers.pt", map_location="cpu", weights_only=False)
    report = json.load(open(CKPT / "report.json", encoding="utf-8"))
    improved = json.load(open(args.improve_results, encoding="utf-8")) if args.improve_results else None

    (APP / "data").mkdir(parents=True, exist_ok=True)
    (APP / "model").mkdir(parents=True, exist_ok=True)
    (APP / "ort").mkdir(parents=True, exist_ok=True)

    # --- classi dei lettori, nell'ordine delle uscite del modello ---
    readers = {}
    for h in HEADS:
        classes = ck["readers"][h]["classes"]
        items = []
        for raw in classes:
            item = {"label": raw}
            if h == "plant":
                item["name"] = display_name("plant", raw, kb, label_map, {})
                item["taxonomy_id"] = raw if raw in tax.plants else None
            elif h == "disease":
                item["name"] = display_name("disease", raw, kb, label_map, {})
                tid = raw if raw in tax.diseases else (label_map.get("plantvillage") or {}).get(raw)
                item["taxonomy_id"] = tid
                if tid:
                    item["card"] = kb.disease_card(tid)
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
    json.dump(readers, open(APP / "data" / "readers.json", "w", encoding="utf-8"), ensure_ascii=False)

    # --- organi, regole della botte, fonti ---
    organs = [{"id": k, "label": v["label"]} for k, v in tax.plant_organs.items()]
    json.dump(organs, open(APP / "data" / "organs.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(load_yaml(ROOT / "configs" / "mixing_rules.yaml"), open(APP / "data" / "mixing_rules.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump({s["id"]: {"title": s["title"], "url": s["url"], "status": s["status"]}
               for s in load_yaml(ROOT / "configs" / "sources.yaml")["sources"]},
              open(APP / "data" / "sources.json", "w", encoding="utf-8"), ensure_ascii=False)

    # --- quiz: foto di test, solo da fonti ripubblicabili ---
    qdir = APP / "quiz"
    if qdir.exists():
        shutil.rmtree(qdir)
    qdir.mkdir(parents=True)
    rows = [r for r in csv.DictReader(open(ROOT / "data" / "processed" / "manifest_v2.csv", encoding="utf-8"))
            if r["split"] == "test" and r["source"] in QUIZ_SOURCES]
    rng = random.Random(42)
    by_class = defaultdict(list)
    for r in rows:
        for h in HEADS:
            if r[h] and r[h] in ck["readers"][h]["classes"]:
                by_class[(h, r[h])].append(r)
    quiz = []
    n = 0
    for (h, lab), rs in sorted(by_class.items()):
        for r in rng.sample(rs, min(QUIZ_PER_CLASS, len(rs))):
            name = f"q{n:05d}.jpg"
            with Image.open(ROOT / "data" / r["path"]) as im:
                im = im.convert("RGB")
                im.thumbnail((320, 320))
                im.save(qdir / name, quality=80)
            quiz.append({"img": name, "head": h, "label": lab, "plant": r["plant"], "credit": QUIZ_SOURCES[r["source"]]})
            n += 1
    json.dump(quiz, open(APP / "data" / "quiz.json", "w", encoding="utf-8"), ensure_ascii=False)

    # --- modello e motore ---
    shutil.copy(args.model, APP / "model" / "plantcare.onnx")
    dist = Path(args.ort_dist)
    for f in ("ort.wasm.min.js", "ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.mjs"):
        shutil.copy(dist / f, APP / "ort" / f)
    lic = next((c for c in (dist.parent / "LICENSE", dist / "LICENSE") if c.exists()), dist.parent / "LICENSE")
    if lic.exists():
        shutil.copy(lic, APP / "ort" / "LICENSE")
    size = sum(p.stat().st_size for p in APP.rglob("*") if p.is_file()) / 1e6
    print(f"app/ pronta: {len(quiz)} foto del quiz, {size:.1f} MB")


if __name__ == "__main__":
    main()
