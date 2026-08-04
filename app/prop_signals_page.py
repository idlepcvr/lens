"""LENS /prop-signals — review queue for the PROP hero (ASIAN_RSI_DIP_v1).

The prop counterpart to /signals: alerts fired by app.prop_scan land here as
pending. Decide each (TAKE A+/TAKE/SKIP → POST /api/signals/{id}/decide, same as
the phone buttons). When you TAKE one and fill it on Kraken, "Log to ledger"
writes an open prop-book trade carrying linked_signal_id, so the eval equity book
ties back to the alert that triggered it.
"""

from .theme import shell

BODY = r"""
<div id="desk"></div>
<div id="body"><div class="skeleton">loading prop signals…</div></div>
<div class="foot">
  The hero only fires on Asian-session 4H closes (00 / 04 UTC). ENTER alerts land
  here + your phone. Decide, then place the order on Kraken and log the fill.
  Refreshes every 60s · <a href="#" id="refresh">refresh now</a>
</div>
<div class="toast" id="toast"></div>
"""

SCRIPT = r"""
const $ = id => document.getElementById(id);
const VLAB = {long:"LONG", short:"SHORT"}, ARROW = {long:"▲", short:"▼"};

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
  if(m<60) return m+'m ago'; if(m<1440) return Math.round(m/60)+'h ago'; return Math.round(m/1440)+'d ago';
}
function fmtTs(iso){ if(!iso) return '—'; const d=new Date(iso.endsWith('Z')||iso.includes('+')?iso:iso+'Z'); return d.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}); }
function gap(a,b){ if(!a||!b) return ''; const ta=new Date(a.endsWith('Z')||a.includes('+')?a:a+'Z'),tb=new Date(b.endsWith('Z')||b.includes('+')?b:b+'Z'); const m=Math.round((tb-ta)/60000); if(m<1)return'<1m'; if(m<60)return m+'m'; if(m<1440)return Math.round(m/60)+'h'; return Math.round(m/1440)+'d'; }
function toggleRow(id){ const r=$('d-'+id); if(r) r.style.display = r.style.display==='none'?'':'none'; }

// the prop order ticket — sized at $5k eval risk, legal-capped leverage
function ticketBlock(t){
  if(!t) return '';
  const winBal=t.account+t.win_usd, loseBal=t.account-t.loss_usd;
  return `<div style="font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.04em;margin:10px 0 4px">`
    + `prop ticket · ${t.eval} · acct $${money(t.account)} · risk ${t.risk_pct}%</div>`
    + `<div class="kv"><span class="k">notional</span><span class="v">$${money(t.notional)}</span></div>`
    + `<div class="kv"><span class="k">size</span><span class="v">${t.size_btc.toFixed(4)} ₿</span></div>`
    + `<div class="kv"><span class="k">leverage</span><span class="v">${t.leverage}× <span style="color:var(--dim)">(cap ${t.max_leverage}×)</span></span></div>`
    + `<div class="kv"><span class="k">margin</span><span class="v">$${money(t.margin_usd)}</span></div>`
    + `<div class="kv"><span class="k">win balance</span><span class="v g">$${money(winBal)} (+$${money(t.win_usd)})</span></div>`
    + `<div class="kv"><span class="k">lose balance</span><span class="v r">$${money(loseBal)} (−$${money(t.loss_usd)})</span></div>`
    + `<div class="kv"><span class="k">risk</span><span class="v r">$${money(t.risk_usd)} · ${t.actual_risk_pct}%</span></div>`
    + `<div class="kv"><span class="k">breakeven</span><span class="v">${money(t.breakeven)}</span></div>`
    + `<div class="kv"><span class="k">liquidation</span><span class="v">${money(t.liq)}</span></div>`;
}

function pendingCard(s){
  const dir=s.direction, t=s.ticket||{};
  return `<div class="scard active" id="card-${s.signal_id}">
    <div class="sh">
      <span class="sid">PROP <span class="d-${dir}">${ARROW[dir]||''} ${VLAB[dir]||dir}</span></span>
      <span class="badge pending">pending · ${ago(s.received_at)}</span>
    </div>
    <div class="sname">${s.strategy_name||''} · ${s.symbol||''}</div>
    <div class="tg" style="margin-bottom:8px">
      <div class="cell"><div class="k">entry</div><div class="v">${money(s.entry_price)}</div></div>
      <div class="cell"><div class="k">R : R</div><div class="v">${s.expected_rr??'—'}</div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(s.stop_price)}</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(s.target_price)}</div></div>
    </div>
    ${ticketBlock(t)}
    <div class="act-row" style="margin-top:10px">
      <button class="btn skip"  onclick="decide('${s.signal_id}','rejected',null)">SKIP<span class="cap">reject</span></button>
      <button class="btn take"  onclick="decide('${s.signal_id}','approved',3)">TAKE<span class="cap">conv 3</span></button>
      <button class="btn aplus" onclick="decide('${s.signal_id}','approved',5)">TAKE A+<span class="cap">conv 5</span></button>
    </div>
    <button class="btn" style="width:100%;margin-top:8px;background:var(--panel);border:1px solid var(--line)" onclick='logLedger(${JSON.stringify(s)})'>＋ Log fill to ledger →</button>
  </div>`;
}

function historyRow(s){
  const id=s.signal_id, conv=s.your_conviction!=null?s.your_conviction:'—', g=gap(s.received_at,s.decided_at);
  const detail = `
    <div class="tg" style="margin:2px 0 8px">
      <div class="cell"><div class="k">entry</div><div class="v">${money(s.entry_price)}</div></div>
      <div class="cell"><div class="k">R : R</div><div class="v">${s.expected_rr??'—'}</div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(s.stop_price)}</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(s.target_price)}</div></div>
    </div>
    ${ticketBlock(s.ticket)}
    <div class="kv" style="margin-top:8px"><span class="k">proposed</span><span class="v">${fmtTs(s.received_at)}</span></div>
    <div class="kv"><span class="k">decided</span><span class="v">${fmtTs(s.decided_at)}${g?(' · '+g+' later'):''}</span></div>
    <div class="kv"><span class="k">conviction</span><span class="v">${conv}</span></div>
    ${s.linked_trade_id?`<div class="kv"><span class="k">ledger</span><span class="v g">logged ✓</span></div>`:''}
    ${s.rejection_reason?`<div class="kv"><span class="k">reason</span><span class="v">${s.rejection_reason}</span></div>`:''}
    ${s.status==='approved'?`<button class="btn" style="margin-top:8px;background:var(--panel);border:1px solid var(--line)" onclick='logLedger(${JSON.stringify(s)})'>＋ Log fill to ledger →</button>`:''}`;
  return `<tr class="hrow" onclick="toggleRow('${id}')" style="cursor:pointer">
    <td style="font-size:11px">${s.strategy_name||'PROP'}</td>
    <td class="${s.direction==='long'?'g':'r'}">${VLAB[s.direction]||s.direction||''}</td>
    <td><span class="badge ${s.status}">${s.status}</span></td>
    <td class="m">${conv}</td>
    <td class="m">${ago(s.decided_at||s.received_at)} ▾</td>
  </tr>
  <tr id="d-${id}" style="display:none"><td colspan="5" style="background:var(--panel);padding:10px 12px">${detail}</td></tr>`;
}

async function decide(id, status, conviction){
  const card=$('card-'+id); if(card) card.querySelectorAll('.act-row button').forEach(b=>b.disabled=true);
  const payload = status==='approved' ? {status, your_conviction:conviction} : {status, rejection_reason:'skipped from prop-signals'};
  try{
    const r = await fetch(`/api/signals/${id}/decide`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const j = await r.json();
    if(!r.ok){ toast(j.detail||'decide failed','err'); if(card) card.querySelectorAll('button').forEach(b=>b.disabled=false); return; }
    toast(status==='approved'?`✓ TAKEN · conviction ${conviction}`:'✕ SKIPPED', status==='approved'?'ok':'no');
    setTimeout(load, 600);
  }catch(e){ toast('network error','err'); if(card) card.querySelectorAll('button').forEach(b=>b.disabled=false); }
}

// handoff: write an OPEN prop-book trade linked to this signal. Close it out
// (exit/pnl) later on /prop-ledger.
async function logLedger(s){
  const t = s.ticket||{};
  if(!t.size_btc){ toast('no ticket to size from','err'); return; }
  const body = {
    symbol:'BTC/USD:USD', direction:s.direction, entry:s.entry_price,
    size:Number(t.size_btc.toFixed(6)), leverage:t.leverage,
    tp:s.target_price, sl:s.stop_price, opened_at:new Date().toISOString(),
    followed_strategy:true, linked_signal_id:s.signal_id
  };
  try{
    const r = await fetch('/api/prop/trades',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok){ const j=await r.json().catch(()=>({})); toast(j.detail||'log failed','err'); return; }
    toast('✓ logged to ledger — close it out on /prop-ledger','ok');
    setTimeout(load, 700);
  }catch(e){ toast('network error','err'); }
}

// ── desk-now strip: the SAME state /prop-desk shows, so this page is never
// silent while the desk says STAND DOWN. One fetch, read-only. ──────────────
function fmtClock(min){ if(min==null) return '—'; if(min<60) return min+'m'; const h=Math.floor(min/60); return h+'h '+(min%60)+'m'; }
async function loadDesk(){
  try{
    const d = await fetch('/api/prop/desk').then(r=>r.json());
    if(d.error){ $('desk').innerHTML=''; return; }
    const enter = d.verdict==='enter', col = enter?'var(--long)':'var(--amber)';
    $('desk').innerHTML = `<div class="panel" style="border-left:3px solid ${col};margin-bottom:14px;display:flex;gap:10px;flex-wrap:wrap;align-items:baseline">
      <b style="color:${col};font-family:var(--mono);letter-spacing:.08em">${enter?'● ENTER':'— STAND DOWN'}</b>
      <span style="font-family:var(--mono);font-size:11px;color:var(--ink)">${d.strategy}</span>
      <span style="font-size:11.5px;color:var(--dim);flex:1;min-width:220px">${enter?('fired this bar — the pending card below is the trade'):(d.stand_down_reason||'no trigger this bar')}${(!enter&&d.next_asian_in_min!=null)?(' · next window in <b style="color:var(--ink)">'+fmtClock(d.next_asian_in_min)+'</b>'):''}</span>
      <a href="/prop-desk" class="ac" style="font-size:11px;white-space:nowrap">desk →</a></div>`;
  }catch(e){ $('desk').innerHTML=''; }
}

// ── hedge crossover rows: the hedge book's signals at eval sizing ───────────
function hedgeRow(s){
  const id='h-'+s.signal_id, conv=s.your_conviction!=null?s.your_conviction:'—';
  const detail = `
    <div class="tg" style="margin:2px 0 8px">
      <div class="cell"><div class="k">entry</div><div class="v">${money(s.entry_price)}</div></div>
      <div class="cell"><div class="k">R : R</div><div class="v">${s.expected_rr??'—'}</div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(s.stop_price)}</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(s.target_price)}</div></div>
    </div>
    ${s.ticket?ticketBlock(s.ticket):'<div class="kv"><span class="k">eval ticket</span><span class="v dim">no stop/target on this signal — can\'t size it</span></div>'}
    ${(s.status==='pending'||s.status==='approved')&&s.ticket?`<button class="btn" style="margin-top:8px;background:var(--panel);border:1px solid var(--line)" onclick='logLedger(${JSON.stringify(s)})'>＋ Took it on the eval — log fill to ledger →</button>`:''}`;
  return `<tr class="hrow" onclick="toggleRow('${id}')" style="cursor:pointer">
    <td style="font-size:11px">${s.strategy_name||s.setup_name||'HEDGE'}</td>
    <td class="${s.direction==='long'?'g':'r'}">${VLAB[s.direction]||s.direction||''}</td>
    <td><span class="badge ${s.status}">${s.status}</span></td>
    <td class="m">${conv}</td>
    <td class="m">${ago(s.decided_at||s.received_at)} ▾</td>
  </tr>
  <tr id="d-${id}" style="display:none"><td colspan="5" style="background:var(--panel);padding:10px 12px">${detail}</td></tr>`;
}

function render(all, hedge){
  const sigs = all;  // API already returns only prop-* signals (whole basket, not just the hero)
  const pending = sigs.filter(s=>s.status==='pending').sort((a,b)=>(b.received_at||'').localeCompare(a.received_at||''));
  const decided = sigs.filter(s=>s.status!=='pending').sort((a,b)=>(b.decided_at||b.received_at||'').localeCompare(a.decided_at||a.received_at||'')).slice(0,25);

  let html = '';
  html += `<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ what is this page</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-help"><div class="help-body">`
    + `<h4>prop alerts</h4>The hourly cron reads your prop tradeable basket (the Strategy Board's top prop strategies, or whatever basket you pinned) on the freshest closed 4H bar. The highest-ranked one saying ENTER wins the bar, lands here as <b class="a">pending</b>, and pushes your phone. Each strategy fires on its own session rule.`
    + `<h4>decide</h4><b class="g">TAKE A+</b> (=5) / <b class="g">TAKE</b> (=3) / <b class="r">SKIP</b> — same buttons as the alert. A skip is recorded too.`
    + `<h4>log fill to ledger</h4>After you place the order on Kraken, hit <b>Log fill to ledger</b>. It writes an <i>open</i> prop-book trade (sized from the ticket) carrying <code>linked_signal_id</code> back to this alert. Close it out — add exit + pnl — on <a href="/prop-ledger" class="ac">Ledger</a>.`
    + `<h4>separate from the hedge book</h4>These are <code>book='prop'</code> trades on the eval account, kept apart from your own-money HEDGE trades.`
    + `<h4>desk strip + hedge crossover</h4>The strip on top mirrors <a href="/prop-desk" class="ac">/prop-desk</a> — when the desk says STAND DOWN, this page says why instead of sitting silent. The <b>hedge signals</b> section shows the hedge book's alerts re-sized to the eval ticket. Sizing only — they're not priced into the pass-rate.`
    + `</div></div>`;

  html += secHead('pending', `pending · ${pending.length}`) + `<div class="sec-body" id="s-pending">`;
  html += pending.length ? `<div class="grid-auto">`+pending.map(pendingCard).join('')+`</div>`
        : `<div class="panel dim" style="text-align:center;color:var(--dim)">no pending prop signals — fires on Asian-session 4H closes (00 / 04 UTC)</div>`;
  html += `</div>`;

  html += secHead('hist','recent decisions') + `<div class="sec-body" id="s-hist"><div class="sb-wrap"><table class="sb">`
    + `<tr><th>strat</th><th>dir</th><th>status</th><th>conv</th><th>when</th></tr>`
    + (decided.length?decided.map(historyRow).join(''):'<tr><td colspan="5" class="m">no decisions yet</td></tr>')
    + `</table></div></div>`;

  // hedge crossover — same levels, eval sizing. Sizing ONLY: these strategies
  // are not in the eval backtest, so nothing here moves the pass-rate math.
  html += secHead('xover', `hedge signals · eval-sized × ${hedge.length}`)
    + `<div class="sec-body" id="s-xover">`
    + `<div class="sub" style="font-size:11px;color:var(--dim);margin:0 0 8px">The hedge book's alerts with the <b style="color:var(--ink)">prop ticket</b> applied (fixed risk on the eval account, legal leverage). `
    + `⚠ <b style="color:var(--amber)">Sizing only</b> — these setups have no backtest against the eval walls, so they are unpriced: the pass-rate on <a href="/prop-goal" class="ac">Goal</a> doesn't include them. Decide them on <a href="/hedge-signals" class="ac">/signals</a>; if you take one on the eval, log the fill here.</div>`
    + (hedge.length
        ? `<div class="sb-wrap"><table class="sb"><tr><th>setup</th><th>dir</th><th>status</th><th>conv</th><th>when</th></tr>`+hedge.map(hedgeRow).join('')+`</table></div>`
        : `<div class="panel dim" style="text-align:center;color:var(--dim)">no recent hedge signals</div>`)
    + `</div>`;
  $('body').innerHTML = html;
}

async function load(){
  try{
    const [j, hj] = await Promise.all([
      fetch('/api/prop/signals?limit=300').then(r=>r.json()),
      fetch('/api/prop/signals/hedge?limit=20').then(r=>r.json()).catch(()=>({signals:[]}))
    ]);
    render(j.signals||[], hj.signals||[]);
  }
  catch(e){ $('body').innerHTML='<div class="skeleton" style="color:var(--amber)">failed to load prop signals</div>'; }
  loadDesk();
}
$('refresh').addEventListener('click', e=>{e.preventDefault(); load();});
load();
setInterval(load, 60000);
"""


def render() -> str:
    return shell("/prop-signals", "Prop Signals", BODY, script=SCRIPT, meta="prop review")
