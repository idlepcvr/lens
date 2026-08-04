"""Self-check for app/strategy_dedup.py — run: python3 test_strategy_dedup.py

Two things here can be wrong without failing loudly:
  · _active() rebuilding the wrong mask (silently dedupes the wrong strategies)
  · the clustering merging or splitting curves it shouldn't
Both are checked against ground truth, not against themselves.
"""

import itertools

import numpy as np

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app.strategy_dedup import _active, _cluster, _correlation, _jaccard, _matrix
from app.strategy_search import SLOTS, combo_params

# --- _active is the exact inverse of combo_params, over the real slot space ---
names = list(SLOTS)
checked = 0
for r in (1, 2, 3):
    for slots in itertools.combinations(names, r):
        for opts in itertools.product(*(SLOTS[n] for n in slots)):
            active = dict(zip(slots, opts))
            back = _active(combo_params("long", active, "4h"))
            assert back == active, f"roundtrip lost {active} → {back}"
            checked += 1
# 1467 → 4847 on 2026-07-25, when the five pattern/HTF slots joined SLOTS.
# 4847 → 6879 on 2026-08-04, when the 'funding' slot joined (app/orderflow.py).
# The roundtrip above passed on every one of them unchanged, which is the part
# that matters: combo_params/_active handle the new slots generically. This
# number is a canary for "the vocabulary moved" — update it deliberately.
assert checked == 6879, f"slot space changed: {checked} combos, expected 6879"

# an rsi_min combo must not come back as rsi_max, and vice versa
assert _active({"rsi_min": 70}) == {"rsi": ("rsi_min", 70)}
assert _active({"rsi_max": 30}) == {"rsi": ("rsi_max", 30)}
# geometry and direction are not slots and must not leak into the mask
assert _active({"direction": "long", "timeframe": "4h",
                "atr_stop_mult": 2.5, "rr": 1.5}) == {}
# vol_spike False is absent, not present-and-false
assert _active({"vol_spike": False}) == {}

# --- _matrix puts each curve on the shared calendar, not its own ---
curves = [(0, {"2026-01-01": 1.0, "2026-01-03": -2.0}, set(), set(), 2),
          (1, {"2026-01-02": 3.0}, set(), set(), 1)]
m, days = _matrix(curves)
assert days == ["2026-01-01", "2026-01-02", "2026-01-03"], days
assert m.tolist() == [[1.0, 0.0, -2.0], [0.0, 3.0, 0.0]], m.tolist()

# --- Jaccard is the real thing being clustered on ---
h = [(f"2026-01-{d:02d}T04", "long") for d in range(1, 21)]
sets = [
    set(h),                    # 0
    set(h),                    # 1 — identical entries
    set(h[:19]) | {("2026-02-01T04", "long")},   # 2 — one condition apart: 19/21
    set(f"2026-06-{d:02d}T04" for d in range(1, 21)) & set(),              # 3 — no trades at all
    {(t, "short") for t, _d in h},   # 4 — same bars, opposite side
]
sets[3] = {(f"2026-06-{d:02d}T04", "long") for d in range(1, 21)}  # disjoint idea
j = _jaccard(sets)
assert j[0, 1] == 1.0, j[0, 1]
assert j[0, 2] > 0.9, f"near-duplicate scored only {j[0,2]}"
assert j[0, 3] == 0.0, "disjoint entries overlapped"
assert j[0, 4] == 0.0, "opposite direction on the same bars counted as the same idea"
assert np.allclose(np.diag(j), 1.0)
assert np.allclose(j, j.T), "Jaccard not symmetric"
assert _jaccard([set(), set()])[0, 1] == 0.0, "two empty sets are not duplicates"

labels = _cluster(j, threshold=0.9)
assert labels[0] == labels[1] == labels[2], f"duplicates split: {labels}"
assert labels[3] != labels[0], f"independent idea absorbed: {labels}"
assert labels[4] != labels[0], f"inverse strategy merged: {labels}"
assert len(set(labels)) == 3, f"expected 3 ideas, got {len(set(labels))}"

# the threshold means what it says: 18/22 = 0.82 overlap is NOT the same idea
loose = [set(h), set(h[:18]) | {("2026-02-01T04", "long"), ("2026-02-02T04", "long")}]
assert abs(_jaccard(loose)[0, 1] - 18 / 22) < 1e-9
assert _cluster(_jaccard(loose), threshold=0.9)[0] != _cluster(_jaccard(loose), threshold=0.9)[1]

# --- correlation is still computed for reporting, and behaves ---
rng = np.random.default_rng(0)
a = rng.normal(size=200)
corr = _correlation(np.vstack([a, a * 2.0, -a, np.zeros(200)]))
assert np.allclose(np.diag(corr), 1.0)
assert corr[0, 1] > 0.99, "scaled copy not correlated"
assert corr[0, 2] < -0.99, "inverse not anti-correlated"
assert corr[0, 3] == 0.0, "dead curve produced a non-zero correlation"

print("ok — params roundtrip exact over "
      f"{checked} combos, shared calendar holds, Jaccard merges duplicates and "
      "keeps disjoint/inverse/empty apart, correlation reports sanely")
