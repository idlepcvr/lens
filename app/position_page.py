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
           'at the plan\'s risk — see <a href="/prop-survival#rules" style="color:var(--accent)">Rules</a>. '
           'Risk sets the <b>size</b>; leverage only sets the <b>margin</b> and the liq price — '
           'move it freely, the stop, target and € at risk don\'t budge. '
           'Override risk %, R:R or leverage below for a per-trade what-if; the saved plan is untouched.'
           if book == "prop" else
           'Entry → full trade: levels, sizing, risk — long &amp; short. Params from your '
           '<a href="/hedge-plan" style="color:var(--accent)">config</a>; override per trade or flip the book below.')
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
      <div class="frow" style="margin-bottom:0;margin-top:11px;display:none" id="f-stop">
        <div class="lf"><label>Stop % <span class="hint">travel-distance dial</span></label><input id="o-stop" type="text" inputmode="decimal" placeholder="strategy's stop"></div>
        <div class="lf" style="justify-content:flex-end"><span class="hint" style="text-transform:none;letter-spacing:0;line-height:1.5">Tighten the stop → bigger size at the same € risk → less travel to TP. Adds a second, side-by-side ticket below; the strategy's stays put.</span></div>
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
let dir='long', book=START_BOOK, CFG=null, deb, HEDGE_BAL=null, LAST=null;
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
  $('o-stop').disabled=!prop;                      // stop override is prop-only sizing
  $('f-stop').style.display=prop?'grid':'none';
  $('o-rr').disabled=$('o-lev').disabled=$('o-risk').disabled=$('p-bal').disabled=false;
  $('bal-label').textContent = prop?'Eval balance $':'Balance €';
  $('lev-label').innerHTML = prop?'Leverage <span class="hint">margin only</span>':'Leverage';
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
  // Carry the PLAN, not just the ticket. Logging used to send entry/size/
  // leverage only, so trades.tp and trades.sl were NULL on every row ever
  // written — which meant a review could never ask "did it reach the target you
  // set", only "did it make money". The levels are already computed right here
  // for display; they just were not being kept.
  LAST={book:'hedge',direction:dir,entry:e,size:p.current_trade_size_btc,leverage:lev,
        tp:(dir==='long'?tpL:tpS), sl:(dir==='long'?slL:slS)};
  $('logbar').style.display='flex'; $('logmsg').textContent='';
}

async function ticket(q){
  const r=await fetch('/api/prop/position?'+q);
  if(!r.ok){ throw new Error((await r.json()).detail||'prop error'); }
  return r.json();
}

async function calcProp(entry){
  const q=new URLSearchParams({entry:entry, direction:dir});
  const ov=(id)=>{ const v=parseFloat($(id).value); return (isFinite(v)&&v>0)?v:null; };
  const bal=ov('p-bal'), rk=ov('o-risk'), rr=ov('o-rr'), lv=ov('o-lev'), st=ov('o-stop');
  if(bal)q.set('balance',bal); if(rk)q.set('risk',rk); if(rr)q.set('rr',rr); if(lv)q.set('lev',lv);
  try{
    // the strategy's ticket always renders; a stop override adds a second one beside it
    const base=await ticket(q);
    let alt=null;
    if(st){ const q2=new URLSearchParams(q); q2.set('stop',st); alt=await ticket(q2); }
    if(!bal) $('p-bal').placeholder=base.account;   // live eval equity, visible before you override
    $('err').classList.add('hide'); renderProp(base, alt);
  }catch(e){ $('err').textContent=String(e.message||e); $('err').classList.remove('hide'); }
}

const MM=0.005;   // maintenance margin — mirrors prop_scan.MM_RATE

// the four prices a ticket actually trades at, long and short
function levels(t){
  const e=t.entry, sp=t.stop_pct/100, tpp=t.tp_pct/100, lev=t.leverage;
  return {e, tpL:e*(1+tpp), slL:e*(1-sp), tpS:e*(1-tpp), slS:e*(1+sp),
          liqL:e*(1-1/lev+MM), liqS:e*(1+1/lev-MM),
          beL:e*(1+t.fee_rt_pct/100), beS:e*(1-t.fee_rt_pct/100)};
}

// The stop override, side by side with the strategy's own numbers. The point of
// the section: risk is identical in both columns — the stop is what buys the
// shorter travel to TP, and it's paid for in leverage and (unshown) win rate.
function overrideSec(t, o){
  const L=levels(o), cut=o.actual_risk_pct < o.risk_pct - 0.001;   // firm's cap ate the size
  const per=x=>fP(x.notional/100);                                  // $ per 1% move
  return sec('Stop override · levels', [
      ['', 'Long', 'Short', 'dim', 'dim'],
      ['Take profit', fP(L.tpL), fP(L.tpS), 'g','g'],
      ['Stop loss',   fP(L.slL), fP(L.slS), 'r','r'],
      ['Entry',       fP(L.e),   fP(L.e),   'ac'],
      ['Liquidation', L.liqL>0?fP(L.liqL):'none', fP(L.liqS), 'a','a'],
      ['Travel to TP', pc(o.tp_pct), 'was '+pc(t.tp_pct), 'g','dim'],
    ])
  + sec('Stop override · vs strategy', [
      ['', 'Strategy', 'Override', 'dim', 'dim'],
      ['Stop',        pc(t.stop_pct), pc(o.stop_pct), 'dim','r'],
      ['Travel to TP',pc(t.tp_pct),   pc(o.tp_pct),   'dim','g'],
      ['Notional',    fP(t.notional), fP(o.notional), 'dim','ac'],
      ['$ / 1% move', per(t),         per(o),         'dim','ac'],
      ['Leverage needed', t.min_leverage+'×', o.min_leverage+'×', 'dim', cut?'r':'a'],
      ['Margin',      pc(t.margin_pct), pc(o.margin_pct), 'dim',''],
      ['Risk / trade',pc(t.actual_risk_pct), pc(o.actual_risk_pct), 'dim', cut?'r':'g'],
      ['Win $',       fP(t.win_usd),  fP(o.win_usd),  'dim','g'],
      [cut ? '⚠ Over the '+o.max_leverage+'× cap' : 'Risk held · same €',
       cut ? 'size cut' : 'yes',
       cut ? 'floor: '+pc(o.risk_pct/o.max_leverage)+' stop' : 'shorter travel, tighter stop',
       cut?'r':'g', 'dim'],
    ]);
}

