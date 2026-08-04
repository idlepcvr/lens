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

// ── same-zone clustering ─────────────────────────────────────────────────────
// The hourly scanner re-fires the same context: 3× S3 within 0.2% is one trade
// idea, not three. Group consecutive signals (same direction, entry within 0.5%
// of the cluster anchor, ≤6h apart) so the queue reads as ideas, not spam.
// Every member keeps its own identity and its own TAKE/SKIP — nothing is merged
// in the data, only in the display.
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

// ── blocked cards ────────────────────────────────────────────────────────────
// A setup that matched and was vetoed. No buttons: blocked is not actionable,
// it's evidence. The ledger line is the whole point — it's the denominator for
// "would taking the vetoed ones have made money?", which /robustness cannot
// answer because it only ever sees setups that became trades.
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
  // No trade ever hit this exact combination — fall back to each rule's own
  // record so the card still cites something measured, and say which it is.
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
      <!-- VETO_LABELS is description-only now, so no stat to strip. One number
           per card, and it's the live one on the line below. -->
      ${rules.map(r=>`<li>${VETO_LABELS[r]||r}</li>`).join('')}
    </ul>
    <!-- colour is inverted on purpose: a bucket that LOST money means the veto
         saved you (green). A bucket in profit means this veto is costing you
         and deserves a second look (amber) — that's the finding worth seeing. -->
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
    if(!open){ // collapsing: also fold any member detail rows left open
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
    ${s.linked_trade_id?`<div class="kv"><span class="k">trade</span><span class="v"><a href="/hedge-journal?trade=${s.linked_trade_id}" style="color:var(--accent);text-decoration:none" onclick="event.stopPropagation()">#${s.linked_trade_id}${s.pnl_eur!=null?` · ${s.pnl_eur>=0?'+':''}€${s.pnl_eur}`:''} — open in journal →</a></span></div>`:''}`;
  return `<tr class="hrow"${grpAttr} onclick="toggleRow('${id}')" style="cursor:pointer">
    <td>${grp?'&nbsp;&nbsp;↳ ':''}${s.trigger_type||'?'}</td>
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
  const isBlocked = s=>(s.rejection_reason||'').startsWith('veto:');
  const blocked = all.filter(isBlocked)
                     .sort((a,b)=>(b.received_at||'').localeCompare(a.received_at||''))
                     .slice(0,20);
  // blocked rows are decisions too, but they get their own section — mixed into
  // recent decisions they'd read as things you skipped, which you didn't.
  const decided = all.filter(s=>s.status!=='pending' && !isBlocked(s))
                     .sort((a,b)=>(b.decided_at||b.received_at||'').localeCompare(a.decided_at||a.received_at||''))
                     .slice(0,25);

  let html = '';
  // help
  html += `<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ what is this page</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-help"><div class="help-body">`
    + `<h4>the queue</h4>Signals the hourly scanner fired land here as <b class="a">pending</b>. Decide each one: <b class="g">TAKE A+</b> (high conviction, =5), <b class="g">TAKE</b> (=3), or <b class="r">SKIP</b>. Same buttons as the phone alert + the desk.`
    + `<h4>proposed vs decided</h4><b>Proposed</b> = when LENS's hourly scanner spotted the setup (the machine, always automatic). <b>Decided</b> = when a verdict was recorded. Click any row in <b>recent decisions</b> to expand its full ticket + both timestamps.`
    + `<h4>who decides</h4>Two deciders, and the <b>reason</b> field tells you which acted. <b>1) LENS itself</b> — the discipline filters auto-reject a signal the instant it's born if it breaks a rule (proposed = decided, conviction —). <b>2) You</b> — signals that pass the filters sit <b class="a">pending</b> until you TAKE/SKIP. I'm not in the loop. A <code>filter:*</code> reason = the machine skipped it; <code>skipped from…</code> = you did.`
    + `<h4>the filters (auto-skips)</h4>Mined from the PRISM loss fingerprint — each one cost real money historically. A rejected signal is still stored so the dataset stays complete.`
    + `<ul style="margin:6px 0 0 16px;padding:0">`
    + `<li><code>filter:saturday</code> — no trading Saturday (UTC). Sat bled €2,606, PF 0.38. <i>(your weekend rejects)</i></li>`
    + `<li><code>filter:bleed_hour_02utc</code> / <code>_11utc</code> — skip the two hours that bleed across every year (PF 0.26 / 0.38).</li>`
    + `<li><code>filter:bad_venue_&lt;x&gt;</code> — Kraken only. Bybit cost €1,874 in 84 trades (PF 0.40), auto-rejected.</li>`
    + `<li><code>filter:cooldown_&lt;n&gt;min</code> — anti-revenge: &lt;5 min since the last accepted signal on the same symbol. Overtrading cost €1,946.</li>`
    + `</ul>`
    + `<h4>blocked</h4>A setup can match and still be stood down by a <b>veto rule</b> — context the loss fingerprint says is where the money went. Those land in <b>blocked</b>: setup ✓, which rules ✗, and what that veto bucket actually did in your ledger. No alert fires — blocked isn't actionable, it's evidence. Before 2026-07-24 these were discarded silently, which is why the feed looked long-only for 10 days while the engine was correctly refusing shorts. <b>Read the ledger line:</b> a bucket in the red means the veto saved you; a bucket in profit means the rule is costing you and wants a second look.`
    + `<h4>why skips matter</h4>A skip is recorded too — it trains the veto map (where you correctly stood down). Don't ignore them.`
    + `<h4>conviction</h4>The number feeds your conviction win-rate metric. Be honest: A+ only for genuine A+ context, not FOMO.`
    + `<h4>you still place the trade</h4>Approving here logs the decision — it does <b>not</b> place an order. Execute on Kraken yourself.`
    + `</div></div>`;

  // pending — clustered: one bordered group per trade idea, cards inside
  html += secHead('pending', `pending · ${pending.length}`) + `<div class="sec-body" id="s-pending">`;
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

  // blocked — setups that matched and were vetoed. Collapsed by default: this
  // is the audit trail, not the queue. Nothing here is actionable.
  // ponytail: no clustering here, unlike the pending queue — a context that
  // persists for four hours genuinely produced four blocked bars, and that
  // repetition IS the denominator. If the wall of near-identical cards starts
  // hiding the interesting ones, group by setup+veto-combo (clusterize() groups
  // by price zone, which would merge rows whose veto reasons differ).
  html += `<div class="sect closed" id="h-blocked" onclick="tog('blocked')"><span class="caret">▾</span><span class="ttl">⃠ blocked · ${blocked.length}</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-blocked">`;
  if(blocked.length===0){
    html += `<div class="panel dim" style="text-align:center;color:var(--dim)">no blocked setups logged yet — they appear here when a setup matches and a veto rule stands it down</div>`;
  } else {
    html += `<div class="grid-auto">${blocked.map(blockedCard).join('')}</div>`;
  }
  html += `</div>`;

  // history — same-zone decisions collapse behind one summary row
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
    # Veto labels + the realized ledger are baked in at render time: they change
    # only when the book does, and a second endpoint for two small dicts would
    # be a round trip the page doesn't need.
    import json

    from .setups import VETO_LABELS, veto_bucket_stats

    try:
        ledger = veto_bucket_stats()
    except Exception:
        ledger = {"rules": {}, "combos": {}}   # a dead stat never blanks the page
    preamble = (f"const VETO_LABELS={json.dumps(VETO_LABELS)};\n"
                f"const VETO_LEDGER={json.dumps(ledger)};\n")
    return shell("/hedge-signals", "Signals", BODY, script=preamble + SCRIPT,
                 meta="approve / reject")
