"""Positioning feeds: perp funding rate and open interest.

The first genuinely new input in the search. Every previous slot — RSI, MACD,
Bollinger, TD, patterns, HTF trend — is a rearrangement of the same OHLC
candles, so a search over them can only ever recombine what price already
said. Funding is different data: it is what the crowd is PAYING to hold its
position. Strongly positive funding = longs paying shorts = crowded long,
which is a short-side fade condition, and the short side is where the
validated edge lives.

Availability, measured against the live APIs on 2026-08-04 (this is the whole
design constraint, so it is written down rather than assumed):

  · funding rate  — Binance USDT-perp, 7,560 settlements back to 2019-09-10,
                    clean 8h cadence, 9 paged requests. Fully backtestable
                    over the same 7-year window the deep-confirmation stage
                    already uses.
  · open interest — ~30 DAYS ONLY. Bybit returned 2026-07-01→08-04, Binance
                    2026-07-04→08-04, and Binance rejects a startTime older
                    than its retention window outright. This is an exchange
                    retention limit, not a paging bug — no amount of
                    pagination reaches further back.

So OI cannot be backtested today: 30 days is ~180 4h bars, and any combo
gated on it lands far below MIN_N=40. Rather than pollute the search with
combos that can only return n≈0, OI is COLLECTED here and left out of SLOTS.
collect_open_interest() appends each fresh 30-day window to the same cache;
run it on a cron and the history accumulates going forward.

ponytail: no OI slots until ~18 months of collected history exists. When it
does, the wiring is oi_columns() + a SLOTS entry mirroring the funding one —
deliberately NOT auto-enabled on a coverage check, because a search space
that silently changes shape between runs is not reproducible.
"""

import sqlite3
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import ccxt

from .paths import DB_PATH as _DB_PATH

FUNDING_SOURCE = "binance:BTC/USDT:USDT"
OI_SOURCE      = "bybit:BTC/USDT:USDT"
FUNDING_START  = datetime(2019, 9, 1, tzinfo=timezone.utc)   # feed begins 2019-09-10
PCT_WINDOW     = 90     # trailing funding settlements for the percentile rank
                        # (3/day × 30d) — regime-relative, because absolute
                        # funding levels drift hard across a 7-year window


