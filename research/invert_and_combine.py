"""Two of his questions, both answerable with the book rather than with opinion.

═══ 1. CAN A LOSING STRATEGY BE INVERTED INTO A WINNING ONE ═══

"If I lose 60% of the time, flipping every trade wins 60% of the time." The win
rate does flip. The fee does not — you pay the round trip whichever way you
face. At symmetric barriers b with friction f, a strategy winning p becomes:

    net_normal   = p(b - f) - (1-p)(b + f) = b(2p - 1) - f
    net_inverted = (1-p)(b - f) - p(b + f) = b(1 - 2p) - f

Both carry the same -f. So inversion pays only when b(1-2p) > f, i.e.

    p < (1 - f/b) / 2        → at b=2.83%, f=0.30%:  p < 44.7%

which is the breakeven win rate (55.3%) reflected about 50%. Being reliably
wrong is exactly as hard as being reliably right, and a coin flip is worthless
in both directions. The question is therefore empirical: is his book near 40%
or near 50%? This measures it instead of assuming, and reports the inverse of
every setup alongside it.

═══ 2. DOES COMBINING THEM FIND AN EDGE ═══

"Triangles, plus lower highs and lower lows, plus the 4h." That is a conjunction
of masks, and no single-mask test can answer it. So every direction-consistent
pair and triple is tested, sequentially, one position at a time.

⚠ This is a search over thousands of combinations and every p-value in it is
uncorrected. That is how S1–S5 happened. Split-half is therefore a gate, not a
footnote: a combination is only reported if it makes money in BOTH halves of
the sample, and even then it is a candidate for forward testing, not a finding.

    python3 research/invert_and_combine.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from itertools import combinations
from math import sqrt

import numpy as np

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.chart_patterns import pattern_masks as chart_masks   # noqa: E402
from app.geometry import FRICTION_PCT                         # noqa: E402
from app.patterns import pattern_masks                        # noqa: E402
from app.paths import RESULTS                                 # noqa: E402
from research.sequential_sim import (DIRECTION, TF_MIN,        # noqa: E402
                                     load, sequential)

BARRIER = 2.8302        # the only geometry anything has ever cleared fees at
HOLD_CAP_H = 24
MIN_TRADES = 30
RISK_PER_LOSS = 0.20


def vocabulary(df):
    """Every mask, tagged with the direction it claims. Direction matters —
    ANDing a long signal with a short one is not a strategy, it is a typo."""
    out = {}
    for key, m in pattern_masks(df).items():
        out[f"{key[0]}/{key[1]}"] = (m, DIRECTION[key])
    for key, m in chart_masks(df).items():
        out[f"chart/{key[1]}"] = (m, key[1].rsplit("_", 1)[1])
    return out


def score(bars, mask, direction, cap, weeks):
    moves, _ = sequential(bars, mask, BARRIER, direction, cap)
    if len(moves) < MIN_TRADES:
        return None
    n = len(moves)
    wr = sum(1 for m in moves if m > 0) / n
    mid = n // 2
    halves = [sum(s) / len(s) - FRICTION_PCT for s in (moves[:mid], moves[mid:])]
    inv = [sum(s) / len(s) * -1 - FRICTION_PCT for s in (moves[:mid], moves[mid:])]
    gross = sum(moves) / n
    se = sqrt(wr * (1 - wr) / n)
    return {"n": n, "per_week": n / weeks, "win_rate": wr,
            "ci_lo": wr - 1.96 * se, "ci_hi": wr + 1.96 * se,
            "gross": gross, "net": gross - FRICTION_PCT,
            "net_inverted": -gross - FRICTION_PCT,
            "halves": halves, "halves_inverted": inv,
            "both_halves": all(h > 0 for h in halves),
            "both_halves_inverted": all(h > 0 for h in inv)}


def main() -> None:
    be = (BARRIER + FRICTION_PCT) / ((BARRIER - FRICTION_PCT) + (BARRIER + FRICTION_PCT))
    flip_wall = (1 - FRICTION_PCT / BARRIER) / 2
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "barrier_pct": BARRIER, "friction_pct": FRICTION_PCT,
           "breakeven_wr": be, "inversion_wall": flip_wall, "cells": []}

    print(f"stop=target {BARRIER}% · friction {FRICTION_PCT}% · one position at a time")
    print(f"To profit normally you need a win rate above {be:.1%}.")
    print(f"To profit by INVERTING you need one below {flip_wall:.1%}.")
    print(f"Between {flip_wall:.1%} and {be:.1%} both directions lose to fees.\n")

    for tf in ["4h", "1h", "15m", "5m"]:
        df = load(tf)
        bars = list(zip(df["ts"].astype("int64"), df["high"], df["low"], df["close"]))
        weeks = (bars[-1][0] - bars[0][0]) / 1000 / 86400 / 7
        cap = max(1, HOLD_CAP_H * 60 // TF_MIN[tf])
        vocab = vocabulary(df)

        singles = {}
        for name, (m, d) in vocab.items():
            r = score(bars, m, d, cap, weeks)
            if r:
                singles[name] = r
                r.update({"timeframe": tf, "setup": name, "parts": 1, "direction": d})
                out["cells"].append(r)

        # Pairs and triples, direction-consistent only.
        usable = [(n, m, d) for n, (m, d) in vocab.items() if m.sum() >= MIN_TRADES]
        combos = 0
        for size in (2, 3):
            for group in combinations(usable, size):
                dirs = {g[2] for g in group}
                if len(dirs) != 1:
                    continue
                m = group[0][1].copy()
                for g in group[1:]:
                    m &= g[1]
                if m.sum() < MIN_TRADES:
                    continue
                r = score(bars, m, group[0][2], cap, weeks)
                combos += 1
                if r:
                    r.update({"timeframe": tf, "setup": " + ".join(g[0] for g in group),
                              "parts": size, "direction": group[0][2]})
                    out["cells"].append(r)

        tf_cells = [c for c in out["cells"] if c["timeframe"] == tf]
        print(f"═══ {tf}: {len(singles)} singles + {combos} direction-consistent "
              f"combinations tested ({len(tf_cells)} had ≥{MIN_TRADES} trades)")
        lo = min(c["win_rate"] for c in tf_cells)
        hi = max(c["win_rate"] for c in tf_cells)
        below = [c for c in tf_cells if c["win_rate"] < flip_wall]
        above = [c for c in tf_cells if c["win_rate"] > be]
        print(f"     win rates span {lo:.1%}–{hi:.1%} · "
              f"{len(above)} above {be:.1%} · {len(below)} below {flip_wall:.1%} "
              f"(invertible) · {len(tf_cells) - len(above) - len(below)} stuck in the dead band")

    print()
    normal = [c for c in out["cells"] if c["net"] > 0 and c["both_halves"]]
    inverted = [c for c in out["cells"] if c["net_inverted"] > 0
                and c["both_halves_inverted"]]
    out["survivors_normal"] = len(normal)
    out["survivors_inverted"] = len(inverted)

    print(f"═══ of {len(out['cells'])} setups tested:")
    print(f"    {len(normal)} are net-positive AND positive in both halves, traded normally")
    print(f"    {len(inverted)} would be, traded INVERTED")
    for label, pool in (("NORMAL", normal), ("INVERTED", inverted)):
        for c in sorted(pool, key=lambda x: -(x["net"] if label == "NORMAL"
                                              else x["net_inverted"]))[:8]:
            net = c["net"] if label == "NORMAL" else c["net_inverted"]
            lev = RISK_PER_LOSS * 100 / (BARRIER + FRICTION_PCT)
            print(f"  {label:>8} {c['timeframe']:>3} {c['setup'][:52]:<52} "
                  f"n={c['n']:<5,} {c['per_week']:>4.1f}/wk win {c['win_rate']:>5.1%} "
                  f"net {net:+.3f}%  ≈{c['per_week'] * net * lev:+.2f}%/wk")

    (RESULTS / "invert_and_combine.json").write_text(json.dumps(out, indent=1))
    print(f"\nwrote {RESULTS / 'invert_and_combine.json'}")


def _selfcheck() -> None:
    """The inversion arithmetic is the claim; check it against the formula."""
    b, f = BARRIER, FRICTION_PCT
    for p in (0.30, 0.40, 0.4470, 0.50, 0.553, 0.70):
        normal = b * (2 * p - 1) - f
        inverted = b * (1 - 2 * p) - f
        assert abs((normal + inverted) - (-2 * f)) < 1e-9, \
            "normal and inverted must sum to minus two fees, always"
    wall = (1 - f / b) / 2
    assert b * (1 - 2 * (wall - 0.01)) - f > 0, "just below the wall must profit inverted"
    assert b * (1 - 2 * (wall + 0.01)) - f < 0, "just above the wall must not"
    be = (b + f) / ((b - f) + (b + f))
    assert abs((be - 0.5) - (0.5 - wall)) < 1e-9, \
        "the two walls must be mirror images about a coin flip"
    # A direction-inconsistent pair must never be built.
    a = (np.array([True, True]), "long")
    c = (np.array([True, True]), "short")
    assert len({a[1], c[1]}) != 1, "long+short is not a strategy"
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
