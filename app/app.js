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
  var ready = Promise.all(['readers.json', 'organs.json', 'mixing_rules.json', 'sources.json', 'quiz.json'].map(getJSON))
    .then(function (a) {
      DATA.readers = a[0]; DATA.organs = a[1]; DATA.rules = a[2]; DATA.sources = a[3]; DATA.quiz = a[4];
      var sel = $('organ');
      DATA.organs.forEach(function (o) { var op = document.createElement('option'); op.value = o.id; op.textContent = o.label; sel.appendChild(op); });
      renderInfo();
    })
    .catch(function () { $('model-status').textContent = "Errore nel caricamento dei dati dell'app: ricarica la pagina."; });

  // ------------------------------------------------------------------ schede
  function showTab(name) {
    ['reader', 'quiz', 'tank', 'info'].forEach(function (t) {
      $('tab-' + t).hidden = t !== name;
      $('t-' + t).setAttribute('aria-selected', String(t === name));
    });
    if (name === 'tank' && !$('tk-rows').children.length) ready.then(initTank);
    window.scrollTo(0, 0);
  }
  ['reader', 'quiz', 'tank', 'info'].forEach(function (t) { $('t-' + t).addEventListener('click', function () { showTab(t); }); });

  // ------------------------------------------------------------------ modello
  function loadModel() {
    if (session) return Promise.resolve(session);
    ort.env.wasm.wasmPaths = new URL('app/ort/', document.baseURI).href;  // URL assoluto: serve all'import() dinamico
    ort.env.wasm.numThreads = 1;
    $('prog').hidden = false;
    $('model-status').textContent = 'Scaricamento del modello in corso…';
    return fetch('app/model/plantcare.onnx').then(function (resp) {
      if (!resp.ok) throw new Error('modello');
      var total = Number(resp.headers.get('content-length')) || 45e6;
      var reader = resp.body.getReader(), chunks = [], got = 0;
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) return;
          chunks.push(r.value); got += r.value.length;
          $('prog').firstElementChild.style.width = Math.min(100, got / total * 100).toFixed(0) + '%';
          return pump();
        });
      }
      return pump().then(function () {
        var buf = new Uint8Array(got), off = 0;
        chunks.forEach(function (c) { buf.set(c, off); off += c.length; });
        $('model-status').textContent = 'Preparazione del modello…';
        return ort.InferenceSession.create(buf, { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
      });
    }).then(function (s) {
      session = s; $('prog').hidden = true; $('model-status').textContent = 'Modello pronto.'; return s;
    });
  }

  // quadrato centrale ridimensionato a 224 px, normalizzato; secondo elemento del batch: immagine specchiata
  function toTensor(source, w, h) {
    var c = $('canvas'); c.width = SIZE; c.height = SIZE;
    var ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    var s = Math.min(w, h);
    ctx.drawImage(source, (w - s) / 2, (h - s) / 2, s, s, 0, 0, SIZE, SIZE);
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

  function analyze(source, w, h) {
    $('out').innerHTML = '<div class="card">Analisi in corso…</div>';
    ready.then(loadModel).then(function (s) {
      var t0 = performance.now();
      return s.run({ image: toTensor(source, w, h) }).then(function (outs) {
        var res = {};
        HEADS.forEach(function (hd) {
          var o = outs[hd].data, k = o.length / 2, probs = [];
          for (var i = 0; i < k; i++) probs.push((o[i] + o[k + i]) / 2);
          res[hd] = probs;
        });
        render(res, (performance.now() - t0) / 1000);
      });
    }).catch(function (e) {
      $('prog').hidden = true;
      $('out').innerHTML = '<div class="card warn">Analisi non riuscita: ' + esc(e.message || e) + '. Controlla la connessione e riprova.</div>';
    });
  }

  function top(probs, k) {
    return probs.map(function (p, i) { return [p, i]; }).sort(function (a, b) { return b[0] - a[0]; }).slice(0, k);
  }

  function render(res, secs) {
    var organ = $('organ').value, h = '<section class="card"><h2>Risultato dei lettori</h2>';
    var answers = {};
    HEADS.forEach(function (hd) {
      var R = DATA.readers[hd], t = top(res[hd], 3), best = R.classes[t[0][1]];
      var ok = t[0][0] >= THRESHOLD;
      answers[hd] = ok ? best : null;
      h += '<div class="reader"><h3>' + esc(READER_LABELS[hd]) + ': ' + esc(ok ? best.name : 'non determinabile') + '</h3>';
      t.forEach(function (x) {
        var c = R.classes[x[1]];
        h += '<div class="cand"><div class="bar"><span style="width:' + (x[0] * 100).toFixed(1) + '%"></span><em>' + esc(c.name) + '</em></div><div class="p">' + pct(x[0]) + '</div></div>';
      });
      var field = R.field && (R.field.plantdoc || R.field.inatag);
      h += '<p class="muted">Affidabilità sul test: ' + pct(R.test_accuracy) + (field ? '; su foto di campo: ' + pct(field.accuracy) : '') + '.</p></div>';
    });
    h += '<div class="reader"><h3>Lettore di insetti e acari</h3><p class="muted">Non incluso nella versione pubblica: il dataset IP102 su cui è addestrato è concesso solo per uso accademico.</p></div>';
    h += referto(answers, organ);
    h += '<p><button type="button" class="secondary" id="go-tank">Prepara la botte</button></p>';
    h += '<p class="muted">Analisi in ' + secs.toFixed(1) + ' s sul dispositivo. Strumento di supporto alla decisione: per virus, viroidi, batteri e nematodi serve la conferma di laboratorio.</p></section>';
    $('out').innerHTML = h;
    $('out').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('go-tank').addEventListener('click', function () { showTab('tank'); });
  }

  function referto(a, organ) {
    var s = '<div class="reader"><h3>Referto</h3>';
    if (a.plant) s += '<p><strong>Coltura:</strong> ' + esc(a.plant.name) + '</p>';
    var d = a.disease, card = d && d.card;
    if (d) s += '<p><strong>Malattia o danno:</strong> ' + esc(d.name) + (card && card.agent ? ' (<em>' + esc(card.agent) + '</em>)' : '') + '</p>';
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
        stream = st; var v = $('video'); v.srcObject = st; v.hidden = false;
        $('cam-shot').disabled = false; $('cam-stop').disabled = false;
        $('cam-status').textContent = 'Inquadra la parte colpita al centro e premi "Scatta e analizza".';
        ready.then(loadModel).catch(function () {});  // scarica il modello mentre si inquadra
      })
      .catch(function () { $('cam-status').textContent = 'Fotocamera non disponibile o permesso negato: usa una foto dalla galleria.'; });
  });
  $('cam-stop').addEventListener('click', function () {
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null; $('video').hidden = true; $('cam-shot').disabled = true; $('cam-stop').disabled = true; $('cam-status').textContent = '';
  });
  $('cam-shot').addEventListener('click', function () {
    var v = $('video'); analyze(v, v.videoWidth, v.videoHeight);
  });
  $('file').addEventListener('change', function () {
    var f = $('file').files[0]; if (!f) return;
    var url = URL.createObjectURL(f);
    $('preview').innerHTML = '<img class="preview" alt="Foto scelta" src="' + url + '">';
    var img = new Image();
    img.onload = function () { analyze(img, img.naturalWidth, img.naturalHeight); };
    img.src = url;
  });

  // ------------------------------------------------------------------ quiz
  var qCur = null, score = { ok: 0, tot: 0 };
  function nameOf(head, label) {
    var c = DATA.readers[head].classes.filter(function (x) { return x.label === label; })[0];
    return c ? c.name : label;
  }
  function shuffle(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  $('q-new').addEventListener('click', function () {
    ready.then(function () {
      var cat = $('q-cat').value;
      var pool = DATA.quiz.filter(function (q) { return cat === 'any' || q.head === cat; });
      var item = pool[Math.floor(Math.random() * pool.length)];
      var labels = {};
      DATA.quiz.forEach(function (q) { if (q.head === item.head) labels[q.label] = q.plant; });
      var others = Object.keys(labels).filter(function (l) { return l !== item.label; });
      if (item.head === 'disease') {
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
      var questions = { plant: 'Quale coltura è?', disease: 'Quale malattia o danno si vede?', deficiency: 'Che disturbo nutrizionale si vede?' };
      $('q-text').textContent = questions[item.head];
      $('q-img').src = 'app/quiz/' + item.img;
      $('q-credit').textContent = 'Foto: ' + item.credit;
      $('q-exp').innerHTML = '';
      var box = $('q-opts'); box.innerHTML = '';
      qCur.opts.forEach(function (l) {
        var b = document.createElement('button'); b.type = 'button'; b.textContent = nameOf(item.head, l);
        b.addEventListener('click', function () { answer(l, b); });
        box.appendChild(b);
      });
      $('q-box').hidden = false;
    });
  });
  function answer(choice) {
    if (!qCur) return;
    var q = qCur; qCur = null;
    var right = choice === q.item.label;
    Array.prototype.forEach.call($('q-opts').children, function (b, i) {
      b.disabled = true;
      if (q.opts[i] === q.item.label) b.classList.add('ok'); else if (q.opts[i] === choice) b.classList.add('ko');
    });
    score.tot++; if (right) score.ok++;
    $('q-score').textContent = 'Punteggio: ' + score.ok + ' su ' + score.tot;
    var h = '<div class="reader"><p><strong>' + (right ? 'Corretto!' : 'Sbagliato.') + '</strong> Risposta: ' + esc(nameOf(q.item.head, q.item.label)) + '</p>';
    if (q.item.head === 'disease') {
      var c = DATA.readers.disease.classes.filter(function (x) { return x.label === q.item.label; })[0];
      var card = c && c.card;
      if (card) {
        if (card.agent) h += '<p class="muted">Agente: <em>' + esc(card.agent) + '</em></p>';
        h += '<p class="muted">' + esc((card.knowledge && card.knowledge.cause) || card.symptoms) + '</p>';
        if (card.organs && card.organs.length) h += '<p class="muted">Organi colpiti: ' + esc(card.organs.map(function (o) { return o.label; }).join(', ')) + '</p>';
        if (card.lab_note) h += '<div class="warn lab">' + esc(card.lab_note) + '</div>';
      }
    } else if (q.item.head === 'deficiency') {
      h += '<p class="muted">Etichetta degli autori del dataset; la conferma richiede l\'analisi fogliare.</p>';
    }
    $('q-exp').innerHTML = h + '</div>';
  }

  // ------------------------------------------------------------------ botte
  var opt = function (v, t) { return '<option value="' + esc(v) + '">' + esc(t) + '</option>'; };
  function initTank() {
    $('tk-legal').textContent = Sprayer.LEGAL_NOTE;
    addRow();
  }
  function addRow() {
    if ($('tk-rows').children.length >= 8) return;
    var d = document.createElement('div'); d.className = 'reader tk-row';
    d.innerHTML = '<label>Nome commerciale<input class="tk-name" maxlength="120"></label>' +
      '<div class="row"><label>Dose<input class="tk-dose" type="number" min="0" step="any" inputmode="decimal"></label>' +
      '<label>Unità<select class="tk-unit">' + ['g/hl', 'ml/hl', 'kg/ha', 'l/ha', 'g/ha', 'ml/ha', '%'].map(function (u) { return opt(u, u); }).join('') + '</select></label></div>' +
      '<div class="row"><label>Formulazione<select class="tk-form">' + DATA.rules.formulation_order.order.map(function (f) { return opt(f.id, f.label); }).join('') + '</select></label>' +
      '<label>Tipo<select class="tk-cat">' + DATA.rules.categories.map(function (c) { return opt(c.id, c.label); }).join('') + '</select></label></div>' +
      '<div class="row"><label>Dose max etichetta <span class="muted">(stessa unità)</span><input class="tk-max" type="number" min="0" step="any" inputmode="decimal"></label>' +
      '<label>Rame g/kg o g/l <span class="muted">(rameici)</span><input class="tk-cug" type="number" min="0" step="any" inputmode="decimal"></label></div>' +
      '<p><button type="button" class="secondary tk-del">Rimuovi</button></p>';
    d.querySelector('.tk-form').value = 'OTHER';
    d.querySelector('.tk-del').addEventListener('click', function () { d.remove(); });
    $('tk-rows').appendChild(d);
  }
  $('tk-add').addEventListener('click', function () { ready.then(addRow); });
  var num = function (v) { return v === '' ? null : Number(v); };
  $('tk-calc').addEventListener('click', function () {
    var products = Array.prototype.map.call(document.querySelectorAll('.tk-row'), function (r) {
      return { name: r.querySelector('.tk-name').value.trim() || 'Prodotto', dose: num(r.querySelector('.tk-dose').value),
        unit: r.querySelector('.tk-unit').value, formulation: r.querySelector('.tk-form').value, category: r.querySelector('.tk-cat').value,
        label_max: num(r.querySelector('.tk-max').value), copper_g_per_unit: num(r.querySelector('.tk-cug').value) };
    });
    var j;
    try {
      j = Sprayer.computeTank(num($('tk-vol').value), products, num($('tk-wha').value), num($('tk-temp').value), num($('tk-cu').value), DATA.rules);
    } catch (e) { $('tk-out').innerHTML = '<div class="card warn">' + esc(e.message) + '</div>'; return; }
    var h = '<section class="card"><h2>Risultato</h2>';
    j.errors.forEach(function (e) { h += '<div class="warn">' + esc(e) + '</div>'; });
    if (j.area_ha != null) h += '<p>Una botte copre <strong>' + esc(j.area_ha) + ' ha</strong> (' + Math.round(j.area_ha * 10000) + ' m²).</p>';
    h += '<table><tr><th>Prodotto</th><th class="n">Nella botte</th><th class="n">Per ettaro</th></tr>';
    j.products.forEach(function (p) {
      h += '<tr><td>' + esc(p.name) + (p.over_label ? ' ⚠' : '') + '<br><span class="muted">' + esc(p.dose + ' ' + p.unit) + '</span></td><td class="n"><strong>' +
        esc(p.amount.value + ' ' + p.amount.unit) + '</strong></td><td class="n">' + (p.per_ha ? esc(p.per_ha.value + ' ' + p.per_ha.unit) : '–') + '</td></tr>';
    });
    h += '</table>';
    if (j.copper_kg_ha != null) h += '<p>Rame metallo: <strong>' + esc(j.copper_kg_ha) + ' kg/ha</strong></p>';
    h += '<h3>Ordine di caricamento</h3><ol>' + j.order.map(function (o) { return '<li>' + esc(o.name) + ' <span class="muted">(' + esc(o.formulation) + ')</span></li>'; }).join('') + '</ol>';
    j.warnings.forEach(function (w) { h += '<div class="warn' + (w.level === 'incompatibile' ? ' lab' : '') + '">' + esc(w.text) + '</div>'; });
    h += '<h3>Procedura</h3><ul>' + j.procedure.map(function (p) { return '<li>' + esc(p.text) + '</li>'; }).join('') + '</ul>';
    var ids = {};
    j.warnings.forEach(function (w) { w.sources.forEach(function (s) { ids[s] = 1; }); });
    j.order_sources.forEach(function (s) { ids[s] = 1; });
    j.procedure.forEach(function (p) { p.sources.forEach(function (s) { ids[s] = 1; }); });
    var links = Object.keys(ids).filter(function (s) { return DATA.sources[s]; }).map(function (s) {
      return '<a href="' + esc(DATA.sources[s].url) + '" target="_blank" rel="noopener">' + esc(DATA.sources[s].title) + '</a>';
    });
    if (links.length) h += '<p class="muted">Fonti: ' + links.join(' · ') + '</p>';
    h += '<p class="muted">' + esc(j.legal_note) + '</p></section>';
    $('tk-out').innerHTML = h;
  });

  // ------------------------------------------------------------------ info
  function renderInfo() {
    var r = DATA.readers;
    var row = function (hd, label) {
      var f = r[hd].field || {};
      return '<tr><td>' + label + '</td><td class="n">' + pct(r[hd].test_accuracy) + '</td><td class="n">' +
        (f.plantdoc ? pct(f.plantdoc.accuracy) : (f.inatag ? pct(f.inatag.accuracy) : '–')) + '</td></tr>';
    };
    $('info').innerHTML = '<h2>Come funziona</h2>' +
      '<p>La rete neurale (estrattori DINOv2 ed EfficientNet-B0 con lettori calibrati) gira nel browser con ONNX Runtime Web. La foto non lascia il dispositivo.</p>' +
      '<table><tr><th>Lettore</th><th class="n">Test</th><th class="n">Foto di campo</th></tr>' +
      row('plant', 'Coltura') + row('disease', 'Malattia') + row('deficiency', 'Carenze') + '</table>' +
      '<p class="muted">Il valore sul test include foto di laboratorio ed è ottimistico; quello su foto di campo (PlantDoc) è più vicino all\'uso reale. Le carenze hanno pochi esempi: indicazione preliminare.</p>' +
      '<h2>Fonti dei dati</h2><ul>' +
      '<li>PlantVillage (Hughes e Salathé, 2015)</li><li>PlantDoc (Singh et al., 2020), CC BY 4.0</li>' +
      '<li>Dataset Project-AgML (UC Davis), CC BY 4.0 / MIT</li><li>iNatAg (Project-AgML), da iNaturalist</li></ul>' +
      '<p class="muted">Conoscenze agronomiche: disciplinare di produzione integrata della Regione Calabria (2023), bollettini ARSAC, schede EPPO, EFSA, Università Mediterranea di Reggio Calabria, Università di Bari. Elenco completo e livello di verifica nel repository.</p>' +
      '<h2>Avvertenze</h2><p class="muted">Strumento di supporto alla decisione, non una diagnosi. Per virus, viroidi, batteri e nematodi serve la conferma di laboratorio. Dosi e compatibilità dei prodotti sono quelle dell\'etichetta autorizzata.</p>' +
      '<p class="muted">Motore: ONNX Runtime Web 1.20.1 (licenza MIT). Codice: <a href="https://github.com/ringhiosaverio-code/riconoscimentopiantemalattiecarenze" target="_blank" rel="noopener">repository</a>, licenza Apache-2.0.</p>';
  }
})();
