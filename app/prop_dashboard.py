"""LENS /prop-dashboard — the prop twin of /dashboard.

/dashboard counts EVERY book (it calls get_trades with no filter), so its "499
trades" is hedge's 491 plus the prop attempts. This page is scoped: prop trades,
prop signals, prop pending, and performance across every eval attempt.

Two scopes are deliberately different and both are correct:
  counters  — the CURRENT eval (book='prop'), because that's the run you're in.
  perf      — ALL attempts (book='prop*'), because one eval is 7 trades long and
              a win-rate over 7 trades is noise.
The current eval's walls, equity and verdict live on /prop-ledger; the time-to-
target cone lives on /prop-goal. This page is the front door that links them.
"""

from .database import get_signals, get_trades
from .theme import shell

# prop_scan stamps every signal it emits as "prop-<strategy>-<bar_ts>"
PROP_SIG_PREFIX = "prop-"


def prop_dashboard_data() -> dict:
    live = get_trades(limit=5000, book="prop")            # current eval only
    allp = get_trades(limit=5000, book="prop*")           # every attempt
    sigs = [s for s in get_signals(limit=5000)
            if str(s.get("signal_id", "")).startswith(PROP_SIG_PREFIX)]
    pending = [s for s in sigs if s["status"] == "pending"]

    from .review import review_analytics
    perf = review_analytics(book="prop")

    # Goal model (Monte-Carlo pass-rate for the live basket) — the same cone summary
    # /prop-goal computes, surfaced here so the dashboard answers "will it pass?".
    from .prop_goal import cone as goal_cone
    try:
        goal = goal_cone()
    except Exception as e:
        goal = {"error": str(e)}

    from .prop_views import prop_config
    cfg = prop_config()

    by_strat: dict = {}
    for s in sigs:
        by_strat[s["strategy_name"]] = by_strat.get(s["strategy_name"], 0) + 1

    return {
        "config": cfg,
        "n_live": len(live),
        "n_open": len([t for t in live if t.pnl is None]),
        "n_all": len(allp),
        "n_signals": len(sigs),
        "n_pending": len(pending),
        "by_strategy": sorted(by_strat.items()),
        "perf": perf,
        "goal": goal,
    }


_CSS = r"""<style>
.pd h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pd .sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.pd .scores{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-bottom:18px}
.pd .sc{display:block;text-decoration:none;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:16px;text-align:center;transition:.15s}
.pd .sc:hover{border-color:var(--accent)}
.pd .sc.pend{border-color:var(--amber)}
.pd .sc-n{font-family:var(--mono);font-size:28px;font-weight:800;color:var(--ink);line-height:1}
.pd .sc-l{font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--dim);margin-top:7px}
.pd .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin-bottom:16px}
.pd .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;position:relative;overflow:hidden}
.pd .card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--line2)}
.pd .card.g::after{background:var(--long)}.pd .card.r::after{background:var(--short)}
.pd .card.a::after{background:var(--amber)}.pd .card.b::after{background:var(--accent)}
.pd .card .lbl{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.pd .card .val{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1.05;color:var(--ink)}
.pd .card .note{font-size:10.5px;color:var(--dim);margin-top:4px}
.pd .sect2{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin:22px 0 9px}
.pd .links{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
.pd .lk{display:block;text-decoration:none;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 13px;transition:.15s}
.pd .lk:hover{border-color:var(--accent)}
.pd .lk b{display:block;color:var(--ink);font-size:12.5px;font-family:var(--mono)}
.pd .lk span{font-size:10.5px;color:var(--dim)}
.pd .empty{text-align:center;padding:22px;color:var(--dim);border:1px dashed var(--line2);border-radius:11px}
.pd .note-warn{background:rgba(255,176,32,.09);border:1px solid var(--amber);border-radius:9px;padding:9px 12px;font-size:11px;color:var(--dim);margin-top:10px}
</style>"""


def _card(lbl, val, note="", cls=""):
    return (f'<div class="card {cls}"><div class="lbl">{lbl}</div>'
            f'<div class="val">{val}</div><div class="note">{note}</div></div>')


