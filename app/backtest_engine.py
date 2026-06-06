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
_DB_PATH = Path(__file__).parent.parent / "lens.db"

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

    # Daily close / EMA50 (resample 4H → daily, ffill back)
    daily_close = c.resample("1D").last()
    daily_ema50 = daily_close.ewm(span=50, adjust=False).mean()
    df["daily_close"] = daily_close.reindex(df.index, method="ffill")
    df["daily_ema50"] = daily_ema50.reindex(df.index, method="ffill")

    # Rolling structure highs/lows (for TREND_4R breakout)
    df["hi20"] = df["high"].shift(1).rolling(20).max()
    df["lo20"] = df["low"].shift(1).rolling(20).min()

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


def _run_backtest(df: pd.DataFrame, signal_fn, params: dict,
                  initial_capital: float = 637.0) -> dict:
    stop_pct    = params.get("stop_pct",    1.0) / 100
    tp_pct      = params.get("tp_pct",      4.0) / 100
    leverage    = params.get("leverage",   10.0)
    commission  = params.get("commission", 0.0015)  # per side
    skip_sat    = params.get("skip_sat",   True)
    cooldown    = params.get("cooldown_bars", 4)
    once_per_day = params.get("once_per_day", True)

    equity = initial_capital
    trades = []
    equity_curve = [{"date": df.index[0].isoformat(), "equity": round(equity, 2)}]

    in_trade      = False
    direction     = None
    entry_price   = 0.0
    entry_bar_idx = 0
    last_entry_bar = -999
    last_trade_day = None

    for i in range(1, len(df)):
        ts = df.index[i]

        if in_trade:
            hi = df["high"].iloc[i]
            lo = df["low"].iloc[i]

            sl_long  = entry_price * (1 - stop_pct)
            tp_long  = entry_price * (1 + tp_pct)
            sl_short = entry_price * (1 + stop_pct)
            tp_short = entry_price * (1 - tp_pct)

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
                    net_pct =  tp_pct   * leverage - commission * 2 * leverage
                else:
                    net_pct = -(stop_pct * leverage + commission * 2 * leverage)
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
                    "hours_held": round(bars_held * 4, 1),
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
    }


# ─── Strategy registry ────────────────────────────────────────────────────────

STRATEGIES: dict = {
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
}


# ─── Public entry point ───────────────────────────────────────────────────────

def run_strategy(name: str, months: int = 30,
                 initial_capital: float = 637.0) -> dict:
    """Run a full backtest for the named strategy. Returns metrics + equity curve + trades."""
    if name not in STRATEGIES:
        return {"error": f"unknown strategy: {name}"}

    strat = STRATEGIES[name]
    df = load_ohlcv(months=months)
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
