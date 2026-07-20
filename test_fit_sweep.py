"""Self-check for /edge #fit — the goal-constrained parameter sweep.

Asserts the two-gate feasibility (edge CLOSES the goal in time AND risk is SANE),
the joint-optimum / nearest-miss layering, the envelope bounds, and that
model-error cells don't kill the run. Pure math, offline (no candles, no HTTP).
Run: python3 test_fit_sweep.py
"""
import datetime as _dt

from app.fit_sweep import evaluate, build_axes, total_cells, start, CELL_CAP

# Horizons are relative: the sweep gates on weeks-REMAINING, so a hardcoded date
# silently becomes "0 weeks left" once it passes and every cell CalcErrors out.
def _in(days: int) -> str:
    return (_dt.date.today() + _dt.timedelta(days=days)).isoformat()


# TIGHT is deliberately ≤7d: annualising a 10^9× target over a longer window stops
# overflowing, and case 5 below needs EVERY cell to blow up.
TIGHT, NEAR, FAR = _in(3), _in(14), _in(345)

# A coarse grid keeps the test fast — the axis-resolution logic is the same.
COARSE = {"lev_min": 1, "lev_max": 10, "lev_step": 3,
          "freq_min": 1, "freq_max": 7, "freq_step": 3,
          "wr_min": 0.3, "wr_max": 0.7, "wr_step": 0.1,
          "rr_min": 1, "rr_max": 5, "rr_step": 1,
          "atr_min": 0, "atr_max": 0.02, "atr_step": 0.01}


def _req(**over):
    base = dict(COARSE, start_balance=1000, max_drawdown_allowed=0.5,
                losses_allowed=20, fractional_kelly=1 / 6, execution_fill_factor=1.0,
                slippage_pct=0.0005)
    base.update(over)
    return base


# ── 1. feasible goal: modest target, long date → a feasible optimum exists ──
r = evaluate(_req(target_balance=2000, target_date=FAR))
o = r["optimum"]
assert r["feasible_count"] > 0, "modest goal should have feasible cells"
assert o["feasible"] and o["closes"], o
assert o["used"] <= o["opt"], ("feasible optimum must be within Kelly", o)
assert o["ror"] <= 1.0, o
assert o["weeks_to_goal"] is not None and o["weeks_to_goal"] <= r["weeks_remaining"], o

# ── 2. the feasibility gate really gates SUFFICIENCY, not just risk ──────────
# Every feasible cell must actually reach the target in time (the /goal blind
# spot this page fixes): a risk-sane cell whose edge is too weak is NOT feasible.
for name, plane in r["planes"].items():
    for c in plane["cells"]:
        if c["feasible"]:
            assert c["closes"] and c["weeks_to_goal"] <= r["weeks_remaining"], (name, c)

# ── 3. envelope bounds contain the optimum ──────────────────────────────────
env = r["envelope"]
assert env, "feasible set → non-empty envelope"
for k in ("lev", "freq", "wr", "rr", "atr"):
    assert env[k]["min"] <= o[k] <= env[k]["max"], (k, env[k], o[k])

# ── 3b. measured strategy is None (no trades) or a well-shaped dict ──────────
m = r["measured"]
assert m is None or (
    m["n"] >= 1
    and (m["wr"] is None or 0 <= m["wr"] <= 1)
    and set(("wr", "rr", "freq", "risk_pct", "kelly_cap_pct", "kelly_util")) <= set(m)
), m

# ── 4. impossible goal: 1000× in two weeks → no feasible, nearest miss shown ─
imp = evaluate(_req(target_balance=1_000_000, target_date=NEAR))
assert imp["feasible_count"] == 0, "1000× in two weeks can't be feasible"
assert imp["optimum"] is not None, "nearest miss must still be surfaced"
assert not imp["optimum"]["feasible"], imp["optimum"]
assert imp["envelope"] == {}, "no feasible set → empty envelope"
# cells still evaluate here → the nearest miss is a real cell, not a blank
assert imp["evaluated"] > 0, imp

# ── 5. numerical blow-ups are skipped, not fatal (absurd target overflows the
#      model's annual-rate term for every cell → 0 evaluated, but no crash) ──
blow = evaluate(_req(target_balance=10**12, target_date=TIGHT))
assert blow["evaluated"] == 0 and blow["optimum"] is None, blow

# ── 6. axis resolution + cap math ───────────────────────────────────────────
ax = build_axes(COARSE)
assert ax["wr"] == [0.3, 0.4, 0.5, 0.6, 0.7], ax["wr"]
assert ax["atr"] == [0.0, 0.01, 0.02], ax["atr"]
big = start({"start_balance": 1000, "target_balance": 2000, "target_date": FAR,
             "lev_step": 0.01, "freq_step": 0.01})   # ~absurd resolution → over cap
assert "error" in big and "too large" in big["error"], big

print(f"ok — fit sweep: feasibility gates sufficiency+risk, envelope contains "
      f"optimum, nearest-miss on impossible goals, cap holds ({CELL_CAP:,})")
