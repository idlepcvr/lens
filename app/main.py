"""
LENS — FastAPI scaffold (Week 1 of LENS_PLAN.md).

Routes:
  GET    /health                    → liveness
  POST   /api/goal                  → EV-first goal model
  POST   /api/position              → position sizing
  GET    /api/trades                → list trades (filters: venue, direction, result, period)
  POST   /api/trades                → create trade
  GET    /api/trades/{id}           → fetch trade
  PATCH  /api/trades/{id}           → update trade
  DELETE /api/trades/{id}           → delete trade
  GET    /api/transfers             → list transfers
  GET    /api/daily-snapshots       → list daily balance snapshots
  POST   /api/sync/kraken           → pull fills + transfers from Kraken
  POST   /api/sync/bybit            → pull closed PnL + transfers from Bybit
  POST   /api/signals               → ingestion stub (week 3 build-out)
  GET    /api/signals               → list signals (filter: status, strategy)
  GET    /api/signals/{signal_id}   → fetch one signal
  POST   /api/signals/{signal_id}/decide → approve / reject (week 4 wire-up)
"""

from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .calculator import CalcError, compute_goal, compute_position, compute_projection
from .database import (
    init_db,
    create_trade, get_trades, get_trade, update_trade, delete_trade,
    upsert_exchange_trade, clear_synced_open_positions,
    get_transfers, upsert_transfer,
    get_daily_snapshots, upsert_daily_snapshot,
    insert_signal, get_signals, get_signal, decide_signal, expire_stale_signals,
    get_last_non_rejected_signal_for_symbol,
    get_lens_config, upsert_lens_config,
    save_projection_plan, get_projection_plans, get_projection_plan,
    update_projection_plan, delete_projection_plan,
    add_projection_actual, get_projection_actuals, delete_projection_actual,
    autofill_projection_actuals,
    get_actual_stats,
)
from . import discipline
from .models import (
    GoalRequest, GoalResponse,
    PositionRequest, PositionResponse,
    TradeCreate, TradeUpdate, TradeResponse,
    SignalIngest, SignalDecision, SignalResponse,
)
from . import bybit_sync, kraken_sync
from .review import get_enriched_trades, get_ohlcv_1h


app = FastAPI(title="LENS", version="1.0.0-dev")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.exception_handler(404)
async def not_found(request, exc):
    # API callers keep the JSON contract; browsers get a branded page.
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    from .theme import shell
    body = (
        '<div style="max-width:520px;margin:12vh auto 0;text-align:center">'
        '<div style="font-family:var(--mono);font-size:64px;color:var(--faint)">404</div>'
        '<p style="color:var(--dim);margin:14px 0 26px">'
        "This route doesn't exist. The signal was a ghost.</p>"
        '<a href="/" style="color:var(--accent);text-decoration:none;'
        'font-family:var(--mono);font-size:12px;letter-spacing:.14em;'
        'text-transform:uppercase">&larr; back to the desk</a></div>'
    )
    return HTMLResponse(shell(request.url.path, "404", body), status_code=404)


# ─── Landing + health ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home():
    """The front door: pick a machine. Two modes, no mixing.
    PROP = pass the Kraken Prop eval. HEDGE = trade your own edge."""
    from .theme import shell
    css = r"""<style>
.choose{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:30px}
@media(max-width:680px){.choose{grid-template-columns:1fr}}
.door{display:block;text-decoration:none;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:26px 24px;transition:.18s;position:relative;overflow:hidden}
.door:active{transform:scale(.985)}
.door .ic{font-size:30px;line-height:1}
.door h2{font-family:var(--mono);font-size:21px;font-weight:800;letter-spacing:.04em;
  margin:14px 0 4px;color:var(--ink)}
.door .sub{font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}
.door p{font-size:13px;line-height:1.55;color:var(--dim);margin:14px 0 0}
.door .go{font-family:var(--mono);font-size:11px;font-weight:700;margin-top:18px;color:var(--ink)}
.door.prop{border-top:3px solid var(--accent)}
.door.hedge{border-top:3px solid var(--amber)}
@media(hover:hover){.door:hover{border-color:var(--line2);transform:translateY(-2px)}}
.intro{font-size:13px;color:var(--dim);margin-top:6px;line-height:1.5}
.intro b{color:var(--ink)}
</style>"""
    body = """
<p class="intro">Two machines, two goals. Pick one — they never mix.<br>
<b>PROP</b> is the money-maker right now: pass the €20 eval, scale to $200k.
<b>HEDGE</b> is your own-money discretionary edge (S1–S5 setups + vetoes).</p>
<div class="choose">
  <a class="door prop" href="/prop">
    <div class="ic">◎</div>
    <div class="sub">Pass the eval</div>
    <h2>PROP</h2>
    <p>Kraken Prop · 5k Advanced · 0.5% risk · survive the 3% floor, hit +9%.
       One mechanical strategy. Cockpit · Survival · Backtest.</p>
    <div class="go">ENTER →</div>
  </a>
  <a class="door hedge" href="/dashboard">
    <div class="ic">▤</div>
    <div class="sub">Trade your edge</div>
    <h2>HEDGE</h2>
    <p>Your own Kraken money. Mined setups S1–S5, the 7 vetoes that kill the
       bleed, sizing & journal. Dashboard · Desk · Signals · Review · Projection.</p>
    <div class="go">ENTER →</div>
  </a>
</div>"""
    return shell("/", "Home", body, head_extra=css, meta="pick a machine")


