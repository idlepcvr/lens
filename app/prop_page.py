"""LENS — Kraken Prop eval page. Visualises the Breakout 1-Step Classic
evaluation: the locked strategy, the walls, and a live Monte Carlo of eval
paths playing out (pass vs bust) so the plan is something you can watch, not
just read. Numbers sourced from app/prop_eval.py + strategies/_prop/BREAKOUT_5K_PLAN.md."""

PROP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LENS — Kraken Prop</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  :root{
    --bg:#0a0a0f;--s1:#12121a;--s2:#1a1a26;--bd:#23233440;
    --ac:#7c6fff;--adim:#7c6fff22;--green:#3dffa0;--red:#ff4d6d;--yellow:#ffd166;
    --t1:#e6e6f5;--t2:#8a8ab8;--t3:#56567e;
    --mono:'SF Mono','Fira Code','Cascadia Code',monospace;
    --font:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
  }
  body{background:var(--bg);color:var(--t1);font-family:var(--font);min-height:100vh;padding:20px 16px 60px}
  .wrap{max-width:1080px;margin:0 auto}
  .topnav{display:flex;gap:2px;margin-bottom:22px;flex-wrap:wrap}
  .topnav a{font-size:12px;color:var(--t2);text-decoration:none;padding:5px 10px;border-radius:5px;transition:all .12s}
  .topnav a:hover{color:var(--t1);background:var(--s2)}
  .topnav a.cur{color:var(--ac);background:var(--adim)}
  h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--ac);text-transform:uppercase;margin-bottom:3px}
  .sub{color:var(--t2);font-size:13px;margin-bottom:22px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:22px}
  .card{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}
  .card .lbl{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--t3);margin-bottom:6px}
  .card .val{font-family:var(--mono);font-size:20px;font-weight:600}
  .card .note{font-size:11px;color:var(--t2);margin-top:3px}
  .green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}.ac{color:var(--ac)}
  .panel{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:18px;margin-bottom:20px}
  .panel h2{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--t2);margin-bottom:14px}
  .controls{display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
  .ctl{display:flex;flex-direction:column;gap:4px}
  .ctl label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
  .ctl .seg{display:flex;gap:2px}
  .ctl .seg button{background:var(--s2);color:var(--t2);border:1px solid var(--bd);font-family:var(--mono);
    font-size:12px;padding:6px 12px;border-radius:6px;cursor:pointer;transition:all .1s}
  .ctl .seg button.on{background:var(--adim);color:var(--ac);border-color:var(--ac)}
  .run{background:var(--ac);color:#0a0a0f;border:none;font-weight:700;font-size:13px;padding:9px 20px;
    border-radius:7px;cursor:pointer;font-family:var(--font)}
  .run:hover{filter:brightness(1.1)}
  canvas{width:100%;height:340px;display:block;background:#08080d;border-radius:8px;border:1px solid var(--bd)}
  .tally{display:flex;gap:24px;margin-top:14px;font-family:var(--mono);font-size:14px}
  .tally b{font-size:22px;display:block}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--bd)}
  th{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--t3);font-weight:500}
  td{font-family:var(--mono)}
  .hl{background:var(--adim)}
  .prose{color:var(--t2);font-size:13.5px;line-height:1.65}
  .prose strong{color:var(--t1)}
  .prose code{font-family:var(--mono);color:var(--ac);background:var(--s2);padding:1px 5px;border-radius:4px}
  .flag{border-left:3px solid var(--yellow);padding:8px 14px;background:#ffd16610;border-radius:0 8px 8px 0;
    font-size:13px;color:var(--t1);margin-top:10px}
