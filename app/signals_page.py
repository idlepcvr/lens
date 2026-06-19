"""LENS /signals — pending queue + decision history, built on the shared design
system (app.theme.shell). Approve/reject each pending signal with conviction
(TAKE A+ = 5, TAKE = 3) or SKIP, same decision path as the desk + ntfy buttons
(POST /api/signals/{id}/decide). Recent decisions listed below.
"""

from .theme import shell

BODY = r"""
<div id="body"><div class="skeleton">loading signals…</div></div>
<div class="foot">
  Every signal — taken or skipped — is data. Skips train the veto map.
  Refreshes every 60s · <a href="#" id="refresh">refresh now</a>
</div>
<div class="toast" id="toast"></div>
"""

SCRIPT = r"""
const $ = id => document.getElementById(id);
const VLAB = {long:"LONG", short:"SHORT"};
const ARROW = {long:"▲", short:"▼"};

function toast(msg, cls){
  const t = $('toast'); t.textContent = msg; t.className = 'toast show ' + cls;
  setTimeout(()=>{ t.className = 'toast ' + cls; }, 2600);
}
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
      <div class="cell"><div class="k">R : R</div><div class="v">${s.expected_rr??'—'}</div></div>
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

// each decision row expands to the full plan as proposed + decision timing
function historyRow(s){
  const id = s.signal_id;
  const conv = s.your_conviction!=null ? s.your_conviction : '—';
  const g = gap(s.received_at, s.decided_at);
  const detail = `
    <div class="tg" style="margin:2px 0 8px">
      <div class="cell"><div class="k">entry</div><div class="v">${money(s.entry_price)}</div></div>
      <div class="cell"><div class="k">R : R</div><div class="v">${s.expected_rr??'—'}</div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(s.stop_price)}</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(s.target_price)}</div></div>
    </div>
    <div class="kv"><span class="k">strategy</span><span class="v">${s.strategy_name||'—'}${s.symbol?(' · '+s.symbol):''}</span></div>
    <div class="kv"><span class="k">proposed</span><span class="v">${fmtTs(s.received_at)}</span></div>
    <div class="kv"><span class="k">decided</span><span class="v">${fmtTs(s.decided_at)}${g?(' · '+g+' later'):''}</span></div>
    <div class="kv"><span class="k">conviction</span><span class="v">${conv}</span></div>
    ${s.rejection_reason?`<div class="kv"><span class="k">reason</span><span class="v">${s.rejection_reason}</span></div>`:''}`;
  return `<tr class="hrow" onclick="toggleRow('${id}')" style="cursor:pointer">
    <td>${s.trigger_type||'?'}</td>
    <td class="${s.direction==='long'?'g':'r'}">${VLAB[s.direction]||s.direction||''}</td>
    <td><span class="badge ${s.status}">${s.status}</span></td>
    <td class="m">${conv}</td>
    <td class="m">${ago(s.decided_at||s.received_at)} ▾</td>
  </tr>
  <tr id="d-${id}" style="display:none"><td colspan="5" style="background:var(--panel);padding:10px 12px">${detail}</td></tr>`;
}

async function decide(id, status, conviction){
  const card = $('card-'+id);
  if(card) card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const payload = status==='approved'
    ? {status, your_conviction:conviction}
    : {status, rejection_reason:'skipped from signals'};
  try{
    const r = await fetch(`/api/signals/${id}/decide`,{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const j = await r.json();
    if(!r.ok){ toast(j.detail||'decide failed','err'); if(card) card.querySelectorAll('button').forEach(b=>b.disabled=false); return; }
    toast(status==='approved'?`✓ TAKEN · conviction ${conviction}`:'✕ SKIPPED', status==='approved'?'ok':'no');
    if(card){ card.style.transition='opacity .4s,transform .4s'; card.style.opacity='0'; card.style.transform='scale(.96)'; }
    setTimeout(load, 700);
  }catch(e){
    toast('network error','err'); if(card) card.querySelectorAll('button').forEach(b=>b.disabled=false);
  }
}

function render(all){
  const pending = all.filter(s=>s.status==='pending')
                     .sort((a,b)=>(b.received_at||'').localeCompare(a.received_at||''));
  const decided = all.filter(s=>s.status!=='pending')
                     .sort((a,b)=>(b.decided_at||b.received_at||'').localeCompare(a.decided_at||a.received_at||''))
                     .slice(0,25);

  let html = '';
  // help
  html += `<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ what is this page</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-help"><div class="help-body">`
    + `<h4>the queue</h4>Signals the hourly scanner fired land here as <b class="a">pending</b>. Decide each one: <b class="g">TAKE A+</b> (high conviction, =5), <b class="g">TAKE</b> (=3), or <b class="r">SKIP</b>. Same buttons as the phone alert + the desk.`
    + `<h4>why skips matter</h4>A skip is recorded too — it trains the veto map (where you correctly stood down). Don't ignore them.`
    + `<h4>conviction</h4>The number feeds your conviction win-rate metric. Be honest: A+ only for genuine A+ context, not FOMO.`
    + `<h4>you still place the trade</h4>Approving here logs the decision — it does <b>not</b> place an order. Execute on Kraken yourself.`
    + `</div></div>`;

  // pending
  html += secHead('pending', `pending · ${pending.length}`) + `<div class="sec-body" id="s-pending">`;
  if(pending.length===0){
    html += `<div class="panel dim" style="text-align:center;color:var(--dim)">no pending signals — scanner runs hourly at :02</div>`;
  } else {
    html += `<div class="grid-auto">` + pending.map(pendingCard).join('') + `</div>`;
  }
  html += `</div>`;

  // history
  html += secHead('hist','recent decisions') + `<div class="sec-body" id="s-hist"><div class="sb-wrap"><table class="sb">`
    + `<tr><th>setup</th><th>dir</th><th>status</th><th>conv</th><th>when</th></tr>`
    + (decided.length?decided.map(historyRow).join(''):'<tr><td colspan="5" class="m">no decisions yet</td></tr>')
    + `</table></div></div>`;

  $('body').innerHTML = html;
}

async function load(){
  try{
    const r = await fetch('/api/signals?limit=500');
    const j = await r.json();
    render(j.signals||[]);
  }catch(e){
    $('body').innerHTML = '<div class="skeleton" style="color:var(--amber)">failed to load signals</div>';
  }
}
$('refresh').addEventListener('click', e=>{e.preventDefault(); load();});
load();
setInterval(load, 60000);
"""


def render() -> str:
    return shell("/signals", "Signals", BODY, script=SCRIPT, meta="approve / reject")
