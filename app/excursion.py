"""MAE / MFE — how far each trade ran against you, and how far it ran your way.

Answers the one question the realized-R number can't: is a low R an EXIT problem
(the move was there, you left it on the table) or a SELECTION problem (the move
was never on offer)? Capture = realized / MFE separates them.

Excursions are in PERCENT OF ENTRY, not in R. `trades.sl` is NULL on all 497
closed rows, so there is no per-trade risk denominator to divide by and an
R-multiple here would be invented. Percent-of-entry is the underlying move,
which is what the geometry (`setups.SL_PCT` / `setups.TP_PCT`) is already quoted
in. Read those constants; never re-pin a literal here — this module graded the
book against a retired 0.95% TP for as long as it existed.

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

from .paths import DB_PATH as _DB_PATH

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


def summary(rows: Optional[list[dict]] = None,
            tp_pct: Optional[float] = None, sl_pct: Optional[float] = None) -> dict:
    """Medians, not means: excursion distributions have long right tails.

    tp_pct/sl_pct default to the LIVE geometry in `setups`, never to a literal.
    They were pinned at the old 0.95% TP here while `setups.TP_PCT` had already
    moved to 1.5%, so the panel graded the book against a target it no longer
    trades. The bar the excursions are held against has to be the bar in use — a
    TP the median trade never reaches is not a target, it's a wish.
    """
    from .setups import SL_PCT, TP_PCT      # lazy: setups is heavy, and imports this
    tp_pct = TP_PCT if tp_pct is None else tp_pct
    sl_pct = SL_PCT if sl_pct is None else sl_pct
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
        "tp_pct": tp_pct, "sl_pct": sl_pct,
        "reach": reachability(tp_pct, sl_pct, rows=rows),
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


def reachability(win_move_pct: float, loss_move_pct: float, rows: Optional[list[dict]] = None,
                 fee_r: float = 0.112, min_n: int = 30) -> Optional[dict]:
    """Can this geometry win at all, given the moves the market has actually made?

    `reach` is the share of closed trades whose price EVER travelled the required
    TP move. Because you cannot win a trade whose target is never touched, reach is
    a CEILING on win rate — and it is a generous one: it ignores whether the stop
    was hit first, so the true ceiling is lower still.

    Hold that ceiling against the win rate the geometry needs to break even,
    WR* = (1 + fee_R) / (1 + R) where R = TP/SL. If the ceiling sits below WR*, no
    amount of entry skill makes the setup profitable — the target is out of reach.

    This is a STANDING VERDICT on the book, not a per-alert signal. It reads only
    the geometry, so for a fixed TP/SL it returns the same word on every trade —
    every plausible cell of a 3×5 TP/SL sweep came back STARVED on 2026-07-09.
    It was briefly wired to the ntfy alert title; that made an alarm that fires
    100% of the time. Keep it on /analytics, where a verdict is read once.

    ponytail: `reach` is measured over the trades he TOOK, at the holds he chose,
    so it is conditioned on his selection rather than on the market at large. That
    is the right conditioning for "is this book's geometry survivable?" and the
    wrong one for "does this edge exist anywhere?". Don't reuse it for the latter.
    """
    if not win_move_pct or not loss_move_pct or win_move_pct <= 0 or loss_move_pct <= 0:
        return None
    rows = excursions() if rows is None else rows
    if len(rows) < min_n:
        return None
    hit = sum(r["mfe_pct"] >= win_move_pct for r in rows)
    reach = hit / len(rows)
    rr = win_move_pct / loss_move_pct
    breakeven_wr = (1.0 + fee_r) / (1.0 + rr)
    ratio = reach / breakeven_wr if breakeven_wr else None
    word = "OFFERED" if ratio >= 1.25 else "TIGHT" if ratio >= 1.0 else "STARVED"
    return {
        "badge": word, "ratio": round(ratio, 2),
        "reach": round(reach, 4), "breakeven_wr": round(breakeven_wr, 4),
        "n": len(rows), "hit": hit, "rr": round(rr, 3),
        "move_pct": round(win_move_pct, 3),
        "text": (f"ceiling {reach:.0%} · breakeven needs {breakeven_wr:.0%} "
                 f"({hit}/{len(rows)} fills ever reached {win_move_pct:.2f}%)"),
    }


if __name__ == "__main__":
    rows = excursions()
    s = summary(rows)
    for k, v in s.items():
        print(f"{k:28} {v}")
