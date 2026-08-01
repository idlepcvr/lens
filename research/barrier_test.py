"""Does the market actually hand over the geometry /geometry prescribes?

The /geometry page derives stop and target from a driftless-random-walk model.
That model makes two falsifiable predictions for a RANDOM entry:

    P(target before stop) = stop / (stop + target) = 1/(1+R)
    E[hold]               = stop · target / σ²

This script tests both against 7 years of real BTC hourly bars by taking EVERY
bar as an entry and walking forward until one barrier is touched. No setups, no
filters, no edge — that is the point. It measures the BASELINE the geometry sits
on, so that any claimed edge can be stated as a delta against it rather than
against zero.

Two questions it settles that the ledger cannot:

  1. Are 5.66% moves reachable at all? The book says 0/512 fills ever travelled
     that far, but the book's median hold is 2.1 hours. That is a fact about
     holding time, not about the market. Here, entries are held until resolution.
  2. Does real BTC behave like the model? Fat tails, trends and vol clustering
     all violate the random-walk assumption. If the realized win rate matches
     1/(1+R) the model is safe to reason with; if it doesn't, the /geometry
     numbers need a haircut.

Conservative on ties: when a single bar's range spans both barriers, the STOP is
recorded. Intrabar path is unknown, and assuming the good fill flatters every
result on the page.

    python3 research/barrier_test.py            # live + superseded geometry
    python3 research/barrier_test.py --sweep    # R:R and hold ladder
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.database import DB_PATH          # noqa: E402
from app.geometry import FRICTION_PCT     # noqa: E402

SYMBOL = "binance:BTC/USDT"
# Give a trade this long to resolve before abandoning it. 60 days is ~24× the
# 2.5-day design hold, so it truncates essentially nothing at the geometries
# tested while keeping the walk bounded.
MAX_HOURS = 24 * 60


def load_bars() -> list[tuple[int, float, float, float]]:
    """(ts, high, low, close) hourly, oldest first."""
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT ts, high, low, close FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe='1h' ORDER BY ts ASC", (SYMBOL,)).fetchall()
    return [(int(t), float(h), float(l), float(c)) for t, h, l, c in rows]


def simulate(bars, stop_pct: float, target_pct: float, direction: str = "long",
             step: int = 1, entries=None, max_bars: int = MAX_HOURS) -> dict:
    """Every `step`-th bar becomes an entry at its close. Walk forward until a
    barrier is touched; record which, and how long it took.

    `entries` restricts entries to those bar indices (a setup's signal bars)
    instead of every step-th bar; `max_bars` caps the walk. Both default to the
    old behaviour. Holds are counted in BARS, which equals hours only when
    `bars` is hourly — sub-hourly callers must convert."""
    wins = losses = unresolved = 0
    hold_win: list[int] = []
    hold_loss: list[int] = []
    n = len(bars)
    long_ = direction == "long"

    for i in (range(0, n - 1, step) if entries is None else entries):
        entry = bars[i][3]
        if long_:
            tp, sl = entry * (1 + target_pct / 100), entry * (1 - stop_pct / 100)
        else:
            tp, sl = entry * (1 - target_pct / 100), entry * (1 + stop_pct / 100)

        end = min(i + 1 + max_bars, n)
        for j in range(i + 1, end):
            _, hi, lo, _ = bars[j]
            hit_sl = lo <= sl if long_ else hi >= sl
            hit_tp = hi >= tp if long_ else lo <= tp
            if hit_sl:                      # stop wins ties, deliberately
                losses += 1
                hold_loss.append(j - i)
                break
            if hit_tp:
                wins += 1
                hold_win.append(j - i)
                break
        else:
            unresolved += 1

    resolved = wins + losses
    if not resolved:
        return {}

    wr = wins / resolved
    holds = hold_win + hold_loss
    # Net R per trade, in % of notional — the same quantity /geometry reports.
    net = wr * (target_pct - FRICTION_PCT) - (1 - wr) * (stop_pct + FRICTION_PCT)
    return {
        "direction": direction,
        "stop_pct": stop_pct, "target_pct": target_pct,
        "rr": target_pct / stop_pct,
        "n": resolved, "unresolved": unresolved,
        "win_rate": wr,
        "theory_wr": stop_pct / (stop_pct + target_pct),
        "mean_hold_h": statistics.mean(holds),
        "median_hold_h": statistics.median(holds),
        "median_win_h": statistics.median(hold_win) if hold_win else None,
        "median_loss_h": statistics.median(hold_loss) if hold_loss else None,
        "net_pct": net,
        "breakeven_wr": (stop_pct + FRICTION_PCT)
                        / ((target_pct - FRICTION_PCT) + (stop_pct + FRICTION_PCT)),
    }


def show(r: dict, label: str) -> None:
    if not r:
        print(f"{label}: no resolved trades")
        return
    edge = (r["win_rate"] - r["breakeven_wr"]) * 100
    verdict = "POSITIVE" if r["net_pct"] > 0 else "negative"
    print(f"\n  {label}  ({r['direction']}, stop {r['stop_pct']:.2f}% / "
          f"target {r['target_pct']:.2f}%, R:R {r['rr']:.2f})")
    print(f"    n            {r['n']:,} resolved  ({r['unresolved']:,} still open at cutoff)")
    print(f"    win rate     {r['win_rate']:.2%}   (random-walk theory: {r['theory_wr']:.2%})")
    print(f"    breakeven    {r['breakeven_wr']:.2%}   → realized edge {edge:+.2f}pp")
    print(f"    hold         median {r['median_hold_h']:.0f}h "
          f"({r['median_hold_h']/24:.1f}d) · mean {r['mean_hold_h']:.0f}h")
    print(f"                 wins {r['median_win_h']}h · losses {r['median_loss_h']}h")
    print(f"    net/trade    {r['net_pct']:+.4f}% of notional  → {verdict}")


def save_baseline(bars, sl: float, tp: float) -> dict:
    """Cache the random-entry baseline for /geometry to render.

    63k forward-walks per direction is far too slow to do on a page render, and
    the answer only moves when new bars land, so it lives on disk. Regenerate by
    re-running this script.
    """
    import json
    import os
    def day(ts):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "bars": len(bars), "from": day(bars[0][0]), "to": day(bars[-1][0]),
           "friction_pct": FRICTION_PCT, "stop_pct": sl, "target_pct": tp}
    agg_w = agg_n = 0
    holds = []
    for d in ("long", "short"):
        r = simulate(bars, sl, tp, d)
        out[d] = {k: r[k] for k in ("win_rate", "median_hold_h", "mean_hold_h",
                                    "median_win_h", "median_loss_h", "n", "net_pct")}
        agg_w += r["win_rate"] * r["n"]; agg_n += r["n"]
        holds.append(r["median_hold_h"])
    out["win_rate"] = agg_w / agg_n
    out["median_hold_h"] = sum(holds) / len(holds)
    out["breakeven_wr"] = (sl + FRICTION_PCT) / ((tp - FRICTION_PCT) + (sl + FRICTION_PCT))
    out["edge_needed_pp"] = (out["breakeven_wr"] - out["win_rate"]) * 100

    # Random-entry win rate per R:R, at the stop the barrier identity gives for
    # a 2.5-day design hold. This is the baseline /target states every required
    # edge against — a measured floor rather than the model's 1/(1+R).
    from app.geometry import solve
    from app.geometry_page import _sigma
    sigma, _ = _sigma()
    rr_base = {}
    for rr in (1.0, 2.0, 3.0, 4.0, 6.0, 8.0):
        g = solve(sigma, 2.5, rr)
        w = n_ = 0
        for d in ("long", "short"):
            r = simulate(bars, g["stop_pct"], g["target_pct"], d, step=3)
            if r:
                w += r["win_rate"] * r["n"]; n_ += r["n"]
        if n_:
            rr_base[str(rr)] = {"win_rate": w / n_, "n": n_,
                                "stop_pct": g["stop_pct"], "target_pct": g["target_pct"]}
            print(f"    R:R {rr:.0f}: random WR {w/n_:.2%}  "
                  f"({g['stop_pct']:.2f}%/{g['target_pct']:.2f}%)")
    out["rr_baseline"] = rr_base
    out["sigma"] = sigma

    path = os.path.join(__file__.rsplit("/research/", 1)[0], "results",
                        "barrier_baseline.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n  → wrote {path}")
    return out


def main() -> None:
    bars = load_bars()
    f = lambda t: datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"{len(bars):,} hourly bars  {f(bars[0][0])} → {f(bars[-1][0])}"
          f"   friction {FRICTION_PCT:.2f}% round trip")

    from app.setups import SL_PCT, TP_PCT
    cases = [
        ((SL_PCT, TP_PCT), "LIVE geometry (barrier-derived)"),
        ((0.63, 1.5), "SUPERSEDED (2026-07-02 fit)"),
    ]
    for (sl, tp), label in cases:
        for d in ("long", "short"):
            show(simulate(bars, sl, tp, d), label)

    save_baseline(bars, SL_PCT, TP_PCT)

    if "--sweep" in sys.argv:
        print("\n\n  R:R sweep at the live stop — random entry, both directions")
        print(f"  {'R:R':>5} {'target':>8} {'WR':>8} {'theory':>8} {'BE':>8} "
              f"{'edge':>8} {'hold':>9} {'net/trade':>11}")
        for rr in (1.0, 2.0, 3.0, 4.0, 6.0, 8.0):
            agg_w = agg_n = 0
            holds = []
            for d in ("long", "short"):
                r = simulate(bars, SL_PCT, SL_PCT * rr, d, step=2)
                if r:
                    agg_w += r["win_rate"] * r["n"]; agg_n += r["n"]
                    holds.append(r["median_hold_h"])
            if not agg_n:
                continue
            wr = agg_w / agg_n
            tgt = SL_PCT * rr
            be = (SL_PCT + FRICTION_PCT) / ((tgt - FRICTION_PCT) + (SL_PCT + FRICTION_PCT))
            net = wr * (tgt - FRICTION_PCT) - (1 - wr) * (SL_PCT + FRICTION_PCT)
            print(f"  {rr:>5.1f} {tgt:>7.2f}% {wr:>7.2%} {1/(1+rr):>7.2%} {be:>7.2%} "
                  f"{(wr-be)*100:>+7.2f}pp {statistics.mean(holds)/24:>7.1f}d "
                  f"{net:>+10.4f}%")

        print("\n  Hold ladder at R:R 4 — stop from the barrier identity")
        from app.geometry import solve
        from app.geometry_page import _sigma
        sigma, _ = _sigma()
        print(f"  {'design':>8} {'stop':>7} {'target':>8} {'WR':>8} {'BE':>8} "
              f"{'realized hold':>15} {'net/trade':>11}")
        for hd in (4/24, 1.0, 43/24, 2.5, 5.0, 10.0):
            g = solve(sigma, hd, 4.0)
            agg_w = agg_n = 0
            holds = []
            for d in ("long", "short"):
                r = simulate(bars, g["stop_pct"], g["target_pct"], d, step=2)
                if r:
                    agg_w += r["win_rate"] * r["n"]; agg_n += r["n"]
                    holds.append(r["median_hold_h"])
            if not agg_n:
                continue
            wr = agg_w / agg_n
            net = (wr * (g["target_pct"] - FRICTION_PCT)
                   - (1 - wr) * (g["stop_pct"] + FRICTION_PCT))
            print(f"  {hd:>7.2f}d {g['stop_pct']:>6.2f}% {g['target_pct']:>7.2f}% "
                  f"{wr:>7.2%} {g['breakeven_wr']:>7.2%} "
                  f"{statistics.mean(holds)/24:>13.1f}d {net:>+10.4f}%")


if __name__ == "__main__":
    main()
