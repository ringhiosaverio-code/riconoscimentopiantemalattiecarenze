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

## 6. Ipotesi calibrate e laboratorio (nell'app)

**Ipotesi con garanzia di copertura.** Oltre alla risposta più probabile, l'app mostra l'elenco più corto di ipotesi che, sulle foto di campo di validazione (PlantDoc e PlantWild; per gli insetti IP102), contiene la risposta giusta 95 o 99 volte su 100: predizione conforme con soglia sulle probabilità (Sadinle et al. 2019; Angelopoulos et al. 2021, arXiv 2009.14193). La copertura si verifica sulle foto di test. Le soglie si calcolano con `scripts/calibrate_hypotheses.py` sul modello web e finiscono in `app/data/hypotheses.json`. La garanzia vale per foto simili a quelle di calibrazione; per le foto di Calabria e Sicilia va verificata con i contributi.

Prova sull'insieme di lettori, foto di campo (prima del modello nuovo):

| Cosa | Livello | Ipotesi in media | Copertura sul test |
|---|---|---|---|
| Causa (fungo, batterio, virus, insetto...) | 99% | 1,9 | 99,1% |
| Malattia, coltura indicata | 99% | 7,3 (mediana 3) | 98,5% |
| Malattia, coltura indicata | 95% | 1,8 | 94,4% |
| Malattia, coltura non indicata | 99% | 26 (mediana 10) | 98,3% |
| Insetti (IP102) | 95% | 5,2 (mediana 3) | 94,9% |

Indicare la coltura nell'app ("Che coltura è?") restringe le malattie a quelle viste su quella coltura nell'addestramento: la malattia giusta passa dall'81,5% all'83,6% e l'elenco al 99% si accorcia da 26 a 7 ipotesi in media.

**Quando serve il laboratorio.** `configs/lab_requirements.yaml` indica, per causa, l'analisi di conferma secondo i protocolli diagnostici EPPO (serie PM 7, letti nel testo): virus (ELISA, RT-PCR), viroidi (RT-PCR: non producono proteine), batteri e fitoplasmi (isolamento, PCR), nematodi (estrazione e microscopio), carenze (analisi fogliare: l'HLB somiglia alle carenze di zinco, rame e manganese), acari, cocciniglie e tripidi (microscopio su vetrino). Se le ipotesi al 99% contengono cause diverse, l'app scrive che dalla foto non si distinguono. Per 19 organismi presenti nei lettori riporta la categoria UE ed EPPO letta sulla scheda EPPO Global Database (11 da quarantena UE, 4 RNQP, 4 solo liste EPPO). Il lettore degli insetti risponde anche se nella foto non c'è un insetto: per questo resta chiuso, salvo quando i sintomi indicano insetti o acari, e i suoi avvisi sono condizionati ("se la foto mostra davvero questo insetto").

## 7. Modello del 25 novembre 2026 (pubblicato)

