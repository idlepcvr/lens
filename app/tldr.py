"""The TL;DR band — every analysis page, answered in the plan's own units.

The pages this sits on (/evidence, /geometry, /audit, /prop-survival) were each
written in their own vocabulary: permutation tests, sigma, MAE/MFE, R-multiples.
All correct, none of it answerable by the only question that decides anything —
does this get me to 50 ₿ by 2028-12-31, and does it cover the burn on the way.

So every one of them opens with the same two blocks:

  what()   one plain sentence saying what the page is for, plus the questions
           it can and cannot answer. Page-specific, written per page.
  band()   the identical scoreboard on all of them, in the units the plan is
           written in: win rate, leverage, trades/week, monthly return, burn,
           and the distance to the goal. Identical everywhere on purpose — the
           same numbers in the same order, so they stop being a new dialect to
           learn on each page.

Nothing here computes anything new. Every figure is read from the same sources
the rest of the cockpit already uses (plan.coverage, review_analytics, the
active plan), so the band cannot disagree with the page under it.
"""

import datetime

_CSS = r"""<style>
.tldr{max-width:1000px;margin:0 auto 6px;padding:0 14px}
.tldr .what{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:15px 17px;margin-bottom:12px}
.tldr .what h3{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin:0 0 8px}
.tldr .what p{color:var(--ink);font-size:14px;line-height:1.6;margin:0 0 8px;max-width:74ch}
.tldr .what ul{margin:8px 0 0;padding-left:18px}
.tldr .what li{color:var(--dim);font-size:13px;line-height:1.65;margin-bottom:3px}
.tldr .what li b{color:var(--ink)}
.tldr .sb{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:15px 17px;margin-bottom:14px}
.tldr .sb h3{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--faint);margin:0 0 11px}
.tldr .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:9px;overflow:hidden}
.tldr .c{background:var(--panel2);padding:11px 13px}
.tldr .c .k{display:block;font-family:var(--mono);font-size:9px;letter-spacing:.13em;
  text-transform:uppercase;color:var(--faint)}
.tldr .c .v{display:block;font-family:var(--mono);font-size:18px;font-weight:700;margin:5px 0 2px;line-height:1.1}
.tldr .c .s{display:block;font-size:10.5px;color:var(--dim);line-height:1.45}
.tldr .g{color:var(--long)} .tldr .r{color:var(--short)} .tldr .a{color:var(--amber)}
.tldr .verdict{margin-top:11px;font-size:13.5px;line-height:1.6;color:var(--ink);
  border-radius:8px;padding:11px 13px;max-width:80ch}
.tldr .verdict.bad{background:rgba(255,93,108,.10);border:1px solid var(--short)}
.tldr .verdict.ok{background:rgba(31,217,137,.10);border:1px solid var(--long)}
.tldr .verdict b{font-family:var(--mono)}
</style>"""


def _cell(k, v, s, cls=""):
    return (f'<div class="c"><span class="k">{k}</span>'
            f'<span class="v {cls}">{v}</span><span class="s">{s}</span></div>')


def numbers() -> dict:
    """Every figure the band shows, from the sources the cockpit already uses."""
    from .plan import active_plan, coverage, latest_snapshot
    from .review import review_analytics

    p = active_plan()
    cov = coverage()
    a = review_analytics()
    snap = latest_snapshot() or {}

    goal_date = datetime.date.fromisoformat(str(p["goal_date"]))
    today = datetime.date.today()
    months_left = max(0, (goal_date.year - today.year) * 12 + goal_date.month - today.month)

    months = cov.get("months") or []
    recent = [m["flow"] for m in months[-3:]]
    avg_flow = round(sum(recent) / len(recent), 2) if recent else None
    acct = cov.get("funded_account") or 0.0
    # Monthly return as a percentage of the funded account — the unit the plan
    # is written in, not EUR, so it sits beside the required figure directly.
    actual_pct = round(avg_flow / acct * 100, 2) if (avg_flow is not None and acct) else None

    return {
        "goal_btc": p["goal_btc"], "goal_date": str(p["goal_date"]),
        "north_star_btc": p["north_star_btc"], "north_star_date": str(p["north_star_date"]),
        "months_left": months_left,
        "stack_btc": float(snap.get("btc_total") or 0.0),
        "burn": cov.get("burn_monthly_eur") or 0.0,
        "required_pct": cov.get("required_monthly_pct"),
        "actual_pct": actual_pct, "avg_flow": avg_flow,
        "coverage": cov.get("trailing3"),
        "account": acct,
        "wr": a.get("wr"), "n": a.get("n"), "expectancy": a.get("expectancy"),
    }


