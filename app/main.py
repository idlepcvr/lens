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

import re
import threading
import time
from datetime import date, datetime
from functools import lru_cache
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .paths import RESULTS
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
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
from .goal_hero import HERO_CSS, HERO_HTML, HERO_JS
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
    _warm_caches()


def _warm_caches():
    """Replay the basket's trade logs once, in the background, at boot.

    The prop pages are pure functions of a frozen backtest, so they're memoised
    (_TL_CACHE) — but *someone* has to pay for the first replay, and until this
    existed that someone was whoever clicked Plan first after a deploy: 7s of
    staring at a dead nav. Now the cache is warm before the landing page is.

    Daemon thread: a failure here must never stop the app booting, and a slow
    warm must never delay it — the pages still compute on demand if this loses
    the race. ponytail: no scheduler, no lock. Worst case is a duplicate replay.
    """
    def warm():
        try:
            from .prop_goal import cone
            cone()
        except Exception as e:                       # a cold cache is not fatal
            print(f"[warm] skipped: {e}")
    threading.Thread(target=warm, daemon=True, name="warm-caches").start()


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
    """The front door: what this is, in plain English, for someone who has never
    traded anything. No numbers, no jargon, nothing for sale."""
    from .explain_page import render
    return render()


@app.get("/hedge-plan", response_class=HTMLResponse)
def landing():
    # Scoped to the hedge book. This counted EVERY book, so its trade count was
    # hedge + every prop attempt, and prop signals landed in the hedge queue —
    # against the front door's own "two machines, they never mix".
    trades  = get_trades(limit=5000, book="hedge")
    sigs    = [s for s in get_signals(limit=5000)
               if not str(s.get("signal_id", "")).startswith("prop-")]
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
.sc{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:13px 16px;display:block;text-decoration:none;transition:border-color .12s}
.sc:hover{border-color:var(--ac)}
.sc.pend{border-color:var(--am)}
.sc.pend .sc-n{color:var(--am)}
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
/* hero + status line come from goal_hero.HERO_CSS (shared with /goal), appended below */
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
""" + HERO_CSS + r"""</style>"""

    body = f"""
<div class="strip">
  <a class="sc" href="/hedge-journal"><div class="sc-n">{len(trades)}</div><div class="sc-l">Trades → journal</div></a>
  <a class="sc" href="/hedge-signals"><div class="sc-n">{len(sigs)}</div><div class="sc-l">Signals → queue</div></a>
  <a class="sc {'pend' if pending else ''}" href="/hedge-desk"><div class="sc-n">{len(pending)}</div><div class="sc-l">Pending → desk</div></a>
</div>

<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this dashboard</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what this page is</h4>A <b>live goal-and-risk calculator</b>, not a trade log. Type your account + strategy assumptions into <b>Parameters</b> (left) and every metric recomputes instantly. It answers: <b>given these numbers, do I reach the target — and what's the risk of blowing up before I get there?</b>
<h4>the only inputs are the parameters</h4>Start €, target €, target date, win rate, R:R, leverage, trades/week, drawdown limits. Every field is a calculator — type <code>300*0.1</code> and hit <b>↵</b> to get <code>30</code>. <b>Apply</b> saves them as your defaults; <b>Reload</b> pulls the last saved set.
<h4>the four hero cards</h4>Each answers one goal question and passes or fails: <b>On time?</b> = does your edge reach the target inside the window (projected arrival vs deadline). <b>Edge / trade</b> = is per-trade EV at least what the goal needs (green only when it clears the bar). <b class="r">Risk of ruin</b> = odds of hitting the drawdown wall before the goal. <b>Risk sizing</b> = used risk vs the Kelly/DD optimal. Detail (Actual R, geometric drift) is in the cards below.
<h4>the metric cards</h4>Break the model down: time-to-goal, required growth rates, the per-trade EV model, Kelly sizing, account impact per win/loss, risk analytics (Sharpe, profit factor, ruin), €-growth projections, and a BTC / Monte-Carlo band (P05 / P50 / P95 outcomes).
<h4>read-only math</h4>LENS computes — it does not trade. Pair this with <a href="/hedge-desk">Desk</a> (can I enter now?) and <a href="/hedge-goal">Goal</a> (equity curve + projection over time).
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
          <div style="margin-top:7px">
            <button type="button" class="btn" id="validated-btn" disabled title="the /short system — the only cell that survived every gate">Use validated</button>
          </div>
          <div class="calc-tip" id="validated-note" style="margin-top:5px">—</div>
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
{HERO_HTML}

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
// ── "Use validated": the /short system — the surviving cell, not the whole book.
// Same source as /goal so Plan and Goal can never disagree about what the edge is.
let VAL=null;
async function loadValidated(){{
  try{{ VAL=await fetch("/api/goal/validated").then(r=>r.json()); }}catch(e){{ return; }}
  const btn=document.getElementById("validated-btn"), note=document.getElementById("validated-note");
  if(!btn||!note) return;
  if(!VAL||!VAL.n){{ note.textContent="no validated cell — run research/short_edge.py"; return; }}
  btn.disabled=!VAL.enough;
  note.innerHTML="<b>"+VAL.cell+"</b> @ R:R "+VAL.rr_ratio+" · n="+VAL.n+" · WR "
    +(VAL.win_rate*100).toFixed(1)+"% vs "+(VAL.matched_random*100).toFixed(1)+"% random ("
    +(VAL.edge_pp>0?"+":"")+VAL.edge_pp+"pp) · stop "+VAL.stop_pct.toFixed(2)+"% / target "
    +VAL.target_pct.toFixed(2)+"% · ~"+VAL.median_hold_h+"h hold"
    +"<br><span style='color:var(--amber)'>⚠ fires "+VAL.trades_per_week
    +"/wk — the target needs ~7. This sets cadence to what you generate, not what you need.</span>";
}}
document.addEventListener("DOMContentLoaded",function(){{
  const b=document.getElementById("validated-btn");
  if(b) b.addEventListener("click",function(){{
    if(!VAL||!VAL.enough) return;
    FORM.elements.win_rate.value=VAL.win_rate;
    FORM.elements.rr_ratio.value=VAL.rr_ratio;
    FORM.elements.trades_per_week.value=VAL.trades_per_week;
    recompute();
  }});
  loadValidated();
}});
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

  renderPillars(g);   // four-pillar hero + status line (shared with /goal, goal_hero.py)

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
""" + HERO_JS

    return shell("/hedge-plan", "Plan", body, script=script, head_extra=css, meta="goal model")


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
def api_prop_position(entry: float, direction: str = "long",
                      risk: Optional[float] = Query(None, gt=0, le=10, description="risk %/trade override"),
                      rr: Optional[float] = Query(None, gt=0, le=20, description="target R override (rescales TP)"),
                      lev: Optional[float] = Query(None, gt=0, le=10, description="leverage to trade at"),
                      stop: Optional[float] = Query(None, gt=0, le=20, description="stop distance % override — the only lever on travel distance"),
                      balance: Optional[float] = Query(None, gt=0, description="eval balance $ override")):
    """Prop-rule sizing for a manual entry: risk RISK% of the eval ÷ stop.

    `stop` is the dial on TRAVEL DISTANCE. Risk is fixed, so notional = risk$ /
    stop% — halve the stop and the position doubles, which halves the price move
    needed for the same $. The target moves with it (the strategy's R is held
    unless `rr` says otherwise), and the tighter stop demands more leverage:
    min_leverage = risk% / stop%, so the firm's 5x cap floors the stop at
    risk%/5. Past that the size is cut and `actual_risk_pct` drops below plan.
    `lev` is only the leverage you'll set on the venue — it moves margin and the
    liq price, never the risk, the size or the levels (see prop_ticket).

    Stop/target otherwise come from the prop hero strategy's measured average
    move, then run through prop_ticket (same math as the signal ticket and the
    eval ledger). Every override is per-trade — the saved plan is untouched."""
    from .prop_scan import prop_ticket
    from .prop_ledger import prop_ledger_data
    from .prop_views import prop_config
    win_pct, loss_pct, wr = _prop_moves()
    if not loss_pct:
        raise HTTPException(status_code=422, detail="prop strategy stats unavailable")
    r_target = rr or (win_pct / loss_pct)   # hold the strategy's own R unless overridden
    if stop:
        loss_pct = stop                     # tighter stop → bigger size → shorter travel
    if rr or stop:
        win_pct = loss_pct * r_target
    # size off the CURRENT eval equity (realized ledger), not the nominal start
    nominal = prop_config()["account"]
    equity = balance or prop_ledger_data().get("equity") or nominal
    long_ = direction == "long"
    stop   = entry * (1 - loss_pct / 100) if long_ else entry * (1 + loss_pct / 100)
    target = entry * (1 + win_pct / 100)  if long_ else entry * (1 - win_pct / 100)
    t = prop_ticket(entry, stop, target, long_, account=equity, risk=risk, lev=lev)
    t.update(entry=entry, stop=round(stop, 1), target=round(target, 1),
             win_rate_pct=round(wr, 1), direction=direction,
             account_nominal=nominal)
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
    book:      Optional[str] = Query(None, description="'hedge', 'prop' (live eval) or 'prop*' (all attempts)"),
):
    trades = get_trades(limit=limit, offset=offset, venue=venue,
                        direction=direction, result=result, period=period, book=book)
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
        # Keep the equity curve fed: one snapshot per day from the balance
        # timeline (was defined but never called — daily_snapshots sat empty,
        # so projections/actuals had nothing to read).
        try:
            result["snapshots_backfilled"] = _timeline_to_daily_snapshots(result.get("eur_timeline") or [])
        except Exception:
            pass
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


# (The old /api/sync/kraken/backfill-balances repair endpoint is gone: the sync
# now refreshes existing rows from exchange truth on every run, and the derived
# before=after−pnl it used would clobber the timeline-sampled balances.)


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


class ExecuteRequest(BaseModel):
    direction: str                        # "long" | "short"
    size_btc: float
    confirm: bool = False                 # nothing is sent without this
    order_type: str = "mkt"               # mkt | lmt | post
    limit_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    mark: Optional[float] = None          # reference price when there's no limit
    reduce_only: bool = False
    post_only: bool = False
    trigger_signal: str = "mark"          # mark | index | last
    leverage: float = 10.0
    signal_id: Optional[str] = None
    override_reason: Optional[str] = None
    account: str = "personal"

    def ticket(self) -> dict:
        return {"order_type": self.order_type, "limit_price": self.limit_price,
                "take_profit": self.take_profit, "stop_loss": self.stop_loss,
                "mark": self.mark, "reduce_only": self.reduce_only,
                "post_only": self.post_only, "trigger_signal": self.trigger_signal,
                "leverage": self.leverage, "signal_id": self.signal_id,
                "override_reason": self.override_reason}


@app.post("/api/execute/check")
def api_execute_check(req: ExecuteRequest):
    """Every gate evaluated plus the exact batch that would be sent. Sends nothing."""
    from .execute import check
    return check(req.direction, req.size_btc, **req.ticket())


@app.post("/api/execute")
def api_execute(req: ExecuteRequest):
    """Place the ticket: entry, plus TP/SL as reduce-only triggers when given."""
    from .execute import execute as do
    return do(req.direction, req.size_btc, confirm=req.confirm,
              account=req.account, **req.ticket())


@app.post("/api/execute/close")
def api_execute_close(req: ExecuteRequest):
    """Close or trim an open position — opposite side, reduce-only, market.
    `direction` is the direction of the POSITION, not of the order."""
    from .execute import close
    return close(req.direction, req.size_btc, confirm=req.confirm,
                 account=req.account, mark=req.mark, leverage=req.leverage)


@app.post("/api/execute/cancel-all")
def api_execute_cancel_all(account: str = "personal"):
    """Pull every resting order — for orphaned TP/SL legs after a manual close."""
    from .execute import cancel_all
    return cancel_all(account)


@app.post("/api/signals/link")
def api_signal_link():
    """Backfill linked_signal_id on unlinked fills. Idempotent.
    Sync links each fill as it lands (database._link_signal); this is the repair
    path for rows that predate that, or that arrived while a signal was pending."""
    from .database import backfill_signal_links
    return {"linked": backfill_signal_links()}


@app.get("/hedge-goal", response_class=HTMLResponse)
def goal_page():
    from .goal_page import render
    return render()


@app.get("/hedge-track", response_class=HTMLResponse)
def track_page():
    from .track_page import render
    return render()


@app.get("/api/track")
def api_track(days: int = 30):
    from .track import track
    return track(days=max(7, min(days, 120)))


@app.get("/api/research/{name}.json")
def api_research_json(name: str):
    """Raw results/<name>.json — the evidence file behind a /research card."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise HTTPException(404)
    fp = RESULTS / f"{name}.json"
    if not fp.exists():
        raise HTTPException(404)
    return FileResponse(fp, media_type="application/json")


