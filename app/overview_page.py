"""/overview — the one snapshot page, both books. See overview.py for the data."""

import json

from .overview import overview_data
from .theme import shell

_CSS = r"""<style>
.ov{max-width:1000px;margin:0 auto;padding:6px 14px 60px}
.ov h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.ov .sub{color:var(--dim);font-size:13px;margin-bottom:16px}
.ov .toggle{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden;margin-bottom:18px}
.ov .toggle button{background:var(--panel);color:var(--dim);border:0;padding:8px 22px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;cursor:pointer}
.ov .toggle button.on{background:var(--accent-d);color:var(--accent)}
.ov h2{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin:22px 0 9px;font-family:var(--mono)}
.ov h2 .hint{text-transform:none;letter-spacing:0;color:var(--dim);font-weight:400;font-size:11px;margin-left:8px}
.ov .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px}
.ov .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;position:relative;overflow:hidden}
.ov .card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--line2)}
.ov .card.g::after{background:var(--long)} .ov .card.r::after{background:var(--short)} .ov .card.a::after{background:var(--amber)} .ov .card.b::after{background:var(--accent)}
.ov .card .lbl{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.ov .card .val{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1.05;color:var(--ink)}
.ov .card .note{font-size:10.5px;color:var(--dim);margin-top:4px}
.ov .green{color:var(--long)} .ov .red{color:var(--short)} .ov .amber{color:var(--amber)}
.ov .empty{color:var(--dim);font-size:12px;padding:14px;border:1px dashed var(--line2);border-radius:9px}
</style>"""


def render() -> str:
    data = overview_data()
    body = r"""
<div class="ov">
  <h1>Overview</h1>
  <div class="sub">One snapshot — live account, performance, market. Read-only; LENS never trades it.</div>
  <div class="toggle">
    <button id="t-hedge" class="on" onclick="setBook('hedge')">Hedge</button>
    <button id="t-prop" onclick="setBook('prop')">Prop</button>
  </div>

  <h2>Live account<span class="hint" id="live-hint">live from Kraken</span></h2>
  <div class="grid" id="live"></div>

  <h2>Performance<span class="hint" id="perf-hint"></span></h2>
  <div class="grid" id="perf"></div>

  <h2>Market<span class="hint">BTC · ATR = ~24h min viable stop</span></h2>
  <div class="grid" id="market"></div>
</div>"""

    script = r"""
const DATA = __DATA__;
const $=id=>document.getElementById(id);
let book='hedge', liveCache=null;
const money=(n,d=0)=>n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:d});
const signed=(n,d=0)=>n==null?'—':(n>=0?'+':'−')+money(Math.abs(n),d);
const card=(lbl,val,note,cls)=>`<div class="card ${cls||''}"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="note">${note||''}</div></div>`;

function renderMarket(){
  const m=DATA.market||{};
  $('market').innerHTML =
      card('BTC', m.btc_price!=null?'$'+money(m.btc_price):'—', 'spot', 'b')
    + card('ATR 14d', m.atr_pct!=null?m.atr_pct+'%':'—', 'daily range', 'b')
    + card('Noise floor', m.noise_floor!=null?m.noise_floor+'%':'—', 'min viable stop ~24h', 'a')
    + card("Today's range", m.range_pct!=null?m.range_pct+'%':'—', m.regime||'', m.regime==='wide'?'r':'b');
}

function renderPerf(){
  const p=(DATA[book].performance)||{};
  $('perf-hint').textContent = p.n? (p.n+' closed · '+book) : 'no '+book+' trades yet';
  if(!p.n){ $('perf').innerHTML='<div class="empty">No closed '+book+' trades yet.</div>'; return; }
  $('perf').innerHTML =
      card('Total P&L', signed(p.total_pnl)+'€', p.n+' closed trades', p.total_pnl>=0?'g':'r')
    + card('Win rate', p.wr+'%', (p.wins||Math.round(p.wr*p.n/100))+'W / '+(p.n-Math.round(p.wr*p.n/100))+'L', 'b')
    + card('R:R ratio', p.rr!=null?p.rr:'—', 'avg win / avg loss', 'b')
    + card('Expectancy', signed(p.expectancy,2)+'€', 'per trade', p.expectancy>=0?'g':'r')
    + card('Max drawdown', p.max_dd_pct!=null?('−'+p.max_dd_pct+'%'):('−€'+money(p.max_dd_eur)), 'from peak', 'r')
    + card('Sharpe', p.sharpe!=null?p.sharpe:'—', 'annualised', 'b')
    + card('Total fees', '−€'+money(Math.abs(p.total_fees||0)), 'trading costs', 'a')
    + card('Avg duration', p.avg_dur_h!=null?p.avg_dur_h+'h':'—', 'per trade', 'b');
}

function renderLive(){
  if(book==='prop'){
    $('live-hint').textContent='manual eval ledger vs walls';
    const l=DATA.prop.live;
    $('live').innerHTML =
        card('Equity', '$'+money(l.equity), 'start $'+money(l.account)+' · DD −'+l.cur_dd_pct+'%', l.equity>=l.account?'g':'r')
      + card('To target', '$'+money(l.to_target), 'target $'+money(l.target), 'b')
      + card('To floor', '$'+money(l.to_floor), 'floor $'+money(l.floor), 'r')
      + card("Today's P&L", signed(l.today_pnl)+'$', 'realised today', l.today_pnl>=0?'g':'r');
    return;
  }
  $('live-hint').textContent='live from Kraken';
  if(liveCache){ paintHedgeLive(liveCache); return; }
  $('live').innerHTML = card('Equity','…','loading','b');
  fetch('/api/account/live').then(r=>r.json()).then(a=>{ liveCache=a; if(book==='hedge') paintHedgeLive(a); })
    .catch(()=>{ $('live').innerHTML=card('Equity','err','live fetch failed','r'); });
}
function paintHedgeLive(a){
  const u=a.unrealized_pnl||0;
  $('live').innerHTML =
      card('Equity', '€'+money(a.total_eur), 'futures wallet', a.total_eur>=0?'g':'b')
    + card('Available margin', a.available_margin!=null?'€'+money(a.available_margin):'—', 'free to deploy', 'b')
    + card('Unrealised P&L', signed(u)+'€', a.kraken_personal&&a.kraken_personal.error?'(partial)':'open positions', u>0?'g':(u<0?'r':''))
    + card('EUR/USD', a.eur_usd!=null?a.eur_usd:'—', 'fx', 'b')
    + card('Business acct', a.biz_eur!=null?'€'+money(a.biz_eur):'—', 'biz funds · not traded', 'b');
}

function setBook(b){
  book=b;
  $('t-hedge').classList.toggle('on', b==='hedge');
  $('t-prop').classList.toggle('on', b==='prop');
  renderLive(); renderPerf();
}
renderMarket(); setBook('hedge');
"""
    script = script.replace("__DATA__", json.dumps(data))
    return shell("/overview", "Overview", body, script=script, head_extra=_CSS, meta="snapshot")
