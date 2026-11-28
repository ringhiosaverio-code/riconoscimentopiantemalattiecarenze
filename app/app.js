/* PlantCare nel browser: lettori ottici (ONNX Runtime Web), quiz, botte, info. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var pct = function (x) { return x == null ? 'n.d.' : (x * 100).toFixed(1) + '%'; };
  var THRESHOLD = 0.5, SIZE = 224, HEADS = ['plant', 'disease', 'deficiency'];
  var MEAN = [0.485, 0.456, 0.406], STD = [0.229, 0.224, 0.225];
  var READER_LABELS = { plant: 'Lettore della coltura', disease: 'Lettore della malattia', deficiency: 'Lettore delle carenze' };
  var DATA = {}, session = null, stream = null;

  function getJSON(name) { return fetch('app/data/' + name).then(function (r) { if (!r.ok) throw new Error(name); return r.json(); }); }
  var ready = Promise.all(['readers.json', 'organs.json', 'mixing_rules.json', 'sources.json', 'quiz.json', 'causes.json', 'quiz_tips.json'].map(getJSON))
    .then(function (a) {
      DATA.readers = a[0]; DATA.organs = a[1]; DATA.rules = a[2]; DATA.sources = a[3]; DATA.quiz = a[4]; DATA.causes = a[5]; DATA.quizTips = a[6];
      var sel = $('organ');
      DATA.organs.forEach(function (o) { var op = document.createElement('option'); op.value = o.id; op.textContent = o.label; sel.appendChild(op); });
      var cs = $('crop');
      DATA.readers.plant.classes.slice().sort(function (x, y) { return x.name.localeCompare(y.name, 'it'); }).forEach(function (c) {
        var op = document.createElement('option'); op.value = c.label; op.textContent = c.name; cs.appendChild(op);
      });
      renderInfo();
      wireInfo();
    })
    .catch(function () { $('model-status').textContent = "Errore nel caricamento dei dati dell'app: ricarica la pagina."; });
  // facoltativi: senza questi file l'app mostra solo le probabilità
  getJSON('hypotheses.json').then(function (d) { DATA.hyp = d; }).catch(function () { DATA.hyp = null; });
  getJSON('lab.json').then(function (d) { DATA.lab = d; }).catch(function () { DATA.lab = null; });
  getJSON('difesa.json').then(function (d) { DATA.difesa = d; }).catch(function () { DATA.difesa = null; });
  getJSON('carenze.json').then(function (d) { DATA.carenze = d; }).catch(function () { DATA.carenze = {}; });
  getJSON('danni_insetti.json').then(function (d) { DATA.danni = d; }).catch(function () { DATA.danni = {}; });
  getJSON('note_legno.json').then(function (d) { DATA.noteLegno = d; }).catch(function () { DATA.noteLegno = []; });
  getJSON('valutazione.json').then(function (d) { DATA.val = d; if ($('info-val')) $('info-val').innerHTML = valHtml(); }).catch(function () { DATA.val = null; });
  // catalogo Gowan per Consigli e Botte (usi registrati, etichette, programmi, Disciplinare, stato UE)
  var CS = null;
  var catReady = getJSON('catalogo.json').then(function (d) { DATA.cat = d; CS = Consigli.prepara(d); showNorme(); return d; });
  catReady.catch(function () { DATA.cat = null; });
  var opt = function (v, t) { return '<option value="' + esc(v) + '">' + esc(t) + '</option>'; };
  var num = function (v) { return v === '' || v == null ? null : Number(v); };
  var fmtN = function (x) { return String(x).replace('.', ','); };
  var fmtQ = function (q) { return q ? fmtN(q.valore) + ' ' + q.unita : '–'; };
  function normeText() {
    var f = DATA.cat && DATA.cat.fonti;
    if (!f) return '';
    var d = function (iso) { return iso ? iso.split('-').reverse().join('/') : 'n.d.'; };
    return 'Norme in uso: Disciplinare Calabria ' + (f.disciplinare.versione || f.disciplinare.anno) + '; stato UE delle sostanze attive del ' +
      d(f.ue && f.ue.scaricato) + '; etichette Gowan del ' + d(f.gowan && f.gowan.consultato) + (f.norme && f.norme.controllato ? '; ultimo controllo automatico ' + d(f.norme.controllato) : '') + '.';
  }
  function showNorme() { if ($('info-norme')) $('info-norme').textContent = normeText(); }
  // avviso quando coltura e organo indicano una malattia del legno (la foto della foglia non basta)
  function woodNote(crop, organ) {
    return (DATA.noteLegno || []).filter(function (n) { return n.colture.indexOf(crop) >= 0 && n.organi.indexOf(organ) >= 0; })
      .map(function (n) {
        return '<div class="warn"><strong>' + esc(n.titolo) + '</strong><br>' + esc(n.testo) + '<br><span class="muted">Fonti: ' + srcLinks(n.fonti) + '</span></div>';
      }).join('');
  }

  // ------------------------------------------------------------------ calendario dei trattamenti
  var klInit = false, klPending = null, klLast = null;
  function isoOggi(n) { var d = new Date(Date.now() + (n || 0) * 864e5); return d.toISOString().slice(0, 10); }
  function dataIt(s) { if (!s) return ''; var p = s.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
  function initCalendario() {
    if (!CS) return;
    if (!klInit) {
      klInit = true;
      var cat = DATA.cat, byName = function (a, b) { return a.nome.localeCompare(b.nome, 'it'); };
      var cal = cat.colture.filter(function (c) { return c.sezioni.length; }).sort(byName);
      var alt = cat.colture.filter(function (c) { return !c.sezioni.length; }).sort(byName);
      $('kl-crop').innerHTML = '<option value="">Scegli la coltura</option>' +
        '<optgroup label="Colture del Disciplinare della Calabria">' + cal.map(function (c) { return opt(c.nome, c.nome); }).join('') + '</optgroup>' +
        '<optgroup label="Altre colture con prodotti Gowan registrati">' + alt.map(function (c) { return opt(c.nome, c.nome); }).join('') + '</optgroup>';
      $('kl-crop').disabled = false;
      var defs = (DATA.readers.deficiency || { classes: [] }).classes.filter(function (c) { return DATA.carenze && DATA.carenze[c.label]; });
      $('kl-def').innerHTML = defs.map(function (c) { return opt(c.label, c.name); }).join('');
      $('kl-start').value = isoOggi(0); $('kl-harvest').value = isoOggi(120);
      $('kl-status').textContent = 'Prodotti Gowan registrati, Disciplinare della Calabria e schede dei concimi.';
      $('kl-kind').addEventListener('change', klKind);
      $('kl-crop').addEventListener('change', klCrop);
      $('kl-adv').addEventListener('change', klAdv);
      ['kl-phase', 'kl-sit', 'kl-start', 'kl-harvest', 'kl-def'].forEach(function (id) { $(id).addEventListener('change', klReady); });
      $('kl-go').addEventListener('click', klRun);
    }
    if (klPending) {
      var p = klPending; klPending = null;
      $('kl-kind').value = 'difesa'; klKind(); $('kl-crop').value = p.c; klCrop();
      if (p.a) { $('kl-adv').value = p.a; klAdv(); }
      if (p.f) $('kl-phase').value = p.f;
      klReady();
    }
  }
  function openCalendario(crop, adv, fase) { klPending = { c: crop, a: adv, f: fase }; showTab('calendario'); }
  function klKind() {
    var dif = $('kl-kind').value === 'difesa';
    $('kl-difesa').hidden = !dif; $('kl-carenza').hidden = dif; $('kl-more').hidden = !dif;
    $('kl-out').innerHTML = ''; klReady();
  }
  function klCrop() {
    var crop = $('kl-crop').value, adv = $('kl-adv'), ph = $('kl-phase');
    $('kl-out').innerHTML = '';
    if (!crop) { adv.disabled = ph.disabled = $('kl-sit').disabled = true; klReady(); return; }
    var list = Consigli.avversita(CS, crop), c = CS.cat.colture[CS.colture[crop].i];
    var grp = function (t) {
      return list.filter(function (e) { return e.t === t; }).map(function (e) {
        return opt(e.id, e.nome + (e.u.length ? '' : ' — solo sostanze del Disciplinare'));
      }).join('');
    };
    adv.innerHTML = '<option value="">Scegli la malattia o il parassita</option><optgroup label="Malattie">' + grp('malattia') +
      '</optgroup><optgroup label="Insetti, acari e altri parassiti">' + grp('insetto') + '</optgroup>';
    adv.disabled = false;
    ph.innerHTML = Consigli.fasi(CS, crop).map(function (f) {
      return opt(f.id, (f.n ? f.n + '. ' : '') + f.nome + (f.bbch ? ' (BBCH ' + f.bbch[0] + (f.bbch[1] !== f.bbch[0] ? '-' + f.bbch[1] : '') + ')' : ''));
    }).join('');
    ph.disabled = false;
    $('kl-disc').disabled = !c.sezioni.length;
    klAdv();
  }
  function klAdv() {
    var crop = $('kl-crop').value, id = $('kl-adv').value, sit = $('kl-sit');
    $('kl-prods').innerHTML = '';
    if (!crop || !id) { sit.disabled = true; sit.innerHTML = ''; klReady(); return; }
    var e = Consigli.avversita(CS, crop).filter(function (x) { return x.id === id; })[0];
    sit.innerHTML = Consigli.situazioni(CS, e.t).map(function (x) { return opt(x.id, x.nome); }).join('');
    sit.disabled = false;
    // prodotti registrati per l'avversità (principi attivi e gruppi di resistenza), da scegliere se si vuole
    var seen = {}, rows = [];
    e.u.forEach(function (i) {
      var p = CS.cat.prodotti[CS.cat.usi[i].p];
      if (seen[p.nome]) return; seen[p.nome] = 1;
      rows.push('<label class="check"><input type="checkbox" class="kl-p" value="' + esc(p.nome) + '"> <span><strong>' + esc(p.nome) + '</strong> — ' +
        esc((p.sostanze || []).map(function (x) { return x.nome; }).join(' + ')) + (p.codici && p.codici.length ? ' <span class="muted">(' + esc(p.codici.join(', ')) + ')</span>' : '') + '</span></label>');
    });
    $('kl-prods').innerHTML = rows.length ? rows.join('') : '<p class="muted">Nessun prodotto Gowan registrato: il calendario elencherà le sostanze ammesse dal Disciplinare.</p>';
    klReady();
  }
  function klReady() {
    var dif = $('kl-kind').value === 'difesa', ok = $('kl-start').value && $('kl-harvest').value;
    $('kl-go').disabled = !(ok && (dif ? $('kl-crop').value && $('kl-adv').value && $('kl-phase').value : $('kl-def').value));
  }
  function klRun() {
    var h;
    if ($('kl-kind').value === 'carenza') {
      var qc = { carenza: $('kl-def').value, coltura: $('kl-crop').value, inizio: $('kl-start').value, raccolta: $('kl-harvest').value, modo: $('kl-mode').value };
      var rc = Calendario.pianoCarenza(DATA.carenze, qc);
      var nome = $('kl-def').selectedOptions[0].textContent;
      h = '<section class="card"><h2>Calendario: ' + esc(nome) + '</h2>';
      if (rc.errore) h += '<p class="warn">' + esc(rc.errore) + '</p>';
      if (rc.interventi.length) {
        h += '<p><strong>' + esc(rc.forma || '') + '</strong>' + (rc.fonte ? ' <span class="muted">— ' + esc(rc.fonte) + '</span>' : '') + '</p>';
        h += '<ol class="tratt">' + rc.interventi.map(function (x) {
          return '<li><p class="t-head"><strong>' + dataIt(x.data) + '</strong>' + (x.dal_precedente ? ' <span class="muted">(+' + x.dal_precedente + ' giorni)</span>' : '') + '</p>' +
            '<p><strong>' + esc(x.prodotto || '') + '</strong></p>' + (x.dose ? '<p class="muted">' + esc(x.dose) + '</p>' : '') + '</li>';
        }).join('') + '</ol>';
      }
      h += (rc.avvisi || []).map(function (a) { return '<p class="muted">' + esc(a) + '</p>'; }).join('');
      klLast = { titolo: nome, interventi: rc.interventi };
    } else {
      var q = { coltura: $('kl-crop').value, avversita: $('kl-adv').value, fase: $('kl-phase').value, situazione: $('kl-sit').value,
                ambito: $('kl-amb').value, bio: $('kl-bio').checked, disciplinare: $('kl-disc').checked && !$('kl-disc').disabled,
                inizio: $('kl-start').value, raccolta: $('kl-harvest').value, fioritura: $('kl-flower').value || null, pressione: $('kl-press').value,
                rame_max: num($('kl-cu').value), ettari: num($('kl-ha').value), acqua: num($('kl-water').value),
                prodotti: Array.prototype.slice.call(document.querySelectorAll('.kl-p:checked')).map(function (x) { return x.value; }) };
      var r;
      try { r = Calendario.piano(CS, q); } catch (err) { $('kl-out').innerHTML = '<div class="card warn">' + esc(err.message) + '</div>'; return; }
      var titolo = q.coltura + ' — ' + (r.avversita || $('kl-adv').selectedOptions[0].textContent);
      h = '<section class="card"><h2>Calendario: ' + esc(titolo) + '</h2>';
      h += '<p class="muted">Dal ' + dataIt(q.inizio) + ' alla raccolta del ' + dataIt(q.raccolta) + (r.fioritura_stimata ? '; piena fioritura ' + (q.fioritura ? 'indicata' : 'stimata') + ' il ' + dataIt(r.fioritura_stimata) : '') +
        '. Pressione ' + esc(q.pressione) + '.</p>';
      if (r.errore) h += '<p class="warn">' + esc(r.errore) + '</p>';
      if (r.interventi.length) {
        h += '<ol class="tratt">' + r.interventi.map(function (x) {
          var dose = [x.dose_ha ? Consigli.fmt(x.dose_ha) + '/ha' : '', x.dose_hl ? Consigli.fmt(x.dose_hl) + '/hl' : ''].filter(Boolean).join(' · ');
          return '<li><p class="t-head"><strong>' + dataIt(x.data) + '</strong>' + (x.dal_precedente ? ' <span class="muted">(+' + x.dal_precedente + ' giorni)</span>' : '') +
            ' · ' + esc(x.fase) + ' <span class="muted">BBCH ~' + x.bbch_stimato + '</span></p>' +
            '<p><strong>' + esc(x.prodotto) + '</strong> <span class="muted">' + esc(x.sostanze.join(' + ')) + (x.gruppi.length ? ' · ' + esc(x.gruppi.join(', ')) : '') + '</span></p>' +
            (dose ? '<p>Dose: ' + esc(dose) + (x.totale ? ' <span class="muted">(totale ' + esc(Consigli.fmt(x.totale)) + ')</span>' : '') + '</p>' : '') +
            '<p class="muted">' + (x.uso_max ? x.uso_n + 'º trattamento su ' + x.uso_max + ' ammessi (' + esc(x.fonte_max || '') + ')' : x.uso_n + 'º trattamento con questo prodotto') +
            (x.phi != null ? ' · carenza ' + x.phi + ' giorni: non oltre il ' + dataIt(x.ultimo_utile) : '') +
            (x.limiti_comuni && x.limiti_comuni.length ? ' · ' + esc(x.limiti_comuni.join('; ')) : '') + '</p>' +
            (x.alternanza ? '<p class="warn">' + esc(x.alternanza) + '</p>' : '') + '</li>';
        }).join('') + '</ol>';
      }
      h += (r.avvisi || []).map(function (a) { return '<p class="muted">' + esc(a) + '</p>'; }).join('');
      if (r.disciplinare && r.disciplinare.length) {
        h += '<details' + (r.interventi.length ? '' : ' open') + '><summary><strong>Sostanze ammesse dal Disciplinare della Calabria</strong> (anche di altre aziende)</summary>' +
          r.disciplinare.map(function (row) {
            return '<p><strong>' + esc(row.avversita) + '</strong> <span class="muted">(' + esc(row.coltura) + ', pag. ' + row.pagina + ')</span></p>' +
              (row.criteri ? '<p class="muted">' + esc(row.criteri) + '</p>' : '') + '<ul>' + row.sostanze.map(function (x) {
                return '<li>' + esc(x.nome) + (x.limiti.length ? ' <span class="muted">— ' + esc(x.limiti.join('; ')) + '</span>' : '') + '</li>';
              }).join('') + '</ul>';
          }).join('') + '</details>';
      }
      klLast = { titolo: titolo, interventi: r.interventi };
    }
    if (klLast.interventi.length)
      h += '<div class="row"><button type="button" id="kl-ics">Aggiungi al calendario del telefono</button><button type="button" class="secondary" id="kl-print">Stampa</button></div>';
    h += '<p class="muted">Strumento di supporto: prima di ogni trattamento controlla l\'etichetta del prodotto, che prevale, e le condizioni in campo.</p></section>';
    $('kl-out').innerHTML = h;
    if ($('kl-ics')) $('kl-ics').addEventListener('click', function () {
      var blob = new Blob([Calendario.ics(klLast.titolo, klLast.interventi)], { type: 'text/calendar' }), a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = 'trattamenti.ics'; document.body.appendChild(a); a.click(); a.remove();
    });
    if ($('kl-print')) $('kl-print').addEventListener('click', function () { window.print(); });
    $('kl-out').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ------------------------------------------------------------------ schede
  var TABS = ['reader', 'consigli', 'calendario', 'quiz', 'tank', 'info'];
  function showTab(name) {
    TABS.forEach(function (t) {
      $('tab-' + t).hidden = t !== name;
      $('t-' + t).setAttribute('aria-selected', String(t === name));
    });
    if (name === 'tank') ready.then(initTank);
    if (name === 'consigli') catReady.then(initConsigli, function () { $('cs-status').textContent = 'Catalogo non disponibile: ricarica la pagina.'; });
    if (name === 'calendario') catReady.then(initCalendario, function () { $('kl-status').textContent = 'Catalogo non disponibile: ricarica la pagina.'; });
    window.scrollTo(0, 0);
  }
  TABS.forEach(function (t) { $('t-' + t).addEventListener('click', function () { showTab(t); }); });

  // ------------------------------------------------------------------ modello
  function loadModel() {
    if (session) return Promise.resolve(session);
    ort.env.wasm.wasmPaths = new URL('app/ort/', document.baseURI).href;  // URL assoluto: serve all'import() dinamico
    ort.env.wasm.numThreads = 1;
    $('prog').hidden = false;
    $('model-status').textContent = 'Scaricamento del modello in corso…';
    // Il modello completo supera i 100 MB ammessi da GitHub per file: è diviso in parti
    // (app/model/parti.json) che qui si scaricano in ordine e si rimettono insieme.
    var chunks = [], got = 0, total = 45e6;
    function scarica(url) {
      return fetch(url).then(function (resp) {
        if (!resp.ok) throw new Error('modello');
        var reader = resp.body.getReader();
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) return;
            chunks.push(r.value); got += r.value.length;
            $('prog').firstElementChild.style.width = Math.min(100, got / total * 100).toFixed(0) + '%';
            return pump();
          });
        }
        return pump();
      });
    }
    return fetch('app/model/parti.json').then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
      .then(function (p) {
        if (p && p.parti) {
          total = p.byte;
          return p.parti.reduce(function (pr, f) { return pr.then(function () { return scarica('app/model/' + f); }); }, Promise.resolve());
        }
        return scarica('app/model/plantcare.onnx');
      }).then(function () {
        var buf = new Uint8Array(got), off = 0;
        chunks.forEach(function (c) { buf.set(c, off); off += c.length; });
        chunks = [];
        $('model-status').textContent = 'Preparazione del modello…';
        return ort.InferenceSession.create(buf, { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
      }).then(function (s) {
      session = s; $('prog').hidden = true; $('model-status').textContent = 'Modello pronto.'; return s;
    });
  }

  // quadrato scelto (di base quello centrale) ridimensionato a 224 px, normalizzato;
  // secondo elemento del batch: immagine specchiata
  function toTensor(source, w, h, sq) {
    var c = $('canvas'); c.width = SIZE; c.height = SIZE;
    var ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    var s = sq ? sq.s : Math.min(w, h), x0 = sq ? sq.x : (w - s) / 2, y0 = sq ? sq.y : (h - s) / 2;
    ctx.drawImage(source, x0, y0, s, s, 0, 0, SIZE, SIZE);
    var px = ctx.getImageData(0, 0, SIZE, SIZE).data, n = SIZE * SIZE;
    var data = new Float32Array(2 * 3 * n);
    for (var y = 0; y < SIZE; y++) {
      for (var x = 0; x < SIZE; x++) {
        var i = (y * SIZE + x) * 4, j = y * SIZE + x, jf = y * SIZE + (SIZE - 1 - x);
        for (var k = 0; k < 3; k++) {
          var v = (px[i + k] / 255 - MEAN[k]) / STD[k];
          data[k * n + j] = v; data[3 * n + k * n + jf] = v;
        }
      }
    }
    return new ort.Tensor('float32', data, [2, 3, SIZE, SIZE]);
  }

  var lastPhoto = null, lastPred = null;
  function keepPhoto(source, w, h) {
    var k = Math.min(1, 1024 / Math.max(w, h)), c = document.createElement('canvas');
    c.width = Math.round(w * k); c.height = Math.round(h * k);
    c.getContext('2d').drawImage(source, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.88);
  }

  function analyze(source, w, h, sq) {
    lastPhoto = keepPhoto(source, w, h);
    $('out').innerHTML = '<div class="card">Analisi in corso…</div>';
    ready.then(loadModel).then(function (s) {
      var t0 = performance.now();
      return s.run({ image: toTensor(source, w, h, sq) }).then(function (outs) {
        var res = {};
        HEADS.concat(['pest']).forEach(function (hd) {
          if (!outs[hd] || !DATA.readers[hd]) return;
          var o = outs[hd].data, k = o.length / 2, probs = [];
          for (var i = 0; i < k; i++) probs.push((o[i] + o[k + i]) / 2);
          res[hd] = probs;
        });
        res.crop = $('crop').value || null;
        if (res.crop) res.disease = cropMask(res.disease, res.crop);
        render(res, (performance.now() - t0) / 1000);
      });
    }).catch(function (e) {
      $('prog').hidden = true;
      $('out').innerHTML = '<div class="card warn">Analisi non riuscita: ' + esc(e.message || e) + '. Controlla la connessione e riprova.</div>';
    });
  }

  // Coltura indicata dall'utente: probabilità delle malattie ristrette a quelle viste su quella coltura
  // nell'addestramento (le classi senza coltura, come "pianta sana", restano), poi rinormalizzate.
  function cropMask(probs, crop) {
    var C = DATA.readers.disease.classes, out = probs.map(function (p, i) {
      var cc = C[i].crops; return (!cc || !cc.length || cc.indexOf(crop) >= 0) ? p : 0;
    });
    var s = out.reduce(function (a, b) { return a + b; }, 0);
    return s > 0 ? out.map(function (p) { return p / s; }) : probs;
  }

  // ------------------------------------------------------------------ ipotesi calibrate (predizione conforme)
  // Elenco delle classi con probabilità >= soglia: la soglia è calibrata sulle foto di campo di validazione
  // perché l'elenco contenga la risposta giusta 95 o 99 volte su 100 (verificato sul test).
  function hypLevel(head, level, crop, cause) {
    var H = DATA.hyp && DATA.hyp[head]; if (!H) return null;
    if (cause) H = H.cause; else if (crop && H.con_coltura) H = H.con_coltura;
    return H && H.livelli && H.livelli[level] ? H.livelli[level] : null;
  }
  function hypSet(probs, lev) {
    return top(probs, probs.length).filter(function (x, k) { return k === 0 || x[0] >= lev.soglia_probabilita; });
  }
  function sureNote(head, p, crop) {
    var s = hypLevel(head, 'sicura', crop);
    if (!s || s.soglia > 1 || p < s.soglia || s.giuste == null) return '';
    return ' <span class="sure">risposta sicura</span><span class="muted"> (con questa confidenza, sulle foto di campo di prova: giusta nel ' + pct(s.giuste) + ' dei casi)</span>';
  }
  function hypHtml(set, nameOf, lev, level, what) {
    var item = function (x) { return '<li>' + esc(nameOf(x[1])) + ' <span class="muted">' + pct(x[0]) + '</span></li>'; };
    var h = '<div class="hyp"><p><strong>' + what + ': ' + set.length + '</strong> <span class="muted">— sulle foto di campo di prova la risposta giusta era nell\'elenco ' +
      pct(lev.copertura) + ' delle volte (obiettivo ' + level + ' su 100)</span></p><ol>' + set.slice(0, 6).map(item).join('') + '</ol>';
    if (set.length > 6) h += '<details><summary>Altre ' + (set.length - 6) + ' ipotesi meno probabili</summary><ol start="7">' + set.slice(6).map(item).join('') + '</ol></details>';
    if (set.length > 6) h += '<p class="muted">Elenco lungo: la foto da sola non basta. Indica la coltura, inquadra la parte colpita da vicino o chiedi un\'analisi.</p>';
    return h + '</div>';
  }

  // ------------------------------------------------------------------ quando serve il laboratorio
  function srcLinks(f) {
    return f.map(function (x) { return '<a href="' + esc(x.url) + '" target="_blank" rel="noopener">' + esc(x.title) + '</a>'; }).join(' · ');
  }
  function labBlock(causeIds, nDisease, regs) {
    var L = DATA.lab; if (!L) return '';
    var A = L.analisi_per_causa, names = DATA.causes || {}, lines = [];
    var real = causeIds.filter(function (c) { return c !== 'sano'; });
    var doubt = real.length > 1 || nDisease > 1;
    if (real.length > 1) lines.push('<p><strong>Dalla foto non si distingue tra: ' + esc(real.map(function (c) { return names[c] || c; }).join(', ')) + '.</strong> Per decidere serve un\'analisi.</p>');
    var specific = regs.filter(function (r) { return r.o.analisi; }).map(function (r) { return r.cause; });
    real.forEach(function (c) {
      var a = A[c]; if (!a || (a.quando !== 'sempre' && !doubt) || specific.indexOf(c) >= 0) return;  // c'è l'analisi specifica
      lines.push('<p><strong>' + esc(names[c] || c) + ':</strong> ' + esc(a.testo) + '<br><span class="muted">Fonte: ' + srcLinks(a.fonti) + '</span></p>');
    });
    if (!lines.length && real.length) lines.push('<p>Dalla foto la diagnosi è netta: il laboratorio serve solo se i sintomi non corrispondono alla scheda della malattia.</p>');
    regs.forEach(function (r) { lines.push(regNote(r.o, r.p, '')); });
    return lines.length ? '<div class="reader"><h3>Serve il laboratorio?</h3>' + lines.join('') + '</div>' : '';
  }
  // organismo regolamentato (categoria letta sulla scheda EPPO) e, se c'è, l'analisi del protocollo EPPO
  function regNote(o, p, prefix) {
    var link = ' (<a href="' + esc(o.url) + '" target="_blank" rel="noopener">scheda EPPO</a>)';
    var head = esc(o.organismo) + ', probabilità stimata ' + pct(p) + '. ' + esc(o.ue) + '; EPPO: ' + esc(o.lista_eppo) + link + '.' + (o.nota ? ' ' + esc(o.nota) : '');
    var an = o.analisi ? '<br><strong>Analisi:</strong> ' + esc(o.analisi) + ' <span class="muted">Fonte: ' + srcLinks(o.fonti) + '</span>' : '';
    if (o.tipo === 'quarantena') return '<div class="warn">' + prefix + '<strong>Organismo da quarantena tra le ipotesi:</strong> ' + head + ' Se lo sospetti, contatta il Servizio Fitosanitario Regionale: la conferma spetta ai laboratori ufficiali.' + an + '</div>';
    if (o.tipo === 'rnqp') return '<p class="muted">' + prefix + '<strong>Organismo regolamentato per il materiale di propagazione:</strong> ' + head + an + '</p>';
    return '<div class="warn">' + prefix + '<strong>Organismo segnalato dall\'EPPO:</strong> ' + head + ' Se lo trovi, informa il Servizio Fitosanitario Regionale.' + an + '</div>';
  }
  function regsIn(head, set) {
    var R = DATA.readers[head], L = DATA.lab, out = [];
    if (!R || !L) return out;
    set.forEach(function (x) { var c = R.classes[x[1]]; if (c.reg != null) out.push({ o: L.organismi_regolamentati[c.reg], p: x[0], cause: c.cause }); });
    return out;
  }

  // ------------------------------------------------------------------ difesa (fonti verificate)
  // Disciplinare di produzione integrata della Regione Calabria (avversità, criteri, sostanze ammesse e
  // limiti) e usi registrati dei prodotti Gowan Italia (dose, intervallo di sicurezza, note): niente è
  // scritto a mano, tutto viene dai documenti; l'etichetta autorizzata prevale.
  // ordine dei prodotti per la classe del lettore (motore di Consigli, situazione "primi sintomi", fase non nota)
  function rankFor(head, label, plant) {
    if (!CS || plant === '*') return null;
    var hits = (DATA.cat.classi[head + '|' + label] || []).filter(function (x) { return x.plant === plant; });
    if (!hits.length) return null;
    var size = function (x) { return (Consigli.avversita(CS, x.c).filter(function (e) { return e.id === x.id; })[0] || { u: [] }).u.length; };
    hits.sort(function (a, b) { return size(b) - size(a); });
    try {
      var r = Consigli.ordina(CS, { coltura: hits[0].c, avversita: hits[0].id, fase: null, situazione: 'primi_sintomi', disciplinare: false, ambito: null });
      return { nomi: r.scelti.map(function (x) { return x.prodotto; }), hit: hits[0] };
    } catch (e) { return null; }
  }
  function wireConsLinks(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.go-cons'), function (a) {
      a.addEventListener('click', function (ev) { ev.preventDefault(); openConsigli(a.getAttribute('data-c'), a.getAttribute('data-a')); });
    });
  }

  function difesaBlock(head, label, crop, plantGuess) {
    var D = DATA.difesa, e = D && D.classi[head + '|' + label];
    if (!e) return '';
    var keys = Object.keys(e), pick = crop && e[crop] ? [crop] : (plantGuess && e[plantGuess] ? [plantGuess] : keys);
    var plantName = function (k) {
      if (k === '*') return 'tutte le colture';
      var c = DATA.readers.plant.classes.filter(function (x) { return x.label === k; })[0];
      return c ? c.name : k;
    };
    var fd = D.fonti.disciplinare, g = D.fonti.gowan;
    var h = '<details class="reader" open><summary><strong>Difesa: cosa prevedono le norme e i prodotti</strong></summary>';
    pick.forEach(function (k) {
      var ent = e[k];
      ent.r.forEach(function (i) {
        var r = D.righe[i], by = { biologico: [], naturale: [], sintesi: [] };
        r.sostanze.forEach(function (x) {
          by[x.t].push(esc(x.s) + (x.n && x.n.length ? ' <span class="muted">(' + esc(x.n.join(', ')) + ')</span>' : '') +
            (x.ue ? ' <strong>⚠ non approvata nell\'UE' + (x.ue.scadenza ? ' (scadenza ' + esc(x.ue.scadenza) + ')' : '') + '</strong>' : ''));
        });
        h += '<div class="dif"><h4>' + esc(r.coltura.charAt(0) + r.coltura.slice(1).toLowerCase()) + ': ' + esc(r.avversita) + '</h4>';
        if (r.criteri) h += '<details><summary>Criteri di intervento</summary><p>' + esc(r.criteri) + '</p></details>';
        if (by.biologico.length) h += '<p><strong>Mezzi biologici e ausiliari:</strong> ' + by.biologico.join(', ') + '</p>';
        if (by.naturale.length) h += '<p><strong>Mezzi di origine naturale o minerale:</strong> ' + by.naturale.join(', ') + '</p>';
        if (by.sintesi.length) h += '<p><strong>Sostanze attive di sintesi:</strong> ' + by.sintesi.join(', ') + '</p>';
        if (!r.sostanze.length) h += '<p class="muted">Nessuna sostanza indicata dal Disciplinare per questa avversità: valgono i criteri di intervento.</p>';
        if (r.note) h += '<p class="muted"><strong>Limitazioni d\'uso e note:</strong> ' + esc(r.note) + '</p>';
        if (r.sostanze.some(function (x) { return x.ue; })) h += '<p class="warn">Secondo la banca dati UE dei pesticidi alcune sostanze di questo elenco non sono più approvate: non usare prodotti che le contengono, salvo i periodi di smaltimento delle scorte fissati dal Ministero.</p>';
        if (r.rimosse && r.rimosse.length) h += '<p class="warn"><strong>Non più nell\'elenco del Disciplinare ' + esc(fd.versione || fd.anno) + ':</strong> ' +
          esc(r.rimosse.map(function (x) { return typeof x === 'string' ? x : x.s + ' (c\'era nella versione di ' + x.v + ')'; }).join(', ')) + '. Prima di usare scorte di magazzino verifica l\'autorizzazione del prodotto.</p>';
        if (r.sostanze.some(function (x) { return /rame/i.test(x.s); }) && D.rame[r.coltura]) h += '<p class="muted">' + esc(D.rame[r.coltura]) + '</p>';
        h += '<p class="muted">Fonte: <a href="' + esc(fd.url) + '" target="_blank" rel="noopener">' + esc(fd.titolo) + '</a>, pag. ' + r.pagina + '. Il raggruppamento in biologici, naturali e di sintesi è dell\'app; lo stato UE delle sostanze è quello della banca dati dei pesticidi della Commissione europea.</p></div>';
      });
      if (ent.u.length) {
        // un prodotto per riga (dose e intervallo del primo uso), i dettagli per coltura si aprono a richiesta
        var byP = {}, order = [];
        ent.u.forEach(function (i) {
          var u = D.usi[i];
          if (!byP[u.prodotto]) { byP[u.prodotto] = { p: u, rows: [] }; order.push(u.prodotto); }
          byP[u.prodotto].rows.push(u);
        });
        var prodHtml = function (name) {
          var g = byP[name], u = g.p, dose = [u.dose_ha, u.dose_hl].filter(Boolean).join(' · ') || 'vedi etichetta';
          var x = '<div class="prod"><p><strong><a href="' + esc(u.pagina) + '" target="_blank" rel="noopener">' + esc(name) + '</a></strong> — ' + esc(u.composizione || '') +
            '<br>Dose: ' + esc(dose) + '; intervallo di sicurezza: ' + esc(u.intervallo_sicurezza || '-') + '</p>';
          var pi = (D.prodotti_info || {})[name] || {};
          x += '<details><summary>Usi registrati, epoche, note e miscele (' + g.rows.length + ')</summary>';
          if (pi.compatibilita) x += '<p><strong>Miscele, dall\'etichetta:</strong> ' + esc(pi.compatibilita) + '</p>';
          if (pi.etichetta) x += '<p class="muted"><a href="' + esc(pi.etichetta) + '" target="_blank" rel="noopener">Etichetta</a>' + (pi.etichetta_validita ? ': ' + esc(pi.etichetta_validita) : '') + '</p>';
          g.rows.forEach(function (r) {
            x += '<p class="muted"><strong>' + esc(r.coltura) + (r.ambito ? ', ' + esc(r.ambito) : '') + '</strong> — ' + esc(r.avversita) + '. Dose: ' +
              esc([r.dose_ha, r.dose_hl].filter(Boolean).join(' · ') || 'vedi etichetta') + '; intervallo: ' + esc(r.intervallo_sicurezza || '-') + '. ' + esc(r.note || '') + '</p>';
          });
          return x + '</details></div>';
        };
        var rk = rankFor(head, label, k);
        if (rk) order.sort(function (a, b) { var ia = rk.nomi.indexOf(a), ib = rk.nomi.indexOf(b); return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib); });
        h += '<div class="dif"><h4>Prodotti Gowan registrati per questa avversità (' + esc(plantName(k)) + '): ' + order.length + '</h4>';
        if (rk) h += '<p class="muted">In ordine di preferenza per i primi sintomi, con le regole della sezione Consigli (programma Gowan, tipo di azione, mezzi a basso impatto). Per fase della coltura, situazione, dosi e quantità: <a href="#" class="go-cons" data-c="' +
          esc(rk.hit.c) + '" data-a="' + esc(rk.hit.id) + '">prepara la ricetta</a>.</p>';
        order.slice(0, 5).forEach(function (n) { h += prodHtml(n); });
        if (order.length > 5) {
          h += '<details><summary>Altri ' + (order.length - 5) + ' prodotti</summary>';
          order.slice(5).forEach(function (n) { h += prodHtml(n); });
          h += '</details>';
        }
        h += '<p class="muted">' + esc(g.fonte) + ', consultato il ' + esc(g.consultato) + '. ' + esc(g.avvertenza) + ' Per prodotti di altre aziende consulta la banca dati dei prodotti fitosanitari del Ministero della Salute.</p></div>';
      }
    });
    var C = D.coadiuvanti;
    if (C && C.prodotti && C.prodotti.length) {
      h += '<details><summary>Coadiuvanti, corroboranti e pulizia della botte (catalogo Gowan)</summary>';
      C.prodotti.forEach(function (x) {
        var mi = (D.prodotti_info || {})[x.nome] || {};
        h += '<p><strong><a href="' + esc(x.pagina) + '" target="_blank" rel="noopener">' + esc(x.nome) + '</a></strong> — ' + esc(x.tipo) + '. ' + esc(x.composizione) + '. ' + esc(x.uso) +
          (mi.compatibilita ? ' <em>Dall\'etichetta:</em> ' + esc(mi.compatibilita) : '') + '</p>';
      });
      h += '<p class="muted">Fonte: ' + esc(C.fonte) + '. Per ogni miscela prevale la sezione compatibilità dell\'etichetta dei prodotti usati.</p></details>';
    }
    h += '<p class="muted">Le miscele ammesse sono quelle indicate in etichetta (sezione compatibilità). Per l\'ordine di immissione nella botte e le incompatibilità note usa la scheda <a href="#" id="go-tank2">Botte</a>.</p>';
    return h + '</details>';
  }

  // Causa probabile: somma delle probabilità delle classi con la stessa causa (insetti, acari, funghi...).
  // Più affidabile della singola classe: due danni da insetti simili non si tolgono probabilità a vicenda.
  function causeBlock(probs) {
    var R = DATA.readers.disease, names = DATA.causes || {}, sum = {};
    if (!probs || !R.classes[0] || !('cause' in R.classes[0])) return { html: '', best: null };
    probs.forEach(function (p, i) { var c = R.classes[i].cause; sum[c] = (sum[c] || 0) + p; });
    var t = Object.keys(sum).map(function (c) { return [sum[c], c]; }).sort(function (a, b) { return b[0] - a[0]; }).slice(0, 3);
    var ok = t[0][0] >= THRESHOLD, best = ok ? { id: t[0][1], name: names[t[0][1]] || t[0][1], p: t[0][0] } : null;
    var h = '<div class="reader"><h3>Causa probabile dei sintomi: ' + esc(best ? best.name : 'non determinabile') + '</h3>';
    t.forEach(function (x) {
      h += '<div class="cand"><div class="bar"><span style="width:' + (x[0] * 100).toFixed(1) + '%"></span><em>' + esc(names[x[1]] || x[1]) + '</em></div><div class="p">' + pct(x[0]) + '</div></div>';
    });
    var pests = (sum.insetto || 0) + (sum.acaro || 0);
    if (pests >= 0.3) h += '<p class="warn">Sintomi compatibili con insetti o acari (' + pct(pests) + '). Cerca l\'insetto o l\'acaro sulla pagina inferiore delle foglie, nei germogli e nei frutti, con una lente: fotografalo da vicino e controlla il lettore degli insetti.</p>';
    // cause possibili al 99%: tutte quelle con probabilità sopra la soglia calibrata
    var lev = hypLevel('disease', '99', null, true), ids = best ? [best.id] : t.slice(0, 2).map(function (x) { return x[1]; });
    if (lev) {
      ids = Object.keys(sum).filter(function (c) { return sum[c] >= lev.soglia_probabilita; }).sort(function (a, b) { return sum[b] - sum[a]; });
      if (!ids.length) ids = [t[0][1]];
      h += '<p><strong>Cause possibili: ' + esc(ids.map(function (c) { return names[c] || c; }).join(', ')) + '</strong> <span class="muted">— sulle foto di campo di prova la causa giusta era tra queste ' + pct(lev.copertura) + ' delle volte (obiettivo 99 su 100)</span></p>';
    }
    return { html: h + '</div>', best: best, ids: ids, pests: pests };
  }

  // Danni da insetti e acari, malattie trasmesse da vettori e fumaggine (configs/danni_insetti.yaml):
  // dal sintomo riconosciuto all'insetto che lo causa, con la difesa contro l'insetto.
  var LINK_TITLE = { danno: 'Danno causato da', vettore: 'Malattia trasmessa da', melata: 'Cresce sulla melata di' };
  function pestIndex() {
    var R = DATA.readers.pest, ix = {};
    if (R) R.classes.forEach(function (c, i) { ix[c.label] = i; });
    return ix;
  }
  function linkBlock(res, crop, plantGuess) {
    var L = DATA.danni, R = DATA.readers.disease, P = DATA.readers.pest;
    if (!L || !res.disease) return { html: '', open: false };
    var ix = pestIndex(), seen = {}, h = '', first = true, open = false;
    top(res.disease, 3).forEach(function (x) {
      var c = R.classes[x[1]], e = L[c.label];
      if (!e || x[0] < 0.15 || seen[c.label]) return;
      seen[c.label] = 1;
      // insetti collegati, ordinati per la probabilità del lettore degli insetti
      var ins = e.insetti.filter(function (l) { return l in ix; }).map(function (l) {
        return { label: l, name: P.classes[ix[l]].name, p: res.pest ? res.pest[ix[l]] : 0 };
      }).sort(function (a, b) { return b.p - a.p; });
      h += '<div class="reader"><h3>' + esc(c.name) + ' (' + pct(x[0]) + '): ' + esc(LINK_TITLE[e.tipo] || 'Collegato a') + '</h3>';
      if (e.nota) h += '<p>' + esc(e.nota) + '</p>';
      if (ins.length) {
        h += '<ul>' + ins.map(function (i) {
          return '<li>' + esc(i.name) + (res.pest ? ' <span class="muted">— lettore degli insetti: ' + pct(i.p) + '</span>' : '') + '</li>';
        }).join('') + '</ul>';
        if (e.tipo === 'danno' || e.tipo === 'vettore') open = true;
        // difesa contro l'insetto più probabile, una sola volta (la prima malattia collegata)
        if (first) {
          var b = difesaBlock('pest', ins[0].label, crop, plantGuess);
          if (b) h += '<p class="muted">Difesa contro ' + esc(ins[0].name) + (ins.length > 1 ? ' (il più probabile tra quelli elencati: per gli altri apri il lettore degli insetti o i Consigli)' : '') + ':</p>' + b;
          first = false;
        }
      }
      h += '</div>';
    });
    if (h) h = '<section><h3>Collegamento con insetti e acari</h3>' + h + '<p class="muted">Per confermare cerca l\'insetto o l\'acaro sulla pianta (pagina inferiore delle foglie, germogli, frutti) e fotografalo da vicino: il lettore degli insetti lo riconosce meglio dell\'insetto che dei suoi danni.</p></section>';
    return { html: h, open: open };
  }
  // dal lettore degli insetti ai danni e alle malattie che quell'insetto causa o trasmette
  function pestLinks(label) {
    var L = DATA.danni || {}, R = DATA.readers.disease, by = { danno: [], vettore: [], melata: [] };
    Object.keys(L).forEach(function (d) {
      if (L[d].insetti.indexOf(label) < 0) return;
      var c = R.classes.filter(function (x) { return x.label === d; })[0];
      if (c && by[L[d].tipo].indexOf(c.name) < 0) by[L[d].tipo].push(c.name);
    });
    var s = '';
    if (by.danno.length) s += '<p><strong>Danni tipici</strong> (riconosciuti dal lettore delle malattie): ' + esc(by.danno.join('; ')) + '.</p>';
    if (by.vettore.length) s += '<p><strong>Trasmette:</strong> ' + esc(by.vettore.join('; ')) + '.</p>';
    if (by.melata.length) s += '<p><strong>Con la melata favorisce:</strong> ' + esc(by.melata.join('; ')) + '.</p>';
    return s;
  }

  // Lettore degli insetti: separato dagli altri, perché ha senso solo se la foto mostra un insetto.
  function pestBlock(probs, open) {
    var R = DATA.readers.pest;
    if (!R || !probs) return '';
    var t = top(probs, 3), ok = t[0][0] >= THRESHOLD;
    // Il lettore non sa dire se nella foto c'è un insetto: su una foglia sana risponde comunque.
    // Per questo resta chiuso, salvo quando i sintomi indicano insetti o acari.
    var h = '<details class="reader"' + (open ? ' open' : '') + '><summary><strong>Lettore di insetti e acari: ' + esc(ok ? R.classes[t[0][1]].name : 'non determinabile') +
      '</strong> <span class="muted">(solo se la foto mostra l\'insetto)</span></summary>' +
      '<p class="muted">Vale solo se la foto mostra un insetto o un acaro, non i suoi danni.</p>';
    var c0 = R.classes[t[0][1]];
    if (ok && c0.reg != null && DATA.lab) h += regNote(DATA.lab.organismi_regolamentati[c0.reg], t[0][0], 'Se la foto mostra davvero questo insetto: ');
    if (ok) h += pestLinks(c0.label) + difesaBlock('pest', c0.label, $('crop').value || null, null);
    t.forEach(function (x) {
      h += '<div class="cand"><div class="bar"><span style="width:' + (x[0] * 100).toFixed(1) + '%"></span><em>' + esc(R.classes[x[1]].name) + '</em></div><div class="p">' + pct(x[0]) + '</div></div>';
    });
    var lev = hypLevel('pest', '95');
    if (lev) h += hypHtml(hypSet(probs, lev), function (i) { return R.classes[i].name; }, lev, 95, 'Ipotesi');
    return h + '<p class="muted">Affidabilità sul test: ' + pct(R.test_accuracy) + '. Addestrato su IP102 (102 insetti dannosi di riso, frumento, mais, erba medica, vite, agrumi e mango, concesso per uso accademico) e, se il modello li comprende, sugli insetti e acari delle norme di difesa della Calabria con foto di iNaturalist (mosca delle olive, cocciniglie, aleurodidi...).</p></details>';
  }

  function top(probs, k) {
    return probs.map(function (p, i) { return [p, i]; }).sort(function (a, b) { return b[0] - a[0]; }).slice(0, k);
  }

  function render(res, secs) {
    var organ = $('organ').value, h = '<section class="card"><h2>Risultato dei lettori</h2>';
    var answers = {}, crop = res.crop, dset = null;
    HEADS.forEach(function (hd) {
      var R = DATA.readers[hd], t = top(res[hd], 3), best = R.classes[t[0][1]];
      var ok = t[0][0] >= THRESHOLD;
      if (hd === 'plant' && crop) {  // coltura indicata dall'utente: il lettore resta come confronto
        var mine = R.classes.filter(function (c) { return c.label === crop; })[0];
        answers.plant = mine || null;
        h += '<div class="reader"><h3>Coltura indicata da te: ' + esc(mine ? mine.name : crop) + '</h3><p class="muted">Il lettore della coltura direbbe: ' +
          esc(best.name) + ' (' + pct(t[0][0]) + '). Le malattie sono cercate solo tra quelle viste su questa coltura.</p></div>';
        return;
      }
      answers[hd] = ok ? best : null;
      h += '<div class="reader"><h3>' + esc(READER_LABELS[hd]) + ': ' + esc(ok ? best.name : 'non determinabile') + '</h3>';
      if (ok && hd !== 'deficiency') h += '<p>' + sureNote(hd, t[0][0], hd === 'disease' && crop) + '</p>';
      t.forEach(function (x) {
        var c = R.classes[x[1]];
        h += '<div class="cand"><div class="bar"><span style="width:' + (x[0] * 100).toFixed(1) + '%"></span><em>' + esc(c.name) + '</em></div><div class="p">' + pct(x[0]) + '</div></div>';
      });
      var lev = (hd === 'disease' || hd === 'plant') ? hypLevel(hd, hd === 'disease' ? '99' : '95', hd === 'disease' && crop) : null;
      if (lev) {
        var set = hypSet(res[hd], lev);
        if (hd === 'disease') dset = set;
        h += hypHtml(set, function (i) { return R.classes[i].name; }, lev, hd === 'disease' ? 99 : 95, 'Ipotesi');
      }
      var field = R.field && (R.field.plantdoc || R.field.inatag);
      h += '<p class="muted">Affidabilità sul test: ' + pct(R.test_accuracy) + (field ? '; su foto di campo: ' + pct(field.accuracy) : '') + '.</p></div>';
    });
    var cz = causeBlock(res.disease);
    answers.cause = cz.best;
    h += cz.html;
    var lk = linkBlock(res, crop, answers.plant && answers.plant.label);
    h += lk.html;
    h += pestBlock(res.pest, (cz.pests || 0) >= 0.3 || lk.open);
    // laboratorio: cause possibili, quante ipotesi, organismi regolamentati tra le malattie più probabili
    var l95 = hypLevel('disease', '95', crop), regs = regsIn('disease', (l95 ? hypSet(res.disease, l95) : top(res.disease, 1)).filter(function (x) { return x[0] >= 0.1; }));
    h += labBlock(cz.ids || [], dset ? dset.length : 1, regs);
    var cropNow = crop || (answers.plant && answers.plant.label);
    if (cropNow && organ) h += woodNote(cropNow, organ);
    var td = top(res.disease, 1)[0], dc = DATA.readers.disease.classes[td[1]];
    if (td[0] >= THRESHOLD && dc.cause !== 'sano') h += difesaBlock('disease', dc.label, crop, answers.plant && answers.plant.label);
    h += referto(answers, organ);
    h += '<p><button type="button" class="secondary" id="go-tank">Prepara la botte</button></p>';
    var unsure = HEADS.some(function (hd) { return !answers[hd]; });
    lastPred = {};
    HEADS.concat(res.pest ? ['pest'] : []).forEach(function (hd) { lastPred[hd] = top(res[hd], 3).map(function (x) { return { label: DATA.readers[hd].classes[x[1]].label, p: Math.round(x[0] * 1e4) / 1e4 }; }); });
    h += contribForm(unsure, answers);
    h += '<p class="muted">Analisi in ' + secs.toFixed(1) + ' s sul dispositivo. Strumento di supporto alla decisione: per virus, viroidi, batteri e nematodi serve la conferma di laboratorio.</p></section>';
    $('out').innerHTML = h;
    $('out').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('go-tank').addEventListener('click', function () { showTab('tank'); });
    if ($('go-tank2')) $('go-tank2').addEventListener('click', function (ev) { ev.preventDefault(); showTab('tank'); });
    wireConsLinks($('out'));
    wireContrib();
  }

  // ------------------------------------------------------------------ contributi per migliorare la rete
  var PROVINCES = ['', 'Reggio Calabria', 'Catanzaro', 'Cosenza', 'Crotone', 'Vibo Valentia', 'Agrigento', 'Caltanissetta',
    'Catania', 'Enna', 'Messina', 'Palermo', 'Ragusa', 'Siracusa', 'Trapani', 'Altra provincia'];
  function selectOf(id, head, chosen) {
    var o = '<option value="">Non so</option>';
    DATA.readers[head].classes.slice().sort(function (a, b) { return a.name.localeCompare(b.name, 'it'); }).forEach(function (c) {
      o += '<option value="' + esc(c.label) + '"' + (chosen && chosen.label === c.label ? ' selected' : '') + '>' + esc(c.name) + '</option>';
    });
    if (head === 'disease') o += '<option value="altro:non_in_elenco">Altro, non in elenco (scrivilo nelle note)</option>';
    return '<select id="' + id + '">' + o + '</select>';
  }
  function contribForm(unsure, answers) {
    var organ = $('organ').value;
    var org = '<option value="">Non indicato</option>' + DATA.organs.map(function (o) { return '<option value="' + esc(o.id) + '"' + (o.id === organ ? ' selected' : '') + '>' + esc(o.label) + '</option>'; }).join('');
    return '<details class="reader" id="cb"' + (unsure ? ' open' : '') + '><summary><strong>' +
      (unsure ? 'Risposta incerta: aiuta a migliorare la rete' : 'Il risultato è sbagliato? Aiuta a migliorare la rete') + '</strong></summary>' +
      '<p class="muted">Indica la risposta corretta. La foto resta nel telefono finché non invii i contributi dalla scheda Info.</p>' +
      '<label>Coltura' + selectOf('cb-plant', 'plant', answers.plant) + '</label>' +
      '<label>Malattia o danno' + selectOf('cb-disease', 'disease', answers.disease) + '</label>' +
      '<label>Stato nutrizionale' + selectOf('cb-def', 'deficiency', answers.deficiency) + '</label>' +
      '<div class="row"><label>Organo<select id="cb-organ">' + org + '</select></label>' +
      '<label>Provincia<select id="cb-prov">' + PROVINCES.map(function (p) { return '<option>' + esc(p) + '</option>'; }).join('') + '</select></label></div>' +
      '<label>Diagnosi confermata da<select id="cb-src"><option value="visual_only">Solo osservazione</option><option value="expert">Agronomo o tecnico</option><option value="lab">Analisi di laboratorio</option></select></label>' +
      '<label>Note <span class="muted">(senza dati personali)</span><textarea id="cb-note" rows="2" maxlength="300"></textarea></label>' +
      '<label style="display:flex;gap:8px;align-items:flex-start;margin-top:8px"><input type="checkbox" id="cb-ok" style="width:auto;margin-top:4px"> <span class="muted">Ho il consenso del titolare del campo, la foto non contiene persone, targhe o dati personali, e accetto che sia usata per addestrare la rete.</span></label>' +
      '<p><button type="button" id="cb-save">Salva contributo</button></p><p class="muted" id="cb-status"></p></details>';
  }
  function wireContrib() {
    $('cb-save').addEventListener('click', function () {
      if (!$('cb-ok').checked) { $('cb-status').textContent = 'Serve il consenso per salvare il contributo.'; return; }
      if (!lastPhoto) { $('cb-status').textContent = 'Nessuna foto da salvare.'; return; }
      var item = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), date: new Date().toISOString().slice(0, 10),
        photo: lastPhoto, predicted: lastPred,
        correct: { plant: $('cb-plant').value, disease: $('cb-disease').value, deficiency: $('cb-def').value },
        organ: $('cb-organ').value, province: $('cb-prov').value, diagnosis_source: $('cb-src').value, note: $('cb-note').value.trim() };
      dbPut(item).then(function () {
        $('cb-status').textContent = 'Contributo salvato. Invialo dalla scheda Info quando vuoi.'; $('cb-save').disabled = true; refreshCount();
      }).catch(function () { $('cb-status').textContent = 'Salvataggio non riuscito: memoria del browser non disponibile.'; });
    });
  }
  // archivio locale (IndexedDB)
  function db() {
    return new Promise(function (ok, ko) {
      var r = indexedDB.open('plantcare', 1);
      r.onupgradeneeded = function () { r.result.createObjectStore('contributi', { keyPath: 'id' }); };
      r.onsuccess = function () { ok(r.result); }; r.onerror = function () { ko(r.error); };
    });
  }
  function dbTx(mode, fn) {
    return db().then(function (d) {
      return new Promise(function (ok, ko) {
        var tx = d.transaction('contributi', mode), st = tx.objectStore('contributi'), out = fn(st);
        tx.oncomplete = function () { ok(out && out.result !== undefined ? out.result : out); }; tx.onerror = function () { ko(tx.error); };
      });
    });
  }
  function dbPut(item) { return dbTx('readwrite', function (st) { return st.put(item); }); }
  function dbAll() { return dbTx('readonly', function (st) { return st.getAll(); }); }
  function dbClear() { return dbTx('readwrite', function (st) { return st.clear(); }); }
  function refreshCount() {
    return dbAll().then(function (all) { var el = $('cb-count'); if (el) el.textContent = String(all.length); return all; }).catch(function () { return []; });
  }
  function exportContrib() {
    refreshCount().then(function (all) {
      if (!all.length) { $('cb-export-status').textContent = 'Nessun contributo da inviare.'; return; }
      var payload = { schema: 'plantcare-contributi/1', app_model: 'readers_dinov2+efficientnet_b0', created: new Date().toISOString(), items: all };
      var name = 'plantcare-contributi-' + new Date().toISOString().slice(0, 10) + '.json';
      var file = new File([JSON.stringify(payload)], name, { type: 'application/json' });
      var done = function () { $('cb-export-status').textContent = all.length + ' contributi pronti. Dopo l\'invio puoi svuotare l\'elenco.'; $('cb-clear').hidden = false; };
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ files: [file], title: 'Contributi PlantCare' }).then(done).catch(function () {});
      } else {
        var a = document.createElement('a'); a.href = URL.createObjectURL(file); a.download = name; document.body.appendChild(a); a.click(); a.remove(); done();
      }
    });
  }

  function wireInfo() {
    $('cb-export').addEventListener('click', exportContrib);
    $('cb-clear').addEventListener('click', function () {
      if (!confirm('Svuotare l\'elenco dei contributi già inviati?')) return;
      dbClear().then(function () { $('cb-clear').hidden = true; $('cb-export-status').textContent = 'Elenco svuotato.'; refreshCount(); });
    });
    refreshCount();
  }

  function referto(a, organ) {
    var s = '<div class="reader"><h3>Referto</h3>';
    if (a.plant) s += '<p><strong>Coltura:</strong> ' + esc(a.plant.name) + '</p>';
    var d = a.disease, card = d && d.card;
    if (d) s += '<p><strong>Malattia o danno:</strong> ' + esc(d.name) + (card && card.agent ? ' (<em>' + esc(card.agent) + '</em>)' : '') + '</p>';
    if (a.cause && a.cause.id !== 'sano') s += '<p><strong>Causa probabile dei sintomi:</strong> ' + esc(a.cause.name) + ' (' + pct(a.cause.p) + ')</p>';
    if (a.deficiency) s += '<p><strong>Stato nutrizionale:</strong> ' + esc(a.deficiency.name) + '</p>';
    if (card) {
      var k = card.knowledge;
      if (k && k.cause) s += '<p><strong>Causa:</strong> ' + esc(k.cause) + '</p>';
      if (k && k.vectors && k.vectors.length) s += '<p><strong>Provocata da:</strong> ' + esc(k.vectors.map(function (v) { return v.name; }).join(', ')) + '</p>';
      else if (card.pathogen_type && card.pathogen_type.id !== 'healthy') s += '<p><strong>Tipo di agente:</strong> ' + esc(card.pathogen_type.label) + '</p>';
      if (card.symptoms) s += '<p class="muted">Sintomi: ' + esc(card.symptoms) + '</p>';
      if (organ && card.organs && card.organs.length && card.pathogen_type.id !== 'healthy') {
        var ids = card.organs.map(function (o) { return o.id; });
        if (ids.indexOf(organ) < 0) s += '<div class="warn">Questa malattia è descritta su: ' + esc(card.organs.map(function (o) { return o.label; }).join(', ')) + '. Sull\'organo indicato la diagnosi è meno probabile.</div>';
        else if (card.organ_symptoms && card.organ_symptoms[organ]) s += '<p class="muted">Su questo organo: ' + esc(card.organ_symptoms[organ]) + '</p>';
      }
      if (k && k.management && k.management.length) {
        s += '<p><strong>Misure (' + (k.sources_verified ? 'fonti verificate' : 'fonti parziali') + '):</strong></p><ul>';
        k.management.forEach(function (m) { s += '<li>' + esc(m.text) + '</li>'; });
        s += '</ul>';
        if (k.sources && k.sources.length) s += '<p class="muted">Fonti: ' + k.sources.map(function (x) { return '<a href="' + esc(x.url) + '" target="_blank" rel="noopener">' + esc(x.title) + '</a>'; }).join(' · ') + '</p>';
      } else if (card.pathogen_type && card.pathogen_type.id === 'healthy') {
        s += '<p>Nessun intervento necessario.</p>';
      } else {
        s += '<p class="muted">Misure: da completare con il tecnico.</p>';
      }
      if (card.lab_note) s += '<div class="warn lab">' + esc(card.lab_note) + '</div>';
    }
    if (!a.plant || !a.disease) s += '<div class="warn">Per uno o più lettori la confidenza è insufficiente: serve una foto più nitida, ravvicinata e a fuoco.</div>';
    return s + '</div>';
  }

  // ------------------------------------------------------------------ fotocamera e file
  $('cam-start').addEventListener('click', function () {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false })
      .then(function (st) {
        stream = st; var v = $('video');
        v.setAttribute('playsinline', ''); v.muted = true; v.srcObject = st; v.hidden = false;
        $('cam-stop').disabled = false;
        $('cam-status').textContent = 'Avvio della fotocamera…';
        // su iPhone e su alcuni Android il video non parte da solo: senza immagini lo scatto resterebbe vuoto
        var pronto = function () {
          if (!v.videoWidth) return;
          $('cam-shot').disabled = false;
          $('cam-status').textContent = 'Inquadra la parte colpita al centro e premi "Scatta e analizza".';
        };
        v.onloadedmetadata = pronto; v.onplaying = pronto;
        var p = v.play(); if (p && p.catch) p.catch(function () {});
        setTimeout(function () {
          if (stream === st && !v.videoWidth)
            $('cam-status').textContent = 'La fotocamera non manda immagini: usa "Scatta con la fotocamera del telefono".';
        }, 4000);
        ready.then(loadModel).catch(function () {});  // scarica il modello mentre si inquadra
      })
      .catch(function () { $('cam-status').textContent = 'Fotocamera non disponibile o permesso negato: usa "Scatta con la fotocamera del telefono" o una foto dalla galleria.'; });
  });
  $('cam-stop').addEventListener('click', function () {
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null; $('video').hidden = true; $('cam-shot').disabled = true; $('cam-stop').disabled = true; $('cam-status').textContent = '';
  });
  $('cam-shot').addEventListener('click', function () {
    var v = $('video'), w = v.videoWidth, h = v.videoHeight, c = document.createElement('canvas');
    if (!w || !h) {
      $('cam-status').textContent = 'La fotocamera non è ancora pronta: attendi un secondo o usa "Scatta con la fotocamera del telefono".';
      return;
    }
    c.width = w; c.height = h; c.getContext('2d').drawImage(v, 0, 0, w, h);
    // si spegne la fotocamera: la foto scattata resta sotto, con il quadrato da spostare
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null; v.hidden = true; $('cam-shot').disabled = true; $('cam-stop').disabled = true;
    $('cam-status').textContent = 'Foto scattata: il risultato compare qui sotto.';
    showPicker(c, w, h, c.toDataURL('image/jpeg', 0.9));
    analyze(c, w, h);
  });
  function fromFile(input) {
    var f = input.files[0]; if (!f) return;
    var url = URL.createObjectURL(f), img = new Image();
    img.onload = function () {
      showPicker(img, img.naturalWidth, img.naturalHeight, url);
      analyze(img, img.naturalWidth, img.naturalHeight);
    };
    img.onerror = function () { $('cam-status').textContent = 'Formato della foto non leggibile: prova a scattarla di nuovo o a sceglierla in JPEG.'; };
    img.src = url;
    input.value = '';  // la stessa foto si può scegliere di nuovo
  }
  $('file').addEventListener('change', function () { fromFile($('file')); });
  $('file-cam').addEventListener('change', function () { fromFile($('file-cam')); });

  // ------------------------------------------------------------------ zona da analizzare
  // Con più foglie, sfondo o terreno nella foto il lettore sbaglia di più: l'utente sposta il
  // quadrato sulla parte colpita (trascinandolo) e lo rimpicciolisce con il cursore.
  var pick = null;
  function placeSquare() {
    var q = $('pick-sq'); if (!q || !pick) return;
    q.style.left = (pick.x / pick.w * 100) + '%'; q.style.top = (pick.y / pick.h * 100) + '%';
    q.style.width = (pick.s / pick.w * 100) + '%'; q.style.height = (pick.s / pick.h * 100) + '%';
  }
  function clampSquare() {
    pick.x = Math.min(Math.max(pick.x, 0), pick.w - pick.s);
    pick.y = Math.min(Math.max(pick.y, 0), pick.h - pick.s);
  }
  function showPicker(source, w, h, url) {
    var s = Math.min(w, h);
    pick = { source: source, w: w, h: h, s: s, x: (w - s) / 2, y: (h - s) / 2 };
    $('preview').innerHTML = '<div class="pick" id="pick" style="max-width:' + Math.round(400 * w / h) + 'px">' +
      '<img alt="Foto scelta" src="' + url + '"><div class="sq" id="pick-sq" role="presentation"></div></div>' +
      '<label class="muted" for="pick-size">Viene analizzata la zona nel quadrato. Con più foglie o sfondo, trascina il quadrato sulla parte colpita e rimpiccioliscilo:</label>' +
      '<input id="pick-size" type="range" min="15" max="100" value="100" aria-label="Dimensione del quadrato">' +
      '<div class="row"><button type="button" id="pick-go">Analizza la zona scelta</button></div>';
    placeSquare();
    var sq = $('pick-sq'), box = $('pick'), drag = null;
    sq.addEventListener('pointerdown', function (e) {
      drag = { x: e.clientX, y: e.clientY, px: pick.x, py: pick.y }; sq.setPointerCapture(e.pointerId); e.preventDefault();
    });
    sq.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var k = pick.w / box.clientWidth;  // pixel dello schermo -> pixel della foto
      pick.x = drag.px + (e.clientX - drag.x) * k; pick.y = drag.py + (e.clientY - drag.y) * k;
      clampSquare(); placeSquare();
    });
    sq.addEventListener('pointerup', function () { drag = null; });
    sq.addEventListener('pointercancel', function () { drag = null; });
    $('pick-size').addEventListener('input', function () {
      var cx = pick.x + pick.s / 2, cy = pick.y + pick.s / 2;
      pick.s = Math.min(w, h) * $('pick-size').value / 100;
      pick.x = cx - pick.s / 2; pick.y = cy - pick.s / 2; clampSquare(); placeSquare();
    });
    $('pick-go').addEventListener('click', function () {
      analyze(pick.source, pick.w, pick.h, { x: pick.x, y: pick.y, s: pick.s });
    });
  }

  // ------------------------------------------------------------------ quiz
  var qCur = null, score = { ok: 0, tot: 0 };
  function nameOf(head, label) {
    return classOf(head, label).name;
  }
  var SEEN_KEY = 'plantcare-quiz-viste';
  function quizSeen() { try { return JSON.parse(localStorage.getItem(SEEN_KEY) || '{}') || {}; } catch (e) { return {}; } }
  function quizSeenSave(o) { try { localStorage.setItem(SEEN_KEY, JSON.stringify(o)); } catch (e) { /* senza memoria si va avanti lo stesso */ } }
  function shuffle(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  $('q-new').addEventListener('click', nextQuestion);
  // argomenti sbagliati: tornano più spesso finché non si risponde giusto (memoria nel telefono)
  var ERR_KEY = 'plantcare-quiz-errori';
  function quizErrors() { try { return JSON.parse(localStorage.getItem(ERR_KEY) || '{}') || {}; } catch (e) { return {}; } }
  function quizErrorsSave(o) { try { localStorage.setItem(ERR_KEY, JSON.stringify(o)); } catch (e) { /* senza memoria si va avanti */ } }
  function pickWeighted(list, w) {
    var tot = list.reduce(function (a, x) { return a + w(x); }, 0), r = Math.random() * tot;
    for (var i = 0; i < list.length; i++) { r -= w(list[i]); if (r <= 0) return list[i]; }
    return list[list.length - 1];
  }
  function nextQuestion() {
    ready.then(function () {
      var cat = $('q-cat').value;
      var pool = DATA.quiz.filter(function (q) {
        if (cat === 'organ') return q.organ && q.organ !== 'leaf';
        if (cat === 'cal') return q.cal || q.sud;
        return cat === 'any' || q.head === cat;
      });
      if (!pool.length) { $('q-text').textContent = 'Nessuna foto per questa categoria.'; $('q-box').hidden = false; return; }
      // foto non ancora viste per prime; quando sono finite si ricomincia
      var seen = quizSeen(), fresh = pool.filter(function (q) { return !seen[q.img]; });
      if (!fresh.length) { pool.forEach(function (q) { delete seen[q.img]; }); fresh = pool; }
      // 4 domande su 10 di ripasso se ci sono errori; delle altre, 7 su 10 su colture, malattie e insetti tipici del
      // Sud e della Calabria, 2 su 10 su quelli del Disciplinare calabrese, 1 su 10 sul resto. Dentro ogni gruppo si
      // sceglie prima la specie e poi la foto, così compaiono tutte le specie e non solo quelle con più foto.
      var errs = quizErrors(), review = false, item = null;
      var wrong = pool.filter(function (q) { return errs[q.head + '|' + q.label]; });
      if (wrong.length && Math.random() < 0.4) {
        var wf = wrong.filter(function (q) { return !seen[q.img]; });
        item = pickWeighted(wf.length ? wf : wrong, function (q) { return errs[q.head + '|' + q.label]; });
        review = true;
      } else {
        var tiers = [fresh.filter(function (q) { return q.sud; }), fresh.filter(function (q) { return q.cal && !q.sud; }),
                     fresh.filter(function (q) { return !q.cal && !q.sud; })];
        var probs = [0.7, 0.2, 0.1], r = Math.random(), src = null;
        for (var t = 0; t < 3; t++) { if (tiers[t].length && r < probs[t]) { src = tiers[t]; break; } r -= probs[t]; }
        if (!src) src = tiers.filter(function (x) { return x.length; })[0];
        var byClass = {};
        src.forEach(function (q) { (byClass[q.head + '|' + q.label] = byClass[q.head + '|' + q.label] || []).push(q); });
        var keys = Object.keys(byClass), list = byClass[keys[Math.floor(Math.random() * keys.length)]];
        item = list[Math.floor(Math.random() * list.length)];
      }
      seen[item.img] = 1; quizSeenSave(seen);
      var labels = {};
      DATA.quiz.forEach(function (q) { if (q.head === item.head) labels[q.label] = q.plant; });
      var others = Object.keys(labels).filter(function (l) { return l !== item.label; });
      if (item.head === 'disease' || item.head === 'pest') {
        var same = others.filter(function (l) { return labels[l] === item.plant; });
        if (same.length >= 3) others = same;
      }
      var opts = [item.label], seen = {}; seen[nameOf(item.head, item.label)] = true;
      shuffle(others).forEach(function (l) {
        var n = nameOf(item.head, l);
        if (opts.length < 4 && !seen[n]) { opts.push(l); seen[n] = true; }
      });
      if (opts.length < 4) { $('q-text').textContent = 'Classi insufficienti: scegli un\'altra categoria.'; return; }
      qCur = { item: item, opts: shuffle(opts) };
      var questions = { plant: 'Quale coltura è?', disease: 'Quale malattia o danno si vede?', deficiency: 'Che disturbo nutrizionale si vede?', pest: 'Quale insetto o acaro è?' };
      var organ = item.organ && DATA.organs.filter(function (o) { return o.id === item.organ; })[0];
      $('q-text').textContent = (review ? 'Ripasso, l\'ultima volta qui hai sbagliato. ' : '') + (item.danno ? 'Di quale insetto o acaro è questo danno?' : questions[item.head]) + (organ ? ' (parte della pianta: ' + organ.label.toLowerCase() + ')' : '');
      $('q-img').src = 'app/quiz/' + item.img;
      $('q-credit').innerHTML = 'Foto: ' + esc(item.credit) + (item.obs ? ' (<a href="' + esc(item.obs) + '" target="_blank" rel="noopener">fonte</a>)' : '');
      $('q-exp').innerHTML = '';
      var box = $('q-opts'); box.innerHTML = '';
      qCur.opts.forEach(function (l) {
        var b = document.createElement('button'); b.type = 'button'; b.textContent = nameOf(item.head, l);
        b.addEventListener('click', function () { answer(l, b); });
        box.appendChild(b);
      });
      $('q-box').hidden = false;
      $('q-text').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
  // Scheda in sintesi dopo la risposta (malattie e insetti): cos'è, gruppo, colture, causa, se serve il
  // laboratorio, se è regolamentato, dove compare nelle norme di difesa della Calabria. Solo dati con fonte.
  function quizSummary(item) {
    var c = classOf(item.head, item.label), s = item.sum || {}, lines = [], cn = DATA.causes || {};
    var kindOf = function (cl) { return cl === 'Insecta' ? 'insetto' : cl === 'Arachnida' ? 'acaro' : null; };
    if (s.name) lines.push('<em>' + esc(s.name) + '</em>' + (s.ordine ? ', ordine ' + esc(s.ordine) : '') + (s.famiglia ? ', famiglia ' + esc(s.famiglia) : '') +
      (kindOf(s.classe) ? ' (' + kindOf(s.classe) + ')' : '') + '.');
    var cause = s.causa || c.cause;
    if (cause && cn[cause] && cause !== 'non_specificato') lines.push('Causa: ' + esc(cn[cause]).toLowerCase() + '.');
    if (c.card && c.card.agent) lines.push('Agente: <em>' + esc(c.card.agent) + '</em>.');
    if (c.crops && c.crops.length) {
      var pn = c.crops.map(function (k) { var p = DATA.readers.plant.classes.filter(function (x) { return x.label === k; })[0]; return p ? p.name : null; }).filter(Boolean);
      if (pn.length) lines.push('Colture su cui l\'abbiamo in foto: ' + esc(pn.slice(0, 6).join(', ')) + '.');
    }
    if (c.group && item.head === 'pest' && !s.name) lines.push('Insetto dannoso di ' + esc(c.group) + ' nel dataset IP102.');
    if (c.card && c.card.organs && c.card.organs.length) lines.push('Organi colpiti: ' + esc(c.card.organs.map(function (o) { return o.label; }).join(', ')) + '.');
    var A = DATA.lab && DATA.lab.analisi_per_causa[cause];
    if (A && A.quando === 'sempre') lines.push('Conferma: ' + esc(A.testo));
    if (c.reg != null && DATA.lab) { var o = DATA.lab.organismi_regolamentati[c.reg]; lines.push('<strong>' + esc(o.ue) + '</strong> (EPPO: ' + esc(o.lista_eppo) + ').'); }
    var disc = s.disciplinare || [];
    var D = DATA.difesa, e = D && D.classi[item.head + '|' + item.label];
    if (!disc.length && e) Object.keys(e).forEach(function (k) { e[k].r.forEach(function (i) { var r = D.righe[i]; disc.push(r.coltura.charAt(0) + r.coltura.slice(1).toLowerCase() + ': ' + r.avversita); }); });
    if (disc.length) lines.push('Nelle norme di difesa integrata della Regione Calabria: ' + esc(disc.filter(function (x, i) { return disc.indexOf(x) === i; }).slice(0, 4).join('; ')) + '.');
    else if (!item.cal) lines.push('Non compare nelle norme di difesa della Calabria.');
    return lines.length ? '<div class="hyp"><p><strong>In sintesi:</strong></p><p class="muted">' + lines.join('<br>') + '</p></div>' : '';
  }
  // classe del lettore se presente, altrimenti dati della foto del quiz (es. insetti IP102)
  function classOf(head, label) {
    var R = DATA.readers[head], c = R && R.classes.filter(function (x) { return x.label === label; })[0];
    if (c) return c;
    var q = DATA.quiz.filter(function (x) { return x.head === head && x.label === label; })[0];
    return q ? { label: label, name: q.name || label, group: q.plant } : { label: label, name: label };
  }
  function symptomsOf(c) {
    var card = c.card;
    return card ? (card.symptoms || (card.knowledge && card.knowledge.cause) || '') : '';
  }
  // Perché la risposta scelta è sbagliata: differenza specifica se nota, altrimenti sintomi e causa a confronto.
  function explainWrong(head, label, choice) {
    var T = DATA.quizTips || {}, good = classOf(head, label), bad = classOf(head, choice), h = '<p><strong>Perché no:</strong> ';
    if (head === 'plant') {
      h += 'la foto mostra ' + esc(good.name) + (good.family ? ' (famiglia ' + esc(good.family) + ')' : '') + ', non ' + esc(bad.name) +
        (bad.family ? ' (famiglia ' + esc(bad.family) + ')' : '') + '.';
      if (good.family && bad.family && good.family === bad.family) h += ' Sono della stessa famiglia: guarda la forma e il margine della foglia, la nervatura e il portamento.';
      return h + '</p>';
    }
    if (head === 'pest') {
      h += 'hai scelto ' + esc(bad.name) + ', ma è ' + esc(good.name) + '.</p>';
      if (good.group && bad.group && good.group !== bad.group) h += '<p class="muted">' + esc(good.name) + ' è un fitofago tipico di ' + esc(good.group) + '; ' + esc(bad.name) + ' invece di ' + esc(bad.group) + '.</p>';
      else if (good.group) h += '<p class="muted">Sono entrambi fitofagi di ' + esc(good.group) + ': confronta forma del corpo, colore, ali, antenne e zampe, e lo stadio (larva, ninfa o adulto).</p>';
      return h;
    }
    if (head === 'deficiency') {
      var d = T.deficiencies || {};
      h += 'hai scelto ' + esc(bad.name) + ', ma è ' + esc(good.name) + '.</p>';
      if (d[label]) h += '<p class="muted">' + esc(d[label]) + '</p>';
      if (d[choice]) h += '<p class="muted">Invece: ' + esc(d[choice]) + '</p>';
      return h;
    }
    h += 'hai scelto ' + esc(bad.name) + ', ma è ' + esc(good.name) + '.</p>';
    var pair = (T.pairs || []).filter(function (p) { return p.labels.indexOf(label) >= 0 && p.labels.indexOf(choice) >= 0; })[0];
    if (pair) h += '<p><strong>Come distinguerle:</strong> ' + esc(pair.tip) + '</p>';
    var cn = DATA.causes || {};
    if (bad.cause === 'sano') {
      h += '<p><strong>La pianta non è sana.</strong> ' + esc((T.cause_tips || {})[good.cause] || 'Guarda macchie, ingiallimenti, deformazioni e appassimenti.') + '</p>';
    } else if (good.cause === 'sano') {
      h += '<p><strong>La pianta è sana:</strong> non ci sono macchie, muffe, fori, ingiallimenti o deformazioni. Piccole differenze di colore o riflessi della luce non sono sintomi.</p>';
    } else if (good.cause && bad.cause && good.cause !== bad.cause && good.cause !== 'non_specificato' && bad.cause !== 'non_specificato') {
      h += '<p><strong>La causa è diversa:</strong> ' + esc(cn[good.cause] || good.cause) + ', non ' + esc(cn[bad.cause] || bad.cause) + '.</p>';
      var ct = (T.cause_tips || {})[good.cause];
      if (ct) h += '<p class="muted">' + esc(ct) + '</p>';
    } else if (good.cause && good.cause !== 'non_specificato') {
      h += '<p><strong>Causa:</strong> ' + esc(cn[good.cause] || good.cause) + '.</p>';
      var ct2 = (T.cause_tips || {})[good.cause];
      if (ct2) h += '<p class="muted">' + esc(ct2) + '</p>';
    }
    var start = h;
    if (!pair) {
      var sg = symptomsOf(good), sb = symptomsOf(bad);
      if (sg) h += '<p class="muted">' + esc(good.name) + ': ' + esc(sg) + '</p>';
      if (sb) h += '<p class="muted">' + esc(bad.name) + ': ' + esc(sb) + '</p>';
    }
    if (h.indexOf('<p', h.indexOf('</p>')) < 0) h += '<p class="muted">Gli autori del dataset hanno classificato questa foto come ' + esc(good.name) + '. Guarda di nuovo la foto: forma, colore e distribuzione dei sintomi sono quelli tipici di questa classe.</p>';
    return h;
  }
  function answer(choice) {
    if (!qCur) return;
    var q = qCur; qCur = null;
    var right = choice === q.item.label;
    Array.prototype.forEach.call($('q-opts').children, function (b, i) {
      b.disabled = true;
      if (q.opts[i] === q.item.label) b.classList.add('ok'); else if (q.opts[i] === choice) b.classList.add('ko');
    });
    score.tot++; if (right) score.ok++;
    var errs = quizErrors(), ek = q.item.head + '|' + q.item.label;
    if (right) { if (errs[ek]) { errs[ek]--; if (errs[ek] <= 0) delete errs[ek]; } } else { errs[ek] = Math.min(5, (errs[ek] || 0) + 2); }
    quizErrorsSave(errs);
    $('q-score').textContent = 'Punteggio: ' + score.ok + ' su ' + score.tot;
    var h = '<div class="reader"><p><strong>' + (right ? 'Corretto!' : 'Sbagliato.') + '</strong> Risposta: ' + esc(nameOf(q.item.head, q.item.label)) + '</p>';
    if (q.item.head === 'disease') {
      var c = DATA.readers.disease.classes.filter(function (x) { return x.label === q.item.label; })[0];
      var card = c && c.card;
      if (card) h += '<p class="muted">' + esc((card.knowledge && card.knowledge.cause) || card.symptoms) + '</p>';
    } else if (q.item.head === 'deficiency') {
      h += '<p class="muted">Etichetta degli autori del dataset; la conferma richiede l\'analisi fogliare.</p>';
    }
    var qc = classOf(q.item.head, q.item.label);
    if ((q.item.head === 'disease' && qc.cause !== 'sano') || q.item.head === 'pest') h += quizSummary(q.item);
    if (!right) h += explainWrong(q.item.head, q.item.label, choice);
    var nErr = Object.keys(quizErrors()).length;
    if (nErr) h += '<p class="muted">Argomenti da ripassare: ' + nErr + '. Torneranno più spesso finché non rispondi giusto.</p>';
    h += '<p><button type="button" id="q-next">Domanda successiva &rarr;</button></p>';
    $('q-exp').innerHTML = h + '</div>';
    $('q-next').addEventListener('click', nextQuestion);
  }

  // ------------------------------------------------------------------ consigli
  var csInit = false, csPending = null;
  function initConsigli() {
    if (!CS) return;
    if (!csInit) {
      csInit = true;
      var cat = DATA.cat, byName = function (a, b) { return a.nome.localeCompare(b.nome, 'it'); };
      var cal = cat.colture.filter(function (c) { return c.sezioni.length; }).sort(byName);
      var alt = cat.colture.filter(function (c) { return !c.sezioni.length; }).sort(byName);
      $('cs-crop').innerHTML = '<option value="">Scegli la coltura</option>' +
        '<optgroup label="Colture del Disciplinare della Calabria">' + cal.map(function (c) { return opt(c.nome, c.nome); }).join('') + '</optgroup>' +
        '<optgroup label="Altre colture con prodotti Gowan registrati">' + alt.map(function (c) { return opt(c.nome, c.nome); }).join('') + '</optgroup>';
      $('cs-crop').disabled = false;
      $('cs-last').innerHTML = '<option value="">Nessuno o non so</option>' + cat.prodotti.filter(function (p) { return p.codici && p.codici.length; })
        .map(function (p) { return opt(p.nome, p.nome + ' (' + p.codici.join(' + ') + ')'); }).join('');
      $('cs-status').textContent = 'Catalogo Gowan: ' + cat.prodotti.length + ' prodotti e ' + cat.usi.length + ' usi registrati. ' + normeText();
      $('cs-crop').addEventListener('change', function () { csCrop(); });
      $('cs-adv').addEventListener('change', function () { csAdv(); });
      ['cs-phase', 'cs-sit'].forEach(function (id) { $(id).addEventListener('change', csReady); });
      $('cs-go').addEventListener('click', function () { csRun(null); });
    }
    if (csPending) { var p = csPending; csPending = null; $('cs-crop').value = p.c; csCrop(); $('cs-adv').value = p.a; csAdv(); }
  }
  function openConsigli(crop, adv) { csPending = { c: crop, a: adv }; showTab('consigli'); }
  function csCrop() {
    var crop = $('cs-crop').value, adv = $('cs-adv'), ph = $('cs-phase');
    $('cs-out').innerHTML = '';
    if (!crop) { adv.disabled = ph.disabled = $('cs-sit').disabled = true; csReady(); return; }
    var list = Consigli.avversita(CS, crop), c = CS.cat.colture[CS.colture[crop].i];
    var grp = function (t) {
      return list.filter(function (e) { return e.t === t; }).map(function (e) {
        return opt(e.id, e.nome + (e.u.length ? '' : ' — nessun prodotto Gowan registrato'));
      }).join('');
    };
    adv.innerHTML = '<option value="">Scegli la malattia o il parassita</option><optgroup label="Malattie (funghi, batteri, virus)">' + grp('malattia') +
      '</optgroup><optgroup label="Insetti, acari e altri parassiti">' + grp('insetto') + '</optgroup>';
    adv.disabled = false;
    ph.innerHTML = '<option value="">Scegli la fase</option>' + Consigli.fasi(CS, crop).map(function (f) {
      return opt(f.id, (f.n ? f.n + '. ' : '') + f.nome + (f.bbch ? ' (BBCH ' + f.bbch[0] + (f.bbch[1] !== f.bbch[0] ? '-' + f.bbch[1] : '') + ')' : ''));
    }).join('');
    ph.disabled = false;
    $('cs-disc').disabled = !c.sezioni.length;
    $('cs-disc').parentNode.title = c.sezioni.length ? '' : 'Il Disciplinare della Calabria non tratta questa coltura';
    csAdv();
  }
  function csAdv() {
    var crop = $('cs-crop').value, id = $('cs-adv').value, sit = $('cs-sit');
    if (!crop || !id) { sit.disabled = true; sit.innerHTML = ''; csReady(); return; }
    var e = Consigli.avversita(CS, crop).filter(function (x) { return x.id === id; })[0];
    sit.innerHTML = Consigli.situazioni(CS, e.t).map(function (x) { return opt(x.id, x.nome); }).join('');
    sit.disabled = false;
    csReady();
  }
  function csReady() { $('cs-go').disabled = !($('cs-crop').value && $('cs-adv').value && $('cs-phase').value && $('cs-sit').value); }
  function csQuery() {
    return { coltura: $('cs-crop').value, avversita: $('cs-adv').value, fase: $('cs-phase').value, situazione: $('cs-sit').value,
             ambito: $('cs-amb').value, giorni: num($('cs-days').value), bio: $('cs-bio').checked,
             disciplinare: $('cs-disc').checked && !$('cs-disc').disabled, ultimo: $('cs-last').value || null, obiettivo: $('cs-goal').value || null };
  }
  function rangeTxt(r) { return r[0] === r[1] ? String(r[0]) : r[0] + '-' + r[1]; }
  function bbchTxt(w) { return w.map(function (x) { return x[0] + '-' + (x[1] === 99 ? 'raccolta' : x[1]); }).join(' e '); }
  var DOSE_MODO = { min: 'dose minima dell\'etichetta, per la prevenzione', media: 'dose intermedia dell\'etichetta', max: 'dose massima dell\'etichetta, per l\'attacco in corso' };
  function ueTxt(p) {
    return Object.keys(p.ue || {}).map(function (k) {
      var e = p.ue[k];
      return e.nome + ': ' + (e.stato === 'Approved' ? 'approvata' + (e.scadenza ? ' fino al ' + e.scadenza : '') : e.stato === 'Not approved' ? 'NON approvata' : 'in valutazione') +
        (e.candidata_sostituzione ? ', candidata alla sostituzione' : '') + (e.basso_rischio ? ', a basso rischio' : '');
    }).join('; ');
  }
  function srcLinksIds(ids) {
    return (ids || []).filter(function (s) { return DATA.sources[s]; }).map(function (s) {
      return '<a href="' + esc(DATA.sources[s].url) + '" target="_blank" rel="noopener">' + esc(DATA.sources[s].title) + '</a>';
    }).join(' · ');
  }
  function productCard(rc, s, opz, main) {
    var p = rc.prodotto, d = rc.dose;
    var x = '<div class="' + (main ? 'pick-card' : 'alt-card') + '">';
    x += '<p class="' + (main ? 'big' : '') + '">' + (main ? '1ª scelta: ' : '') + '<strong><a href="' + esc(p.pagina) + '" target="_blank" rel="noopener">' + esc(p.nome) + '</a></strong>' +
      (p.bio ? '<span class="badge">BIO</span>' : '') + '</p>';
    x += '<p class="muted">' + esc(p.tipo || '') + (p.composizione ? ' — ' + esc(p.composizione) : '') + (p.codici && p.codici.length ? ' · gruppo ' + esc(p.codici.join(' + ')) : '') + '</p>';
    var pos = s.motivi.filter(function (m) { return m.peso > 0; }), neg = s.motivi.filter(function (m) { return m.peso < 0; });
    if (pos.length || neg.length) x += '<ul class="why">' + pos.map(function (m) { return '<li>✓ ' + esc(m.testo) + '</li>'; }).join('') +
      neg.map(function (m) { return '<li>⚠ ' + esc(m.testo) + '</li>'; }).join('') + '</ul>';
    x += '<div class="dose-box"><p><strong>Dose:</strong> ' + [d.per_hl ? '<strong>' + esc(fmtQ(d.per_hl)) + '</strong> per ettolitro' : null,
      d.per_ha ? '<strong>' + esc(fmtQ(d.per_ha)) + '</strong> per ettaro' : null].filter(Boolean).join(' · ') + '</p>';
    x += '<p class="muted">' + esc(DOSE_MODO[d.modo] || '') + '. In etichetta: ' + esc([d.etichetta_hl, d.etichetta_ha].filter(Boolean).join(' · ').replace(/\./g, ',')) + '.</p>';
    if (d.totale) x += '<p>Per ' + esc(fmtN(opz.ettari)) + ' ha servono <strong>' + esc(fmtQ(d.totale)) + '</strong> di prodotto.</p>';
    if (d.botte) x += '<p>In una botte da ' + esc(opz.botte) + ' l: <strong>' + esc(fmtQ(d.botte)) + '</strong>' + (d.botte_ettari ? ' (una botte tratta ' + esc(fmtN(d.botte_ettari)) + ' ha)' : '') + '.</p>';
    if (rc.acqua_etichetta) x += '<p class="muted">L\'etichetta indica ' + rangeTxt(rc.acqua_etichetta) + ' l/ha di acqua.</p>';
    x += '</div>';
    var t = [];
    if (rc.n_max) t.push('al massimo ' + rc.n_max + ' trattamenti');
    else if (rc.n_tipico) t.push(rangeTxt(rc.n_tipico) + ' trattamenti');
    if (rc.intervallo) t.push('ogni ' + rangeTxt(rc.intervallo) + ' giorni');
    if (rc.phi != null) t.push('intervallo di sicurezza ' + (rc.phi === 0 ? 'non necessario' : rc.phi + ' giorni'));
    if (rc.phi_fase) t.push(rc.phi_fase);
    if (rc.bbch) t.push('stadi BBCH ' + bbchTxt(rc.bbch));
    if (t.length) x += '<p><strong>Dall\'etichetta:</strong> ' + esc(t.join('; ')) + '.</p>';
    if (rc.dose_nota) x += '<p class="muted">Etichetta: «' + esc(rc.dose_nota) + '»</p>';
    rc.disciplinare.forEach(function (dd) { if (dd.limiti.length) x += '<p><strong>Disciplinare:</strong> ' + esc(dd.sostanza) + ': ' + esc(dd.limiti.join('; ')) + '.</p>'; });
    if (rc.rame_kg_ha != null) x += '<p>Rame metallo: <strong>' + esc(fmtN(rc.rame_kg_ha)) + ' kg/ha</strong> per trattamento. ' + esc(rc.rame_limite || '') + '</p>';
    if (p.api) x += '<p class="muted">Api: «' + esc(p.api) + '» (etichetta)</p>';
    var ue = ueTxt(p);
    if (ue) x += '<p class="muted">Banca dati UE: ' + esc(ue) + '.</p>';
    s.avvisi.concat(rc.avvisi).forEach(function (a) { x += '<div class="warn">' + esc(a) + '</div>'; });
    x += '<details><summary>Uso registrato, nota d\'etichetta e miscele</summary><p><strong>Uso registrato:</strong> ' + esc(rc.registrato) + ' (' + esc(rc.uso.s === 'serra' ? 'in serra' : 'in pieno campo') + ').</p>' +
      (rc.nota ? '<p class="muted">' + esc(rc.nota) + '</p>' : '') + (p.compatibilita ? '<p><strong>Miscele:</strong> ' + esc(p.compatibilita) + '</p>' : '') +
      (p.etichetta ? '<p class="muted"><a href="' + esc(p.etichetta) + '" target="_blank" rel="noopener">Etichetta</a>' + (p.etichetta_validita ? ': ' + esc(p.etichetta_validita) : '') + '</p>' : '') + '</details>';
    x += main ? '<div class="row"><button type="button" id="cs-tank-go">Porta nella botte</button></div>'
              : '<p><button type="button" class="secondary cs-use" data-p="' + esc(p.nome) + '">Ricetta con questo prodotto</button></p>';
    return x + '</div>';
  }
  function csRun(pick) {
    var q = csQuery(), res;
    try { res = Consigli.ordina(CS, q); } catch (e) { $('cs-out').innerHTML = '<div class="card warn">' + esc(e.message) + '</div>'; return; }
    var cat = DATA.cat, opz = { ettari: num($('cs-ha').value), acqua: num($('cs-water').value), botte: num($('cs-tank').value) };
    var h = '<section class="card"><h2>Ricetta: ' + esc(q.coltura) + ' — ' + esc(res.avversita.nome) + '</h2>';
    h += '<p class="muted">' + [res.fase ? 'Fase: ' + res.fase.nome : null, 'Situazione: ' + res.situazione.nome, q.ambito === 'serra' ? 'in serra' : 'in pieno campo',
      q.bio ? 'produzione biologica' : null, q.disciplinare && res.righe.length ? 'Disciplinare Calabria' : null,
      q.giorni != null ? q.giorni + ' giorni alla raccolta' : null].filter(Boolean).map(esc).join(' · ') + '</p>';
    res.righe.forEach(function (r) {
      var crit = /^AVVERSIT/i.test(r.criteri || '') ? '' : r.criteri;  // intestazione della tabella letta come testo
      if (crit || r.generale) h += '<div class="dif"><h4>Quando intervenire (Disciplinare Calabria, ' + esc(cat.fonti.disciplinare.versione) + ', ' +
        esc(r.coltura.charAt(0) + r.coltura.slice(1).toLowerCase()) + ', pag. ' + r.pagina + ')</h4>' +
        (crit ? '<p>' + esc(crit) + '</p>' : '') + (r.generale ? '<p class="muted"><strong>Note e limiti:</strong> ' + esc(r.generale) + '</p>' : '') + '</div>';
    });
    h += '<p>' + esc(res.situazione.consiglio) + '</p>';
    var s0 = res.scelti.filter(function (x) { return x.prodotto === pick; })[0] || res.scelti[0], rc = null;
    if (!s0) {
      h += '<div class="warn">' + (res.avversita.u.length ? 'Con le condizioni scelte nessun prodotto Gowan registrato è utilizzabile: vedi i motivi qui sotto.'
        : 'Nessun prodotto Gowan è registrato per questa avversità su questa coltura.') + '</div>';
      res.righe.forEach(function (r) {
        if (r.sostanze.length) h += '<p><strong>Il Disciplinare ammette:</strong> ' + esc(r.sostanze.map(function (x) { return x.s; }).join(', ')) + '.</p>';
      });
    } else {
      rc = Consigli.ricetta(CS, q, s0, opz);
      h += productCard(rc, s0, opz, true);
      if (rc.coadiuvanti.length) {
        h += '<h3>Da aggiungere nella botte</h3>';
        rc.coadiuvanti.forEach(function (c) {
          h += '<p><strong><a href="' + esc(c.pagina) + '" target="_blank" rel="noopener">' + esc(c.nome) + '</a></strong> — ' + esc(c.tipo) + '. Dose: ' + esc(c.dose || '') +
            (c.per_ha ? '; con la tua acqua: <strong>' + esc(fmtQ(c.per_ha)) + '</strong> per ettaro' + (c.botte ? ', <strong>' + esc(fmtQ(c.botte)) + '</strong> nella botte' : '') : '') + '.</p>';
        });
      }
      var alts = res.scelti.filter(function (x) { return x !== s0; });
      if (alts.length) {
        h += '<h3>In alternativa, in ordine di preferenza</h3>';
        alts.slice(0, 3).forEach(function (a) { h += productCard(Consigli.ricetta(CS, q, a, opz), a, opz, false); });
        if (alts.length > 3) {
          h += '<details><summary>Altri prodotti utilizzabili (' + (alts.length - 3) + ')</summary>';
          alts.slice(3).forEach(function (a) { h += productCard(Consigli.ricetta(CS, q, a, opz), a, opz, false); });
          h += '</details>';
        }
      }
      if (res.alternanza.length > 1) h += '<h3>Strategia contro le resistenze</h3><p>Alterna prodotti di gruppi diversi, per esempio: <strong>' + esc(res.alternanza.join(' → ')) +
        '</strong>' + (rc.intervallo ? ', con l\'intervallo indicato in etichetta (' + rangeTxt(rc.intervallo) + ' giorni per ' + esc(s0.prodotto) + ')' : '') + '. I rameici e i biologici si possono ripetere nei limiti di etichetta.</p>';
      if (rc.nutrizionali.length) {
        h += '<h3>Nutrizione e biostimolanti (facoltativi)</h3>';
        rc.nutrizionali.forEach(function (n) {
          var u = n.uso, d = [u.fogliare ? 'fogliare ' + u.fogliare : null, u.fogliare_ha ? 'fogliare ' + u.fogliare_ha : null, u.radicale ? 'fertirrigazione ' + u.radicale : null].filter(Boolean).join(', ');
          h += '<div class="alt-card"><p><strong><a href="' + esc(n.pagina) + '" target="_blank" rel="noopener">' + esc(n.nome) + '</a></strong> — ' + esc(n.tipo) + '</p><p>' + esc(n.scopo) + '</p>' +
            '<p><strong>Dose:</strong> ' + esc(d) + '; ' + esc(u.epoca) + '.</p>' + (n.separato ? '<div class="warn">' + esc(n.separato) + '</div>' : '') +
            (n.avvertenze.length ? '<p class="muted">' + esc(n.avvertenze.join(' ')) + '</p>' : '') + '</div>';
        });
        h += '<p class="muted">' + esc(cat.nutrizionali.avvertenza) + '</p>';
      }
    }
    if (res.esclusi.length) {
      h += '<details><summary>Prodotti registrati ma esclusi (' + res.esclusi.length + ')</summary><ul>' + res.esclusi.map(function (x) {
        return '<li><strong>' + esc(x.prodotto) + '</strong>: ' + esc(x.motivo) + '</li>';
      }).join('') + '</ul></details>';
    }
    var c = cat.colture[CS.colture[q.coltura].i], pr = c.programma && cat.programmi[c.programma], fd = cat.fonti.disciplinare;
    h += '<p class="muted">Fonti: ' + [pr ? '<a href="' + esc(pr.url) + '" target="_blank" rel="noopener">' + esc(pr.titolo) + '</a>' : null,
      res.righe.length ? '<a href="' + esc(fd.url) + '" target="_blank" rel="noopener">' + esc(fd.titolo) + '</a>' : null,
      cat.fonti.ue && cat.fonti.ue.url ? '<a href="' + esc(cat.fonti.ue.url) + '" target="_blank" rel="noopener">EU Pesticides Database</a>' : null,
      esc(cat.fonti.gowan.fonte) + ' (' + esc(cat.fonti.gowan.consultato) + ')', srcLinksIds(['dir_2009_128_ce', 'frac_code_list', 'irac_moa'])].filter(Boolean).join(' · ') + '</p>';
    h += '<p class="muted">' + esc(cat.regole.avvertenza) + '</p></section>';
    h += '<p><button type="button" class="secondary" id="cs-cal">Prepara il calendario dei trattamenti</button></p>';
    $('cs-out').innerHTML = h;
    if ($('cs-cal')) $('cs-cal').addEventListener('click', function () { openCalendario(q.coltura, q.avversita, q.fase); });
    $('cs-out').scrollIntoView({ behavior: 'smooth', block: 'start' });
    Array.prototype.forEach.call(document.querySelectorAll('.cs-use'), function (b) { b.addEventListener('click', function () { csRun(b.getAttribute('data-p')); }); });
    if (rc && $('cs-tank-go')) $('cs-tank-go').addEventListener('click', function () { fillTank(rc.botte, q.coltura, opz); });
  }

  // ------------------------------------------------------------------ botte
  var UNITS = ['g/hl', 'ml/hl', 'kg/ha', 'l/ha', 'g/ha', 'ml/ha', '%'];
  var tankInit = false;
  function initTank() {
    if (!tankInit) {
      tankInit = true;
      $('tk-legal').textContent = Sprayer.LEGAL_NOTE;
      catReady.then(function () {
        var sel = $('tk-crop');
        DATA.cat.colture.slice().sort(function (a, b) { return a.nome.localeCompare(b.nome, 'it'); }).forEach(function (c) {
          var o = document.createElement('option'); o.value = c.nome; o.textContent = c.nome; sel.appendChild(o);
        });
        Array.prototype.forEach.call(document.querySelectorAll('.tk-row'), function (r) { fillPicker(r); });
      }, function () {});
      $('tk-crop').addEventListener('change', function () { Array.prototype.forEach.call(document.querySelectorAll('.tk-row'), refreshUses); });
    }
    if (!$('tk-rows').children.length) addRow();
  }
  function fillPicker(d) {
    var sel = d.querySelector('.tk-pick'), cur = sel.value;
    if (!DATA.cat || sel.querySelector('optgroup')) return;
    var g = document.createElement('optgroup'); g.label = 'Catalogo Gowan';
    DATA.cat.prodotti.slice().sort(function (a, b) { return a.nome.localeCompare(b.nome, 'it'); }).forEach(function (p) {
      var o = document.createElement('option'); o.value = p.nome; o.textContent = p.nome + (p.tipo ? ' — ' + p.tipo : ''); g.appendChild(o);
    });
    sel.insertBefore(g, sel.querySelector('option[value="__altro"]'));
    sel.value = cur;
  }
  function product(name) { return DATA.cat && CS && CS.prodotti[name] != null ? DATA.cat.prodotti[CS.prodotti[name]] : null; }
  function coadiuvante(name) { return ((DATA.cat && DATA.cat.coadiuvanti) || []).filter(function (c) { return c.nome === name; })[0] || null; }
  function addRow(pre) {
    if ($('tk-rows').children.length >= 8) return null;
    var d = document.createElement('div'); d.className = 'reader tk-row';
    d.innerHTML = '<label>Prodotto<select class="tk-pick"><option value="">Scegli dal catalogo Gowan…</option><option value="__altro">Altro prodotto: scrivo i dati dell\'etichetta</option></select></label>' +
      '<p class="muted tk-info"></p>' +
      '<label class="tk-use-l" hidden>Uso registrato sulla coltura <span class="muted">(propone la dose)</span><select class="tk-use"></select></label>' +
      '<div class="tk-manual" hidden><label>Nome commerciale<input class="tk-name" maxlength="120"></label>' +
      '<div class="row"><label>Formulazione<select class="tk-form">' + DATA.rules.formulation_order.order.map(function (f) { return opt(f.id, f.label); }).join('') + '</select></label>' +
      '<label>Tipo<select class="tk-cat">' + DATA.rules.categories.map(function (c) { return opt(c.id, c.label); }).join('') + '</select></label></div>' +
      '<div class="row"><label>Dose massima in etichetta <span class="muted">(stessa unità)</span><input class="tk-max" type="number" min="0" step="any" inputmode="decimal"></label>' +
      '<label>Rame g/kg o g/l <span class="muted">(rameici)</span><input class="tk-cug" type="number" min="0" step="any" inputmode="decimal"></label></div></div>' +
      '<div class="row"><label>Dose<input class="tk-dose" type="number" min="0" step="any" inputmode="decimal"></label>' +
      '<label>Unità<select class="tk-unit">' + UNITS.map(function (u) { return opt(u, u); }).join('') + '</select></label></div>' +
      '<p class="muted tk-range"></p><p><button type="button" class="secondary tk-del">Rimuovi</button></p>';
    d.querySelector('.tk-form').value = 'OTHER';
    d.querySelector('.tk-del').addEventListener('click', function () { d.remove(); });
    d.querySelector('.tk-pick').addEventListener('change', function () { pickProduct(d); });
    d.querySelector('.tk-use').addEventListener('change', function () { applyUse(d); });
    $('tk-rows').appendChild(d);
    fillPicker(d);
    if (pre) {
      if (product(pre.name) || coadiuvante(pre.name)) { d.querySelector('.tk-pick').value = pre.name; pickProduct(d, true); }
      else { d.querySelector('.tk-pick').value = '__altro'; pickProduct(d, true); d.querySelector('.tk-name').value = pre.name; }
      d.querySelector('.tk-dose').value = pre.dose;
      d.querySelector('.tk-unit').value = pre.unit;
      d.dataset.max = pre.label_max != null ? pre.label_max : '';
      d.dataset.maxha = pre.label_max_ha ? JSON.stringify(pre.label_max_ha) : '';
      d.dataset.form = pre.formulation || 'OTHER'; d.dataset.cat = pre.category || 'altro'; d.dataset.cug = pre.copper_g_per_unit || '';
      if (pre.uso != null && d.querySelector('.tk-use option[value="' + pre.uso + '"]')) d.querySelector('.tk-use').value = String(pre.uso);
      d.querySelector('.tk-range').textContent = pre.label_max != null ? 'Dose massima di etichetta: ' + fmtN(pre.label_max) + ' ' + pre.unit +
        (pre.label_max_ha ? ' (al massimo ' + fmtN(pre.label_max_ha.value) + ' ' + pre.label_max_ha.unit + ')' : '') + '.' : '';
    }
    return d;
  }
  var FORM_LABEL = function (id) { var f = DATA.rules.formulation_order.order.filter(function (x) { return x.id === id; })[0]; return f ? f.label : id; };
  function pickProduct(d, keep) {
    var v = d.querySelector('.tk-pick').value, man = d.querySelector('.tk-manual'), info = d.querySelector('.tk-info');
    d.dataset.max = d.dataset.maxha = d.dataset.cug = ''; d.dataset.form = 'OTHER'; d.dataset.cat = 'altro';
    info.textContent = ''; d.querySelector('.tk-range').textContent = '';
    man.hidden = v !== '__altro';
    var p = product(v), c = coadiuvante(v);
    if (p) {
      d.dataset.form = p.form || 'OTHER'; d.dataset.cat = p.categoria || 'altro'; d.dataset.cug = p.rame_g || '';
      info.textContent = [FORM_LABEL(p.form || 'OTHER'), p.tipo, p.rame_g ? 'rame ' + fmtN(p.rame_g) + (p.liquido ? ' g/l' : ' g/kg') : null, p.bio ? 'BIO' : null].filter(Boolean).join(' · ');
    }
    if ((v === 'MAGO' || (c && !p)) && c && c.dose_hl && !keep) {
      d.dataset.form = 'ADJ'; d.querySelector('.tk-unit').value = 'ml/hl'; d.querySelector('.tk-dose').value = c.dose_hl[0];
      d.dataset.max = c.dose_hl[1]; d.dataset.maxha = JSON.stringify({ value: c.max_ha / 1000, unit: 'l/ha' });
      d.querySelector('.tk-range').textContent = 'Dose di etichetta: ' + c.dose + '.';
    }
    refreshUses(d);
  }
  function refreshUses(d) {
    var p = product(d.querySelector('.tk-pick').value), crop = $('tk-crop').value, lab = d.querySelector('.tk-use-l'), sel = d.querySelector('.tk-use');
    lab.hidden = true; sel.innerHTML = '';
    if (!p) return;
    if (!crop) { if (!d.querySelector('.tk-range').textContent) d.querySelector('.tk-range').textContent = 'Indica la coltura al passo 1 per vedere gli usi registrati e le dosi.'; return; }
    var ci = CS.colture[crop] ? CS.colture[crop].i : -1, pi = CS.prodotti[p.nome], seen = {}, opts = [];
    DATA.cat.usi.forEach(function (u, i) {
      if (u.p !== pi || u.c !== ci) return;
      var label = DATA.cat.testi[u.a] + (u.s === 'serra' ? ' (serra)' : '') + ' — ' + ([u.hl ? doseTxt(u.hl) : null, u.ha ? doseTxt(u.ha) : null].filter(Boolean).join(' · ') || 'dose: vedi etichetta');
      if (seen[label]) return; seen[label] = 1;
      opts.push(opt(i, label));
    });
    if (!opts.length) { d.querySelector('.tk-range').textContent = 'Nessun uso registrato di ' + p.nome + ' su ' + crop + ': controlla l\'etichetta.'; return; }
    sel.innerHTML = '<option value="">Scegli l\'avversità</option>' + opts.join('');
    lab.hidden = false;
  }
  function doseTxt(r) { return (r[3] ? 'max ' : '') + (r[0] === r[1] || r[3] ? fmtN(r[1]) : fmtN(r[0]) + '-' + fmtN(r[1])) + ' ' + r[2]; }
  var TO_TANK = { 'g/hl': ['g/hl', 1], 'kg/hl': ['g/hl', 1000], 'ml/hl': ['ml/hl', 1], 'l/hl': ['ml/hl', 1000],
                  'g/ha': ['g/ha', 1], 'kg/ha': ['kg/ha', 1], 'ml/ha': ['ml/ha', 1], 'l/ha': ['l/ha', 1] };
  function applyUse(d) {
    var i = d.querySelector('.tk-use').value;
    if (i === '') return;
    var u = DATA.cat.usi[Number(i)];
    if (!u.hl && !u.ha) { d.querySelector('.tk-range').textContent = 'Per questo uso la dose non è sul sito Gowan: leggila nell\'etichetta e scrivila qui.'; return; }
    // con la dose a ettaro in etichetta si propone quella: l'etichetta chiede di rispettarla con qualunque volume d'acqua
    var r = u.ha || u.hl, t = TO_TANK[r[2]];
    d.querySelector('.tk-unit').value = t[0];
    d.querySelector('.tk-dose').value = Math.round((r[3] ? r[1] : r[0]) * t[1] * 1000) / 1000;
    d.dataset.max = Math.round(r[1] * t[1] * 1000) / 1000;
    d.dataset.maxha = '';
    var x = ['Dose di etichetta: ' + [u.hl ? doseTxt(u.hl) : null, u.ha ? doseTxt(u.ha) : null].filter(Boolean).join(' · ')];
    if (u.phi != null) x.push('intervallo di sicurezza ' + (u.phi === 0 ? 'non necessario' : u.phi + ' giorni'));
    if (u.phi_fase) x.push((DATA.cat.regole.limiti_fase[u.phi_fase] || {}).testo || u.phi_fase);
    if (u.n_max) x.push('al massimo ' + u.n_max + ' trattamenti');
    d.querySelector('.tk-range').textContent = x.join('; ') + '. Proposta la dose minima' + (u.ha ? ' a ettaro' : '') + ': modificala entro i limiti.';
  }
  function fillTank(rows, crop, opz) {
    ready.then(function () {
      initTank();
      $('tk-rows').innerHTML = '';
      if (opz.botte) $('tk-vol').value = opz.botte;
      if (opz.acqua) $('tk-wha').value = opz.acqua;
      catReady.then(function () { $('tk-crop').value = crop || ''; rows.forEach(function (r) { addRow(r); }); }, function () { rows.forEach(function (r) { addRow(r); }); });
      $('tk-out').innerHTML = '';
      showTab('tank');
    });
  }
  $('tk-add').addEventListener('click', function () { ready.then(function () { addRow(); }); });
  $('tk-calc').addEventListener('click', function () {
    var products = Array.prototype.map.call(document.querySelectorAll('.tk-row'), function (r) {
      var v = r.querySelector('.tk-pick').value, manual = v === '__altro' || v === '';
      var maxha = r.dataset.maxha ? JSON.parse(r.dataset.maxha) : null;
      return { name: manual ? (r.querySelector('.tk-name').value.trim() || 'Prodotto') : v, dose: num(r.querySelector('.tk-dose').value),
        unit: r.querySelector('.tk-unit').value, formulation: manual ? r.querySelector('.tk-form').value : (r.dataset.form || 'OTHER'),
        category: manual ? r.querySelector('.tk-cat').value : (r.dataset.cat || 'altro'),
        label_max: manual ? num(r.querySelector('.tk-max').value) : num(r.dataset.max),
        copper_g_per_unit: manual ? num(r.querySelector('.tk-cug').value) : num(r.dataset.cug), label_max_ha: manual ? null : maxha };
    });
    var j, vol = num($('tk-vol').value);
    try {
      j = Sprayer.computeTank(vol, products, num($('tk-wha').value), num($('tk-temp').value), num($('tk-cu').value), DATA.rules);
    } catch (e) { $('tk-out').innerHTML = '<div class="card warn">' + esc(e.message) + '</div>'; return; }
    var h = '<section class="card"><h2>Risultato</h2>';
    j.errors.forEach(function (e) { h += '<div class="warn lab">' + esc(e) + '</div>'; });
    if (j.area_ha != null) h += '<p class="big">Una botte da ' + esc(vol) + ' l tratta ' + esc(fmtN(j.area_ha)) + ' ha <span class="muted">(' + Math.round(j.area_ha * 10000) + ' m²)</span></p>';
    var left = j.products.slice();
    var take = function (name) { for (var i = 0; i < left.length; i++) if (left[i].name === name) return left.splice(i, 1)[0]; return null; };
    h += '<h3>Come preparare la botte</h3><ol class="prep"><li>Riempi la botte d\'acqua per circa metà e accendi l\'agitatore.</li>';
    j.order.forEach(function (o) {
      var p = take(o.name);
      if (p) h += '<li>Aggiungi <strong>' + esc(fmtN(p.amount.value) + ' ' + p.amount.unit) + '</strong> di <strong>' + esc(o.name) + '</strong>' + (p.over_label ? ' ⚠' : '') +
        ' <span class="muted">(' + esc(o.formulation) + ')</span> e aspetta che sia ben sciolto o disperso.</li>';
    });
    h += '<li>Completa con l\'acqua fino a ' + esc(vol) + ' litri, sempre con l\'agitatore acceso, e tratta subito.</li></ol>';
    h += '<table><tr><th>Prodotto</th><th class="n">Nella botte</th><th class="n">Per ettaro</th></tr>';
    j.products.forEach(function (p) {
      h += '<tr><td>' + esc(p.name) + (p.over_label ? ' ⚠' : '') + '<br><span class="muted">' + esc(fmtN(p.dose) + ' ' + p.unit) + '</span></td><td class="n"><strong>' +
        esc(fmtN(p.amount.value) + ' ' + p.amount.unit) + '</strong></td><td class="n">' + (p.per_ha ? esc(fmtN(p.per_ha.value) + ' ' + p.per_ha.unit) : '–') + '</td></tr>';
    });
    h += '</table>';
    if (j.copper_kg_ha != null) h += '<p>Rame metallo distribuito: <strong>' + esc(fmtN(j.copper_kg_ha)) + ' kg/ha</strong></p>';
    if (j.warnings.length) h += '<h3>Attenzioni</h3>';
    j.warnings.forEach(function (w) { h += '<div class="warn' + (w.level === 'incompatibile' ? ' lab' : '') + '">' + esc(w.text).replace(/(\d)\.(\d)/g, '$1,$2') + '</div>'; });
    h += '<details><summary>Regole generali di preparazione</summary><ul>' + j.procedure.map(function (p) { return '<li>' + esc(p.text) + '</li>'; }).join('') + '</ul></details>';
    var ids = {};
    j.warnings.forEach(function (w) { w.sources.forEach(function (s) { ids[s] = 1; }); });
    j.order_sources.forEach(function (s) { ids[s] = 1; });
    j.procedure.forEach(function (p) { p.sources.forEach(function (s) { ids[s] = 1; }); });
    var links = srcLinksIds(Object.keys(ids));
    if (links) h += '<p class="muted">Fonti: ' + links + '</p>';
    h += '<p class="muted">' + esc(j.legal_note) + '</p></section>';
    $('tk-out').innerHTML = h;
  });

  // ------------------------------------------------------------------ info
  // risultati del modello pubblicato sulle foto di campo (configs/valutazione_web.yaml)
  function valHtml() {
    var v = DATA.val, R = DATA.readers;
    if (!v || !R) return '';
    var names = { plant: 'Coltura', disease: 'Malattia', pest: 'Insetti e acari', deficiency: 'Carenze' };
    var h = '<table><tr><th>Lettore e foto di prova</th><th class="n">Giuste</th></tr>';
    ['plant', 'disease', 'pest', 'deficiency'].forEach(function (hd) {
      if (!R[hd]) return;
      h += '<tr><td colspan="2"><strong>' + names[hd] + '</strong> <span class="muted">(' + R[hd].classes.length + ' classi; prova mista con foto di laboratorio: ' + pct(R[hd].test_accuracy) + ')</span></td></tr>';
      v.prove.filter(function (p) { return p.lettore === hd; }).forEach(function (p) {
        h += '<tr><td>' + esc(p.nome) + '</td><td class="n">' + pct(p.accuratezza) + '</td></tr>';
      });
    });
    return h + '</table><p class="muted">Modello ' + esc(v.modello) + ' del ' + esc(v.data.split('-').reverse().join('/')) + '. La prova mista include foto di laboratorio ed è ottimistica; ' +
      'le foto di campo sono più vicine all\'uso reale. La prova "esperti del Sud" usa foto di bollettini, riviste e tesi (legno, cancri, essudati) che il modello non ha mai visto: ' +
      'è la più difficile e mostra dove serve ancora lavoro. Le carenze hanno pochi esempi: indicazione preliminare. Quando il lettore non è sicuro mostra più ipotesi invece di una sola.</p>';
  }
  function quizHtml() {
    var q = DATA.quiz || [];
    if (!q.length) return '';
    var cls = {}, sud = 0;
    q.forEach(function (x) { cls[x.head + '|' + x.label] = 1; if (x.sud) sud++; });
    return '<p>Quiz: <strong>' + q.length.toLocaleString('it-IT') + ' foto</strong> di ' + Object.keys(cls).length + ' colture, malattie, carenze e insetti; ' +
      Math.round(sud / q.length * 100) + '% su colture tipiche del Sud Italia e della Calabria, che escono in 7 domande su 10.</p>';
  }

  function renderInfo() {
    $('info').innerHTML = '<h2>Contributi per migliorare la rete</h2>' +
      '<p>Contributi salvati in questo telefono: <strong id="cb-count">0</strong>.</p>' +
      '<p class="muted">Inviali al responsabile del progetto (mail, WhatsApp, Drive): servono a riaddestrare la rete sulle foto reali dei campi calabresi e siciliani.</p>' +
      '<div class="row"><button type="button" id="cb-export">Invia contributi</button><button type="button" class="secondary" id="cb-clear" hidden>Svuota elenco</button></div>' +
      '<p class="muted" id="cb-export-status"></p>' +
      '<h2>Come funziona</h2>' +
      '<p><strong>Lettore.</strong> Una rete neurale riconosce coltura, malattia o danno, carenze e insetti. Usa due estrattori di immagini, DINOv2 ed EfficientNet-B0. Per ogni domanda decidono più lettori calibrati (14 per malattie e danni, 10 per gli insetti, 5 per coltura e carenze), e ne conta la media. ' +
      'La rete gira nel browser con ONNX Runtime Web: la foto non lascia il dispositivo. È addestrata su raccolte scientifiche aperte e su foto di campo del Sud Italia, anche di ARSAC, riviste e tesi, verificate a vista una per una.</p>' +
      '<div id="info-val">' + valHtml() + '</div>' +
      '<p><strong>Consigli.</strong> Scegli coltura, avversità, fase e situazione: l\'app ordina i prodotti Gowan registrati come un tecnico della difesa integrata e prepara la ricetta. ' +
      '<p><strong>Calendario.</strong> Da coltura, avversità (o carenza), fase di partenza e data di raccolta prepara le date dei trattamenti: rispetta numero massimo e intervalli dell\'etichetta, limiti del Disciplinare (anche quelli comuni a un gruppo di sostanze), carenze, fasi ammesse, alternanza FRAC/IRAC e rame massimo; si può aggiungere al calendario del telefono.</p>' +
      'Non è una rete neurale: sono regole scritte con le loro fonti, cioè etichette, programmi Gowan, Disciplinare della Calabria e banca dati UE. Ogni prodotto mostra il motivo della sua posizione.</p>' +
      '<p><strong>Botte.</strong> Prodotti dal catalogo Gowan o scritti a mano: quantità per la botte e per ettaro, ordine di carico, incompatibilità, rame, limiti di etichetta.</p>' +
      '<div id="info-quiz">' + quizHtml() + '</div>' +
      '<h2>Fonti dei dati</h2><ul>' +
      '<li>PlantVillage (Hughes e Salathé, 2015); PlantDoc (Singh et al., 2020, CC BY 4.0); PlantWild; dataset Project-AgML (UC Davis, CC BY 4.0 / MIT) e iNatAg</li>' +
      '<li>iNaturalist e Observation.org: foto con licenza aperta e autore citato, con le osservazioni della Calabria e dell\'Italia per prime</li>' +
      '<li>Bugwood (Università della Georgia), DiaMOS, FieldVitis, virus della vite</li>' +
      '<li>Dataset aperti di campo (CC BY 4.0) da Mendeley Data e Zenodo: esca della vite (Università Politecnica delle Marche), agrumi di Fès, limone, peronospora della vite (Merlot; Spagna e Norvegia), peperone (progetto EU EWA-BELT)</li>' +
      '<li>Solo per l\'addestramento, non ripubblicate: foto di ARSAC, Servizio fitosanitario, riviste, tesi UNIRC, Europe PMC e dispense universitarie, verificate a vista una per una (art. 70-ter, legge sul diritto d\'autore)</li>' +
      '<li>IP102 (Wu et al., 2019): solo uso accademico; EPPO Global Database: uso didattico</li></ul>' +
      '<p class="muted">Conoscenze agronomiche: Disciplinare di produzione integrata della Regione Calabria 2026 (aggiornamento di agosto), bollettini ARSAC, schede EPPO, EFSA, banca dati UE dei pesticidi, etichette e programmi Gowan Italia, Università Mediterranea di Reggio Calabria e altre università del Sud. Elenco completo e livello di verifica nel repository.</p>' +
      '<h2>Norme e aggiornamenti</h2><p class="muted" id="info-norme">' + esc(normeText()) + '</p>' +
      '<p class="muted">Ogni giorno un controllo automatico cerca un nuovo Disciplinare della Calabria sul sito ARSAC e lo stato delle sostanze attive nella banca dati UE, ogni settimana le etichette Gowan; le novità diventano una proposta di aggiornamento che una persona controlla prima della pubblicazione.</p>' +
      '<h2>Avvertenze</h2><p class="muted">Strumento di supporto alla decisione, non una diagnosi. Per virus, viroidi, batteri e nematodi serve la conferma di laboratorio. Dosi e compatibilità dei prodotti sono quelle dell\'etichetta autorizzata.</p>' +
      '<p class="muted">Motore: ONNX Runtime Web 1.20.1 (licenza MIT). Codice: <a href="https://github.com/ringhiosaverio-code/riconoscimentopiantemalattiecarenze" target="_blank" rel="noopener">repository</a>, licenza Apache-2.0.</p>';
  }
})();
