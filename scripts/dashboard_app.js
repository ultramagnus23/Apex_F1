const D = JSON.parse(document.getElementById('data').textContent);
const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = (x, d = 2) => (x == null || Number.isNaN(x)) ? 'n/a' : Number(x).toFixed(d);
const pct = (x) => (x == null || Number.isNaN(x)) ? 'n/a' : Math.round(x * 100) + '%';
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const NS = 'http://www.w3.org/2000/svg';

/* ------------------------------------------------------------ chart kit */
const tip = document.createElement('div');
tip.className = 'tip';
document.body.appendChild(tip);
function showTip(e, html) {
  tip.innerHTML = html;
  tip.style.display = 'block';
  const w = tip.offsetWidth;
  const x = Math.min(e.clientX + 14, window.innerWidth - w - 8);
  tip.style.left = Math.max(8, x) + 'px';
  tip.style.top = (e.clientY + 14) + 'px';
}
function hideTip() { tip.style.display = 'none'; }
function hover(el, html) {
  el.addEventListener('mouseenter', (e) => showTip(e, html));
  el.addEventListener('mousemove', (e) => showTip(e, html));
  el.addEventListener('mouseleave', hideTip);
  el.setAttribute('tabindex', '0');
  el.addEventListener('focus', () => {
    const r = el.getBoundingClientRect();
    showTip({ clientX: r.left + r.width / 2, clientY: r.top }, html);
  });
  el.addEventListener('blur', hideTip);
}
function mk(tag, attrs, parent) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}
function txt(parent, x, y, s, attrs) {
  const t = mk('text', Object.assign({ x, y, fill: css('--text-2'), 'font-size': 12 }, attrs || {}), parent);
  t.textContent = s;
  return t;
}
function niceTicks(lo, hi, n) {
  const span = hi - lo || 1;
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(Math.round(v / step) * step);
  return out;
}
function hexToRgb(h) { const n = parseInt(h.replace('#', ''), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function lerpColor(a, b, t) {
  const x = hexToRgb(a), y = hexToRgb(b);
  return 'rgb(' + x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(',') + ')';
}
function svgIn(el, h) {
  el.innerHTML = '';
  const w = Math.max(320, el.clientWidth || 640);
  const svg = mk('svg', { viewBox: `0 0 ${w} ${h}`, width: '100%', height: h, role: 'img' }, el);
  return { svg, w, h };
}
function legend(el, items) {
  const div = document.createElement('div');
  div.className = 'legend';
  div.innerHTML = items.map((i) => `<span><i style="background:${i.hollow ? 'transparent' : i.color};border:2px solid ${i.color}"></i>${esc(i.name)}</span>`).join('');
  el.appendChild(div);
}

/* Horizontal dot plot with interval whiskers: rows = [{label, x, lo, hi, tip}] */
function dotRows(el, rows, xTitle, color) {
  const rowH = 24, top = 8, bot = 44, left = 52, right = 20;
  const { svg, w, h } = svgIn(el, top + rows.length * rowH + bot);
  const lo = Math.min(0, ...rows.map((r) => r.lo)), hi = Math.max(...rows.map((r) => r.hi));
  const sx = (v) => left + (v - lo) / (hi - lo || 1) * (w - left - right);
  niceTicks(lo, hi, 6).forEach((t) => {
    mk('line', { x1: sx(t), x2: sx(t), y1: top, y2: h - bot, stroke: css('--grid') }, svg);
    txt(svg, sx(t), h - bot + 16, String(+t.toFixed(3)), { 'text-anchor': 'middle' });
  });
  txt(svg, (left + w - right) / 2, h - 6, xTitle, { 'text-anchor': 'middle' });
  rows.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    txt(svg, left - 8, y + 4, r.label, { 'text-anchor': 'end' });
    mk('line', { x1: sx(r.lo), x2: sx(r.hi), y1: y, y2: y, stroke: color, 'stroke-width': 2, 'stroke-linecap': 'round' }, svg);
    const hit = mk('g', {}, svg);
    mk('rect', { x: left, y: y - rowH / 2, width: w - left - right, height: rowH, fill: 'transparent' }, hit);
    mk('circle', { cx: sx(r.x), cy: y, r: 5, fill: color, stroke: css('--surface'), 'stroke-width': 2 }, hit);
    hover(hit, r.tip);
  });
}

