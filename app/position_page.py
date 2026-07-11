"""LENS /position — full port of Prism's Position page.

Entry + direction → the whole trade laid out, long AND short side-by-side:
sizing levels, account-impact calculations, Kelly/risk rules, ruin math, the
8h expected range and the risk read. Goal params come from saved config; the
"Override risk inputs" panel (and the Hedge/Prop preset) let you size for either
book without touching the dashboard — that's the hedge↔prop differentiation.

Backend: POSTs the merged payload to BOTH /api/goal (model outputs) and
/api/position (sizing). Long/short columns are derived client-side from the
goal's underlying move %, exactly like Prism did.
"""

import json

from .theme import shell

_CSS = r"""<style>
.pz{max-width:1040px;margin:0 auto;padding:6px 14px 60px}
.pz h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pz .sub{color:var(--dim);font-size:13px;margin-bottom:16px}
.pz form{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:15px 17px;margin-bottom:18px}
.pz .frow{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin-bottom:11px}
.pz .lf{display:flex;flex-direction:column;gap:4px}
.pz .lf label{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.pz .lf input{background:var(--panel2);border:1px solid var(--line2);color:var(--ink);padding:7px 10px;border-radius:6px;font-family:var(--mono);font-size:13px}
.pz .lf input:focus{outline:none;border-color:var(--accent)}
.pz .seg{display:flex;border:1px solid var(--line2);border-radius:6px;overflow:hidden}
.pz .seg button{flex:1;background:var(--panel2);color:var(--dim);border:0;padding:7px 0;font-family:var(--mono);font-size:12px;font-weight:700;text-transform:uppercase;cursor:pointer}
.pz .seg button.on.long{background:rgba(31,217,137,.16);color:var(--long)}
.pz .seg button.on.short{background:rgba(255,84,104,.16);color:var(--short)}
.pz .seg button.on.book{background:var(--accent-d);color:var(--accent)}
.pz .advtog{background:none;border:0;color:var(--dim);font-size:11px;cursor:pointer;padding:4px 0;font-family:var(--mono)}
.pz .adv{border-top:1px dashed var(--line2);margin-top:6px;padding-top:11px}
.pz .adv.hide{display:none}
.pz .hint{font-size:9px;color:var(--faint);font-weight:600}
.pz .err{margin:0 0 14px;padding:10px 14px;border:1px solid var(--short);background:rgba(255,84,104,.08);color:var(--short);border-radius:8px;font-size:12px}
.pz .err.hide{display:none}
.pz .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.pz .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 17px}
.pz .ct{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--dim);padding-bottom:8px;border-bottom:1px solid var(--line);margin-bottom:6px}
.pz .r3{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:6px;padding:5px 0;border-bottom:1px solid var(--line);font-size:12px;align-items:baseline}
.pz .r3:last-child{border-bottom:0}
.pz .rl{color:var(--dim)}
.pz .rv{font-family:var(--mono);font-weight:600;color:var(--ink);text-align:right}
.pz .rv2{font-family:var(--mono);color:var(--dim);text-align:right}
.pz .g{color:var(--long)!important} .pz .r{color:var(--short)!important} .pz .a{color:var(--amber)!important} .pz .ac{color:var(--accent)!important} .pz .dim{color:var(--faint)!important}
.pz .empty{text-align:center;padding:30px;color:var(--dim);border:1px dashed var(--line2);border-radius:11px}
</style>"""


