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
    upsert_exchange_trade,
    get_transfers, upsert_transfer,
    get_daily_snapshots,
    insert_signal, get_signals, get_signal, decide_signal, expire_stale_signals,
    get_last_non_rejected_signal_for_symbol,
    get_lens_config, upsert_lens_config,
)
from . import discipline
from .models import (
    GoalRequest, GoalResponse,
    PositionRequest, PositionResponse,
    TradeCreate, TradeUpdate, TradeResponse,
    SignalIngest, SignalDecision, SignalResponse,
)
from . import bybit_sync, kraken_sync


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


# ─── Projection (parameter-first "new method") ────────────────────────────────

@app.get("/projection", response_class=HTMLResponse)
def projection_page(
    start: float = Query(360,   description="Start balance €"),
    stop:  float = Query(1.0,   description="Stop — % price move"),
    tp:    float = Query(4.0,   description="Take profit — % price move"),
    lev:   float = Query(10.0,  description="Leverage"),
    wr:    float = Query(44.0,  description="Win rate %"),
    tpw:   float = Query(5.0,   description="Trades / week"),
    weeks: float = Query(26.0,  description="Horizon (weeks)"),
    btc:   float = Query(60000, description="BTC price € (for BTC equivalent)"),
    fee:   float = Query(0.30,  description="Fee % round trip (0.15%/side)"),
):
    def fmt_eur(v):
        if v is None:
            return "—"
        if abs(v) >= 1_000_000:
            return f"€{v/1_000_000:.2f}M"
        if abs(v) >= 10_000:
            return f"€{v/1000:.1f}k"
        return f"€{v:,.0f}"

    try:
        p = compute_projection(
            start_balance=start, stop_pct=stop/100, tp_pct=tp/100, leverage=lev,
            win_rate=wr/100, trades_per_week=tpw, weeks=weeks, btc_price_eur=btc,
            fee_roundtrip=fee/100,
        )
        err_html = ""
    except CalcError as e:
        p = None
        err_html = f"<div class='err'>{e}</div>"

    # ── Curve rows (the multicolour bands) ──────────────────────────────────
    curve_rows = ""
    if p:
        for r in p["curve"]:
            btc_cell = f"<td class='btc'>{r['btc_p50']:.4f}</td>" if r["btc_p50"] is not None else "<td>—</td>"
            curve_rows += (
                f"<tr><td>{r['week']}</td><td class='dim'>{r['trades']}</td>"
                f"<td class='p05'>{fmt_eur(r['p05'])}</td>"
                f"<td class='p25'>{fmt_eur(r['p25'])}</td>"
                f"<td class='p50'>{fmt_eur(r['p50'])}</td>"
                f"<td class='p75'>{fmt_eur(r['p75'])}</td>"
                f"<td class='p95'>{fmt_eur(r['p95'])}</td>"
                f"{btc_cell}</tr>"
            )

    # ── Win-rate sensitivity (proves WR is NOT the lever) ───────────────────
    wr_rows = ""
    for w in [30, 40, 44, 54, 60]:
        try:
            s = compute_projection(start_balance=start, stop_pct=stop/100, tp_pct=tp/100,
                                   leverage=lev, win_rate=w/100, trades_per_week=tpw,
                                   weeks=weeks, btc_price_eur=btc, fee_roundtrip=fee/100)
            dbl = f"{s['weeks_to_double']} wk" if s["weeks_to_double"] else "never"
            cls = "pos" if s["is_positive_ev"] else "neg"
            here = " ←" if abs(w - wr) < 0.5 else ""
            final = s["curve"][-1]["p50"]
            wr_rows += (f"<tr><td>{w}%{here}</td><td class='{cls}'>{s['per_trade_ev']:+.2f}%</td>"
                        f"<td>{dbl}</td><td>{fmt_eur(final)}</td><td>{s['risk_of_ruin']}%</td></tr>")
        except CalcError:
            wr_rows += f"<tr><td>{w}%</td><td colspan=4 class='dim'>invalid</td></tr>"

    # ── R sensitivity (proves R IS the lever — vary TP, stop fixed) ─────────
    r_rows = ""
    for tp_v in [2.0, 3.0, 4.0, 5.0]:
        try:
            s = compute_projection(start_balance=start, stop_pct=stop/100, tp_pct=tp_v/100,
                                   leverage=lev, win_rate=wr/100, trades_per_week=tpw,
                                   weeks=weeks, btc_price_eur=btc, fee_roundtrip=fee/100)
            dbl = f"{s['weeks_to_double']} wk" if s["weeks_to_double"] else "never"
            cls = "pos" if s["is_positive_ev"] else "neg"
            here = " ←" if abs(tp_v - tp) < 0.01 else ""
            final = s["curve"][-1]["p50"]
            r_rows += (f"<tr><td>{s['nominal_r']:.0f}R{here}</td><td class='{cls}'>{s['per_trade_ev']:+.2f}%</td>"
                       f"<td>{dbl}</td><td>{fmt_eur(final)}</td><td>{s['risk_of_ruin']}%</td></tr>")
        except CalcError:
            r_rows += f"<tr><td>{tp_v:.0f}%</td><td colspan=4 class='dim'>invalid</td></tr>"

    # ── Headline metrics ────────────────────────────────────────────────────
    if p:
        ev_cls = "pos" if p["is_positive_ev"] else "neg"
        ror_cls = "pos" if p["risk_of_ruin"] <= 5 else ("warn" if p["risk_of_ruin"] <= 20 else "neg")
        metrics = f"""
        <div class="card"><div class="n {ev_cls}">{p['per_trade_ev']:+.2f}%</div><div class="l">EV / trade</div></div>
        <div class="card"><div class="n">{p['actual_r']}R</div><div class="l">Actual R (after fees)</div></div>
        <div class="card"><div class="n">{p['weeks_to_double'] or '∞'}</div><div class="l">Weeks to double</div></div>
        <div class="card"><div class="n {ror_cls}">{p['risk_of_ruin']}%</div><div class="l">Ruin risk (−{int(p['max_drawdown'])}%)</div></div>
        <div class="card"><div class="n {('neg' if wr < p['breakeven_wr'] else 'pos')}">{p['breakeven_wr']}%</div><div class="l">Breakeven WR</div></div>
        <div class="card"><div class="n pos">{p['acct_gain_win']:+.0f}%</div><div class="l">Account / win</div></div>
        <div class="card"><div class="n neg">−{p['acct_loss_loss']:.0f}%</div><div class="l">Account / loss</div></div>
        <div class="card"><div class="n">{p['geometric_drift']:+.2f}%</div><div class="l">Geo growth / trade</div></div>
        """
    else:
        metrics = ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>LENS — projection</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{box-sizing:border-box}}
  body{{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#0c0c0d;color:#d4d4d4;margin:0;padding:24px;max-width:1100px;margin:0 auto}}
  h1{{font-size:26px;letter-spacing:.08em;margin:0 0 2px;color:#fff;font-weight:600}}
  h1 .v{{font-size:11px;opacity:.4;margin-left:10px}}
  a{{color:#7aa2f7;text-decoration:none}} a:hover{{text-decoration:underline}}
  h2{{font-size:11px;text-transform:uppercase;letter-spacing:.18em;color:#888;border-bottom:1px solid #272729;padding-bottom:6px;margin:26px 0 12px}}
  .strat{{background:#111112;border:1px solid #232325;border-left:3px solid #7aa2f7;border-radius:6px;padding:14px 18px;margin:14px 0 8px;font-size:12.5px;color:#bbb}}
  .strat b{{color:#fff}} .strat .one{{color:#a6c1ff;font-style:italic;display:block;margin-bottom:8px}}
  .strat ul{{margin:6px 0 0;padding-left:18px}} .strat li{{margin:3px 0}}
  form{{display:flex;flex-wrap:wrap;gap:10px;align-items:end;background:#111112;border:1px solid #232325;border-radius:6px;padding:12px 16px;margin:8px 0}}
  form .f{{display:flex;flex-direction:column;gap:3px}}
  form label{{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#888}}
  form input{{background:#0c0c0d;border:1px solid #2a2a2c;color:#fff;padding:5px 8px;border-radius:4px;font:inherit;font-size:12px;width:80px}}
  form input:focus{{outline:none;border-color:#7aa2f7}}
  button{{background:#293551;color:#a6c1ff;border:1px solid #3a4a72;padding:7px 16px;border-radius:4px;cursor:pointer;font:inherit;font-size:11px;text-transform:uppercase;letter-spacing:.1em}}
  button:hover{{background:#324063;color:#fff}}
  .status{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0}}
  @media(max-width:760px){{.status{{grid-template-columns:repeat(2,1fr)}}}}
  .card{{background:#161617;border:1px solid #272729;border-radius:6px;padding:12px 14px}}
  .card .n{{font-size:20px;color:#fff;font-weight:600;line-height:1}}
  .card .l{{font-size:9.5px;text-transform:uppercase;letter-spacing:.1em;color:#777;margin-top:6px}}
  table{{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}}
  th{{text-align:right;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#777;padding:6px 8px;border-bottom:1px solid #272729}}
  th:first-child,td:first-child{{text-align:left}}
  td{{text-align:right;padding:5px 8px;border-bottom:1px solid #1a1a1a}}
  td.dim,.dim{{color:#666}}
  .p05{{color:#f7768e}} .p25{{color:#e0af68}} .p50{{color:#fff;font-weight:600}} .p75{{color:#9ad68a}} .p95{{color:#9ece6a}}
  td.btc{{color:#f0a000}}
  .pos{{color:#9ece6a}} .neg{{color:#f7768e}} .warn{{color:#e0af68}}
  .two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} @media(max-width:760px){{.two{{grid-template-columns:1fr}}}}
  .note{{color:#777;font-size:11px;margin:6px 0}}
  .err{{background:#3b1d20;border:1px solid #6c3439;color:#f7768e;padding:10px 14px;border-radius:6px;margin:8px 0}}
</style></head><body>

<h1>LENS · PROJECTION<span class="v">parameter-first · <a href="/">← dashboard (goal-first)</a></span></h1>

<div class="strat">
  <span class="one">"I trade BTC perps on Kraken — with-trend, on the 4H chart — risking a fixed 10% of my account to make 40% (a 4R trade). My entire edge is holding winners to the full 4R instead of bailing early."</span>
  <b>The locked rules:</b>
  <ul>
    <li><b>Market / TF:</b> BTC perpetual futures, Kraken. 4-hour chart. Holds 1–3 days. Not scalping, not daily swing.</li>
    <li><b>Direction:</b> long or short — <b>only with the trend.</b> Never counter-trend.</li>
    <li><b>Risk (fixed):</b> 1% price stop = <b>10% of account</b> at 10x. Same 10% on every trade.</li>
    <li><b>Exit (this IS the edge):</b> take profit at +4% price = <b>+40% account = 4R.</b> Hands-off — set SL/TP, walk away. No closing early.</li>
    <li><b>Frequency:</b> ~1 trade/day max; 2–3 good setups a week. Most of the time, no trade.</li>
    <li><b>Not optimizing win rate.</b> 44% is fine. <b>R is the lever</b> — see the two tables below.</li>
  </ul>
</div>

<form method="get" action="/projection">
  <div class="f"><label>Start €</label><input name="start" type="number" step="any" value="{start:g}"></div>
  <div class="f"><label>Stop %</label><input name="stop" type="number" step="any" value="{stop:g}"></div>
  <div class="f"><label>TP %</label><input name="tp" type="number" step="any" value="{tp:g}"></div>
  <div class="f"><label>Leverage</label><input name="lev" type="number" step="any" value="{lev:g}"></div>
  <div class="f"><label>Win rate %</label><input name="wr" type="number" step="any" value="{wr:g}"></div>
  <div class="f"><label>Trades/wk</label><input name="tpw" type="number" step="any" value="{tpw:g}"></div>
  <div class="f"><label>Weeks</label><input name="weeks" type="number" step="any" value="{weeks:g}"></div>
  <div class="f"><label>BTC € </label><input name="btc" type="number" step="any" value="{btc:g}"></div>
  <div class="f"><label>Fee % RT</label><input name="fee" type="number" step="any" value="{fee:g}"></div>
  <button type="submit">Project →</button>
</form>
{err_html}

<div class="status">{metrics}</div>

<h2>Projected equity — percentile bands</h2>
<p class="note">Median (P50) is the expected path. P05 = unlucky (worst 5%), P95 = lucky. Spread = variance, not a forecast. BTC column converts the median at €{btc:,.0f}/BTC.</p>
<table>
  <tr><th>Week</th><th>Trades</th><th class="p05">P05</th><th class="p25">P25</th><th class="p50">Median</th><th class="p75">P75</th><th class="p95">P95</th><th>BTC (P50)</th></tr>
  {curve_rows}
</table>

<div class="two">
  <div>
    <h2>Win-rate sensitivity <span class="dim">(R held at {p['nominal_r'] if p else tp/stop:g}R)</span></h2>
    <p class="note">Win rate compounds hard too — but it's a <b>byproduct of entry quality</b>: slow to move, and below the breakeven WR you die. You don't chase it; you let better setups raise it over time.</p>
    <table>
      <tr><th>WR</th><th>EV/trade</th><th>Double</th><th>Final (P50)</th><th>Ruin</th></tr>
      {wr_rows}
    </table>
  </div>
  <div>
    <h2>R sensitivity <span class="dim">(WR held at {wr:g}%)</span></h2>
    <p class="note">Same horizon, WR fixed, only R moves. Just as explosive — and <b>R is the one you control</b>: it's an exit choice (hold to target vs. close early), fixable today. That's why it's "the lever".</p>
    <table>
      <tr><th>R</th><th>EV/trade</th><th>Double</th><th>Final (P50)</th><th>Ruin</th></tr>
      {r_rows}
    </table>
  </div>
</div>

<p class="note" style="margin-top:18px">⚠ <b>Read the shape, not the raw totals.</b> Over many trades, compounding produces absurd numbers (millions, hundreds of BTC) — those are arithmetic, not realistic outcomes: liquidity, position size, and your own psychology cap the real path. What's trustworthy here is the <b>early weeks, the EV/trade, the breakeven WR, and the ruin %</b>. It also assumes the win rate holds at a <b>1% stop</b> (unproven — history used wider stops) and ignores funding on multi-day holds. A model, not a promise. Validate via the <code>TREND_4R_v1</code> backtest first.</p>

</body></html>"""


# ─── Landing + health ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
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

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>LENS — dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{box-sizing:border-box}}
  body{{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#0c0c0d;color:#d4d4d4;margin:0;padding:24px;max-width:1100px;margin:0 auto}}
  h1{{font-size:28px;letter-spacing:.1em;margin:0 0 2px;color:#fff;font-weight:600}}
  h1 .v{{font-size:11px;opacity:.4;letter-spacing:.05em;margin-left:10px}}
  p.mission{{color:#888;border-left:2px solid #333;padding-left:12px;margin:12px 0 20px;font-size:12px}}
  h2{{font-size:11px;text-transform:uppercase;letter-spacing:.18em;color:#888;border-bottom:1px solid #272729;padding-bottom:6px;margin:28px 0 12px;display:flex;justify-content:space-between;align-items:end}}
  h2 .sub{{font-size:10px;opacity:.6;text-transform:none;letter-spacing:.05em}}
  a{{color:#7aa2f7;text-decoration:none}}
  a:hover{{text-decoration:underline}}

  /* Status cards */
  .status{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:8px}}
  .status .card{{background:#161617;border:1px solid #272729;border-radius:6px;padding:14px 16px}}
  .status .n{{font-size:24px;color:#fff;font-weight:600;line-height:1}}
  .status .l{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#777;margin-top:6px}}

  /* Two-column main */
  .main{{display:grid;grid-template-columns:340px 1fr;gap:16px;margin-top:8px}}
  @media (max-width:880px){{.main{{grid-template-columns:1fr}}}}

  /* Config form */
  .panel{{background:#111112;border:1px solid #232325;border-radius:6px;padding:14px 16px}}
  .panel .title{{font-size:11px;text-transform:uppercase;letter-spacing:.15em;color:#888;margin:-2px 0 12px;display:flex;justify-content:space-between;align-items:center}}
  .panel .title .saved{{font-size:10px;color:#9ece6a;opacity:0;transition:opacity .3s}}
  .panel .title .saved.show{{opacity:1}}
  .row{{display:grid;grid-template-columns:130px 1fr;gap:6px;align-items:center;margin-bottom:6px}}
  .row label{{font-size:11px;color:#999}}
  .row input{{background:#0c0c0d;border:1px solid #2a2a2c;color:#fff;padding:5px 8px;border-radius:4px;font:inherit;font-size:12px;width:100%}}
  .row input:focus{{outline:none;border-color:#7aa2f7}}
  .row input.err{{border-color:#f7768e}}
  .btnrow{{display:flex;gap:8px;margin-top:12px}}
  button{{background:#1a1a1c;color:#d4d4d4;border:1px solid #2a2a2c;padding:6px 14px;border-radius:4px;cursor:pointer;font:inherit;font-size:11px;text-transform:uppercase;letter-spacing:.1em}}
  button:hover{{background:#222224;color:#fff}}
  button.primary{{background:#293551;color:#a6c1ff;border-color:#3a4a72}}
  button.primary:hover{{background:#324063;color:#fff}}

  /* Result grid */
  .results{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}
  @media (max-width:560px){{.results{{grid-template-columns:1fr}}}}
  .results .panel{{padding:10px 14px}}
  .kv{{display:grid;grid-template-columns:1fr auto;gap:4px 12px;font-size:12px}}
  .kv .k{{color:#888}}
  .kv .v{{color:#fff;text-align:right;font-variant-numeric:tabular-nums}}
  .kv .v.dim{{color:#666}}
  .kv .v.pos{{color:#9ece6a}}
  .kv .v.neg{{color:#f7768e}}
  .kv .v.warn{{color:#e0af68}}

  .err{{background:#3b1d20;border:1px solid #6c3439;color:#f7768e;padding:10px 14px;border-radius:6px;margin-top:8px;font-size:12px}}
  .err.hide{{display:none}}

  /* Compact secondary sections */
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  table td{{padding:5px 0;border-bottom:1px solid #1d1d1f}}
  .ep{{display:grid;grid-template-columns:55px 1fr;gap:10px;padding:3px 0;border-bottom:1px solid #1a1a1a;font-size:12px}}
  .ep .m{{color:#bb9af7;font-weight:600;font-size:10px;padding-top:2px}}
  .ep .p{{color:#9ece6a}}
  .ep .d{{color:#666;font-size:11px}}
</style></head><body>

<h1>LENS<span class="v">v1.0.0-dev · :8765 · <a href="/projection">projection →</a></span></h1>
<p class="mission">Build the dataset that makes month-6 predictive scoring possible. Every Pine signal — taken or skipped — captured with locked schema, linked to exchange fills, outcome-attached.</p>

<div class="status">
  <div class="card"><div class="n">{len(trades)}</div><div class="l">Trades</div></div>
  <div class="card"><div class="n">{len(sigs)}</div><div class="l">Signals</div></div>
  <div class="card"><div class="n">{len(pending)}</div><div class="l">Pending decision</div></div>
</div>

<div class="main">

  <!-- ── Goal config form ─────────────────────────────────────────────── -->
  <div class="panel">
    <div class="title">Goal config <span class="saved" id="saved-pulse">saved ✓</span></div>
    <form id="goal-form" autocomplete="off">
      <div class="row"><label>Start balance €</label><input type="number" step="any" name="start_balance"></div>
      <div class="row"><label>Target balance €</label><input type="number" step="any" name="target_balance"></div>
      <div class="row"><label>Target date</label><input type="date" name="target_date"></div>
      <div class="row"><label>Trades / week</label><input type="number" step="any" name="trades_per_week"></div>
      <div class="row"><label>Win rate (0–1)</label><input type="number" step="0.01" min="0.01" max="0.99" name="win_rate"></div>
      <div class="row"><label>R:R ratio</label><input type="number" step="0.1" name="rr_ratio"></div>
      <div class="row"><label>Leverage</label><input type="number" step="any" name="leverage"></div>
      <div class="row"><label>Max drawdown</label><input type="number" step="0.01" min="0.01" max="0.99" name="max_drawdown_allowed"></div>
      <div class="row"><label>Losses allowed</label><input type="number" step="1" min="1" name="losses_allowed"></div>
      <div class="row"><label>Fractional Kelly</label><input type="number" step="0.01" min="0.01" max="1" name="fractional_kelly"></div>
      <div class="row"><label>ATR floor (opt)</label><input type="number" step="any" name="min_underlying_stop_pct" placeholder="null"></div>
      <div class="row"><label>BTC price € (opt)</label><input type="number" step="any" name="btc_price_eur" placeholder="null"></div>
      <div class="row"><label>BTC growth /mo</label><input type="number" step="0.01" name="btc_growth_monthly"></div>
      <div class="btnrow">
        <button type="button" class="primary" id="save-btn">Save</button>
        <button type="button" id="reset-btn">Reload</button>
      </div>
    </form>
    <div id="err" class="err hide"></div>
  </div>

  <!-- ── Goal results ─────────────────────────────────────────────────── -->
  <div>
    <div class="results">

      <div class="panel"><div class="title">Time to goal</div><div class="kv" id="r-time"></div></div>
      <div class="panel"><div class="title">Required growth</div><div class="kv" id="r-growth"></div></div>

      <div class="panel"><div class="title">Per-trade model</div><div class="kv" id="r-trade"></div></div>
      <div class="panel"><div class="title">Risk &amp; Kelly</div><div class="kv" id="r-risk"></div></div>

      <div class="panel"><div class="title">Account impact / trade</div><div class="kv" id="r-acct"></div></div>
      <div class="panel"><div class="title">Risk analytics</div><div class="kv" id="r-stats"></div></div>

      <div class="panel"><div class="title">Growth projections</div><div class="kv" id="r-proj"></div></div>
      <div class="panel"><div class="title">BTC / Monte Carlo</div><div class="kv" id="r-btc"></div></div>

    </div>
  </div>

</div>

<h2>Signals per strategy <span class="sub">→ <a href="/api/signals">/api/signals</a></span></h2>
<table>{strat_rows}</table>

<h2>API <span class="sub">interactive: <a href="/docs">/docs</a> · <a href="/redoc">/redoc</a></span></h2>
<div class="ep"><span class="m">GET</span><div><span class="p">/health</span> <span class="d">liveness</span></div></div>
<div class="ep"><span class="m">GET/PATCH</span><div><span class="p">/api/config</span> <span class="d">persisted goal inputs</span></div></div>
<div class="ep"><span class="m">POST</span><div><span class="p">/api/goal</span> <span class="d">EV-first goal model</span></div></div>
<div class="ep"><span class="m">POST</span><div><span class="p">/api/position</span> <span class="d">ATR-adaptive position sizing</span></div></div>
<div class="ep"><span class="m">GET</span><div><span class="p">/api/trades</span> <span class="d">venue/direction/result/period filters</span></div></div>
<div class="ep"><span class="m">POST</span><div><span class="p">/api/sync/kraken</span> <span class="d">background fill sync</span></div></div>
<div class="ep"><span class="m">POST</span><div><span class="p">/api/sync/bybit</span> <span class="d">closed-pnl sync</span></div></div>
<div class="ep"><span class="m">POST</span><div><span class="p">/api/signals</span> <span class="d">ingest Pine alert (locked schema)</span></div></div>
<div class="ep"><span class="m">POST</span><div><span class="p">/api/signals/&lt;id&gt;/decide</span> <span class="d">approve or reject</span></div></div>

<script>
const FORM     = document.getElementById("goal-form");
const ERR      = document.getElementById("err");
const SAVED    = document.getElementById("saved-pulse");
const SAVE_BTN = document.getElementById("save-btn");
const RESET    = document.getElementById("reset-btn");

const NUM_FIELDS = [
  "start_balance","target_balance","trades_per_week","win_rate","rr_ratio",
  "leverage","max_drawdown_allowed","losses_allowed","fractional_kelly",
  "execution_fill_factor","min_underlying_stop_pct","btc_price_eur","btc_growth_monthly"
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
  document.getElementById("r-time").innerHTML =
      row("Days remaining",    fmtInt(g.days_remaining))
    + row("Weeks remaining",   fmtNum(g.weeks_remaining))
    + row("Months remaining",  fmtNum(g.months_remaining))
    + row("Total interest",    fmtPct(g.total_interest));

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
    + row("Trades needed",      fmtInt(g.trades_needed))
    + row("Trades in window",   fmtInt(g.total_trades))
    + row("Trades to double",   g.trades_to_double != null ? fmtInt(g.trades_to_double) : "∞");

  document.getElementById("r-risk").innerHTML =
      row("Leverage",         fmtNum(g.leverage) + "×")
    + row("Full Kelly",       fmtPct(g.full_kelly))
    + row("Fractional Kelly", fmtPct(g.fractional_kelly))
    + row("Kelly risk",       fmtPct(g.kelly_risk))
    + row("DD constraint",    fmtPct(g.dd_risk_constraint))
    + row("Optimal risk",     fmtPct(g.optimal_risk_pct))
    + row("Used risk / trade", fmtPct(g.risk_per_trade), "warn")
    + row("DD-implied lev",   g.dd_implied_leverage != null ? fmtNum(g.dd_implied_leverage) + "×" : "—");

  document.getElementById("r-acct").innerHTML =
      row("Gain / win",   fmtPct(g.acct_gain_win),  "pos")
    + row("Loss / loss",  fmtPct(g.acct_loss_loss), "neg")
    + row("Geom drift",   fmtPct4(g.geometric_drift),
        g.geometric_drift > 0 ? "pos" : "neg")
    + row("Typical win (log)",   fmtPct(g.typical_win),  "pos")
    + row("Typical loss (log)",  fmtPct(g.typical_loss), "neg");

  document.getElementById("r-stats").innerHTML =
      row("Sharpe (per trade)", fmtNum(g.sharpe_ratio))
    + row("Profit factor",      g.profit_factor != null ? fmtNum(g.profit_factor) : "∞")
    + row("Trade volatility",   fmtPct(g.trade_volatility))
    + row("Risk of ruin",       fmtPct(g.risk_of_ruin) + " <span class='v dim'>(" + g.ror_label + ")</span>",
        g.risk_of_ruin <= 1 ? "pos" : g.risk_of_ruin <= 5 ? "warn" : "neg")
    + row("Losses to ruin",     fmtInt(g.losses_to_ruin))
    + row("Wins to breakeven",  fmtInt(g.wins_to_breakeven))
    + row("Weeks to goal (actual)", g.weeks_to_goal_actual != null ? fmtNum(g.weeks_to_goal_actual) : "∞");

  document.getElementById("r-proj").innerHTML =
      row("Weekly",    fmtEur(g.weekly_growth_eur))
    + row("Monthly",   fmtEur(g.monthly_growth_eur))
    + row("Quarterly", fmtEur(g.quarterly_growth_eur));

  let btc = row("BTC @ goal",  g.btc_price_at_goal != null ? fmtEur(g.btc_price_at_goal) : "<span class='v dim'>set BTC price</span>")
          + row("Target AUM",   g.target_aum_btc != null ? fmtNum(g.target_aum_btc) + " BTC" : "—")
          + row("MC p05", fmtEur(g.mc_p05), "neg")
          + row("MC p50", fmtEur(g.mc_p50))
          + row("MC p95", fmtEur(g.mc_p95), "pos");
  document.getElementById("r-btc").innerHTML = btc;

  ERR.classList.add("hide");
}}

async function recompute() {{
  const body = readForm();
  // /api/goal requires non-null values for these
  const required = ["start_balance","target_balance","target_date","trades_per_week","win_rate","rr_ratio","leverage"];
  for (const r of required) {{
    if (body[r] === null) {{ ERR.textContent = "Missing required: " + r; ERR.classList.remove("hide"); return; }}
  }}
  // Strip null fields so server-side defaults apply
  const payload = {{}};
  for (const k in body) if (body[k] !== null) payload[k] = body[k];

  try {{
    const r = await fetch("/api/goal", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }});
    if (!r.ok) {{
      const d = await r.json();
      ERR.textContent = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
      ERR.classList.remove("hide");
      return;
    }}
    const g = await r.json();
    render(g);
  }} catch (e) {{
    ERR.textContent = "Network: " + e.message;
    ERR.classList.remove("hide");
  }}
}}

// Debounced recompute on form input change
let debounce;
FORM.addEventListener("input", () => {{
  clearTimeout(debounce);
  debounce = setTimeout(recompute, 250);
}});

SAVE_BTN.addEventListener("click", async () => {{
  const body = readForm();
  const r = await fetch("/api/config", {{
    method: "PATCH",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(body),
  }});
  if (r.ok) {{
    SAVED.classList.add("show");
    setTimeout(() => SAVED.classList.remove("show"), 1500);
  }}
}});

RESET.addEventListener("click", async () => {{
  const cfg = await fetch("/api/config").then(r => r.json());
  populate(cfg);
  recompute();
}});

// Boot
(async () => {{
  const cfg = await fetch("/api/config").then(r => r.json());
  populate(cfg);
  recompute();
}})();
</script>

</body></html>"""


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
            risk_per_trade=req.risk_per_trade,
        )
        return compute_position(
            req.entry_price, req.direction,
            req.balance_eur, req.btc_price_eur, goal,
            btc_std_dev=req.btc_std_dev,
        )
    except CalcError as e:
        raise HTTPException(status_code=422, detail=str(e))


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


def _run_kraken_sync(account: str, api_key: str, api_secret: str, last_fill_time):
    _kraken_sync_status[account] = {"running": True}
    try:
        result = kraken_sync.sync_account(
            api_key, api_secret,
            db_upsert_fn=upsert_exchange_trade,
            db_transfer_fn=upsert_transfer,
            last_fill_time=last_fill_time,
        )
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
        last_fill_time=req.last_fill_time,
    )
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
    risk_per_trade:          Optional[float] = None     # null = let kelly/dd decide
    min_underlying_stop_pct: Optional[float] = None     # null = no ATR floor
    btc_price_eur:           Optional[float] = None
    btc_growth_monthly:      Optional[float] = None


@app.get("/api/config")
def get_config():
    return get_lens_config()


@app.patch("/api/config")
def patch_config(data: ConfigUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        return get_lens_config()
    return upsert_lens_config(updates)


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
    return {"signals": get_signals(status=status, strategy=strategy, limit=limit)}


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
