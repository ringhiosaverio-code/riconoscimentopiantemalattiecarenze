# Consigli di difesa, Botte e aggiornamento delle norme

La sezione **Consigli** dell'app propone una ricetta di difesa con i prodotti Gowan Italia: si sceglie la coltura,
la malattia o il parassita, la fase della coltura e la situazione in campo. L'app mette in ordine i prodotti registrati
come farebbe un tecnico della difesa integrata e calcola dosi e quantità. Propone anche il coadiuvante e, se si vuole,
concimi e biostimolanti. La **Botte** usa lo stesso catalogo per non dover scrivere a mano prodotti e caratteristiche.

## Regole scritte, non una rete neurale

L'ordine dei prodotti **non si "addestra"** come i lettori ottici. Una dose o un intervallo di sicurezza sbagliati
non sono un errore di previsione accettabile. Per questo i consigli sono regole scritte (`configs/difesa/consigli_regole.yaml`)
applicate ai documenti ufficiali.

- Ogni regola cita la sua fonte.
- Ogni prodotto proposto mostra i motivi della sua posizione.
- Un test controlla le regole su casi verificabili a mano (`tests/test_consigli.py`).

Quando escono nuove norme o nuove etichette, i consigli cambiano da soli, perché si ricostruiscono i dati: le regole
restano le stesse.

## Da dove vengono i dati

| Dato | File | Fonte |
|---|---|---|
| Usi registrati: coltura, avversità, dosi a ettaro e a ettolitro, intervallo di sicurezza, note | `configs/difesa/gowan_italia.json` | pagine prodotto ed etichette Gowan (`scripts/import_gowan.py`) |
| Gruppo FRAC o IRAC, tipo di azione, avvertenze per le api, con la frase letterale | `configs/difesa/gowan_caratteristiche.yaml` | etichette Gowan; dove mancano, Allegato 4 del Disciplinare (classificazione FRAC e IRAC) |
| Posizionamento dei prodotti per fase ed epoca, prodotti BIO | `configs/difesa/gowan_programmi.yaml` | depliant e schede colturali Gowan 2025-2026 (vite, pomodoro, lattuga, fragola, pesco, susino, ciliegio, actinidia, olivo, zucchino, patata, nocciolo) |
| Concimi e biostimolanti | `configs/difesa/gowan_nutrizionali.yaml` | schede catalogo Gowan (Tamarack, Premio, Dinamic Pro, Ridox Stim, Sprinfer New) |
| Coadiuvanti | `configs/difesa/gowan_coadiuvanti.yaml` | MAGO: 50-150 ml/hl, al massimo 1,5 l/ha (etichetta) |
| Avversità, sostanze ammesse, limiti, criteri di intervento | `configs/difesa/disciplinare_calabria_*.json` | Disciplinari della Regione Calabria; in uso l'aggiornamento di agosto 2026 (Allegato B) |
| Stato delle sostanze attive: approvata, scadenza, candidata alla sostituzione | `configs/difesa/sostanze_ue.json` | EU Pesticides Database (Commissione europea) |
| Nomi delle sostanze nei vari documenti | `configs/difesa/sostanze.yaml` | composizione dei prodotti, Disciplinare, banca dati UE |

