"""LENS — Kraken Prop eval page. Two modes via a toggle:

  • AUTO (live)  — picks strategy/eval/risk/account, fetches REAL open-equity
                   numbers from app/prop_eval.eval_summary (via /api/prop/eval).
                   Source of truth; numbers can never go stale.
  • MANUAL (what-if) — hand-tweak WR / geometry / trades-per-month and watch a
                   client-side Monte Carlo. For "if I found a 55%-WR setup…".

On the shared LENS design system (app/theme.py shell() + /assets/lens.css)."""

from .theme import shell

# ── page CSS — component styles on the shared token palette ───────────────────
_HEAD = r"""<style>
:root{
  /* mapped onto the shared LENS palette (see app/theme.py LENS_CSS) */
  --ac:#5b9dff;--adim:#10203f;--green:#1fd989;--red:#ff5468;--yellow:#f6ad3c;
  --s1:#0b0f16;--s2:#10151e;--bd:#192232;
  --t1:#e8eef8;--t2:#828ea6;--t3:#465064;--font:var(--hud);
}
.pp h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--ac);text-transform:uppercase;margin-bottom:3px}
.pp .sub{color:var(--t2);font-size:13px;margin-bottom:22px}
.pp .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:22px}
.pp .card{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}
.pp .card .lbl{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--t3);margin-bottom:6px}
.pp .card .val{font-family:var(--mono);font-size:20px;font-weight:600}
.pp .card .note{font-size:11px;color:var(--t2);margin-top:3px}
.pp .green{color:var(--green)} .pp .red{color:var(--red)} .pp .yellow{color:var(--yellow)} .pp .ac{color:var(--ac)}
.pp .panel{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:18px;margin-bottom:20px}
.pp .panel h2{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--t2);margin-bottom:14px}
.pp .controls{display:flex;gap:18px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px}
.pp .ctl{display:flex;flex-direction:column;gap:4px}
.pp .ctl label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.pp .ctl .seg{display:flex;gap:2px}
.pp .ctl .seg button{background:var(--s2);color:var(--t2);border:1px solid var(--bd);font-family:var(--mono);
  font-size:12px;padding:6px 12px;border-radius:6px;cursor:pointer;transition:all .1s}
.pp .ctl .seg button.on{background:var(--adim);color:var(--ac);border-color:var(--ac)}
.pp select,.pp input[type=number]{background:var(--s2);color:var(--t1);border:1px solid var(--bd);
  font-family:var(--mono);font-size:13px;padding:7px 10px;border-radius:6px;min-width:130px}
.pp input[type=number]{width:96px;min-width:0}
.pp .modebar{display:flex;gap:2px;margin-bottom:16px}
.pp .modebar button{background:var(--s2);color:var(--t2);border:1px solid var(--bd);font-family:var(--mono);
  font-size:12px;letter-spacing:.06em;padding:8px 18px;cursor:pointer;transition:all .1s}
.pp .modebar button:first-child{border-radius:8px 0 0 8px}
.pp .modebar button:last-child{border-radius:0 8px 8px 0}
.pp .modebar button.on{background:var(--adim);color:var(--ac);border-color:var(--ac)}
.pp .run{background:var(--ac);color:var(--bg);border:none;font-weight:700;font-size:13px;padding:9px 20px;
  border-radius:7px;cursor:pointer;font-family:var(--font)}
.pp .run:hover{filter:brightness(1.1)}
.pp .run:disabled{opacity:.5;cursor:wait}
.pp canvas{width:100%;height:340px;display:block;background:var(--bg);border-radius:8px;border:1px solid var(--bd)}
.pp .tally{display:flex;gap:24px;margin-top:14px;font-family:var(--mono);font-size:14px;flex-wrap:wrap}
.pp .tally b{font-size:22px;display:block}
.pp table{width:100%;border-collapse:collapse;font-size:13px}
.pp th,.pp td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--bd)}
.pp th{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--t3);font-weight:500}
.pp td{font-family:var(--mono)}
.pp .hl{background:var(--adim)}
.pp .prose{color:var(--t2);font-size:13.5px;line-height:1.65}
.pp .prose strong{color:var(--t1)}
.pp .prose code{font-family:var(--mono);color:var(--ac);background:var(--s2);padding:1px 5px;border-radius:4px}
.pp .flag{border-left:3px solid var(--yellow);padding:8px 14px;background:var(--amber-d);border-radius:0 8px 8px 0;
  font-size:13px;color:var(--t1);margin-top:10px}
.pp .hide{display:none}
.pp .srcbadge{font-family:var(--mono);font-size:10px;letter-spacing:.1em;padding:3px 8px;border-radius:5px;text-transform:uppercase}
.pp .srcbadge.live{background:var(--adim);color:var(--green);border:1px solid var(--green)}
.pp .srcbadge.whatif{background:var(--s2);color:var(--yellow);border:1px solid var(--yellow)}
</style>"""

