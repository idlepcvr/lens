"""PRISM Monte Carlo page — standalone simulator, integrated into LENS nav."""

MONTECARLO_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRISM Monte Carlo</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --border: #1e1e2e;
    --accent: #7c6fff;
    --green: #3dffa0;
    --red: #ff4d6d;
    --yellow: #ffd166;
    --text: #e0e0f0;
    --muted: #6060a0;
    --font-mono: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    --font: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    min-height: 100vh;
    padding: 24px 16px;
  }

  h1 {
    font-family: var(--font-mono);
    font-size: 13px;
    letter-spacing: 0.15em;
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: 4px;
  }

  .subtitle {
    font-size: 12px;
    color: var(--muted);
    font-family: var(--font-mono);
    margin-bottom: 24px;
  }

  .controls {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 20px;
  }

  .control {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
  }

  .control label {
    display: block;
    font-size: 10px;
    color: var(--muted);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 6px;
  }

  .control input {
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 16px;
    font-weight: 600;
    outline: none;
  }

  .run-btn {
    width: 100%;
    background: var(--accent);
    color: #0a0a0f;
    border: none;
    border-radius: 6px;
    padding: 12px;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
    margin-bottom: 20px;
    transition: opacity 0.15s;
  }

  .run-btn:hover { opacity: 0.85; }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 20px;
  }

  .stat {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
  }

  .stat-label {
    font-size: 10px;
    color: var(--muted);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
  }

  .stat-value {
    font-size: 18px;
    font-family: var(--font-mono);
    font-weight: 700;
  }

  .stat-value.green { color: var(--green); }
  .stat-value.red { color: var(--red); }
  .stat-value.yellow { color: var(--yellow); }
  .stat-value.accent { color: var(--accent); }

  canvas {
    width: 100%;
    border-radius: 6px;
    background: var(--surface);
    border: 1px solid var(--border);
    display: block;
    margin-bottom: 12px;
  }

  .chart-label {
    font-size: 10px;
    color: var(--muted);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }

  .percentile-legend {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 20px;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--muted);
  }

  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .dist-chart-wrap {
    margin-bottom: 8px;
  }

  .ruin-bar {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .ruin-label {
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--muted);
  }

  .ruin-value {
    font-size: 14px;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--red);
  }

  .ruin-value.safe { color: var(--green); }

  .topnav{display:flex;gap:2px;flex-wrap:wrap;margin-bottom:20px}
  .topnav a{font-size:12px;color:var(--muted);text-decoration:none;padding:5px 10px;border-radius:5px;font-family:var(--font-mono);transition:all .12s}
  .topnav a:hover{color:var(--text);background:var(--surface)}
  .topnav a.cur{color:var(--accent);background:var(--surface)}
</style>
</head>
<body>

<nav class="topnav">
  <a href="/">Dashboard</a>
  <a href="/signals">Signals</a>
  <a href="/projection">Projection</a>
  <a href="/backtest">Backtest</a>
  <a href="/review">Review</a>
  <a href="/montecarlo" class="cur">Monte Carlo</a>
</nav>

<h1>PRISM // Monte Carlo</h1>
<div class="subtitle">BTC perp · 4H · systematic</div>

<div class="controls">
  <div class="control">
    <label>Starting Capital ($)</label>
    <input type="number" id="capital" value="250">
  </div>
  <div class="control">
    <label>Weeks</label>
    <input type="number" id="weeks" value="22">
  </div>
  <div class="control">
    <label>Win Rate (%)</label>
    <input type="number" id="winrate" value="44">
  </div>
  <div class="control">
    <label>R:R (reward)</label>
    <input type="number" id="rr" value="4">
  </div>
  <div class="control">
    <label>Risk per Trade (%)</label>
    <input type="number" id="risk" value="10">
  </div>
  <div class="control">
    <label>Trades per Week</label>
    <input type="number" id="tpw" value="5">
  </div>
</div>

<button class="run-btn" onclick="runSimulation()">▶ Run 1,000 Simulations</button>

<div class="stats-grid" id="stats" style="display:none">
  <div class="stat">
    <div class="stat-label">Median Final</div>
    <div class="stat-value green" id="s-median">—</div>
  </div>
  <div class="stat">
    <div class="stat-label">p90 (best 10%)</div>
    <div class="stat-value accent" id="s-p90">—</div>
  </div>
  <div class="stat">
    <div class="stat-label">p10 (worst 10%)</div>
    <div class="stat-value yellow" id="s-p10">—</div>
  </div>
  <div class="stat">
    <div class="stat-label">Theoretical EV</div>
    <div class="stat-value accent" id="s-ev">—</div>
  </div>
</div>

<div id="charts" style="display:none">
  <div class="chart-label">Equity Paths — percentile bands</div>
  <canvas id="pathChart" height="200"></canvas>

  <div class="percentile-legend">
    <div class="legend-item"><div class="legend-dot" style="background:#3dffa0"></div>p90</div>
    <div class="legend-item"><div class="legend-dot" style="background:#7c6fff"></div>median</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ffd166"></div>p10</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff4d6d"></div>p5 (ruin zone)</div>
  </div>

  <div class="chart-label">Final Balance Distribution</div>
  <div class="dist-chart-wrap">
    <canvas id="distChart" height="140"></canvas>
  </div>

  <div class="chart-label">Ruin & Target Probability</div>
  <div id="ruin-stats"></div>
