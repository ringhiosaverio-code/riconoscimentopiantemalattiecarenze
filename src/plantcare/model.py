"""Modello multi-task: un backbone condiviso e una testa di classificazione per compito.

Le etichette assenti per un'immagine sono marcate con IGNORE_INDEX e non
contribuiscono alla perdita. Così una stessa rete può imparare da dataset
diversi (PlantVillage per malattie, IP102 per fitofagi) senza etichette finte.
"""

from __future__ import annotations

import timm
import torch
import torch.nn as nn
import torch.nn.functional as F

IGNORE_INDEX = -100


class MultiTaskNet(nn.Module):
    def __init__(
        self,
        backbone: str,
        head_sizes: dict[str, int],
        pretrained: bool = False,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        if not head_sizes:
            raise ValueError("Serve almeno una testa")
        self.backbone_name = backbone
        self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0)
        feat = self.backbone.num_features
        self.heads = nn.ModuleDict({
            name: nn.Sequential(nn.Dropout(dropout), nn.Linear(feat, n))
            for name, n in head_sizes.items()
        })

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        feats = self.backbone(x)
        return {name: head(feats) for name, head in self.heads.items()}


def multitask_loss(
    outputs: dict[str, torch.Tensor],
    targets: dict[str, torch.Tensor],
    weights: dict[str, float] | None = None,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Somma pesata delle cross-entropy delle teste che hanno almeno un'etichetta nel batch."""
    weights = weights or {}
    any_logits = next(iter(outputs.values()))
    total = any_logits.new_zeros(())
    parts: dict[str, float] = {}
    for name, logits in outputs.items():
        target = targets[name]
        if (target != IGNORE_INDEX).sum() == 0:
            continue
        loss = F.cross_entropy(logits, target, ignore_index=IGNORE_INDEX)
        total = total + weights.get(name, 1.0) * loss
        parts[name] = float(loss.detach())
    return total, parts
