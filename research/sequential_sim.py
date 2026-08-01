"""One position at a time, sized to hit 10%/week. What actually survives?

`pattern_edge.py` counted every signal a setup fires. That is wrong for how he
trades: he holds ONE position, so a signal arriving mid-trade is not a trade, it
is a signal he never sees. Cadence therefore is not "how often does this fire",
it is "how often is it flat AND firing", which is a much smaller number, and the
per-signal statistics do not survive the substitution unchanged.

So this replays the book the way the account experiences it — enter, hold to a
barrier or to the 24h cap, go flat, and only then look for the next signal —
and compounds a real equity curve through it.

The question is not "is there edge" but his actual question: does it print
5–20% a week? Edge is necessary and not sufficient, because size converts edge
into weekly return and drawdown at the same rate. So for every setup the sizing
is SOLVED rather than assumed: find the leverage that lands the weekly return on
10%, then report what that leverage does to the worst drawdown. A setup that
needs 40x to reach the band has answered the question with a no.

Two things kept honest:

  · Positions that hit the 24h cap are closed at the market price, not thrown
    away. Discarding them silently deletes the trades that went nowhere, which
    are the ones that pay friction for no move.
  · Liquidation is checked per trade. At high leverage a stop is a wipeout, and
    an equity curve that goes through zero and comes back is fiction.

    python3 research/sequential_sim.py
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

SYMBOL = "bybit:BTC/USDT:USDT"
TIMEFRAMES = ["5m", "15m", "1h", "4h"]
TF_MIN = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
BARRIERS = [0.5, 1.0, 1.5, 2.0, 2.8302]
HOLD_CAP_H = 24
MIN_TRADES = 30

# His band. Below 5%/wk it does not reach the goal; above 20%/wk he does not
# want the risk that comes with it. Outside the band is not a result.
WEEK_LO, WEEK_HI, WEEK_TARGET = 0.05, 0.20, 0.10
MAX_LEVERAGE = 50.0          # past this the stop is a liquidation anyway

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


def sequential(bars, mask, b, direction, cap):
    """Flat → signal → hold to a barrier or the cap → flat. Returns the raw
    per-trade % move on price (friction not yet applied), in order."""
    n = len(bars)
    long_ = direction == "long"
    moves, holds, i = [], [], 0
    while i < n - 1:
        if not mask[i]:
            i += 1
            continue
        entry = bars[i][3]
        tp = entry * (1 + b / 100) if long_ else entry * (1 - b / 100)
        sl = entry * (1 - b / 100) if long_ else entry * (1 + b / 100)
        end = min(i + 1 + cap, n)
        for j in range(i + 1, end):
            _, hi, lo, close = bars[j]
            hit_sl = lo <= sl if long_ else hi >= sl
            hit_tp = hi >= tp if long_ else lo <= tp
            if hit_sl:                       # stop wins ties, deliberately
                moves.append(-b)
                break
            if hit_tp:
                moves.append(b)
                break
        else:
            j = end - 1                      # cap reached: close at market
            close = bars[j][3]
            pct = (close - entry) / entry * 100
            moves.append(pct if long_ else -pct)
        holds.append(j - i)
        i = j                                # flat again at the exit bar
    return moves, holds


def equity(moves, lev):
    """Compound the account. Returns (growth_factor, max_drawdown, blown)."""
    eq = peak = 1.0
    dd = 0.0
    for m in moves:
        eq *= 1 + lev * (m - FRICTION_PCT) / 100
        if eq <= 0:
            return 0.0, 1.0, True
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return eq, dd, False


def solve_leverage(moves, weeks, target=WEEK_TARGET):
    """Smallest leverage whose compounded weekly return reaches `target`."""
    def weekly(lev):
        eq, _, blown = equity(moves, lev)
        return -1.0 if blown or eq <= 0 else eq ** (1 / weeks) - 1
    if weekly(MAX_LEVERAGE) < target:
        return None
    lo, hi = 0.01, MAX_LEVERAGE
    for _ in range(60):
        mid = (lo + hi) / 2
        if weekly(mid) < target:
            lo = mid
        else:
            hi = mid
    return hi


def main() -> None:
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "symbol": SYMBOL, "friction_pct": FRICTION_PCT,
           "hold_cap_h": HOLD_CAP_H, "one_position_at_a_time": True,
           "band": [WEEK_LO, WEEK_HI], "cells": []}

    print(f"ONE position at a time · hold capped {HOLD_CAP_H}h · friction "
          f"{FRICTION_PCT}% round trip · stop = target (1:1)")
    print(f"Target {WEEK_TARGET:.0%}/week, acceptable {WEEK_LO:.0%}–{WEEK_HI:.0%}. "
          f"Leverage is SOLVED to hit the target, then judged on drawdown.\n")

    for tf in TIMEFRAMES:
        df = load(tf)
        if len(df) < 500:
            continue
        bars = list(zip(df["ts"].astype("int64"), df["high"], df["low"], df["close"]))
        cap = max(1, HOLD_CAP_H * 60 // TF_MIN[tf])
        weeks = (bars[-1][0] - bars[0][0]) / 1000 / 86400 / 7
        masks = pattern_masks(df)
        for key in [("pattern", "double_top"), ("pattern", "double_bottom"),
                    ("breakout", "up"), ("breakout", "down"),
                    ("structure", "up"), ("structure", "down")]:
            side = DIRECTION[key]
            combo = (key[0] + "+4h", key[1])
            masks[combo] = masks[key] & masks[("htf4h", "up" if side == "long" else "down")]
            DIRECTION[combo] = side

        print(f"═══ {tf}  ({len(df):,} bars · {weeks:.0f} weeks · hold cap {cap} bars)")
        print(f"  {'setup':>24} {'stop':>6} {'trades':>7} {'/wk':>5} {'win%':>6} "
              f"{'avg move':>9} {'hold':>6} {'lev for 10%':>12} {'worst DD':>9}")

        for b in BARRIERS:
            for key, mask in sorted(masks.items()):
                direction = DIRECTION[key]
                moves, holds = sequential(bars, mask, b, direction, cap)
                if len(moves) < MIN_TRADES:
                    continue
                per_week = len(moves) / weeks
                wins = sum(1 for m in moves if m > 0)
                wr = wins / len(moves)
                avg = sum(moves) / len(moves)
                mean_hold_h = sum(holds) / len(holds) * TF_MIN[tf] / 60
                lev = solve_leverage(moves, weeks)

                mid = len(moves) // 2
                halves = [sum(s) / len(s) - FRICTION_PCT for s in (moves[:mid], moves[mid:])]

                cell = {"timeframe": tf, "slot": key[0], "option": key[1],
                        "direction": direction, "barrier_pct": b,
                        "trades": len(moves), "per_week": per_week, "win_rate": wr,
                        "avg_move_pct": avg, "net_per_trade": avg - FRICTION_PCT,
                        "mean_hold_h": mean_hold_h,
                        "lev_for_target": lev, "halves_net": halves}
                if lev:
                    _, dd, _ = equity(moves, lev)
                    cell["dd_at_target"] = dd
                    cell["in_band"] = lev <= MAX_LEVERAGE and dd < 0.5
                else:
                    cell["dd_at_target"] = None
                    cell["in_band"] = False
                out["cells"].append(cell)

                lev_s = f"{lev:.1f}x" if lev else "impossible"
                dd_s = f"{cell['dd_at_target']:.0%}" if lev else "—"
                mark = "  <<<" if cell["in_band"] and all(h > 0 for h in halves) else ""
                print(f"  {key[0] + '/' + key[1]:>24} {b:>5.2f}% {len(moves):>7,} "
                      f"{per_week:>5.1f} {wr:>5.1%} {avg - FRICTION_PCT:>+8.3f}% "
                      f"{mean_hold_h:>5.1f}h {lev_s:>12} {dd_s:>9}{mark}")
        print()

    good = [c for c in out["cells"] if c["in_band"] and all(h > 0 for h in c["halves_net"])]
    out["survivors"] = len(good)
    print(f"═══ {len(good)} of {len(out['cells'])} setups reach {WEEK_TARGET:.0%}/week "
          f"at survivable size AND make money in both halves")
    for c in sorted(good, key=lambda x: x["dd_at_target"]):
        print(f"  {c['timeframe']:>3} {c['slot']}/{c['option']:<16} {c['direction']:>5} "
              f"stop {c['barrier_pct']:.2f}%  {c['per_week']:.1f} trades/wk  "
              f"win {c['win_rate']:.1%}  {c['lev_for_target']:.1f}x  "
              f"worst drawdown {c['dd_at_target']:.0%}")

    (RESULTS / "sequential_sim.json").write_text(json.dumps(out, indent=1))
    print(f"\nwrote {RESULTS / 'sequential_sim.json'}")


def _selfcheck() -> None:
    """Sequencing and sizing are the two things that must not be wrong."""
    # Price ramps up 1%/bar: a long with a 1% barrier wins on the very next bar.
    bars = [(i * 3600_000, 100 * 1.01 ** i * 1.001, 100 * 1.01 ** i * 0.999,
             100 * 1.01 ** i) for i in range(200)]
    always = [True] * 200
    moves, holds = sequential(bars, always, 1.0, "long", 24)
    assert all(m == 1.0 for m in moves), moves[:5]
    # Sequencing: signals on every bar cannot produce more trades than bars.
    assert len(moves) <= 200 and all(h >= 1 for h in holds)
    # A 2-bar hold must yield strictly fewer trades than a 1-bar hold.
    slow = [(i * 3600_000, 100 * 1.005 ** i * 1.001, 100 * 1.005 ** i * 0.999,
             100 * 1.005 ** i) for i in range(200)]
    assert len(sequential(slow, always, 1.0, "long", 24)[0]) < len(moves)
    # Equity compounds and a big enough loss blows the account.
    eq, _, blown = equity([1.0] * 10, 1.0)
    assert abs(eq - (1 + 0.007) ** 10) < 1e-9, eq
    assert equity([-10.0], 10.0)[2] is True
    # Solver lands on the target it was asked for.
    lev = solve_leverage([1.0] * 100, 10.0)
    assert lev and abs(equity([1.0] * 100, lev)[0] ** (1 / 10) - 1 - 0.10) < 1e-4
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
