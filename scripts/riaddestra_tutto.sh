#!/bin/bash
# Riaddestramento completo con i nuovi dati (eseguito in background, un passo dopo l'altro).
cd "$(dirname "$0")/.."
export PYTHONPATH=src
log() { echo "[$(date -u +%H:%M)] $*"; }
log "attendo la fine del primo riaddestramento"
while pgrep -f finetune_disease >/dev/null; do sleep 30; done
mkdir -p models/v1
cp models/disease_ft.pt models/finetune_disease.json models/v1/ 2>/dev/null
cp models/ensemble_*.pt models/improve_results.json models/v1/
cp -r "models/readers_vit_small_patch14_dinov2+efficientnet_b0" models/v1/readers
log "primo riaddestramento: $(python3 -c 'import json;d=json.load(open("models/finetune_disease.json"));print({k:d[k] for k in ("insieme_attuale","riaddestrato","fusione")})' 2>&1)"
rm -rf data/processed/ft_tokens
python3 -c "from pathlib import Path; from plantcare import readers as rd; from plantcare.data.pipeline import read_manifest; R=Path('.').resolve(); p=[R/'data'/r['path'] for r in read_manifest(R/'data/processed/manifest_v2.csv')]; [rd.extract_features(p,b,R/f'data/processed/features_{b}_224') for b in ('efficientnet_b0','vit_small_patch14_dinov2.lvd142m')]" || { log "ERRORE estrazione"; exit 1; }
log "lettori singoli (train-readers)"
python3 -m plantcare.cli train-readers || { log "ERRORE train-readers"; exit 1; }
log "insiemi di 5 lettori"
python3 scripts/improve_readers.py plant disease deficiency pest --solo-insieme || { log "ERRORE insiemi"; exit 1; }
log "riaddestramento dei blocchi 9-11 per le malattie"
python3 scripts/finetune_disease.py --epochs 6 --split-at 9 || { log "ERRORE riaddestramento"; exit 1; }
log "PIPELINE FINITA"
