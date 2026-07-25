"""Pattern + HTF features must be causal, or the backtest is a fantasy.

The failure this locks down is not a crash. A lookahead bug in a feature makes
every backtest that uses it look excellent and lose money live — the most
expensive class of bug this repo can have, and the least visible.

The test is a truncation check, which is the only honest way to ask the
question: compute a feature over the full series, then recompute it over the
series CUT OFF at bar i. If the value at bar i disagrees, the full-series
version used a bar that had not happened yet. No amount of reading the code
proves this; re-running it on a shorter series does.

Also covers the shape claims: a double top needs two comparable highs, a
breakout must exceed the PRIOR window and not its own bar.

Run: python3 tests/test_patterns.py
"""
import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd

import numpy as np
import pandas as pd

from app import patterns as P

# A deterministic series with real swings — a trending sine plus noise, so
# pivots, double tops and breakouts all actually occur.
rng = np.random.default_rng(7)
N = 3000  # 125 days — the 1d HTF feature needs >50 daily bars to warm up
idx = pd.date_range("2026-01-01", periods=N, freq="1h", tz="UTC")
base = 65000 + np.cumsum(rng.normal(0, 40, N)) + 900 * np.sin(np.arange(N) / 25)
high = base + rng.uniform(20, 90, N)
low = base - rng.uniform(20, 90, N)
close = base + rng.uniform(-30, 30, N)
DF = pd.DataFrame({"open": base, "high": high, "low": low,
                   "close": close, "volume": rng.uniform(1, 9, N)}, index=idx)

FEATURES = {
    "double_top":    lambda d: P.double_top(d),
    "double_bottom": lambda d: P.double_bottom(d),
    "structure_up":  lambda d: P.structure(d, "up"),
    "structure_dn":  lambda d: P.structure(d, "down"),
    "breakout_up":   lambda d: P.breakout(d, "up"),
    "breakout_dn":   lambda d: P.breakout(d, "down"),
    "htf4h_up":      lambda d: P.htf_trend(d, "4h", "up"),
    "htf1d_up":      lambda d: P.htf_trend(d, "1D", "up"),
}

# ── the lookahead check ───────────────────────────────────────────────────
# Full-series value at bar i must equal the value computed knowing only bars
# ≤ i. Probe late bars so every feature is past its warm-up.
PROBES = [1500, 1873, 2204, 2661, 2999]

for name, fn in FEATURES.items():
    full = fn(DF)
    for i in PROBES:
        truncated = fn(DF.iloc[:i + 1])
        assert full[i] == truncated[i], (
            f"LOOKAHEAD in {name} at bar {i}: full series says {full[i]}, "
            f"but knowing only bars 0..{i} says {truncated[i]} — this feature "
            f"reads the future and any backtest using it is invalid")

# a feature that is never true would pass the check above vacuously
for name, fn in FEATURES.items():
    fired = fn(DF).sum()
    assert fired > 0, f"{name} never fires on the fixture — dead feature, not a passing test"

# ── shape checks ──────────────────────────────────────────────────────────
# breakout compares against PRIOR bars only: a bar that sets a new high but
# does not close above the previous 20 highs is not a breakout.
flat = DF.copy()
flat["high"] = 100.0
flat["low"] = 90.0
flat["close"] = 95.0
assert not P.breakout(flat, "up").any(), "flat series cannot break out"
assert not P.breakout(flat, "down").any(), "flat series cannot break down"

spike = flat.copy()
spike.iloc[1500, spike.columns.get_loc("close")] = 150.0
assert P.breakout(spike, "up")[1500], "a close above the prior 20-bar high is a breakout"
assert not P.breakout(spike, "up")[1499], "the breakout must not appear before its bar"

# double bottom fires as an EVENT: on confirmation of the second equal low,
# and then goes quiet. A version that stays true for the next 60 bars is the
# bug this replaced — it fired on 51% of real bars and meant nothing.
#
# A pure sine gives troughs of identical depth, evenly spaced — the textbook
# double bottom, repeated. (A FLAT series cannot test this: every bar ties the
# rolling min, so every bar is a pivot and the min_gap rule correctly kills it.)
PERIOD = 40
wave = 100 + 5 * np.sin(np.arange(N) / (PERIOD / (2 * np.pi)))
sine = pd.DataFrame({"open": wave, "high": wave + 0.5, "low": wave - 0.5,
                     "close": wave, "volume": np.ones(N)}, index=idx)
db = P.double_bottom(sine)
assert db.any(), "equal, well-separated swing lows must fire a double bottom"

# it must be an event: far fewer firings than bars, not a standing regime
assert db.mean() < 0.35, \
    f"double bottom fires on {db.mean():.0%} of bars — that is weather, not a signal"

# and it must fire only AFTER a trough is confirmed, never on the trough itself
first = int(np.argmax(db))
trough = int(np.argmin(wave[:first + 1]))
assert first > trough, "double bottom fired at or before the low that produced it"

# two pivots only a few bars apart are one jagged low, not two tests of a level
fast_wave = 100 + 5 * np.sin(np.arange(N) / (6 / (2 * np.pi)))   # period 6 < min_gap
fast = pd.DataFrame({"open": fast_wave, "high": fast_wave + 0.5,
                     "low": fast_wave - 0.5, "close": fast_wave,
                     "volume": np.ones(N)}, index=idx)
assert not P.double_bottom(fast).any(), \
    f"lows 6 bars apart are chop, not a double bottom (min_gap={P.DT_MIN_GAP})"

# structure up and down are mutually exclusive
up, dn = P.structure(DF, "up"), P.structure(DF, "down")
assert not (up & dn).any(), "a bar cannot be both higher-high and lower-low structure"

# htf 'down' must mean a real down-verdict, not warm-up emptiness
u, d = P.htf_trend(DF, "4h", "up"), P.htf_trend(DF, "4h", "down")
assert not (u & d).any(), "htf up and down must be exclusive"

print(f"ok — {len(FEATURES)} features causal at {len(PROBES)} probes, all fire, shapes hold")
