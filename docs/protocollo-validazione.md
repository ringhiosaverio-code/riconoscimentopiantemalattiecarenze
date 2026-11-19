# Protocollo di validazione sul campo

Obiettivo: misurare quanto PlantCare funziona su foto scattate in campo, da persone diverse da quelle che hanno costruito il modello, con una diagnosi di riferimento indipendente.

I risultati su PlantVillage e IP102 non bastano: sono immagini di laboratorio o di letteratura, e i valori riportati su questi dataset tendono a sovrastimare le prestazioni in campo (vedi `docs/ricerca.md`).

## 1. Disegno dello studio

- **Località:** almeno tre aziende o campi, in più zone agrarie (es. una pianura, una collina, una zona tropicale in Calabria per le colture di priorità 2).
- **Stagioni:** almeno due campagne, per coprire sintomi diversi.
- **Fotografi:** persone non coinvolte nell'addestramento, con un telefono qualsiasi, seguendo la guida per le foto (`docs/guida-agronomi.md`).
- **Campione:** foto di piante con sintomi e di piante sane della stessa coltura. Le piante sane sono obbligatorie.

## 2. Diagnosi di riferimento

Ogni foto ha una diagnosi di riferimento, scelta in questo ordine:

1. **Laboratorio** (ELISA, RT-PCR, coltura, analisi tissutale): per virus, viroidi, batteri, carenze.
2. **Esperto** indipendente, che vede la pianta dal vivo e non il risultato del sistema.
3. Solo se non possibili le prime due: **osservazione visiva**, marcata come tale e analizzata a parte.

Un'etichetta di riferimento è valida solo se il valutatore non ha visto la risposta di PlantCare (cieco).

## 3. Doppia lettura

Il 10% delle foto è letto da due esperti indipendenti. Si misura l'accordo tra loro con il kappa di Cohen. Se l'accordo è basso, la classe va rivista prima di usarla come riferimento.

## 4. Metriche da riportare

Per ogni testa (coltura, malattia, insetto):

- **accuratezza** e **macro-F1** sul campo;
- **F1 per classe**, con il numero di foto per classe (le classi con pochi casi vanno segnalate);
- **matrice di confusione**, per capire quali malattie si confondono;
- **ECE** (errore di calibrazione): la probabilità dichiarata è affidabile?
- **curva copertura/accuratezza**: quante foto ricevono una risposta e con quale accuratezza, al variare della soglia.

Riportare **separatamente** i risultati di campo da quelli di laboratorio. La differenza tra i due è un'informazione utile, non un errore da nascondere.

## 5. Criteri di accettazione

Da definire con un comitato di agronomi **prima** della raccolta dati, per non adattare i criteri ai risultati. Proposta di partenza da discutere:

- per le malattie ad alta frequenza nella coltura: macro-F1 sul campo almeno pari a quello su dati di validazione, con una riduzione massima concordata;
- per le classi a rischio di confusione (virosi vs carenze): tasso di risposte sbagliate sotto soglia di rifiuto riportato esplicitamente;
- per ogni classe: il numero minimo di foto di campo prima di dichiararla affidabile.

## 6. Divieti

- Non addestrare il modello sui dati di valutazione.
- Non cambiare la soglia dopo aver visto i risultati di campo: va fissata prima.
- Non escludere foto difficili senza una motivazione scritta prima del test.

## 7. Dati e privacy

- Le foto dei campi possono essere identificative (luogo, proprietà): registrarle con località anonimizzata (es. `IT-EMR-03`).
- Il consenso dell'azienda e del fotografo va raccolto prima della raccolta.
- Pubblicare solo risultati aggregati, non le foto dei singoli campi senza consenso.

## 8. Report finale

Un documento unico con: disegno, campione, diagnosi di riferimento e accordo tra valutatori, metriche per testa, errori tipici, limiti e le decisioni prese sulla soglia.
