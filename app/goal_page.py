"""LENS /goal — the goal model, reorganised to read top-down by what matters.

A duplicate of /dashboard's calculator (same inputs, same /api/goal compute) with
a redesigned results hierarchy: an infeasibility/health VERDICT banner first, then
the four hero cards, required-growth vs per-trade, a dedicated Risk & Kelly card
that spells out the optimal-vs-used mismatch in plain English, then analytics.
The non-physical Monte-Carlo output is flagged rather than shown as a forecast,
and the buggy per-period € projections are omitted. /dashboard is left untouched.
"""

from .theme import shell
from .goal_hero import HERO_CSS, HERO_HTML, HERO_JS

CSS = r"""<style>
:root{
  --s1:var(--panel);--s2:var(--panel2);--b1:var(--line);--b2:var(--line2);--b3:#313d52;
  --t1:var(--ink);--t2:var(--dim);--t3:var(--faint);--ac:var(--accent);--adim:var(--accent-d);
  --gr:var(--long);--re:var(--short);--am:var(--amber);
}
.main{display:grid;grid-template-columns:248px 1fr;gap:14px;align-items:start;margin-top:14px}
.sidebar{position:sticky;top:74px}
@media(max-width:820px){.main{grid-template-columns:1fr}.sidebar{position:static!important}}
.panel-hd{cursor:pointer;user-select:none}
.pcaret{font-size:11px;color:var(--t3);transition:transform .2s}
.panel.col .pcaret{transform:rotate(-90deg)}
.panel.col form{display:none}
.panel{background:var(--s1);border:1px solid var(--b1);border-radius:10px;overflow:hidden;padding:0}
.panel-hd{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--b1)}
.panel-title{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.2em;color:var(--t2)}
.saved{font-size:10px;color:var(--gr);opacity:0;transition:opacity .3s}.saved.show{opacity:1}
.fsec{padding:10px 14px;border-bottom:1px solid var(--b1)}
.fsec-lbl{font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:.22em;color:var(--t3);margin-bottom:7px}
.frow{display:grid;grid-template-columns:1fr 90px;gap:3px 6px;align-items:center;margin-bottom:4px}
.frow label{font-size:11px;color:var(--t2)}
.frow label .hint{font-size:8.5px;color:var(--t4);font-weight:600}
.frow input{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 8px;border-radius:5px;font-family:var(--mono);font-size:11.5px;width:100%;min-width:0;box-sizing:border-box}
.frow input:focus{outline:none;border-color:var(--ac)}
.frow input.cx{border-color:var(--am)!important;color:var(--am)}
.frow input[type=date]{font-family:inherit;font-size:11.5px}
/* date needs more room than the 90px value column — give it a full-width row */
.frow.frow-date{grid-template-columns:1fr}
.frow.frow-date label{margin-bottom:1px}
/* iOS date inputs overflow their box & drop right padding — normalise on mobile only (keeps desktop's native calendar icon) */
@media(max-width:820px){.frow.frow-date input[type=date]{-webkit-appearance:none;appearance:none;max-width:100%}}
.factns{padding:10px 14px;display:flex;gap:7px;align-items:center}
.btn{padding:6px 13px;border-radius:5px;border:1px solid var(--b2);background:var(--s2);color:var(--t2);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;cursor:pointer;font-family:inherit}
.btn:hover{color:var(--t1);border-color:var(--b3)}
.btn.p{background:var(--adim);color:var(--ac)}
.calc-tip{font-size:9px;color:var(--t3);font-family:var(--mono)}
.metrics{display:flex;flex-direction:column;gap:10px}
/* hero + status line come from goal_hero.HERO_CSS (shared with /dashboard), appended below */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
.card{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:13px 15px}
.card-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--t2);padding-bottom:8px;border-bottom:1px solid var(--b1);margin-bottom:9px}
.kv{display:grid;grid-template-columns:1fr auto;row-gap:1px}
.kv .k{font-size:11.5px;color:var(--t2);padding:2.5px 0}
.kv .v{font-family:var(--mono);font-size:11.5px;color:var(--t1);text-align:right;padding:2.5px 0}
.kv .v.pos{color:var(--gr)}.kv .v.neg{color:var(--re)}.kv .v.warn{color:var(--am)}.kv .v.dim{color:var(--t3)}
/* risk & kelly card */
.rk{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 16px}
.rk-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--t2);margin-bottom:11px}
.rk-row{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:12px;align-items:center}
@media(max-width:560px){.rk-row{grid-template-columns:1fr 1fr;gap:14px}.rk-arrow{display:none}}
.rk-cell .l{font-size:9.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);margin-bottom:3px}
.rk-cell .n{font-family:var(--mono);font-size:21px;font-weight:700;line-height:1}
.rk-cell .s{font-size:10.5px;color:var(--t3);margin-top:3px}
.rk-arrow{font-size:18px;color:var(--t3);text-align:center}
.explain{font-size:11.5px;color:var(--t2);line-height:1.6;border-top:1px solid var(--b1);margin-top:13px;padding-top:11px}
.explain b{color:var(--t1)}
.flagcard{background:rgba(224,175,104,.09);border:1px solid var(--am);border-radius:10px;padding:13px 15px}
.flagcard .ft{font-size:12px;font-weight:600;color:var(--am);margin:0 0 4px}
.flagcard p{font-size:11.5px;color:var(--am);line-height:1.55;margin:0}
.err{background:var(--short-d);border:1px solid var(--short);color:var(--re);padding:10px 14px;border-radius:8px;font-size:12px}
.err.hide{display:none}
/* sensitivity tables (win-rate / R-target) */
.st{display:grid;grid-template-columns:1.1fr 1fr 1fr 1fr;gap:1px 10px;font-family:var(--mono);font-size:11px}
.st span{padding:2px 0;text-align:right;color:var(--t1)}
.st .lc{text-align:left;color:var(--t2)}
.st .sh{font-size:8px;text-transform:uppercase;letter-spacing:.08em;color:var(--t3);border-bottom:1px solid var(--b1);padding-bottom:3px;margin-bottom:2px}
.st .pos{color:var(--gr)}.st .neg{color:var(--re)}.st .warn{color:var(--am)}
.st .cur{font-weight:800}
.st-note{font-size:10px;color:var(--t3);margin-top:7px;line-height:1.4}
/* plan panel — locked plan, amendment log, milestone ladder, stack snapshot */
.card.fold>.card-title{cursor:pointer;user-select:none}
.card.fold .pcaret{display:inline-block;transition:transform .2s}
.card.fold.col .pcaret{transform:rotate(-90deg)}
.card.fold.col .fold-body{display:none}
.fold-sum{font-weight:400;text-transform:none;letter-spacing:0;color:var(--t3);margin-left:8px;font-family:var(--mono);font-size:10.5px;display:none}
.card.fold.col .fold-sum{display:inline}
.plan-line{font-family:var(--mono);font-size:10.5px;color:var(--t3);margin-bottom:10px}
.plan-line b{color:var(--am)}
.mrow{display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:baseline;font-size:11.5px;padding:2.5px 0}
.mrow .mb{font-family:var(--mono);color:var(--t1);min-width:44px}
.mrow .ml{color:var(--t2)}
.mrow .md{font-family:var(--mono);font-size:10.5px;color:var(--t3)}
.mrow.done .mb,.mrow.done .ml{color:var(--gr)}
.mrow.next{background:var(--s2);border-radius:5px;padding:4px 6px;margin:1px -6px}
.mrow.next .ml{color:var(--t1);font-weight:600}
.stale{color:var(--am);font-size:10.5px;margin-top:8px}
.amend{border-top:1px solid var(--b1);margin-top:12px;padding-top:11px;display:none}
.amend.open{display:block}
.amend input,.amend textarea{width:100%;box-sizing:border-box;background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:5px 8px;border-radius:5px;font-family:var(--mono);font-size:11.5px;margin-bottom:6px}
.amend textarea{font-family:inherit;resize:vertical;min-height:52px}
.amend .lbl{font-size:9px;text-transform:uppercase;letter-spacing:.15em;color:var(--t3);margin-bottom:3px}
.snapf{display:grid;grid-template-columns:1fr 1fr auto;gap:6px;margin-top:10px}
.snapf input{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:5px 8px;border-radius:5px;font-family:var(--mono);font-size:11.5px;min-width:0}
.msrc{font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;padding:0 3px;border-radius:3px}
.msrc.typed{color:var(--t3);border:1px solid var(--b2)}
.msrc.measured{color:var(--gr);border:1px solid var(--gr)}
/* ladder hero (C6) — stage · next rung · progress · status word · coverage */
.lhero{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:12px;align-items:center;
  background:var(--s2);border:1px solid var(--b1);border-radius:8px;padding:10px 12px;margin-bottom:10px}
@media(max-width:640px){.lhero{grid-template-columns:1fr}}
.lhero .lh-l{font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:.16em;color:var(--t3);margin-bottom:3px}
.lhero .lh-v{font-family:var(--mono);font-size:13px;font-weight:700;color:var(--t1);line-height:1.2}
.lhero .lh-s{font-size:9.5px;color:var(--t3);margin-top:2px}
.lbar{height:4px;border-radius:2px;background:var(--b1);margin-top:6px;overflow:hidden}
.lbar span{display:block;height:100%;background:var(--ac)}
.sword{font-family:var(--mono);font-size:9.5px;font-weight:800;letter-spacing:.1em;padding:2px 6px;border-radius:4px}
.sword.AHEAD,.sword.ON{color:var(--gr);border:1px solid var(--gr)}
.sword.BEHIND{color:var(--am);border:1px solid var(--am)}
.sword.OFF-PLAN{color:var(--re);border:1px solid var(--re)}
.cov-note{font-size:10px;color:var(--t3);line-height:1.5;margin-top:8px;border-top:1px solid var(--b1);padding-top:7px}
.cov-note b{color:var(--t1)}
.cov-m{display:flex;gap:3px;margin-top:5px}
.cov-m i{flex:1;height:3px;border-radius:1px;background:var(--b2)}
.cov-m i.ok{background:var(--gr)} .cov-m i.no{background:var(--re);opacity:.55}
/* scenario ladder — WR × R, monthly % big / EV small, breakeven frontier drawn */
.slwrap{overflow-x:auto}
.slad{border-collapse:collapse;font-family:var(--mono)}
.slad th{font-size:8.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);padding:4px 6px;text-align:center}
.slad th.rh{text-align:right}
.slad td{width:66px;height:40px;text-align:center;border:1px solid var(--b1);position:relative}
.slad td .m{font-size:12.5px;font-weight:700;color:var(--t1);line-height:1.1}
.slad td .e{font-size:8.5px;color:var(--t3)}
/* the frontier: the last profitable row in each column — its bottom edge IS breakeven WR */
.slad td.fr{border-bottom:2px solid var(--am)}
.slpin{position:absolute;top:1px;right:1px;font-size:7.5px;font-weight:900;letter-spacing:.04em;padding:0 2px;border-radius:2px;color:#0b0f15}
.slpin.meas{background:var(--gr)}
.slpin.plan{background:var(--am);top:1px;right:auto;left:1px}
""" + HERO_CSS + r"""</style>"""

