"""Can the VETO rules alone BE the scanner?

The validated edge is "non-VETO shorts", and until now that has been treated as
unscannable because it was measured on trades he chose. But the VETO half of it
was never discretionary: `setups.vetoes()` is seven mechanical rules over a bar's
own context, and it can be evaluated on any bar in history, not just on his fills.

So the question is sharp and answerable: if you entered a short on EVERY bar with
no veto against it, would that beat a coin flip in the same window and direction?

  If yes — the mechanism already exists in the codebase and has for weeks. The
  scanner becomes "no veto → signal", frequency stops being the problem, and the
  discretionary part of his edge was never the load-bearing half.

  If no — then the VETO rules only work as a filter on entries he already wanted
  to take, and the selection he applies before the filter is doing the work. That
  is a much harder thing to automate, and worth knowing before trying.

Both directions, same gates as everything else: beat a period- and
direction-matched random baseline, stay positive in both halves, survive a
permutation test.

    python3 research/veto_scanner.py
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.database import DB_PATH                       # noqa: E402
from app.geometry import FRICTION_PCT                  # noqa: E402
from app.paths import RESULTS                          # noqa: E402
from app.setups import WARMUP, SetupEngine, vetoes     # noqa: E402

MAX_HOURS = 24 * 60
N_PERM = 3000
SEED = 42


def load_rows():
    return sqlite3.connect(DB_PATH).execute(
        "SELECT ts, open, high, low, close, volume FROM ohlcv_cache "
        "WHERE symbol='binance:BTC/USDT' AND timeframe='1h' ORDER BY ts").fetchall()


def resolve(rows, sl_pct, tp_pct, direction):
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    n = len(rows)
    out = [None] * n
    long_ = direction == "long"
    for i in range(n - 1):
        e = closes[i]
        if long_:
            tp, sl = e * (1 + tp_pct / 100), e * (1 - sl_pct / 100)
        else:
            tp, sl = e * (1 - tp_pct / 100), e * (1 + sl_pct / 100)
        for j in range(i + 1, min(i + 1 + MAX_HOURS, n)):
            if (lows[j] <= sl) if long_ else (highs[j] >= sl):
                out[i] = False; break
            if (highs[j] >= tp) if long_ else (lows[j] <= tp):
                out[i] = True; break
    return out


def stats(sel, outc, sl, tp):
    res = [outc[i] for i in sel if outc[i] is not None]
    if not res:
        return None
    w = sum(res) / len(res)
    return {"n": len(res), "win_rate": w,
            "net_pct": w * (tp - FRICTION_PCT) - (1 - w) * (sl + FRICTION_PCT)}


def main() -> None:
    random.seed(SEED)
    cfg = json.load(open(RESULTS / "short_edge.json"))["best"]
    SL, TP = cfg["stop_pct"], cfg["target_pct"]
    rows = load_rows()
    print(f"{len(rows):,} bars · geometry {SL:.2f}%/{TP:.2f}% (R:R {cfg['rr']:.0f})")

    print("building contexts and evaluating vetoes on every bar…", flush=True)
    eng = SetupEngine(rows)
    no_veto = {"long": [], "short": []}
    veto = {"long": [], "short": []}
    for i in range(WARMUP, len(rows) - 1):
        ctx = eng.context(i)
        for d in ("long", "short"):
            (no_veto if not vetoes(ctx, d) else veto)[d].append(i)
    for d in ("long", "short"):
        tot = len(no_veto[d]) + len(veto[d])
        print(f"  {d}: {len(no_veto[d]):,} clean bars of {tot:,} "
              f"({len(no_veto[d])/tot:.1%})")

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "bars": len(rows), "stop_pct": SL, "target_pct": TP, "cells": []}
    weeks = len(rows) / 24 / 7
    half = len(rows) // 2

    for d in ("long", "short"):
        print(f"\nresolving {d}…", flush=True)
        outc = resolve(rows, SL, TP, d)
        allsel = [i for i in range(WARMUP, len(rows) - 1) if outc[i] is not None]
        base = stats(allsel, outc, SL, TP)
        clean = stats(no_veto[d], outc, SL, TP)
        dirty = stats(veto[d], outc, SL, TP)
        if not clean:
            continue

        h1 = stats([i for i in no_veto[d] if i < half], outc, SL, TP)
        h2 = stats([i for i in no_veto[d] if i >= half], outc, SL, TP)

        # permutation: is "no veto" better than a random subset of the same size?
        pool = [outc[i] for i in allsel]
        k = clean["n"]
        ge = sum(1 for _ in range(N_PERM)
                 if sum(random.sample(pool, k)) / k >= clean["win_rate"])
        p = ge / N_PERM

        edge = (clean["win_rate"] - base["win_rate"]) * 100
        per_week = clean["n"] / weeks
        print(f"  ALL bars      {base['win_rate']:.2%}  net {base['net_pct']:+.3f}%")
        print(f"  NO VETO       {clean['win_rate']:.2%}  net {clean['net_pct']:+.3f}%  "
              f"({edge:+.2f}pp)  n={clean['n']:,}  {per_week:.1f}/wk")
        if dirty:
            print(f"  VETO'd        {dirty['win_rate']:.2%}  net {dirty['net_pct']:+.3f}%")
        print(f"  halves        H1 {h1['net_pct']:+.3f}%   H2 {h2['net_pct']:+.3f}%")
        print(f"  permutation   p = {p:.4f}")

        gates = {
            "beats_all_bars": clean["win_rate"] > base["win_rate"],
            "net_positive": clean["net_pct"] > 0,
            "both_halves": h1["net_pct"] > 0 and h2["net_pct"] > 0,
            "permutation": p < 0.05,
        }
        print(f"  gates         {sum(gates.values())}/4 "
              f"{'✓ MECHANISM' if all(gates.values()) else '✗'}")
        out["cells"].append({
            "direction": d, "all_bars": base, "no_veto": clean, "veto": dirty,
            "edge_pp": edge, "per_week": per_week, "perm_p": p,
            "h1_net": h1["net_pct"], "h2_net": h2["net_pct"],
            "gates": gates, "gates_passed": sum(gates.values()),
        })

    with open(RESULTS / "veto_scanner.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n→ wrote {RESULTS / 'veto_scanner.json'}")

    good = [c for c in out["cells"] if c["gates_passed"] == 4]
    if good:
        print("\nTHE MECHANISM EXISTS. Directions that clear every gate:")
        for c in good:
            print(f"  {c['direction']}: {c['no_veto']['win_rate']:.2%} vs "
                  f"{c['all_bars']['win_rate']:.2%}, {c['per_week']:.1f}/wk, "
                  f"net {c['no_veto']['net_pct']:+.3f}%")
    else:
        print("\nNo direction clears every gate on 'no veto' alone.")
        print("The VETO rules filter entries he already wanted; they do not")
        print("generate them. The selection BEFORE the filter is the edge.")


if __name__ == "__main__":
    main()
