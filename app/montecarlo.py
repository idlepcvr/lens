"""PRISM Monte Carlo page — standalone simulator, on the shared LENS design system."""

from .theme import shell

# ── page-specific CSS (uses shared tokens from /assets/lens.css) ──────────────
_HEAD = r"""<style>
.mc-sub{font-family:var(--mono);font-size:12px;color:var(--dim);margin:-4px 0 18px}
.mc-banner{display:none;background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:10px 12px;margin-bottom:16px;font-family:var(--mono);font-size:11px;color:var(--dim)}
.mc-banner a{color:var(--accent);margin-left:8px}
.mc-banner b{color:var(--ink)}
.mc-controls{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.mc-ctl{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.mc-ctl label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-bottom:6px}
.mc-ctl input{width:100%;background:transparent;border:none;color:var(--ink);font-family:var(--mono);font-size:16px;font-weight:700;outline:none}
.mc-ctl select{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);padding:7px 8px;font-family:var(--mono);font-size:12px;outline:none}
.run-btn{width:100%;background:var(--accent);color:var(--bg);border:none;border-radius:11px;padding:14px;
  font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;margin-bottom:18px;transition:filter .15s}
.run-btn:hover{filter:brightness(1.1)}
.run-btn:active{transform:scale(.98)}
.mc-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:18px}
.mc-stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px}
.mc-stat .l{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin-bottom:4px}
.mc-stat .v{font-family:var(--mono);font-size:18px;font-weight:700}
.mc-stat .v.g{color:var(--long)} .mc-stat .v.r{color:var(--short)} .mc-stat .v.a{color:var(--amber)} .mc-stat .v.acc{color:var(--accent)}
.mc-clabel{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin-bottom:8px}
canvas{width:100%;border-radius:10px;background:var(--panel);border:1px solid var(--line);display:block;margin-bottom:12px}
.mc-legend{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:18px}
.mc-legend .it{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;color:var(--dim)}
.mc-legend .dot{width:8px;height:8px;border-radius:50%}
.mc-ruin{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:8px;
  display:flex;justify-content:space-between;align-items:center}
.mc-ruin .l{font-family:var(--mono);font-size:11px;color:var(--dim)}
.mc-ruin .v{font-family:var(--mono);font-size:14px;font-weight:700;color:var(--short)}
.mc-ruin .v.safe{color:var(--long)}
</style>"""

_BODY = r"""
<div class="mc-sub">BTC perp · 4H · systematic — 1,000 simulated paths</div>

<div id="seed-banner" class="mc-banner">
  <span id="seed-text"></span>
  <a href="#" id="seed-reset">reset defaults ↺</a>
</div>

<div class="mc-ctl" style="margin-bottom:10px">
  <label>Seed inputs from</label>
  <select id="src"><option value="live">Live trades (realized)</option></select>
</div>

<div class="mc-controls">
  <div class="mc-ctl"><label>Starting Capital ($)</label><input type="number" id="capital" value="250"></div>
  <div class="mc-ctl"><label>Weeks</label><input type="number" id="weeks" value="22"></div>
  <div class="mc-ctl"><label>Win Rate (%)</label><input type="number" id="winrate" value="44"></div>
  <div class="mc-ctl"><label>R:R (reward)</label><input type="number" id="rr" value="4"></div>
  <div class="mc-ctl"><label>Risk per Trade (%)</label><input type="number" id="risk" value="10"></div>
  <div class="mc-ctl"><label>Trades per Week</label><input type="number" id="tpw" value="5"></div>
</div>

<button class="run-btn" onclick="runSimulation()">▶ Run 1,000 Simulations</button>

<div class="mc-stats" id="stats" style="display:none">
  <div class="mc-stat"><div class="l">Median Final</div><div class="v g" id="s-median">—</div></div>
  <div class="mc-stat"><div class="l">p90 (best 10%)</div><div class="v acc" id="s-p90">—</div></div>
  <div class="mc-stat"><div class="l">p10 (worst 10%)</div><div class="v a" id="s-p10">—</div></div>
  <div class="mc-stat"><div class="l">Theoretical EV</div><div class="v acc" id="s-ev">—</div></div>
</div>

<div id="charts" style="display:none">
  <div class="mc-clabel">Equity Paths — percentile bands</div>
  <canvas id="pathChart" height="200"></canvas>

  <div class="mc-legend">
    <div class="it"><div class="dot" style="background:#1fd989"></div>p90</div>
    <div class="it"><div class="dot" style="background:#5b9dff"></div>median</div>
    <div class="it"><div class="dot" style="background:#f6ad3c"></div>p10</div>
    <div class="it"><div class="dot" style="background:#ff5468"></div>p5 (ruin zone)</div>
  </div>

  <div class="mc-clabel">Final Balance Distribution</div>
  <canvas id="distChart" height="140"></canvas>

  <div class="mc-clabel">Ruin &amp; Target Probability</div>
  <div id="ruin-stats"></div>
</div>
"""

