"""LENS /robustness — are the discipline rules signal, or luck?

Runs the permutation test from research/perm_test.py server-side and renders the verdict:
shuffle P&L across the ledger's timestamps a few thousand times and ask how often
chance alone produces buckets as extreme as the ones the rules were derived from
(the 09:00 BKK bleed hour, the removed Saturday veto). Also tracks the conviction
calibration question — the journal fields are the dataset, still filling up.

Results are cached per ledger size, so the page recomputes only when a new
trade lands. CLI twin: `python3 research/perm_test.py` (10k shuffles).
"""

import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from .database import DB_PATH
from .theme import shell

N_SHUFFLES = 4000   # page-side; CLI uses 10k. SE of p≈0.25 at 4k shuffles ≈ ±0.007
BKK = timedelta(hours=7)

_cache: dict = {}


def load_trades(since: str | None = None) -> list[tuple[int, int, float]]:
    """(bkk_hour, bkk_weekday Mon=0, pnl) per closed trade, bucketed by opened_at."""
    q = "SELECT opened_at, pnl FROM trades WHERE pnl IS NOT NULL"
    if since:
        q += f" AND opened_at >= '{since}'"
    rows = sqlite3.connect(DB_PATH).execute(q).fetchall()
    out = []
    for ts, pnl in rows:
        dt = datetime.fromisoformat(ts.replace("Z", "")) + BKK
        out.append((dt.hour, dt.weekday(), pnl))
    return out


def _sums(keys, pnls):
    s = defaultdict(float)
    for k, p in zip(keys, pnls):
        s[k] += p
    return s


def perm_test(trades, n_shuffles=N_SHUFFLES, seed=42) -> dict:
    """Permutation test: p-values for the hour-9 bucket (fixed and
    selection-corrected over all 24 hours) and Saturday-as-best-weekday."""
    hours = [t[0] for t in trades]
    days = [t[1] for t in trades]
    pnls = [t[2] for t in trades]

    hr, dy = _sums(hours, pnls), _sums(days, pnls)
    obs = {
        "n": len(trades),
        "h9_pnl": hr.get(9, 0.0), "h9_n": hours.count(9),
        "worst_hr": min(hr, key=hr.get), "worst_hr_pnl": min(hr.values()),
        "sat_pnl": dy.get(5, 0.0), "sat_n": days.count(5),
    }

    hits_h9 = hits_worst = hits_sat = 0
    shuffled = pnls[:]
    rng = random.Random(seed)
    for _ in range(n_shuffles):
        rng.shuffle(shuffled)
        h = _sums(hours, shuffled)
        if h.get(9, 0.0) <= obs["h9_pnl"]:
            hits_h9 += 1
        if min(h.values()) <= obs["worst_hr_pnl"]:
            hits_worst += 1
        if max(_sums(days, shuffled).values()) >= obs["sat_pnl"]:
            hits_sat += 1

    obs.update(p_h9=hits_h9 / n_shuffles,
               p_worst=hits_worst / n_shuffles,
               p_sat=hits_sat / n_shuffles)
    return obs


def results() -> dict:
    """Both windows, cached by ledger size."""
    n = sqlite3.connect(DB_PATH).execute(
        "SELECT COUNT(*) FROM trades WHERE pnl IS NOT NULL").fetchone()[0]
    if _cache.get("n") != n:
        _cache.clear()
        _cache["n"] = n
        _cache["2026"] = perm_test(load_trades("2026-01-01"))
        _cache["life"] = perm_test(load_trades())
        _cache["cf"] = counterfactual()
    return _cache