Combinazioni di 5 lettori addestrate con i dati nuovi: PlantWild, CCMT, FieldVitis (vite in campo, mal
dell'esca), foglie di melo ATLDSD, 44 insetti e acari della Calabria e malattie calabresi da iNaturalist
(occhio di pavone, rogna, colpo di fuoco, muffa grigia, corineo, mal bianco del pesco, ruggine della
fava). Il ramo riaddestrato non è incluso: su questa macchina, che si riavvia spesso, non riesce a
finire. Modello web quantizzato, stessa preparazione della foto del browser:

| Foto di prova | Lettore | Prima (v1) | Ora |
|---|---|---|---|
| PlantWild (campo, "in natura") | malattia | 49,5% | **83,6%** |
| PlantWild | coltura | 71,6% | **91,7%** |
| PlantDoc (campo) | malattia | **80,7%** | 76,9% |
| PlantDoc | coltura | 91,1% | 90,7% |
| iNatAg | coltura | 79,7% | **80,4%** |
| FieldVitis (vite in campo) | malattia | 21,6% | **96,1%** |
| Malattie calabresi (iNaturalist) | malattia | 20,0% | **87,7%** |
| Insetti calabresi (iNaturalist) | insetti | non previsti | **82,9%** |
| IP102 (25 per classe) | insetti | 66,7% | **68,2%** |
| PlantVillage | malattia | 98,0% | 98,5% |
| Contributo di Reggio Calabria (olivo) | coltura | sbagliata | **giusta** |

Eccezione alla regola 1 qui sotto: su PlantDoc la malattia scende di 3,8 punti (manca il ramo
riaddestrato), ma sulle foto di campo indipendenti (PlantWild) sale di 34 punti e il lettore riconosce
le malattie e gli insetti della Calabria. Il ramo riaddestrato si riaggiunge quando l'addestramento
lungo può completarsi.

## 8. Nuove fonti di foto (25 novembre 2026, sera)

Fonti cercate e scelte in `docs/ricerca-ia.md` (sezione 10). Due versioni addestrate e valutate come
il browser (modello quantizzato) sulle stesse foto di prova:

- **A**: tutte le fonti nuove, comprese 15.000 foto di arancio, cetriolo e anguria (Bangladesh, sfondi
  semplici);
- **B**: senza arancio, cetriolo e anguria; con le malattie da iNaturalist (fino a 600 foto per specie),
  DiaMOS, virus della vite e foto da letteratura.

| Foto di prova | Lettore | Pubblicato | A | **B (pubblicato ora)** |
|---|---|---|---|---|
| PlantDoc | malattia | 76,9% | 74,5% | **77,4%** |
| PlantDoc | coltura | 90,7% | 90,7% | 90,5% |
| PlantWild | malattia | 83,6% | 83,8% | 83,5% |
| PlantWild | coltura | 91,7% | 91,7% | 91,8% |
| iNatAg | coltura | 80,4% | 79,3% | 80,4% |
| FieldVitis (vite, mal dell'esca) | malattia | 96,1% | 98,0% | 98,0% |
| Virus della vite (accartocciamento) | malattia | 63,6% | 97,4% | 96,1% |
| DiaMOS (pero in Sardegna) | coltura | 42,6% | 100% | 100% |
| DiaMOS | malattia | non prevista | 84,4% | 85,2% |
| Malattie calabresi (iNaturalist, anche le classi nuove) | malattia | 84,5% (solo classi note) | 86,9% | 87,2% |
| Insetti calabresi (iNaturalist) | insetti | 84,7% | 84,7% | 84,7% |

A peggiora la malattia su PlantDoc di 2,4 punti: le foto di arancio, cetriolo e anguria (quasi tutte
giuste al 99-100%, quindi troppo facili) spostano il lettore verso foto da laboratorio. B rispetta le
regole qui sotto (malattia su PlantDoc migliore, coltura con una foto su 451 di differenza) e aggiunge
le classi: ruggine del pero, Xylella fastidiosa, cancro batterico da Pseudomonas syringae, antracnosi e
lebbra (Colletotrichum), nebbia rossa del susino, Sclerotinia, mal secco degli agrumi, limacina e
maculature del pero. Il mal secco ha solo 21 foto: va letto come ipotesi da confermare in laboratorio.

## 9. Fonti del Sud Italia (26 novembre 2026)

Nuove foto (`docs/ricerca-ia.md`, sezione 11): Bugwood (4.719), Observation.org tramite GBIF (7.231),
Servizio fitosanitario dell'Emilia-Romagna (291), ARSAC Calabria (9). Classi nuove: marciume da
Phytophthora capsici, cancro della corteccia del castagno, peronospora della cipolla, verticilliosi.

Versioni provate (stesse foto di prova, modello quantizzato come nel browser):

| Foto di prova | Lettore | B (prima) | C (fonti nuove, peso 2) | **D (pubblicato)** |
|---|---|---|---|---|
| PlantDoc | malattia | 77,4% | 76,7% | 76,9% |
| PlantDoc | coltura | 90,5% | 90,0% | 90,5% |
| PlantWild | malattia | 83,5% | 83,5% | **84,4%** |
| iNatAg | coltura | 80,4% | 80,4% | 80,4% |
| Malattie calabresi (iNaturalist) | malattia | 87,2% | 88,7% | 88,4% |
| Insetti calabresi (iNaturalist) | insetti | 84,7% | 87,7% | **87,7%** |
| Observation.org | malattia | 68,6% | 89,9% | **89,4%** |
| Observation.org | insetti | 92,1% | 94,9% | **94,9%** |
| Bugwood | insetti | 34,9% | 60,5% | **60,5%** |
| IP102 (25 per classe) | insetti | 68,2% | 67,4% | 67,4% |
| FieldVitis | malattia | 98,0% | 96,1% | 96,1% |
| Virus della vite | malattia | 96,1% | 90,9% | 90,9% |

D unisce i lettori migliori: coltura e carenze di B, insetti di C, malattie riaddestrate con le fonti
nuove a peso normale (1,0 invece di 2,0). Eccezione alle regole qui sotto: su PlantDoc la malattia perde
2 foto su 451 (0,5 punti), FieldVitis 1 foto su 51 e il virus della vite 4 su 77; in cambio PlantWild
guadagna 8 foto su 844 e migliorano molto le malattie e gli insetti di Calabria e Mediterraneo, la
priorità del progetto. L'errore di calibrazione degli insetti sale al 3,3% (regola: sotto il 3%): le
ipotesi calibrate (insiemi conformi) restano corrette perché le soglie sono ricalcolate su questo modello.

## 10. Foto da ARSAC, riviste, tesi ed Europe PMC; prova "esperti del Sud" (26 novembre 2026)

390 foto verificate a vista (`docs/ricerca-ia.md`, sezione 12): ARSAC 65, Phytopathologia Mediterranea
120 (dopo i doppioni), UNIRC 11, Europe PMC 203. Un quarto dei documenti è tenuto da parte come prova
nuova, **"esperti del Sud"** (83 foto: mal dell'esca, muffa grigia, Xylella, rogna dell'olivo, cancro
del castagno, tignoletta della vite, tignola del pomodoro e altre), che nessun modello ha visto.

Versione G pubblicata: lettore delle malattie riaddestrato con le foto verificate (peso 2), lettori di
coltura e insetti uguali alla versione D. Stessa preparazione della foto del browser:

| Foto di prova | Lettore | D (prima) | **G** |
|---|---|---|---|
| Esperti del Sud | malattia | 34,9% | **44,4%** |
| Esperti del Sud | insetti | 45,0% | 45,0% |
| PlantDoc | malattia | 76,9% | **77,4%** |
| PlantDoc | coltura | 90,5% | 90,5% |
| PlantWild | malattia | 84,4% | 83,6% |
| iNatAg | coltura | 80,4% | 80,4% |
| Malattie calabresi (iNaturalist) | malattia | 88,4% | 87,8% |
| Insetti calabresi (iNaturalist) | insetti | 87,7% | 87,7% |
| FieldVitis | malattia | 96,1% | **98,0%** |
| Virus della vite | malattia | 90,9% | **94,8%** |
| Observation.org | malattia | 89,4% | **90,4%** |

La prova "esperti del Sud" mostra quanto resta da fare: foto da bollettini e articoli (legno, cancri,
essudati, tubercoli) sono ancora molto più difficili delle foto di campo delle raccolte aperte.

## 11. Giro H: insetti e malattie del Sud da iNaturalist e Bugwood (26 novembre 2026)

Nuove foto di campo per l'addestramento:
- fino a 200 foto per specie da iNaturalist, osservazioni "research grade" con licenza aperta;
- foto di Bugwood per 20 insetti e acari del Sud aggiunti al quiz: fleotribo, oziorrinco e cecidomia
  dell'olivo, cinipide, balanino e tortrice del castagno, punteruolo rosso, cocciniglie, aleurodide e afidi
  degli agrumi, cimice verde e altri;
- antracnosi della vite, alternariosi e cancro del castagno tra le malattie.

Il lettore degli insetti passa da 145 a 163 classi: 18 specie nuove riconoscibili, mentre per l'antracnosi
della vite le 4 foto di iNaturalist non bastano a farne una classe.

| Foto di prova | Lettore | G | H (riaddestrato) | Insieme G+H | **Pubblicato** |
|---|---|---|---|---|---|
| PlantDoc | malattia | 77,4% | 76,7% | 76,5% | **77,4%** (G) |
| Malattie calabresi (iNaturalist) | malattia | 88,9% | 90,3% | 89,6% | 88,9% |
| Bugwood | malattia | 75,4% | 82,9% | 83,4% | 75,4% |
| Insetti calabresi, specie già note | insetti | 85,5% | 86,1% | – | **86,1%** |
| Insetti calabresi, con le 18 specie nuove | insetti | – | 83,8% | – | **83,8%** |
| IP102 | insetti | 67,4% | 67,6% | – | **67,6%** |
| Observation.org | insetti | 94,9% | 94,1% | – | 94,1% |

Il lettore delle malattie riaddestrato migliora sulle foto del Sud, ma perde punti su PlantDoc. Per la
regola 1 qui sotto resta quello di G. È pubblicato solo il nuovo lettore degli insetti: riconosce le 18
specie nuove (77% di risposte giuste sulle loro foto di prova) e migliora sulle specie già note, salvo un
calo minimo su Observation.org (4 foto su 505).

## 12. Giro I: più peso a PlantDoc nel lettore delle malattie (27 novembre 2026)

Il lettore delle malattie del giro H migliorava sulle foto del Sud ma perdeva su PlantDoc. Con le stesse
foto ho riaddestrato 5 lettori con peso 6 a PlantDoc (prima 3) e 4 a PlantWild, e li ho uniti ai 5 lettori di
G in un insieme di 10. Ho provato anche peso 10 e una scelta del lettore migliore basata in parte su PlantDoc:
peggiorano altre prove, quindi le ho scartate.

| Foto di prova (come nel browser) | G | **I (pubblicato)** |
|---|---|---|
| PlantDoc | 77,4% | **77,4%** |
| PlantWild | 83,6% | **83,9%** |
| Malattie calabresi (iNaturalist) | 88,9% | **89,3%** |
| Bugwood | 75,4% | **83,4%** |
| Vite in campo, virus della vite, DiaMOS | 98,0 / 94,8 / 85,2% | uguali |
| Observation.org | 90,4% | 89,9% (1 foto su 188) |

PlantDoc non peggiora e le altre prove di campo migliorano, quindi il modello si pubblica. Il costo è il
modello un po' più grande: 85 MB invece di 76. Le foto inviate dall'app con "Invia contributi" e corrette
da un agronomo hanno da ora peso 5 nell'addestramento, il più alto, perché sono le più vicine all'uso reale.

## 13. Giro K: dispense dell'utente e dataset aperti di campo (27 novembre 2026)

**Dati nuovi.**
- 276 foto di campo estratte dalle dispense caricate dall'utente (ARSAC, Bilancio fitosanitario agrumi,
  cucurbitacee, TSWV, TYLCV, Psa del kiwi, virus da quarantena, lotta ai virus, olivo, agrumi, kiwi di
  Rosarno), guardate una per una: tolte slide di testo, mappe, piastre, trappole e figure con etichetta
  dubbia (configs/verificate/dispense.json). Solo addestramento: non vanno nel quiz.
- 4707 foto da dataset aperti CC BY 4.0 fotografati in campo (scripts/import_aperti.py):
  - esca della vite delle Marche (Università Politecnica delle Marche, Mendeley);
  - agrumi di Fès, Marocco;
  - foglie di limone (campione per classe);
  - peronospora della vite (Merlot; Spagna e Norvegia);
  - peperone (Etiopia, progetto EU EWA-BELT).
- Scartati: la raccolta "web sourced" (stesse classi e fonti di PlantDoc: falserebbe il test) e i progetti
  GitHub con il 90-99% di accuratezza, tutti addestrati su PlantVillage (foto di laboratorio).

**Addestramento.** Due insiemi da 5 lettori con più peso a PlantDoc (6 e 8) e meno ai dati aperti (1 e
0,7), scelti in parte sull'accuratezza di PlantDoc, uniti a 8 lettori di I: 18 lettori per le malattie
(modello di 100,6 MB, sotto il limite di 100 MiB per file di GitHub). Insetti, coltura e carenze: come I.

| Foto di prova (come nel browser, stesse foto) | I | **K (pubblicato)** |
|---|---|---|
| Dataset aperti di campo (504 foto mai viste) | 29,2% | **88,1%** |
| Esperti del Sud: bollettini, riviste, tesi, dispense (87) | 44,8% | **50,6%** |
| Bugwood (175) | 83,4% | **85,1%** |
| Observation.org (188) | 89,9% | **90,4%** |
| PlantWild, vite in campo, virus della vite, DiaMOS | 83,9 / 98,0 / 94,8 / 85,2% | uguali |
| Malattie calabresi da iNaturalist (298) | 89,3% | 88,9% (1 foto) |
| PlantDoc (451) | 77,4% | 76,5% (4 foto) |

Su PlantDoc la differenza è di 4 foto su 451, dentro la variabilità della misura (circa ±4 punti al 95%):
dare più peso ai lettori di I non la recupera (PlantDoc oscilla tra 76,3 e 76,9% con qualunque peso). Per
questo la regola 1 qui sotto ammette ora fino a 1 punto in meno su PlantDoc, come già per il test
complessivo, quando le altre prove di campo migliorano. Il modello I resta in models/vI per tornare indietro.

## 14. Giro M: danni da insetti, malattie e insetti di orticole e fruttiferi (28 novembre 2026)

**Danni da insetti e acari** (scripts/import_danni.py, solo addestramento): 9 classi nuove nel lettore
delle malattie, con causa insetto o acaro:
- galle del cinipide del castagno;
- cotonosità della psilla dell'olivo;
- afide lanigero;
- colonie di afidi;
- argentature da tripidi;
- fori da carpocapsa e tortrici;
- punture di cimici;
- gallerie della piralide;
- erinosi della vite.

Le foto vengono da Bugwood (marcate "Damage"), da iNaturalist (scelte a vista tra quelle degli insetti) e,
per l'erinosi, da un dataset Mendeley CC BY. Nell'app ogni danno, malattia trasmessa da un vettore o
fumaggine è collegato all'insetto responsabile, con la difesa contro l'insetto (configs/danni_insetti.yaml).

**Malattie nuove** (iNaturalist e Bugwood): ruggine e antracnosi del fagiolo, oidio del pisello,
peronospora della fava, oidio e ruggine bianca delle crucifere, cercosporiosi della bietola, vaiolatura e
maculatura angolare della fragola, oidio del nocciolo, ruggine e mosaico del fico, mosaico del cetriolo
(CMV), ticchiolatura e maculatura bruna del pero, alternariosi.

**Insetti nuovi**: 67 specie del Disciplinare della Calabria e organismi da quarantena (configs/
quiz_calabria.yaml), per un totale di 222 classi nel lettore degli insetti.

Il lettore delle malattie ha 14 lettori nuovi, perché le classi sono cambiate; per gli insetti ci sono
10 lettori con più peso alle foto della Calabria. Il modello pesa 103,5 MB.

| Foto di prova (come nel browser) | K | **M (pubblicato)** |
|---|---|---|
| PlantDoc (451) | 76,5% | **77,6%** |
| PlantWild (844) | 83,9% | 83,2% |
| Danni da insetti e acari (77, classi nuove) | non previsti | **87,0%** |
| Malattie nuove sul test dei lettori (202) | non previste | **79,7%** |
| Insetti: specie già note della Calabria (stesso test) | 85,8% | 84,2% |
| Insetti: 67 specie nuove (801) | non previste | **82,3%** |
| Insetti Bugwood / Observation.org | 55,3 / 94,1% | **69,4 / 95,0%** |
| DiaMOS, virus della vite, esperti del Sud (malattie) | 85,2 / 94,8 / 50,6% | 1-2 foto in meno ciascuno |

Con 67 specie di insetti in più, le specie già note perdono 1,6 punti: alcune specie nuove sono simili
a quelle già presenti (nottue, cocciniglie, afidi). È il compromesso per riconoscere tutti gli insetti
delle colture del Sud: le foto di prova delle specie nuove passano dallo 0% (non previste) all'82%.
Per questo la regola 1 ammette, quando si aggiungono classi, fino a 2 punti in meno sulle classi già
presenti se le classi nuove sono riconosciute almeno nel 75% dei casi. I modelli K e I restano in models/.

## 15. Giro N: BioCLIP per malattie e insetti, lettori distillati (28 novembre 2026)

**BioCLIP** (ViT-B/16, licenza MIT, addestrato su milioni di foto di organismi dell'albero della vita) si
affianca a DINOv2 ed EfficientNet per i lettori delle malattie e degli insetti: le caratteristiche passano
da 1664 a 2176 (BioCLIP normalizzato ×10). Con 14 + 10 lettori il modello pesava 206 MB, troppo per il
telefono: ogni lettore è stato quindi **distillato** in 2 "allievi" che imitano l'insieme (probabilità a
temperatura 2, peso 0,7, stessi pesi delle foto di campo; scripts/distilla_lettori.py). Coltura e carenze
restano sulle caratteristiche attuali, anch'esse distillate in 2 allievi. Il modello pesa **146 MB**
(in 3 parti, resta in memoria dopo il primo scaricamento).

| Foto di prova (come nel browser) | M | **N (pubblicato)** |
|---|---|---|
| Malattie: PlantDoc (451) | 77,6% | **79,4%** |
| Malattie: PlantWild (844) | 83,2% | **84,4%** |
| Malattie: Calabria iNaturalist (216) | 88,9% | **90,7%** |
| Malattie: DiaMOS / virus della vite / Observation | 84,4 / 93,5 / 89,9% | **86,9 / 96,1 / 92,0%** |
| Malattie: Bugwood (181) | **82,9%** | 77,9% |
| Malattie: PlantVillage (laboratorio, 400) | **98,8%** | 94,3% |
| Insetti: Calabria iNaturalist (484) | 85,7% | **88,6%** |
| Insetti: Bugwood / Observation | 69,4 / 95,1% | **72,9 / 96,2%** |
| Insetti: IP102 (25 per specie) | **67,5%** | 63,8% |
| Coltura: PlantDoc / iNatAg | 90,5 / 80,4% | 90,0 / 78,6% |

Sul test complessivo dei lettori: malattie 88,1 → 87,7%, insetti 74,6 → 74,8%; errore di calibrazione
sotto il 3% per tutti (insetti 2,8%). Le foto di campo del Sud migliorano, PlantDoc non peggiora: il
modello rispetta le regole. Peggiorano le foto di laboratorio (PlantVillage) e Bugwood malattie, che sono
spesso primi piani su sfondo uniforme: BioCLIP dà più peso al contesto di campo. I modelli M e N completo
restano in models/vM e models/vN.

## Regole per accettare un nuovo modello

Un nuovo modello sostituisce quello pubblicato solo se:
1. sul **test di campo** (PlantDoc e contributi) nessun lettore perde più di 1 punto (variabilità della misura) e
   le prove di campo del Sud migliorano; se si aggiungono classi, le classi già presenti possono perdere fino a
   2 punti quando le nuove sono riconosciute almeno nel 75% dei casi;
2. l'errore di calibrazione resta sotto il 3%;
3. sul test complessivo non perde più di 1 punto;
4. i test automatici passano e la versione web (quantizzata) conferma le stesse misure.

## Misure da riportare a ogni ciclo

- accuratezza e macro-F1 per lettore, separate per fonte (laboratorio, campo, contributi);
- per i contributi: separate per provincia e per tipo di diagnosi (laboratorio, tecnico, osservazione);
- copertura contro accuratezza alle soglie 0,5 / 0,7 / 0,9.
