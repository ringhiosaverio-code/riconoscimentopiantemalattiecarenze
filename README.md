# PlantCare

Sistema di riconoscimento visivo (deep learning) per piante di interesse agrario, con l'obiettivo di:

1. **riconoscere la specie vegetale**, con priorità alle colture agrarie;
2. **riconoscere malattie** di origine fungina, virale, da viroidi, batterica e da danni di insetti;
3. **riconoscere insetti** distinguendo gli **entomofagi** (utili: predatori, parassitoidi, impollinatori) dai **fitofagi** (dannosi);
4. **stimare carenze nutrizionali** macro (N, P, K, Ca, Mg, S) e micro (Fe, Mn, Zn, Cu, B, Mo, Cl) dalle foto delle foglie.

> **Avvertenza.** PlantCare è uno strumento di **supporto alla decisione** per tecnici e agricoltori, non una diagnosi.
> Le immagini descrivono sintomi, non sempre la causa. Virus e viroidi richiedono conferma di laboratorio (ELISA, RT-PCR).
> Le carenze hanno sintomi che si confondono con virosi, stress idrico e danni di parassiti: il sistema deve poter rispondere **"non determinabile"**.

## Stato del progetto

| Area | Stato |
|---|---|
| Tassonomia (specie, agenti, malattie, insetti, nutrienti) | Prima versione in `configs/taxonomy.yaml` |
| Validazione della tassonomia e test | Implementata (`src/plantcare/taxonomy.py`, `tests/`) |
| Documentazione di ricerca e dataset | `docs/ricerca.md`, `docs/dataset.md` |
| Architettura del modello | `docs/architettura.md` |
| Pipeline di dati e addestramento | Da fare |
| Inferenza e interfaccia | Da fare |

## Struttura

```
configs/taxonomy.yaml     Fonte unica di verità: classi, id stabili, riferimenti incrociati
src/plantcare/            Pacchetto Python (caricamento e validazione tassonomia)
tests/                    Test automatici
docs/                     Ricerca, dataset, architettura
data/                     Dati locali (non versionati)
models/                   Pesi dei modelli (non versionati)
```

## Avvio rapido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Per l'addestramento deep learning (in arrivo):

```bash
pip install -e ".[train]"
```

## Principi di progetto

- **Multi-task.** Una foto produce più risposte insieme: specie, tipo di agente, malattia, insetto, carenza. Un solo backbone condiviso, più teste di classificazione. Vedi `docs/architettura.md`.
- **Gli id non si rinominano.** Modelli e dataset dipendono dagli id della tassonomia.
- **Riferimenti scientifici.** Ogni classe di malattia e insetto deve avere agente causale o nome scientifico. Le fonti sono in `docs/ricerca.md`.
- **Onestà sull'incertezza.** Il sistema restituisce probabilità e può astenersi. Non presenta mai una carenza o una virosi come certa solo da una foto.
- **Validazione in campo.** I risultati su dataset da laboratorio sovrastimano le prestazioni reali. Serve un set di test raccolto in campo.

## Roadmap

1. Consolidare la tassonomia con un agronomo o fitopatologo (revisione delle classi e dei sintomi).
2. Raccogliere e licenziare i dataset (vedi `docs/dataset.md`), partendo da PlantVillage e IP102 per l'avvio.
3. Addestrare un baseline (backbone pre-addestrato, teste multi-task) e misurarlo con metriche per classe.
4. Costruire un set di test di campo, separato per località e stagione.
5. Aggiungere carenze nutrizionali, per le quali i dati pubblici sono scarsi e va pianificata una raccolta dedicata.
6. Interfaccia (API o app) con soglia di confidenza e indicazione "non determinabile".

## Licenza

Da definire prima della pubblicazione: i dataset scelti hanno licenze diverse e vincolano il riuso dei pesi.