@app.get("/dashboard", response_class=HTMLResponse)
def landing():
    trades  = get_trades(limit=5000)
    sigs    = get_signals(limit=5000)
    pending = [s for s in sigs if s["status"] == "pending"]
    by_strat: dict = {}
    for s in sigs:
        by_strat[s["strategy_name"]] = by_strat.get(s["strategy_name"], 0) + 1
    strat_rows = "".join(
        f"<tr><td>{name}</td><td style='text-align:right'>{n}</td></tr>"
        for name, n in sorted(by_strat.items())
    ) or "<tr><td colspan=2 style='opacity:.5'>none yet — wire up Pine (Week 2)</td></tr>"

    from .theme import shell

    css = r"""<style>
:root{
  /* alias the dashboard's local names onto the shared LENS tokens */
  --s1:var(--panel);--s2:var(--panel2);--s3:var(--panel3);
  --b1:var(--line);--b2:var(--line2);--b3:#313d52;
  --t1:var(--ink);--t2:var(--dim);--t3:var(--faint);--t4:#1c2636;
  --ac:var(--accent);--adim:var(--accent-d);
  --gr:var(--long);--re:var(--short);--am:var(--amber);--ui:var(--hud);
}
/* page-local container width override — match Projection's desktop width */
.app{max-width:1180px}
.strip{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:4px 0 18px}
.sc{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:13px 16px}
.sc-n{font-family:var(--mono);font-size:24px;font-weight:600;color:#fff;line-height:1}
.sc-l{font-size:9.5px;font-weight:600;text-transform:uppercase;letter-spacing:.16em;color:var(--t3);margin-top:6px}
.main{display:grid;grid-template-columns:248px 1fr;gap:14px;align-items:start;margin-top:18px}
.sidebar{position:sticky;top:74px}
/* mobile reset MUST come after the base rule or source-order overrides it */
@media(max-width:820px){.main{grid-template-columns:1fr}.sidebar{position:static!important}}
/* collapsible Parameters panel (esp. mobile, where it stacks on top) */
.panel-hd{cursor:pointer;user-select:none;-webkit-tap-highlight-color:transparent}
.pcaret{font-size:11px;color:var(--t3);transition:transform .2s}
.panel.col .pcaret{transform:rotate(-90deg)}
.panel.col form{display:none}
.metrics-hd{margin-top:0}
.panel{background:var(--s1);border:1px solid var(--b1);border-radius:10px;overflow:hidden;margin-bottom:0;padding:0}
.panel-hd{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--b1)}
.panel-title{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.2em;color:var(--t2)}
.saved{font-size:10px;color:var(--gr);opacity:0;transition:opacity .3s}
.saved.show{opacity:1}
.fsec{padding:10px 14px;border-bottom:1px solid var(--b1)}
.fsec-lbl{font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:.22em;color:var(--t4);margin-bottom:7px}
.frow{display:grid;grid-template-columns:1fr 90px;gap:3px 6px;align-items:center;margin-bottom:4px}
.frow:last-child{margin-bottom:0}
.frow label{font-size:11px;color:var(--t2)}
.frow label .hint{font-size:8.5px;color:var(--t4);font-weight:600}
.frow input{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 8px;border-radius:5px;font-family:var(--mono);font-size:11.5px;width:100%;min-width:0;box-sizing:border-box;transition:border-color .12s}
.frow input:focus{outline:none;border-color:var(--ac)}
.frow input.cx{border-color:var(--am)!important;color:var(--am)}
.frow input[type=date]{font-family:var(--ui);font-size:11.5px}
/* date needs more room than the 90px value column — give it a full-width row (matches /goal) */
.frow.frow-date{grid-template-columns:1fr}
.frow.frow-date label{margin-bottom:1px}
/* iOS date inputs overflow their box & drop right padding — normalise on mobile only (keeps desktop's native calendar icon) */
@media(max-width:820px){.frow.frow-date input[type=date]{-webkit-appearance:none;appearance:none;max-width:100%}}
.factns{padding:10px 14px;display:flex;gap:7px;align-items:center}
.btn{padding:6px 13px;border-radius:5px;border:1px solid var(--b2);background:var(--s2);color:var(--t2);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;cursor:pointer;font-family:inherit;transition:all .12s}
.btn:hover{color:var(--t1);border-color:var(--b3)}
.btn.p{background:var(--adim);color:var(--ac);border-color:var(--b2)}
.btn.p:hover{filter:brightness(1.3)}
.calc-tip{font-size:9px;color:var(--t4);font-family:var(--mono)}
.metrics{display:flex;flex-direction:column;gap:14px}
.hero{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
@media(max-width:960px){.hero{grid-template-columns:repeat(2,1fr)}}
.hcard{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 15px;position:relative;overflow:hidden}
.hcard::after{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.hcard.pos::after{background:linear-gradient(90deg,var(--gr),#73daca)}
.hcard.neg::after{background:linear-gradient(90deg,var(--re),#c04060)}
.hcard.warn::after{background:linear-gradient(90deg,var(--am),#ff9e64)}
.hcard.blue::after{background:linear-gradient(90deg,var(--ac),#bb9af7)}
.hbig{font-family:var(--mono);font-size:20px;font-weight:700;color:#fff;margin-top:4px;line-height:1}
.hlbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.15em;color:var(--t3);margin-top:9px}
.hsub{font-size:10px;color:var(--t3);margin-top:3px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
.card{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:15px 17px}
.card-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--t2);padding-bottom:9px;border-bottom:1px solid var(--b1);margin-bottom:11px}
.kv{display:grid;grid-template-columns:1fr auto;row-gap:3px;column-gap:14px}
.kv .k{font-size:11.5px;color:var(--t2);padding:4px 0;border:none}
.kv .v{font-family:var(--mono);font-size:11.5px;color:var(--t1);text-align:right;padding:4px 0}
.kv .v.pos{color:var(--gr)}.kv .v.neg{color:var(--re)}.kv .v.warn{color:var(--am)}.kv .v.dim{color:var(--t3)}
.volcard{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 17px;margin:14px 0;display:flex;gap:20px;flex-wrap:wrap;align-items:center;font-size:12px;color:var(--t2)}
.volcard b{color:var(--t1);font-weight:600}
.volcard .pos{color:var(--gr)}.volcard .neg{color:var(--re)}.volcard .warn{color:var(--am)}.volcard .dim{color:var(--t3)}
.volcard.hide{display:none}
.err{background:var(--short-d);border:1px solid var(--short);color:var(--re);padding:10px 14px;border-radius:8px;font-size:12px}
.err.hide{display:none}
.sec{margin-top:28px}
.sec-hd{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--b1);padding-bottom:7px;margin-bottom:12px}
.sec-hd h2{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.2em;color:var(--t3)}
.sec-hd a{font-size:11px;color:var(--t3);text-decoration:none}
.sec-hd a:hover{color:var(--ac)}
.sigt{width:100%;border-collapse:collapse}
.sigt td{padding:5px 0;font-size:12px;border-bottom:1px solid var(--b1);color:var(--t2)}
.sigt td:last-child{text-align:right;font-family:var(--mono);color:var(--t1)}
.ep{display:flex;align-items:center;gap:10px;padding:5px 8px;border-radius:5px}
.ep:hover{background:var(--s1)}
.ep .m{font-family:var(--mono);font-size:9px;font-weight:700;color:var(--ac);width:52px;flex-shrink:0}
.ep .m.post{color:var(--gr)}.ep .m.patch{color:var(--am)}.ep .m.del{color:var(--re)}
.ep .path{font-family:var(--mono);font-size:11.5px}
.ep .desc{font-size:11px;color:var(--t3);margin-left:auto}
</style>"""

    body = f"""
<div class="strip">
  <div class="sc"><div class="sc-n">{len(trades)}</div><div class="sc-l">Trades</div></div>
  <div class="sc"><div class="sc-n">{len(sigs)}</div><div class="sc-l">Signals</div></div>
  <div class="sc"><div class="sc-n">{len(pending)}</div><div class="sc-l">Pending</div></div>
</div>

<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this dashboard</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what this page is</h4>A <b>live goal-and-risk calculator</b>, not a trade log. Type your account + strategy assumptions into <b>Parameters</b> (left) and every metric recomputes instantly. It answers: <b>given these numbers, do I reach the target — and what's the risk of blowing up before I get there?</b>
<h4>the only inputs are the parameters</h4>Start €, target €, target date, win rate, R:R, leverage, trades/week, drawdown limits. Every field is a calculator — type <code>300*0.1</code> and hit <b>↵</b> to get <code>30</code>. <b>Apply</b> saves them as your defaults; <b>Reload</b> pulls the last saved set.
<h4>the four hero cards</h4><b class="a">Actual R</b> = reward ÷ risk after fees — the one lever you fully control. <b>EV / trade</b> = expected geometric drift per trade; must be <b class="g">positive</b> or the account bleeds. <b class="r">Risk of ruin</b> = odds of hitting the drawdown wall before the goal. <b>Days to goal</b> = time at this pace.
<h4>the metric cards</h4>Break the model down: time-to-goal, required growth rates, the per-trade EV model, Kelly sizing, account impact per win/loss, risk analytics (Sharpe, profit factor, ruin), €-growth projections, and a BTC / Monte-Carlo band (P05 / P50 / P95 outcomes).
<h4>read-only math</h4>LENS computes — it does not trade. Pair this with <a href="/desk">Desk</a> (can I enter now?) and <a href="/goal">Goal</a> (equity curve + projection over time).
</div></div>

<div class="main">
  <div class="sidebar">
    <div class="panel">
      <div class="panel-hd" onclick="this.parentElement.classList.toggle('col')">
        <span class="panel-title">⚙ Parameters</span>
        <span style="display:flex;align-items:center;gap:9px">
          <span class="saved" id="saved-pulse">saved ✓</span>
          <span class="pcaret">▾</span>
        </span>
      </div>
      <form id="goal-form" autocomplete="off">
        <div class="fsec">
          <div class="fsec-lbl">Account</div>
          <div class="frow"><label>Start €</label><input type="text" inputmode="decimal" name="start_balance"></div>
          <div class="frow"><label>Target €</label><input type="text" inputmode="decimal" name="target_balance"></div>
          <div class="frow"><label>Target BTC <span class="hint">@ today →€</span></label><input type="text" inputmode="decimal" id="target_btc" placeholder="e.g. 50"></div>
          <div class="frow frow-date"><label>Target date</label><input type="date" name="target_date"></div>
        </div>
        <div class="fsec">
          <div class="fsec-lbl">Trading</div>
          <div class="frow"><label>Win rate (0–1)</label><input type="text" inputmode="decimal" name="win_rate"></div>
          <div class="frow"><label>R:R ratio</label><input type="text" inputmode="decimal" name="rr_ratio"></div>
          <div class="frow"><label>Leverage</label><input type="text" inputmode="decimal" name="leverage"></div>
          <div class="frow"><label>Trades / week</label><input type="text" inputmode="decimal" name="trades_per_week"></div>
        </div>
        <div class="fsec">
          <div class="fsec-lbl">Risk</div>
          <div class="frow"><label>Max drawdown</label><input type="text" inputmode="decimal" name="max_drawdown_allowed"></div>
          <div class="frow"><label>Losses allowed</label><input type="text" inputmode="decimal" name="losses_allowed"></div>
          <div class="frow"><label>Frac. Kelly</label><input type="text" inputmode="decimal" name="fractional_kelly"></div>
          <div class="frow"><label>ATR floor <input type="checkbox" id="atr-auto" style="vertical-align:-1px"> <span class="hint">auto, decimal</span></label><input type="text" inputmode="decimal" name="min_underlying_stop_pct" placeholder="0.015"></div>
          <div class="frow"><label>Noise × <span class="hint">ATR mult</span></label><input type="text" inputmode="decimal" id="atr-mult" value="0.5"></div>
        </div>
        <div class="fsec">
          <div class="fsec-lbl">Execution</div>
          <div class="frow"><label>Fill factor <span class="hint">0–1, size</span></label><input type="text" inputmode="decimal" name="execution_fill_factor" placeholder="1.0"></div>
          <div class="frow"><label>Slippage <span class="hint">frac, 0.001=0.1%</span></label><input type="text" inputmode="decimal" name="slippage_pct" placeholder="0"></div>
        </div>
        <div class="fsec">
          <div class="fsec-lbl">Optional</div>
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
    <div class="sect metrics-hd" id="h-results" onclick="tog('results')"><span class="caret">▾</span><span class="ttl">Goal model — results</span><span class="line"></span></div>
    <div class="sec-body" id="s-results">
    <div class="hero">
      <div class="hcard blue" id="hc-r">
        <div class="hbig" id="h-r">—</div>
        <div class="hlbl">Actual R</div>
        <div class="hsub" id="h-r-sub">after fees</div>
      </div>
      <div class="hcard" id="hc-ev">
        <div class="hbig" id="h-ev">—</div>
        <div class="hlbl">EV / trade</div>
        <div class="hsub" id="h-ev-sub">geo drift</div>
      </div>
      <div class="hcard" id="hc-ror">
        <div class="hbig" id="h-ror">—</div>
        <div class="hlbl">Risk of ruin</div>
        <div class="hsub" id="h-ror-sub">—</div>
      </div>
      <div class="hcard blue">
        <div class="hbig" id="h-ttg">—</div>
        <div class="hlbl">Days to goal</div>
        <div class="hsub" id="h-ttg-sub">—</div>
      </div>
    </div>

    <div id="vol-card" class="volcard hide"></div>

    <div class="grid2">
      <div class="card"><div class="card-title">Time to goal</div><div class="kv" id="r-time"></div></div>
      <div class="card"><div class="card-title">Required growth</div><div class="kv" id="r-growth"></div></div>
      <div class="card"><div class="card-title">Per-trade model</div><div class="kv" id="r-trade"></div></div>
      <div class="card"><div class="card-title">Risk &amp; Kelly</div><div class="kv" id="r-risk"></div></div>
      <div class="card"><div class="card-title">Account impact</div><div class="kv" id="r-acct"></div></div>
      <div class="card"><div class="card-title">Risk analytics</div><div class="kv" id="r-stats"></div></div>
      <div class="card"><div class="card-title">Growth projections</div><div class="kv" id="r-proj"></div></div>
      <div class="card"><div class="card-title">BTC / Monte Carlo</div><div class="kv" id="r-btc"></div></div>
    </div>

    <div id="err" class="err hide"></div>
    </div>
  </div>
</div>

<div class="sect" id="h-sigstrat" onclick="tog('sigstrat')"><span class="caret">▾</span><span class="ttl">Signals by strategy</span><span class="line"></span></div>
<div class="sec-body" id="s-sigstrat">
  <table class="sigt">{strat_rows}</table>
  <a href="/api/signals" style="font-size:11px;color:var(--t3);display:inline-block;margin-top:8px" onclick="event.stopPropagation()">/api/signals →</a>
</div>

<div class="sect closed" id="h-api" onclick="tog('api')"><span class="caret">▾</span><span class="ttl">API</span><span class="line"></span></div>
<div class="sec-body closed" id="s-api">
  <a href="/docs" style="font-size:11px;color:var(--t3);display:inline-block;margin-bottom:8px" onclick="event.stopPropagation()">interactive docs →</a>
  <div style="display:flex;flex-direction:column;gap:1px">
    <div class="ep"><span class="m">GET</span><span class="path">/health</span><span class="desc">liveness</span></div>
    <div class="ep"><span class="m patch">PATCH</span><span class="path">/api/config</span><span class="desc">save goal inputs</span></div>
    <div class="ep"><span class="m post">POST</span><span class="path">/api/goal</span><span class="desc">EV-first goal model</span></div>
    <div class="ep"><span class="m post">POST</span><span class="path">/api/position</span><span class="desc">ATR-adaptive sizing</span></div>
    <div class="ep"><span class="m">GET</span><span class="path">/api/trades</span><span class="desc">venue / direction / result filters</span></div>
    <div class="ep"><span class="m post">POST</span><span class="path">/api/sync/kraken</span><span class="desc">background fill sync</span></div>
    <div class="ep"><span class="m post">POST</span><span class="path">/api/sync/bybit</span><span class="desc">closed-pnl sync</span></div>
    <div class="ep"><span class="m post">POST</span><span class="path">/api/signals</span><span class="desc">ingest Pine alert</span></div>
    <div class="ep"><span class="m post">POST</span><span class="path">/api/signals/&lt;id&gt;/decide</span><span class="desc">approve / reject</span></div>
  </div>
</div>
"""

    script = f"""
function tog(id){{ document.getElementById('h-'+id).classList.toggle('closed'); document.getElementById('s-'+id).classList.toggle('closed'); }}
const FORM     = document.getElementById("goal-form");
const ERR      = document.getElementById("err");
const SAVED    = document.getElementById("saved-pulse");
const SAVE_BTN = document.getElementById("save-btn");
const RESET    = document.getElementById("reset-btn");

const NUM_FIELDS = [
  "start_balance","target_balance","trades_per_week","win_rate","rr_ratio",
  "leverage","max_drawdown_allowed","losses_allowed","fractional_kelly",
  "execution_fill_factor","slippage_pct","min_underlying_stop_pct","btc_price_eur","btc_growth_monthly"
];

function readForm() {{
  const fd = new FormData(FORM);
  const out = {{}};
  for (const [k, v] of fd.entries()) {{
    if (v === "" || v === null) {{ out[k] = null; continue; }}
    if (NUM_FIELDS.includes(k)) {{
      const n = Number(v); out[k] = Number.isFinite(n) ? n : null;
    }} else {{ out[k] = v; }}
  }}
  return out;
}}

function populate(cfg) {{
  for (const k in cfg) {{
    const el = FORM.elements.namedItem(k);
    if (!el || cfg[k] === null || cfg[k] === undefined) continue;
    el.value = cfg[k];
  }}
}}

const fmtPct  = v => (v === null || v === undefined) ? "—" : v.toFixed(2) + "%";
const fmtPct4 = v => (v === null || v === undefined) ? "—" : v.toFixed(4) + "%";
const fmtNum  = v => (v === null || v === undefined) ? "—" : v.toLocaleString("en-US", {{maximumFractionDigits:2}});
const fmtInt  = v => (v === null || v === undefined) ? "—" : Math.round(v).toLocaleString();
const fmtEur  = v => (v === null || v === undefined) ? "—" : "€" + v.toLocaleString("en-US", {{maximumFractionDigits:0}});

function row(k, v, cls="") {{
  return `<div class="k">${{k}}</div><div class="v ${{cls}}">${{v}}</div>`;
}}

function render(g) {{
  // euro impact on the current balance — every % also shown as what it costs/makes
  const _bal = parseFloat(FORM.elements.namedItem("start_balance").value) || 0;
  const eurOf = p => (_bal && p != null) ? "€" + (_bal * p / 100).toLocaleString("en-US",{{maximumFractionDigits:2}}) : "—";
  const balAfter = p => (_bal && p != null) ? "€" + (_bal * (1 + p / 100)).toLocaleString("en-US",{{maximumFractionDigits:0}}) : "—";

  const ar = g.actual_rr;
  const rCls = ar >= 3.5 ? 'pos' : ar >= 2.5 ? 'warn' : 'neg';
  document.getElementById('hc-r').className = 'hcard ' + rCls;
  document.getElementById('h-r').textContent = ar != null ? ar.toFixed(2) + 'R' : '—';
  document.getElementById('h-r-sub').textContent = 'vs ' + fmtPct(g.underlying_win_pct) + ' TP';

  const evCls = (g.per_trade_ev ?? 0) >= 0 ? 'pos' : 'neg';
  document.getElementById('hc-ev').className = 'hcard ' + evCls;
  document.getElementById('h-ev').textContent = g.per_trade_ev != null ? ((g.per_trade_ev >= 0 ? '+' : '') + g.per_trade_ev.toFixed(3) + '%') : '—';
  document.getElementById('h-ev-sub').textContent = g.geometric_drift != null ? ('drift ' + (g.geometric_drift >= 0 ? '+' : '') + g.geometric_drift.toFixed(3) + '%') : '';

  const rorVal = g.risk_of_ruin ?? 0;
  document.getElementById('hc-ror').className = 'hcard ' + (rorVal <= 5 ? 'pos' : rorVal <= 20 ? 'warn' : 'neg');
  document.getElementById('h-ror').textContent = g.risk_of_ruin != null ? g.risk_of_ruin.toFixed(2) + '%' : '—';
  document.getElementById('h-ror-sub').textContent = g.ror_label ?? '';

  document.getElementById('h-ttg').textContent = g.days_remaining != null ? Math.round(g.days_remaining).toLocaleString() + 'd' : '—';
  document.getElementById('h-ttg-sub').textContent = g.weeks_remaining != null ? (g.weeks_remaining.toFixed(1) + 'w · ' + (g.months_remaining?.toFixed(1)) + 'mo') : '';

  document.getElementById("r-time").innerHTML =
      row("Days remaining",   fmtInt(g.days_remaining))
    + row("Weeks remaining",  fmtNum(g.weeks_remaining))
    + row("Months remaining", fmtNum(g.months_remaining))
    + row("Total interest",   fmtPct(g.total_interest));

  document.getElementById("r-growth").innerHTML =
      row("Daily",     fmtPct4(g.daily_rate))
    + row("Weekly",    fmtPct(g.weekly_rate))
    + row("Monthly",   fmtPct(g.monthly_rate))
    + row("Quarterly", fmtPct(g.quarterly_rate))
    + row("Annual",    fmtPct(g.annual_rate));

  document.getElementById("r-trade").innerHTML =
      row("EV required / trade", fmtPct4(g.per_trade_ev_required))
    + row("EV current / trade",  fmtPct4(g.per_trade_ev),
        g.per_trade_ev >= g.per_trade_ev_required ? "pos" : "neg")
    + row("TP move %",   fmtPct(g.underlying_win_pct))
    + row("SL move %",   fmtPct(g.underlying_loss_pct)
        + (g.atr_adjusted ? " <span class='v warn'>(ATR ↑)</span>" : ""))
    + row("Actual R",    fmtNum(g.actual_rr))
    + row("R multiple",  fmtNum(g.r_multiple))
    + row("Goal %",      fmtPct4(g.goal_pct))
    + row("Trades needed",    fmtInt(g.trades_needed))
    + row("Trades in window", fmtInt(g.total_trades))
    + row("Trades to double", g.trades_to_double != null ? fmtInt(g.trades_to_double) : "∞");

  document.getElementById("r-risk").innerHTML =
      row("Leverage",          fmtNum(g.leverage) + "×")
    + row("Full Kelly",        fmtPct(g.full_kelly) + " · " + eurOf(g.full_kelly))
    + row("Fractional Kelly",  fmtPct(g.fractional_kelly) + " · " + eurOf(g.fractional_kelly))
    + row("Kelly risk",        fmtPct(g.kelly_risk) + " · " + eurOf(g.kelly_risk))
    + row("DD constraint",     fmtPct(g.dd_risk_constraint) + " · " + eurOf(g.dd_risk_constraint))
    + row("Optimal risk",      fmtPct(g.optimal_risk_pct) + " · " + eurOf(g.optimal_risk_pct))
    + row("Used risk / trade", fmtPct(g.risk_per_trade) + " · " + eurOf(g.risk_per_trade), "warn")
    + row("DD-implied lev",    g.dd_implied_leverage != null ? fmtNum(g.dd_implied_leverage) + "×" : "—");

  document.getElementById("r-acct").innerHTML =
      row("Gain / win",         fmtPct(g.acct_gain_win) + " · +" + eurOf(g.acct_gain_win),  "pos")
    + row("Balance if win",     balAfter(g.acct_gain_win), "pos")
    + row("Loss / loss",        fmtPct(g.acct_loss_loss) + " · −" + eurOf(g.acct_loss_loss), "neg")
    + row("Balance if loss",    balAfter(-g.acct_loss_loss), "neg")
    + row("Geom drift",         fmtPct4(g.geometric_drift), g.geometric_drift > 0 ? "pos" : "neg")
    + row("Fill factor",        g.execution_fill_factor != null ? g.execution_fill_factor.toFixed(1) + "%" : "—",
        (g.execution_fill_factor ?? 100) < 100 ? "warn" : "dim")
    + row("Slippage / trade",   fmtPct4(g.slippage_pct), (g.slippage_pct ?? 0) > 0 ? "warn" : "dim")
    + row("Friction (fee+slip)", fmtPct4(g.friction_pct), "neg")
    + row("Typical win (log)",  fmtPct(g.typical_win),  "pos")
    + row("Typical loss (log)", fmtPct(g.typical_loss), "neg");

  document.getElementById("r-stats").innerHTML =
      row("Sharpe (per trade)", fmtNum(g.sharpe_ratio))
    + row("Profit factor",      g.profit_factor != null ? fmtNum(g.profit_factor) : "∞")
    + row("Trade volatility",   fmtPct(g.trade_volatility))
    + row("Risk of ruin",       fmtPct(g.risk_of_ruin) + " <span class='v dim'>(" + g.ror_label + ")</span>",
        g.risk_of_ruin <= 1 ? "pos" : g.risk_of_ruin <= 5 ? "warn" : "neg")
    + row("Losses to ruin",     fmtInt(g.losses_to_ruin))
    + row("Wins to breakeven",  fmtInt(g.wins_to_breakeven))
    + row("Weeks to goal",      g.weeks_to_goal_actual != null ? fmtNum(g.weeks_to_goal_actual) : "∞");

  document.getElementById("r-proj").innerHTML =
      row("Weekly",    fmtEur(g.weekly_growth_eur))
    + row("Monthly",   fmtEur(g.monthly_growth_eur))
    + row("Quarterly", fmtEur(g.quarterly_growth_eur));

  document.getElementById("r-btc").innerHTML =
      row("BTC @ goal",  g.btc_price_at_goal != null ? fmtEur(g.btc_price_at_goal) : "<span class='v dim'>set BTC price</span>")
    + row("Target AUM",  g.target_aum_btc != null ? fmtNum(g.target_aum_btc) + " BTC" : "—")
    + row("MC P05", fmtEur(g.mc_p05), "neg")
    + row("MC P50", fmtEur(g.mc_p50))
    + row("MC P95", fmtEur(g.mc_p95), "pos");

  renderVol(g);
  ERR.classList.add("hide");
}}

async function recompute() {{
  const body = readForm();
  const required = ["start_balance","target_balance","target_date","trades_per_week","win_rate","rr_ratio","leverage"];
  for (const r of required) {{
    if (body[r] === null) {{ ERR.textContent = "Missing: " + r; ERR.classList.remove("hide"); return; }}
  }}
  const payload = {{}};
  for (const k in body) if (body[k] !== null) payload[k] = body[k];
  try {{
    const r = await fetch("/api/goal", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(payload)}});
    if (!r.ok) {{
      const d = await r.json();
      ERR.textContent = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
      ERR.classList.remove("hide"); return;
    }}
    render(await r.json());
  }} catch (e) {{ ERR.textContent = "Network: " + e.message; ERR.classList.remove("hide"); }}
}}

let debounce;
FORM.addEventListener("input", () => {{ clearTimeout(debounce); debounce = setTimeout(recompute, 250); }});

SAVE_BTN.addEventListener("click", async () => {{
  await fetch("/api/config", {{method:"PATCH",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(readForm())}});
  SAVED.classList.add("show");
  setTimeout(() => SAVED.classList.remove("show"), 1500);
}});

RESET.addEventListener("click", async () => {{
  populate(await fetch("/api/config").then(r => r.json()));
  recompute();
}});

(async () => {{
  populate(await fetch("/api/config").then(r => r.json()));
  recompute();
}})();

// calculator — type 300*0.1 → Enter → 30 (skip date inputs: "2028-12-31" would eval to 1985)
document.querySelectorAll('#goal-form input:not([type=date])').forEach(function(inp) {{
  function tryCalc() {{
    var v = inp.value.trim();
    if (!v) return;
    try {{
      var r = Function('"use strict";return(' + v.replace(/[^0-9+\-*/.() \t]/g,'') + ')')();
      if (isFinite(r)) {{ inp.value = parseFloat(r.toFixed(8)); inp.classList.remove('cx'); recompute(); }}
    }} catch(e) {{}}
  }}
  inp.addEventListener('input', function(e) {{
    if (/[+*\/]/.test(inp.value)) {{ e.stopPropagation(); inp.classList.add('cx'); }}
    else inp.classList.remove('cx');
  }});
  inp.addEventListener('blur', tryCalc);
  inp.addEventListener('keydown', function(e) {{ if (e.key === 'Enter') {{ tryCalc(); e.preventDefault(); }} }});
}});

// Target BTC helper — type a BTC count → fills Target € at TODAY's price.
// Price cancels: no BTC-appreciation credit is baked into the trading bar.
const TBTC = document.getElementById("target_btc");
function tbtcApply() {{
  const n  = parseFloat(TBTC.value);
  const pxEl = FORM.elements.namedItem("btc_price_eur");
  const px = pxEl ? parseFloat(pxEl.value) : NaN;
  const TBAL = FORM.elements.namedItem("target_balance");
  if (Number.isFinite(n) && Number.isFinite(px) && px > 0) {{
    TBAL.value = Math.round(n * px);
    recompute();
  }}
}}
TBTC.addEventListener("input", tbtcApply);
TBTC.addEventListener("keydown", function(e) {{ if (e.key === "Enter") {{ tbtcApply(); e.preventDefault(); }} }});

// ── ATR noise-floor checker — live ATR vs your SL; toggle auto-fills the floor ──
let lastVol = null, volDeb;
const ATR_AUTO = document.getElementById("atr-auto");
const ATR_MULT = document.getElementById("atr-mult");

function applyAtrAuto() {{
  const fld = FORM.elements.namedItem("min_underlying_stop_pct");
  if (ATR_AUTO.checked && lastVol && lastVol.noise_floor_pct != null) {{
    // calc compares this to the price-move fraction → store decimal, not percent
    fld.value = (lastVol.noise_floor_pct / 100).toFixed(5); fld.readOnly = true; fld.style.opacity = 0.6;
  }} else {{
    fld.readOnly = false; fld.style.opacity = 1;
  }}
  recompute();
}}

async function refreshVol() {{
  const m = parseFloat(ATR_MULT.value) || 0.5;
  try {{ lastVol = await fetch("/api/volatility?mult=" + m).then(r => r.json()); }}
  catch (e) {{ lastVol = null; }}
  applyAtrAuto();
}}

function renderVol(g) {{
  const c = document.getElementById("vol-card");
  if (!lastVol || lastVol.atr_14d_pct == null) {{ c.classList.add("hide"); return; }}
  const sl = g.underlying_loss_pct, floor = lastVol.noise_floor_pct;
  const verdict = sl == null
    ? "<span class='v dim'>set inputs for an SL</span>"
    : (sl + 0.005 >= floor)
      ? "<span class='v pos'>✅ clears noise floor</span>"
      : "<span class='v neg'>⚠️ INSIDE NOISE — variance will stop you out</span>";
  c.classList.remove("hide");
  c.innerHTML =
      "<span><b>ATR 14d</b> " + lastVol.atr_14d_pct.toFixed(2) + "%</span>"
    + "<span><b>Noise floor</b> " + floor.toFixed(2) + "% <span class='v dim'>(×" + lastVol.noise_mult + ")</span></span>"
    + "<span><b>Your SL</b> " + (sl != null ? sl.toFixed(2) + "%" : "—")
        + (g.atr_adjusted ? " <span class='v warn'>(ATR ↑)</span>" : "") + "</span>"
    + "<span style='margin-left:auto'>" + verdict + "</span>";
}}

ATR_AUTO.addEventListener("change", applyAtrAuto);
ATR_MULT.addEventListener("input", () => {{ clearTimeout(volDeb); volDeb = setTimeout(refreshVol, 350); }});
refreshVol();
"""

    return shell("/dashboard", "Dashboard", body, script=script, head_extra=css, meta="goal model")


