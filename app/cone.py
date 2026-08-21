"""C3 — the projection cone on the equity curve, and the one status word.

The honesty surface. Monte-Carlo bands (P10/P25/P50/P75/P90) grown from the
ACTUAL trade history — bootstrapped realized P&L, so the expectancy and the
variance are the ones you really trade, not a tidy Gaussian. Below the sample
threshold the history can't speak: fall back to the plan's typed parameters and
say so on the badge. Never draw a history-based cone on six trades.

Units: cumulative realized P&L in EUR — the /analytics curve's primary series.
Deposits and withdrawals never touch it, which is the whole reason it's the axis
we project in. (`trades.balance_after` is NOT account equity on this ledger —
70 of 489 rows imply |return| > 60%, dozens exactly −100% — so per-trade returns
can't be computed from it, and normalizing by the daily snapshot instead flips
the sign of the mean depending on where you cap the outliers. The EUR P&L the
exchange reports is the one number that isn't an artifact.)

Trade size drifts as the account does, so a sampled old P&L is rescaled by one
robust scalar: today's balance ÷ the median balance across the sample window.

Anchored MONTHLY, not daily. Daily re-anchoring drags the cone along behind the
account and hides drift; a month-old anchor lets the gap open where you can see
it. The cone runs anchor → the next milestone's derived date.

One status word comes out — AHEAD / ON / BEHIND / OFF-PLAN — computed here and
only here, because /analytics, /goal, /calendar and /journal all quote it and
must never disagree.

The cone tracks the ENGINE (this account's realized P&L, where the math is
real). The milestone ladder tracks the STACK. Don't conflate them.
"""

import random
import statistics
from datetime import date, datetime, timedelta, timezone

from .database import _conn

PATHS = 2000          # Monte-Carlo paths; P10/P90 are stable to ~1% at this count
MIN_N = 30            # below this, history is noise — use plan params and badge it
MAX_HORIZON_DAYS = 730
DEFAULT_HORIZON_DAYS = 180   # when no milestone date is derivable (no stack snapshot)

WORDS = ("OFF-PLAN", "BEHIND", "ON", "AHEAD")


# ─── inputs ──────────────────────────────────────────────────────────────────

def _trades() -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT pnl, closed_at FROM trades "
        "WHERE closed_at IS NOT NULL AND pnl IS NOT NULL ORDER BY closed_at"
    ).fetchall()
    c.close()
    return [{"pnl": r["pnl"], "d": r["closed_at"][:10]} for r in rows]


def _balances() -> list[tuple[str, float]]:
    c = _conn()
    rows = c.execute(
        "SELECT snapshot_date, eur_balance FROM daily_snapshots "
        "WHERE eur_balance IS NOT NULL ORDER BY snapshot_date"
    ).fetchall()
    c.close()
    return [(r["snapshot_date"], r["eur_balance"]) for r in rows]


def _cum_at(trades: list[dict], upto: date) -> float:
    """Cumulative realized P&L through the end of `upto` — the anchor's value."""
    s = upto.isoformat()
    return sum(t["pnl"] for t in trades if t["d"] <= s)


def _balance_on(bals: list[tuple[str, float]], d: date) -> float:
    """Account equity on `d` — the last snapshot at or before it."""
    s = d.isoformat()
    prior = [b for dd, b in bals if dd <= s]
    return prior[-1] if prior else bals[0][1]


def _scale(trades: list[dict], bals: list[tuple[str, float]], base_bal: float) -> float:
    """base balance ÷ median balance across the sample window. One robust scalar
    instead of a per-trade denominator — see the module docstring."""
    if not trades or not bals:
        return 1.0
    lo, hi = trades[0]["d"], trades[-1]["d"]
    window = [b for d, b in bals if lo <= d <= hi and b > 0]
    med = statistics.median(window) if window else 0.0
    if med <= 0 or base_bal <= 0:
        return 1.0
    return base_bal / med


def _horizon(today: date) -> tuple[date, str]:
    """Next milestone's derived date — the cone's right edge — and its label."""
    from . import plan
    try:
        L = plan.ladder()
    except Exception:
        return today + timedelta(days=DEFAULT_HORIZON_DAYS), "next milestone"
    for m in L["milestones"]:
        if not m["done"] and m["date"]:
            d = date.fromisoformat(m["date"])
            if d > today:
                return min(d, today + timedelta(days=MAX_HORIZON_DAYS)), f"{m['btc']} ₿ · {m['label']}"
    return today + timedelta(days=DEFAULT_HORIZON_DAYS), "no derived milestone date (log a stack snapshot)"


