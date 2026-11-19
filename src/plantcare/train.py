"""Addestramento baseline multi-task a partire dal manifest.

Flusso:
1. legge il manifest e separa gli split;
2. costruisce il vocabolario delle etichette SOLO dal train (nessuna classe "vista" in test);
3. addestra con perdita mascherata e scheduler cosinus;
4. seleziona il modello migliore per macro-F1 medio sulle teste di validazione;
5. salva checkpoint (pesi + vocabolari + configurazione) e report JSON.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T

from plantcare.data.pipeline import read_manifest
from plantcare.metrics import confusion, macro_f1, per_class_report
from plantcare.model import IGNORE_INDEX, MultiTaskNet, multitask_loss

HEADS = ("plant", "disease", "pest")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def build_label_maps(rows: list[dict[str, str]], heads: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """Vocabolario per testa, ordinato e costruito solo dalle righe di train."""
    maps: dict[str, dict[str, int]] = {}
    for head in heads:
        values = sorted({r[head] for r in rows if r[head]})
        if values:
            maps[head] = {v: i for i, v in enumerate(values)}
    return maps


def make_transforms(image_size: int, train: bool) -> T.Compose:
    if train:
        return T.Compose([
            T.RandomResizedCrop(image_size, scale=(0.7, 1.0)),
            T.RandomHorizontalFlip(),
            T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    return T.Compose([
        T.Resize(int(image_size * 1.14)),
        T.CenterCrop(image_size),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


class ManifestDataset(Dataset):
    def __init__(self, rows: list[dict[str, str]], root: Path, label_maps: dict[str, dict[str, int]], transform: T.Compose):
        self.rows = rows
        self.root = root
        self.label_maps = label_maps
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        row = self.rows[i]
        with Image.open(self.root / row["path"]) as im:
            x = self.transform(im.convert("RGB"))
        targets = {}
        for head, mapping in self.label_maps.items():
            value = row.get(head, "")
            targets[head] = torch.tensor(mapping.get(value, IGNORE_INDEX) if value else IGNORE_INDEX)
        return x, targets


def collate(batch):
    xs = torch.stack([b[0] for b in batch])
    heads = batch[0][1].keys()
    ts = {h: torch.stack([b[1][h] for b in batch]) for h in heads}
    return xs, ts


@torch.no_grad()
def evaluate(model: MultiTaskNet, loader: DataLoader, device: torch.device) -> dict[str, dict[str, Any]]:
    """Restituisce, per testa: predizioni, probabilità, etichette vere."""
    model.eval()
    collected: dict[str, dict[str, list]] = {}
    for x, targets in loader:
        out = model(x.to(device))
        for head, logits in out.items():
            c = collected.setdefault(head, {"probs": [], "true": []})
            c["probs"].append(F.softmax(logits, dim=1).cpu().numpy())
            c["true"].append(targets[head].numpy())
    result = {}
    for head, c in collected.items():
        probs = np.concatenate(c["probs"])
        true = np.concatenate(c["true"])
        keep = true != IGNORE_INDEX
        result[head] = {"probs": probs[keep], "true": true[keep], "pred": probs[keep].argmax(axis=1)}
    return result


@dataclass
class TrainResult:
    best_val_macro_f1: float
    checkpoint: Path
    report: Path


def train(cfg: dict[str, Any]) -> TrainResult:
    set_seed(cfg.get("seed", 42))
    device = torch.device(cfg.get("device", "cuda" if torch.cuda.is_available() else "cpu"))

    manifest = Path(cfg["manifest"])
    data_root = Path(cfg["data_root"])
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_manifest(manifest)
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] == "val"]
    if not train_rows:
        raise ValueError("Il manifest non contiene righe di train")

    heads = tuple(cfg.get("heads", HEADS))
    label_maps = build_label_maps(train_rows, heads)
    if not label_maps:
        raise ValueError("Nessuna testa ha etichette nel train")

    size = cfg.get("image_size", 224)
    bs = cfg.get("batch_size", 32)
    nw = cfg.get("num_workers", 0)
    train_ds = ManifestDataset(train_rows, data_root, label_maps, make_transforms(size, True))
    val_ds = ManifestDataset(val_rows, data_root, label_maps, make_transforms(size, False))
    train_dl = DataLoader(train_ds, batch_size=bs, shuffle=True, num_workers=nw, collate_fn=collate)
    val_dl = DataLoader(val_ds, batch_size=bs, shuffle=False, num_workers=nw, collate_fn=collate)

    head_sizes = {h: len(m) for h, m in label_maps.items()}
    model = MultiTaskNet(
        cfg.get("backbone", "resnet18"),
        head_sizes,
        pretrained=cfg.get("pretrained", False),
        dropout=cfg.get("dropout", 0.2),
    ).to(device)

    opt = torch.optim.AdamW(model.parameters(), lr=cfg.get("lr", 3e-4), weight_decay=cfg.get("weight_decay", 1e-4))
    epochs = cfg.get("epochs", 10)
    steps = max(1, epochs * len(train_dl))
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    weights = cfg.get("head_weights", {})

    best = -1.0
    best_state = None
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        for x, targets in train_dl:
            x = x.to(device)
            targets = {h: t.to(device) for h, t in targets.items()}
            loss, _ = multitask_loss(model(x), targets, weights)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            running += float(loss.detach())

        val = evaluate(model, val_dl, device)
        scores = {h: macro_f1(v["true"], v["pred"]) for h, v in val.items() if len(v["true"])}
        mean_f1 = float(np.mean(list(scores.values()))) if scores else 0.0
        history.append({"epoch": epoch, "train_loss": running / max(1, len(train_dl)), "val_macro_f1": scores, "mean": mean_f1})
        print(f"epoch {epoch}/{epochs} loss={running / max(1, len(train_dl)):.4f} val_macro_f1={mean_f1:.4f}")

        if mean_f1 > best:
            best = mean_f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is None:
        raise RuntimeError("Nessuna epoca completata")
    model.load_state_dict(best_state)

    ckpt = out_dir / "model.pt"
    torch.save({
        "model_state": best_state,
        "backbone": cfg.get("backbone", "resnet18"),
        "head_sizes": head_sizes,
        "label_maps": label_maps,
        "image_size": size,
        "config": cfg,
    }, ckpt)

    # Report finale sulla validazione del modello migliore, per testa.
    final_val = evaluate(model, val_dl, device)
    per_head = {}
    for head, v in final_val.items():
        names = sorted(label_maps[head], key=label_maps[head].get)
        per_head[head] = {
            "macro_f1": macro_f1(v["true"], v["pred"]) if len(v["true"]) else None,
            "per_class": per_class_report(v["true"], v["pred"], names) if len(v["true"]) else {},
            "confusion": confusion(v["true"], v["pred"], len(names)).tolist(),
            "class_names": names,
        }
    report = out_dir / "report.json"
    with open(report, "w", encoding="utf-8") as fh:
        json.dump({"history": history, "best_val_mean_macro_f1": best, "heads": per_head}, fh, ensure_ascii=False, indent=2, default=float)

    return TrainResult(best_val_macro_f1=best, checkpoint=ckpt, report=report)


def load_config(path: Path | str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
