"""Riaddestra gli ultimi 2 blocchi di DINOv2 per il lettore delle malattie (su CPU).

Gli estrattori congelati confondono malattie simili su foto di campo (peronospora precoce e
tardiva del pomodoro, virosi e pianta sana). Qui si riaddestrano solo gli ultimi due blocchi:
  1. si salvano una volta i token all'ingresso del blocco 10 (fp16, su disco, riprendibile);
     per il train due viste: la foto intera e una versione aumentata (ritaglio, specchio, luce);
  2. si addestrano blocchi 10-11 + lettore, con i token delle foto oscurati a caso (25%) e le
     foto di campo pesate di più;
  3. si calibra la temperatura sulla validazione e si confronta sul test con l'insieme attuale.

Nell'app i due blocchi riaddestrati sono un ramo separato: coltura, carenze e insetti usano
ancora l'estrattore originale.

Uso: PYTHONPATH=src python scripts/finetune_disease.py [--epochs 5]
"""
from __future__ import annotations

import argparse
import os
import copy
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T

from plantcare import readers as rd
from plantcare.data.pipeline import read_manifest
from plantcare.metrics import expected_calibration_error, macro_f1

ROOT = Path(__file__).resolve().parents[1]
DINO = "vit_small_patch14_dinov2.lvd142m"
EFF = "efficientnet_b0"
SPLIT_AT = 10
TOK_DIR = ROOT / "data" / "processed" / "ft_tokens"
FIELD_W = {"plantdoc": 3.0, "plantwild": 3.0}
FIELD_SOURCES = ("plantdoc", "plantwild")  # foto di campo: misurate a parte e usate per scegliere il modello
PV_TRAIN, PV_VAL = 8000, 2000
TRAIN_CAP = {"pest": 300}
SOURCE_CAP = {"train": 330, "val": 100}  # foto di train per classe (IP102 è molto numeroso: tokens su disco)
HEAD = "disease"
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


def select(rows, classes):
    """Righe per split: PlantVillage campionato (è facile e molto numeroso), il resto tutto."""
    rng = random.Random(0)
    idx = {"train": [], "val": [], "test": []}
    for i, r in enumerate(rows):
        if r.get(HEAD) in classes:
            idx[r["split"]].append(i)
    # tetto per (fonte, classe) fuori dalle foto di campo: i token su disco restano entro ~25 GB
    for split, n in (("train", SOURCE_CAP["train"]), ("val", SOURCE_CAP["val"])):
        if HEAD != "disease":
            break
        by = defaultdict(list)
        for i in idx[split]:
            by[(rows[i]["source"], rows[i][HEAD])].append(i)
        idx[split] = sorted(j for (src, _), v in by.items()
                            for j in (v if src in FIELD_SOURCES or len(v) <= n else rng.sample(v, n)))
    cap = TRAIN_CAP.get(HEAD)
    if cap:
        by = defaultdict(list)
        for i in idx["train"]:
            by[rows[i][HEAD]].append(i)
        idx["train"] = sorted(j for v in by.values() for j in (rng.sample(v, cap) if len(v) > cap else v))
    for split, n in (("train", PV_TRAIN), ("val", PV_VAL)):
        pv = [i for i in idx[split] if rows[i]["source"] == "plantvillage"]
        keep = set(rng.sample(pv, min(n, len(pv))))
        idx[split] = [i for i in idx[split] if rows[i]["source"] != "plantvillage" or i in keep]
    return idx


def idx_pd(rows, split):
    return [i for i, r in enumerate(rows) if r["split"] == split and r["source"] == "plantdoc" and r.get(HEAD)]


class Imgs(Dataset):
    def __init__(self, paths, tf):
        self.paths, self.tf = paths, tf

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        try:
            with Image.open(self.paths[i]) as im:
                return self.tf(im.convert("RGB")), i
        except Exception:
            return torch.zeros(3, 224, 224), i


def trunk(vit):
    def f(x):
        h = vit.norm_pre(vit._pos_embed(vit.patch_embed(x)))
        for b in vit.blocks[:SPLIT_AT]:
            h = b(h)
        return h
    return f


