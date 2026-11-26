# PlantCare

**Apri l'app:** https://ringhiosaverio-code.github.io/riconoscimentopiantemalattiecarenze/ (funziona da telefono: il modello gira nel browser, la foto non lascia il dispositivo).

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
| Malattia | malattie e danni visibili | PlantVillage (laboratorio), PlantDoc, PlantWild e FieldVitis (campo), dataset AgML (vite, limone, pomodoro, melanzana, patata, cipolla, peperoncino, banano, cavolfiore, *Tuta absoluta*), iNaturalist (malattie della Calabria), DiaMOS (pero in campo), virus della vite, poche foto da letteratura ed EPPO per il mal secco degli agrumi |
| Insetti e acari | 102 specie di insetti dannosi | IP102 (uso accademico) |
| Carenze | sintomi di carenza, carenza di calcio, eccesso di azoto | dataset AgML di limone, peperoncino e pomodoro (etichette degli autori; il nutriente è indicato solo per calcio e azoto) |

**Risultati** (dettagli in `docs/lettori-ottici.md`): sulle foto di campo il lettore della malattia raggiunge il 76% (PlantDoc), quello della coltura il 79-89%, quello degli insetti il 74% (IP102). Su foto di laboratorio (PlantVillage) si arriva al 99%: la differenza indica che servono più foto di campo.

Ogni lettore restituisce una **probabilità calibrata** (temperature scaling sulla validazione) e l'app mostra la sua **affidabilità misurata sul test**, separata per fonte (laboratorio o campo). Sotto la soglia di confidenza il lettore risponde "non determinabile".

L'elenco dei dataset, con licenza e citazione, è in `configs/external_datasets.yaml`. Il download è riproducibile con `python -m plantcare.data.download`, l'importazione con `plantcare import-external`, l'addestramento con `plantcare train-readers`.

## Quiz

La scheda **Quiz** dell'app mostra una foto a caso e quattro risposte, una sola corretta. Le categorie sono colture, malattie e danni, insetti e acari, carenze, oppure tutte mescolate.
- Le foto vengono dai dataset scientifici usati per l'addestramento, con l'etichetta dei loro autori.
- Le risposte sbagliate sono scelte tra le classi della stessa categoria; per le malattie, quando possibile, tra quelle della stessa coltura.
- La risposta corretta resta sul server fino alla risposta, e l'immagine viene servita senza esporre il percorso del file.
- Dopo la risposta compare la spiegazione dalla scheda: agente, sintomi, organi colpiti, avviso di laboratorio. Se la risposta è sbagliata, l'app spiega perché: come distinguere le malattie simili (`configs/quiz_tips.yaml`), causa diversa, sintomi a confronto.

Nell'app del browser il quiz ha circa 5.200 foto, con **la Calabria in primo piano**: 8 domande su 10 riguardano colture, insetti e malattie presenti nelle norme di difesa integrata della Regione Calabria (Disciplinare 2026), e c'è la categoria "Solo Calabria". Le fonti:
- fino a 30 foto per coltura, malattia o carenza da PlantDoc e dai dataset Project-AgML (CC BY 4.0);
- circa 1.900 foto da iNaturalist (osservazioni con identificazione confermata dalla comunità, licenze CC0, CC BY o CC BY-NC, autore e link all'osservazione sotto ogni foto) di olivo, agrumi, vite e altre arboree, e di 44 insetti e 15 malattie citati nel Disciplinare, come mosca delle olive, cocciniglie degli agrumi, occhio di pavone e rogna dell'olivo (`configs/quiz_calabria.yaml`, `scripts/import_inat_quiz.py`);
- per gli insetti di IP102 (Wu et al. 2019, **solo per uso accademico**, indicato sotto ogni foto) 20 foto per quelli citati nel Disciplinare e 6 per gli altri.

Le risposte sbagliate tornano più spesso (4 domande su 10 sono di ripasso) finché non si risponde giusto. Dopo ogni domanda su malattie e insetti c'è una scheda in sintesi: nome scientifico, ordine e famiglia, causa, colture, se serve il laboratorio, se è regolamentato, dove compare nelle norme di difesa della Calabria. Le foto già viste tornano solo dopo aver visto tutte le altre. Per radici, tuberi e bulbi non sono stati trovati dataset ripubblicabili: servono le foto raccolte con l'app.

Nella versione con server il quiz è attivo quando ci sono le immagini e il manifest (`data/processed/manifest_v2.csv`, oppure `PLANTCARE_QUIZ_MANIFEST` e `PLANTCARE_QUIZ_DATA`).

## Consigli di difesa

La scheda **Consigli** prepara una ricetta come farebbe un tecnico della difesa integrata. Si scelgono:
- coltura;
- malattia o parassita;
- fase della coltura;
- situazione: prevenzione, primi sintomi o attacco in corso; per i parassiti, monitoraggio, forme giovani o infestazione.

Si possono indicare anche:
- giorni alla raccolta;
- produzione biologica;
- rispetto del Disciplinare;
- ultimo prodotto usato.

L'app mette in ordine i prodotti Gowan registrati e mostra perché. Le regole tengono conto di:
- posizionamento per fase nei programmi Gowan;
- tipo di azione scritto in etichetta;
- preferenza per i mezzi biologici e selettivi;
- alternanza dei gruppi FRAC e IRAC;
- esclusioni per fioritura e api, intervallo di sicurezza, stadi BBCH, Disciplinare della Calabria e stato UE delle
  sostanze.

La ricetta contiene:
- dose per ettolitro e per ettaro;
- quantità per la superficie e per la botte;
- numero massimo di trattamenti e intervallo;
- limiti del Disciplinare;
- rame metallo;
- coadiuvante MAGO;
- alternanza dei prodotti;
- concimi e biostimolanti facoltativi.

Sono **regole scritte con le loro fonti**, non una rete neurale (`configs/difesa/consigli_regole.yaml`, `app/consigli.js`).
Dettagli in [docs/consigli.md](docs/consigli.md).

## Preparazione della botte

La scheda **Botte** aiuta a preparare la miscela in tre passi:
1. la botte;
2. i prodotti;
3. il calcolo.

I prodotti si scelgono dal **catalogo Gowan**. Formulazione, tipo, contenuto di rame e, scelto l'uso registrato
sulla coltura, dose e limiti di etichetta si compilano da soli. Per i prodotti di altre aziende si scrivono i dati
dell'etichetta.
- **Proporzioni**: dal volume della botte e dalla dose di etichetta (per ettolitro, per ettaro o in percentuale) calcola quanto prodotto mettere e quanta superficie copre la botte.
- **Controlli**: segnala se la dose supera la massima di etichetta, per ettolitro o, con il volume d'acqua indicato, per ettaro. Per i rameici calcola i kg di rame metallo per ettaro e li confronta con i limiti del Disciplinare calabrese (28 kg/ha in 7 anni, media consigliata 4 kg/ha all'anno).
- **Miscibilità**: istruzioni numerate per caricare la botte, nell'ordine per tipo di formulazione. Segnala le incompatibilità documentate (zolfo con olio minerale e con prodotti alcalini, polisolfuro con olio), gli avvisi di temperatura e la prova in barattolo.

