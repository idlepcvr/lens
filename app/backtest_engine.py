"""
LENS backtest engine.

Fetches BTC/USDT 4H OHLCV from Bybit (public, no auth), caches in SQLite,
computes indicators, runs strategy signal functions, simulates fixed-SL/TP
trades, returns metrics.

Usage:
    from app.backtest_engine import run_strategy, STRATEGIES
    result = run_strategy("PULLBACK_4R_v1")
"""

import time
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import ccxt

# ─── Paths ────────────────────────────────────────────────────────────────────
from .paths import DB_PATH as _DB_PATH

# ─── OHLCV cache ─────────────────────────────────────────────────────────────

def _ohlcv_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv_cache (
            symbol    TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            ts        INTEGER NOT NULL,
            open      REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, timeframe, ts)
        )
    """)
    conn.commit()
    return conn


def _fetch_from_exchange(symbol: str, timeframe: str, since_ms: int,
                         exchange_id: str = "bybit") -> list:
    if exchange_id == "binance":
        exchange = ccxt.binance({"enableRateLimit": True})
    else:
        exchange = ccxt.bybit({"enableRateLimit": True})
    now_ms = exchange.milliseconds()
    all_bars: list = []
    cur = since_ms
    while cur < now_ms - _tf_ms(timeframe):
        try:
            chunk = exchange.fetch_ohlcv(symbol, timeframe, since=cur, limit=1000)
        except Exception as e:
            print(f"[backtest_engine] fetch error: {e}")
            break
        if not chunk:
            break
        all_bars.extend(chunk)
        last_ts = chunk[-1][0]
        if last_ts <= cur:
            break
        cur = last_ts + 1
        time.sleep(0.25)
    return all_bars


def fetch_window(symbol: str, timeframe: str, since_ms: int, until_ms: int,
                 exchange_id: str = "bybit") -> list:
    """One bounded fetch for a specific historical window. Unlike
    _fetch_from_exchange (which always walks forward to 'now' — fine for
    warming a rolling cache, ruinous for 1m where 'now' could be years of
    bars away), this stops at `until_ms`. A trade from a year ago on 1m
    is one fast request (~150 bars, well under the 1000-bar API limit),
    not a backfill of everything since."""
    if exchange_id == "binance":
        exchange = ccxt.binance({"enableRateLimit": True})
    else:
        exchange = ccxt.bybit({"enableRateLimit": True})
    bars: list = []
    cur = since_ms
    while cur < until_ms:
        try:
            chunk = exchange.fetch_ohlcv(symbol, timeframe, since=cur, limit=1000)
        except Exception as e:
            print(f"[backtest_engine] fetch_window error: {e}")
            break
        if not chunk:
            break
        bars.extend(chunk)
        last_ts = chunk[-1][0]
        if last_ts <= cur:
            break
        cur = last_ts + 1
        if last_ts >= until_ms:
            break
    return [b for b in bars if b[0] <= until_ms]


def _tf_ms(timeframe: str) -> int:
    mapping = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
               "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
    return mapping.get(timeframe, 14_400_000)


def load_ohlcv(symbol: str = "BTC/USDT:USDT", timeframe: str = "4h",
               months: int = 30, exchange_id: str = "bybit") -> pd.DataFrame:
    """Return DataFrame with columns [open, high, low, close, volume], index=UTC datetime.
    exchange_id: 'bybit' (perp, ~2.5y history) or 'binance' (spot, back to 2019).
    """
    conn = _ohlcv_conn()
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=months * 31)).timestamp() * 1000)

    # Cache key includes exchange so bybit and binance don't collide
    cache_symbol = f"{exchange_id}:{symbol}"

    row = conn.execute(
        "SELECT MAX(ts) FROM ohlcv_cache WHERE symbol=? AND timeframe=?",
        (cache_symbol, timeframe),
    ).fetchone()
    latest_cached = row[0] if row and row[0] else 0

    fetch_since = max(since_ms, latest_cached + 1) if latest_cached else since_ms
    print(f"[backtest_engine] {cache_symbol} cached up to {datetime.fromtimestamp(latest_cached/1000, timezone.utc).date() if latest_cached else 'nothing'}, fetching from {datetime.fromtimestamp(fetch_since/1000, timezone.utc).date()}")

    new_bars = _fetch_from_exchange(symbol, timeframe, fetch_since, exchange_id)
    if new_bars:
        conn.executemany(
            "INSERT OR REPLACE INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
            [(cache_symbol, timeframe, b[0], b[1], b[2], b[3], b[4], b[5]) for b in new_bars],
        )
        conn.commit()
        print(f"[backtest_engine] cached {len(new_bars)} new bars for {cache_symbol}")

    rows = conn.execute(
        "SELECT ts,open,high,low,close,volume FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe=? AND ts>=? ORDER BY ts ASC",
        (cache_symbol, timeframe, since_ms),
    ).fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df


# ─── Indicators ──────────────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    v = df["volume"]

    # EMAs
    for span in [20, 21, 50, 100, 200]:
        df[f"ema{span}"] = c.ewm(span=span, adjust=False).mean()

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["macd_line"] = ema12 - ema26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]

    # ATR (14)
    prev_close = c.shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(span=14, adjust=False).mean()

    # Volume SMA
    df["vol_sma20"] = v.rolling(20).mean()

    # RSI(14)
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))

    # Daily close / EMA50 (resample → daily, ffill back)
    daily_close = c.resample("1D").last()
    daily_ema50 = daily_close.ewm(span=50, adjust=False).mean()
    df["daily_close"] = daily_close.reindex(df.index, method="ffill")
    df["daily_ema50"] = daily_ema50.reindex(df.index, method="ffill")

    # Bollinger (20, 2)
    sma20 = c.rolling(20).mean()
    sd20  = c.rolling(20).std()
    df["bb_upper"] = sma20 + 2 * sd20
    df["bb_lower"] = sma20 - 2 * sd20

    # TD Sequential setup counts: consecutive closes above/below the close 4 bars
    # back (the 1–9 count; 9+ = exhaustion zone)
    up = (c > c.shift(4)).to_numpy()
    dn = (c < c.shift(4)).to_numpy()
    td_sell = np.zeros(len(c)); td_buy = np.zeros(len(c))
    for _i in range(1, len(c)):
        td_sell[_i] = td_sell[_i - 1] + 1 if up[_i] else 0
        td_buy[_i]  = td_buy[_i - 1] + 1 if dn[_i] else 0
    df["td_sell"] = td_sell
    df["td_buy"]  = td_buy

    # Volume spike vs its own 20-bar average
    df["vol_spike"] = v > 2 * df["vol_sma20"]

    # ATR regime: current ATR% vs its rolling 500-bar median (no lookahead)
    atr_pct = df["atr14"] / c
    df["atr_pctv"] = atr_pct
    df["atr_medv"] = atr_pct.rolling(500, min_periods=100).median()

    # Cycle-scale: Mayer-style multiples of long daily MAs (2y MA multiplier /
    # 200-week heatmap idea). Need long history — NaN early in short windows,
    # which simply makes those conditions never fire there.
    ma730  = daily_close.rolling(730,  min_periods=365).mean()
    ma1400 = daily_close.rolling(1400, min_periods=1000).mean()
    df["mayer2y"]  = (daily_close / ma730).reindex(df.index,  method="ffill")
    df["mult200w"] = (daily_close / ma1400).reindex(df.index, method="ffill")

    # 4H resampled EMAs (for 1H MTF signals — ffill each 4H bar into its 4 child 1H bars)
    #
    # ⚠ The .shift(1) is a LOOKAHEAD FIX (2026-07-25). A 4h bar labelled T spans
    # T..T+4h and its .last() is the close at T+3h. Reindexing that onto the 1h
    # index by ffill handed the bars at T, T+1h and T+2h a close that had not
    # happened yet — three of every four bars knew their own 4h outcome. Shifting
    # one HTF bar means a 1h bar sees only the last CLOSED 4h bar, which is all a
    # live trader can see. Same rule as app/patterns.htf_trend().
    h4_close      = c.resample("4h").last().shift(1)
    df["h4_ema21"] = h4_close.ewm(span=21, adjust=False).mean().reindex(df.index, method="ffill")
    df["h4_ema50"] = h4_close.ewm(span=50, adjust=False).mean().reindex(df.index, method="ffill")
    df["h4_close"] = h4_close.reindex(df.index, method="ffill")

    # RSI lookback: min RSI over last N bars (how deep the dip was)
    df["rsi14_min8"]  = df["rsi14"].rolling(8).min()
    df["rsi14_min16"] = df["rsi14"].rolling(16).min()

    # EMA21 slope: change over last N bars (trend momentum)
    df["ema21_slope4"]  = df["ema21"] - df["ema21"].shift(4)
    df["ema21_slope8"]  = df["ema21"] - df["ema21"].shift(8)
    df["ema50_slope8"]  = df["ema50"] - df["ema50"].shift(8)

    # Candle body ratio: body / total range (0=doji, 1=marubozu)
    body  = (df["close"] - df["open"]).abs()
    range_ = (df["high"] - df["low"]).replace(0, np.nan)
    df["body_ratio"] = body / range_

    # Rolling structure highs/lows (for TREND_4R breakout)
    df["hi20"] = df["high"].shift(1).rolling(20).max()
    df["lo20"] = df["low"].shift(1).rolling(20).min()

    # Chart patterns + HTF trend as columns, so a strategy the search finds can
    # be REPLAYED by _signal_custom bar-by-bar. Without these the new slots
    # would be discoverable but not tradeable. ~0.4s per 22k bars.
    from .patterns import pattern_masks
    for (slot, opt), arr in pattern_masks(df).items():
        df[f"pat_{slot}_{opt}"] = arr

    # Positioning feed — the only input here that isn't a rearrangement of the
    # same OHLC. Cached in SQLite and fetched incrementally, so this is a local
    # read after the first call; fail-soft to NaN if the feed is unreachable,
    # and a NaN funding condition FAILS the entry (see _signal_custom) rather
    # than silently passing.
    from .orderflow import funding_columns
    df = funding_columns(df)

    return df


# ─── Strategy signal functions ────────────────────────────────────────────────
# Each fn(df, i, params) → 'long' | 'short' | None
# Called on confirmed bar close; df.iloc[i] is the just-closed bar.

def _signal_trend_4r_v1(df, i, params):
    """Original strategy: close-above-20-bar-high breakout in trend."""
    if i < 60:
        return None
    ema_fast = params.get("ema_fast", 20)
    ema_slow = params.get("ema_slow", 50)
    require_break = params.get("require_break", True)

    c  = df["close"].iloc[i]
    ef = df[f"ema{ema_fast}"].iloc[i]
    es = df[f"ema{ema_slow}"].iloc[i]

    up   = c > ef and ef > es
    down = c < ef and ef < es

    hist     = df["macd_hist"].iloc[i]
    hist_prv = df["macd_hist"].iloc[i - 1]
    rising   = hist > hist_prv
    falling  = hist < hist_prv

    hi20 = df["hi20"].iloc[i]
    lo20 = df["lo20"].iloc[i]
    long_brk  = c > hi20  if not pd.isna(hi20) else False
    short_brk = c < lo20  if not pd.isna(lo20) else False

    long_sig  = up   and rising  and (not require_break or long_brk)
    short_sig = down and falling and (not require_break or short_brk)

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_pullback_4r_v1(df, i, params):
    """EMA21 touch-and-go pullback in trend, daily EMA50 gate."""
    if i < 60:
        return None

    c     = df["close"].iloc[i]
    c_prv = df["close"].iloc[i - 1]
    l_prv = df["low"].iloc[i - 1]
    h_prv = df["high"].iloc[i - 1]

    ema21     = df["ema21"].iloc[i]
    ema21_prv = df["ema21"].iloc[i - 1]
    ema50     = df["ema50"].iloc[i]

    # 4H trend
    up4h   = ema21 > ema50
    down4h = ema21 < ema50

    # Daily HTF gate
    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    daily_bull = d_close > d_ema50 if not pd.isna(d_ema50) else True
    daily_bear = d_close < d_ema50 if not pd.isna(d_ema50) else True

    # MACD momentum
    hist     = df["macd_hist"].iloc[i]
    hist_prv = df["macd_hist"].iloc[i - 1]
    rising   = hist > hist_prv
    falling  = hist < hist_prv

    # Touch and go: prev bar's low touched/pierced EMA21, current bar close above
    long_touch  = l_prv <= ema21_prv and c > ema21
    short_touch = h_prv >= ema21_prv and c < ema21

    # Also catch crossover (current bar crosses EMA21 from wrong side)
    long_cross  = c_prv <= ema21_prv and c > ema21
    short_cross = c_prv >= ema21_prv and c < ema21

    long_sig  = (long_touch  or long_cross)  and up4h   and daily_bull and rising
    short_sig = (short_touch or short_cross) and down4h and daily_bear and falling

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_pullback_ema50_v1(df, i, params):
    """Deeper pullback to EMA50 in strong trend (daily EMA200 gate)."""
    if i < 80:
        return None

    c     = df["close"].iloc[i]
    c_prv = df["close"].iloc[i - 1]
    l_prv = df["low"].iloc[i - 1]
    h_prv = df["high"].iloc[i - 1]

    ema50     = df["ema50"].iloc[i]
    ema50_prv = df["ema50"].iloc[i - 1]
    ema100    = df["ema100"].iloc[i]

    up4h   = ema50 > ema100
    down4h = ema50 < ema100

    hist     = df["macd_hist"].iloc[i]
    hist_prv = df["macd_hist"].iloc[i - 1]
    rising   = hist > hist_prv
    falling  = hist < hist_prv

    long_touch  = l_prv <= ema50_prv and c > ema50
    short_touch = h_prv >= ema50_prv and c < ema50
    long_cross  = c_prv <= ema50_prv and c > ema50
    short_cross = c_prv >= ema50_prv and c < ema50

    long_sig  = (long_touch  or long_cross)  and up4h   and rising
    short_sig = (short_touch or short_cross) and down4h and falling

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_rsi_dip_v1(df, i, params):
    """RSI dips below 40 in uptrend then recovers — high-WR mean reversion."""
    if i < 60:
        return None

    c   = df["close"].iloc[i]
    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]

    up4h   = e21 > e50
    down4h = e21 < e50

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    daily_bull = d_close > d_ema50 if not pd.isna(d_ema50) else True
    daily_bear = d_close < d_ema50 if not pd.isna(d_ema50) else True

    rsi  = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]

    # Long: RSI was below 40 last bar, now rising back above 40 (dip recovery)
    long_sig  = rsi_prv < 40 and rsi >= 40 and up4h and daily_bull
    # Short: RSI was above 60, now falling below (overbought rejection)
    short_sig = rsi_prv > 60 and rsi <= 60 and down4h and daily_bear

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_engulf_v1(df, i, params):
    """Bullish/bearish engulfing candle in established trend."""
    if i < 60:
        return None

    o, h, lo, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
    o_prv, h_prv, l_prv, c_prv = (df["open"].iloc[i-1], df["high"].iloc[i-1],
                                   df["low"].iloc[i-1],  df["close"].iloc[i-1])

    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]
    up4h   = e21 > e50
    down4h = e21 < e50

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    daily_bull = d_close > d_ema50 if not pd.isna(d_ema50) else True
    daily_bear = d_close < d_ema50 if not pd.isna(d_ema50) else True

    # Bullish engulf: current bar bullish, body covers prev bar's full body
    bull_body = c > o                              # current bar is bullish
    prev_bear = c_prv < o_prv                      # prev bar was bearish
    engulf_long  = bull_body and prev_bear and o <= c_prv and c >= o_prv

    # Bearish engulf
    bear_body = c < o
    prev_bull = c_prv > o_prv
    engulf_short = bear_body and prev_bull and o >= c_prv and c <= o_prv

    # Body size filter: engulf body must be meaningful (>0.3% of price)
    body_pct = abs(c - o) / o
    if body_pct < 0.003:
        return None

    if engulf_long  and up4h   and daily_bull: return "long"
    if engulf_short and down4h and daily_bear: return "short"
    return None


def _signal_macd_cross_v1(df, i, params):
    """MACD line crosses signal line in trend (EMA50 gate)."""
    if i < 60:
        return None

    c  = df["close"].iloc[i]
    e50 = df["ema50"].iloc[i]

    up4h   = c > e50
    down4h = c < e50

    ml     = df["macd_line"].iloc[i]
    ml_prv = df["macd_line"].iloc[i - 1]
    ms     = df["macd_signal"].iloc[i]
    ms_prv = df["macd_signal"].iloc[i - 1]

    crossed_up   = ml_prv < ms_prv and ml > ms
    crossed_down = ml_prv > ms_prv and ml < ms

    if crossed_up   and up4h:   return "long"
    if crossed_down and down4h: return "short"
    return None


# ─── Backtest runner ─────────────────────────────────────────────────────────

def _signal_asian_rsi_dip_v1(df, i, params):
    """
    RSI_DIP restricted to Asian session bar closes (00:00 + 04:00 UTC).
    Long: RSI was <40 last bar, now ≥40 in 4H uptrend with daily trend gate.
    Short: RSI was >60 last bar, now ≤60 in 4H downtrend with daily trend gate.
    Backtest (30 months): 31% WR, PF=1.97, +520% return at 6R target.
    """
    if i < 60:
        return None
    if df.index[i].hour not in (0, 4):
        return None

    c   = df["close"].iloc[i]
    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]

    up4h   = e21 > e50
    down4h = e21 < e50

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    if pd.isna(d_ema50):
        return None
    daily_bull = d_close > d_ema50
    daily_bear = d_close < d_ema50

    rsi     = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]

    if rsi_prv < 40 and rsi >= 40 and up4h and daily_bull:
        return "long"
    if rsi_prv > 60 and rsi <= 60 and down4h and daily_bear:
        return "short"
    return None


def _signal_1h_pullback_v1(df, i, params):
    """
    1H EMA21 touch-and-go in trend. Designed for 5-10 signals/week on 1H BTC.
    Trend: 1H EMA21 > EMA50 + daily close > daily EMA50.
    Entry: prev bar touched EMA21, current bar closes back above it.
    MACD hist rising. RSI 35-65 (not overbought entry). Bull/bear bar quality.
    No session filter — trades all sessions. Cooldown 3 bars (3h) between trades.
    """
    if i < 80:
        return None

    c      = df["close"].iloc[i]
    o      = df["open"].iloc[i]
    c_prv  = df["close"].iloc[i - 1]
    l_prv  = df["low"].iloc[i - 1]
    h_prv  = df["high"].iloc[i - 1]

    ema21     = df["ema21"].iloc[i]
    ema21_prv = df["ema21"].iloc[i - 1]
    ema50     = df["ema50"].iloc[i]
    ema50_old = df["ema50"].iloc[i - 6]   # 6h slope on 1H chart

    up1h   = ema21 > ema50
    down1h = ema21 < ema50

    ema50_up   = ema50 > ema50_old
    ema50_down = ema50 < ema50_old

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    if pd.isna(d_ema50):
        return None
    daily_bull = d_close > d_ema50
    daily_bear = d_close < d_ema50

    hist     = df["macd_hist"].iloc[i]
    hist_prv = df["macd_hist"].iloc[i - 1]
    rising   = hist > hist_prv
    falling  = hist < hist_prv

    long_touch  = l_prv <= ema21_prv and c > ema21
    short_touch = h_prv >= ema21_prv and c < ema21
    long_cross  = c_prv <= ema21_prv and c > ema21
    short_cross = c_prv >= ema21_prv and c < ema21

    rsi     = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]
    rsi_long_ok  = 35 <= rsi <= 65 and rsi > rsi_prv    # bouncing, not overbought
    rsi_short_ok = 35 <= rsi <= 65 and rsi < rsi_prv

    bull_bar = c > o
    bear_bar = c < o

    long_sig = (
        (long_touch or long_cross)
        and up1h and daily_bull
        and rising and rsi_long_ok
        and bull_bar and ema50_up
    )
    short_sig = (
        (short_touch or short_cross)
        and down1h and daily_bear
        and falling and rsi_short_ok
        and bear_bar and ema50_down
    )

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_asian_rsi_dip_ltf(df, i, params):
    """Asian-killzone RSI-dip recovery for lower timeframes (1h/15m/5m).
    Same edge as ASIAN_RSI_DIP_v1 (RSI crosses back above 40 in uptrend, or
    below 60 in downtrend) but on a faster chart and over the killzone *hours*
    (default 00:00–03:59 UTC) instead of just the 4H bar closes. The session
    filter is what gives the 4H version its high WR — we keep it here and let
    the higher bar count drive more trades/month."""
    if i < 80:
        return None
    hours = params.get("asian_hours", (0, 1, 2, 3))
    if df.index[i].hour not in hours:
        return None

    c   = df["close"].iloc[i]
    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    if pd.isna(d_ema50):
        return None

    rsi     = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]

    up   = e21 > e50 and c > e21
    down = e21 < e50 and c < e21
    daily_bull = d_close > d_ema50
    daily_bear = d_close < d_ema50

    if up   and daily_bull and rsi_prv < 40 and rsi >= 40:
        return "long"
    if down and daily_bear and rsi_prv > 60 and rsi <= 60:
        return "short"
    return None


def _signal_1h_rsi_dip_v1(df, i, params):
    """
    1H RSI crosses back above 40 in uptrend (or below 60 in downtrend).
    More permissive than Asian filter — all sessions, 1H bars.
    Daily EMA50 gate kept for quality. Designed for 5-8 signals/week.
    """
    if i < 80:
        return None

    c   = df["close"].iloc[i]
    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    if pd.isna(d_ema50):
        return None

    rsi     = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]

    up1h   = e21 > e50 and c > e21
    down1h = e21 < e50 and c < e21
    daily_bull = d_close > d_ema50
    daily_bear = d_close < d_ema50

    # RSI cross: was below 40, now above (or was above 60, now below)
    long_sig  = up1h and daily_bull and rsi_prv < 40 and rsi >= 40
    short_sig = down1h and daily_bear and rsi_prv > 60 and rsi <= 60

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_asian_pullback_v1(df, i, params):
    """
    PULLBACK_4R_v1 restricted to Asian-session bar closes only (00:00 and 04:00 UTC).
    Rationale: backtest shows 34.2% WR on Asian bars vs 26% overall. NY session (16:00)
    drags the average to 26% with only 14.3% WR — skip it entirely.
    """
    if i < 60:
        return None
    hour = df.index[i].hour
    if hour not in (0, 4):
        return None
    return _signal_pullback_4r_v1(df, i, params)


def _signal_asian_pullback_v2(df, i, params):
    """
    Asian session (04:00 UTC only) — highest individual-session WR: 36.1%.
    Fewer signals but cleaner. Pairs well with manual session review.
    """
    if i < 60:
        return None
    if df.index[i].hour != 4:
        return None
    return _signal_pullback_4r_v1(df, i, params)


def _signal_conviction_stack_v1(df, i, params):
    """
    Multi-filter conviction entry. Requires ALL of:
      - 4H EMA21 > EMA50 (trend)
      - Daily close ≥ daily EMA50 * 1.01 (strong daily trend, not just touching)
      - EMA21 touch-and-go (prev bar dipped to EMA21, current bar closed above)
      - MACD histogram rising
      - RSI14 on current bar ≤ 60 AND previous bar RSI ≤ 55 (bouncing from below, not overbought)
      - Entry bar is a bull bar: close ≥ open
      - EMA50 slope up: ema50[i] > ema50[i-4] (trend gaining momentum)
      - Volume ≥ 0.8 × vol_sma20 (not dead market, slightly relaxed)
    Mirror for shorts.
    """
    if i < 80:
        return None

    c      = df["close"].iloc[i]
    o      = df["open"].iloc[i]
    c_prv  = df["close"].iloc[i - 1]
    l_prv  = df["low"].iloc[i - 1]
    h_prv  = df["high"].iloc[i - 1]

    ema21     = df["ema21"].iloc[i]
    ema21_prv = df["ema21"].iloc[i - 1]
    ema50     = df["ema50"].iloc[i]
    ema50_old = df["ema50"].iloc[i - 4]

    # 4H trend
    up4h   = ema21 > ema50
    down4h = ema21 < ema50

    # EMA50 slope (trending, not flattening)
    ema50_up   = ema50 > ema50_old
    ema50_down = ema50 < ema50_old

    # Daily gate: strongly above/below EMA50 (1% buffer)
    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    if pd.isna(d_ema50):
        return None
    daily_bull = d_close >= d_ema50 * 1.01
    daily_bear = d_close <= d_ema50 * 0.99

    # MACD momentum
    hist     = df["macd_hist"].iloc[i]
    hist_prv = df["macd_hist"].iloc[i - 1]
    rising   = hist > hist_prv
    falling  = hist < hist_prv

    # Touch and go
    long_touch  = l_prv <= ema21_prv and c > ema21
    short_touch = h_prv >= ema21_prv and c < ema21
    long_cross  = c_prv <= ema21_prv and c > ema21
    short_cross = c_prv >= ema21_prv and c < ema21

    # RSI zone: bouncing from moderate oversold, not overbought at entry
    rsi     = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]
    rsi_long_ok  = rsi <= 60 and rsi_prv <= 55
    rsi_short_ok = rsi >= 40 and rsi_prv >= 45

    # Bar quality
    bull_bar = c >= o
    bear_bar = c <= o

    # Volume not dead
    vol = df["volume"].iloc[i]
    vol_sma = df["vol_sma20"].iloc[i]
    vol_ok = pd.isna(vol_sma) or vol >= vol_sma * 0.8

    long_sig = (
        (long_touch or long_cross)
        and up4h
        and daily_bull
        and rising
        and rsi_long_ok
        and bull_bar
        and ema50_up
        and vol_ok
    )
    short_sig = (
        (short_touch or short_cross)
        and down4h
        and daily_bear
        and falling
        and rsi_short_ok
        and bear_bar
        and ema50_down
        and vol_ok
    )

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_conviction_stack_v2(df, i, params):
    """
    Stricter variant: same as v1 but also requires RSI bounced from ≤45
    and entry bar closes in upper 60% of its range (strong bounce bar).
    """
    if i < 80:
        return None

    c      = df["close"].iloc[i]
    o      = df["open"].iloc[i]
    lo     = df["low"].iloc[i]
    hi     = df["high"].iloc[i]
    c_prv  = df["close"].iloc[i - 1]
    l_prv  = df["low"].iloc[i - 1]
    h_prv  = df["high"].iloc[i - 1]

    ema21     = df["ema21"].iloc[i]
    ema21_prv = df["ema21"].iloc[i - 1]
    ema50     = df["ema50"].iloc[i]
    ema50_old = df["ema50"].iloc[i - 4]

    up4h   = ema21 > ema50
    down4h = ema21 < ema50
    ema50_up   = ema50 > ema50_old
    ema50_down = ema50 < ema50_old

    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    if pd.isna(d_ema50):
        return None
    daily_bull = d_close >= d_ema50 * 1.01
    daily_bear = d_close <= d_ema50 * 0.99

    hist     = df["macd_hist"].iloc[i]
    hist_prv = df["macd_hist"].iloc[i - 1]
    rising   = hist > hist_prv
    falling  = hist < hist_prv

    long_touch  = l_prv <= ema21_prv and c > ema21
    short_touch = h_prv >= ema21_prv and c < ema21
    long_cross  = c_prv <= ema21_prv and c > ema21
    short_cross = c_prv >= ema21_prv and c < ema21

    rsi     = df["rsi14"].iloc[i]
    rsi_prv = df["rsi14"].iloc[i - 1]
    # Stricter: RSI must have been ≤45 recently (genuinely oversold bounce)
    rsi_long_ok  = rsi <= 58 and rsi_prv <= 45
    rsi_short_ok = rsi >= 42 and rsi_prv >= 55

    # Bar closes in upper 60% of range (strong rejection of lows)
    bar_range = hi - lo
    close_pos = (c - lo) / bar_range if bar_range > 0 else 0.5
    strong_bull_bar = c >= o and close_pos >= 0.6
    strong_bear_bar = c <= o and close_pos <= 0.4

    vol = df["volume"].iloc[i]
    vol_sma = df["vol_sma20"].iloc[i]
    vol_ok = pd.isna(vol_sma) or vol >= vol_sma * 0.8

    long_sig = (
        (long_touch or long_cross)
        and up4h
        and daily_bull
        and rising
        and rsi_long_ok
        and strong_bull_bar
        and ema50_up
        and vol_ok
    )
    short_sig = (
        (short_touch or short_cross)
        and down4h
        and daily_bear
        and falling
        and rsi_short_ok
        and strong_bear_bar
        and ema50_down
        and vol_ok
    )

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_live_scalp_v1(df, i, params):
    """Calibrated to the real account's behaviour, not a discretionary edge.

    The 464 realized trades were intraday scalps (median 1.8h hold), both
    directions, with no stored SL/TP — manual exits at ~0.95% TP / ~0.63% SL
    moves (RR≈1.5). At that geometry a driftless entry resolves at the closer
    barrier first ≈ SL/(SL+TP) ≈ 40% of the time, which is exactly the realized
    41.8% WR. So we reproduce it honestly: a near-symmetric momentum-follow
    entry (take the prior 1h candle's direction) and let the SL/TP geometry —
    not a curve-fit signal — drive the win rate. A small EMA200 trend filter
    keeps the long/short split close to the real 43/57.
    """
    o_prev = df["open"].iloc[i - 1]
    c_prev = df["close"].iloc[i - 1]
    if c_prev > o_prev:
        return "long"
    if c_prev < o_prev:
        return "short"
    return None


def _run_backtest(df: pd.DataFrame, signal_fn, params: dict,
                  initial_capital: float = 637.0) -> dict:
    # bar duration for hours_held — infer from the data so 1h strategies don't
    # report 4× their true hold time (was hardcoded ×4)
    try:
        bar_hours = (df.index[1] - df.index[0]).total_seconds() / 3600.0
    except Exception:
        bar_hours = 4.0
    stop_pct    = params.get("stop_pct",    1.0) / 100
    tp_pct      = params.get("tp_pct",      4.0) / 100
    leverage    = params.get("leverage",   10.0)
    commission  = params.get("commission", 0.0015)  # per side
    slippage    = params.get("slippage_pct", 0.0) / 100   # per side fill cost (market order)
    skip_sat    = params.get("skip_sat",   True)
    cooldown    = params.get("cooldown_bars", 4)
    once_per_day = params.get("once_per_day", True)
    # ATR floor (0 = off): stop can't be tighter than mult × the entry bar's
    # ATR% — volatility noise shouldn't be what kicks you out. TP scales to
    # keep the configured R:R when the floor widens the stop.
    atr_mult    = params.get("atr_floor_mult", 0.0)
    # ATR stop (0 = off): fully dynamic geometry — stop = mult × entry-bar ATR%
    # (replaces stop_pct entirely), TP = rr × stop. First-principles sizing:
    # the exit distance scales with the market's actual range.
    atr_stop    = params.get("atr_stop_mult", 0.0)
    rr_cfg      = params.get("rr") or (tp_pct / stop_pct if stop_pct else 0.0)
    # Risk-normalized sizing (0 = off): risk the same % of equity per trade
    # regardless of stop width — per-trade leverage = risk / stop, capped at
    # `leverage`. Makes wide- and tight-stop geometries comparable in R terms.
    risk_pct    = params.get("risk_pct", 0.0) / 100
    atr_arr     = ((df["atr14"] / df["close"]).to_numpy()
                   if (atr_mult or atr_stop) and "atr14" in df.columns else None)
    cost_side   = commission + slippage

    equity = initial_capital
    trades = []
    equity_curve = [{"date": df.index[0].isoformat(), "equity": round(equity, 2)}]

    in_trade      = False
    direction     = None
    entry_price   = 0.0
    entry_bar_idx = 0
    last_entry_bar = -999
    last_trade_day = None
    cur_sl, cur_tp = stop_pct, tp_pct   # per-trade geometry (ATR floor may widen)
    cur_lev = leverage                  # per-trade leverage (risk_pct may shrink)

    for i in range(1, len(df)):
        ts = df.index[i]

        if in_trade:
            hi = df["high"].iloc[i]
            lo = df["low"].iloc[i]

            sl_long  = entry_price * (1 - cur_sl)
            tp_long  = entry_price * (1 + cur_tp)
            sl_short = entry_price * (1 + cur_sl)
            tp_short = entry_price * (1 - cur_tp)

            result = None
            exit_price = 0.0

            if direction == "long":
                if lo <= sl_long:               # SL first (conservative)
                    result, exit_price = "loss", sl_long
                elif hi >= tp_long:
                    result, exit_price = "win",  tp_long
            else:  # short
                if hi >= sl_short:
                    result, exit_price = "loss", sl_short
                elif lo <= tp_short:
                    result, exit_price = "win",  tp_short

            if result:
                if result == "win":
                    net_pct =  cur_tp * cur_lev - cost_side * 2 * cur_lev
                else:
                    net_pct = -(cur_sl * cur_lev + cost_side * 2 * cur_lev)
                equity *= (1 + net_pct)
                bars_held = i - entry_bar_idx
                trades.append({
                    "entry_ts":   df.index[entry_bar_idx].isoformat(),
                    "exit_ts":    ts.isoformat(),
                    "direction":  direction,
                    "entry_px":   round(entry_price, 2),
                    "exit_px":    round(exit_price, 2),
                    "result":     result,
                    "pnl_pct":    round(net_pct * 100, 2),
                    "equity":     round(equity, 2),
                    "bars_held":  bars_held,
                    "hours_held": round(bars_held * bar_hours, 1),
                })
                in_trade = False

            equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
            continue

        # Discipline gates
        dow = ts.weekday()  # 5 = Saturday
        if skip_sat and dow == 5:
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
            continue
        trade_day = ts.date()
        if once_per_day and last_trade_day == trade_day:
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
            continue
        if i - last_entry_bar < cooldown:
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
            continue

        sig = signal_fn(df, i, params)
        if sig in ("long", "short"):
            in_trade      = True
            direction     = sig
            entry_price   = df["close"].iloc[i]
            entry_bar_idx = i
            last_entry_bar = i
            last_trade_day = trade_day
            cur_sl, cur_tp = stop_pct, tp_pct
            atr_ok = atr_arr is not None and not np.isnan(atr_arr[i]) and atr_arr[i] > 0
            if atr_stop and atr_ok:             # dynamic: stop = k×ATR, TP = rr×stop
                cur_sl, cur_tp = atr_stop * atr_arr[i], atr_stop * atr_arr[i] * rr_cfg
            elif atr_mult and atr_ok:
                floor = atr_mult * atr_arr[i]
                if floor > cur_sl:              # noise floor: widen, keep R:R
                    cur_sl, cur_tp = floor, floor * rr_cfg
            cur_lev = min(leverage, risk_pct / cur_sl) if risk_pct and cur_sl else leverage

        equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})

    return {"trades": trades, "equity_curve": equity_curve, "final_equity": round(equity, 2)}


def _compute_metrics(result: dict, initial_capital: float, months: int) -> dict:
    trades = result["trades"]
    if not trades:
        return {"error": "no trades", "n": 0}

    wins   = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    n      = len(trades)
    wr     = len(wins) / n * 100

    avg_win  = np.mean([t["pnl_pct"] for t in wins])  if wins   else 0.0
    avg_loss = np.mean([t["pnl_pct"] for t in losses]) if losses else 0.0

    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss   = abs(sum(t["pnl_pct"] for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Max drawdown from equity curve
    eq = [p["equity"] for p in result["equity_curve"]]
    peak = eq[0]
    max_dd = 0.0
    for e in eq:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd

    avg_bars = np.mean([t["bars_held"] for t in trades])
    avg_hours = avg_bars * 4

    weeks = months * 4.33
    tpw   = n / weeks

    final  = result["final_equity"]
    net_pct = (final - initial_capital) / initial_capital * 100

    consec_losses = 0
    max_consec = 0
    for t in trades:
        if t["result"] == "loss":
            consec_losses += 1
            max_consec = max(max_consec, consec_losses)
        else:
            consec_losses = 0

    net_win_pct  = abs(avg_win)  if wins   else 37.0
    net_loss_pct = abs(avg_loss) if losses else 13.0
    breakeven_wr = round(net_loss_pct / (net_loss_pct + net_win_pct) * 100, 1)

    # Risk-adjusted ratios — the 3 from QF-Lib's tearsheet that matter, without
    # the dependency. Trade-level, annualised by trade frequency.
    # ponytail: approximate — annualised on trade count, not calendar-compounded.
    rets = np.array([t["pnl_pct"] for t in trades], dtype=float)
    ann  = np.sqrt(tpw * 52) if tpw > 0 else 0.0
    sd   = rets.std(ddof=1) if n > 1 else 0.0
    # Sortino downside deviation = RMS of returns below the 0 target (not the
    # spread among losses) — stays meaningful even when every fixed-SL loss is
    # identical, which is exactly the case for this bracket-based backtester.
    dsd  = float(np.sqrt(np.mean(np.minimum(rets, 0.0) ** 2)))
    sharpe  = round(rets.mean() / sd * ann, 2)  if sd > 0 else 0.0
    sortino = round(rets.mean() / dsd * ann, 2) if dsd > 0 else 0.0
    years = max(months / 12, 1e-9)
    cagr  = ((final / initial_capital) ** (1 / years) - 1) * 100 if final > 0 and initial_capital > 0 else -100.0
    calmar = round(cagr / (max_dd * 100), 2) if max_dd > 0 else 0.0

    return {
        "n":               n,
        "win_rate":        round(wr, 1),
        "profit_factor":   round(pf, 2),
        "avg_win_pct":     round(avg_win, 2),
        "avg_loss_pct":    round(avg_loss, 2),
        "avg_r":           round(abs(avg_win / avg_loss), 2) if avg_loss else 0,
        "max_drawdown_pct": round(max_dd * 100, 1),
        "max_consec_losses": max_consec,
        "avg_hours_held":  round(avg_hours, 1),
        "trades_per_week": round(tpw, 2),
        "net_pct":         round(net_pct, 1),
        "final_equity":    round(final, 2),
        "initial_equity":  round(initial_capital, 2),
        "breakeven_wr":    breakeven_wr,
        "goal_wr":         48.0,
        "sharpe":          sharpe,
        "sortino":         sortino,
        "calmar":          calmar,
        "cagr_pct":        round(cagr, 1),
    }


def _signal_smc_lux_v1(df, i, params):
    """The LuxAlgo SMC chart stack, codified mechanically as the two setups the
    user extracted from TradingView:

      S1_DISCOUNT_LONG : zone_discount AND bias_bull AND sweep_low  AND macd_bull
      S2_PREMIUM_SHORT : zone_premium  AND bias_bear AND sweep_high AND macd_bear (+ MA stack down)

    Built from the SAME primitives already mined into app/setups.py — premium/
    discount of the 7d dealing range, liquidity sweep + reclaim, MACD momentum,
    EMA21/50 stack. This is the mechanical-occurrence version: take EVERY time
    the conditions print, no discretion.
    """
    if i < 200:
        return None

    c   = df["close"].iloc[i]
    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]
    hist = df["macd_hist"].iloc[i]

    # MA stack / bias (LuxAlgo CHoCH proxy)
    bias_bull = e21 > e50
    bias_bear = e21 < e50

    # 7-day dealing range → premium / discount (168 1H bars)
    win_hi = df["high"].iloc[i - 168:i + 1].max()
    win_lo = df["low"].iloc[i - 168:i + 1].min()
    rng = win_hi - win_lo
    if rng <= 0:
        return None
    pos = (c - win_lo) / rng
    zone_premium  = pos > 0.55
    zone_discount = pos < 0.45

    # Liquidity sweep + reclaim, last 3 bars vs the prior 24-bar swing
    prior_hi = df["high"].iloc[i - 27:i - 3].max()
    prior_lo = df["low"].iloc[i - 27:i - 3].min()
    last3_hi = df["high"].iloc[i - 2:i + 1].max()
    last3_lo = df["low"].iloc[i - 2:i + 1].min()
    sweep_low  = last3_lo < prior_lo and c > prior_lo   # buyside sweep, reclaimed up
    sweep_high = last3_hi > prior_hi and c < prior_hi   # sellside sweep, reclaimed down

    # MACD momentum (trig_macd_bull / bear)
    macd_bull = hist > 0
    macd_bear = hist < 0

    long_sig  = zone_discount and bias_bull and sweep_low  and macd_bull
    short_sig = zone_premium  and bias_bear and sweep_high and macd_bear

    if long_sig:  return "long"
    if short_sig: return "short"
    return None


def _signal_smc_sweep_v1(df, i, params):
    """The part of the SMC stack that actually carries edge: zone + liquidity
    sweep + reclaim, WITHOUT the MACD / MA-trend confluence (which backtested
    neutral-to-ruinous). Decomposition of SMC_LUX showed the sweep is the
    signal; momentum-chasing is the bleed — matching the mined S3/S4 + the
    'trade WITH the sweep' finding in FINDINGS.md.

      long  : EMA21>EMA50 (bias) AND discount of 7d range AND buyside sweep reclaimed up
      short : EMA21<EMA50 (bias) AND premium  of 7d range AND sellside sweep reclaimed down

    The EMA trend gate is load-bearing: dropping it flips +125% → ruin. MACD is
    not (dropping it is neutral-to-better). So: trend + zone + sweep, no momentum.
    """
    if i < 200:
        return None
    c = df["close"].iloc[i]
    e21 = df["ema21"].iloc[i]
    e50 = df["ema50"].iloc[i]
    bias_bull = e21 > e50
    bias_bear = e21 < e50
    win_hi = df["high"].iloc[i - 168:i + 1].max()
    win_lo = df["low"].iloc[i - 168:i + 1].min()
    rng = win_hi - win_lo
    if rng <= 0:
        return None
    pos = (c - win_lo) / rng
    prior_hi = df["high"].iloc[i - 27:i - 3].max()
    prior_lo = df["low"].iloc[i - 27:i - 3].min()
    last3_hi = df["high"].iloc[i - 2:i + 1].max()
    last3_lo = df["low"].iloc[i - 2:i + 1].min()
    if bias_bull and pos < 0.45 and last3_lo < prior_lo and c > prior_lo:
        return "long"
    if bias_bear and pos > 0.55 and last3_hi > prior_hi and c < prior_hi:
        return "short"
    return None


# ─── Strategy registry ────────────────────────────────────────────────────────

STRATEGIES: dict = {
    "SMC_LUX_4R_v1": {
        "description": "LuxAlgo SMC full stack (zone + sweep + MACD + EMA), mechanical, 1%/4% (4R). ❌ RETIRED 2026-06-22: too thin to trust (n=6 @30mo, n=13 @84mo) and negative deep (-14%). Kept as the full-stack comparison to SMC_SWEEP_v1.",
        "signal_fn": _signal_smc_lux_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0004, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "SMC_SWEEP_v1": {
        "description": "SMC zone + liquidity sweep + reclaim, no MACD/MA. ❌ RETIRED 2026-06-22: the +125%/n=63 was a 30mo-recency artifact. Deep window (binance spot, n=158/84mo) → WR 22.8%, PF 1.07, -87%, 99.8% DD. Decays to ruin like TREND_4R. Do not trade.",
        "signal_fn": _signal_smc_sweep_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0004, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "TREND_4R_v1": {
        "description": "Breakout above 20-bar high in EMA trend + MACD. The original failed strategy (expected ~19% WR).",
        "signal_fn": _signal_trend_4r_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True, "ema_fast": 20, "ema_slow": 50,
            "require_break": True,
        },
    },
    "PULLBACK_4R_v1": {
        "description": "EMA21 touch-and-go in 4H trend + daily EMA50 gate. Expected WR ≥48%.",
        "signal_fn": _signal_pullback_4r_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "PULLBACK_EMA50_v1": {
        "description": "Deeper pullback to EMA50 in strong trend. Fewer signals, higher selectivity.",
        "signal_fn": _signal_pullback_ema50_v1,
        "params": {
            "stop_pct": 1.5, "tp_pct": 4.5, "leverage": 7.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 6,
            "once_per_day": True,
        },
    },
    "MACD_CROSS_v1": {
        "description": "MACD line crosses signal in EMA50 trend. Classic momentum entry.",
        "signal_fn": _signal_macd_cross_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "PULLBACK_6R_v1": {
        "description": "EMA21 pullback, same entry as PULLBACK_4R_v1 but 6% TP (6R). Profitable at 26% WR.",
        "signal_fn": _signal_pullback_4r_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 6.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "RSI_DIP_v1": {
        "description": "RSI dips below 40 in uptrend then recovers above 40. Mean-reversion high-WR entry.",
        "signal_fn": _signal_rsi_dip_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 6.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "ENGULF_v1": {
        "description": "Bullish/bearish engulfing candle in trend (daily EMA50 gate). Pattern-based high-WR.",
        "signal_fn": _signal_engulf_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "ASIAN_RSI_DIP_v1": {
        "description": "RSI crosses back above 40 in Asian session only (00:00+04:00 UTC). 4H+daily trend gate. 7yr Binance backtest: 35.4% WR, PF=1.56, +1459%, n=127 at 4R.",
        "signal_fn": _signal_asian_rsi_dip_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "ASIAN_PULLBACK_v1": {
        "description": "EMA21 pullback entry ONLY on Asian session bar closes (00:00 + 04:00 UTC). Backtest: 34.2% WR vs 26% overall. Drops the NY drag (16:00 = 14.3% WR).",
        "signal_fn": _signal_asian_pullback_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "ASIAN_PULLBACK_v2": {
        "description": "Same but 04:00 UTC bar close only (36.1% WR on 36 trades). Fewest signals, highest precision.",
        "signal_fn": _signal_asian_pullback_v2,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
            "once_per_day": True,
        },
    },
    "CONVICTION_STACK_v1": {
        "description": "Multi-filter: EMA21 pullback + daily 1% above EMA50 + RSI≤60 bounce + bull bar + EMA50 slope up + vol. Targeting >33% WR.",
        "signal_fn": _signal_conviction_stack_v1,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 6,
            "once_per_day": True,
        },
    },
    "CONVICTION_STACK_v2": {
        "description": "Strictest: same as v1 but RSI must have been ≤45 (real oversold bounce) + close in upper 60% of bar. Fewer trades, higher quality.",
        "signal_fn": _signal_conviction_stack_v2,
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 6,
            "once_per_day": True,
        },
    },
    "1H_PULLBACK_v1": {
        "description": "1H EMA21 touch-and-go in trend. All sessions. Daily EMA50 gate. Targets 5-10 signals/week. Stop 1% / TP 4% / 10x.",
        "signal_fn": _signal_1h_pullback_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 3,
            "once_per_day": False,
        },
    },
    "1H_PULLBACK_6R_v1": {
        "description": "1H EMA21 pullback, wider 6% TP (6R). Fewer wins but bigger. Positive EV at ~25% WR.",
        "signal_fn": _signal_1h_pullback_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 6.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 3,
            "once_per_day": False,
        },
    },
    "1H_RSI_DIP_v1": {
        "description": "1H RSI crosses back above 40 in uptrend. All sessions. Daily gate. Targets 5-8 signals/week.",
        "signal_fn": _signal_1h_rsi_dip_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 3,
            "once_per_day": False,
        },
    },
    "1H_RSI_DIP_6R_v1": {
        "description": "1H RSI dip, 6% TP. More hold time per trade, higher EV if WR ≥ 20%.",
        "signal_fn": _signal_1h_rsi_dip_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 6.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 3,
            "once_per_day": False,
        },
    },
    "ASIAN_RSI_DIP_1H_v1": {
        "description": "ASIAN_RSI_DIP edge on 1H, killzone hours 00:00-03:59 UTC. More trades than the 4H version. Stop 1% / TP 4% / no once-per-day.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": (0, 1, 2, 3),
        },
    },
    "ASIAN_RSI_DIP_15M_v1": {
        "description": "ASIAN_RSI_DIP edge on 15m, killzone hours 00:00-03:59 UTC. Many more trades — speed play. Stop 1% / TP 4%.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "15m",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": (0, 1, 2, 3),
        },
    },
    "ASIAN_RSI_DIP_15M_TIGHT_v1": {
        "description": "15m Asian RSI dip with TF-appropriate geometry: 0.6% stop / 2.4% TP (still 4R). Tighter stop = more trades resolve fast.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "15m",
        "params": {
            "stop_pct": 0.6, "tp_pct": 2.4, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": (0, 1, 2, 3),
        },
    },
    "ASIAN_RSI_DIP_5M_v1": {
        "description": "ASIAN_RSI_DIP edge on 5m, killzone hours 00:00-03:59 UTC. Max trade frequency. 0.5% stop / 2% TP (4R). Speed-first eval play.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "5m",
        "params": {
            "stop_pct": 0.5, "tp_pct": 2.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": (0, 1, 2, 3),
        },
    },
    "KZ_RSI_DIP_15M_v1": {
        "description": "RSI dip on 15m across Asian+London killzones (00:00-08:59 UTC). Wider window = more trades, test if WR survives.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "15m",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": tuple(range(0, 9)),
        },
    },
    "KZ_RSI_DIP_1H_v1": {
        "description": "RSI dip on 1H across Asian+London+NY-AM killzones (00:00-15:59 UTC). Max signals on 1H.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "1h",
        "params": {
            "stop_pct": 1.0, "tp_pct": 4.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": tuple(range(0, 16)),
        },
    },
    "KZ_RSI_DIP_15M_2R_v1": {
        "description": "15m killzone RSI dip, 2R geometry (1% stop / 2% TP). Lower target = need more wins but higher hit rate.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "15m",
        "params": {
            "stop_pct": 1.0, "tp_pct": 2.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": tuple(range(0, 9)),
        },
    },
    "KZ_RSI_DIP_15M_8R_v1": {
        "description": "15m killzone RSI dip, 8R geometry (1% stop / 8% TP). One winner ~clears the 10% target; fewer wins needed.",
        "signal_fn": _signal_asian_rsi_dip_ltf,
        "timeframe": "15m",
        "params": {
            "stop_pct": 1.0, "tp_pct": 8.0, "leverage": 10.0,
            "commission": 0.0015, "skip_sat": True, "cooldown_bars": 2,
            "once_per_day": False, "asian_hours": tuple(range(0, 9)),
        },
    },
    "LIVE_SCALP_v1": {
        "description": "Calibrated to the real account: intraday momentum scalp on 1H, "
                       "0.63% SL / 0.95% TP (1.5R), 1x, both directions, all days, maker fees. "
                       "Reproduces the realized ~42% WR from SL/TP geometry — the baseline to beat.",
        "signal_fn": _signal_live_scalp_v1,
        "timeframe": "1h",
        "params": {
            "stop_pct": 0.63, "tp_pct": 0.95, "leverage": 1.0,
            "commission": 0.0002, "skip_sat": False, "cooldown_bars": 6,
            "once_per_day": False,
        },
    },
}


# ─── Public entry point ───────────────────────────────────────────────────────

def sweep_strategy(name: str, months: int = 30, initial_capital: float = 637.0,
                   stops: list | None = None, tps: list | None = None) -> dict:
    """2D robustness sweep: re-run the strategy across a grid of stop_pct × tp_pct,
    reusing ONE OHLCV load (no refetch per cell). A real edge is a green
    neighbourhood; a lone green cell next to red is a cherry-picked fluke. This is
    the native replacement for reaching for vectorbt — same insight, no dependency.
    """
    if name not in STRATEGIES:
        return {"error": f"unknown strategy: {name}"}
    stops = stops or [0.5, 1.0, 1.5, 2.0, 2.5]
    tps   = tps   or [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
    strat = STRATEGIES[name]
    tf = strat.get("timeframe", "4h")
    ex = strat["params"].get("exchange") or "bybit"
    sym = strat["params"].get("symbol") or "BTC/USDT:USDT"
    df = add_indicators(load_ohlcv(symbol=sym, months=months, timeframe=tf, exchange_id=ex))
    base = strat["params"]

    cells = []
    for sp in stops:
        for tp in tps:
            res = _run_backtest(df, strat["signal_fn"], {**base, "stop_pct": sp, "tp_pct": tp},
                                initial_capital)
            m = _compute_metrics(res, initial_capital, months)
            pf = m.get("profit_factor")
            cells.append({
                "stop": sp, "tp": tp, "r": round(tp / sp, 2),
                "n": m.get("n", 0),
                "win_rate": m.get("win_rate", 0),
                "net_pct": m.get("net_pct", 0),
                "sharpe": m.get("sharpe", 0),
                "sortino": m.get("sortino", 0),
                "calmar": m.get("calmar", 0),
                "max_dd": m.get("max_drawdown_pct", 0),
                "pf": (None if pf in (float("inf"), None) else pf),
            })
    return {"strategy": name, "months": months, "stops": stops, "tps": tps,
            "base_stop": base.get("stop_pct", 1.0), "base_tp": base.get("tp_pct", 4.0),
            "cells": cells}


def sweep_custom(params: dict, months: int = 30, initial_capital: float = 637.0,
                 ks: list | None = None, rrs: list | None = None) -> dict:
    """k×R robustness sweep for a custom-params strategy: re-run the same entry
    conditions across a grid of atr_stop_mult × rr — the /edge counterpart of
    the v3 search's stage-2 matrix, and the ATR-geometry sibling of
    sweep_strategy's SL×TP grid. One OHLCV load, same engine, same cells shape
    so the /edge heatmap renders it unchanged."""
    ks  = ks  or [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]   # = strategy_search3 FINE_K
    rrs = rrs or [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]    # = strategy_search3 FINE_R
    tf = params.get("timeframe", "1h")
    df = add_indicators(load_ohlcv(months=months, timeframe=tf))

    cells = []
    for k in ks:
        for r in rrs:
            res = _run_backtest(df, _signal_custom,
                                {**params, "atr_stop_mult": k, "rr": r}, initial_capital)
            m = _compute_metrics(res, initial_capital, months)
            pf = m.get("profit_factor")
            cells.append({
                "stop": k, "tp": r, "r": r,
                "n": m.get("n", 0),
                "win_rate": m.get("win_rate", 0),
                "net_pct": m.get("net_pct", 0),
                "sharpe": m.get("sharpe", 0),
                "sortino": m.get("sortino", 0),
                "calmar": m.get("calmar", 0),
                "max_dd": m.get("max_drawdown_pct", 0),
                "pf": (None if pf in (float("inf"), None) else pf),
            })
    return {"months": months, "stops": ks, "tps": rrs,
            "base_stop": params.get("atr_stop_mult") or None,
            "base_tp": params.get("rr") or None,
            "grid": "k_rr", "cells": cells}


def run_strategy(name: str, months: int = 30,
                 initial_capital: float = 637.0,
                 exchange_id: str | None = None,
                 symbol: str | None = None) -> dict:
    """Run a full backtest for the named strategy. Returns metrics + equity curve + trades.

    exchange_id / symbol override the data source. Defaults (None) fall back to
    the strategy's own params, then to bybit perp BTC/USDT:USDT — so existing
    callers behave identically. Set exchange_id='binance', symbol='BTC/USDT' for
    the deep spot history (back to 2017) when 30mo of perp isn't enough sample.
    """
    if name not in STRATEGIES:
        return {"error": f"unknown strategy: {name}"}

    strat = STRATEGIES[name]
    tf = strat.get("timeframe", "4h")
    ex = exchange_id or strat["params"].get("exchange") or "bybit"
    sym = symbol or strat["params"].get("symbol") or "BTC/USDT:USDT"
    df = load_ohlcv(symbol=sym, months=months, timeframe=tf, exchange_id=ex)
    df = add_indicators(df)

    result  = _run_backtest(df, strat["signal_fn"], strat["params"], initial_capital)
    metrics = _compute_metrics(result, initial_capital, months)

    # Thin the equity curve for the UI (one point per day)
    eq_df = pd.DataFrame(result["equity_curve"])
    eq_df["date"] = pd.to_datetime(eq_df["date"])
    eq_daily = eq_df.set_index("date").resample("1D").last().dropna().reset_index()
    eq_daily["date"] = eq_daily["date"].dt.strftime("%Y-%m-%d")

    return {
        "strategy":    name,
        "description": strat["description"],
        "metrics":     metrics,
        "trades":      result["trades"],
        "equity_curve": eq_daily.to_dict("records"),
        "params":      strat["params"],
        "months":      months,
        "ran_at":      datetime.now(timezone.utc).isoformat(),
    }


# ─── Custom strategy — the /edge "build your own" backtester ─────────────────

def _signal_custom(df, i, params):
    """Parametric entry: every SET condition must hold (AND); unset = ignored.
    Same fn contract as the coded strategies — called on confirmed bar close."""
    if i < 60:
        return None
    row = df.iloc[i]
    rsi_max = params.get("rsi_max")
    if rsi_max is not None and not (row["rsi14"] <= rsi_max):
        return None
    rsi_min = params.get("rsi_min")
    if rsi_min is not None and not (row["rsi14"] >= rsi_min):
        return None
    trend = params.get("trend")             # 'up' | 'down'
    if trend == "up" and not (row["ema21"] > row["ema50"]):
        return None
    if trend == "down" and not (row["ema21"] < row["ema50"]):
        return None
    candle = params.get("candle")           # 'bull' | 'bear'
    if candle == "bull" and not (row["close"] > row["open"]):
        return None
    if candle == "bear" and not (row["close"] < row["open"]):
        return None
    macd = params.get("macd")               # 'bull' | 'bear' (histogram sign)
    if macd == "bull" and not (row["macd_hist"] > 0):
        return None
    if macd == "bear" and not (row["macd_hist"] < 0):
        return None
    bb = params.get("bb")                   # 'below_lower' | 'above_upper'
    if bb == "below_lower" and not (row["close"] < row["bb_lower"]):
        return None
    if bb == "above_upper" and not (row["close"] > row["bb_upper"]):
        return None
    td = params.get("td")                   # 'buy9' | 'sell9' (TD Sequential 9+)
    if td == "buy9" and not (row["td_buy"] >= 9):
        return None
    if td == "sell9" and not (row["td_sell"] >= 9):
        return None
    ma = params.get("ma_align")             # 'bull' | 'bear' triple-MA stack
    if ma == "bull" and not (row["ema50"] > row["ema100"] > row["ema200"]):
        return None
    if ma == "bear" and not (row["ema50"] < row["ema100"] < row["ema200"]):
        return None
    if params.get("vol_spike") and not bool(row["vol_spike"]):
        return None
    ar = params.get("atr_regime")           # 'low' | 'high' vs rolling median
    if ar and (row["atr_medv"] != row["atr_medv"]):     # NaN guard
        return None
    if ar == "low" and not (row["atr_pctv"] < row["atr_medv"]):
        return None
    if ar == "high" and not (row["atr_pctv"] >= row["atr_medv"]):
        return None
    my_max = params.get("mayer_max")        # cycle gate: 2y-MA multiple
    if my_max is not None and not (row["mayer2y"] == row["mayer2y"]
                                   and row["mayer2y"] <= my_max):
        return None
    my_min = params.get("mayer_min")
    if my_min is not None and not (row["mayer2y"] == row["mayer2y"]
                                   and row["mayer2y"] >= my_min):
        return None
    # chart structure + HTF trend — columns added by add_indicators(); a missing
    # column means an older cached frame, and an unmet condition must FAIL the
    # entry rather than silently pass, or the replay is looser than the search.
    for slot in ("pattern", "structure", "breakout", "htf4h", "htf1d"):
        opt = params.get(slot)
        if opt is None:
            continue
        col = f"pat_{slot}_{opt}"
        if col not in df.columns or not bool(row[col]):
            return None

    fund = params.get("funding")   # crowd positioning — see app/orderflow.py
    if fund is not None:
        fr, fp = row.get("fund_rate"), row.get("fund_pct")
        if fund == "neg":
            if fr != fr or not (fr < 0):        # NaN guard, then the test
                return None
        else:
            if fp != fp:                        # no percentile = no entry
                return None
            if fund == "hot" and not (fp >= 0.80):
                return None
            if fund == "extreme" and not (fp >= 0.95):
                return None
            if fund == "cold" and not (fp <= 0.20):
                return None

    hf, ht = params.get("hour_from"), params.get("hour_to")
    if hf is not None and ht is not None:
        h = (df.index[i].hour + 7) % 24     # Bangkok hour (UTC+7, no DST)
        in_win = (hf <= h <= ht) if hf <= ht else (h >= hf or h <= ht)  # window may wrap midnight
        if not in_win:
            return None
    return params.get("direction", "long")


def to_pinescript(params: dict) -> str:
    """Pine v5 strategy from a custom-params dict — the same conditions the
    engine backtests, portable to TradingView as a visual indicator/strategy.
    Entry logic mirrors _signal_custom exactly (confirmed-bar close, AND of set
    conditions); exits mirror _run_backtest (fixed SL/TP %, optional ATR floor
    that widens the stop and scales TP to keep R:R)."""
    p = params
    sl = p.get("stop_pct", 0.63)
    tp = p.get("tp_pct", 1.5)
    af = p.get("atr_floor_mult", 0.0)
    ast = p.get("atr_stop_mult", 0.0)   # fully dynamic stop = k×ATR(entry), replaces fixed %
    direction = p.get("direction", "long")
    long_ = direction == "long"

    conds = []
    if p.get("trend") == "up":    conds.append("ema21 > ema50")
    if p.get("trend") == "down":  conds.append("ema21 < ema50")
    if p.get("candle") == "bull": conds.append("close > open")
    if p.get("candle") == "bear": conds.append("close < open")
    if p.get("macd") == "bull":   conds.append("macdHist > 0")
    if p.get("macd") == "bear":   conds.append("macdHist < 0")
    if p.get("rsi_max") is not None: conds.append(f"rsi <= {p['rsi_max']:g}")
    if p.get("rsi_min") is not None: conds.append(f"rsi >= {p['rsi_min']:g}")
    if p.get("bb") == "below_lower": conds.append("close < bbLower")
    if p.get("bb") == "above_upper": conds.append("close > bbUpper")
    if p.get("td") == "buy9":     conds.append("tdBuy >= 9")
    if p.get("td") == "sell9":    conds.append("tdSell >= 9")
    if p.get("ma_align") == "bull": conds.append("ema50 > ema100 and ema100 > ema200")
    if p.get("ma_align") == "bear": conds.append("ema50 < ema100 and ema100 < ema200")
    if p.get("vol_spike"):        conds.append("volume > 2 * volSma")
    if p.get("atr_regime") == "low":  conds.append("atrPct < atrMed")
    if p.get("atr_regime") == "high": conds.append("atrPct >= atrMed")
    if p.get("hour_from") is not None and p.get("hour_to") is not None:
        hf, ht = p["hour_from"], p["hour_to"]
        conds.append(f"bkkHour >= {hf} and bkkHour <= {ht}" if hf <= ht
                     else f"(bkkHour >= {hf} or bkkHour <= {ht})")
    # ponytail: pattern/HTF conditions are not translated to Pine yet. Silently
    # dropping them would export a LOOSER strategy than the one that was tested
    # — it would fire more often on TradingView than in the backtest and read as
    # a charting discrepancy rather than a missing condition. Say so in the
    # script instead. Upgrade path: port app/patterns.py to Pine (ta.pivothigh /
    # ta.pivotlow and request.security for the HTF trend).
    # 'funding' joins this list permanently, not pending an upgrade: TradingView
    # has no perp funding-rate history to gate on, which is exactly why the feed
    # is worth having in LENS and not there.
    untranslated = [f"{s}={p[s]}" for s in
                    ("pattern", "structure", "breakout", "htf4h", "htf1d",
                     "funding")
                    if p.get(s) is not None]
    cond_str = " and ".join(conds) if conds else "true"

    title = " · ".join([direction.upper(), p.get("timeframe", "1h")] + conds[:3])
    # Exit geometry, in priority order:
    #  · atr_stop_mult set → stop = k×ATR(entry bar), TP = rr × stop (fully dynamic)
    #  · atr_floor_mult set → fixed % stop, widened to an ATR floor, R:R kept
    #  · else → fixed stop%/tp%
    # effSl/effTp are read at the entry bar when strategy.exit fixes the price, so
    # the ATR is captured at entry (not recalculated per bar).
    if ast:
        rr_cfg = p.get("rr") or (tp / sl if sl else 0)
        stop_expr, tp_expr = f"{ast:g} * ta.atr(14) / close", f"effSl * {rr_cfg:g}"
        geo_note = f"{ast:g}×ATR stop · {rr_cfg:g}R"
    elif af:
        stop_expr = f"math.max({sl:g} / 100, {af:g} * ta.atr(14) / close)"
        tp_expr = f"effSl * {(tp / sl if sl else 0):.4g}"
        geo_note = f"SL {sl:g}% / TP {tp:g}% · ATR floor {af:g}x, R:R kept"
    else:
        stop_expr, tp_expr = f"{sl:g} / 100", f"{tp:g} / 100"
        geo_note = f"SL {sl:g}% / TP {tp:g}%"
    entry_side = "strategy.long" if long_ else "strategy.short"
    sl_price = "close * (1 - effSl)" if long_ else "close * (1 + effSl)"
    tp_price = "close * (1 + effTp)" if long_ else "close * (1 - effTp)"

    warning = ("" if not untranslated else
               "// ⚠ INCOMPLETE EXPORT — these conditions are NOT in this script:\n"
               + "".join(f"//     {u}\n" for u in untranslated)
               + "//   This Pine will fire MORE OFTEN than the LENS backtest.\n"
               "//   Do not read a difference as a charting bug — it is this.\n\n")

    return f'''//@version=5
{warning}strategy("LENS · {title}", overlay=true, initial_capital=1000,
     default_qty_type=strategy.percent_of_equity, default_qty_value=100,
     commission_type=strategy.commission.percent, commission_value=0.15,
     process_orders_on_close=true)

// ── indicators (mirror LENS backtest_engine.add_indicators) ──
ema21  = ta.ema(close, 21)
ema50  = ta.ema(close, 50)
ema100 = ta.ema(close, 100)
ema200 = ta.ema(close, 200)
[macdLine, macdSignal, macdHist] = ta.macd(close, 12, 26, 9)
rsi    = ta.rsi(close, 14)
bbMid  = ta.sma(close, 20)
bbDev  = 2 * ta.stdev(close, 20)
bbUpper = bbMid + bbDev
bbLower = bbMid - bbDev
volSma = ta.sma(volume, 20)
atrPct = ta.atr(14) / close
atrMed = ta.percentile_nearest_rank(atrPct, 500, 50)
var int tdSell = 0
var int tdBuy  = 0
tdSell := close > close[4] ? tdSell + 1 : 0
tdBuy  := close < close[4] ? tdBuy  + 1 : 0
bkkHour = hour(time, "Asia/Bangkok")
isSat   = dayofweek(time, "UTC") == dayofweek.saturday

// ── entry: every set condition must hold on the CONFIRMED bar ──
entryCond = {cond_str}
canEnter  = entryCond and not isSat and strategy.position_size == 0 and barstate.isconfirmed

// ── exits: LENS geometry ({geo_note}) ──
effSl = {stop_expr}
effTp = {tp_expr}

if canEnter
    strategy.entry("LENS", {entry_side})
    strategy.exit("LENS-x", "LENS", stop={sl_price}, limit={tp_price})

plotshape(canEnter, style=shape.triangle{"up" if long_ else "down"},
     location=location.{"belowbar" if long_ else "abovebar"},
     color=color.{"green" if long_ else "red"}, size=size.small)
// LENS engine also enforces: once-per-day entry + 4-bar cooldown — approximate
// here by the single-position rule; expect slightly more Pine entries.
'''


# Mined 2026-07-04 by app.strategy_search (1,596 combos, split-half filter):
# the ONLY combo positive in both halves. n=39 (just under MIN_N=40) AND
# best-of-1,596 → assume multiple-comparisons luck until the Monday re-rank
# confirms it on fresh data. It does rhyme with the live-log edge (≈10:00 BKK
# entries pay) and the ASIAN_DIP family. Shadow-track only — never alert.
STRATEGIES["ASIAN_MORNING_LONG_v1"] = {
    "description": "Asian-morning momentum long: bull 4h bar closing RSI≥60 with MACD hist still <0, BKK 06–11h. Mined 2026-07-04 (+22%/39tr, both halves green, PF 1.23). Shadow — thin, unproven.",
    "signal_fn": _signal_custom,
    "timeframe": "4h",
    "params": {
        "direction": "long", "candle": "bull", "macd": "bear", "rsi_min": 60,
        "hour_from": 6, "hour_to": 11,
        "stop_pct": 0.63, "tp_pct": 1.5, "leverage": 10.0,
        "commission": 0.0015, "skip_sat": True, "cooldown_bars": 4,
        "once_per_day": True,
    },
}


# ── search-v3 gate-4 survivors — SHADOW TRACK ONLY, NEVER ALERT ──────────────
# Mined 2026-07-04 by app.strategy_search3 (dynamic k×ATR geometry, risk-
# normalized 2%/trade, 5x lev cap, 0.03%/side slippage). One representative per
# family of the 402 gate-4 survivors. These are registered so the Monday re-rank
# / prop-desk can track them on fresh data — NOT for promotion or alerting.
# No promotion before ~1 month of forward data (early Aug 2026). The phone-alert
# path (app/setups.py hero setups) never iterates STRATEGIES, so registration
# alone is inert. Params reproduce the search's own evaluation path exactly
# (strategy_search3.RISK merged with the survivor combo); see test_atr_stop.py.

# Family A — 4h trend-momentum long. 30mo: n=64, wr 40.6, PF 1.63, +67.7%,
# dd 19.2, halves +49.6/+7.2. Deep 7y: n=149, PF 1.42, +125.5%. Edge over the
# random long baseline +1.045%/trade (baseline itself −34.9%).
STRATEGIES["TREND_MOMO_VOLSPIKE_v3"] = {
    "description": "Trend-momentum long (v3 shadow): 4h EMA21>EMA50 uptrend, MACD hist >0, volume spike. 1.5×ATR stop, 3R target, 2%/trade risk. Mined 2026-07-04, gate-4 survivor. SHADOW — never alert, no promotion before ~Aug 2026.",
    "signal_fn": _signal_custom,
    "timeframe": "4h",
    "params": {
        "direction": "long", "timeframe": "4h", "trend": "up", "macd": "bull",
        "vol_spike": True, "atr_stop_mult": 1.5, "rr": 3.0,
        "risk_pct": 2.0, "leverage": 5.0, "slippage_pct": 0.03,
        "stop_pct": 1.0, "tp_pct": 2.0,
    },
}

# Family B — 1h dip-buy in bull structure. 30mo: n=46, wr 28.3, PF 1.62,
# +50.8%, dd 19.4, halves +18.8/+28.9. Deep 7y: n=147, PF 1.32, +88.3% but
# dd 52.5 — deep drawdown, watch it. Low win-rate / high-R geometry.
STRATEGIES["DIP_BB_MASTACK_v3"] = {
    "description": "Dip-buy long (v3 shadow): 1h close below lower Bollinger, EMA50>100>200 bull stack, high-vol regime. 2.5×ATR stop, 5R target, 2%/trade risk. Mined 2026-07-04, gate-4 survivor. Deep-history dd 52.5%. SHADOW — never alert, no promotion before ~Aug 2026.",
    "signal_fn": _signal_custom,
    "timeframe": "1h",
    "params": {
        "direction": "long", "timeframe": "1h", "bb": "below_lower",
        "ma_align": "bull", "atr_regime": "high", "atr_stop_mult": 2.5, "rr": 5.0,
        "risk_pct": 2.0, "leverage": 5.0, "slippage_pct": 0.03,
        "stop_pct": 1.0, "tp_pct": 2.0,
    },
}

# Family C — 1h short capitulation fade. 30mo: n=40, wr 50.0, PF 2.08, +70.0%,
# dd 12.7, halves +43.1/+13.5. Deep 7y: n=85, PF 1.40, +57.3%. Edge over the
# random short baseline +2.083%/trade (baseline SHORT loses −99.3%) — the
# biggest per-trade edge in the whole v3 run.
STRATEGIES["CAPITULATION_FADE_SHORT_v3"] = {
    "description": "Capitulation-fade short (v3 shadow): 1h green bar closing below lower Bollinger on a volume spike. 1.5×ATR stop, 3R target, 2%/trade risk. Mined 2026-07-04, gate-4 survivor — biggest per-trade edge in the run (+2.08%/trade vs a −99% random short). SHADOW — never alert, no promotion before ~Aug 2026.",
    "signal_fn": _signal_custom,
    "timeframe": "1h",
    "params": {
        "direction": "short", "timeframe": "1h", "candle": "bull",
        "bb": "below_lower", "vol_spike": True, "atr_stop_mult": 1.5, "rr": 3.0,
        "risk_pct": 2.0, "leverage": 5.0, "slippage_pct": 0.03,
        "stop_pct": 1.0, "tp_pct": 2.0,
    },
}


def run_custom(params: dict, months: int = 30, initial_capital: float = 637.0) -> dict:
    """Backtest a user-built parametric strategy through the exact same engine
    as the coded ones — same fills, fees, discipline gates, metrics."""
    tf = params.get("timeframe", "1h")
    df = load_ohlcv(months=months, timeframe=tf)
    df = add_indicators(df)
    result  = _run_backtest(df, _signal_custom, params, initial_capital)
    metrics = _compute_metrics(result, initial_capital, months)

    eq_df = pd.DataFrame(result["equity_curve"])
    eq_df["date"] = pd.to_datetime(eq_df["date"])
    eq_daily = eq_df.set_index("date").resample("1D").last().dropna().reset_index()
    eq_daily["date"] = eq_daily["date"].dt.strftime("%Y-%m-%d")

    bits = [params.get("direction", "long").upper(), tf]
    if params.get("rsi_max") is not None: bits.append(f"RSI≤{params['rsi_max']:g}")
    if params.get("rsi_min") is not None: bits.append(f"RSI≥{params['rsi_min']:g}")
    if params.get("trend"):  bits.append(f"trend {params['trend']}")
    if params.get("candle"): bits.append(f"{params['candle']} bar")
    if params.get("macd"):   bits.append(f"MACD {params['macd']}")
    if params.get("bb"):     bits.append("BB " + ("<lower" if params["bb"] == "below_lower" else ">upper"))
    if params.get("td"):     bits.append(f"TD {params['td']}")
    if params.get("ma_align"): bits.append(f"MA-stack {params['ma_align']}")
    if params.get("vol_spike"): bits.append("vol spike")
    if params.get("atr_regime"): bits.append(f"{params['atr_regime']}-vol")
    # chart structure + HTF — omitting these would describe the strategy as
    # looser than the one that was actually tested
    if params.get("pattern"):   bits.append(params["pattern"].replace("_", " "))
    if params.get("structure"): bits.append(f"structure {params['structure']}")
    if params.get("breakout"):  bits.append(f"breakout {params['breakout']}")
    if params.get("htf4h"):     bits.append(f"4h trend {params['htf4h']}")
    if params.get("htf1d"):     bits.append(f"1d trend {params['htf1d']}")
    if params.get("mayer_max") is not None: bits.append(f"2yMA≤{params['mayer_max']:g}")
    if params.get("mayer_min") is not None: bits.append(f"2yMA≥{params['mayer_min']:g}")
    if params.get("hour_from") is not None and params.get("hour_to") is not None:
        bits.append(f"BKK {params['hour_from']:02d}–{params['hour_to']:02d}h")
    geo = f"SL {params.get('stop_pct', 1.0):g}% · TP {params.get('tp_pct', 1.5):g}% · {params.get('leverage', 10):g}x"
    if params.get("atr_floor_mult"):
        geo += f" · ATRfloor {params['atr_floor_mult']:g}×"
    if params.get("slippage_pct"):
        geo += f" · slip {params['slippage_pct']:g}%"
    bits.append(geo)
    return {
        "strategy":    "CUSTOM",
        "description": " · ".join(bits),
        "metrics":     metrics,
        "trades":      result["trades"],
        "equity_curve": eq_daily.to_dict("records"),
        "params":      params,
        "months":      months,
        "ran_at":      datetime.now(timezone.utc).isoformat(),
    }
