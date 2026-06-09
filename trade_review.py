#!/usr/bin/env python3
"""Generate trade_review.html — visual trade reviewer with edge computation."""

import bisect
import datetime
import json
import math
import sqlite3

DB  = "/home/mini/lens/lens.db"
OUT = "/home/mini/lens/trade_review.html"

CANDLE_STEP_1H = 3_600_000   # ms
CANDLE_STEP_4H = 14_400_000  # ms
APR25_MS = int(datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
EMA_WARMUP_4H = 100  # extra 4h bars before Apr25 for EMA50 warmup


# ── math helpers ──────────────────────────────────────────────────────────────

def compute_ema(closes, period):
    k = 2 / (period + 1)
    result = []
    avg = None
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


def compute_rsi(closes, period=14):
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
    losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    result[period] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + gains[i-1]) / period
        avg_l = (avg_l * (period - 1) + losses[i-1]) / period
        result[i] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return result


def bar_idx(ts_arr, target_ms):
    """Index of the bar whose open is <= target_ms (i.e. bar containing target)."""
    i = bisect.bisect_right(ts_arr, target_ms) - 1
    return i if i >= 0 else None


def parse_ts(iso_str):
    """ISO 8601 string → UTC timestamp ms."""
    s = iso_str.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


# ── data loading ──────────────────────────────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB)
    cur  = conn.cursor()

    cur.execute("""
        SELECT ts, open, high, low, close, volume
        FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    c1h = cur.fetchall()

    warmup_ms = APR25_MS - EMA_WARMUP_4H * CANDLE_STEP_4H
    cur.execute("""
        SELECT ts, open, high, low, close
        FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='4h' AND ts >= ?
        ORDER BY ts
    """, (warmup_ms,))
    c4h = cur.fetchall()

    cur.execute("""
        SELECT id, direction, entry, exit, pnl, fees, size, leverage,
               opened_at, closed_at, notes, balance_after
        FROM trades WHERE closed_at IS NOT NULL ORDER BY opened_at
    """)
    trades = cur.fetchall()

    conn.close()
    return c1h, c4h, trades


# ── enrichment ────────────────────────────────────────────────────────────────

def enrich(trades, c1h, c4h):
    ts1h   = [r[0] for r in c1h]
    open1h = [r[1] for r in c1h]
    clos1h = [r[4] for r in c1h]
    rsi14  = compute_rsi(clos1h, 14)

    ts4h   = [r[0] for r in c4h]
    clos4h = [r[4] for r in c4h]
    ema21  = compute_ema(clos4h, 21)
    ema50  = compute_ema(clos4h, 50)

    out = []
    for row in trades:
        (tid, direction, entry, exit_, pnl, fees, size, leverage,
         opened_at, closed_at, notes, bal_after) = row

        ts_e = parse_ts(opened_at)
        ts_x = parse_ts(closed_at)

        i1 = bar_idx(ts1h, ts_e)
        i4 = bar_idx(ts4h, ts_e)

        bar_dir = bar_aligned = rsi_val = rsi_zone = None
        trend_4h = trend_aligned = None

        if i1 is not None and i1 < len(c1h):
            o, c = open1h[i1], clos1h[i1]
            bar_dir = "bull" if c >= o else "bear"
            bar_aligned = (bar_dir == "bull") == (direction == "long")
            rsi_val = rsi14[i1]
            if rsi_val is not None:
                if rsi_val < 40:
                    rsi_zone = "dip"
                elif rsi_val > 55:
                    rsi_zone = "momentum"
                else:
                    rsi_zone = "neutral"

        if i4 is not None and i4 < len(c4h):
            e21, e50 = ema21[i4], ema50[i4]
            if e21 and e50:
                trend_4h = "bull" if e21 > e50 else "bear"
                trend_aligned = (trend_4h == "bull") == (direction == "long")

        if entry and exit_:
            move_pct = ((exit_ - entry) / entry * 100) * (1 if direction == "long" else -1)
        else:
            move_pct = None

        out.append({
            "id":           tid,
            "direction":    direction,
            "entry":        entry,
            "exit":         exit_,
            "pnl":          pnl,
            "fees":         fees,
            "size":         size,
            "leverage":     leverage,
            "opened_at":    opened_at[:19].replace("T", " "),
            "closed_at":    closed_at[:19].replace("T", " "),
            "notes":        notes or "",
            "balance_after": bal_after,
            "ts_entry":     ts_e // 1000,
            "ts_exit":      ts_x // 1000,
            "bar_dir":      bar_dir,
            "bar_aligned":  bar_aligned,
            "rsi":          round(rsi_val, 1) if rsi_val else None,
            "rsi_zone":     rsi_zone,
            "trend_4h":     trend_4h,
            "trend_aligned": trend_aligned,
            "move_pct":     round(move_pct, 3) if move_pct else None,
        })
    return out


def candles_to_json(c1h):
    out = []
    for r in c1h:
        out.append({
            "time":   r[0] // 1000,
            "open":   r[1],
            "high":   r[2],
            "low":    r[3],
            "close":  r[4],
            "volume": r[5],
        })
    return out


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>LENS Trade Reviewer</title>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0e0e12;
  --bg2: #16161e;
  --bg3: #1e1e2a;
  --border: #2a2a3a;
  --text: #e0e0e8;
  --muted: #888;
  --green: #26a69a;
  --red: #ef5350;
  --blue: #5c9cf6;
  --orange: #f0a040;
  --purple: #a78bfa;
}
body { background: var(--bg); color: var(--text); font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 12px; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* header */
#hdr { display: flex; align-items: center; gap: 16px; padding: 8px 16px; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; }
#hdr h1 { font-size: 14px; letter-spacing: 2px; color: var(--blue); font-weight: 600; }
.stat-chip { background: var(--bg3); border: 1px solid var(--border); border-radius: 4px; padding: 3px 8px; font-size: 11px; }
.stat-chip span { font-weight: 700; }
#hdr-right { margin-left: auto; display: flex; gap: 8px; align-items: center; }

/* layout */
#content { display: flex; flex: 1; overflow: hidden; }

/* sidebar */
#sidebar { width: 310px; display: flex; flex-direction: column; border-right: 1px solid var(--border); flex-shrink: 0; }

/* filters */
#filters { padding: 8px; border-bottom: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 6px; background: var(--bg2); }
#filters select, #filters input { background: var(--bg3); border: 1px solid var(--border); color: var(--text); padding: 3px 6px; border-radius: 3px; font-size: 11px; font-family: inherit; }
#filters select { cursor: pointer; }

/* trade list */
#trade-list { flex: 1; overflow-y: auto; }
.trade-row { display: grid; grid-template-columns: 78px 28px 52px auto 18px; gap: 4px; align-items: center; padding: 5px 8px; border-bottom: 1px solid #1a1a24; cursor: pointer; transition: background 0.1s; }
.trade-row:hover { background: var(--bg3); }
.trade-row.selected { background: #1a2540; border-left: 2px solid var(--blue); }
.trade-row .date { color: var(--muted); font-size: 10px; }
.trade-row .dir { font-size: 10px; font-weight: 700; }
.dir.long { color: var(--green); }
.dir.short { color: var(--red); }
.trade-row .pnl { font-size: 11px; font-weight: 600; text-align: right; }
.pnl.pos { color: var(--green); }
.pnl.neg { color: var(--red); }
.badges { display: flex; gap: 2px; flex-wrap: wrap; }
.badge { font-size: 9px; padding: 1px 4px; border-radius: 3px; font-weight: 700; letter-spacing: 0.5px; }
.badge-bar-ok  { background: #1a3a1a; color: var(--green); }
.badge-bar-no  { background: #3a1a1a; color: var(--red); }
.badge-4h-ok   { background: #1a2a3a; color: var(--blue); }
.badge-4h-no   { background: #2a1a2a; color: #c77; }
.badge-dip     { background: #2a2a1a; color: var(--orange); }
.badge-mom     { background: #1a2a1a; color: #7f7; }
.badge-neu     { background: #2a2a2a; color: var(--muted); }
.badge-setup   { background: #2a1a3a; color: var(--purple); }
.setup-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); cursor: pointer; }
.setup-dot.tagged { background: var(--purple); }

/* edge stats */
#edge-panel { border-top: 1px solid var(--border); background: var(--bg2); padding: 8px; flex-shrink: 0; }
#edge-panel h3 { font-size: 10px; color: var(--muted); letter-spacing: 1px; margin-bottom: 6px; }
.edge-table { width: 100%; border-collapse: collapse; font-size: 10px; }
.edge-table th { color: var(--muted); text-align: left; padding: 2px 4px; font-weight: 400; }
.edge-table td { padding: 2px 4px; }
.edge-table tr:nth-child(even) td { background: #0d0d12; }

/* main */
#main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
#chart-container { flex: 1; }

/* detail */
#detail { height: 130px; border-top: 1px solid var(--border); background: var(--bg2); padding: 10px 16px; overflow-y: auto; display: flex; gap: 20px; }
#detail-left { flex: 1; }
#detail-right { width: 220px; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; }
.dfield { }
.dfield label { font-size: 9px; color: var(--muted); display: block; margin-bottom: 2px; letter-spacing: 0.8px; }
.dfield value { font-size: 12px; font-weight: 600; }
#setup-editor { margin-top: 8px; }
#setup-editor label { font-size: 9px; color: var(--muted); letter-spacing: 0.8px; }
#setup-select { background: var(--bg3); border: 1px solid var(--border); color: var(--text); padding: 4px 8px; border-radius: 4px; font-size: 11px; font-family: inherit; margin-top: 4px; width: 100%; cursor: pointer; }
#cond-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.cond-item { background: var(--bg3); border: 1px solid var(--border); border-radius: 4px; padding: 5px 8px; }
.cond-item label { font-size: 9px; color: var(--muted); display: block; }
.cond-item value { font-size: 12px; font-weight: 700; }

/* scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

#no-trade { padding: 20px; color: var(--muted); text-align: center; }
</style>
</head>
<body>

<div id="hdr">
  <h1>LENS REVIEW</h1>
  <div class="stat-chip">WR <span id="s-wr">—</span></div>
  <div class="stat-chip">Avg PnL <span id="s-avg">—</span></div>
  <div class="stat-chip">Trades <span id="s-n">—</span></div>
  <div class="stat-chip">Total <span id="s-total">—</span></div>
  <div id="hdr-right">
    <button onclick="exportTags()" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px;">Export Tags CSV</button>
  </div>
</div>

<div id="content">
  <div id="sidebar">
    <div id="filters">
      <select id="f-dir" onchange="applyFilters()">
        <option value="">All dirs</option>
        <option value="long">Long</option>
        <option value="short">Short</option>
      </select>
      <select id="f-tag" onchange="applyFilters()">
        <option value="">All setups</option>
        <option value="__none__">Untagged</option>
      </select>
      <select id="f-bar" onchange="applyFilters()">
        <option value="">Bar: all</option>
        <option value="true">Bar aligned</option>
        <option value="false">Bar counter</option>
      </select>
      <select id="f-4h" onchange="applyFilters()">
        <option value="">4H: all</option>
        <option value="true">4H aligned</option>
        <option value="false">4H counter</option>
      </select>
      <select id="f-rsi" onchange="applyFilters()">
        <option value="">RSI: all</option>
        <option value="dip">Dip &lt;40</option>
        <option value="momentum">Mom &gt;55</option>
        <option value="neutral">Neutral</option>
      </select>
      <select id="f-result" onchange="applyFilters()">
        <option value="">All results</option>
        <option value="win">Wins</option>
        <option value="loss">Losses</option>
      </select>
    </div>

    <div id="trade-list"></div>

    <div id="edge-panel">
      <h3>EDGE BY SETUP TAG</h3>
      <table class="edge-table">
        <thead><tr><th>Setup</th><th>n</th><th>WR</th><th>Avg€</th><th>Total€</th></tr></thead>
        <tbody id="edge-body"></tbody>
      </table>
    </div>
  </div>

  <div id="main">
    <div id="chart-container"></div>
    <div id="detail">
      <div id="detail-left">
        <div class="detail-grid" id="detail-grid">
          <div id="no-trade" style="grid-column:1/-1;color:var(--muted)">← Select a trade</div>
        </div>
        <div id="setup-editor" style="display:none">
          <label>SETUP TAG</label><br>
          <select id="setup-select" onchange="saveTag(this.value)">
            <option value="">— untagged —</option>
            <option value="DIP">DIP (RSI&lt;40 pullback)</option>
            <option value="MOMENTUM">MOMENTUM (RSI&gt;55 breakout)</option>
            <option value="FOMO">FOMO (chased)</option>
            <option value="COUNTER">COUNTER-TREND</option>
            <option value="SCALP">SCALP</option>
            <option value="RANGE">RANGE play</option>
            <option value="REVERSAL">REVERSAL</option>
            <option value="QUALITY">QUALITY (all 3 conditions)</option>
            <option value="GARBAGE">GARBAGE (0 conditions)</option>
          </select>
        </div>
      </div>
      <div id="detail-right">
        <div id="cond-grid"></div>
      </div>
    </div>
  </div>
</div>

<script>
const CANDLES = __CANDLES__;
const TRADES  = __TRADES__;

const SETUP_TAGS_KEY = 'lens_setup_tags_v1';
let tags = {};
try { tags = JSON.parse(localStorage.getItem(SETUP_TAGS_KEY) || '{}'); } catch(e) {}

function saveTag(val) {
  if (!selectedTrade) return;
  if (val) tags[selectedTrade.id] = val;
  else delete tags[selectedTrade.id];
  localStorage.setItem(SETUP_TAGS_KEY, JSON.stringify(tags));
  renderList();
  renderEdgeTable();
  updateHeaderStats();
}

function getTag(id) { return tags[id] || ''; }

// ── chart ────────────────────────────────────────────────────────────────────
const chartEl = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(chartEl, {
  layout: { background: { color: '#0e0e12' }, textColor: '#888' },
  grid: { vertLines: { color: '#1a1a24' }, horzLines: { color: '#1a1a24' } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#2a2a3a' },
  timeScale: { borderColor: '#2a2a3a', timeVisible: true, secondsVisible: false },
  handleScroll: true,
  handleScale: true,
});

const candleSeries = chart.addCandlestickSeries({
  upColor: '#26a69a', downColor: '#ef5350',
  borderUpColor: '#26a69a', borderDownColor: '#ef5350',
  wickUpColor: '#26a69a', wickDownColor: '#ef5350',
});
candleSeries.setData(CANDLES);

let entryLine = null, exitLine = null;
let markers = [];
const activeLines = [];

function clearOverlays() {
  activeLines.forEach(l => { try { candleSeries.removePriceLine(l); } catch(e){} });
  activeLines.length = 0;
  candleSeries.setMarkers([]);
}

function showTrade(t) {
  clearOverlays();

  const isLong = t.direction === 'long';
  const entryColor = isLong ? '#26a69a' : '#ef5350';
  const exitColor  = isLong ? '#ef5350' : '#26a69a';

  if (t.entry) {
    const l = candleSeries.createPriceLine({
      price: t.entry, color: entryColor, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true, title: 'ENTRY',
    });
    activeLines.push(l);
  }
  if (t.exit) {
    const l = candleSeries.createPriceLine({
      price: t.exit, color: '#aaa', lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title: 'EXIT',
    });
    activeLines.push(l);
  }

  const ms = [];
  if (t.ts_entry) ms.push({
    time: t.ts_entry,
    position: isLong ? 'belowBar' : 'aboveBar',
    color: entryColor,
    shape: isLong ? 'arrowUp' : 'arrowDown',
    text: 'E',
    size: 1.5,
  });
  if (t.ts_exit) ms.push({
    time: t.ts_exit,
    position: isLong ? 'aboveBar' : 'belowBar',
    color: exitColor,
    shape: isLong ? 'arrowDown' : 'arrowUp',
    text: 'X',
    size: 1.5,
  });
  candleSeries.setMarkers(ms);

  // Scroll to entry - 48 bars before to 24 after exit
  const from = t.ts_entry - 48 * 3600;
  const to   = (t.ts_exit || t.ts_entry) + 24 * 3600;
  chart.timeScale().setVisibleRange({ from, to });
}

// ── resize ────────────────────────────────────────────────────────────────────
new ResizeObserver(() => {
  chart.applyOptions({ width: chartEl.clientWidth, height: chartEl.clientHeight });
}).observe(chartEl);

// ── state ────────────────────────────────────────────────────────────────────
let visibleTrades = [...TRADES];
let selectedTrade = null;

// ── filters ───────────────────────────────────────────────────────────────────
function applyFilters() {
  const dir    = document.getElementById('f-dir').value;
  const tag    = document.getElementById('f-tag').value;
  const bar    = document.getElementById('f-bar').value;
  const th     = document.getElementById('f-4h').value;
  const rsi    = document.getElementById('f-rsi').value;
  const result = document.getElementById('f-result').value;

  visibleTrades = TRADES.filter(t => {
    if (dir && t.direction !== dir) return false;
    const tg = getTag(t.id);
    if (tag === '__none__' && tg) return false;
    if (tag && tag !== '__none__' && tg !== tag) return false;
    if (bar && String(t.bar_aligned) !== bar) return false;
    if (th  && String(t.trend_aligned) !== th) return false;
    if (rsi && t.rsi_zone !== rsi) return false;
    if (result === 'win'  && (t.pnl || 0) <= 0) return false;
    if (result === 'loss' && (t.pnl || 0) >= 0) return false;
    return true;
  });

  renderList();
  renderEdgeTable();
  updateHeaderStats();
}

// ── trade list ────────────────────────────────────────────────────────────────
function renderList() {
  const el = document.getElementById('trade-list');
  if (!visibleTrades.length) { el.innerHTML = '<div id="no-trade">No trades match filters</div>'; return; }

  el.innerHTML = visibleTrades.slice().reverse().map(t => {
    const tg  = getTag(t.id);
    const pnl = t.pnl || 0;
    const pnlStr = (pnl >= 0 ? '+' : '') + pnl.toFixed(0) + '€';
    const isSelected = selectedTrade && selectedTrade.id === t.id;

    const badges = [];
    if (t.bar_aligned === true)  badges.push('<span class="badge badge-bar-ok">BAR✓</span>');
    if (t.bar_aligned === false) badges.push('<span class="badge badge-bar-no">BAR✗</span>');
    if (t.trend_aligned === true)  badges.push('<span class="badge badge-4h-ok">4H✓</span>');
    if (t.trend_aligned === false) badges.push('<span class="badge badge-4h-no">4H✗</span>');
    if (t.rsi_zone === 'dip')      badges.push('<span class="badge badge-dip">DIP</span>');
    if (t.rsi_zone === 'momentum') badges.push('<span class="badge badge-mom">MOM</span>');
    if (t.rsi_zone === 'neutral')  badges.push('<span class="badge badge-neu">NEU</span>');
    if (tg) badges.push(`<span class="badge badge-setup">${tg}</span>`);

    return `<div class="trade-row${isSelected?' selected':''}" onclick="selectTrade(${t.id})">
      <span class="date">${t.opened_at.slice(0,16)}</span>
      <span class="dir ${t.direction}">${t.direction.toUpperCase().slice(0,1)}</span>
      <span class="pnl ${pnl>=0?'pos':'neg'}">${pnlStr}</span>
      <div class="badges">${badges.join('')}</div>
      <div class="setup-dot${tg?' tagged':''}" onclick="event.stopPropagation();selectTradeForTag(${t.id})" title="Tag setup"></div>
    </div>`;
  }).join('');
}

// ── select trade ──────────────────────────────────────────────────────────────
function selectTrade(id) {
  selectedTrade = TRADES.find(t => t.id === id);
  if (!selectedTrade) return;

  renderList();   // refresh selected highlight
  showTrade(selectedTrade);
  renderDetail(selectedTrade);
}

function selectTradeForTag(id) {
  selectTrade(id);
}

function renderDetail(t) {
  const pnl  = t.pnl || 0;
  const dur  = t.ts_exit ? Math.round((t.ts_exit - t.ts_entry) / 60) : null;
  const durStr = dur ? (dur < 60 ? dur + 'm' : Math.round(dur/60) + 'h') : '—';
  const tg = getTag(t.id);

  document.getElementById('detail-grid').innerHTML = `
    <div class="dfield"><label>DIR</label><value style="color:${t.direction==='long'?'#26a69a':'#ef5350'}">${t.direction.toUpperCase()}</value></div>
    <div class="dfield"><label>PNL</label><value style="color:${pnl>=0?'#26a69a':'#ef5350'}">${pnl>=0?'+':''}${pnl.toFixed(2)}€</value></div>
    <div class="dfield"><label>MOVE</label><value>${t.move_pct!=null?(t.move_pct>0?'+':'')+t.move_pct+'%':'—'}</value></div>
    <div class="dfield"><label>DURATION</label><value>${durStr}</value></div>
    <div class="dfield"><label>ENTRY</label><value>$${t.entry?.toFixed(0)||'—'}</value></div>
    <div class="dfield"><label>EXIT</label><value>$${t.exit?.toFixed(0)||'—'}</value></div>
    <div class="dfield"><label>SIZE</label><value>${t.size?.toFixed(4)||'—'}</value></div>
    <div class="dfield"><label>LEVERAGE</label><value>${t.leverage||'—'}×</value></div>
  `;

  document.getElementById('setup-editor').style.display = 'block';
  document.getElementById('setup-select').value = tg || '';

  document.getElementById('cond-grid').innerHTML = `
    <div class="cond-item"><label>ENTRY BAR</label>
      <value style="color:${t.bar_aligned===true?'#26a69a':t.bar_aligned===false?'#ef5350':'#888'}">
        ${t.bar_dir ? (t.bar_dir.toUpperCase() + (t.bar_aligned?' ✓':' ✗')) : '—'}</value></div>
    <div class="cond-item"><label>4H TREND</label>
      <value style="color:${t.trend_aligned===true?'#26a69a':t.trend_aligned===false?'#ef5350':'#888'}">
        ${t.trend_4h ? (t.trend_4h.toUpperCase() + (t.trend_aligned?' ✓':' ✗')) : '—'}</value></div>
    <div class="cond-item"><label>RSI @ ENTRY</label>
      <value style="color:${t.rsi_zone==='dip'?'#f0a040':t.rsi_zone==='momentum'?'#26a69a':'#888'}">
        ${t.rsi!=null?t.rsi:'—'} <small>${t.rsi_zone||''}</small></value></div>
    <div class="cond-item"><label>BALANCE AFTER</label>
      <value>${t.balance_after!=null?t.balance_after.toFixed(2)+'€':'—'}</value></div>
  `;
}

// ── edge table ────────────────────────────────────────────────────────────────
function renderEdgeTable() {
  const groups = {};

  visibleTrades.forEach(t => {
    const key = getTag(t.id) || '(untagged)';
    if (!groups[key]) groups[key] = { n: 0, wins: 0, total: 0 };
    groups[key].n++;
    if ((t.pnl || 0) > 0) groups[key].wins++;
    groups[key].total += t.pnl || 0;
  });

  const rows = Object.entries(groups).sort((a,b) => b[1].total - a[1].total);
  document.getElementById('edge-body').innerHTML = rows.map(([k, g]) =>
    `<tr>
      <td>${k}</td>
      <td>${g.n}</td>
      <td>${(g.wins/g.n*100).toFixed(0)}%</td>
      <td style="color:${g.total/g.n>=0?'#26a69a':'#ef5350'}">${(g.total/g.n>=0?'+':'')+(g.total/g.n).toFixed(0)}€</td>
      <td style="color:${g.total>=0?'#26a69a':'#ef5350'}">${(g.total>=0?'+':'')+(g.total).toFixed(0)}€</td>
    </tr>`
  ).join('');
}

// ── header stats ──────────────────────────────────────────────────────────────
function updateHeaderStats() {
  const n = visibleTrades.length;
  const wins = visibleTrades.filter(t => (t.pnl||0) > 0).length;
  const total = visibleTrades.reduce((s,t) => s + (t.pnl||0), 0);
  const avg = n ? total / n : 0;
  document.getElementById('s-wr').textContent    = n ? (wins/n*100).toFixed(1)+'%' : '—';
  document.getElementById('s-avg').textContent   = n ? (avg>=0?'+':'')+avg.toFixed(0)+'€' : '—';
  document.getElementById('s-n').textContent     = n;
  document.getElementById('s-total').textContent = n ? (total>=0?'+':'')+total.toFixed(0)+'€' : '—';
}

// ── populate tag filter ────────────────────────────────────────────────────────
function populateTagFilter() {
  const usedTags = [...new Set(Object.values(tags))].sort();
  const sel = document.getElementById('f-tag');
  const existing = ['', '__none__'];
  usedTags.forEach(tg => {
    if (!existing.includes(tg)) {
      const opt = document.createElement('option');
      opt.value = tg; opt.textContent = tg;
      sel.appendChild(opt);
    }
  });
}

// ── export ────────────────────────────────────────────────────────────────────
function exportTags() {
  const rows = ['id,opened_at,direction,pnl,setup_tag,bar_aligned,trend_4h_aligned,rsi_zone,rsi'];
  TRADES.forEach(t => {
    rows.push([t.id, t.opened_at, t.direction, t.pnl||0, getTag(t.id)||'',
      t.bar_aligned??'', t.trend_aligned??'', t.rsi_zone||'', t.rsi??''].join(','));
  });
  const blob = new Blob([rows.join('\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lens_trades_tagged.csv';
  a.click();
}

// ── init ──────────────────────────────────────────────────────────────────────
populateTagFilter();
applyFilters();
renderEdgeTable();
updateHeaderStats();

// Select most recent trade by default
if (TRADES.length) selectTrade(TRADES[TRADES.length-1].id);
</script>
</body>
</html>
"""


def main():
    print("Loading data from lens.db...")
    c1h, c4h, trades = load_data()
    print(f"  1h candles: {len(c1h)}, 4h candles: {len(c4h)}, trades: {len(trades)}")

    print("Enriching trades with edge conditions...")
    enriched = enrich(trades, c1h, c4h)
    candles  = candles_to_json(c1h)

    print(f"  Candles JSON: {len(candles)} rows")

    candles_js = json.dumps(candles, separators=(",", ":"))
    trades_js  = json.dumps(enriched, separators=(",", ":"))

    html = HTML.replace("__CANDLES__", candles_js).replace("__TRADES__", trades_js)

    with open(OUT, "w") as f:
        f.write(html)

    size_kb = len(html) / 1024
    print(f"Written: {OUT} ({size_kb:.0f} KB)")
    print("Open in browser: xdg-open trade_review.html")


if __name__ == "__main__":
    main()
