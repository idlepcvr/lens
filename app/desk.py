"""LENS /desk — live entry cockpit. One screen that answers: can I enter RIGHT NOW?

Mobile-first HUD / instrument-cluster design, built on the shared design system
(app.theme.shell) like every other page. Renders desk_state() from app.setups:
per-direction verdict (ENTER / BLOCKED / STAND DOWN), the trade plan + money
ticket when clean, live S1-S5 condition checklists, active vetoes, and the
realized per-setup scoreboard. Pulls the live pending signal from /api/signals
and lets you TAKE A+ / TAKE / SKIP it from the thumb zone — the decision POSTs
straight to /api/signals/{id}/decide (same path as the ntfy buttons). Built
phone-first: a single ~460px column, big glanceable numbers, sticky action bar.
"""

from .theme import shell

# Custom top-bar right slot: the live/stale dot + label the render JS updates.
RIGHT = '<div class="live"><span class="dot" id="dot"></span><span id="livetxt">live</span></div>'

BODY = r"""
<div id="body"><div class="skeleton">reading market state…</div></div>

<div class="foot">
  Patterns are mechanical coin-flips alone — realized WRs came from <i>your selection inside
  these contexts</i> + fast exits. ENTER = "the context where you historically win is live",
  not a guaranteed trade. Refreshes every 60s · <a href="#" id="refresh">refresh now</a>
</div>

<div class="actions" id="actions">
  <div class="actions-inner">
    <div class="act-label" id="actlabel"></div>
    <div class="act-row">
      <button class="btn skip"  id="b-skip"  onclick="decide('rejected',null)">SKIP<span class="cap">reject</span></button>
      <button class="btn take"  id="b-take"  onclick="decide('approved',3)">TAKE<span class="cap">conv 3</span></button>
      <button class="btn aplus" id="b-aplus" onclick="decide('approved',5)">TAKE A+<span class="cap">conv 5</span></button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>
"""

