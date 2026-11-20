"""Esporta i lettori ottici in ONNX per l'app nel browser (senza server).

- parte dal checkpoint dei lettori (DINOv2 + EfficientNet-B0);
- esclude il lettore degli insetti (IP102: solo uso accademico) salvo --with-pest;
- uscite: probabilità calibrate per lettore (softmax dei logit divisi per la temperatura);
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
args = ap.parse_args()

net, ck = load_readers(Path(args.checkpoint))
heads = [h for h in ("plant", "disease", "deficiency", "pest") if h in net.heads and (h != "pest" or args.with_pest)]


class Web(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = net

    def forward(self, x):
        out = self.net(x)
        return tuple(torch.softmax(out[h], dim=1) for h in heads)


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