def counterfactual() -> dict:
    """Retro-apply today's discipline rules to every historical trade: which
    would have been vetoed, what did they cost, and (for the cooldown, which was
    set a priori rather than bucket-mined) does the damage beat luck?"""
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT opened_at, symbol, pnl FROM trades WHERE pnl IS NOT NULL "
        "ORDER BY opened_at").fetchall()
    pnls, h9_idx, cool_idx, any_idx = [], [], [], []
    last_open: dict = {}
    for i, (ts, sym, pnl) in enumerate(rows):
        dt = datetime.fromisoformat(ts.replace("Z", ""))
        pnls.append(pnl)
        hit = False
        if (dt + BKK).hour == 9:
            h9_idx.append(i); hit = True
        prev = last_open.get(sym)
        if prev and timedelta(0) < dt - prev < timedelta(minutes=60):
            cool_idx.append(i); hit = True
        last_open[sym] = dt
        if hit:
            any_idx.append(i)

    obs_cool = sum(pnls[i] for i in cool_idx)
    hits = 0
    shuffled = pnls[:]
    rng = random.Random(7)
    for _ in range(N_SHUFFLES):
        rng.shuffle(shuffled)
        if sum(shuffled[i] for i in cool_idx) <= obs_cool:
            hits += 1

    total = sum(pnls)
    vetoed = sum(pnls[i] for i in any_idx)
    return {
        "n": len(pnls), "total": total,
        "h9": (len(h9_idx), sum(pnls[i] for i in h9_idx)),
        "cool": (len(cool_idx), obs_cool, hits / N_SHUFFLES),
        "any": (len(any_idx), vetoed),
        "rest": (len(pnls) - len(any_idx), total - vetoed),
    }


def conviction_rows() -> tuple[list, int, int]:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT conviction, COUNT(*), ROUND(SUM(pnl),0), "
        "ROUND(100.0*SUM(pnl>0)/COUNT(*),0) FROM trades "
        "WHERE pnl IS NOT NULL AND conviction IS NOT NULL "
        "GROUP BY conviction ORDER BY conviction").fetchall()
    tagged, total = con.execute(
        "SELECT SUM(conviction IS NOT NULL), COUNT(*) FROM trades "
        "WHERE pnl IS NOT NULL").fetchone()
    return rows, tagged or 0, total


def _badge(p: float) -> str:
    if p < 0.05:
        return '<span class="badge approved">beats luck</span>'
    if p < 0.30:
        return '<span class="badge pending">suggestive</span>'
    return '<span class="badge rejected">could be luck</span>'


def _eur(x: float) -> str:
    cls = "g" if x > 0 else "r"
    return f'<td class="{cls}">€{x:+,.0f}</td>'