BODY = r"""
<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this page</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what changed vs /dashboard</h4>Same calculator, reorganised to read <b>top-down by what matters</b>. The <b>verdict banner</b> headlines whether the goal is reachable at sane risk; everything below is subordinate to it.
<h4>Risk &amp; Kelly — the core diagnosis</h4><b>Optimal risk</b> = the most you <i>should</i> risk per trade — the smaller of Kelly (growth-optimal) and the drawdown cap. <b>DD constraint</b> = the per-trade risk that keeps your allowed losing streak inside your max-drawdown limit. <b>Used risk</b> = what the goal+date actually <i>force</i> (derived, not chosen). When used ≫ optimal, you're risking ruin to hit a date.
<h4>flagged, not shown</h4>When Monte-Carlo P50 exceeds sanity it means the compounding assumption broke (it ignores ruin) — so it's flagged, not presented as a forecast. The per-period € projections are omitted (source formula inconsistent).
</div></div>

<div class="main">
  <div class="sidebar">
    <div class="panel">
      <div class="panel-hd" onclick="this.parentElement.classList.toggle('col')">
        <span class="panel-title">⚙ Parameters</span>
        <span style="display:flex;align-items:center;gap:9px"><span class="saved" id="saved-pulse">saved ✓</span><span class="pcaret">▾</span></span>
      </div>
      <form id="goal-form" autocomplete="off">
        <div class="fsec"><div class="fsec-lbl">Account</div>
          <div class="frow"><label>Start €</label><input type="text" inputmode="decimal" name="start_balance"></div>
          <div class="frow"><label>Target €</label><input type="text" inputmode="decimal" name="target_balance"></div>
          <div class="frow"><label>Target BTC <span class="hint">@ today →€</span></label><input type="text" inputmode="decimal" id="target_btc" placeholder="e.g. 50"></div>
          <div class="frow frow-date"><label>Target date</label><input type="date" name="target_date"></div>
        </div>
        <div class="fsec"><div class="fsec-lbl">Trading</div>
          <div class="frow"><label>Win rate (0–1) <span class="msrc typed" id="src-win_rate">typed</span></label><input type="text" inputmode="decimal" name="win_rate"></div>
          <div class="frow"><label>R:R ratio <span class="msrc typed" id="src-rr_ratio">typed</span></label><input type="text" inputmode="decimal" name="rr_ratio"></div>
          <div class="frow"><label>Leverage</label><input type="text" inputmode="decimal" name="leverage"></div>
          <div class="frow"><label>Trades / week <span class="msrc typed" id="src-trades_per_week">typed</span></label><input type="text" inputmode="decimal" name="trades_per_week"></div>
          <div style="display:flex;gap:6px;align-items:center;margin-top:7px">
            <button type="button" class="btn" id="measured-btn" disabled>Use measured</button>
            <button type="button" class="btn" id="measured-win" title="window">all</button>
            <button type="button" class="btn" id="validated-btn" disabled title="the /short system — the only cell that survived every gate">Use validated</button>
          </div>
          <div class="calc-tip" id="measured-note" style="margin-top:5px">—</div>
          <div class="calc-tip" id="validated-note" style="margin-top:4px">—</div>
        </div>
        <div class="fsec"><div class="fsec-lbl">Risk</div>
          <div class="frow"><label>Max drawdown</label><input type="text" inputmode="decimal" name="max_drawdown_allowed"></div>
          <div class="frow"><label>Losses allowed</label><input type="text" inputmode="decimal" name="losses_allowed"></div>
          <div class="frow"><label>Frac. Kelly</label><input type="text" inputmode="decimal" name="fractional_kelly"></div>
          <div class="frow"><label>ATR floor <input type="checkbox" id="atr-auto" checked style="vertical-align:-1px"> <span class="hint">auto, decimal</span></label><input type="text" inputmode="decimal" name="min_underlying_stop_pct" placeholder="—"></div>
          <div class="frow"><label>Noise × <span class="hint">ATR mult</span></label><input type="text" inputmode="decimal" id="atr-mult" value="0.5"></div>
        </div>
        <div class="fsec"><div class="fsec-lbl">Execution</div>
          <div class="frow"><label>Fill factor <span class="hint">0–1, size</span></label><input type="text" inputmode="decimal" name="execution_fill_factor" placeholder="1.0"></div>
          <div class="frow"><label>Slippage <span class="hint">frac, 0.001=0.1%</span></label><input type="text" inputmode="decimal" name="slippage_pct" placeholder="0"></div>
        </div>
        <div class="fsec"><div class="fsec-lbl">Optional</div>
          <div class="frow"><label>BTC price €</label><input type="text" inputmode="decimal" name="btc_price_eur" placeholder="—"></div>
          <div class="frow"><label>BTC growth /mo</label><input type="text" inputmode="decimal" name="btc_growth_monthly"></div>
        </div>
        <div class="factns">
          <button type="button" class="btn p" id="save-btn">Apply</button>
          <button type="button" class="btn" id="reset-btn">Reload</button>
          <span class="calc-tip">300*0.1 → ↵</span>
        </div>
      </form>
    </div>
  </div>

  <div class="metrics">
""" + HERO_HTML + r"""
    <div class="grid2">
      <div class="card"><div class="card-title">Required growth to hit goal</div><div class="kv" id="r-growth"></div></div>
      <div class="card"><div class="card-title">Per-trade model</div><div class="kv" id="r-trade"></div></div>
    </div>
    <div class="rk">
      <div class="rk-title">Risk &amp; Kelly — the core mismatch<a class="qh" href="/glossary#kelly" target="_blank" rel="noopener" title="Kelly, DD constraint & optimal risk explained">?</a></div>
      <div class="rk-row" id="rk-row"></div>
      <div class="explain" id="rk-explain"></div>
    </div>
    <div class="grid2">
      <div class="card"><div class="card-title">Risk analytics</div><div class="kv" id="r-stats"></div></div>
      <div class="card"><div class="card-title">Account impact / trade</div><div class="kv" id="r-acct"></div></div>
    </div>
    <div id="r-mc"></div>
    <div class="grid2">
      <div class="card"><div class="card-title">Win-rate sensitivity</div><div class="st" id="r-wrs"></div>
        <div class="st-note">How EV &amp; ruin move as WR slips/improves around your current rate (R held). Below breakeven WR the edge dies regardless of R.</div></div>
      <div class="card"><div class="card-title">R-target scenarios</div><div class="st" id="r-rtgt"></div>
        <div class="st-note">What each reward:risk target yields after fees (WR held). R is the lever you control — exit discipline. ← = your current R:R.</div></div>
    </div>
    <div class="card">
      <div class="card-title">Stack projection — when the rungs land</div>
      <div id="stackproj"></div>
    </div>
    <div class="card">
      <div class="card-title">Scenario ladder — win rate × realized R</div>
      <div class="slwrap"><table class="slad" id="sladder"></table></div>
      <div class="st-note" id="slad-note"></div>
    </div>
    <div class="card fold col" id="ladder-card">
      <div class="card-title">
        <span class="pcaret">▾</span> Milestone ladder
        <span class="fold-sum" id="ladder-sum"></span>
        <span style="float:right;font-weight:400;text-transform:none;letter-spacing:0;color:var(--t3)" id="stack-now">—</span>
      </div>
      <div class="fold-body">
        <div class="lhero" id="lhero" style="display:none"></div>
        <div class="cov-note" id="cov-note" style="display:none"></div>
        <div id="ladder"></div>
        <div class="stale" id="stack-stale" style="display:none"></div>
        <div class="snapf">
          <input type="date" id="sn-date"><input type="text" inputmode="decimal" id="sn-btc" placeholder="BTC total">
          <button type="button" class="btn" id="sn-save">Log</button>
        </div>
      </div>
    </div>
    <div class="card fold col" id="plan-card">
      <div class="card-title">
        <span class="pcaret">▾</span> The plan
        <span class="fold-sum" id="plan-sum"></span>
        <span style="float:right;font-weight:400;text-transform:none;letter-spacing:0"><a href="#" id="amend-toggle" style="color:var(--t3)">amend</a></span>
      </div>
      <div class="fold-body">
        <div class="plan-line" id="plan-line">—</div>
        <div class="kv" id="plan-kv"></div>
        <div class="amend" id="amend-box">
          <div class="lbl">Goal BTC / date</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
            <input type="text" inputmode="decimal" id="am-goal-btc">
            <input type="date" id="am-goal-date">
          </div>
          <div class="lbl">Monthly burn €</div>
          <input type="text" inputmode="decimal" id="am-burn">
          <div class="lbl">Reason (min 20 chars — this is the cage)</div>
          <textarea id="am-reason" placeholder="Why does the plan change? Recorded forever."></textarea>
          <button type="button" class="btn p" id="am-save">Amend plan</button>
          <span class="calc-tip" id="am-msg"></span>
        </div>
      </div>
    </div>
    <div id="err" class="err hide"></div>
  </div>
</div>
"""