@app.get("/health")
def health():
    return {"ok": True, "service": "lens", "ts": datetime.utcnow().isoformat()}


# ─── Goal / Position ──────────────────────────────────────────────────────────

@app.post("/api/goal", response_model=GoalResponse)
def api_goal(req: GoalRequest):
    try:
        result = compute_goal(
            req.start_balance, req.target_balance, req.target_date,
            req.trades_per_week, req.win_rate, req.rr_ratio, req.leverage,
            max_drawdown_allowed=req.max_drawdown_allowed,
            losses_allowed=req.losses_allowed,
            fractional_kelly=req.fractional_kelly,
            execution_fill_factor=req.execution_fill_factor,
            slippage_pct=req.slippage_pct,
            risk_per_trade=req.risk_per_trade,
            min_underlying_stop_pct=req.min_underlying_stop_pct,
            btc_price_eur=req.btc_price_eur,
            btc_growth_monthly=req.btc_growth_monthly,
        )
    except CalcError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {k: v for k, v in result.items() if not k.startswith("_")}


@app.post("/api/position", response_model=PositionResponse)
def api_position(req: PositionRequest):
    try:
        goal = compute_goal(
            req.start_balance, req.target_balance, req.target_date,
            req.trades_per_week, req.win_rate, req.rr_ratio, req.leverage,
            max_drawdown_allowed=req.max_drawdown_allowed,
            losses_allowed=req.losses_allowed,
            fractional_kelly=req.fractional_kelly,
            execution_fill_factor=req.execution_fill_factor,
            slippage_pct=req.slippage_pct,
            risk_per_trade=req.risk_per_trade,
        )
        return compute_position(
            req.entry_price, req.direction,
            req.balance_eur, req.btc_price_eur, goal,
            btc_std_dev=req.btc_std_dev,
        )
    except CalcError as e:
        raise HTTPException(status_code=422, detail=str(e))


