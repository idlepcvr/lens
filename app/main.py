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
from .review import REVIEW_HTML, get_enriched_trades, get_ohlcv_1h
from .montecarlo import MONTECARLO_HTML


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
    start:      float = Query(360,   description="Start balance €"),
    stop:       float = Query(1.0,   description="Stop — % price move"),
    tp:         float = Query(5.5,   description="Take profit — % price move (5.5% → actual 4R after 0.30% fee)"),
    lev:        float = Query(10.0,  description="Leverage"),
    wr:         float = Query(44.0,  description="Win rate %"),
    tpw:        float = Query(5.0,   description="Trades / week"),
    weeks:      float = Query(26.0,  description="Horizon (weeks)"),
    btc:        float = Query(60000, description="BTC price € (for BTC equivalent)"),
    fee:        float = Query(0.30,  description="Fee % round trip (0.15%/side)"),
    start_date: str   = Query("",    description="Plan start date (YYYY-MM-DD)"),
):
    import math
    from datetime import date as _date, timedelta as _td

    # ── start date handling ───────────────────────────────────────────────────────
    try:
        _sd = _date.fromisoformat(start_date) if start_date else None
    except ValueError:
        _sd = None
    sd_default = _date.today().isoformat()
    start_date_val = start_date or sd_default

    def week_date(w):
        if _sd is None: return ""
        return (_sd + _td(weeks=int(w))).strftime("%-d %b %Y")

    # ── live account stats (feedback loop) ───────────────────────────────────────
    actual = get_actual_stats()

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
            wd = week_date(r["week"])
            date_col = f"<td class='dim' style='font-size:10px'>{wd}</td>" if wd else "<td class='dim'>—</td>"
            curve_rows += (
                f"<tr{rc}><td>{r['week']}w</td>{date_col}<td class='dim'>{r['trades']}</td>"
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
    p50_final_val = round(p["curve"][-1]["p50"], 2) if (p and p.get("curve")) else 0
    import json as _json

    # ── Live stats widget ─────────────────────────────────────────────────────────
    def _live_stats_html():
        items = []
        live_bal  = actual.get("current_balance")
        live_date = actual.get("balance_date", "")
        live_wr   = actual.get("actual_wr")
        n_trades  = actual.get("total_trades", 0)
        wins      = actual.get("wins", 0)
        losses    = actual.get("losses", 0)
        total_pnl = actual.get("total_pnl")
        avg_win   = actual.get("avg_win_eur")
        avg_loss  = actual.get("avg_loss_eur")

        # Actual R — THE key metric (is the exit discipline holding?)
        if avg_win and avg_loss and n_trades >= 10:
            real_r = avg_win / abs(avg_loss)
            model_r = p["actual_r"] if p else None
            r_cls = "live-pos" if (model_r and real_r >= model_r * 0.85) else "live-neg"
            model_hint = f' <span class="live-dim">(model {model_r}R)</span>' if model_r else ""
            items.append(
                f'<div class="live-item live-item-wide">'
                f'<div class="live-lbl">Actual R achieved — exit discipline</div>'
                f'<div class="live-val {r_cls}" style="font-size:16px;font-weight:700">'
                f'{real_r:.2f}R{model_hint}'
                f'</div>'
                f'<div class="live-dim" style="font-size:10px;margin-top:2px">'
                f'avg win {fmt_eur(avg_win)} · avg loss {fmt_eur(avg_loss)} · {n_trades} closed trades'
                f'</div>'
                f'</div>'
            )

        # Balance item
        if live_bal is not None:
            bal_str = fmt_eur(live_bal)
            use_link = ""
            if abs(live_bal - start) > 0.5:
                import urllib.parse as _up
                params = dict(start=live_bal, stop=stop, tp=tp, lev=lev, wr=wr,
                              tpw=tpw, weeks=weeks, btc=btc, fee=fee,
                              start_date=start_date_val)
                qs = _up.urlencode({k: v for k, v in params.items() if v != ""})
                use_link = f' <a href="/projection?{qs}" class="live-use">use →</a>'
            date_hint = f' <span class="live-dim">({live_date})</span>' if live_date else ""
            items.append(
                f'<div class="live-item">'
                f'<div class="live-lbl">Account balance</div>'
                f'<div class="live-val">{bal_str}{date_hint}{use_link}</div>'
                f'</div>'
            )

        # Win rate item
        if live_wr is not None:
            wr_diff = live_wr - wr
            diff_cls = "live-pos" if wr_diff >= 0 else "live-neg"
            diff_str = f' <span class="{diff_cls}">({wr_diff:+.1f}pp vs model)</span>' if n_trades >= 10 else \
                       f' <span class="live-dim">(need ≥10 trades)</span>'

            # "use live →": seed model with realized WR, trade freq, and R-target
            seed_link = ""
            live_rr  = actual.get("actual_rr")
            live_tpw = actual.get("trades_per_week")
            if n_trades >= 10:
                import urllib.parse as _up
                seed = dict(start=start, stop=stop, tp=tp, lev=lev, wr=live_wr,
                            tpw=tpw, weeks=weeks, btc=btc, fee=fee,
                            start_date=start_date_val)
                seed["wr"] = live_wr
                if live_tpw is not None:
                    seed["tpw"] = round(live_tpw)
                if live_rr is not None:
                    # map realized R → TP% via same formula as the R-target table
                    seed["tp"] = round((live_rr * (stop / 100 + fee / 100) + fee / 100) * 100, 2)
                qs = _up.urlencode({k: v for k, v in seed.items() if v != ""})
                seed_link = f' <a href="/projection?{qs}" class="live-use">use live →</a>'

            items.append(
                f'<div class="live-item">'
                f'<div class="live-lbl">Actual win rate</div>'
                f'<div class="live-val">{live_wr}% — {wins}W / {losses}L{diff_str}{seed_link}</div>'
                f'</div>'
            )

        # Total PnL
        if total_pnl is not None:
            pnl_cls = "live-pos" if total_pnl >= 0 else "live-neg"
            items.append(
                f'<div class="live-item">'
                f'<div class="live-lbl">Realised PnL ({n_trades} trades)</div>'
                f'<div class="live-val {pnl_cls}">{fmt_eur(total_pnl)}</div>'
                f'</div>'
            )

        if not items:
            return ""
        return '<div class="live-strip">' + "".join(items) + "</div>"

    live_stats_html = _live_stats_html()
    import json as _json
    curve_json_val = _json.dumps(
        [{"week": r["week"], "p50": round(r["p50"], 2)} for r in p["curve"]]
    ) if (p and p.get("curve")) else "[]"

    # ── CSS ───────────────────────────────────────────────────────────────────────
    CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  /* mapped onto the shared LENS palette (see app/theme.py LENS_CSS) */
  --bg:#06080c;--s1:#0b0f16;--s2:#10151e;
  --b1:#192232;--b2:#28344a;--b3:#313d52;
  --t1:#e8eef8;--t2:#828ea6;--t3:#465064;--t4:#1c2636;
  --ac:#5b9dff;--adim:#10203f;
  --gr:#1fd989;--re:#ff5468;--am:#f6ad3c;
  --mono:'JetBrains Mono','SF Mono',ui-monospace,monospace;
  --ui:'Chakra Petch',-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
}
/* page-local container width override (shell provides bar/nav/.app + cockpit bg) */
.app{max-width:1180px}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
/* strategy block */
.strat{background:var(--s1);border:1px solid var(--b1);border-left:3px solid var(--ac);border-radius:10px;padding:14px 18px;margin:0 0 16px}
.strat .tl{color:#a6c1ff;font-style:italic;font-size:12.5px;display:block;margin-bottom:10px;line-height:1.6}
.strat ul{padding-left:18px;list-style:disc}
.strat li{margin:3px 0;color:var(--t2);font-size:12px}
.strat b{color:var(--t1)}
/* param form */
.param-form{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:12px 16px;margin:0 0 16px}
.pf{display:flex;flex-direction:column;gap:3px}
.pf label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--t3)}
.pf input{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:5px 8px;border-radius:5px;font-family:var(--mono);font-size:12px;width:80px;transition:border-color .12s}
.pf input:focus{outline:none;border-color:var(--ac)}
.pf input.calc-on{border-color:var(--am)!important;color:var(--am)}
.proj-btn{background:var(--adim);color:var(--ac);border:1px solid #28344a;padding:7px 16px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;transition:all .12s;align-self:flex-end}
.proj-btn:hover{background:#10203f;color:#8fbaff}
.calc-hint{font-size:9px;color:var(--t4);align-self:flex-end;padding-bottom:8px;font-family:var(--mono)}
/* hero cards */
.hero{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 16px}
@media(max-width:800px){.hero{grid-template-columns:repeat(2,1fr)}}
.hcard{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 15px;position:relative;overflow:hidden}
.hcard::after{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.hcard.pos::after{background:linear-gradient(90deg,var(--gr),#73daca)}
.hcard.neg::after{background:linear-gradient(90deg,var(--re),#c04060)}
.hcard.warn::after{background:linear-gradient(90deg,var(--am),#ff9e64)}
.hcard.neutral::after{background:linear-gradient(90deg,var(--ac),#bb9af7)}
.hbig{font-family:var(--mono);font-size:22px;font-weight:700;color:#fff;line-height:1;margin-top:4px}
.hlbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.15em;color:var(--t3);margin-top:9px}
.hsub{font-size:10px;color:var(--t3);margin-top:3px}
/* section heads */
.sec-hd{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--b1);padding-bottom:7px;margin:24px 0 10px}
.sec-hd h2{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.2em;color:var(--t3)}
.sec-hd span{font-size:11px;color:var(--t3)}
/* chart */
.chart-wrap{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:12px 14px;margin:0 0 8px}
.chart-legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px}
.dot{display:inline-block;width:14px;height:2px}
.leg-btn{background:none;border:none;cursor:pointer;font-family:var(--ui);font-size:10px;display:flex;align-items:center;gap:5px;padding:2px 5px;border-radius:3px;transition:opacity .12s}
.leg-btn:hover{opacity:1 !important}
/* tables */
table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}
th{text-align:right;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);padding:6px 8px;border-bottom:1px solid var(--b1)}
th:first-child,td:first-child{text-align:left}
td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--b1);color:var(--t1)}
tr.alt td{background:#0b0b0d}
tr.cur-row td{background:#121624}
tr.cur-row td:first-child{border-left:2px solid var(--ac)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:780px){.two{grid-template-columns:1fr}}
/* text styles */
.dim{color:var(--t3)}
.p05{color:var(--re)}.p25{color:var(--am)}.p50{color:#fff;font-weight:600}.p75{color:#9ad68a}.p95{color:var(--gr)}
.btc{color:#f0a000}
.pos{color:var(--gr)}.neg{color:var(--re)}.warn{color:var(--am)}
/* mc grid */
.mc-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:8px 0 0}
@media(max-width:780px){.mc-grid{grid-template-columns:repeat(3,1fr)}}
.mc-card{background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:12px 12px;text-align:center}
.mc-n{font-family:var(--mono);font-size:14px;font-weight:600;color:#fff}
.mc-n.neg{color:var(--re)}.mc-n.warn{color:var(--am)}.mc-n.mc75{color:#9ad68a}.mc-n.mc95{color:var(--gr)}
.mc-l{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);margin-top:5px}
/* misc */
.bt-empty{text-align:center;padding:32px 20px;color:var(--t3);border:1px dashed var(--b2);border-radius:10px;margin:8px 0}
.bt-empty p{font-size:11px;margin-top:5px;line-height:1.7;color:var(--t3)}
.note{color:var(--t3);font-size:11px;margin:5px 0 10px;line-height:1.6}
.note b{color:var(--t2)}
.note code{background:var(--s2);padding:1px 5px;border-radius:3px;color:var(--t2)}
.err{background:#140910;border:1px solid #3e1a24;color:var(--re);padding:10px 14px;border-radius:8px;margin:8px 0}
/* collapse toggle */
.collapse-btn{background:transparent;border:none;color:var(--t3);cursor:pointer;font-size:11px;padding:3px 7px;border-radius:4px;transition:all .12s;line-height:1}
.collapse-btn:hover{color:var(--t1);background:var(--s2)}
/* save plan */
.save-plan-btn{background:#0e1f10;color:var(--gr);border-color:#1a3d1e}
.save-plan-btn:hover{background:#132518;color:#5de08a}
.saved-flash{font-size:10px;color:var(--gr);opacity:0;transition:opacity .3s;align-self:flex-end;padding-bottom:8px;font-family:var(--mono)}
.saved-flash.show{opacity:1}
/* plan cards */
.plan-card{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:14px 16px;margin:8px 0}
.plan-hdr{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.plan-label-inp{background:transparent;border:none;border-bottom:1px solid transparent;color:var(--t1);font-size:13px;font-weight:600;font-family:var(--ui);padding:2px 4px;border-radius:3px;flex:1;min-width:120px;transition:border-color .15s}
.plan-label-inp:hover{border-bottom-color:var(--b3)}
.plan-label-inp:focus{outline:none;border-bottom-color:var(--ac);background:var(--s2)}
.plan-meta{font-size:11px;color:var(--t3);margin-bottom:10px;font-family:var(--mono)}
.plan-target{font-size:11px;color:var(--t2);margin-bottom:10px}
.plan-target b{color:var(--t1)}
.status-chip{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;padding:2px 7px;border-radius:20px;cursor:pointer;border:none;font-family:var(--ui);transition:all .12s}
.status-active{background:#0e1f10;color:var(--gr)}
.status-paused{background:#1e1a0a;color:var(--am)}
.status-completed{background:#0a1220;color:var(--ac)}
.sync-btn{background:transparent;border:1px solid var(--b2);color:var(--t3);cursor:pointer;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;padding:2px 8px;border-radius:4px;font-family:var(--ui);transition:all .12s}
.sync-btn:hover{color:var(--ac);border-color:var(--ac)}
.sync-btn:disabled{opacity:.4;cursor:default}
.plan-del-btn{background:transparent;border:none;color:var(--t3);cursor:pointer;font-size:14px;padding:2px 6px;border-radius:4px;margin-left:auto;line-height:1;transition:color .12s}
.plan-del-btn:hover{color:var(--re)}
.act-table{width:100%;border-collapse:collapse;font-size:11.5px;margin-top:6px}
.act-table th{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);padding:4px 8px;border-bottom:1px solid var(--b1);text-align:left}
.act-table th:not(:first-child){text-align:right}
.act-table td{padding:5px 8px;border-bottom:1px solid var(--b1);color:var(--t1);text-align:right}
.act-table td:first-child{text-align:left;color:var(--t2);font-family:var(--mono)}
.act-table td.act-note{color:var(--t3);font-size:10px;text-align:left;max-width:200px}
.act-del{background:transparent;border:none;color:var(--t3);cursor:pointer;font-size:12px;padding:1px 5px;border-radius:3px;transition:color .12s}
.act-del:hover{color:var(--re)}
.add-act-row td{padding:6px 8px;border-bottom:none}
.add-act-inp{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 7px;border-radius:4px;font-family:var(--mono);font-size:11px;transition:border-color .12s}
.add-act-inp:focus{outline:none;border-color:var(--ac)}
.add-act-inp[type=date]{width:120px}
.add-act-inp[type=number]{width:90px}
.add-act-inp[type=text]{width:140px}
.add-act-btn{background:var(--adim);color:var(--ac);border:1px solid #28344a;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:10px;font-weight:700;font-family:var(--ui);letter-spacing:.08em;transition:all .12s}
.add-act-btn:hover{background:#10203f;color:#8fbaff}
/* live stats strip */
.live-strip{display:flex;flex-wrap:wrap;gap:6px;background:var(--s1);border:1px solid var(--b1);border-left:3px solid var(--gr);border-radius:10px;padding:10px 16px;margin:0 0 12px}
.live-item{flex:1;min-width:160px}
.live-lbl{font-size:8.5px;font-weight:700;text-transform:uppercase;letter-spacing:.16em;color:var(--t3);margin-bottom:2px}
.live-val{font-family:var(--mono);font-size:12px;color:var(--t1)}
.live-dim{color:var(--t3);font-size:10px;font-family:var(--ui)}
.live-pos{color:var(--gr)}
.live-neg{color:var(--re)}
.live-use{font-size:10px;color:var(--ac);text-decoration:none;margin-left:6px;font-family:var(--ui)}
.live-use:hover{text-decoration:underline}
.live-item-wide{flex-basis:100%;border-bottom:1px solid var(--b1);padding-bottom:8px;margin-bottom:2px}
/* ── collapsible sections: let a long body (My plans) expand past LENS's 5000px cap ── */
.sec-body.tall:not(.closed){max-height:20000px}
/* ── mobile: keep wide tables + plan cards inside the viewport ── */
table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
.plan-card{max-width:100%;overflow-x:auto}
.param-form,.live-strip,.hero,.mc-grid,.chart-wrap,.two{max-width:100%}
@media(max-width:680px){
  .app{padding:0 10px 120px}
  .param-form{padding:10px 12px;gap:7px}
  .pf input{width:72px}
  .plan-meta{font-size:10px;line-height:1.5}
  .act-table{font-size:10.5px}
  .add-act-inp[type=date]{width:112px}
  .add-act-inp[type=number]{width:78px}
  .add-act-inp[type=text]{width:120px}
}
"""

    # ── JS ────────────────────────────────────────────────────────────────────────
    JS = r"""
// persist projection params in localStorage — restore on bare /projection visit
(function() {
  var LS_KEY = 'lens_proj_params';
  var qs = window.location.search;
  if (qs && qs.length > 1) {
    try { localStorage.setItem(LS_KEY, qs); } catch(e) {}
  } else {
    try {
      var saved = localStorage.getItem(LS_KEY);
      if (saved) { window.location.replace('/projection' + saved); }
    } catch(e) {}
  }
})();

// calculator — type 300*0.1 → Enter → 30
document.querySelectorAll('.pf input').forEach(function(inp) {
  function tryCalc() {
    var v = inp.value.trim();
    if (!v) return;
    try {
      var r = Function('"use strict";return(' + v.replace(/[^0-9+\-*/.() \t]/g,'') + ')')();
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
  var p05 = document.getElementById('sp05'), p95 = document.getElementById('sp95'), fill = document.getElementById('sband');
  if (fill && p05 && p95) fill.style.display = (p05.style.display !== 'none' || p95.style.display !== 'none') ? '' : 'none';
}

// ── My Plans ──────────────────────────────────────────────────────────────────

function fmtEur(v) {
  if (v == null) return '—';
  var n = parseFloat(v);
  if (isNaN(n)) return '—';
  if (Math.abs(n) >= 1000000) return '€' + (n/1000000).toFixed(2) + 'M';
  if (Math.abs(n) >= 10000)   return '€' + (n/1000).toFixed(1) + 'k';
  return '€' + n.toFixed(0);
}

function fmtPct(v) {
  return (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
}

function savePlan() {
  var params = new URLSearchParams(window.location.search);
  var p50 = parseFloat(document.getElementById('proj-p50-val').dataset.val) || 0;
  var curveEl = document.getElementById('proj-curve-data');
  var curveJson = curveEl ? curveEl.textContent.trim() : '[]';
  var today = new Date().toISOString().slice(0, 10);
  var payload = {
    label: 'Plan ' + today,
    start_bal: parseFloat(params.get('start') || 360),
    stop_pct:  parseFloat(params.get('stop')  || 1.0),
    tp_pct:    parseFloat(params.get('tp')    || 5.5),
    leverage:  parseFloat(params.get('lev')   || 10),
    win_rate:  parseFloat(params.get('wr')    || 44),
    tpw:       parseFloat(params.get('tpw')   || 5),
    weeks:     parseFloat(params.get('weeks') || 26),
    btc_price: parseFloat(params.get('btc')   || 60000),
    fee_rt:          parseFloat(params.get('fee')   || 0.30),
    p50_final:       p50,
    plan_start_date: params.get('start_date') || today,
    curve_json: curveJson,
  };
  fetch('/api/projections', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }).then(function(r) {
    if (!r.ok) throw new Error('save failed');
    var flash = document.getElementById('plan-saved-flash');
    flash.classList.add('show');
    setTimeout(function() { flash.classList.remove('show'); }, 2000);
    loadPlans();
  }).catch(function(e) { alert('Save failed: ' + e.message); });
}

function loadPlans() {
  fetch('/api/projections').then(function(r) { return r.json(); }).then(function(data) {
    var plans = data.plans || [];
    var countEl = document.getElementById('plans-count');
    var emptyEl = document.getElementById('plans-empty');
    var listEl  = document.getElementById('plans-list');
    if (countEl) countEl.textContent = plans.length ? plans.length + ' saved' : '';
    if (emptyEl) emptyEl.style.display = plans.length ? 'none' : '';
    if (!listEl) return;
    listEl.innerHTML = plans.map(renderPlanCard).join('');
    // Sync form start_date to active plan's start date
    var activePlan = plans.find(function(p) { return p.status === 'active' && p.plan_start_date; });
    if (activePlan) {
      var sdInput = document.querySelector('input[name="start_date"]');
      if (sdInput) sdInput.value = activePlan.plan_start_date;
    }
  });
}

function renderPlanCard(plan) {
  var created = plan.created_at ? plan.created_at.slice(0, 10) : '';
  var statusMap = {active:'status-active', paused:'status-paused', completed:'status-completed'};
  var statusCls = statusMap[plan.status] || 'status-active';
  var nextStatus = {active:'paused', paused:'completed', completed:'active'}[plan.status] || 'active';
  var meta = [
    '€' + plan.start_bal,
    plan.stop_pct + '% SL',
    plan.tp_pct + '% TP',
    plan.leverage + '×',
    plan.win_rate + '% WR',
    plan.tpw + '/wk',
    plan.weeks + 'w',
    plan.btc_price ? 'BTC €' + Number(plan.btc_price).toLocaleString('en') : '',
  ].filter(Boolean).join(' · ');
  var targetLine = plan.p50_final
    ? '<span class="plan-target">P50 target: <b>' + fmtEur(plan.p50_final) + '</b> in ' + plan.weeks + 'w · projected gain <b>' + fmtPct((plan.p50_final - plan.start_bal) / plan.start_bal * 100) + '</b></span>'
    : '';
  var startDateField =
    '<span style="font-size:10px;color:var(--t3)">start </span>' +
    '<input class="plan-label-inp" style="width:100px;font-size:11px" ' +
      'value="' + escHtml(plan.plan_start_date || '') + '" ' +
      'type="date" ' +
      'onblur="updatePlanStartDate(' + plan.id + ', this.value)" ' +
      'onkeydown="if(event.key===\'Enter\')this.blur()">';
  var actualsHtml = renderActualsTable(plan);
  return (
    '<div class="plan-card" id="plan-' + plan.id + '">' +
    '<div class="plan-hdr">' +
    '<input class="plan-label-inp" value="' + escHtml(plan.label || 'Plan ' + created) + '" ' +
      'onblur="updatePlanLabel(' + plan.id + ', this.value)" ' +
      'onkeydown="if(event.key===\'Enter\')this.blur()">' +
    '<button class="status-chip ' + statusCls + '" onclick="cycleStatus(' + plan.id + ',\'' + nextStatus + '\')">' + plan.status + '</button>' +
    startDateField +
    '<button class="plan-del-btn" onclick="deletePlan(' + plan.id + ')" title="Delete plan">×</button>' +
    '</div>' +
    '<div class="plan-meta">' + meta + '</div>' +
    targetLine +
    actualsHtml +
    '</div>'
  );
}

function projectedAtDate(plan, dateStr) {
  if (!plan.plan_start_date) return null;
  var startMs   = new Date(plan.plan_start_date).getTime();
  var checkMs   = new Date(dateStr).getTime();
  var weeksFrac = (checkMs - startMs) / (7 * 24 * 3600 * 1000);
  if (weeksFrac < 0) return null;

  // Use stored curve if available — exact Monte Carlo P50 values
  var curve = null;
  try { curve = plan.curve_json ? JSON.parse(plan.curve_json) : null; } catch(e) {}
  if (curve && curve.length) {
    // Find the two surrounding week points and linearly interpolate
    var prev = curve[0], next = curve[curve.length - 1];
    for (var i = 0; i < curve.length; i++) {
      if (curve[i].week <= weeksFrac) prev = curve[i];
      if (curve[i].week >= weeksFrac) { next = curve[i]; break; }
    }
    if (prev.week === next.week) return prev.p50;
    var t = (weeksFrac - prev.week) / (next.week - prev.week);
    return prev.p50 + t * (next.p50 - prev.p50);
  }

  // Fallback: geometric interpolation
  if (!plan.p50_final) return null;
  var ratio = plan.p50_final / plan.start_bal;
  return plan.start_bal * Math.pow(ratio, weeksFrac / plan.weeks);
}

function renderActualsTable(plan) {
  var hasActuals = (plan.actuals || []).length > 0;
  var syncNote = '';
  if (!hasActuals) {
    syncNote = '<p style="font-size:10px;color:var(--t3);margin:6px 0 4px">No checkpoints yet — daily balances auto-fill at 00:05. Add manually below.</p>';
  }

  var addRow =
    '<tr class="add-act-row">' +
    '<td><input class="add-act-inp" type="date" id="act-date-' + plan.id + '" value="' + new Date().toISOString().slice(0,10) + '"></td>' +
    '<td><input class="add-act-inp" type="number" id="act-bal-' + plan.id + '" placeholder="actual €" step="0.01"></td>' +
    '<td colspan="2"><input class="add-act-inp" type="text" id="act-note-' + plan.id + '" placeholder="note (optional)" style="width:180px"></td>' +
    '<td><button class="add-act-btn" onclick="addActual(' + plan.id + ')">+ Add</button></td>' +
    '</tr>';

  var rows = (plan.actuals || []).map(function(a) {
    var proj = projectedAtDate(plan, a.date);
    var diff = (proj != null) ? (a.balance - proj) : null;
    var diffCls = diff == null ? '' : (diff >= 0 ? 'pos' : 'neg');
    var projCell = proj != null ? fmtEur(proj) : '<span class="dim">—</span>';
    var diffCell = diff != null ? ('<span class="' + diffCls + '">' + fmtPct(diff / proj * 100) + '</span>') : '<span class="dim">—</span>';
    var autoNote = a.note === 'auto: daily snapshot' ? '<span style="color:var(--ac);font-size:9px">auto</span>' : escHtml(a.note || '');
    return '<tr>' +
      '<td>' + (a.date || '') + '</td>' +
      '<td style="font-weight:600">' + fmtEur(a.balance) + '</td>' +
      '<td class="dim">' + projCell + '</td>' +
      '<td>' + diffCell + '</td>' +
      '<td class="act-note">' + autoNote + '</td>' +
      '<td><button class="act-del" onclick="deleteActual(' + plan.id + ',' + a.id + ')" title="Delete">×</button></td>' +
      '</tr>';
  }).join('');

  return (
    syncNote +
    '<table class="act-table">' +
    '<tr><th>Date</th><th>Actual €</th><th>Proj P50</th><th>vs Plan</th><th>Note</th><th></th></tr>' +
    rows + addRow +
    '</table>'
  );
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function addActual(planId) {
  var date  = document.getElementById('act-date-' + planId).value;
  var bal   = parseFloat(document.getElementById('act-bal-' + planId).value);
  var note  = document.getElementById('act-note-' + planId).value;
  if (!date || isNaN(bal)) { alert('Date and balance required'); return; }
  fetch('/api/projections/' + planId + '/actuals', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({date: date, balance: bal, note: note || null}),
  }).then(function(r) {
    if (!r.ok) throw new Error('add failed');
    loadPlans();
  }).catch(function(e) { alert('Failed: ' + e.message); });
}

function deleteActual(planId, actualId) {
  fetch('/api/projections/' + planId + '/actuals/' + actualId, {method:'DELETE'})
    .then(function() { loadPlans(); });
}

function deletePlan(planId) {
  if (!confirm('Delete this plan and all its checkpoints?')) return;
  fetch('/api/projections/' + planId, {method:'DELETE'})
    .then(function() { loadPlans(); });
}

function cycleStatus(planId, newStatus) {
  fetch('/api/projections/' + planId, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: newStatus}),
  }).then(function() { loadPlans(); });
}

function updatePlanLabel(planId, label) {
  fetch('/api/projections/' + planId, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({label: label}),
  });
}

function updatePlanStartDate(planId, date) {
  if (!date) return;
  fetch('/api/projections/' + planId, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({plan_start_date: date}),
  }).then(function() { loadPlans(); });
}

function syncActuals(planId) {
  var btn = event.target;
  var orig = btn.textContent;
  btn.textContent = 'syncing…';
  btn.disabled = true;
  fetch('/api/projections/' + planId + '/actuals/autofill', {method: 'POST'})
    .then(function(r) { return r.json(); })
    .then(function(d) {
      btn.disabled = false;
      if (d.added > 0) {
        btn.textContent = '✓ +' + d.added + ' added';
        setTimeout(function() { btn.textContent = orig; }, 2500);
      } else {
        btn.textContent = 'no new snapshots';
        btn.title = 'No daily_snapshots found for this plan\'s date range. Run a Kraken sync first via /api/sync/kraken.';
        setTimeout(function() { btn.textContent = orig; btn.title = 'Auto-fill from Kraken daily balance snapshots'; }, 3500);
      }
      loadPlans();
    })
    .catch(function() { btn.textContent = orig; btn.disabled = false; });
}

// ── Collapse chart section ────────────────────────────────────────────────────
(function() {
  var LS_KEY = 'lens_chart_collapsed';
  try { if (localStorage.getItem(LS_KEY) === '1') applyChartCollapse(true); } catch(e) {}
})();

function applyChartCollapse(collapsed) {
  var body = document.getElementById('chart-body');
  var btn  = document.getElementById('chart-toggle');
  if (!body || !btn) return;
  body.style.display = collapsed ? 'none' : '';
  btn.textContent    = collapsed ? '▶' : '▼';
}

function toggleChartSection() {
  var body = document.getElementById('chart-body');
  if (!body) return;
  var collapsed = body.style.display === 'none';
  applyChartCollapse(!collapsed);
  try { localStorage.setItem('lens_chart_collapsed', !collapsed ? '1' : '0'); } catch(e) {}
}

document.addEventListener('DOMContentLoaded', loadPlans);
"""

    from .theme import shell

    body = f"""
<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this projection</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what this page is</h4>A <b>forward projection</b> of the locked TREND_4R_v1 plan: plug in your parameters and it Monte-Carlos thousands of equity paths, then shows the <b>percentile bands</b> — not one line, a cone of outcomes. It answers: <b>where could this account realistically be in N weeks?</b>
<h4>the parameters drive everything</h4>Start €, stop %, TP %, leverage, win rate, trades/week, horizon. Edit any field and hit <b>Project →</b>. Every field is a calculator (type <code>300*0.1</code> → ↵). <b>Save Plan</b> snapshots the current params to track actual results against later.
<h4>read the bands, not the totals</h4><b>P50</b> = median path, <b class="r">P05</b> = unlucky worst 5%, <b class="g">P95</b> = best 5%. The spread is <b>variance, not a forecast</b>. Compounding makes far-out totals absurd — trust the <b>early weeks, EV/trade, breakeven WR, and ruin %</b>.
<h4>the tables</h4><b>R-target scenarios</b> = what each TP% yields as actual R after fees (the lever you control). <b>Win-rate sensitivity</b> = how fragile the edge is to WR slipping. Below breakeven WR you lose regardless of R.
<h4>a model, not a promise</h4>Assumes the win rate holds at a 1% stop (unproven) and ignores funding on multi-day holds. Validate the assumptions in <a href="/backtest">Backtest</a> and <a href="/review">Review</a>.
</div></div>

<div class="sect closed" id="h-strat" onclick="tog('strat')"><span class="caret">▾</span><span class="ttl">📋 the strategy — TREND_4R_v1</span><span class="line"></span></div>
<div class="sec-body closed" id="s-strat">
<div class="strat">
  <span class="tl">"I trade BTC perps on Kraken — with-trend, 4H chart — risking a fixed 10% of my account to make 40%+. My entire edge is holding winners to the full target instead of bailing early."</span>
  <b>TREND_4R_v1 — locked rules:</b>
  <ul>
    <li><b>Market / TF:</b> BTC perpetual futures, Kraken. 4H chart. Holds 1–3 days.</li>
    <li><b>Direction:</b> long or short — <b>only with the trend.</b> Never counter-trend.</li>
    <li><b>Risk (fixed):</b> 1% price stop = <b>10% of account</b> at 10×. Same risk every trade.</li>
    <li><b>Exit (this IS the edge):</b> 5.5% TP → <b>+52% account → 4R actual</b> after 0.30% round-trip fee. Set it and walk away.</li>
    <li><b>Frequency:</b> ~2–5 trades/week. Most of the time, <em>no trade</em>.</li>
    <li><b>Not chasing WR.</b> 44% is fine. <b>R is the lever</b> — see the tables below.</li>
  </ul>
</div>
</div>

<div class="sect" id="h-params" onclick="tog('params')"><span class="caret">▾</span><span class="ttl">⚙ parameters</span><span class="line"></span></div>
<div class="sec-body" id="s-params">
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
  <div class="pf"><label>Start date</label><input name="start_date" type="date" value="{start_date_val}" style="width:110px"></div>
  <button class="proj-btn" type="submit">Project →</button>
  <button class="proj-btn save-plan-btn" type="button" id="save-plan-btn" onclick="savePlan()">Save Plan</button>
  <span class="saved-flash" id="plan-saved-flash">saved ✓</span>
  <span class="calc-hint">300*0.1 → ↵</span>
</form>
</div>
<span id="proj-p50-val" data-val="{p50_final_val}" style="display:none"></span>
<script id="proj-curve-data" type="application/json">{curve_json_val}</script>
{live_stats_html}
{err_html}

<div class="sect" id="h-metrics" onclick="tog('metrics')"><span class="caret">▾</span><span class="ttl">📊 key metrics</span><span class="line"></span></div>
<div class="sec-body" id="s-metrics">
<div class="hero">{cards}</div>
</div>

<div class="sect" id="h-chart" onclick="tog('chart')"><span class="caret">▾</span><span class="ttl">Equity projection — percentile bands (log scale)</span><span class="line"></span></div>
<div class="sec-body" id="s-chart">
<div class="chart-wrap">
  {sparkline}
  <div class="chart-legend">
    <button class="leg-btn" onclick="toggleBand('sp05',this)" style="color:var(--re);opacity:0.35"><span class="dot" style="background:var(--re)"></span>P05 worst</button>
    <button class="leg-btn" onclick="toggleBand('sp25',this)" style="color:var(--am);opacity:0.35"><span class="dot" style="background:var(--am)"></span>P25</button>
    <button class="leg-btn" onclick="toggleBand('sp50',this)" style="color:#fff"><span class="dot" style="background:#fff;height:2.5px"></span>P50 median</button>
    <button class="leg-btn" onclick="toggleBand('sp75',this)" style="color:#9ad68a;opacity:0.35"><span class="dot" style="background:#9ad68a"></span>P75</button>
    <button class="leg-btn" onclick="toggleBand('sp95',this)" style="color:var(--gr);opacity:0.35"><span class="dot" style="background:var(--gr)"></span>P95 best</button>
  </div>
</div>
<p class="note"><b>P50</b> = expected median path · <b>P05</b> = worst 5% · <b>P95</b> = best 5%. Spread is variance, not a forecast.</p>
<table>
  <tr><th>Week</th><th>Date</th><th>Trades</th><th class="p05">P05</th><th class="p25">P25</th><th class="p50">Median</th><th class="p75">P75</th><th class="p95">P95</th><th>BTC (P50)</th></tr>
  {curve_rows}
</table>
</div>

<div class="two" style="margin-top:24px">
  <div>
    <div class="sect" id="h-rtgt" onclick="tog('rtgt')"><span class="caret">▾</span><span class="ttl">R-target scenarios <span class="dim" style="font-weight:400">· WR {wr:g}% · SL {stop:g}% · fee {fee:g}% RT</span></span><span class="line"></span></div>
    <div class="sec-body" id="s-rtgt">
    <p class="note">What TP% gives you each <b>actual R after fees</b>. R is the one lever you fully control — exit discipline, not a market outcome. ← = current params.</p>
    <table>
      <tr><th>Target R</th><th>Params</th><th>EV/trade</th><th>Geo drift</th><th>To 2×</th><th>Final P50</th><th>Ruin</th></tr>
      {r_target_rows}
    </table>
    </div>
  </div>
  <div>
    <div class="sect" id="h-wrs" onclick="tog('wrs')"><span class="caret">▾</span><span class="ttl">Win-rate sensitivity <span class="dim" style="font-weight:400">· R held at {wr_r_label}</span></span><span class="line"></span></div>
    <div class="sec-body" id="s-wrs">
    <p class="note">WR is a <b>byproduct of entry quality</b> — hard to control directly. Below breakeven WR you lose money regardless of R.</p>
    <table>
      <tr><th>WR</th><th>EV/trade</th><th>Geo drift</th><th>To 2×</th><th>Final P50</th><th>Ruin</th></tr>
      {wr_rows}
    </table>
    </div>
  </div>
</div>

<div class="sect" id="h-mc" onclick="tog('mc')"><span class="caret">▾</span><span class="ttl">Monte Carlo — final distribution at {weeks:g} weeks</span><span class="line"></span></div>
<div class="sec-body" id="s-mc">{mc_html}</div>

<div class="sect closed" id="h-bt" onclick="tog('bt')"><span class="caret">▾</span><span class="ttl">Backtest tracker</span><span class="line"></span></div>
<div class="sec-body closed" id="s-bt">
<div class="bt-empty">
  <b style="color:var(--t2)">No backtest data yet</b>
  <p>Run <code>TREND_4R_v1</code> on TradingView → export CSV → paste results here to validate the 44% WR assumption at a 1% stop / 5.5% TP on the 4H chart.</p>
  <p>Fields: date · direction · entry · SL hit / TP hit · hold time · R achieved</p>
</div>
</div>

<div class="sect" id="h-plans" onclick="tog('plans')"><span class="caret">▾</span><span class="ttl">My plans <span id="plans-count" class="dim" style="font-weight:400"></span></span><span class="line"></span></div>
<div class="sec-body tall" id="s-plans">
<div id="plans-section">
  <div class="bt-empty" id="plans-empty" style="display:none">
    <b style="color:var(--t2)">No saved plans yet</b>
    <p>Click <b>Save Plan</b> above to snapshot the current projection and track actual results over time.</p>
  </div>
  <div id="plans-list"></div>
</div>
</div>

<p class="note" style="margin-top:20px"><b>Read the shape, not the raw totals.</b> Compounding over many trades produces absurd numbers — trust the <b>early weeks, EV/trade, breakeven WR, and ruin %</b>. Assumes win rate holds at a 1% stop (unproven) and ignores funding on multi-day holds. A model, not a promise.</p>
"""

    script = ("function tog(id){ document.getElementById('h-'+id).classList.toggle('closed');"
              " document.getElementById('s-'+id).classList.toggle('closed'); }\n") + JS
    return shell("/projection", "Projection", body, script=script,
                 head_extra=f"<style>{CSS}</style>", meta="parameter-first")


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
.frow input{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 8px;border-radius:5px;font-family:var(--mono);font-size:11.5px;width:100%;transition:border-color .12s}
.frow input:focus{outline:none;border-color:var(--ac)}
.frow input.cx{border-color:var(--am)!important;color:var(--am)}
.frow input[type=date]{font-family:var(--ui);font-size:11px}
.factns{padding:10px 14px;display:flex;gap:7px;align-items:center}
.btn{padding:6px 13px;border-radius:5px;border:1px solid var(--b2);background:var(--s2);color:var(--t2);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;cursor:pointer;font-family:inherit;transition:all .12s}
.btn:hover{color:var(--t1);border-color:var(--b3)}
.btn.p{background:var(--adim);color:var(--ac);border-color:var(--b2)}
.btn.p:hover{filter:brightness(1.3)}
.calc-tip{font-size:9px;color:var(--t4);font-family:var(--mono)}
.metrics{display:flex;flex-direction:column;gap:10px}
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
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
.card{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:13px 15px}
.card-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--t2);padding-bottom:8px;border-bottom:1px solid var(--b1);margin-bottom:9px}
.kv{display:grid;grid-template-columns:1fr auto;row-gap:1px}
.kv .k{font-size:11.5px;color:var(--t2);padding:2.5px 0;border:none}
.kv .v{font-family:var(--mono);font-size:11.5px;color:var(--t1);text-align:right;padding:2.5px 0}
.kv .v.pos{color:var(--gr)}.kv .v.neg{color:var(--re)}.kv .v.warn{color:var(--am)}.kv .v.dim{color:var(--t3)}
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
<h4>read-only math</h4>LENS computes — it does not trade. Pair this with <a href="/desk">Desk</a> (can I enter now?) and <a href="/projection">Projection</a> (equity curve over time).
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
    strat_opts = "".join(
        f'<option value="{k}">{k} — {v["description"][:70]}</option>'
        for k, v in BT_STRATEGIES.items()
    )
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
</style>"""

    body = f"""
<h1>Strategy Backtest</h1>
<div class="sub">BTC/USDT 4H · Bybit perpetuals · 30 months · €637 initial · 0.15%/side fee</div>

<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this backtest</span><span class="line"></span></div>
<div class="sec-body closed" id="s-help"><div class="help-body">
<h4>what this page is</h4>Runs a <b>locked, mechanical strategy</b> over ~30 months of BTC/USDT 4H history and reports exactly how it would have done — no discretion, no curve-fitting. Pick a strategy, hit <b>Run</b>, read the scorecard.
<h4>the metrics that matter</h4><b class="g">Win rate</b> ≥48% = goal-grade. <b>Profit factor</b> ≥1.5 (gross win ÷ gross loss). <b class="a">Avg R</b> ≥3.5 — the real lever. <b class="r">Max DD</b> &lt;40% survivable, and <b>max consecutive losses</b> = your risk-of-ruin reality check.
<h4>equity curve + trade log</h4>The curve is account €over the window; the log lists every entry/exit with PnL% and hold time. Look for <b>smooth-ish</b> growth, not one lucky spike.
<h4>historical, not live</h4>Past fills on past candles — assumptions, not promises. These metrics <b>seed Monte Carlo</b>: pick a backtest there to stress-test the same edge forward. Compare against your real results in <a href="/review">Review</a>.
</div></div>

<div class="row">
  <select id="strat">{strat_opts}</select>
  <button class="run" id="run-btn" onclick="runBacktest()">▶ Run</button>
  <span id="status"></span>
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

  fetch('/api/backtest/run', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{name: name}})
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

function metricColor(key, val) {{
  if (key === 'win_rate') return val >= 48 ? 'good' : val >= 31 ? 'warn' : 'bad';
  if (key === 'profit_factor') return val >= 1.5 ? 'good' : val >= 1.0 ? 'warn' : 'bad';
  if (key === 'max_drawdown_pct') return val < 40 ? 'good' : val < 70 ? 'warn' : 'bad';
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

  // Equity curve
  drawChart(d.equity_curve);

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


@app.get("/api/backtest/strategies")
def api_backtest_strategies():
    return {
        k: {"description": v["description"], "params": v["params"]}
        for k, v in BT_STRATEGIES.items()
    }


# ─── Trade Review ─────────────────────────────────────────────────────────────

@app.get("/review", response_class=HTMLResponse)
def review_page():
    return REVIEW_HTML


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page():
    from .calendar_page import CALENDAR_HTML
    return CALENDAR_HTML


@app.get("/montecarlo", response_class=HTMLResponse)
def montecarlo_page():
    return MONTECARLO_HTML


@app.get("/prop", response_class=HTMLResponse)
def prop_page():
    from .prop_views import goals_page
    return goals_page()


@app.get("/strategy", response_class=HTMLResponse)
def strategy_engine():
    from .prop_views import strategy_page
    return strategy_page()


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
    """Log a trade onto the prop book (forces book='prop')."""
    trade.book = "prop"
    return create_trade(trade)


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