Le regole e le loro fonti sono in `configs/mixing_rules.yaml`. **Non è una rete neurale**: le dosi devono essere
esatte e derivare dall'etichetta autorizzata, che prevale su qualunque calcolo.

Per la malattia riconosciuta, il referto mostra:
- le sostanze ammesse dal Disciplinare di difesa integrata della Regione Calabria;
- i limiti d'uso;
- le sostanze uscite dall'elenco;
- quelle non più approvate nell'UE;
- i prodotti Gowan registrati, in ordine di preferenza, con il collegamento alla ricetta.

## Norme aggiornate in automatico

`scripts/aggiorna_norme.py` fa questi controlli:
- cerca sul sito ARSAC i nuovi Disciplinari della Calabria;
- scarica lo stato delle sostanze attive dalla banca dati UE dei pesticidi;
- se richiesto, rilegge pagine ed etichette Gowan;
- ricostruisce i dati di difesa dell'app.

Il flusso `.github/workflows/aggiorna-norme.yml` lo esegue ogni giorno (le etichette Gowan il lunedì). Se qualcosa cambia apre una pull request
con il riepilogo, che una persona controlla prima di pubblicare.

## App nel browser (GitHub Pages)

`index.html` e la cartella `app/` sono l'app statica pubblicata su GitHub Pages:
- lettori di coltura, malattia e carenze con ONNX Runtime Web (modello quantizzato a 8 bit per canale, circa 76 MB, accuratezza uguale al modello pieno sulle foto di test; ogni lettore è la media calibrata di 5 lettori, vedi docs/miglioramento.md);
- quiz con circa 5.200 foto da PlantDoc, Project-AgML (CC BY o MIT), iNaturalist (CC0, CC BY, CC BY-NC, con autore) e IP102 (solo uso accademico), Calabria in primo piano;
- consigli di difesa con i prodotti Gowan e botte con il catalogo: regole e calcolatore verificati dai test (`tests/test_consigli.py`, `tests/test_sprayer.py`, `tests/test_webapp.py`);
- il lettore degli insetti non è incluso, perché IP102 è concesso solo per uso accademico;
- contributi: l'agronomo corregge il risultato, la foto resta nel telefono e si esporta come file JSON da importare con `plantcare import-contributi`. Il piano per migliorare la rete è in [docs/miglioramento.md](docs/miglioramento.md).

Per ricostruirla dopo un nuovo addestramento:

```bash
PYTHONPATH=src python scripts/export_web_model.py --checkpoint models/readers_.../readers.pt --out /tmp/web/plantcare.onnx
# quantizzazione per canale: vedi docs/lettori-ottici.md
PYTHONPATH=src python scripts/build_web.py --model <modello quantizzato> --ort-dist <onnxruntime-web/dist>
```

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
  difesa.py              Disciplinare della Calabria (versioni), stato UE delle sostanze, usi Gowan per il referto
  consigli.py            catalogo Gowan per Consigli e Botte (app/data/catalogo.json)
  sprayer.py             calcolatore della botte (gemello di app/sprayer.js)
  cli.py                 comando `plantcare`
metadata/                 mappa dei gruppi foglia di PlantVillage (per lo split senza fuga di dati)
Dockerfile                immagine per la pubblicazione (vedi docs/deploy.md)
tests/                   test unitari e di integrazione (dati sintetici)
docs/                    ricerca, dataset, architettura, consigli di difesa (docs/consigli.md)
.github/workflows/       controllo settimanale delle norme (aggiorna-norme.yml)
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