@app.get("/evidence", response_class=HTMLResponse)
def evidence_page():
    """What has actually been tested, and what survived.

    Was three routes — /short, /robustness, /research — which is one argument
    split into three pages with no stated relationship, so none of them said
    what it was for. Ordered here as the argument actually runs: the claim
    that survived, then the test that it isn't luck, then every experiment
    including the ones that failed.
    """
    from .research_page import parts as notebook
    from .robustness_page import parts as luck
    from .short_page import parts as verdict
    from .theme import merged
    from .tldr import opener
    intro = opener(
        "What this page is",
        "Every trading idea you've had was tested against the price history to "
        "see whether it makes money for a real reason, or only made money by "
        "coincidence in the sample it was found in. Twelve ideas were tested. "
        "One survived. That is all the word “evidence” means here.",
        ["<b>The verdict</b> — the one idea that still made money when tested on "
         "data it had never seen, and beat a coin-flip entry in the same market. "
         "Everything else died.",
         "<b>Is it luck?</b> — the same trades, shuffled into random order a few "
         "thousand times, to measure how often pure chance produces a result this "
         "good. Low number = the pattern is probably real.",
         "<b>The notebook</b> — every test ever run, including the failures. The "
         "failures are the point: they are why the verdict is only one line long."],
        "whether that one surviving edge is <b>big enough</b>. It is real, and it "
        "is still far too small — the scoreboard above is the answer to that, and "
        "nothing on this page changes it.")
    return merged("/evidence", "Evidence", [
        {"id": "verdict", "label": "The verdict · what survived", **verdict()},
        {"id": "luck", "label": "Is it luck? · permutation test", **luck()},
        {"id": "notebook", "label": "The notebook · every experiment", **notebook()},
    ], meta="what survived testing", intro=intro)


class ReviewVerdict(BaseModel):
    month:   str
    combo:   str
    verdict: str
    reason:  str


@app.get("/review", response_class=HTMLResponse)
def review_route(month: Optional[str] = None):
    """NEXT_SESSION.md #1: the month's trades grouped by setup_tag, computed
    live, plus a place to record a keep/tune/retire verdict on a veto combo."""
    from .review_page import render
    return render(month)


@app.post("/api/review/verdict")
def api_review_verdict(req: ReviewVerdict):
    from . import review_page
    try:
        review_page.record_verdict(req.month, req.combo, req.verdict, req.reason)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@app.post("/api/review/notify")
def api_review_notify():
    """Cron hits this on the 1st — ntfy for last month, same topic as everything else."""
    from . import review_page
    return {"sent": review_page.notify_monthly()}


@app.get("/philosophy", response_class=HTMLResponse)
def philosophy_page():
    """The public site's third page — worldview and the model he was wrong about.
    Split from /about so that page stays short enough to read in one sitting."""
    from .philosophy_page import render
    return render()


@app.get("/about", response_class=HTMLResponse)
def about_page():
    """The page for a reader who can judge the work — a friend, not a partner.

    "/" is for someone who already cares about him and wants to know he's okay.
    /evidence is the argument. This is the introduction: what this is, where it
    sits in his wider thesis, and what has failed. Deliberately keeps the
    glossary/robustness/short/target routes DEAD — they were consolidated on
    2026-08-03 and resurrecting them here would undo that on merge.
    """
    from .about_page import render
    return render()


@app.get("/geometry", response_class=HTMLResponse)
def geometry_page():
    """One calculation, both directions. /geometry derived what a configuration
    earns; /target inverted it — name a weekly return, see the edge it demands.
    target_page.py said so in its own docstring, so they merged 2026-08-03."""
    from .geometry_page import parts as geo
    from .target_page import parts as tgt
    from .theme import merged
    from .tldr import opener
    intro = opener(
        "What this page is",
        "Where the stop-loss and the take-profit go, and what that choice earns. "
        "Put the stop too close and normal noise knocks you out; too far and one "
        "loss costs more than several wins. This page picks the distance from how "
        "much Bitcoin actually moves in a day, rather than from a round number.",
        ["<b>What this configuration earns</b> — given the stop and target you're "
         "using now, the win rate you'd need and the return it produces.",
         "<b>What a named target demands</b> — the same maths backwards: name a "
         "weekly return, and see the win rate it would take to get there. This is "
         "where a target stops being a wish.",
         "The honest bit: each requirement is priced against a <b>random entry</b>, "
         "not against zero. Beating a coin flip is the real bar, and it is higher "
         "than it looks."],
        "whether the target is reachable. Naming 10%/week does not make it "
        "available — the win rate the table demands for it is the price, and the "
        "scoreboard above is what you're actually achieving.")
    return merged("/geometry", "Geometry", [
        {"id": "geometry", "label": "What this configuration earns", **geo()},
        {"id": "target", "label": "What a named target demands", **tgt()},
    ], meta="where the stop comes from", intro=intro)


