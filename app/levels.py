"""Resistance-becomes-support (and the mirror) — swing-point + flip detection.

Pure functions over plain arrays (no DB), same shape as trade_review.py's
math helpers, so a future research/level_miner.py can import this exactly
the way edge_miner.py imports from trade_review — this is detection only,
not yet tested for edge. It draws on the chart; it does not claim to work.

Two-step definition:
  1. A SWING HIGH/LOW is a fractal pivot — the highest high (or lowest low)
     in a symmetric window of `k` bars either side.
  2. A level FLIPS when price later closes decisively through it (a break),
     then comes back to re-test it from the other side and holds — resistance
     that gets closed above, then defended as support on the retest, or the
     mirror on the way down.
"""
from __future__ import annotations


def swing_points(highs: list, lows: list, k: int = 5) -> tuple[list, list]:
    """Bar i is a swing high if highs[i] is the STRICT max of the window
    [i-k, i+k] (ties excluded — a flat top isn't a pivot). Symmetric for lows."""
    n = len(highs)
    swing_high = [False] * n
    swing_low = [False] * n
    for i in range(k, n - k):
        window_h = highs[i - k:i + k + 1]
        if highs[i] == max(window_h) and window_h.count(highs[i]) == 1:
            swing_high[i] = True
        window_l = lows[i - k:i + k + 1]
        if lows[i] == min(window_l) and window_l.count(lows[i]) == 1:
            swing_low[i] = True
    return swing_high, swing_low


def level_flips(highs: list, lows: list, closes: list, k: int = 5,
                tol_pct: float = 0.4, break_pct: float = 0.2,
                confirm_bars: int = 5, max_lookahead: int = 500) -> list[dict]:
    """Every confirmed flip, as {level, kind, pivot_i, break_i, retest_i, confirm_i}.

    kind='r2s' (resistance→support): a swing HIGH gets closed above by more
    than break_pct, price later comes back down within tol_pct of the level,
    and within confirm_bars closes back above level*(1-tol_pct) — held, not
    round-tripped straight through. kind='s2r' is the exact mirror on a
    swing LOW broken to the downside.

    A level is used at most once per direction — the first flip found, not
    every subsequent retest — so a well-worn level doesn't flood the output.
    """
    n = len(closes)
    sh, sl = swing_points(highs, lows, k)
    out = []
    used_high = set()
    used_low = set()

    for i in range(n):
        if sh[i] and i not in used_high:
            level = highs[i]
            break_i = None
            for j in range(i + 1, min(n, i + 1 + max_lookahead)):
                if closes[j] >= level * (1 + break_pct / 100):
                    break_i = j
                    break
            if break_i is None:
                continue
            retest_i = None
            for j in range(break_i + 1, min(n, break_i + 1 + max_lookahead)):
                if lows[j] <= level * (1 + tol_pct / 100):
                    retest_i = j
                    break
            if retest_i is None:
                continue
            confirm_i = None
            for j in range(retest_i, min(n, retest_i + confirm_bars)):
                if closes[j] >= level * (1 - tol_pct / 100):
                    confirm_i = j
                    break
                if closes[j] < level * (1 - break_pct / 100):
                    break   # round-tripped straight through — not a flip
            if confirm_i is not None:
                out.append({"level": level, "kind": "r2s", "pivot_i": i,
                           "break_i": break_i, "retest_i": retest_i, "confirm_i": confirm_i})
                used_high.add(i)

        if sl[i] and i not in used_low:
            level = lows[i]
            break_i = None
            for j in range(i + 1, min(n, i + 1 + max_lookahead)):
                if closes[j] <= level * (1 - break_pct / 100):
                    break_i = j
                    break
            if break_i is None:
                continue
            retest_i = None
            for j in range(break_i + 1, min(n, break_i + 1 + max_lookahead)):
                if highs[j] >= level * (1 - tol_pct / 100):
                    retest_i = j
                    break
            if retest_i is None:
                continue
            confirm_i = None
            for j in range(retest_i, min(n, retest_i + confirm_bars)):
                if closes[j] <= level * (1 + tol_pct / 100):
                    confirm_i = j
                    break
                if closes[j] > level * (1 + break_pct / 100):
                    break
            if confirm_i is not None:
                out.append({"level": level, "kind": "s2r", "pivot_i": i,
                           "break_i": break_i, "retest_i": retest_i, "confirm_i": confirm_i})
                used_low.add(i)

    return out