</style>
</head>
<body>
<div class="wrap">
  <nav class="topnav">
    <a href="/">Dashboard</a>
    <a href="/desk">Desk</a>
    <a href="/signals">Signals</a>
    <a href="/projection">Projection</a>
    <a href="/backtest">Backtest</a>
    <a href="/review">Review</a>
    <a href="/montecarlo">Monte Carlo</a>
    <a href="/prop" class="cur">Prop</a>
  </nav>

  <h1>Kraken Prop — Breakout 1-Step Classic</h1>
  <div class="sub">Separate system from the hedge-fund thesis. Objective: survive the walls to +10%, not maximise compounding.</div>

  <!-- Eval walls -->
  <div class="grid" id="walls"></div>

  <!-- Live Monte Carlo -->
  <div class="panel">
    <h2>Eval, played out — live Monte Carlo</h2>
    <div class="controls">
      <div class="ctl">
        <label>Account</label>
        <div class="seg" id="acctSeg">
          <button data-acct="5000" class="on">$5k</button>
          <button data-acct="200000">$200k</button>
        </div>
      </div>
      <div class="ctl">
        <label>Risk / trade</label>
        <div class="seg" id="riskSeg">
          <button data-risk="1">1%</button>
          <button data-risk="1.5">1.5%</button>
          <button data-risk="2" class="on">2%</button>
        </div>
      </div>
      <div class="ctl">
        <label>&nbsp;</label>
        <button class="run" id="runBtn">▶ Run 300 paths</button>
      </div>
    </div>
    <canvas id="cv"></canvas>
    <div class="tally">
      <div>PASS <b class="green" id="tPass">–</b></div>
      <div>BUST <b class="red" id="tFail">–</b></div>
      <div>pass rate <b class="ac" id="tRate">–</b></div>
      <div>median trades <b id="tMed">–</b></div>
    </div>
    <div class="flag">Each line = one eval. Green hits <b>+10% target</b>, red hits the <b>6% floor</b>. WR fixed at the
      mechanical 40%. Watch the failure mode: a cold 3-loss start before the first win. Land one win → the static floor
      cushion carries it home.</div>
  </div>

  <!-- The locked config -->
  <div class="panel">
    <h2>The locked config</h2>
    <table>
      <tr><th>&nbsp;</th><th>Eval phase (pass it)</th><th>Funded phase (earn)</th></tr>
      <tr><td>Strategy</td><td class="green">ASIAN_RSI_DIP_v1</td><td>same</td></tr>
      <tr><td>Chart</td><td>4H · Asian killzone 00:00+04:00 UTC</td><td>same</td></tr>
      <tr><td>Geometry</td><td>1% stop · 4% TP (4R)</td><td>same</td></tr>
      <tr><td>Risk / trade</td><td class="yellow">2% (2x lev) — speed</td><td class="green">1% (1x lev) — survival</td></tr>
      <tr><td>Odds</td><td>~70% pass in ~2 months</td><td>—</td></tr>
      <tr><td>5k vs 200k</td><td colspan="2">Identical — rules are %-based, account size is irrelevant to odds</td></tr>
    </table>
  </div>

  <!-- Speed vs probability frontier -->
  <div class="panel">
    <h2>Speed ↔ probability frontier (the hard law)</h2>
    <table>
      <tr><th>Pass within</th><th>Best pass%</th><th>Config</th></tr>
      <tr><td>1 month</td><td class="red">45%</td><td>ASIAN_PULLBACK_v1 @2% — coin flip, reject</td></tr>
      <tr class="hl"><td>2 months</td><td class="yellow">70%</td><td>ASIAN_RSI_DIP_v1 @2% — the play</td></tr>
      <tr><td>6 months</td><td>76%</td><td>ASIAN_RSI_DIP_v1 @1.5%</td></tr>
      <tr><td>9 months</td><td class="green">91%</td><td>ASIAN_RSI_DIP_v1 @0.75%</td></tr>
    </table>
    <div class="prose" style="margin-top:12px">+10% in a month while dodging −6% needs an edge BTC mean-reversion doesn't have.
      Because evals are cheap (~$20), <strong>expected time favours 2%</strong>: ~70% × 2mo + cheap retries ≈ <strong>~3 months & ~$29 to funded</strong>.</div>
  </div>

  <!-- Funded income -->
  <div class="panel">
    <h2>What funded actually earns (after split)</h2>
    <table>
      <tr><th>Account</th><th>Per win (7.4%, 80%)</th><th>~Monthly @2% (1.68%)</th><th>~Monthly @1% safe (0.84%)</th></tr>
      <tr><td>$10k</td><td>$592</td><td>$168</td><td>$84</td></tr>
      <tr><td>$100k</td><td>$5,920</td><td>$1,680</td><td>$840</td></tr>
      <tr class="hl"><td>$200k</td><td>$11,840</td><td class="green">~$3,360</td><td>~$1,680</td></tr>
    </table>
    <div class="flag">Per-win ≠ income. At 40% WR, expectancy is <b>+1.4%/trade</b>, ~1.5 trades/mo. Income is <b>lumpy</b>
      (a $200k month ranges roughly −$8k to +$26k, avg +$3.4k). The lever for more is <b>WR & R</b>, not account size.</div>
  </div>

  <!-- The plan, written -->
  <div class="panel">
    <h2>The plan, written</h2>
    <div class="prose">
      <p><strong>1.</strong> Pass the <strong>$5k 1-Step Classic</strong> eval with <code>ASIAN_RSI_DIP_v1 @ 2% risk</code> (~$20 fee, ~70%, ~2mo).</p>
      <p><strong>2.</strong> Get funded, drop risk to <strong>1%</strong>, bank payouts.</p>
      <p><strong>3.</strong> Don't ladder 5k→25k→100k→200k (4 sequential evals = slow). <strong>Buy the biggest eval you can afford directly</strong> — same ~2-month odds at any size.</p>
      <p><strong>4.</strong> Funded $200k @1% → ~$1.7k/mo safe (or 2% for ~$3.4k, higher bust risk).</p>
      <p><strong>5.</strong> Long game: raise WR/R via the LENS discretionary edge (real flush WR ~60% vs 40% mechanical) → roughly doubles income.</p>
      <p style="color:var(--t3);margin-top:10px">Caveats: sim checks closed PnL (real eval counts open equity → a few pts lower) · thin sample (45 trades/30mo) · $200k eval fee ≫ $20, confirm in dashboard.</p>
    </div>
  </div>