/* Heatmap: labels (square matrix), matrix values in 0..1 */
function heat(el, labels, m) {
  const n = labels.length, left = 40, top = 8, bot = 36;
  const w0 = Math.max(320, el.clientWidth || 640);
  const cell = Math.max(14, Math.min(30, Math.floor((w0 - left - 70) / n)));
  const { svg } = svgIn(el, top + n * cell + bot);
  svg.setAttribute('width', left + n * cell + 70);
  svg.setAttribute('viewBox', `0 0 ${left + n * cell + 70} ${top + n * cell + bot}`);
  svg.removeAttribute('height');
  svg.style.maxWidth = '100%';
  svg.style.height = 'auto';
  const lo = css('--seq-lo'), hi = css('--seq-hi');
  labels.forEach((l, i) => {
    txt(svg, left - 6, top + i * cell + cell / 2 + 4, l, { 'text-anchor': 'end', 'font-size': 10 });
    const t = txt(svg, left + i * cell + cell / 2, top + n * cell + 10, l, { 'text-anchor': 'end', 'font-size': 10 });
    t.setAttribute('transform', `rotate(-60 ${left + i * cell + cell / 2} ${top + n * cell + 10})`);
  });
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const v = m[i][j];
    const r = mk('rect', { x: left + j * cell + 1, y: top + i * cell + 1, width: cell - 2, height: cell - 2, rx: 2,
      fill: i === j ? css('--surface-2') : lerpColor(lo, hi, v) }, svg);
    if (i !== j) hover(r, `<b>${esc(labels[i])}</b> faster than <b>${esc(labels[j])}</b>: ${pct(v)}`);
  }
  const lx = left + n * cell + 16;
  for (let k = 0; k < 40; k++) mk('rect', { x: lx, y: top + k * 4, width: 12, height: 4, fill: lerpColor(hi, lo, k / 39) }, svg);
  txt(svg, lx + 18, top + 10, '100%', { 'font-size': 10 });
  txt(svg, lx + 18, top + 160, '0%', { 'font-size': 10 });
}

/* Category dot plot: cats [..], series [{name,color,points:[{cat,y,hollow,tip}]}], ref line optional */
function dotCats(el, cats, series, yTitle, opts) {
  opts = opts || {};
  const left = 56, right = 16, top = 12, bot = 100, h = 400;
  const { svg, w } = svgIn(el, h);
  const ys = series.flatMap((s) => s.points.map((p) => p.y));
  const y0 = opts.yMin != null ? opts.yMin : 0;
  const y1 = opts.yMax != null ? opts.yMax : Math.max(...ys, 0.1) * 1.08;
  const sy = (v) => top + (1 - (v - y0) / (y1 - y0)) * (h - top - bot);
  const sx = (i) => left + (i + 0.5) / cats.length * (w - left - right);
  niceTicks(y0, y1, 5).forEach((t) => {
    mk('line', { x1: left, x2: w - right, y1: sy(t), y2: sy(t), stroke: css('--grid') }, svg);
    txt(svg, left - 8, sy(t) + 4, opts.pct ? pct(t) : String(+t.toFixed(2)), { 'text-anchor': 'end' });
  });
  const yt = txt(svg, 14, (top + h - bot) / 2, yTitle, { 'text-anchor': 'middle' });
  yt.setAttribute('transform', `rotate(-90 14 ${(top + h - bot) / 2})`);
  cats.forEach((c, i) => {
    const t = txt(svg, sx(i), h - bot + 14, c, { 'text-anchor': 'end', 'font-size': 11 });
    t.setAttribute('transform', `rotate(-50 ${sx(i)} ${h - bot + 14})`);
  });
  if (opts.ref != null) {
    mk('line', { x1: left, x2: w - right, y1: sy(opts.ref), y2: sy(opts.ref), stroke: css('--text-3'), 'stroke-dasharray': '5 4' }, svg);
    txt(svg, w - right, sy(opts.ref) - 5, opts.refLabel || '', { 'text-anchor': 'end', 'font-size': 11 });
  }
  const off = series.length > 1 ? 7 : 0;
  series.forEach((s, k) => s.points.forEach((p) => {
    const i = cats.indexOf(p.cat);
    if (i < 0 || p.y == null) return;
    const g = mk('g', {}, svg);
    const cx = sx(i) + (k - (series.length - 1) / 2) * off * 1.6;
    mk('circle', { cx: cx, cy: sy(p.y), r: 11, fill: 'transparent' }, g);
    mk('circle', { cx: cx, cy: sy(p.y), r: 5, fill: p.hollow ? css('--surface') : s.color, stroke: s.color, 'stroke-width': 2 }, g);
    hover(g, p.tip);
  }));
  if (series.length > 1) legend(el, series.map((s) => ({ name: s.name, color: s.color })));
}