def _plan_draw(now_bal: float):
    """(draw, trades_per_week, label) from the typed config — the fallback when
    the ledger is too small to speak. risk = the account loss the goal+date force,
    straight out of the goal model."""
    from .calculator import CalcError, compute_goal
    from .database import get_lens_config
    cfg = get_lens_config()
    wr = cfg.get("win_rate") or 0.4
    rr = cfg.get("rr_ratio") or 2.0
    tpw = cfg.get("trades_per_week") or 3.0
    risk = 0.02
    try:
        td = cfg.get("target_date")
        g = compute_goal(cfg["start_balance"], cfg["target_balance"],
                         date.fromisoformat(td) if isinstance(td, str) else td,
                         trades_per_week=tpw, win_rate=wr, rr_ratio=rr,
                         leverage=cfg.get("leverage") or 1.0)
        risk = g["risk_per_trade"] / 100.0
    except (CalcError, ArithmeticError, ValueError, KeyError, TypeError):
        pass
    win, loss = risk * rr * now_bal, -risk * now_bal
    return (lambda rng: win if rng.random() < wr else loss), tpw


def _trades_per_week(trades: list[dict]) -> float:
    if len(trades) < 2:
        return 1.0
    span = (date.fromisoformat(trades[-1]["d"]) - date.fromisoformat(trades[0]["d"])).days
    return len(trades) / max(span / 7.0, 1.0)


# ─── the simulation ──────────────────────────────────────────────────────────

# The projection compounds one risk appetite to the horizon, so the upper
# percentiles run away — P90 reaching tens of millions says nothing except that
# exponentials are exponential. Rather than capping the SIMULATION (which would
# quietly change the odds the band reports), the reported percentiles are bent
# toward a ceiling: below the knee they pass through untouched, above it they
# approach CEILING and never reach it.
#
# CEILING is "past this, LENS has nothing useful to say" — not a prediction and
# not a target. Stated in EUR as a magnitude; it came from a round $40M, and no
# FX conversion is applied because a soft asymptote does not deserve a rate.
CEILING = 40_000_000.0
KNEE = 20_000_000.0


def _soften(v: float) -> float:
    """Bend a value toward CEILING above KNEE. Continuous, and flat-passing
    below the knee so ordinary numbers are never distorted."""
    if v <= KNEE:
        return v
    import math
    span = CEILING - KNEE
    return KNEE + span * (1.0 - math.exp(-(v - KNEE) / span))


def _percentiles(vals: list[float]) -> dict:
    v = sorted(vals)
    last = len(v) - 1
    return {f"p{p}": round(_soften(v[min(last, int(p / 100 * last))]), 2)
            for p in (10, 25, 50, 75, 90)}


def _simulate(cum0: float, floor: float, draw, n_trades: int, sample_at: list[int]) -> list[dict]:
    """`draw(rng)` yields one trade's realized P&L in EUR. Cumulative P&L can't
    fall below `floor` = cum0 − equity: that's the account gone. A path that hits
    it stops trading — the cone must be allowed to say a path died."""
    rng = random.Random(42)                     # deterministic: same trades → same cone
    want = {idx: j for j, idx in enumerate(sample_at)}
    cols = [[] for _ in sample_at]
    for _ in range(PATHS):
        cum = cum0
        dead = False
        for i in range(n_trades + 1):
            if i in want:
                cols[want[i]].append(cum)
            if dead:
                continue
            cum += draw(rng)
            if cum <= floor:
                cum, dead = floor, True
    return [_percentiles(c) for c in cols]


def _status_word(actual: float, band: dict) -> str:
    if actual > band["p75"]:
        return "AHEAD"
    if actual >= band["p25"]:
        return "ON"
    if actual >= band["p10"]:
        return "BEHIND"
    return "OFF-PLAN"


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


# ─── the near band ───────────────────────────────────────────────────────────

