# Guida per agronomi e tecnici

PlantCare aiuta a orientarsi davanti a una pianta sintomatica. Non sostituisce il sopralluogo, l'analisi di laboratorio né la diagnosi di un tecnico abilitato.

## Come leggere il risultato

Per ogni foto il sistema mostra tre risposte:

- **Coltura**: la specie più probabile tra quelle note al sistema.
- **Malattia**: la causa più probabile, con la scheda (agente causale, ospiti, sintomi).
- **Insetto**: se presente, con il ruolo (fitofago, entomofago, impollinatore).

Accanto a ogni risposta ci sono le **prime tre ipotesi con probabilità**. Leggere sempre l'elenco, non solo la risposta principale: due ipotesi vicine indicano un caso ambiguo.

### "Non determinabile"

Il sistema risponde così quando la probabilità della prima ipotesi è sotto la soglia (predefinita 50%). Non è un errore: significa che i sintomi non bastano per decidere. Cause tipiche:

- foto sfocata, scura o troppo lontana;
- sintomi precoci o misti (più patologie sulla stessa foglia);
- sintomi che si confondono con stress idrico, carenze o danni meccanici.

### Avvertenza di laboratorio

Quando l'ipotesi è di natura **virale, viroide, batterica o nematodica**, il sistema mostra un avviso specifico. Il sintomo visivo non distingue queste cause in modo affidabile:

- **virus e viroidi**: serve ELISA o RT-PCR;
- **batteri e fitoplasmi**: serve coltura o PCR specifica;
- **nematodi**: serve analisi del terreno o dei tessuti.

Non intervenire con trattamenti specifici senza conferma, salvo indicazioni del servizio fitosanitario.

## Quale parte della pianta fotografare

Il menu "Quale parte della pianta è colpita?" è importante: lo stesso agente causa sintomi diversi su foglia, frutto, tronco o radice. Il sistema mostra i sintomi dell'organo scelto e avvisa se la malattia non è descritta su quella parte.

| Organo | Esempi |
|---|---|
| Foglia | macchie, muffe, ingiallimenti, mosaici |
| Frutto | marciumi, croste, fori di insetti, cascola |
| Fiore o infiorescenza | imbrunimenti, spiga o grappolo colpiti |
| Ramo, fusto, germoglio | cancri, disseccamenti, pastorale |
| Tronco o colletto | gommosi, cancri, carie del legno, cordoni miceliari |
| Radice | marciumi, galle, micelio bianco |
| Tubero o bulbo | rogna, marciumi molli, sclerozi, muffe |

Per patologie del tronco e delle radici (es. mal dell'esca, marciume radicale, gommosi) foto ravvicinate del colletto o del legno sono più utili della chioma.

## Come fare una buona foto

1. Foto ravvicinata della parte colpita, con luce naturale e senza flash.
2. Messa a fuoco sulla lesione, con la pagina della foglia visibile per intero se possibile.
3. Una foto della parte sana per confronto.
4. Per gli insetti: foto dall'alto e di profilo, con un riferimento di scala (es. una moneta).
5. Evitare più patologie nella stessa foto: una foto per organo.

## Il feedback

Dopo ogni risultato l'agronomo può indicare **sì** o **no**, con un commento facoltativo. Ogni risposta migliora il sistema, perché le correzioni diventano nuove etichette per l'addestramento.

- Non inserire nel commento dati personali (nomi, indirizzi, contatti).
- La foto non viene salvata con il feedback.

## Limiti da conoscere

- Il sistema riconosce sintomi visivi, non la causa biologica certa.
- Le colture di priorità 2 (tropicali presenti in Calabria) hanno pochi dati: le risposte sono meno affidabili.
- Le carenze nutrizionali non sono ancora riconosciute dal modello: la tassonomia le descrive, ma servono dati dedicati (vedi `docs/dataset.md`).
- PlantCare non indica prodotti fitosanitari, dosi o tempi di intervento: sono competenza del tecnico e del quadro normativo vigente.
- Le prestazioni sul campo possono essere più basse di quelle di laboratorio: vedi `docs/protocollo-validazione.md`.

## Cosa fare con le schede

Le schede malattie sono disponibili anche senza foto: `/api/diseases` (elenco), `/api/diseases/{id}` (dettaglio), `/api/plants?priority=1` (colture prioritarie).
