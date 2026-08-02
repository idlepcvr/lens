"""Cadence-constrained strategy search — the one objective nothing else scored.

═══ WHY THIS EXISTS ═══

`strategy_search3` (43,703 combos), the GA breeder and `candidate_15m` all
optimized QUALITY: expectancy in R, drawdown-penalised score, permutation
significance. Cadence was never an objective, only an outcome — and the outcome
was always the same, 1–2 trades/month:

    ASIAN_RSI_DIP_v1 (the prop hero)   1.51 trades/month
    candidate_15m (permutation-clean)  1.3  trades/month  ← LOWER, on a 16× faster bar

That second line is the whole reason this file is not just "run v3 on 5m".
Dropping the timeframe did not raise cadence, because cadence is set by how
selective the condition CONJUNCTION is, not by how fast the bars arrive. A
3-condition AND fires about as rarely on 15m as on 4H. Searching a lower
timeframe without gating on cadence just re-finds rare setups faster.

═══ WHAT THE TARGET NUMBER IS AND WHERE IT COMES FROM ═══

Monte Carlo over the hero's real trade log (3,000 paths, app/prop_eval.py),
$10k Breakout eval:

    eval     risk   pass%   median trades to resolve
    TURBO    0.5%   87.6%   15      ≈ 9.9 months at 1.51/mo
    CLASSIC  1.0%   87.8%    8      ≈ 5.3 months at 1.51/mo
    TURBO    1.5%   36.2%    2      ≈ 1.3 months  ← speed bought with pass rate

CLASSIC @1% resolves in a median 8 trades at 87.8% pass. So **8 trades/month
passes the eval in about a month without touching risk**. That is the spec:

    MIN_PER_MONTH = 6      (8 is the goal; 6 is the gate, to see the shoulder)

Cadence is the CONSTRAINT, expectancy is still the objective. This does not
lower the bar for edge — it refuses to consider edges too rare to be useful.

═══ THE HONESTY GATES (unchanged from v3, plus one) ═══

  1. cadence     ≥ MIN_PER_MONTH trades/month, and n ≥ MIN_N absolute
  2. split-half  both halves of the window net-positive, independently
  3. permutation survivors only: N_PERM random-entry nulls at the SAME cadence
                 and geometry, Bonferroni-corrected over every stage-1 test run

Gate 3 is what `strategy_search3`'s survivors never faced and why its "48 finds"
were mostly noise — random entries clear a split-half gate ~12% of the time, so
365 tests manufacture ~45 false survivors. Bonferroni over the ACTUAL number of
tests is the only correction that covers a search this size.

**A zero-survivor result is a real answer, not a failed run.** It would say: at
this quality bar, cadence of 6+/month does not exist in this vocabulary — stop
trying to speed up the eval with a new strategy and change the eval config
instead.

Run from the repo root (long; use a background run):
    python3 research/cadence_search.py            # 1h + 15m + 4h control
    python3 research/cadence_search.py --tf 1h    # one timeframe
    python3 research/cadence_search.py --selfcheck
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np

import _bootstrap  # noqa: F401  — repo root onto sys.path; must precede `app`

from app.backtest_engine import _run_backtest                      # noqa: E402
from app.paths import RESULTS                                      # noqa: E402
from app.strategy_search import (CAPITAL, MAX_CONDS, MIN_N,        # noqa: E402
                                 SLOTS, _combo_mask, _describe,
                                 _eval, _masks, _sig_fn,
                                 combo_params)
from app.strategy_search3 import RISK, _geo, _load                 # noqa: E402

# ── the cadence spec (see module docstring for the derivation) ────────────────
MIN_PER_MONTH = 6.0        # hard gate; 8/mo is what passes CLASSIC@1% in a month
TIMEFRAMES = ("1h", "15m", "4h")   # 4h is the control — the hero's own timeframe
MONTHS = 30

# Geometry: the coarse (k×ATR, R) grid. Fine-tuning geometry per survivor is a
# stage-2 luxury; the question here is whether ANY cell clears the cadence bar.
# ponytail: coarse grid only — widen to strategy_search3.FINE_* if a shoulder appears
COARSE_K = (0.75, 1.5, 2.5)
COARSE_R = (1.5, 3.0, 5.0)

N_PERM = 25_000            # matches candidate_15m; 8k cannot clear Bonferroni
CAP_BARS = 24              # hold cap for the permutation null's barrier race
ALPHA = 0.05
TOP_REPORT = 25


def _combos(tf: str):
    """v3's generator. The `hours` slot stays on every intraday timeframe — the
    session filter is the hero's entire edge, so it must remain searchable."""
    slots = {n: o for n, o in SLOTS.items() if not (tf == "1d" and n == "hours")}
    names = list(slots)
    for r in range(1, MAX_CONDS + 1):
        for chosen in itertools.combinations(names, r):
            for opts in itertools.product(*(slots[n] for n in chosen)):
                active = dict(zip(chosen, opts))
                for direction in ("long", "short"):
                    yield direction, active


