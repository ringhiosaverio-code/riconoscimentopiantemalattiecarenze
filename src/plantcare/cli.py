"""Riga di comando: plantcare <comando>.

    plantcare check-taxonomy              verifica tassonomia e copertura colture
    plantcare build-manifest              crea data/processed/manifest.csv dai dataset
    plantcare train -c configs/train_baseline.yaml
    plantcare serve                       avvia l'interfaccia web e l'API (PLANTCARE_CKPT)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from plantcare.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy

ROOT = Path(__file__).resolve().parents[2]


def cmd_check_taxonomy(_: argparse.Namespace) -> int:
    tax = load_taxonomy(DEFAULT_TAXONOMY_PATH)
    print(f"Tassonomia v{tax.version} valida.")
    print(f"  colture: {len(tax.plants)}  malattie: {len(tax.diseases)}  insetti: {len(tax.insects)}")
    disease_hosts = {h for d in tax.diseases.values() for h in d.get("hosts", [])}
    no_disease = sorted(p for p in tax.plants if p not in disease_hosts)
    print(f"  colture senza malattie di riferimento ({len(no_disease)}): {', '.join(no_disease) or '-'}")
    insect_hosts = {h for i in tax.insects.values() if i["role"] == "phytophagous" for h in i.get("hosts", [])}
    no_insect = sorted(p for p in tax.plants if p not in insect_hosts)
    print(f"  colture senza fitofagi di riferimento ({len(no_insect)}): {', '.join(no_insect) or '-'}")
    return 0


def cmd_build_manifest(args: argparse.Namespace) -> int:
    from plantcare.data.pipeline import (
        find_corrupt_images, find_cross_split_duplicates, scan_ip102, scan_plantvillage,
        summarize, write_manifest,
    )
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    # Convenzione: ogni dataset sta in data_root/<nome>, e i percorsi del manifest
    # sono relativi a data_root (es. 'plantvillage/color/Tomato___healthy/x.jpg').
    data_root = Path(cfg.get("data_root", ROOT / "data" / "raw"))
    from plantcare.data.pipeline import load_leaf_map
    rows = []
    pv_dir = data_root / "plantvillage"
    if (pv_dir / "raw" / "color").is_dir():  # layout del dataset ufficiale (zip di Hugging Face)
        pv_dir = pv_dir / "raw" / "color"
    if pv_dir.is_dir() and any(p.is_dir() and "___" in p.name for p in pv_dir.iterdir()):
        # mappa dei gruppi foglia: copia nel dataset, altrimenti quella versionata nel repository
        candidates = [data_root / "plantvillage" / "leaf_grouping" / "leaf-map.json",
                      ROOT / "metadata" / "plantvillage" / "leaf-map.json"]
        leaf_map = next((load_leaf_map(c) for c in candidates if c.exists()), {})
        if not leaf_map:
            print("Attenzione: mappa dei gruppi foglia assente, lo split PlantVillage sarà ottimistico", file=sys.stderr)
        for r in scan_plantvillage(pv_dir, seed=cfg.get("seed", 42), leaf_map=leaf_map):
            r.path = f"{pv_dir.relative_to(data_root).as_posix()}/{r.path}"
            rows.append(r)
    if (data_root / "ip102").is_dir():
        for r in scan_ip102(data_root / "ip102", images_dir=cfg.get("ip102_images_dir", "images"),
                            label_base=cfg.get("ip102_label_base", 0)):
            r.path = f"ip102/{r.path}"
            rows.append(r)
    if not rows:
        print(f"Nessun dataset trovato in {data_root}/plantvillage o {data_root}/ip102", file=sys.stderr)
        return 1

    out = Path(cfg.get("manifest", ROOT / "data" / "processed" / "manifest.csv"))
    write_manifest(rows, out)
    print(f"Manifest: {out} ({len(rows)} righe)")
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))

    if args.check:
        leaks = find_cross_split_duplicates(data_root, rows)
        bad = find_corrupt_images(data_root, rows)
        print(f"Duplicati identici tra split: {len(leaks)} gruppi")
        print(f"Immagini corrotte: {len(bad)}")
        if leaks:
            print("Primi gruppi:", leaks[:5])
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    from plantcare.train import load_config, train
    cfg = load_config(args.config)
    result = train(cfg)
    print(f"Checkpoint: {result.checkpoint}")
    print(f"Report: {result.report}")
    print(f"Miglior macro-F1 medio di validazione: {result.best_val_macro_f1:.4f}")
    return 0


def cmd_import_external(args: argparse.Namespace) -> int:
    """Importa PlantVillage e i dataset esterni in un manifest unificato (data/processed/manifest_v2.csv)."""
    from plantcare.data import importers as im
    from plantcare.data.pipeline import summarize, write_manifest
    reg = {e["name"]: e for e in yaml.safe_load(open(ROOT / "configs" / "external_datasets.yaml", encoding="utf-8"))["datasets"]}
    rows = []
    steps = [("plantvillage", lambda: im.import_plantvillage(ROOT / "metadata" / "plantvillage" / "leaf-map.json")),
             ("ip102", im.import_ip102), ("plantdoc", im.import_plantdoc), ("inatag", im.import_inatag)]
    for name, e in reg.items():
        if name.startswith("agml_"):
            steps.append((name, lambda e=e: im.import_agml(e["name"], e["repo"], e["crop"])))
    for name, fn in steps:
        if args.only and name not in args.only:
            continue
        got = fn()
        print(f"{name}: {len(got)} righe", flush=True)
        rows += got
    out = ROOT / "data" / "processed" / "manifest_v2.csv"
    write_manifest(rows, out)
    print(f"Manifest unificato: {out} ({len(rows)} righe)")
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))
    return 0


def cmd_train_readers(args: argparse.Namespace) -> int:
    """Estrae le caratteristiche, addestra e calibra i lettori, li valuta e salva il checkpoint."""
    import numpy as np
    import timm
    from plantcare import readers as rd
    from plantcare.data.pipeline import read_manifest
    rows = read_manifest(ROOT / "data" / "processed" / "manifest_v2.csv")
    paths = [ROOT / "data" / r["path"] for r in rows]
    parts = []
    for bb in args.backbone:
        feat_dir = ROOT / "data" / "processed" / f"features_{bb}_{args.image_size}"
        print(f"Estrazione caratteristiche: {bb}", flush=True)
        parts.append(rd.extract_features(paths, bb, feat_dir, image_size=args.image_size,
                                         num_workers=args.workers))
    feats = np.concatenate(parts, axis=1)
    dim = feats.shape[1]
    readers, infos = {}, {}
    for head in rd.HEADS:
        hd = rd.prepare_head(rows, feats, head)
        if hd is None:
            print(f"{head}: nessun dato di addestramento, lettore non disponibile")
            continue
        r, info = rd.train_reader(hd, dim)
        readers[head], infos[head] = r, info
        t = info["test"]
        print(f"{head}: {len(hd.classes)} classi, {info['arch']}, test acc={t['accuracy']:.4f} "
              f"macroF1={t['macro_f1']:.4f} ECE={t['ece']:.4f} T={info['temperature']:.2f}", flush=True)
    out_dir = ROOT / "models" / ("readers_" + "+".join(b.split(".")[0] for b in args.backbone))
    out_dir.mkdir(parents=True, exist_ok=True)
    cfgs = [timm.data.resolve_data_config({"input_size": (3, args.image_size, args.image_size)},
                                          model=timm.create_model(b, pretrained=False, num_classes=0,
                                                                  **rd.backbone_kwargs(b, args.image_size)))
            for b in args.backbone]
    if any((c["mean"], c["std"]) != (cfgs[0]["mean"], cfgs[0]["std"]) for c in cfgs):
        raise SystemExit("I backbone usano normalizzazioni diverse: non combinabili con un'unica trasformazione")
    data_cfg = cfgs[0]
    sources = sorted({r["source"] for r in rows})
    rd.save_readers(out_dir / "readers.pt", args.backbone, readers, infos, data_cfg, sources, args.image_size)
    rd.write_report(out_dir / "report.json", infos, {"backbones": args.backbone, "image_size": args.image_size,
                                                    "sources": sources, "n_images": len(rows)})
    print(f"Checkpoint: {out_dir / 'readers.pt'}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    from plantcare.api import create_app
    app = create_app(args.checkpoint, abstain_threshold=args.threshold)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="plantcare")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-taxonomy").set_defaults(func=cmd_check_taxonomy)

    bm = sub.add_parser("build-manifest")
    bm.add_argument("-c", "--config", default=str(ROOT / "configs" / "datasets.yaml"))
    bm.add_argument("--check", action="store_true", help="controlla duplicati tra split e immagini corrotte")
    bm.set_defaults(func=cmd_build_manifest)

    tr = sub.add_parser("train")
    tr.add_argument("-c", "--config", default=str(ROOT / "configs" / "train_baseline.yaml"))
    tr.set_defaults(func=cmd_train)

    ie = sub.add_parser("import-external")
    ie.add_argument("--only", nargs="*", default=None)
    ie.set_defaults(func=cmd_import_external)

    trd = sub.add_parser("train-readers")
    trd.add_argument("--backbone", nargs="+", default=["vit_small_patch14_dinov2.lvd142m", "efficientnet_b0"])
    trd.add_argument("--image-size", type=int, default=224)
    trd.add_argument("--workers", type=int, default=2)
    trd.set_defaults(func=cmd_train_readers)

    sv = sub.add_parser("serve")
    sv.add_argument("--checkpoint", default=None)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--threshold", type=float, default=0.5)
    sv.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
