"""Do HIS entries beat a random one — and at which geometry?

Everything measured so far conflates two different things: where he chose to get
in, and when he chose to get out. The book's 39.4%-at-1.31R is the product of
both, and its 2.1-hour median hold means the exits dominate. That makes the
important question unanswerable from the P&L alone:

    Is the entry selection worth anything, independent of the exits?

This replays every real entry — same price, same direction, same moment — forward
through actual hourly bars to whichever barrier is hit first, at a grid of
geometries. Holding is removed as a variable: every trade is held to resolution.
What remains is the entry.

Then each result is priced against the SAME barrier replay run from random bars
(results/barrier_baseline.json), so the output is an edge in percentage points
over chance rather than a win rate floating free of its baseline. A 22% win rate
means nothing until you know a coin gets 20.7%.

Split three ways, because the ledger's own tags claim they differ:
  ALL      every entry
  NON-VETO entries the discipline rules would have allowed
  VETO     entries the rules flag — the "#1 money lever" claim, tested

Conservative on ties, same as barrier_test.py: a bar spanning both barriers is
recorded as a loss.

    python3 research/entry_edge.py
"""
from __future__ import annotations

import bisect
import json
import sqlite3
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.database import DB_PATH              # noqa: E402
from app.geometry import FRICTION_PCT, solve  # noqa: E402
from app.paths import RESULTS                 # noqa: E402

SYMBOL = "binance:BTC/USDT"
MAX_HOURS = 24 * 60
RRS = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0]


def load_bars():
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT ts, high, low, close FROM ohlcv_cache WHERE symbol=? "
        "AND timeframe='1h' ORDER BY ts ASC", (SYMBOL,)).fetchall()
    return [(int(t), float(h), float(l), float(c)) for t, h, l, c in rows]


def load_trades():
    """Real entries: (ts_ms, direction, entry_price, setup_tag)."""
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT opened_at, direction, entry, setup_tag FROM trades "
        "WHERE entry IS NOT NULL AND direction IN ('long','short') "
        "ORDER BY opened_at ASC").fetchall()
    out = []
    for opened, d, entry, tag in rows:
        try:
            s = opened.replace("Z", "")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            out.append((int(dt.timestamp() * 1000), d, float(entry), tag or "NONE"))
        except Exception:
            continue
    return out


def replay(bars, ts_index, trades, stop_pct: float, target_pct: float) -> dict:
    """Every entry walked forward to a barrier. Returns win rate + holds."""
    wins = losses = skipped = 0
    holds = []
    for ts, d, entry, _tag in trades:
        i = bisect.bisect_left(ts_index, ts)
        if i >= len(bars) - 1:
            skipped += 1
            continue
        long_ = d == "long"
        if long_:
            tp, sl = entry * (1 + target_pct / 100), entry * (1 - stop_pct / 100)
        else:
            tp, sl = entry * (1 - target_pct / 100), entry * (1 + stop_pct / 100)
        end = min(i + MAX_HOURS, len(bars))
        for j in range(i, end):
            _, hi, lo, _c = bars[j]
            hit_sl = lo <= sl if long_ else hi >= sl
            hit_tp = hi >= tp if long_ else lo <= tp
            if hit_sl:
                losses += 1; holds.append(j - i); break
            if hit_tp:
                wins += 1; holds.append(j - i); break
        else:
            skipped += 1

    n = wins + losses
    if not n:
        return {}
    wr = wins / n
    net = wr * (target_pct - FRICTION_PCT) - (1 - wr) * (stop_pct + FRICTION_PCT)
    return {"n": n, "wins": wins, "unresolved": skipped, "win_rate": wr,
            "net_pct": net, "median_hold_h": statistics.median(holds),
            "breakeven_wr": (stop_pct + FRICTION_PCT)
                            / ((target_pct - FRICTION_PCT) + (stop_pct + FRICTION_PCT))}


def trades_per_week(trades) -> float:
    if len(trades) < 2:
        return 0.0
    span_wk = (trades[-1][0] - trades[0][0]) / 1000 / 86400 / 7
    return len(trades) / span_wk if span_wk > 0 else 0.0


