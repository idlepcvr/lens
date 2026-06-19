"""Trade review page — enriched trades with edge conditions, integrated into LENS."""

import bisect
import datetime
import json
import sqlite3
from typing import Any

from .database import DB_PATH

APR25_MS      = int(datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
STEP_4H_MS    = 14_400_000
EMA_WARMUP_4H = 100


# ── math ──────────────────────────────────────────────────────────────────────

def _ema(closes: list, period: int) -> list:
    k = 2 / (period + 1)
    result, avg = [], None
    for i, v in enumerate(closes):
        if i < period - 1:
            result.append(None)
        elif i == period - 1:
            avg = sum(closes[:period]) / period
            result.append(avg)
        else:
            avg = v * k + avg * (1 - k)
            result.append(avg)
    return result


def _rsi(closes: list, period: int = 14) -> list:
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains  = [max(0.0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
    losses = [max(0.0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
    avg_g  = sum(gains[:period])  / period
    avg_l  = sum(losses[:period]) / period
    result[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + gains[i-1])  / period
        avg_l = (avg_l * (period - 1) + losses[i-1]) / period
        result[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    return result


def _bar_idx(ts_arr: list, target_ms: int):
    i = bisect.bisect_right(ts_arr, target_ms) - 1
    return i if i >= 0 else None


def _parse_ms(iso_str: str) -> int:
    s  = iso_str.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


# ── data ──────────────────────────────────────────────────────────────────────

def _load_ohlcv():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts, open, high, low, close, volume FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    c1h = cur.fetchall()
    warmup = APR25_MS - EMA_WARMUP_4H * STEP_4H_MS
    cur.execute("""
        SELECT ts, open, high, low, close FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='4h' AND ts >= ?
        ORDER BY ts
    """, (warmup,))
    c4h = cur.fetchall()
    conn.close()
    return c1h, c4h


def _load_trades():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, direction, entry, exit, pnl, fees, size, leverage,
               opened_at, closed_at, notes, balance_after, setup_tag,
               tp, sl, funding_cost, followed_plan, followed_strategy,
               market_type, order_type, fill_count,
               grade, conviction, emotion, mistakes, went_right, went_wrong, lesson
        FROM trades WHERE closed_at IS NOT NULL ORDER BY opened_at
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


# ── enrichment ────────────────────────────────────────────────────────────────

def get_enriched_trades() -> list:
    c1h, c4h   = _load_ohlcv()
    trades_raw = _load_trades()

    ts1h   = [r[0] for r in c1h]
    open1h = [r[1] for r in c1h]
    clos1h = [r[4] for r in c1h]
    rsi14  = _rsi(clos1h, 14)

    ts4h   = [r[0] for r in c4h]
    clos4h = [r[4] for r in c4h]
    ema21  = _ema(clos4h, 21)
    ema50  = _ema(clos4h, 50)

    out = []
    for row in trades_raw:
        (tid, direction, entry, exit_, pnl, fees, size, leverage,
         opened_at, closed_at, notes, bal_after, setup_tag,
         tp, sl, funding_cost, followed_plan, followed_strategy,
         market_type, order_type, fill_count,
         grade, conviction, emotion, mistakes, went_right, went_wrong, lesson) = row

        ts_e = _parse_ms(opened_at)
        ts_x = _parse_ms(closed_at)
        i1   = _bar_idx(ts1h, ts_e)
        i4   = _bar_idx(ts4h, ts_e)

        bar_dir = bar_aligned = rsi_val = rsi_zone = None
        trend_4h = trend_aligned = None

        if i1 is not None and i1 < len(c1h):
            o, c   = open1h[i1], clos1h[i1]
            bar_dir    = "bull" if c >= o else "bear"
            bar_aligned = (bar_dir == "bull") == (direction == "long")
            rsi_val    = rsi14[i1]
            if rsi_val is not None:
                rsi_zone = "dip" if rsi_val < 40 else ("momentum" if rsi_val > 55 else "neutral")

        if i4 is not None and i4 < len(c4h):
            e21, e50 = ema21[i4], ema50[i4]
            if e21 and e50:
                trend_4h    = "bull" if e21 > e50 else "bear"
                trend_aligned = (trend_4h == "bull") == (direction == "long")

        move_pct = None
        if entry and exit_:
            raw = (exit_ - entry) / entry * 100
            move_pct = round(raw * (1 if direction == "long" else -1), 3)

        out.append({
            "id":             tid,
            "direction":      direction,
            "entry":          entry,
            "exit":           exit_,
            "pnl":            pnl,
            "fees":           fees,
            "size":           size,
            "leverage":       leverage,
            "opened_at":      opened_at[:19].replace("T", " "),
            "closed_at":      closed_at[:19].replace("T", " "),
            "notes":          notes or "",
            "balance_after":  bal_after,
            "setup_tag":      setup_tag or "",
            "ts_entry":       ts_e // 1000,
            "ts_exit":        ts_x // 1000,
            "bar_dir":        bar_dir,
            "bar_aligned":    bar_aligned,
            "rsi":            round(rsi_val, 1) if rsi_val else None,
            "rsi_zone":       rsi_zone,
            "trend_4h":       trend_4h,
            "trend_aligned":  trend_aligned,
            "move_pct":       move_pct,
            # breakdown extras (for the editable modal, step B)
            "tp":             tp,
            "sl":             sl,
            "funding_cost":   funding_cost,
            "market_type":    market_type,
            "order_type":     order_type,
            "fill_count":     fill_count,
            "followed_plan":     None if followed_plan     is None else bool(followed_plan),
            "followed_strategy": None if followed_strategy is None else bool(followed_strategy),
            # review layer
            "grade":          grade,
            "conviction":     conviction,
            "emotion":        emotion,
            "mistakes":       mistakes or "",
            "went_right":     went_right or "",
            "went_wrong":     went_wrong or "",
            "lesson":         lesson or "",
        })
    return out


def get_ohlcv_1h() -> list:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts, open, high, low, close FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    rows = cur.fetchall()
    conn.close()
    return [{"time": r[0]//1000, "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in rows]


# ── HTML ──────────────────────────────────────────────────────────────────────

REVIEW_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LENS // Review</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
<link rel="apple-touch-icon" href="/assets/favicon.svg">
<link rel="stylesheet" href="/assets/lens.css">
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  /* Palette aliased onto the shared LENS tokens (app/theme.py LENS_CSS, served
     via /assets/lens.css) — single source of truth, no hardcoded hex so the
     review page can never drift from the design system. --bg/--mono inherit
     straight from the LENS :root; --b3/--t4 have no LENS equivalent. */
  --s1:var(--panel); --s2:var(--panel2);
  --b1:var(--line);  --b2:var(--line2); --b3:#313d52;
  --t1:var(--ink);   --t2:var(--dim);   --t3:var(--faint); --t4:#1c2636;
  --ac:var(--accent);--adim:var(--accent-d);
  --gr:var(--long);  --re:var(--short); --am:var(--amber);
  --ui:var(--hud);
}
/* kill the LENS cockpit grid overlay — review is a full-bleed chart IDE */
body::before{content:none}
html,body{height:100%;overflow:hidden}
body{font-family:var(--ui);font-size:13px;background:var(--bg);color:var(--t1);-webkit-font-smoothing:antialiased;display:flex;flex-direction:column}

/* ── topbar ── */
.topbar{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;border-bottom:1px solid var(--b1);background:var(--bg);flex-shrink:0;gap:12px;flex-wrap:wrap}
.topnav{display:flex;gap:6px;flex-wrap:wrap}
.topnav a{font-family:var(--mono);font-size:11px;color:var(--t2);text-decoration:none;padding:6px 12px;border:1px solid var(--b1);border-radius:999px;background:var(--s1);letter-spacing:.04em;transition:all .15s}
.topnav a:hover{color:var(--t1);border-color:var(--b2);text-decoration:none}
.topnav a.cur{color:var(--bg);background:var(--ac);border-color:var(--ac);font-weight:700}
.topbar-right{display:flex;gap:8px;align-items:center;margin-left:auto}
.tb-btn{background:var(--s1);border:1px solid var(--b2);color:var(--t2);padding:5px 12px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:11px;font-weight:600;transition:all .12s;white-space:nowrap}
.tb-btn:hover{border-color:var(--ac);color:var(--ac)}
.tb-btn.primary{background:var(--adim);color:var(--ac);border-color:#1e2e54}
.tb-btn.primary:hover{background:#172448}
.tb-btn:disabled{opacity:.4;cursor:default}
.sync-status{font-family:var(--mono);font-size:10px;color:var(--t3)}

/* ── stat chips ── */
.chips{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.chip{background:var(--s1);border:1px solid var(--b1);border-radius:5px;padding:3px 9px;font-family:var(--mono);font-size:11px;color:var(--t2);white-space:nowrap}
.chip b{color:var(--t1)}
.chip.pos b{color:var(--gr)}
.chip.neg b{color:var(--re)}

/* ── layout ── */
#content{display:flex;flex:1;overflow:hidden;min-height:0}

/* ── sidebar ── */
#sidebar{width:300px;display:flex;flex-direction:column;border-right:1px solid var(--b1);flex-shrink:0;background:var(--bg)}

/* ── filters ── */
#filters{padding:8px;border-bottom:1px solid var(--b1);display:flex;flex-wrap:wrap;gap:5px;background:var(--s1)}
#filters select{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:3px 6px;border-radius:4px;font-size:10px;font-family:var(--ui);cursor:pointer;min-width:0}

/* ── trade list ── */
#trade-list{flex:1;overflow-y:auto}
.trade-row{display:grid;grid-template-columns:74px 24px 54px 1fr 18px;gap:3px;align-items:center;padding:4px 8px;border-bottom:1px solid var(--b1);cursor:pointer;transition:background 0.08s}
.trade-row:hover{background:var(--s1)}
.trade-row.selected{background:var(--adim);border-left:2px solid var(--ac);padding-left:6px}
.tr-date{color:var(--t3);font-family:var(--mono);font-size:10px}
.tr-dir{font-size:10px;font-weight:700;font-family:var(--mono)}
.tr-dir.long{color:var(--gr)}
.tr-dir.short{color:var(--re)}
.tr-pnl{font-size:11px;font-weight:600;text-align:right;font-family:var(--mono)}
.tr-pnl.pos{color:var(--gr)}
.tr-pnl.neg{color:var(--re)}
.badges{display:flex;gap:2px;flex-wrap:wrap;min-width:0;overflow:hidden}
.badge{font-size:8px;padding:1px 3px;border-radius:3px;font-weight:700;letter-spacing:0.3px;white-space:nowrap;font-family:var(--mono)}
.b-bar-ok{background:#0d2014;color:var(--gr);border:1px solid #1a3a20}
.b-bar-no{background:#200d12;color:var(--re);border:1px solid #3a1a1e}
.b-4h-ok{background:#0d1428;color:var(--ac);border:1px solid #1a2848}
.b-4h-no{background:#1e0d28;color:#b060e0;border:1px solid #3a1a48}
.b-dip{background:#281e0d;color:var(--am);border:1px solid #483a1a}
.b-mom{background:#0d2814;color:#60e080;border:1px solid #1a4828}
.b-neu{background:var(--s2);color:var(--t3);border:1px solid var(--b2)}
.b-setup{background:#1e0d3a;color:#c084fc;border:1px solid #3a1a5a}
.tag-dot{width:7px;height:7px;border-radius:50%;background:var(--b2);border:1px solid var(--b3);cursor:pointer;flex-shrink:0;transition:all .12s}
.tag-dot:hover{border-color:var(--ac)}
.tag-dot.tagged{background:#c084fc;border-color:#9d4dfc}

/* ── edge panel ── */
#edge-panel{border-top:1px solid var(--b1);background:var(--s1);padding:8px;flex-shrink:0;max-height:200px;overflow-y:auto}
#edge-panel h3{font-size:9px;color:var(--t3);letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px}
.edge-tbl{width:100%;border-collapse:collapse;font-size:10px;font-family:var(--mono)}
.edge-tbl th{color:var(--t3);text-align:left;padding:2px 5px;font-weight:400;border-bottom:1px solid var(--b1);font-size:9px;text-transform:uppercase;letter-spacing:.1em}
.edge-tbl td{padding:3px 5px;border-bottom:1px solid var(--b1)}
.edge-tbl tr:hover td{background:var(--s2)}

/* ── main ── */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;background:var(--bg)}
#chart-container{flex:1;min-height:0}

/* ── detail panel ── */
#detail{height:130px;border-top:1px solid var(--b1);background:var(--s1);padding:10px 16px;display:flex;gap:16px;flex-shrink:0;overflow:hidden}
#det-left{flex:1;min-width:0}
#det-right{width:220px;flex-shrink:0}
.det-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
.df label{font-size:9px;color:var(--t3);display:block;letter-spacing:.1em;text-transform:uppercase;margin-bottom:2px}
.df value{font-size:12px;font-weight:600;font-family:var(--mono)}
#setup-row{margin-top:8px;display:flex;align-items:center;gap:8px}
#setup-row label{font-size:9px;color:var(--t3);letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
#setup-select{flex:1;background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 7px;border-radius:4px;font-size:11px;font-family:var(--ui);cursor:pointer;transition:border-color .12s}
#setup-select:focus{outline:none;border-color:var(--ac)}
.cond-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.cond-item{background:var(--s2);border:1px solid var(--b1);border-radius:6px;padding:6px 8px}
.cond-item label{font-size:9px;color:var(--t3);display:block;text-transform:uppercase;letter-spacing:.08em;margin-bottom:2px}
.cond-item value{font-size:12px;font-weight:700;font-family:var(--mono)}
#no-sel{color:var(--t3);font-size:12px;padding:10px 0}

/* ── modal ── */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;align-items:center;justify-content:center}
.modal-bg.open{display:flex}
.modal{background:var(--s1);border:1px solid var(--b2);border-radius:10px;padding:20px 24px;width:420px;max-width:95vw}
.modal h2{font-size:14px;font-weight:700;margin-bottom:16px;color:var(--t1)}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
.fld{display:flex;flex-direction:column;gap:4px}
.fld label{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--t3);font-weight:700}
.fld input,.fld select{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:6px 9px;border-radius:5px;font-family:var(--mono);font-size:12px;transition:border-color .12s;width:100%}
.fld input:focus,.fld select:focus{outline:none;border-color:var(--ac)}
.modal-btns{display:flex;gap:8px;justify-content:flex-end}
.btn-cancel{background:transparent;border:1px solid var(--b2);color:var(--t2);padding:7px 16px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:12px}
.btn-save{background:var(--adim);color:var(--ac);border:1px solid #1e2e54;padding:7px 16px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:12px;font-weight:600}
.btn-save:hover{background:#172448}

::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}

/* ── phone (<=700px): restack the 3-pane IDE vertically + detail as a slide-up sheet ── */
#det-close{display:none}
@media(max-width:700px){
  html,body{height:auto;overflow:auto}
  body{display:block}
  .topbar{position:sticky;top:0;z-index:20}
  #content{flex-direction:column;overflow:visible;min-height:0}
  #main{order:-1;display:block;flex:none;min-width:0}
  #chart-container{height:42vh;min-height:240px}
  #sidebar{width:100%;border-right:none;border-top:1px solid var(--b1)}
  #filters{position:sticky;top:52px;z-index:5}
  #trade-list{flex:none;max-height:none}
  #edge-panel{max-height:none}
  /* detail panel → bottom sheet, revealed when a trade is picked */
  #detail{position:fixed;left:0;right:0;bottom:0;height:auto;max-height:72vh;
    flex-direction:column;gap:10px;overflow-y:auto;z-index:60;
    transform:translateY(105%);transition:transform .25s ease;
    box-shadow:0 -10px 30px rgba(0,0,0,.55);border-top:1px solid var(--b2)}
  #detail.open{transform:translateY(0)}
  #det-left,#det-right{width:100%}
  .det-grid{grid-template-columns:repeat(2,1fr)}
  #det-close{display:block;width:100%;background:var(--s2);border:none;
    border-bottom:1px solid var(--b1);color:var(--t2);font-family:var(--ui);
    font-size:12px;padding:10px;cursor:pointer;position:sticky;top:0}
}
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">LEN<span class="s">S</span> <span class="pg">Review</span></div>
  <div class="modesw">
    <a href="/prop">◎ PROP</a>
    <a href="/dashboard" class="on">▤ HEDGE</a>
    <a href="/" class="home">⌂</a>
  </div>
  <nav class="topnav">
    <a href="/dashboard">Dashboard</a>
    <a href="/desk">Desk</a>
    <a href="/signals">Signals</a>
    <a href="/review" class="cur">Review</a>
    <a href="/projection">Projection</a>
  </nav>
  <div class="topbar-right">
    <div class="chips">
      <div class="chip">WR <b id="s-wr">—</b></div>
      <div class="chip">Avg <b id="s-avg">—</b></div>
      <div class="chip">n=<b id="s-n">—</b></div>
      <div class="chip">Total <b id="s-total">—</b></div>
    </div>
    <button class="tb-btn" onclick="openLogModal()">+ Log Trade</button>
    <button class="tb-btn primary" id="sync-btn" onclick="syncKraken()">Sync Kraken</button>
    <span class="sync-status" id="sync-status"></span>
    <button class="tb-btn" onclick="exportCSV()">Export CSV</button>
  </div>
</div>

<div id="content">
  <div id="sidebar">
    <div id="filters">
      <select id="f-dir"    onchange="filter()"><option value="">All dirs</option><option>long</option><option>short</option></select>
      <select id="f-tag"    onchange="filter()"><option value="">All setups</option><option value="__none__">Untagged</option></select>
      <select id="f-bar"    onchange="filter()"><option value="">Bar: all</option><option value="true">Bar ✓</option><option value="false">Bar ✗</option></select>
      <select id="f-4h"     onchange="filter()"><option value="">4H: all</option><option value="true">4H ✓</option><option value="false">4H ✗</option></select>
      <select id="f-rsi"    onchange="filter()"><option value="">RSI: all</option><option value="dip">Dip &lt;40</option><option value="momentum">Mom &gt;55</option><option value="neutral">Neutral</option></select>
      <select id="f-result" onchange="filter()"><option value="">All results</option><option value="win">Wins</option><option value="loss">Losses</option></select>
    </div>
    <div id="trade-list"><div style="padding:16px;color:var(--t3)">Loading…</div></div>
    <div id="edge-panel">
      <h3>Edge by Setup Tag</h3>
      <table class="edge-tbl">
        <thead><tr><th>Setup</th><th>n</th><th>WR</th><th>Avg€</th><th>Total€</th><th>Verdict</th></tr></thead>
        <tbody id="edge-body"></tbody>
      </table>
    </div>
  </div>

  <div id="main">
    <div id="chart-container"></div>
    <div id="detail">
      <button id="det-close" onclick="document.getElementById('detail').classList.remove('open')">▾ close</button>
      <div id="det-left">
        <div class="det-grid" id="det-grid"><div id="no-sel">← select a trade to review</div></div>
        <div id="setup-row" style="display:none">
          <label>Setup Tag</label>
          <select id="setup-select" onchange="saveTag(this.value)">
            <option value="">— untagged —</option>
            <option value="DIP">DIP (RSI&lt;40 pullback)</option>
            <option value="MOMENTUM">MOMENTUM (RSI&gt;55)</option>
            <option value="FOMO">FOMO (chased entry)</option>
            <option value="COUNTER">COUNTER-TREND</option>
            <option value="SCALP">SCALP</option>
            <option value="RANGE">RANGE play</option>
            <option value="REVERSAL">REVERSAL</option>
            <option value="QUALITY">QUALITY (all 3 rules)</option>
            <option value="GARBAGE">GARBAGE (no rules met)</option>
          </select>
        </div>
      </div>
      <div id="det-right"><div class="cond-grid" id="cond-grid"></div></div>
    </div>
  </div>
</div>

<!-- Log Trade Modal -->
<div class="modal-bg" id="log-modal" onclick="if(event.target===this)closeLogModal()">
  <div class="modal">
    <h2>Log Trade Manually</h2>
    <div class="form-grid">
      <div class="fld">
        <label>Direction</label>
        <select id="m-dir"><option value="long">Long</option><option value="short">Short</option></select>
      </div>
      <div class="fld">
        <label>Symbol</label>
        <select id="m-symbol">
          <option value="BTC/USD:USD">BTC/USD:USD (Kraken)</option>
          <option value="BTC/USDT:USDT">BTC/USDT:USDT (Bybit)</option>
        </select>
      </div>
      <div class="fld"><label>Entry Price ($)</label><input id="m-entry" type="number" step="any" placeholder="84000"></div>
      <div class="fld"><label>Exit Price ($)</label><input id="m-exit" type="number" step="any" placeholder="86000"></div>
      <div class="fld"><label>Size (BTC)</label><input id="m-size" type="number" step="any" placeholder="0.01"></div>
      <div class="fld"><label>Leverage</label><input id="m-lev" type="number" step="any" placeholder="5" value="1"></div>
      <div class="fld"><label>PnL (€)</label><input id="m-pnl" type="number" step="any" placeholder="42.50"></div>
      <div class="fld"><label>Fees (€)</label><input id="m-fees" type="number" step="any" placeholder="0.80" value="0"></div>
      <div class="fld"><label>Opened At</label><input id="m-open" type="datetime-local"></div>
      <div class="fld"><label>Closed At</label><input id="m-close" type="datetime-local"></div>
    </div>
    <div class="fld" style="margin-bottom:16px"><label>Notes</label><input id="m-notes" type="text" placeholder="optional notes"></div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeLogModal()">Cancel</button>
      <button class="btn-save" onclick="submitLog()">Save Trade</button>
    </div>
  </div>
</div>

<script>
let ALL_TRADES = [], CANDLES = [], visible = [], selected = null;

// ── chart ──────────────────────────────────────────────────────────────────────
const chartEl = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(chartEl, {
  layout: { background:{color:'#06080c'}, textColor:'#465064' },
  grid:   { vertLines:{color:'#192232'}, horzLines:{color:'#192232'} },
  crosshair: { mode:LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor:'#192232' },
  timeScale: { borderColor:'#192232', timeVisible:true, secondsVisible:false },
});
const series = chart.addCandlestickSeries({
  upColor:'#1fd989', downColor:'#ff5468',
  borderUpColor:'#1fd989', borderDownColor:'#ff5468',
  wickUpColor:'#1fd989', wickDownColor:'#ff5468',
});
new ResizeObserver(() => chart.applyOptions({width:chartEl.clientWidth, height:chartEl.clientHeight})).observe(chartEl);

const activeLines = [];
function clearOverlays() {
  activeLines.forEach(l => { try { series.removePriceLine(l); } catch(e){} });
  activeLines.length = 0;
  series.setMarkers([]);
}
function showTrade(t) {
  clearOverlays();
  const isL = t.direction === 'long';
  const ec  = isL ? '#1fd989' : '#ff5468';
  if (t.entry) activeLines.push(series.createPriceLine({price:t.entry, color:ec, lineWidth:1, lineStyle:LightweightCharts.LineStyle.Solid, axisLabelVisible:true, title:'ENTRY'}));
  if (t.exit)  activeLines.push(series.createPriceLine({price:t.exit, color:'#828ea6', lineWidth:1, lineStyle:LightweightCharts.LineStyle.Dashed, axisLabelVisible:true, title:'EXIT'}));
  const ms = [];
  if (t.ts_entry) ms.push({time:t.ts_entry, position:isL?'belowBar':'aboveBar', color:ec, shape:isL?'arrowUp':'arrowDown', text:'E', size:1.5});
  if (t.ts_exit)  ms.push({time:t.ts_exit, position:isL?'aboveBar':'belowBar', color:isL?'#ff5468':'#1fd989', shape:isL?'arrowDown':'arrowUp', text:'X', size:1.5});
  series.setMarkers(ms);
  chart.timeScale().setVisibleRange({from:t.ts_entry-48*3600, to:(t.ts_exit||t.ts_entry)+24*3600});
}

// ── save tag ───────────────────────────────────────────────────────────────────
async function saveTag(val) {
  if (!selected) return;
  selected.setup_tag = val;
  renderList(); renderEdge(); updateStats();
  try {
    await fetch(`/api/trades/${selected.id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({setup_tag: val || null})
    });
    buildTagFilter();
  } catch(e) { console.error('Tag save failed', e); }
}

// ── filters ────────────────────────────────────────────────────────────────────
function filter() {
  const dir = document.getElementById('f-dir').value;
  const tag = document.getElementById('f-tag').value;
  const bar = document.getElementById('f-bar').value;
  const th  = document.getElementById('f-4h').value;
  const rsi = document.getElementById('f-rsi').value;
  const res = document.getElementById('f-result').value;
  visible = ALL_TRADES.filter(t => {
    if (dir && t.direction !== dir) return false;
    const tg = t.setup_tag || '';
    if (tag === '__none__' && tg) return false;
    if (tag && tag !== '__none__' && tg !== tag) return false;
    if (bar && String(t.bar_aligned) !== bar) return false;
    if (th  && String(t.trend_aligned) !== th) return false;
    if (rsi && t.rsi_zone !== rsi) return false;
    if (res === 'win'  && (t.pnl||0) <= 0) return false;
    if (res === 'loss' && (t.pnl||0) >= 0) return false;
    return true;
  });
  renderList(); renderEdge(); updateStats();
}

// ── render list ────────────────────────────────────────────────────────────────
function renderList() {
  const el = document.getElementById('trade-list');
  if (!visible.length) { el.innerHTML='<div style="padding:16px;color:var(--t3)">No trades match</div>'; return; }
  el.innerHTML = visible.slice().reverse().map(t => {
    const pnl = t.pnl||0, ps = pnl>=0?'+':'';
    const sel = selected && selected.id===t.id;
    const bs = [];
    if (t.bar_aligned===true)  bs.push('<span class="badge b-bar-ok">BAR✓</span>');
    if (t.bar_aligned===false) bs.push('<span class="badge b-bar-no">BAR✗</span>');
    if (t.trend_aligned===true)  bs.push('<span class="badge b-4h-ok">4H✓</span>');
    if (t.trend_aligned===false) bs.push('<span class="badge b-4h-no">4H✗</span>');
    if (t.rsi_zone==='dip')      bs.push('<span class="badge b-dip">DIP</span>');
    if (t.rsi_zone==='momentum') bs.push('<span class="badge b-mom">MOM</span>');
    if (t.rsi_zone==='neutral')  bs.push('<span class="badge b-neu">NEU</span>');
    if (t.setup_tag) bs.push(`<span class="badge b-setup">${t.setup_tag}</span>`);
    return `<div class="trade-row${sel?' selected':''}" onclick="pick(${t.id})">
      <span class="tr-date">${t.opened_at.slice(0,16)}</span>
      <span class="tr-dir ${t.direction}">${t.direction==='long'?'L':'S'}</span>
      <span class="tr-pnl ${pnl>=0?'pos':'neg'}">${ps}${pnl.toFixed(0)}€</span>
      <div class="badges">${bs.join('')}</div>
      <div class="tag-dot${t.setup_tag?' tagged':''}" title="Click to tag" onclick="event.stopPropagation();pick(${t.id});document.getElementById('setup-select').focus()"></div>
    </div>`;
  }).join('');
  // scroll selected into view
  if (selected) {
    const rows = el.querySelectorAll('.trade-row');
    rows.forEach(r => { if (r.classList.contains('selected')) r.scrollIntoView({block:'nearest'}); });
  }
}

// ── pick trade ─────────────────────────────────────────────────────────────────
function pick(id) {
  selected = ALL_TRADES.find(t => t.id===id);
  if (!selected) return;
  renderList();
  showTrade(selected);
  renderDetail(selected);
  document.getElementById('detail').classList.add('open');  // reveal sheet on phone (no-op on desktop)
}

function renderDetail(t) {
  const pnl = t.pnl||0;
  const dur = t.ts_exit ? Math.round((t.ts_exit-t.ts_entry)/60) : null;
  const durS = dur ? (dur<60?dur+'m':Math.round(dur/60)+'h') : '—';
  document.getElementById('det-grid').innerHTML = `
    <div class="df"><label>Direction</label><value style="color:${t.direction==='long'?'var(--gr)':'var(--re)'}">${t.direction.toUpperCase()}</value></div>
    <div class="df"><label>PnL</label><value style="color:${pnl>=0?'var(--gr)':'var(--re)'}">${pnl>=0?'+':''}${pnl.toFixed(2)}€</value></div>
    <div class="df"><label>Move</label><value>${t.move_pct!=null?(t.move_pct>0?'+':'')+t.move_pct+'%':'—'}</value></div>
    <div class="df"><label>Hold</label><value>${durS}</value></div>
    <div class="df"><label>Entry</label><value>$${t.entry?.toFixed(0)||'—'}</value></div>
    <div class="df"><label>Exit</label><value>$${t.exit?.toFixed(0)||'—'}</value></div>
    <div class="df"><label>Size</label><value>${t.size?.toFixed(4)||'—'}</value></div>
    <div class="df"><label>Lev</label><value>${t.leverage||'—'}×</value></div>
  `;
  document.getElementById('setup-row').style.display = 'flex';
  document.getElementById('setup-select').value = t.setup_tag || '';
  document.getElementById('cond-grid').innerHTML = `
    <div class="cond-item"><label>Entry Bar</label>
      <value style="color:${t.bar_aligned===true?'var(--gr)':t.bar_aligned===false?'var(--re)':'var(--t3)'}">
        ${t.bar_dir?(t.bar_dir.toUpperCase()+(t.bar_aligned?' ✓':' ✗')):'—'}</value></div>
    <div class="cond-item"><label>4H Trend</label>
      <value style="color:${t.trend_aligned===true?'var(--gr)':t.trend_aligned===false?'var(--re)':'var(--t3)'}">
        ${t.trend_4h?(t.trend_4h.toUpperCase()+(t.trend_aligned?' ✓':' ✗')):'—'}</value></div>
    <div class="cond-item"><label>RSI @ Entry</label>
      <value style="color:${t.rsi_zone==='dip'?'var(--am)':t.rsi_zone==='momentum'?'var(--gr)':'var(--t3)'}">
        ${t.rsi!=null?t.rsi:'—'} <small style="font-size:9px;opacity:.7">${t.rsi_zone||''}</small></value></div>
    <div class="cond-item"><label>Bal After</label>
      <value>${t.balance_after!=null?t.balance_after.toFixed(2)+'€':'—'}</value></div>
  `;
}

// ── edge table ─────────────────────────────────────────────────────────────────
// Collapse a raw setup_tag into a readable family: S1..S5 stand alone, a
// matched-but-vetoed setup → "Sx (vetoed)", a pure veto → "VETO", else as-is.
function edgeFamily(tag){
  if(!tag) return '(untagged)';
  if(tag.startsWith('VETO:')) return 'VETO';
  if(tag.includes('|VETO:')) return tag.split('|')[0]+' (vetoed)';
  return tag;
}
// KEEP/CUT/SIZE-UP from realised expectancy + sample. Thin samples say so.
function edgeVerdict(n,wr,exp){
  if(n<8)              return ['THIN','var(--t3)'];
  if(exp<=0)           return ['CUT','var(--re)'];
  if(exp>=10&&n>=12&&wr>=45) return ['SIZE-UP','var(--gr)'];
  return ['KEEP','var(--am)'];
}
function renderEdge() {
  const g = {};
  visible.forEach(t => {
    const k = edgeFamily(t.setup_tag);
    if (!g[k]) g[k]={n:0,wins:0,total:0,byGrade:{}};
    g[k].n++; if ((t.pnl||0)>0) g[k].wins++; g[k].total+=t.pnl||0;
    const gr=t.grade||'—';
    if(!g[k].byGrade[gr]) g[k].byGrade[gr]={n:0,wins:0,total:0};
    g[k].byGrade[gr].n++; if((t.pnl||0)>0) g[k].byGrade[gr].wins++; g[k].byGrade[gr].total+=t.pnl||0;
  });
  const rows = Object.entries(g).sort((a,b)=>b[1].total-a[1].total);
  document.getElementById('edge-body').innerHTML = rows.map(([k,d])=>{
    const exp=d.total/d.n, wr=d.wins/d.n*100;
    const [vlabel,vcol]=edgeVerdict(d.n,wr,exp);
    const grades=Object.entries(d.byGrade).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
    const sub = grades.length>1 ? grades.map(([gr,gd])=>
      `<span style="display:inline-block;font-size:9px;padding:1px 5px;margin:3px 4px 0 0;border:1px solid var(--b3);border-radius:3px;color:var(--t2)">`+
      `${gr}: ${gd.n}·${(gd.wins/gd.n*100).toFixed(0)}%·<span style="color:${gd.total>=0?'var(--gr)':'var(--re)'}">${gd.total>=0?'+':''}${gd.total.toFixed(0)}€</span></span>`
    ).join('') : '';
    return `<tr>
      <td>${k}</td><td>${d.n}</td>
      <td>${wr.toFixed(0)}%</td>
      <td style="color:${exp>=0?'var(--gr)':'var(--re)'}">${(exp>=0?'+':'')+exp.toFixed(0)}€</td>
      <td style="color:${d.total>=0?'var(--gr)':'var(--re)'}">${(d.total>=0?'+':'')+d.total.toFixed(0)}€</td>
      <td><b style="color:${vcol}">${vlabel}</b></td>
    </tr>${sub?`<tr><td colspan="6" style="padding:0 0 4px 8px">${sub}</td></tr>`:''}`;
  }).join('');
}

// ── header stats ───────────────────────────────────────────────────────────────
function updateStats() {
  const n = visible.length;
  const wins  = visible.filter(t=>(t.pnl||0)>0).length;
  const total = visible.reduce((s,t)=>s+(t.pnl||0),0);
  const avg   = n ? total/n : 0;
  document.getElementById('s-wr').textContent    = n ? (wins/n*100).toFixed(1)+'%' : '—';
  document.getElementById('s-avg').textContent   = n ? (avg>=0?'+':'')+avg.toFixed(0)+'€' : '—';
  document.getElementById('s-n').textContent     = n;
  document.getElementById('s-total').textContent = n ? (total>=0?'+':'')+total.toFixed(0)+'€' : '—';
  document.querySelector('#s-total').parentElement.className = 'chip '+(total>=0?'pos':'neg');
}

// ── tag filter ─────────────────────────────────────────────────────────────────
function buildTagFilter() {
  const used = [...new Set(ALL_TRADES.map(t=>t.setup_tag).filter(Boolean))].sort();
  const sel  = document.getElementById('f-tag');
  const cur  = sel.value;
  sel.innerHTML = '<option value="">All setups</option><option value="__none__">Untagged</option>';
  used.forEach(tg => { const o=document.createElement('option'); o.value=o.textContent=tg; sel.appendChild(o); });
  sel.value = cur;
}

// ── sync kraken ────────────────────────────────────────────────────────────────
let syncPoll = null;
async function syncKraken() {
  const btn = document.getElementById('sync-btn');
  const st  = document.getElementById('sync-status');
  btn.disabled = true; btn.textContent = 'Syncing…'; st.textContent = '';
  try {
    await fetch('/api/sync/kraken', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    syncPoll = setInterval(async () => {
      const r = await fetch('/api/sync/kraken/result?account=personal');
      const d = await r.json();
      st.textContent = d.detail || '';
      if (!d.running) {
        clearInterval(syncPoll); syncPoll = null;
        btn.disabled = false; btn.textContent = 'Sync Kraken';
        // reload trades
        const res = await fetch('/api/review/trades');
        ALL_TRADES = await res.json();
        buildTagFilter(); filter();
      }
    }, 2000);
  } catch(e) {
    btn.disabled = false; btn.textContent = 'Sync Kraken';
    st.textContent = 'Error: ' + e.message;
  }
}

// ── log trade modal ────────────────────────────────────────────────────────────
function openLogModal() {
  // prefill datetime with now
  const now = new Date();
  const fmt = d => d.toISOString().slice(0,16);
  document.getElementById('m-open').value  = fmt(now);
  document.getElementById('m-close').value = fmt(now);
  document.getElementById('log-modal').classList.add('open');
}
function closeLogModal() {
  document.getElementById('log-modal').classList.remove('open');
}
async function submitLog() {
  const toISO = s => s ? new Date(s).toISOString() : null;
  const payload = {
    direction:  document.getElementById('m-dir').value,
    symbol:     document.getElementById('m-symbol').value,
    entry:      parseFloat(document.getElementById('m-entry').value),
    exit:       parseFloat(document.getElementById('m-exit').value)||null,
    size:       parseFloat(document.getElementById('m-size').value)||0.001,
    leverage:   parseFloat(document.getElementById('m-lev').value)||1,
    pnl:        parseFloat(document.getElementById('m-pnl').value)||null,
    fees:       parseFloat(document.getElementById('m-fees').value)||0,
    notes:      document.getElementById('m-notes').value||null,
    opened_at:  toISO(document.getElementById('m-open').value),
    closed_at:  toISO(document.getElementById('m-close').value),
    venue:      'manual',
  };
  if (!payload.entry) return alert('Entry price required');
  try {
    const r = await fetch('/api/trades', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) { const e=await r.json(); throw new Error(JSON.stringify(e)); }
    closeLogModal();
    // reload
    const res = await fetch('/api/review/trades');
    ALL_TRADES = await res.json();
    buildTagFilter(); filter();
    // select new trade
    pick(ALL_TRADES[ALL_TRADES.length-1].id);
  } catch(e) { alert('Save failed: ' + e.message); }
}

// ── export ─────────────────────────────────────────────────────────────────────
function exportCSV() {
  const hdr = 'id,opened_at,direction,pnl,setup_tag,bar_aligned,trend_4h_aligned,rsi_zone,rsi,move_pct';
  const rows = ALL_TRADES.map(t=>[t.id,t.opened_at,t.direction,t.pnl||0,t.setup_tag||'',
    t.bar_aligned??'',t.trend_aligned??'',t.rsi_zone||'',t.rsi??'',t.move_pct??''].join(','));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([[hdr,...rows].join('\n')],{type:'text/csv'}));
  a.download = 'lens_trades_tagged.csv'; a.click();
}

// ── init ───────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const [tr, ca] = await Promise.all([fetch('/api/review/trades'), fetch('/api/review/ohlcv')]);
    ALL_TRADES = await tr.json();
    CANDLES    = await ca.json();
    series.setData(CANDLES);
    buildTagFilter();
    filter();
    if (ALL_TRADES.length) pick(ALL_TRADES[ALL_TRADES.length-1].id);
  } catch(e) {
    document.getElementById('trade-list').innerHTML = `<div style="padding:16px;color:var(--re)">Load error: ${e.message}</div>`;
  }
}
init();
</script>
</body>
</html>
"""
