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

- Sostanze attive, limiti d'uso e criteri di intervento vengono dal Disciplinare di produzione integrata della Regione Calabria (2026, confrontato con il 2023 per le sostanze uscite dall'elenco); dosi, intervalli di sicurezza ed epoche dei prodotti Gowan dalle pagine prodotto del produttore. Niente è scritto a mano; l'etichetta autorizzata prevale e la decisione resta del tecnico.
- Non stabilisce se un'azienda è obbligata a un intervento di lotta: lo stabilisce la norma regionale o nazionale.

## Copertura del disciplinare 2023 (letta nel testo)

Il disciplinare calabrese copre le colture con sezioni per coltura. Per ciascuna colture letta sono state estratte le misure agronomiche, le soglie e le regole di segnalazione. Le colonne dei prodotti non sono state riportate.

| Coltura | Stato |
|---|---|
| Olivo | letta: occhio di pavone, lebbra, rogna, verticilliosi, carie, tignola (soglie), fitofagi |
| Vite (da tavola e da vino) | letta in parte: esca, peronospora, monitoraggio della flavescenza |
| Agrumi | letta: tristezza (segnalazione), monitoraggio, cocciniglie, afidi, ragnetti (ARSAC 2025) |
| Actinidia (kiwi) | letta: botrite, marciume del colletto, batteriosi, cocciniglia, eulia, metcalfa |
| Ciliegio | letta: monilia, corineo, mosca della ciliegia, capnodis, drosofila, afidi, cocciniglie |
| Melo | letta in parte: ticchiolatura, mal bianco, carpocapsa, colpo di fuoco, ragno rosso, afidi |
| Pomodoro (pieno campo) | letta in parte: peronospora, alternariosi, virosi, muffa grigia |
| Peperone | letta in parte: batteriosi, virosi, oidio, afidi, piralide, ragnetto |
| Melanzana | letta in parte: muffa grigia, verticilliosi, peronospora, virosi, afidi, tripidi, tarsonemide, ragnetto |
| Patata | letta: peronospora, rizottoniosi, virosi, dorifora, tignola, afidi, nematodi |
| Lattuga | letta: peronospora, Rhizoctonia, batteriosi, virosi, afidi, liriomyza |
| Carciofo | letta: peronospora, botrite, oidio, virosi, afidi |
| Cavolo a infiorescenza (broccolo) | letta: peronospora, batteriosi, alternariosi, tignola, cavolaia, afidi, altica, mosca, tripidi |
| Cipolla | letta: peronospora, botrite, fusariosi, batteriosi, mosche, tripidi, nottue, nematodi |

| Pero | letta: colpo di fuoco, cocciniglia, psilla, carpocapsa, cidia, tentredine, ricamatori, rodilegni, ragnetto rosso, eriofidi |
| Pesco | letta: bolla, corineo, mal bianco, monilia, cancri, cancro batterico, sharka, afidi, tripidi, cocciniglie, cidia, anarsia, ragnetto rosso, capnode |
| Nocciolo | letta: mal dello stacco, necrosi batterica, cancro batterico e moria, eriofide delle gemme, acari, balanino, cimici |
| Fragola | letta: oidio, muffa grigia, vaiolatura, marciume bruno, antracnosi, batteriosi, afidi, oziorrinco, tripidi, ragnetti, drosofila, aleurodidi |
| Frumento | letta: carbone, carie, fusariosi, oidio, septoria, ruggini, afidi |
| Mais | letta: carbone, marciume del fusto, batteriosi, virosi, diabrotica, elateridi, piralide, nottue, afidi |
| Zucchino e cetriolo | **senza sezione propria** nel disciplinare: si usano le indicazioni della sezione melone (cucurbitacee: oidio, peronospora, cancro gommoso, batteriosi, afidi, aleurodidi, tripidi, minatori) e lo si dichiara in ogni voce |

**Non coperti dal disciplinare**: aglio, cipolla rossa di Tropea come varietà (si usa la sezione cipolla), colture tropicali (avocado, banano, cherimoya, fico d'India), brusone settentrionale del mais.

## Acari fitofagi

Sono nella tassonomia come fitofagi, con la nota che non sono insetti: ragnetto rosso (*Tetranychus urticae*), ragno rosso degli agrumi (*Panonychus citri*), ragno rosso del melo (*Panonychus ulmi*), acaro tarsonemide (*Polyphagotarsonemus latus*). Aggiunti dal disciplinare: ragnetto giallo (*Eotetranychus carpini*) di vite, fragola e nocciolo; acariosi della vite (*Calepitrimerus vitis*); eriofide delle gemme del nocciolo; eriofidi del pero; acaro delle meraviglie ed eriofide rugginoso degli agrumi; eriofide del pomodoro. Ognuno ha soglie o misure del disciplinare.

**Acari dell'olivo**: il disciplinare calabrese 2023 non li tratta. Le specie (*Aceria oleae*, *Tegolophus hassani*, *Oxycenus maxwelli*) sono inserite sulla base della rassegna universitaria di Nuzzaci e Parenzan (Università di Bari, 1983), letta nel riassunto. La fonte serve al riconoscimento delle specie, non dà misure di difesa.
