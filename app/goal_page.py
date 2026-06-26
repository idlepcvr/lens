"""LENS /goal — the goal model, reorganised to read top-down by what matters.

A duplicate of /dashboard's calculator (same inputs, same /api/goal compute) with
a redesigned results hierarchy: an infeasibility/health VERDICT banner first, then
the four hero cards, required-growth vs per-trade, a dedicated Risk & Kelly card
that spells out the optimal-vs-used mismatch in plain English, then analytics.
The non-physical Monte-Carlo output is flagged rather than shown as a forecast,
and the buggy per-period € projections are omitted. /dashboard is left untouched.
"""

from .theme import shell

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
/* verdict banner */
.verdict{border-radius:10px;padding:14px 16px;display:flex;gap:12px;align-items:flex-start}
.verdict .vi{font-size:20px;line-height:1;margin-top:1px}
.verdict h3{font-size:15px;font-weight:600;margin:0 0 4px}
.verdict p{font-size:12.5px;line-height:1.5;margin:0}
.verdict.danger{background:var(--short-d);border:1px solid var(--re);color:var(--re)}
.verdict.warn{background:rgba(224,175,104,.10);border:1px solid var(--am);color:var(--am)}
.verdict.ok{background:rgba(115,218,202,.09);border:1px solid var(--gr);color:var(--gr)}
.hero{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
@media(max-width:960px){.hero{grid-template-columns:repeat(2,1fr)}}
.hcard{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 15px;position:relative;overflow:hidden}
.hcard::after{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.hcard.pos::after{background:var(--gr)}.hcard.neg::after{background:var(--re)}
.hcard.warn::after{background:var(--am)}.hcard.blue::after{background:var(--ac)}
.hbig{font-family:var(--mono);font-size:20px;font-weight:700;color:#fff;margin-top:4px;line-height:1}
.hlbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.15em;color:var(--t3);margin-top:9px}
.hsub{font-size:10px;color:var(--t3);margin-top:3px}
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
</style>"""

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
          <div class="frow"><label>Win rate (0–1)</label><input type="text" inputmode="decimal" name="win_rate"></div>
          <div class="frow"><label>R:R ratio</label><input type="text" inputmode="decimal" name="rr_ratio"></div>
          <div class="frow"><label>Leverage</label><input type="text" inputmode="decimal" name="leverage"></div>
          <div class="frow"><label>Trades / week</label><input type="text" inputmode="decimal" name="trades_per_week"></div>
        </div>
        <div class="fsec"><div class="fsec-lbl">Risk</div>
          <div class="frow"><label>Max drawdown</label><input type="text" inputmode="decimal" name="max_drawdown_allowed"></div>
          <div class="frow"><label>Losses allowed</label><input type="text" inputmode="decimal" name="losses_allowed"></div>
          <div class="frow"><label>Frac. Kelly</label><input type="text" inputmode="decimal" name="fractional_kelly"></div>
          <div class="frow"><label>ATR floor</label><input type="text" inputmode="decimal" name="min_underlying_stop_pct" placeholder="—"></div>
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
    <div id="verdict" class="verdict"><div class="vi">…</div><div><h3>computing…</h3><p>enter your parameters</p></div></div>
    <div class="hero">
      <div class="hcard blue"><div class="hbig" id="h-ttg">—</div><div class="hlbl">Time to goal</div><div class="hsub" id="h-ttg-sub">—</div></div>
      <div class="hcard" id="hc-r"><div class="hbig" id="h-r">—</div><div class="hlbl">Actual R<a class="qh" href="/glossary#truerr" target="_blank" rel="noopener" title="what is this?">?</a></div><div class="hsub" id="h-r-sub">after fees</div></div>
      <div class="hcard" id="hc-ev"><div class="hbig" id="h-ev">—</div><div class="hlbl">EV / trade<a class="qh" href="/glossary#ev" target="_blank" rel="noopener" title="what is this?">?</a></div><div class="hsub" id="h-ev-sub">geo drift</div></div>
      <div class="hcard" id="hc-ror"><div class="hbig" id="h-ror">—</div><div class="hlbl">Risk of ruin</div><div class="hsub" id="h-ror-sub">—</div></div>
    </div>
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
function row(k,v,cls=""){ return `<div class="k">${k}</div><div class="v ${cls}">${v}</div>`; }

function render(g){
  const used=g.risk_per_trade??0, opt=g.optimal_risk_pct??0, ror=g.risk_of_ruin??0;
  const over=opt>0?used/opt:Infinity;
  const tgt=Number(FORM.elements.target_balance.value)||null;
  const date=FORM.elements.target_date.value||"the target date";

  // ── verdict banner ──────────────────────────────────────────────
  let lvl,icon,title,msg;
  if(ror>5||over>3){
    lvl="danger"; icon="⛔"; title="Goal infeasible at sane risk";
    msg=`Hitting ${tgt?("€"+fmtInt(tgt)):"the target"} by ${date} needs ${fmtPct(g.monthly_rate)}/mo growth. The only way the math closes is risking ${fmtPct(used)} per trade — ${isFinite(over)?over.toFixed(1)+"×":"∞"} over the ${fmtPct(opt)} optimal (Kelly). Risk of ruin ${fmtPct(ror)}; losses to ruin: ${fmtInt(g.losses_to_ruin)}${g.losses_to_ruin===1?" — a single max loss can end the account.":"."}`;
  } else if(ror>1||over>1.5){
    lvl="warn"; icon="⚠️"; title="Reachable, but over optimal risk";
    msg=`Used risk ${fmtPct(used)} is ${isFinite(over)?over.toFixed(1)+"×":"∞"} the ${fmtPct(opt)} optimal. Risk of ruin ${fmtPct(ror)}. You're leaning on leverage — trim risk or push the date out to de-risk.`;
  } else {
    lvl="ok"; icon="✅"; title="Within safe risk";
    msg=`Used risk ${fmtPct(used)} sits at/under the ${fmtPct(opt)} optimal. Risk of ruin ${fmtPct(ror)} (${g.ror_label}). This goal/date pair is reachable at sane sizing.`;
  }
  document.getElementById("verdict").className="verdict "+lvl;
  document.getElementById("verdict").innerHTML=`<div class="vi">${icon}</div><div><h3>${title}</h3><p>${msg}</p></div>`;

  // ── hero ────────────────────────────────────────────────────────
  document.getElementById("h-ttg").textContent=g.days_remaining!=null?fmtInt(g.days_remaining)+"d":"—";
  document.getElementById("h-ttg-sub").textContent=g.weeks_remaining!=null?(g.weeks_remaining.toFixed(1)+"w · "+g.months_remaining?.toFixed(1)+"mo"):"";
  const ar=g.actual_rr; const rCls=ar>=3.5?"pos":ar>=2.5?"warn":"neg";
  document.getElementById("hc-r").className="hcard "+rCls;
  document.getElementById("h-r").textContent=ar!=null?ar.toFixed(2)+"R":"—";
  document.getElementById("h-r-sub").textContent="vs "+fmtPct(g.underlying_win_pct)+" TP";
  document.getElementById("hc-ev").className="hcard "+((g.per_trade_ev??0)>=0?"pos":"neg");
  document.getElementById("h-ev").textContent=g.per_trade_ev!=null?((g.per_trade_ev>=0?"+":"")+g.per_trade_ev.toFixed(2)+"%"):"—";
  document.getElementById("h-ev-sub").textContent=g.geometric_drift!=null?("drift "+(g.geometric_drift>=0?"+":"")+g.geometric_drift.toFixed(2)+"%"):"";
  document.getElementById("hc-ror").className="hcard "+(ror<=1?"pos":ror<=5?"warn":"neg");
  document.getElementById("h-ror").textContent=fmtPct(ror);
  document.getElementById("h-ror-sub").textContent=g.ror_label??"";

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
    + row("Trades needed",fmtInt(g.trades_needed)+' <span class="v dim">/ '+fmtInt(g.total_trades)+" window</span>");

  // ── Risk & Kelly card ───────────────────────────────────────────
  document.getElementById("rk-row").innerHTML=
      `<div class="rk-cell"><div class="l">Optimal risk</div><div class="n" style="color:var(--gr)">${fmtPct(opt)}</div><div class="s">⅙ Kelly / DD cap</div></div>`
    + `<div class="rk-arrow">→</div>`
    + `<div class="rk-cell"><div class="l" style="color:var(--re)">Used risk / trade</div><div class="n" style="color:var(--re)">${fmtPct(used)}</div><div class="s" style="color:var(--re)">${isFinite(over)?over.toFixed(1)+"× over":"—"}</div></div>`
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
      row("Gain / win","+"+fmtPct(g.acct_gain_win),"pos")
    + row("Loss / loss","−"+fmtPct(g.acct_loss_loss),"neg")
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
  ERR.classList.add("hide");
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
SAVE_BTN.addEventListener("click",async()=>{ await fetch("/api/config",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(readForm())}); SAVED.classList.add("show"); setTimeout(()=>SAVED.classList.remove("show"),1500); });
RESET.addEventListener("click",async()=>{ populate(await fetch("/api/config").then(r=>r.json())); recompute(); });
(async()=>{ populate(await fetch("/api/config").then(r=>r.json())); recompute(); })();

document.querySelectorAll('#goal-form input:not([type=date])').forEach(function(inp){
  function tryCalc(){ var v=inp.value.trim(); if(!v) return;
    try{ var r=Function('"use strict";return('+v.replace(/[^0-9+\-*/.() \t]/g,'')+')')(); if(isFinite(r)){ inp.value=parseFloat(r.toFixed(8)); inp.classList.remove('cx'); recompute(); } }catch(e){} }
  inp.addEventListener('input',function(e){ if(/[+*\/]/.test(inp.value)){ e.stopPropagation(); inp.classList.add('cx'); } else inp.classList.remove('cx'); });
  inp.addEventListener('blur',tryCalc);
  inp.addEventListener('keydown',function(e){ if(e.key==='Enter'){ tryCalc(); e.preventDefault(); } });
});

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
"""


def render() -> str:
    return shell("/goal", "Goal", BODY, script=SCRIPT, head_extra=CSS, meta="re-solved goal model")
