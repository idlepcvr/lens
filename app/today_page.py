"""LENS /today — the two numbers, and nothing else.

Built 2026-08-20 after the ledger answered a question nobody asked: since 1 May,
110 trades and 23 of them had a signal behind them. The engine had been pointing
long (211 signals to 36) while the book ran short (65 to 45). Two systems with no
contact, and no surface anywhere that would have shown it.

So this page holds exactly two things:

  1. THE NEXT RUNG — not the 2028 number. The v3 amendment rebased the ladder so
     the next target is always within one doubling; staring at 50 BTC instead is
     what makes the whole thing feel like it needs 16% a week.
  2. YESTERDAY — signals fired, how many were acted on, how many fills had no
     signal at all.

# ponytail: counts only, no P&L attribution and no advice. His call — the page
# reports, he reads it. Add the on/off-signal P&L split if the count alone stops
# landing.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import plan
from .database import _conn
from .theme import shell

ADHERENCE_DAYS = 30


# ─── data ────────────────────────────────────────────────────────────────────

def _next_rung(ladder: dict) -> dict | None:
    for m in ladder["milestones"]:
        if not m.get("done"):
            return m
    return None


def _window(day: date) -> tuple[str, str]:
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def adherence(since: str, until: str) -> dict:
    """Fills and signals over [since, until). Counts only."""
    c = _conn()
    fired = c.execute(
        "SELECT COUNT(*) FROM signals WHERE received_at >= ? AND received_at < ?",
        (since, until)).fetchone()[0]
    acted = c.execute(
        "SELECT COUNT(DISTINCT linked_signal_id) FROM trades "
        "WHERE linked_signal_id IS NOT NULL AND opened_at >= ? AND opened_at < ?",
        (since, until)).fetchone()[0]
    fills = c.execute(
        "SELECT COUNT(*) FROM trades WHERE opened_at >= ? AND opened_at < ?",
        (since, until)).fetchone()[0]
    orphan = c.execute(
        "SELECT COUNT(*) FROM trades WHERE linked_signal_id IS NULL "
        "AND opened_at >= ? AND opened_at < ?", (since, until)).fetchone()[0]
    c.close()
    return {"fired": fired, "acted": acted, "fills": fills, "orphan": orphan,
            "rate": (fills - orphan) / fills if fills else None}


def parts() -> dict:
    ladder = plan.ladder()
    snap = ladder["stack"]
    cur = snap["btc_total"] if snap else 0.0
    rung = _next_rung(ladder)

    prev = _next_rung_floor(ladder, rung)
    span = (rung["btc"] - prev) if rung else 0.0
    pct = max(0.0, min(1.0, (cur - prev) / span)) if span > 0 else 0.0
    gap = (rung["btc"] - cur) if rung else 0.0
    days = _days_to(rung.get("date")) if rung else None

    y = date.today() - timedelta(days=1)
    yday = adherence(*_window(y))
    win = adherence((date.today() - timedelta(days=ADHERENCE_DAYS)).isoformat(),
                    (date.today() + timedelta(days=1)).isoformat())

    return {"cur": cur, "rung": rung, "prev": prev, "pct": pct, "gap": gap,
            "days": days, "yday": yday, "yday_date": y, "win": win,
            "stale": ladder["stack_stale"], "snap_date": snap["date"] if snap else None,
            "stack_age": ladder["stack_age_days"]}


def _next_rung_floor(ladder: dict, rung: dict | None) -> float:
    """The rung below the next one — the bar's left edge. 0 if it's the first."""
    if not rung:
        return 0.0
    prev = 0.0
    for m in ladder["milestones"]:
        if m is rung or m.get("btc") == rung.get("btc"):
            break
        prev = m["btc"]
    return prev


def _days_to(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (date.fromisoformat(str(iso)[:10]) - date.today()).days
    except ValueError:
        return None


# ─── view ────────────────────────────────────────────────────────────────────

CSS = """<style>
.tdy{max-width:760px;margin:0 auto}
.tdy h2{font:600 11px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;
  color:var(--dim);margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.tdy section{margin:0 0 42px}
.rung{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:18px}
.rung b{font:600 30px/1 var(--mono);color:var(--ink)}
.rung .lbl{font:400 13px/1 var(--mono);color:var(--dim)}
.bar{position:relative;height:6px;background:var(--panel);border:1px solid var(--line);border-radius:3px}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--accent);border-radius:2px;display:block}
.ends{display:flex;justify-content:space-between;margin-top:8px;
  font:400 12px/1 var(--mono);color:var(--dim)}
