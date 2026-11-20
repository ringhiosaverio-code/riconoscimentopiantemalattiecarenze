# Come migliorare la rete neurale

Il dato da cui partire: sulle foto di laboratorio (PlantVillage) i lettori arrivano al 99%, sulle foto di campo (PlantDoc) la malattia è al 76% e la coltura all'89-90%. Il divario dipende dai dati, non dall'architettura. Le azioni sono ordinate per impatto atteso.

## 1. Foto di campo calabresi e siciliane (impatto più alto)

**Strumento già pronto nell'app**: sotto ogni risultato c'è "Aiuta a migliorare". L'agronomo indica la risposta corretta, l'organo, la provincia e il tipo di diagnosi, e dà il consenso. I contributi restano nel telefono e si inviano dalla scheda Info come file JSON.

**Come si usano**:

```bash
plantcare import-contributi cartella_con_i_file_json/
plantcare import-external
plantcare train-readers          # calcola solo le caratteristiche delle foto nuove
```

- Il 30% dei contributi va in un **test di campo** fisso, assegnato in modo stabile per contributo: è la misura di riferimento per la Calabria e la Sicilia.
- Le foto con diagnosi di laboratorio pesano di più nelle decisioni; quelle solo osservate servono per l'addestramento ma vanno riportate a parte nelle metriche.
- Le foto con risposta "non determinabile" sono le più utili (apprendimento attivo): l'app apre il modulo in automatico in quei casi.

**Obiettivo minimo per la prima campagna**: 100 foto per malattia principale di olivo, agrumi (incluso bergamotto), vite, pomodoro, cipolla di Tropea e peperoncino, da almeno 3 aziende, seguendo `docs/protocollo-raccolta-foto.md`.

## 2. Carenze verificate da laboratorio

Il lettore delle carenze riconosce solo calcio, eccesso di azoto e carenza generica, con pochi esempi. Per i singoli nutrienti servono prove in vaso con omissione controllata (un elemento per volta) e analisi fogliare come riferimento (vedi `docs/dataset.md`).

## 3. Fine-tuning degli estrattori (serve una GPU)

Oggi gli estrattori (DINOv2, EfficientNet-B0) sono congelati e si addestrano solo i lettori. Con una GPU:
- sbloccare gli ultimi blocchi di DINOv2 e addestrare con le foto di campo pesate di più;
- provare DINOv2-B al posto di ViT-S;
- aumentare i dati con ritagli casuali, rotazioni e variazioni di luce, che sulle CPU disponibili non è praticabile.

## 4. Miglioramenti già misurabili senza nuovi dati

Provati sulle caratteristiche in cache (`scripts/improve_readers.py`), sullo stesso test:

| Lettore | Variante | Test | Campo PlantDoc | Campo iNat | Errore di calibrazione |
|---|---|---|---|---|---|
| Coltura | un lettore | 98,5% | 88,9% | 79,3% | 17% |
| Coltura | foto di campo pesate ×3 | 98,4% | 88,5% | 77,9% | 17% |
| Coltura | **insieme di 5, calibrato** | 98,5% | **90,0%** | **79,7%** | **0,3%** |
| Malattia | un lettore | 96,1% | 76,3% | – | 20% |
| Malattia | foto di campo pesate ×3 | 96,2% | 77,6% | – | 21% |
| Malattia | **insieme di 5, calibrato** | 96,2% | **78,1%** | – | **0,6%** |
| Carenze | un lettore | 99,3% | – | – | 30% |
| Carenze | **insieme di 5, calibrato** | 99,3% | – | – | **0,4%** |

L'errore di calibrazione dei singoli lettori qui è senza temperatura; quello pubblicato prima era già calibrato (sotto l'1%).

L'insieme rispetta le regole qui sotto ed è nell'app pubblicata. Verifica sul modello web quantizzato, con la stessa preparazione della foto del browser: PlantDoc coltura 91,1% (prima 90,2%), malattia 78,0% (prima 76,3%), PlantVillage malattia 98,7% (prima 98,3%). Costo: il modello passa da 45 a 66 MB.

Ricostruzione:

```bash
PYTHONPATH=src python scripts/improve_readers.py
PYTHONPATH=src python scripts/export_web_model.py --checkpoint models/readers_.../readers.pt --out /tmp/web/plantcare.onnx --ensemble-dir models
PYTHONPATH=src python scripts/build_web.py --model /tmp/web/plantcare.onnx --ort-dist <onnxruntime-web/dist> --improve-results models/improve_results.json
```

## 5. Ramo riaddestrato per le malattie (ultimi blocchi di DINOv2, su CPU)

`scripts/finetune_disease.py` riaddestra gli ultimi blocchi dell'estrattore solo per il lettore delle malattie (token in cache su disco, aumenti di dati, token oscurati al 25%, foto di campo pesate ×3) e fonde il risultato con l'insieme di 5 lettori (peso scelto sulla validazione). Nell'app è un ramo separato: coltura, carenze e insetti usano l'estrattore originale.

Prima versione (blocchi 10-11, 5 epoche, stessi dati di prima), sullo stesso test:

| Malattia | Test | Macro-F1 | Campo PlantDoc |
|---|---|---|---|
| Insieme di 5 lettori | 96,2% | 0,906 | 78,0% |
| Ramo riaddestrato | 95,5% | 0,905 | 79,8% |
| **Fusione (pubblicata)** | **96,5%** | **0,917** | **80,0%** |

Modello web quantizzato, stessa preparazione della foto del browser: PlantDoc malattia 80,7% (prima 78,0%), coltura invariata.

In corso: seconda versione con i nuovi dataset (AppleLeaf9, CitrusUAT, agrumi frutti e foglie, susino, melograno, fico, patata in campo, ortaggi del Bangladesh, frutti di melanzana) e 3 blocchi riaddestrati (`scripts/riaddestra_tutto.sh`).

## Regole per accettare un nuovo modello

Un nuovo modello sostituisce quello pubblicato solo se:
1. sul **test di campo** (PlantDoc e contributi) non peggiora nessun lettore e migliora almeno la malattia;
2. l'errore di calibrazione resta sotto il 3%;
3. sul test complessivo non perde più di 1 punto;
4. i test automatici passano e la versione web (quantizzata) conferma le stesse misure.

## Misure da riportare a ogni ciclo

- accuratezza e macro-F1 per lettore, separate per fonte (laboratorio, campo, contributi);
- per i contributi: separate per provincia e per tipo di diagnosi (laboratorio, tecnico, osservazione);
- copertura contro accuratezza alle soglie 0,5 / 0,7 / 0,9.
