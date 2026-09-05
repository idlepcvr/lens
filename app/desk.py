"""LENS /desk — live entry cockpit. One screen that answers: can I enter RIGHT NOW?

Mobile-first HUD / instrument-cluster design, built on the shared design system
(app.theme.shell) like every other page. Renders desk_state() from app.setups:
per-direction verdict (ENTER / BLOCKED / STAND DOWN), the trade plan + money
ticket when clean, live S1-S5 condition checklists, active vetoes, and the
realized per-setup scoreboard. Pulls the live pending signal from /api/signals
and lets you TAKE A+ / TAKE / SKIP it from the thumb zone — the decision POSTs
straight to /api/signals/{id}/decide (same path as the ntfy buttons). Built
phone-first: a single ~460px column, big glanceable numbers, sticky action bar.

2026-09-05: merged /signals into this page. Desk and Signals were the same
job — same data, same /api/signals/{id}/decide endpoint — shown two ways:
cockpit-glance vs list-scan. The cockpit above stays the primary view; a
"queue & decisions" section below it (queue, blocked, recent decisions) folds
in everything Signals uniquely had: the full pending queue for when more than
one signal is live at once, the vetoed/blocked audit trail, and decision
history. /signals now 301s here (see LEGACY_ROUTES in main.py).
"""

from .theme import shell

# Custom top-bar right slot: the live/stale dot + label the render JS updates.
RIGHT = '<div class="live"><span class="dot" id="dot"></span><span id="livetxt">live</span></div>'

