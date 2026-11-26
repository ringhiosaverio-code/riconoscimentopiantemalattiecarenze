/* Consigli di difesa con i prodotti Gowan: ordine di preferenza e ricetta, come un tecnico della difesa integrata.
   Regole scritte (configs/difesa/consigli_regole.yaml) applicate ai dati del catalogo (app/data/catalogo.json):
   usi registrati, etichette, programmi Gowan per fase, Disciplinare della Calabria, banca dati UE.
   Non è una rete neurale e non sostituisce l'etichetta, che prevale sempre. Verificato da tests/test_consigli.py. */
(function (root) {
  'use strict';

  function lower(s) { return String(s || '').toLowerCase(); }
  function overlap(a, b) { return a && b && a[0] <= b[1] && b[0] <= a[1]; }
  function round(x, d) { var f = Math.pow(10, d); return Math.round(x * f) / f; }
  function rx(s) { try { return new RegExp(s, 'i'); } catch (e) { return null; } }

  // ------------------------------------------------------------------ dati
  function prepara(cat) {
    var ctx = { cat: cat, colture: {}, prodotti: {}, rx: {} };
    cat.colture.forEach(function (c, i) { ctx.colture[c.nome] = { info: c, i: i }; });
    cat.prodotti.forEach(function (p, i) { ctx.prodotti[p.nome] = i; });
    Object.keys(cat.sostanze_disciplinare || {}).forEach(function (k) { ctx.rx[k] = rx(cat.sostanze_disciplinare[k]); });
    return ctx;
  }
  function coltura(ctx, nome) { var c = ctx.colture[nome]; if (!c) throw new Error('Coltura sconosciuta: ' + nome); return c.info; }
  function avversita(ctx, nome) { return ctx.cat.avversita[nome] || []; }
  function voce(ctx, nome, id) {
    var e = avversita(ctx, nome).filter(function (x) { return x.id === id; })[0];
    if (!e) throw new Error('Avversità sconosciuta: ' + id);
    return e;
  }

  // fasi della coltura: quelle del programma Gowan (vite, pomodoro, lattuga, fragola) o quelle generiche del gruppo
  function fasi(ctx, nome) {
    var c = coltura(ctx, nome), pr = c.programma && ctx.cat.programmi[c.programma];
    if (pr && pr.fasi) return pr.fasi.map(function (f, i) { return { id: 'p' + (i + 1), nome: f.nome, bbch: f.bbch, n: i + 1 }; });
    var g = ctx.cat.regole.fasi_generiche[c.gruppo] || ctx.cat.regole.fasi_generiche.orticole;
    return g.map(function (f) { return { id: f.id, nome: f.nome, bbch: f.bbch }; });
  }
  function situazioni(ctx, tipo) { return ctx.cat.regole.situazioni[tipo === 'insetto' ? 'insetto' : 'malattia']; }

  // ------------------------------------------------------------------ criteri
  function gruppiResistenza(p, basso) {
    return (p.codici || []).filter(function (c) {
      return !basso.some(function (b) { return c.indexOf(b) === 0; });
    }).map(function (c) { return c.replace(/^(IRAC \d+)[A-Z]?$/, '$1'); });  // IRAC 21A e 21: stesso gruppo
  }
  function inFioritura(ctx, f) { return f && f.bbch && overlap(f.bbch, ctx.cat.regole.fioritura_bbch); }

  // posizione nel programma Gowan della coltura: +peso se nella fase scelta
  function programma(ctx, c, e, p, f) {
    var pr = c.programma && ctx.cat.programmi[c.programma];
    if (!pr) return null;
    var keys = ctx.cat.avversita_programmi || {}, nome = lower(e.nome), out = null;
    (pr.voci || []).forEach(function (v) {
      var r = rx(keys[v.avversita] || v.avversita);
      if (v.prodotto !== p.nome || !r || !r.test(nome)) return;
      var dentro = f && f.n != null && f.n >= v.da && f.n <= v.a;
      if (!out || (dentro && !out.dentro)) out = { dentro: dentro, da: v.da, a: v.a, nota: v.nota || null };
    });
    (pr.epoche || []).forEach(function (v) {
      var r = rx(v.avversita);
      if (v.prodotti.indexOf(p.nome) < 0 || !r || !r.test(nome)) return;
      var ok = (ctx.cat.regole.epoche_fasi[v.tipo_epoca] || []).indexOf(f && f.id) >= 0;
      if (!out || (ok && !out.dentro)) out = { dentro: ok, epoca: v.epoca, nota: null };
    });
    if (out) out.titolo = pr.titolo, out.url = pr.url;
    return out;
  }

  // uso registrato più adatto del prodotto per questa avversità: ambito e stadi BBCH della fase
  function sceltaUso(ctx, e, pi, q, f) {
    var usi = e.u.map(function (i) { return { i: i, u: ctx.cat.usi[i] }; }).filter(function (x) { return x.u.p === pi; });
    var amb = q.ambito ? usi.filter(function (x) { return x.u.s === q.ambito; }) : usi;
    if (!amb.length) return { esclusione: q.ambito === 'campo' ? 'registrato per questa avversità solo in serra' : 'registrato per questa avversità solo in pieno campo' };
    var buoni = amb.filter(function (x) { return !x.u.bbch || !f || !f.bbch || x.u.bbch.some(function (w) { return overlap(w, f.bbch); }); });
    if (!buoni.length) {
      var w = amb[0].u.bbch.map(function (x) { return x[0] + '-' + (x[1] === 99 ? 'raccolta' : x[1]); }).join(' e ');
      return { esclusione: 'la nota dell\'etichetta lo ammette solo negli stadi BBCH ' + w + ', fuori dalla fase scelta', uso: amb[0].i };
    }
    buoni.sort(function (a, b) { return (b.u.hl ? 1 : 0) + (b.u.ha ? 1 : 0) - (a.u.hl ? 1 : 0) - (a.u.ha ? 1 : 0); });
    return { uso: buoni[0].i };
  }

  // sostanze del prodotto che il Disciplinare non ammette per l'avversità (quelle ammesse solo in esche o
  // dispositivi attract and kill non valgono per un trattamento alla chioma)
  function ammessoDisciplinare(ctx, p, righe) {
    var nonAmm = [];
    (p.sostanze || []).forEach(function (s) {
      var r = ctx.rx[s.id], esca = false;
      var ok = r && righe.some(function (row) {
        return row.sostanze.some(function (x) {
          if (!r.test(lower(x.s))) return false;
          if (x.esca) { esca = true; return false; }
          return true;
        });
      });
      if (!ok) nonAmm.push(s.nome + (esca ? ' (solo in esche o dispositivi attract and kill)' : ''));
    });
    return nonAmm;
  }

  // ------------------------------------------------------------------ ordine
  /* q: {coltura, avversita, fase, situazione, bio, disciplinare, ambito ('campo'|'serra'|null), giorni (alla raccolta),
         ultimo (nome del prodotto usato nell'ultimo trattamento), obiettivo (nutrizionali: stress, accrescimento,
         cracking, ripresa, allegagione, carenza_ferro)} */
  function ordina(ctx, q) {
    var cat = ctx.cat, R = cat.regole, P = R.punteggi;
    var c = coltura(ctx, q.coltura), e = voce(ctx, q.coltura, q.avversita);
    var f = fasi(ctx, q.coltura).filter(function (x) { return x.id === q.fase; })[0] || null;
    var sit = situazioni(ctx, e.t).filter(function (s) { return s.id === q.situazione; })[0] || situazioni(ctx, e.t)[0];
    var righe = e.r.map(function (i) { return cat.righe[i]; });
    // pomodoro e altre colture con due schede (pieno campo e coltura protetta): quella dell'ambito scelto
    var perAmbito = righe.filter(function (r) { return q.ambito === 'serra' ? /PROTETTA/.test(r.coltura) : !/PROTETTA/.test(r.coltura); });
    if (q.ambito && perAmbito.length) righe = perAmbito;
    var ultimo = q.ultimo != null && ctx.prodotti[q.ultimo] != null ? cat.prodotti[ctx.prodotti[q.ultimo]] : null;
    var gUltimo = ultimo ? gruppiResistenza(ultimo, R.gruppi_basso_rischio) : [];
    var visti = {}, scelti = [], esclusi = [];
    e.u.forEach(function (i) { visti[cat.usi[i].p] = 1; });
    Object.keys(visti).map(Number).forEach(function (pi) {
      var p = cat.prodotti[pi], motivi = [], avvisi = [], punti = 0;
      function add(k, extra) { var r = P[k]; punti += r.peso; motivi.push({ testo: r.testo + (extra ? ': ' + extra : ''), peso: r.peso, fonti: r.fonti }); }
      function escludi(m) { esclusi.push({ prodotto: p.nome, motivo: m }); }
      var su = sceltaUso(ctx, e, pi, q, f);
      if (su.esclusione) return escludi(su.esclusione);
      var u = cat.usi[su.uso];
      // limiti di fase scritti al posto dell'intervallo di sicurezza
      var lf = u.phi_fase && R.limiti_fase[u.phi_fase];
      if (lf && f && f.bbch) {
        if (lf.fino_bbch != null && f.bbch[0] > lf.fino_bbch) return escludi('etichetta: ' + lf.testo);
        if (lf.solo_riposo && !(f.bbch[1] <= 1 || f.bbch[0] >= 91)) return escludi('etichetta: ' + lf.testo);
      }
      if (q.giorni != null && u.phi != null && u.phi > q.giorni)
        return escludi('intervallo di sicurezza di ' + u.phi + ' giorni: mancano ' + q.giorni + ' giorni alla raccolta');
      if (q.bio && !p.bio) return escludi('non segnato da Gowan come consentito in agricoltura biologica');
      var nonUe = Object.keys(p.ue || {}).filter(function (k) { return p.ue[k].stato === 'Not approved'; });
      if (nonUe.length) return escludi('sostanza attiva non più approvata nell\'UE: ' + nonUe.map(function (k) { return p.ue[k].nome + (p.ue[k].scadenza ? ' (scadenza ' + p.ue[k].scadenza + ')' : ''); }).join(', '));
      if (inFioritura(ctx, f) && p.api_fioritura === 'escludi') return escludi('in fioritura: «' + p.api + '» (etichetta)');
      if (righe.length) {
        var na = ammessoDisciplinare(ctx, p, righe);
        if (na.length) {
          if (q.disciplinare) return escludi('il Disciplinare della Calabria non ammette ' + na.join(', ') + ' per questa avversità');
          add('non_nel_disciplinare', na.join(', '));
        }
      }
      // punteggio
      var pg = programma(ctx, c, e, p, f);
      if (pg) {
        if (pg.dentro) add('programma_fase', pg.nota || pg.epoca || '');
        else add('programma_altra_fase', pg.da != null ? 'fasi ' + pg.da + '-' + pg.a : (pg.epoca || ''));
      }
      var az = (p.azione || []).slice();
      if (p.momento === 'prime_larve') az.push('larvicida');
      if (p.momento === 'uova') az.push('ovicida');
      var ad = az.filter(function (a) { return sit.azioni_adatte.indexOf(a) >= 0; });
      var pa = az.filter(function (a) { return sit.azioni_parziali.indexOf(a) >= 0; });
      if (ad.length) add('situazione_adatta', 'azione ' + ad.join(', '));
      else if (pa.length) add('situazione_parziale', 'azione ' + pa.join(', '));
      else if (u.ai_sintomi && sit.id !== 'prevenzione') add('situazione_parziale', 'l\'etichetta indica di intervenire ai primi sintomi o alla prima comparsa');
      if (p.bio) add('basso_impatto');
      if (e.t === 'insetto' && az.indexOf('selettivo') >= 0) add('selettivo');
      if (gUltimo.length) {
        var comuni = gruppiResistenza(p, R.gruppi_basso_rischio).filter(function (g) { return gUltimo.indexOf(g) >= 0; });
        if (comuni.length) add('stesso_gruppo', comuni.join(', '));
      }
      if (Object.keys(p.ue || {}).some(function (k) { return p.ue[k].candidata_sostituzione; })) add('candidata_sostituzione');
      if (inFioritura(ctx, f) && p.api_fioritura === 'avviso') { add('api_avviso'); avvisi.push('Etichetta: «' + p.api + '»'); }
      if (inFioritura(ctx, f) && p.api_fioritura === 'sera') avvisi.push('In fioritura: «' + p.api + '»; ' + (p.api_sera ? '«per ' + p.api_sera + '»' : ''));
      if (u.collaterale) avvisi.push('Per alcune avversità l\'etichetta indica solo un\'azione collaterale: controlla la nota d\'uso.');
      scelti.push({ prodotto: p.nome, p: pi, uso: su.uso, punteggio: round(punti, 2), motivi: motivi, avvisi: avvisi,
                    phi: u.phi, phi_fase: u.phi_fase || null, gruppi: p.codici || [], programma: pg });
    });
    scelti.sort(function (a, b) {
      return b.punteggio - a.punteggio || (a.phi == null ? 999 : a.phi) - (b.phi == null ? 999 : b.phi) || a.prodotto.localeCompare(b.prodotto);
    });
    esclusi.sort(function (a, b) { return a.prodotto.localeCompare(b.prodotto); });
    return { coltura: c, avversita: e, fase: f, situazione: sit, righe: righe, scelti: scelti, esclusi: esclusi,
             alternanza: alternanza(ctx, scelti) };
  }

  // sequenza di prodotti con gruppi di resistenza diversi (i multisito e i biologici si possono ripetere)
  function alternanza(ctx, scelti) {
    var out = [], usati = {};
    scelti.forEach(function (s) {
      if (out.length >= 3) return;
      var g = gruppiResistenza(ctx.cat.prodotti[s.p], ctx.cat.regole.gruppi_basso_rischio);
      if (g.some(function (x) { return usati[x]; })) return;
      g.forEach(function (x) { usati[x] = 1; });
      out.push(s.prodotto);
    });
    return out;
  }

  // ------------------------------------------------------------------ ricetta
  var BASE = { g: ['g', 1], kg: ['g', 1000], ml: ['ml', 1], l: ['ml', 1000] };
  function quantita(v, base) {  // g o ml -> testo leggibile
    if (v == null || !isFinite(v)) return null;
    if (v >= 1000) return { valore: round(v / 1000, 2), unita: base === 'g' ? 'kg' : 'l' };
    return { valore: round(v, v < 10 ? 1 : 0), unita: base };
  }
  function scegli(range, modo) {
    if (!range) return null;
    if (range[3]) return range[1];  // solo dose massima scritta
    return modo === 'max' ? range[1] : modo === 'media' ? round((range[0] + range[1]) / 2, 3) : range[0];
  }

  /* opz: {ettari, acqua (l/ha), botte (l)} */
  function ricetta(ctx, q, s, opz) {
    var cat = ctx.cat, p = cat.prodotti[s.p], u = cat.usi[s.uso], res = ordina.cache || null;
    var e = voce(ctx, q.coltura, q.avversita);
    var sit = situazioni(ctx, e.t).filter(function (x) { return x.id === q.situazione; })[0] || situazioni(ctx, e.t)[0];
    var acqua = opz && opz.acqua > 0 ? opz.acqua : null, ha = opz && opz.ettari > 0 ? opz.ettari : null, botte = opz && opz.botte > 0 ? opz.botte : null;
    var r = { prodotto: p, uso: u, uso_i: s.uso, registrato: cat.testi[u.a], nota: u.n != null ? cat.note[u.n] : null, avvisi: [], errori: [] };
    var hl = u.hl, haR = u.ha, perHl = null, perHa = null, base = null;
    if (haR && acqua) {
      // la dose a ettaro è quella che conta: con volumi d'acqua diversi da quelli normali le etichette chiedono di
      // adeguare la concentrazione e mantenere la dose per ettaro
      var bh = BASE[haR[2].split('/')[0]]; base = bh[0];
      perHa = scegli(haR, sit.dose) * bh[1];
      perHl = perHa / acqua * 100;
      if (hl) {
        var bl = BASE[hl[2].split('/')[0]], lo = hl[0] * bl[1], hi = hl[1] * bl[1];
        if (perHl < lo * 0.999 || perHl > hi * 1.001)
          r.avvisi.push('Con ' + acqua + ' l/ha di acqua la concentrazione è ' + fmt(quantita(perHl, base)) + ' per ettolitro, diversa da quella indicata per i volumi normali (' +
                        rng(hl) + '): come chiede l\'etichetta resta fissa la dose a ettaro.');
      }
    } else if (hl) {
      var bu = BASE[hl[2].split('/')[0]]; base = bu[0];
      perHl = scegli(hl, sit.dose) * bu[1];  // g o ml per ettolitro
      if (acqua) perHa = perHl * acqua / 100;
    } else if (haR) {
      var b2 = BASE[haR[2].split('/')[0]]; base = b2[0];
      perHa = scegli(haR, sit.dose) * b2[1];
    }
    r.dose = { modo: sit.dose, base: base, per_hl: quantita(perHl, base), per_ha: quantita(perHa, base),
               etichetta_hl: hl ? rng(hl) : null, etichetta_ha: haR ? rng(haR) : null };
    if (!acqua) r.avvisi.push('Indica i litri d\'acqua per ettaro: servono per passare dalla dose a ettaro a quella per ettolitro e alla botte.');
    if (ha && perHa != null) r.dose.totale = quantita(perHa * ha, base);
    if (botte && perHl != null) r.dose.botte = quantita(perHl * botte / 100, base);
    if (botte && acqua) r.dose.botte_ettari = round(botte / acqua, 3);
    if (u.acqua) r.acqua_etichetta = u.acqua;
    r.n_max = u.n_max || null; r.n_tipico = u.n_tipico || null; r.intervallo = u.intervallo || null; r.bbch = u.bbch || null;
    r.phi = u.phi; r.phi_fase = u.phi_fase ? (cat.regole.limiti_fase[u.phi_fase] || {}).testo || u.phi_fase : null;
    // limiti del Disciplinare per le sostanze del prodotto
    r.disciplinare = [];
    e.r.forEach(function (i) {
      var row = cat.righe[i];
      (p.sostanze || []).forEach(function (st) {
        var rr = ctx.rx[st.id];
        row.sostanze.forEach(function (x) {
          if (rr && rr.test(lower(x.s))) {
            var lim = (x.n || []).map(function (n) { return row.limiti[n]; }).filter(Boolean);
            r.disciplinare.push({ sostanza: x.s, limiti: lim, riga: row.avversita, pagina: row.pagina });
          }
        });
      });
      if (row.generale) r.disciplinare_generale = row.generale;
    });
    // rame metallo
    if (p.categoria === 'rame' && p.rame_g && perHa != null) {
      var cu = perHa / 1000 * p.rame_g / 1000;  // kg (o l) di prodotto x g/kg -> kg di rame
      r.rame_kg_ha = round(cu, 3);
      var sez = coltura(ctx, q.coltura).sezioni || [];
      r.rame_limite = (sez.map(function (x) { return (cat.rame || {})[x]; }).filter(Boolean)[0] || '').replace(/^\(\*+\)\s*/, '').replace(/\s+:\s*/, ': ') || null;
    }
    if (p.dose_nota) r.dose_nota = p.dose_nota;
    // coadiuvante consigliato da Gowan nei programmi (MAGO), corroboranti e nutrizionali della fase
    r.coadiuvanti = coadiuvanti(ctx, q, p, acqua, botte);
    r.nutrizionali = nutrizionali(ctx, q, p);
    r.botte = righeBotte(ctx, p, r, u);
    return r;
  }
  function fmt(x) { return x ? String(x.valore).replace('.', ',') + ' ' + x.unita : '–'; }
  function rng(r) { return (r[0] !== r[1] ? String(r[0]).replace('.', ',') + '-' : '') + String(r[1]).replace('.', ',') + ' ' + r[2]; }

  function coadiuvanti(ctx, q, p, acqua, botte) {
    var out = [];
    (ctx.cat.coadiuvanti || []).forEach(function (x) {
      if (x.nome === 'MAGO' && x.dose_hl) {
        var d = { nome: x.nome, tipo: x.tipo, uso: x.uso, pagina: x.pagina, dose: x.dose, scheda: x.scheda };
        if (acqua) {
          var perHa = Math.min(x.dose_hl[0] * acqua / 100, x.max_ha || Infinity);
          d.per_ha = quantita(perHa, 'ml');
          if (botte) d.botte = quantita(perHa * botte / acqua, 'ml');
        }
        d.per_hl = quantita(x.dose_hl[0], 'ml');
        out.push(d);
      }
      if (x.nome === 'ZEOLITE GOWAN' && /olivo|nocciolo/i.test(q.coltura)) out.push({ nome: x.nome, tipo: x.tipo, uso: x.uso, pagina: x.pagina, dose: x.dose });
    });
    return out;
  }

  function gruppoColtura(ctx, nome) { return coltura(ctx, nome).gruppo; }
  function nutrizionali(ctx, q, prodottoTrattamento) {
    var N = ctx.cat.nutrizionali, out = [];
    if (!N || !N.prodotti) return out;
    var f = fasi(ctx, q.coltura).filter(function (x) { return x.id === q.fase; })[0];
    var nome = lower(q.coltura), gr = gruppoColtura(ctx, q.coltura);
    N.prodotti.forEach(function (x) {
      if (x.escludi_colture && rx(x.escludi_colture).test(nome)) return;
      var sx = x.situazioni || [];
      if (q.obiettivo ? sx.indexOf(q.obiettivo) < 0 : (sx.length === 1 && sx[0] === 'carenza_ferro')) return;
      var uso = (x.usi || []).filter(function (u) {
        var okC = u.colture === '*' ? (u.gruppi || []).indexOf(gr) >= 0 : rx(u.colture).test(nome);
        var okA = !u.ambito || !q.ambito || u.ambito === q.ambito;
        var okF = !f || !f.bbch || !u.fasi_bbch || overlap(u.fasi_bbch, f.bbch);
        return okC && okA && okF;
      })[0];
      if (!uso) return;
      var n = { nome: x.nome, tipo: x.tipo, scopo: x.scopo, pagina: x.pagina, scheda: x.scheda, uso: uso,
                biologico: x.biologico || null, avvertenze: x.avvertenze || [] };
      if (x.rame_solo_colture && prodottoTrattamento && prodottoTrattamento.categoria === 'rame' && !rx(x.rame_solo_colture).test(nome))
        n.separato = 'Non in miscela con il rame e non subito dopo un trattamento rameico (fitotossicità, scheda Gowan): applicalo in un trattamento separato.';
      out.push(n);
    });
    return out;
  }

  // righe per la Botte: unità della botte (g/hl, ml/hl, kg/ha, l/ha...) e limiti di etichetta
  function righeBotte(ctx, p, r, u) {
    var rows = [];
    var hl = u.hl, haR = u.ha;
    if (r.dose.per_ha && haR) {
      // dose a ettaro (con il volume d'acqua indicato): la botte la converte nella quantità per la sua capienza
      var bh = BASE[haR[2].split('/')[0]];
      rows.push({ name: p.nome, dose: round(toBase(r.dose.per_ha) / bh[1], 4), unit: haR[2], formulation: p.form || 'OTHER',
                  category: p.categoria || 'altro', copper_g_per_unit: p.rame_g || null, label_max: haR[1], label_max_ha: null, uso: r.uso_i });
    } else if (r.dose.per_hl && hl) {
      var bu = BASE[hl[2].split('/')[0]];
      rows.push({ name: p.nome, dose: round(toBase(r.dose.per_hl), 3), unit: bu[0] + '/hl', formulation: p.form || 'OTHER',
                  category: p.categoria || 'altro', copper_g_per_unit: p.rame_g || null, label_max: round(hl[1] * bu[1], 3),
                  label_max_ha: haR ? { value: haR[1], unit: haR[2] } : null, uso: r.uso_i });
    }
    (r.coadiuvanti || []).forEach(function (c) {
      if (c.nome === 'MAGO' && c.per_hl) rows.push({ name: 'MAGO', dose: toBase(c.per_hl), unit: 'ml/hl', formulation: 'ADJ', category: 'altro',
                                                     label_max: 150, copper_g_per_unit: null, label_max_ha: { value: 1.5, unit: 'l/ha' } });
    });
    return rows;
  }
  function toBase(qt) { return qt.unita === 'kg' || qt.unita === 'l' ? qt.valore * 1000 : qt.valore; }

  var api = { prepara: prepara, fasi: fasi, situazioni: situazioni, avversita: avversita, ordina: ordina, ricetta: ricetta,
              quantita: quantita, fmt: fmt };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Consigli = api;
})(this);
