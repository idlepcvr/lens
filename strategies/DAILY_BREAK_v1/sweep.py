#!/usr/bin/env python3
"""
DAILY_BREAK_v1 — bounded parameter sweep (NEXT_SESSION.md D8)

Axes, and only these:
  be_at_r      None | 0.5 | 1.0          (breakeven-plus trigger, D2)
  trail_buf    0.15 | 0.25 | 0.40 x ATR  (box floor buffer, D1)
  partial_at_r 1.5 | 2.0                 (C variants only)

Reports the MEDIAN cell per variant, not the best cell. The best cell of a
50-cell sweep is noise, and picking it is how a backtest starts lying. The best
cell is printed too — as the size of the gap to the median, which is the actual
information: a wide gap means the variant is parameter-sensitive, i.e. fragile.

No axes beyond these. If the answer disappoints, the answer is the answer.

Run: python3 strategies/DAILY_BREAK_v1/sweep.py
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import backtest as bt

BE_AT_R = [None, 0.5, 1.0]
TRAIL_BUF = [0.15, 0.25, 0.40]
PARTIAL_AT = [1.5, 2.0]


def cells(variant: str):
    partials = PARTIAL_AT if variant.startswith("C") else [2.0]
    for be in BE_AT_R:
        for buf in TRAIL_BUF:
            for pa in partials:
                yield bt.Params(variant=variant, be_at_r=be, trail_buf=buf,
                                partial_at_r=pa)


def main() -> None:
    df = bt.load_bars()
    d, daily = bt.build_frame(df)
    warm = d.index[d["daily_bars"] >= bt.HTF_EMA_LEN]
    cutoff = max(warm[0] if len(warm) else d.index[0],
                 d.index[-1] - pd.Timedelta(days=bt.WINDOW_MONTHS * 31))
    start_i = int(d.index.searchsorted(cutoff))
    funding = bt.load_funding(d.index[start_i].to_pydatetime(),
                              d.index[-1].to_pydatetime())

    # The control has no swept parameters — one cell, and the bar everything
    # else is measured against.
    base = bt.metrics(bt.run(d, daily, bt.Params(variant="A"), funding, start_i))
    print(f"\n  control A: n={base['n']} PF={base['pf']:.2f} "
          f"maxDD={base['max_dd']:.1f}% net={base['net']:+.0f}")

    print("\n" + "=" * 96)
    print("  SWEEP — median cell per variant (D8)")
    print("=" * 96)
    print(f"  {'variant':6} {'cells':>6} {'med PF':>7} {'med DD%':>8} {'med net':>9} "
          f"{'med n':>6} {'best PF':>8} {'worst PF':>9} {'spread':>7}")
    print("  " + "-" * 92)

    detail: dict[str, list] = {}
    for variant in ("B", "B+P", "C", "C+P"):
        results = []
        for p in cells(variant):
            m = bt.metrics(bt.run(d, daily, p, funding, start_i))
            if m.get("n", 0):
                results.append((p, m))
        detail[variant] = results
        pfs = [m["pf"] for _, m in results]
        med_pf = statistics.median(pfs)
        print(f"  {variant:6} {len(results):6d} {med_pf:7.2f} "
              f"{statistics.median(m['max_dd'] for _, m in results):8.1f} "
              f"{statistics.median(m['net'] for _, m in results):9.0f} "
              f"{statistics.median(m['n'] for _, m in results):6.0f} "
              f"{max(pfs):8.2f} {min(pfs):9.2f} {max(pfs)-min(pfs):7.2f}")
    print("=" * 96)

    print("\n  Per-cell detail (PF), rows = be_at_r, cols = trail_buf:")
    for variant, results in detail.items():
        print(f"\n  {variant}")
        print("    be_at_r  " + "".join(f"{b:>10}" for b in TRAIL_BUF))
        for be in BE_AT_R:
            cellpfs = []
            for buf in TRAIL_BUF:
                got = [m["pf"] for p, m in results
                       if p.be_at_r == be and p.trail_buf == buf]
                cellpfs.append(statistics.median(got) if got else float("nan"))
            print(f"    {str(be):8} " + "".join(f"{v:10.2f}" for v in cellpfs))

    med_of_medians = {v: statistics.median(m["pf"] for _, m in r)
                      for v, r in detail.items()}
    best_variant = max(med_of_medians, key=med_of_medians.get)
    print(f"\n  Median-cell read: best variant by median PF is {best_variant} "
          f"({med_of_medians[best_variant]:.2f}) against control A "
          f"({base['pf']:.2f}).")
    if base["pf"] < 1.0:
        print("  The control loses money, so no cell in this grid is adoptable — "
              "a higher PF than a losing control is still a losing system. "
              "Nothing here is a reason to trade.")


if __name__ == "__main__":
    main()