/* Vertical bars: values[], x as fraction centres */
function bars(el, values, xTitle, yTitle, color) {
  const left = 52, right = 16, top = 10, bot = 44, h = 300;
  const { svg, w } = svgIn(el, h);
  const mx = Math.max(1, ...values);
  const sy = (v) => top + (1 - v / mx) * (h - top - bot);
  niceTicks(0, mx, 5).forEach((t) => {
    mk('line', { x1: left, x2: w - right, y1: sy(t), y2: sy(t), stroke: css('--grid') }, svg);
    txt(svg, left - 8, sy(t) + 4, String(t), { 'text-anchor': 'end' });
  });
  const bw = (w - left - right) / values.length;
  values.forEach((v, i) => {
    const x = left + i * bw + 1.5;
    const g = mk('g', {}, svg);
    mk('rect', { x: left + i * bw, y: top, width: bw, height: h - top - bot, fill: 'transparent' }, g);
    if (v > 0) mk('path', { d: `M${x},${h - bot} V${sy(v) + 3} Q${x},${sy(v)} ${x + 3},${sy(v)} H${x + bw - 6} Q${x + bw - 3},${sy(v)} ${x + bw - 3},${sy(v) + 3} V${h - bot} Z`, fill: color }, g);
    hover(g, `lap position ${pct(i / values.length)} to ${pct((i + 1) / values.length)}<br>${v} events`);
  });
  [0, 0.25, 0.5, 0.75, 1].forEach((f) => txt(svg, left + f * (w - left - right), h - bot + 16, pct(f), { 'text-anchor': 'middle' }));
  txt(svg, (left + w - right) / 2, h - 6, xTitle, { 'text-anchor': 'middle' });
  const yt = txt(svg, 14, (top + h - bot) / 2, yTitle, { 'text-anchor': 'middle' });
  yt.setAttribute('transform', `rotate(-90 14 ${(top + h - bot) / 2})`);
}

function tile(k, v, n) { return `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${v}</div>${n ? `<div class="n">${esc(n)}</div>` : ''}</div>`; }
function table(el, head, rows) {
  el.innerHTML = '<thead><tr>' + head.map((x) => `<th>${esc(x)}</th>`).join('') + '</tr></thead><tbody>' +
    rows.map((r) => '<tr>' + r.map((c) => `<td>${esc(c)}</td>`).join('') + '</tr>').join('') + '</tbody>';
}
function fill(sel, items) { sel.innerHTML = items.map((it) => `<option value="${esc(it.v)}">${esc(it.l)}</option>`).join(''); }

/* ------------------------------------------------------------ tabs and theme */
let current = 'pace';
document.querySelectorAll('nav button').forEach((b) => b.addEventListener('click', () => {
  current = b.dataset.tab;
  document.querySelectorAll('nav button').forEach((x) => x.setAttribute('aria-selected', x === b));
  ['pace', 'ers', 'check', 'about'].forEach((t) => { $('tab-' + t).hidden = t !== current; });
  render();
}));
try { const s = localStorage.getItem('apex-theme'); if (s) document.documentElement.dataset.theme = s; } catch (e) { /* storage blocked */ }
$('theme').addEventListener('click', () => {
  const dark = getComputedStyle(document.documentElement).colorScheme === 'dark';
  const next = dark ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('apex-theme', next); } catch (e) { /* storage blocked */ }
  render();
});
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => render());
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(render, 150); });

/* ------------------------------------------------------------ race pace */
const paceYears = Object.keys(D.pace).sort();
fill($('pace-year'), paceYears.map((y) => ({ v: y, l: y })));
const paceRaces = () => D.pace[$('pace-year').value] || [];
function fillRaces() {
  fill($('pace-race'), paceRaces().map((r, i) => ({ v: i, l: `${r.meta.location} (${String(r.meta.date).slice(0, 10)})${r.status !== 'OK' ? ' - not modelled' : ''}` })));
}
function pickFirstOk() {
  const i = paceRaces().findIndex((r) => r.status === 'OK');
  if (i >= 0) $('pace-race').value = String(i);
}
$('pace-year').addEventListener('change', () => { fillRaces(); pickFirstOk(); render(); });
$('pace-race').addEventListener('change', render);

