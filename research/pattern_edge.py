"""Do chart patterns carry edge at day-trade geometry, on every timeframe?

The open problem is cadence, not edge: the one validated cell (short non-VETO,
2.83/2.83) pays +0.726%/trade but fires 1.51×/week against a plan that wants 7.
Chart patterns are the proposed fix — they are what he reads by eye, and an
auto-pattern indicator marks them on the 5m all day long.

This asks the only question that matters about them: taken as entry signals and
resolved against symmetric barriers, do they beat taking EVERY bar on the same
timeframe over the same window? A pattern that does not beat all-bars is not a
signal, it is exposure with extra steps.

Three things this is careful about, because each one silently manufactures edge:

  · Causality. Every mask comes from app/patterns.py, where pivots are shifted
    by their confirmation lag and HTF series are shifted one HTF bar. A pattern
    you can only draw in hindsight is not tradeable, and the indicator on the
    screenshot repaints exactly this way.
  · The baseline is per-timeframe and per-direction. BTC fell over this window,
    which flatters every short.
  · Hold is capped at 24h. A "5m signal" held six weeks is not a day trade, and
    letting it run is how a scalp backtest quietly becomes a swing backtest.

Geometry is swept because barrier SIZE is the binding constraint at leverage:
with friction f, symmetric barriers b need a win rate of (b+f)/(2b) just to
break even. That wall is at 65% for b=1.0% and 87.5% for b=0.4%. Small barriers
do not fail because patterns are bad; they fail because friction is fixed.

    python3 research/pattern_edge.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.database import DB_PATH                  # noqa: E402
from app.geometry import FRICTION_PCT             # noqa: E402
from app.patterns import pattern_masks            # noqa: E402
from app.paths import RESULTS                     # noqa: E402
from research.barrier_test import simulate        # noqa: E402

SYMBOL = "bybit:BTC/USDT:USDT"       # one venue for all frames = comparable
TIMEFRAMES = ["5m", "15m", "1h", "4h"]
TF_MIN = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
BARRIERS = [0.5, 1.0, 1.5, 2.0, 2.8302]   # symmetric, 1:1
HOLD_CAP_H = 24                            # day trade, not swing
LEVERAGE = 10                              # his stated size, for account maths
MIN_N = 30

# Which way a pattern points. This is the pattern's own claim, not a fit.
DIRECTION = {
    ("pattern", "double_top"): "short", ("pattern", "double_bottom"): "long",
    ("structure", "up"): "long",       ("structure", "down"): "short",
    ("breakout", "up"): "long",        ("breakout", "down"): "short",
    ("htf4h", "up"): "long",           ("htf4h", "down"): "short",
    ("htf1d", "up"): "long",           ("htf1d", "down"): "short",
}


def load(timeframe: str) -> pd.DataFrame:
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT ts, open, high, low, close, volume FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe=? ORDER BY ts ASC",
        (SYMBOL, timeframe)).fetchall()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.astype(float)


def breakeven_wr(b: float) -> float:
    return (b + FRICTION_PCT) / ((b - FRICTION_PCT) + (b + FRICTION_PCT))


def assess(bars, idx, b, direction, cap, span_weeks, baseline_wr) -> dict | None:
    """One (mask, geometry) cell: resolve it, and split it in half."""
    if len(idx) < MIN_N:
        return None
    r = simulate(bars, b, b, direction, entries=idx, max_bars=cap)
    if not r or r["n"] < MIN_N:
        return None

    mid = len(idx) // 2
    halves = []
    for sub in (idx[:mid], idx[mid:]):
        h = simulate(bars, b, b, direction, entries=sub, max_bars=cap)
        halves.append(h["net_pct"] if h and h["n"] >= 10 else None)

    per_week = len(idx) / span_weeks if span_weeks else 0.0
    return {
        "n": r["n"], "win_rate": r["win_rate"], "net_pct": r["net_pct"],
        "breakeven_wr": r["breakeven_wr"], "baseline_wr": baseline_wr,
        "edge_pp": (r["win_rate"] - baseline_wr) * 100,
        "per_week": per_week,
        # What his stated 10x sizing turns this into, before compounding.
        "acct_pct_per_week": per_week * r["net_pct"] * LEVERAGE,
        "halves": halves,
        "g1_beats_all_bars": r["win_rate"] > baseline_wr,
        "g2_net_positive": r["net_pct"] > 0,
        "g3_both_halves": all(h is not None and h > 0 for h in halves),
    }


def main() -> None:
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "symbol": SYMBOL, "friction_pct": FRICTION_PCT,
           "hold_cap_h": HOLD_CAP_H, "leverage": LEVERAGE, "cells": []}

    print(f"friction {FRICTION_PCT}% · hold capped {HOLD_CAP_H}h · symmetric 1:1 · "
          f"{LEVERAGE}x for account maths\n")
    print("  breakeven win rate by barrier size (pure arithmetic, no data):")
    print("   " + "  ".join(f"{b:.2f}%→{breakeven_wr(b):.1%}" for b in BARRIERS) + "\n")

    for tf in TIMEFRAMES:
        df = load(tf)
        if len(df) < 500:
            print(f"{tf}: only {len(df)} bars, skipped\n")
            continue
        bars = list(zip(df["ts"].astype("int64"), df["high"], df["low"], df["close"]))
        cap = max(1, HOLD_CAP_H * 60 // TF_MIN[tf])
        span_weeks = (bars[-1][0] - bars[0][0]) / 1000 / 86400 / 7
        masks = pattern_masks(df)

        # Add the thing he actually described: read the pattern on the low
        # timeframe, take it only when the 4h agrees.
        for key in [("pattern", "double_top"), ("pattern", "double_bottom"),
                    ("breakout", "up"), ("breakout", "down"),
                    ("structure", "up"), ("structure", "down")]:
            side = DIRECTION[key]
            htf = masks[("htf4h", "up" if side == "long" else "down")]
            combo = (key[0] + "+4h", key[1])
            masks[combo] = masks[key] & htf
            DIRECTION[combo] = side

        print(f"═══ {tf}  ({len(df):,} bars · {df.index[0].date()} → "
              f"{df.index[-1].date()} · {span_weeks:.0f} weeks · hold cap {cap} bars)")
        print(f"  {'setup':>22} {'bar':>6} {'n':>6} {'WR':>7} {'base':>7} {'edge':>7} "
              f"{'BE':>7} {'net%':>8} {'/wk':>7} {'acct%/wk':>9}  gates")

        for b in BARRIERS:
            # Gate-1 baseline: every bar, same frame, same direction, same geometry.
            step = max(1, len(bars) // 8000)
            base = {d: simulate(bars, b, b, d, step=step, max_bars=cap)
                    for d in ("long", "short")}
            for key, mask in sorted(masks.items()):
                direction = DIRECTION[key]
                bw = base[direction].get("win_rate")
                if bw is None:
                    continue
                idx = [i for i, v in enumerate(mask) if v and i < len(bars) - 1]
                c = assess(bars, idx, b, direction, cap, span_weeks, bw)
                if not c:
                    continue
                c.update({"timeframe": tf, "slot": key[0], "option": key[1],
                          "direction": direction, "barrier_pct": b})
                out["cells"].append(c)
                g = sum([c["g1_beats_all_bars"], c["g2_net_positive"], c["g3_both_halves"]])
                flag = "  ***" if g == 3 else ""
                print(f"  {key[0] + '/' + key[1]:>22} {b:>5.2f}% {c['n']:>6,} "
                      f"{c['win_rate']:>6.1%} {bw:>6.1%} {c['edge_pp']:>+6.1f} "
                      f"{c['breakeven_wr']:>6.1%} {c['net_pct']:>+8.3f} "
                      f"{c['per_week']:>7.1f} {c['acct_pct_per_week']:>+9.1f}  {g}/3{flag}")
        print()

    survivors = [c for c in out["cells"] if c["g1_beats_all_bars"]
                 and c["g2_net_positive"] and c["g3_both_halves"]]
    out["survivors"] = len(survivors)
    print(f"═══ {len(survivors)} of {len(out['cells'])} cells pass all three gates")
    for c in sorted(survivors, key=lambda x: -x["acct_pct_per_week"])[:12]:
        print(f"  {c['timeframe']:>4} {c['slot']}/{c['option']:<16} {c['direction']:>5} "
              f"{c['barrier_pct']:.2f}%  n={c['n']:<6,} WR {c['win_rate']:.1%} "
              f"net {c['net_pct']:+.3f}%  {c['per_week']:.1f}/wk  "
              f"→ {c['acct_pct_per_week']:+.1f}% acct/wk at {LEVERAGE}x")

    (RESULTS / "pattern_edge.json").write_text(json.dumps(out, indent=1))
    print(f"\nwrote {RESULTS / 'pattern_edge.json'}")


def _selfcheck() -> None:
    """The one thing that must not break: entry filtering and the hold cap."""
    bars = [(i * 3600_000, 100.0 + i, 100.0 - i, 100.0) for i in range(50)]
    all_ = simulate(bars, 5.0, 5.0, "long")
    two = simulate(bars, 5.0, 5.0, "long", entries=[0, 1])
    assert two["n"] == 2 < all_["n"], (two["n"], all_["n"])
    # The cap must bind: entries too close to a barrier-touch expire unresolved.
    wide = simulate(bars, 5.0, 5.0, "long", entries=list(range(40)))
    tight = simulate(bars, 5.0, 5.0, "long", entries=list(range(40)), max_bars=1)
    assert tight["n"] < wide["n"], (tight["n"], wide["n"])
    assert abs(breakeven_wr(2.8302) - 0.553) < 0.001, breakeven_wr(2.8302)
    assert abs(breakeven_wr(1.0) - 0.65) < 0.001, breakeven_wr(1.0)
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