_BODY = r"""
<div class="pp">
  <h1>Kraken Prop — Breakout eval</h1>
  <div class="sub">Separate system from the hedge-fund thesis. Objective: survive the walls to the target, not maximise compounding.</div>

  <!-- Mode toggle -->
  <div class="modebar">
    <button id="mAuto" class="on">● AUTO — live (real open-equity)</button>
    <button id="mMan">○ MANUAL — what-if</button>
  </div>

  <div class="panel">
    <!-- AUTO controls -->
    <div class="controls" id="autoCtl">
      <div class="ctl"><label>Strategy</label><select id="selStrat"></select></div>
      <div class="ctl"><label>Eval</label><select id="selEval"></select></div>
      <div class="ctl"><label>Risk / trade</label>
        <select id="selRisk">
          <option value="0.5">0.5%</option><option value="0.75">0.75%</option>
          <option value="1">1%</option><option value="1.5">1.5%</option>
          <option value="2" selected>2%</option>
        </select></div>
      <div class="ctl"><label>Account</label>
        <select id="selAcct">
          <option value="5000" selected>$5k</option><option value="25000">$25k</option>
          <option value="50000">$50k</option><option value="100000">$100k</option>
          <option value="200000">$200k</option>
        </select></div>
      <div class="ctl"><label>&nbsp;</label><span class="srcbadge live" id="srcA">LIVE · open-equity</span></div>
    </div>

    <!-- MANUAL controls -->
    <div class="controls hide" id="manCtl">
      <div class="ctl"><label>Win rate %</label><input type="number" id="mWr" value="40" step="1" min="1" max="99"></div>
      <div class="ctl"><label>Stop %</label><input type="number" id="mStop" value="1.0" step="0.05" min="0.1"></div>
      <div class="ctl"><label>TP %</label><input type="number" id="mTp" value="4.0" step="0.25" min="0.1"></div>
      <div class="ctl"><label>Trades / mo</label><input type="number" id="mTpm" value="1.5" step="0.1" min="0.1"></div>
      <div class="ctl"><label>Eval (walls)</label><select id="mEval"></select></div>
      <div class="ctl"><label>Risk / trade %</label><input type="number" id="mRisk" value="2.0" step="0.25" min="0.1"></div>
      <div class="ctl"><label>Account</label><input type="number" id="mAcct" value="5000" step="1000" min="100"></div>
      <div class="ctl"><label>&nbsp;</label><button class="run" id="mRun">▶ Run</button></div>
      <div class="ctl"><label>&nbsp;</label><span class="srcbadge whatif">WHAT-IF · client sim</span></div>
    </div>

    <!-- Eval walls -->
    <div class="grid" id="walls"></div>

    <h2 style="margin-top:6px">Eval, played out</h2>
    <canvas id="cv"></canvas>
    <div class="tally">
      <div>pass rate <b class="ac" id="tRate">–</b></div>
      <div>fail (DD) <b class="red" id="tDD">–</b></div>
      <div>fail (daily) <b class="yellow" id="tDay">–</b></div>
      <div>median trades <b id="tMed">–</b></div>
      <div>~time to resolve <b id="tMo">–</b></div>
    </div>
    <div class="flag" id="modeNote"></div>
  </div>

  <!-- The current config -->
  <div class="panel">
    <h2>The config</h2>
    <table>
      <tr><th>Field</th><th>Value</th></tr>
      <tr><td>Strategy</td><td class="green" id="cStrat">–</td></tr>
      <tr><td>Chart</td><td id="cTf">–</td></tr>
      <tr><td>Geometry</td><td id="cGeo">–</td></tr>
      <tr><td>Win rate (measured)</td><td id="cWr">–</td></tr>
      <tr><td>Per trade</td><td id="cWL">–</td></tr>
      <tr><td>Risk / sizing</td><td class="yellow" id="cRisk">–</td></tr>
      <tr><td>Eval walls</td><td id="cWalls">–</td></tr>
      <tr><td class="ac">Pass odds</td><td class="ac" id="cOdds">–</td></tr>
    </table>
  </div>

  <!-- Speed vs probability frontier (CLASSIC, open-equity) -->
  <div class="panel">
    <h2>Speed ↔ probability frontier — 1-Step Classic, open-equity (the hard law)</h2>
    <table>
      <tr><th>Pass within</th><th>Best pass%</th><th>Config</th></tr>
      <tr><td>1 month</td><td class="red">36%</td><td>ASIAN_PULLBACK_v1 @2% — coin flip, reject</td></tr>
      <tr class="hl"><td>2 months</td><td class="yellow">57%</td><td>ASIAN_RSI_DIP_v1 @2% — the play</td></tr>
      <tr><td>6 months</td><td>69%</td><td>ASIAN_RSI_DIP_v1 @1.5%</td></tr>
      <tr><td>9 months</td><td class="green">89%</td><td>ASIAN_RSI_DIP_v1 @0.75%</td></tr>
    </table>
    <div class="prose" style="margin-top:12px">+10% in a month while dodging −6% needs an edge BTC mean-reversion doesn't have.
      Because evals are cheap (~$20), <strong>expected time favours 2%</strong>: ~57% × 2mo + cheap retries ≈ <strong>~3–4 months to funded</strong>.
      You can't dial past 57% at 2mo — only a <strong>higher-WR setup</strong> moves that ceiling.</div>
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
      <p><strong>1.</strong> Pass the <strong>$5k 1-Step Classic</strong> eval with <code>ASIAN_RSI_DIP_v1 @ 2% risk</code> (~$20 fee, ~57%, ~2mo open-equity).</p>
      <p><strong>2.</strong> Get funded, bank ~$1k profit.</p>
      <p><strong>3.</strong> Use that profit to buy a <strong>$200k 1-Step Classic</strong> eval directly (don't ladder) — same ~57%/2mo odds at any size.</p>
      <p><strong>4.</strong> Funded $200k @1% → ~$1.7k/mo safe (or 2% for ~$3.4k, higher bust risk).</p>
      <p><strong>5.</strong> Long game: a higher-WR setup is the only way past 57%/2mo — raise WR via the LENS discretionary edge (real flush WR ~60% vs 40% mechanical).</p>
      <p style="color:var(--t3);margin-top:10px">AUTO mode = real open-equity sim (each trade's worst adverse excursion tested vs the live wall) · thin sample (44 trades/30mo) · $200k eval fee ≫ $20, confirm in dashboard.</p>
    </div>
  </div>
</div>
"""

