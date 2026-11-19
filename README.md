# PlantCare

Sistema di riconoscimento visivo (deep learning) per piante di interesse agrario, con l'obiettivo di:

1. **riconoscere la coltura**, con priorità alle colture di maggior interesse agrario in Italia e a quelle tropicali/subtropicali presenti in Calabria;
2. **riconoscere malattie** di origine fungina, virale, da viroidi, batterica e da danni di insetti;
3. **riconoscere insetti** distinguendo gli **entomofagi** (utili) dai **fitofagi** (dannosi);
4. **stimare carenze nutrizionali** macro (N, P, K, Ca, Mg, S) e micro (Fe, Mn, Zn, Cu, B, Mo, Cl) dalle foto.

> **Avvertenza.** PlantCare è uno strumento di **supporto alla decisione**, non una diagnosi.
> Le immagini descrivono sintomi, non sempre la causa. Virus e viroidi richiedono conferma di laboratorio.
> Le carenze hanno sintomi confondibili con virosi, stress idrico e parassiti: il sistema può rispondere **"non determinabile"**.

## Colture prioritarie

- **Priorità 1 (Italia):** frumento tenero e duro, mais, vite, **olivo**, pomodoro, patata, melo, pero, pesco, ciliegio, kiwi, arancio, limone, mandarino, nocciolo, fragola, lattuga, peperone, melanzana, zucchina, cetriolo, carciofo, **aglio**, **broccolo**.
- **Priorità 2 (Calabria, tropicali/subtropicali):** bergamotto, avocado, banano, cherimoya, fico d'India.
- **Priorità 3 (interesse locale in Calabria):** **cipolla rossa di Tropea**, **peperoncino calabrese**.

Ogni malattia è descritta per **organo colpito**: foglia, frutto, fiore, infiorescenza, fusto, ramo, tronco, radice, tubero, bulbo. L'utente indica la parte colpita e il sistema ne mostra i sintomi. Le colture con poche malattie note (cherimoya, nocciolo, fico d'India) sono dichiarate come tali.

Le colture di priorità 2 e 3 hanno poche immagini pubbliche: per loro serve raccolta propria (vedi `docs/dataset.md`).

## Stato del progetto

| Area | Stato |
|---|---|
| Tassonomia (colture, agenti, malattie, insetti, nutrienti) | Versione 0.2.0 in `configs/taxonomy.yaml` |
| Pipeline dei dati (PlantVillage, IP102, manifest, duplicati, immagini corrotte) | Implementata e testata su dati sintetici |
| Addestramento multi-task (baseline) | Implementato e testato su dati sintetici |
| Metriche (F1 per classe, ECE, copertura vs accuratezza) | Implementate |
| Inferenza con astensione e avvertenze | Implementata |
| Interfaccia web e API (`/predict`) | Implementata |
| Schede per agronomi (malattie per organo, insetti, colture, carenze) | Implementate (`/api/*`), 77 malattie su 32 colture |
| Feedback degli agronomi (sì/no e correzione) | Implementato, attivo con `PLANTCARE_FEEDBACK_DIR` |
| Immagine Docker per la pubblicazione | Scritta, **non ancora costruita né provata** |
| **Baseline reale su PlantVillage e IP102** | **Non ancora eseguita**: i dati non sono stati scaricati in questo ambiente |
| Dati per carenze, viroidi, entomofagi | Da raccogliere (piano in `docs/dataset.md`) |

## Lettori ottici

L'app usa la fotocamera del telefono o del computer (oppure una foto caricata) e la passa a quattro **lettori ottici**:

| Lettore | Cosa riconosce | Dati di addestramento |
|---|---|---|
| Coltura | la specie coltivata | PlantVillage, PlantDoc, iNatAg (iNaturalist), dataset AgML per coltura |
| Malattia | malattie e danni visibili | PlantVillage (laboratorio), PlantDoc (campo), dataset AgML (vite, limone, pomodoro, melanzana, patata, cipolla, peperoncino, banano, cavolfiore, *Tuta absoluta*) |
| Insetti e acari | 102 specie di insetti dannosi | IP102 (uso accademico) |
| Carenze | macro e micro carenze | **non addestrato**: non esistono dataset di immagini di carenze verificati da analisi di laboratorio |

