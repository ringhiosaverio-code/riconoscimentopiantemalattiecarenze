"""Esporta i lettori ottici in ONNX per l'app nel browser (senza server).

- parte dal checkpoint dei lettori (DINOv2 + EfficientNet-B0);
- esclude il lettore degli insetti (IP102: solo uso accademico) salvo --with-pest;
- uscite: probabilità calibrate per lettore (softmax dei logit divisi per la temperatura);
- con --ensemble-dir usa, per i lettori che lo hanno, l'insieme di 5 lettori calibrato
  (models/ensemble_<lettore>.pt, da scripts/improve_readers.py) al posto del lettore singolo;
- quantizzazione dinamica a 8 bit per canale dei pesi delle MatMul (onnxruntime), lettori esclusi.
"""
import argparse
from pathlib import Path

import torch
import torch.nn as nn

from plantcare.readers import load_readers

ap = argparse.ArgumentParser()
ap.add_argument("--checkpoint", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--with-pest", action="store_true")
ap.add_argument("--ensemble-dir", default=None, help="cartella con ensemble_<lettore>.pt")
ap.add_argument("--disease-ft", default=None,
                help="models/disease_ft.pt (scripts/finetune_disease.py): ramo con gli ultimi blocchi riaddestrati")
ap.add_argument("--pest-ft", default=None, help="models/pest_ft.pt: ramo riaddestrato per gli insetti")
ap.add_argument("--bioclip", action="store_true",
                help="aggiunge l'estrattore BioCLIP (ViT-B/16): i lettori con ingresso più largo ricevono anche le sue caratteristiche")
args = ap.parse_args()

net, ck = load_readers(Path(args.checkpoint))
heads = [h for h in ("plant", "disease", "deficiency", "pest") if h in net.heads and (h != "pest" or args.with_pest)]


from plantcare.readers import Reader

dim = sum(b.num_features for b in net.backbones)
ensembles, temps = nn.ModuleDict(), {}
for h in heads:
    f = Path(args.ensemble_dir) / f"ensemble_{h}.pt" if args.ensemble_dir else None
    if not f or not f.exists():
        continue
    e = torch.load(f, map_location="cpu", weights_only=False)
    if list(e["classes"]) != list(ck["readers"][h]["classes"]):
        raise SystemExit(f"{h}: classi dell'insieme diverse da quelle del checkpoint")
    members = nn.ModuleList()
    for st in e["models"]:
        r = Reader(st["net.0.weight"].shape[0], len(e["classes"]), hidden=1024)
        r.load_state_dict(st)
        members.append(r.eval())
    ensembles[h], temps[h] = members, e["temperature"]
    print(f"{h}: insieme di {len(members)} lettori, T={e['temperature']:.3f}")


import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finetune_disease import DiseaseBranch  # noqa: E402

branches, ft_w, split_of = nn.ModuleDict(), {}, {}
for h, f in (("disease", args.disease_ft), ("pest", args.pest_ft)):
    if not f or h not in heads:
        continue
    ft = torch.load(f, map_location="cpu", weights_only=False)
    if list(ft["classes"]) != list(ck["readers"][h]["classes"]):
        raise SystemExit(f"{h}: classi del ramo riaddestrato diverse da quelle del checkpoint")
    b = DiseaseBranch(net.backbones[0], len(ft["classes"]), split_at=ft["split_at"])
    b.load_state_dict(ft["state"])
    branches[h], ft_w[h], split_of[h] = b.eval(), ft["fusion_weight"], ft["split_at"]
    print(f"{h}: ramo riaddestrato dal blocco {ft['split_at']}, peso nella fusione {ft['fusion_weight']}")


bioclip = None
if args.bioclip:
    import open_clip
    bioclip = open_clip.create_model_and_transforms("hf-hub:imageomics/bioclip")[0].visual.eval()
IMNET = (torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1), torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))
CLIPN = (torch.tensor([0.48145466, 0.4578275, 0.40821073]).view(1, 3, 1, 1),
         torch.tensor([0.26862954, 0.26130258, 0.27577711]).view(1, 3, 1, 1))


class Web(nn.Module):
    def __init__(self):
        super().__init__()
        self.bioclip = bioclip
        self.backbones = net.backbones
        self.heads = net.heads
        self.ens_heads = ensembles
        self.ft_branches = branches

    def forward(self, x):
        vit, eff = self.backbones[0], self.backbones[1]
        t = vit.norm_pre(vit._pos_embed(vit.patch_embed(x)))
        tok_at = {}
        for i, b in enumerate(vit.blocks):
            if i in split_of.values():
                tok_at[i] = t
            t = b(t)
        fe = eff(x)
        f = torch.cat([vit.norm(t)[:, 0], fe], dim=1)
        fb = None
        if self.bioclip is not None:
            # stessa foto, normalizzata come vuole CLIP; caratteristiche unitarie x10 (come in addestramento)
            xc = ((x * IMNET[1] + IMNET[0]) - CLIPN[0]) / CLIPN[1]
            fb = self.bioclip(xc)
            fb = fb / fb.norm(dim=1, keepdim=True) * 10
            f_tutto = torch.cat([f, fb], dim=1)
        outs = []
        for h in heads:
            if h in self.ens_heads:
                p = torch.stack([torch.softmax(m(f_tutto if fb is not None and m.net[0].weight.shape[0] > f.shape[1] else f), dim=1)
                                 for m in self.ens_heads[h]]).mean(0)
                p = torch.softmax(p.clamp_min(1e-9).log() / temps[h], dim=1)
            else:
                p = torch.softmax(self.heads[h](f), dim=1)
            if h in self.ft_branches:
                pf = torch.softmax(self.ft_branches[h](tok_at[split_of[h]], fe), dim=1)
                w = ft_w[h]
                p = torch.softmax(w * pf.clamp_min(1e-9).log() + (1 - w) * p.clamp_min(1e-9).log(), dim=1)
            outs.append(p)
        return tuple(outs)


m = Web().eval()
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
fp32 = out.with_name(out.stem + "_fp32.onnx")
torch.onnx.export(m, torch.randn(1, 3, 224, 224), fp32, input_names=["image"], output_names=list(heads),
                  dynamic_axes={"image": {0: "batch"}, **{h: {0: "batch"} for h in heads}}, opset_version=17,
                  dynamo=False)
import onnx
from onnxruntime.quantization import QuantType, quantize_dynamic

# Quantizzazione per canale delle sole MatMul/Gemm, lettori finali esclusi: la quantizzazione
# semplice (per tensore) faceva scendere la malattia su PlantVillage dal 99% al 77%;
# questa mantiene l'accuratezza del modello pieno (verificato sulle foto di test).
graph = onnx.load(str(fp32)).graph
head_nodes = [n.name for n in graph.node if n.op_type in ("MatMul", "Gemm")
              and ("heads" in n.name or any("heads" in i for i in n.input))]
quantize_dynamic(str(fp32), str(out), weight_type=QuantType.QInt8, per_channel=True,
                 nodes_to_exclude=head_nodes, op_types_to_quantize=["MatMul", "Gemm"])
print("heads:", heads)
print("fp32 MB:", round(fp32.stat().st_size / 1e6, 1), "int8 MB:", round(out.stat().st_size / 1e6, 1))
