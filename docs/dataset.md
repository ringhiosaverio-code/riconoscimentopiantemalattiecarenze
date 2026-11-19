# Dataset: piano di raccolta, pipeline e licenze

I dati grezzi **non vanno nel repository** (sono in `data/`, ignorata da git).

## Dataset usati nella baseline

| Dataset | Compito | Layout atteso in `data/raw/` | Come si ottiene |
|---|---|---|---|
| PlantVillage | coltura + malattia (38 classi) | `plantvillage/` con cartelle `Coltura___Malattia` in `raw/color/`, più `leaf_grouping/leaf-map.json` | Repository spMohanty su GitHub (dati su Hugging Face `mohanty/PlantVillage`). Licenza indicata come CC BY-SA 3.0 nel loader: verificarla |
| IP102 | fitofago (102 classi) | `ip102/images/` + `train.txt`, `val.txt`, `test.txt`; nomi in `configs/ip102_classes.yaml` | Download da Google Drive o AliyunDrive, linkati dal repository xpwu95/IP102; uso accademico |

## Pipeline

```bash
plantcare build-manifest --check   # crea data/processed/manifest.csv e controlla duplicati e immagini corrotte
plantcare train -c configs/train_baseline.yaml
plantcare serve --checkpoint models/baseline/model.pt
```

Passi della pipeline:

1. **Scansione.** PlantVillage: una riga per immagine, con coltura e malattia dal nome della cartella. IP102: righe dai file di split ufficiali.
2. **Split.** PlantVillage: per gruppo di foglia, usando `leaf_grouping/leaf-map.json` del dataset ufficiale. Tutte le foto di una stessa foglia vanno nello stesso split, altrimenti il risultato è ottimistico. Il README ufficiale riporta 54.306 immagini, 14 specie e 26 malattie. IP102: split ufficiali (train/val/test.txt).
3. **Controllo duplicati tra split.** Hash SHA-256: foto identiche in split diversi sono una fuga di dati e vengono segnalate.
4. **Controllo immagini.** Immagini corrotte segnalate prima dell'addestramento.
5. **Manifest.** CSV con colonne `path, source, split, plant, disease, pest`. È l'unico ingresso del training.
6. **Mappatura alla tassonomia.** `configs/label_maps.yaml` collega le classi grezze agli id di `configs/taxonomy.yaml`. Le classi non mappate restano grezze e vengono segnalate.

## Schema dei metadati (dataset propri)

Per i dati raccolti in proprio, il manifest si estende con questi campi:

```yaml
image_id: "2026-06-12_tom_0001"
plant: solanum_lycopersicum
pathogen_type: fungal           # id di pathogen_types
diseases: [tomato_late_blight]  # lista, può essere vuota
insects: []                     # id di insects
nutrients: []                   # es. [N] o [Fe, Mg]
nutrients_undetermined: false
organ: leaf                     # leaf | fruit | stem | root | flower | whole_plant
diagnosis: expert               # lab | expert | visual_only
location: "anonimizzata, es. IT-EMR-03"
date: 2026-06-12
device: smartphone
license: CC-BY-4.0
source: "nome del dataset o raccolta propria"
```

## Piano per le lacune

I dataset pubblici non coprono tre aree. Per ciascuna serve una raccolta dedicata, con un riferimento diagnostico.

### 1. Carenze nutrizionali

- **Perché non bastano i dati pubblici:** non esistono dataset di qualità con carenze confermate da analisi.
- **Metodo proposto:** prove in vaso con omissione controllata di un solo elemento per volta (es. piante di pomodoro o frumento senza azoto, poi senza ferro), con fotografie a intervalli regolari. Il riferimento è l'analisi del tessuto fogliare (macro e micro) in laboratorio, non il solo giudizio visivo.
- **Controlli:** un gruppo di piante con nutrizione completa per ogni prova, per distinguere la carenza dallo stress generico.
- **Responsabile scientifico:** un agronomo o un chimico del suolo che valida la mappa sintomo-carenza.

### 2. Viroidi separati dai virus

- **Perché non bastano i dati pubblici:** PlantVillage e gli altri dataset non distinguono viroidi e virus; spesso i sintomi si sovrappongono.
- **Metodo proposto:** raccogliere foto di piante con diagnosi molecolare confermata (RT-PCR o sequenziamento) per il viroide della tuberizzazione fusiforme della patata e per i virus del pomodoro. Richiedere la collaborazione dei servizi fitosanitari regionali o di laboratori universitari che hanno già questi campioni.
- **Regola:** nessuna etichetta "viroide" senza conferma molecolare; le foto senza conferma restano nella classe virale generica o nelle classi di sospetto.

### 3. Entomofagi

- **Perché non bastano i dati pubblici:** IP102 riguarda solo fitofagi; non esistono dataset agronomici di entomofagi.
- **Metodo proposto:** foto di insetti utili catturati con trappole gialle o raccolta a vista nelle colture target, identificati da un entomologo fino al livello di famiglia o specie. Le specie utili più comuni (coccinellidi, crisopidi, imenotteri parassitoidi, antocoridi) sono le prime da coprire.
- **Bilanciamento:** per ogni entomofago servono foto di più stadi (uovo, larva, adulto), perché l'aspetto cambia molto.
- **Collaborazione:** centri di lotta biologica e servizi di difesa integrata, che già monitorano questi insetti.

## Regole di qualità

1. Una diagnosi confermata da laboratorio pesa più di una solo visiva: campo `diagnosis`.
2. Foto di campo e di laboratorio si riportano separatamente nelle metriche.
3. Piante sane obbligatorie: senza di esse il modello segnala malattie ovunque.
4. Doppia annotazione per il 10% delle immagini, con misura dell'accordo (kappa di Cohen).
5. Nessuna informazione personale in immagini o metadati: niente volti, targhe, indirizzi precisi dei campi.

## Licenze

Ogni dataset ha la sua licenza, che vincola il riuso dei pesi del modello. Registrare in `data/SOURCES.md` (non versionato): nome, URL, licenza, data di accesso.

## Verifiche sui dataset (fatte il 2026-11-19)

- Nomi delle 38 classi PlantVillage: letti dal loader ufficiale `plant_village.py` del repository spMohanty. Sono in `configs/label_maps.yaml`: 20 collegate alla tassonomia, 18 senza corrispondenza (`null`).
- Nomi delle 102 classi IP102: da `classes.txt` del repository xpwu95/IP102, indici 1-based (`configs/ip102_classes.yaml`).
- Split ufficiali PlantVillage (`splits/*_train.txt`): non raggiungibili da questo ambiente, perché ospitati su Hugging Face. La pipeline usa la mappa dei gruppi foglia, che invece è accessibile.
- Base degli indici nei file `train.txt` di IP102 (0 o 1): non verificata, perché i file non sono scaricabili da questo ambiente. Va controllata e impostata in `configs/datasets.yaml`.

## Registro delle fonti usate

| Dataset | Fonte scaricata | Data | Note |
|---|---|---|---|
| PlantVillage (raw/color, 38 classi, 54.305 immagini) | `data.zip` di Hugging Face `mohanty/PlantVillage`, con `leaf_grouping/leaf-map.json` | 2026-11-19 | Licenza da verificare alla fonte. Il README dichiara 54.306 immagini: il file scaricato ne contiene 54.305. |
| IP102 | non scaricato | — | Download da Google Drive o AliyunDrive, non raggiungibile da questo ambiente |

Il manifest generato contiene 37.902 immagini di train, 8.164 di val e 8.239 di test, con split per gruppo di foglia. Il controllo SHA-256 non ha trovato duplicati tra split, e nessuna immagine risulta corrotta.
