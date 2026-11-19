# Ricerca di riferimento

Questo documento raccoglie le basi scientifiche su cui si appoggia il progetto. Le citazioni sono state compilate **senza verifica online e senza DOI**: prima di ogni uso in pubblicazioni o decisioni tecniche, controllare ogni voce.

## 1. Riconoscimento di malattie fogliari con deep learning

- **Mohanty, Hughes, Salathé (2016).** *Using Deep Learning for Image-Based Plant Disease Detection.* Frontiers in Plant Science. Dimostra che una CNN addestrata su PlantVillage raggiunge elevata accuratezza su immagini di laboratorio. È il riferimento di partenza più citato.
- **Ferentinos (2018).** *Deep learning models for plant disease detection and diagnosis.* Computers and Electronics in Agriculture. Confronto di architetture su dataset ampi.
- **Barbedo (2018, 2019).** Analisi dei fattori che limitano il deep learning in campo: sfondi complessi, illuminazione, più patologie sulla stessa foglia, sintomi precoci. Argomento centrale per la fase di validazione.

## 2. Dataset principali

| Dataset | Contenuto | Uso previsto | Note |
|---|---|---|---|
| **PlantVillage** (Hughes & Salathé, 2015; arXiv:1511.08060) | ~54k immagini, 14 specie, 26 malattie | Baseline per malattie | Fondo uniforme, quasi solo laboratorio: sovrastima le prestazioni in campo |
| **PlantDoc** (Singh et al., 2020) | Immagini da web, ~2.6k, 13 specie, 27 classi | Test di robustezza in condizioni reali | Piccolo, annotazione rumorosa |
| **PlantNet-300K** (Garcia-Ospina et al., 2021, NeurIPS) | ~300k immagini, ~1.08k specie | Riconoscimento specie | Foto da cittadini; buona varietà di condizioni |
| **IP102** (Wu et al., 2019, CVPR) | ~75k immagini, 102 specie di insetti dannosi | Fitofagi | Dataset di riferimento per i parassiti |
| **iNaturalist 2021** (Van Horn et al., 2021) | Molte specie, anche insetti | Pre-addestramento su insetti utili e nei generali | Non specifico per l'agricoltura |
| **Plant Pathology 2020 – FGVC7** (Thapa et al., 2020; arXiv:2004.11958) | Foglie di melo, 4 classi | Benchmark piccolo di sanità/malattia | Utile per test rapidi |

**Lacuna nota:** non esiste un dataset pubblico di qualità per le **carenze nutrizionali** né per i **viroidi** separati dai virus. Vanno costruiti con raccolta propria, con diagnosi di laboratorio associata. Per gli **entomofagi** non esistono dataset agronomici standard: serve raccolta dedicata sugli insetti utili delle colture target.

## 3. Modelli visivi (backbone)

- **DINOv2** (Oquab et al., 2023; arXiv:2304.07193). Apprendimento auto-supervisionato, buone feature generali e robuste. Candidato principale come backbone condiviso.
- **EfficientNet** (Tan & Le, 2019, ICML). Compromesso efficienza/accuratezza, adatto a dispositivi mobili.
- **Vision Transformer** (Dosovitskiy et al., 2021, ICLR). Efficace con molti dati o pre-addestramento forte.
- **CLIP** (Radford et al., 2021). Utile per classificazione a zero-shot e per descrivere classi rare, ad esempio gli insetti con pochi esempi.
- **YOLO** (famiglia di rilevatori). Serve per localizzare le lesioni o gli insetti in foto con più oggetti, non per la sola classificazione.

## 4. Principi metodologici da seguire

1. **Split per località e per stagione**, non casuale. Una stessa pianta fotografata più volte non deve finire in train e test.
2. **Metriche per classe**, non solo accuratezza globale: con classi sbilanciate l'accuratezza inganna. Usare precisione, richiamo, F1 e matrice di confusione.
3. **Calibrazione della confidenza** (temperature scaling o simili), così una probabilità dell'80% significa davvero circa l'80%.
4. **Classe "non determinabile"** e soglia di rifiuto: il sistema deve astenersi quando i sintomi non bastano.
5. **Dati fuori distribuzione**: includere foto di piante sane, altre specie e sfondi non agricoli, per ridurre i falsi positivi.
6. **Annotazione da esperti**: ogni etichetta di malattia o carenza va verificata da un fitopatologo o agronomo. Le etichette di PlantVillage non sempre sono corrette.

## 5. Parti scientifiche su cui serve revisione esperta

- Sintomi di carenze nutrizionali: confondibili con virosi, stress e danni da insetti; la mappa sintomo-carenza in `configs/taxonomy.yaml` va validata con un agronomo.
- Distinzione visiva tra virosi e viroidi: spesso non possibile dall'immagine. Il modello dovrebbe trattare le due classi come probabilità separate, con conferma diagnostica.
- Entomofagi e fitofagi: distinzione possibile in genere a livello di famiglia o ordine. Per la specie serve spesso un esemplare o un campione.
