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
    tp:    float = Query(5.5,   description="Take profit — % price move (5.5% → actual 4R after 0.30% fee)"),
    lev:   float = Query(10.0,  description="Leverage"),
    wr:    float = Query(44.0,  description="Win rate %"),
    tpw:   float = Query(5.0,   description="Trades / week"),
    weeks: float = Query(26.0,  description="Horizon (weeks)"),
    btc:   float = Query(60000, description="BTC price € (for BTC equivalent)"),
    fee:   float = Query(0.30,  description="Fee % round trip (0.15%/side)"),
):
    import math

    # ── helpers ──────────────────────────────────────────────────────────────────
    def fmt_eur(v):
        if v is None: return "—"
        if abs(v) >= 1_000_000: return f"€{v/1_000_000:.2f}M"
        if abs(v) >= 10_000: return f"€{v/1000:.1f}k"
        return f"€{v:,.0f}"

    # ── compute ──────────────────────────────────────────────────────────────────
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

    # ── SVG sparkline (log-scale equity bands) ───────────────────────────────────
    def make_sparkline(curve):
        if not curve or len(curve) < 2: return ""
        min_v = max(1.0, min(r["p05"] for r in curve if r["p05"] > 0))
        max_v = max(r["p95"] for r in curve)
        lmin = math.log(min_v); lmax = math.log(max_v); lr = lmax - lmin or 1
        mw = curve[-1]["week"]
        W, H, gx, gy = 880, 148, 6, 8
        def xc(w): return round(gx + w / mw * (W - 2 * gx), 1)
        def yc(v): return round(H - gy - (math.log(max(1.0, v)) - lmin) / lr * (H - 2 * gy), 1)
        def pd(k): return "M " + " L ".join(f"{xc(r['week'])} {yc(r[k])}" for r in curve)
        fwd = " L ".join(f"{xc(r['week'])} {yc(r['p95'])}" for r in curve)
        bwd = " L ".join(f"{xc(r['week'])} {yc(r['p05'])}" for r in reversed(curve))
        lbls = ""
        for i, r in enumerate(curve):
            if i in (0, len(curve) // 2, len(curve) - 1):
                lbls += f'<text x="{xc(r["week"])}" y="{yc(r["p50"]) - 7}" text-anchor="middle" fill="#444" font-size="9">{fmt_eur(r["p50"])}</text>'
        return (
            f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:128px;display:block">'
            f'<path id="sband" d="M {fwd} L {bwd} Z" fill="#7aa2f7" opacity="0.07" style="display:none"/>'
            f'<path id="sp05" d="{pd("p05")}" stroke="#f7768e" stroke-width="1" fill="none" stroke-dasharray="5 3" opacity="0.65" style="display:none"/>'
            f'<path id="sp25" d="{pd("p25")}" stroke="#e0af68" stroke-width="1" fill="none" opacity="0.4" style="display:none"/>'
            f'<path id="sp75" d="{pd("p75")}" stroke="#9ad68a" stroke-width="1" fill="none" opacity="0.4" style="display:none"/>'
            f'<path id="sp95" d="{pd("p95")}" stroke="#9ece6a" stroke-width="1" fill="none" stroke-dasharray="5 3" opacity="0.65" style="display:none"/>'
            f'<path id="sp50" d="{pd("p50")}" stroke="#fff" stroke-width="2.5" fill="none"/>'
            f'{lbls}</svg>'
        )

    sparkline = make_sparkline(p["curve"]) if p else ""

    # ── Curve rows ───────────────────────────────────────────────────────────────
    curve_rows = ""
    if p:
        for i, r in enumerate(p["curve"]):
            btc_c = f"<td class='btc'>{r['btc_p50']:.4f}</td>" if r["btc_p50"] else "<td class='dim'>—</td>"
            rc = " class='alt'" if i % 2 else ""
            curve_rows += (
                f"<tr{rc}><td>{r['week']}w</td><td class='dim'>{r['trades']}</td>"
                f"<td class='p05'>{fmt_eur(r['p05'])}</td>"
                f"<td class='p25'>{fmt_eur(r['p25'])}</td>"
                f"<td class='p50'>{fmt_eur(r['p50'])}</td>"
                f"<td class='p75'>{fmt_eur(r['p75'])}</td>"
                f"<td class='p95'>{fmt_eur(r['p95'])}</td>"
                f"{btc_c}</tr>"
            )

    # ── R-target sensitivity (actual R after fees) ───────────────────────────────
    r_target_rows = ""
    cur_ar = p["actual_r"] if p else 0.0
    for tgt_r in [2.0, 3.0, 4.0, 5.0, 6.0]:
        tp_f = tgt_r * (stop / 100 + fee / 100) + fee / 100
        tp_pct_v = tp_f * 100
        nom_r_v = tp_pct_v / stop
        is_cur = abs(tgt_r - cur_ar) < 0.3
        mark = " ←" if is_cur else ""
        hl = " class='cur-row'" if is_cur else ""
        try:
            s = compute_projection(
                start_balance=start, stop_pct=stop / 100, tp_pct=tp_f,
                leverage=lev, win_rate=wr / 100, trades_per_week=tpw,
                weeks=weeks, btc_price_eur=btc, fee_roundtrip=fee / 100,
            )
            dbl = f"{s['weeks_to_double']:.0f}w" if s["weeks_to_double"] else "never"
            ec = "pos" if s["is_positive_ev"] else "neg"
            rc2 = "pos" if s["risk_of_ruin"] <= 10 else "neg"
            r_target_rows += (
                f"<tr{hl}><td><b>{tgt_r:.0f}R actual</b>{mark}</td>"
                f"<td class='dim'>{nom_r_v:.1f}R nom · {tp_pct_v:.1f}% TP</td>"
                f"<td class='{ec}'>{s['per_trade_ev']:+.2f}%</td>"
                f"<td>{s['geometric_drift']:+.2f}%</td>"
                f"<td>{dbl}</td>"
                f"<td>{fmt_eur(s['curve'][-1]['p50'])}</td>"
                f"<td class='{rc2}'>{s['risk_of_ruin']}%</td></tr>"
            )
        except CalcError:
            r_target_rows += f"<tr><td>{tgt_r:.0f}R actual</td><td colspan='6' class='dim'>invalid</td></tr>"

    # ── Win-rate sensitivity ──────────────────────────────────────────────────────
    wr_rows = ""
    for w in [30, 40, 44, 50, 55, 60]:
        is_here = abs(w - wr) < 0.5
        mark = " ←" if is_here else ""
        hl = " class='cur-row'" if is_here else ""
        try:
            s = compute_projection(
                start_balance=start, stop_pct=stop / 100, tp_pct=tp / 100,
                leverage=lev, win_rate=w / 100, trades_per_week=tpw,
                weeks=weeks, btc_price_eur=btc, fee_roundtrip=fee / 100,
            )
            dbl = f"{s['weeks_to_double']:.0f}w" if s["weeks_to_double"] else "never"
            ec = "pos" if s["is_positive_ev"] else "neg"
            rc2 = "pos" if s["risk_of_ruin"] <= 10 else "neg"
            wr_rows += (
                f"<tr{hl}><td>{w}%{mark}</td>"
                f"<td class='{ec}'>{s['per_trade_ev']:+.2f}%</td>"
                f"<td>{s['geometric_drift']:+.2f}%</td>"
                f"<td>{dbl}</td>"
                f"<td>{fmt_eur(s['curve'][-1]['p50'])}</td>"
                f"<td class='{rc2}'>{s['risk_of_ruin']}%</td></tr>"
            )
        except CalcError:
            wr_rows += f"<tr><td>{w}%</td><td colspan='5' class='dim'>invalid</td></tr>"

    # ── Hero metric cards ─────────────────────────────────────────────────────────
    if p:
        ar = p["actual_r"]
        r_cls   = "pos"  if ar >= 3.5 else ("warn" if ar >= 2.5 else "neg")
        ev_cls  = "pos"  if p["is_positive_ev"] else "neg"
        ror_cls = "pos"  if p["risk_of_ruin"] <= 5 else ("warn" if p["risk_of_ruin"] <= 20 else "neg")
        bwrm    = round(wr - p["breakeven_wr"], 1)
        bwr_cls = "pos"  if bwrm > 0 else "neg"
        wtd     = f"{p['weeks_to_double']:.0f}w" if p["weeks_to_double"] else "∞"
        ttd     = f"{p['trades_to_double']:.0f}" if p["trades_to_double"] else "∞"
        cards = (
            f'<div class="hcard {r_cls}">'
            f'<div class="hbig">{ar}R</div>'
            f'<div class="hlbl">Actual R (after fees)</div>'
            f'<div class="hsub">Nom {p["nominal_r"]:.1f}R · TP {tp:g}% · SL {stop:g}%</div></div>'

            f'<div class="hcard {ev_cls}">'
            f'<div class="hbig">{p["per_trade_ev"]:+.2f}%</div>'
            f'<div class="hlbl">EV / trade</div>'
            f'<div class="hsub">Geo drift {p["geometric_drift"]:+.2f}% per trade</div></div>'

            f'<div class="hcard neutral">'
            f'<div class="hbig">+{p["acct_gain_win"]:.0f}% / −{p["acct_loss_loss"]:.0f}%</div>'
            f'<div class="hlbl">Win / Loss on account</div>'
            f'<div class="hsub">{lev:g}× lev · breakeven {p["breakeven_wr"]}% WR</div></div>'

            f'<div class="hcard neutral">'
            f'<div class="hbig">{wtd}</div>'
            f'<div class="hlbl">Weeks to double</div>'
            f'<div class="hsub">{ttd} trades to 2×</div></div>'

            f'<div class="hcard {ror_cls}">'
            f'<div class="hbig">{p["risk_of_ruin"]}%</div>'
            f'<div class="hlbl">Ruin risk (−{int(p["max_drawdown"])}% DD)</div>'
            f'<div class="hsub">{round(tpw * weeks)} trades · {weeks:g} weeks</div></div>'

            f'<div class="hcard {bwr_cls}">'
            f'<div class="hbig">{p["breakeven_wr"]}%</div>'
            f'<div class="hlbl">Breakeven win rate</div>'
            f'<div class="hsub">You\'re at {wr:g}% · margin {bwrm:+.1f}pp</div></div>'
        )
    else:
        cards = ""

    # ── Monte Carlo final percentiles ─────────────────────────────────────────────
    mc_html = ""
    if p and p["curve"]:
        final = p["curve"][-1]
        mc_items = [
            ("P05 · worst 5%", fmt_eur(final["p05"]), "neg"),
            ("P25",             fmt_eur(final["p25"]), "warn"),
            ("P50 · median",   fmt_eur(final["p50"]), ""),
            ("P75",             fmt_eur(final["p75"]), "mc75"),
            ("P95 · best 5%",  fmt_eur(final["p95"]), "mc95"),
        ]
        mc_cards_html = "".join(
            f'<div class="mc-card"><div class="mc-n {c}">{v}</div><div class="mc-l">{l}</div></div>'
            for l, v, c in mc_items
        )
        mc_html = (
            f'<p class="note">Log-normal simulation · {round(tpw * weeks)} trades · {weeks:g}w horizon. '
            f'WR {wr:g}% · {lev:g}× · {p["actual_r"]}R actual.</p>'
            f'<div class="mc-grid">{mc_cards_html}</div>'
        )

    wr_r_label = f"{p['actual_r']}R actual" if p else f"{tp:g}% TP"

    # ── CSS ───────────────────────────────────────────────────────────────────────
    CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;background:#09090b;color:#c9c9c9;padding:20px 24px}
.wrap{max-width:1140px;margin:0 auto}
a{color:#7aa2f7;text-decoration:none}a:hover{text-decoration:underline}
.hdr{display:flex;align-items:baseline;gap:10px;margin-bottom:16px}
.hdr h1{font-size:20px;letter-spacing:.08em;color:#fff;font-weight:700}
.hdr .v{font-size:11px;color:#444}
h2{font-size:9.5px;text-transform:uppercase;letter-spacing:.2em;color:#444;border-bottom:1px solid #1a1a1c;padding-bottom:5px;margin:26px 0 10px}
.strat{background:#0d0d0f;border:1px solid #1a1a1c;border-left:3px solid #7aa2f7;border-radius:8px;padding:14px 18px;margin:10px 0 14px}
.strat .tl{color:#a6c1ff;font-style:italic;font-size:12.5px;display:block;margin-bottom:10px}
.strat ul{padding-left:18px;list-style:disc}
.strat li{margin:3px 0;color:#888;font-size:12px}
.strat b{color:#ddd}
.param-form{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;background:#0d0d0f;border:1px solid #1a1a1c;border-radius:8px;padding:11px 14px;margin:10px 0}
.pf{display:flex;flex-direction:column;gap:3px}
.pf label{font-size:9px;text-transform:uppercase;letter-spacing:.13em;color:#444}
.pf input{background:#09090b;border:1px solid #222224;color:#e0e0e0;padding:6px 9px;border-radius:5px;font:inherit;font-size:12.5px;width:80px;transition:border-color .15s}
.pf input:focus{outline:none;border-color:#7aa2f7}
.pf input.calc-on{border-color:#e0af68 !important;color:#e0af68}
.proj-btn{background:#141d2e;color:#7aa2f7;border:1px solid #243658;padding:8px 16px;border-radius:5px;cursor:pointer;font:inherit;font-size:11px;text-transform:uppercase;letter-spacing:.12em;transition:all .15s;align-self:flex-end}
.proj-btn:hover{background:#1c2940;color:#c0d5ff}
.calc-hint{font-size:9.5px;color:#2e2e30;align-self:flex-end;padding-bottom:10px}
.hero{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}
@media(max-width:800px){.hero{grid-template-columns:repeat(2,1fr)}}
.hcard{background:#0d0d0f;border:1px solid #1a1a1c;border-radius:8px;padding:13px 15px;position:relative;overflow:hidden}
.hcard::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:8px 8px 0 0}
.hcard.pos::after{background:linear-gradient(90deg,#9ece6a,#73daca)}
.hcard.neg::after{background:linear-gradient(90deg,#f7768e,#e06060)}
.hcard.warn::after{background:linear-gradient(90deg,#e0af68,#ff9e64)}
.hcard.neutral::after{background:linear-gradient(90deg,#7aa2f7,#bb9af7)}
.hbig{font-size:24px;font-weight:700;color:#fff;line-height:1;margin-top:4px}
.hlbl{font-size:9px;text-transform:uppercase;letter-spacing:.13em;color:#444;margin-top:9px}
.hsub{font-size:11px;color:#3a3a3c;margin-top:4px}
.chart-wrap{background:#0d0d0f;border:1px solid #1a1a1c;border-radius:8px;padding:12px 14px;margin:0 0 8px}
.chart-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:7px}
.chart-legend span{font-size:10px;color:#555;display:flex;align-items:center;gap:5px}
.dot{display:inline-block;width:14px;height:2px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:780px){.two{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}
th{text-align:right;font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:#444;padding:6px 8px;border-bottom:1px solid #1a1a1c}
th:first-child,td:first-child{text-align:left}
td{text-align:right;padding:5px 8px;border-bottom:1px solid #111113}
tr.alt td{background:#0b0b0d}
tr.cur-row td{background:#121624}
tr.cur-row td:first-child{border-left:2px solid #7aa2f7}
.dim{color:#3a3a3c}
.p05{color:#f7768e}.p25{color:#e0af68}.p50{color:#fff;font-weight:600}.p75{color:#9ad68a}.p95{color:#9ece6a}
.btc{color:#f0a000}
.pos{color:#9ece6a}.neg{color:#f7768e}.warn{color:#e0af68}
.mc-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:8px 0 0}
@media(max-width:780px){.mc-grid{grid-template-columns:repeat(3,1fr)}}
.mc-card{background:#0d0d0f;border:1px solid #1a1a1c;border-radius:7px;padding:11px 12px;text-align:center}
.mc-n{font-size:15px;font-weight:600;color:#fff}
.mc-n.neg{color:#f7768e}.mc-n.warn{color:#e0af68}.mc-n.mc75{color:#9ad68a}.mc-n.mc95{color:#9ece6a}
.mc-l{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:#444;margin-top:5px}
.bt-empty{text-align:center;padding:36px 20px;color:#2a2a2c;border:1px dashed #1e1e20;border-radius:8px;margin:8px 0}
.bt-empty .ico{font-size:22px;margin-bottom:8px}
.bt-empty b{color:#3a3a3c}
.bt-empty p{font-size:11px;margin-top:5px;line-height:1.7;color:#2a2a2c}
.note{color:#444;font-size:11px;margin:5px 0 10px;line-height:1.6}
.note b{color:#666}
.note code{background:#111113;padding:1px 5px;border-radius:3px;color:#777}
.err{background:#1e0d0f;border:1px solid #4a1e22;color:#f7768e;padding:10px 14px;border-radius:6px;margin:8px 0}
.leg-btn{background:none;border:none;cursor:pointer;font:inherit;font-size:10px;display:flex;align-items:center;gap:5px;padding:2px 5px;border-radius:3px;transition:opacity .15s}
.leg-btn:hover{opacity:1 !important}
"""

    # ── JS ────────────────────────────────────────────────────────────────────────
    JS = r"""
// calculator for projection form — type 300*0.1 → Enter → 30
document.querySelectorAll('.pf input').forEach(function(inp) {
  function tryCalc() {
    var v = inp.value.trim();
    if (!v) return;
    try {
      var expr = v.replace(/[^0-9+\-*/.() \t]/g, '');
      var r = Function('"use strict";return(' + expr + ')')();
      if (isFinite(r)) { inp.value = parseFloat(r.toFixed(8)); inp.classList.remove('calc-on'); }
    } catch(e) {}
  }
  inp.addEventListener('input', function() { inp.classList.toggle('calc-on', /[+*\/]/.test(inp.value)); });
  inp.addEventListener('blur', tryCalc);
  inp.addEventListener('keydown', function(e) { if (e.key === 'Enter') { tryCalc(); e.preventDefault(); } });
});

// percentile band toggle
function toggleBand(id, btn) {
  var el = document.getElementById(id);
  if (!el) return;
  var show = el.style.display === 'none';
  el.style.display = show ? '' : 'none';
  btn.style.opacity = show ? '1' : '0.35';
  var p05 = document.getElementById('sp05');
  var p95 = document.getElementById('sp95');
  var fill = document.getElementById('sband');
  if (fill && p05 && p95) {
    fill.style.display = (p05.style.display !== 'none' || p95.style.display !== 'none') ? '' : 'none';
  }
}
"""

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>LENS · PROJECTION</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style>
</head><body><div class="wrap">

<div class="hdr">
  <h1>LENS · PROJECTION</h1>
  <span class="v">parameter-first · <a href="/">← dashboard (goal-first)</a></span>
</div>

<div class="strat">
  <span class="tl">"I trade BTC perps on Kraken — with-trend, 4H chart — risking a fixed 10% of my account to make 40%+. My entire edge is holding winners to the full target instead of bailing early."</span>
  <b>TREND_4R_v1 — locked rules:</b>
  <ul>
    <li><b>Market / TF:</b> BTC perpetual futures, Kraken. 4H chart. Holds 1–3 days.</li>
    <li><b>Direction:</b> long or short — <b>only with the trend.</b> Never counter-trend.</li>
    <li><b>Risk (fixed):</b> 1% price stop = <b>10% of account</b> at 10×. Same risk every trade.</li>
    <li><b>Exit (this IS the edge):</b> 5.5% TP → <b>+52% account → 4R actual</b> after 0.30% round-trip fee. Set it and walk away.</li>
    <li><b>Frequency:</b> ~2–5 trades/week. Most of the time, <em>no trade</em>.</li>
    <li><b>Not chasing WR.</b> 44% is fine. <b>R is the lever</b> — see the sensitivity tables below.</li>
  </ul>
</div>

<form class="param-form" method="get" action="/projection">
  <div class="pf"><label>Start €</label><input name="start" value="{start:g}"></div>
  <div class="pf"><label>Stop %</label><input name="stop" value="{stop:g}"></div>
  <div class="pf"><label>TP %</label><input name="tp" value="{tp:g}"></div>
  <div class="pf"><label>Leverage</label><input name="lev" value="{lev:g}"></div>
  <div class="pf"><label>Win rate %</label><input name="wr" value="{wr:g}"></div>
  <div class="pf"><label>Trades / wk</label><input name="tpw" value="{tpw:g}"></div>
  <div class="pf"><label>Weeks</label><input name="weeks" value="{weeks:g}"></div>
  <div class="pf"><label>BTC €</label><input name="btc" value="{btc:g}"></div>
  <div class="pf"><label>Fee % RT</label><input name="fee" value="{fee:g}"></div>
  <button class="proj-btn" type="submit">Project →</button>
  <span class="calc-hint">Tip: type 300*0.1 in any field → Enter</span>
</form>
{err_html}

<div class="hero">{cards}</div>

<h2>Equity projection — percentile bands (log scale)</h2>
<div class="chart-wrap">
  {sparkline}
  <div class="chart-legend">
    <button class="leg-btn" onclick="toggleBand('sp05',this)" style="color:#f7768e;opacity:0.35"><span class="dot" style="background:#f7768e"></span>P05 worst</button>
    <button class="leg-btn" onclick="toggleBand('sp25',this)" style="color:#e0af68;opacity:0.35"><span class="dot" style="background:#e0af68"></span>P25</button>
    <button class="leg-btn" onclick="toggleBand('sp50',this)" style="color:#fff"><span class="dot" style="background:#fff;height:2.5px"></span>P50 median</button>
    <button class="leg-btn" onclick="toggleBand('sp75',this)" style="color:#9ad68a;opacity:0.35"><span class="dot" style="background:#9ad68a"></span>P75</button>
    <button class="leg-btn" onclick="toggleBand('sp95',this)" style="color:#9ece6a;opacity:0.35"><span class="dot" style="background:#9ece6a"></span>P95 best</button>
  </div>
</div>
<p class="note"><b>P50</b> = expected median path · <b>P05</b> = worst 5% · <b>P95</b> = best 5%. Spread is variance, not a forecast.</p>
<table>
  <tr><th>Week</th><th>Trades</th><th class="p05">P05</th><th class="p25">P25</th><th class="p50">Median</th><th class="p75">P75</th><th class="p95">P95</th><th>BTC (P50)</th></tr>
  {curve_rows}
</table>

<div class="two" style="margin-top:20px">
  <div>
    <h2>R-target scenarios <span class="dim">(WR {wr:g}% · SL {stop:g}% · fee {fee:g}% RT)</span></h2>
    <p class="note">What TP% gives you each <b>actual R after fees</b>. R is the one lever you fully control — it's an exit discipline, not a market outcome. ← = current params.</p>
    <table>
      <tr><th>Target R</th><th>Params</th><th>EV/trade</th><th>Geo drift</th><th>To 2×</th><th>Final P50</th><th>Ruin</th></tr>
      {r_target_rows}
    </table>
  </div>
  <div>
    <h2>Win-rate sensitivity <span class="dim">(R held at {wr_r_label})</span></h2>
    <p class="note">WR is a <b>byproduct of entry quality</b> — hard to control directly. Below breakeven WR you lose money regardless of R. Better setups raise it over time.</p>
    <table>
      <tr><th>WR</th><th>EV/trade</th><th>Geo drift</th><th>To 2×</th><th>Final P50</th><th>Ruin</th></tr>
      {wr_rows}
    </table>
  </div>
</div>

<h2>Monte Carlo — final distribution at {weeks:g} weeks</h2>
{mc_html}

<h2>Backtest tracker</h2>
<div class="bt-empty">
  <div class="ico">📋</div>
  <b>No backtest data yet</b>
  <p>Run <code>TREND_4R_v1</code> on TradingView → export CSV → paste results here to validate the 44% WR assumption at a 1% stop / 5.5% TP on the 4H BTC chart.</p>
  <p>Fields: date · direction · entry · SL hit / TP hit · hold time · R achieved</p>
</div>

<p class="note" style="margin-top:20px">⚠ <b>Read the shape, not the raw totals.</b> Compounding over many trades produces absurd numbers — those are arithmetic, not realistic outcomes. Liquidity, position limits, and psychology cap the real path. Trust the <b>early weeks, EV/trade, breakeven WR, and ruin %</b>. Assumes win rate holds at a 1% stop (unproven) and ignores funding on multi-day holds. A model, not a promise. Validate via <code>TREND_4R_v1</code> backtest first.</p>

</div><script>{JS}</script></body></html>"""


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
<title>LENS</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  :root{{
    --bg:#08080a;--s1:#0f0f12;--s2:#141418;--s3:#1c1c22;
    --b1:#1e1e26;--b2:#28282e;--b3:#36363e;
    --t1:#eaeaee;--t2:#72728a;--t3:#3c3c48;--t4:#26262e;
    --ac:#5b8ef7;--adim:#121c36;
    --gr:#38c068;--re:#e8445a;--am:#e8a23d;
    --mono:'SF Mono',ui-monospace,'Cascadia Code',monospace;
    --ui:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  }}
  body{{font-family:var(--ui);font-size:13px;line-height:1.5;background:var(--bg);color:var(--t1);-webkit-font-smoothing:antialiased}}
  .app{{max-width:1180px;margin:0 auto;padding:0 22px 60px}}
  a{{color:var(--ac);text-decoration:none}}
  a:hover{{text-decoration:underline}}
  /* ─ topbar ─ */
  .topbar{{display:flex;align-items:center;justify-content:space-between;padding:18px 0 16px;border-bottom:1px solid var(--b1);margin-bottom:22px}}
  .brand{{display:flex;align-items:baseline;gap:11px}}
  .brand-name{{font-family:var(--mono);font-size:16px;font-weight:700;color:#fff;letter-spacing:.12em}}
  .brand-name b{{color:var(--ac)}}
  .brand-meta{{font-family:var(--mono);font-size:10px;color:var(--t3)}}
  .topnav{{display:flex;gap:2px}}
  .topnav a{{font-size:12px;color:var(--t2);text-decoration:none;padding:5px 10px;border-radius:5px;letter-spacing:.01em;transition:all .12s}}
  .topnav a:hover{{color:var(--t1);background:var(--s2);text-decoration:none}}
  .topnav a.cur{{color:var(--ac);background:var(--adim)}}
  /* ─ strip ─ */
  .strip{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:20px}}
  .sc{{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:13px 16px}}
  .sc-n{{font-family:var(--mono);font-size:24px;font-weight:600;color:#fff;line-height:1}}
  .sc-l{{font-size:9.5px;font-weight:600;text-transform:uppercase;letter-spacing:.16em;color:var(--t3);margin-top:6px}}
  /* ─ main ─ */
  .main{{display:grid;grid-template-columns:248px 1fr;gap:14px;align-items:start}}
  @media(max-width:820px){{.main{{grid-template-columns:1fr}}}}
  /* ─ sidebar ─ */
  .sidebar{{position:sticky;top:16px}}
  .panel{{background:var(--s1);border:1px solid var(--b1);border-radius:10px;overflow:hidden}}
  .panel-hd{{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--b1)}}
  .panel-title{{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.2em;color:var(--t2)}}
  .saved{{font-size:10px;color:var(--gr);opacity:0;transition:opacity .3s}}
  .saved.show{{opacity:1}}
  .fsec{{padding:10px 14px;border-bottom:1px solid var(--b1)}}
  .fsec-lbl{{font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:.22em;color:var(--t4);margin-bottom:7px}}
  .frow{{display:grid;grid-template-columns:1fr 90px;gap:3px 6px;align-items:center;margin-bottom:4px}}
  .frow:last-child{{margin-bottom:0}}
  .frow label{{font-size:11px;color:var(--t2)}}
  .frow input{{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 8px;border-radius:5px;font-family:var(--mono);font-size:11.5px;width:100%;transition:border-color .12s}}
  .frow input:focus{{outline:none;border-color:var(--ac)}}
  .frow input.cx{{border-color:var(--am)!important;color:var(--am)}}
  .frow input[type=date]{{font-family:var(--ui);font-size:11px}}
  .factns{{padding:10px 14px;display:flex;gap:7px;align-items:center}}
  .btn{{padding:6px 13px;border-radius:5px;border:1px solid var(--b2);background:var(--s2);color:var(--t2);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;cursor:pointer;font-family:inherit;transition:all .12s}}
  .btn:hover{{color:var(--t1);border-color:var(--b3)}}
  .btn.p{{background:var(--adim);color:var(--ac);border-color:#1e2e54}}
  .btn.p:hover{{background:#172448;color:#82b4ff}}
  .calc-tip{{font-size:9px;color:var(--t4);font-family:var(--mono)}}
  /* ─ metrics ─ */
  .metrics{{display:flex;flex-direction:column;gap:10px}}
  .hero{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
  @media(max-width:960px){{.hero{{grid-template-columns:repeat(2,1fr)}}}}
  .hcard{{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 15px;position:relative;overflow:hidden}}
  .hcard::after{{content:'';position:absolute;top:0;left:0;right:0;height:2px}}
  .hcard.pos::after{{background:linear-gradient(90deg,var(--gr),#73daca)}}
  .hcard.neg::after{{background:linear-gradient(90deg,var(--re),#c04060)}}
  .hcard.warn::after{{background:linear-gradient(90deg,var(--am),#ff9e64)}}
  .hcard.blue::after{{background:linear-gradient(90deg,var(--ac),#bb9af7)}}
  .hbig{{font-family:var(--mono);font-size:20px;font-weight:700;color:#fff;margin-top:4px;line-height:1}}
  .hlbl{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.15em;color:var(--t3);margin-top:9px}}
  .hsub{{font-size:10px;color:var(--t3);margin-top:3px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
  @media(max-width:640px){{.grid2{{grid-template-columns:1fr}}}}
  .card{{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:13px 15px}}
  .card-title{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--t2);padding-bottom:8px;border-bottom:1px solid var(--b1);margin-bottom:9px}}
  .kv{{display:grid;grid-template-columns:1fr auto;row-gap:1px}}
  .kv .k{{font-size:11.5px;color:var(--t2);padding:2.5px 0}}
  .kv .v{{font-family:var(--mono);font-size:11.5px;color:var(--t1);text-align:right;padding:2.5px 0}}
  .kv .v.pos{{color:var(--gr)}}.kv .v.neg{{color:var(--re)}}.kv .v.warn{{color:var(--am)}}.kv .v.dim{{color:var(--t3)}}
  /* ─ error ─ */
  .err{{background:#140910;border:1px solid #3e1a24;color:var(--re);padding:10px 14px;border-radius:8px;font-size:12px}}
  .err.hide{{display:none}}
  /* ─ secondary ─ */
  .sec{{margin-top:28px}}
  .sec-hd{{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--b1);padding-bottom:7px;margin-bottom:12px}}
  .sec-hd h2{{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.2em;color:var(--t3)}}
  .sec-hd a{{font-size:11px;color:var(--t3);text-decoration:none}}
  .sec-hd a:hover{{color:var(--ac)}}
  .sigt{{width:100%;border-collapse:collapse}}
  .sigt td{{padding:5px 0;font-size:12px;border-bottom:1px solid var(--b1);color:var(--t2)}}
  .sigt td:last-child{{text-align:right;font-family:var(--mono);color:var(--t1)}}
  .ep{{display:flex;align-items:center;gap:10px;padding:5px 8px;border-radius:5px}}
  .ep:hover{{background:var(--s1)}}
  .ep .m{{font-family:var(--mono);font-size:9px;font-weight:700;color:var(--ac);width:52px;flex-shrink:0}}
  .ep .m.post{{color:var(--gr)}}.ep .m.patch{{color:var(--am)}}.ep .m.del{{color:var(--re)}}
  .ep .path{{font-family:var(--mono);font-size:11.5px}}
  .ep .desc{{font-size:11px;color:var(--t3);margin-left:auto}}
</style></head><body><div class="app">

<div class="topbar">
  <div class="brand">
    <div class="brand-name">LEN<b>S</b></div>
    <div class="brand-meta">v1.0-dev · :8765</div>
  </div>
  <nav class="topnav">
    <a href="/" class="cur">Dashboard</a>
    <a href="/projection">Projection →</a>
    <a href="/docs">API</a>
  </nav>
</div>

<div class="strip">
  <div class="sc"><div class="sc-n">{len(trades)}</div><div class="sc-l">Trades</div></div>
  <div class="sc"><div class="sc-n">{len(sigs)}</div><div class="sc-l">Signals</div></div>
  <div class="sc"><div class="sc-n">{len(pending)}</div><div class="sc-l">Pending</div></div>
</div>

<div class="main">
  <div class="sidebar">
    <div class="panel">
      <div class="panel-hd">
        <span class="panel-title">Parameters</span>
        <span class="saved" id="saved-pulse">saved ✓</span>
      </div>
      <form id="goal-form" autocomplete="off">
        <div class="fsec">
          <div class="fsec-lbl">Account</div>
          <div class="frow"><label>Start €</label><input type="text" inputmode="decimal" name="start_balance"></div>
          <div class="frow"><label>Target €</label><input type="text" inputmode="decimal" name="target_balance"></div>
          <div class="frow"><label>Target date</label><input type="date" name="target_date"></div>
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
          <div class="frow"><label>ATR floor</label><input type="text" inputmode="decimal" name="min_underlying_stop_pct" placeholder="—"></div>
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

<div class="sec">
  <div class="sec-hd"><h2>Signals by strategy</h2><a href="/api/signals">/api/signals →</a></div>
  <table class="sigt">{strat_rows}</table>
</div>

<div class="sec">
  <div class="sec-hd"><h2>API</h2><a href="/docs">interactive docs →</a></div>
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

</div>
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
    + row("Full Kelly",        fmtPct(g.full_kelly))
    + row("Fractional Kelly",  fmtPct(g.fractional_kelly))
    + row("Kelly risk",        fmtPct(g.kelly_risk))
    + row("DD constraint",     fmtPct(g.dd_risk_constraint))
    + row("Optimal risk",      fmtPct(g.optimal_risk_pct))
    + row("Used risk / trade", fmtPct(g.risk_per_trade), "warn")
    + row("DD-implied lev",    g.dd_implied_leverage != null ? fmtNum(g.dd_implied_leverage) + "×" : "—");

  document.getElementById("r-acct").innerHTML =
      row("Gain / win",         fmtPct(g.acct_gain_win),  "pos")
    + row("Loss / loss",        fmtPct(g.acct_loss_loss), "neg")
    + row("Geom drift",         fmtPct4(g.geometric_drift), g.geometric_drift > 0 ? "pos" : "neg")
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

// calculator — type 300*0.1 → Enter → 30
document.querySelectorAll('#goal-form input').forEach(function(inp) {{
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
