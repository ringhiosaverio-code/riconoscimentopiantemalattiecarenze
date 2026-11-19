# Pubblicazione del servizio

## Requisiti prima di pubblicare

1. **Modello addestrato e validato** (vedi `docs/protocollo-validazione.md`). Senza checkpoint il sito funziona, ma `/predict` risponde 503.
2. **Licenza scelta** per il codice e per i pesi del modello. Dipende dalle licenze dei dataset di addestramento: PlantVillage e IP102 hanno condizioni proprie.
3. **Revisione legale della privacy**: le foto caricate passano dal server. L'app non le salva, ma il gestore del servizio deve documentare log, backup e tempi di conservazione.
4. **Revisione scientifica** dei testi della pagina e delle schede malattie da parte di un fitopatologo.

## Esecuzione con Docker

```bash
docker build -t plantcare .
docker run -d -p 8000:8000 \
  -e PLANTCARE_CKPT=/app/models/baseline/model.pt \
  -e PLANTCARE_FEEDBACK_DIR=/app/feedback \
  -v "$PWD/models:/app/models:ro" \
  -v "$PWD/feedback:/app/feedback" \
  plantcare
curl http://127.0.0.1:8000/health
```

Senza `PLANTCARE_FEEDBACK_DIR` il feedback resta disattivato. Senza `PLANTCARE_CKPT` il servizio non fa predizioni.

La build è stata preparata ma **non ancora eseguita**: nell'ambiente di sviluppo il demone Docker non era disponibile. Va provata prima della pubblicazione.

## Dietro un proxy HTTPS

Mettere il container dietro un reverse proxy con TLS (Caddy, nginx, Traefik). Il proxy deve:

- limitare la dimensione delle richieste (il server accetta foto fino a 10 MB);
- limitare la frequenza delle richieste per indirizzo IP, perché l'API non ha autenticazione;
- non registrare il corpo delle richieste (contiene le foto).

## Cosa non fa il servizio

- Non autentica gli utenti: chiunque può usare `/predict` e `/api/feedback`. Per un uso riservato agli agronomi serve un livello di accesso davanti al servizio.
- Non ha un database: il feedback è un file JSON Lines in `PLANTCARE_FEEDBACK_DIR`. Per volumi maggiori va sostituito.
- Non ha un sistema di aggiornamento del modello: si sostituisce il checkpoint e si riavvia il container.

## Verifiche consigliate dopo il deploy

- `GET /health` restituisce `model_loaded: true` e la versione del modello attesa.
- Caricare una foto di prova e verificare che l'avvertenza di laboratorio compaia per le malattie virali.
- Verificare che `/docs` mostri le schede e che la pagina principale funzioni su telefono.
