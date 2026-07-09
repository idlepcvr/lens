"""Goal ladder — the locked plan, its amendment log, and the stack snapshots.

Why this exists (NEXT_SESSION.md): the goal never moves, the plan gets rewritten
every iteration. `goal_plan` is append-only and every amendment costs a reason;
the UI shows "v3 · amended 2 times · last: <reason>" so churn is visible.

Two levels, don't conflate them:
  · engine  = LENS equity + prop payouts (the calculator, /money) — where the math is real
  · stack   = total BTC held (existing BTC + savings + engine inflows) — the score

Milestone rungs are fixed in BTC. Milestone *dates* are derived, never stored:
constant-CAGR interpolation from (current stack, today) → (goal_btc, goal_date).
The dates move with reality; the rungs never do.
"""

import json
import math
from datetime import date, datetime

from .database import _conn

# Roughly geometric — each rung is a similar % climb, so a similar felt difficulty.
DEFAULT_MILESTONES = [
    {"btc": 0.1,  "label": "Seed"},
    {"btc": 0.25, "label": "Foothold"},
    {"btc": 0.5,  "label": "Half"},
    {"btc": 1.0,  "label": "Whole coin"},
    {"btc": 2.0,  "label": "Cushion"},
    {"btc": 3.5,  "label": "Rent covered"},
    {"btc": 5.0,  "label": "Income complete"},
    {"btc": 8.0,  "label": "Runway"},
    {"btc": 12.0, "label": "Escape velocity"},
    {"btc": 20.0, "label": "Fortress"},
    {"btc": 32.0, "label": "Sovereign"},
    {"btc": 50.0, "label": "Goal"},
]

# Ratified 2026-07-06. Seeded once as v1; change only through amend().
SEED = {
    "north_star_btc": 150.0,
    "north_star_date": "2032-12-31",
    "goal_btc": 50.0,
    "goal_date": "2028-12-31",
    "milestones": DEFAULT_MILESTONES,
    "price_scenarios": {"bear": -20.0, "base": 15.0, "bull": 50.0},
    "burn_monthly_eur": 2800.0,   # ≈ $3,000
}

AMENDABLE = ("north_star_btc", "north_star_date", "goal_btc", "goal_date",
             "milestones", "price_scenarios", "burn_monthly_eur")
MIN_REASON = 20
STALE_DAYS = 40          # snapshot older than this → nag on the goal hero
MEASURED_MIN_N = 30      # below this the ledger can't speak; "Use measured" stays greyed out


def _row(r):
    d = dict(r)
    d["milestones"] = json.loads(d["milestones"])
    d["price_scenarios"] = json.loads(d["price_scenarios"])
    return d


def active_plan() -> dict:
    """The current plan. Seeds v1 from SEED on first call."""
    c = _conn()
    r = c.execute("SELECT * FROM goal_plan WHERE active = 1").fetchone()
    if not r:
        c.execute(
            """INSERT INTO goal_plan (version, created_at, north_star_btc, north_star_date,
                   goal_btc, goal_date, milestones, price_scenarios, burn_monthly_eur,
                   amendment_reason, active)
               VALUES (1,?,?,?,?,?,?,?,?,?,1)""",
            (datetime.utcnow().isoformat(), SEED["north_star_btc"], SEED["north_star_date"],
             SEED["goal_btc"], SEED["goal_date"], json.dumps(SEED["milestones"]),
             json.dumps(SEED["price_scenarios"]), SEED["burn_monthly_eur"],
             "ratified 2026-07-06"),
        )
        c.commit()
        r = c.execute("SELECT * FROM goal_plan WHERE active = 1").fetchone()
    c.close()
    return _row(r)


def history() -> list[dict]:
    c = _conn()
    rows = c.execute("SELECT * FROM goal_plan ORDER BY version DESC").fetchall()
    c.close()
    return [_row(r) for r in rows]