def main() -> None:
    bars = load_bars()
    ts_index = [b[0] for b in bars]
    trades = load_trades()
    with open(RESULTS / "barrier_baseline.json") as fh:
        bl = json.load(fh)
    sigma = bl["sigma"]

    non_veto = [t for t in trades if not str(t[3]).startswith("VETO")]
    veto = [t for t in trades if str(t[3]).startswith("VETO")]

    tpw_all = trades_per_week(trades)
    # Live-era rate matters more than lifetime: cadence changed.
    recent = [t for t in trades if t[0] >= trades[-1][0] - 90 * 86400 * 1000]
    tpw_recent = trades_per_week(recent)

    print(f"{len(trades)} entries  {len(non_veto)} non-VETO  {len(veto)} VETO")
    print(f"cadence: {tpw_all:.2f}/wk lifetime · {tpw_recent:.2f}/wk last 90d "
          f"({len(recent)} trades)")
    print(f"friction {FRICTION_PCT:.2f}%  ·  baseline from {bl['bars']:,} random entries\n")

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "n_entries": len(trades), "n_non_veto": len(non_veto), "n_veto": len(veto),
           "trades_per_week": tpw_all, "trades_per_week_90d": tpw_recent,
           "sigma": sigma, "friction_pct": FRICTION_PCT, "cells": []}

    groups = [("ALL", trades), ("NON-VETO", non_veto), ("VETO", veto)]
    print(f"  {'R:R':>4} {'stop':>6} {'target':>7} {'group':>9} {'n':>5} "
          f"{'WR':>7} {'random':>7} {'EDGE':>8} {'BE':>7} {'hold':>7} {'net/trade':>11}")
    for rr in RRS:
        g = solve(sigma, 2.5, rr)
        rand_wr = bl["rr_baseline"][str(rr)]["win_rate"]
        for label, ts_group in groups:
            if len(ts_group) < 20:
                continue
            r = replay(bars, ts_index, ts_group, g["stop_pct"], g["target_pct"])
            if not r:
                continue
            edge = (r["win_rate"] - rand_wr) * 100

            # Two guards against reading noise as edge. Both are mandatory here
            # because this repo has already shipped one mined edge (S1–S5) that
            # looked strong in-sample and died out of sample.
            #
            #   z  — is the win rate distinguishable from its own breakeven at
            #        this n at all?
            #   split-half — does it hold in BOTH halves of the book, in time
            #        order? An edge present only in the first half is decay or
            #        luck, never a system.
            w, n_ = r["win_rate"], r["n"]
            se = (w * (1 - w) / n_) ** 0.5 if n_ else 0
            z = (w - r["breakeven_wr"]) / se if se else 0
            chrono = sorted(ts_group, key=lambda t: t[0])
            half = len(chrono) // 2
            h1 = replay(bars, ts_index, chrono[:half], g["stop_pct"], g["target_pct"])
            h2 = replay(bars, ts_index, chrono[half:], g["stop_pct"], g["target_pct"])
            both = bool(h1 and h2 and h1["net_pct"] > 0 and h2["net_pct"] > 0)

            out["cells"].append({
                "rr": rr, "group": label, "stop_pct": g["stop_pct"],
                "target_pct": g["target_pct"], "n": r["n"],
                "win_rate": r["win_rate"], "random_wr": rand_wr, "edge_pp": edge,
                "breakeven_wr": r["breakeven_wr"], "net_pct": r["net_pct"],
                "median_hold_h": r["median_hold_h"],
                "z": z, "significant": abs(z) > 1.96,
                "h1_wr": h1.get("win_rate") if h1 else None,
                "h2_wr": h2.get("win_rate") if h2 else None,
                "h1_net": h1.get("net_pct") if h1 else None,
                "h2_net": h2.get("net_pct") if h2 else None,
                "both_halves": both,
            })
            print(f"  {rr:>4.0f} {g['stop_pct']:>5.2f}% {g['target_pct']:>6.2f}% "
                  f"{label:>9} {r['n']:>5} {r['win_rate']:>6.1%} {rand_wr:>6.1%} "
                  f"{edge:>+7.1f}pp {r['breakeven_wr']:>6.1%} "
                  f"{r['median_hold_h']:>6.0f}h {r['net_pct']:>+10.4f}%")

    path = RESULTS / "entry_edge.json"
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n  → wrote {path}")

    # ── what his measured entry edge is worth per week ──────────────────────
    print("\n  Weekly return from the MEASURED entry edge, at his own cadence")
    print(f"  {'R:R':>4} {'group':>9} {'WR':>7} {'risk':>6} {'lev':>6} "
          f"{'tr/wk':>6} {'per trade':>10} {'per week':>9}")
    survivors = [c for c in out["cells"] if c["net_pct"] > 0 and c["both_halves"]]
    print(f"\n  cells positive in BOTH halves: {len(survivors)} of {len(out['cells'])}")
    if not survivors:
        print("  ⚠ every positive cell is first-half only — the same failure mode")
        print("    that disarmed S1–S5. Nothing here is a validated edge yet.")
    out["survivors"] = len(survivors)

    best = []
    for c in out["cells"]:
        if c["net_pct"] <= 0:
            continue
        for risk in (2.0, 3.0, 5.0):
            lev = risk / (c["stop_pct"] + FRICTION_PCT)
            per = c["net_pct"] * lev
            for tpw, tag in ((tpw_recent, "90d"), (10.0, "10/wk")):
                wk = (1 + per / 100) ** tpw - 1
                best.append((wk, c, risk, lev, tpw, tag, per))
    for wk, c, risk, lev, tpw, tag, per in sorted(best, reverse=True)[:10]:
        print(f"  {c['rr']:>4.0f} {c['group']:>9} {c['win_rate']:>6.1%} "
              f"{risk:>5.1f}% {lev:>5.2f}x {tpw:>5.1f} {per:>+9.3f}% {wk:>+8.2%}")
    if not best:
        print("    no cell has a positive edge — nothing to compound")


if __name__ == "__main__":
    main()
