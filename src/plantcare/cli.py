"""Riga di comando: plantcare <comando>.

    plantcare check-taxonomy              verifica tassonomia e copertura colture
    plantcare build-manifest              crea data/processed/manifest.csv dai dataset
    plantcare train -c configs/train_baseline.yaml
    plantcare serve                       avvia l'interfaccia web (PLANTCARE_CKPT)
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
    rows = []
    if (data_root / "plantvillage").is_dir():
        for r in scan_plantvillage(data_root / "plantvillage", seed=cfg.get("seed", 42)):
            r.path = f"plantvillage/{r.path}"
            rows.append(r)
    if (data_root / "ip102").is_dir():
        for r in scan_ip102(data_root / "ip102", images_dir=cfg.get("ip102_images_dir", "images")):
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