def amend(changes: dict, reason: str) -> dict:
    """Insert a new plan version. Append-only: the old row stays, just inactive."""
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise ValueError(f"Amendment needs a reason of at least {MIN_REASON} characters.")
    cur = active_plan()
    new = {k: changes.get(k, cur[k]) for k in AMENDABLE}
    if all(new[k] == cur[k] for k in AMENDABLE):
        raise ValueError("Nothing changed — an amendment must change the plan.")

    c = _conn()
    c.execute("UPDATE goal_plan SET active = 0")
    c.execute(
        """INSERT INTO goal_plan (version, created_at, north_star_btc, north_star_date,
               goal_btc, goal_date, milestones, price_scenarios, burn_monthly_eur,
               amendment_reason, active)
           VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
        (cur["version"] + 1, datetime.utcnow().isoformat(),
         new["north_star_btc"], new["north_star_date"], new["goal_btc"], new["goal_date"],
         json.dumps(new["milestones"]), json.dumps(new["price_scenarios"]),
         new["burn_monthly_eur"], reason),
    )
    c.commit()
    c.close()
    return active_plan()


# ─── Stack snapshots ─────────────────────────────────────────────────────────

def add_snapshot(d: str, btc_total: float, note: str = None) -> dict:
    c = _conn()
    c.execute("INSERT INTO stack_snapshot (date, btc_total, note, created_at) VALUES (?,?,?,?)",
              (d, float(btc_total), note, datetime.utcnow().isoformat()))
    c.commit()
    c.close()
    return latest_snapshot()


def snapshots(limit: int = 24) -> list[dict]:
    c = _conn()
    rows = c.execute("SELECT * FROM stack_snapshot ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def latest_snapshot() -> dict | None:
    s = snapshots(1)
    return s[0] if s else None


def _age_days(iso_date: str) -> int:
    return (date.today() - date.fromisoformat(iso_date[:10])).days


# ─── Derived milestone dates ─────────────────────────────────────────────────

def milestone_dates(plan: dict, current_btc: float | None, today: date = None) -> list[dict]:
    """Constant-CAGR interpolation (current_btc, today) → (goal_btc, goal_date).

    Rung m lands at fraction ln(m/cur) / ln(goal/cur) of the remaining window.
    Returns each rung with `done` and a derived `date` (None when underivable:
    no snapshot, stack ≥ goal, or the goal date is already past).
    """
    today = today or date.today()
    out = []
    goal_btc = plan["goal_btc"]
    try:
        days_left = (date.fromisoformat(plan["goal_date"]) - today).days
    except Exception:
        days_left = None
    derivable = (current_btc is not None and current_btc > 0
                 and current_btc < goal_btc and days_left and days_left > 0)
    span = math.log(goal_btc / current_btc) if derivable else None

    for m in plan["milestones"]:
        btc = m["btc"]
        done = current_btc is not None and current_btc >= btc
        d = None
        if derivable and not done and btc <= goal_btc:
            frac = math.log(btc / current_btc) / span
            d = date.fromordinal(today.toordinal() + round(frac * days_left)).isoformat()
        out.append({**m, "done": done, "date": d})
    return out


def ladder() -> dict:
    """Everything /goal's Plan panel needs in one call."""
    p = active_plan()
    hist = history()
    snap = latest_snapshot()
    cur_btc = snap["btc_total"] if snap else None
    return {
        "plan": p,
        "amendments": len(hist) - 1,
        "last_reason": p["amendment_reason"],
        "history": [{"version": h["version"], "created_at": h["created_at"],
                     "reason": h["amendment_reason"], "goal_btc": h["goal_btc"],
                     "goal_date": h["goal_date"]} for h in hist],
        "milestones": milestone_dates(p, cur_btc),
        "stack": snap,
        "stack_age_days": _age_days(snap["date"]) if snap else None,
        "stack_stale": (_age_days(snap["date"]) > STALE_DAYS) if snap else True,
        "snapshots": snapshots(),
    }


# ─── Measured parameters (the ledger's own numbers) ──────────────────────────

def measured(days: int = None) -> dict:
    """WR, realized R, trades/week and fee drag straight from closed trades.

    `days=None` → all time. Fee drag is expressed in R (fees per trade ÷ avg loss)
    because that's the unit the goal model's breakeven-WR argument lives in.
    """
    c = _conn()
    where = "closed_at IS NOT NULL AND pnl IS NOT NULL"
    params = []
    if days:
        where += " AND closed_at >= ?"
        params.append(date.fromordinal(date.today().toordinal() - days).isoformat())
    rows = c.execute(f"SELECT pnl, fees, closed_at FROM trades WHERE {where} ORDER BY closed_at",
                     params).fetchall()
    c.close()

    n = len(rows)
    if not n:
        return {"n": 0, "days": days}
    pnls = [r["pnl"] for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    fees = sum(r["fees"] or 0.0 for r in rows)

    span = max(1, (date.fromisoformat(rows[-1]["closed_at"][:10])
                   - date.fromisoformat(rows[0]["closed_at"][:10])).days)
    return {
        "n": n,
        "days": days,
        "span_days": span,
        "win_rate": round(len(wins) / n, 4),
        "rr_ratio": round(avg_win / avg_loss, 3) if avg_loss else None,
        "trades_per_week": round(n / (span / 7.0), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "fees_total": round(fees, 2),
        "fee_r": round((fees / n) / avg_loss, 3) if avg_loss else None,
        "enough": n >= MEASURED_MIN_N,
        "min_n": MEASURED_MIN_N,
    }