@app.get("/audit", response_class=HTMLResponse)
def audit_page():
    """Plain-English home for the 2026-07-02 strategy-audit recommendations,
    compared LIVE against the current goal config. The 'where do I see this'
    page — recommendations were previously only in code comments and git.

    2026-08-01: the geometry rows are SUPERSEDED by /geometry, which derives the
    stop and target from live σ instead of fitting them to past winners. The
    goal-model rows below still stand — they were always about the config being
    consistent with the alerts, and that question survives the geometry change.
    """
    from . import geometry as G
    from .geometry_page import HOLD_DAYS, RR, WIN_RATE, _sigma
    from .setups import SL_PCT, TP_PCT
    from .theme import shell
    cfg = get_lens_config()
    rr_live = round(TP_PCT / SL_PCT, 2)
    rr_cfg = cfg.get("rr_ratio")
    wr_cfg = cfg.get("win_rate")
    sigma, _ = _sigma()
    derived = G.config(sigma, HOLD_DAYS, RR, WIN_RATE)
    rows = []

    def row(ok, what, current, rec, why):
        badge = ('<span style="color:var(--long)">✓</span>' if ok
                 else '<span style="color:var(--short)">✗ fix</span>')
        rows.append(f"<tr><td>{badge}</td><td>{what}</td><td class='m'>{current}</td>"
                    f"<td class='m'>{rec}</td><td class='why'>{why}</td></tr>")

    row(abs(SL_PCT - derived["stop_pct"]) / derived["stop_pct"] <= 0.15,
        "Alert stop", f"{SL_PCT}%", f"{derived['stop_pct']:.2f}%",
        "Superseded. The old 0.63% came from the MAE of winning trades — a sample "
        "picked by the outcome it was supposed to predict — and implied a ~5 hour "
        "hold, over which the 0.30% round trip was half the stop. The figure on the "
        "right is σ·√(hold/R:R) at live volatility. See /geometry.")
    row(abs(TP_PCT - derived["target_pct"]) / derived["target_pct"] <= 0.15,
        "Alert target", f"{TP_PCT}%", f"{derived['target_pct']:.2f}%",
        "Superseded. The old 1.5% was the median MFE of winners, which is a "
        "description of the past, not a target that clears friction. The new one "
        f"is the stop × R:R {RR:g}, giving a {derived['breakeven_wr']:.1%} breakeven "
        f"win rate against a {derived['coinflip_wr']:.0%} coin flip.")
    row(rr_cfg is not None and abs(rr_cfg - rr_live) < 0.2,
        "Goal-model R:R (Dashboard → Parameters)", f"{rr_cfg}", f"{rr_live}",
        f"Your projections on /goal and /dashboard are computed with this payoff. "
        f"The alerts actually deliver {rr_live}R gross (~1.3R net of fees) — set it "
        f"to {rr_live} so the projections stop assuming a payoff you never take.")
    row(wr_cfg is not None and derived["breakeven_wr"] <= wr_cfg <= 0.32,
        "Goal-model win rate", f"{wr_cfg}",
        f"{derived['breakeven_wr']:.2f}–0.30",
        f"Must be read against the payoff. At R:R {RR:g} the coin-flip win rate is "
        f"{derived['coinflip_wr']:.0%} and breakeven is {derived['breakeven_wr']:.1%}, so "
        f"{wr_cfg} is not conservative here — paired with a 4R payoff it implies an "
        "enormous edge and the projections inherit it. The old 0.44–0.50 range belonged "
        "to the 2.4R geometry and does not transfer.")
    row(False, "Leverage reality", "10x all-in", f"{derived['leverage']:.2f}×",
        "Superseded, and the old framing was backwards. Leverage multiplies the win "
        "and the loss by the same factor, so it cannot make a negative system "
        "positive — it sets the size of the P&L, never its sign. It is a drawdown "
        f"dial: {derived['leverage']:.2f}× is what caps a 15-loss streak at 25% of "
        f"the account at a {derived['risk_pct']:.2f}% risk budget. At 10× the toll "
        "was multiplied by ten alongside everything else.")
    row(False, "Goal target €" + format(int(cfg.get("target_balance") or 0), ","),
        "€52,950 by Oct", "keep as north star, don't trust the ETA",
        "At honest numbers (44–50% WR, ~1.3R net, 2 trades/wk from your balance) the "
        "math lands near €1,200–1,500 by October — the dashboard only connects to "
        "€53k through the old 3R assumption. The goal is yours; the timeline isn't data.")

    body = (
        '<div class="card" style="background:var(--panel);border:1px solid var(--amber);'
        'border-radius:10px;padding:16px 18px;margin:14px 0">'
        '<b>Superseded 2026-08-01 by <a href="/geometry" style="color:var(--accent)">'
        "/geometry</a>.</b> This audit set the stop and target from the MAE/MFE of "
        "<i>winning</i> trades — fitted to a sample selected by the outcome it was "
        "meant to predict, and never asking how long the resulting trade takes to "
        "resolve. setups.py already records that the S1–S5 edge those numbers were "
        "built on did not survive out of sample. The geometry rows below are kept so "
        "the change is legible, not because they are still the recommendation.</div>"
        '<div class="card" style="background:var(--panel);border:1px solid var(--line);'
        'border-radius:10px;padding:16px 18px;margin:14px 0">'
        "<b>What changed 2026-07-02:</b> every scanner alert now carries the validated "
        "geometry below, and clean S1–S5 playbook matches alert again (previously only "
        "the mechanical board top-3 could page you — a clean S3, your best realized "
        "earner, could never send a notification. That was the desk-says-ENTER-but-"
        "phone-stays-silent bug.)</div>"
        "<table><tr><th></th><th>Setting</th><th>Current</th><th>Recommended</th>"
        "<th>Why (plain English)</th></tr>" + "".join(rows) + "</table>"
        '<p style="margin-top:18px"><a href="/geometry" style="color:var(--accent)">'
        "→ Where the geometry now comes from</a> · "
        '<a href="/audit#report" style="color:var(--accent)">'
        "→ Full audit report (visual, historical)</a> · "
        '<a href="/strategy" style="color:var(--accent)">→ live strategy re-ranks (H12/H13 watch)</a></p>'
    )
    css = ("<style>table{border-collapse:collapse;width:100%;font-size:13.5px}"
           "th{text-align:left;color:var(--faint);font-family:var(--mono);font-size:10.5px;"
           "text-transform:uppercase;letter-spacing:.12em;padding:7px 9px;border-bottom:1px solid var(--line)}"
           "td{padding:9px;border-bottom:1px solid var(--line);vertical-align:top}"
           "td.m{font-family:var(--mono);font-size:12.5px;white-space:nowrap}"
           "td.why{color:var(--dim);font-size:12.5px;line-height:1.55}</style>")
    from .theme import merged
    # The original report is a standalone document with its own :root and body
    # rules — inlining it would overwrite the cockpit's. An iframe keeps the
    # July artifact exactly as written and costs one line.
    report = (
        '<div style="max-width:1000px;margin:0 auto;padding:0 14px">'
        '<p style="color:var(--dim);font-size:13px;margin:0 0 10px">'
        'The original 2026-07-02 report, unedited. Its geometry findings are '
        'superseded by <a href="/geometry" class="ac">/geometry</a>; it is kept '
        'as the record of what was believed at the time. '
        '<a href="/audit-report-raw" class="ac" target="_blank">open standalone →</a></p>'
        '<iframe src="/audit-report-raw" title="Strategy Audit 2026-07-02" '
        'style="width:100%;height:78vh;border:1px solid var(--line);'
        'border-radius:10px;background:var(--bg)"></iframe></div>'
    )
    from .tldr import opener
    intro = opener(
        "What this page is",
        "On 2 July 2026 the strategy was reviewed end to end and a list of changes "
        "was written down. This page is that list, checked automatically against "
        "what the system is set to today — so you can see which recommendations "
        "were actually applied and which were quietly ignored. It is a to-do list "
        "with a memory, not an analysis.",
        ["<b>Recommendations vs live config</b> — each July recommendation beside "
         "the value in use right now, so a drift between what was decided and what "
         "is running shows up as a mismatched row.",
         "<b>The original report</b> — the July document itself, unedited, kept as "
         "the record of what was believed at the time.",
         "Its stop-and-target findings are <b>out of date on purpose</b>: they were "
         "fitted to past winning trades, which is circular. "
         "<a href='/geometry' class='ac'>Geometry</a> replaced that method."],
        "anything about today. It is a snapshot from July. If a row disagrees with "
        "the live config, the live config is not automatically wrong — the July "
        "recommendation may be the stale one.")
    return merged("/audit", "Audit", [
        {"id": "recommendations", "label": "Recommendations vs live config",
         "body": body, "css": css},
        {"id": "report", "label": "The original report · 2026-07-02",
         "body": report},
    ], meta="what to change and why", intro=intro)


@app.get("/audit-report-raw", include_in_schema=False)
def audit_report_raw():
    """The frozen July report, served as its own document so /audit#report can
    frame it. Not in the sitemap — it is a section, not a page."""
    import os
    from fastapi.responses import FileResponse
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "strategies", "_research", "STRATEGY_AUDIT_20260702.html")
    return FileResponse(path, media_type="text/html")


# ─── Goal ladder: locked plan + amendment log + stack snapshots ──────────────

class PlanAmend(BaseModel):
    reason:            str
    north_star_btc:    Optional[float] = None
    north_star_date:   Optional[str] = None
    goal_btc:          Optional[float] = None
    goal_date:         Optional[str] = None
    milestones:        Optional[list] = None
    price_scenarios:   Optional[dict] = None
    burn_monthly_eur:  Optional[float] = None


class StackSnapshot(BaseModel):
    date:       str
    btc_total:  float
    note:       Optional[str] = None


@app.get("/api/plan")
def api_plan():
    from . import plan
    return plan.ladder()


@app.post("/api/plan/amend")
def api_plan_amend(req: PlanAmend):
    from . import plan
    changes = {k: v for k, v in req.model_dump(exclude={"reason"}).items() if v is not None}
    try:
        plan.amend(changes, req.reason)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return plan.ladder()


@app.post("/api/stack")
def api_stack_snapshot(req: StackSnapshot):
    from . import plan
    plan.add_snapshot(req.date, req.btc_total, req.note)
    return plan.ladder()


@app.get("/api/goal/measured")
def api_goal_measured(days: Optional[int] = Query(None, description="window; omit = all time"),
                      book: Optional[str] = Query(None, description="prop = all eval attempts")):
    from . import plan
    return plan.measured(days, book=book)


@app.get("/api/goal/validated")
def api_goal_validated():
    """The /short system's params — the surviving cell, not the whole book."""
    from . import plan
    return plan.validated()


@app.get("/api/goal/geometry")
def api_goal_geometry():
    """Your entries replayed across a (stop × R:R × hold) grid — the win rate at
    geometries you have never traded. research/entry_geometry.py generates it."""
    from . import plan
    return plan.geometry()


@app.get("/api/goal/hero")
def api_goal_hero():
    """C6 — stage, next rung, progress, the C3 status word, and coverage."""
    from . import plan
    return plan.hero()


@app.get("/api/goal/stack")
def api_goal_stack():
    """Stack projection: when 5 BTC and 50 BTC land, measured vs plan, under the
    plan's three price scenarios."""
    from . import stack_proj
    return stack_proj.payload()


@app.get("/api/cone")
def api_cone():
    """Projection cone on cumulative realized P&L + the status word (C3)."""
    from . import cone
    return cone.cone()


@app.get("/api/cone/status")
def api_cone_status():
    """Just the status word and the numbers behind it — for the pages that quote it."""
    from . import cone
    return cone.status()


@app.get("/api/excursion")
def api_excursion():
    """MAE/MFE summary — is a low realized R an exit problem or a selection problem?"""
    from . import excursion
    return excursion.summary()


def _seed_prop_goal_config() -> dict:
    """First-run defaults for the prop goal config (lens_config row 2): the live
    eval's walls + the active basket's backtest geometry. After seeding it's a
    normal editable config — Apply/Reload on /prop-goal work exactly like hedge."""
    import datetime as _dt
    from .prop_views import prop_config
    from .prop_eval import EVALS
    pc = prop_config()
    rule = EVALS[pc["eval_name"]]
    acct, risk = pc["account"], pc["risk"]
    seed = {
        "start_balance": acct,
        "target_balance": round(acct * (1 + rule["profit_target_pct"] / 100), 2),
        "target_date": (_dt.date.today() + _dt.timedelta(days=45)).isoformat(),
        "max_drawdown_allowed": rule["max_dd_pct"] / 100.0,
        "losses_allowed": max(1, int((rule["max_dd_pct"] / 100.0) / (risk / 100.0))),
        "leverage": rule["max_leverage"],
        "fractional_kelly": 0.25, "execution_fill_factor": 1.0, "slippage_pct": 0.0,
        "btc_growth_monthly": 0.0,
        "win_rate": 0.5, "rr_ratio": 3.0, "trades_per_week": 2.0,   # overwritten below when geometry exists
    }
    try:
        from .prop_goal import _basket_geometry
        geo = _basket_geometry()
        if geo:
            seed["win_rate"] = round(geo["win_rate"], 4)
            seed["rr_ratio"] = round(geo["rr"], 2)
            seed["trades_per_week"] = round(geo["trades_per_month"] / 4.345, 2)
    except Exception:
        pass
    return upsert_lens_config(seed, row_id=2)


@app.get("/api/config")
def get_config(book: str = "hedge"):
    if book == "prop":
        return get_lens_config(2) or _seed_prop_goal_config()
    return get_lens_config()


@app.patch("/api/config")
def patch_config(data: ConfigUpdate, book: str = "hedge"):
    row_id = 2 if book == "prop" else 1
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        return get_lens_config(row_id)
    return upsert_lens_config(updates, row_id=row_id)


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


@lru_cache(maxsize=4)
def _eur_usd_hourly(hour_bucket: int) -> float:
    # ponytail: hour-bucketed lru_cache = one FX HTTP call per hour, built-in 1.10 fallback
    from .bybit_sync import _get_eur_usdt
    return _get_eur_usdt()


