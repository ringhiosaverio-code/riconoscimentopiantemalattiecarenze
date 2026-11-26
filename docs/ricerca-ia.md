# Cosa fanno le altre intelligenze artificiali e cosa applichiamo

Rassegna di studi verificati (articoli, rassegne, prove sul campo) su riconoscimento di malattie,
insetti e carenze dalle foto, con la scelta fatta per PlantCare. Le misure di PlantCare sono sulle
stesse foto di prova descritte in `docs/miglioramento.md`.

## 1. Il divario tra laboratorio e campo

- Una rassegna sistematica su *Plant Methods* (2025) riporta che ConvNeXt passa dal 99,47% su
  PlantVillage (foto di laboratorio) al 71,76% su PlantDoc (foto di campo), e ResNet50 dal 98,18% al
  41,79% ([Plant Methods 2025](https://link.springer.com/article/10.1186/s13007-025-01450-0)). Cause indicate: sfondi complessi,
  luce variabile, qualità delle foto dei telefoni, sintomi diversi quando agiscono più stress insieme.
- PlantDoc è piccolo (2.598 foto, 27 classi, 13 piante) e contiene foto con etichetta sbagliata.
- **PlantCare**: sulle foto di campo di PlantDoc la malattia giusta è intorno al 77-82%, in linea con i
  risultati migliori pubblicati. Per questo l'addestramento usa più dati di campo (PlantDoc, PlantWild,
  CCMT, AgML) pesati di più, e i numeri si riportano separati per foto di laboratorio e di campo.

## 2. Le app commerciali sul campo

- Plantix, valutata da CABI e ICRISAT su 900 casi in campo in India (2019): la prima diagnosi era giusta
  in poco più del 51% dei casi e nel 20% la malattia giusta non veniva trovata; in una fase successiva il
  progetto riporta la risposta giusta al primo posto nel 75% dei casi e tra le prime tre nell'80%
  ([PlantwisePlus](https://blog.plantwise.org/2020/06/19/teaching-an-app-to-help-farmers/)).
- Una valutazione di 17 app (Agronomy 2022) trova una sola app completa per riconoscimento, base di
  dati e trattamenti ([arXiv 2208.02446](https://arxiv.org/pdf/2208.02446)).
- **PlantCare**: oltre alla prima risposta mostra le ipotesi calibrate (elenco che contiene la risposta
  giusta 95 o 99 volte su 100) e dice quando serve il laboratorio.

## 3. Prima la foglia, poi la malattia

- Su foto larghe di cetriolo, un sistema in due fasi (una rete trova le foglie, un'altra le classifica)
  ha un F1 più di sei volte quello di un sistema unico (Fujita et al. 2019,
  [arXiv 1910.11506](https://ar5iv.labs.arxiv.org/html/1910.11506)). Risultati simili su pero e kiwi con
  sfondi complessi.
- **PlantCare**: c'è già il quadrato da spostare sulla foglia colpita (+3 punti sulle foto intere di
  PlantDoc: dal 79,2% all'82,2%). Prossimo passo: un rilevatore automatico delle foglie addestrato sui
  riquadri di PlantDoc.

## 4. Modelli di base per la biologia

- BioCLIP (CVPR 2024), addestrato su 10 milioni di immagini dell'albero della vita, riconosce anche
  specie mai viste dai nomi scientifici e migliora del 17-20% le classificazioni fini rispetto ai modelli
  generici ([CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/html/Stevens_BioCLIP_A_Vision_Foundation_Model_for_the_Tree_of_Life_CVPR_2024_paper.html)).
- **PlantCare**: usa DINOv2 ViT-S/14 (piccolo, adatto al telefono). Prossimo passo: provare le
  caratteristiche di BioCLIP sugli insetti e sulle colture con lo stesso protocollo della prova ViT-B; su
  questa macchina senza GPU l'estrazione per tutte le foto richiede molte ore.

## 5. Dire "non lo so": malattie che il modello non conosce

- Per riconoscere malattie sconosciute serve addestrare anche con esempi "estranei" (outlier exposure):
  senza, il riconoscimento dell'ignoto è scarso (fragola, Jiang et al. 2022,
  [Frontiers](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9520169/)); un punteggio di incertezza da più
  modelli aiuta (Dong et al. 2025, [Frontiers](https://www.frontiersin.org/articles/10.3389/fpls.2025.1623907/full)).
- **PlantCare**: l'insieme di 5 lettori calibrati e le ipotesi conformi danno già "non determinabile" o
  un elenco lungo quando la foto è incerta. È il caso della malattia di Petri della vite (sezione 9).
  Prossimo passo: misurare quante volte una malattia esclusa dall'addestramento riceve una risposta
  sicura sbagliata, e aggiungere esempi estranei.

## 6. Colore, saturazione, sfondo

- Nessuno spazio colore vince sempre ([CropGCNN](https://peerj.com/articles/cs-2136/)); con reti
  preaddestrate su foto normali convertire i colori può peggiorare. Il bilanciamento del colore ha aiutato
  sulle foglie di melo ([2025](https://link.springer.com/article/10.1007/s10341-025-01541-1)); in scala di
  grigi i risultati peggiorano (Mohanty et al. 2016); in PlantVillage 8 pixel di sfondo bastano per il
  49% (Noyan 2022, [arXiv 2206.04374](https://arxiv.org/abs/2206.04374)).
- **Prova su PlantCare** (lettore addestrato sulle foto originali, variante applicata solo alla foto da
  analizzare, `scripts/exp_colore.py`):

| Variante | Malattia, campo | Coltura, campo | Insetti (IP102) |
|---|---|---|---|
| Foto originale | **81,5%** | **84,7%** | **61,3%** |
| Saturazione +50% | 81,1% | 84,7% | 61,1% |
| Scala di grigi | 68,5% | 78,6% | 52,3% |
| Bilanciamento "gray world" | 78,7% | 83,3% | 58,7% |
| Contrasto locale (CLAHE) | 77,8% | 82,4% | 59,8% |
| Sfondo neutro (ExG−ExR) | 72,5% | 76,3% | 47,2% |

  Nessuna variante migliora; il colore conta (in grigio si perdono 13 punti) e togliere lo sfondo con
  l'indice di vegetazione cancella anche le parti necrotiche, cioè i sintomi. **Scelta**: la foto si
  analizza com'è; le variazioni di luce e colore si insegnano durante l'addestramento (aumento dei dati
  nel ramo riaddestrato). Gli indici di riflettanza veri (NDVI) richiedono il vicino infrarosso, che i
  telefoni non hanno.

## 7. Carenze nutrizionali

- Le rassegne trovano buoni risultati soprattutto su riso e macronutrienti, ma un forte divario con il
  campo e il potassio più difficile ([AgriEngineering 2025](https://www.mdpi.com/2624-7402/8/3/101/htm));
  anche per gli esperti le carenze si confondono tra loro (barbabietola,
  [2020](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7589690/)).
- **PlantCare**: il lettore delle carenze resta un'indicazione; l'app chiede sempre l'analisi fogliare
  (configs/lab_requirements.yaml).

## 8. Insetti

- Le rassegne descrivono il passaggio da reti convoluzionali a modelli con trasformatori e ibridi per la
  classificazione fine ([arXiv 2507.01494](https://arxiv.org/abs/2507.01494)), e molti studi sul
  conteggio automatico degli insetti nelle trappole (rassegna sistematica di 92 studi 2016-2022,
  [Agriculture 2023](https://www.academia.edu/144753992/A_Systematic_Review_on_Automatic_Insect_Detection_Using_Deep_Learning);
  vedi anche [questa rassegna](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10652400/)).
- Su IP102 i risultati migliori pubblicati sono intorno al 75-82% con modelli molto più grandi; PlantCare
  è al 74,5% con l'insieme di lettori (in corso il riaddestramento dei blocchi).
- **Idea per la Calabria**: contare mosca delle olive e mosca della frutta sulle trappole cromotropiche
  fotografate con il telefono (serve una raccolta di foto di trappole).

## 9. Malattia di Petri della vite

Perché il lettore non la riconosce:
1. non ha questa classe e non esistono dataset pubblici di foto per addestrarla;
2. colpisce soprattutto viti giovani (1-5 anni) con sintomi generici sulla chioma (germogliamento tardivo,
   internodi corti, ingiallimenti, deperimento) o senza sintomi; il segno tipico è nel legno, con
   striature brune o nere visibili tagliando il fusto o il portinnesto
   ([Phytopathologia Mediterranea 2005](https://ucanr.edu/sites/default/files/2021-01/343528.pdf));
3. la conferma richiede isolamento o PCR sul legno
   ([Applied and Environmental Microbiology 2012](https://journals.asm.org/doi/10.1128/aem.07360-11)).

Cosa fa ora l'app: se indichi vite e tronco, ramo o radice, mostra questo avviso con le fonti
(`configs/note_legno.yaml`); per il mal dell'esca, che ha gli stessi funghi (Phaeomoniella
chlamydospora, Phaeoacremonium spp.), mostra la difesa del Disciplinare della Regione Calabria.
Per insegnarla alla rete servono foto di sezioni di legno e di viti giovani con diagnosi di laboratorio,
inviate con "Aiuta a migliorare".

## 10. Fonti di foto cercate il 25 novembre 2026 (uso accademico)

Ricerca su Zenodo, Hugging Face (Project-AgML), iNaturalist, EPPO Global Database e PDF universitari.
Criterio: foto di campo, licenza che permetta l'addestramento a fini di ricerca, colture della Calabria.

| Fonte | Cosa aggiunge | Licenza | Esito |
|---|---|---|---|
| iNaturalist, osservazioni "research grade" | ruggine del pero, Xylella fastidiosa, Pseudomonas syringae, Colletotrichum (antracnosi e lebbra), nebbia rossa del susino, Sclerotinia, bozzacchioni, ticchiolatura e ruggine del pesco, peronospora delle cucurbitacee, fumaggine; fino a 600 foto per specie | CC0, CC BY, CC BY-NC | importate; split per autore |
| PlantSeg (Wei et al. 2024, arXiv 2409.04038) | 11.458 foto dal web, 115 malattie | CC BY-NC-ND | quasi tutte copie di PlantWild (distanza dHash mediana 0): 13 foto nuove |
| Foglie di arancio dolce (Emon et al. 2024, Data in Brief 55) | cancro batterico, HLB, cotonello, aleurodide spinoso, oidio, impallinatura | CC BY 4.0 | importate, ma escluse dal modello pubblicato: peggiorano le foto di campo (miglioramento.md, sezione 8) |
| Cetriolo (Sultana et al. 2023, Data in Brief 49) | antracnosi, peronospora, cancro gommoso, marciumi del frutto | CC BY 4.0 | importate, escluse come l'arancio |
| Anguria (Project-AgML) | antracnosi, peronospora, mosaico | CC BY 4.0 | importate, escluse come l'arancio |
| DiaMOS Plant (Fenu e Malloci 2021, Agronomy 11) | pero in campo in Sardegna: limacina, maculature | CC BY 4.0 | zip di 13 GB letto a pezzi, 1.144 foglie |
| Vine Virus Photo Dataset (MacDonald et al. 2025, Plant Disease) | accartocciamento fogliare (GLRaV-3) con stato virale verificato in laboratorio | CC BY 4.0 | fino a 600 + 400 foto |
| EPPO Global Database | mal secco, cancro batterico dell'actinidia, rogna dell'olivo | solo uso didattico | 34 foto, solo addestramento |
| PDF (mal secco, Sicilia; tesi UNIRC su Colletotrichum e Phytophthora) | 12 foto di sintomi del mal secco, 1 di lebbra su olive | diritto d'autore | solo addestramento (art. 70-ter L. 633/1941) |
| Foglie di mandorlo (Zenodo 19560931) | 65 foto originali, classi senza nome della malattia | CC BY 4.0 | scartato |
| Verticillium dell'olivo da drone (Zenodo 8144164) | immagini aeree | CC BY 4.0 | scartato: non sono foto da telefono |

Il mal secco degli agrumi resta la malattia calabrese con meno foto aperte: 21 in tutto (1 su
iNaturalist). Per migliorarlo servono foto di campo dei servizi fitosanitari o dell'università, con il
loro permesso. Lo stesso vale per verticilliosi (29 foto su iNaturalist), gommosi, Phytophthora capsici e
peronospora della cipolla (meno di 15 ciascuna).

## 11. Fonti italiane e del Sud, forum (25 novembre 2026, notte)

Siti aperti nella rete dell'ambiente su richiesta: Bugwood, GBIF, Observation.org, Servizio fitosanitario
dell'Emilia-Romagna, CREA, Regioni Campania e Sicilia, emergenzaxylella.it, UNIRC.

| Fonte | Cosa aggiunge | Etichetta | Licenza e uso |
|---|---|---|---|
| Bugwood Images (Univ. Georgia: ipmimages.org) | 4.700 foto di 80 malattie e insetti: Phytophthora capsici (800), cancro del castagno (200), Xylella (112), peronospora della cipolla, verticilliosi, colpo di fuoco, Sclerotinia, mosca della frutta, dorifora, afidi... | specialisti | uso non commerciale con citazione; solo addestramento |
| Observation.org (tramite GBIF) | fino a 300 foto per specie, prima dai paesi mediterranei (molte dalla Spagna), solo identificazioni "Approved" | revisori della piattaforma | CC BY-NC o BY-NC-ND; solo addestramento |
| Servizio fitosanitario Emilia-Romagna, schede delle avversità | 291 foto: colpo di fuoco (150), sharka, aleurodide spinoso, cimice asiatica, Psa, Xylella, peronospora della cipolla | tecnici del servizio | diritto d'autore della Regione; solo addestramento (art. 70-ter) |
| ARSAC Calabria (immagini dei bollettini e degli articoli) | 9 foto calabresi: mosca delle olive, peronospora e oidio della vite (Cirò, Bagnara), cotonello dell'olivo | tecnici ARSAC | diritto d'autore; solo addestramento |
| CREA, Regioni Campania e Sicilia, emergenzaxylella.it, UNIRC | nessuna galleria di foto etichettate leggibile in automatico (pagine dinamiche o PDF divulgativi) | | non usate |

**Forum (giardinaggio, coltivazione biologica, agraria) non usati.** Le foto dei forum sono di privati,
con nome utente e a volte luoghi riconoscibili, e la diagnosi è una discussione, spesso senza conferma:
un'etichetta sbagliata insegna al modello l'errore e peggiora proprio le malattie simili tra loro.
Molti forum, inoltre, escludono nel regolamento la raccolta automatica dei contenuti. Per le foto di
privati la strada giusta è quella già prevista dall'app: i contributi con consenso, senza dati personali,
con la diagnosi confermata da un esperto.

## 12. ARSAC, Servizio fitosanitario, università, riviste, forum (26 novembre 2026)

Metodo comune per PDF e figure (`scripts/estrai_pdf.py`, `scripts/europepmc_figure.py`):
1. immagini di ogni pagina convertite in RGB (in PNG: le immagini CMYK estratte "grezze" uscivano in
   negativo) e figure composte divise in pannelli (`src/plantcare/data/pannelli.py`);
2. etichetta dalla didascalia degli autori o, per i bollettini, dal testo della pagina, solo se nomina
   **una sola** classe (`src/plantcare/data/testo_classi.py`: nomi scientifici anche abbreviati,
   sinonimi come *Spilocaea oleaginea* e *Phoma tracheiphila*, nomi italiani legati alla coltura) e se la
   coltura citata è quella della classe (una foglia di vite non diventa "marciume nero del melo");
3. filtro CLIP "foto di campo" (`src/plantcare/data/filtro_foto.py`): via grafici, alberi
   filogenetici, piastre, microscopio, locandine, schermate;
4. **verifica a vista di ogni foto** (`scripts/foglio_contatti.py`): si tengono solo quelle in cui il
   sintomo o l'insetto si vede. Le foto tenute sono in `data/external/verificate/`.

| Fonte | Materiale letto | Candidate | Tenute dopo la verifica |
|---|---|---|---|
| ARSAC (sito: 4.706 immagini, 1.547 articoli) | foto con didascalia o testo vicino | 36 | 8 (in `configs/foto_letteratura.yaml`) |
| ARSAC (628 PDF tecnici: bollettini, vademecum, schede di monitoraggio degli organismi da quarantena del Servizio fitosanitario regionale) | immagini dei PDF | 340 | 65 |
| Phytopathologia Mediterranea (1.234 articoli, 636 su malattie delle colture; CC BY) | figure con didascalia | 258 | 120 |
| UNIRC, IRIS (24.964 record, 429 pertinenti, 229 PDF aperti: tesi di dottorato e articoli) | figure con didascalia | 18 | 11 |
| IRIS di Palermo, Bari, Napoli, Basilicata (1.321 PDF elencati) | molti riservati (rimandano al login); i server Cineca rispondono "troppe richieste" anche a un PDF ogni 3 secondi | | raccolta fermata per rispetto del limite |
| IRIS di Catania | il server rifiuta la connessione sicura del proxy (errore TLS) | | non raggiungibile |
| Europe PMC (al posto di Google Scholar): 4.074 articoli aperti sulle specie del progetto, 24.335 figure; didascalie dal servizio OAI di PubMed Central, immagini dai siti degli editori (MDPI, Springer Nature/BMC, Frontiers) | 5.296 figure con una sola classe in didascalia, 9.895 pannelli | 653 | 203 (12 rietichettate: coltura sbagliata o insetto nel lettore sbagliato) |
| forum.giardinaggio.it | robots.txt assente; 3.200 titoli letti, 33 con una sola classe; dopo 160 pagine il sito chiude le connessioni | | fermato: nessuna foto usata |
| PubMed Central (pagine degli articoli) | il sito mostra un controllo anti-robot (reCAPTCHA): non aggirato | | si usa il servizio OAI ufficiale |
| forum.agraria.org | pagina di verifica anti-robot | | non usato |

In tutto **399 foto verificate** (390 dopo aver tolto le copie della stessa foto in due documenti):
307 per l'addestramento e 83 per una prova nuova, **"esperti del Sud"**, con un quarto dei documenti
tenuto da parte (foto dello stesso documento sempre nella stessa parte).

**Perché non basta l'accordo con il modello.** Sulle 185 foto verificate a mano (etichetta giusta) il
modello pubblicato mette la classe giusta al primo posto solo nel 26% dei casi e tra le prime cinque nel
50%: legno con il mal dell'esca, essudati di Psa, cancri, tubercoli di rogna sono sintomi che le foto di
campo usate finora quasi non contengono. Filtrare le candidate tenendo solo quelle su cui il modello è
d'accordo scarterebbe proprio le foto più utili: per questo la verifica è stata fatta a vista.

**Google Scholar e Google Lens** non hanno un'interfaccia per programmi e le condizioni di Google
vietano la raccolta automatica: al loro posto Europe PMC (testo completo e figure degli articoli aperti,
con la licenza di ciascuno) e gli archivi OAI-PMH delle università e delle riviste.

**Lezioni e dispense**: quelle sulle piattaforme di Ateneo richiedono le credenziali; si sono usate solo
tesi, articoli e PDF pubblici.

## Prossimi passi in ordine di impatto atteso

1. Rilevatore automatico delle foglie (due fasi) addestrato sui riquadri di PlantDoc.
2. Foto di campo calabresi con diagnosi (contributi), soprattutto olivo e agrumi.
3. Esempi estranei e misura del "non lo so" per malattie non in elenco.
4. Prova di BioCLIP per insetti e colture.
5. Foto di trappole cromotropiche per il conteggio delle mosche.