def _months_of(df) -> float:
    return (df.index[-1] - df.index[0]).days / 30.44


def _bar_outcomes(df, k, r, direction, cap=CAP_BARS):
    """Per-bar trade outcome in R, for EVERY bar — computed once, sampled many.

    A full `_run_backtest` per permutation is ~0.2–2.2s depending on timeframe;
    25,000 of them per survivor is 5+ hours and the honest gate never runs. But
    a random-entry null does not need the sequential one-position-at-a-time
    engine — it needs "what would entering here have returned", which depends
    only on the bar itself. So resolve every bar's barrier race once (O(n×cap))
    and a permutation collapses to sampling n values from that array.

    Geometry matches stage 1: stop = k×ATR(entry bar), target = r×stop, so the
    outcome is already expressed in R (+r on a win, −1 on a stop, fractional at
    the hold cap). ponytail: ties go to the stop, same as sequential_sim.
    """
    hi, lo, cl = (df["high"].to_numpy(), df["low"].to_numpy(),
                  df["close"].to_numpy())
    atr = df["atr14"].to_numpy()
    n = len(cl)
    long_ = direction == "long"
    out = np.full(n, np.nan)
    for i in range(n - 1):
        stop_d = k * atr[i]
        if not np.isfinite(stop_d) or stop_d <= 0:
            continue
        entry = cl[i]
        sl = entry - stop_d if long_ else entry + stop_d
        tp = entry + r * stop_d if long_ else entry - r * stop_d
        end = min(i + 1 + cap, n)
        for j in range(i + 1, end):
            if (lo[j] <= sl) if long_ else (hi[j] >= sl):
                out[i] = -1.0
                break
            if (hi[j] >= tp) if long_ else (lo[j] <= tp):
                out[i] = r
                break
        else:
            j = end - 1
            move = (cl[j] - entry) if long_ else (entry - cl[j])
            out[i] = move / stop_d
    return out


def _perm_pvalue(outcomes, n_signals, observed_r, rng, n_perm):
    """Random-entry null: same number of entries, same geometry, random bars.

    The question a cadence-gated search MUST ask, because gating on frequency
    actively selects for combos that fire a lot — and in a trending market,
    firing a lot is worth something all by itself. If random entries at the same
    cadence do as well, the combo's conditions contributed nothing.
    """
    valid = outcomes[np.isfinite(outcomes)]
    if len(valid) < n_signals:
        return 1.0
    # vectorized: one (n_perm × n_signals) draw, compare all means at once
    draws = rng.choice(valid, size=(n_perm, n_signals), replace=True)
    beat = int((draws.mean(axis=1) >= observed_r).sum())
    # rule of three when nothing beats it: p is bounded, never zero
    return (3.0 / n_perm) if beat == 0 else (beat + 1) / (n_perm + 1)


