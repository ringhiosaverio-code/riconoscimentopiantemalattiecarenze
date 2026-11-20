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

Provati sulle caratteristiche in cache (`scripts/improve_readers.py`): insieme di più lettori e pesatura delle foto di campo. I risultati sono nella sezione seguente.

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