_SCRIPT = r"""
const MAXT = 30;            // cap trades drawn per path
const FEE = 0.0015;         // per-side commission (matches prop_eval)
let MODE = 'auto';
let CFG = {strategies:[], evals:[]};
let ST = {wr:0.40, win:0.074, loss:0.026, floor:0.06, target:0.10, daily:0.03,
          account:5000, tpm:1.5, maxlev:5};
let busy = false;

const $ = id => document.getElementById(id);

// ── option lists from the backend ────────────────────────────────────────────
async function loadConfigs(){
  const r = await fetch('/api/prop/configs'); CFG = await r.json();
  const strat = $('selStrat');
  CFG.strategies.forEach(s=>{
    const o = document.createElement('option');
    o.value = s.name; o.textContent = `${s.name}  (${s.tf}, ${s.r}R)`;
    if(s.name==='ASIAN_RSI_DIP_v1') o.selected = true;
    strat.appendChild(o);
  });
  [$('selEval'), $('mEval')].forEach(sel=>{
    CFG.evals.forEach(e=>{
      const o = document.createElement('option');
      o.value = e.name;
      o.textContent = `${e.name.replace('BREAKOUT_','')}  (${e.target_pct}% tgt, ${e.dd_pct}% ${e.dd_type} DD)`;
      if(e.name==='BREAKOUT_1STEP_CLASSIC') o.selected = true;
      sel.appendChild(o);
    });
  });
}

// ── AUTO: pull real numbers from the backend ─────────────────────────────────
async function fetchAuto(){
  if(busy) return; busy = true; $('srcA').textContent='loading…';
  const q = new URLSearchParams({
    strategy: $('selStrat').value, eval: $('selEval').value,
    account: $('selAcct').value, risk: $('selRisk').value, open_equity: 'true',
  });
  try{
    const r = await fetch('/api/prop/eval?'+q); const d = await r.json();
    if(d.error){ $('srcA').textContent='ERR: '+d.error; busy=false; return; }
    ST = {
      wr: d.win_rate_pct/100, win: d.avg_win_pct/100, loss: Math.abs(d.avg_loss_pct)/100,
      floor: d.dd_pct/100, target: d.target_pct/100, daily: d.daily_pct/100,
      account: d.account, tpm: d.trades_per_month, maxlev: 5,
    };
    // tally = REAL backend numbers
    $('tRate').textContent = (d.pass_pct!=null? d.pass_pct.toFixed(0):'–')+'%';
    $('tDD').textContent  = (d.fail_dd_pct!=null? d.fail_dd_pct.toFixed(0):'–')+'%';
    $('tDay').textContent = (d.fail_daily_pct!=null? d.fail_daily_pct.toFixed(0):'–')+'%';
    $('tMed').textContent = d.median_trades ?? '–';
    $('tMo').textContent  = d.est_months!=null ? '~'+d.est_months+' mo' : '–';
    fillConfig({
      strat:d.strategy, tf:d.tf, stop:d.stop_pct, tp:d.tp_pct, r:d.r_multiple,
      wrPct:d.win_rate_pct, win:d.avg_win_pct, loss:d.avg_loss_pct,
      risk:d.risk_pct, lev:d.leverage,
      eval:d.eval, target:d.target_pct, daily:d.daily_pct, dd:d.dd_pct, ddtype:d.dd_type,
      odds:(d.pass_pct!=null? d.pass_pct.toFixed(0)+'% in ~'+d.est_months+' mo':'–'),
    });
    $('modeNote').innerHTML = 'Tally = <b>real open-equity Monte Carlo</b> from <code>prop_eval.eval_summary</code> '
      +'(3000 paths, each trade\'s worst adverse excursion tested vs the live wall). '
      +'Canvas paths are an illustrative closed-PnL sketch of the same WR/geometry.';
    $('srcA').textContent='LIVE · open-equity';
    drawPaths();
  }catch(e){ $('srcA').textContent='fetch failed'; }
  busy = false;
}

// ── MANUAL: derive geometry from inputs, run client sim ───────────────────────
function runManual(){
  const wr=+$('mWr').value/100, stop=+$('mStop').value, tp=+$('mTp').value,
        risk=+$('mRisk').value, acct=+$('mAcct').value, tpm=+$('mTpm').value;
  const ev = CFG.evals.find(e=>e.name===$('mEval').value) || {target_pct:10,daily_pct:3,dd_pct:6,dd_type:'static'};
  const lev = Math.min(risk/stop, ST.maxlev);
  const win  = (tp*lev   - FEE*2*lev*100)/100;   // fraction of account
  const loss = (stop*lev + FEE*2*lev*100)/100;
  ST = {wr, win, loss, floor:ev.dd_pct/100, target:ev.target_pct/100,
        daily:ev.daily_pct/100, account:acct, tpm, maxlev:5};
  const res = drawPaths();   // returns client-sim tally
  $('tRate').textContent = res.rate.toFixed(0)+'%';
  $('tDD').textContent   = res.failPct.toFixed(0)+'%';
  $('tDay').textContent  = '–';
  $('tMed').textContent  = res.med;
  $('tMo').textContent   = res.med && tpm ? '~'+(res.med/tpm).toFixed(1)+' mo' : '–';
  fillConfig({
    strat:'(manual)', tf:'—', stop, tp, r:+(tp/stop).toFixed(1),
    wrPct:(wr*100).toFixed(0), win:+(win*100).toFixed(2), loss:-(loss*100).toFixed(2),
    risk, lev:+lev.toFixed(2),
    eval:$('mEval').value, target:ev.target_pct, daily:ev.daily_pct, dd:ev.dd_pct, ddtype:ev.dd_type,
    odds:res.rate.toFixed(0)+'% (client sim)',
  });
  $('modeNote').innerHTML = 'What-if mode: <b>client-side closed-PnL sim</b> on your inputs. '
    +'Use it to ask "what would a higher-WR setup pass?" — not a substitute for the AUTO backtest.';
}

// ── shared: walls grid + config table + canvas ────────────────────────────────
function fillConfig(c){
  $('cStrat').textContent = c.strat;
  $('cTf').textContent = c.tf;
  $('cGeo').textContent = `${c.stop}% stop · ${c.tp}% TP (${c.r}R)`;
  $('cWr').textContent = c.wrPct+'%';
  $('cWL').textContent = `win +${c.win}% · loss ${c.loss}%`;
  $('cRisk').textContent = `${c.risk}% risk · ${c.lev}x lev`;
  $('cWalls').textContent = `${c.eval.replace('BREAKOUT_','')} — ${c.target}% target · ${c.dd}% ${c.ddtype} DD · ${c.daily}% daily`;
  $('cOdds').textContent = c.odds;
}

function walls(){
  const a=ST.account, f=Math.round(a*(1-ST.floor)), t=Math.round(a*(1+ST.target)),
        d=Math.round(a*ST.daily);
  $('walls').innerHTML = `
    <div class="card"><div class="lbl">Start</div><div class="val">$${a.toLocaleString()}</div><div class="note">account size</div></div>
    <div class="card"><div class="lbl">Floor (${(ST.floor*100).toFixed(0)}% DD)</div><div class="val red">$${f.toLocaleString()}</div><div class="note">bust line</div></div>
    <div class="card"><div class="lbl">Target (+${(ST.target*100).toFixed(0)}%)</div><div class="val green">$${t.toLocaleString()}</div><div class="note">pass line</div></div>
    <div class="card"><div class="lbl">Daily limit (${(ST.daily*100).toFixed(0)}%)</div><div class="val yellow">−$${d.toLocaleString()}</div><div class="note">resets each day</div></div>
    <div class="card"><div class="lbl">Win / trade</div><div class="val green">+$${Math.round(a*ST.win).toLocaleString()}</div><div class="note">+${(ST.win*100).toFixed(1)}%</div></div>
    <div class="card"><div class="lbl">Loss / trade</div><div class="val red">−$${Math.round(a*ST.loss).toLocaleString()}</div><div class="note">−${(ST.loss*100).toFixed(1)}%</div></div>`;
}

function simPath(){
  let eq = 1.0, pts = [1.0];
  const floor = 1-ST.floor, target = 1+ST.target;
  for(let t=0;t<MAXT;t++){
    eq *= (Math.random() < ST.wr) ? (1+ST.win) : (1-ST.loss);
    pts.push(eq);
    if(eq <= floor) return {pts, res:'fail', n:t+1};
    if(eq >= target) return {pts, res:'pass', n:t+1};
  }
  return {pts, res:'open', n:MAXT};
}

function drawPaths(){
  walls();
  const cv = $('cv'), dpr = window.devicePixelRatio||1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W*dpr; cv.height = H*dpr;
  const x = cv.getContext('2d'); x.scale(dpr,dpr); x.clearRect(0,0,W,H);
  const yLo = 1-ST.floor-0.01, yHi = 1+ST.target+0.02;
  const X = t => 40 + (W-55)*(t/MAXT);
  const Y = e => (H-26) - (H-40)*((e-yLo)/(yHi-yLo));
  function hline(eq,color,label){
    x.strokeStyle=color; x.lineWidth=1; x.setLineDash([5,4]);
    x.beginPath(); x.moveTo(40,Y(eq)); x.lineTo(W-15,Y(eq)); x.stroke(); x.setLineDash([]);
    x.fillStyle=color; x.font='11px monospace'; x.fillText(label, 44, Y(eq)-4);
  }
  const a = ST.account;
  hline(1+ST.target,'#1fd989','+'+(ST.target*100).toFixed(0)+'% target  ($'+Math.round(a*(1+ST.target)).toLocaleString()+')');
  hline(1,'#465064','start  ($'+a.toLocaleString()+')');
  hline(1-ST.floor,'#ff5468','−'+(ST.floor*100).toFixed(0)+'% floor  ($'+Math.round(a*(1-ST.floor)).toLocaleString()+')');
  let pass=0, fail=0; const ns=[]; const N=300;
  for(let i=0;i<N;i++){
    const p = simPath();
    if(p.res==='pass'){pass++; ns.push(p.n);} else if(p.res==='fail'){fail++; ns.push(p.n);}
    x.strokeStyle = p.res==='pass' ? 'rgba(31,217,137,.30)' : p.res==='fail' ? 'rgba(255,84,104,.28)' : 'rgba(130,142,166,.18)';
    x.lineWidth = 1; x.beginPath();
    p.pts.forEach((e,t)=> t===0 ? x.moveTo(X(t),Y(e)) : x.lineTo(X(t),Y(e)));
    x.stroke();
  }
  ns.sort((a,b)=>a-b); const med = ns.length? ns[Math.floor(ns.length/2)] : 0;
  const resolved = pass+fail;
  return {rate: resolved? 100*pass/resolved : 0, failPct: resolved? 100*fail/resolved : 0, med, pass, fail};
}

// ── mode switching + wiring ───────────────────────────────────────────────────
function setMode(m){
  MODE = m;
  $('mAuto').classList.toggle('on', m==='auto');
  $('mMan').classList.toggle('on', m==='manual');
  $('autoCtl').classList.toggle('hide', m!=='auto');
  $('manCtl').classList.toggle('hide', m!=='manual');
  if(m==='auto') fetchAuto(); else runManual();
}

$('mAuto').addEventListener('click',()=>setMode('auto'));
$('mMan').addEventListener('click',()=>setMode('manual'));
['selStrat','selEval','selRisk','selAcct'].forEach(id=>$(id).addEventListener('change',fetchAuto));
$('mRun').addEventListener('click',runManual);
['mWr','mStop','mTp','mTpm','mEval','mRisk','mAcct'].forEach(id=>$(id).addEventListener('change',runManual));
window.addEventListener('resize',()=>{ if(MODE==='auto') drawPaths(); else runManual(); });

loadConfigs().then(()=>fetchAuto());
"""

PROP_HTML = shell("/prop", "Prop", _BODY, script=_SCRIPT, head_extra=_HEAD,
                  meta="breakout eval")
