"""Self-check for app/strategy_breeder.py — run: .venv/bin/python test_strategy_breeder.py

The one that matters is the overfit clamp: a genome that wins in-sample and
loses out-of-sample must NOT be able to score well. If that breaks, the GA
still runs, still reports a champion, and the champion is garbage.
"""

import random

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app.strategy_breeder import (GEO_K, GEO_R, MAX_CONDS, _crossover, _fitness,
                                  _key, _mutate, _random_genome, _score)
from app.strategy_search import MIN_N, SLOTS


def trades(pnls, capital=1000.0):
    out, eq = [], capital
    for i, p in enumerate(pnls):
        eq *= 1 + p / 100
        out.append({"pnl_pct": p, "equity": eq,
                    "entry_ts": f"2026-01-{i%28+1:02d}T00:00:00"})
    return out


# --- score: drawdown-penalised, and the penalty actually bites ---
assert _score([]) is None
flat = _score(trades([1.0] * 50))
holed = _score(trades([1.0] * 25 + [-20.0] + [1.0] * 25))
assert holed["score"] < flat["score"], "a 20% hole scored no worse than none"
assert holed["exp_r"] < flat["exp_r"]
# same expectancy, worse path ⇒ worse score. This is the whole reason PF lost.
a = _score(trades([2.0, 2.0, 2.0, 2.0]))
b = _score(trades([12.0, -6.0, 2.0, 0.0]))
assert abs(a["exp_r"] - b["exp_r"]) < 0.01, "fixture drifted: expectancies differ"
assert b["dd_r"] > 1.0, f"fixture sits on the 1R floor: {b}"
assert a["score"] > b["score"], "path-dependence not penalised"
# the 1R denominator floor stops a tiny-drawdown genome scoring on noise
tiny = _score(trades([0.01] * 50))
assert tiny["dd_r"] < 1.0 and tiny["score"] == tiny["exp_r"], tiny

# --- the overfit clamp: min(train, holdout), not the average, not train ---
class FakeCtx(dict):
    pass


def fake_ctx(train_pnls, hold_pnls):
    """A ctx whose backtest returns a known trade list, so the clamp is tested
    without a market."""
    import app.strategy_breeder as sb
    tr = [{"pnl_pct": p, "equity": 1000.0 + i, "entry_ts": f"2026-01-01T{i:02d}"}
          for i, p in enumerate(train_pnls)]
    hd = [{"pnl_pct": p, "equity": 1000.0 + i, "entry_ts": f"2026-06-01T{i:02d}"}
          for i, p in enumerate(hold_pnls)]
    sb._run_backtest = lambda *a, **k: {"trades": tr + hd, "final_equity": 1000.0}
    import numpy as np
    n = 500
    return {"df": None, "masks": None, "nb": n,
            "mid": "2026-03-01T00:00:00"}, np.ones(n, dtype=bool)


import app.strategy_breeder as sb
import numpy as np

real_backtest, real_mask = sb._run_backtest, sb._combo_mask
sb._combo_mask = lambda masks, nb, conds: np.ones(nb, dtype=bool)
sb._sig_fn = lambda mask, direction: None

g = {"direction": "long", "conds": {"trend": "up"}, "k": 1.5, "rr": 3.0}

# wins in-sample, loses out-of-sample — the curve-fit champion
ctx, _ = fake_ctx([3.0] * 60, [-3.0] * 60)
ev = _fitness(g, ctx)
assert ev["train"]["score"] > 0 > ev["fitness"], \
    f"curve-fit genome scored {ev['fitness']} — the clamp is not clamping"
assert ev["fitness"] == ev["holdout"]["score"], "fitness took train, not min"

# honest genome: works in both halves
ctx, _ = fake_ctx([2.0] * 60, [2.0] * 60)
good = _fitness(g, ctx)
assert good["fitness"] > 0, good
assert good["fitness"] <= good["train"]["score"], "min() returned above a half"

# thin holdout is disqualified outright, however good it looks
ctx, _ = fake_ctx([3.0] * 60, [9.0] * (MIN_N - 1))
thin = _fitness(g, ctx)
assert thin["fitness"] < -8e8, f"a {MIN_N-1}-trade holdout survived: {thin}"

sb._run_backtest, sb._combo_mask = real_backtest, real_mask

# --- genome ops stay inside the rules ---
rng = random.Random(7)
for tf in ("1h", "4h", "1d"):
    for _ in range(400):
        x, y = _random_genome(rng, tf), _random_genome(rng, tf)
        for g2 in (x, y, _crossover(x, y, rng), _mutate(x, rng, tf)):
            assert 1 <= len(g2["conds"]) <= MAX_CONDS, g2
            assert g2["k"] in GEO_K and g2["rr"] in GEO_R, g2
            assert g2["direction"] in ("long", "short")
            for slot, opt in g2["conds"].items():
                assert opt in SLOTS[slot], (slot, opt)
                # 1d has no session filter — a daily bar is one hour stamp
                assert not (tf == "1d" and slot == "hours"), "hours bred on 1d"

# identity: same strategy ⇒ same cache key regardless of dict order
g1 = {"direction": "long", "conds": {"trend": "up", "macd": "bull"}, "k": 1.5, "rr": 3.0}
g2 = {"direction": "long", "conds": {"macd": "bull", "trend": "up"}, "k": 1.5, "rr": 3.0}
assert _key(g1) == _key(g2), "cache would re-evaluate the same genome"
assert _key(g1) != _key({**g1, "rr": 5.0}), "geometry dropped from identity"

print("ok — drawdown penalty bites, the out-of-sample clamp kills curve-fits "
      "and thin holdouts, genome ops respect MAX_CONDS/grids/1d, cache key "
      "is order-free and geometry-aware")
