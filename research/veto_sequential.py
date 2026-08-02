"""Sequential one-at-a-time sim of the veto-scanner mechanism — the answer is NO.

veto_scanner.py proved "no veto → signal" clears all 4 gates *per bar*. But a
per-bar barrier stat lets every entry borrow up to 60 days of resolution time,
and overlapping bars are not independent trades. This script asks the tradeable
version: enter on EVERY clean 1h bar while flat, one position at a time,
±2.83% barrier, a real hold cap — how many trades/week, what weekly % at 1x?

Result (2026-08-02): dead at every cap and fee model.
  · 24h cap: WR collapses 52% → 28–32% (39–45% of trades time out)
  · 336h cap: WR recovers to ~51% but best cell (short, all-maker) makes
    +0.085%/week at 1x, fails both-halves, 100% drawdown at 5x — before the
    up-to-2-weeks of unmodeled funding that would eat what remains.
So the per-bar edge was an upper bound, not a strategy — the selection BEFORE
the veto filter (his setups) is load-bearing, exactly the harder branch the
veto_scanner docstring warned about.

Fee models (kraken futures tier 1, %/side maker 0.02 / taker 0.05):
  taker_all : entry, TP and SL all taker — measured FRICTION_PCT
  maker_real: maker entry + maker TP, but the SL is a stop = taker exit
  maker_all : everything maker (needs limit-only exits, optimistic)

    python3 research/veto_sequential.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.database import DB_PATH                    # noqa: E402
from app.geometry import FRICTION_PCT               # noqa: E402
from app.paths import RESULTS                       # noqa: E402
from app.setups import WARMUP, SetupEngine, vetoes  # noqa: E402

BARRIER = 2.8302          # same geometry as short_edge.json best
CAPS_H = (24, 72, 168, 336)
MAKER, TAKER = 0.02, 0.05
FEE_MODELS = [                        # (name, fee_pct on win, fee_pct on loss/timeout)
    ("taker_all", FRICTION_PCT, FRICTION_PCT),
    ("maker_real", 2 * MAKER, MAKER + TAKER),
    ("maker_all", 2 * MAKER, 2 * MAKER),
]
LEVERAGES = [1, 5, 10]


def load_rows():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True).execute(
        "SELECT ts, open, high, low, close, volume FROM ohlcv_cache "
        "WHERE symbol='binance:BTC/USDT' AND timeframe='1h' ORDER BY ts").fetchall()


def simulate(rows, clean, direction, cap_h):
    """clean[i] True if bar i is enterable. → list of (entry_idx, gross_pct, outcome)."""
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    n = len(rows)
    long_ = direction == "long"
    trades, i = [], WARMUP
    while i < n - 1:
        if not clean[i]:
            i += 1
            continue
        e = closes[i]
        tp = e * (1 + BARRIER / 100) if long_ else e * (1 - BARRIER / 100)
        sl = e * (1 - BARRIER / 100) if long_ else e * (1 + BARRIER / 100)
        exit_px, outcome, j_end = None, "timeout", min(i + cap_h, n - 1)
        for j in range(i + 1, j_end + 1):
            sl_hit = lows[j] <= sl if long_ else highs[j] >= sl
            tp_hit = highs[j] >= tp if long_ else lows[j] <= tp
            if sl_hit:                      # both barriers in one bar → SL first
                exit_px, outcome, j_end = sl, "loss", j
                break
            if tp_hit:
                exit_px, outcome, j_end = tp, "win", j
                break
        if exit_px is None:
            exit_px = closes[j_end]
        gross = (exit_px / e - 1) * 100 * (1 if long_ else -1)
        trades.append((i, gross, outcome))
        i = j_end + 1                       # flat again next bar
    return trades


def summarize(trades, weeks, half_idx):
    def mean_net(sub, fee_win, fee_loss):
        if not sub:
            return None
        nets = [g - (fee_win if o == "win" else fee_loss) for _, g, o in sub]
        return sum(nets) / len(nets)

    out = {"trades": len(trades), "per_week": len(trades) / weeks,
           "win_rate": sum(1 for t in trades if t[2] == "win") / len(trades),
           "timeout_rate": sum(1 for t in trades if t[2] == "timeout") / len(trades),
           "models": {}}
    for name, fw, fl in FEE_MODELS:
        nets = [g - (fw if o == "win" else fl) for _, g, o in trades]
        mean = sum(nets) / len(nets)
        h1 = mean_net([t for t in trades if t[0] < half_idx], fw, fl)
        h2 = mean_net([t for t in trades if t[0] >= half_idx], fw, fl)
        levs = {}
        for lv in LEVERAGES:
            eq, peak, mdd = 1.0, 1.0, 0.0
            for r in nets:
                eq *= 1 + lv * r / 100
                peak = max(peak, eq)
                mdd = max(mdd, 1 - eq / peak)
                if eq <= 0:
                    eq = 0.0
                    break
            wk = (eq ** (1 / weeks) - 1) * 100 if eq > 0 else None
            levs[f"{lv}x"] = {"weekly_geo_pct": wk, "max_dd_pct": mdd * 100,
                              "final_multiple": eq}
        out["models"][name] = {
            "net_per_trade_pct": mean,
            "weekly_arith_pct_1x": mean * out["per_week"],
            "h1_net": h1, "h2_net": h2,
            "both_halves_positive": bool(h1 and h2 and h1 > 0 and h2 > 0),
            "leverage": levs,
        }
    return out


def main():
    rows = load_rows()
    weeks = len(rows) / 24 / 7
    half_idx = len(rows) // 2
    print(f"{len(rows):,} bars ({weeks:.0f} weeks) · barrier ±{BARRIER}%")

    eng = SetupEngine(rows)
    clean = {"long": [False] * len(rows), "short": [False] * len(rows)}
    for i in range(WARMUP, len(rows) - 1):
        ctx = eng.context(i)
        for d in ("long", "short"):
            clean[d][i] = not vetoes(ctx, d)
    # note: "exactly one side clean" cells were tested and are identical to
    # these — the vetoes never leave both directions clean on the same bar.

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "barrier_pct": BARRIER,
           "fee_models": {n: {"win": fw, "loss": fl} for n, fw, fl in FEE_MODELS},
           "note": "sequential one-at-a-time sim of veto_scanner's mechanism; "
                   "trade-every-clean-bar fails every cap and fee model",
           "cells": {}}
    for cap in CAPS_H:
        for d in ("long", "short"):
            s = summarize(simulate(rows, clean[d], d, cap), weeks, half_idx)
            out["cells"][f"{d}_{cap}h"] = s
            m = s["models"]
            print(f"\n{d} cap {cap}h: {s['trades']} trades · {s['per_week']:.2f}/wk · "
                  f"WR {s['win_rate']:.1%} · timeout {s['timeout_rate']:.1%}")
            for name in m:
                r = m[name]
                print(f"  {name:10s} net/trade {r['net_per_trade_pct']:+.4f}%  "
                      f"weekly(1x) {r['weekly_arith_pct_1x']:+.4f}%  "
                      f"halves {'++' if r['both_halves_positive'] else '--'}")

    dest = RESULTS / "veto_sequential.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"\n→ wrote {dest}")


def _selfcheck():
    rows = [(i, 100, 100, 100, 100, 0) for i in range(10)]
    rows[3] = (3, 100, 103, 100, 103, 0)   # TP bar for a long from close 100
    clean = [False] * 10
    clean[2] = True
    global WARMUP
    WARMUP = 0
    t = simulate(rows, clean, "long", 24)
    assert len(t) == 1 and t[0][2] == "win" and abs(t[0][1] - BARRIER) < 0.2, t
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--check" in sys.argv else main()