`src/plantcare/consigli.py` unisce tutto in `app/data/catalogo.json` (circa 2 MB, 230 kB compresso). Lo scarica
l'app quando serve. Dalle note d'uso delle etichette legge, con espressioni regolari:
- gli stadi BBCH ammessi (anche quelli a cavallo dell'inverno, come "BBCH 93-03");
- il numero massimo di trattamenti e gli intervalli;
- i volumi d'acqua;
- le indicazioni preventive o "ai primi sintomi".

La nota intera resta sempre leggibile nella ricetta.

## Come si mettono in ordine i prodotti

**Esclusioni.** Il prodotto non si propone e compare tra gli "esclusi" con il motivo quando:
- non è registrato sulla coltura per l'avversità, oppure è registrato solo in serra o solo in pieno campo;
- la nota d'etichetta indica stadi BBCH fuori dalla fase scelta;
- la fase è oltre il limite scritto al posto dell'intervallo di sicurezza: IF = sospendere a inizio fioritura,
  FF = a fine fioritura, TB = solo trattamenti al bruno. Il significato delle sigle è verificato sulle etichette;
- l'intervallo di sicurezza è più lungo dei giorni che mancano alla raccolta;
- è richiesta la produzione biologica e il prodotto non ha il marchio BIO nelle schede Gowan;
- è richiesto il Disciplinare e la sostanza non è ammessa per quella coltura e avversità. Le sostanze ammesse solo in
  esche o dispositivi "attract and kill" non valgono per un trattamento alla chioma: per esempio la deltametrina contro
  la mosca delle olive;
- in fioritura, se l'etichetta vieta il trattamento per proteggere le api;
- la sostanza non è più approvata nell'UE.

**Punteggio** (a parità vale l'intervallo di sicurezza più breve):

| Criterio | Punti | Fonte |
|---|---|---|
| Gowan lo posiziona in questa fase nel programma della coltura | +3 | depliant e schede Gowan |
| Nel programma Gowan, ma in un'altra fase | +0,5 | depliant e schede Gowan |
| Tipo di azione adatto alla situazione: preventiva e di copertura in prevenzione; curativa, citotropica, eradicante ai primi sintomi o con l'attacco in corso; ovo-larvicida e Bacillus thuringiensis sulle forme giovani; abbattente sugli adulti | +2 (utile: +1) | etichette; Disciplinare, Allegato 3 per il Bt |
| Mezzo biologico o ammesso in biologico | +1 | Disciplinare: «devono essere privilegiati, ogniqualvolta possibile, i metodi non chimici» |
| Insetticida selettivo | +1 | Disciplinare: «ricorrendo ai fitofarmaci più selettivi» |
| Stesso gruppo FRAC o IRAC dell'ultimo trattamento (esclusi multisito e biologici) | −3 | Disciplinare, Allegato 4 |
| Sostanza candidata alla sostituzione | −0,5 | banca dati UE |
| Non ammesso dal Disciplinare, se non si chiede di rispettarlo | −4 | Disciplinare |

**Ricetta.**
- **Dose.** Si sceglie dentro l'intervallo di etichetta: la minima in prevenzione, l'intermedia ai primi sintomi, la
  massima con l'attacco in corso. Quando l'etichetta dà la dose a ettaro e si conosce il volume d'acqua, resta fissa
  la dose a ettaro e si adatta la concentrazione, come chiedono le etichette per i volumi ridotti o elevati.
- **Quantità.** Prodotto per la superficie indicata e per una botte.
- **Limiti di etichetta.** Numero di trattamenti, intervallo, intervallo di sicurezza, stadi.
- **Limiti del Disciplinare** per le sostanze del prodotto.
- **Rame metallo** per ettaro, con il limite del Disciplinare.
- **Stato UE** delle sostanze.
- **Coadiuvante** MAGO.
- **Alternanza** di gruppi di resistenza diversi.
- **Concimi e biostimolanti** della fase. Tamarack non si propone su susino e non va in miscela con il rame fuori
  dall'olivo, come dice la scheda Gowan.
- **"Porta nella botte"** riempie la Botte con prodotto e coadiuvante.

## La Botte

La Botte si usa in tre passi:
1. capienza della botte, acqua per ettaro e, se si vuole, la coltura;
2. i prodotti, scelti dal catalogo Gowan. Si compilano da soli formulazione, tipo, rame per kg o per litro e, scelto
   l'uso registrato sulla coltura, la dose e i limiti di etichetta. Per i prodotti di altre aziende c'è "Altro prodotto",
   con i campi da compilare a mano;
3. il calcolo: superficie trattata da una botte, istruzioni numerate per caricarla (quantità, ordine per formulazione),
   tabella per botte e per ettaro, rame, incompatibilità e fonti.

Oltre alla dose massima per ettolitro, la Botte controlla la dose massima a ettaro di etichetta con il volume d'acqua
indicato (`label_max_ha` in `src/plantcare/sprayer.py` e `app/sprayer.js`).

## Aggiornamento automatico delle norme

`scripts/aggiorna_norme.py` fa tre controlli:
- **Disciplinare.** Cerca nell'elenco dei PDF pubblicati da ARSAC (`/wp-json/wp/v2/media`) un Disciplinare "difesa e
  diserbo" più recente di quello in uso. Se c'è, lo legge con `scripts/import_disciplinare.py` e lo salva come nuova
  versione. L'app usa sempre la più recente e segnala le sostanze uscite rispetto alle versioni precedenti, con la
  versione in cui c'erano ancora. Al primo controllo ha trovato l'aggiornamento di agosto 2026 (Allegato B).
  Rispetto ad aprile:
  - tolti fenpyrazamine (non più approvato nell'UE dal 15/01/2025) e Bacillus pumilus;
  - aggiunti cyantraniliprole e flupyradifurone su olivo e protioconazolo su mandorlo;
  - cambiati diversi limiti per numero di trattamenti.
- **Banca dati UE** (`--ue`). Scarica dall'interfaccia pubblica lo stato delle sostanze attive. Nei Disciplinari le
  sostanze non più approvate sono segnalate nel lettore. Il confronto tra nomi italiani e inglesi è prudente:
  - un abbinamento incerto non segnala mai una sostanza come revocata. Per esempio "Fenaxamide" potrebbe essere
    fenexamid o fentrazamide;
  - le voci generiche si confrontano a mano in `configs/difesa/sostanze.yaml`.
- **Gowan** (`--gowan`). Scarica pagine prodotto ed etichette, una richiesta ogni 2 secondi, e rilegge gli usi registrati.

Con `--app` ricostruisce `app/data/difesa.json` e `app/data/catalogo.json` senza il modello e senza il dataset.
La copia delle colture per classe è in `configs/difesa/colture_per_classe.json`.

Il flusso `.github/workflows/aggiorna-norme.yml` lo esegue ogni giorno, con le etichette Gowan il lunedì, e a mano. Se le norme sono cambiate:
- esegue i test;
- apre una pull request con il riepilogo delle novità.

Una persona la controlla sul PDF ufficiale e sulla banca dati UE prima di unirla: nessuna norma entra nell'app senza
revisione. GitHub esegue i flussi programmati solo dal ramo predefinito del repository (qui `claude/gracious-noether-kz4in8`,
lo stesso pubblicato con GitHub Pages): il controllo è attivo.

```bash
PYTHONPATH=src python scripts/aggiorna_norme.py                 # Disciplinare, banca dati UE, dati dell'app
PYTHONPATH=src python scripts/aggiorna_norme.py --gowan --app   # anche etichette e usi Gowan
```

## Limiti

- I consigli riguardano solo i prodotti Gowan Italia. Per gli altri prodotti autorizzati serve la banca dati dei
  prodotti fitosanitari del Ministero della Salute; il Disciplinare elenca comunque tutte le sostanze ammesse.
- Fasi e stadi BBCH sono indicativi. Il programma Gowan dà le fasi per vite, pomodoro, lattuga e fragola; per le altre
  colture si usano fasi generiche per gruppo (arboree, orticole, cereali, industriali, ornamentali).
- La lettura delle note d'etichetta con espressioni regolari può perdere indicazioni scritte in modo insolito: per
  questo la nota intera è sempre leggibile.
- L'etichetta autorizzata prevale sempre. La ricetta non sostituisce il tecnico abilitato, e l'uso professionale dei
  prodotti fitosanitari richiede il certificato di abilitazione (D.Lgs. 150/2012).
