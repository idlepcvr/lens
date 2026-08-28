"""Track — the next rung, the band you should be inside, and the daily score.

Everything here is a VIEW over numbers that already exist. `plan.ladder()` owns
the milestone rungs, `cone.cone()` owns the Monte-Carlo band. This module adds
one thing neither has: a per-day score, so the ladder has a daily surface
instead of only a quarterly one.

Four components, weighted. Discipline is worth more than everything else put
together on purpose — the ledger's problem is cost x frequency, so a day that
trades well scores below a day that didn't break a rule.

  discipline  4   no trade that day was flagged off-plan (a quiet day keeps it)
  plan        3   at least one trade taken that WAS the plan (followed_plan=1)
  band        2   where cumulative P&L sits inside the cone's percentile band
  decision    1   a signal was approved or rejected — you showed up

Streak is NOT "points > 0". A streak day is: discipline kept AND you engaged
(logged a decision or took a trade). Otherwise doing nothing for a month would
read as a 30-day streak, which would make the number a lie.

Units follow cone.py: cumulative realized P&L in EUR, hedge book only.
"""

from datetime import date, datetime, timedelta

from .database import _conn
from .plan import LENS_BOOK

WEIGHTS = {"discipline": 4, "plan": 3, "band": 2, "decision": 1}
MAX_POINTS = sum(WEIGHTS.values())
WINDOW_DAYS = 30
NEAR_DAYS = 14        # horizon of the day-stepped band on /track

# Percentile position -> share of the band weight. Above the median pays more
# than below it, and under P10 pays nothing: that is the band saying you are
# off the trajectory, not merely behind it.
BAND_STEPS = ((75, 1.0), (50, 0.75), (25, 0.5), (10, 0.25))


def _d(iso: str) -> str:
    """Date half of an ISO timestamp — the ledger stores both forms."""
    return (iso or "")[:10]


def _window(days: int, today: date) -> list[str]:
    return [(today - timedelta(days=n)).isoformat() for n in range(days - 1, -1, -1)]


# ─── inputs ──────────────────────────────────────────────────────────────────

def _trades_by_day(since: str) -> dict:
    """date -> {'n', 'breached', 'on_plan', 'pnl'} for the hedge book.

    A trade counts on the day it OPENED — the day the decision was made. P&L is
    attributed on close, which is why the two are read from different columns.
    """
    c = _conn()
    rows = c.execute(
        "SELECT opened_at, closed_at, pnl, followed_plan, followed_strategy "
        "FROM trades WHERE book = ? AND opened_at >= ?", (LENS_BOOK, since)
    ).fetchall()
    c.close()
    out: dict = {}
    for r in rows:
        d = out.setdefault(_d(r["opened_at"]),
                           {"n": 0, "breached": 0, "on_plan": 0, "unreviewed": 0})
        d["n"] += 1
        # NULL means never reviewed, which is not a breach — only an explicit 0 is.
        # It isn't a pass either: an unreviewed day can't earn the plan points, and
        # the page says so rather than letting silence read as compliance.
        if r["followed_plan"] == 0 or r["followed_strategy"] == 0:
            d["breached"] += 1
        elif r["followed_plan"] == 1:
            d["on_plan"] += 1
        else:
            d["unreviewed"] += 1
    return out


def _decisions_by_day(since: str) -> dict:
    """date -> count of signals actually decided (approve or reject both count —
    a reject is a decision, and rejecting well is the edge)."""
    c = _conn()
    rows = c.execute(
        "SELECT substr(decided_at,1,10) AS d, COUNT(*) AS n FROM signals "
        "WHERE decided_at IS NOT NULL AND status IN ('approved','rejected') "
        "AND decided_at >= ? GROUP BY d", (since,)
    ).fetchall()
    c.close()
    return {r["d"]: r["n"] for r in rows}


def _cum_by_day(window: list[str]) -> dict:
    """date -> cumulative realized P&L through the END of that day, matching the
    axis cone.py projects in (all closed hedge trades, from the beginning)."""
    c = _conn()
    rows = c.execute(
        "SELECT substr(closed_at,1,10) AS d, SUM(pnl) AS p FROM trades "
        "WHERE book = ? AND pnl IS NOT NULL AND closed_at IS NOT NULL "
        "GROUP BY d ORDER BY d", (LENS_BOOK,)
    ).fetchall()
    c.close()
    running, out, i = 0.0, {}, 0
    daily = [(r["d"], r["p"] or 0.0) for r in rows]
    for day in window:
        while i < len(daily) and daily[i][0] <= day:
            running += daily[i][1]
            i += 1
        out[day] = round(running, 2)
    # days before the window still have to be summed in, or every day reads 0
    lead = sum(p for d, p in daily if d < window[0]) if window else 0.0
    return {d: round(v + lead, 2) for d, v in out.items()}