@app.get("/api/volatility")
def api_volatility(mult: float = 0.5):
    """Live BTC ATR(14d) + the noise floor a stop must clear (ATR × mult).
    Feeds the dashboard's ATR auto-floor toggle. btc_eur feeds the goal pages'
    auto BTC-price fill."""
    from .volatility import fetch_volatility
    v = fetch_volatility(noise_mult=mult)
    if v.get("btc_usd"):
        v["btc_eur"] = round(v["btc_usd"] / _eur_usd_hourly(int(time.time() // 3600)), 2)
    return v


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


@app.get("/api/orders/live")
def orders_live():
    """Resting orders on the exchange — what is actually working, as opposed to
    what the model planned. Read-only.

    Also returns the prices the triggers fire on, because a stop that triggers
    on mark and a page that only shows last are two different truths."""
    out = []
    for account in ("personal", "biz"):
        try:
            key, secret = kraken_sync.get_api_keys(account)
            out.extend(kraken_sync.fetch_open_orders(key, secret, account))
        except Exception:
            pass
    prices = {}
    try:
        from kraken.futures import Market
        key, secret = kraken_sync.get_api_keys("personal")
        t = [x for x in Market(key=key, secret=secret).get_tickers()["tickers"]
             if x.get("symbol") == "PF_XBTUSD"]
        if t:
            t = t[0]
            prices = {"mark": t.get("markPrice"), "index": t.get("indexPrice"),
                      "last": t.get("last"), "bid": t.get("bid"), "ask": t.get("ask"),
                      "funding": t.get("fundingRate"),
                      "high24h": t.get("high24h"), "low24h": t.get("low24h")}
    except Exception:
        pass
    return {"orders": out, "prices": prices}


@app.post("/api/orders/cancel")
def orders_cancel(order_id: str, account: str = "personal"):
    """Cancel one resting order."""
    try:
        from kraken.futures import Trade
        key, secret = kraken_sync.get_api_keys(account)
        return {"ok": True, "response": Trade(key=key, secret=secret,
                sandbox=False).cancel_order(order_id=order_id)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


@app.post("/api/orders/edit")
def orders_edit(order_id: str, stop_price: Optional[float] = None,
                 limit_price: Optional[float] = None, account: str = "personal"):
    """Move a resting order's trigger in place. NEXT_SESSION.md: `Trade.edit_order`
    was unwired — the SDK call already existed, moving a stop meant the website
    or cancel-and-replace. Routed through execute.edit_order so sandbox mode
    is respected the same way execute()/close() already are."""
    from . import execute
    if stop_price is None and limit_price is None:
        raise HTTPException(status_code=422, detail="stop_price or limit_price required")
    return execute.edit_order(order_id, stop_price=stop_price, limit_price=limit_price,
                               account=account)


@app.get("/api/market/read")
def market_read(direction: str = "long"):
    """The briefing shown before he trades against the scanner: RSI, MACD, the
    moving averages, Bollinger position and ATR, each with a stance and a
    sentence, from the locally cached candles."""
    from .market_read import read
    return read(direction)


@app.get("/api/veto-overrides")
def veto_overrides(limit: int = Query(50, ge=1, le=500)):
    """Trades taken against the scanner, with the reasoning attached. The
    training set for whether his read beats the rules."""
    from .veto_log import recent
    return {"overrides": recent(limit)}


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

    Signals that violate discipline (09:00-BKK bleed hour, sub-60min cooldown,
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

@app.get("/hedge-signals", response_class=HTMLResponse)
def signals_page_new():
    """Responsive signals queue built on the shared design system."""
    from .signals_page import render
    return render()



# ─── Backtest ─────────────────────────────────────────────────────────────────

from app.backtest_engine import STRATEGIES as BT_STRATEGIES, run_strategy as _run_strategy
import threading as _threading

_bt_cache: dict = {}       # name → result
_bt_running: dict = {}     # name → True/False


def _backtest_fragment():
    """The interactive backtest runner (strategy picker → run / SL×TP sweep).
    Lives embedded on /strategy so live ranks, simulated ranks and the runner
    are one surface; /backtest redirects there. Returns (css, body, script)."""
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
.c-n{width:72px;background:var(--s1);border:1px solid var(--b2);color:var(--t1);border-radius:6px;padding:8px 10px;font-size:12px;font-family:var(--mono);margin-left:4px}
</style>"""

    body = f"""
<h1 id="backtest" style="margin-top:34px">Strategy Backtest — run it yourself</h1>
<div class="sub">BTC perps · Bybit USDT data (= same price action as Kraken USD, arbitraged tick-for-tick — Kraken's public API only serves ~4mo of candles) · each strategy on its own timeframe · starting balance editable (defaults to your live equity) · 0.15%/side fee</div>

<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this backtest</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what this page is</h4>Runs a <b>locked, mechanical strategy</b> over ~30 months of BTC/USDT 4H history and reports exactly how it would have done — no discretion, no curve-fitting. Pick a strategy, hit <b>Run</b>, read the scorecard.
<h4>the metrics that matter</h4><b class="g">Win rate</b> ≥48% = goal-grade. <b>Profit factor</b> ≥1.5 (gross win ÷ gross loss). <b class="a">Avg R</b> ≥3.5 — the real lever. <b class="r">Max DD</b> &lt;40% survivable, and <b>max consecutive losses</b> = your risk-of-ruin reality check.
<h4>the risk-adjusted trio (plain English)</h4><b>Sharpe</b> = return per unit of <i>bumpiness</i> — how much reward you got for how wildly the equity swung. ≥1 is solid, higher is smoother. <b>Sortino</b> = the same idea but only counts the <i>downside</i> swings (it doesn't punish you for big <i>up</i> moves — fairer for high-R strategies). <b>Calmar</b> = annual return ÷ worst drawdown — "how much did I make for the deepest hole I sat in." Use them to compare two strategies with similar returns: the higher trio = the same money with less pain.
<h4>equity curve + trade log</h4>The curve is account €over the window; the log lists every entry/exit with PnL% and hold time. Look for <b>smooth-ish</b> growth, not one lucky spike.
<h4>historical, not live</h4>Past fills on past candles — assumptions, not promises. Compare against your real results in <a href="/hedge-journal">Journal</a>.
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

<div class="sect closed" id="h-custom" onclick="tog('custom')"><span class="caret">▾</span><span class="ttl">🛠 build your own strategy</span><span class="line"></span></div>
<div class="sec-body closed" id="s-custom">
  <div class="card" style="margin-top:8px">
    <div style="font-size:11px;color:var(--t3);margin-bottom:14px;line-height:1.55">
      Pick entry conditions — every <b>set</b> condition must hold (AND), blank/any = ignored.
      Runs through the <b>exact same engine</b> as the coded strategies (same fills, fees, discipline gates),
      over the months &amp; starting balance selected above. Hours are Bangkok time, window may wrap midnight.</div>
    <div class="row" style="margin-bottom:12px">
      <select id="c-dir"><option value="long">LONG</option><option value="short">SHORT</option><option value="">any (search)</option></select>
      <select id="c-tf"><option value="1h">1h bars</option><option value="4h">4h bars</option><option value="">any (search)</option></select>
      <select id="c-trend"><option value="">trend: any</option><option value="up">trend: up (EMA21&gt;50)</option><option value="down">trend: down (EMA21&lt;50)</option></select>
      <select id="c-candle"><option value="">bar: any</option><option value="bull">bar: bull close</option><option value="bear">bar: bear close</option></select>
      <select id="c-macd"><option value="">MACD: any</option><option value="bull">MACD: bull (hist&gt;0)</option><option value="bear">MACD: bear (hist&lt;0)</option></select>
    </div>
    <div class="row" style="margin-bottom:12px">
      <select id="c-bb"><option value="">Bollinger: any</option><option value="below_lower">BB: below lower</option><option value="above_upper">BB: above upper</option></select>
      <select id="c-td"><option value="">TD seq: any</option><option value="buy9">TD: buy 9+ (exhaustion ↓)</option><option value="sell9">TD: sell 9+ (exhaustion ↑)</option></select>
      <select id="c-ma"><option value="">MA stack: any</option><option value="bull">MA 50&gt;100&gt;200</option><option value="bear">MA 50&lt;100&lt;200</option></select>
      <select id="c-ar"><option value="">Vol regime: any</option><option value="low">low vol (ATR&lt;median)</option><option value="high">high vol (ATR≥median)</option></select>
      <label style="font-size:11px;color:var(--t2)"><input id="c-vs" type="checkbox" style="vertical-align:-2px"> vol spike ≥2×</label>
    </div>
    <div class="row" style="margin-bottom:12px">
      <label style="font-size:11px;color:var(--t2)">RSI ≤ <input id="c-rsimax" type="number" step="any" placeholder="off" class="c-n"></label>
      <label style="font-size:11px;color:var(--t2)">RSI ≥ <input id="c-rsimin" type="number" step="any" placeholder="off" class="c-n"></label>
      <label style="font-size:11px;color:var(--t2)">BKK hour <input id="c-hf" type="number" min="0" max="23" placeholder="from" class="c-n" style="width:58px">–<input id="c-ht" type="number" min="0" max="23" placeholder="to" class="c-n" style="width:58px"></label>
    </div>
    <div class="row" style="margin-bottom:12px">
      <label style="font-size:11px;color:var(--t2)">SL % <input id="c-sl" type="number" step="any" value="0.63" class="c-n"></label>
      <label style="font-size:11px;color:var(--t2)">TP % <input id="c-tp" type="number" step="any" value="1.5" class="c-n"></label>
      <label style="font-size:11px;color:var(--t2)">Lev × <input id="c-lev" type="number" step="any" value="10" class="c-n" style="width:58px"></label>
      <label style="font-size:11px;color:var(--t2)" title="Per-side fill cost added to fees — market orders never fill at the ideal price">Slip % <input id="c-slip" type="number" step="any" value="0.03" class="c-n" style="width:64px"></label>
      <label style="font-size:11px;color:var(--t2)" title="Stop can't be tighter than this × the entry bar's ATR% — volatility noise shouldn't stop you out. 0 = off; try 1–1.5">ATR floor × <input id="c-atrf" type="number" step="any" value="0" class="c-n" style="width:58px"></label>
    </div>
    <div class="row" style="margin-bottom:10px">
      <span style="font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em" title="Dynamic stops scaled to volatility (search-v3 geometry). For a single backtest the LEFT box is used and the SL/TP % boxes above are ignored when ATR stop &gt; 0. For a search, the range is swept.">risk envelope —</span>
      <label style="font-size:11px;color:var(--t2)" title="Stop = k × the entry bar's ATR. Left = from, right = to. Single backtest uses the LEFT value (0 = off → fixed SL/TP). v3 survivors sit at 1.5–2.5.">ATR stop × <input id="c-atrs-lo" type="number" step="any" value="0" class="c-n" style="width:48px">–<input id="c-atrs-hi" type="number" step="any" value="2.5" class="c-n" style="width:48px"></label>
      <label style="font-size:11px;color:var(--t2)" title="Take-profit = R × the stop distance. Left = from, right = to. v3 survivors use 3–5.">R <input id="c-rr-lo" type="number" step="any" value="2" class="c-n" style="width:44px">–<input id="c-rr-hi" type="number" step="any" value="5" class="c-n" style="width:44px"></label>
      <label style="font-size:11px;color:var(--t2)" title="Risk-normalized sizing: each trade risks this % of equity, leverage = risk ÷ stop capped at Lev. Left = from, right = to (only the two ends are tested — risk scales monotonically). v3 used 2.">Risk %/trade <input id="c-risk-lo" type="number" step="any" value="2" class="c-n" style="width:44px">–<input id="c-risk-hi" type="number" step="any" value="2" class="c-n" style="width:44px"></label>
    </div>
    <div class="row" style="margin-bottom:12px">
      <button class="run" id="search-btn" onclick="runCustomSearch()" title="Sweep every blank field above (set fields stay pinned) across the whole risk envelope, and rank the condition-sets that survive. Blank direction/timeframe = both are searched too.">🔍 Search blanks</button>
      <button class="run" id="custom-btn" onclick="runCustom()" title="Backtest ONE exact idea — pick a direction &amp; timeframe, uses the left value of each range">▶ Backtest it</button>
      <button id="csweep-btn" onclick="runCustomSweep()" title="Re-run these exact entry conditions across the whole ATR-stop × R grid (the 7×7 matrix search v3 used) — a real edge is a green neighbourhood, not one lucky cell">⊞ Sweep k×R</button>
      <button id="pine-btn" onclick="exportPine()" title="Export these exact conditions as a TradingView Pine v5 strategy — paste into the Pine editor">⧉ Pine</button>
    </div>
    <div class="row" style="margin-bottom:10px;gap:10px">
      <label id="feas-lbl" style="font-size:11px;color:var(--t2);display:inline-flex;align-items:center;gap:6px;cursor:pointer"
             title="Keep only the strategies whose win rate, R:R and cadence land inside the feasible envelope from the Fit sweep above.">
        <input type="checkbox" id="feas-only" disabled> Feasible only</label>
      <span id="feas-note" style="font-size:10px;color:var(--t3)">run the Fit sweep to get an envelope</span>
    </div>
    <div id="search-prog" style="display:none;font-size:11px;color:var(--t2);margin-bottom:10px"></div>
    <div id="search-results" style="display:none;margin-bottom:12px"></div>
    <div style="font-size:10px;color:var(--t3)">Results render in the same scorecard below. Mined in-sample — a green result is a candidate to sweep &amp; forward-test, not a green light.</div>
    <pre id="pine-out" style="display:none;margin-top:12px;padding:12px;background:var(--bg);border:1px solid var(--b1);border-radius:6px;font-size:10px;max-height:320px;overflow:auto;white-space:pre"></pre>
  </div>
</div>

<div id="sweep-wrap" style="display:none">
  <div class="card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
      <div id="sweep-title" style="font-size:14px;font-weight:700;color:var(--t1)">Robustness sweep — SL × TP</div>
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
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
      <div id="strat-name" style="font-size:14px;font-weight:700;color:var(--ink);margin-bottom:4px"></div>
      <a id="result-goal" href="#" style="font-size:11px;white-space:nowrap" title="Send this backtest's win rate, R and trade frequency to the Goal model">→ Goal model</a>
    </div>
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

function runCustom() {{
  var body = customBody();
  var stat = document.getElementById('status');
  if (!body.direction || !body.timeframe) {{
    stat.textContent = 'Pick a direction & timeframe to backtest one idea — or hit 🔍 Search blanks to sweep them.';
    return;
  }}
  var btn = document.getElementById('custom-btn');
  btn.disabled = true; btn.textContent = '⏳ Running…';
  stat.textContent = 'Backtesting your strategy…';
  fetch('/api/backtest/custom', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body)
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    btn.disabled = false; btn.textContent = '▶ Backtest it';
    if (d.error) {{ stat.textContent = 'Error: ' + d.error; return; }}
    stat.textContent = '';
    renderResults(d);
    document.getElementById('results').scrollIntoView({{behavior:'smooth'}});
  }})
  .catch(function(e) {{ btn.disabled = false; btn.textContent = '▶ Backtest it'; stat.textContent = 'Failed: ' + e; }});
}}

function customBody() {{
  var num = function(id) {{ var v = document.getElementById(id).value; return v === '' ? null : parseFloat(v); }};
  var sel = function(id) {{ return document.getElementById(id).value || null; }};
  var lo = function(id) {{ var v = num(id); return v === null ? null : v; }};
  var klo = num('c-atrs-lo'), khi = num('c-atrs-hi');
  var rlo = num('c-rr-lo'),   rhi = num('c-rr-hi');
  var xlo = num('c-risk-lo'), xhi = num('c-risk-hi');
  return {{
    months: parseInt(document.getElementById('months').value) || 24,
    initial_capital: parseFloat(document.getElementById('capital').value) || 637,
    // dir/tf sent raw so "" (any) survives to the search; single-run guards blank
    timeframe: document.getElementById('c-tf').value, direction: document.getElementById('c-dir').value,
    trend: sel('c-trend'), candle: sel('c-candle'), macd: sel('c-macd'),
    bb: sel('c-bb'), td: sel('c-td'), ma_align: sel('c-ma'), atr_regime: sel('c-ar'),
    vol_spike: document.getElementById('c-vs').checked,
    rsi_max: num('c-rsimax'), rsi_min: num('c-rsimin'),
    hour_from: num('c-hf'), hour_to: num('c-ht'),
    stop_pct: num('c-sl') || {setups.SL_PCT}, tp_pct: num('c-tp') || {setups.TP_PCT}, leverage: num('c-lev') || 10,
    slippage_pct: num('c-slip') !== null ? num('c-slip') : 0.03,
    atr_floor_mult: num('c-atrf') || 0,
    // single-run geometry = the FROM (left) values
    atr_stop_mult: klo || 0, rr: rlo, risk_pct: xlo || 0,
    // search envelope
    k_min: klo !== null ? klo : 0, k_max: khi !== null ? khi : 3,
    r_min: rlo !== null ? rlo : 1, r_max: rhi !== null ? rhi : 5,
    risk_min: xlo !== null ? xlo : 2, risk_max: xhi !== null ? xhi : 2
  }};
}}

// Fill the whole form from a params dict (search-result row → editable strategy)
function fillFromParams(p) {{
  var setSel = function(id, v) {{ document.getElementById(id).value = (v == null ? '' : v); }};
  setSel('c-dir', p.direction); setSel('c-tf', p.timeframe);
  setSel('c-trend', p.trend); setSel('c-candle', p.candle); setSel('c-macd', p.macd);
  setSel('c-bb', p.bb); setSel('c-td', p.td); setSel('c-ma', p.ma_align); setSel('c-ar', p.atr_regime);
  document.getElementById('c-vs').checked = !!p.vol_spike;
  setSel('c-rsimax', p.rsi_max); setSel('c-rsimin', p.rsi_min);
  setSel('c-hf', p.hour_from); setSel('c-ht', p.hour_to);
  var k = p.atr_stop_mult || 0, r = p.rr, x = p.risk_pct || 0;
  setSel('c-atrs-lo', k); setSel('c-atrs-hi', k);
  setSel('c-rr-lo', r); setSel('c-rr-hi', r);
  setSel('c-risk-lo', x); setSel('c-risk-hi', x);
  document.getElementById('h-custom').scrollIntoView({{behavior:'smooth'}});
}}

var _searchPoll = null;
function runCustomSearch() {{
  var btn = document.getElementById('search-btn');
  var prog = document.getElementById('search-prog');
  var res = document.getElementById('search-results');
  btn.disabled = true; btn.textContent = '⏳ Searching…';
  res.style.display = 'none'; res.innerHTML = '';
  prog.style.display = ''; prog.textContent = 'Starting…';
  fetch('/api/backtest/search', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(customBody())
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    if (d.error) {{ prog.textContent = '⚠ ' + d.error; btn.disabled = false; btn.textContent = '🔍 Search blanks'; return; }}
    prog.textContent = 'Running ~' + (d.total_est||0).toLocaleString() + ' backtests…';
    _searchPoll = setInterval(pollSearch, 2000);
    pollSearch();
  }})
  .catch(function(e) {{ prog.textContent = 'Failed: ' + e; btn.disabled = false; btn.textContent = '🔍 Search blanks'; }});
}}

function pollSearch() {{
  fetch('/api/backtest/search/status').then(function(r) {{ return r.json(); }}).then(function(d) {{
    var prog = document.getElementById('search-prog');
    var pct = d.total ? Math.round(100 * d.done / d.total) : 0;
    prog.textContent = (d.running ? '⏳ ' : '✓ ') + 'Ran ' + d.done.toLocaleString() + ' / ' +
      d.total.toLocaleString() + ' (' + pct + '%) · ' + d.found + ' results · showing top ' +
      Math.min(50, d.top.length);
    if (d.error) prog.textContent = '⚠ ' + d.error;
    window._lastSearch = d;
    renderSearch(d);
    if (!d.running) {{
      clearInterval(_searchPoll); _searchPoll = null;
      var btn = document.getElementById('search-btn');
      btn.disabled = false; btn.textContent = '🔍 Search blanks';
    }}
  }});
}}

// ── Stage B: the Fit envelope filters the real search ───────────────────────
function envNote(env) {{
  var lbl = document.getElementById('feas-note'), box = document.getElementById('feas-only');
  if (!env) {{ box.disabled = true; box.checked = false;
    lbl.textContent = 'run the Fit sweep to get an envelope'; return false; }}
  if (env.stale) {{ box.disabled = true; box.checked = false;
    lbl.innerHTML = '<span style="color:var(--amber)">envelope is ' + env.age_days +
      ' days old — <a href="#fit">re-run Fit</a> before filtering on it</span>'; return false; }}
  if (!env.usable) {{ box.disabled = true; box.checked = false;
    lbl.innerHTML = '<span style="color:var(--short)">last sweep found <b>no feasible envelope</b> — ' +
      'nothing to filter by. Push the date, cut the target, or loosen the risk caps.</span>'; return false; }}
  var e = env.envelope;
  var s = 'envelope: WR ' + (e.wr.min*100).toFixed(0) + '–' + (e.wr.max*100).toFixed(0) + '% · R ' +
    e.rr.min.toFixed(1) + '–' + e.rr.max.toFixed(1) + ' · ' + e.freq.min + '–' + e.freq.max +
    '/wk · ' + env.feasible_count.toLocaleString() + ' feasible cells · ' + env.age_days + 'd old';
  if (!env.leverage_ok && e.lev)
    s += ' — ⚠ every backtest runs at ' + env.search_leverage + '× leverage, outside the envelope\\'s ' +
         e.lev.min + '–' + e.lev.max + '×';
  box.disabled = false; lbl.textContent = s;
  if (!env.leverage_ok) lbl.style.color = 'var(--amber)'; else lbl.style.color = 'var(--t3)';
  return true;
}}

function fitCell(row) {{
  if (!row.fit) return '<span style="color:var(--t3)">—</span>';
  if (row.fit.fits) return '<span class="win" style="font-weight:700">FITS</span>';
  var f = row.fit.fails[0];
  return '<span style="color:var(--t3)" title="' +
    row.fit.fails.map(function(x) {{ return x.axis + ': needs ' + x.needs + ', has ' + x.has; }}).join(' · ') +
    '">' + f.axis + ' ' + f.needs + '</span>';
}}

// C4 — a strategy can be robust in-sample and still need a move the market
// rarely makes. Colour by supply-vs-need, always carrying the two numbers.
var RCOL = {{OFFERED: 'var(--long)', TIGHT: 'var(--amber)', STARVED: 'var(--short)'}};
function realCell(row) {{
  var R = row.realism;
  if (!R) return '<span style="color:var(--t3)">—</span>';
  return '<span style="color:' + RCOL[R.badge] + ';font-weight:700" title="' + R.text + '">' +
    R.badge + '</span>';
}}

function renderSearch(d) {{
  var res = document.getElementById('search-results');
  var usable = envNote(d.env);
  var feasOnly = usable && document.getElementById('feas-only').checked;
  if (!d.top.length) {{ return; }}
  var rows = feasOnly ? d.top.filter(function(r) {{ return r.fit && r.fit.fits; }}) : d.top;

  // the empty corridor — the most valuable state this page has, so say it plainly
  if (feasOnly && !rows.length) {{
    var near = d.top.slice().sort(function(a, b) {{
      return ((a.fit&&a.fit.dist)||1e9) - ((b.fit&&b.fit.dist)||1e9); }})[0];
    var miss = '';
    if (near && near.fit) miss = ' Nearest miss: <b>' + near.desc + '</b> (fails on ' +
      near.fit.fails.map(function(x) {{ return x.axis + ': needs ' + x.needs + ', has ' + x.has; }}).join('; ') + ').';
    res.innerHTML = '<div style="border:1px solid var(--short);background:var(--short-d);color:var(--short);' +
      'border-radius:8px;padding:12px 14px;font-size:12px;line-height:1.55">' +
      '<b>The corridor is empty</b> — nothing in the strategy library fits this envelope. ' +
      'At these constraints the goal is not reachable with anything you can currently trade.' + miss +
      '</div>';
    res.style.display = ''; return;
  }}

  window._searchTop = rows; window._searchMonths = d.months;
  var weeks = (d.months || 30) * 4.345;
  var h = '<div style="font-size:10px;color:var(--t3);margin:2px 0 8px">Ranked by <b>fit</b> (inside the envelope first), then <b>robust</b> (green = profitable in BOTH halves, n≥40 · 30mo split-half), then net %. Still in-sample — a survivor is a candidate to forward-test, not a green light. <b>Click a row</b> to load it into the builder above.' +
    (usable ? ' <b>' + d.fits_count + '</b> of ' + d.found + ' land inside the envelope.' : '') + '</div>';
  h += '<div style="overflow-x:auto;max-height:420px;overflow-y:auto"><table><thead><tr>' +
       '<th>#</th><th>strategy</th><th>tf</th><th>n</th><th>/wk</th><th>WR</th><th>PF</th><th>net%</th><th>maxDD</th><th>halves</th><th>fit</th><th title="Does the market actually offer this strategy\\'s take-profit move often enough to feed its cadence?">on offer</th><th></th></tr></thead><tbody>';
  rows.forEach(function(row, i) {{
    var cls = row.robust ? 'win' : '';
    h += '<tr style="cursor:pointer" onclick="fillFromParams(window._searchTop['+i+'].params)">' +
      '<td>' + (i+1) + '</td>' +
      '<td style="font-size:10px">' + row.desc + '</td>' +
      '<td>' + row.tf + '</td>' +
      '<td>' + row.n + '</td>' +
      '<td>' + (row.freq != null ? row.freq : '—') + '</td>' +
      '<td>' + row.wr + '%</td>' +
      '<td>' + row.pf + '</td>' +
      '<td class="' + cls + '">' + (row.net_pct>=0?'+':'') + row.net_pct + '%</td>' +
      '<td>' + row.max_dd + '%</td>' +
      '<td style="font-size:10px">' + (row.half1>=0?'+':'') + row.half1 + ' / ' + (row.half2>=0?'+':'') + row.half2 + '</td>' +
      '<td style="font-size:10px">' + fitCell(row) + '</td>' +
      '<td style="font-size:10px">' + realCell(row) + '</td>' +
      '<td><a href="#" onclick="event.stopPropagation();toGoal(' + row.wr + ',' + row.rr + ',' + (row.n/weeks).toFixed(2) + ');return false" title="Send this strategy\\'s stats to the Goal model">→ Goal</a></td>' +
      '</tr>';
  }});
  h += '</tbody></table></div>';
  res.innerHTML = h; res.style.display = '';
}}

// re-filter without re-running the search
document.addEventListener('DOMContentLoaded', function() {{
  var box = document.getElementById('feas-only');
  if (box) box.addEventListener('change', function() {{
    if (window._lastSearch) renderSearch(window._lastSearch);
  }});
  fetch('/api/backtest/search/status').then(function(r) {{ return r.json(); }})
    .then(function(d) {{ envNote(d.env); }}).catch(function() {{}});
}});

function toGoal(wrPct, rr, freq) {{
  var q = 'win_rate=' + (wrPct/100).toFixed(4) + '&rr_ratio=' + rr + '&trades_per_week=' + freq;
  window.open('/hedge-goal?' + q, '_blank');
}}

function runCustomSweep() {{
  var btn = document.getElementById('csweep-btn');
  var stat = document.getElementById('status');
  btn.disabled = true; btn.textContent = '⏳ Sweeping…';
  stat.textContent = 'Sweeping ATR-stop × R grid (49 backtests, one data load)…';
  document.getElementById('sweep-wrap').style.display = 'none';
  fetch('/api/backtest/custom-sweep', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(customBody())
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    btn.disabled = false; btn.textContent = '⊞ Sweep k×R';
    if (d.error) {{ stat.textContent = 'Sweep error: ' + d.error; return; }}
    stat.textContent = '';
    window._sweep = d; buildHeatmap(d);
    document.getElementById('sweep-wrap').style.display = '';
    document.getElementById('sweep-wrap').scrollIntoView({{behavior:'smooth'}});
  }})
  .catch(function(e) {{ btn.disabled = false; btn.textContent = '⊞ Sweep k×R'; stat.textContent = 'Sweep failed: ' + e; }});
}}

