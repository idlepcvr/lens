"""/overview (prop) and /overview-hedge — one read-only snapshot per book.

A hero band carries the one number that matters (eval equity vs floor/target
walls for prop; live wallet equity + unrealised for hedge), then Performance
and Market sit below as supporting context. See overview.py for the data."""

import json

from .overview import overview_data
from .theme import shell

_CSS = r"""<style>
.ov{max-width:1040px;margin:0 auto;padding:6px 14px 40px}
.ov h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.ov .sub{color:var(--dim);font-size:13px;margin-bottom:20px;max-width:70ch}

/* ── hero band — the focal instrument ── */
.ov .hero{display:grid;grid-template-columns:minmax(190px,250px) 1fr;gap:30px;align-items:center;
  background:linear-gradient(155deg,var(--panel2),var(--panel));border:1px solid var(--line2);
  border-radius:16px;padding:24px 26px;margin:4px 0 28px}
.ov .hero.hedge{grid-template-columns:minmax(190px,290px) 1fr}
.ov .hmain .hlbl{font-family:var(--mono);font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin-bottom:9px}
.ov .hmain .heq{font-family:var(--mono);font-size:46px;font-weight:800;line-height:.95;letter-spacing:-.02em;color:var(--ink)}
.ov .hmain .hsub{font-family:var(--mono);font-size:11.5px;color:var(--dim);margin-top:12px;line-height:1.55}
.ov .hmain .hsub b{font-weight:700}
.ov .hsub b.g{color:var(--long)} .ov .hsub b.r{color:var(--short)} .ov .hsub b.dim{color:var(--ink)}

/* meter: floor ◄ equity ► target */
.ov .mtrack{position:relative;height:12px;border-radius:7px;background:var(--bg);border:1px solid var(--line)}
.ov .mfill{position:absolute;top:0;bottom:0;left:0;border-radius:7px 0 0 7px;transition:width .7s cubic-bezier(.22,1,.36,1)}
.ov .mfill.g{background:linear-gradient(90deg,var(--long-d),var(--long))}
.ov .mfill.r{background:linear-gradient(90deg,var(--short-d),var(--short))}
.ov .mstart{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--dim);opacity:.65}
.ov .mnow{position:absolute;top:50%;width:4px;height:22px;border-radius:2px;transform:translate(-50%,-50%);box-shadow:0 0 0 2px var(--bg),0 0 12px -2px currentColor}
.ov .mnow.g{background:var(--long);color:var(--long)} .ov .mnow.r{background:var(--short);color:var(--short)}
.ov .mends{display:flex;justify-content:space-between;margin-top:13px;font-family:var(--mono);font-size:11px;line-height:1.5}
.ov .mends .target{text-align:right}
.ov .mends .cap{color:var(--dim)} .ov .mends .floor .cap{color:var(--short)} .ov .mends .target .cap{color:var(--long)}
.ov .mends .d{display:block;color:var(--faint);font-size:10px;margin-top:1px}

/* hedge hero: equity + three live stats instead of a meter */
.ov .hstats{display:grid;grid-template-columns:repeat(3,1fr);gap:11px}
.ov .hstat{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:11px 13px}
.ov .hstat .k{font-size:8.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:6px;font-family:var(--mono)}
.ov .hstat .v{font-family:var(--mono);font-size:17px;font-weight:700;color:var(--ink)}
.ov .hstat .n{font-size:10px;color:var(--dim);margin-top:3px}

.ov .hskel{padding:40px;text-align:center;color:var(--dim);font-family:var(--mono);font-size:12px;letter-spacing:.04em;
  background:var(--panel);border:1px dashed var(--line2);border-radius:16px;margin:4px 0 28px}
.ov .hskel.err{color:var(--amber);border-color:rgba(246,173,60,.4)}

/* ── supporting sections ── */
.ov .support{display:grid;grid-template-columns:1fr;gap:6px 30px}
.ov h2{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin:14px 0 11px;font-family:var(--mono)}
.ov h2 .hint{text-transform:none;letter-spacing:0;color:var(--dim);font-weight:400;font-size:11px;margin-left:8px}
.ov h2 .h2go{float:right;text-transform:none;letter-spacing:0;font-size:11px;color:var(--dim);text-decoration:none}
.ov h2 .h2go:hover{color:var(--accent)}
.ov .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:9px}
.ov .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;position:relative;overflow:hidden}
.ov .card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--line2)}
.ov .card.g::after{background:var(--long)} .ov .card.r::after{background:var(--short)} .ov .card.a::after{background:var(--amber)} .ov .card.b::after{background:var(--accent)}
.ov .card .lbl{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.ov .card .val{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1.05;color:var(--ink)}
.ov .card .note{font-size:10.5px;color:var(--dim);margin-top:4px}
.ov .green{color:var(--long)} .ov .red{color:var(--short)} .ov .amber{color:var(--amber)}
.ov .empty{color:var(--dim);font-size:12px;padding:18px;border:1px dashed var(--line2);border-radius:9px;text-align:center}

@media (min-width:980px){ .ov .support{grid-template-columns:1.5fr 1fr;align-items:start} }
@media (max-width:680px){
  .ov .hero,.ov .hero.hedge{grid-template-columns:1fr;gap:22px;padding:20px}
  .ov .hmain .heq{font-size:38px}
  .ov .hstats{grid-template-columns:1fr 1fr}
}
@media (prefers-reduced-motion:reduce){ .ov .mfill{transition:none} }
</style>"""


