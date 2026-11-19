# Protocollo di raccolta foto per organo

Questo protocollo serve a raccogliere foto di campo con lo stesso metodo, in modo che i dati di aziende, stagioni e fotografi diversi siano confrontabili. È pensato per agronomi, tecnici dei servizi fitosanitari e collaboratori. Per la validazione delle prestazioni vedi `docs/protocollo-validazione.md`.

## 1. Principi

1. **Ogni foto ha una diagnosi di riferimento**, anche se provvisoria: senza, la foto non entra nel dataset di addestramento.
2. **Più organi per pianta**: la stessa pianta si documenta su foglia, frutto, fusto e radice quando sono colpiti.
3. **Una pianta sana per confronto** per ogni coltura e per ogni campo.
4. **Niente ritocchi**: nessun filtro, nessun ritaglio che tolga sintomi o contesto. Il ridimensionamento lo fa il software.
5. **Privacy**: nessuna persona, targa o indirizzo esatto nelle foto. La località è un codice aziendale.

## 2. Attrezzatura minima

- Smartphone con fotocamera di almeno 12 megapixel, obiettivo principale (non grandangolo, non zoom digitale).
- **Riferimento di scala**: una moneta da 2 euro o un cartoncino di dimensioni note, posato nel piano della lesione.
- **Sfondo neutro**: foglio bianco o grigio, da usare per organi piccoli, campioni estirpati e insetti.
- Sacchetti di plastica con chiusura, contenitori con etanolo al 70% per gli insetti, cartellino a matita impermeabile.
- Scheda di raccolta (`docs/templates/scheda_raccolta_foto.csv`), una riga per foto.
- Lente da 10x per gli insetti piccoli (tripidi, afidi, aleurodi).

## 3. Impostazioni della fotocamera

- Formato JPEG (o HEIC convertito in JPEG al rientro), risoluzione massima.
- Flash **spento**. Preferire la luce diffusa: nuvole, o all'ombra, alle 9-11 e alle 15-17.
- Non fotografare con pioggia, vento forte o foglie bagnate da rugiada: le gocce creano riflessi.
- Messa a fuoco sul soggetto con tocco sullo schermo. Se disponibile, bloccare l'esposizione.
- Distanza: 20-30 cm per la lesione, 1-2 m per l'insieme della pianta, con l'intero soggetto nell'inquadratura.

## 4. Quante foto

Per ogni pianta sintomatica:

| Foto | Contenuto | Quante |
|---|---|---|
| Insieme | pianta intera o porzione di filare, con contesto | 1 |
| Dettaglio | la parte colpita, a 20-30 cm, con scala | 2-3 per organo |
| Confronto | la stessa parte in una pianta sana vicina | 1 |

Per ogni campo: almeno cinque piante sintomatiche in punti distanti tra loro, più una pianta sana per ciascuna coltura.

## 5. Come fotografare ogni organo