SCRIPT = r"""
const $ = id => document.getElementById(id);
const VLAB = {long:"LONG", short:"SHORT"};
const ARROW = {long:"▲", short:"▼"};
let STATE = null;      // last desk state
let PENDING = {};      // {long:signal, short:signal} live pending signals
let RISK = {};         // remembered risk-€ per direction

const STATE_TXT = {
  enter:"ENTER", blocked:"BLOCKED", veto:"NO TRADE", stand_down:"STAND DOWN"
};
const STATE_SUB = {
  enter:"context where you win is live — this is a real signal",
  blocked:"DO NOT TAKE — a setup fired but a veto kills it",
  veto:"DO NOT TAKE — veto active, sit on hands",
  stand_down:"nothing here — no setup fired this bar"
};
const rank = {enter:3, blocked:2, veto:1, stand_down:0};

function toast(msg, cls){
  const t = $('toast'); t.textContent = msg; t.className = 'toast show ' + cls;
  setTimeout(()=>{ t.className = 'toast ' + cls; }, 2600);
}
function chip(label,val,cls){return `<div class="chip ${cls||''}">${label} <b>${val}</b></div>`;}
function secHead(id,title){return `<div class="sect" id="h-${id}" onclick="tog('${id}')"><span class="caret">▾</span><span class="ttl">${title}</span><span class="line"></span></div>`;}
function tog(id){ $('h-'+id).classList.toggle('closed'); $('s-'+id).classList.toggle('closed'); }
function money(n){return n.toLocaleString(undefined,{maximumFractionDigits:0});}

function ticketHTML(dir,v,d){
  if(!v.plan) return '';
  const p = v.plan, live = v.state==='enter';
  const risk0 = RISK[dir] ?? (d.balance?Math.max(1,Math.round(d.balance*0.1)):10);
  return `<div class="ticket ${live?'':'dim'}">
    ${live?'':'<div class="ticket-ref">reference only — context says no. if price gets here clean, this is the shape:</div>'}
    <div class="tg">
      <div class="cell"><div class="k">entry</div><div class="v">${money(p.entry)}</div></div>
      <div class="cell"><div class="k">R : R<a class="qh" href="/glossary#rr" target="_blank" rel="noopener">?</a></div><div class="v">${p.rr}<span class="sub" style="display:inline"> reward/risk</span></div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(p.stop)}</div><div class="sub">−${p.sl_pct}% risk</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(p.target)}</div><div class="sub">+${p.tp_pct}% reward</div></div>
    </div>
    <div class="sizer"><label>risk €<a class="qh" href="/glossary#risk" target="_blank" rel="noopener">?</a></label>
      <input type="number" id="risk-${dir}" value="${risk0}" inputmode="numeric">
      <span class="size-out" id="size-${dir}"></span></div>
    <div class="outcome" id="out-${dir}"></div>
    <div class="exit-note">⏱ winners resolve 2–8h (50% WR, +€1,552). Trades closed &lt;2h ran 34–35% (−€747). Take +0.5–0.9% if it's there — don't panic-scalp out in minutes.</div>
  </div>`;
}

function wireSizer(dir,d){
  const inp = $('risk-'+dir); if(!inp) return;
  const p = STATE.verdicts[dir].plan;
  const upd = ()=>{
    const risk = parseFloat(inp.value)||0; RISK[dir]=risk;
    const notional = risk/(p.sl_pct/100), btc = notional/d.close, fee = notional*0.0004;
    const win = notional*(p.tp_pct/100)-fee, early = notional*0.007-fee, loss = risk+fee;
    $('size-'+dir).innerHTML = `→ €${money(notional)} <span style="color:var(--dim)">(${btc.toFixed(4)} BTC · €${money(notional/10)} margin @10x)</span>`;
    $('out-'+dir).innerHTML =
      `target <b class="g">+€${win.toFixed(2)}</b> · +0.7% early <b class="g">+€${early.toFixed(2)}</b> · stop <b class="r">−€${loss.toFixed(2)}</b>`
      + (d.balance?` · <span style="color:var(--dim)">stop = ${(loss/d.balance*100).toFixed(1)}% of acct</span>`:'');
  };
  inp.addEventListener('input',upd); upd();
}

function gaugeHTML(dir,v,d,primary){
  const cls = v.state;
  let body = '';
  if(v.vetoes.length)
    body += `<ul class="vetolist">`+v.vetoes.map(x=>`<li>${x}</li>`).join('')+`</ul>`;
  body += ticketHTML(dir,v,d);
  const setupTag = v.setups.length?`<span class="g-setup">${v.setups.join(' + ')}</span>`:'';
  return `<div class="gauge ${cls}">
    <div class="g-top">
      <span class="g-dir ${dir}"><span class="arrow">${ARROW[dir]}</span> ${VLAB[dir]}</span>
      ${setupTag}
    </div>
    <div class="verdict">${STATE_TXT[v.state]}</div>
    <div class="verdict-sub">${STATE_SUB[v.state]}<br><span style="color:var(--faint)">read of the 1H bar that closed ${d.bar_ts.slice(11,16)} UTC · ${d.bar_age_min}m ago — not a logged trade</span></div>
    ${body}
  </div>`;
}

function render(){
  const d = STATE;
  const stale = d.bar_age_min > 130;
  $('dot').className = 'dot' + (stale?' stale':'');
  $('livetxt').textContent = stale ? 'stale' : 'live';

  // order directions: best state first (the actionable one on top)
  const dirs = ['long','short'].sort((a,b)=> rank[d.verdicts[b].state]-rank[d.verdicts[a].state]);

  let html = `<div class="tape">
    <div class="px">$${d.close.toLocaleString()}<span class="c"> BTC</span></div>
    <div class="meta">
      1H bar <b>${d.bar_ts.slice(11,16)}</b> UTC<br>
      <span class="${stale?'stale':''}">${stale?'⚠ candle stale · ':''}closed <b>${d.bar_age_min}m</b> ago</span>
      ${d.balance?`<br>account <b>€${d.balance.toFixed(0)}</b>`:''}
    </div>
  </div>`;

  // help / explainer (collapsed by default)
  html += `<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this desk</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-help"><div class="help-body">`
    + `<h4>what this page is</h4>A <b>live read of the 1H candle that just closed</b> — not a trade log. It answers one thing: <b>can I enter right now, long or short?</b> Refreshes every 60s.`
    + `<h4>the verdict</h4><b class="g">ENTER</b> = real signal, the context where you historically win is live → it also buzzes your phone + lights the buttons below. <b class="r">BLOCKED / NO TRADE</b> = do not take it. <b>STAND DOWN</b> = nothing here. LONG and SHORT both always show so you see both sides.`
    + `<h4>the only knob is risk €</h4>You don't set entry/stop/target — the <b>strategy</b> does (entry = price now, stop −0.63%, target +1.5% — the ONE validated geometry, every surface reads it). You only type how many <b>€ you'll risk</b>; it shows position size + exact €-win / €-loss.`
    + `<h4>R : R</h4>reward ÷ risk → target 1.5% ÷ stop 0.63% = <b>2.38</b>. The 2026-07-02 audit: the old 0.95% target was too tight — half your winners ran to 1.5%+.`
    + `<h4>you place the trade, not LENS</h4>LENS is read-only. You execute on Kraken yourself; it syncs your fills after and tags <i>which setup</i> it was.`
    + `<h4>sections below</h4><b>context</b> = the readings that caused the verdict (the why). <b>checklists</b> = all 5 recipes, ✓/✗ per condition. <b>scoreboard</b> = how each setup really performed. Tap any header to collapse.`
    + `</div></div>`;
  html += `<div class="gauges">`;
  for(const dir of dirs) html += gaugeHTML(dir, d.verdicts[dir], d, dir===dirs[0]);
  html += `</div>`;

  // context chips
  const c = d.context;
  const kz = {london_kz:'London 07–10',ny_am_kz:'NY AM 13–16 ★',ny_pm_kz:'NY PM 18–21 ☠',none:'—'}[c.killzone];
  html += secHead('ctx','context — why the verdict') + `<div class="sec-body" id="s-ctx"><div class="chips">`
    + chip('RSI', c.rsi===null?'—':c.rsi+' '+(c.rsi_zone==='dead'?'☠':c.rsi_zone), c.rsi_zone==='dead'?'bad':(c.rsi_zone?'good':''))
    + chip('killzone', kz, c.killzone==='ny_am_kz'?'good':c.killzone==='ny_pm_kz'?'bad':'')
    + chip('7d range', c.pd_zone||'—')
    + chip('sweep', c.sweep?c.sweep+' taken':'none')
    + chip('PD raid', c.pd_raid||'none')
    + chip('displacement', c.displacement||'—')
    + chip('EMA21', c.slope||'flat')
    + chip('3× bear', c.bear_streak3?'yes':'no', c.bear_streak3?'bad':'')
    + `</div></div>`;

  // setup cards
  html += secHead('setups','setup checklists') + `<div class="sec-body" id="s-setups"><div class="setups-grid">`;
  html += d.checklists.map(s=>{
    const cls = s.active ? (s.vetoed?'vetoed':'active') : '';
    const flag = s.active ? (s.vetoed
        ? `<div class="sflag veto">▲ conditions met but VETOED — stand down</div>`
        : `<div class="sflag go">● LIVE — context active now</div>`) : '';
    return `<div class="scard ${cls}"><div class="sh">
      <span class="sid">${s.id} <span class="d-${s.direction}">${s.direction.toUpperCase()}</span></span>
      <span class="swr">${s.wr}</span></div>
      <div class="sname">${s.name}</div>`
      + s.conds.map(x=>`<div class="cond ${x.ok?'ok':'no'}"><span class="tk">${x.ok?'✓':'·'}</span>${x.label}</div>`).join('')
      + flag + `</div>`;
  }).join('') + `</div></div>`;

  // scoreboard
  html += secHead('sb','realized scoreboard') + `<div class="sec-body" id="s-sb"><div class="sb-wrap"><table class="sb">
    <tr><th>tag</th><th>n</th><th>WR</th><th>PnL €</th><th>exp</th><th>halves</th></tr>`
    + Object.entries(d.scoreboard).map(([k,s])=>`<tr>
      <td class="${k==='VETO'?'r':k==='NONE'?'m':''}">${k}</td><td>${s.n}</td>
      <td class="${s.wr>=50?'g':s.wr<40?'r':''}">${s.wr??'—'}%</td>
      <td class="${s.pnl>=0?'g':'r'}">${s.pnl>=0?'+':''}${s.pnl.toFixed(0)}</td>
      <td class="m">${s.exp??'—'}</td><td class="m">${(s.wr_halves||[]).join(' / ')}</td></tr>`).join('')
    + `</table></div></div>`;

  $('body').innerHTML = html;
  for(const dir of dirs) wireSizer(dir,d);
  renderActions();
}

// ── live pending signal → action bar ──
function renderActions(){
  // pick the most actionable pending signal: enter direction first
  let target = null;
  for(const dir of ['long','short']){
    const sig = PENDING[dir];
    if(sig){ target = {dir, sig}; if(STATE && STATE.verdicts[dir].state==='enter') break; }
  }
  const box = $('actions');
  if(!target){ box.classList.remove('show'); return; }
  ACTIVE_SIGNAL = target.sig;
  const v = STATE ? STATE.verdicts[target.dir] : null;
  const warn = v && v.state!=='enter' ? ` · ⚠ ${STATE_TXT[v.state]}` : '';
  $('actlabel').innerHTML = `live signal · <b>${target.sig.trigger_type} ${VLAB[target.dir]}</b>${warn}`;
  ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=false);
  box.classList.add('show');
}

let ACTIVE_SIGNAL = null;
async function decide(status, conviction){
  if(!ACTIVE_SIGNAL) return;
  ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=true);
  const payload = status==='approved'
    ? {status, your_conviction:conviction}
    : {status, rejection_reason:'skipped from desk'};
  try{
    const r = await fetch(`/api/signals/${ACTIVE_SIGNAL.signal_id}/decide`,{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const j = await r.json();
    if(!r.ok){ toast(j.detail||'decide failed','err'); ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=false); return; }
    if(status==='approved') toast(`✓ TAKEN · conviction ${conviction}`,'ok');
    else toast('✕ SKIPPED','no');
    delete PENDING[ACTIVE_SIGNAL.direction];
    ACTIVE_SIGNAL = null;
    setTimeout(()=>{ $('actions').classList.remove('show'); loadPending(); }, 900);
  }catch(e){
    toast('network error','err'); ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=false);
  }
}

async function loadPending(){
  try{
    const r = await fetch('/api/signals?status=pending');
    const j = await r.json();
    PENDING = {};
    for(const s of (j.signals||[])) if(!PENDING[s.direction]) PENDING[s.direction]=s;
    renderActions();
  }catch(e){ /* non-fatal */ }
}

async function load(){
  try{
    const [stRes] = await Promise.all([fetch('/api/setups/state'), loadPending()]);
    STATE = await stRes.json();
    render();
  }catch(e){
    $('body').innerHTML = '<div class="skeleton" style="color:var(--amber)">failed to load state — is the candle fetch offline?</div>';
  }
}
$('refresh').addEventListener('click', e=>{e.preventDefault(); load();});
load();
setInterval(load, 60000);
"""

DESK_HTML = shell("/desk", "Desk", BODY, script=SCRIPT, right=RIGHT, meta="can I enter?")
