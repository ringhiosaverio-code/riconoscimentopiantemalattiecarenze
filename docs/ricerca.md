# Ricerca di riferimento

## Stato della verifica

Ogni citazione è stata controllata con la ricerca web e, dove possibile, con il DOI o l'ID arXiv.
Legenda:

- **✅ verificata**: DOI o arXiv risolto, oppure metadati confermati da più fonti indipendenti.
- **⚠️ parziale**: metadati confermati da fonti secondarie, DOI risolto solo in parte.
- **❌ corretta**: la versione precedente era errata; la correzione è indicata.

Limite dell'ambiente di verifica: `doi.org` e `arxiv.org` sono raggiungibili, ma i redirect degli editori (Elsevier, ACM, IEEE) non lo sono. Per questo, per gli articoli Elsevier, ACM e IEEE, il DOI è stato risolto fino alla pagina dell'editore ma non se ne sono letti i metadati completi. Va riaperto il link dal proprio browser prima della pubblicazione.

## 1. Riconoscimento di malattie fogliari con deep learning

| Riferimento | DOI / ID | Stato | Note |
|---|---|---|---|
| Mohanty, Hughes, Salathé (2016). *Using Deep Learning for Image-Based Plant Disease Detection.* Frontiers in Plant Science, 7:1419 | doi:10.3389/fpls.2016.01419 | ✅ | DOI risolto su Frontiers. Il preprint arXiv 1604.03169 riporta un calo forte di accuratezza su immagini esterne ai dati di laboratorio: confermare il dato nel PDF prima di citarlo. |
| Ferentinos (2018). *Deep learning models for plant disease detection and diagnosis.* Computers and Electronics in Agriculture, 145:311–318 | doi:10.1016/j.compag.2018.01.009 | ✅ | DOI risolto su Elsevier (pii S0168169917311742). Le stime di citazioni nelle fonti trovate sono discordanti: non citarle. |
| Barbedo (2018). *Factors influencing the use of deep learning for plant disease recognition.* Biosystems Engineering, 172:84–91 | doi:10.1016/j.biosystemseng.2018.05.013 | ❌ → ⚠️ | Il DOI che avevo scritto prima (`2018.01.009`) punta a un articolo del 2016: è sbagliato. Il DOI corretto risulta da fonti secondarie e da un redirect Elsevier coerente con il 2018. Verificare sulla pagina ScienceDirect. |

## 2. Dataset principali

| Dataset | Riferimento | Stato | Contenuto verificato |
|---|---|---|---|
| **PlantVillage** | Hughes & Salathé (2015). *An open access repository of images on plant health…* arXiv:1511.08060 | ✅ | Preprint di Hughes e Salathé. Il numero di immagini citato dalle fonti è ~54.300 (TFDS) o ~54.306 (articolo di Mohanty), 38 classi coltura-malattia. |
| **PlantDoc** | Singh et al. (2020). *PlantDoc: A Dataset for Visual Plant Disease Detection.* CoDS-COMAD 2020, pp. 249–253 | ✅ | DOI 10.1145/3371158.3371196 e pagine confermate. I conteggi variano tra fonti (2.598 o 2.569 immagini; 13 specie, 17 o 27 classi): usare quelli del PDF originale. |
| **IP102** | Wu et al. (2019). *IP102: A Large-Scale Benchmark Dataset for Insect Pest Recognition.* CVPR 2019, pp. 8787–8796 | ✅ | DOI 10.1109/CVPR.2019.00899. ~75.000 immagini, 102 classi di insetti dannosi, con parte di immagini annotate con bounding box. Dataset gratuito per uso accademico: chiedere il permesso per usi commerciali all'autore (repository GitHub xpwu95/IP102). |
| **Pl@ntNet-300K** | Garcin et al. (2021). *Pl@ntNet-300K: a plant image dataset with high label ambiguity and a long-tailed distribution.* NeurIPS 2021, Datasets & Benchmarks | ⚠️ | ❌ L'ID arXiv 2105.10956 che avevo indicato è un altro articolo (sul dialogo): rimosso. Dataset su Zenodo, record 5645731, versione 1.1 (la 1.0 riporta erroneamente NeurIPS 2022). ~306.000 immagini, 1.081 specie. |
| **iNat2021** | Van Horn et al. (2021). *Benchmarking Representation Learning for Natural World Image Collections.* CVPR 2021 | ✅ | arXiv:2103.16483. Oltre 2,7 milioni di immagini e 10.000 specie. Non specifico per l'agricoltura. |
| **Plant Pathology 2020 (FGVC7)** | Thapa et al. (2020). *The Plant Pathology Challenge 2020 data set to classify foliar disease of apples.* Applications in Plant Sciences, 8(9):e11390 | ✅ | arXiv:2004.11958. 3.651 immagini reali di malattie fogliari del melo. |

**Lacune:** i dataset pubblici non coprono le **carenze nutrizionali**, i **viroidi** separati dai virus, né gli **entomofagi** delle colture target. Vedi `docs/dataset.md`, sezione "Piano per le lacune".

## 3. Modelli visivi (backbone)

| Riferimento | ID | Stato |
|---|---|---|
| Oquab et al. (2023). *DINOv2: Learning Robust Visual Features without Supervision* | arXiv:2304.07193 | ✅ |
| Tan & Le (2019). *EfficientNet: Rethinking Model Scaling for CNNs.* ICML 2019 | arXiv:1905.11946 | ✅ |
| Dosovitskiy et al. (2021). *An Image is Worth 16x16 Words.* ICLR 2021 | arXiv:2010.11929 | ✅ |
| Radford et al. (2021). *Learning Transferable Visual Models From Natural Language Supervision.* ICML 2021, PMLR 139:8748–8763 | arXiv:2103.00020 | ✅ |
| YOLO (famiglia di rilevatori) | — | Da scegliere una versione specifica e citarne il paper ufficiale prima dell'uso |

## 4. Principi metodologici

1. **Split per località e per stagione**, non casuale. Una stessa pianta fotografata più volte non deve finire in train e test. PlantVillage non ha questa informazione: lo split è casuale e quindi ottimistico.
2. **Metriche per classe**, non solo accuratezza globale: con classi sbilanciate l'accuratezza inganna. Precisione, richiamo, F1 e matrice di confusione.
3. **Calibrazione** (ECE, temperature scaling), così una probabilità dell'80% corrisponde davvero a circa l'80% di risposte corrette.
4. **Classe "non determinabile"** e soglia di rifiuto: il sistema si astiene quando i sintomi non bastano. Il compromesso copertura/accuratezza va riportato.
5. **Dati fuori distribuzione**: includere piante sane e sfondi non agricoli per ridurre i falsi positivi.
6. **Annotazione da esperti**: le etichette di malattia e carenza vanno verificate da un fitopatologo o agronomo.

## 5. Parti che richiedono revisione esperta

- Sintomi di carenze nutrizionali: confondibili con virosi, stress idrico e danni di parassiti. La mappa sintomo-carenza in `configs/taxonomy.yaml` va validata.
- Virosi e viroidi: spesso indistinguibili dall'immagine. Trattare le due classi come probabilità separate, con conferma di laboratorio.
- Entomofagi e fitofagi: la distinzione è affidabile in genere a livello di famiglia o ordine, meno a livello di specie.