_PROP_MOVES_CACHE: dict = {}

def _prop_moves() -> tuple:
    """(avg_win_pct, avg_loss_pct_abs, win_rate_pct) for the prop hero strategy.
    Cached per-process — a backtest, so don't recompute on every keystroke.
    ponytail: process-lifetime cache; add a TTL if the strategy stats drift."""
    if "v" not in _PROP_MOVES_CACHE:
        from .prop_views import prop_metrics
        m = prop_metrics()
        _PROP_MOVES_CACHE["v"] = (m.get("avg_win_pct") or 0.0,
                                  abs(m.get("avg_loss_pct") or 0.0),
                                  m.get("win_rate_pct") or 0.0)
    return _PROP_MOVES_CACHE["v"]


@app.get("/api/prop/position")
def api_prop_position(entry: float, direction: str = "long"):
    """Prop-rule sizing for a manual entry: risk RISK% of the $5k eval ÷ stop,
    leverage capped at the firm's max. Stop/target derived from the prop hero
    strategy's measured average move, then run through prop_ticket (same math as
    the signal ticket and the eval ledger)."""
    from .prop_scan import prop_ticket
    from .prop_ledger import prop_ledger_data
    from .prop_views import prop_config
    win_pct, loss_pct, wr = _prop_moves()
    if not loss_pct:
        raise HTTPException(status_code=422, detail="prop strategy stats unavailable")
    # size off the CURRENT eval equity (realized ledger), not the nominal start
    equity = prop_ledger_data().get("equity") or prop_config()["account"]
    long_ = direction == "long"
    stop   = entry * (1 - loss_pct / 100) if long_ else entry * (1 + loss_pct / 100)
    target = entry * (1 + win_pct / 100)  if long_ else entry * (1 - win_pct / 100)
    t = prop_ticket(entry, stop, target, long_, account=equity)
    t.update(entry=entry, stop=round(stop, 1), target=round(target, 1),
             win_rate_pct=round(wr, 1), direction=direction,
             account_nominal=PROP_NOMINAL)
    return t


# ─── Trades ───────────────────────────────────────────────────────────────────

@app.get("/api/trades")
def list_trades(
    limit:     int           = Query(2000, ge=1, le=5000),
    offset:    int           = Query(0,    ge=0),
    venue:     Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    result:    Optional[str] = Query(None),
    period:    Optional[int] = Query(None),
):
    trades = get_trades(limit=limit, offset=offset, venue=venue,
                        direction=direction, result=result, period=period)
    return {"trades": trades, "count": len(trades), "limit": limit, "offset": offset}


@app.post("/api/trades", response_model=TradeResponse, status_code=201)
def add_trade(trade: TradeCreate):
    return create_trade(trade)


@app.get("/api/trades/{trade_id}", response_model=TradeResponse)
def fetch_trade(trade_id: int):
    t = get_trade(trade_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trade not found")
    return t


@app.patch("/api/trades/{trade_id}", response_model=TradeResponse)
def patch_trade(trade_id: int, data: TradeUpdate):
    t = update_trade(trade_id, data)
    if not t:
        raise HTTPException(status_code=404, detail="Trade not found")
    return t


@app.delete("/api/trades/{trade_id}")
def remove_trade(trade_id: int):
    if not delete_trade(trade_id):
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"ok": True}


# ─── Transfers + daily snapshots (read-only for week 1) ───────────────────────

@app.get("/api/transfers")
def list_transfers(limit: int = Query(200, ge=1, le=2000)):
    return get_transfers(limit=limit)


@app.get("/api/daily-snapshots")
def list_daily_snapshots(limit: int = Query(90, ge=1, le=365)):
    return get_daily_snapshots(limit=limit)


# ─── Sync — Kraken ────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
    account:        str           = "personal"   # personal | biz
    last_fill_time: Optional[str] = None


_kraken_sync_status: dict = {}


def _timeline_to_daily_snapshots(eur_timeline: list) -> int:
    """Take (datetime, eur_balance) timeline, insert one snapshot per calendar day (last balance that day).
    Skips dates that already have a snapshot — live-API captures (portfolioValue) take priority."""
    if not eur_timeline:
        return 0
    by_day: dict = {}
    for dt, bal in eur_timeline:
        day = dt.strftime("%Y-%m-%d")
        by_day[day] = bal
    from app.database import _conn as _db_conn, _DSNAP_COLS
    c = _db_conn()
    existing_dates = {
        row[0] for row in c.execute("SELECT snapshot_date FROM daily_snapshots").fetchall()
    }
    count = 0
    for day, bal in by_day.items():
        if day in existing_dates:
            continue  # don't overwrite live-API snapshots with EUR-wallet-only data
        try:
            upsert_daily_snapshot({"snapshot_date": day, "eur_balance": round(bal, 2)})
            count += 1
        except Exception:
            pass
    c.close()
    return count


def _run_kraken_sync(account: str, api_key: str, api_secret: str, last_fill_time):
    _kraken_sync_status[account] = {"running": True}
    try:
        result = kraken_sync.sync_account(
            api_key, api_secret,
            db_upsert_fn=upsert_exchange_trade,
            db_transfer_fn=upsert_transfer,
            db_clear_open_fn=clear_synced_open_positions,
            last_fill_time=last_fill_time,
        )
        result.pop("eur_timeline", None)
        # Auto-classify newly-synced closed trades (S1–S5 / VETO / NONE) so
        # setup_tag stays current without a manual backfill call.
        try:
            from . import setups
            result["tagged"] = setups.backfill_setup_tags(only_untagged=True).get("tagged", 0)
        except Exception as e:
            result["tag_error"] = str(e)
        result["running"] = False
        _kraken_sync_status[account] = result
    except Exception as e:
        _kraken_sync_status[account] = {
            "running": False, "imported": 0, "skipped": 0,
            "errors": [str(e)], "fills_fetched": 0, "trades_processed": 0,
        }