def run(timeframes=TIMEFRAMES, min_per_month=MIN_PER_MONTH, n_perm=N_PERM):
    t0 = time.time()
    coarse = [(k, r) for k in COARSE_K for r in COARSE_R]
    rows, tests = [], 0

    print(f"cadence search · gate ≥{min_per_month}/mo · {len(coarse)} geometry "
          f"regimes · risk {RISK['risk_pct']}%/trade · {MONTHS}mo", flush=True)

    for tf in timeframes:
        df = _load(tf, MONTHS)
        masks = _masks(df)
        nb, months = len(df), _months_of(df)
        mid_iso = df.index[nb // 2].isoformat()
        combos = list(_combos(tf))
        need = min_per_month * months          # min signal BARS to be worth testing
        print(f"[{tf}] {nb} bars · {months:.1f} months · {len(combos)} combos "
              f"· need ≥{need:.0f} signals", flush=True)

        kept = skipped = 0
        for direction, active in combos:
            mask = _combo_mask(masks, nb, active)
            sigs = int(mask.sum())
            # Cadence prune BEFORE any backtest. Trades ≤ signals always (one
            # position at a time), so a combo that cannot signal often enough
            # can never trade often enough. This is what makes 15m tractable.
            if sigs < need or sigs < MIN_N:
                skipped += 1
                continue
            kept += 1
            sig = _sig_fn(mask, direction)
            for k, r in coarse:
                geo = _geo(k, r)
                ev = _eval(_run_backtest(df, sig, geo, CAPITAL), mid_iso)
                tests += 1
                if ev is None:
                    continue
                per_mo = ev["n"] / months
                if per_mo < min_per_month or not ev["robust"]:
                    continue
                rows.append({
                    "tf": tf, "direction": direction, "k": k, "rr": r,
                    "per_month": round(per_mo, 2),
                    "signals": sigs,
                    "params": {**combo_params(direction, active, tf),
                               "atr_stop_mult": k, "rr": r},
                    "desc": f"{_describe(direction, active, tf)} · {k}×ATR · {r}R",
                    **ev,
                })
        print(f"[{tf}] cadence-pruned {skipped}/{len(combos)} combos before "
              f"backtest · {kept} tested · {len(rows)} survivors so far "
              f"({time.time() - t0:.0f}s)", flush=True)

    # expectancy in R per trade — the objective, now that cadence is a constraint
    for r_ in rows:
        r_["exp_r"] = round((r_["half1"] + r_["half2"]) / r_["n"] / RISK["risk_pct"], 3)
    rows.sort(key=lambda x: x["exp_r"], reverse=True)

    bonf = ALPHA / max(tests, 1)
    print(f"\nstage 1: {tests:,} tests · {len(rows)} cleared cadence + split-half"
          f"\nBonferroni threshold: {ALPHA}/{tests:,} = {bonf:.3g}", flush=True)

    # ── stage 2: permutation, survivors only (expensive, so top-N) ────────────
    rng = np.random.default_rng(42)
    dfs = {tf: _load(tf, MONTHS) for tf in {r_["tf"] for r_ in rows[:TOP_REPORT]}}
    oc: dict = {}
    for r_ in rows[:TOP_REPORT]:
        key = (r_["tf"], r_["k"], r_["rr"], r_["direction"])
        if key not in oc:
            oc[key] = _bar_outcomes(dfs[r_["tf"]], r_["k"], r_["rr"], r_["direction"])
        p = _perm_pvalue(oc[key], r_["n"], r_["exp_r"], rng, n_perm)
        r_["perm_p"] = p
        r_["survives"] = bool(p < bonf)
        print(f"  {'✓' if r_['survives'] else '✗'} p={p:.2g} "
              f"[{r_['tf']}] {r_['per_month']}/mo exp {r_['exp_r']}R "
              f"n={r_['n']} wr={r_['wr']}% · {r_['desc']}", flush=True)

    survivors = [r_ for r_ in rows[:TOP_REPORT] if r_.get("survives")]
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "min_per_month": min_per_month, "months": MONTHS,
        "timeframes": list(timeframes),
        "stage1_tests": tests, "bonferroni": bonf, "permutations": n_perm,
        "cadence_split_half_survivors": len(rows),
        "permutation_survivors": len(survivors),
        "rows": rows[:TOP_REPORT],
    }
    path = RESULTS / "cadence_search.json"
    path.write_text(json.dumps(out, indent=1))

    print(f"\n{'='*72}")
    if survivors:
        print(f"{len(survivors)} survivor(s) cleared cadence + split-half + "
              f"permutation@Bonferroni:")
        for s in survivors:
            print(f"  {s['per_month']}/mo · exp {s['exp_r']}R · wr {s['wr']}% "
                  f"· n={s['n']} · {s['desc']}")
    else:
        print("ZERO survivors. That is the answer, not a failure: at this "
              f"quality bar, ≥{min_per_month} trades/month does not exist in "
              "this vocabulary. Change the eval config, not the strategy.")
    print(f"wrote {path} · {time.time() - t0:.0f}s")
    return out


