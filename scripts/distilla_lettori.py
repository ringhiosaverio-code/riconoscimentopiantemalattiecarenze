"""Distillazione: pochi lettori "allievi" che imitano l'insieme di molti lettori, per un modello più leggero.

Ogni allievo ha la stessa forma di un lettore e impara le probabilità dell'insieme (temperatura 2) insieme
alle etichette vere, con gli stessi pesi delle foto di campo. Confronto sulle stesse foto di prova, per fonte.
Malattie e insetti sulle caratteristiche attuali + BioCLIP (models/vN), coltura e carenze su quelle attuali.

Uso: PYTHONPATH=src python scripts/distilla_lettori.py [--allievi 2]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import improve_readers as ir  # noqa: E402
import estrai_bioclip as eb  # noqa: E402
from plantcare import readers as rd  # noqa: E402
from plantcare.metrics import macro_f1  # noqa: E402

OUT = ROOT / "models" / "vN_distillato"
TESTE = []


def carica(p, dim):
    ck = torch.load(p, map_location="cpu", weights_only=False)
    ms = []
    for st in ck["models"]:
        m = rd.Reader(st["net.0.weight"].shape[0], len(ck["classes"]), hidden=1024); m.load_state_dict(st); m.eval(); ms.append(m)
    return ck, ms


def allievo(hd, dim, teacher_p, seed, epochs=40, T=2.0, alpha=0.7):
    torch.manual_seed(seed)
    r = rd.Reader(dim, len(hd.classes), hidden=1024)
    counts = torch.bincount(hd.y["train"], minlength=len(hd.classes)).float().clamp(min=1)
    cw = (counts.sum() / counts).sqrt(); cw = cw / cw.mean()
    sw = torch.tensor([ir.FIELD.get(s, 1.0) for s in hd.sources["train"]])
    X, y = hd.X["train"], hd.y["train"]
    opt = torch.optim.AdamW(r.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    g = torch.Generator().manual_seed(seed)
    best, state, bad = -1, None, 0
    for _ in range(epochs):
        r.train(); perm = torch.randperm(len(X), generator=g)
        for i in range(0, len(X), 512):
            b = perm[i:i + 512]
            out = r(X[b])
            kd = (F.kl_div(F.log_softmax(out / T, 1), teacher_p[b], reduction="none").sum(1) * T * T)
            ce = F.cross_entropy(out, y[b], weight=cw, label_smoothing=0.05, reduction="none")
            loss = ((alpha * kd + (1 - alpha) * ce) * sw[b]).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step(); r.eval()
        with torch.no_grad():
            s = macro_f1(hd.y["val"].numpy(), r(hd.X["val"]).argmax(1).numpy())
        if s > best: best, state, bad = s, {k: v.clone() for k, v in r.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 6: break
    r.load_state_dict(state)
    return r


def per_fonte(pt, hd):
    pred, y, src = pt.argmax(1).numpy(), hd.y["test"].numpy(), np.array(hd.sources["test"])
    out = {"tutte": round(float((pred == y).mean()), 4)}
    for s in sorted(set(src)):
        m = src == s
        if m.sum() >= 20:
            out[s] = round(float((pred[m] == y[m]).mean()), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allievi", type=int, default=2)
    ap.add_argument("--teste", default="", help="es. plant,deficiency (vuoto = tutte)")
    args = ap.parse_args()
    global TESTE
    TESTE = [t for t in args.teste.split(",") if t]
    rows, feats = ir.load()
    idx = eb.selezione(rows)
    sub = [rows[i] for i in idx]
    d = np.load(ROOT / "data/processed/features_bioclip_224.npz", allow_pickle=True)["d"].item()
    fb = np.stack([d[r["path"]] for r in sub]).astype(np.float32)
    fb = fb / np.linalg.norm(fb, axis=1, keepdims=True) * 10
    X_n = np.concatenate([feats[idx], fb], 1)
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for head, rws, X, src_ens in (("disease", sub, X_n, "models/vN/ensemble_disease.pt"), ("pest", sub, X_n, "models/vN/ensemble_pest.pt"),
                                   ("plant", rows, feats, "models/vM/ensemble_plant.pt"), ("deficiency", rows, feats, "models/vM/ensemble_deficiency.pt")):
        if TESTE and head not in TESTE:
            continue
        ck, ens = carica(ROOT / src_ens, X.shape[1])
        if head in ("plant", "deficiency"):  # solo le classi del lettore pubblicato (dati nuovi con colture in più)
            noti = set(ck["classes"])
            rws = [dict(r, **{head: r[head] if r.get(head) in noti else ""}) for r in rws]
        hd = rd.prepare_head(rws, X, head)
        assert list(ck["classes"]) == list(hd.classes), head
        with torch.no_grad():
            tp = F.softmax(ir.probs(ens, hd.X["train"]).clamp_min(1e-9).log() / 2.0, 1)
        studs = [allievo(hd, X.shape[1], tp, 1000 + s) for s in range(args.allievi)]
        pv = ir.probs(studs, hd.X["val"]); t = ir.calibrate(pv, hd.y["val"])
        ps = F.softmax(ir.probs(studs, hd.X["test"]).clamp_min(1e-9).log() / t, 1)
        pe = F.softmax(ir.probs(ens, hd.X["test"]).clamp_min(1e-9).log() / ck["temperature"], 1)
        a, b = per_fonte(pe, hd), per_fonte(ps, hd)
        print(f"== {head}: insieme di {len(ens)} contro {len(studs)} allievi", flush=True)
        for k in a:
            print(f"   {k:16s} insieme={a[k]}  allievi={b.get(k)}", flush=True)
        res[head] = {"insieme": a, "allievi": b}
        torch.save({"models": [m.state_dict() for m in studs], "temperature": t, "classes": hd.classes}, OUT / f"ensemble_{head}.pt")
    old = json.load(open(OUT / "confronto.json")) if (OUT / "confronto.json").exists() else {}
    old.update(res)
    json.dump(old, open(OUT / "confronto.json", "w"), indent=1)


if __name__ == "__main__":
    main()