function renderPace() {
  const r = paceRaces()[Number($('pace-race').value)];
  if (!r) return;
  $('pace-banner').innerHTML = r.status === 'OK' ? '' :
    `<div class="banner"><strong>Not modelled.</strong> ${esc(r.status_reasons.join('; '))}. The numbers are shown for transparency and should not be used.</div>`;
  const v = r.validation;
  $('pace-tiles').innerHTML =
    tile('Clean laps used', r.clean_laps, `${r.exclusions.FLAG} flag, ${r.exclusions.OUTLIER} outlier, ${r.exclusions.PIT_IN + r.exclusions.PIT_OUT} pit laps excluded`) +
    tile('Lap-time noise (sigma)', fmt(r.noise_sigma_s) + ' s', 'after adjustments') +
    tile('Whole-stint holdout', pct(v.stint.coverage), 'coverage; target ' + pct(v.stint.nominal)) +
    tile('Reference', esc(r.reference.compound), `fresh tyre, lap ${r.reference.lap}`);
  const ds = r.drivers.slice().sort((a, b) => a.mean_s - b.mean_s);
  const m0 = ds[0].mean_s;
  dotRows($('pace-chart'), ds.map((d) => ({
    label: d.code, x: d.mean_s - m0, lo: d.lo_s - m0, hi: d.hi_s - m0,
    tip: `<b>${esc(d.code)}</b><br>pace ${fmt(d.mean_s, 3)} s<br>90% interval ${fmt(d.lo_s)} to ${fmt(d.hi_s)} s<br>${d.n_laps} clean laps`
  })), 'Gap to fastest driver (s), with 90% interval', css('--s1'));
  heat($('pace-heat'), r.prob_faster.drivers, r.prob_faster.matrix);
  table($('pace-params'), ['Parameter', 'Mean', '90% interval', 'Unit', 'Note'],
    r.parameters.map((p) => [p.name, fmt(p.mean, 3), `${fmt(p.lo, 3)} to ${fmt(p.hi, 3)}`, p.unit, p.note]));
  table($('pace-table'), ['Driver', 'Pace (s)', 'Low', 'High', 'Clean laps', 'Mean rank'],
    ds.map((d) => [d.code, fmt(d.mean_s, 3), fmt(d.lo_s, 2), fmt(d.hi_s, 2), d.n_laps, fmt(d.rank_mean, 1)]));
}

/* ------------------------------------------------------------ ERS */
const ersYears = [...new Set(D.ers.sessions.map((s) => String(s.year)))].sort();
fill($('ers-year'), ersYears.map((y) => ({ v: y, l: y })));
const ersSessions = () => D.ers.sessions.filter((s) => String(s.year) === $('ers-year').value);
function fillSessions() { fill($('ers-session'), ersSessions().map((s) => ({ v: s.location, l: s.location + (s.wet ? ' (wet)' : '') }))); }
$('ers-year').addEventListener('change', () => { fillSessions(); render(); });
$('ers-session').addEventListener('change', render);
$('confounders').textContent = D.ers.confounders.join('; ');