def near(days: int = 14) -> dict:
    """The next `days` days, one step per calendar day, anchored on TODAY.

    cone() answers "where should I be by the rung" — it anchors at the start of
    the month and steps per trade, because that is the horizon the milestone is
    measured on. This answers the question underneath it: given where I actually
    am right now, where should tomorrow land?

    Two things differ from cone() and both matter:

      * It anchors on today's cumulative and today's balance, not the month's.
        A band that starts three weeks ago cannot tell you anything about
        tomorrow — by the time it reaches tomorrow it has already spent its
        variance on days that are now history.
      * It steps per DAY, not per trade. A day is converted to an expected trade
        count with the measured trades-per-week rate, so a day you would not
        normally trade carries the same band as the day before it. That flat
        stretch is the honest answer: no expected trades means no expected
        spread, and a band that fans out on a quiet Sunday would be a lie.

    Same draw as cone(): resampled from real closed trades when there are
    enough, the typed plan otherwise.
    """
    today = date.today()
    trades = _trades()
    bals = _balances()
    if not trades or not bals:
        return {"n": 0, "reason": "no closed trades or no balance snapshots"}

    now_bal = bals[-1][1]
    cum_now = sum(t["pnl"] for t in trades)
    n = len(trades)
    if n >= MIN_N:
        source = "measured"
        badge = f"measured — {n} closed trades"
        tpw = _trades_per_week(trades)
        k = _scale(trades, bals, now_bal)
        pnls = [t["pnl"] * k for t in trades]

        def draw(rng, _p=pnls):
            return _p[rng.randrange(len(_p))]
    else:
        source = "plan"
        badge = f"plan-assumed — insufficient sample (n={n})"
        draw, tpw = _plan_draw(now_bal)

    tpd = max(tpw, 0.01) / 7.0
    n_trades = max(1, min(round(tpd * days), 20_000))
    floor = cum_now - now_bal              # the account is gone at this cum P&L

    # day -> how many trades are expected to have happened by then. Days that
    # share a trade count share a band, which is what makes a quiet day flat.
    pairs = [(d, min(n_trades, round(d * tpd))) for d in range(days + 1)]
    sample_at = sorted({idx for _, idx in pairs})
    by_idx = dict(zip(sample_at, _simulate(cum_now, floor, draw, n_trades, sample_at)))

    points = [{"t": _ts(today + timedelta(days=d)), **by_idx[idx]} for d, idx in pairs]
    tomorrow = points[1] if len(points) > 1 else points[0]

    return {
        "n": n, "source": source, "badge": badge,
        "anchor": today.isoformat(), "anchor_cum": round(cum_now, 2),
        "balance": round(now_bal, 2), "base_balance": round(now_bal, 2),
        "floor": round(floor, 2),
        "trades_per_week": round(tpw, 2), "trades_per_day": round(tpd, 3),
        "n_trades": n_trades, "paths": PATHS, "days": days,
        "points": points,
        "tomorrow": {k: round(v, 2) for k, v in tomorrow.items() if k != "t"},
    }