_SCRIPT = r"""
function fmt(n) {
  if (n >= 1e6) return '$' + (n/1e6).toFixed(2) + 'M';
  if (n >= 1e3) return '$' + (n/1e3).toFixed(1) + 'k';
  return '$' + n.toFixed(0);
}

function runSimulation() {
  const capital = parseFloat(document.getElementById('capital').value);
  const weeks = parseInt(document.getElementById('weeks').value);
  const winRate = parseFloat(document.getElementById('winrate').value) / 100;
  const rr = parseFloat(document.getElementById('rr').value);
  const riskPct = parseFloat(document.getElementById('risk').value) / 100;
  const tpw = parseInt(document.getElementById('tpw').value);

  const N = 1000;
  const totalTrades = weeks * tpw;
  const winMult = 1 + riskPct * rr;
  const lossMult = 1 - riskPct;

  const allPaths = [];
  const finalBalances = [];

  for (let s = 0; s < N; s++) {
    let bal = capital;
    const path = [bal];
    for (let t = 0; t < totalTrades; t++) {
      if (Math.random() < winRate) { bal *= winMult; }
      else { bal *= lossMult; }
      if (bal < 1) { bal = 0; break; }
    }
    allPaths.push(path);
    finalBalances.push(bal);
  }

  const weeklyPaths = { p5: [], p10: [], p50: [], p90: [] };
  for (let w = 0; w <= weeks; w++) {
    const vals = [];
    for (let s = 0; s < N; s++) {
      let bal = capital;
      const trades = w * tpw;
      for (let t = 0; t < trades; t++) {
        if (Math.random() < winRate) bal *= winMult;
        else bal *= lossMult;
        if (bal < 1) { bal = 0; break; }
      }
      vals.push(bal);
    }
    vals.sort((a, b) => a - b);
    weeklyPaths.p5.push(vals[Math.floor(N * 0.05)]);
    weeklyPaths.p10.push(vals[Math.floor(N * 0.10)]);
    weeklyPaths.p50.push(vals[Math.floor(N * 0.50)]);
    weeklyPaths.p90.push(vals[Math.floor(N * 0.90)]);
  }

  finalBalances.sort((a, b) => a - b);
  const median = finalBalances[Math.floor(N * 0.5)];
  const p10 = finalBalances[Math.floor(N * 0.1)];
  const p90 = finalBalances[Math.floor(N * 0.9)];

  const ev = (winRate * winMult + (1 - winRate) * lossMult);
  const evFinal = capital * Math.pow(ev, totalTrades);

  document.getElementById('s-median').textContent = fmt(median);
  document.getElementById('s-p90').textContent = fmt(p90);
  document.getElementById('s-p10').textContent = fmt(p10);
  document.getElementById('s-ev').textContent = fmt(evFinal);

  document.getElementById('stats').style.display = 'grid';
  document.getElementById('charts').style.display = 'block';

  const ruinCount = finalBalances.filter(b => b < capital * 0.1).length;
  const targetCount = finalBalances.filter(b => b >= 10000).length;
  const target50k = finalBalances.filter(b => b >= 50000).length;

  document.getElementById('ruin-stats').innerHTML = `
    <div class="mc-ruin">
      <span class="l">P(ruin, &lt;10% start)</span>
      <span class="v ${ruinCount/N < 0.15 ? 'safe' : ''}">${(ruinCount/N*100).toFixed(1)}%</span>
    </div>
    <div class="mc-ruin">
      <span class="l">P(reach $10k)</span>
      <span class="v safe">${(targetCount/N*100).toFixed(1)}%</span>
    </div>
    <div class="mc-ruin">
      <span class="l">P(reach $50k)</span>
      <span class="v safe">${(target50k/N*100).toFixed(1)}%</span>
    </div>
  `;

  drawPathChart(weeklyPaths, weeks, capital);
  drawDistChart(finalBalances, capital);
}

function drawPathChart(paths, weeks, capital) {
  const canvas = document.getElementById('pathChart');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.parentElement.offsetWidth;
  const H = 200;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const pad = { t: 12, r: 12, b: 28, l: 52 };
  const cw = W - pad.l - pad.r;
  const ch = H - pad.t - pad.b;

  const allVals = [...paths.p90, ...paths.p50, ...paths.p10, ...paths.p5];
  const maxVal = Math.max(...allVals);
  const minVal = 0;

  const xScale = i => pad.l + (i / weeks) * cw;
  const yScale = v => pad.t + ch - ((v - minVal) / (maxVal - minVal)) * ch;

  ctx.strokeStyle = '#192232';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(pad.l + cw, y);
    ctx.stroke();

    const val = maxVal * (1 - i/4);
    ctx.fillStyle = '#828ea6';
    ctx.font = '9px JetBrains Mono, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(fmt(val), pad.l - 4, y + 3);
  }

  ctx.fillStyle = '#828ea6';
  ctx.font = '9px JetBrains Mono, monospace';
  ctx.textAlign = 'center';
  for (let w = 0; w <= weeks; w += Math.ceil(weeks / 5)) {
    ctx.fillText('W' + w, xScale(w), H - 6);
  }

  const drawLine = (data, color, width) => {
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = 'round';
    data.forEach((v, i) => {
      if (i === 0) ctx.moveTo(xScale(i), yScale(v));
      else ctx.lineTo(xScale(i), yScale(v));
    });
    ctx.stroke();
  };

  ctx.beginPath();
  paths.p90.forEach((v, i) => {
    if (i === 0) ctx.moveTo(xScale(i), yScale(v));
    else ctx.lineTo(xScale(i), yScale(v));
  });
  [...paths.p10].reverse().forEach((v, i) => {
    ctx.lineTo(xScale(weeks - i), yScale(v));
  });
  ctx.closePath();
  ctx.fillStyle = 'rgba(91, 157, 255, 0.07)';
  ctx.fill();

  drawLine(paths.p5,  '#ff5468', 1.5);
  drawLine(paths.p10, '#f6ad3c', 1.5);
  drawLine(paths.p50, '#5b9dff', 2);
  drawLine(paths.p90, '#1fd989', 1.5);

  const refY = yScale(capital);
  ctx.beginPath();
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = '#28344a';
  ctx.lineWidth = 1;
  ctx.moveTo(pad.l, refY);
  ctx.lineTo(pad.l + cw, refY);
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawDistChart(finals, capital) {
  const canvas = document.getElementById('distChart');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.parentElement.offsetWidth;
  const H = 140;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const pad = { t: 12, r: 12, b: 28, l: 52 };
  const cw = W - pad.l - pad.r;
  const ch = H - pad.t - pad.b;

  const maxVal = finals[Math.floor(finals.length * 0.95)];
  const bins = 40;
  const binSize = maxVal / bins;
  const counts = new Array(bins).fill(0);

  finals.forEach(v => {
    const b = Math.min(Math.floor(v / binSize), bins - 1);
    counts[b]++;
  });

  const maxCount = Math.max(...counts);
  const barW = cw / bins;

  counts.forEach((c, i) => {
    const x = pad.l + i * barW;
    const bh = (c / maxCount) * ch;
    const y = pad.t + ch - bh;
    const val = i * binSize;

    let color = '#5b9dff';
    if (val < capital * 0.5) color = '#ff5468';
    else if (val > capital * 10) color = '#1fd989';

    ctx.fillStyle = color + '99';
    ctx.fillRect(x + 1, y, barW - 2, bh);
  });

  ctx.fillStyle = '#828ea6';
  ctx.font = '9px JetBrains Mono, monospace';
  ctx.textAlign = 'center';
  for (let i = 0; i <= 4; i++) {
    const val = (maxVal / 4) * i;
    ctx.fillText(fmt(val), pad.l + (i / 4) * cw, H - 6);
  }
}

// ── Seed inputs from live trades OR a backtest strategy, then run ────────────
const MC_DEFAULTS = { winrate: 44, rr: 4, tpw: 5 };
const B = (v) => `<b>${v}</b>`;

function setInputs(wr, rr, tpw) {
  if (wr  != null) document.getElementById('winrate').value = wr;
  if (rr  != null) document.getElementById('rr').value      = rr;
  if (tpw != null) document.getElementById('tpw').value     = Math.round(tpw);
}

function showBanner(html) {
  document.getElementById('seed-text').innerHTML = html;
  document.getElementById('seed-banner').style.display = 'block';
}

function applyDefaults() {
  setInputs(MC_DEFAULTS.winrate, MC_DEFAULTS.rr, MC_DEFAULTS.tpw);
  runSimulation();
}

async function loadStrategies() {
  try {
    const r = await fetch('/api/backtest/strategies');
    if (!r.ok) return;
    const strats = await r.json();
    const sel = document.getElementById('src');
    for (const name of Object.keys(strats)) {
      const o = document.createElement('option');
      o.value = 'bt:' + name;
      o.textContent = 'Backtest · ' + name;
      sel.appendChild(o);
    }
  } catch (e) { /* backtest engine unavailable — live-only */ }
}

async function seedFromSource() {
  const src = document.getElementById('src').value;
  try {
    if (src === 'live') {
      const s = await (await fetch('/api/stats/trades')).json();
      const n = s.total_trades || 0;
      if (n >= 10 && s.actual_wr != null && s.actual_rr != null) {
        setInputs(s.actual_wr, s.actual_rr, s.trades_per_week);
        showBanner(`seeded from your ${B(n)} real closed trades · WR ${B(s.actual_wr + '%')} · ` +
          `R:R ${B(s.actual_rr)}` + (s.trades_per_week != null ? ` · ${B(s.trades_per_week)}/wk` : ''));
      } else {
        showBanner(`only ${n} closed trades — using default assumptions`);
      }
    } else if (src.startsWith('bt:')) {
      const name = src.slice(3);
      showBanner(`running backtest ${B(name)}…`);
      const r = await fetch('/api/backtest/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const d = await r.json();
      if (d.error || !d.metrics) throw new Error(d.error || 'no metrics');
      const m = d.metrics;
      setInputs(m.win_rate, m.avg_r, m.trades_per_week);
      showBanner(`seeded from backtest ${B(name)} · ${B(m.n)} trades · ` +
        `WR ${B(m.win_rate + '%')} · avg ${B(m.avg_r + 'R')} · ${B(m.trades_per_week)}/wk ` +
        `<span class="muted">(historical, not live)</span>`);
    }
  } catch (e) {
    showBanner(`could not seed (${e.message}) — using current inputs`);
  }
  runSimulation();
}

document.getElementById('seed-reset').addEventListener('click', (e) => {
  e.preventDefault();
  applyDefaults();
});
document.getElementById('src').addEventListener('change', seedFromSource);

window.addEventListener('load', async () => {
  await loadStrategies();
  seedFromSource();
});
"""

MONTECARLO_HTML = shell("/montecarlo", "Monte Carlo", _BODY,
                        script=_SCRIPT, head_extra=_HEAD, meta="1,000 paths")
