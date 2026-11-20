#!/bin/bash
# Riaddestramento completo con le foto di campo (PlantWild, CCMT, peperone) e ramo per gli insetti.
cd "$(dirname "$0")/.."
export PYTHONPATH=src
log() { echo "[$(date -u +%H:%M)] $*"; }
python3 -c "from pathlib import Path; from plantcare import readers as rd; from plantcare.data.pipeline import read_manifest; R=Path('.').resolve(); p=[R/'data'/r['path'] for r in read_manifest(R/'data/processed/manifest_v2.csv')]; [rd.extract_features(p,b,R/f'data/processed/features_{b}_224') for b in ('efficientnet_b0','vit_small_patch14_dinov2.lvd142m')]" || { log "ERRORE estrazione"; exit 1; }
log "lettori singoli (train-readers)"
python3 -m plantcare.cli train-readers || { log "ERRORE train-readers"; exit 1; }
log "insiemi di 5 lettori"
python3 scripts/improve_readers.py plant disease deficiency pest --solo-insieme || { log "ERRORE insiemi"; exit 1; }
log "riaddestramento dei blocchi 9-11 per le malattie"
python3 scripts/finetune_disease.py --head disease --epochs 6 --split-at 9 || { log "ERRORE malattie"; exit 1; }
log "malattie: $(python3 -c 'import json;d=json.load(open("models/finetune_disease.json"));print({k:d[k] for k in ("insieme_attuale","riaddestrato","fusione")})')"
rm -rf data/processed/ft_tokens/disease_blocco9
log "riaddestramento dei blocchi 9-11 per gli insetti"
python3 scripts/finetune_disease.py --head pest --epochs 5 --split-at 9 || { log "ERRORE insetti"; exit 1; }
log "insetti: $(python3 -c 'import json;d=json.load(open("models/finetune_pest.json"));print({k:d[k] for k in ("insieme_attuale","riaddestrato","fusione")})')"
rm -rf data/processed/ft_tokens/pest_blocco9
log "PIPELINE FINITA"
