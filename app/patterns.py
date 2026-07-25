"""Chart-pattern and higher-timeframe features for the strategy search.

Why this exists: `strategy_search.SLOTS` was ten indicator slots — trend, RSI,
MACD, Bollinger, TD, MA alignment, volume, ATR, hour. Every strategy the grid
search and the breeder have ever found was built from that vocabulary, so no
run has ever been *able* to find a double-bottom strategy or a "4h trend up,
enter on the 15m" strategy. Absence of those findings was a vocabulary limit,
not evidence against them.

Everything here returns a plain bool numpy array aligned to `df.index`, so it
drops straight into `_masks()` and the whole pipeline (grid search, breeder,
board) gains it at once.

═══ CAUSALITY ═══

Every feature is causal: the value at bar i uses only bars ≤ i. This is the
whole correctness burden of this module, because a lookahead bug here does not
crash — it silently prints a spectacular backtest and loses real money.

Two specific traps, both handled:

  · A swing pivot is NOT known when it happens. A pivot high at bar i needs
    `right` more bars to confirm it is a local max, so it first becomes usable
    at bar i+right. Every pivot array here is shifted by `right`.
  · A higher-timeframe bar is NOT known until it closes. The 4h bar covering
    09:00–13:00 is unknown at 10:00. HTF series are shifted one HTF bar before
    being broadcast down.

`tests/test_patterns.py` asserts both properties directly.
"""
import numpy as np
import pandas as pd

# Swing-pivot shape. left/right are bars either side that must be lower (for a
# high). right also sets the confirmation lag — bigger = cleaner pivots, later.
PIVOT_LEFT = 3
PIVOT_RIGHT = 3


def _pivots(df, left=PIVOT_LEFT, right=PIVOT_RIGHT):
    """(pivot_high, pivot_low) bool arrays, each already shifted by `right`.

    True at bar i means "a pivot was confirmed as of bar i", not "bar i is a
    pivot" — that distinction is what keeps the feature causal."""
    high, low = df["high"], df["low"]
    win = left + right + 1
    # centred rolling extreme: is this bar the max of its neighbourhood?
    roll_max = high.rolling(win, center=True).max()
    roll_min = low.rolling(win, center=True).min()
    ph = (high >= roll_max) & roll_max.notna()
    pl = (low <= roll_min) & roll_min.notna()
    # confirmation lag — a centred window peeks `right` bars ahead, so the
    # result is only legitimately available `right` bars later.
    return (ph.shift(right, fill_value=False).to_numpy(),
            pl.shift(right, fill_value=False).to_numpy())


def _last_two(values, flags, i, lookback):
    """The two most recent flagged values at or before bar i, newest first.

    Returns None when there aren't two inside `lookback` — a pattern with only
    one pivot to stand on is not a pattern."""
    lo = max(0, i - lookback + 1)
    idx = np.flatnonzero(flags[lo:i + 1])
    if len(idx) < 2:
        return None
    a, b = idx[-1] + lo, idx[-2] + lo
    return values[a], values[b]


# A double top is an EVENT, not a regime. The first cut used tol=0.006 and a
# 60-bar lookback with no freshness rule and fired on 51% of bars — it meant
# "a double top happened at some point recently", which is not a signal, it's
# weather. `fresh` is what makes it an event: the second touch must have just
# been confirmed. `min_gap` rejects two pivots a few bars apart, which is one
# jagged top, not two tests of a level.
DT_TOL = 0.003
DT_FRESH = 6
DT_MIN_GAP = 8


def _double(values, flags, tol, lookback, fresh, min_gap):
    out = np.zeros(len(values), dtype=bool)
    for i in range(len(values)):
        lo = max(0, i - lookback + 1)
        idx = np.flatnonzero(flags[lo:i + 1])
        if len(idx) < 2:
            continue
        a, b = idx[-1] + lo, idx[-2] + lo          # newest, previous
        if i - a > fresh or a - b < min_gap:
            continue
        if abs(values[a] - values[b]) / max(values[b], 1e-9) <= tol:
            out[i] = True
    return out


