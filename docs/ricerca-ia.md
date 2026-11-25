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

## Prossimi passi in ordine di impatto atteso

1. Rilevatore automatico delle foglie (due fasi) addestrato sui riquadri di PlantDoc.
2. Foto di campo calabresi con diagnosi (contributi), soprattutto olivo e agrumi.
3. Esempi estranei e misura del "non lo so" per malattie non in elenco.
4. Prova di BioCLIP per insetti e colture.
5. Foto di trappole cromotropiche per il conteggio delle mosche.
