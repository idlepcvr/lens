"""Self-check for the goal ladder (app/plan.py) — runs against a throwaway DB.

    python test_plan.py
"""
import os, tempfile
from datetime import date

from app import database

database.DB_PATH = os.path.join(tempfile.mkdtemp(), "test_plan.db")
database.init_db()

from app import plan  # noqa: E402  (must import after DB_PATH is redirected)


def test_seed_and_amend():
    p = plan.active_plan()
    assert p["version"] == 1 and p["goal_btc"] == 50.0 and p["goal_date"] == "2028-12-31"
    assert len(p["milestones"]) == 12 and p["milestones"][-1]["btc"] == 50.0

    for bad in ("too short", ""):
        try:
            plan.amend({"goal_btc": 60.0}, bad); assert False, "short reason accepted"
        except ValueError:
            pass
    try:
        plan.amend({}, "a perfectly long and valid reason string"); assert False, "no-op accepted"
    except ValueError:
        pass

    p2 = plan.amend({"goal_btc": 60.0}, "stretched the goal after the 2026 bull leg")
    assert p2["version"] == 2 and p2["goal_btc"] == 60.0
    assert len(plan.history()) == 2, "amendment must append, never overwrite"
    assert plan.active_plan()["version"] == 2
    plan.amend({"goal_btc": 50.0}, "reverted: 60 was plan churn, not evidence")


def test_milestone_dates():
    p = plan.active_plan()
    today = date(2026, 7, 9)

    assert all(m["date"] is None for m in plan.milestone_dates(p, None, today)), "no stack → no dates"

    ms = plan.milestone_dates(p, 1.0, today)
    by = {m["btc"]: m for m in ms}
    assert by[0.5]["done"] and by[1.0]["done"] and not by[2.0]["done"]
    assert by[50.0]["date"] == p["goal_date"], "top rung lands exactly on the goal date"
    dates = [m["date"] for m in ms if m["date"]]
    assert dates == sorted(dates), "derived dates must be monotone up the ladder"
    # constant CAGR: 5 BTC is ln(5)/ln(50) ≈ 41% of the way through the window
    days = (date.fromisoformat(p["goal_date"]) - today).days
    want = date.fromordinal(today.toordinal() + round(0.4114 * days))
    assert abs((date.fromisoformat(by[5.0]["date"]) - want).days) <= 1


def test_measured():
    m = plan.measured()
    assert m["n"] == 0 and not m.get("enough")

    c = database._conn()
    for i in range(40):
        pnl = 30.0 if i % 4 == 0 else -10.0          # 25% WR, R = 3
        c.execute("""INSERT INTO trades (symbol,direction,entry,size,leverage,opened_at,closed_at,pnl,fees)
                     VALUES ('BTC/USD:USD','long',100,1,10,?,?,?,1.0)""",
                  (f"2026-05-{i % 28 + 1:02d}T10:00:00", f"2026-06-{i % 28 + 1:02d}T12:00:00", pnl))
    c.commit(); c.close()

    m = plan.measured()
    assert m["n"] == 40 and m["enough"]
    assert m["win_rate"] == 0.25 and m["rr_ratio"] == 3.0
    assert m["fee_r"] == 0.1, "fee drag in R: €1 fee ÷ €10 avg loss"
    assert m["trades_per_week"] > 0


if __name__ == "__main__":
    test_seed_and_amend(); test_milestone_dates(); test_measured()
    print("ok — plan ladder, derived dates, measured params")