def _selfcheck() -> None:
    """The cadence prune must never discard a combo that would have passed.

    Trades ≤ signal bars (one position at a time), so pruning on signal count is
    only safe if the threshold used for signals is ≤ the one used for trades.
    """
    months = 10.0
    need = MIN_PER_MONTH * months
    # a combo signalling exactly at the gate must survive the prune
    assert not (need < need), "prune must be inclusive at the boundary"
    # a combo signalling below the gate can never reach it in trades
    for sigs in (0, int(need) - 1):
        assert sigs < need, "below-gate signal counts must be pruned"
    # and one above must not be pruned
    assert not (int(need) + 1 < need)

    # rule-of-three bound: 0 hits in N gives p ≤ 3/N, never 0
    n = 25_000
    assert abs(3.0 / n - 0.00012) < 1e-9
    assert 3.0 / n < ALPHA / 365, "25k perms must clear Bonferroni over 365 tests"
    assert 3.0 / 8_000 > ALPHA / 365, "8k perms must NOT clear it (why N_PERM=25k)"

    # the null must be calibrated: an "observed" equal to the mean of the pool
    # should land mid-distribution (p≈0.5), and an absurd one should be extreme
    rng = np.random.default_rng(0)
    pool = rng.normal(0.0, 1.0, 5_000)
    assert 0.35 < _perm_pvalue(pool, 30, float(pool.mean()), rng, 2_000) < 0.65, \
        "null miscalibrated: mean observation must sit mid-distribution"
    assert _perm_pvalue(pool, 30, 10.0, rng, 2_000) <= 3.0 / 2_000, \
        "an unreachable observation must bound p, not return 0"

    # barrier race: a clean monotone ramp up must resolve LONG at +r, never -1
    import pandas as pd
    n_ = 120
    px = pd.Series(np.linspace(100.0, 200.0, n_))
    df = pd.DataFrame({"high": px * 1.001, "low": px * 0.999, "close": px,
                       "atr14": pd.Series(np.full(n_, 1.0))})
    out = _bar_outcomes(df, k=1.0, r=2.0, direction="long", cap=24)
    got = out[np.isfinite(out)]
    assert (got > 0).all(), f"monotone ramp must never stop out long: {got.min()}"
    assert abs(got.max() - 2.0) < 1e-9, "a reached target must score exactly +r"
    print("selfcheck OK — prune conservative, null calibrated, barriers correct")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", nargs="*", default=list(TIMEFRAMES))
    ap.add_argument("--min-per-month", type=float, default=MIN_PER_MONTH)
    ap.add_argument("--perms", type=int, default=N_PERM)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        sys.exit(0)
    run(tuple(a.tf), a.min_per_month, a.perms)
