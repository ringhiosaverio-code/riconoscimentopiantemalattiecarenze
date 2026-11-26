"""Foglio di provini per la verifica a vista delle foto candidate (numero, classe proposta).

Uso: python scripts/foglio_contatti.py candidate.json uscita.jpg [--min-campo 0.8] [--da 0 --a 60]
candidate.json: lista di {"path": percorso sotto data/, "classe": ..., "campo": punteggio CLIP}
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("out")
    ap.add_argument("--min-campo", type=float, default=0.8)
    ap.add_argument("--da", type=int, default=0)
    ap.add_argument("--a", type=int, default=60)
    ap.add_argument("--cols", type=int, default=6)
    args = ap.parse_args()
    items = [(i, x) for i, x in enumerate(json.load(open(args.candidate, encoding="utf-8")))
             if x.get("campo", 1) >= args.min_campo][args.da:args.a]
    w, h = 230, 250
    rows = (len(items) + args.cols - 1) // args.cols
    sheet = Image.new("RGB", (args.cols * w, max(1, rows) * h), "white")
    d = ImageDraw.Draw(sheet)
    for k, (i, x) in enumerate(items):
        try:
            with Image.open(ROOT / "data" / x["path"]) as im:
                im = im.convert("RGB")
                im.thumbnail((w - 10, h - 40))
                X, Y = (k % args.cols) * w, (k // args.cols) * h
                sheet.paste(im, (X + 5, Y + 5))
        except Exception:
            X, Y = (k % args.cols) * w, (k // args.cols) * h
        d.text((X + 5, Y + h - 32), f"{i}: {x['classe'][-30:]}", fill="black")
    sheet.save(args.out, quality=85)
    print(len(items), "foto nel foglio")


if __name__ == "__main__":
    main()
