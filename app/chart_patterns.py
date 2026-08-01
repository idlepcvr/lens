"""Wedges, triangles and pennants — the shapes his TradingView indicator draws.

`patterns.py` has double tops, breakouts, structure and HTF trend. It does not
have the converging-trendline family, which is what he actually reads off a
chart, so "patterns don't work" was never a claim the codebase could support.
This adds them so it can be tested rather than asserted.

═══ WHAT A PATTERN IS HERE ═══

Two trendlines, each drawn through the last three confirmed pivots — upper
through pivot highs, lower through pivot lows — exactly the way you draw them by
hand. The pair is classified by the two slopes and whether the gap between them
is closing:

    rising wedge        both up, converging, lower rising faster    → short
    falling wedge       both down, converging, upper falling faster → long
    symmetric triangle  upper down, lower up                        → either way
    ascending triangle  upper flat, lower up                        → long
    descending triangle upper down, lower flat                      → short
    bull pennant        symmetric triangle after a sharp rally      → long
    bear pennant        symmetric triangle after a sharp selloff    → short

═══ THE ENTRY IS THE BREAK, NOT THE SHAPE ═══

The signal fires on the bar that CLOSES beyond the line, not when the shape
becomes visible. That matters for two reasons. A shape is a state and would fire
on every bar it persists, which is weather, not a signal. And the break is the
only moment the pattern makes a falsifiable claim about what happens next.

═══ CAUSALITY ═══

The whole correctness burden, because a lookahead bug here does not crash, it
prints a beautiful backtest and loses real money.

  · Pivots come from `patterns._pivots`, already shifted by their confirmation
    lag. A pivot high at bar i is not usable until bar i+right.
  · Trendlines are fitted ONLY through pivots confirmed at or before the current
    bar, and extrapolated forward. The line never moves once drawn.
  · The break is tested on the current bar's close against the line's value at
    the current bar — no future bars consulted.

This is precisely where his indicator differs: it redraws a wedge once the bars
that complete it have printed, so the shape on screen at 19:54 was not on screen
at 15:00. `tests/test_chart_patterns.py` asserts the shift here directly.
"""
from __future__ import annotations

import numpy as np

from .patterns import _pivots

LOOKBACK = 60          # bars a trendline may reach back over
MIN_PIVOTS = 3         # three touches; two points is a line, not a trendline
FLAT_PCT = 0.15        # |slope| over the span, as % of price, that counts as flat
CONVERGE = 0.75        # closing gap must reach this fraction of the opening gap
POLE_BARS = 20         # window the pennant's flagpole must have moved in
POLE_PCT = 2.0         # how far it must have moved to count as a pole


def _line(idx, vals):
    """Least-squares slope/intercept through confirmed pivots. Returns price
    per bar and the value at bar 0, so the line can be evaluated anywhere."""
    n = len(idx)
    mx = sum(idx) / n
    my = sum(vals) / n
    den = sum((x - mx) ** 2 for x in idx)
    if den == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(idx, vals)) / den
    return slope, my - slope * mx


def _recent(flags, values, i, lookback, k):
    """The k newest confirmed pivots at or before bar i, oldest first."""
    lo = max(0, i - lookback + 1)
    hit = np.flatnonzero(flags[lo:i + 1])
    if len(hit) < k:
        return None
    sel = hit[-k:] + lo
    return list(sel), [values[j] for j in sel]


def classify(df, lookback=LOOKBACK):
    """Per bar: which converging-trendline pattern is live, and its two lines.

    Returns a list of (name, upper_slope, upper_at_i, lower_slope, lower_at_i)
    or None. Everything is computed from pivots already confirmed at bar i."""
    ph, pl = _pivots(df)
    high, low, close = (df[c].to_numpy() for c in ("high", "low", "close"))
    n = len(df)
    out = [None] * n

    for i in range(n):
        hp = _recent(ph, high, i, lookback, MIN_PIVOTS)
        lp = _recent(pl, low, i, lookback, MIN_PIVOTS)
        if not hp or not lp:
            continue
        hs, hb = _line(hp[0], hp[1])
        ls, lb = _line(lp[0], lp[1])

        span = max(hp[0][-1], lp[0][-1]) - min(hp[0][0], lp[0][0])
        if span <= 0:
            continue
        px = close[i]
        # slope expressed as % of price over the pattern's own span
        h_move = hs * span / px * 100
        l_move = ls * span / px * 100
        h_flat, l_flat = abs(h_move) < FLAT_PCT, abs(l_move) < FLAT_PCT

        start = min(hp[0][0], lp[0][0])
        gap_open = (hs * start + hb) - (ls * start + lb)
        gap_now = (hs * i + hb) - (ls * i + lb)
        if gap_open <= 0 or gap_now <= 0:
            continue                                   # lines already crossed
        converging = gap_now < gap_open * CONVERGE

        name = None
        if converging and h_move > FLAT_PCT and l_move > FLAT_PCT:
            name = "rising_wedge"
        elif converging and h_move < -FLAT_PCT and l_move < -FLAT_PCT:
            name = "falling_wedge"
        elif h_flat and l_move > FLAT_PCT:
            name = "ascending_triangle"
        elif l_flat and h_move < -FLAT_PCT:
            name = "descending_triangle"
        elif h_move < -FLAT_PCT and l_move > FLAT_PCT:
            # A symmetric triangle; a sharp move INTO it makes it a pennant. The
            # pole is measured over the bars before the pattern's first pivot —
            # measuring the last POLE_BARS instead would sample the consolidation
            # itself, which by construction has gone nowhere.
            j = max(0, start - POLE_BARS)
            pole = (close[start] - close[j]) / close[j] * 100
            if pole >= POLE_PCT:
                name = "bull_pennant"
            elif pole <= -POLE_PCT:
                name = "bear_pennant"
            else:
                name = "symmetric_triangle"
        if name:
            out[i] = (name, hs * i + hb, ls * i + lb)
    return out


# Which way each shape claims price will go, and therefore which line's break
# counts as the entry. Symmetric triangles claim nothing, so both breaks trade.
BIAS = {
    "rising_wedge": "short", "falling_wedge": "long",
    "ascending_triangle": "long", "descending_triangle": "short",
    "bull_pennant": "long", "bear_pennant": "short",
    "symmetric_triangle": "both",
}


def breaks(df, lookback=LOOKBACK):
    """(name, direction) -> bool array. True on the bar that closes through the
    line, and only if the shape was already live on the PREVIOUS bar."""
    live = classify(df, lookback)
    close = df["close"].to_numpy()
    n = len(df)
    names = list(BIAS)
    out = {(nm, d): np.zeros(n, dtype=bool) for nm in names for d in ("long", "short")}

    for i in range(1, n):
        prev = live[i - 1]
        if prev is None:
            continue
        name, upper, lower = prev
        broke_up = close[i] > upper
        broke_dn = close[i] < lower
        bias = BIAS[name]
        if broke_up and bias in ("long", "both"):
            out[(name, "long")][i] = True
        if broke_dn and bias in ("short", "both"):
            out[(name, "short")][i] = True
    return out


def pattern_masks(df, lookback=LOOKBACK):
    """Same contract as patterns.pattern_masks, so it drops into the same sims."""
    return {("chart", f"{nm}_{d}"): m for (nm, d), m in breaks(df, lookback).items()
            if m.any()}
