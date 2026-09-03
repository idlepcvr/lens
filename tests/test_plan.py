"""Self-check for the goal ladder (app/plan.py) — runs against a throwaway DB.

    python test_plan.py
"""
import os, tempfile
from datetime import date

import pytest

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app import database

_DB = os.path.join(tempfile.mkdtemp(), "test_plan.db")
database.DB_PATH = _DB
database.init_db()


@pytest.fixture(autouse=True)
def _own_db():
    """Re-point DB_PATH per test instead of trusting import order.

    Several files in this suite are scripts rather than test functions
    (test_signal_link.py, test_excursion.py): pytest still imports them during
    collection, their whole body runs, and they reassign database.DB_PATH to
    their own temp DB. Collection finishes before any test does, so whichever
    imported last owned the database by the time these tests ran — which is why
    test_measured saw 9 foreign trades where it had inserted none.
    """
    database.DB_PATH = _DB

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


def test_pinned_dates_anchor_the_ladder():
    """A pinned rung is never recomputed, and the rungs under it compress to
    fit rather than being stretched across the whole goal window."""
    from datetime import date
    p = {
        "goal_btc": 1.0, "goal_date": "2028-12-31",
        "milestones": [
            {"btc": 0.005, "label": "Half step"},
            {"btc": 0.01, "label": "One percent", "by": "2026-08-31"},
            {"btc": 0.1, "label": "Seed"},
            {"btc": 1.0, "label": "Goal"},
        ],
    }
    today = date(2026, 8, 9)
    out = plan.milestone_dates(p, 0.0033, today=today)
    by_label = {m["label"]: m for m in out}

    # the pin is honoured verbatim
    assert by_label["One percent"]["date"] == "2026-08-31"
    assert by_label["One percent"]["pinned"] is True

    # the rung BELOW the pin lands before it, not months later
    half = by_label["Half step"]
    assert half["pinned"] is False
    assert today.isoformat() < half["date"] < "2026-08-31", half["date"]

    # a rung ABOVE the pin still runs out to the goal
    assert by_label["Seed"]["date"] > "2026-08-31"
    # the top rung lands exactly on the goal date
    assert by_label["Goal"]["date"] == "2028-12-31"


def test_unpinned_ladder_is_unchanged_by_the_pin_feature():
    """No pins anywhere = the original constant-CAGR curve, so existing plans
    keep their dates."""
    from datetime import date
    p = {"goal_btc": 1.0, "goal_date": "2027-08-09",
         "milestones": [{"btc": 0.1, "label": "a"}, {"btc": 1.0, "label": "b"}]}
    out = plan.milestone_dates(p, 0.01, today=date(2026, 8, 9))
    # 0.1 is the geometric midpoint of 0.01 -> 1.0, so it lands mid-window
    assert out[0]["date"] == "2027-02-07", out[0]["date"]
    assert out[1]["date"] == "2027-08-09"