SCRIPT = r"""
function tog(id){ document.getElementById('h-'+id).classList.toggle('closed'); document.getElementById('s-'+id).classList.toggle('closed'); }
const FORM=document.getElementById("goal-form"), ERR=document.getElementById("err");
const SAVED=document.getElementById("saved-pulse"), SAVE_BTN=document.getElementById("save-btn"), RESET=document.getElementById("reset-btn");
const NUM_FIELDS=["start_balance","target_balance","trades_per_week","win_rate","rr_ratio","leverage","max_drawdown_allowed","losses_allowed","fractional_kelly","execution_fill_factor","slippage_pct","min_underlying_stop_pct","btc_price_eur","btc_growth_monthly"];

function readForm(){ const fd=new FormData(FORM),out={}; for(const[k,v]of fd.entries()){ if(v===""||v===null){out[k]=null;continue;} out[k]=NUM_FIELDS.includes(k)?(Number.isFinite(Number(v))?Number(v):null):v; } return out; }
function populate(cfg){ for(const k in cfg){ const el=FORM.elements.namedItem(k); if(el&&cfg[k]!=null) el.value=cfg[k]; } }
const fmtPct=v=>(v==null)?"—":v.toFixed(2)+"%";
const fmtPct4=v=>(v==null)?"—":v.toFixed(4)+"%";
const fmtNum=v=>(v==null)?"—":v.toLocaleString("en-US",{maximumFractionDigits:2});
const fmtInt=v=>(v==null)?"—":Math.round(v).toLocaleString();
const fmtEur=v=>(v==null)?"—":"€"+v.toLocaleString("en-US",{maximumFractionDigits:0});
// projected arrival at your ACTUAL geometric drift (weeks from today) → a real date
function projDate(weeks){ if(weeks==null||!isFinite(weeks))return null; const d=new Date(); d.setDate(d.getDate()+Math.round(weeks*7)); return d; }
const fmtMY=d=>d?d.toLocaleDateString("en-GB",{month:"short",year:"numeric"}):"—";
function row(k,v,cls=""){ return `<div class="k">${k}</div><div class="v ${cls}">${v}</div>`; }

function render(g){
  const used=g.risk_per_trade??0, opt=g.optimal_risk_pct??0, ror=g.risk_of_ruin??0;
  const over=opt>0?used/opt:Infinity;
  const start=Number(FORM.elements.start_balance.value)||null;
  const tgt=Number(FORM.elements.target_balance.value)||null;
  const eurOf=p=>(start!=null&&p!=null)?fmtEur(p/100*start):null;              // % of account → €
  const withEur=p=>fmtPct(p)+(eurOf(p)?" ("+eurOf(p)+")":"");                  // "16.40% (€820)"

  // ── sufficiency: at your ACTUAL geometric drift, do you reach goal in-window? ──
  // trades_needed vs total_trades ⟺ weeks_to_goal_actual vs weeks_remaining (same drift).
  const timeShort=g.trades_needed>g.total_trades;
  const insufficient=timeShort;
  const projD=projDate(g.weeks_to_goal_actual);
  renderPillars(g);   // four-pillar hero + status line (shared with /dashboard, goal_hero.py)

  // ── required growth | per-trade ─────────────────────────────────
  document.getElementById("r-growth").innerHTML=
      row("Daily",fmtPct4(g.daily_rate))+row("Weekly",fmtPct(g.weekly_rate))
    + row("Monthly",fmtPct(g.monthly_rate), g.monthly_rate>50?"neg":"")
    + row("Quarterly",fmtPct(g.quarterly_rate))+row("Annual",fmtPct(g.annual_rate), g.annual_rate>1000?"neg":"");
  document.getElementById("r-trade").innerHTML=
      row("EV required / trade",fmtPct4(g.per_trade_ev_required))
    + row("EV current / trade",fmtPct4(g.per_trade_ev), g.per_trade_ev>=g.per_trade_ev_required?"pos":"neg")
    + row("TP / SL move",fmtPct(g.underlying_win_pct)+" / "+fmtPct(g.underlying_loss_pct)+(g.atr_adjusted?" (ATR↑)":""))
    + row("Actual R",fmtNum(g.actual_rr))
    + row("Trades needed",fmtInt(g.trades_needed)+' <span class="v dim">/ '+fmtInt(g.total_trades)+" window</span>", timeShort?"neg":"pos")
    + row("Projected arrival", projD?fmtMY(projD):"never (drift ≤ 0)", insufficient?"neg":"pos");

  // ── Risk & Kelly card ───────────────────────────────────────────
  document.getElementById("rk-row").innerHTML=
      `<div class="rk-cell"><div class="l">Optimal risk</div><div class="n" style="color:var(--gr)">${fmtPct(opt)}</div><div class="s">⅙ Kelly / DD cap</div></div>`
    + `<div class="rk-arrow">→</div>`
    + `<div class="rk-cell"><div class="l" style="color:var(--re)">Used risk / trade</div><div class="n" style="color:var(--re)">${fmtPct(used)}</div><div class="s" style="color:var(--re)">${eurOf(used)?eurOf(used)+" · ":""}${isFinite(over)?over.toFixed(1)+"× over":"—"}</div></div>`
    + `<div class="rk-arrow"></div>`
    + `<div class="rk-cell"><div class="l">DD-implied lev</div><div class="n">${g.dd_implied_leverage!=null?fmtNum(g.dd_implied_leverage)+"×":"—"}</div><div class="s">vs ${fmtNum(g.leverage)}× used</div></div>`;
  document.getElementById("rk-explain").innerHTML=
      `<b>Optimal risk</b> = the most you <i>should</i> risk per trade — the smaller of <b>Kelly</b> (${fmtPct(g.kelly_risk)}, growth-optimal) and the <b>DD cap</b> (${fmtPct(g.dd_risk_constraint)}); here ${g.kelly_risk<=g.dd_risk_constraint?"Kelly":"the DD cap"} binds → ${fmtPct(opt)}.<br>`
    + `<b>DD constraint (${fmtPct(g.dd_risk_constraint)})</b> = the per-trade risk that keeps ${fmtInt(g.losses_allowed)} losses in a row inside your ${fmtPct(g.max_drawdown_allowed)} drawdown limit — a survival cap, not a growth target.<br>`
    + `<b>Used risk (${fmtPct(used)})</b> = what the goal+date <b>force</b> — derived, not a number you chose. ${isFinite(over)?over.toFixed(1)+"× over optimal":""}. <b>Losses to ruin: ${fmtInt(g.losses_to_ruin)}</b>${g.losses_to_ruin===1?" — one max loss can end the account.":"."}`;

  // ── analytics | account ─────────────────────────────────────────
  document.getElementById("r-stats").innerHTML=
      row("Sharpe / trade",fmtNum(g.sharpe_ratio))
    + row("Profit factor",g.profit_factor!=null?fmtNum(g.profit_factor):"∞","pos")
    + row("Trade volatility",fmtPct(g.trade_volatility))
    + row("Risk of ruin",fmtPct(ror), ror<=1?"pos":ror<=5?"warn":"neg")
    + row("Wins to breakeven",fmtInt(g.wins_to_breakeven));
  document.getElementById("r-acct").innerHTML=
      row("Gain / win","+"+withEur(g.acct_gain_win),"pos")
    + row("Loss / loss","−"+withEur(g.acct_loss_loss),"neg")
    + row("Geom drift",(g.geometric_drift>=0?"+":"")+fmtPct(g.geometric_drift), g.geometric_drift>0?"pos":"neg")
    + row("Fill factor",g.execution_fill_factor!=null?g.execution_fill_factor.toFixed(1)+"%":"—",(g.execution_fill_factor??100)<100?"warn":"dim")
    + row("Slippage / trade",fmtPct4(g.slippage_pct),(g.slippage_pct??0)>0?"warn":"dim")
    + row("Friction (fee+slip)",fmtPct4(g.friction_pct),"neg")
    + row("Typical win (log)","+"+fmtPct(g.typical_win),"pos")
    + row("Typical loss (log)",fmtPct(g.typical_loss),"neg");

  // ── Monte Carlo / BTC (flag when non-physical) ──────────────────
  const mcBroken = g.mc_p50!=null && (g.mc_p50>1e9 || (tgt && g.mc_p50>tgt*100));
  let mc;
  if(mcBroken){
    mc=`<div class="flagcard"><p class="ft">🧪 Monte-Carlo output is non-physical</p>`
      +`<p>P50 projects ${fmtEur(g.mc_p50)} — it compounds the +${fmtPct(g.geometric_drift)}/trade drift but <b>ignores ruin</b>. With losses-to-ruin = ${fmtInt(g.losses_to_ruin)}, that drift is never realised. Treat it as the model over-extrapolating, not a forecast.${g.btc_price_at_goal!=null?" &nbsp;Target AUM: "+fmtNum(g.target_aum_btc)+" BTC @ "+fmtEur(g.btc_price_at_goal)+".":""}</p></div>`;
  } else {
    mc=`<div class="card"><div class="card-title">Monte Carlo / BTC</div><div class="kv">`
      +row("MC P05",fmtEur(g.mc_p05),"neg")+row("MC P50",fmtEur(g.mc_p50))+row("MC P95",fmtEur(g.mc_p95),"pos")
      +(g.btc_price_at_goal!=null?row("BTC @ goal",fmtEur(g.btc_price_at_goal))+row("Target AUM",fmtNum(g.target_aum_btc)+" BTC"):"")
      +`</div></div>`;
  }
  document.getElementById("r-mc").innerHTML=mc;
  LAST_G=g; renderScenarioLadder(g);
  ERR.classList.add("hide");
}

// ── Scenario ladder — the 2-D sibling of the sensitivity tables ──────────────
// Cell EV is in R units: WR×(1+R) − 1 − feeR. Monthly % = (1 + risk×EV)^tpm − 1.
// Breakeven WR = (1+feeR)/(1+R) — drawn as the boundary between red and green.
let LAST_G=null;
const SL_WRS=[0.25,0.30,0.35,0.40,0.45,0.50,0.55];
const SL_RS=[1,1.5,2,2.5,3,3.5,4];
function nearestIdx(arr,v){ if(v==null||!isFinite(v))return -1;
  if(v<arr[0]-1e-9||v>arr[arr.length-1]+1e-9) return -1;   // off-grid: don't pretend
  let bi=0; arr.forEach((x,i)=>{ if(Math.abs(x-v)<Math.abs(arr[bi]-v)) bi=i; }); return bi; }
function renderScenarioLadder(g){
  const T=document.getElementById("sladder"), NOTE=document.getElementById("slad-note");
  if(!T||!g) return;
  const riskPct=g.risk_per_trade;
  if(!(riskPct>0)){ T.innerHTML=""; NOTE.textContent="Needs a positive risk/trade to scale."; return; }
  const feeR=(g.friction_pct*g.leverage)/riskPct;   // per-trade friction, in units of one R
  const risk=riskPct/100;
  const tpw=Number(FORM.elements.trades_per_week.value)||0, tpm=tpw*52/12;
  const monthly=(wr,R)=>{ const ev=wr*(1+R)-1-feeR; const base=1+risk*ev;
    return {ev, m: base<=0 ? -1 : Math.pow(base,tpm)-1}; };

  const mi=[nearestIdx(SL_WRS, MEAS&&MEAS.enough?MEAS.win_rate:null),
            nearestIdx(SL_RS,  MEAS&&MEAS.enough?MEAS.rr_ratio:null)];
  const pi=[nearestIdx(SL_WRS, Number(FORM.elements.win_rate.value)),
            nearestIdx(SL_RS,  Number(FORM.elements.rr_ratio.value))];

  let h='<thead><tr><th class="rh">WR ╲ R</th>'+SL_RS.map(r=>`<th>${r.toFixed(1)}R</th>`).join("")+"</tr></thead><tbody>";
  SL_WRS.forEach((wr,i)=>{
    h+=`<tr><th class="rh">${(wr*100).toFixed(0)}%</th>`;
    SL_RS.forEach((R,j)=>{
      const {ev,m}=monthly(wr,R);
      const be=(1+feeR)/(1+R);                                  // breakeven WR for this column
      const below=SL_WRS[i-1];                                  // the row under this one
      const frontier = wr>=be && (i===0 || below<be) ? " fr" : "";
      const t=Math.max(-1,Math.min(1,m/0.20));                  // ±20%/mo saturates the colour
      const bg=`hsla(${t>=0?150:5},72%,45%,${(0.08+0.45*Math.abs(t)).toFixed(3)})`;
      const pins=(i===mi[0]&&j===mi[1]?'<span class="slpin meas">M</span>':"")
                +(i===pi[0]&&j===pi[1]?'<span class="slpin plan">P</span>':"");
      h+=`<td class="${frontier.trim()}" style="background:${bg}" title="WR ${(wr*100).toFixed(0)}% · ${R}R → EV ${ev.toFixed(3)}R/trade, ${(m*100).toFixed(1)}%/mo at ${riskPct.toFixed(2)}% risk × ${tpm.toFixed(1)} trades/mo">`
        +`${pins}<div class="m">${m<=-1?"−100%":(m>=0?"+":"")+(m*100).toFixed(1)+"%"}</div><div class="e">${ev>=0?"+":""}${ev.toFixed(2)}R</div></td>`;
    });
    h+="</tr>";
  });
  T.innerHTML=h+"</tbody>";

  const off=x=>x<0?" <b style='color:var(--am)'>off-grid</b>":"";
  const measTxt = (MEAS&&MEAS.enough)
    ? `<span class="msrc measured">M</span> measured: WR ${(MEAS.win_rate*100).toFixed(1)}% · R ${MEAS.rr_ratio} (n=${MEAS.n})${off(mi[0])}${off(mi[1])}`
    : `<span class="msrc measured">M</span> measured: ${MEAS&&MEAS.n?`n=${MEAS.n}, need ${MEAS.min_n}+`:"no closed trades"}`;
  NOTE.innerHTML=
    `Monthly % big, EV small — at ${riskPct.toFixed(2)}% risk/trade, ${tpm.toFixed(1)} trades/mo, fee drag ${feeR.toFixed(3)}R/trade. `
    +`The <b style="color:var(--am)">amber line</b> is the breakeven frontier: below it no R saves you.<br>`
    +`${measTxt} &nbsp;·&nbsp; <span class="msrc typed" style="border-color:var(--am);color:var(--am)">P</span> plan: `
    +`WR ${(Number(FORM.elements.win_rate.value)*100).toFixed(1)}% · R ${Number(FORM.elements.rr_ratio.value).toFixed(2)}${off(pi[0])}${off(pi[1])}. `
    +`The gap between the two pins is the distance between what you claim and what you've shown.`;
}

async function recompute(){
  const body=readForm();
  for(const r of ["start_balance","target_balance","target_date","trades_per_week","win_rate","rr_ratio","leverage"])
    if(body[r]==null){ ERR.textContent="Missing: "+r; ERR.classList.remove("hide"); return; }
  const payload={}; for(const k in body) if(body[k]!=null) payload[k]=body[k];
  try{
    const r=await fetch("/api/goal",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if(!r.ok){ const d=await r.json(); ERR.textContent=typeof d.detail==="string"?d.detail:JSON.stringify(d.detail); ERR.classList.remove("hide"); return; }
    const g=await r.json(); render(g); renderSensitivity(payload);
  }catch(e){ ERR.textContent="Network: "+e.message; ERR.classList.remove("hide"); }
}

// ── Win-rate & R-target sensitivity — reuses /api/goal with one field varied ──
async function goalAt(payload, ov){
  try{ const r=await fetch("/api/goal",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify(Object.assign({},payload,ov))});
    return r.ok? await r.json(): null; }catch(e){ return null; }
}
const evCls=x=>x>=0?"pos":"neg";
const ruinCls=x=>x<=5?"pos":x<=15?"warn":"neg";
const sgn=x=>(x>=0?"+":"")+x.toFixed(2)+"%";
async function renderSensitivity(payload){
  const baseWr=payload.win_rate, baseRr=payload.rr_ratio;
  let wrs=[-0.10,-0.05,0,0.05,0.10].map(d=>+(baseWr+d).toFixed(3)).filter(w=>w>0.02&&w<0.98);
  wrs=[...new Set(wrs)].sort((a,b)=>a-b);
  const rrs=[2,3,4,5,6];
  const [wrG,rrG]=await Promise.all([
    Promise.all(wrs.map(w=>goalAt(payload,{win_rate:w}))),
    Promise.all(rrs.map(rr=>goalAt(payload,{rr_ratio:rr}))),
  ]);
  let h='<span class="sh lc">WR</span><span class="sh">EV/tr</span><span class="sh">Drift</span><span class="sh">Ruin</span>';
  wrs.forEach((w,i)=>{ const g=wrG[i]; if(!g)return; const c=Math.abs(w-baseWr)<1e-6?" cur":"";
    h+=`<span class="lc${c}">${(w*100).toFixed(0)}%</span><span class="${evCls(g.per_trade_ev)}${c}">${sgn(g.per_trade_ev)}</span>`
     +`<span class="${c}">${sgn(g.geometric_drift)}</span><span class="${ruinCls(g.risk_of_ruin)}${c}">${g.risk_of_ruin.toFixed(0)}%</span>`;
  });
  document.getElementById("r-wrs").innerHTML=h;
  let h2='<span class="sh lc">R:R</span><span class="sh">Act R</span><span class="sh">EV/tr</span><span class="sh">Ruin</span>';
  rrs.forEach((rr,i)=>{ const g=rrG[i]; if(!g)return; const c=Math.abs(rr-baseRr)<0.5?" cur":"";
    h2+=`<span class="lc${c}">${rr.toFixed(1)}${c?" ←":""}</span><span class="${c}">${g.actual_rr!=null?g.actual_rr.toFixed(2):"—"}</span>`
      +`<span class="${evCls(g.per_trade_ev)}${c}">${sgn(g.per_trade_ev)}</span><span class="${ruinCls(g.risk_of_ruin)}${c}">${g.risk_of_ruin.toFixed(0)}%</span>`;
  });
  document.getElementById("r-rtgt").innerHTML=h2;
}

let debounce;
FORM.addEventListener("input",()=>{ clearTimeout(debounce); debounce=setTimeout(recompute,250); });
SAVE_BTN.addEventListener("click",async()=>{ await fetch("/api/config"+BQ,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(readForm())}); SAVED.classList.add("show"); setTimeout(()=>SAVED.classList.remove("show"),1500); });
RESET.addEventListener("click",async()=>{ populate(await fetch("/api/config"+BQ).then(r=>r.json())); recompute(); });
(async()=>{
  populate(await fetch("/api/config"+BQ).then(r=>r.json()));
  // prefill from an /edge "→ Goal" handoff (?win_rate=..&rr_ratio=..&trades_per_week=..
  // — the Fit link also carries the goal itself: start/target/date)
  const qs=new URLSearchParams(location.search);
  ["win_rate","rr_ratio","trades_per_week","leverage","start_balance","target_balance","target_date"].forEach(function(k){
    if(qs.has(k)){ const el=FORM.elements.namedItem(k); if(el) el.value=qs.get(k); }
  });
  recompute();
  // auto-fills read the populated form, so they run strictly after populate()
  loadLadder(); loadMeasured(); loadValidated(); refreshVol();
})();

// ── ATR noise floor + live-price auto-fill (same behaviour as /dashboard) ────
let lastVol=null, volDeb;
const ATR_AUTO=document.getElementById("atr-auto"), ATR_MULT=document.getElementById("atr-mult");
function applyAtrAuto(){
  const fld=FORM.elements.namedItem("min_underlying_stop_pct");
  if(ATR_AUTO.checked && lastVol && lastVol.noise_floor_pct!=null){
    // calc compares this to the price-move fraction → store decimal, not percent
    fld.value=(lastVol.noise_floor_pct/100).toFixed(5); fld.readOnly=true; fld.style.opacity=0.6;
  } else { fld.readOnly=false; fld.style.opacity=1; }
  recompute();
}
async function refreshVol(){
  const m=parseFloat(ATR_MULT.value)||0.5;
  try{ lastVol=await fetch("/api/volatility?mult="+m).then(r=>r.json()); }
  catch(e){ lastVol=null; }
  // BTC price €: live spot at load — we know this number, don't ask for it
  if(lastVol && lastVol.btc_eur && !PX_FILLED){
    FORM.elements.namedItem("btc_price_eur").value=lastVol.btc_eur; PX_FILLED=true;
  }
  applyAtrAuto();
}
let PX_FILLED=false;
ATR_AUTO.addEventListener("change",applyAtrAuto);
ATR_MULT.addEventListener("input",()=>{ clearTimeout(volDeb); volDeb=setTimeout(refreshVol,350); });

document.querySelectorAll('#goal-form input:not([type=date])').forEach(function(inp){
  function tryCalc(){ var v=inp.value.trim(); if(!v) return;
    try{ var r=Function('"use strict";return('+v.replace(/[^0-9+\-*/.() \t]/g,'')+')')(); if(isFinite(r)){ inp.value=parseFloat(r.toFixed(8)); inp.classList.remove('cx'); recompute(); } }catch(e){} }
  inp.addEventListener('input',function(e){ if(/[+*\/]/.test(inp.value)){ e.stopPropagation(); inp.classList.add('cx'); } else inp.classList.remove('cx'); });
  inp.addEventListener('blur',tryCalc);
  inp.addEventListener('keydown',function(e){ if(e.key==='Enter'){ tryCalc(); e.preventDefault(); } });
});

// ── Plan panel: locked plan + amendment log + milestone ladder + stack snapshot ──
const fmtD=s=>s?new Date(s).toLocaleDateString("en-GB",{month:"short",year:"numeric"}):"—";
let LADDER=null;
function renderLadder(L){
  LADDER=L; const p=L.plan;
  document.getElementById("plan-line").innerHTML=
    `<b>v${p.version}</b> · amended ${L.amendments} time${L.amendments===1?"":"s"} · last: ${L.last_reason||"—"}`;
  document.getElementById("plan-sum").textContent=`v${p.version} · ${p.goal_btc} BTC by ${p.goal_date}`;
  document.getElementById("plan-kv").innerHTML=
      row("Goal",`${p.goal_btc} BTC by ${p.goal_date}`)
    + row("North star",`${p.north_star_btc} BTC by ${p.north_star_date}`,"dim")
    + row("Monthly burn",fmtEur(p.burn_monthly_eur))
    + row("Price scenarios",`${p.price_scenarios.bear}% / +${p.price_scenarios.base}% / +${p.price_scenarios.bull}% p.a.`,"dim");
  document.getElementById("am-goal-btc").value=p.goal_btc;
  document.getElementById("am-goal-date").value=p.goal_date;
  document.getElementById("am-burn").value=p.burn_monthly_eur;

  // BTC growth /mo: empty or 0 = unset → fill from the plan's base scenario (% p.a. → monthly)
  const gr=FORM.elements.namedItem("btc_growth_monthly");
  if(!parseFloat(gr.value)&&p.price_scenarios&&p.price_scenarios.base!=null){
    gr.value=(Math.pow(1+p.price_scenarios.base/100,1/12)-1).toFixed(4); recompute();
  }

  const nextIdx=L.milestones.findIndex(m=>!m.done);
  document.getElementById("ladder").innerHTML=L.milestones.map((m,i)=>
    `<div class="mrow ${m.done?"done":""} ${i===nextIdx?"next":""}"><span class="mb">${m.done?"✓ ":""}${m.btc} ₿</span>`
    +`<span class="ml">${m.label}</span><span class="md">${m.date?fmtD(m.date):(m.done?"reached":"—")}</span></div>`).join("");
  document.getElementById("stack-now").textContent=L.stack?`${L.stack.btc_total} ₿ @ ${L.stack.date}`:"no snapshot";
  const nx=L.milestones[nextIdx], dn=L.milestones.filter(m=>m.done);
  document.getElementById("ladder-sum").textContent=
    `${dn.length?dn[dn.length-1].label:"Pre-seed"} → next ${nx?`${nx.btc} ₿ ${nx.label}`:"—"}`;
  const st=document.getElementById("stack-stale");
  if(L.stack_stale){ st.style.display="block";
    st.textContent=L.stack?`⚠ stack snapshot is ${L.stack_age_days} days old — log this month's total.`
                          :"⚠ no stack snapshot — milestone dates need one to be derived."; }
  else st.style.display="none";
}
async function loadLadder(){ renderLadder(await fetch("/api/plan").then(r=>r.json())); loadHero(); }

// ── C6 · ladder hero — stage, next rung, the C3 status word, coverage ────────
function renderHero(H){
  const box=document.getElementById("lhero"), note=document.getElementById("cov-note");
  const C=H.coverage, n=H.next;
  box.style.display="grid";
  box.innerHTML=
     `<div><div class="lh-l">Stage</div><div class="lh-v">${H.stage}</div>`
    +`<div class="lh-s">${H.stack_btc!=null?H.stack_btc+" ₿ · "+(H.overall_pct??0)+"% of goal":"no stack snapshot"}</div>`
    +(H.progress_pct!=null?`<div class="lbar"><span style="width:${H.progress_pct}%"></span></div>`:"")+`</div>`
    +`<div><div class="lh-l">Next rung</div><div class="lh-v">${n?n.btc+" ₿ · "+n.label:"—"}</div>`
    +`<div class="lh-s">${n&&n.date?fmtD(n.date):"date needs a snapshot"}${H.progress_pct!=null?" · "+H.progress_pct+"% there":""}</div></div>`
    +`<div><div class="lh-l">Vs plan</div><div class="lh-v">${H.status?`<span class="sword ${H.status}">${H.status}</span>`:"—"}</div>`
    +`<div class="lh-s">coverage ${C.trailing3!=null?(C.trailing3*100).toFixed(0)+"%":"—"} of burn · ${C.streak}/${C.streak_needed} mo</div></div>`;

  // the honest bar: what the funded account must return monthly to cover burn —
  // so the UI never lets 5–9%/mo become the silent assumption
  const bars=C.months.map(m=>`<i class="${m.ratio>=1?"ok":"no"}" title="${m.month}: ${fmtEur(m.flow)} vs ${fmtEur(C.burn_monthly_eur)} burn"></i>`).join("");
  note.style.display="block";
  note.innerHTML=
     `<b>Income complete</b> fires on ${C.streak_needed} consecutive months of engine cash flow ≥ burn `
    +`(${fmtEur(C.burn_monthly_eur)}/mo) — not on 4% withdrawal math. Streak: <b>${C.streak}</b>.`
    +`<div class="cov-m">${bars}</div>`
    +(C.required_monthly_pct!=null
      ? `<div style="margin-top:5px">At the current funded size <b>${fmtEur(C.funded_account)}</b> × ${(C.payout_share*100).toFixed(0)}% take-home, `
        +`covering burn needs <b style="color:${C.required_monthly_pct>10?"var(--re)":"var(--t1)"}">~${C.required_monthly_pct}%/mo</b>.</div>`
      : "")
    +`<div style="margin-top:4px;color:var(--t3)">Prop payouts: <b>€0</b> — evaluation P&amp;L isn't cash, so it doesn't count toward coverage.</div>`;
}
async function loadHero(){ try{ renderHero(await fetch("/api/goal/hero").then(r=>r.json())); }catch(e){} }

// ── Stack projection — engine → BTC at the three price scenarios ─────────────
function renderStackProj(S){
  const box=document.getElementById("stackproj");
  if(!S||S.stack==null){
    box.innerHTML=`<div class="st-note">${S&&S.reason?S.reason:"—"}</div>`; return; }
  const SC=["bear","base","bull"];
  const cell=d=>d?`<span>${d}</span>`:`<span style="color:var(--re)">never</span>`;
  const src=k=>k==="measured"
    ? `<span class="msrc measured">M</span> measured`
    : `<span class="msrc typed" style="border-color:var(--am);color:var(--am)">P</span> plan`;
  let body="";
  ["measured","plan"].forEach(k=>{
    const R=S.rows[k]; if(!R) return;
    S.targets.forEach((t,i)=>{
      // server keys are Python floats ("5.0"); JS String(5.0) is "5"
      const r=R.rungs[t.toFixed(1)];
      body+=`<span class="lc">${i===0?src(k):""}</span>`
        +`<span class="lc" style="color:var(--t1)">${t} ₿</span>`
        +SC.map(sc=>cell(r[sc])).join("");
    });
    body+=`<span class="lc" style="grid-column:1/-1;color:var(--t3);font-size:9.5px;padding-bottom:5px">`
      +`WR ${(R.win_rate*100).toFixed(1)}% · R ${Number(R.rr).toFixed(2)} · ${R.trades_per_week}/wk · risk ${R.risk_pct}%/trade`
      +`${k==="measured"?` <span style="color:var(--re)">(n=${R.n})</span>`:" (typed)"}</span>`;
  });
  const head=`<span class="sh lc">source</span><span class="sh lc">rung</span>`
    +SC.map(sc=>`<span class="sh">${sc} ${S.scenarios[sc]>0?"+":""}${S.scenarios[sc]}%</span>`).join("");
  box.innerHTML=
     `<div class="st" style="grid-template-columns:1.3fr .6fr 1fr 1fr 1fr">${head}${body}</div>`
    +`<div class="st-note">Stack <b>${S.stack} ₿</b> @ ${S.stack_date} · BTC ${fmtEur(S.price_eur)} · burn ${fmtEur(S.burn_monthly_eur)}/mo.<br>`
    +`${S.note}<br>`
    +`<b>Bear lands first</b> — the rungs are denominated in BTC, so EUR income buys more coin when the price is low. `
    +`A bull run makes a BTC target <i>harder</i> to reach from fiat earnings, not easier.</div>`;
}
async function loadStackProj(){ renderStackProj(await fetch("/api/goal/stack").then(r=>r.json())); }
loadStackProj();
document.querySelectorAll(".card.fold>.card-title").forEach(h=>
  h.addEventListener("click",()=>h.parentElement.classList.toggle("col")));
document.getElementById("amend-toggle").addEventListener("click",e=>{ e.preventDefault(); e.stopPropagation();
  document.getElementById("plan-card").classList.remove("col");
  document.getElementById("amend-box").classList.toggle("open"); });
document.getElementById("am-save").addEventListener("click",async()=>{
  const msg=document.getElementById("am-msg");
  const body={reason:document.getElementById("am-reason").value,
              goal_btc:Number(document.getElementById("am-goal-btc").value),
              goal_date:document.getElementById("am-goal-date").value,
              burn_monthly_eur:Number(document.getElementById("am-burn").value)};
  const r=await fetch("/api/plan/amend",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const d=await r.json();
  if(!r.ok){ msg.textContent=typeof d.detail==="string"?d.detail:"failed"; msg.style.color="var(--re)"; return; }
  msg.textContent="amended ✓"; msg.style.color="var(--gr)";
  document.getElementById("am-reason").value="";
  renderLadder(d); document.getElementById("amend-box").classList.remove("open");
});
document.getElementById("sn-save").addEventListener("click",async()=>{
  const d=document.getElementById("sn-date").value, b=Number(document.getElementById("sn-btc").value);
  if(!d||!Number.isFinite(b)||b<=0) return;
  renderLadder(await fetch("/api/stack",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({date:d,btc_total:b})}).then(r=>r.json()));
  document.getElementById("sn-btc").value="";
});
document.getElementById("sn-date").value=new Date().toISOString().slice(0,10);

// ── "Use measured": the ledger's own WR / R / frequency, never silently mixed with typed ──
let MEAS=null, MEAS_DAYS=null;
// exposed so the hero can flag typed-vs-measured divergence (goal_hero.py)
Object.defineProperty(window,"MEAS",{get:()=>MEAS});
function markSrc(measured){ ["win_rate","rr_ratio","trades_per_week"].forEach(k=>{
  const el=document.getElementById("src-"+k); el.textContent=measured?"measured":"typed";
  el.className="msrc "+(measured?"measured":"typed"); }); }
async function loadMeasured(){
  MEAS=await fetch("/api/goal/measured"+(BQ||"?x=1")+(MEAS_DAYS?"&days="+MEAS_DAYS:"")).then(r=>r.json());
  const btn=document.getElementById("measured-btn"), note=document.getElementById("measured-note");
  const ok=MEAS.n&&MEAS.enough&&MEAS.rr_ratio!=null;
  btn.disabled=!ok;
  note.innerHTML=!MEAS.n ? "no closed trades"
    : ok ? `n=${MEAS.n} · WR ${(MEAS.win_rate*100).toFixed(1)}% · R ${MEAS.rr_ratio} · ${MEAS.trades_per_week}/wk · fees ${MEAS.fee_r}R/trade`
         : `n=${MEAS.n}, need ${MEAS.min_n}+`;
  if(LAST_G) renderScenarioLadder(LAST_G);   // the M pin lands once the ledger has spoken
}
document.getElementById("measured-win").addEventListener("click",async e=>{
  MEAS_DAYS=MEAS_DAYS?null:90; e.target.textContent=MEAS_DAYS?"90d":"all"; await loadMeasured(); });
// ── "Use validated": the /short system — the surviving cell, not the whole book.
// measured() averages the long side (worse than random) with the one thing that
// works, so it correctly reports a negative edge and no reachable target. This
// loads what the account would do trading only the cell that cleared every gate.
let VAL=null;
window.GOAL_SRC="typed";   // typed | measured | validated — read by the hero banner
async function loadValidated(){
  try{ VAL=await fetch("/api/goal/validated").then(r=>r.json()); }catch(e){ return; }
  window.VALIDATED=VAL;   // the hero banner detects the validated source from these
  const btn=document.getElementById("validated-btn"), note=document.getElementById("validated-note");
  if(!btn||!note) return;
  if(!VAL||!VAL.n){ note.textContent="no validated cell — run research/short_edge.py"; return; }
  btn.disabled=!VAL.enough;
  const short=(VAL.trades_per_week||0);
  note.innerHTML=`<b>${VAL.cell}</b> @ R:R ${VAL.rr_ratio} · n=${VAL.n} · WR `
    +`${(VAL.win_rate*100).toFixed(1)}% vs ${(VAL.matched_random*100).toFixed(1)}% random `
    +`(${VAL.edge_pp>0?"+":""}${VAL.edge_pp}pp) · stop ${VAL.stop_pct.toFixed(2)}% / `
    +`target ${VAL.target_pct.toFixed(2)}% · ~${VAL.median_hold_h}h hold`
    +`<br><span style="color:var(--amber)">⚠ fires ${short}/wk — the target needs ~7. `
    +`Loading this sets cadence to what you actually generate, not what you need.</span>`
    +(VAL.mechanical?`<br><span style="color:var(--faint)">+${VAL.mechanical.rules} mechanical `
      +`candidates (${VAL.mechanical.long}L/${VAL.mechanical.short}S, ~${VAL.mechanical.per_week}/wk) `
      +`— uncorrected for multiple comparisons, not counted here.</span>`:"");
}
document.getElementById("validated-btn").addEventListener("click",()=>{
  if(!VAL||!VAL.enough) return;
  FORM.elements.win_rate.value=VAL.win_rate;
  FORM.elements.rr_ratio.value=VAL.rr_ratio;
  FORM.elements.trades_per_week.value=VAL.trades_per_week;
  ["win_rate","rr_ratio","trades_per_week"].forEach(k=>{
    const el=document.getElementById("src-"+k);
    if(el){ el.textContent="validated"; el.className="msrc measured"; }});
  window.GOAL_SRC="validated"; recompute();
});
document.getElementById("measured-btn").addEventListener("click",()=>{
  if(!MEAS||!MEAS.enough) return;
  FORM.elements.win_rate.value=MEAS.win_rate;
  FORM.elements.rr_ratio.value=MEAS.rr_ratio;
  FORM.elements.trades_per_week.value=MEAS.trades_per_week;
  window.GOAL_SRC="measured"; markSrc(true); recompute();
});
FORM.addEventListener("input",()=>{ window.GOAL_SRC="typed"; markSrc(false); });

// Target BTC helper — type a BTC count → fills Target € at TODAY's price (price cancels).
const TBTC=document.getElementById("target_btc");
function tbtcApply(){
  const n=parseFloat(TBTC.value);
  const pxEl=FORM.elements.namedItem("btc_price_eur");
  const px=pxEl?parseFloat(pxEl.value):NaN;
  const TBAL=FORM.elements.namedItem("target_balance");
  if(Number.isFinite(n)&&Number.isFinite(px)&&px>0){ TBAL.value=Math.round(n*px); recompute(); }
}
TBTC.addEventListener("input",tbtcApply);
TBTC.addEventListener("keydown",function(e){ if(e.key==="Enter"){ tbtcApply(); e.preventDefault(); } });
""" + HERO_JS


def render(book: str = "hedge") -> str:
    """One page, two books — an exact clone. `book` only changes which config row
    and measured book feed the form (BQ suffix); every panel and computation is
    identical. Prop values are seeded on first load (see _seed_prop_goal_config)."""
    path = "/prop-goal" if book == "prop" else "/goal"
    bq = "?book=prop" if book == "prop" else ""
    script = f'const BQ="{bq}";\n' + SCRIPT
    return shell(path, "Goal", BODY, script=script, head_extra=CSS, meta="re-solved goal model")
