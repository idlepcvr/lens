"""The 68.1% short-book win rate counts trades he could never have taken.

`short_edge.py` scores all 91 non-VETO short entries independently. That is the
right way to measure whether a FILTER selects, and the wrong way to measure what
an ACCOUNT earns, because he holds one position at a time. A signal arriving
while he is already in a trade is not a trade he passed up — it is a trade that
was never available.

It matters more than it sounds like it should, because the skipped signals are
not a random subset. Short signals cluster: BTC starts falling, several fire
inside an hour, and they resolve together. Clustered signals in a falling market
are disproportionately WINNERS, so scoring them independently counts the same
favourable move several times over. Enforcing one position at a time removes the
duplicates and the win rate falls to what a single account could actually have
banked.

    all 91 resolved signals          68.1%   ← the headline
    57 arriving while flat           57.9%   ← what one account gets
    34 arriving mid-trade            85.3%   ← the duplicates

Breakeven at this geometry is 55.3%, so the edge is +2.6pp, not +16.3pp. Still
positive, still real, an eighth of the size. This does not overturn the finding
that non-VETO shorts select — the filter still beats random. It overturns what
that selection is worth to the account, which is the number sizing uses.

Also reported: what the surviving edge compounds to. At a stop sized so one
loss costs 20% of the account, the book returns −0.74%/week at current friction
and +0.31%/week at maker fees, with a 72–75% drawdown either way. The frequency
problem and the edge problem are the same problem — there is not enough of it.

    python3 research/one_at_a_time.py
"""
from __future__ import annotations

import bisect
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.geometry import FRICTION_PCT              # noqa: E402
from app.paths import RESULTS                      # noqa: E402
from research.entry_edge import load_bars, load_trades   # noqa: E402

STOP = TARGET = 2.8302
RISK_PER_LOSS = 0.20      # size so one stop-out costs 20% of the account
MAKER_FRICTION = 0.12     # limit-in, limit-out on Bybit, incl. some slippage
CAPS_H = [24, 60, 720]    # day trade · design hold · effectively uncapped


def resolve(bars, ts, trade, cap_h):
    """Walk one entry to a barrier, or close it at market when the cap hits.
    Returns (pct_move_in_your_favour, exit_bar_index) — None if it can't start."""
    t, d, entry, _tag = trade
    i = bisect.bisect_left(ts, t)
    if i >= len(bars) - 1:
        return None
    long_ = d == "long"
    tp = entry * (1 + TARGET / 100) if long_ else entry * (1 - TARGET / 100)
    sl = entry * (1 - STOP / 100) if long_ else entry * (1 + STOP / 100)
    for j in range(i, min(i + cap_h, len(bars))):
        _, hi, lo, _c = bars[j]
        if (lo <= sl) if long_ else (hi >= sl):     # stop wins ties
            return -STOP, j
        if (hi >= tp) if long_ else (lo <= tp):
            return TARGET, j
    j = min(i + cap_h, len(bars)) - 1
    pct = (bars[j][3] - entry) / entry * 100
    return (pct if long_ else -pct), j


def split(bars, ts, pool, cap_h):
    """Partition a pool into the entries one account could take, and the rest."""
    taken, missed, busy_until = [], [], -1
    for tr in pool:
        r = resolve(bars, ts, tr, cap_h)
        if r is None:
            continue
        move, exit_i = r
        if bisect.bisect_left(ts, tr[0]) >= busy_until:
            taken.append(move)
            busy_until = exit_i
        else:
            missed.append(move)
    return taken, missed


def compound(moves, lev, friction):
    eq = peak = 1.0
    dd = 0.0
    for m in moves:
        eq *= 1 + lev * (m - friction) / 100
        if eq <= 0:
            return 0.0, 1.0, True
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return eq, dd, False


def main() -> None:
    bars = load_bars()
    ts = [b[0] for b in bars]
    trades = sorted(load_trades(), key=lambda t: t[0])
    pools = {
        "short non-VETO": [t for t in trades if t[1] == "short"
                           and not str(t[3]).startswith("VETO")],
        "short all": [t for t in trades if t[1] == "short"],
        "whole book": trades,
    }
    wr = lambda ms: sum(1 for m in ms if m > 0) / len(ms) if ms else 0.0  # noqa: E731
    be = (STOP + FRICTION_PCT) / ((TARGET - FRICTION_PCT) + (STOP + FRICTION_PCT))
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "stop_pct": STOP, "breakeven_wr": be, "cells": []}

    print(f"stop=target {STOP}% · breakeven {be:.1%} · one position at a time\n")
    for name, pool in pools.items():
        for cap_h in CAPS_H:
            taken, missed = split(bars, ts, pool, cap_h)
            if len(taken) < 20:
                continue
            allm = taken + missed
            span = [t[0] for t in pool]
            weeks = (span[-1] - span[0]) / 1000 / 86400 / 7
            print(f"  {name:<15} cap {cap_h:>3}h │ {len(allm):>3} signals @ {wr(allm):>5.1%} "
                  f"→ {len(taken):>3} takeable @ {wr(taken):>5.1%}  "
                  f"({len(missed):>2} mid-trade @ {wr(missed) if missed else 0:>5.1%})")
            cell = {"pool": name, "cap_h": cap_h, "signals": len(allm),
                    "signal_wr": wr(allm), "taken": len(taken), "taken_wr": wr(taken),
                    "missed": len(missed), "missed_wr": wr(missed) if missed else None,
                    "per_week": len(taken) / weeks, "sizing": []}
            for f in (FRICTION_PCT, MAKER_FRICTION):
                lev = RISK_PER_LOSS * 100 / (STOP + f)
                eq, dd, blown = compound(taken, lev, f)
                weekly = -1.0 if blown else eq ** (1 / weeks) - 1
                print(f"  {'':>15}          │   friction {f:.2f}% → "
                      f"{sum(taken) / len(taken) - f:+.3f}%/trade · {lev:.1f}x · "
                      f"{weekly:+.2%}/week · worst drawdown {dd:.0%}")
                cell["sizing"].append({"friction": f, "leverage": lev,
                                       "weekly": weekly, "max_dd": dd})
            out["cells"].append(cell)
        print()

    (RESULTS / "one_at_a_time.json").write_text(json.dumps(out, indent=1))
    print(f"wrote {RESULTS / 'one_at_a_time.json'}")


def _selfcheck() -> None:
    """The partition is the whole point: taken must never overlap."""
    bars = [(i * 3600_000, 100.0, 100.0, 100.0) for i in range(100)]   # flat: no barrier hit
    ts = [b[0] for b in bars]
    pool = [(i * 3600_000, "short", 100.0, "X") for i in range(10)]    # a signal every bar
    taken, missed = split(bars, ts, pool, 5)
    assert len(taken) + len(missed) == 10, (taken, missed)
    # With a 5-bar cap and a signal every bar, at most every 5th can be taken.
    assert len(taken) <= 3, len(taken)
    assert missed, "signals inside an open trade must be recorded as missed"
    # Flat market, capped exit: every move is ~0, so friction is pure loss.
    eq, _, _ = compound([0.0, 0.0], 1.0, 0.30)
    assert eq < 1.0, eq
    assert compound([-2.8302], 40.0, 0.30)[2] is True, "a stop at 40x must blow the account"
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