@torch.no_grad()
def cache_tokens(name, paths, tf, vit, seed=0):
    """Token all'ingresso del blocco SPLIT_AT, in un memmap fp16 riprendibile."""
    TOK_DIR.mkdir(parents=True, exist_ok=True)
    f, done_f = TOK_DIR / f"{name}.f16", TOK_DIR / f"{name}.done"
    shape = (len(paths), 257, 384)
    mm = np.memmap(f, dtype=np.float16, mode="r+" if f.exists() else "w+", shape=shape)
    done = int(done_f.read_text()) if done_f.exists() else 0
    if done >= len(paths):
        return mm
    torch.manual_seed(seed + done)
    run = trunk(vit)
    dl = DataLoader(Imgs(paths[done:], tf), batch_size=64, num_workers=2)
    t0 = time.time()
    for x, i in dl:
        mm[done + i.numpy()] = run(x).numpy().astype(np.float16)
        n = done + int(i.max()) + 1
        if (n // 64) % 20 == 0:
            mm.flush()
            done_f.write_text(str(n))
            print(f"  {name}: {n}/{len(paths)} ({time.time() - t0:.0f}s)", flush=True)
    mm.flush()
    done_f.write_text(str(len(paths)))
    return mm


class DiseaseBranch(nn.Module):
    """Ultimi blocchi riaddestrati + norma + lettore su [CLS, media dei token, EfficientNet]."""

    def __init__(self, vit, n_classes, eff_dim=1280, split_at=None):
        super().__init__()
        self.blocks = copy.deepcopy(vit.blocks[split_at if split_at is not None else SPLIT_AT:])
        self.norm = copy.deepcopy(vit.norm)
        self.reader = rd.Reader(384 * 2 + eff_dim, n_classes, hidden=1024)

    def forward(self, tokens, eff):
        h = self.norm(self.blocks(tokens))
        return self.reader(torch.cat([h[:, 0], h[:, 1:].mean(1), eff], dim=1))


def drop_tokens(t, p=0.25):
    n = t.shape[1] - 1
    keep = max(1, int(n * (1 - p)))
    idx = torch.rand(t.shape[0], n).argsort(1)[:, :keep] + 1
    idx = torch.cat([torch.zeros(t.shape[0], 1, dtype=torch.long), idx], 1)
    return t.gather(1, idx[..., None].expand(-1, -1, t.shape[2]))


@torch.no_grad()
def predict(model, toks, eff, bs=256):
    model.eval()
    out = []
    for i in range(0, len(eff), bs):
        out.append(model(torch.from_numpy(np.asarray(toks[i:i + bs], dtype=np.float32)), eff[i:i + bs]))
    return torch.cat(out)


def metrics(p, y, src):
    pred = p.argmax(1)
    out = {"acc": float((pred == y).float().mean()), "f1": macro_f1(y.numpy(), pred.numpy()),
           "ece": expected_calibration_error(p.numpy(), y.numpy())}
    for fs in FIELD_SOURCES:
        m = torch.tensor([s == fs for s in src])
        if m.any():
            out[fs] = float((pred[m] == y[m]).float().mean())
    return out


def score_of(m):
    """Punteggio per scegliere epoca e fusione: media tra test complessivo e foto di campo."""
    vals = [m["acc"]] + [m[fs] for fs in FIELD_SOURCES if fs in m]
    return sum(vals) / len(vals)


def main():
    global SPLIT_AT, TOK_DIR, HEAD
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", default="disease", choices=["disease", "pest"])
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--only-cache", action="store_true")
    ap.add_argument("--split-at", type=int, default=SPLIT_AT, help="primo blocco riaddestrato (12 blocchi in tutto)")
    args = ap.parse_args()
    SPLIT_AT = args.split_at
    HEAD = args.head
    TOK_DIR = TOK_DIR / f"{HEAD}_blocco{SPLIT_AT}"
    torch.set_num_threads(4)

    rows = read_manifest(ROOT / "data/processed/manifest_v2.csv")
    classes = torch.load(ROOT / f"models/ensemble_{HEAD}.pt", weights_only=False)["classes"]
    ci = {c: i for i, c in enumerate(classes)}
    idx = select(rows, set(classes))
    if os.environ.get("FT_SMOKE"):  # prova rapida del codice
        TOK_DIR = Path(os.environ["FT_SMOKE"])
        rs = random.Random(1)
        idx = {k: sorted(rs.sample(v, 300)) for k, v in idx.items()}
        for k in ("val", "test"):
            idx[k] += [i for i in idx_pd(rows, k)][:60]
    print({k: len(v) for k, v in idx.items()}, flush=True)
    paths = {k: [ROOT / "data" / rows[i]["path"] for i in v] for k, v in idx.items()}

    vit = timm.create_model(DINO, pretrained=True, num_classes=0, img_size=224).eval()
    base_tf = T.Compose([T.Resize(224, interpolation=T.InterpolationMode.BICUBIC), T.CenterCrop(224),
                         T.ToTensor(), T.Normalize(MEAN, STD)])
    aug_tf = T.Compose([T.RandomResizedCrop(224, scale=(0.45, 1.0), interpolation=T.InterpolationMode.BICUBIC),
                        T.RandomHorizontalFlip(), T.RandomVerticalFlip(0.2), T.ColorJitter(0.25, 0.25, 0.15, 0.02),
                        T.ToTensor(), T.Normalize(MEAN, STD)])
    toks = {"train0": cache_tokens("train0", paths["train"], base_tf, vit),
            "val": cache_tokens("val", paths["val"], base_tf, vit),
            "test": cache_tokens("test", paths["test"], base_tf, vit),
            "train1": cache_tokens("train1", paths["train"], aug_tf, vit, seed=1)}
    if args.only_cache:
        return

    all_paths = [ROOT / "data" / r["path"] for r in rows]
    eff_all = rd.extract_features(all_paths, EFF, ROOT / f"data/processed/features_{EFF}_224")
    eff = {k: torch.from_numpy(eff_all[v].astype(np.float32)) for k, v in idx.items()}
    y = {k: torch.tensor([ci[rows[i][HEAD]] for i in v]) for k, v in idx.items()}
    src = {k: [rows[i]["source"] for i in v] for k, v in idx.items()}

    torch.manual_seed(0)
    model = DiseaseBranch(vit, len(classes), split_at=SPLIT_AT)
    counts = torch.bincount(y["train"], minlength=len(classes)).float().clamp(min=1)
    cw = (counts.sum() / counts).sqrt()
    cw = cw / cw.mean()
    sw = torch.tensor([FIELD_W.get(s, 1.0) for s in src["train"]])
    bb = list(model.blocks.parameters()) + list(model.norm.parameters())
    opt = torch.optim.AdamW([{"params": bb, "lr": 3e-5}, {"params": model.reader.parameters(), "lr": 1e-3}],
                            weight_decay=0.05)
    bs = 64
    steps = args.epochs * (len(y["train"]) // bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[3e-5, 1e-3], total_steps=steps, pct_start=0.1)
    best, best_state = -1, None
    log = []
    # ripresa dopo un'interruzione (riavvio della macchina): stato salvato alla fine di ogni epoca
    ckpt = ROOT / f"models/{HEAD}_ft_ripresa.pt"
    sig = {"epochs": args.epochs, "split_at": SPLIT_AT, "n_train": len(y["train"]), "classes": len(classes)}
    start = 0
    if ckpt.exists():
        c = torch.load(ckpt, weights_only=False)
        if c.get("sig") == sig:
            model.load_state_dict(c["model"]); opt.load_state_dict(c["opt"]); sched.load_state_dict(c["sched"])
            best, best_state, log, start = c["best"], c["best_state"], c["log"], c["epoch"]
            torch.set_rng_state(c["rng"]); random.setstate(c["py_rng"])
            print(f"ripresa dall'epoca {start + 1}", flush=True)
    for ep in range(start, args.epochs):
        model.train()
        perm = torch.randperm(len(y["train"]))
        t0 = time.time()
        for s in range(len(perm) // bs):
            b = perm[s * bs:(s + 1) * bs].sort().values.numpy()
            view = toks["train1"] if random.random() < 0.5 else toks["train0"]
            t = drop_tokens(torch.from_numpy(np.asarray(view[b], dtype=np.float32)))
            loss = (F.cross_entropy(model(t, eff["train"][b]), y["train"][b], weight=cw,
                                    label_smoothing=0.1, reduction="none") * sw[b]).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            if s % 100 == 0:
                print(f"  epoca {ep + 1} passo {s}/{len(perm) // bs} loss={loss.item():.3f} "
                      f"({time.time() - t0:.0f}s)", flush=True)
        pv = predict(model, toks["val"], eff["val"]).softmax(1)
        mv = metrics(pv, y["val"], src["val"])
        score = score_of(mv)
        log.append({"epoch": ep + 1, **mv})
        print(f"epoca {ep + 1}: val {mv}", flush=True)
        if score > best:
            best, best_state = score, {k: v.clone() for k, v in model.state_dict().items()}
        tmp = ckpt.with_suffix(".tmp")
        torch.save({"sig": sig, "epoch": ep + 1, "model": model.state_dict(), "opt": opt.state_dict(),
                    "sched": sched.state_dict(), "best": best, "best_state": best_state, "log": log,
                    "rng": torch.get_rng_state(), "py_rng": random.getstate()}, tmp)
        tmp.replace(ckpt)
    model.load_state_dict(best_state)

    lv = predict(model, toks["val"], eff["val"])
    model.reader.temperature.fill_(1.0)
    lt = torch.zeros(1, requires_grad=True)
    o = torch.optim.LBFGS([lt], lr=0.1, max_iter=100)

    def closure():
        o.zero_grad()
        loss = F.cross_entropy(lv / lt.exp(), y["val"])
        loss.backward()
        return loss
    o.step(closure)
    temp = float(lt.exp().detach())
    model.reader.temperature.fill_(temp)

    p_ft = predict(model, toks["test"], eff["test"]).softmax(1)
    # insieme attuale sulle stesse foto di test
    dim = 384 + 1280
    dino_all = rd.extract_features(all_paths, DINO, ROOT / f"data/processed/features_{DINO}_224")
    Xt = torch.from_numpy(np.concatenate([dino_all[idx["test"]], eff_all[idx["test"]]], 1).astype(np.float32))
    Xv = torch.from_numpy(np.concatenate([dino_all[idx["val"]], eff_all[idx["val"]]], 1).astype(np.float32))
    e = torch.load(ROOT / f"models/ensemble_{HEAD}.pt", weights_only=False)
    ms = []
    for st in e["models"]:
        m = rd.Reader(dim, len(classes), hidden=1024)
        m.load_state_dict(st)
        ms.append(m.eval())

    def ens(X):
        with torch.no_grad():
            p = torch.stack([F.softmax(m(X), 1) for m in ms]).mean(0)
        return F.softmax(p.clamp_min(1e-9).log() / e["temperature"], 1)
    p_ens, pv_ens = ens(Xt), ens(Xv)
    pv_ft = (lv / temp).softmax(1)
    # peso della fusione scelto sulla validazione
    best_w, best_s = 0.0, -1
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        q = (w * pv_ft.clamp_min(1e-9).log() + (1 - w) * pv_ens.clamp_min(1e-9).log()).softmax(1)
        mv = metrics(q, y["val"], src["val"])
        s = score_of(mv)
        if s > best_s:
            best_w, best_s = w, s
    p_mix = (best_w * p_ft.clamp_min(1e-9).log() + (1 - best_w) * p_ens.clamp_min(1e-9).log()).softmax(1)
    res = {"insieme_attuale": metrics(p_ens, y["test"], src["test"]),
           "riaddestrato": metrics(p_ft, y["test"], src["test"]),
           "fusione": {**metrics(p_mix, y["test"], src["test"]), "peso_riaddestrato": best_w},
           "temperatura": temp, "epoche": log}
    for k in ("insieme_attuale", "riaddestrato", "fusione"):
        print(f"  {k:16s} " + " ".join(f"{a}={b:.4f}" for a, b in res[k].items()), flush=True)
    torch.save({"state": model.state_dict(), "classes": classes, "temperature": temp, "split_at": SPLIT_AT,
                "fusion_weight": best_w, "backbone": DINO, "head": HEAD}, ROOT / f"models/{HEAD}_ft.pt")
    json.dump(res, open(ROOT / f"models/finetune_{HEAD}.json", "w"), indent=2)
    ckpt.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
