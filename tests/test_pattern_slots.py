"""The search's mask path and the live replay path must agree, bar for bar.

Two different pieces of code decide whether a pattern condition holds:

  · `strategy_search._masks()` builds whole-array masks — this is what the grid
    search and the breeder score strategies with.
  · `backtest_engine._signal_custom()` checks one row at a time — this is what
    actually replays a found strategy, and what a live signal runs through.

If they disagree, the search reports edges that cannot be reproduced, which is
worse than finding nothing: it manufactures confident false findings. The new
pattern/HTF slots are the first conditions to live in BOTH paths, so this is
the seam worth pinning.

Also asserts the slots reached the shared vocabulary at all — a silent import
failure would just quietly return the search to its old ten-slot world.

Needs the project venv (backtest_engine imports ccxt):
  .venv/bin/python3 tests/test_pattern_slots.py
"""
import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd

import numpy as np
import pandas as pd

from app.backtest_engine import add_indicators, _signal_custom
from app.patterns import PATTERN_SLOTS
from app.strategy_search import SLOTS, _masks, _combo_mask, combo_params

# ── the vocabulary actually grew ──────────────────────────────────────────
for slot in PATTERN_SLOTS:
    assert slot in SLOTS, f"{slot} never reached strategy_search.SLOTS"
assert len(SLOTS) == 15, f"expected 15 slots, got {len(SLOTS)}"

# ── a synthetic series with genuine structure (no network) ────────────────
rng = np.random.default_rng(11)
N = 2500
idx = pd.date_range("2025-01-01", periods=N, freq="1h", tz="UTC")
base = 60000 + np.cumsum(rng.normal(0, 60, N)) + 1200 * np.sin(np.arange(N) / 30)
df = pd.DataFrame({"open": base + rng.normal(0, 10, N),
                   "high": base + rng.uniform(30, 120, N),
                   "low":  base - rng.uniform(30, 120, N),
                   "close": base + rng.normal(0, 25, N),
                   "volume": rng.uniform(1, 10, N)}, index=idx)
df = add_indicators(df)

for slot in PATTERN_SLOTS:
    for opt in PATTERN_SLOTS[slot]:
        assert f"pat_{slot}_{opt}" in df.columns, \
            f"add_indicators did not emit pat_{slot}_{opt} — replay would be impossible"

# ── mask path vs replay path ──────────────────────────────────────────────
masks = _masks(df)
nb = len(df)

CASES = [
    {"pattern": "double_bottom"},
    {"pattern": "double_top"},
    {"structure": "up"},
    {"breakout": "up"},
    {"htf4h": "up"},
    {"htf1d": "down"},
    {"structure": "up", "htf4h": "up"},          # regime + regime
    {"breakout": "up", "htf4h": "up"},           # event + regime, the real shape
    {"pattern": "double_bottom", "trend": "up"}, # new slot AND'd with an old one
]

for active in CASES:
    mask = _combo_mask(masks, nb, active)
    params = combo_params("long", active, "1h")
    replay = np.zeros(nb, dtype=bool)
    for i in range(60, nb):                      # _signal_custom warm-up is 60
        replay[i] = _signal_custom(df, i, params) is not None

    m = mask.copy()
    m[:60] = False
    disagree = np.flatnonzero(m != replay)
    assert len(disagree) == 0, (
        f"{active}: mask and replay disagree on {len(disagree)} bars "
        f"(first at {disagree[:5].tolist()}) — the search would report an edge "
        f"that _signal_custom cannot reproduce")

    assert mask[60:].sum() > 0, f"{active} never fires — case proves nothing"

# ── an unset pattern condition must not gate anything ─────────────────────
plain = combo_params("long", {"trend": "up"}, "1h")
assert "pattern" not in plain, "combo_params leaked an unset slot"
fires = sum(_signal_custom(df, i, plain) is not None for i in range(60, nb))
assert fires > 0, "a plain trend strategy stopped firing — pattern gate is too eager"

print(f"ok — {len(SLOTS)} slots; mask and replay agree on {len(CASES)} pattern combos "
      f"across {nb} bars")