def band() -> str:
    """The scoreboard. Identical on every page that carries it, by design."""
    d = numbers()
    req, act = d["required_pct"], d["actual_pct"]
    on_track = act is not None and req is not None and act >= req

    gap = ("—" if (req is None or act is None)
           else f"{act - req:+.1f}pp")
    cells = "".join([
        _cell("Monthly return", f"{act:+.1f}%" if act is not None else "—",
              "measured · last 3 months", "g" if (act or 0) > 0 else "r"),
        _cell("Needed / month", f"{req:.0f}%" if req is not None else "—",
              f"to cover €{d['burn']:,.0f} burn", "a"),
        _cell("Gap", gap, "actual − needed", "g" if on_track else "r"),
        _cell("Win rate", f"{d['wr']}%" if d["wr"] is not None else "—",
              f"{d['n']} closed trades", "g" if (d["wr"] or 0) >= 50 else "r"),
        _cell("Per trade", f"€{d['expectancy']:,.2f}" if d["expectancy"] is not None else "—",
              "expectancy", "g" if (d["expectancy"] or 0) >= 0 else "r"),
        _cell("Stack", f"{d['stack_btc']:.2f} ₿",
              f"of {d['goal_btc']:.0f} ₿ goal", "r" if d["stack_btc"] < 1 else "g"),
        _cell("Time left", f"{d['months_left']} mo",
              f"to {d['goal_date']}", "a"),
    ])

    if on_track:
        verdict = (f'<div class="verdict ok">On the plan\'s own arithmetic this clears the bar: '
                   f'<b>{act:+.1f}%/mo</b> against the <b>{req:.0f}%/mo</b> the burn needs.</div>')
    else:
        a_txt = f"{act:+.1f}%" if act is not None else "no measured return yet"
        verdict = (
            '<div class="verdict bad">'
            f'<b>Not on track, and not close.</b> The engine returned <b>{a_txt}</b> a month '
            f'over the last three complete months. Covering the <b>€{d["burn"]:,.0f}</b> burn '
            f'needs <b>{req:.0f}%/mo</b> on the €{d["account"]:,.0f} account. '
            f'The stack is <b>{d["stack_btc"]:.2f} ₿</b> against a <b>{d["goal_btc"]:.0f} ₿</b> '
            f'goal with <b>{d["months_left"]} months</b> left. '
            'Every page below is a different way of asking why — none of them change this number.'
            '</div>')

    return ('<div class="tldr"><div class="sb">'
            '<h3>Does this get me to the goal?</h3>'
            f'<div class="row">{cells}</div>{verdict}</div></div>')


def what(title: str, lead: str, answers: list[str], cannot: str = "") -> str:
    """The page's own plain-English opener. `answers` are what it can tell you;
    `cannot` is the honest limit, which is the half that was always missing."""
    items = "".join(f"<li>{x}</li>" for x in answers)
    tail = f'<li><b>What it can\'t tell you:</b> {cannot}</li>' if cannot else ""
    return ('<div class="tldr"><div class="what">'
            f'<h3>{title}</h3><p>{lead}</p><ul>{items}{tail}</ul></div></div>')


def opener(title: str, lead: str, answers: list[str], cannot: str = "") -> str:
    """what() + band(), with the stylesheet emitted once. This is what pages use."""
    return _CSS + what(title, lead, answers, cannot) + band()
