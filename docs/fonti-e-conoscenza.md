# Fonti, verifica e base di conoscenza

## Come funziona il referto

La rete neurale riconosce **cosa c'è nella foto**: specie, malattia, insetto. Causa, vettori e misure di gestione **non vengono prodotti dalla rete**: sono letti da una base di conoscenza verificata (`configs/knowledge_base.yaml`), collegata alla malattia riconosciuta tramite il suo id. Questo serve per due motivi:

- una rete addestrata su immagini non può garantire che una misura di gestione sia corretta;
- ogni indicazione deve poter essere ricondotta alla fonte che la sostiene.

Per ogni malattia il referto riporta: pianta, malattia, agente causale, cosa la trasmette (vettore), misure di gestione e stato delle fonti.

## Livelli di verifica

| Stato | Significato |
|---|---|
| `testo_letto` | Il documento è stato scaricato, il testo estratto e il passaggio citato controllato |
| `riassunto_verificato` | Metadati e riassunto confermati; il testo completo non è stato letto |
| `solo_metadati` | Esiste, ma il contenuto non è stato letto: non usare per indicazioni tecniche |

Le fonti sono in `configs/sources.yaml`. L'API le espone su `/api/sources`.

## Fonti lette

**Calabria**
- Regione Calabria, *Disciplinari di produzione integrata 2023 - Difesa e controllo infestanti* (Allegato A). Contiene misure agronomiche e soglie per olivo (pp. 91-93), vite (pp. 118-125), agrumi, e le densità delle trappole di monitoraggio (tab. 3). Non cita la *Xylella*.
- ARSAC, *Bilancio fitosanitario Agrumi Calabria 2024-2025* (4 dicembre 2025): avversità degli agrumi in Calabria, strategie e soglie.
- ARSAC, *Bollettino agrometeorologico n. 20, area 1* (11 agosto 2020): soglie per la mosca dell'olivo e avversità dell'olivo e della vite nel Cosentino. È un documento del 2020: le soglie vanno confermate con il bollettino corrente.
- Gullo G., Dattola A., Zappia R. (2020), *Fruits* 75(4):170-179, DOI 10.17660/th2020/75.4.4, Università Mediterranea di Reggio Calabria: il bergamotto è innestato su arancio amaro, molto suscettibile al CTV, presente in Calabria.

**Internazionali**
- EPPO Global Database, datasheet *Xylella fastidiosa* (XYLEFA): unico vettore accertato in natura nella regione EPPO *Philaenus spumarius*; il rame non cura né previene la trasmissione; categoria A2 EPPO e Allegato II B del regolamento UE 2019/2072.
- EPPO Global Database, datasheet *Plum pox virus* (PPV000), aggiornato al 2024: vettori afidi non persistenti; categoria A2 EPPO e RNQP UE Allegato IV.
- EFSA (2019), *Update of the Scientific Opinion on the risks to plant health posed by Xylella fastidiosa in the EU territory*, EFSA Journal 17(5), DOI 10.2903/j.efsa.2019.5665: non esiste un modo noto per eliminare il batterio dalla pianta infetta in pieno campo; l'eradicazione locale in oliveto è possibile con campionamento intenso e interventi rapidi. **Letta solo nel riassunto**: il DOI non si risolve al sito dell'editore dall'ambiente di verifica.

## Fonti non ancora verificate

- Pubblicazioni dell'Università Mediterranea di Reggio Calabria su *Xylella* e sulle malattie del bergamotto: non trovate. Il preprint del 2024 segnalato dalla ricerca non ha un titolo verificato, quindi non è citato.
- Studio su *Xylella* e vettori sulla costa ionica calabrese (Lombardo e Rizzo, repository Università Cattolica): trovato come metadati, testo non letto.
- Norme di lotta obbligatoria alla flavescenza dorata: le fonti trovate riguardano Piemonte e Valle d'Aosta. Per la Calabria non è documentato nulla in questa base di conoscenza.
- Regolamento UE 2019/2072 e successive modifiche: citato dai documenti, non letto integralmente.

## Lacune

- Le malattie senza voce nella base di conoscenza (la maggior parte delle colture) mostrano esplicitamente "da completare con il tecnico": il sistema non inventa misure.
- Per la Xylella il disciplinare calabrese 2023 non contiene misure: le indicazioni di quarantena vanno cercate nelle disposizioni vigenti.
- I bollettini ARSAC più recenti dell'olivo e della vite non sono stati trovati: quelli letti sono del 2020.

## Cosa non fa il sistema

- Non indica sostanze attive, dosi, né tempi di trattamento. Quelli sono nel disciplinare vigente e nella decisione del tecnico.
- Non stabilisce se un'azienda è obbligata a un intervento di lotta: lo stabilisce la norma regionale o nazionale.
