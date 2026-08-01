"""The one thing in this book that survives every test: non-VETO shorts.

Built by elimination, not by search. Every other cell examined this session died
to one of four gates; this one passes all four, so it is the only candidate for
a system rather than a hypothesis.

  1. Beats a RANDOM entry            — else it is not selection, it is exposure
  2. Beats a PERIOD-MATCHED random   — else it is the market, not the trader
  3. Beats a DIRECTION-MATCHED one   — else it is drift; BTC fell 105k→63k over
                                       this book, which flatters every short
  4. Positive in BOTH halves         — else it is the S1–S5 failure again

Gate 3 is the one that usually kills a short book and the reason the baseline is
recomputed per-window and per-direction rather than taken from the 7-year run.
A short strategy in a falling market must clear the bar a coin-flip short clears
in that same falling market, not the bar averaged over seven years.

What it does NOT establish: that the edge extends to entries he did not take.
The sample is his own selection, so this measures the filter he already applies,
whatever it is. The stated cadence — ~1.5/week — is a property of that filter,
and raising it is the open problem, because the edge itself is now sufficient
and the frequency is not.

    python3 research/short_edge.py
"""
from __future__ import annotations

import bisect
import json
import sys
from datetime import datetime, timezone
from math import sqrt

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.geometry import FRICTION_PCT, solve      # noqa: E402
from app.paths import RESULTS                     # noqa: E402
from research.barrier_test import simulate        # noqa: E402
from research.entry_edge import load_bars, load_trades, replay   # noqa: E402

RRS = [1.0, 2.0, 3.0]
WEEKLY_GOAL = 0.10


def period_random(bars, lo, hi, sl, tp, direction) -> float | None:
    """Random-entry win rate inside one window, one direction. Gate 2 + 3."""
    sub = [b for b in bars if lo <= b[0] <= hi]
    if len(sub) < 200:
        return None
    r = simulate(sub, sl, tp, direction)
    return r["win_rate"] if r else None


def assess(bars, ts, trades, sl, tp, direction) -> dict | None:
    """Full four-gate assessment of one (geometry, direction, filter) cell."""
    if len(trades) < 30:
        return None
    r = replay(bars, ts, trades, sl, tp)
    if not r:
        return None
    w, n, be = r["win_rate"], r["n"], r["breakeven_wr"]
    se = sqrt(w * (1 - w) / n)
    z = (w - be) / se if se else 0.0

    matched = period_random(bars, trades[0][0], trades[-1][0], sl, tp, direction)
    mid = len(trades) // 2
    halves = []
    for sub in (trades[:mid], trades[mid:]):
        hr = replay(bars, ts, sub, sl, tp)
        hrand = period_random(bars, sub[0][0], sub[-1][0], sl, tp, direction)
        if not hr:
            return None
        halves.append({"win_rate": hr["win_rate"], "net_pct": hr["net_pct"],
                       "random": hrand, "n": hr["n"],
                       "edge_pp": (hr["win_rate"] - hrand) * 100 if hrand else None})

    span_wk = (trades[-1][0] - trades[0][0]) / 1000 / 86400 / 7
    return {
        "direction": direction, "stop_pct": sl, "target_pct": tp,
        "n": n, "win_rate": w, "breakeven_wr": be, "net_pct": r["net_pct"],
        "median_hold_h": r["median_hold_h"],
        "z": z, "ci_lo": w - 1.96 * se, "ci_hi": w + 1.96 * se,
        "matched_random": matched,
        "edge_pp": (w - matched) * 100 if matched else None,
        "halves": halves,
        "trades_per_week": n / span_wk if span_wk else 0,
        # the four gates
        "g1_beats_random": bool(matched and w > matched),
        "g2_significant": z > 1.96,
        "g3_ci_clears_be": (w - 1.96 * se) > be,
        "g4_both_halves": all(h["net_pct"] > 0 for h in halves),
    }