@app.post("/api/sync/kraken")
def sync_kraken(req: SyncRequest = SyncRequest(), background_tasks: BackgroundTasks = None):
    try:
        api_key, api_secret = kraken_sync.get_api_keys(req.account)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if _kraken_sync_status.get(req.account, {}).get("running"):
        return {"running": True, "detail": "Sync already in progress"}

    background_tasks.add_task(
        _run_kraken_sync, req.account, api_key, api_secret, req.last_fill_time
    )
    _kraken_sync_status[req.account] = {"running": True}
    return {
        "running": True,
        "detail": f"Sync started — poll /api/sync/kraken/result?account={req.account}",
    }


@app.get("/api/sync/kraken/result")
def sync_kraken_result(account: str = "personal"):
    return _kraken_sync_status.get(account, {"running": False, "detail": "No sync run yet"})


# ─── Sync — Bybit ─────────────────────────────────────────────────────────────

@app.post("/api/sync/bybit")
def sync_bybit(req: SyncRequest = SyncRequest()):
    try:
        api_key, api_secret = bybit_sync.get_api_keys(req.account)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result = bybit_sync.sync_account(
        api_key, api_secret,
        db_upsert_fn=upsert_exchange_trade,
        db_transfer_fn=upsert_transfer,
        db_clear_open_fn=clear_synced_open_positions,
        last_fill_time=req.last_fill_time,
    )
    # Auto-classify newly-synced closed trades (S1–S5 / VETO / NONE).
    try:
        from . import setups
        result["tagged"] = setups.backfill_setup_tags(only_untagged=True).get("tagged", 0)
    except Exception as e:
        result["tag_error"] = str(e)
    if result.get("errors"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=207, content=result)
    return result


# ─── Config (drives the dashboard goal calculator) ───────────────────────────

class ConfigUpdate(BaseModel):
    start_balance:           Optional[float] = None
    target_balance:          Optional[float] = None
    target_date:             Optional[str]   = None     # YYYY-MM-DD
    trades_per_week:         Optional[float] = None
    win_rate:                Optional[float] = None     # 0–1
    rr_ratio:                Optional[float] = None
    leverage:                Optional[float] = None
    max_drawdown_allowed:    Optional[float] = None
    losses_allowed:          Optional[int]   = None
    fractional_kelly:        Optional[float] = None
    execution_fill_factor:   Optional[float] = None
    slippage_pct:            Optional[float] = None
    risk_per_trade:          Optional[float] = None     # null = let kelly/dd decide
    min_underlying_stop_pct: Optional[float] = None     # null = no ATR floor
    btc_price_eur:           Optional[float] = None
    btc_growth_monthly:      Optional[float] = None


@app.get("/goal", response_class=HTMLResponse)
def goal_page():
    from .goal_page import render
    return render()


@app.get("/projection")
def projection_removed():
    """Projection page removed — redirect any old links/bookmarks to Goal."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/goal", status_code=307)


@app.get("/glossary", response_class=HTMLResponse)
def glossary_page():
    from .glossary_page import render
    return render()


@app.get("/api/config")
def get_config():
    return get_lens_config()


@app.patch("/api/config")
def patch_config(data: ConfigUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        return get_lens_config()
    return upsert_lens_config(updates)


# ─── Balance snapshot (all accounts → daily_snapshots) ───────────────────────

def _fetch_all_balances() -> dict:
    """Fetch live equity from every configured account, return per-account breakdown + total."""
    from datetime import timezone
    results = {}
    total_eur = 0.0
    total_unrealized = 0.0

    for account in ("personal", "biz"):
        try:
            key, secret = kraken_sync.get_api_keys(account)
            b = kraken_sync.fetch_live_balance(key, secret)
            results[f"kraken_{account}"] = b
            total_eur        += b.get("eur_balance", 0.0)
            total_unrealized += b.get("unrealized_pnl", 0.0)
        except Exception as e:
            results[f"kraken_{account}"] = {"eur_balance": 0.0, "error": str(e)}

    for account in ("personal", "biz"):
        try:
            key, secret = bybit_sync.get_api_keys(account)
            b = bybit_sync.fetch_live_balance(key, secret)
            results[f"bybit_{account}"] = b
            total_eur        += b.get("eur_balance", 0.0)
            total_unrealized += b.get("unrealized_pnl", 0.0)
        except Exception as e:
            results[f"bybit_{account}"] = {"eur_balance": 0.0, "error": str(e)}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    upsert_daily_snapshot({
        "snapshot_date":  today,
        "eur_balance":    round(total_eur, 2),
        "unrealized_pnl": round(total_unrealized, 2),
    })
    results["total_eur"]        = round(total_eur, 2)
    results["unrealized_pnl"]   = round(total_unrealized, 2)
    results["snapshot_date"]    = today
    return results


@app.post("/api/snapshot/balance")
def snapshot_balance():
    """Fetch live equity from all configured accounts and upsert today's daily_snapshot."""
    return _fetch_all_balances()


@app.get("/api/volatility")
def api_volatility(mult: float = 0.5):
    """Live BTC ATR(14d) + the noise floor a stop must clear (ATR × mult).
    Feeds the dashboard's ATR auto-floor toggle."""
    from .volatility import fetch_volatility
    return fetch_volatility(noise_mult=mult)


@app.get("/api/positions/live")
def positions_live():
    """Live open positions across Kraken accounts, Kraken-style detail (mark,
    value, UP&L€/%, RoE, est. liquidation, margin, leverage). Read-only."""
    out = []
    for account in ("personal", "biz"):
        try:
            key, secret = kraken_sync.get_api_keys(account)
            out.extend(kraken_sync.fetch_open_positions_enriched(key, secret, account))
        except Exception:
            pass
    return {"positions": out}


@app.get("/api/account/live")
def account_live():
    """Read-only live balances — no snapshot write. Powers /overview.
    personal = the hedge book you actually trade → drives the hedge equity card.
    biz = separate business funds, shown as its own readout (NOT summed in).
    LENS never trades either."""
    results: dict = {}
    eur_usd = None
    for account in ("personal", "biz"):
        try:
            key, secret = kraken_sync.get_api_keys(account)
            b = kraken_sync.fetch_live_balance(key, secret)
            results[f"kraken_{account}"] = b
            if "error" not in b:
                eur_usd = b.get("eur_usd", eur_usd)
        except Exception as e:
            results[f"kraken_{account}"] = {"error": str(e)}

    personal = results.get("kraken_personal", {})
    biz      = results.get("kraken_biz", {})
    # Hedge = personal only. biz funds are business, not trading equity.
    results["total_eur"]        = round(personal.get("eur_balance", 0.0), 2)
    results["available_margin"] = round(personal.get("available_margin", 0.0), 2)
    results["unrealized_pnl"]   = round(personal.get("unrealized_pnl", 0.0), 2)
    results["biz_eur"]          = round(biz.get("eur_balance"), 2) if "error" not in biz else None
    results["eur_usd"]          = eur_usd
    return results


# ─── Projection plans ─────────────────────────────────────────────────────────

class ProjectionPlanCreate(BaseModel):
    label:           str            = ""
    start_bal:       float
    stop_pct:        float
    tp_pct:          float
    leverage:        float
    win_rate:        float
    tpw:             float
    weeks:           float
    btc_price:       float
    fee_rt:          float
    p50_final:       Optional[float] = None
    plan_start_date: Optional[str]   = None
    curve_json:      Optional[str]   = None


class ProjectionPlanUpdate(BaseModel):
    label:           Optional[str] = None
    status:          Optional[str] = None   # active|paused|completed
    plan_start_date: Optional[str] = None
    curve_json:      Optional[str] = None


class ActualCreate(BaseModel):
    date:    str
    balance: float
    note:    Optional[str] = None


def _plan_with_actuals(plan: dict) -> dict:
    if not plan:
        return plan
    plan["actuals"] = get_projection_actuals(plan["id"])
    return plan


@app.post("/api/projections", status_code=201)
def create_projection(data: ProjectionPlanCreate):
    plan = save_projection_plan(data.model_dump())
    return _plan_with_actuals(plan)


@app.get("/api/projections")
def list_projections():
    plans = get_projection_plans()
    for p in plans:
        if p.get("status") in ("active", None, "paused"):
            autofill_projection_actuals(p["id"])
    plans = get_projection_plans()
    return {"plans": [_plan_with_actuals(p) for p in plans]}


