"""What the book actually cost, and what inverting it would have done.

Two findings live here and the first one reframes the whole project.

═══ THE BOOK WAS PROFITABLE BEFORE COSTS ═══

512 closed trades. Realised P&L −4,848.58. Fees and funding 5,535.99. So the
entry and exit decisions generated +687.41 of gross edge and the exchange took
eight times that. The 38.9% win rate reads like a man who cannot pick direction;
on raw price movement alone he is 40.8%, and positive in aggregate. What he
cannot do is pay 10.81 per trade to collect 1.34 of edge, 512 times.

That is not a strategy defect and no new strategy fixes it. Edge per trade has
to exceed cost per trade, and the cheapest way to raise the left side is to stop
cutting trades short: at his actual exits the average trade moves +0.027% in his
favour, and held to a 2.83% barrier the same entries move +0.352%. Thirteen
times the edge for exactly the same fee.

═══ AND FRICTION_PCT IS OVERSTATED ═══

`geometry.FRICTION_PCT` is 0.30%. His measured round trip is 0.083% of notional.
Every negative result in this repo was computed against a cost 3.6× larger than
the one he pays. Correcting it moves the short book from −0.74%/week to
+0.54%/week — a real improvement, and still an order of magnitude short of the
goal, so this is a correction and not a rescue.

⚠ Do NOT simply set FRICTION_PCT to 0.083. That figure is exchange fees only.
A backtest fills at a bar close; a human fills somewhere worse. The gap between
them is slippage, it is real, and it is not in the `fees` column. 0.083% is the
floor, 0.30% was the guess, and the honest number is between them and needs
measuring against signal-time prices rather than assumed.

═══ INVERSION ═══

"If I lose 60% of the time, flipping every trade wins 60%." The direction flips.
The fee does not. Inverted, the same book returns −6,223.40 against an actual
−4,848.58 — worse, because his raw edge is positive and inversion throws that
away while still paying the toll twice.

    python3 research/realized_costs.py
"""
from __future__ import annotations

import json
import sqlite3
import statistics as st
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.database import DB_PATH      # noqa: E402
from app.paths import RESULTS         # noqa: E402

QUERY = """SELECT direction, entry, exit, pnl, fees, funding_cost, size
           FROM trades
           WHERE pnl IS NOT NULL AND entry IS NOT NULL AND exit IS NOT NULL
             AND direction IN ('long','short')"""


def load():
    return sqlite3.connect(DB_PATH).execute(QUERY).fetchall()


def analyse(rows) -> dict:
    moves, pnls, costs, notionals = [], [], [], []
    for d, entry, ex, pnl, fee, fund, size in rows:
        mv = (ex - entry) / entry * 100
        moves.append(mv if d == "long" else -mv)
        pnls.append(pnl)
        costs.append((fee or 0) + (fund or 0))
        if size:
            notionals.append(entry * size)

    n = len(rows)
    gross_pnl = sum(p + c for p, c in zip(pnls, costs))
    # Inversion: the price move flips sign, the cost does not.
    inverted_pnl = sum(-(p + c) - c for p, c in zip(pnls, costs))
    fee_pct = st.median([c / nt * 100 for c, nt in zip(costs, notionals) if nt]) \
        if notionals else None
    return {
        "trades": n,
        "win_rate_realised": sum(1 for p in pnls if p > 0) / n,
        "win_rate_price_only": sum(1 for m in moves if m > 0) / n,
        "realised_pnl": sum(pnls),
        "total_costs": sum(costs),
        "gross_pnl_before_costs": gross_pnl,
        "inverted_pnl": inverted_pnl,
        "avg_move_pct": sum(moves) / n,
        "cost_per_trade": sum(costs) / n,
        "gross_edge_per_trade": gross_pnl / n,
        "measured_friction_pct": fee_pct,
        "median_notional": st.median(notionals) if notionals else None,
    }


def main() -> None:
    r = analyse(load())
    print(f"{r['trades']} closed trades\n")
    print(f"  win rate, realised P&L        {r['win_rate_realised']:>8.1%}")
    print(f"  win rate, price move only     {r['win_rate_price_only']:>8.1%}"
          "   ← costs turned winners into losers\n")
    print(f"  realised P&L                  {r['realised_pnl']:>12,.2f}")
    print(f"  fees + funding                {r['total_costs']:>12,.2f}")
    print(f"  P&L BEFORE costs              {r['gross_pnl_before_costs']:>12,.2f}"
          "   ← the entries were fine\n")
    print(f"  gross edge per trade          {r['gross_edge_per_trade']:>12,.2f}")
    print(f"  cost per trade                {r['cost_per_trade']:>12,.2f}"
          f"   ← {r['cost_per_trade'] / max(r['gross_edge_per_trade'], 1e-9):.1f}× the edge\n")
    print(f"  measured round-trip friction  {r['measured_friction_pct']:>11.4f}%"
          "   (FRICTION_PCT assumes 0.30% — fees only, excludes slippage)\n")
    print(f"  inverting every trade would give {r['inverted_pnl']:,.2f} "
          f"against an actual {r['realised_pnl']:,.2f}")
    print(f"  because the average trade moves {r['avg_move_pct']:+.4f}% his way — "
          "inversion discards that and still pays the toll")

    out = dict(r, generated=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    (RESULTS / "realized_costs.json").write_text(json.dumps(out, indent=1))
    print(f"\nwrote {RESULTS / 'realized_costs.json'}")


def _selfcheck() -> None:
    """Inversion accounting is the claim: costs must be charged in both books."""
    # One long: entry 100, exit 102 (+2%), cost 5, so realised pnl = 2% gross - 5.
    rows = [("long", 100.0, 102.0, 15.0, 5.0, 0.0, 1.0)]
    r = analyse(rows)
    assert r["gross_pnl_before_costs"] == 20.0, r["gross_pnl_before_costs"]
    # Inverted: gross becomes -20, still pay 5 → -25.
    assert r["inverted_pnl"] == -25.0, r["inverted_pnl"]
    assert abs(r["avg_move_pct"] - 2.0) < 1e-9
    # A short that fell is a winner on price.
    r2 = analyse([("short", 100.0, 98.0, 15.0, 5.0, 0.0, 1.0)])
    assert r2["win_rate_price_only"] == 1.0 and abs(r2["avg_move_pct"] - 2.0) < 1e-9
    # Sum rule: a book and its inverse differ by exactly twice the costs.
    assert abs((r["realised_pnl"] - r["inverted_pnl"]) - 2 * r["gross_pnl_before_costs"]) < 1e-9
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