.need{margin-top:16px;font:400 14px/1.5 var(--mono);color:var(--ink)}
.need s{text-decoration:none;color:var(--dim)}
.rows{width:100%;border-collapse:collapse;font:400 14px/1 var(--mono)}
.rows td{padding:11px 0;border-bottom:1px solid var(--line)}
.rows td+td{text-align:right;font-weight:600;color:var(--ink)}
.rows tr:last-child td{border-bottom:none}
.rows .off td+td{color:var(--short)}
.note{margin-top:12px;font:400 12px/1.6 var(--mono);color:var(--faint)}
.warn{margin-bottom:20px;padding:10px 12px;border:1px solid var(--amber-d);
  border-radius:4px;font:400 12px/1.5 var(--mono);color:var(--amber)}
</style>"""


def _pct(v) -> str:
    return "—" if v is None else f"{v*100:.0f}%"


def body(p: dict) -> str:
    rung, cur = p["rung"], p["cur"]
    stale = ""
    if p["stale"]:
        stale = (f"<div class=warn>Stack snapshot is {p['stack_age']} days old "
                 f"({p['snap_date']}). The rung below is measured against it.</div>")

    if rung:
        when = f" · {rung['date']}" if rung.get("date") else ""
        dtxt = ("overdue" if p["days"] is not None and p["days"] < 0
                else f"{p['days']} days left" if p["days"] is not None else "no date")
        top = (
            f"<div class=rung><b>{rung['btc']:.4f} BTC</b>"
            f"<span class=lbl>{rung['label']}{when}</span></div>"
            f"<div class=bar><i style='width:{p['pct']*100:.1f}%'></i></div>"
            f"<div class=ends><span>{p['prev']:.4f}</span>"
            f"<span>{p['pct']*100:.0f}%</span><span>{rung['btc']:.4f}</span></div>"
            f"<div class=need>at <b>{cur:.5f}</b> · need "
            f"<b>{p['gap']:.5f} BTC</b> <s>·</s> {dtxt}</div>"
        )
    else:
        top = "<div class=need>Every rung on the ladder is cleared.</div>"

    y, w = p["yday"], p["win"]
    return f"""<div class=tdy>
{stale}
<section>
  <h2>Next rung</h2>
  {top}
  <div class=note>The ladder was rebased on 2026-08-06 so the next target is
  always within one doubling. This is that target. The 2028 number lives on
  <a href="/goal">/goal</a> and is not today's business.</div>
</section>

<section>
  <h2>Yesterday · {p['yday_date']}</h2>
  <table class=rows>
    <tr><td>signals fired</td><td>{y['fired']}</td></tr>
    <tr><td>you acted on</td><td>{y['acted']}</td></tr>
    <tr class=off><td>fills with no signal</td><td>{y['orphan']}</td></tr>
  </table>
</section>

<section>
  <h2>Last {ADHERENCE_DAYS} days</h2>
  <table class=rows>
    <tr><td>signals fired</td><td>{w['fired']}</td></tr>
    <tr><td>fills</td><td>{w['fills']}</td></tr>
    <tr class=off><td>fills with no signal</td><td>{w['orphan']}</td></tr>
    <tr><td>on-signal rate</td><td>{_pct(w['rate'])}</td></tr>
  </table>
  <div class=note>A fill counts as on-signal when <code>database._link_signal</code>
  claimed one for it — an <b>approved</b> signal, same direction, entry within
  tolerance. A signal left pending or expired never links, so a low rate here can
  mean the signal was never decided as much as never followed. Counts only.</div>
</section>
</div>"""


def render() -> str:
    p = parts()
    return shell("/today", "Today", body(p), head_extra=CSS,
                 meta="the next rung, and whether I followed the system")
