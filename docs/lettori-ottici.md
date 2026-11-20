# Lettori ottici: risultati dell'addestramento

Modello: `models/readers_vit_small_patch14_dinov2+efficientnet_b0/readers.pt` (131 MB, non versionato).
Caratteristiche: DINOv2 ViT-S/14 ed EfficientNet-B0 pre-addestrati, concatenati (insieme di estrattori, come in Bruno, Moroni e Martinelli, CNR-ISTI 2023). Immagini a 224 px. Un lettore MLP per testa, scelto tra lineare e MLP sul set di validazione. Probabilità calibrate con temperature scaling.
Dati: 170.376 immagini (PlantVillage, PlantDoc, IP102, iNatAg, 10 dataset Project-AgML). Data dell'addestramento: 20 novembre 2026.

## Risultati sul set di test

| Lettore | Classi | Accuratezza | Macro-F1 | Errore di calibrazione (ECE) |
|---|---|---|---|---|
| Coltura | 32 | 98,5% | 0,903 | 0,5% |
| Malattia | 69 | 96,0% | 0,905 | 0,5% |
| Insetti e acari | 102 | 73,8% | 0,668 | 2,7% |
| Carenze | 4 | 99,4% | 0,933 | 0,2% |

**Questi numeri complessivi sono ottimistici.** Sono dominati da PlantVillage, che ha foto di laboratorio su sfondo uniforme. Le misure che contano per l'uso in campo sono queste:

| Lettore | Foto di campo | Accuratezza | Macro-F1 |
|---|---|---|---|
| Coltura | iNatAg (piante intere, iNaturalist) | 79,0% | 0,786 |
| Coltura | PlantDoc (foglie fotografate in campo) | 89,4% | 0,853 |
| Malattia | PlantDoc | **76,1%** | 0,696 |
| Insetti e acari | IP102 (split ufficiali) | 73,8% | 0,668 |

## Avvertenze sulla lettura dei risultati

- **Coltura sui dataset AgML (100%)**: ogni dataset AgML contiene una sola coltura, quindi il lettore può riconoscere lo stile delle foto del dataset invece della pianta. Questo risultato non misura il riconoscimento della specie.
- **Split casuali**: PlantVillage è diviso per gruppo di foglia; i dataset AgML sono divisi a caso, quindi foto quasi identiche possono essere in train e test. Le loro accuratezze sono ottimistiche.
- **Carenze**: il nutriente è indicato solo per il calcio (11 foto di test) e per l'eccesso di azoto (4 foto di test). Per classe: calcio F1 0,82; eccesso di azoto 4 su 4; sintomi di carenza generici F1 0,92. Sono indicazioni preliminari.
- **Insetti**: i nomi sono quelli originali di IP102, in inglese. IP102 riguarda soprattutto riso, mais, frumento, barbabietola, erba medica, vite, agrumi e mango.

## Copertura contro accuratezza (malattia)

Con la soglia di astensione il lettore risponde meno spesso ma sbaglia meno:

| Soglia | Foto con risposta | Accuratezza sulle risposte |
|---|---|---|
| 0,3 | 99,7% | 96,2% |
| 0,5 | 98,6% | 96,8% |
| 0,7 | 96,3% | 97,8% |
| 0,9 | 91,7% | 98,8% |

Lo stesso compromesso per gli insetti: con soglia 0,5 risponde all'80% delle foto con accuratezza 83%; con soglia 0,9 al 42% con accuratezza 92%.

## Prova nell'app

Su tre foto di test mai viste (peperone sano di PlantDoc, insetto di IP102, pomodoro con eccesso di azoto) tutti i lettori hanno risposto correttamente. Gli altri lettori hanno risposto "non determinabile" dove la foto non conteneva il loro soggetto. Tempo per foto: circa 0,15 secondi su CPU, inclusa la media con l'immagine specchiata.

## Come migliorare l'accuratezza in campo

1. **Foto di campo calabresi e siciliane** raccolte con il protocollo (`docs/protocollo-raccolta-foto.md`): è la leva principale, perché il divario tra laboratorio (99%) e campo (76%) dipende dai dati.
2. **Fine-tuning** degli estrattori sulle foto di campo, su una macchina con GPU.
3. **Feedback degli agronomi** dall'app: le correzioni diventano nuove etichette.
4. Dataset con split per località e stagione, per misure non ottimistiche.

## Avvio con il modello

```bash
PLANTCARE_CKPT=models/readers_vit_small_patch14_dinov2+efficientnet_b0/readers.pt plantcare serve
```
