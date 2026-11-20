/* Preparazione della botte: stessa logica di src/plantcare/sprayer.py (verificata da test).
   Calcolatore deterministico, non una rete neurale. L'etichetta del prodotto prevale sempre. */
(function (root) {
  'use strict';
  var PER_HL = { 'g/hl': 'g', 'ml/hl': 'ml' };
  var PER_HA = { 'g/ha': ['g', 1], 'kg/ha': ['g', 1000], 'ml/ha': ['ml', 1], 'l/ha': ['ml', 1000] };
  var DRY = ['WG', 'WP', 'SG', 'WSB'];
  var LEGAL_NOTE = "Le dosi, i limiti d'impiego, gli intervalli di sicurezza e le compatibilità sono quelli dell'etichetta " +
    "autorizzata del prodotto, che prevale su qualunque calcolo. L'uso professionale di prodotti fitosanitari " +
    "richiede il certificato di abilitazione (D.Lgs. 150/2012) e i dispositivi di protezione indicati in etichetta.";

  function round(x, d) { var f = Math.pow(10, d); return Math.round(x * f) / f; }
  function fmt(value, unit) {
    if (value >= 1000) return { value: round(value / 1000, 3), unit: unit === 'g' ? 'kg' : 'l' };
    return { value: round(value, 1), unit: unit };
  }

  function computeTank(tankL, products, waterLHa, temperatureC, copperAlreadyKgHa, rules) {
    var res = { products: [], order: [], order_sources: [], area_ha: null, copper_kg_ha: null,
                warnings: [], errors: [], procedure: [], legal_note: LEGAL_NOTE };
    if (!(tankL > 0)) throw new Error('Il volume della botte deve essere maggiore di zero.');
    if (waterLHa != null && !(waterLHa > 0)) throw new Error("Il volume d'acqua per ettaro deve essere maggiore di zero.");
    if (!products || !products.length) throw new Error('Inserire almeno un prodotto.');
    if (waterLHa) res.area_ha = round(tankL / waterLHa, 4);

    var copperGHa = 0;
    products.forEach(function (p) {
      var units = Object.keys(PER_HL).concat(Object.keys(PER_HA), ['%']);
      if (units.indexOf(p.unit) < 0) throw new Error(p.name + ': unità di dose non valida (' + p.unit + ').');
      if (!(p.dose > 0)) throw new Error(p.name + ': la dose deve essere maggiore di zero.');
      var row = { name: p.name, dose: p.dose, unit: p.unit, formulation: p.formulation || 'OTHER', category: p.category || 'altro' };
      var base, amount, perHa = null;
      if (PER_HL[p.unit]) {
        base = PER_HL[p.unit]; amount = p.dose * tankL / 100;
        if (waterLHa) perHa = p.dose * waterLHa / 100;
      } else if (p.unit === '%') {
        base = DRY.indexOf(p.formulation) >= 0 ? 'g' : 'ml';
        amount = p.dose / 100 * tankL * 1000;
        if (waterLHa) perHa = p.dose / 100 * waterLHa * 1000;
      } else {
        base = PER_HA[p.unit][0];
        if (!waterLHa) { res.errors.push(p.name + ": la dose è per ettaro, serve il volume d'acqua per ettaro per calcolarla."); return; }
        perHa = p.dose * PER_HA[p.unit][1]; amount = perHa * tankL / waterLHa;
      }
      row.amount = fmt(amount, base);
      if (perHa != null) row.per_ha = fmt(perHa, base);
      if (p.label_max != null && p.dose > p.label_max) {
        res.errors.push(p.name + ': la dose ' + p.dose + ' ' + p.unit + ' supera la dose massima di etichetta (' +
          p.label_max + ' ' + p.unit + '). Non preparare la botte con questa dose.');
        row.over_label = true;
      }
      if (row.category === 'rame' && p.copper_g_per_unit && perHa != null) copperGHa += perHa / 1000 * p.copper_g_per_unit;
      res.products.push(row);
    });

    if (copperGHa) {
      var c = rules.copper;
      res.copper_kg_ha = round(copperGHa / 1000, 3);
      var total = res.copper_kg_ha + (copperAlreadyKgHa || 0);
      var msg = 'Questo trattamento apporta ' + res.copper_kg_ha + ' kg/ha di rame metallo' +
        (copperAlreadyKgHa ? "; con quelli già fatti quest'anno si arriva a " + round(total, 3) + ' kg/ha.' : '.') + ' ' + c.text;
      res.warnings.push({ level: total > c.avg_year_kg_ha ? 'attenzione' : 'info', text: msg, sources: c.sources });
    }
    var cats = {};
    products.forEach(function (p) { cats[p.category || 'altro'] = true; });
    rules.pairs.forEach(function (r) {
      if (cats[r.categories[0]] && cats[r.categories[1]]) res.warnings.push({ level: 'incompatibile', text: r.text, sources: r.sources });
    });
    if (temperatureC != null) {
      rules.temperature.forEach(function (t) {
        if (cats[t.category] && temperatureC >= t.max_c) res.warnings.push({ level: 'attenzione', text: t.text, sources: t.sources });
      });
    }
    var orderIds = rules.formulation_order.order.map(function (f) { return f.id; });
    var labels = {}; rules.formulation_order.order.forEach(function (f) { labels[f.id] = f.label; });
    var first = {};
    (rules.order_rules || []).forEach(function (r) {
      if (cats[r.when_category]) {
        r.move_first_formulations.forEach(function (f) { first[f] = true; });
        if (products.some(function (p) { return first[p.formulation]; })) res.warnings.push({ level: 'ordine', text: r.text, sources: r.sources });
      }
    });
    var sorted = products.map(function (p, i) { return { p: p, i: i }; }).sort(function (a, b) {
      function key(p) { var f = orderIds.indexOf(p.formulation) >= 0 ? p.formulation : 'OTHER'; return [first[f] ? 0 : 1, orderIds.indexOf(f)]; }
      var ka = key(a.p), kb = key(b.p);
      return ka[0] - kb[0] || ka[1] - kb[1] || a.i - b.i;
    });
    sorted.forEach(function (x, i) { res.order.push({ step: i + 1, name: x.p.name, formulation: labels[x.p.formulation] || x.p.formulation }); });
    res.order_sources = rules.formulation_order.sources;
    res.procedure = rules.procedure;
    return res;
  }

  var api = { computeTank: computeTank, LEGAL_NOTE: LEGAL_NOTE };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Sprayer = api;
})(this);