def _goal_section(g: dict) -> str:
    """The goal-model summary as cards. Same numbers as /prop-goal's hero."""
    if not g or g.get("error") or g.get("pass_pct") is None:
        why = g.get("error", "no basket set") if g else "no basket set"
        return (f'<div class="empty"><b>Goal model unavailable</b><br>{why} — '
                f'set a basket on <a href="/prop-goal" class="ac">Goal</a>.</div>')
    days, eta, cost = g.get("median_days_to_target"), g.get("eta_date"), g.get("expected_cost_per_pass")
    pp = g["pass_pct"]
    return '<div class="grid">' + "".join([
        _card("Pass probability", f"{pp}%", f"{g.get('paths', 0):,} MC paths",
              "g" if pp >= 50 else "a"),
        _card("Median time to pass", f"{days}d" if days else "—",
              f"ETA {eta}" if eta else "no passers in horizon", "b"),
        _card("Signals / week", f"{g['signals_per_week']}",
              f"{g['trades_per_month']}/mo · basket of {len(g.get('basket', []))}", "b"),
        _card("Target / floor", f"${g['target']:,.0f}",
              f"floor ${g['floor']:,.0f} · −{g['dd_pct']}% wall", "r"),
        _card("Cost per pass", f"${cost:,.0f}" if cost else "—", "fee ÷ pass%", "a"),
    ]) + "</div>"


def dashboard_page() -> str:
    d = prop_dashboard_data()
    cfg, p = d["config"], d["perf"]
    acct = cfg["account"]

    scores = f"""
<div class="scores">
  <a class="sc" href="/prop-ledger"><div class="sc-n">{d['n_live']}</div><div class="sc-l">Trades → ledger</div></a>
  <a class="sc" href="/prop-signals"><div class="sc-n">{d['n_signals']}</div><div class="sc-l">Signals → queue</div></a>
  <a class="sc {'pend' if d['n_pending'] else ''}" href="/prop-desk"><div class="sc-n">{d['n_pending']}</div><div class="sc-l">Pending → desk</div></a>
</div>"""

    if not p.get("n"):
        perf = '<div class="empty"><b>No closed prop trades yet</b><br>The current eval has no realised trades.</div>'
    else:
        pnl = p["total_pnl"]
        wins = round(p["n"] * p["wr"] / 100)     # review_analytics reports wr, not W/L counts
        dd = f"−€{abs(p['max_dd_eur']):,.0f}"
        if p.get("max_dd_pct") is not None:
            dd += f" · {p['max_dd_pct']:.1f}%"
        perf = '<div class="grid">' + "".join([
            _card("Total P&amp;L", f"{'+' if pnl >= 0 else '−'}€{abs(pnl):,.0f}",
                  f"{p['n']} closed · all attempts", "g" if pnl >= 0 else "r"),
            _card("Win rate", f"{p['wr']}%", f"{wins}W / {p['n'] - wins}L", "b"),
            _card("Expectancy", f"€{p['expectancy']}", "per trade",
                  "g" if p["expectancy"] >= 0 else "r"),
            _card("Max drawdown", dd, "peak → trough", "r"),
            _card("Total fees", f"−€{abs(p['total_fees']):,.0f}", "trading costs", "a"),
            _card("Avg duration", f"{p['avg_dur_h']}h" if p.get("avg_dur_h") else "—",
                  "per trade", "b"),
        ]) + "</div>"
        if p.get("capital_note"):
            perf += f'<div class="note-warn">⚠ {p["capital_note"]}. Percent-of-capital figures are hidden rather than faked.</div>'

    strat = "".join(f'<div class="lk"><b>{n}</b><span>{c} signal(s)</span></div>'
                    for n, c in d["by_strategy"]) or \
            '<div class="empty">No prop signals emitted yet.</div>'

    body = f"""
<div class="pd">
  <h1>Prop Dashboard</h1>
  <div class="sub">Scoped to the prop book — <b>${acct:,.0f}</b> {cfg['eval_name']} at {cfg['risk']}% risk.
    Counters are the <b>current eval</b>; performance spans <b>every attempt</b>.
    The hedge twin is <a href="/plan" class="ac">/plan</a>.</div>

  {scores}

  <div class="sect2">performance · all prop attempts</div>
  {perf}

  <div class="sect2">goal model · will this basket pass? · <a href="/prop-survival#projection" class="ac">full cone →</a></div>
  {_goal_section(d['goal'])}

  <div class="sect2">signals by strategy</div>
  <div class="links">{strat}</div>

  <div class="sect2">engines</div>
  <div class="links">
    <a class="lk" href="/prop-survival"><b>Survival →</b><span>walls · bet size · streaks · both cones</span></a>
    <a class="lk" href="/prop-ledger"><b>Ledger →</b><span>equity vs the walls · past attempts</span></a>
    <a class="lk" href="/prop-income"><b>Income →</b><span>what a pass is worth</span></a>
    <a class="lk" href="/regime"><b>Regime →</b><span>does the hero win in this market?</span></a>
    <a class="lk" href="/prop"><b>All engines →</b><span>every prop page in one index</span></a>
  </div>
</div>"""
    return shell("/prop-plan", "Dashboard", body, head_extra=_CSS, meta="prop front door")
