# Dataset: piano di raccolta e licenze

Questo file descrive cosa raccogliere e come. I dati grezzi **non vanno nel repository** (sono in `data/`, ignorata da git).

## Schema dei metadati per immagine

Ogni immagine ha un record con almeno questi campi:

```yaml
image_id: "2026-06-12_tom_0001"
file: "data/raw/tomato/2026-06-12_tom_0001.jpg"
plant: solanum_lycopersicum
pathogen_type: fungal           # id di pathogen_types
diseases: [tomato_late_blight]  # lista, può essere vuota
insects: []                     # id di insects, con ruolo implicito
nutrients: []                   # es. [N] o [Fe, Mg]; vuota = nessuna carenza visibile
nutrients_undetermined: false
organ: leaf                     # leaf | fruit | stem | root | flower | whole_plant
diagnosis: expert               # lab | expert | visual_only
location: "anonimizzata, es. IT-EMR-03"
date: 2026-06-12
device: smartphone
license: CC-BY-4.0
source: "nome del dataset o raccolta propria"
```

## Regole di qualità

1. **Una malattia confermata da laboratorio** ha più peso di una solo visiva. Marcare il campo `diagnosis`.
2. **Foto di campo e di laboratorio** vanno tenute separate nei report, non mescolate nella stessa metrica.
3. **Foto di piante sane** sono obbligatorie: senza di esse il modello segnala malattie ovunque.
4. **Doppia annotazione** per il 10% delle immagini, con misura dell'accordo tra annotatori (kappa di Cohen).
5. **Nessuna informazione personale** nelle immagini o nei metadati: niente volti, targhe, indirizzi precisi dei campi.

## Licenze

Ogni dataset esterno ha la sua licenza. Verificarla prima di usarlo per addestrare un modello distribuito. Registrarla in un file `data/SOURCES.md` (non versionato) con: nome, URL, licenza, data di accesso.

## Ordine di raccolta suggerito

1. Dataset pubblici per il pre-addestramento e il benchmark (PlantVillage, PlantDoc, IP102, PlantNet-300K).
2. Raccolta propria per le colture target, nelle stagioni di manifestazione dei sintomi.
3. Raccolta dedicata per le carenze, con analisi del terreno o fogliare di laboratorio come riferimento.
4. Raccolta dedicata per gli insetti utili delle colture target, anche con cattura e identificazione di un entomologo.
