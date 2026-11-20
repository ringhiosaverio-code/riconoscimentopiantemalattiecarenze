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
        r = Reader(dim, len(e["classes"]), hidden=1024)
        r.load_state_dict(st)
        members.append(r.eval())
    ensembles[h], temps[h] = members, e["temperature"]
    print(f"{h}: insieme di {len(members)} lettori, T={e['temperature']:.3f}")


branch, ft_w = None, 0.0
if args.disease_ft:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from finetune_disease import DiseaseBranch
    ft = torch.load(args.disease_ft, map_location="cpu", weights_only=False)
    if list(ft["classes"]) != list(ck["readers"]["disease"]["classes"]):
        raise SystemExit("disease_ft: classi diverse da quelle del checkpoint")
    branch = DiseaseBranch(net.backbones[0], len(ft["classes"]), split_at=ft["split_at"])
    branch.load_state_dict(ft["state"])
    branch.eval()
    split_at, ft_w = ft["split_at"], ft["fusion_weight"]
    print(f"disease: ramo riaddestrato dal blocco {split_at}, peso nella fusione {ft_w}")


class Web(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbones = net.backbones
        self.heads = net.heads
        self.ens_heads = ensembles
        self.ft_branch = branch

    def features(self, x):
        if self.ft_branch is None:
            return torch.cat([b(x) for b in self.backbones], dim=1), None, None
        vit, eff = self.backbones[0], self.backbones[1]
        t = vit.norm_pre(vit._pos_embed(vit.patch_embed(x)))
        for b in vit.blocks[:split_at]:
            t = b(t)
        h = t
        for b in vit.blocks[split_at:]:
            h = b(h)
        fe = eff(x)
        return torch.cat([vit.norm(h)[:, 0], fe], dim=1), t, fe

    def forward(self, x):
        f, tok, fe = self.features(x)
        outs = []
        for h in heads:
            if h in self.ens_heads:
                p = torch.stack([torch.softmax(m(f), dim=1) for m in self.ens_heads[h]]).mean(0)
                p = torch.softmax(p.clamp_min(1e-9).log() / temps[h], dim=1)
            else:
                p = torch.softmax(self.heads[h](f), dim=1)
            if h == "disease" and self.ft_branch is not None:
                pf = torch.softmax(self.ft_branch(tok, fe), dim=1)
                p = torch.softmax(ft_w * pf.clamp_min(1e-9).log() + (1 - ft_w) * p.clamp_min(1e-9).log(), dim=1)
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