BODY = r"""
<div id="body"><div class="skeleton">reading market state…</div></div>

<div id="queue"><div class="skeleton">loading queue…</div></div>

<div class="foot">
  Patterns are mechanical coin-flips alone — realized WRs came from <i>your selection inside
  these contexts</i> + fast exits. ENTER = "the context where you historically win is live",
  not a guaranteed trade. Refreshes every 60s · <a href="#" id="refresh">refresh now</a>
</div>

<div class="actions" id="actions">
  <div class="actions-inner">
    <div class="act-label" id="actlabel"></div>
    <div class="act-row">
      <button class="btn skip"  id="b-skip"  onclick="deskDecide('rejected',null)">SKIP<span class="cap">reject</span></button>
      <button class="btn take"  id="b-take"  onclick="deskDecide('approved',3)">TAKE<span class="cap">conv 3</span></button>
      <button class="btn aplus" id="b-aplus" onclick="deskDecide('approved',5)">TAKE A+<span class="cap">conv 5</span></button>
    </div>
    <div style="margin-top:6px;font-size:11px;color:var(--dim);text-align:center">signals you skipped went on to win 83% (n=30, one_at_a_time) — SKIP only on a veto you can name, not a feeling</div>
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
function money(n){ return (n==null)?'—':Number(n).toLocaleString(undefined,{maximumFractionDigits:0}); }
function ago(iso){
  if(!iso) return '';
  const t = new Date(iso.endsWith('Z')||iso.includes('+')?iso:iso+'Z');
  const m = Math.round((Date.now()-t.getTime())/60000);
  if(m<60) return m+'m ago';
  if(m<1440) return Math.round(m/60)+'h ago';
  return Math.round(m/1440)+'d ago';
}

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
    // position that puts exactly `risk` € at the stop, and its BTC size
    const notional = risk/(p.sl_pct/100), btc = notional/d.close;
    // outcomes priced at MEASURED friction (taker entries — what the book pays),
    // then the € recovered by resting post-only limits instead of crossing.
    const fee = notional*GEO.fee_t, feeM = notional*GEO.fee_m, save = fee-feeM;
    const win = notional*(p.tp_pct/100)-fee, early = notional*0.007-fee, loss = risk+fee;
    $('size-'+dir).innerHTML = `→ €${money(notional)} <span style="color:var(--dim)">(${btc.toFixed(4)} BTC · €${money(notional/10)} margin @10x)</span>`;
    $('out-'+dir).innerHTML =
      `target <b class="g">+€${win.toFixed(2)}</b> · +0.7% early <b class="g">+€${early.toFixed(2)}</b> · stop <b class="r">−€${loss.toFixed(2)}</b>`
      + (d.balance?` · <span style="color:var(--dim)">stop = ${(loss/d.balance*100).toFixed(1)}% of acct</span>`:'')
      + `<br><span style="color:var(--dim)">fees €${fee.toFixed(2)} market → €${feeM.toFixed(2)} post-only limit · </span><b class="g">save €${save.toFixed(2)}</b><span style="color:var(--dim)"> — rest the entry, don't cross</span>`;
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
    + `<h4>the only knob is risk €</h4>You don't set entry/stop/target — the <b>strategy</b> does (entry = price now, stop −${GEO.sl}%, target +${GEO.tp}% — the ONE geometry, every surface reads it). You only type how many <b>€ you'll risk</b>; it shows position size + exact €-win / €-loss.`
    + `<h4>R : R</h4>reward ÷ risk → target ${GEO.tp}% ÷ stop ${GEO.sl}% = <b>${GEO.rr}</b>. These are derived, not fitted: the stop is σ·√(hold ÷ R:R) for a trade meant to resolve in ~${GEO.hold} days. <a href="/geometry" style="color:var(--accent)">why</a>.`
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
// shared decide path — sticky action bar (deskDecide, below) and the queue
// section's per-card buttons both funnel through here, same endpoint the
// ntfy phone alert also hits.
async function decide(id, status, conviction){
  const isActive = ACTIVE_SIGNAL && ACTIVE_SIGNAL.signal_id===id;
  const card = $('card-'+id);
  if(isActive) ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=true);
  if(card) card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const payload = status==='approved'
    ? {status, your_conviction:conviction}
    : {status, rejection_reason:'skipped from desk'};
  try{
    const r = await fetch(`/api/signals/${id}/decide`,{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const j = await r.json();
    if(!r.ok){
      toast(j.detail||'decide failed','err');
      if(isActive) ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=false);
      if(card) card.querySelectorAll('button').forEach(b=>b.disabled=false);
      return;
    }
    if(status==='approved') toast(`✓ TAKEN · conviction ${conviction}`,'ok');
    else toast('✕ SKIPPED','no');
    if(card){ card.style.transition='opacity .4s,transform .4s'; card.style.opacity='0'; card.style.transform='scale(.96)'; }
    if(isActive){
      delete PENDING[ACTIVE_SIGNAL.direction];
      ACTIVE_SIGNAL = null;
      $('actions').classList.remove('show');
    }
    setTimeout(()=>{ loadPending(); loadQueue(); }, isActive?900:700);
  }catch(e){
    toast('network error','err');
    if(isActive) ['b-skip','b-take','b-aplus'].forEach(b=>$(b).disabled=false);
    if(card) card.querySelectorAll('button').forEach(b=>b.disabled=false);
  }
}
// sticky action-bar buttons only ever act on the current ACTIVE_SIGNAL.
function deskDecide(status, conviction){
  if(!ACTIVE_SIGNAL) return;
  decide(ACTIVE_SIGNAL.signal_id, status, conviction);
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

// ── queue & decisions (folded in from the old /signals page) ─────────────────
// Sticky action bar above handles the one most-actionable pending signal;
// this section is the rest: the full queue for when more than one signal is
// live, the vetoed/blocked audit trail, and recent decision history.

// same-zone clustering — the hourly scanner re-fires the same context, so
// group consecutive signals (same direction, entry within 0.5%, ≤6h apart)
// into one trade idea for display. Nothing is merged in the data — every
// member keeps its own identity and its own TAKE/SKIP.
const ZONE_PCT=0.005, ZONE_GAP_MS=6*3600e3;
function clusterize(list){ // list sorted newest-first
  const out=[];
  for(const s of list){
    const c=out[out.length-1];
    const prev=c&&c.members[c.members.length-1];
    if(c && s.direction===c.dir && s.entry_price && c.entry &&
       Math.abs(s.entry_price-c.entry)/c.entry<ZONE_PCT &&
       prev && (new Date(prev.received_at)-new Date(s.received_at))<ZONE_GAP_MS){
      c.members.push(s);
    } else {
      out.push({dir:s.direction, entry:s.entry_price, members:[s]});
    }
  }
  return out;
}
function zoneLabel(c){
  const es=c.members.map(m=>m.entry_price).filter(Boolean);
  if(es.length<2) return '';
  const lo=Math.min(...es), hi=Math.max(...es);
  const w=((hi-lo)/lo*100).toFixed(2);
  return `${money(lo)}–${money(hi)} · ${w}% apart`;
}

function pendingCard(s){
  const dir = s.direction;
  return `<div class="scard active" id="card-${s.signal_id}">
    <div class="sh">
      <span class="sid">${s.trigger_type||'?'} <span class="d-${dir}">${ARROW[dir]||''} ${VLAB[dir]||dir}</span></span>
      <span class="badge pending">pending · ${ago(s.received_at)}</span>
    </div>
    <div class="sname">${s.strategy_name||''} ${s.symbol?('· '+s.symbol):''}</div>
    <div class="tg" style="margin-bottom:12px">
      <div class="cell"><div class="k">entry</div><div class="v">${money(s.entry_price)}</div></div>
      <div class="cell"><div class="k">R : R<a class="qh" href="/glossary#rr" target="_blank" rel="noopener">?</a></div><div class="v">${s.expected_rr??'—'}</div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(s.stop_price)}</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(s.target_price)}</div></div>
    </div>
    <div class="act-row">
      <button class="btn skip"  onclick="decide('${s.signal_id}','rejected',null)">SKIP<span class="cap">reject</span></button>
      <button class="btn take"  onclick="decide('${s.signal_id}','approved',3)">TAKE<span class="cap">conv 3</span></button>
      <button class="btn aplus" onclick="decide('${s.signal_id}','approved',5)">TAKE A+<span class="cap">conv 5</span></button>
    </div>
  </div>`;
}

// blocked cards — a setup that matched and was vetoed. No buttons: blocked is
// not actionable, it's evidence for "would taking the vetoed ones have made
// money?", which the scoreboard above can't answer (it only sees trades).
function vetoRules(s){
  const r = s.rejection_reason||'';
  return r.startsWith('veto:') ? r.slice(5).split(',').filter(Boolean) : [];
}
function ledgerLine(rules){
  const exact = VETO_LEDGER.combos[rules.slice().sort().join(',')];
  if(exact) return {txt:`this exact veto bucket, realized: <b>${exact.n} trades · €${exact.pnl>0?'+':'−'}${money(Math.abs(exact.pnl))} · ${exact.wr}% WR</b>`, pnl:exact.pnl};
  const parts = rules.map(r=>{
    const x = VETO_LEDGER.rules[r];
    return x ? `${r} ${x.n}t €${x.pnl>0?'+':'−'}${money(Math.abs(x.pnl))}` : null;
  }).filter(Boolean);
  if(!parts.length) return {txt:'no realized trades in this bucket yet', pnl:0};
  return {txt:`no trade hit this exact combination · per rule: <b>${parts.join(' · ')}</b>`,
          pnl:rules.reduce((a,r)=>a+((VETO_LEDGER.rules[r]||{}).pnl||0),0)};
}
function blockedCard(s){
  const dir = s.direction, rules = vetoRules(s);
  const led = ledgerLine(rules);
  const checks = Array.isArray(s.mtf_confluence)?s.mtf_confluence:[];
  return `<div class="scard" style="opacity:.86">
    <div class="sh">
      <span class="sid">${s.trigger_type||'?'} <span class="d-${dir}">${ARROW[dir]||''} ${VLAB[dir]||dir}</span></span>
      <span class="badge rejected">blocked · ${ago(s.received_at)}</span>
    </div>
    <div class="sname">${s.strategy_name||''} ${s.entry_price?('· '+money(s.entry_price)):''}</div>
    ${checks.length?`<div style="font-size:12px;margin:8px 0 2px"><span class="g">setup ✓</span> <span class="m">${checks.join(' · ')}</span></div>`:''}
    <div style="font-size:12px;margin:8px 0 2px"><span class="r">blocked ✗</span></div>
    <ul style="margin:2px 0 0 16px;padding:0;font-size:12px;color:var(--dim)">
      ${rules.map(r=>`<li>${VETO_LABELS[r]||r}</li>`).join('')}
    </ul>
    <div style="font-size:12px;margin-top:10px" class="${led.pnl<0?'g':'a'}">${led.txt}</div>
  </div>`;
}

function fmtTs(iso){
  if(!iso) return '—';
  const d = new Date(iso.endsWith('Z')||iso.includes('+')?iso:iso+'Z');
  return d.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function gap(a,b){
  if(!a||!b) return '';
  const ta=new Date(a.endsWith('Z')||a.includes('+')?a:a+'Z'), tb=new Date(b.endsWith('Z')||b.includes('+')?b:b+'Z');
  const m=Math.round((tb-ta)/60000);
  if(m<1) return '<1m'; if(m<60) return m+'m'; if(m<1440) return Math.round(m/60)+'h'; return Math.round(m/1440)+'d';
}
function toggleRow(id){
  const r=document.getElementById('d-'+id); if(!r) return;
  r.style.display = r.style.display==='none' ? '' : 'none';
}
function togGroup(gi){
  const rows=document.querySelectorAll(`tr[data-grp="${gi}"]`);
  const open=rows.length&&rows[0].style.display==='none';
  rows.forEach(r=>{
    r.style.display=open?'':'none';
    if(!open){
      const oc=r.getAttribute('onclick')||'';
      const m=oc.match(/toggleRow\('(.+)'\)/);
      if(m){ const d=document.getElementById('d-'+m[1]); if(d) d.style.display='none'; }
    }
  });
}

// the full order ticket (sizing as the alert + desk compute it) — same numbers
// you'd punch into Kraken. null when the signal predates ticket math.
function ticketBlock(t){
  if(!t) return '';
  const winBal = t.account + t.reward_usd, loseBal = t.account - t.risk_usd;
  return `<div style="font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.04em;margin:10px 0 4px">`
    + `full ticket · acct $${money(t.account)} · ${t.leverage}× · fee ${t.fee_rt_pct.toFixed(2)}%`
    + `<a class="qh" href="/glossary#notional" target="_blank" rel="noopener" title="notional, margin, risk, fees explained">?</a></div>`
    + `<div class="kv"><span class="k">notional</span><span class="v">$${money(t.notional)}</span></div>`
    + `<div class="kv"><span class="k">size</span><span class="v">${t.size_btc.toFixed(4)} ₿</span></div>`
    + `<div class="kv"><span class="k">margin</span><span class="v">$${money(t.margin_usd)} · ${t.cost_btc.toFixed(4)} ₿</span></div>`
    + `<div class="kv"><span class="k">win balance</span><span class="v g">$${money(winBal)} (+$${money(t.reward_usd)})</span></div>`
    + `<div class="kv"><span class="k">lose balance</span><span class="v r">$${money(loseBal)} (−$${money(t.risk_usd)})</span></div>`
    + `<div class="kv"><span class="k">risk</span><span class="v r">$${money(t.risk_usd)} · ${t.loss_pct.toFixed(1)}%</span></div>`
    + `<div class="kv"><span class="k">hurdle</span><span class="v">$${t.hurdle_usd.toFixed(2)} (${t.fee_rt_pct.toFixed(2)}% rt)</span></div>`
    + `<div class="kv"><span class="k">breakeven</span><span class="v">${money(t.breakeven)}</span></div>`
    + `<div class="kv"><span class="k">liquidation</span><span class="v">${money(t.liq)}</span></div>`;
}

// each decision row expands to the full plan as proposed + decision timing.
// grp: cluster index — member rows start hidden behind their zone summary row.
function historyRow(s, grp){
  const id = s.signal_id;
  const grpAttr = grp?` data-grp="${grp}" style="display:none"`:'';
  const conv = s.your_conviction!=null ? s.your_conviction : '—';
  const g = gap(s.received_at, s.decided_at);
  const detail = `
    <div class="tg" style="margin:2px 0 8px">
      <div class="cell"><div class="k">entry</div><div class="v">${money(s.entry_price)}</div></div>
      <div class="cell"><div class="k">R : R<a class="qh" href="/glossary#rr" target="_blank" rel="noopener">?</a></div><div class="v">${s.expected_rr??'—'}</div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(s.stop_price)}</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(s.target_price)}</div></div>
    </div>
    ${ticketBlock(s.ticket)}
    <div class="kv" style="margin-top:8px"><span class="k">strategy</span><span class="v">${s.strategy_name||'—'}${s.symbol?(' · '+s.symbol):''}</span></div>
    <div class="kv"><span class="k">proposed</span><span class="v">${fmtTs(s.received_at)}</span></div>
    <div class="kv"><span class="k">decided</span><span class="v">${fmtTs(s.decided_at)}${g?(' · '+g+' later'):''}</span></div>
    <div class="kv"><span class="k">conviction</span><span class="v">${conv}</span></div>
    ${s.rejection_reason?`<div class="kv"><span class="k">reason</span><span class="v">${s.rejection_reason}</span></div>`:''}
    ${s.linked_trade_id?`<div class="kv"><span class="k">trade</span><span class="v"><a href="/journal?trade=${s.linked_trade_id}" style="color:var(--accent);text-decoration:none" onclick="event.stopPropagation()">#${s.linked_trade_id}${s.pnl_eur!=null?` · ${s.pnl_eur>=0?'+':''}€${s.pnl_eur}`:''} — open in journal →</a></span></div>`:''}`;
  return `<tr class="hrow"${grpAttr} onclick="toggleRow('${id}')" style="cursor:pointer">
    <td>${grp?'&nbsp;&nbsp;↳ ':''}${s.trigger_type||'?'}</td>
    <td class="${s.direction==='long'?'g':'r'}">${VLAB[s.direction]||s.direction||''}</td>
    <td><span class="badge ${s.status}">${s.status}</span></td>
    <td class="m">${conv}</td>
    <td class="m">${ago(s.decided_at||s.received_at)} ▾</td>
  </tr>
  <tr id="d-${id}" style="display:none"><td colspan="5" style="background:var(--panel);padding:10px 12px">${detail}</td></tr>`;
}

function renderQueue(all){
  const pending = all.filter(s=>s.status==='pending')
                     .sort((a,b)=>(b.received_at||'').localeCompare(a.received_at||''));
  const isBlocked = s=>(s.rejection_reason||'').startsWith('veto:');
  const blocked = all.filter(isBlocked)
                     .sort((a,b)=>(b.received_at||'').localeCompare(a.received_at||''))
                     .slice(0,20);
  const decided = all.filter(s=>s.status!=='pending' && !isBlocked(s))
                     .sort((a,b)=>(b.decided_at||b.received_at||'').localeCompare(a.decided_at||a.received_at||''))
                     .slice(0,25);

  let html = '';
  html += `<div class="sect closed" id="h-qhelp" onclick="tog('qhelp')"><span class="caret">▾</span><span class="ttl">❔ queue, filters &amp; history</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-qhelp"><div class="help-body">`
    + `<h4>proposed vs decided</h4><b>Proposed</b> = when the hourly scanner spotted the setup. <b>Decided</b> = when a verdict was recorded. Click a row in <b>recent decisions</b> to expand its full ticket + both timestamps.`
    + `<h4>who decides</h4>Two deciders — the <b>reason</b> field says which acted. <b>1) LENS</b> — the discipline filters auto-reject a signal the instant it's born if it breaks a rule (proposed = decided). <b>2) You</b> — signals that pass sit <b class="a">pending</b> until TAKE/SKIP, here or on the sticky bar above.`
    + `<h4>the filters (auto-skips)</h4>Mined from the loss fingerprint — each one cost real money historically. A rejected signal is still stored so the dataset stays complete.`
    + `<ul style="margin:6px 0 0 16px;padding:0">`
    + `<li><code>filter:saturday</code> — no trading Saturday (UTC). Sat bled €2,606, PF 0.38.</li>`
    + `<li><code>filter:bleed_hour_02utc</code> / <code>_11utc</code> — skip the two hours that bleed across every year (PF 0.26 / 0.38).</li>`
    + `<li><code>filter:bad_venue_&lt;x&gt;</code> — Kraken only. Bybit cost €1,874 in 84 trades (PF 0.40), auto-rejected.</li>`
    + `<li><code>filter:cooldown_&lt;n&gt;min</code> — anti-revenge: &lt;5 min since the last accepted signal on the same symbol.</li>`
    + `</ul>`
    + `<h4>blocked</h4>A setup can match and still be stood down by a <b>veto rule</b>. Setup ✓, which rules ✗, and what that veto bucket actually did in your ledger. No alert fires — blocked isn't actionable, it's evidence. A bucket in the red means the veto saved you; a bucket in profit means the rule is costing you.`
    + `<h4>why skips matter</h4>A skip is recorded too — it trains the veto map. Don't ignore them.`
    + `</div></div>`;

  html += secHead('pending', `queue · ${pending.length} pending`) + `<div class="sec-body" id="s-pending">`;
  if(pending.length===0){
    html += `<div class="panel dim" style="text-align:center;color:var(--dim)">no pending signals — scanner runs hourly at :02</div>`;
  } else {
    html += clusterize(pending).map(c=>{
      if(c.members.length===1) return `<div class="grid-auto">${pendingCard(c.members[0])}</div>`;
      return `<div style="border:1px solid var(--line2);border-radius:10px;padding:10px;margin-bottom:12px">`
        + `<div style="font-size:11px;color:var(--dim);margin:0 2px 8px">≋ <b style="color:var(--ink)">${c.members.length} signals · same zone</b>`
        + ` <span class="mono">${zoneLabel(c)}</span> — one trade idea rescanned hourly; decide each</div>`
        + `<div class="grid-auto">${c.members.map(pendingCard).join('')}</div></div>`;
    }).join('');
  }
  html += `</div>`;

  html += `<div class="sect closed" id="h-blocked" onclick="tog('blocked')"><span class="caret">▾</span><span class="ttl">⃠ blocked · ${blocked.length}</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-blocked">`;
  if(blocked.length===0){
    html += `<div class="panel dim" style="text-align:center;color:var(--dim)">no blocked setups logged yet — they appear here when a setup matches and a veto rule stands it down</div>`;
  } else {
    html += `<div class="grid-auto">${blocked.map(blockedCard).join('')}</div>`;
  }
  html += `</div>`;

  let hist='';
  let gi=0;
  for(const c of clusterize(decided)){
    if(c.members.length===1){ hist+=historyRow(c.members[0]); continue; }
    gi++;
    const st={}; c.members.forEach(m=>st[m.status]=(st[m.status]||0)+1);
    const stTxt=Object.entries(st).map(([k,v])=>`<span class="badge ${k}">${v} ${k}</span>`).join(' ');
    const ty={}; c.members.forEach(m=>{const t=m.trigger_type||'?';ty[t]=(ty[t]||0)+1;});
    const tyTxt=Object.entries(ty).map(([t,n])=>`${n}× ${t}`).join(' + ');
    const newest=c.members[0];
    hist+=`<tr class="hrow" onclick="togGroup(${gi})" style="cursor:pointer">
      <td>≋ ${tyTxt} <span class="m mono" style="font-size:10px">${zoneLabel(c)}</span></td>
      <td class="${c.dir==='long'?'g':'r'}">${VLAB[c.dir]||c.dir||''}</td>
      <td>${stTxt}</td>
      <td class="m">—</td>
      <td class="m">${ago(newest.decided_at||newest.received_at)} ▸</td></tr>`;
    hist+=c.members.map(m=>historyRow(m,gi)).join('');
  }
  html += secHead('hist','recent decisions') + `<div class="sec-body" id="s-hist"><div class="sb-wrap"><table class="sb">`
    + `<tr><th>setup</th><th>dir</th><th>status</th><th>conv</th><th>when</th></tr>`
    + (decided.length?hist:'<tr><td colspan="5" class="m">no decisions yet</td></tr>')
    + `</table></div></div>`;

  $('queue').innerHTML = html;
}

async function loadQueue(){
  try{
    const r = await fetch('/api/signals?limit=500');
    const j = await r.json();
    renderQueue(j.signals||[]);
  }catch(e){
    $('queue').innerHTML = '<div class="skeleton" style="color:var(--amber)">failed to load queue</div>';
  }
}

async function load(){
  try{
    const [stRes] = await Promise.all([fetch('/api/setups/state'), loadPending(), loadQueue()]);
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

# Geometry into the help prose from the one source, so the explainer can never
# quote a stop the desk no longer uses. SCRIPT is a raw literal full of JS
# template braces, so it's prepended rather than .format()ed.
from .geometry import FRICTION_LADDER, FRICTION_PCT     # noqa: E402
from .geometry_page import HOLD_DAYS as _HOLD           # noqa: E402
from .setups import SL_PCT as _SL, TP_PCT as _TP        # noqa: E402

# fee_t = measured round-trip friction (the taker entries the book actually
# pays); fee_m = the ladder's "maker both sides". Both as fractions for JS.
# 346/512 realized trades were pure-taker IOC — the ticket's old hardcoded
# 0.0004 was quoting the maker world while the book lived in the taker one.
_GEO_JS = (f"const GEO={{sl:{_SL},tp:{_TP},"
           f"rr:'{_TP / _SL:.2f}',hold:{_HOLD:g},"
           f"fee_t:{FRICTION_PCT / 100:g},"
           f"fee_m:{FRICTION_LADDER['maker both sides'] / 100:g}}};\n")


def render() -> str:
    # VETO_LABELS + the realized veto ledger feed the queue section's
    # "blocked" cards (folded in from the old /signals page). Baked in at
    # render time, same as /signals did — they change only when the book
    # does, not worth a second round trip.
    import json

    from .setups import VETO_LABELS, veto_bucket_stats

    try:
        ledger = veto_bucket_stats()
    except Exception:
        ledger = {"rules": {}, "combos": {}}   # a dead stat never blanks the page
    preamble = (f"const VETO_LABELS={json.dumps(VETO_LABELS)};\n"
                f"const VETO_LEDGER={json.dumps(ledger)};\n")
    return shell("/desk", "Desk", BODY, script=_GEO_JS + preamble + SCRIPT,
                 right=RIGHT, meta="can I enter?")
