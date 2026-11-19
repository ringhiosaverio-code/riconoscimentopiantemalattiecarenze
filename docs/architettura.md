# Architettura

## Obiettivo del modello

Dato un insieme di foto della stessa pianta o foglia, il sistema produce insieme:

| Testa | Output | Tipo |
|---|---|---|
| `plant` | Specie vegetale | Softmax su `plants` |
| `pathogen` | Tipo di agente (fungina, virale, viroide, batterica, da insetti, abiotica, nutrizionale, sana) | Softmax su `pathogen_types` |
| `disease` | Malattia specifica | Sigmoid multi-label (una foto può avere più malattie) |
| `insect` | Specie di insetto | Softmax su `insects` + ruolo (`phytophagous`/`entomophagous`/`pollinator`) |
| `nutrient` | Carenza macro o micro, o "non determinabile" | Sigmoid multi-label su `nutrients` |

Le teste sono **multi-label** dove una foto può avere più etichette contemporaneamente (malattia e carenza insieme, più insetti). Le uscite sono probabilità, non decisioni.

## Pipeline

```
foto → [controllo qualità] → [rilevamento ROI, opzionale] → backbone condiviso → teste multi-task
                                                                                    ↓
                         [calibrazione + soglia di rifiuto] → referto con confidenza e avvertenze
```

1. **Controllo qualità.** Scarta foto sfocate, troppo scure o senza soggetto. Restituire il motivo.
2. **Rilevamento (opzionale).** Un rilevatore (YOLO) isola la foglia o l'insetto. Riduce il rumore di sfondo, che è una causa nota di errore in campo.
3. **Backbone condiviso.** DINOv2 o EfficientNet pre-addestrato. Le feature sono condivise tra le teste.
4. **Teste multi-task.** Perdita combinata: somma pesata delle perdite delle singole teste. I pesi vanno tarati, perché i dataset hanno dimensioni molto diverse.
5. **Calibrazione e rifiuto.** Temperature scaling per testa. Sotto soglia, l'uscita è "non determinabile".
6. **Referto.** Specie, probabilità del tipo di agente, malattie candidate, insetti con ruolo, carenze candidate, più le avvertenze pertinenti (es. "conferma di laboratorio consigliata" per le virosi).

## Regole di sicurezza nell'output

- Mai una sola etichetta certa: sempre una lista con probabilità.
- Per virus e viroidi: avvertenza obbligatoria e suggerimento di analisi di laboratorio.
- Per insetti: segnalare quando la specie non è determinabile e mostrare il livello tassonomico raggiunto.
- Per carenze: mostrare sempre le cause alternative (virosi, stress idrico, parassiti) e la classe "non determinabile".
- Non dare raccomandazioni di prodotti fitosanitari né dosi: fuori scopo e di competenza di un tecnico abilitato.

## Divisione dei dati

- **Train / validazione / test** divisi per **località o campagna**, non casualmente.
- Un **set di campo** separato, raccolto con foto di smartphone in condizioni reali, è il riferimento finale.
- Ogni immagine con metadati: specie, data, località, dispositivo, conferma diagnostica (laboratorio, esperto o nessuna).

## Metriche

- Per testa: precisione, richiamo, F1 per classe; macro-F1 come riepilogo.
- Calibrazione: errore di calibrazione atteso (ECE).
- Copertura vs accuratezza: percentuale di foto a cui il sistema risponde, con accuratezza su quelle risposte, al variare della soglia.
- Prestazioni separate su dati di laboratorio e di campo: la differenza è un indicatore diretto di generalizzazione.

## Fasi

| Fase | Contenuto |
|---|---|
| 0 (ora) | Tassonomia validata, pacchetto con test |
| 1 | Baseline su PlantVillage e IP102 (malattie e fitofagi), valutazione su PlantDoc |
| 2 | Teste per insetti entomofagi e impollinatori, raccolta dati propria |
| 3 | Carenze nutrizionali: raccolta, annotazione con agronomo, modello dedicato |
| 4 | Test di campo, calibrazione, interfaccia con soglia di rifiuto |