| Organo | Cosa fotografare | Distanza e vista | Errori da evitare |
|---|---|---|---|
| **Foglia** | tre foglie a diverse altezze: pagina superiore e inferiore di una foglia sintomatica, l'intera foglia | 20 cm, foglia su fondo neutro | sole diretto sulla foglia, foglia tagliata a metà dal bordo |
| **Frutto** | frutto intero; frutto tagliato a metà per vedere la polpa; dettaglio della lesione | intero a 30 cm, taglio su foglio bianco | frutto con la lesione fuori inquadratura |
| **Fiore o infiorescenza** | infiorescenza o spiga o grappolo intero; dettaglio del fiore o della spighetta | intero a 30 cm, dettaglio a 10 cm | fiori già caduti: fotografare anche la parte colpita |
| **Fusto o culmo** | tratto di fusto con la lesione; in caso di sospetto vascolare, sezione trasversale su bianco | 20 cm; sezione a 10 cm | sezione obliqua o sporca di terra |
| **Ramo o germoglio** | ramo con la lesione e la foglia attaccata; sezione del ramo se c'è annerimento interno | 20-30 cm | ramo senza foglie e senza contesto |
| **Tronco o colletto** | corteccia con la lesione; gommosi o cancri con essudato; colletto scoperto alla base | 50 cm per il tronco, 15 cm per il dettaglio | tronco fotografato da troppo lontano |
| **Radice** | pianta estirpata con radici intere, lavate delicatamente, su foglio bianco; dettaglio delle radici lesionate | 30 cm su foglio bianco | radici asciutte o spezzate senza annotarlo |
| **Tubero** | tuberi interi con la buccia; tubero tagliato a metà per vedere la polpa; eventuali sclerozi | 20 cm, taglio su bianco | tuberi bagnati di terra, buccia non visibile |
| **Bulbo** | bulbo intero; bulbo tagliato in longitudinale per vedere il collo e le radici | 20 cm, taglio su bianco | bulbo già tagliato e marcio senza foto intera |
| **Insetto** | adulto dal dorso e dal ventre; larva; esemplare sul foglio bianco con scala | 2-5 cm, lente 10x per gli insetti piccoli | insetto fotografato sulla pianta mosso o nascosto |
| **Danno da insetti** | danno e insetto insieme, se presente | 20 cm | foto del danno senza l'insetto quando c'è |

### Foto per coltura

- **Olivo**: tronco e rami (rogna, cancri, tumori, cordoni miceliari), frutti (occhio di pavone, lebbra, fori della mosca), foglie su entrambe le pagine, radici al colletto se la pianta è deperita.
- **Vite**: grappolo intero, acini singoli, tralcio e foglia della stessa parte, tronco per l'esca (corteccia e legno con sezione).
- **Pomodoro, peperone, peperoncino, melanzana**: foglia, frutto tagliato, fusto alla base.
- **Patata**: pianta intera, fusto alla base (nero), tuberi tagliati.
- **Cipolla di Tropea e aglio**: foglie, bulbo tagliato, radici; in campo, anche le foglie flosce.
- **Broccolo**: foglia, infiorescenza, radici estirpate (ernia del cavolo).
- **Frumento e mais**: spiga o pannocchia, culmo, foglie.
- **Agrumi e bergamotto**: foglie, frutto con lesioni, tronco con gommosi, rametto secco.
- **Avocado e banano**: radici, foglia, frutto, pseudofusto in sezione (banano).
- **Frutta a nocciolo e pomacee**: frutto con lesione, rametto con cancri, fiore in fioritura.
- **Fragola**: colletto, foglia con bordi arrotolati, frutto.
- **Fico d'India**: cladodio (pala) con colonie di cocciniglia e frutto.

## 6. Insetti: raccolta e conservazione

1. Le trappole gialle adesive servono per afidi, aleurodi e mosche. Posizionarle in campo nella fase di attività dell'insetto, e annotare la data di sostituzione.
2. Per gli insetti notturni (es. lepidotteri) usare le trappole previste dal servizio fitosanitario regionale.
3. Campionare solo ciò che serve: un esemplare per specie e per stadio, più le larve se presenti.
4. Conservare gli insetti in etanolo al 70%, in contenitori etichettati con data, luogo, coltura e numero di campione.
5. Far identificare gli esemplari da un entomologo. Fino all'identificazione, il campo `insect_candidate` resta indicativo.
6. Le foto dell'insetto vanno fatte prima di conservarlo: l'etanolo cambia il colore.

## 7. Campioni destinati al laboratorio

Quando serve conferma di laboratorio (virus, viroidi, batteri, nematodi, carenze):

1. **Foto prima del prelievo**, con la pianta e la parte colpita.
2. Prelevare la parte sintomatica e una parte sana, in sacchetti separati.
3. Assegnare un codice al campione e riportarlo nella colonna `lab_sample_id`.
4. Conservare a 4 °C e inviare entro 24-48 ore, come indicato dal laboratorio.
5. Quando il risultato arriva, aggiornare la scheda con `diagnosis_source = lab` e `diagnosis_reference` con il numero del referto.

