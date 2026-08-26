"""LENS /prop-track — the daily read on the eval, /hedge-track's missing twin.

/prop-goal is the monthly question (goal_page.render("prop") — is the basket
still on pace for the target, under the cone). This is the daily one: how far
from the target, how far from the floor, and did today breach the daily wall.
Everything the page needs already exists in `prop_ledger.prop_ledger_data()` —
this only reframes it around "today", the way track_page.py does for hedge.

No new computation, no new table. NEXT_SESSION.md: "the prop book has a goal,
a ladder and a horizon too, and the evaluation has never had the surface the
hedge book got."
"""
from datetime import datetime, timezone

from .database import get_trades
from .prop_ledger import prop_ledger_data
from .theme import shell


def _eur(v, dp: int = 0) -> str:
    if v is None:
        return "—"
    return f"{'−' if v < 0 else ''}${abs(v):,.{dp}f}"


def _days_trading() -> int:
    rows = get_trades(limit=5000, book="prop")
    opened = [t.opened_at for t in rows if t.opened_at]
    if not opened:
        return 0
    first = min(opened)
    now = datetime.now(timezone.utc)
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    return max((now - first).days, 0)


def render() -> str:
    d = prop_ledger_data()
    days = _days_trading()

    if d["passed"]:
        verdict, cls = "PASSED — eval target reached", "approved"
    elif d["failed"]:
        reason = ("max drawdown" if d["breach_dd"] else
                   "floor" if d["breach_floor"] else "daily loss limit")
        verdict, cls = f"FAILED — {reason} breached", "rejected"
    else:
        verdict, cls = "RUNNING", "pending"

    today_cls = "g" if d["today_pnl"] >= 0 else "r"
    daily_room = d["daily_limit_usd"] - max(-d["today_pnl"], 0)
    over = d["passed"] or d["failed"]   # the run is decided — no more "away"/"left"

    if over:
        target_row = (f"{_eur(d['to_target_usd'])} short when it ended"
                      if d["to_target_usd"] > 0 else
                      f"cleared by {_eur(-d['to_target_usd'])}")
        floor_row = (f"held with {_eur(d['to_floor_usd'])} to spare"
                    if d["to_floor_usd"] >= 0 else
                    f"breached by {_eur(-d['to_floor_usd'])}")
    else:
        target_row = f"{_eur(d['to_target_usd'])} away &middot; {d['progress_pct']:.1f}% of the way there"
        floor_row = f"{_eur(d['to_floor_usd'])} of room left"
    dd_row = f"drawdown reached {d['cur_dd_pct']:.1f}% of {d['dd_limit_pct']}% max"

    body = f"""
<div class="help-body" style="margin-bottom:12px">
<h4>What this page answers</h4>
<p>Three numbers a fixed-horizon eval actually needs day to day: how close to
the <b>target</b> ({_eur(d['target'])}, {d['target_pct']}% up), how close to the
<b>floor</b> ({_eur(d['floor'])}, {d['dd_limit_pct']}% max drawdown), and whether
<b>today</b> is inside the daily wall ({d['daily_limit_pct']}% of the day's
opening equity, {_eur(d['daily_limit_usd'])}). /prop-goal is the monthly
question — is the whole basket still on pace under the cone.</p>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;padding:6px 4px 10px">
<span class="m">{d['eval']} &middot; {_eur(d['account'])} account &middot; day {days}</span>
<span class="badge {cls}">{verdict}</span>
</div>
<table class="sb">
<tr><td>Live equity</td><td class="mono">{_eur(d['live_equity'])}
{f" (+{_eur(d['open_upnl'])} open)" if d['open_upnl'] else ''}</td></tr>
<tr><td>Today's P&amp;L</td><td class="{today_cls} mono">{_eur(d['today_pnl'])}
{f" &middot; {_eur(max(daily_room,0))} of daily room left" if not over else ''}</td></tr>
<tr><td>Target</td><td class="mono">{target_row}</td></tr>
<tr><td>Floor</td><td class="mono">{floor_row} &middot; {dd_row}</td></tr>
</table>
</div>

<details class="sect">
<summary>30-day detail &middot; {d['n_trades']} trades, {d['win_rate']:.0f}% win rate</summary>
<div class="sb-wrap" style="margin-top:10px">
<table class="sb">
<tr><th>wins</th><th>losses</th><th>avg win</th><th>avg loss</th>
<th>expectancy</th><th>total R</th><th>max loss streak</th></tr>
<tr><td>{d['wins']}</td><td>{d['losses']}</td><td class="mono">{_eur(d['avg_win'])}</td>
<td class="mono">{_eur(d['avg_loss'])}</td><td class="mono">{_eur(d['expectancy_usd'])}</td>
<td class="mono">{d['total_r']}</td><td>{d['max_loss_streak']}</td></tr>
</table>
</div>
</details>

<p class="m" style="margin-top:14px">Full ledger and manual log/close at
<a href="/prop-ledger">/prop-ledger</a>. Basket-level pace and the cone at
<a href="/prop-goal">/prop-goal</a>.</p>
"""
    return shell("/prop-track", "Track", body, meta="today's read on the eval")