def _ts(d: str) -> int:
    return int(datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())


def band_at(points: list[dict], ts: int) -> dict | None:
    """Interpolate the cone's percentile band at `ts`. None outside its span —
    the cone is anchored monthly, so early-window days genuinely have no band and
    must score as n/a rather than as a miss.

    ponytail: linear between sampled points; the cone samples weekly, so the
    error is under a rounding step. Resample the cone if that stops being true.
    """
    if not points or ts < points[0]["t"] or ts > points[-1]["t"]:
        return None
    for a, b in zip(points, points[1:]):
        if a["t"] <= ts <= b["t"]:
            span = max(b["t"] - a["t"], 1)
            f = (ts - a["t"]) / span
            return {k: a[k] + f * (b[k] - a[k]) for k in a if k != "t"}
    return {k: v for k, v in points[-1].items() if k != "t"}


def band_position(cum: float, band: dict | None) -> tuple[int | None, float]:
    """(percentile floor the day cleared, share of the band weight earned).

    Returns (None, 0.0) when there is no band — the caller must render that as
    n/a, never as a zero, or a day the cone can't see looks like a bad day.
    """
    if not band:
        return None, 0.0
    for pct, share in BAND_STEPS:
        if cum >= band.get(f"p{pct}", 0.0):
            return pct, share
    return 0, 0.0


# ─── adherence ───────────────────────────────────────────────────────────────
# Did the book follow the engine? Absorbed from /today on 2026-08-21 when the two
# pages merged. This is NOT the discipline score above: discipline asks whether a
# trade obeyed its own plan, adherence asks whether a signal existed at all.
#
# The trade side is scoped to LENS_BOOK. /today was not, so its fill and orphan
# counts included every prop attempt — the same bug main.py fixed for /plan.
# `signals` has no book column (the engine fires once, not per book), so `fired`
# is genuinely cross-book and the page says so rather than implying a hedge-only
# denominator.

ADHERENCE_DAYS = 30


def adherence(since: str, until: str) -> dict:
    """Signals fired vs fills that had one, over [since, until). Counts only."""
    c = _conn()
    fired = c.execute(
        "SELECT COUNT(*) FROM signals WHERE received_at >= ? AND received_at < ?",
        (since, until)).fetchone()[0]
    acted = c.execute(
        "SELECT COUNT(DISTINCT linked_signal_id) FROM trades "
        "WHERE linked_signal_id IS NOT NULL AND book = ? "
        "AND opened_at >= ? AND opened_at < ?", (LENS_BOOK, since, until)).fetchone()[0]
    fills = c.execute(
        "SELECT COUNT(*) FROM trades WHERE book = ? AND opened_at >= ? AND opened_at < ?",
        (LENS_BOOK, since, until)).fetchone()[0]
    orphan = c.execute(
        "SELECT COUNT(*) FROM trades WHERE linked_signal_id IS NULL AND book = ? "
        "AND opened_at >= ? AND opened_at < ?", (LENS_BOOK, since, until)).fetchone()[0]
    c.close()
    return {"fired": fired, "acted": acted, "fills": fills, "orphan": orphan,
            "rate": (fills - orphan) / fills if fills else None}


def adherence_pair(today: date, days: int = ADHERENCE_DAYS) -> dict:
    """Yesterday, and the trailing window — the two frames /today showed."""
    y = today - timedelta(days=1)
    return {
        "yesterday": adherence(y.isoformat(), today.isoformat()),
        "yesterday_date": y.isoformat(),
        "window": adherence((today - timedelta(days=days)).isoformat(),
                            (today + timedelta(days=1)).isoformat()),
        "window_days": days,
    }


# ─── scoring ─────────────────────────────────────────────────────────────────

def score_day(trades: dict | None, decisions: int, cum: float,
              band: dict | None) -> dict:
    """Pure — one day in, one scored day out. All the DB work happens above."""
    t = trades or {"n": 0, "breached": 0, "on_plan": 0, "unreviewed": 0}
    disciplined = t["breached"] == 0
    engaged = decisions > 0 or t["n"] > 0
    pct, band_share = band_position(cum, band)

    # Discipline is a GATE, not just the heaviest component. A day with a breach
    # scores zero however well it went — profitable rule-breaking is the habit
    # this page exists to make expensive, so it must never outscore a clean day.
    parts = {
        "discipline": WEIGHTS["discipline"] if disciplined else 0,
        "plan": WEIGHTS["plan"] if t["on_plan"] > 0 else 0,
        "band": round(WEIGHTS["band"] * band_share, 2),
        "decision": WEIGHTS["decision"] if decisions > 0 else 0,
    }
    if not disciplined:
        parts = {k: 0 for k in parts}
    return {
        "parts": parts,
        "points": round(sum(parts.values()), 2),
        "max_points": MAX_POINTS,
        "trades": t["n"], "breaches": t["breached"], "on_plan": t["on_plan"],
        "unreviewed": t.get("unreviewed", 0), "decisions": decisions,
        "cum": cum, "band_pct": pct, "band": band,
        "disciplined": disciplined, "engaged": engaged,
        # the streak rule, in one place
        "kept": disciplined and engaged,
    }


