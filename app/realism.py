"""C4 — regime-realism check: is the envelope's edge actually on offer?

The complaint this fixes: Fit says "7 trades/wk at 7% moves, 2× lev" — feasible
on paper, unavailable in the market that is actually on offer. Feasibility and
availability are different questions and the goal model only answers the first.

The check: take the required TP move, count the days in the last 90 whose full
range cleared it — and separately, the days that did so *within the current
regime*, because a move that BULL hands you every other day may never appear in
SIDEWAYS. Turn that into offered setups per week and hold it next to the trades
per week the plan needs.

  OFFERED   supply ≥ 1.5× need
  TIGHT     0.75 – 1.5×
  STARVED   < 0.75×

Always with the numbers: "needs 7/wk · regime offers ~2/wk".

ponytail: day-range vs required-move is a proxy — it ignores intraday path (a day
can range 3% without ever handing you 3% from your entry) and session timing.
It also treats one qualifying day as at most one setup, so supply is a ceiling.
Ship the proxy; upgrade to session-window ranges only if the badge misleads in
practice.
"""

import sqlite3
import time
from datetime import datetime, timezone

from .database import DB_PATH

SYMBOL = "binance:BTC/USDT"
WINDOW_DAYS = 90
TTL = 900          # 15 min — daily ranges and the regime map don't move faster
OFFERED, TIGHT, STARVED = "OFFERED", "TIGHT", "STARVED"

_cache: dict = {}


def _memo(key: str, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


# ─── daily range distribution ────────────────────────────────────────────────

def _daily_ranges(days: int = WINDOW_DAYS) -> list[dict]:
    """[{date, range_pct}] for the last `days` UTC days, from the 1h cache."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT ts, high, low, open FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe='1h' ORDER BY ts DESC LIMIT ?",
        (SYMBOL, days * 24 + 24),
    ).fetchall()
    conn.close()
    bars: dict = {}
    for ts, h, l, o in reversed(rows):
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        b = bars.setdefault(d, {"h": h, "l": l, "o": o})
        b["h"], b["l"] = max(b["h"], h), min(b["l"], l)
    out = [{"date": d, "range_pct": (b["h"] - b["l"]) / b["o"] * 100.0}
           for d, b in bars.items() if b["o"]]
    return out[-days:]


def _regime_map() -> tuple[str, dict]:
    """(current regime, date→regime). Degrades to ("UNKNOWN", {}) if the feed
    is down — the 90-day supply still works, only the regime slice is lost."""
    try:
        from .regime import detect_regimes
        r = detect_regimes()
        return r.get("current_regime", "UNKNOWN"), r.get("by_date", {})
    except Exception:
        return "UNKNOWN", {}


def supply(move_pct: float) -> dict:
    """How many days per week the market hands you a range ≥ move_pct — overall,
    and within the current regime."""
    daily = _memo("daily", _daily_ranges)
    current, by_date = _memo("regime", _regime_map)
    if not daily or move_pct is None or move_pct <= 0:
        return {"days": 0, "per_week": None, "regime": current, "regime_per_week": None}

    hit = sum(1 for d in daily if d["range_pct"] >= move_pct)
    reg = [d for d in daily if by_date.get(d["date"]) == current] if by_date else []
    reg_hit = sum(1 for d in reg if d["range_pct"] >= move_pct)
    return {
        "move_pct": round(move_pct, 3),
        "days": len(daily), "hit": hit,
        "per_week": round(hit / len(daily) * 7, 2),
        "regime": current, "regime_days": len(reg), "regime_hit": reg_hit,
        "regime_per_week": round(reg_hit / len(reg) * 7, 2) if reg else None,
    }


def badge(move_pct: float, needed_per_week: float) -> dict | None:
    """The verdict. Uses the regime-conditioned supply when the regime is known —
    the market you're in now is the one that has to hand you the setups."""
    if not move_pct or not needed_per_week or needed_per_week <= 0:
        return None
    s = supply(move_pct)
    offers = s.get("regime_per_week")
    scope = f"{s['regime']} regime"
    if offers is None:
        offers, scope = s.get("per_week"), "last 90d"
    if offers is None:
        return None
    ratio = offers / needed_per_week
    word = OFFERED if ratio >= 1.5 else TIGHT if ratio >= 0.75 else STARVED
    return {
        "badge": word, "ratio": round(ratio, 2),
        "needs": round(needed_per_week, 2), "offers": offers, "scope": scope,
        "move_pct": s["move_pct"], "days": s["days"], "hit": s["hit"],
        "regime": s["regime"], "per_week_90d": s.get("per_week"),
        "text": f"needs {needed_per_week:.2g}/wk · {scope} offers ~{offers:g}/wk "
                f"of ≥{s['move_pct']:.2f}% moves",
    }


# ─── per-strategy required move (the /edge search rows) ──────────────────────

def atr_pct(timeframe: str) -> float | None:
    """Mean ATR(14) as % of close on `timeframe` — the scale a k×ATR stop is
    measured in. Cached: the search polls this every couple of seconds."""
    def _load():
        from .backtest_engine import add_indicators, load_ohlcv
        df = add_indicators(load_ohlcv(months=6, timeframe=timeframe))
        return float((df["atr14"] / df["close"]).mean() * 100.0)
    try:
        return _memo(f"atr:{timeframe}", _load)
    except Exception:
        return None


def row_move_pct(k: float, rr: float, timeframe: str) -> float | None:
    """A search row's TP move: stop = k×ATR, TP = rr×stop."""
    a = atr_pct(timeframe)
    return None if a is None else k * a * rr


if __name__ == "__main__":   # ponytail: one runnable check
    d = _daily_ranges()
    assert d and all(x["range_pct"] >= 0 for x in d), "no daily ranges"
    assert len(d) <= WINDOW_DAYS

    # supply is monotone: a bigger required move can never be offered more often
    lo, hi = supply(0.5), supply(8.0)
    assert lo["per_week"] >= hi["per_week"], (lo, hi)

    # the three verdicts, driven purely by the ratio
    easy = badge(0.2, 0.5)      # a move the market hands over constantly
    hard = badge(25.0, 7.0)     # a move BTC essentially never makes in a day
    assert easy["badge"] == OFFERED, easy
    assert hard["badge"] == STARVED, hard
    assert badge(1.0, 0) is None and badge(0, 1.0) is None
    print("90d:", {k: v for k, v in supply(2.0).items()})
    print("easy:", easy["text"])
    print("hard:", hard["text"])
    print("1h ATR%:", atr_pct("1h"), "→ 1.5k×3R move:", row_move_pct(1.5, 3.0, "1h"))