# book -> (route, nav label, page title)
_META = {
    "prop":  ("/prop-overview",       "Overview", "Overview — PROP"),
    "hedge": ("/hedge-overview", "Overview", "Overview — HEDGE"),
}


def render(book: str = "hedge") -> str:
    path, label, title = _META[book]
    data = overview_data()
    blurb = ("Eval account vs the floor and target walls — plus closed-trade "
             "performance and current market. Read-only; LENS never trades it."
             if book == "prop" else
             "Your live futures wallet — equity, open risk, performance and "
             "current market. Read-only; LENS never trades it.")
    body = f"""
<div class="ov">
  <h1>{title}</h1>
  <div class="sub">{blurb}</div>

  <div id="hero" class="hskel">loading account…</div>

  <div class="support">
    <section>
      <h2>Performance<span class="hint" id="perf-hint"></span><a class="h2go" href="{'/prop-ledger' if book == 'prop' else '/hedge-analytics'}">{'ledger' if book == 'prop' else 'analytics'} →</a></h2>
      <div class="grid" id="perf"></div>
    </section>
    <section>
      <h2>Market<span class="hint">BTC · ATR &asymp; 24h min stop</span><a class="h2go" href="/regime">regime →</a></h2>
      <div class="grid" id="market"></div>
    </section>
  </div>
</div>"""

    script = r"""
const DATA = __DATA__;
const $=id=>document.getElementById(id);
let book='__BOOK__', liveCache=null;
const money=(n,d=0)=>n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:d});
const signed=(n,d=0)=>n==null?'—':(n>=0?'+':'−')+money(Math.abs(n),d);
const card=(lbl,val,note,cls)=>`<div class="card ${cls||''}"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="note">${note||''}</div></div>`;
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));

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
  if(!p.n){ $('perf').innerHTML='<div class="empty">No closed '+book+' trades yet — they appear here once the journal logs one.</div>'; return; }
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

function heroProp(){
  const l=DATA.prop.live;
  const lo=l.floor, hi=l.target, rng=Math.max(hi-lo,1);
  const pct=x=>clamp((x-lo)/rng*100,0,100);
  const up=l.equity>=l.account, cls=up?'g':'r';
  $('hero').className='hero';
  $('hero').innerHTML = `
    <div class="hmain">
      <div class="hlbl">Eval equity</div>
      <div class="heq">$${money(l.equity)}</div>
      <div class="hsub">start <b class="dim">$${money(l.account)}</b> · drawdown <b class="${l.cur_dd_pct>0?'r':'dim'}">−${l.cur_dd_pct}%</b><br>today <b class="${l.today_pnl>=0?'g':'r'}">${signed(l.today_pnl)}$</b></div>
    </div>
    <div class="hmeter">
      <div class="mtrack">
        <div class="mfill ${cls}" style="width:${pct(l.equity)}%"></div>
        <div class="mstart" style="left:${pct(l.account)}%"></div>
        <div class="mnow ${cls}" style="left:${pct(l.equity)}%"></div>
      </div>
      <div class="mends">
        <span class="floor"><span class="cap">▼ Floor $${money(l.floor)}</span><span class="d">${l.to_floor>=0?'$'+money(l.to_floor)+' of room':'breached'}</span></span>
        <span class="target"><span class="cap">Target $${money(l.target)} ▲</span><span class="d">$${money(l.to_target)} to pass</span></span>
      </div>
    </div>`;
}

function heroHedge(a){
  const u=a.unrealized_pnl||0;
  const partial=a.kraken_personal&&a.kraken_personal.error?' · partial':'';
  $('hero').className='hero hedge';
  $('hero').innerHTML = `
    <div class="hmain">
      <div class="hlbl">Live equity · futures wallet</div>
      <div class="heq">€${money(a.total_eur)}</div>
      <div class="hsub">unrealised <b class="${u>0?'g':(u<0?'r':'dim')}">${signed(u)}€</b><br><a href="/hedge-journal" style="color:inherit">open positions →</a>${partial}</div>
    </div>
    <div class="hstats">
      <div class="hstat"><div class="k">Available margin</div><div class="v">${a.available_margin!=null?'€'+money(a.available_margin):'—'}</div><div class="n">free to deploy</div></div>
      <div class="hstat"><div class="k">EUR / USD</div><div class="v">${a.eur_usd!=null?a.eur_usd:'—'}</div><div class="n">fx rate</div></div>
      <div class="hstat"><div class="k">Business acct</div><div class="v">${a.biz_eur!=null?'€'+money(a.biz_eur):'—'}</div><div class="n">not traded</div></div>
    </div>`;
}

function renderHero(){
  if(book==='prop'){ heroProp(); return; }
  if(liveCache){ heroHedge(liveCache); return; }
  $('hero').className='hskel';
  $('hero').textContent='loading live account…';
  fetch('/api/account/live').then(r=>r.json()).then(a=>{ liveCache=a; heroHedge(a); })
    .catch(()=>{ $('hero').className='hskel err'; $('hero').textContent='live account fetch failed'; });
}

renderMarket(); renderHero(); renderPerf();
"""
    script = script.replace("__DATA__", json.dumps(data)).replace("__BOOK__", book)
    return shell(path, label, body, script=script, head_extra=_CSS, meta="snapshot")