def cone() -> dict:
    """The whole C3 payload: bands, badge, status word. `{"n": 0}` when there's
    nothing to project from."""
    today = date.today()
    trades = _trades()
    bals = _balances()
    if not trades or not bals:
        return {"n": 0, "reason": "no closed trades or no balance snapshots"}

    now_bal = bals[-1][1]
    anchor_date = max(today.replace(day=1), date.fromisoformat(trades[0]["d"]))
    cum_anchor = _cum_at(trades, anchor_date)
    cum_now = sum(t["pnl"] for t in trades)
    # ONE capital base for the whole cone: the equity the engine had at the anchor.
    # Sizing the draws off today's balance while measuring ruin against the anchor's
    # would mix two accounts. Withdraw capital mid-month and you fall behind the
    # cone — correct: you took fuel out of the engine.
    base_bal = _balance_on(bals, anchor_date)

    n = len(trades)
    if n >= MIN_N:
        source = "measured"
        badge = f"measured — {n} closed trades"
        tpw = _trades_per_week(trades)
        k = _scale(trades, bals, base_bal)
        pnls = [t["pnl"] * k for t in trades]
        def draw(rng, _p=pnls):
            return _p[rng.randrange(len(_p))]
    else:
        source = "plan"
        badge = f"plan-assumed — insufficient sample (n={n})"
        draw, tpw = _plan_draw(base_bal)

    horizon, milestone = _horizon(today)
    weeks = max((horizon - anchor_date).days, 7) / 7.0
    n_trades = max(1, min(round(tpw * weeks), 20_000))
    floor = cum_anchor - base_bal          # the account is gone at this cum P&L

    n_weeks = max(1, int(weeks))
    sample_at = sorted({0, n_trades} | {min(n_trades, round(w * tpw)) for w in range(1, n_weeks + 1)})
    bands = _simulate(cum_anchor, floor, draw, n_trades, sample_at)

    days_per_trade = (horizon - anchor_date).days / n_trades
    points = [{"t": _ts(anchor_date + timedelta(days=round(i * days_per_trade))), **b}
              for i, b in zip(sample_at, bands)]

    # today's band — linear interpolation between the two straddling samples
    t_now = _ts(today)
    band_now = {k: v for k, v in points[0].items() if k != "t"}
    for a, b in zip(points, points[1:]):
        if a["t"] <= t_now <= b["t"]:
            f = (t_now - a["t"]) / max(b["t"] - a["t"], 1)
            band_now = {k: a[k] + f * (b[k] - a[k]) for k in a if k != "t"}
            break

    word = _status_word(cum_now, band_now)
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = nxt - timedelta(days=1)
    me = next((p for p in points if p["t"] >= _ts(month_end)), points[-1])

    return {
        "n": n, "source": source, "badge": badge,
        "anchor": anchor_date.isoformat(), "anchor_cum": round(cum_anchor, 2),
        "horizon": horizon.isoformat(), "milestone": milestone,
        "balance": round(now_bal, 2), "base_balance": round(base_bal, 2),
        "floor": round(floor, 2),
        "trades_per_week": round(tpw, 2), "n_trades": n_trades, "paths": PATHS,
        "points": points,
        "now": {"t": t_now, "cum": round(cum_now, 2),
                **{k: round(v, 2) for k, v in band_now.items()}},
        "status": word,
        "month_end": {"date": month_end.isoformat(), "p50": me["p50"]},
    }


_cache: dict = {}


def status() -> dict:
    """The status word + the numbers behind it, for the pages that only quote it.
    Cached per (day, trade count, balance) — the cone is deterministic in those."""
    c = _conn()
    n = c.execute("SELECT COUNT(*) FROM trades WHERE pnl IS NOT NULL").fetchone()[0]
    row = c.execute("SELECT eur_balance FROM daily_snapshots WHERE eur_balance IS NOT NULL "
                    "ORDER BY snapshot_date DESC LIMIT 1").fetchone()
    c.close()
    key = (date.today().isoformat(), n, row["eur_balance"] if row else None)
    if _cache.get("key") != key:
        d = cone()
        _cache.update(key=key, val={
            "status": d.get("status"), "source": d.get("source"), "badge": d.get("badge"),
            "n": d.get("n"), "now": d.get("now"), "month_end": d.get("month_end"),
            # anchor_cum turns the month-end P50 (a cumulative figure) into a
            # month P&L target the calendar can hold against its own month total
            "anchor": d.get("anchor"), "anchor_cum": d.get("anchor_cum"),
        })
    return _cache["val"]


if __name__ == "__main__":   # ponytail: one runnable check
    d = cone()
    assert d["n"] == 0 or d["status"] in WORDS, d.get("status")
    if d["n"]:
        pts = d["points"]
        for p in pts:
            assert p["p10"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p90"], p
            assert p["p10"] >= d["floor"] - 0.01, ("path fell through the floor", p)
        assert pts[0]["t"] < pts[-1]["t"]
        assert pts[0]["p90"] == pts[0]["p10"] == d["anchor_cum"]     # anchor is a point
        # the cone widens after the anchor — it may later collapse onto the floor
        # if every path ruins, which is a verdict, not a bug
        assert max(p["p90"] - p["p10"] for p in pts) > 0
        assert _status_word(1e9, d["now"]) == "AHEAD"
        assert _status_word(d["floor"] - 1, d["now"]) == "OFF-PLAN"
    print({k: v for k, v in d.items() if k != "points"})
    print("points:", len(d.get("points", [])), "| first:", d["points"][0], "| last:", d["points"][-1])