def _streaks(days: list[dict]) -> dict:
    """Current run of kept days (counting back from the most recent) and the best
    run anywhere in the window."""
    cur = 0
    for d in reversed(days):
        if d["kept"]:
            cur += 1
        else:
            break
    best = run = 0
    for d in days:
        run = run + 1 if d["kept"] else 0
        best = max(best, run)
    return {"current": cur, "best": best}


# ─── the step plan ───────────────────────────────────────────────────────────

def step_plan(today: date = None) -> dict:
    """The rung, divided by the number of trades left to reach it.

    The hero says "0.0093 of 0.0149, 62%". True, and useless at the moment of a
    trade: nobody sizes an entry against a percentage of a milestone. This turns
    the same gap into the only number that can actually be acted on — what the
    NEXT trade has to make.

    Everything is in STACK euros, not account equity. The rung is a BTC target
    and the stack is what gets measured against it, so a step expressed in
    account terms would be answering a different question than the one the
    hero above it asks.

    The divisor is expected TRADES, not days: `days_left x trades_per_day` from
    the measured rate. A per-day figure quietly assumes you trade every day, and
    the ledger says otherwise.
    """
    today = today or date.today()
    from .plan import hero as _hero, ladder as _l
    try:
        H = _hero()
        L = _l()
    except Exception:
        return {"ok": False}

    nxt = H.get("next") or {}
    cur_btc, tgt_btc = H.get("stack_btc"), nxt.get("btc")
    if not cur_btc or not tgt_btc or tgt_btc <= cur_btc:
        return {"ok": False}

    from .database import get_lens_config
    try:
        px = float(get_lens_config().get("btc_price_eur") or 0) or None
    except Exception:
        px = None

    days_left = None
    if nxt.get("date"):
        try:
            days_left = (date.fromisoformat(str(nxt["date"])[:10]) - today).days
        except ValueError:
            days_left = None

    try:
        from .cone import near as _near
        tpd = (_near(7) or {}).get("trades_per_day") or 0.0
    except Exception:
        tpd = 0.0

    # No date, no rate, or the rung is already overdue: fall back to one step so
    # the section still answers "what does the next trade need to make" rather
    # than disappearing exactly when the plan is in trouble.
    steps = 1
    if days_left and days_left > 0 and tpd > 0:
        steps = max(1, round(days_left * tpd))

    # The phase the stack is in right now, and the rate the plan says it should
    # compound at. Before v8 the rates lived only in prose inside the amendment
    # reason, so no page could say which phase you were in — only how far from
    # the 2028 number, which is not a thing anyone acts on.
    phase = None
    try:
        for ph in (L.get("plan", {}).get("phases") or []):
            if cur_btc < ph["to_btc"]:
                phase = ph
                break
    except Exception:
        phase = None

    growth = tgt_btc / cur_btc
    per_step = growth ** (1.0 / steps) - 1.0
    nxt_btc = cur_btc * (1.0 + per_step)

    # where the stack was before the snapshot it is on now
    prev_btc = None
    c = _conn()
    row = c.execute("SELECT btc_total FROM stack_snapshot WHERE date < "
                    "(SELECT MAX(date) FROM stack_snapshot) ORDER BY date DESC "
                    "LIMIT 1").fetchone()
    c.close()
    if row is not None:
        prev_btc = row[0]

    eur = (lambda b: None if (b is None or not px) else round(b * px, 2))
    return {
        "ok": True, "px": px,
        "phase": (phase or {}).get("name"),
        "phase_rate": (phase or {}).get("rate_monthly"),
        "phase_to": (phase or {}).get("to_btc"),
        "label": nxt.get("label"), "date": nxt.get("date"),
        "days_left": days_left, "steps": steps,
        "trades_per_day": round(tpd, 2),
        "per_step_pct": round(per_step * 100, 2),
        "total_pct": round((growth - 1) * 100, 1),
        "prev_btc": prev_btc, "cur_btc": cur_btc,
        "next_btc": nxt_btc, "target_btc": tgt_btc,
        "prev_eur": eur(prev_btc), "cur_eur": eur(cur_btc),
        "next_eur": eur(nxt_btc), "target_eur": eur(tgt_btc),
        "gain_eur": (None if not px else round((nxt_btc - cur_btc) * px, 2)),
        "gain_btc": nxt_btc - cur_btc,
    }


