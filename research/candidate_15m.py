"""The one combination that survived a correction for having searched 365 of them.

    15m · double_bottom AND structure-up AND ascending-triangle-break · LONG
    stop = target = 2.83% · one position at a time · 24h cap

    41 trades · 75.6% win · +0.925%/trade net of 0.085% friction
    0 of 25,000 random-entry permutations beat its win rate OR its net
    random entries average -0.099%/trade over the same bars

═══ WHY THIS ONE AND NOT THE OTHER 47 ═══

The combination search returned 48 setups passing "net positive AND positive in
both halves". That gate is far weaker than it reads: permutation says random
entries pass it 12.3% of the time, so over 365 tests it alone manufactures ~45
false survivors. 48 found, ~45 expected from noise — the POPULATION of survivors
is noise, and reporting it as 48 finds would have been the S1–S5 mistake again.

This one is separated from that population by a test the others fail. Bonferroni
over 365 tests demands p < 0.000137. With 0 hits in 25,000 permutations the
rule-of-three 95% upper bound on p is 3/25,000 = 0.00012, which clears it. 8,000
trials would NOT have been enough to say so — 0/8,000 bounds p at 0.000375, and
the point estimate clearing a threshold is not the same as clearing it.

═══ WHAT THIS DOES NOT ESTABLISH ═══

  · Cadence. 41 trades in 133 weeks is one trade every three weeks. Whatever
    this is, it cannot carry a weekly return target, and sizing it up to try is
    how a real edge becomes a blown account.
  · The permutation null is RANDOM ENTRY TIMES, not random combinations drawn
    from the same vocabulary. Real features cluster in ways random timestamps do
    not, so this null is the more generous of the two. Bonferroni over the 365
    is what covers the search itself; both together are a reasonable argument
    and not a proof.
  · No forward test. The 15m book runs 2023-12 to 2026-06 and this was found
    inside it. Nothing here has been traded.

Treat it as the one candidate worth forward-testing, not as a system.

    python3 research/candidate_15m.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from math import sqrt

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.chart_patterns import pattern_masks as chart_masks   # noqa: E402
from app.geometry import FRICTION_PCT                         # noqa: E402
from app.patterns import pattern_masks                        # noqa: E402
from app.paths import RESULTS                                 # noqa: E402
from research.one_at_a_time import compound                   # noqa: E402
from research.sequential_sim import TF_MIN, load, sequential   # noqa: E402

TF = "15m"
BARRIER = 2.8302
HOLD_CAP_H = 24
RISK_PER_LOSS = 0.20     # size so one stop-out costs 20% of the account


def build(df):
    """The three conditions, ANDed. All three are causal — see app/patterns.py
    and app/chart_patterns.py, both of which shift by their confirmation lag."""
    p, c = pattern_masks(df), chart_masks(df)
    return (p[("pattern", "double_bottom")]
            & p[("structure", "up")]
            & c[("chart", "ascending_triangle_long")])


def main() -> None:
    df = load(TF)
    bars = list(zip(df["ts"].astype("int64"), df["high"], df["low"], df["close"]))
    weeks = (bars[-1][0] - bars[0][0]) / 1000 / 86400 / 7
    cap = max(1, HOLD_CAP_H * 60 // TF_MIN[TF])

    mask = build(df)
    moves, holds = sequential(bars, mask, BARRIER, "long", cap)
    n = len(moves)
    wr = sum(1 for m in moves if m > 0) / n
    net = sum(moves) / n - FRICTION_PCT
    be = (BARRIER + FRICTION_PCT) / ((BARRIER - FRICTION_PCT) + (BARRIER + FRICTION_PCT))
    se = sqrt(wr * (1 - wr) / n)
    lev = RISK_PER_LOSS * 100 / (BARRIER + FRICTION_PCT)
    eq, dd, blown = compound(moves, lev, FRICTION_PCT)
    weekly = -1.0 if blown else eq ** (1 / weeks) - 1
    mid = n // 2
    halves = [sum(s) / len(s) - FRICTION_PCT for s in (moves[:mid], moves[mid:])]

    print(f"{TF} · double_bottom AND structure-up AND ascending-triangle · LONG")
    print(f"stop = target {BARRIER}% · {HOLD_CAP_H}h cap · friction {FRICTION_PCT}%\n")
    print(f"  signal bars              {int(mask.sum()):>10,}")
    print(f"  trades actually taken    {n:>10,}   (one position at a time)")
    print(f"  cadence                  {n / weeks:>10.2f} /week   ← one every "
          f"{7 / (n / weeks):.0f} days")
    print(f"  win rate                 {wr:>10.1%}   (breakeven {be:.1%})")
    print(f"  95% CI                   {wr - 1.96 * se:>9.1%}–{wr + 1.96 * se:.1%}")
    print(f"  net per trade            {net:>+10.3f}%")
    print(f"  halves                   {halves[0]:>+10.3f}% / {halves[1]:+.3f}%")
    print(f"  mean hold                {sum(holds) / len(holds) * TF_MIN[TF] / 60:>10.1f}h")
    print(f"\n  at {lev:.1f}x (one loss = {RISK_PER_LOSS:.0%} of account):")
    print(f"    weekly                 {weekly:>+10.2%}")
    print(f"    worst drawdown         {dd:>10.0%}")
    print(f"\n  ⚠ 41 trades over {weeks:.0f} weeks cannot carry a weekly target. "
          "Forward-test it; do not size it up.")

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "timeframe": TF, "barrier_pct": BARRIER, "friction_pct": FRICTION_PCT,
           "trades": n, "per_week": n / weeks, "win_rate": wr, "breakeven_wr": be,
           "net_per_trade": net, "halves": halves, "leverage": lev,
           "weekly": weekly, "max_drawdown": dd,
           "permutations": 25000, "perm_beat_win_rate": 0, "perm_beat_net": 0,
           "perm_p_upper_95": 3 / 25000, "bonferroni_threshold": 0.05 / 365}
    (RESULTS / "candidate_15m.json").write_text(json.dumps(out, indent=1))
    print(f"\nwrote {RESULTS / 'candidate_15m.json'}")


def _selfcheck() -> None:
    """The claim is a conjunction — it must be rarer than any of its parts."""
    df = load(TF).iloc[-8000:]
    p, c = pattern_masks(df), chart_masks(df)
    parts = [p[("pattern", "double_bottom")], p[("structure", "up")],
             c[("chart", "ascending_triangle_long")]]
    both = build(df)
    for i, part in enumerate(parts):
        assert both.sum() <= part.sum(), f"conjunction exceeds part {i}"
    assert (both & ~parts[0]).sum() == 0, "fired without a double bottom"
    assert (both & ~parts[2]).sum() == 0, "fired without a triangle break"
    # Rule of three, the arithmetic the verdict rests on.
    assert 3 / 25000 < 0.05 / 365, "0/25000 must clear Bonferroni over 365 tests"
    assert 3 / 8000 > 0.05 / 365, "0/8000 must NOT have been enough"
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
