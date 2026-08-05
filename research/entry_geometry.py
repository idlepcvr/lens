"""What YOUR entries are worth at a geometry you have never traded.

`entry_edge.py` answers "how did these entries do?" but only at geometries
`solve()` derives from a 2.5-day hold, so it sweeps R:R with the stop pinned.
`plan.measured()` is coarser still: one blended win rate and R:R for the whole
book. Neither can answer the question that actually comes up — *if I ran a 1%
stop instead of 2.83%, what would my win rate be?* — because a win rate is not a
property of a trader, it is a property of a trader AT a geometry. Move the
barriers and it moves, and no amount of rescaling the old number recovers it.

So this walks every real entry — real timestamp, real direction — forward to a
free (stop × R:R × hold) grid and measures the win rate at each. That is the one
measurement `/hedge-goal` could not source: it lets a cell be fed to the goal
model on evidence rather than on a typed guess.

WHAT THIS IS NOT. The grid is a search, and this repo has already shipped one
mined edge that died out of sample (S1–S5). 288 cells are tried here, so at
p<0.05 chance alone hands back roughly 14 winners. Two guards travel with every
cell and both must hold before it is called a candidate:

  z          — is the win rate distinguishable from its own breakeven at this n?
  both_halves— does it hold in BOTH halves of the book, in time order? An edge
               in the first half only is decay or luck, never a system.

Even then a surviving cell is a CANDIDATE, not a finding: the p-values are
per-cell and uncorrected (Bonferroni here would be p<0.00017). The sample is
also his own selection, so this measures the filter he already applies — it does
not establish the edge extends to entries he did not take. Forward trades on
bars the grid never saw are the only thing that settles it.

    python3 research/entry_geometry.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.geometry import FRICTION_PCT                      # noqa: E402
from app.paths import RESULTS                              # noqa: E402
from research.entry_edge import (load_bars, load_trades,   # noqa: E402
                                 replay, trades_per_week)

# Free axes. Stop is swept independently of hold — that independence is the
# whole point of the file.
STOPS = [0.5, 0.75, 1.0, 1.5, 2.0, 2.8302, 4.0, 5.0]   # % underlying move
RRS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
HOLDS = [24, 72, 240]                                   # hours to walk away
MIN_N = 30          # below this a win rate is noise, not a measurement
MIN_RESOLVED = 0.60  # a cell resolving <60% of entries is a horizon artifact


def guarded(bars, ts_index, group, stop, target, hold) -> dict | None:
    """One cell, with both noise guards attached. None if it cannot be judged."""
    r = replay(bars, ts_index, group, stop, target, max_hours=hold)
    if not r or r["n"] < MIN_N:
        return None
    total = r["n"] + r["unresolved"]
    if total and r["n"] / total < MIN_RESOLVED:
        return None

    w, n = r["win_rate"], r["n"]
    se = (w * (1 - w) / n) ** 0.5 if n else 0
    z = (w - r["breakeven_wr"]) / se if se else 0.0

    chrono = sorted(group, key=lambda t: t[0])
    half = len(chrono) // 2
    h1 = replay(bars, ts_index, chrono[:half], stop, target, max_hours=hold)
    h2 = replay(bars, ts_index, chrono[half:], stop, target, max_hours=hold)
    both = bool(h1 and h2 and h1["net_pct"] > 0 and h2["net_pct"] > 0)

    return {
        "stop_pct": round(stop, 4), "target_pct": round(target, 4),
        "rr": round(target / stop, 2), "hold_h": hold,
        "n": n, "unresolved": r["unresolved"],
        "resolved_frac": round(r["n"] / total, 3) if total else 0.0,
        "win_rate": round(w, 4),
        "breakeven_wr": round(r["breakeven_wr"], 4),
        # the bar a coin flip clears at these barriers, ignoring drift — a cell
        # beating breakeven but not this is geometry, not selection
        "random_wr": round(stop / (stop + target), 4),
        "edge_pp": round((w - r["breakeven_wr"]) * 100, 2),
        "net_pct": round(r["net_pct"], 4),
        "median_hold_h": r["median_hold_h"],
        "z": round(z, 2),
        "significant": bool(z > 1.96),
        "both_halves": both,
        # a cell is only ever a CANDIDATE — see the module docstring
        "candidate": bool(z > 1.96 and both and r["net_pct"] > 0),
    }


def main() -> None:
    bars = load_bars()
    ts_index = [b[0] for b in bars]
    trades = load_trades()
    non_veto = [t for t in trades if not str(t[3]).startswith("VETO")]

    groups = [("ALL", trades), ("NON-VETO", non_veto)]
    tried = 0
    cells = []
    for label, group in groups:
        if len(group) < MIN_N:
            continue
        tpw = trades_per_week(group)
        for stop in STOPS:
            for rr in RRS:
                for hold in HOLDS:
                    tried += 1
                    c = guarded(bars, ts_index, group, stop, stop * rr, hold)
                    if not c:
                        continue
                    c["group"] = label
                    c["trades_per_week"] = round(tpw, 2)
                    cells.append(c)

    cells.sort(key=lambda c: -c["net_pct"])
    cand = [c for c in cells if c["candidate"]]

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "n_entries": len(trades),
        "n_non_veto": len(non_veto),
        "friction_pct": FRICTION_PCT,
        "cells_tried": tried,
        "cells_judged": len(cells),
        "candidates": len(cand),
        # uncorrected and per-cell — stated so no caller can read p<0.05 as proof
        "bonferroni_p": round(0.05 / tried, 6) if tried else None,
        # How many cells this grid hands back with NO edge present: P(z>1.96) ≈
        # .025 × P(both halves net>0) ≈ .25. Compare `candidates` against THIS,
        # never against zero — a count below it is noise wearing a result's hat.
        "expected_by_chance": round(tried * 0.025 * 0.25, 1),
        "cells": cells,
    }
    (RESULTS / "entry_geometry.json").write_text(json.dumps(out, indent=1))

    print(f"{len(trades)} entries ({len(non_veto)} non-VETO) · friction {FRICTION_PCT}%")
    print(f"{tried} cells tried · {len(cells)} judged · {len(cand)} candidates "
          f"(~{out['expected_by_chance']} expected with NO edge)")
    print(f"Bonferroni for this grid: p < {out['bonferroni_p']}\n")
    hdr = (f"  {'group':>9} {'stop':>6} {'target':>7} {'R:R':>5} {'hold':>5} "
           f"{'n':>4} {'WR':>7} {'BE':>7} {'rand':>7} {'net':>8} {'z':>6} {'2h':>3}")
    print(hdr)
    for c in cells[:18]:
        print(f"  {c['group']:>9} {c['stop_pct']:6.2f} {c['target_pct']:7.2f} "
              f"{c['rr']:5.2f} {c['hold_h']:4d}h {c['n']:4d} "
              f"{c['win_rate']*100:6.1f}% {c['breakeven_wr']*100:6.1f}% "
              f"{c['random_wr']*100:6.1f}% {c['net_pct']:+7.3f}% {c['z']:6.2f} "
              f"{'Y' if c['both_halves'] else '·':>3}")
    if not cand:
        print("\nNo cell clears both guards. That is a result, not a failure.")


if __name__ == "__main__":
    main()