def _conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flow_cache (
            source TEXT NOT NULL,
            metric TEXT NOT NULL,
            ts     INTEGER NOT NULL,
            value  REAL,
            PRIMARY KEY (source, metric, ts)
        )
    """)
    conn.commit()
    return conn


def _cached(conn, source: str, metric: str) -> pd.Series:
    rows = conn.execute(
        "SELECT ts, value FROM flow_cache WHERE source=? AND metric=? ORDER BY ts ASC",
        (source, metric),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True)
    return pd.Series([r[1] for r in rows], index=idx, dtype=float)


def _store(conn, source: str, metric: str, pairs) -> int:
    pairs = [(source, metric, int(ts), float(v)) for ts, v in pairs if v is not None]
    if pairs:
        conn.executemany("INSERT OR REPLACE INTO flow_cache VALUES (?,?,?,?)", pairs)
        conn.commit()
    return len(pairs)


# ─── Funding rate ────────────────────────────────────────────────────────────

def load_funding(refresh: bool = True) -> pd.Series:
    """Full funding-rate history as a Series indexed by settlement time.

    Incremental: only settlements newer than the cache are fetched, so the
    steady-state cost is one request. Fail-soft — a network error returns
    whatever is cached, because a dead API must not take the backtester down
    with it.
    """
    conn = _conn()
    ser = _cached(conn, FUNDING_SOURCE, "funding")

    if refresh:
        since = int(ser.index[-1].timestamp() * 1000) + 1 if len(ser) \
            else int(FUNDING_START.timestamp() * 1000)
        try:
            ex = ccxt.binance({"enableRateLimit": True,
                               "options": {"defaultType": "swap"}})
            fetched, cur = [], since
            while True:
                chunk = ex.fetch_funding_rate_history(
                    "BTC/USDT:USDT", since=cur, limit=1000)
                if not chunk:
                    break
                fetched += [(c["timestamp"], c["fundingRate"]) for c in chunk]
                if chunk[-1]["timestamp"] <= cur:
                    break
                cur = chunk[-1]["timestamp"] + 1
                time.sleep(0.2)
            n = _store(conn, FUNDING_SOURCE, "funding", fetched)
            if n:
                print(f"[orderflow] cached {n} new funding settlements")
                ser = _cached(conn, FUNDING_SOURCE, "funding")
        except Exception as e:
            print(f"[orderflow] funding fetch failed ({type(e).__name__}: {e}) "
                  f"— using {len(ser)} cached")

    conn.close()
    return ser


def funding_columns(df: pd.DataFrame, refresh: bool = True) -> pd.DataFrame:
    """Attach fund_rate + fund_pct to a bar frame, aligned without lookahead.

    Each bar takes the last funding rate SETTLED AT OR BEFORE the bar's index
    timestamp. df.index is bar-OPEN time (ccxt convention) and signals fire on
    bar close, so this is strictly conservative: the rate was public for the
    whole bar before the entry decision is taken.

    fund_rate — the raw 8h rate (positive = longs pay shorts = crowded long)
    fund_pct  — its rank in the trailing 90-settlement window, 0..1. Absolute
                funding drifted a long way between 2019 and 2026, so a fixed
                threshold means different things in different years; a
                percentile keeps 'crowded' meaning the same thing throughout.
    """
    ser = load_funding(refresh=refresh)
    if ser.empty or df.empty:
        df["fund_rate"] = np.nan
        df["fund_pct"] = np.nan
        return df

    # Percentile computed on the funding series' own 8h cadence, so it does not
    # change meaning when the bar timeframe changes. min_periods keeps the
    # warm-up honest instead of ranking against a half-empty window.
    pct = ser.rolling(PCT_WINDOW, min_periods=PCT_WINDOW).apply(
        lambda w: (w[:-1] <= w[-1]).mean(), raw=True)

    flow = pd.DataFrame({"fund_rate": ser, "fund_pct": pct})

    # merge_asof refuses to join keys of different datetime RESOLUTIONS, and the
    # frames reaching here genuinely differ: ohlcv_cache rows come back through
    # pd.to_datetime(unit="ms") as nanosecond stamps, while a pd.date_range built
    # in a test or a resampled frame can be microsecond. Same instants, different
    # dtype, hard MergeError. Pin both sides to nanoseconds instead of trusting
    # the caller. Only .to_numpy() is read off the result, so row order — not the
    # merged index — is what carries the alignment back.
    left = pd.DataFrame(index=df.index.as_unit("ns")).sort_index()
    flow.index = flow.index.as_unit("ns")
    merged = pd.merge_asof(
        left, flow.sort_index(),
        left_index=True, right_index=True, direction="backward",
    )
    df["fund_rate"] = merged["fund_rate"].to_numpy()
    df["fund_pct"] = merged["fund_pct"].to_numpy()
    return df


# ─── Open interest (collect-only; see module docstring) ──────────────────────

def collect_open_interest(timeframe: str = "4h") -> int:
    """Append the exchange's current ~30-day OI window to the cache.

    Nothing here is usable for backtesting yet; the point is that history only
    exists in future if collection starts now. Idempotent (INSERT OR REPLACE),
    so running it daily just fills the overlap.

    Run: python3 -m app.orderflow
    """
    conn = _conn()
    try:
        ex = ccxt.bybit({"enableRateLimit": True,
                         "options": {"defaultType": "swap"}})
        rows = ex.fetch_open_interest_history("BTC/USDT:USDT", timeframe, limit=200)
        n = _store(conn, OI_SOURCE, f"oi_{timeframe}",
                   [(r["timestamp"], r.get("openInterestAmount")) for r in rows])
        span = _cached(conn, OI_SOURCE, f"oi_{timeframe}")
        print(f"[orderflow] OI {timeframe}: +{n} rows, cache now {len(span)} "
              f"({span.index[0].date()} → {span.index[-1].date()})"
              if len(span) else f"[orderflow] OI {timeframe}: +{n} rows")
        return n
    except Exception as e:
        print(f"[orderflow] OI collect failed: {type(e).__name__}: {e}")
        return 0
    finally:
        conn.close()


def oi_coverage_days(timeframe: str = "4h") -> float:
    """How much OI history has accumulated — the gate on wiring OI slots."""
    conn = _conn()
    ser = _cached(conn, OI_SOURCE, f"oi_{timeframe}")
    conn.close()
    if len(ser) < 2:
        return 0.0
    return round((ser.index[-1] - ser.index[0]).total_seconds() / 86400, 1)


if __name__ == "__main__":
    collect_open_interest()
    print(f"[orderflow] OI coverage: {oi_coverage_days()} days "
          f"(need ~550 before OI slots are worth searching)")