def parts() -> dict:
    """Body only — this page carries no CSS of its own."""
    r = results()
    cf = r["cf"]
    conv, tagged, total = conviction_rows()

    hour_rows = ""
    for label, key in (("2026 only", "2026"), ("lifetime", "life")):
        o = r[key]
        hour_rows += (
            f"<tr><td class=\"m\">{label}</td>"
            f"<td>{o['h9_n']} trades</td>{_eur(o['h9_pnl'])}"
            f"<td>{o['p_h9']:.3f}</td><td><b>{o['p_worst']:.2f}</b></td>"
            f"<td>{_badge(o['p_worst'])}</td></tr>"
        )

    sat_rows = ""
    for label, key in (("2026 only", "2026"), ("lifetime", "life")):
        o = r[key]
        sat_rows += (
            f"<tr><td class=\"m\">{label}</td>"
            f"<td>{o['sat_n']} trades</td>{_eur(o['sat_pnl'])}"
            f"<td colspan=\"2\">{o['p_sat']:.2f}</td>"
            f"<td><span class=\"badge approved\">removal stands</span></td></tr>"
        )

    conv_rows = "".join(
        f"<tr><td>{c}</td><td>{n}</td>{_eur(p)}<td class=\"m\">{int(w)}%</td></tr>"
        for c, n, p, w in conv
    ) or '<tr><td colspan="4" class="m">no tagged trades yet</td></tr>'

    body = f"""
<div class="help-body" style="margin-bottom:12px">
<h4>What this page answers</h4>
<p>The discipline rules were found by slicing the ledger into hour and weekday
buckets and picking the extremes. Slice noise into 24 buckets and one bucket
<b>always</b> looks terrible. So: shuffle every trade's P&amp;L across the ledger's
timestamps {N_SHUFFLES:,} times and count how often pure chance produces buckets as
extreme as the real ones. <b class="g">Low p = the rule beats luck.</b>
<b class="a">High p = the rule may be noise-mined</b> — keep it or not, but know that.
Recomputes automatically when a new trade lands.</p>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="6">Rule 1 — no 09:00 BKK (the bleed hour)</th></tr>
<tr><th>window</th><th>bucket</th><th>p&amp;l</th><th>p if pre-named</th><th>p honest*</th><th>verdict</th></tr>
{hour_rows}
</table>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="6">Removed rule — Saturday veto (needs Saturday to be not-bad)</th></tr>
<tr><th>window</th><th>bucket</th><th>p&amp;l</th><th colspan="2">p (any weekday this good)</th><th>verdict</th></tr>
{sat_rows}
</table>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="5">Counterfactual — if today's rules had always been on (lifetime)</th></tr>
<tr><th>rule</th><th>trades hit</th><th>p&amp;l</th><th>p</th><th>note</th></tr>
<tr><td>no 09:00 BKK</td><td>{cf['h9'][0]}</td>{_eur(cf['h9'][1])}
<td class="m">{r['life']['p_worst']:.2f}</td><td class="m">honest p from above — bucket-mined</td></tr>
<tr><td>cooldown &lt;60m</td><td>{cf['cool'][0]}</td>{_eur(cf['cool'][1])}
<td><b>{cf['cool'][2]:.3f}</b></td><td class="m">rule was set a priori, so this p is honest</td></tr>
<tr><td><b>any rule</b></td><td>{cf['any'][0]}</td>{_eur(cf['any'][1])}
<td class="m">—</td><td class="m">{100*cf['any'][1]/cf['total']:.0f}% of lifetime net P&amp;L (€{cf['total']:+,.0f})</td></tr>
<tr><td class="m">everything else</td><td class="m">{cf['rest'][0]}</td>{_eur(cf['rest'][1])}
<td class="m">—</td><td class="m">the ledger with the rules applied</td></tr>
<tr><td colspan="5" class="m">Retro-tags use only objective entry-time facts (clock, gap
since last trade) — never outcomes. Bybit rows were purged from this ledger, so that rule
can't be retro-tested. Live signals are already auto-vetoed by these rules; rejected ones
are stored as the ongoing out-of-sample test.</td></tr>
</table>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb">
<tr><th colspan="4">Conviction calibration — does your gut grade mean anything?</th></tr>
<tr><th>conviction</th><th>trades</th><th>p&amp;l</th><th>win rate</th></tr>
{conv_rows}
<tr><td colspan="4" class="m">{tagged} of {total} closed trades tagged —
verdict unlocks around 50. Tag conviction on every trade.</td></tr>
</table>
</div>

<div class="help-body">
<h4>How to read it</h4>
<p><b>p if pre-named</b> — how often chance makes the 09:00 bucket this bad, if you
had named that hour <i>before</i> looking. It wasn't pre-named, so this flatters the rule.<br>
<b>p honest*</b> — how often chance makes <i>any</i> of the 24 hour buckets look this
bad. This is the number that matters, because the rule was found by picking the worst
bucket. <span class="a">Suggestive</span> means: kept as cheap insurance (one skipped
hour vs a possibly-real bleed), not proved. Rejected 09:00 signals are stored, so the
out-of-sample evidence accumulates on its own — check back every ~50 trades.</p>
</div>

<div class="foot">engine: research/perm_test.py · {N_SHUFFLES:,} shuffles · buckets by opened_at,
Bangkok clock · pnl only, never balance_after</div>
"""
    return {"body": body, "css": ""}


def render() -> str:
    return shell("/robustness", "Robustness", parts()["body"], meta="is it luck?")
