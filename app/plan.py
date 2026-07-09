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

# "Income complete" fires on 6 consecutive months of coverage ≥ 1.0 — the
# doctrine's stress-test rule 3, NOT 4%-withdrawal math on a stack you hold.
COVERAGE_STREAK = 6
PAYOUT_SHARE = 0.80      # prop take-home after the firm's split
LENS_BOOK = "hedge"      # the personal account; prop_* books are evaluations, not cash


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


# ─── C6 · Coverage — does the engine pay the bills yet? ──────────────────────

def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _prev_months(n: int, today: date = None) -> list[str]:
    """The last `n` COMPLETE months, oldest → newest. The current month is
    excluded: a month that's three days old always looks like a shortfall."""
    today = today or date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y:04d}-{m:02d}")
    return out[::-1]


def monthly_engine_flow(n: int = COVERAGE_STREAK) -> list[dict]:
    """Engine cash flow per complete month = LENS realized P&L + prop payouts.

    Prop *payouts* are cash; prop *evaluation* P&L is not, so evaluation books are
    excluded — counting them would let a paper account pay the rent. There is no
    payouts table yet, so `payout` is 0 until a funded account starts paying.
    """
    months = _prev_months(n)
    c = _conn()
    rows = c.execute(
        "SELECT substr(closed_at,1,7) AS m, COALESCE(SUM(pnl),0) AS pnl "
        "FROM trades WHERE pnl IS NOT NULL AND closed_at IS NOT NULL AND book = ? "
        "GROUP BY m", (LENS_BOOK,)
    ).fetchall()
    c.close()
    by_month = {r["m"]: r["pnl"] for r in rows}
    return [{"month": m, "lens": round(by_month.get(m, 0.0), 2), "payout": 0.0,
             "flow": round(by_month.get(m, 0.0), 2)} for m in months]


def coverage() -> dict:
    """Coverage ratio = monthly engine cash flow ÷ monthly burn. The trailing-3mo
    figure averages the flow to a MONTHLY rate first — a 3-month total over a
    1-month burn would read 3× too high."""
    p = active_plan()
    burn = p["burn_monthly_eur"] or 0.0
    flow = monthly_engine_flow()
    for f in flow:
        f["ratio"] = round(f["flow"] / burn, 3) if burn else None

    last3 = flow[-3:]
    t3 = (sum(f["flow"] for f in last3) / len(last3) / burn) if (burn and last3) else None

    streak = 0
    for f in reversed(flow):
        if f["ratio"] is not None and f["ratio"] >= 1.0:
            streak += 1
        else:
            break

    # The honest bar: what the funded account must return monthly to cover burn.
    # Same-currency assumption (EUR burn vs the eval account's units) — a ~1.08
    # EURUSD would move this ~8%, which never changes the verdict here.
    acct = 0.0
    try:
        from .database import get_prop_eval
        acct = float(get_prop_eval().get("account") or 0.0)
    except Exception:
        pass
    req_pct = (burn / (acct * PAYOUT_SHARE) * 100.0) if (acct and burn) else None

    return {
        "burn_monthly_eur": burn,
        "months": flow,
        "trailing3": round(t3, 3) if t3 is not None else None,
        "streak": streak, "streak_needed": COVERAGE_STREAK,
        "income_complete": streak >= COVERAGE_STREAK,
        "funded_account": acct, "payout_share": PAYOUT_SHARE,
        "required_monthly_pct": round(req_pct, 2) if req_pct is not None else None,
    }


def hero() -> dict:
    """Everything the /goal ladder hero shows: stage, next rung + derived date,
    progress, the C3 status word, and the coverage ratio."""
    L = ladder()
    ms = L["milestones"]
    done = [m for m in ms if m["done"]]
    nxt = next((m for m in ms if not m["done"]), None)
    cur = L["stack"]["btc_total"] if L["stack"] else None

    prev_btc = done[-1]["btc"] if done else 0.0
    pct = None
    if cur is not None and nxt and nxt["btc"] > prev_btc:
        pct = max(0.0, min(100.0, (cur - prev_btc) / (nxt["btc"] - prev_btc) * 100.0))

    try:
        from .cone import status as cone_status
        cs = cone_status()
    except Exception:
        cs = {}

    return {
        "stage": done[-1]["label"] if done else "Pre-seed",
        "stage_btc": prev_btc,
        "next": nxt,
        "stack_btc": cur,
        "goal_btc": L["plan"]["goal_btc"],
        "progress_pct": round(pct, 1) if pct is not None else None,
        "overall_pct": round(cur / L["plan"]["goal_btc"] * 100, 2) if cur else None,
        "status": cs.get("status"), "status_source": cs.get("source"),
        "stack_stale": L["stack_stale"], "stack_age_days": L["stack_age_days"],
        "coverage": coverage(),
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