</div>

<script>
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

  // Run simulations
  const allPaths = [];
  const finalBalances = [];

  for (let s = 0; s < N; s++) {
    let bal = capital;
    const path = [bal];
    for (let t = 0; t < totalTrades; t++) {
      if (Math.random() < winRate) {
        bal *= winMult;
      } else {
        bal *= lossMult;
      }
      if (bal < 1) { bal = 0; break; } // ruin
    }
    // Pad path to full length
    allPaths.push(path);
    finalBalances.push(bal);
  }

  // Build week-by-week percentile paths (sample trades per week)
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

  // Theoretical EV per trade
  const ev = (winRate * winMult + (1 - winRate) * lossMult);
  const evFinal = capital * Math.pow(ev, totalTrades);

  // Stats
  document.getElementById('s-median').textContent = fmt(median);
  document.getElementById('s-p90').textContent = fmt(p90);
  document.getElementById('s-p10').textContent = fmt(p10);
  document.getElementById('s-ev').textContent = fmt(evFinal);

  document.getElementById('stats').style.display = 'grid';
  document.getElementById('charts').style.display = 'block';

  // Ruin stats
  const ruinCount = finalBalances.filter(b => b < capital * 0.1).length;
  const targetCount = finalBalances.filter(b => b >= 10000).length;
  const target50k = finalBalances.filter(b => b >= 50000).length;

  const ruinHtml = `
    <div class="ruin-bar">
      <span class="ruin-label">P(ruin, &lt;10% start)</span>
      <span class="ruin-value ${ruinCount/N < 0.15 ? 'safe' : ''}">${(ruinCount/N*100).toFixed(1)}%</span>
    </div>
    <div class="ruin-bar">
      <span class="ruin-label">P(reach $10k)</span>
      <span class="ruin-value safe">${(targetCount/N*100).toFixed(1)}%</span>
    </div>
    <div class="ruin-bar">
      <span class="ruin-label">P(reach $50k)</span>
      <span class="ruin-value safe">${(target50k/N*100).toFixed(1)}%</span>
    </div>
  `;
  document.getElementById('ruin-stats').innerHTML = ruinHtml;

  // Draw path chart
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

  // Find max for scale
  const allVals = [...paths.p90, ...paths.p50, ...paths.p10, ...paths.p5];
  const maxVal = Math.max(...allVals);
  const minVal = 0;

  const xScale = i => pad.l + (i / weeks) * cw;
  const yScale = v => pad.t + ch - ((v - minVal) / (maxVal - minVal)) * ch;

  // Grid lines
  ctx.strokeStyle = '#1e1e2e';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (i / 4) * ch;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(pad.l + cw, y);
    ctx.stroke();

    const val = maxVal * (1 - i/4);
    ctx.fillStyle = '#6060a0';
    ctx.font = '9px SF Mono, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(fmt(val), pad.l - 4, y + 3);
  }

  // X axis labels
  ctx.fillStyle = '#6060a0';
  ctx.font = '9px SF Mono, monospace';
  ctx.textAlign = 'center';
  for (let w = 0; w <= weeks; w += Math.ceil(weeks / 5)) {
    ctx.fillText('W' + w, xScale(w), H - 6);
  }

  // Draw bands
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

  // Fill between p10 and p90
  ctx.beginPath();
  paths.p90.forEach((v, i) => {
    if (i === 0) ctx.moveTo(xScale(i), yScale(v));
    else ctx.lineTo(xScale(i), yScale(v));
  });
  [...paths.p10].reverse().forEach((v, i) => {
    ctx.lineTo(xScale(weeks - i), yScale(v));
  });
  ctx.closePath();
  ctx.fillStyle = 'rgba(124, 111, 255, 0.06)';
  ctx.fill();

  drawLine(paths.p5,  '#ff4d6d', 1.5);
  drawLine(paths.p10, '#ffd166', 1.5);
  drawLine(paths.p50, '#7c6fff', 2);
  drawLine(paths.p90, '#3dffa0', 1.5);

  // Capital reference line
  const refY = yScale(capital);
  ctx.beginPath();
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = '#2a2a4a';
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

    let color = '#7c6fff';
    if (val < capital * 0.5) color = '#ff4d6d';
    else if (val > capital * 10) color = '#3dffa0';

    ctx.fillStyle = color + '99';
    ctx.fillRect(x + 1, y, barW - 2, bh);
  });

  // X axis
  ctx.fillStyle = '#6060a0';
  ctx.font = '9px SF Mono, monospace';
  ctx.textAlign = 'center';
  for (let i = 0; i <= 4; i++) {
    const val = (maxVal / 4) * i;
    ctx.fillText(fmt(val), pad.l + (i / 4) * cw, H - 6);
  }
}

// Auto-run on load
window.addEventListener('load', runSimulation);
</script>
</body>
</html>
"""