@app.patch("/api/projections/{plan_id}")
def update_projection(plan_id: int, data: ProjectionPlanUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    plan = update_projection_plan(plan_id, updates)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _plan_with_actuals(plan)


@app.delete("/api/projections/{plan_id}", status_code=204)
def remove_projection(plan_id: int):
    if not delete_projection_plan(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")


@app.post("/api/projections/{plan_id}/actuals", status_code=201)
def add_actual(plan_id: int, data: ActualCreate):
    if not get_projection_plan(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return add_projection_actual(plan_id, data.date, data.balance, data.note)


@app.get("/api/projections/{plan_id}/actuals")
def list_actuals(plan_id: int):
    if not get_projection_plan(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"actuals": get_projection_actuals(plan_id)}


@app.delete("/api/projections/{plan_id}/actuals/{actual_id}", status_code=204)
def remove_actual(plan_id: int, actual_id: int):
    if not delete_projection_actual(actual_id):
        raise HTTPException(status_code=404, detail="Actual not found")


@app.post("/api/projections/{plan_id}/actuals/autofill")
def autofill_actuals(plan_id: int):
    if not get_projection_plan(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    added = autofill_projection_actuals(plan_id)
    plan = _plan_with_actuals(get_projection_plan(plan_id))
    return {"added": added, "plan": plan}


# ─── Signals (week 3 wires the real ingestion path; endpoint exists now) ──────

@app.post("/api/signals", response_model=SignalResponse, status_code=201)
def ingest_signal(payload: SignalIngest):
    """Accept a Pine Script alert payload, run discipline filters, persist.

    Signals that violate discipline (Saturday, sub-5min cooldown, bleed hour,
    bad venue) are still stored — with status='rejected' and rejection_reason
    set — so the dataset stays complete. Live signals land as status='pending'
    for manual approve/reject in the decision view.
    """
    data = payload.model_dump()
    last = get_last_non_rejected_signal_for_symbol(data["symbol"])
    reason = discipline.evaluate(data, last)
    try:
        return insert_signal(data, auto_rejection_reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/discipline")
def get_discipline_settings():
    """Current server-side discipline filter settings."""
    return discipline.settings()


@app.get("/api/signals")
def list_signals(
    status:   Optional[str] = Query(None, description="pending|approved|rejected|expired"),
    strategy: Optional[str] = Query(None),
    limit:    int           = Query(200, ge=1, le=2000),
):
    from .setups import _trade_shape
    sigs = get_signals(status=status, strategy=strategy, limit=limit)
    for sg in sigs:
        try:
            if sg.get("entry_price") and sg.get("stop_price") and sg.get("target_price"):
                sg["ticket"] = _trade_shape(sg)
        except Exception:
            pass
    return {"signals": sigs}


@app.get("/api/signals/{signal_id}", response_model=SignalResponse)
def fetch_signal(signal_id: str):
    s = get_signal(signal_id)
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    return s


@app.post("/api/signals/{signal_id}/decide", response_model=SignalResponse)
def decide(signal_id: str, decision: SignalDecision):
    try:
        s = decide_signal(
            signal_id,
            status=decision.status,
            your_conviction=decision.your_conviction,
            rejection_reason=decision.rejection_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    return s


@app.post("/api/signals/expire-stale")
def expire_stale(older_than_minutes: int = Query(30, ge=1, le=10080)):
    """Mark pending signals older than N minutes as 'expired'. Week 4 cron target."""
    n = expire_stale_signals(older_than_minutes=older_than_minutes)
    return {"expired": n}


# ─── Signals / Conviction page ───────────────────────────────────────────────

@app.get("/signals", response_class=HTMLResponse)
def signals_page_new():
    """Responsive signals queue built on the shared design system."""
    from .signals_page import render
    return render()



# ─── Backtest ─────────────────────────────────────────────────────────────────

from app.backtest_engine import STRATEGIES as BT_STRATEGIES, run_strategy as _run_strategy
import threading as _threading

_bt_cache: dict = {}       # name → result
_bt_running: dict = {}     # name → True/False


@app.get("/backtest", response_class=HTMLResponse)
def backtest_page():
    from .theme import shell
    # Order the dropdown by the cached strategy ranking (strategy_scores.json,
    # the same R-sweep that powers the /strategy board) so the best-scoring
    # backtestable edges surface first instead of raw registry order. Ranking
    # also contains hedge setups (S1/H8…) that aren't in the backtest registry —
    # filter to names we can actually run.
    try:
        import json as _json, os as _os
        _sp = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "strategy_scores.json")
        _ranked = _json.load(open(_sp)).get("results", [])
    except Exception:
        _ranked = []
    _rank = {r["name"]: r for r in _ranked
             if r.get("name") in BT_STRATEGIES and not r.get("thin")}
    _order = [r["name"] for r in sorted(_rank.values(),
                                        key=lambda r: r.get("score", -99), reverse=True)]
    _rest = [k for k in BT_STRATEGIES if k not in _rank]

    def _bt_opt(k, i=None):
        r = _rank.get(k)
        if r and r.get("best_wr") is not None:
            lbl = f'#{i} · {k} · {r["best_wr"]}% WR @ {r["best_r"]}R · n={r.get("n","?")} (score {r["score"]})'
        else:
            lbl = f'{k} — {BT_STRATEGIES[k]["description"][:60]}'
        return f'<option value="{k}">{lbl}</option>'

    strat_opts = "".join(_bt_opt(k, i + 1) for i, k in enumerate(_order))
    if _rest:
        strat_opts += '<option disabled>──────── unranked / thin ────────</option>'
        strat_opts += "".join(_bt_opt(k) for k in _rest)
    css = r"""<style>
:root{
  --s1:var(--panel);--s2:var(--panel2);--b1:var(--line);--b2:var(--line2);
  --t1:var(--ink);--t2:var(--dim);--t3:var(--faint);--ac:var(--accent);--adim:var(--accent-d);--ui:var(--hud);
}
h1{color:var(--t1);font-size:17px;margin:4px 0 4px}
.sub{color:var(--t3);font-size:11px;margin-bottom:20px}
select,button{background:var(--s1);border:1px solid var(--b2);color:var(--t1);border-radius:6px;padding:8px 14px;font-size:12px;cursor:pointer;font-family:var(--ui)}
button.run{background:var(--adim);color:var(--ac);border-color:var(--b2);font-weight:600;padding:9px 22px}
button.run:hover{filter:brightness(1.3)}
button.run:disabled{opacity:.5;cursor:default}
.row{display:flex;gap:12px;align-items:center;margin-bottom:24px;flex-wrap:wrap}
.card{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:16px 20px;margin-bottom:16px}
.metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin-bottom:16px}
.metric{background:var(--bg);border:1px solid var(--b1);border-radius:6px;padding:10px 14px}
.metric .lbl{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}
.metric .val{font-size:20px;font-weight:700;font-family:var(--mono);color:var(--t1)}
.metric .val.good{color:var(--long)}.metric .val.bad{color:var(--short)}.metric .val.warn{color:var(--amber)}
.metric .val.big{font-size:14px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{padding:6px 10px;text-align:left;font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--b1)}
td{padding:6px 10px;border-bottom:1px solid var(--b1)}
.win{color:var(--long)}.loss{color:var(--short)}
#status{color:var(--ac);font-size:12px;margin-left:12px}
canvas{width:100%;height:200px;display:block}
.hm{border-collapse:collapse;font-family:var(--mono);width:auto}
.hm th{padding:5px 8px;font-size:9px;color:var(--t3);text-align:center;border:none}
.hm th.hm-corner,.hm tbody th{text-align:right;color:var(--t2)}
.hm td.hm-cell{width:56px;height:34px;text-align:center;font-size:11px;border:1px solid var(--b1);color:var(--t1)}
.hm td.hm-base{outline:2px solid var(--t1);outline-offset:-2px}
</style>"""

    body = f"""
<h1>Strategy Backtest</h1>
<div class="sub">BTC perps · Bybit USDT data (= same price action as Kraken USD, arbitraged tick-for-tick — Kraken's public API only serves ~4mo of candles) · each strategy on its own timeframe · starting balance editable (defaults to your live equity) · 0.15%/side fee</div>

<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this backtest</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what this page is</h4>Runs a <b>locked, mechanical strategy</b> over ~30 months of BTC/USDT 4H history and reports exactly how it would have done — no discretion, no curve-fitting. Pick a strategy, hit <b>Run</b>, read the scorecard.
<h4>the metrics that matter</h4><b class="g">Win rate</b> ≥48% = goal-grade. <b>Profit factor</b> ≥1.5 (gross win ÷ gross loss). <b class="a">Avg R</b> ≥3.5 — the real lever. <b class="r">Max DD</b> &lt;40% survivable, and <b>max consecutive losses</b> = your risk-of-ruin reality check.
<h4>the risk-adjusted trio (plain English)</h4><b>Sharpe</b> = return per unit of <i>bumpiness</i> — how much reward you got for how wildly the equity swung. ≥1 is solid, higher is smoother. <b>Sortino</b> = the same idea but only counts the <i>downside</i> swings (it doesn't punish you for big <i>up</i> moves — fairer for high-R strategies). <b>Calmar</b> = annual return ÷ worst drawdown — "how much did I make for the deepest hole I sat in." Use them to compare two strategies with similar returns: the higher trio = the same money with less pain.
<h4>equity curve + trade log</h4>The curve is account €over the window; the log lists every entry/exit with PnL% and hold time. Look for <b>smooth-ish</b> growth, not one lucky spike.
<h4>historical, not live</h4>Past fills on past candles — assumptions, not promises. Compare against your real results in <a href="/journal">Journal</a>.
</div></div>

<div class="row">
  <select id="strat">{strat_opts}</select>
  <select id="months" title="Lookback window — longer = bigger sample (more reliable WR), shorter = more recent regime">
    <option value="12">12 mo (recent)</option>
    <option value="24" selected>24 mo</option>
    <option value="36">36 mo (max sample)</option>
  </select>
  <input id="capital" type="number" step="any" value="637" title="Starting balance for the sim — defaults to your live hedge equity"
         style="width:96px;background:var(--s1);border:1px solid var(--b2);color:var(--t1);border-radius:6px;padding:8px 10px;font-size:12px;font-family:var(--ui)">
  <button class="run" id="run-btn" onclick="runBacktest()">▶ Run</button>
  <button id="sweep-btn" onclick="runSweep()" title="Re-run this strategy across a grid of stop-loss × take-profit to see if the edge is robust or a lucky single point">⊞ Sweep SL×TP</button>
  <span id="status"></span>
</div>

<div id="sweep-wrap" style="display:none">
  <div class="card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
      <div style="font-size:14px;font-weight:700;color:var(--t1)">Robustness sweep — SL × TP</div>
      <select id="sweep-metric" onchange="colorHeatmap()" style="padding:6px 12px">
        <option value="net_pct">colour by: Net return %</option>
        <option value="sharpe">colour by: Sharpe</option>
        <option value="sortino">colour by: Sortino</option>
        <option value="calmar">colour by: Calmar</option>
        <option value="win_rate">colour by: Win rate %</option>
      </select>
    </div>
    <div id="heatmap" style="overflow-x:auto"></div>
    <div style="font-size:11px;color:var(--t3);margin-top:12px;line-height:1.55">Each cell = the same strategy re-run with that <b>SL</b> (rows, stop-loss) and <b>TP</b> (columns, take-profit). <b class="win">A real edge is a green neighbourhood</b> — several good cells clustered together. <b class="loss">One lone green square surrounded by red</b> = curve-fitting; it won't survive live. The <b>outlined</b> cell is the strategy's own configured setting. Hover any cell for full stats.</div>
  </div>
</div>

<div id="results" style="display:none">
  <div class="card">
    <div id="strat-name" style="font-size:14px;font-weight:700;color:var(--ink);margin-bottom:4px"></div>
    <div id="strat-desc" style="font-size:11px;color:var(--faint);margin-bottom:14px"></div>
    <div class="metrics" id="metrics-grid"></div>
    <canvas id="eq-chart"></canvas>
  </div>
  <div class="card">
    <div style="font-size:11px;font-weight:600;color:var(--faint);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">Trade Log</div>
    <div style="overflow-x:auto;max-height:400px;overflow-y:auto">
    <table>
      <thead><tr><th>Entry</th><th>Exit</th><th>Dir</th><th>Entry $</th><th>Exit $</th><th>Result</th><th>PnL %</th><th>Hours</th><th>Equity</th></tr></thead>
      <tbody id="trade-tbody"></tbody>
    </table>
    </div>
  </div>
</div>
"""

    script = f"""
function tog(id){{ document.getElementById('h-'+id).classList.toggle('closed'); document.getElementById('s-'+id).classList.toggle('closed'); }}
function runBacktest() {{
  var name = document.getElementById('strat').value;
  var btn  = document.getElementById('run-btn');
  var stat = document.getElementById('status');
  btn.disabled = true;
  btn.textContent = '⏳ Running…';
  stat.textContent = 'Fetching data + running backtest…';
  document.getElementById('results').style.display = 'none';

  var months = parseInt(document.getElementById('months').value) || 24;
  var capital = parseFloat(document.getElementById('capital').value) || 637;
  fetch('/api/backtest/run', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{name: name, months: months, initial_capital: capital}})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    btn.disabled = false; btn.textContent = '▶ Run';
    if (d.error) {{ stat.textContent = 'Error: ' + d.error; return; }}
    stat.textContent = '';
    renderResults(d);
  }})
  .catch(function(e) {{ btn.disabled = false; btn.textContent = '▶ Run'; stat.textContent = 'Failed: ' + e; }});
}}

function runSweep() {{
  var name = document.getElementById('strat').value;
  var months = parseInt(document.getElementById('months').value) || 24;
  var capital = parseFloat(document.getElementById('capital').value) || 637;
  var btn = document.getElementById('sweep-btn');
  btn.disabled = true; btn.textContent = '⏳ Sweeping…';
  document.getElementById('sweep-wrap').style.display = 'none';
  fetch('/api/backtest/sweep', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{name: name, months: months, initial_capital: capital}})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    btn.disabled = false; btn.textContent = '⊞ Sweep SL×TP';
    if (d.error) {{ alert('Sweep error: ' + d.error); return; }}
    window._sweep = d; buildHeatmap(d);
    document.getElementById('sweep-wrap').style.display = '';
  }})
  .catch(function(e) {{ btn.disabled = false; btn.textContent = '⊞ Sweep SL×TP'; alert('Sweep failed: ' + e); }});
}}

function buildHeatmap(d) {{
  var map = {{}};
  d.cells.forEach(function(c) {{ map[c.stop + '|' + c.tp] = c; }});
  var h = '<table class="hm"><thead><tr><th class="hm-corner">SL ╲ TP</th>';
  d.tps.forEach(function(tp) {{ h += '<th>' + tp + '%</th>'; }});
  h += '</tr></thead><tbody>';
  d.stops.forEach(function(sp) {{
    h += '<tr><th>' + sp + '%</th>';
    d.tps.forEach(function(tp) {{
      var c = map[sp + '|' + tp] || {{}};
      var base = (sp === d.base_stop && tp === d.base_tp) ? ' hm-base' : '';
      var tip = 'SL ' + sp + '% / TP ' + tp + '% · R ' + (c.r||'') + ' · n=' + (c.n||0) +
                ' · WR ' + (c.win_rate||0) + '% · Sharpe ' + (c.sharpe||0) +
                ' · Sortino ' + (c.sortino||0) + ' · net ' + (c.net_pct||0) + '% · maxDD ' + (c.max_dd||0) + '%';
      h += '<td class="hm-cell' + base + '" data-k="' + sp + '|' + tp + '" title="' + tip + '"></td>';
    }});
    h += '</tr>';
  }});
  h += '</tbody></table>';
  document.getElementById('heatmap').innerHTML = h;
  colorHeatmap();
}}

function colorHeatmap() {{
  var d = window._sweep; if (!d) return;
  var metric = document.getElementById('sweep-metric').value;
  var map = {{}}; d.cells.forEach(function(c) {{ map[c.stop + '|' + c.tp] = c; }});
  var vals = d.cells.filter(function(c) {{ return c.n > 0; }}).map(function(c) {{ return c[metric]; }});
  var maxAbs = Math.max.apply(null, vals.map(function(v) {{ return Math.abs(v); }}).concat([1]));
  var isWR = (metric === 'win_rate');
  document.querySelectorAll('#heatmap .hm-cell').forEach(function(td) {{
    var c = map[td.dataset.k] || {{}};
    if (!c.n) {{ td.style.background = 'var(--s1)'; td.style.color = 'var(--t3)'; td.textContent = '—'; return; }}
    var v = c[metric];
    var t = isWR ? (v - 50) / 50 : v / maxAbs;
    t = Math.max(-1, Math.min(1, t));
    var hue = t >= 0 ? 150 : 5;
    td.style.background = 'hsla(' + hue + ',72%,45%,' + (0.12 + 0.55 * Math.abs(t)) + ')';
    td.style.color = 'var(--t1)';
    td.textContent = (metric === 'net_pct' || metric === 'win_rate') ? Math.round(v) + '%' : ('' + v);
  }});
}}

function metricColor(key, val) {{
  if (key === 'win_rate') return val >= 48 ? 'good' : val >= 31 ? 'warn' : 'bad';
  if (key === 'profit_factor') return val >= 1.5 ? 'good' : val >= 1.0 ? 'warn' : 'bad';
  if (key === 'max_drawdown_pct') return val < 40 ? 'good' : val < 70 ? 'warn' : 'bad';
  if (key === 'sharpe' || key === 'sortino' || key === 'calmar') return val >= 1 ? 'good' : val >= 0 ? 'warn' : 'bad';
  if (key === 'net_pct') return val > 0 ? 'good' : 'bad';
  return '';
}}

function renderResults(d) {{
  document.getElementById('strat-name').textContent = d.strategy;
  document.getElementById('strat-desc').textContent = d.description;

  var m = d.metrics;
  var fields = [
    ['win_rate',          'Win Rate',        m.win_rate + '%',     '≥48% = goal'],
    ['profit_factor',     'Profit Factor',   m.profit_factor,      '≥1.5 target'],
    ['n',                 'Trades',          m.n,                  d.months + 'mo'],
    ['trades_per_week',   'Trades/wk',       m.trades_per_week,    'target 1–5'],
    ['avg_r',             'Avg R',           m.avg_r,              'target ≥3.5'],
    ['sharpe',            'Sharpe',          m.sharpe,             '≥1 = solid'],
    ['sortino',           'Sortino',         m.sortino,            'downside-only'],
    ['calmar',            'Calmar',          m.calmar,             'return ÷ maxDD'],
    ['max_drawdown_pct',  'Max DD',          m.max_drawdown_pct + '%', '<40% safe'],
    ['max_consec_losses', 'Max Consec Loss', m.max_consec_losses,  'risk of ruin'],
    ['avg_hours_held',    'Avg Hold (h)',    m.avg_hours_held,     '≥24h = multi-day'],
    ['net_pct',           'Net Return',      m.net_pct + '%',      d.months + 'mo'],
    ['final_equity',      'Final €',         '€' + m.final_equity.toLocaleString('en', {{maximumFractionDigits:0}}), 'from €' + m.initial_equity],
  ];
  var grid = document.getElementById('metrics-grid');
  grid.innerHTML = fields.map(function(f) {{
    var cls = metricColor(f[0], parseFloat(f[2])) + (String(f[2]).length > 8 ? ' big' : '');
    return '<div class="metric"><div class="lbl">' + f[1] + '</div>' +
           '<div class="val ' + cls + '">' + f[2] + '</div>' +
           '<div style="font-size:9px;color:#465064;margin-top:2px">' + f[3] + '</div></div>';
  }}).join('');

  // Trades
  var tbody = document.getElementById('trade-tbody');
  tbody.innerHTML = d.trades.slice().reverse().map(function(t) {{
    var cls = t.result === 'win' ? 'win' : 'loss';
    return '<tr>' +
      '<td>' + t.entry_ts.slice(0,10) + '</td>' +
      '<td>' + t.exit_ts.slice(0,10)  + '</td>' +
      '<td>' + t.direction + '</td>' +
      '<td style="font-family:monospace">$' + t.entry_px.toLocaleString('en') + '</td>' +
      '<td style="font-family:monospace">$' + t.exit_px.toLocaleString('en') + '</td>' +
      '<td class="' + cls + '">' + t.result + '</td>' +
      '<td class="' + cls + '" style="font-family:monospace">' + (t.pnl_pct >= 0 ? '+' : '') + t.pnl_pct + '%</td>' +
      '<td>' + t.hours_held + 'h</td>' +
      '<td style="font-family:monospace">€' + t.equity.toLocaleString('en', {{maximumFractionDigits:0}}) + '</td>' +
    '</tr>';
  }}).join('');

  document.getElementById('results').style.display = '';
  // Draw the equity curve AFTER results is visible — drawing while display:none
  // gives the canvas offsetWidth 0 → a flat/empty chart (the old visual bug).
  drawChart(d.equity_curve);
}}

function drawChart(curve) {{
  var canvas = document.getElementById('eq-chart');
  var ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth * window.devicePixelRatio || 800;
  canvas.height = 200 * window.devicePixelRatio || 200;
  ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
  var W = canvas.offsetWidth, H = 200;
  ctx.clearRect(0,0,W,H);

  var vals = curve.map(function(p) {{ return p.equity; }});
  var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
  if (mx === mn) return;

  function px(i) {{ return (i / (curve.length-1)) * (W-20) + 10; }}
  function py(v) {{ return H - 20 - ((v - mn) / (mx - mn)) * (H - 40); }}

  // Fill
  ctx.beginPath();
  ctx.moveTo(px(0), py(vals[0]));
  for (var i=1; i<vals.length; i++) ctx.lineTo(px(i), py(vals[i]));
  ctx.lineTo(px(vals.length-1), H-20);
  ctx.lineTo(px(0), H-20);
  ctx.closePath();
  ctx.fillStyle = 'rgba(91,157,255,0.12)';
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.strokeStyle = '#5b9dff'; ctx.lineWidth = 1.5;
  ctx.moveTo(px(0), py(vals[0]));
  for (var i=1; i<vals.length; i++) ctx.lineTo(px(i), py(vals[i]));
  ctx.stroke();

  // Labels
  ctx.fillStyle = '#828ea6'; ctx.font = '10px monospace';
  ctx.fillText('€' + Math.round(mn).toLocaleString('en'), 10, H-8);
  ctx.fillText('€' + Math.round(mx).toLocaleString('en'), 10, 14);
  ctx.fillText(curve[0].date.slice(0,7), 10, H-20);
  ctx.fillText(curve[curve.length-1].date.slice(0,7), W-60, H-20);
}}

// default the starting balance to your live hedge equity (falls back to 637)
(async function() {{
  try {{ var a = await fetch('/api/account/live').then(function(r){{return r.json();}});
    if (a && a.total_eur) document.getElementById('capital').value = Math.round(a.total_eur);
  }} catch(e) {{}}
}})();
"""

    return HTMLResponse(shell("/backtest", "Backtest", body, script=script, head_extra=css, meta="30mo history"))


class BtRunRequest(BaseModel):
    name: str = "PULLBACK_4R_v1"
    months: int = 30
    initial_capital: float = 637.0


@app.post("/api/backtest/run")
def api_backtest_run(req: BtRunRequest):
    if req.name not in BT_STRATEGIES:
        return {"error": f"unknown strategy '{req.name}'. Available: {list(BT_STRATEGIES)}"}
    try:
        result = _run_strategy(req.name, months=req.months, initial_capital=req.initial_capital)
        _bt_cache[req.name] = result
        return result
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}


@app.post("/api/backtest/sweep")
def api_backtest_sweep(req: BtRunRequest):
    if req.name not in BT_STRATEGIES:
        return {"error": f"unknown strategy '{req.name}'. Available: {list(BT_STRATEGIES)}"}
    try:
        from app.backtest_engine import sweep_strategy as _sweep
        return _sweep(req.name, months=req.months, initial_capital=req.initial_capital)
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}


@app.get("/api/backtest/strategies")
def api_backtest_strategies():
    return {
        k: {"description": v["description"], "params": v["params"]}
        for k, v in BT_STRATEGIES.items()
    }


# ─── Trade Review ─────────────────────────────────────────────────────────────

@app.get("/overview", response_class=HTMLResponse)
def overview_page():
    """Prop-book snapshot — eval ledger, performance, market."""
    from .overview_page import render
    return render("prop")


@app.get("/overview-hedge", response_class=HTMLResponse)
def overview_page_hedge():
    """Hedge-book snapshot — live Kraken account, performance, market."""
    from .overview_page import render
    return render("hedge")


@app.get("/position", response_class=HTMLResponse)
def position_page_route():
    """Entry + direction → SL/TP/liq levels and size in ₿/€ (uses /api/position)."""
    from .position_page import position_page
    return position_page()


@app.get("/sitemap", response_class=HTMLResponse)
def sitemap_route():
    """Every HTML page in one map — built live from the route table."""
    from .sitemap_page import render
    skip = {"/health", "/sitemap", "/style", "/openapi.json", "/docs", "/redoc"}
    paths = sorted({
        r.path for r in app.routes
        if "GET" in getattr(r, "methods", set())
        and not r.path.startswith(("/api", "/assets"))
        and "{" not in r.path and r.path not in skip
    })
    return render(paths)


@app.get("/journal", response_class=HTMLResponse)
def journal_page():
    from .journal_page import JOURNAL_HTML
    return JOURNAL_HTML


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page():
    from .analytics_page import ANALYTICS_HTML
    return ANALYTICS_HTML


@app.get("/edge", response_class=HTMLResponse)
def edge_page():
    from .edge_page import EDGE_HTML
    return EDGE_HTML


# /review + /recap deleted — the Journal is the single trade-history surface.


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page():
    from .calendar_page import CALENDAR_HTML
    return CALENDAR_HTML


@app.get("/prop", response_class=HTMLResponse)
def prop_page():
    from .prop_views import goals_page
    return goals_page()


@app.get("/strategy", response_class=HTMLResponse)
def strategy_engine():
    from .prop_views import strategy_page
    return strategy_page("prop")


@app.get("/strategy-hedge", response_class=HTMLResponse)
def strategy_engine_hedge():
    from .prop_views import strategy_page
    return strategy_page("hedge")


@app.get("/risk", response_class=HTMLResponse)
def risk_engine():
    from .prop_views import risk_page
    return risk_page()


@app.get("/survival", response_class=HTMLResponse)
def survival_engine():
    from .prop_views import survival_page
    return survival_page()


@app.get("/rules", response_class=HTMLResponse)
def rules_engine():
    from .prop_views import rules_page
    return rules_page()


@app.get("/equity", response_class=HTMLResponse)
def equity_engine():
    from .prop_views import equity_page
    return equity_page()


@app.get("/regime", response_class=HTMLResponse)
def regime_page():
    """PROP analytic: market regime + hero win-rate per regime."""
    from .regime import regime_payload
    from .regime_page import render
    return render(regime_payload())


@app.get("/api/prop/regime")
def api_prop_regime():
    from .regime import regime_payload
    return regime_payload()


@app.get("/api/prop/configs")
def api_prop_configs():
    """Dropdown metadata for the /prop AUTO mode."""
    from .prop_eval import list_configs
    return list_configs()


@app.get("/api/prop/eval")
def api_prop_eval(strategy: str = "ASIAN_RSI_DIP_v1",
                  eval: str = "BREAKOUT_1STEP_CLASSIC",
                  account: float = 5000.0, risk: float = 2.0,
                  open_equity: bool = True, paths: int = 3000):
    """Live open-equity numbers for one config — the page's source of truth."""
    from .prop_eval import eval_summary
    return eval_summary(strategy, eval, account, risk, paths=paths,
                        open_equity=open_equity)


@app.get("/api/prop/desk")
def api_prop_desk():
    """Live ENTER / STAND DOWN read for the prop hero on the latest closed 4H bar."""
    from .prop_desk import prop_desk_state
    return prop_desk_state()


@app.get("/prop-desk", response_class=HTMLResponse)
def prop_desk_page():
    from .prop_desk import PROP_DESK_HTML
    return PROP_DESK_HTML


@app.get("/api/prop/ledger")
def api_prop_ledger():
    """Realised prop-book trades as an equity ledger vs the eval walls."""
    from .prop_ledger import prop_ledger_data
    return prop_ledger_data()


@app.post("/api/prop/trades")
def api_prop_trade(trade: TradeCreate):
    """Log a trade onto the prop book (forces book='prop'). Blocked once the eval
    is failed — you can't trade a blown book; close/edit existing trades or start a
    new eval. Guard uses the realised (latched) verdict, no live feed needed."""
    from .prop_ledger import prop_ledger_data
    if prop_ledger_data(live=False)["failed"]:
        raise HTTPException(status_code=409,
            detail="This eval is failed — start a new eval to log fresh trades.")
    trade.book = "prop"
    return create_trade(trade)


class PropEvalParams(BaseModel):
    account: float
    risk: float
    eval_name: str


@app.get("/api/prop/config")
def api_prop_config():
    """Active eval params + the available plans (for the new-eval form)."""
    from .prop_views import prop_config
    from .prop_eval import EVALS
    plans = {k: {"daily_loss_pct": v["daily_loss_pct"], "max_dd_pct": v["max_dd_pct"],
                 "profit_target_pct": v["profit_target_pct"], "max_leverage": v["max_leverage"]}
             for k, v in EVALS.items()}
    return {"config": prop_config(), "plans": plans}


@app.post("/api/prop/new-eval")
def api_prop_new_eval(params: PropEvalParams):
    """Start a new eval: archive the current run (book='prop' → dated archive) AND
    save the new account/risk/plan so every prop page resets to it. History kept."""
    from .database import archive_prop_trades, set_prop_eval
    from .prop_views import prop_config
    from .prop_eval import EVALS
    if params.eval_name not in EVALS:
        raise HTTPException(status_code=422, detail=f"unknown plan {params.eval_name}")
    archived = archive_prop_trades(meta=prop_config())   # stamp the run's params before re-tag
    cfg = set_prop_eval(params.account, params.risk, params.eval_name)
    return {"archived": archived, "config": cfg}


@app.get("/api/prop/archives")
def api_prop_archives():
    """Past eval attempts, scored under the params each ran with."""
    from .prop_ledger import archive_summaries
    return {"archives": archive_summaries()}


@app.get("/api/prop/positions/open")
def api_prop_open_positions():
    """Logged OPEN prop-book trades (no exit yet), marked to the live BTC market.
    Breakout's eval account has no readable API, so we mark your logged fill to
    public Kraken price + funding — same card shape as /api/positions/live, but
    USD money (the eval account is USD)."""
    from .database import get_trades
    opens = [t for t in get_trades(limit=5000, book="prop") if t.pnl is None]
    if not opens:
        return {"positions": []}
    mk = {"mark": None, "funding": None}
    try:
        key, secret = kraken_sync.get_api_keys("personal")
        mk = kraken_sync.fetch_market_btc(key, secret)
    except Exception:
        pass
    mark, funding = mk.get("mark"), mk.get("funding")
    out = []
    for t in opens:
        entry = float(t.entry or 0); size = abs(float(t.size or 0))
        if not entry or not size:
            continue
        is_short = (t.direction == "short")
        lev = float(t.leverage or 1.0) or 1.0
        m = float(mark) if mark else entry
        notional = size * m
        cost = size * entry
        margin = notional / lev if lev else notional
        upnl = (m - entry) * size * (-1 if is_short else 1)
        upnl_pct = (upnl / cost * 100) if cost else None
        roe = (upnl / margin * 100) if margin else None
        move_pct = ((m - entry) / entry * 100) * (-1 if is_short else 1)
        # ponytail: liq estimate off the logged leverage (entry ± 1/lev), not the
        # eval's true wallet margin — same approximation the live card uses.
        liq = entry * (1 + 1 / lev) if is_short else entry * (1 - 1 / lev)
        out.append({
            "id": t.id, "venue": "Kraken Prop (Breakout)", "symbol": "BTC/USD:USD",
            "direction": "short" if is_short else "long", "leverage": round(lev, 2),
            "entry": round(entry, 2), "mark": round(m, 2), "move_pct": round(move_pct, 3),
            "size": round(size, 6), "quote_qty": round(notional, 2), "cost_usd": round(cost, 2),
            "margin_usd": round(margin, 2), "upnl_usd": round(upnl, 2),
            "upnl_pct": round(upnl_pct, 2) if upnl_pct is not None else None,
            "roe_pct": round(roe, 2) if roe is not None else None,
            "liquidation": round(liq, 2),
            "funding": round(funding, 6) if funding is not None else None,
            "live": mark is not None,
        })
    return {"positions": out}


@app.get("/api/prop/signals")
def api_prop_signals(limit: int = Query(300, ge=1, le=2000)):
    """Prop hero signals (ASIAN_RSI_DIP_v1), each with the prop-legal ticket."""
    from .prop_scan import PROP_STRATEGY, prop_ticket
    sigs = get_signals(strategy=PROP_STRATEGY, limit=limit)
    for sg in sigs:
        try:
            if sg.get("entry_price") and sg.get("stop_price") and sg.get("target_price"):
                sg["ticket"] = prop_ticket(
                    sg["entry_price"], sg["stop_price"], sg["target_price"],
                    sg["direction"] == "long")
        except Exception:
            pass
    return {"signals": sigs}


@app.get("/prop-signals", response_class=HTMLResponse)
def prop_signals_page():
    from .prop_signals_page import render
    return render()


@app.get("/prop-ledger", response_class=HTMLResponse)
def prop_ledger_page():
    from .prop_ledger import ledger_page
    return ledger_page()


@app.get("/prop-income", response_class=HTMLResponse)
def prop_income_page():
    from .prop_income import income_page
    return income_page()


@app.get("/api/review/trades")
def api_review_trades():
    return get_enriched_trades()


@app.get("/api/review/analytics")
def api_review_analytics():
    from .review import review_analytics
    return review_analytics()


@app.get("/api/review/ohlcv")
def api_review_ohlcv():
    return get_ohlcv_1h()


@app.get("/api/stats/trades")
def api_stats_trades():
    """Realized stats from closed trades — feeds Monte Carlo + projection seeding."""
    return get_actual_stats()


# ─── LENS_EDGE_v3 setup engine (see strategies/LENS_EDGE_v3_ICT/FINDINGS.md) ──

@app.get("/desk", response_class=HTMLResponse)
def desk_page():
    from .desk import DESK_HTML
    return DESK_HTML


@app.get("/assets/lens.css")
def lens_css():
    """Shared design-system stylesheet — single source of truth for every page."""
    from fastapi.responses import Response
    from .theme import LENS_CSS
    return Response(LENS_CSS, media_type="text/css",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/assets/favicon.svg")
def favicon_svg():
    """Brand mark (scope/aperture iris) — see app/theme.py FAVICON_SVG."""
    from fastapi.responses import Response
    from .theme import FAVICON_SVG
    return Response(FAVICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/style", response_class=HTMLResponse)
def style_guide_page():
    from .style_guide import STYLE_HTML
    return STYLE_HTML


@app.get("/api/setups/state")
def api_setups_state(refresh: bool = Query(True, description="fetch fresh candles first")):
    """Live desk state: per-direction verdicts, checklists, vetoes, scoreboard."""
    from . import setups
    return setups.desk_state(refresh=refresh)


@app.post("/api/setups/scan")
def api_setups_scan(emit: bool = Query(True, description="insert pending signals for clean matches")):
    """Evaluate the latest closed 1h bar against S1–S5 + vetoes.

    Clean matches (setup hit, zero vetoes) become pending signals in the
    normal /signals approve/reject flow. Also re-tags any untagged synced
    trades so the scoreboard stays current.
    """
    from . import setups
    scan = setups.scan_latest()
    scan["signals_emitted"] = setups.emit_signals(scan) if emit else []
    scan["tag_backfill"] = setups.backfill_setup_tags(only_untagged=True)
    return scan


@app.post("/api/setups/backfill-tags")
def api_setups_backfill(all: bool = Query(False, description="re-tag every trade, not just untagged")):
    """Classify entry context of closed trades → trades.setup_tag."""
    from . import setups
    return setups.backfill_setup_tags(only_untagged=not all)


@app.get("/api/stats/setups")
def api_stats_setups():
    """Realized WR / expectancy per setup tag, halves split for drift."""
    from . import setups
    return setups.setup_scoreboard()