function renderErs() {
  const eras = D.ers.summary.years || {};
  const con = D.ers.summary.era_contrast_2026_minus_2025;
  let t = '';
  Object.keys(eras).sort().forEach((y) => {
    const e = eras[y];
    t += tile(`${y}: events per lap`, fmt(e.events_per_lap), `${e.sessions} dry sessions, ${pct(e.share_laps_with_event)} of laps have one`);
  });
  if (con) {
    const c = con.events_per_lap;
    t += tile('2026 minus 2025', (c.diff >= 0 ? '+' : '') + fmt(c.diff), `events per lap; 95% interval ${fmt(c.lo)} to ${fmt(c.hi)}, resampling sessions`);
  }
  const pc = D.ers.summary.paired_circuits;
  if (pc) t += tile('Same circuit, both years', `${pc.higher_in_2026} of ${pc.circuits}`, `2026 higher; ${pc.lower_in_2026} lower; Wilcoxon p = ${pc.wilcoxon_p.toFixed(3)}`);
  $('ers-era').innerHTML = t;

  const colors = { '2025': css('--s1'), '2026': css('--s2') };
  const locs = [...new Set(D.ers.sessions.slice().sort((a, b) => String(a.date).localeCompare(String(b.date))).map((s) => s.location))];
  const series = ersYears.map((y) => ({
    name: y, color: colors[y] || css('--s3'),
    points: D.ers.sessions.filter((s) => String(s.year) === y).map((s) => ({
      cat: s.location, y: s.events_per_lap, hollow: s.wet,
      tip: `<b>${esc(s.location)} ${y}</b>${s.wet ? ' (wet)' : ''}<br>${fmt(s.events_per_lap)} events per lap<br>${s.laps} laps<br>repeat lift ${s.repeat_lift == null ? 'n/a' : fmt(s.repeat_lift, 1) + 'x'}`
    }))
  }));
  dotCats($('ers-compare'), locs, series, 'Events per lap');

  const s = ersSessions().find((x) => x.location === $('ers-session').value);
  if (!s) return;
  $('ers-tiles').innerHTML =
    tile('Laps analysed', s.laps, `${s.laps_with_event} with at least one event`) +
    tile('Events per lap', fmt(s.events_per_lap)) +
    tile('Share of full-throttle time', pct(s.clip_share_mean), 'spent decelerating') +
    tile('Repeat lift', s.repeat_lift == null ? 'n/a' : fmt(s.repeat_lift, 1) + 'x', 'chance level: ' + pct(s.repeat_chance)) +
    tile('Median deceleration', s.median_decel_ms2 == null ? 'n/a' : fmt(s.median_decel_ms2) + ' m/s2');
  bars($('ers-hist'), D.ers.hist[`${s.year}|${s.location}`] || [], 'Position along the lap (fraction of distance)', 'Events (all analysed laps)', colors[String(s.year)] || css('--s1'));
  table($('ers-table'), ['Circuit', 'Year', 'Wet', 'Laps', 'Events/lap', 'Laps with event', 'Repeat lift', 'Median decel'],
    D.ers.sessions.slice().sort((a, b) => (a.year - b.year) || String(a.date).localeCompare(String(b.date))).map((x) =>
      [x.location, x.year, x.wet ? 'yes' : 'no', x.laps, fmt(x.events_per_lap), x.laps_with_event, x.repeat_lift == null ? 'n/a' : fmt(x.repeat_lift, 1), x.median_decel_ms2 == null ? 'n/a' : fmt(x.median_decel_ms2)]));
}

/* ------------------------------------------------------------ validation */
fill($('check-year'), paceYears.map((y) => ({ v: y, l: y })));
$('check-year').addEventListener('change', render);
function renderCheck() {
  const y = $('check-year').value;
  const rs = (D.pace[y] || []).slice().sort((a, b) => String(a.meta.date).localeCompare(String(b.meta.date)));
  const ok = rs.filter((r) => r.status === 'OK');
  const mean = (k) => ok.reduce((a, r) => a + r.validation[k].coverage, 0) / Math.max(ok.length, 1);
  $('check-tiles').innerHTML =
    tile('Races modelled', `${ok.length} of ${rs.length}`, 'wet or very noisy races are not modelled') +
    tile('Random-lap holdout', pct(mean('random')), 'mean coverage, target 90%') +
    tile('Whole-stint holdout', pct(mean('stint')), 'mean coverage, target 90%') +
    tile('Forward prediction', pct(mean('forward')), 'undercovers: not a forecast tool');
  const defs = [['random', 'Random laps held out', css('--s1')], ['stint', 'Whole stints held out', css('--s2')], ['forward', 'Last 20% of race predicted', css('--s3')]];
  const series = defs.map(([k, name, c]) => ({
    name, color: c,
    points: rs.map((r) => ({ cat: r.meta.location, y: r.validation[k].coverage, hollow: r.status !== 'OK',
      tip: `<b>${esc(r.meta.location)}</b>${r.status !== 'OK' ? ' (not modelled)' : ''}<br>${esc(name)}: ${pct(r.validation[k].coverage)}` }))
  }));
  dotCats($('check-chart'), rs.map((r) => r.meta.location), series, 'Held-out laps inside 90% interval', { yMin: 0.3, yMax: 1.02, pct: true, ref: 0.9, refLabel: '90% target' });
  table($('check-table'), ['Race', 'Status', 'Clean laps', 'Random', 'Whole stint', 'Forward', 'Noise (s)'],
    rs.map((r) => [r.meta.location, r.status, r.clean_laps, pct(r.validation.random.coverage), pct(r.validation.stint.coverage), pct(r.validation.forward.coverage), fmt(r.noise_sigma_s)]));
}

function render() {
  hideTip();
  if (current === 'pace') renderPace();
  else if (current === 'ers') renderErs();
  else if (current === 'check') renderCheck();
}
$('built').textContent = D.note;
fillRaces();
pickFirstOk();
fillSessions();
const firstDry = ersSessions().find((s) => !s.wet);
if (firstDry) $('ers-session').value = firstDry.location;
render();
