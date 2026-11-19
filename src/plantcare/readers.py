"""Lettori ottici: un estrattore di caratteristiche pre-addestrato e un lettore per testa.

Teste (lettori): plant (coltura), disease (malattia), pest (insetto/acaro), deficiency (carenza).
Ogni lettore restituisce probabilità calibrate con temperature scaling sul set di validazione.

Flusso:
    1. extract_features(manifest)  -> caratteristiche salvate a blocchi (riprendibile)
    2. train_readers(features)     -> un classificatore per testa, scelto su validazione
    3. calibrate + evaluate        -> temperatura per testa, metriche su test (anche per fonte)
    4. save_readers(...)           -> checkpoint unico per l'app
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from plantcare.metrics import coverage_accuracy, expected_calibration_error, macro_f1

HEADS = ("plant", "disease", "pest", "deficiency")
READER_LABELS = {
    "plant": "Lettore della coltura",
    "disease": "Lettore della malattia",
    "pest": "Lettore di insetti e acari",
    "deficiency": "Lettore delle carenze",
}


# ---------------------------------------------------------------------------
# Estrattore di caratteristiche
# ---------------------------------------------------------------------------
def backbone_kwargs(name: str, image_size: int) -> dict:
    """I ViT (es. DINOv2) accettano una dimensione d'ingresso esplicita; le CNN no."""
    return {"img_size": image_size} if "vit" in name else {}


def build_backbone(name: str, pretrained: bool = True, image_size: int = 224) -> tuple[nn.Module, Any]:
    model = timm.create_model(name, pretrained=pretrained, num_classes=0, **backbone_kwargs(name, image_size))
    model.eval()
    cfg = timm.data.resolve_data_config({"input_size": (3, image_size, image_size)}, model=model)
    cfg["crop_pct"] = 1.0
    transform = timm.data.create_transform(**cfg)
    return model, transform


class _ImageList(Dataset):
    def __init__(self, paths: list[Path], transform, image_size: int = 224):
        self.paths, self.transform, self.size = paths, transform, image_size

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        try:
            with Image.open(self.paths[i]) as im:
                return self.transform(im.convert("RGB")), i, True
        except Exception:
            return torch.zeros(3, self.size, self.size), i, False


