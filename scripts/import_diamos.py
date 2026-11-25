"""DiaMOS Plant (Fenu e Malloci 2021, Zenodo 5557313, CC BY 4.0): foglie di pero in campo (Sardegna).

Lo zip è di 13 GB: si legge a pezzi via HTTP (richieste "Range") e si estraggono solo le foto delle
foglie, ridotte a 512 px. Le etichette sono nel CSV del dataset (una colonna per malattia).

Uso: python scripts/import_diamos.py   poi le righe vanno nel manifest (fonte "diamos").
"""
import csv
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://zenodo.org/records/5557313/files/Pear.zip?download=1"
OUT = ROOT / "data" / "external" / "diamos"
IMG = ROOT / "data" / "external" / "images" / "diamos"
# foto per classe (cartelle di Pear/leaves): "curl" escluso, la causa dell'accartocciamento non è indicata
CAP = {"healthy": 44, "slug": 500, "spot": 600}


class HttpFile(io.RawIOBase):
    """File di sola lettura su HTTP con richieste Range (blocchi da 1 MB in memoria)."""

    def __init__(self, url, block=1 << 20):
        self.url, self.block, self.pos, self.cache = url, block, 0, {}
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])
            self.url = r.url

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def _get(self, b):
        if b not in self.cache:
            if len(self.cache) > 64:
                self.cache.clear()
            start, end = b * self.block, min(self.size, (b + 1) * self.block) - 1
            for k in range(5):
                try:
                    req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        self.cache[b] = r.read()
                    break
                except Exception:
                    if k == 4:
                        raise
        return self.cache[b]

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            b, o = divmod(self.pos, self.block)
            chunk = self._get(b)[o:o + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, buf):
        data = self.read(len(buf))
        buf[:len(data)] = data
        return len(data)


def main():
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(HttpFile(URL))
    names = zf.namelist()
    if "--list" in sys.argv:
        csvs = [n for n in names if n.lower().endswith((".csv", ".xlsx", ".txt"))]
        print(len(names), "file;", csvs)
        dirs = sorted({"/".join(n.split("/")[:3]) for n in names})
        print("\n".join(dirs[:60]))
        for c in csvs:
            (OUT / Path(c).name).write_bytes(zf.read(c))
        return
    labels = {}
    for c in [n for n in names if n.lower().endswith(".csv")]:
        text = zf.read(c).decode("utf-8-sig", "ignore")
        (OUT / Path(c).name).write_text(text, encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ","):
            labels[r.get("filename") or r.get("Filename") or next(iter(r.values()))] = r
    done = json.load(open(OUT / "estratte.json")) if (OUT / "estratte.json").exists() else {}
    import random
    leaves = [n for n in names if "/leaves/" in n and not n.split("/")[-1].startswith("._")
              and n.lower().endswith((".jpg", ".jpeg", ".png")) and n.split("/")[-2] in CAP]
    by = {}
    for n in sorted(leaves):
        by.setdefault(n.split("/")[-2], []).append(n)
    leaves = [n for k, v in by.items() for n in sorted(random.Random(42).sample(v, min(len(v), CAP[k])))]
    print(len(leaves), "foto di foglie,", len(labels), "etichette", flush=True)
    import threading
    from concurrent.futures import ThreadPoolExecutor
    local, lock = threading.local(), threading.Lock()

    def one(n):  # ogni thread ha il suo zip remoto
        if not hasattr(local, "zf"):
            local.zf = zipfile.ZipFile(HttpFile(URL))
        f = IMG / n.split("/")[-2] / (Path(n).stem + ".jpg")
        try:
            with Image.open(io.BytesIO(local.zf.read(n))) as im:
                im = im.convert("RGB")
                im.thumbnail((512, 512))
                f.parent.mkdir(parents=True, exist_ok=True)
                im.save(f, quality=90)
        except Exception as ex:
            print("errore", n, ex, flush=True)
            return
        with lock:
            done[n] = str(f.relative_to(ROOT / "data"))
            if len(done) % 50 == 0:
                json.dump(done, open(OUT / "estratte.json", "w"))
                print(f"  {len(done)}/{len(leaves)}", flush=True)

    todo = [n for n in leaves if n not in done and not (IMG / n.split("/")[-2] / (Path(n).stem + ".jpg")).exists()]
    for n in leaves:
        f = IMG / n.split("/")[-2] / (Path(n).stem + ".jpg")
        if n not in done and f.exists():
            done[n] = str(f.relative_to(ROOT / "data"))
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, todo))
    json.dump(done, open(OUT / "estratte.json", "w"))
    print("FATTO", len(done))


if __name__ == "__main__":
    main()