def track(days: int = WINDOW_DAYS, today: date = None) -> dict:
    """The whole /track payload: next rung, the cone, the scored window."""
    today = today or date.today()
    window = _window(days, today)
    since = window[0]

    from .cone import cone as _cone, near as _near
    from .plan import hero as _hero
    try:
        C = _cone()
    except Exception:
        C = {"n": 0}
    # The near band is a second, shorter projection anchored on today — see
    # cone.near(). Kept separate from C rather than merged into it: they use
    # different anchors and different axes, and averaging them would produce a
    # band that describes neither question.
    try:
        NEAR = _near(NEAR_DAYS)
    except Exception:
        NEAR = {"n": 0}
    try:
        H = _hero()
    except Exception:
        H = {}

    points = C.get("points") or []
    trades = _trades_by_day(since)
    decisions = _decisions_by_day(since)
    cums = _cum_by_day(window)

    # The realised line drawn inside the fan: anchor -> today, on the cone's axis.
    # Without it the fan is a forecast nobody can check; with it, the gap between
    # plan and reality is the whole picture.
    #
    # The two series must share a baseline or the comparison is meaningless, and
    # they do NOT share one by default: cone._trades() has no book filter, so its
    # cumulative includes prop trades, while everything here is book='hedge'. So
    # anchor to the cone's own starting value and carry the shape from there.
    # ponytail: an offset, not a reconciliation — fix the filter in cone.py and
    # this constant goes to zero on its own. Deliberately not fixed here: four
    # pages quote the status word that filter feeds.
    actual, offset = [], 0.0
    if C.get("anchor"):
        a = date.fromisoformat(C["anchor"])
        span = _window((today - a).days + 1, today) if today >= a else []
        acum = _cum_by_day(span) if span else {}
        if span:
            offset = (C.get("anchor_cum") or 0.0) - acum[span[0]]
            actual = [{"t": _ts(d), "cum": round(acum[d] + offset, 2)} for d in span]

    # the band is scored on the same shifted axis, or every day reads as under P10
    cums = {d: round(v + offset, 2) for d, v in cums.items()}

    scored = []
    for d in window:
        row = score_day(trades.get(d), decisions.get(d, 0), cums.get(d, 0.0),
                        band_at(points, _ts(d)))
        row["date"] = d
        scored.append(row)

    # Real account equity, straight from the daily snapshots. The cone projects
    # cumulative P&L (deposits and withdrawals never touch it, which is why it is
    # the axis to PROJECT in) — but the number you actually recognise is the
    # balance, so the page can show it and the band is transformed to match.
    balances = []
    try:
        from .cone import _balances
        cutoff = (today - timedelta(days=400)).isoformat()
        balances = [{"t": _ts(d), "v": round(v, 2)}
                    for d, v in _balances() if d >= cutoff and v is not None]
    except Exception:
        balances = []

    nxt = H.get("next") or {}
    days_left = None
    if nxt.get("date"):
        days_left = (date.fromisoformat(nxt["date"]) - today).days

    earned = sum(d["points"] for d in scored)
    return {
        "today": today.isoformat(),
        "window_days": days,
        "days": scored,
        "streak": _streaks(scored),
        "score": {
            "earned": round(earned, 1),
            "possible": len(scored) * MAX_POINTS,
            "pct": round(earned / (len(scored) * MAX_POINTS) * 100, 1) if scored else 0.0,
            "weights": WEIGHTS,
            # trades in the window nobody has marked on-plan or off-plan. High
            # counts mean the discipline score is measuring silence, not conduct.
            "unreviewed": sum(d["unreviewed"] for d in scored),
            "traded_days": sum(1 for d in scored if d["trades"]),
        },
        "rung": {
            "label": nxt.get("label"), "btc": nxt.get("btc"),
            "date": nxt.get("date"), "days_left": days_left,
            "from_btc": H.get("stage_btc"), "stack_btc": H.get("stack_btc"),
            "progress_pct": H.get("progress_pct"),
            "stage": H.get("stage"), "goal_btc": H.get("goal_btc"),
            "overall_pct": H.get("overall_pct"),
            "stale": H.get("stack_stale"), "age_days": H.get("stack_age_days"),
        },
        "adherence": adherence_pair(today),
        "step": step_plan(today),
        "cone": C,
        "near": NEAR,
        "actual": actual,
        "balances": balances,
        "status": C.get("status") or H.get("status"),
    }