@torch.no_grad()
def extract_features(paths: list[Path], backbone_name: str, out_dir: Path, chunk: int = 4096,
                     batch_size: int = 64, num_workers: int = 2, image_size: int = 224) -> np.ndarray:
    """Caratteristiche per ogni immagine, con cache indicizzata per percorso (riprendibile).

    Ogni blocco salva le caratteristiche (.npy) e l'elenco dei percorsi (.txt). A ogni esecuzione
    si calcolano solo le immagini mancanti; il risultato segue l'ordine di `paths`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, np.ndarray] = {}
    for f in sorted(out_dir.glob("block_*.npy")):
        names = (f.with_suffix(".txt")).read_text(encoding="utf-8").splitlines()
        arr = np.load(f)
        cache.update(zip(names, arr))
    keys = [str(p) for p in paths]
    missing = [p for p, k in zip(paths, keys) if k not in cache]
    if missing:
        model, transform = build_backbone(backbone_name, image_size=image_size)
        start = len(list(out_dir.glob("block_*.npy")))
        n_chunks = math.ceil(len(missing) / chunk)
        for c in range(n_chunks):
            sub = missing[c * chunk:(c + 1) * chunk]
            dl = DataLoader(_ImageList(sub, transform, image_size), batch_size=batch_size, num_workers=num_workers)
            feats = np.zeros((len(sub), model.num_features), dtype=np.float16)
            for x, idx, ok in dl:
                feats[idx.numpy()] = model(x).float().numpy().astype(np.float16)
            stem = out_dir / f"block_{start + c:05d}"
            np.save(stem.with_suffix(".npy"), feats)
            stem.with_suffix(".txt").write_text("\n".join(str(p) for p in sub), encoding="utf-8")
            cache.update(zip((str(p) for p in sub), feats))
            print(f"  blocco {c + 1}/{n_chunks} ({len(missing)} immagini nuove)", flush=True)
    return np.stack([cache[k] for k in keys])


# ---------------------------------------------------------------------------
# Lettori
# ---------------------------------------------------------------------------
class Reader(nn.Module):
    def __init__(self, dim: int, n_classes: int, hidden: int = 0, dropout: float = 0.2):
        super().__init__()
        if hidden:
            self.net = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, hidden), nn.GELU(),
                                     nn.Dropout(dropout), nn.Linear(hidden, n_classes))
        else:
            self.net = nn.Sequential(nn.LayerNorm(dim), nn.Dropout(dropout), nn.Linear(dim, n_classes))
        self.register_buffer("temperature", torch.ones(1))

    def forward(self, x):
        return self.net(x) / self.temperature


def _fit(reader: Reader, X: torch.Tensor, y: torch.Tensor, Xv: torch.Tensor, yv: torch.Tensor,
         class_weights: torch.Tensor, epochs: int = 40, lr: float = 1e-3, wd: float = 1e-4,
         batch: int = 512, patience: int = 6) -> float:
    if len(yv) == 0:  # senza validazione si seleziona sul train (risultato ottimistico)
        Xv, yv = X, y
    opt = torch.optim.AdamW(reader.parameters(), lr=lr, weight_decay=wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    best, best_state, bad = -1.0, None, 0
    g = torch.Generator().manual_seed(0)
    for _ in range(epochs):
        reader.train()
        perm = torch.randperm(len(X), generator=g)
        for i in range(0, len(X), batch):
            b = perm[i:i + batch]
            loss = F.cross_entropy(reader(X[b]), y[b], weight=class_weights, label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
        sched.step()
        reader.eval()
        with torch.no_grad():
            pv = reader(Xv).argmax(1).numpy()
        score = macro_f1(yv.numpy(), pv)
        if score > best:
            best, best_state, bad = score, {k: v.clone() for k, v in reader.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= patience:
                break
    reader.load_state_dict(best_state)
    return best


def calibrate_temperature(reader: Reader, Xv: torch.Tensor, yv: torch.Tensor) -> float:
    """Temperatura che minimizza la log-verosimiglianza negativa sulla validazione."""
    reader.eval()
    reader.temperature.fill_(1.0)
    with torch.no_grad():
        logits = reader(Xv)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / log_t.exp(), yv)
        loss.backward()
        return loss

    opt.step(closure)
    t = float(log_t.exp().clamp(0.05, 20.0))
    reader.temperature.fill_(t)
    return t


@dataclass
class HeadData:
    classes: list[str]
    X: dict[str, torch.Tensor]
    y: dict[str, torch.Tensor]
    sources: dict[str, list[str]]


def prepare_head(rows: list[dict], feats: np.ndarray, head: str, min_train: int = 5) -> HeadData | None:
    """Vocabolario dal train (classi con almeno `min_train` esempi) e tensori per split."""
    train_counts: dict[str, int] = {}
    for r in rows:
        if r["split"] == "train" and r.get(head):
            train_counts[r[head]] = train_counts.get(r[head], 0) + 1
    classes = sorted(c for c, n in train_counts.items() if n >= min_train)
    if len(classes) < 2:
        return None
    index = {c: i for i, c in enumerate(classes)}
    X, y, src = {}, {}, {}
    for split in ("train", "val", "test"):
        idx = [i for i, r in enumerate(rows) if r["split"] == split and r.get(head) in index]
        X[split] = torch.from_numpy(feats[idx].astype(np.float32))
        y[split] = torch.tensor([index[rows[i][head]] for i in idx], dtype=torch.long)
        src[split] = [rows[i]["source"] for i in idx]
    return HeadData(classes, X, y, src)


def evaluate(reader: Reader, hd: HeadData, split: str = "test") -> dict[str, Any]:
    reader.eval()
    with torch.no_grad():
        probs = F.softmax(reader(hd.X[split]), dim=1).numpy()
    y = hd.y[split].numpy()
    pred = probs.argmax(1)
    out: dict[str, Any] = {
        "n": int(len(y)),
        "accuracy": float((pred == y).mean()) if len(y) else None,
        "macro_f1": macro_f1(y, pred) if len(y) else None,
        "ece": expected_calibration_error(probs, y) if len(y) else None,
        "coverage": coverage_accuracy(probs, y, [0.3, 0.5, 0.7, 0.9]) if len(y) else [],
        "by_source": {},
    }
    srcs = np.array(hd.sources[split])
    for s in sorted(set(srcs)):
        m = srcs == s
        out["by_source"][s] = {"n": int(m.sum()), "accuracy": float((pred[m] == y[m]).mean()),
                               "macro_f1": macro_f1(y[m], pred[m])}
    return out


def train_reader(hd: HeadData, dim: int) -> tuple[Reader, dict[str, Any]]:
    """Prova un lettore lineare e un MLP; tiene il migliore in validazione; poi calibra."""
    counts = torch.bincount(hd.y["train"], minlength=len(hd.classes)).float().clamp(min=1)
    weights = (counts.sum() / counts).sqrt()
    weights = weights / weights.mean()
    candidates = []
    for hidden in (0, 1024):
        r = Reader(dim, len(hd.classes), hidden=hidden)
        score = _fit(r, hd.X["train"], hd.y["train"], hd.X["val"], hd.y["val"], weights)
        candidates.append((score, hidden, r))
    score, hidden, best = max(candidates, key=lambda c: c[0])
    has_val = len(hd.y["val"]) > 0
    before = evaluate(best, hd, "val")["ece"] if has_val else None
    t = calibrate_temperature(best, hd.X["val"], hd.y["val"]) if has_val else 1.0
    info = {
        "arch": "mlp" if hidden else "linear",
        "val_macro_f1": score,
        "temperature": t,
        "val_ece_before": before,
        "val_ece_after": evaluate(best, hd, "val")["ece"] if has_val else None,
        "test": evaluate(best, hd, "test"),
        "classes": hd.classes,
        "n_train": int(len(hd.y["train"])),
    }
    return best, info


# ---------------------------------------------------------------------------
# Modello completo per l'inferenza
# ---------------------------------------------------------------------------
class ReadersNet(nn.Module):
    """Uno o più backbone (caratteristiche concatenate) + lettori.

    Interfaccia uguale a MultiTaskNet: restituisce un dict di logit già calibrati.
    """

    def __init__(self, backbones: list[str] | str, readers: dict[str, dict], pretrained: bool = False,
                 image_size: int = 224):
        super().__init__()
        names = [backbones] if isinstance(backbones, str) else list(backbones)
        self.backbones = nn.ModuleList([
            timm.create_model(n, pretrained=pretrained, num_classes=0, **backbone_kwargs(n, image_size))
            for n in names
        ])
        dim = sum(b.num_features for b in self.backbones)
        self.heads = nn.ModuleDict({
            h: Reader(dim, len(r["classes"]), hidden=1024 if r["arch"] == "mlp" else 0)
            for h, r in readers.items()
        })

    def forward(self, x):
        f = torch.cat([b(x) for b in self.backbones], dim=1)
        return {h: m(f) for h, m in self.heads.items()}


def save_readers(path: Path, backbones: list[str] | str, readers: dict[str, Reader], infos: dict[str, dict],
                 data_config: dict, sources: list[str], image_size: int = 224,
                 backbone_models: list[nn.Module] | None = None) -> None:
    names = [backbones] if isinstance(backbones, str) else list(backbones)
    models = backbone_models or [
        timm.create_model(n, pretrained=True, num_classes=0, **backbone_kwargs(n, image_size)) for n in names
    ]
    torch.save({
        "kind": "readers",
        "backbones": names,
        "image_size": image_size,
        "backbone_states": [m.state_dict() for m in models],
        "data_config": data_config,
        "readers": {h: {"state": r.state_dict(), "arch": infos[h]["arch"], "classes": infos[h]["classes"],
                        "temperature": infos[h]["temperature"]} for h, r in readers.items()},
        "metrics": {h: {k: v for k, v in infos[h].items() if k != "classes"} for h in infos},
        "training_sources": sources,
    }, path)


def load_readers(path: Path, device: str = "cpu") -> tuple[ReadersNet, dict]:
    ck = torch.load(path, map_location=device, weights_only=False)
    names = ck.get("backbones") or [ck["backbone"]]
    states = ck.get("backbone_states") or [ck["backbone_state"]]
    net = ReadersNet(names, ck["readers"], pretrained=False, image_size=ck.get("image_size", 224))
    for b, st in zip(net.backbones, states):
        b.load_state_dict(st)
    for h, r in ck["readers"].items():
        net.heads[h].load_state_dict(r["state"])
    net.eval()
    return net, ck


def write_report(path: Path, infos: dict[str, dict], extra: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"readers": infos, **extra}, fh, ensure_ascii=False, indent=2, default=float)