def double_top(df, tol=DT_TOL, lookback=60, fresh=DT_FRESH, min_gap=DT_MIN_GAP):
    """A level just rejected for the second time at a comparable high."""
    ph, _ = _pivots(df)
    return _double(df["high"].to_numpy(), ph, tol, lookback, fresh, min_gap)


def double_bottom(df, tol=DT_TOL, lookback=60, fresh=DT_FRESH, min_gap=DT_MIN_GAP):
    """A level just held for the second time at a comparable low."""
    _, pl = _pivots(df)
    return _double(df["low"].to_numpy(), pl, tol, lookback, fresh, min_gap)


def structure(df, direction, lookback=60):
    """Market structure: 'up' = higher high AND higher low, 'down' = the mirror.

    This is the "top, then a lower high" read — the thing you look at by eye
    — expressed as confirmed pivots rather than as an indicator."""
    ph, pl = _pivots(df)
    high, low = df["high"].to_numpy(), df["low"].to_numpy()
    out = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        hs = _last_two(high, ph, i, lookback)
        ls = _last_two(low, pl, i, lookback)
        if not hs or not ls:
            continue
        if direction == "up":
            out[i] = hs[0] > hs[1] and ls[0] > ls[1]
        else:
            out[i] = hs[0] < hs[1] and ls[0] < ls[1]
    return out


def breakout(df, direction, window=20):
    """Close beyond the prior `window` bars' extreme — the prior bars EXCLUDE
    the current one, or every breakout would trivially include its own bar."""
    if direction == "up":
        prior = df["high"].rolling(window).max().shift(1)
        return (df["close"] > prior).fillna(False).to_numpy()
    prior = df["low"].rolling(window).min().shift(1)
    return (df["close"] < prior).fillna(False).to_numpy()


def htf_trend(df, rule, direction, fast=21, slow=50):
    """Higher-timeframe trend broadcast onto this df's bars.

    This is the "trend on the 4h, execute on the 15m" feature. `rule` is a
    pandas offset for the higher frame ('4H', '1D').

    The shift(1) is load-bearing: an HTF bar is only known once it has closed,
    so bars inside the forming HTF bar must see the PREVIOUS one. Without it a
    15m entry would know how its own 4h bar ends."""
    htf_close = df["close"].resample(rule).last().dropna()
    if len(htf_close) < slow + 1:
        return np.zeros(len(df), dtype=bool)
    ema_f = htf_close.ewm(span=fast, adjust=False).mean()
    ema_s = htf_close.ewm(span=slow, adjust=False).mean()
    up = (ema_f > ema_s).shift(1)              # only closed HTF bars are visible
    broadcast = up.reindex(df.index, method="ffill")
    trend_up = broadcast.fillna(False).astype(bool).to_numpy()
    return trend_up if direction == "up" else ~trend_up & _seen(broadcast)


def _seen(broadcast):
    """Bars where an HTF verdict actually exists — so 'down' means a real
    down-verdict, not merely the absence of one during warm-up."""
    return broadcast.notna().to_numpy()


# The slots these features add, in `strategy_search.SLOTS` form. Kept here so
# the vocabulary and its implementation live together.
PATTERN_SLOTS = {
    "pattern":   ["double_top", "double_bottom"],
    "structure": ["up", "down"],
    "breakout":  ["up", "down"],
    "htf4h":     ["up", "down"],
    "htf1d":     ["up", "down"],
}


def pattern_masks(df) -> dict:
    """Every PATTERN_SLOTS option as a (slot, option) -> bool array mapping."""
    return {
        ("pattern", "double_top"):    double_top(df),
        ("pattern", "double_bottom"): double_bottom(df),
        ("structure", "up"):          structure(df, "up"),
        ("structure", "down"):        structure(df, "down"),
        ("breakout", "up"):           breakout(df, "up"),
        ("breakout", "down"):         breakout(df, "down"),
        ("htf4h", "up"):              htf_trend(df, "4h", "up"),
        ("htf4h", "down"):            htf_trend(df, "4h", "down"),
        ("htf1d", "up"):              htf_trend(df, "1D", "up"),
        ("htf1d", "down"):            htf_trend(df, "1D", "down"),
    }
