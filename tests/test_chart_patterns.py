"""Wedges, triangles and pennants must be causal, and must be the shape claimed.

The whole reason to build these in-repo rather than read them off a chart is
that a drawn pattern repaints — the wedge visible at 19:54 was not visible at
15:00, because the bars that complete it had not printed. A repainting feature
backtests beautifully and loses money live.

So the same truncation check the rest of the pattern suite uses: compute the
signal over the full series, recompute it over the series CUT OFF at bar i, and
demand agreement at bar i. Reading the code cannot prove this; re-running it on
a shorter series can.

Plus the shape claims, on hand-built series where the answer is known: lines
that spread apart are not a wedge, a break is the bar that closes through the
line rather than the bar the shape appears, and a pennant needs its flagpole.

Run: python3 tests/test_chart_patterns.py
"""
import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd

import numpy as np
import pandas as pd

from app import chart_patterns as C


def frame(close, wick=0.0005):
    idx = pd.date_range("2026-01-01", periods=len(close), freq="1h", tz="UTC")
    c = np.asarray(close, dtype=float)
    return pd.DataFrame({"open": c, "high": c * (1 + wick), "low": c * (1 - wick),
                         "close": c, "volume": np.ones(len(c))}, index=idx)


# A converging series. The swing period must be short enough that three pivots
# fit inside the lookback — at sin(i/3.5) the period is ~22 bars, which clears
# the 7-bar pivot window and still puts 3 highs well inside 60 bars.
rng = np.random.default_rng(11)
N = 2500
amp = np.linspace(1400, 90, N)                 # amplitude decays → convergence
wave = 65000 + amp * np.sin(np.arange(N) / 3.5) + np.cumsum(rng.normal(0, 5, N))
DF = frame(wave)

MASKS = C.pattern_masks(DF)
assert MASKS, "no chart pattern fired on a converging series — detector is dead"
fired = {k[1]: int(v.sum()) for k, v in MASKS.items()}

# ── 1. CAUSALITY: truncating the series must not change the past ──
PROBES = [400, 700, 1100, 1500, 1900, 2300]
for key, full in MASKS.items():
    for i in PROBES:
        cut = C.pattern_masks(DF.iloc[:i + 1]).get(key)
        got = bool(cut[i]) if cut is not None and len(cut) > i else False
        assert bool(full[i]) == got, (
            f"{key} at bar {i}: full series says {bool(full[i])}, series truncated "
            f"at {i} says {got} — the feature used a bar that had not happened")

# ── 2. A break requires a shape that was already live on the previous bar ──
live = C.classify(DF)
for key, m in MASKS.items():
    for i in np.flatnonzero(m):
        assert live[i - 1] is not None, \
            f"{key} fired at bar {i} with no pattern live at {i-1} — break without a shape"

# ── 3. Lines that spread apart are not a wedge ──
grow = 65000 + np.linspace(90, 1400, N) * np.sin(np.arange(N) / 3.5)
named = {p[0] for p in C.classify(frame(grow)) if p}
assert not (named & {"rising_wedge", "falling_wedge"}), \
    f"diverging trendlines classified as a wedge: {named}"

# ── 4. A directional shape must not produce a mask for the opposite side ──
for nm, bias in C.BIAS.items():
    if bias == "both":
        continue
    other = "short" if bias == "long" else "long"
    assert ("chart", f"{nm}_{other}") not in MASKS, \
        f"{nm} claims {bias} but a {other} mask exists"

# ── 5. A pennant needs its flagpole ──
# Same converging triangle, once with a preceding +6% pole and once flat. It has
# to converge hard: over the ~57 bars three pivots span, a gently decaying
# amplitude moves each trendline less than FLAT_PCT and reads as a rectangle.
tri = np.linspace(1500, 30, 200) * np.sin(np.arange(200) / 3.5)
poled = np.concatenate([np.full(80, 60000.0), np.linspace(60000, 63600, 20), 63600 + tri])
flatd = np.concatenate([np.full(100, 63600.0), 63600 + tri])

assert "bull_pennant" in {p[0] for p in C.classify(frame(poled)) if p}, \
    "a +6% pole into a converging triangle is a bull pennant"
assert "bull_pennant" not in {p[0] for p in C.classify(frame(flatd)) if p}, \
    "a converging triangle with no prior move is not a pennant"

print(f"ok — {len(MASKS)} chart-pattern signals causal at {len(PROBES)} probes; "
      f"fired {fired}")
