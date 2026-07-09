"""MAE / MFE — how far each trade ran against you, and how far it ran your way.

Answers the one question the realized-R number can't: is a low R an EXIT problem
(the move was there, you left it on the table) or a SELECTION problem (the move
was never on offer)? Capture = realized / MFE separates them.

Excursions are in PERCENT OF ENTRY, not in R. `trades.sl` is NULL on all 497
closed rows, so there is no per-trade risk denominator to divide by and an
R-multiple here would be invented. Percent-of-entry is the underlying move,
which is what the geometry (0.63% SL / 0.95% TP) is already quoted in.

ponytail: a candle that straddles the entry (or the exit) contributes its whole
high/low, so both excursions are very slightly overstated at the edges. At 5m
resolution against multi-hour holds this is noise. Upgrade to trade-tick data
only if a decision ever turns on the third decimal.
"""
import sqlite3
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Optional

_DB_PATH = Path(__file__).parent.parent / "lens.db"

# Preference order: finest resolution first. 5m stops ~2026-06-26, 1h runs to now,
# so recent trades fall back automatically rather than dropping out of the sample.
_SOURCES = [
    ("bybit:BTC/USDT:USDT", "5m", 300_000),
    ("bybit:BTC/USDT:USDT", "1h", 3_600_000),
    ("binance:BTC/USDT", "1h", 3_600_000),
]


def _ms(iso: str) -> Optional[int]:
    if not iso:
        return None
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def _load(conn, symbol: str, timeframe: str) -> tuple[list[int], list[float], list[float]]:
    rows = conn.execute(
        "SELECT ts, high, low FROM ohlcv_cache WHERE symbol=? AND timeframe=? ORDER BY ts",
        (symbol, timeframe),
    ).fetchall()
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]


def _window(ts, highs, lows, tf_ms, open_ms, close_ms):
    """High/low across every candle overlapping [open_ms, close_ms]."""
    lo = bisect_right(ts, open_ms - tf_ms)   # first candle whose end is past entry
    hi = bisect_left(ts, close_ms)           # last candle that starts before exit
    if hi <= lo:
        hi = lo + 1                          # sub-candle trade: use the one it sits in
    if lo >= len(ts):
        return None
    hi = min(hi, len(ts))
    return max(highs[lo:hi]), min(lows[lo:hi])


def excursions(limit: Optional[int] = None) -> list[dict]:
    """Per-trade MAE/MFE for every closed trade the candle cache can cover."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    series = {(s, tf): _load(conn, s, tf) for s, tf, _ in _SOURCES}
    trades = conn.execute(
        "SELECT id, direction, entry, exit, opened_at, closed_at, pnl, setup_tag "
        "FROM trades WHERE exit IS NOT NULL AND closed_at IS NOT NULL AND entry > 0 "
        "ORDER BY opened_at"
    ).fetchall()
    conn.close()

    out = []
    for t in trades:
        o_ms, c_ms = _ms(t["opened_at"]), _ms(t["closed_at"])
        if o_ms is None or c_ms is None or c_ms < o_ms:
            continue
        hit = None
        for sym, tf, tf_ms in _SOURCES:
            ts, highs, lows = series[(sym, tf)]
            if not ts or o_ms < ts[0] or c_ms > ts[-1] + tf_ms:
                continue            # window not covered by this series
            w = _window(ts, highs, lows, tf_ms, o_ms, c_ms)
            if w:
                hit = (w, tf)
                break
        if not hit:
            continue
        (hi, lo), tf = hit
        entry, exit_ = t["entry"], t["exit"]
        long = t["direction"] == "long"

        mfe = (hi - entry) / entry if long else (entry - lo) / entry
        mae = (entry - lo) / entry if long else (hi - entry) / entry
        realized = (exit_ - entry) / entry if long else (entry - exit_) / entry
        # An excursion is a distance, never negative: price that only ever went one
        # way means the other excursion is zero, not a negative number.
        mfe, mae = max(mfe, 0.0), max(mae, 0.0)

        out.append({
            "id": t["id"], "direction": t["direction"], "setup_tag": t["setup_tag"],
            "opened_at": t["opened_at"], "pnl": t["pnl"], "resolution": tf,
            "mfe_pct": round(mfe * 100, 4),
            "mae_pct": round(mae * 100, 4),
            "realized_pct": round(realized * 100, 4),
            # How much of the best available move you actually banked. >1 means you
            # exited beyond the best close-to-close excursion (a gap in your favour).
            "capture": round(realized / mfe, 4) if mfe > 1e-9 else None,
        })
        if limit and len(out) >= limit:
            break
    return out


def summary(rows: Optional[list[dict]] = None, tp_pct: float = 0.95) -> dict:
    """Medians, not means: excursion distributions have long right tails.

    tp_pct is the mined take-profit geometry (0.95% underlying). It is the bar the
    excursions are held against — a TP the median trade never reaches is not a
    target, it's a wish.
    """
    rows = excursions() if rows is None else rows
    if not rows:
        return {"n": 0}
    wins = [r for r in rows if (r["pnl"] or 0) > 0]
    losses = [r for r in rows if (r["pnl"] or 0) <= 0]
    # Capture is only interpretable on WINNERS. On a loser, realized is negative and
    # the ratio is a sign artefact, not a fraction of the move banked.
    caps = [r["capture"] for r in wins if r["capture"] is not None]
    cap_med = median(caps) if caps else None
    mfe_losers = median(r["mfe_pct"] for r in losses) if losses else None
    return {
        "n": len(rows),
        "n_5m": sum(r["resolution"] == "5m" for r in rows),
        "median_mfe_pct": round(median(r["mfe_pct"] for r in rows), 3),
        "median_mae_pct": round(median(r["mae_pct"] for r in rows), 3),
        "median_realized_pct": round(median(r["realized_pct"] for r in rows), 3),
        # How much of the best available move you banked, on trades that worked.
        "median_capture_on_winners": round(cap_med, 3) if cap_med else None,
        # The diagnostic: on LOSERS, how far did price go your way before it died?
        # A fat number means the exits are the problem, not the entries.
        "median_mfe_on_losers_pct": round(mfe_losers, 3) if mfe_losers is not None else None,
        "median_mae_on_winners_pct": round(median(r["mae_pct"] for r in wins), 3) if wins else None,
        "pct_never_reached_tp": round(100 * sum(r["mfe_pct"] < tp_pct for r in rows) / len(rows), 1),
        "pct_losers_that_touched_tp": round(
            100 * sum(r["mfe_pct"] >= tp_pct for r in losses) / len(losses), 1) if losses else None,
        "verdict": _verdict(cap_med, mfe_losers),
    }


def _verdict(cap: Optional[float], mfe_losers: Optional[float]) -> str:
    """Early exits vs absent moves — the whole reason this module exists.

    cap is median capture ON WINNERS; mfe_losers is the median favourable
    excursion (%) on losers. High capture + flat losers = you take what's offered
    and nothing is offered. Low capture + fat losers = the move came and you sat.
    """
    if cap is None or mfe_losers is None:
        return "insufficient data"
    if cap >= 0.7 and mfe_losers < 0.5:
        return "SELECTION — you bank the move when it comes; on losers it never comes"
    if cap < 0.5 and mfe_losers >= 0.5:
        return "EXITS — the move was there on losers, you didn't take it"
    return "MIXED — neither exits nor selection dominates"


if __name__ == "__main__":
    rows = excursions()
    s = summary(rows)
    for k, v in s.items():
        print(f"{k:28} {v}")