function exportPine() {{
  fetch('/api/backtest/pine', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(customBody())
  }})
  .then(function(r) {{ return r.text(); }})
  .then(function(t) {{
    var el = document.getElementById('pine-out');
    el.textContent = t; el.style.display = '';
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(function() {{
      document.getElementById('pine-btn').textContent = '✓ copied';
      setTimeout(function() {{ document.getElementById('pine-btn').textContent = '⧉ Pine'; }}, 2000);
    }});
  }});
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
  var kr = d.grid === 'k_rr';   // ATR-geometry sweep vs classic SL×TP
  var corner = kr ? 'k×ATR ╲ R' : 'SL ╲ TP', rs = kr ? '×' : '%', cs = kr ? 'R' : '%';
  document.getElementById('sweep-title').textContent =
    kr ? 'Robustness sweep — ATR stop × R' : 'Robustness sweep — SL × TP';
  var map = {{}};
  d.cells.forEach(function(c) {{ map[c.stop + '|' + c.tp] = c; }});
  var h = '<table class="hm"><thead><tr><th class="hm-corner">' + corner + '</th>';
  d.tps.forEach(function(tp) {{ h += '<th>' + tp + cs + '</th>'; }});
  h += '</tr></thead><tbody>';
  d.stops.forEach(function(sp) {{
    h += '<tr><th>' + sp + rs + '</th>';
    d.tps.forEach(function(tp) {{
      var c = map[sp + '|' + tp] || {{}};
      var base = (sp === d.base_stop && tp === d.base_tp) ? ' hm-base' : '';
      var tip = (kr ? 'stop ' + sp + '×ATR / TP ' + tp + 'R' : 'SL ' + sp + '% / TP ' + tp + '% · R ' + (c.r||'')) + ' · n=' + (c.n||0) +
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
  // → Goal link: real WR / R / trade-frequency from this backtest into /goal
  var gp = d.params || {{}};
  var gR = gp.rr || (gp.stop_pct ? (gp.tp_pct / gp.stop_pct) : m.avg_r) || 3;
  var gLink = document.getElementById('result-goal');
  if (m.win_rate != null) {{
    gLink.href = '/hedge-goal?win_rate=' + (m.win_rate/100).toFixed(4) + '&rr_ratio=' +
                 (+gR).toFixed(2) + '&trades_per_week=' + (m.trades_per_week||1);
    gLink.target = '_blank'; gLink.style.display = '';
  }} else {{ gLink.style.display = 'none'; }}
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

    return css, body, script


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


from . import setups   # noqa: E402  — module level: the defaults below need it


class BtCustomRequest(BaseModel):
    months: int = 24
    initial_capital: float = 637.0
    timeframe: str = "1h"
    direction: str = "long"
    rsi_max: float | None = None
    rsi_min: float | None = None
    trend: str | None = None        # up | down
    candle: str | None = None       # bull | bear
    macd: str | None = None         # bull | bear (histogram sign)
    bb: str | None = None           # below_lower | above_upper
    td: str | None = None           # buy9 | sell9 (TD Sequential 9+)
    ma_align: str | None = None     # bull | bear (EMA 50/100/200 stack)
    vol_spike: bool = False         # volume > 2× its 20-bar SMA
    atr_regime: str | None = None   # low | high (vs rolling median ATR%)
    funding: str | None = None      # hot | extreme | cold | neg (app/orderflow.py)
    mayer_max: float | None = None  # 2y-MA multiple cycle gates
    mayer_min: float | None = None
    hour_from: int | None = None    # Bangkok hours, window may wrap midnight
    hour_to: int | None = None
    stop_pct: float = setups.SL_PCT   # defaults track the armed geometry, so an
    tp_pct: float = setups.TP_PCT     # unspecified search tests what he runs
    leverage: float = 10.0
    slippage_pct: float = 0.03     # per-side market-order fill cost
    atr_floor_mult: float = 0.0    # stop >= mult × entry-bar ATR% (0 = off)
    atr_stop_mult: float = 0.0     # dynamic stop = k × entry-bar ATR% (0 = off; replaces SL/TP %)
    rr: float | None = None        # TP = rr × stop (with atr_stop_mult)
    risk_pct: float = 0.0          # risk-normalized sizing: %equity/trade, lev = risk/stop capped (0 = off)
    cooldown_bars: int = 4
    once_per_day: bool = True
    skip_sat: bool = True
    # search-mode geometry envelope (blank builder fields = swept dimensions)
    k_min: float = 0.0
    k_max: float = 3.0
    r_min: float = 1.0
    r_max: float = 5.0
    risk_min: float = 2.0
    risk_max: float = 2.0


@app.post("/api/backtest/custom")
def api_backtest_custom(req: BtCustomRequest):
    """Backtest a user-built parametric strategy (the /edge 'build your own')."""
    if req.timeframe not in ("1h", "4h"):
        return {"error": "timeframe must be 1h or 4h"}
    if req.direction not in ("long", "short"):
        return {"error": "direction must be long or short"}
    try:
        from app.backtest_engine import run_custom
        params = req.model_dump(exclude_none=True)
        return run_custom(params, months=req.months, initial_capital=req.initial_capital)
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}


@app.post("/api/backtest/custom-sweep")
def api_backtest_custom_sweep(req: BtCustomRequest):
    """k×R geometry sweep of a user-built strategy — the v3 search's stage-2
    matrix, on demand from the /edge builder. Same cells shape as the SL×TP
    sweep so the heatmap renders it unchanged."""
    if req.timeframe not in ("1h", "4h"):
        return {"error": "timeframe must be 1h or 4h"}
    if req.direction not in ("long", "short"):
        return {"error": "direction must be long or short"}
    try:
        from app.backtest_engine import sweep_custom
        return sweep_custom(req.model_dump(exclude_none=True),
                            months=req.months, initial_capital=req.initial_capital)
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}


@app.post("/api/backtest/search")
def api_backtest_search(req: BtCustomRequest):
    """Start a background search: blank builder fields are swept, set fields are
    pinned, geometry ranges bound the k×R×risk envelope. Poll /search/status."""
    if req.direction not in ("long", "short") and req.direction:
        return {"error": "direction must be long, short, or blank"}
    from app.search_custom import start
    # direction/timeframe: treat the form's non-blank defaults as pins only when
    # the user actually chose; the builder always sends both, so a blank sweep is
    # requested via the dedicated fields below. Here both are always pins unless
    # the client sent them empty — the UI sends "" to mean "sweep".
    body = req.model_dump()
    return start(body)


@app.get("/api/backtest/search/status")
def api_backtest_search_status():
    from app.search_custom import status
    return status()


# ─── /edge #fit — goal-constrained parameter sweep (Stage A) ──────────────────

class FitRequest(BaseModel):
    # swept-axis ranges (any omitted → app.fit_sweep defaults; freq hi → hist avg)
    lev_min:  float | None = None
    lev_max:  float | None = None
    freq_min: float | None = None
    freq_max: float | None = None
    wr_min:   float | None = None
    wr_max:   float | None = None
    rr_min:   float | None = None
    rr_max:   float | None = None
    atr_min:  float | None = None      # ATR floor as a price-move fraction
    atr_max:  float | None = None
    # fixed goal params (page prefills from /api/config)
    start_balance:         float
    target_balance:        float
    target_date:           date
    max_drawdown_allowed:  float = 0.50
    losses_allowed:        int   = 20
    fractional_kelly:      float = 1.0 / 6.0
    execution_fill_factor: float = 1.0
    slippage_pct:          float = 0.0
    btc_price_eur:         float | None = None
    btc_growth_monthly:    float = 0.04
    # prop: risk is FIXED by the plan (fraction, 0.005 = 0.5%), not derived;
    # book routes the measured pin to the prop ledger instead of hedge trades
    risk_per_trade:        float | None = None
    book:                  str | None = None


@app.get("/api/fit/defaults")
def api_fit_defaults(book: str = "hedge"):
    """Prefill payload for the Fit form: goal params + the historical weekly trade
    frequency (the trades/week axis ceiling). `book='prop'` swaps the hedge BTC-stack
    goal for the EVAL goal — start=eval account, target=+profit_target%, floor=-max_dd%,
    horizon=45d, and btc_growth=0 (an eval account is USD, it doesn't ride BTC)."""
    from app.fit_sweep import historical_freq_per_week
    cfg = get_lens_config()
    if book == "prop":
        import datetime
        from app.prop_views import prop_config
        from app.prop_eval import EVALS
        pc = prop_config()
        rule = EVALS[pc["eval_name"]]
        acct, risk = pc["account"], pc["risk"]
        cfg = {**cfg,
               "start_balance": acct,
               "target_balance": round(acct * (1 + rule["profit_target_pct"] / 100), 2),
               "target_date": (datetime.date.today() + datetime.timedelta(days=45)).isoformat(),
               "max_drawdown_allowed": rule["max_dd_pct"] / 100.0,
               "losses_allowed": max(1, int((rule["max_dd_pct"] / 100.0) / (risk / 100.0))),
               "leverage": rule["max_leverage"],
               # eval reality: limit fills (no slip, full size), ¼-Kelly advisory,
               # a USD account that doesn't ride BTC, and risk FIXED by the plan
               "execution_fill_factor": 1.0,
               "slippage_pct": 0.0,
               "fractional_kelly": 0.25,
               "btc_price_eur": None,
               "btc_growth_monthly": 0.0,
               "risk_per_trade": risk / 100.0}
        # freq ceiling = the BASKET's real cadence, not the hedge ledger's
        freq = historical_freq_per_week()
        try:
            from app.prop_goal import _basket_geometry
            geo = _basket_geometry()
            if geo:
                freq = round(geo["trades_per_month"] / 4.345, 2)
        except Exception:
            pass
        return {"config": cfg, "freq_per_week": freq}
    return {"config": cfg, "freq_per_week": historical_freq_per_week()}


@app.post("/api/fit/run")
def api_fit_run(req: FitRequest):
    """Start the background parameter sweep. Poll /api/fit/status."""
    from app.fit_sweep import start
    body = req.model_dump()
    body["target_date"] = req.target_date.isoformat()
    return start({k: v for k, v in body.items() if v is not None})


@app.get("/api/fit/status")
def api_fit_status():
    from app.fit_sweep import status
    return status()


@app.get("/api/fit/envelope")
def api_fit_envelope():
    """The newest saved feasible envelope (Stage B) + its age. `null` before the
    first sweep — the /edge search shows a 'run Fit first' nudge on that."""
    from app.fit_sweep import latest_envelope
    return latest_envelope()


@app.post("/api/backtest/pine")
def api_backtest_pine(req: BtCustomRequest):
    """TradingView Pine v5 export of a custom strategy — same conditions the
    engine backtests, as a visual indicator/strategy."""
    from app.backtest_engine import to_pinescript
    return PlainTextResponse(to_pinescript(req.model_dump(exclude_none=True)))


@app.get("/api/backtest/strategies")
def api_backtest_strategies():
    return {
        k: {"description": v["description"], "params": v["params"]}
        for k, v in BT_STRATEGIES.items()
    }


# ─── Trade Review ─────────────────────────────────────────────────────────────

@app.get("/prop-overview", response_class=HTMLResponse)
def overview_page():
    """Prop-book snapshot — eval ledger, performance, market."""
    from .overview_page import render
    return render("prop")


# Hedge pages were renamed to a /hedge-* namespace on 2026-08-03 so the URL matches
# the nav chip and mirrors /prop-*. Old bare paths 301 to the new ones — bookmarks,
# the phone's home-screen shortcuts and any stale href keep working.
LEGACY_ROUTES = {
    "/overview-hedge": "/hedge-overview", "/dashboard": "/hedge-plan",
    "/goal": "/hedge-goal", "/desk": "/hedge-desk", "/signals": "/hedge-signals",
    "/journal": "/hedge-journal", "/calendar": "/hedge-calendar",
    "/analytics": "/hedge-analytics", "/position": "/hedge-position",
    "/edge": "/hedge-edge",
    # prop, renamed the same day so both books read alike
    "/overview": "/prop-overview", "/prop-dashboard": "/prop-plan",
    # Older shims, folded in here from four hand-written handlers. They were
    # identical 301s that each forgot include_in_schema=False, so /sitemap
    # listed them as if they were pages — two of them under "Engines".
    "/backtest": "/hedge-edge#backtest",
    "/strategy": "/hedge-edge#board", "/strategy-hedge": "/hedge-edge#board",
    # The survival group: five pages that shared prop_metrics() and one question.
    "/rules": "/prop-survival#rules", "/risk": "/prop-survival#risk",
    "/survival": "/prop-survival#survival", "/equity": "/prop-survival#equity",
    "/prop-cone": "/prop-survival#projection",
    "/prop-goal-old": "/prop-survival#projection",
    # 2026-08-03 merges. Reading material is one page with tabs; the audit is
    # one July artifact, not two; geometry/target are one calculation run in
    # both directions; short/robustness/research are conclusion, evidence and
    # appendix of a single argument.
    "/glossary": "/manual?doc=glossary",
    "/audit-report": "/audit#report",
    "/target": "/geometry#target",
    "/short": "/evidence#verdict",
    "/robustness": "/evidence#luck",
    "/research": "/evidence#notebook",
    # 2026-08-21: /today merged into /hedge-track. Both opened on the next rung;
    # /today's unique half was the signal-adherence count, which now lives there
    # as "Did the book follow the engine?" — scoped to the hedge book on the way
    # in, which /today never was.
    "/today": "/hedge-track",
}
def _legacy_redirect(new: str):
    # A factory, not a loop closure: closing over the loop variable would send
    # every legacy path to /hedge-edge. `request` must be annotated or FastAPI
    # reads it as a query param and 422s.
    def go(request: Request):
        q = request.url.query
        # Some targets carry a #fragment; the query has to go before it or the
        # browser reads "?book=prop" as part of the anchor name.
        base, _, frag = new.partition("#")
        # A target may already carry its own query (?doc=glossary), so the
        # incoming one joins with & rather than a second ?.
        sep = "&" if "?" in base else "?"
        return RedirectResponse(
            base + (f"{sep}{q}" if q else "") + (f"#{frag}" if frag else ""),
            status_code=301)
    return go


for _old, _new in LEGACY_ROUTES.items():
    app.get(_old, include_in_schema=False)(_legacy_redirect(_new))


@app.get("/hedge-overview", response_class=HTMLResponse)
def overview_page_hedge():
    """Hedge-book snapshot — live Kraken account, performance, market."""
    from .overview_page import render
    return render("hedge")


@app.get("/hedge-position", response_class=HTMLResponse)
def position_page_route(book: str = "hedge"):
    """Entry + direction → SL/TP/liq levels and size in ₿/€ (uses /api/position).
    Shared page: `book` preselects its Hedge|Prop tab and keeps that mode's nav."""
    from .position_page import position_page
    return position_page(book)


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
        # Legacy 301s and FastAPI's own plumbing are registered with
        # include_in_schema=False. They're not pages; don't map them.
        and getattr(r, "include_in_schema", True)
    })
    return render(paths)


@app.get("/hedge-journal", response_class=HTMLResponse)
def journal_page(book: str = "hedge"):
    from .journal_page import render
    return render(book)


@app.get("/hedge-analytics", response_class=HTMLResponse)
def analytics_page(book: str = "hedge"):
    from .analytics_page import render
    return render(book)


@app.get("/money", response_class=HTMLResponse)
def money_page():
    from .money_page import render_page
    return render_page()


@app.get("/api/money")
def api_money(refresh: bool = Query(False)):
    from .money_page import money_data
    return money_data(refresh=refresh)


@app.get("/hedge-edge", response_class=HTMLResponse)
def edge_page(book: str = "hedge"):
    from .edge_page import render_page
    css, body, script = _backtest_fragment()
    return render_page(bt_css=css, bt_body=body, bt_script=script, book=book)


# /review + /recap deleted — the Journal is the single trade-history surface.


@app.get("/hedge-calendar", response_class=HTMLResponse)
def calendar_page(book: str = "hedge"):
    from .calendar_page import render
    return render(book)


# ── Prop twins: same render, book hard-locked to prop, own URL + nav entry.
# Not clones — one render each, so hedge and prop can never drift. See theme.NAV_PROP.
@app.get("/prop-journal", response_class=HTMLResponse)
def prop_journal_page():
    from .journal_page import render
    return render("prop")


@app.get("/prop-analytics", response_class=HTMLResponse)
def prop_analytics_page():
    from .analytics_page import render
    return render("prop")


@app.get("/prop-position", response_class=HTMLResponse)
def prop_position_page():
    from .position_page import position_page
    return position_page("prop")


@app.get("/prop-edge", response_class=HTMLResponse)
def prop_edge_page():
    from .edge_page import render_page
    css, body, script = _backtest_fragment()
    return render_page(bt_css=css, bt_body=body, bt_script=script, book="prop")


@app.get("/prop-calendar", response_class=HTMLResponse)
def prop_calendar_page():
    from .calendar_page import render
    return render("prop")


@app.get("/prop", response_class=HTMLResponse)
def prop_page():
    from .prop_views import goals_page
    return goals_page()


# Both boards + the backtest runner live on /edge now (one page, three tenses).
@app.get("/prop-survival", response_class=HTMLResponse)
def prop_survival_page():
    """How big do I bet, and will I survive the walls — one page.

    Was five routes: /rules, /risk, /survival, /equity and /prop-cone. They
    read the same prop_metrics() and answered one question between them, so
    reading any one of them alone told you a fifth of the answer. Ordered as
    the question is actually asked: the walls, then the bet size, then what a
    losing streak does to it, then the same thing simulated two ways.

    The two simulations are deliberately both here. /equity draws paths from
    the typed WR and R:R — "what if"; the cone bootstraps your ACTUAL realised
    P&L — "what the book says". Side by side the gap between them is legible,
    which on separate pages it never was.
    """
    from .prop_goal import parts as cone
    from .prop_views import (equity_page_parts, risk_page_parts,
                             rules_page_parts, survival_page_parts)
    from .theme import merged
    from .tldr import opener
    intro = opener(
        "What this page is",
        "The prop firm gives you a funded account with two tripwires: lose 3% in "
        "one day, or drop 3% below the starting balance at any point, and the "
        "account is gone. This page answers one question — how big can each bet "
        "be so that a normal run of losses doesn't hit those tripwires before the "
        "strategy has a chance to work.",
        ["<b>The walls</b> — the exact rules that end the account, and the ones "
         "that turn out not to matter.",
         "<b>Bet size</b> — how much per trade, and why it's that number.",
         "<b>Loss streaks</b> — how many losses in a row you can take before "
         "you're out, and how likely that streak is.",
         "<b>Both simulations</b> — the same account run thousands of times. One "
         "uses your typed win rate, the other uses your <b>real past trades</b>. "
         "When they disagree, the second one is the honest one."],
        "whether passing the eval gets you to 50 ₿. Passing pays a share of "
        "profits on a €10,000 account — the scoreboard above is what that has to "
        "produce monthly just to cover the burn.")
    return merged("/prop-survival", "Survival", [
        {"id": "rules", "label": "The walls", "heading": False, **rules_page_parts()},
        {"id": "risk", "label": "Bet size", "heading": False, **risk_page_parts()},
        {"id": "survival", "label": "Loss streaks", "heading": False, **survival_page_parts()},
        {"id": "equity", "label": "Simulated · from typed WR", "heading": False, **equity_page_parts()},
        {"id": "projection", "label": "Simulated · from real trades", "heading": False, **cone()},
    ], meta="will I survive the walls?", intro=intro)


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
    fee: float = 0.0


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
    cfg = set_prop_eval(params.account, params.risk, params.eval_name, params.fee)
    return {"archived": archived, "config": cfg}


class PropBasket(BaseModel):
    basket: list[str]


@app.get("/prop-plan", response_class=HTMLResponse)
def prop_dashboard_page():
    from .prop_dashboard import dashboard_page
    return dashboard_page()


@app.get("/prop-goal", response_class=HTMLResponse)
def prop_goal_page():
    """Exact clone of the hedge /goal (same page, same panels), fed the prop
    config row + prop measured stats. The MC cone/checks page → /prop-cone."""
    from .goal_page import render
    return render("prop")




@app.get("/prop-track", response_class=HTMLResponse)
def prop_track_page():
    """/hedge-track's missing prop twin (test_nav_parity.py). The daily read
    on the eval — target/floor/today's wall — built on prop_ledger_data(),
    which already computes all of it."""
    from .prop_track_page import render
    return render()


@app.get("/api/prop/goal")
def api_prop_goal():
    """Time-to-target cone for the active basket under the live eval walls."""
    from .prop_goal import cone
    return cone()


@app.get("/api/prop/goal/model")
def api_prop_goal_model():
    """The /prop-goal metrics panel: the hedge goal engine fed the eval's FIXED
    risk and 3% floor, so `risk_of_ruin` becomes P(touching the floor)."""
    from .prop_goal import model
    return model()


@app.get("/api/prop/baskets")
def api_prop_baskets():
    """Candidate baskets scored on speed vs survival, so the trade-off is visible
    before it's chosen."""
    from .prop_goal import basket_options
    from .prop_views import prop_config
    return {"options": basket_options(), "fee": prop_config().get("fee") or 0.0}


@app.post("/api/prop/basket")
def api_prop_set_basket(p: PropBasket):
    """Swap which strategies the scanner may fire. Not a new eval — the running
    account/risk/fee are untouched."""
    from .database import set_prop_basket
    from .backtest_engine import STRATEGIES
    unknown = [n for n in p.basket if n not in STRATEGIES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"not backtest strategies: {unknown}")
    if not p.basket:
        raise HTTPException(status_code=422, detail="basket cannot be empty")
    return {"config": set_prop_basket(p.basket)}


@app.get("/api/prop/archives")
def api_prop_archives():
    """Past eval attempts + lifetime fee spend (archived runs plus the live one —
    the active eval's fee is already paid, so it counts against the tally)."""
    from .prop_ledger import archive_summaries
    from .prop_views import prop_config
    archives = archive_summaries()
    active_fee = prop_config().get("fee") or 0.0
    return {
        "archives": archives,
        "attempts": len(archives) + 1,
        "spent": round(sum(a["fee"] for a in archives) + active_fee, 2),
        "active_fee": round(active_fee, 2),
    }


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
    """Every prop signal (all prop-* strategies the scanner fired), each with the
    prop-legal ticket. Scoped by the `prop-` signal_id prefix, not by strategy, so
    the whole tradeable basket surfaces — not just the hero."""
    from .prop_scan import prop_ticket
    sigs = get_signals(id_prefix="prop-", limit=limit)
    for sg in sigs:
        try:
            if sg.get("entry_price") and sg.get("stop_price") and sg.get("target_price"):
                sg["ticket"] = prop_ticket(
                    sg["entry_price"], sg["stop_price"], sg["target_price"],
                    sg["direction"] == "long")
        except Exception:
            pass
    return {"signals": sigs}


@app.get("/api/prop/signals/hedge")
def api_prop_signals_hedge(limit: int = Query(20, ge=1, le=100)):
    """Recent HEDGE-book signals, re-sized to the eval account — the display-level
    crossover: if the hedge fires, this shows what taking the same levels on the
    eval would look like at the firm's fixed risk. Sizing only — these strategies
    are NOT in the eval backtest, so nothing here feeds the pass-rate math (the
    priced hybrid was rejected 2026-07-11 and stays rejected)."""
    from .prop_scan import prop_ticket
    sigs = [s for s in get_signals(limit=limit * 4)
            if not (s.get("signal_id") or "").startswith("prop-")][:limit]
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
def api_review_trades(book: str = None):
    return get_enriched_trades(book)


@app.get("/api/review/analytics")
def api_review_analytics(book: str = None, era: str = "current"):
    """book='hedge' | 'prop' (all prop attempts incl. archives) | omit for all books.
    era='current' (default, since review.ERA_START) | 'all' (lifetime)."""
    from .review import review_analytics
    return review_analytics(book, era=era)


@app.get("/api/review/equity")
def api_review_equity(book: str = None, era: str = "current"):
    from .review import equity_timing
    return equity_timing(book, era=era)


@app.get("/api/review/ohlcv")
def api_review_ohlcv():
    return get_ohlcv_1h()


@app.get("/api/review/indicators")
def api_review_indicators():
    from .review import get_indicators_1h
    return get_indicators_1h()


@app.get("/chart-review", response_class=HTMLResponse)
def chart_review_page(trade: Optional[int] = None, book: str = "hedge"):
    """Full-size chart review, pulled out of the journal modal — no room
    there for RSI/MACD/levels without squashing every pane unreadable."""
    from .chart_review_page import render
    return render(trade, book if book in ("hedge", "prop") else "hedge")


@app.get("/api/review/levels")
def api_review_levels():
    from .review import get_levels_1h
    return get_levels_1h()


@app.get("/api/stats/trades")
def api_stats_trades():
    """Realized stats from closed trades — feeds Monte Carlo + projection seeding."""
    return get_actual_stats()


# ─── LENS_EDGE_v3 setup engine (see strategies/LENS_EDGE_v3_ICT/FINDINGS.md) ──

@app.get("/hedge-desk", response_class=HTMLResponse)
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


@app.get("/assets/lightweight-charts.js")
def charts_js():
    """TradingView Lightweight Charts, vendored. /analytics pulled this from a
    CDN, which contradicted the no-network rule the rest of the app keeps — and
    a chart that fails to load offline takes the page's answer with it."""
    from fastapi.responses import FileResponse
    from .paths import CHARTS_JS
    return FileResponse(CHARTS_JS, media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=86400"})


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


@app.get("/manual", response_class=HTMLResponse)
def manual_page(doc: str = Query("readme", description="readme|plan|changelog|product|brand")):
    """The repo's markdown, rendered from disk on every request — a generated
    copy would be stale the next time CHANGELOG.md is appended to."""
    from .docs_page import render
    return render(doc)


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