## 8. Nomi dei file

Formato: `AAAA-MM-GG_CODICEAZIENDA_COLTURA_PIANTA_ORGANO_NN.jpg`

Esempio: `2026-06-12_AZ03_olea_P01_fruit_01.jpg`

- `CODICEAZIENDA`: codice interno, mai il nome dell'azienda.
- `NN`: numero progressivo della foto sulla stessa parte.

## 9. Scheda di raccolta (metadati)

| Campo | Obbligatorio | Contenuto |
|---|---|---|
| `image_id` | sì | identificativo unico della foto |
| `file` | sì | nome del file |
| `date`, `time` | sì | data e ora della foto |
| `farm_code` | sì | codice aziendale anonimo |
| `crop_id` | sì | id della coltura nella tassonomia |
| `plant_code` | sì | numero della pianta nel campo |
| `organ` | sì | id dell'organo (`leaf`, `fruit`, `trunk`, ...) |
| `view` | sì | `overview`, `close_up`, `cross_section`, `underside` |
| `scale_reference` | no | riferimento di scala usato |
| `symptoms_observed` | sì | sintomi visti, con parole proprie |
| `disease_candidate` | no | id della malattia ipotizzata |
| `insect_candidate` | no | id dell'insetto ipotizzato |
| `healthy_reference` | sì | `yes` per pianta sana, `no` per sintomatica |
| `lab_sample_id` | no | codice del campione inviato al laboratorio |
| `diagnosis_source` | sì | `lab`, `expert`, `visual_only` |
| `diagnosis_reference` | no | numero del referto o nome dell'esperto |
| `photographer_role` | sì | ruolo, non nome (es. `tecnico`, `agronomo`) |
| `device` | no | modello dello smartphone |
| `consent_id` | sì | riferimento al consenso firmato dall'azienda |
| `notes` | no | note libere, senza dati personali |

**Le coordinate GPS precise non vanno nel dataset.** Se servono per il campionamento, restano in un registro separato con accesso limitato.

## 10. Controllo di qualità prima dell'invio

Prima di accettare una foto nel dataset, controllare:

- [ ] la parte colpita è a fuoco e visibile;
- [ ] non ci sono persone, targhe o indirizzi riconoscibili;
- [ ] il riferimento di scala è presente, quando richiesto;
- [ ] l'organo nella scheda corrisponde all'organo fotografato;
- [ ] la diagnosi di riferimento è indicata, anche se visiva;
- [ ] il consenso dell'azienda è registrato.

Le foto che non superano il controllo non vengono scartate senza annotazione: si marcano come `rejected` con il motivo.

## 11. Etichettatura e doppia lettura

1. Due lettori indipendenti etichettano il 10% delle foto senza vedere le etichette dell'altro.
2. Se sono in disaccordo, un terzo esperto decide.
3. Il risultato di laboratorio prevale su qualunque lettura visiva.
4. Si calcola il kappa di Cohen sulla doppia lettura e lo si riporta nel report.

## 12. Obiettivi di campionamento (da fissare con il comitato)

Proposta di partenza da discutere, non ancora approvata:

- almeno 100 foto per ogni coppia malattia-organo, distribuite su almeno tre aziende;
- almeno 50 foto di piante sane per ogni coltura;
- per le colture di priorità 2 e 3 e per le classi rare, obiettivi più bassi ma dichiarati come tali nel report.

## 13. Consenso, privacy e conservazione

- Consenso scritto dell'azienda prima della prima foto, con indicazione dell'uso (addestramento, pubblicazione dei risultati aggregati).
- Il proprietario può ritirare il consenso: le sue foto vengono rimosse dal dataset di addestramento alla release successiva.
- Le foto non vanno pubblicate senza un'ulteriore autorizzazione scritta.
- Il fotografo non ha diritti sulla foto: i diritti restano all'azienda e al progetto, come stabilito nel consenso.
- Conservare le schede separate dal dataset, con accesso limitato.