</div>

<script>
const WR = 0.40;          // mechanical win rate of ASIAN_RSI_DIP_v1
const FLOOR = 0.06;       // 6% static drawdown
const TARGET = 0.10;      // 10% profit target
const MAXT = 24;          // cap trades drawn per path
let acct = 5000, risk = 2.0, N = 300;

function winLoss(r){ return { win: r*3.7/100, loss: r*1.3/100 }; }   // 4R net of fees, scales with risk

function simPath(){
  const {win,loss} = winLoss(risk);
  let eq = 1.0, pts = [1.0];
  const floor = 1 - FLOOR, target = 1 + TARGET;
  for(let t=0;t<MAXT;t++){
    eq *= (Math.random() < WR) ? (1+win) : (1-loss);
    pts.push(eq);
    if(eq <= floor) return {pts, res:'fail', n:t+1};
    if(eq >= target) return {pts, res:'pass', n:t+1};
  }
  return {pts, res:'open', n:MAXT};
}

function run(){
  const cv = document.getElementById('cv'), dpr = window.devicePixelRatio||1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  const x = cv.getContext('2d'); x.scale(dpr,dpr);
  x.clearRect(0,0,W,H);

  const yLo = 1-FLOOR-0.01, yHi = 1+TARGET+0.02;
  const X = t => 40 + (W-55) * (t/MAXT);
  const Y = e => (H-26) - (H-40) * ((e-yLo)/(yHi-yLo));

  // wall lines
  function hline(eq,color,label){
    x.strokeStyle=color; x.lineWidth=1; x.setLineDash([5,4]);
    x.beginPath(); x.moveTo(40,Y(eq)); x.lineTo(W-15,Y(eq)); x.stroke(); x.setLineDash([]);
    x.fillStyle=color; x.font='11px monospace'; x.fillText(label, 44, Y(eq)-4);
  }
  hline(1+TARGET,'#3dffa0','+10% target  ($'+Math.round(acct*1.1).toLocaleString()+')');
  hline(1,'#56567e','start  ($'+acct.toLocaleString()+')');
  hline(1-FLOOR,'#ff4d6d','−6% floor  ($'+Math.round(acct*0.94).toLocaleString()+')');

  let pass=0, fail=0; const ns=[];
  for(let i=0;i<N;i++){
    const p = simPath();
    if(p.res==='pass'){pass++; ns.push(p.n);} else if(p.res==='fail'){fail++; ns.push(p.n);}
    x.strokeStyle = p.res==='pass' ? 'rgba(61,255,160,.30)' : p.res==='fail' ? 'rgba(255,77,109,.28)' : 'rgba(138,138,184,.18)';
    x.lineWidth = 1; x.beginPath();
    p.pts.forEach((e,t)=> t===0 ? x.moveTo(X(t),Y(e)) : x.lineTo(X(t),Y(e)));
    x.stroke();
  }
  const rate = pass+fail>0 ? (100*pass/(pass+fail)) : 0;
  ns.sort((a,b)=>a-b); const med = ns.length? ns[Math.floor(ns.length/2)] : 0;
  document.getElementById('tPass').textContent = pass;
  document.getElementById('tFail').textContent = fail;
  document.getElementById('tRate').textContent = rate.toFixed(0)+'%';
  document.getElementById('tMed').textContent = med + '  (~'+(med/1.5).toFixed(1)+' mo)';
}