Ogni lettore restituisce una **probabilità calibrata** (temperature scaling sulla validazione) e l'app mostra la sua **affidabilità misurata sul test**, separata per fonte (laboratorio o campo). Sotto la soglia di confidenza il lettore risponde "non determinabile".

L'elenco dei dataset, con licenza e citazione, è in `configs/external_datasets.yaml`. Il download è riproducibile con `python -m plantcare.data.download`, l'importazione con `plantcare import-external`, l'addestramento con `plantcare train-readers`.

## Avvio rapido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Flusso completo, una volta scaricati i dataset in `data/raw/`:

```bash
plantcare check-taxonomy                       # tassonomia e copertura colture
plantcare build-manifest --check               # manifest + controlli su duplicati e immagini
plantcare train -c configs/train_baseline.yaml # baseline multi-task
plantcare serve --checkpoint models/baseline/model.pt
# poi aprire http://127.0.0.1:8000
```

## Per chi usa il sistema

- **Agronomi e tecnici:** `docs/guida-agronomi.md` spiega come leggere il risultato, quando serve il laboratorio e come inviare un feedback.
- **Validazione sul campo:** `docs/protocollo-validazione.md` definisce il protocollo per misurare le prestazioni reali.
- **Pubblicazione del servizio:** `docs/deploy.md` elenca i requisiti (modello validato, licenza, privacy, revisione scientifica).

## Struttura

```
configs/
  taxonomy.yaml          fonte unica di verità: classi e id stabili
  label_maps.yaml        etichette grezze dei dataset -> id della tassonomia
  datasets.yaml          percorsi dei dataset per build-manifest
  train_baseline.yaml    iperparametri della baseline
src/plantcare/
  taxonomy.py            caricamento e validazione della tassonomia
  labelmap.py            mappatura delle etichette dei dataset
  data/pipeline.py       scansione, split, duplicati, immagini corrotte, manifest
  model.py               backbone condiviso e teste multi-task con perdita mascherata
  train.py               addestramento e report
  metrics.py             F1, ECE, copertura vs accuratezza
  predict.py             inferenza con astensione e avvertenze
  api.py                 interfaccia web e endpoint /predict
  kb.py                  schede per agronomi (malattie, insetti, colture, carenze)
  cli.py                 comando `plantcare`
metadata/                 mappa dei gruppi foglia di PlantVillage (per lo split senza fuga di dati)
Dockerfile                immagine per la pubblicazione (vedi docs/deploy.md)
tests/                   test unitari e di integrazione (dati sintetici)
docs/                    ricerca, dataset, architettura
```

## Principi di progetto

- **Multi-task.** Un backbone condiviso con teste per coltura, malattia e fitofago. Vedi `docs/architettura.md`.
- **Gli id non si rinominano.** Modelli e dataset dipendono dagli id della tassonomia.
- **Fonti verificate.** Ogni citazione in `docs/ricerca.md` riporta lo stato della verifica.
- **Onestà sull'incertezza.** Probabilità, soglia di astensione e avvertenze per virosi e viroidi.
- **Validazione in campo.** I risultati su dati di laboratorio sovrastimano le prestazioni reali. Serve un test di campo separato.

## Roadmap

1. Scaricare PlantVillage e IP102, costruire il manifest e lanciare la prima baseline reale.
2. Far revisionare tassonomia, malattie e sintomi da un fitopatologo o agronomo.
3. Raccogliere dati per le colture di priorità 2 e per le lacune (carenze, viroidi, entomofagi).
4. Costruire un set di test di campo, separato per località e stagione.
5. Passare a DINOv2 come backbone e confrontarlo con la baseline.

## Licenza

Il codice e la documentazione sono rilasciati sotto **Apache License 2.0** (file `LICENSE`).

Attenzione: la licenza **non** copre i dataset di addestramento né i pesi del modello addestrati su di essi. Per IP102 l'uso commerciale richiede il permesso dell'autore, e la licenza di PlantVillage va verificata alla fonte. Vedi `NOTICE`.