def position_page(book: str = "hedge") -> str:
    sub = ('Entry → full trade: levels, sizing, risk — long &amp; short. Sized off <b>live eval equity</b> '
           'at the plan\'s risk — see <a href="/rules" style="color:var(--accent)">Rules</a>. '
           'Override risk %, R:R or the leverage cap below for a per-trade what-if; the saved plan is untouched.'
           if book == "prop" else
           'Entry → full trade: levels, sizing, risk — long &amp; short. Params from your '
           '<a href="/dashboard" style="color:var(--accent)">config</a>; override per trade or flip the book below.')
    body = r"""
<div class="pz">
  <h1>Position</h1>
  <div class="sub">""" + sub + r"""</div>

  <form id="pf" onsubmit="return false">
    <div class="frow">
      <div class="lf"><label>Entry $</label><input id="p-entry" type="text" inputmode="decimal" placeholder="61900" autofocus></div>
      <div class="lf"><label>Direction</label>
        <div class="seg"><button type="button" id="d-long" class="on long" onclick="setDir('long')">▲ long</button><button type="button" id="d-short" class="short" onclick="setDir('short')">▼ short</button></div>
      </div>
      <div class="lf" id="f-bal"><label id="bal-label">Balance €</label><input id="p-bal" type="text" inputmode="decimal" placeholder="—"></div>
      <div class="lf" id="f-btc"><label>BTC price €</label><input id="p-btc" type="text" inputmode="decimal" placeholder="—"></div>
    </div>
    <div class="frow" style="margin-bottom:0" id="book-preset-row">
      <div class="lf"><label>Book preset</label>
        <div class="seg"><button type="button" id="b-hedge" class="on book" onclick="setBook('hedge')">Hedge</button><button type="button" id="b-prop" class="book" onclick="setBook('prop')">Prop</button></div>
      </div>
    </div>
    <button type="button" class="advtog" id="advtog" onclick="toggleAdv()">▸ override risk inputs</button>
    <div class="adv hide" id="adv">
      <div class="frow" style="margin-bottom:0">
        <div class="lf" id="f-wr"><label>Win rate <span class="hint">0–1</span></label><input id="o-wr" type="text" inputmode="decimal" placeholder="from config"></div>
        <div class="lf"><label>R:R ratio</label><input id="o-rr" type="text" inputmode="decimal" placeholder="from config"></div>
        <div class="lf"><label id="lev-label">Leverage</label><input id="o-lev" type="text" inputmode="decimal" placeholder="from config"></div>
        <div class="lf"><label>Risk/trade <span class="hint" id="risk-hint">0–1 dec</span></label><input id="o-risk" type="text" inputmode="decimal" placeholder="auto (EV)"></div>
        <div class="lf"><label>Daily vol σ <span class="hint">auto from ATR feed</span></label><input id="o-std" type="text" inputmode="decimal" placeholder="0.0356"></div>
      </div>
    </div>
  </form>

  <div id="err" class="err hide"></div>
  <div id="logbar" style="display:none;margin:0 0 14px;display:flex;gap:10px;align-items:center">
    <button type="button" id="logbtn" onclick="logTrade()" style="background:var(--accent);color:var(--bg);border:0;border-radius:7px;padding:9px 18px;font-family:var(--mono);font-size:12px;font-weight:700;cursor:pointer">＋ Log as open trade</button>
    <span id="logmsg" style="font-size:12px;color:var(--dim)"></span>
  </div>
  <div id="out"><div class="empty">Enter an entry price to size the trade.</div></div>
</div>"""

    script = r"""
const $=id=>document.getElementById(id);
let dir='long', book=START_BOOK, CFG=null, deb, EURUSD=null, HEDGE_BAL=null, LAST=null;
const fP=n=>n==null?'—':Number(n).toLocaleString('en',{useGrouping:false,minimumFractionDigits:2,maximumFractionDigits:2}); // ponytail: no $/commas so prices paste straight into Kraken
const fE=n=>n==null?'—':'€'+Number(n).toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
const fB=n=>n==null?'—':Number(n).toFixed(6)+' ₿';
const pc=n=>n==null?'—':Number(n).toFixed(2)+'%';

async function ensureCfg(){ if(!CFG) CFG=await fetch('/api/config').then(r=>r.json()); return CFG; }
function setDir(d){ dir=d; $('d-long').classList.toggle('on',d==='long'); $('d-short').classList.toggle('on',d==='short'); calc(); }
function toggleAdv(){ const a=$('adv'); a.classList.toggle('hide'); $('advtog').textContent=(a.classList.contains('hide')?'▸':'▾')+' override risk inputs'; }
function setBook(b){
  book=b; $('b-hedge').classList.toggle('on',b==='hedge'); $('b-prop').classList.toggle('on',b==='prop');
  const prop = b==='prop';
  // Prop sizes by the firm's rule server-side, but risk %, R:R (rescales TP),
  // leverage cap and the eval balance are per-trade overridable. Win-rate and
  // daily σ only feed the hedge goal model — greyed out in prop mode.
  $('o-wr').disabled=$('o-std').disabled=prop;
  $('o-rr').disabled=$('o-lev').disabled=$('o-risk').disabled=$('p-bal').disabled=false;
  $('bal-label').textContent = prop?'Eval balance $':'Balance €';
  $('lev-label').textContent = prop?'Leverage cap':'Leverage';
  $('risk-hint').textContent = prop?'% · 0.5':'0–1 dec';
  $('pf').style.opacity=1;
  if(!prop){ if(HEDGE_BAL!=null) $('p-bal').value=HEDGE_BAL; }
  else { $('p-bal').value=''; $('p-bal').placeholder='live eval equity'; $('o-lev').value=''; $('o-risk').value=''; }
  calc();
}

async function calc(){
  const entry=parseFloat($('p-entry').value);
  if(!entry){ $('out').innerHTML='<div class="empty">Enter an entry price to size the trade.</div>'; $('err').classList.add('hide'); return; }
  if(book==='prop'){ return calcProp(entry); }
  const cfg=await ensureCfg();
  const bal=parseFloat($('p-bal').value)||cfg.start_balance;
  const btc=parseFloat($('p-btc').value)||cfg.btc_price_eur;
  const ov=(id,lo,hi)=>{ const v=parseFloat($(id).value); return (isFinite(v)&&(lo==null||v>lo)&&(hi==null||v<hi))?v:undefined; };
  const payload={
    start_balance:cfg.start_balance, target_balance:cfg.target_balance, target_date:cfg.target_date,
    trades_per_week:cfg.trades_per_week, win_rate:cfg.win_rate, rr_ratio:cfg.rr_ratio, leverage:cfg.leverage,
    max_drawdown_allowed:cfg.max_drawdown_allowed, losses_allowed:cfg.losses_allowed,
    fractional_kelly:cfg.fractional_kelly, execution_fill_factor:cfg.execution_fill_factor, slippage_pct:cfg.slippage_pct,
    entry_price:entry, direction:dir, balance_eur:bal, btc_price_eur:btc, btc_std_dev:ov('o-std',0)||0.0356,
  };
  const wr=ov('o-wr',0,1), rr=ov('o-rr',0), lev=ov('o-lev',0.99), rk=ov('o-risk',0,1);
  if(wr!=null)payload.win_rate=wr; if(rr!=null)payload.rr_ratio=rr; if(lev!=null)payload.leverage=lev; if(rk!=null)payload.risk_per_trade=rk;
  Object.keys(payload).forEach(k=>payload[k]==null&&delete payload[k]);
  const opt={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
  try{
    const [gr,pr]=await Promise.all([fetch('/api/goal',opt),fetch('/api/position',opt)]);
    if(!gr.ok){ throw new Error((await gr.json()).detail||'goal error'); }
    if(!pr.ok){ throw new Error((await pr.json()).detail||'position error'); }
    $('err').classList.add('hide'); render(await gr.json(), await pr.json(), payload, bal, btc);
  }catch(e){ $('err').textContent=String(e.message||e); $('err').classList.remove('hide'); }
}

function sec(title, rows){
  return `<div class="card"><div class="ct">${title}</div>`+rows.map(r=>
    `<div class="r3"><span class="rl">${r[0]}</span><span class="rv ${r[3]||''}">${r[1]}</span><span class="rv2 ${r[4]||''}">${r[2]!=null?r[2]:''}</span></div>`).join('')+`</div>`;
}

function render(g, p, pl, bal, btcE){
  const e=p.entry, uw=g.underlying_win_pct/100, ul=g.underlying_loss_pct/100, lev=g.leverage;
  const tpL=e*(1+uw), slL=e*(1-ul), tpS=e*(1-uw), slS=e*(1+ul);
  const liqL=e*(1-0.5/lev), liqS=e*(1+0.5/lev);
  const beL=e*(1+p.hurdle_cost_pct/100), beS=e*(1-p.hurdle_cost_pct/100);
  const gainE=bal*g.acct_gain_win/100, lossE=p.risk_eur;
  const out =
    sec('Position sizing', [
      ['', 'Long', 'Short', 'dim', 'dim'],
      ['Take profit', fP(tpL), fP(tpS), 'g', 'g'],
      ['Stop loss',   fP(slL), fP(slS), 'r', 'r'],
      ['Entry',       fP(e),   fP(e),   'ac'],
      ['Breakeven',   fP(beL), fP(beS)],
      ['Liquidation', fP(liqL),fP(liqS),'a','a'],
      ['Cost ₿ / $',  p.cost_btc.toFixed(6)+' ₿', fP(p.cost_usd)],
      ['Hurdle (fees)', pc(p.hurdle_cost_pct), 'fee drag', 'dim','dim'],
    ])
  + sec('Calculations', [
      ['Win / loss rate', pc(pl.win_rate*100), pc((1-pl.win_rate)*100), 'g','r'],
      ['Acct gain (win)', '+'+pc(g.acct_gain_win), 'mkt +'+pc(g.underlying_win_pct), 'g','g'],
      ['Acct loss (loss)','−'+pc(g.acct_loss_loss), 'mkt −'+pc(g.underlying_loss_pct), 'r','r'],
      ['€ if win',  '+'+fE(gainE), fE(bal+gainE), 'g'],
      ['€ if loss', '−'+fE(lossE), fE(bal-lossE), 'r'],
    ])
  + sec('Rules', [
      ['Optimal bet (Kelly)', fE(bal*g.optimal_risk_pct/100), pc(g.optimal_risk_pct)],
      ['Actual risk (EV)',    fE(lossE), pc(g.risk_per_trade), 'r'],
      ['Leverage', lev.toFixed(2)+'×', ''],
      ['Trading size', fE(p.position_size_eur), p.position_size_btc.toFixed(4)+' ₿'],
      ['R multiple', pl.rr_ratio.toFixed(1)+'× nom', g.actual_rr.toFixed(2)+'× net', 'dim','dim'],
    ])
  + sec('Risk budget', [
      ['Max DD allowed', pc(g.max_drawdown_allowed), fE(bal*g.max_drawdown_allowed/100)],
      ['Losses allowed', g.losses_allowed+' losses', ''],
      ['DD risk / trade', pc(g.dd_risk_constraint), pc(g.risk_per_trade)],
      ['Losses to ruin', g.losses_to_ruin+' losses', '', 'r'],
      ['Wins to breakeven', g.wins_to_breakeven+' wins', ''],
    ])
  + sec('Trade size & range', [
      ['Current trade size', p.current_trade_size_btc.toFixed(4)+' ₿', lev.toFixed(2)+'×'],
      ['Current size €', fE(p.current_trade_size_eur), ''],
      ['Expected 8h range', fP(p.expected_8hr_high), fP(p.expected_8hr_low), 'g','r'],
      ['1σ move', fP(p.std_8hr_usd), '', 'dim'],
    ])
  + sec('Risk read', [
      ['Typical win', '+'+pc(g.typical_win), (g.typical_win>=7?'GOOD':g.typical_win>=3?'OK':'WEAK'), 'g', (g.typical_win>=7?'g':g.typical_win>=3?'a':'r')],
      ['Typical loss', pc(g.typical_loss), '', 'r'],
      ['Avg growth/trade μ', (g.avg_growth_per_trade>=0?'+':'')+g.avg_growth_per_trade.toFixed(4)+'%', '', g.avg_growth_per_trade>=0?'g':'r'],
      ['Trade volatility σ', g.trade_volatility.toFixed(4)+'%', ''],
    ]);
  $('out').innerHTML='<div class="grid">'+out+'</div>';
  LAST={book:'hedge',direction:dir,entry:e,size:p.current_trade_size_btc,leverage:lev};
  $('logbar').style.display='flex'; $('logmsg').textContent='';
}

async function calcProp(entry){
  const q=new URLSearchParams({entry:entry, direction:dir});
  const ov=(id)=>{ const v=parseFloat($(id).value); return (isFinite(v)&&v>0)?v:null; };
  const bal=ov('p-bal'), rk=ov('o-risk'), rr=ov('o-rr'), lv=ov('o-lev');
  if(bal)q.set('balance',bal); if(rk)q.set('risk',rk); if(rr)q.set('rr',rr); if(lv)q.set('lev',lv);
  try{
    const r=await fetch('/api/prop/position?'+q);
    if(!r.ok){ throw new Error((await r.json()).detail||'prop error'); }
    const t=await r.json();
    if(!bal) $('p-bal').placeholder=t.account;   // live eval equity, visible before you override
    $('err').classList.add('hide'); renderProp(t);
  }catch(e){ $('err').textContent=String(e.message||e); $('err').classList.remove('hide'); }
}

function renderProp(t){
  const e=t.entry, sp=t.stop_pct/100, tpp=t.tp_pct/100, lev=t.leverage;
  const tpL=e*(1+tpp), slL=e*(1-sp), tpS=e*(1-tpp), slS=e*(1+sp);
  const liqL=lev>1?e*(1-1/lev):null, liqS=lev>1?e*(1+1/lev):null;
  const beL=e*(1+t.fee_rt_pct/100), beS=e*(1-t.fee_rt_pct/100);
  const btcE=parseFloat($('p-btc').value)||1, marginE=EURUSD?t.margin_usd/EURUSD:t.margin_usd;
  const out =
    sec('Position sizing · PROP', [
      ['', 'Long', 'Short', 'dim', 'dim'],
      ['Take profit', fP(tpL), fP(tpS), 'g','g'],
      ['Stop loss',   fP(slL), fP(slS), 'r','r'],
      ['Entry',       fP(e),   fP(e),   'ac'],
      ['Breakeven',   fP(beL), fP(beS)],
      ['Liquidation', liqL?fP(liqL):'none', liqS?fP(liqS):'none', 'a','a'],
      ['Stop / TP move', pc(t.stop_pct), pc(t.tp_pct), 'r','g'],
    ])
  + sec('Prop rule sizing', [
      ['Eval equity', fP(t.account), 'nominal '+fP(t.account_nominal), 'ac', 'dim'],
      ['Risk / trade', pc(t.risk_pct), fP(t.risk_usd), 'r','r'],
      ['Notional', fP(t.notional), t.size_btc.toFixed(4)+' ₿'],
      ['Margin', fP(t.margin_usd), fE(marginE)],
      ['Leverage', lev.toFixed(2)+'×', 'cap '+t.max_leverage+'×', lev>t.max_leverage?'r':''],
      ['R:R (net)', t.rr.toFixed(2)+'×', ''],
    ])
  + sec('Outcome', [
      ['Win',  '+'+fP(t.win_usd),  fP(t.account+t.win_usd),  'g','g'],
      ['Loss', '−'+fP(t.loss_usd), fP(t.account-t.loss_usd), 'r','r'],
      ['Win rate (hist)', pc(t.win_rate_pct), ''],
      ['Strategy', t.strategy, t.eval, 'dim','dim'],
    ]);
  $('out').innerHTML='<div class="grid">'+out+'</div>';
  LAST={book:'prop',direction:dir,entry:e,size:t.size_btc,leverage:lev};
  $('logbar').style.display='flex'; $('logmsg').textContent='';
}

async function logTrade(){
  if(!LAST||!LAST.entry){ return; }
  $('logbtn').disabled=true; $('logmsg').textContent='logging…';
  try{
    const r=await fetch('/api/trades',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:'BTC/USD',direction:LAST.direction,entry:LAST.entry,
        size:Number(LAST.size.toFixed(6)),leverage:LAST.leverage,book:LAST.book})});
    if(!r.ok){ throw new Error((await r.json()).detail||'log failed'); }
    const t=await r.json();
    $('logmsg').innerHTML='✓ logged open '+LAST.direction+' #'+t.id+' · <a href="/journal?trade='+t.id+'" style="color:var(--accent)">journal</a>';
  }catch(e){ $('logmsg').textContent='✗ '+(e.message||e); }
  $('logbtn').disabled=false;
}

// calculator — type 60000*1.02 → Enter/blur → evaluates, then re-sizes
['p-entry','p-bal','p-btc','o-wr','o-rr','o-lev','o-risk','o-std'].forEach(id=>{
  const inp=$(id);
  function tryCalc(){ const v=inp.value.trim(); if(!v||!/[+*\/]/.test(v))return;
    try{ const r=Function('"use strict";return('+v.replace(/[^0-9+\-*/.() \t]/g,'')+')')();
      if(isFinite(r)){ inp.value=parseFloat(r.toFixed(8)); calc(); } }catch(e){} }
  inp.addEventListener('input', ()=>{ clearTimeout(deb); deb=setTimeout(calc, 250); });
  inp.addEventListener('blur', tryCalc);
  inp.addEventListener('keydown', e=>{ if(e.key==='Enter'){ tryCalc(); e.preventDefault(); } });
});

// arrive via /prop-position → the Prop tab is already selected
if(START_BOOK==='prop') setBook('prop');

(async ()=>{ const c=await ensureCfg();
  HEDGE_BAL = c.start_balance!=null ? c.start_balance : null;
  if(c.start_balance!=null) $('p-bal').placeholder=c.start_balance;
  if(c.btc_price_eur!=null) $('p-btc').placeholder=c.btc_price_eur;
  // live balance + BTC price + auto daily σ (best-effort)
  try{ const a=await fetch('/api/account/live').then(r=>r.json());
    if(a.eur_usd) EURUSD=a.eur_usd;
    if(a.total_eur){ HEDGE_BAL=a.total_eur.toFixed(2); if(book==='hedge') $('p-bal').value=HEDGE_BAL; }
    const v=await fetch('/api/volatility').then(r=>r.json());
    if(v.btc_usd){ $('p-entry').placeholder=v.btc_usd.toFixed(0); if(!$('p-entry').value){ $('p-entry').value=v.btc_usd.toFixed(0); calc(); } }
    if(v.btc_usd && a.eur_usd) $('p-btc').value=(v.btc_usd/a.eur_usd).toFixed(2);
    if(v.daily_sigma){ $('o-std').placeholder=v.daily_sigma; if(!$('o-std').value) $('o-std').value=v.daily_sigma; }
  }catch(e){}
})();
"""
    from .prop_views import prop_config
    from .prop_eval import EVALS
    cfg = prop_config()
    prop_def = {"account": cfg["account"], "risk": round(cfg["risk"] / 100, 4),
                "leverage": EVALS[cfg["eval_name"]]["max_leverage"]}
    script = f"const PROP={json.dumps(prop_def)};\nconst START_BOOK=\"{book}\";\n" + script
    # /prop-position keeps the PROP nav + preselects the Prop tab (see theme.NAV_PROP).
    # On the prop page there's no hedge sizing — lock the book and hide the
    # hedge-only inputs (BTC € price, win-rate override). Balance (eval $) and the
    # risk/R:R/leverage-cap overrides stay: per-trade what-ifs against the plan.
    path = "/prop-position" if book == "prop" else "/position"
    head = _CSS + ("<style>#book-preset-row,#f-btc,#f-wr{display:none!important}</style>"
                   if book == "prop" else "")
    return shell(path, "Position", body, script=script, head_extra=head, meta="size the trade")