function walls(){
  const f=Math.round(acct*0.94), t=Math.round(acct*1.10), d=Math.round(acct*0.03);
  const {win,loss}=winLoss(risk);
  document.getElementById('walls').innerHTML = `
    <div class="card"><div class="lbl">Start</div><div class="val">$${acct.toLocaleString()}</div><div class="note">1-Step Classic</div></div>
    <div class="card"><div class="lbl">Floor (6% static)</div><div class="val red">$${f.toLocaleString()}</div><div class="note">locked, never moves</div></div>
    <div class="card"><div class="lbl">Target (+10%)</div><div class="val green">$${t.toLocaleString()}</div><div class="note">pass line</div></div>
    <div class="card"><div class="lbl">Daily limit (3%)</div><div class="val yellow">−$${d.toLocaleString()}</div><div class="note">never binds (1 trade/day)</div></div>
    <div class="card"><div class="lbl">Win / trade</div><div class="val green">+$${Math.round(acct*win).toLocaleString()}</div><div class="note">+${(win*100).toFixed(1)}% · ${risk}% risk · ${(risk/1).toFixed(1)}x lev</div></div>
    <div class="card"><div class="lbl">Loss / trade</div><div class="val red">−$${Math.round(acct*loss).toLocaleString()}</div><div class="note">−${(loss*100).toFixed(1)}%</div></div>`;
}

document.getElementById('acctSeg').addEventListener('click',e=>{
  if(!e.target.dataset.acct)return;
  [...e.currentTarget.children].forEach(b=>b.classList.remove('on')); e.target.classList.add('on');
  acct=+e.target.dataset.acct; walls(); run();
});
document.getElementById('riskSeg').addEventListener('click',e=>{
  if(!e.target.dataset.risk)return;
  [...e.currentTarget.children].forEach(b=>b.classList.remove('on')); e.target.classList.add('on');
  risk=+e.target.dataset.risk; walls(); run();
});
document.getElementById('runBtn').addEventListener('click',run);
walls(); run();
</script>
</body>
</html>
"""