function renderProp(t, o){
  const L=levels(t), lev=t.leverage;
  const e=L.e, tpL=L.tpL, slL=L.slL, tpS=L.tpS, slS=L.slS, liqL=L.liqL, liqS=L.liqS, beL=L.beL, beS=L.beS;
  const out =
    sec('Position sizing · PROP', [
      ['', 'Long', 'Short', 'dim', 'dim'],
      ['Take profit', fP(tpL), fP(tpS), 'g','g'],
      ['Stop loss',   fP(slL), fP(slS), 'r','r'],
      ['Entry',       fP(e),   fP(e),   'ac'],
      ['Breakeven',   fP(beL), fP(beS)],
      ['Liquidation', liqL>0?fP(liqL):'none', fP(liqS), 'a','a'],
      ['Stop / TP move', pc(t.stop_pct), pc(t.tp_pct), 'r','g'],
    ])
  + sec('Prop rule sizing', [
      ['Eval equity', fP(t.account), 'nominal '+fP(t.account_nominal), 'ac', 'dim'],
      ['Risk / trade', pc(t.actual_risk_pct), fP(t.risk_usd), 'r','r'],
      ['Notional', fP(t.notional), t.size_btc.toFixed(4)+' ₿'],
      ['Margin', fP(t.margin_usd), pc(t.margin_pct)+' of acct'],
      ['Leverage', lev.toFixed(2)+'×', 'min '+t.min_leverage+'× · cap '+t.max_leverage+'×', 'ac', 'dim'],
      ['R:R (net)', t.rr.toFixed(2)+'×', ''],
    ])
  + sec('Outcome', [
      ['Win',  '+'+fP(t.win_usd),  fP(t.account+t.win_usd),  'g','g'],
      ['Loss', '−'+fP(t.loss_usd), fP(t.account-t.loss_usd), 'r','r'],
      ['Win rate (hist)', pc(t.win_rate_pct), ''],
      ['Strategy', t.strategy, t.eval, 'dim','dim'],
    ])
  + (o ? overrideSec(t, o) : '');
  $('out').innerHTML='<div class="grid">'+out+'</div>';
  // log the ticket you'd actually place — the override when there is one
  const k = o || t;
  // levels() already resolves the override's own stop/target, so `k` carries the
  // plan actually being placed rather than the strategy default it replaced
  const kl = levels(k);
  LAST={book:'prop',direction:dir,entry:k.entry,size:k.size_btc,leverage:k.leverage,
        tp:(dir==='long'?kl.tpL:kl.tpS), sl:(dir==='long'?kl.slL:kl.slS)};
  $('logbar').style.display='flex';
  $('logmsg').textContent = o ? 'logs the OVERRIDE ticket ('+pc(o.stop_pct)+' stop)' : '';
}

async function logTrade(){
  if(!LAST||!LAST.entry){ return; }
  $('logbtn').disabled=true; $('logmsg').textContent='logging…';
  try{
    const r=await fetch('/api/trades',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:'BTC/USD',direction:LAST.direction,entry:LAST.entry,
        size:Number(LAST.size.toFixed(6)),leverage:LAST.leverage,book:LAST.book,
        // the plan as it stood at entry, overrides included — this is what the
        // review later compares reality against
        tp:LAST.tp!=null?Number(LAST.tp.toFixed(2)):null,
        sl:LAST.sl!=null?Number(LAST.sl.toFixed(2)):null})});
    if(!r.ok){ throw new Error((await r.json()).detail||'log failed'); }
    const t=await r.json();
    $('logmsg').innerHTML='✓ logged open '+LAST.direction+' #'+t.id+' · <a href="/hedge-journal?trade='+t.id+'" style="color:var(--accent)">journal</a>';
  }catch(e){ $('logmsg').textContent='✗ '+(e.message||e); }
  $('logbtn').disabled=false;
}

// calculator — type 60000*1.02 → Enter/blur → evaluates, then re-sizes
['p-entry','p-bal','p-btc','o-wr','o-rr','o-lev','o-risk','o-std','o-stop'].forEach(id=>{
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
    path = "/prop-position" if book == "prop" else "/hedge-position"
    head = _CSS + ("<style>#book-preset-row,#f-btc,#f-wr{display:none!important}</style>"
                   if book == "prop" else "")
    return shell(path, "Position", body, script=script, head_extra=head, meta="size the trade")
