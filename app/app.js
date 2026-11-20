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
      renderInfo();
      wireInfo();
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
        render(res, (performance.now() - t0) / 1000);
      });
    }).catch(function (e) {
      $('prog').hidden = true;
      $('out').innerHTML = '<div class="card warn">Analisi non riuscita: ' + esc(e.message || e) + '. Controlla la connessione e riprova.</div>';
    });
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
    return { html: h + '</div>', best: best };
  }

  // Lettore degli insetti: separato dagli altri, perché ha senso solo se la foto mostra un insetto.
  function pestBlock(probs) {
    var R = DATA.readers.pest;
    if (!R || !probs) return '';
    var t = top(probs, 3), ok = t[0][0] >= THRESHOLD;
    var h = '<div class="reader"><h3>Lettore di insetti e acari: ' + esc(ok ? R.classes[t[0][1]].name : 'non determinabile') + '</h3>' +
      '<p class="muted">Vale solo se la foto mostra un insetto o un acaro, non i suoi danni.</p>';
    t.forEach(function (x) {
      h += '<div class="cand"><div class="bar"><span style="width:' + (x[0] * 100).toFixed(1) + '%"></span><em>' + esc(R.classes[x[1]].name) + '</em></div><div class="p">' + pct(x[0]) + '</div></div>';
    });
    return h + '<p class="muted">Affidabilità sul test: ' + pct(R.test_accuracy) + '. Addestrato su IP102 (102 insetti dannosi, soprattutto di riso, frumento, mais, erba medica, vite, agrumi e mango), concesso per uso accademico: mancano molte specie mediterranee, come la mosca delle olive.</p></div>';
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
    var cz = causeBlock(res.disease);
    answers.cause = cz.best;
    h += cz.html;
    h += pestBlock(res.pest);
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
    var v = $('video'), w = v.videoWidth, h = v.videoHeight, c = document.createElement('canvas');
    if (!w || !h) return;
    c.width = w; c.height = h; c.getContext('2d').drawImage(v, 0, 0, w, h);
    showPicker(c, w, h, c.toDataURL('image/jpeg', 0.9));
    analyze(c, w, h);
  });
  $('file').addEventListener('change', function () {
    var f = $('file').files[0]; if (!f) return;
    var url = URL.createObjectURL(f), img = new Image();
    img.onload = function () {
      showPicker(img, img.naturalWidth, img.naturalHeight, url);
      analyze(img, img.naturalWidth, img.naturalHeight);
    };
    img.src = url;
  });

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
  function nextQuestion() {
    ready.then(function () {
      var cat = $('q-cat').value;
      var pool = DATA.quiz.filter(function (q) {
        if (cat === 'organ') return q.organ && q.organ !== 'leaf';
        return cat === 'any' || q.head === cat;
      });
      if (!pool.length) { $('q-text').textContent = 'Nessuna foto per questa categoria.'; $('q-box').hidden = false; return; }
      // foto non ancora viste per prime; quando sono finite si ricomincia
      var seen = quizSeen(), fresh = pool.filter(function (q) { return !seen[q.img]; });
      if (!fresh.length) { pool.forEach(function (q) { delete seen[q.img]; }); fresh = pool; }
      var item = fresh[Math.floor(Math.random() * fresh.length)];
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
      $('q-text').textContent = questions[item.head] + (organ ? ' (parte della pianta: ' + organ.label.toLowerCase() + ')' : '');
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
      $('q-text').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
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
    if (!right) h += explainWrong(q.item.head, q.item.label, choice);
    h += '<p><button type="button" id="q-next">Domanda successiva &rarr;</button></p>';
    $('q-exp').innerHTML = h + '</div>';
    $('q-next').addEventListener('click', nextQuestion);
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
    $('info').innerHTML = '<h2>Contributi per migliorare la rete</h2>' +
      '<p>Contributi salvati in questo telefono: <strong id="cb-count">0</strong>.</p>' +
      '<p class="muted">Inviali al responsabile del progetto (mail, WhatsApp, Drive): servono a riaddestrare la rete sulle foto reali dei campi calabresi e siciliani.</p>' +
      '<div class="row"><button type="button" id="cb-export">Invia contributi</button><button type="button" class="secondary" id="cb-clear" hidden>Svuota elenco</button></div>' +
      '<p class="muted" id="cb-export-status"></p>' +
      '<h2>Come funziona</h2>' +
      '<p>La rete neurale (estrattori DINOv2 ed EfficientNet-B0 con lettori calibrati) gira nel browser con ONNX Runtime Web. La foto non lascia il dispositivo.</p>' +
      '<table><tr><th>Lettore</th><th class="n">Test</th><th class="n">Foto di campo</th></tr>' +
      row('plant', 'Coltura') + row('disease', 'Malattia') + row('deficiency', 'Carenze') + (r.pest ? row('pest', 'Insetti (IP102)') : '') + '</table>' +
      '<p class="muted">Il valore sul test include foto di laboratorio ed è ottimistico; quello su foto di campo (PlantDoc) è più vicino all\'uso reale. Le carenze hanno pochi esempi: indicazione preliminare.</p>' +
      '<h2>Fonti dei dati</h2><ul>' +
      '<li>PlantVillage (Hughes e Salathé, 2015)</li><li>PlantDoc (Singh et al., 2020), CC BY 4.0</li>' +
      '<li>Dataset Project-AgML (UC Davis), CC BY 4.0 / MIT</li><li>iNatAg (Project-AgML), da iNaturalist</li></ul>' +
      '<p class="muted">Conoscenze agronomiche: disciplinare di produzione integrata della Regione Calabria (2023), bollettini ARSAC, schede EPPO, EFSA, Università Mediterranea di Reggio Calabria, Università di Bari. Elenco completo e livello di verifica nel repository.</p>' +
      '<h2>Avvertenze</h2><p class="muted">Strumento di supporto alla decisione, non una diagnosi. Per virus, viroidi, batteri e nematodi serve la conferma di laboratorio. Dosi e compatibilità dei prodotti sono quelle dell\'etichetta autorizzata.</p>' +
      '<p class="muted">Motore: ONNX Runtime Web 1.20.1 (licenza MIT). Codice: <a href="https://github.com/ringhiosaverio-code/riconoscimentopiantemalattiecarenze" target="_blank" rel="noopener">repository</a>, licenza Apache-2.0.</p>';
  }
})();
