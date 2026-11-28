/* Calendario dei trattamenti, come lo prepara un tecnico della difesa integrata.
   Dalla coltura, dall'avversità (o dalla carenza), dalla fase di partenza e dalla data prevista di raccolta
   costruisce le date degli interventi rispettando, per ogni prodotto scelto:
   - numero massimo di trattamenti dell'etichetta (n_max) e limiti del Disciplinare della Calabria per sostanza;
   - intervallo tra i trattamenti dell'etichetta (più stretto con pressione alta, più largo con pressione bassa);
   - intervallo di sicurezza (carenza) prima della raccolta e limiti di fase (es. "fino a inizio fioritura");
   - stadi BBCH ammessi dall'etichetta, stimati lungo la stagione tra la fase di partenza e la raccolta;
   - alternanza dei gruppi di resistenza FRAC/IRAC (mai due volte di seguito lo stesso gruppo, salvo i multisito);
   - rame metallo accumulato nell'anno.
   Usa il motore dei Consigli (app/consigli.js) per l'ordine dei prodotti e per le dosi: le dosi sono quelle
   delle etichette registrate, mai stimate. L'etichetta prevale sempre. Verificato da tests/test_calendario.py. */
(function (root) {
  'use strict';
  var C = (typeof module !== 'undefined' && module.exports) ? require('./consigli.js') : root.Consigli;
  var GIORNO = 86400000;

  function data(s) { var d = new Date(s + 'T12:00:00'); return isNaN(d) ? null : d; }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function piu(d, n) { return new Date(d.getTime() + n * GIORNO); }
  function giorni(a, b) { return Math.round((b - a) / GIORNO); }

  // intervallo di etichetta: pressione alta = il più stretto, bassa = il più largo
  var DEFAULT = { malattia: [7, 14], insetto: [10, 21] };
  function passo(range, tipo, pressione) {
    var r = range || DEFAULT[tipo] || DEFAULT.malattia;
    if (pressione === 'alta') return r[0];
    if (pressione === 'bassa') return r[1];
    return Math.round((r[0] + r[1]) / 2);
  }

  // limiti del Disciplinare scritti come testo: "Al massimo 2 interventi l'anno", "Max 3 interventi..."
  function limiteDisciplinare(testi) {
    var n = null;
    (testi || []).forEach(function (t) {
      var m = /(?:max(?:imo)?|al massimo|massimo)\D{0,12}(\d+)\s*(?:interventi|trattamenti|applicazioni)/i.exec(t || '');
      if (m) n = n == null ? +m[1] : Math.min(n, +m[1]);
    });
    return n;
  }

  // gruppi di resistenza che contano per l'alternanza (i multisito FRAC M e BM si possono ripetere)
  function gruppi(cat, p) {
    var basso = cat.regole.gruppi_basso_rischio || [];
    return (p.codici || []).filter(function (c) { return !basso.some(function (b) { return c.indexOf(b) === 0; }); })
      .map(function (c) { return c.replace(/^(IRAC \d+)[A-Z]?$/, '$1'); });
  }

  /* q: {coltura, avversita, fase (id della fase di partenza), situazione, ambito, bio, disciplinare,
         inizio (AAAA-MM-GG), raccolta (AAAA-MM-GG), pressione ('alta'|'media'|'bassa'),
         prodotti (nomi scelti dall'utente; vuoto = scelta automatica), ettari, acqua} */
  function piano(ctx, q) {
    var cat = ctx.cat, out = { interventi: [], avvisi: [], prodotti: [], rame_kg_ha: 0 };
    var d0 = data(q.inizio), dr = data(q.raccolta);
    if (!d0 || !dr || dr <= d0) { out.errore = 'Indica una data di inizio e una data di raccolta successiva.'; return out; }
    var fasi = C.fasi(ctx, q.coltura), f0 = fasi.filter(function (f) { return f.id === q.fase; })[0] || fasi[0];
    var bbch0 = f0 && f0.bbch ? f0.bbch[0] : 0, bbchR = 89, FIOR = 65;
    // fenologia stimata a tratti: partenza -> piena fioritura (BBCH 65) -> raccolta (BBCH 89). La data di
    // fioritura si può indicare; altrimenti si pone a un terzo della stagione (vite, fruttiferi, orticole da frutto)
    var df = data(q.fioritura);
    if (!df || df <= d0 || df >= dr) df = bbch0 < FIOR ? piu(d0, Math.round(giorni(d0, dr) * 0.35)) : null;
    function bbchAl(d) {
      var t;
      if (df && d <= df) { t = (d - d0) / (df - d0); return Math.round(bbch0 + (FIOR - bbch0) * t); }
      var a = df || d0, b0 = df ? FIOR : bbch0;
      t = Math.max(0, Math.min(1, (d - a) / (dr - a)));
      return Math.round(b0 + (bbchR - b0) * t);
    }
    function faseDi(b) {
      var dentro = fasi.filter(function (f) { return f.bbch && b >= f.bbch[0] && b <= f.bbch[1]; });
      if (dentro.length) return dentro[0];
      return fasi.filter(function (f) { return f.bbch; }).sort(function (x, y) {
        return Math.abs((x.bbch[0] + x.bbch[1]) / 2 - b) - Math.abs((y.bbch[0] + y.bbch[1]) / 2 - b);
      })[0] || f0;
    }
    // prodotti ammessi in almeno una fase tra la partenza e la raccolta (ordine della prima fase in cui compaiono)
    var ord = C.ordina(ctx, Object.assign({}, q, { fase: f0 && f0.id, giorni: null }));
    var e = ord.avversita, tipo = e.t, visti = {};
    ord.scelti.forEach(function (s) { visti[s.prodotto] = 1; });
    fasi.slice(fasi.indexOf(f0) + 1).forEach(function (f) {
      if (f.bbch && f.bbch[0] > bbchR) return;
      var o = C.ordina(ctx, Object.assign({}, q, { fase: f.id, giorni: null }));
      o.scelti.forEach(function (s) { if (!visti[s.prodotto]) { visti[s.prodotto] = 1; ord.scelti.push(s); } });
    });
    ord.esclusi = ord.esclusi.filter(function (x) { return !visti[x.prodotto]; });

    var scelti = ord.scelti;
    if (q.prodotti && q.prodotti.length) {
      var voluti = q.prodotti;
      scelti = scelti.filter(function (s) { return voluti.indexOf(s.prodotto) >= 0; });
      voluti.forEach(function (n) {
        if (!ord.scelti.some(function (s) { return s.prodotto === n; })) {
          var ex = ord.esclusi.filter(function (x) { return x.prodotto === n; })[0];
          out.avvisi.push(n + ': non utilizzabile' + (ex ? ' (' + ex.motivo + ')' : ' per questa coltura e avversità'));
        }
      });
    }
    // sostanze ammesse dal Disciplinare per questa avversità (anche di altre aziende): con i limiti scritti
    out.disciplinare = ord.righe.map(function (row) {
      return { coltura: row.coltura, avversita: row.avversita, pagina: row.pagina, criteri: row.criteri || '',
               sostanze: row.sostanze.filter(function (x) { return !x.esca; }).map(function (x) {
                 return { nome: x.s, limiti: (x.n || []).map(function (k) { return row.limiti[k]; }).filter(Boolean) };
               }) };
    });
    if (!scelti.length) {
      out.errore = 'Nessun prodotto Gowan registrato e ammesso per questa coltura e avversità: il calendario si costruisce con le sostanze ammesse dal Disciplinare qui sotto, con dosi, intervalli e carenze dell\'etichetta del prodotto commerciale scelto.';
      return out;
    }

    // per ogni prodotto: ricetta (dosi), limiti, intervallo, carenza, gruppi
    var condivisi = {};
    var info = scelti.map(function (s) {
      var r = C.ricetta(ctx, q, s, { ettari: q.ettari, acqua: q.acqua });
      var lim = [];
      (r.disciplinare || []).forEach(function (x) { lim = lim.concat(x.limiti); });
      var nd = limiteDisciplinare(lim), nm = r.n_max;
      var max = nm != null && nd != null ? Math.min(nm, nd) : (nm != null ? nm : nd);
      var fase = r.phi_fase ? (cat.regole.limiti_fase[cat.usi[s.uso].phi_fase] || {}) : {};
      // limiti del Disciplinare condivisi: la stessa nota (es. "Max 3 interventi con IBE") vale per tutte le
      // sostanze che la richiamano nella riga dell'avversità, quindi il conteggio è comune ai prodotti
      var chiavi = [];
      ord.righe.forEach(function (row) {
        var ri = cat.righe.indexOf(row);
        (cat.prodotti[s.p].sostanze || []).forEach(function (st) {
          var rr = ctx.rx[st.id];
          row.sostanze.forEach(function (x) {
            if (!rr || !rr.test(String(x.s).toLowerCase())) return;
            (x.n || []).forEach(function (k) {
              var lim = limiteDisciplinare([row.limiti[k]]);
              if (lim != null && chiavi.indexOf(ri + '|' + k) < 0) { chiavi.push(ri + '|' + k); condivisi[ri + '|' + k] = { max: lim, usati: 0, testo: row.limiti[k] }; }
            });
          });
        });
      });
      return { s: s, r: r, p: cat.prodotti[s.p], max: max, chiavi: chiavi, fonte_max: nm != null && (nd == null || nm <= nd) ? 'etichetta' : (nd != null ? 'Disciplinare' : null),
               intervallo: r.intervallo, phi: r.phi, fino_bbch: fase.fino_bbch != null ? fase.fino_bbch : null,
               bbch: r.bbch, g: gruppi(cat, cat.prodotti[s.p]), usati: 0, ultimo: null };
    });

    // ordine del tecnico nella fase di ogni data (programmi per fase, azione adatta alla situazione)
    var perFase = {};
    function punteggi(f) {
      if (!perFase[f.id]) {
        var o = C.ordina(ctx, Object.assign({}, q, { fase: f.id, giorni: null })), m = {};
        o.scelti.forEach(function (s, i) { m[s.prodotto] = { punteggio: s.punteggio, ordine: i }; });
        perFase[f.id] = m;
      }
      return perFase[f.id];
    }
    var rameMax = q.rame_max != null ? q.rame_max : 4, rame = 0;

    var d = d0, prev = null, n = 0, sicurezza = 0;
    while (d <= dr && sicurezza++ < 200) {
      var b = bbchAl(d), fase = faseDi(b), pf = punteggi(fase);
      var base = info.filter(function (x) {
        if (x.r.rame_kg_ha && rame + x.r.rame_kg_ha > rameMax + 1e-9) return false;
        if (x.max != null && x.usati >= x.max) return false;
        if (x.chiavi.some(function (k) { return condivisi[k].usati >= condivisi[k].max; })) return false;
        if (x.phi != null && giorni(d, dr) < x.phi) return false;
        if (x.fino_bbch != null && b > x.fino_bbch) return false;
        if (x.bbch && x.bbch.length && !x.bbch.some(function (w) { return b >= w[0] - 2 && b <= w[1] + 2; })) return false;
        if (x.ultimo && x.intervallo && giorni(x.ultimo, d) < x.intervallo[0]) return false;
        return true;
      });
      var ok = base.filter(function (x) { return !(prev && x.g.length && x.g.some(function (g) { return prev.g.indexOf(g) >= 0; })); });
      var senzaAlternanza = false;
      if (!ok.length && base.length) { ok = base; senzaAlternanza = true; }
      if (!ok.length) {
        // nessun prodotto oggi: si riprova dopo qualche giorno (può tornare utilizzabile per intervallo o alternanza)
        var dopo = piu(d, 3);
        if (info.every(function (x) { return (x.max != null && x.usati >= x.max) || (x.phi != null && giorni(dopo, dr) < x.phi); })) break;
        d = dopo; continue;
      }
      // il primo nell'ordine del tecnico per la fase della data; a parità, quello usato meno volte
      // (con pochi prodotti ammessi in quella fase restano utilizzabili gli altri, in coda)
      ok.sort(function (a, z) {
        var pa = pf[a.p.nome], pz = pf[z.p.nome];
        if (!!pa !== !!pz) return pa ? -1 : 1;
        if (pa && pz && pa.punteggio !== pz.punteggio) return pz.punteggio - pa.punteggio;
        if (a.usati !== z.usati) return a.usati - z.usati;
        return (pa ? pa.ordine : 99) - (pz ? pz.ordine : 99);
      });
      var x = ok[0];
      x.usati++; x.ultimo = d; n++;
      x.chiavi.forEach(function (k) { condivisi[k].usati++; });
      if (x.r.rame_kg_ha) rame += x.r.rame_kg_ha;
      var step = passo(x.intervallo, tipo, q.pressione);
      out.interventi.push({
        n: n, data: iso(d), dal_precedente: prev ? giorni(prev.d, d) : null, bbch_stimato: b, fase: fase.nome,
        prodotto: x.p.nome, sostanze: (x.p.sostanze || []).map(function (s) { return s.nome; }), gruppi: x.p.codici || [],
        dose_ha: x.r.dose.per_ha, dose_hl: x.r.dose.per_hl, dose_etichetta_ha: x.r.dose.etichetta_ha, dose_etichetta_hl: x.r.dose.etichetta_hl,
        totale: x.r.dose.totale || null, phi: x.phi, ultimo_utile: x.phi != null ? iso(piu(dr, -x.phi)) : null,
        uso_n: x.usati, uso_max: x.max, fonte_max: x.fonte_max, prossimo_tra: step,
        nota: x.r.nota || null, azione: x.p.azione || [], rame_kg_ha: x.r.rame_kg_ha || null,
        alternanza: senzaAlternanza ? 'Stesso gruppo di resistenza del trattamento precedente: tra i prodotti Gowan non c\'è un\'alternativa in questa data. Alterna con un prodotto di un altro gruppo ammesso dal Disciplinare (elenco sotto).' : null,
        limiti_comuni: x.chiavi.map(function (k) { return condivisi[k].testo + ' (' + condivisi[k].usati + ' su ' + condivisi[k].max + ')'; })
      });
      if (x.r.rame_kg_ha) out.rame_kg_ha += x.r.rame_kg_ha;
      prev = { g: x.g, d: d };
      d = piu(d, step);
    }
    out.prodotti = info.map(function (x) {
      return { prodotto: x.p.nome, usati: x.usati, max: x.max, fonte_max: x.fonte_max, intervallo: x.intervallo, phi: x.phi,
               gruppi: x.p.codici || [], bbch: x.bbch, fino_bbch: x.fino_bbch };
    });
    out.rame_kg_ha = Math.round(out.rame_kg_ha * 1000) / 1000;
    out.rame_max = rameMax;
    if (info.some(function (x) { return x.r.rame_kg_ha; }))
      out.avvisi.push('Rame metallo nel piano: ' + String(out.rame_kg_ha).replace('.', ',') + ' kg/ha su un massimo di ' + String(rameMax).replace('.', ',') +
                      ' kg/ha l\'anno (Regolamento UE 2018/1981: 28 kg/ha in 7 anni). Se in questa stagione hai già usato altro rame, riduci il massimo.');
    out.fioritura_stimata = df ? iso(df) : null;
    if (!out.interventi.length) out.errore = 'Con questi limiti (carenza, fase, numero di trattamenti) non resta nessuna data utile prima della raccolta.';
    if (tipo === 'insetto') out.avvisi.push('Per gli insetti le date sono un massimo possibile: si tratta solo al superamento della soglia d\'intervento del Disciplinare (catture nelle trappole, controlli in campo), non a calendario fisso.');
    else out.avvisi.push('Le date sono indicative: anticipa prima delle piogge infettanti, ritarda con tempo secco; dopo piogge dilavanti (oltre 20-30 mm) i prodotti di copertura vanno rinnovati.');
    out.avvisi.push('La fase fenologica (BBCH) è stimata tra la fase di partenza e la raccolta: controlla in campo prima di ogni trattamento che il prodotto sia ammesso in quello stadio.');
    out.situazione = ord.situazione; out.avversita = e.nome; out.tipo = tipo; out.righe = ord.righe;
    return out;
  }

  // ------------------------------------------------------------------ carenze nutrizionali
  /* q: {carenza (classe del lettore), coltura, inizio, raccolta, modo ('curativo'|'preventivo')}
     schemi: configs/difesa/carenze_calendario.yaml (app/data/carenze.json) */
  function pianoCarenza(schemi, q) {
    var s = schemi[q.carenza], out = { interventi: [], avvisi: [] };
    if (!s) { out.errore = 'Nessuno schema per questa carenza.'; return out; }
    var d0 = data(q.inizio), dr = data(q.raccolta);
    if (!d0) { out.errore = 'Indica la data di inizio.'; return out; }
    var m = s[q.modo === 'preventivo' ? 'preventivo' : 'curativo'] || s.curativo;
    if (!m) { out.errore = s.nota || 'Nessun intervento previsto.'; out.avvisi = s.avvisi || []; return out; }
    var d = d0;
    for (var i = 0; i < m.n; i++) {
      if (dr && d > dr) break;
      out.interventi.push({ n: i + 1, data: iso(d), dal_precedente: i ? m.intervallo : null, prodotto: s.prodotto || s.forma,
                            dose: s.dose || null, modo: s.modo || null });
      d = piu(d, m.intervallo);
    }
    out.forma = s.forma; out.fonte = s.fonte || null; out.avvisi = (s.avvisi || []).slice();
    if (!s.dose) out.avvisi.push('Dose: quella dell\'etichetta del concime scelto e del piano di concimazione basato sulle analisi del terreno e, dove serve, fogliari (Disciplinare di produzione integrata).');
    return out;
  }

  // ------------------------------------------------------------------ esportazione nel calendario del telefono
  function ics(titolo, interventi) {
    var righe = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//PlantCare//Calendario trattamenti//IT', 'CALSCALE:GREGORIAN'];
    interventi.forEach(function (x) {
      var g = x.data.replace(/-/g, ''), fine = iso(piu(data(x.data), 1)).replace(/-/g, '');
      var desc = [x.prodotto, x.dose_ha ? 'dose ' + C.fmt(x.dose_ha) + '/ha' : '', x.dose_hl ? C.fmt(x.dose_hl) + '/hl' : '', x.dose || '',
                  x.phi != null ? 'carenza ' + x.phi + ' giorni' : ''].filter(Boolean).join(' - ');
      righe.push('BEGIN:VEVENT', 'UID:plantcare-' + g + '-' + x.n + '-' + Math.random().toString(36).slice(2, 8), 'DTSTAMP:' + g + 'T080000Z',
                 'DTSTART;VALUE=DATE:' + g, 'DTEND;VALUE=DATE:' + fine,
                 'SUMMARY:' + (titolo + ' - trattamento ' + x.n).replace(/[,;]/g, ' '),
                 'DESCRIPTION:' + desc.replace(/[,;]/g, ' ').replace(/\n/g, ' '), 'END:VEVENT');
    });
    righe.push('END:VCALENDAR');
    return righe.join('\r\n');
  }

  var api = { piano: piano, pianoCarenza: pianoCarenza, ics: ics, limiteDisciplinare: limiteDisciplinare, passo: passo };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Calendario = api;
})(this);
