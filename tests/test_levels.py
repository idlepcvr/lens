"""Resistance-becomes-support detection (app/levels.py) — checked against
hand-constructed price paths where the answer is known, not just 'runs
without crashing'. This is pattern-detection, not indicator math; it's
easy to write something that finds a 'flip' in noise.
"""
import _bootstrap  # noqa: F401
from app.levels import level_flips, swing_points


def _rally_break_retest_hold():
    """A clean pivot high at 115, later broken above, retested from above,
    and held — the textbook resistance-becomes-support shape."""
    closes, highs, lows = [], [], []

    def bar(c, w):
        closes.append(c); highs.append(c + w); lows.append(c - w)

    for i in range(10): bar(100 + (i % 2), 0.5)          # base chop
    for c in [102, 105, 108, 111, 114]: bar(c, 1)         # rally to the pivot
    highs[-1] = 115                                       # the pivot high itself
    for c in [111, 108, 105, 102, 100]: bar(c, 0.5)       # pull back
    for i in range(5): bar(100 + (i % 2), 0.5)            # chop either side of pivot
    for c in [103, 107, 111, 114, 116, 117]: bar(c, 0.5)  # rally through 115 (break)
    for c in [115.2, 114.9, 115.1, 116]: bar(c, 0.3)      # retest from above, holds
    for i in range(10): bar(116 + (i % 2), 0.5)           # tail padding
    return highs, lows, closes


def test_swing_points_find_the_constructed_pivot():
    highs, lows, closes = _rally_break_retest_hold()
    sh, sl = swing_points(highs, lows, k=5)
    assert sh[14] is True and highs[14] == 115
    assert not any(sl[10:20])   # no swing low hiding in the rally/pullback


def test_r2s_flip_confirmed_on_the_constructed_hold():
    highs, lows, closes = _rally_break_retest_hold()
    flips = level_flips(highs, lows, closes, k=5, tol_pct=0.4, break_pct=0.2, confirm_bars=5)
    r2s = [f for f in flips if f["kind"] == "r2s"]
    assert len(r2s) == 1, flips
    f = r2s[0]
    assert f["level"] == 115 and f["pivot_i"] == 14
    assert f["break_i"] > f["pivot_i"] and f["retest_i"] > f["break_i"]


def test_round_trip_straight_through_is_not_a_flip():
    """Same pivot and break, but price crashes straight through the level
    on the way back down instead of holding — must NOT be reported."""
    highs, lows, closes = _rally_break_retest_hold()
    # replace the hold-on-retest tail with a straight crash through the level
    crash_start = 31
    del closes[crash_start:], highs[crash_start:], lows[crash_start:]
    for c in [110, 105, 100, 95, 90]:
        closes.append(c); highs.append(c + 0.5); lows.append(c - 0.5)
    flips = level_flips(highs, lows, closes, k=5, tol_pct=0.4, break_pct=0.2, confirm_bars=5)
    assert not any(f["kind"] == "r2s" and f["level"] == 115 for f in flips), flips


if __name__ == "__main__":
    test_swing_points_find_the_constructed_pivot()
    test_r2s_flip_confirmed_on_the_constructed_hold()
    test_round_trip_straight_through_is_not_a_flip()
    print("test_levels OK")
