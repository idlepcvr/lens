"""Locks down the risk↔leverage split on the prop ticket.

The bug: leverage was DERIVED (min(risk/stop, cap)) and shown as "the" leverage,
so asking for 5x got you 0.50x and the number was really a risk cap. Leverage is
a free variable — it moves margin and the liq price, never the risk, the size or
the levels. Only the margin ceiling (all-in at the firm's cap) can cut the size.

Offline (no Kraken, no network). Run: .venv/bin/python test_prop_ticket.py
"""
import os
import tempfile

from app import database


def main():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = path
    database.init_db()
    database.set_prop_eval(10000.0, 0.5, "BREAKOUT_1STEP_TURBO", fee=48.0)

    from app.prop_scan import prop_ticket

    entry, stop, target = 60000.0, 59400.0, 62400.0     # 1% stop, 4% target, long
    base = prop_ticket(entry, stop, target, True, account=10000.0)

    # the firm's max is the default — not the old derived 0.5x
    assert base["leverage"] == 5.0, base["leverage"]
    assert base["max_leverage"] == 5.0

    # risk 0.5% of 10k = $50; 1% stop → $5,000 notional. Leverage is not in this.
    assert abs(base["risk_usd"] - 50.0) < 0.01, base["risk_usd"]
    assert abs(base["notional"] - 5000.0) < 0.01, base["notional"]
    assert abs(base["actual_risk_pct"] - 0.5) < 0.01, base["actual_risk_pct"]

    # ── the invariant: sweep leverage, risk and the levels must not move ───────
    for lev in (0.5, 1, 2, 3, 5):
        t = prop_ticket(entry, stop, target, True, account=10000.0, lev=lev)
        assert t["leverage"] == lev, (lev, t["leverage"])
        assert abs(t["risk_usd"] - base["risk_usd"]) < 0.01, lev
        assert abs(t["notional"] - base["notional"]) < 0.01, lev
        assert abs(t["size_btc"] - base["size_btc"]) < 1e-9, lev
        assert t["stop_pct"] == base["stop_pct"] and t["tp_pct"] == base["tp_pct"], lev
        assert t["loss_usd"] == base["loss_usd"] and t["win_usd"] == base["win_usd"], lev
        # ...only the margin does, at notional/lev
        assert abs(t["margin_usd"] - 5000.0 / lev) < 0.01, (lev, t["margin_usd"])
        # ...and the liq price, which must stay beyond the stop (or not exist at
        # all below 1x, where the margin posted exceeds the notional)
        assert t["liq"] is None or t["liq"] < stop, (lev, t["liq"])

    # clamps: over the firm's cap → cap; under the margin floor → floor (0.5x here)
    assert prop_ticket(entry, stop, target, True, account=10000.0, lev=20)["leverage"] == 5.0
    assert prop_ticket(entry, stop, target, True, account=10000.0, lev=0.1)["leverage"] == 0.5

    # margin ceiling: a 0.05% stop wants 100k notional on a 10k account — can't
    # margin it even all-in at 5x, so the SIZE gets cut and the risk with it.
    tight = prop_ticket(entry, entry * 0.9995, target, True, account=10000.0)
    assert abs(tight["notional"] - 50000.0) < 1.0, tight["notional"]      # 10k × 5x
    assert tight["actual_risk_pct"] < 0.5, tight["actual_risk_pct"]       # under-risked
    assert abs(tight["margin_usd"] - 10000.0) < 1.0, tight["margin_usd"]  # the whole account

    # ── the stop IS the travel-distance dial: halve it, halve the travel ───────
    # Base is a 1% stop / 4% target (R=4). Halve the stop to 0.5% and hold R:
    # the position doubles, the travel to TP halves, risk and $ win are untouched.
    half = prop_ticket(entry, entry * (1 - 0.005), entry * (1 + 0.02), True, account=10000.0)
    assert abs(half["stop_pct"] - base["stop_pct"] / 2) < 0.01, half["stop_pct"]
    assert abs(half["tp_pct"] - base["tp_pct"] / 2) < 0.01, half["tp_pct"]   # half the travel
    assert abs(half["notional"] - 2 * base["notional"]) < 1.0, half["notional"]
    assert abs(half["risk_usd"] - base["risk_usd"]) < 0.01, half["risk_usd"]
    assert half["rr"] == base["rr"], "R must be held when the stop is tightened"
    assert half["min_leverage"] > base["min_leverage"], "tighter stop must demand more leverage"
    # the leverage a stop demands is exactly risk% / stop%
    assert abs(half["min_leverage"] - 0.5 / 0.5) < 0.02, half["min_leverage"]

    os.unlink(path)
    print("ok — risk/size/levels invariant under leverage; the stop is the travel dial")


if __name__ == "__main__":
    main()