def main() -> None:
    bars = load_bars()
    ts = [b[0] for b in bars]
    trades = sorted(load_trades(), key=lambda t: t[0])
    sigma = json.load(open(RESULTS / "barrier_baseline.json"))["sigma"]

    def px(t):
        return bars[min(bisect.bisect_left(ts, t), len(bars) - 1)][3]

    print(f"{len(trades)} entries · BTC {px(trades[0][0]):,.0f} → {px(trades[-1][0]):,.0f} "
          f"over the book (a FALLING market — gate 3 matters)\n")

    pools = {
        "short non-VETO": [t for t in trades if t[1] == "short"
                           and not str(t[3]).startswith("VETO")],
        "short all":      [t for t in trades if t[1] == "short"],
        "long non-VETO":  [t for t in trades if t[1] == "long"
                           and not str(t[3]).startswith("VETO")],
        "long all":       [t for t in trades if t[1] == "long"],
    }

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "sigma": sigma, "friction_pct": FRICTION_PCT, "cells": []}

    print(f"  {'cell':>16} {'R:R':>4} {'n':>4} {'WR':>7} {'matched':>8} {'edge':>8} "
          f"{'BE':>7} {'z':>6} {'H1':>7} {'H2':>7} {'gates':>7}")
    for rr in RRS:
        g = solve(sigma, 2.5, rr)
        for label, pool in pools.items():
            d = "short" if label.startswith("short") else "long"
            a = assess(bars, ts, pool, g["stop_pct"], g["target_pct"], d)
            if not a:
                continue
            a["cell"] = label
            a["rr"] = rr
            gates = sum([a["g1_beats_random"], a["g2_significant"],
                         a["g3_ci_clears_be"], a["g4_both_halves"]])
            a["gates_passed"] = gates
            out["cells"].append(a)
            h1, h2 = a["halves"]
            print(f"  {label:>16} {rr:>4.0f} {a['n']:>4} {a['win_rate']:>6.1%} "
                  f"{a['matched_random']:>7.1%} {a['edge_pp']:>+7.1f}pp "
                  f"{a['breakeven_wr']:>6.1%} {a['z']:>+6.2f} "
                  f"{h1['net_pct']:>+6.2f} {h2['net_pct']:>+6.2f} "
                  f"{gates:>4}/4 {'✓' if gates == 4 else ''}")

    survivors = [c for c in out["cells"] if c["gates_passed"] == 4]
    out["survivors"] = len(survivors)
    print(f"\n  {len(survivors)} of {len(out['cells'])} cells pass all four gates")

    if survivors:
        b = max(survivors, key=lambda c: c["net_pct"])
        out["best"] = b
        lev = lambda risk: risk / (b["stop_pct"] + FRICTION_PCT)
        print(f"\n  ── THE SYSTEM ──")
        print(f"  {b['cell']} at R:R {b['rr']:.0f} — stop {b['stop_pct']:.2f}% / "
              f"target {b['target_pct']:.2f}%, ~{b['median_hold_h']:.0f}h hold")
        print(f"  WR {b['win_rate']:.1%} vs {b['matched_random']:.1%} matched random "
              f"({b['edge_pp']:+.1f}pp) · breakeven {b['breakeven_wr']:.1%}")
        print(f"  95% CI [{b['ci_lo']:.1%}, {b['ci_hi']:.1%}] — clears breakeven")
        print(f"  net {b['net_pct']:+.4f}%/trade · cadence {b['trades_per_week']:.2f}/wk")
        print(f"\n  what it pays, and what the missing piece is:")
        for risk in (3.0, 5.0):
            for tpw in (b["trades_per_week"], 3.0, 5.0, 7.5):
                per = b["net_pct"] * lev(risk)
                wk = (1 + per / 100) ** tpw - 1
                flag = "  ← TARGET" if wk >= WEEKLY_GOAL else ""
                print(f"    risk {risk:>4.1f}%  {tpw:>4.2f} tr/wk → {wk:>+6.2%}/wk"
                      f"  {(1+wk)**4.35-1:>+7.1%}/mo{flag}")
        out["gap"] = {"have_tpw": b["trades_per_week"], "need_tpw_at_5pct": None}
        for tpw in [x / 4 for x in range(4, 61)]:
            if (1 + b["net_pct"] * lev(5.0) / 100) ** tpw - 1 >= WEEKLY_GOAL:
                out["gap"]["need_tpw_at_5pct"] = tpw
                print(f"\n  GAP: have {b['trades_per_week']:.2f}/wk, "
                      f"need {tpw:.2f}/wk at 5% risk → "
                      f"{tpw / b['trades_per_week']:.1f}× more setups. "
                      f"The edge is sufficient; the frequency is not.")
                break

    with open(RESULTS / "short_edge.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n  → wrote {RESULTS / 'short_edge.json'}")


if __name__ == "__main__":
    main()
