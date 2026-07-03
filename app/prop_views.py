"""LENS — PROP engine pages.

The cockpit split into focused, single-purpose pages (the user's spec):
  /prop      Goals hub — visual target + the 3 upgrades, links to engines
  /strategy  Strategy Engine — WR, R, expectancy, frequency
  /risk      Risk Engine — account, risk, stop, position size, leverage
  /survival  Survival Engine — DD limit, max hist DD, loss-streak stress
  /rules     Prop Rules Engine — the live Kraken Prop constraint layer
  /equity    Equity Curve Simulator — Monte Carlo paths (client canvas)

All numbers come from one place: prop_metrics() (built on prop_eval), so no
view can drift from another. Server-rendered except /equity (needs a canvas).
"""

from .theme import shell

HERO = "ASIAN_RSI_DIP_v1"
# Defaults only — the live eval (account size / risk / plan) is persisted and read
# via prop_config(). These are the fallback when nothing's been saved yet.
EVAL = "BREAKOUT_1STEP_TURBO"   # "Advanced" — the €20 plan
ACCOUNT = 5000.0
RISK = 0.5


def prop_config() -> dict:
    """Active eval params from the DB (account, risk, eval_name). Single source
    of truth for every prop page so a 'new eval' propagates everywhere."""
    from .database import get_prop_eval
    return get_prop_eval()


# ── shared metrics ────────────────────────────────────────────────────────────
def prop_metrics(strategy=HERO, eval_name=None, account=None, risk=None, months=30):
    """One dict with everything every engine page needs."""
    cfg = prop_config()
    eval_name = eval_name or cfg["eval_name"]
    account = account if account is not None else cfg["account"]
    risk = risk if risk is not None else cfg["risk"]
    from .prop_eval import eval_summary, _trade_log, _cached_df, EVALS
    from .backtest_engine import STRATEGIES

    s = eval_summary(strategy, eval_name, account, risk, months=months)
    if "error" in s:
        return s

    wr = s["win_rate_pct"] / 100.0
    win = s["avg_win_pct"] / 100.0            # +fraction of account per win
    loss = abs(s["avg_loss_pct"]) / 100.0     # +fraction per loss (magnitude)
    floor = s["dd_pct"] / 100.0
    # expectancy
    exp_pct = wr * s["avg_win_pct"] + (1 - wr) * s["avg_loss_pct"]   # avg_loss signed −
    exp_r = (exp_pct / s["risk_pct"]) if s["risk_pct"] else 0.0
    s["expectancy_pct"] = round(exp_pct, 3)
    s["expectancy_r"] = round(exp_r, 2)
    s["trades_per_week"] = round(s["trades_per_month"] / 4.345, 2)

    # max historical drawdown — walk the real trade sequence (compounding)
    strat = STRATEGIES[strategy]
    df = _cached_df(months, strat.get("timeframe", "4h"))
    trades = _trade_log(df, strat["signal_fn"], strat["params"], EVALS[eval_name], risk)
    eq, peak, maxdd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1 + t["pnl_pct"] / 100.0)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)
    s["max_hist_dd_pct"] = round(maxdd * 100, 2)
    try:
        s["last_price"] = round(float(df["close"].iloc[-1]), 2)
    except Exception:
        s["last_price"] = None

    # loss-streak stress table + bust point
    rows, bust_k = [], None
    for k in range(1, 9):
        eqk = (1 - loss) ** k
        dd = 1 - eqk
        p = (1 - wr) ** k
        busted = dd >= floor
        if busted and bust_k is None:
            bust_k = k
        rows.append({"k": k, "equity_usd": round(account * eqk),
                     "dd_pct": round(dd * 100, 1), "odds_pct": round(p * 100, 2),
                     "busted": busted})
    s["loss_streak"] = rows
    s["bust_k"] = bust_k
    dpt = (30.4 / s["trades_per_month"]) if s["trades_per_month"] else 0
    s["days_to_breach"] = round(bust_k * dpt) if bust_k else None
    s["bust_odds_pct"] = round((1 - wr) ** bust_k * 100, 2) if bust_k else 0.0
    return s


# ── shared chrome ─────────────────────────────────────────────────────────────
_CSS = r"""<style>
.pv h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pv .sub{color:var(--dim);font-size:13px;margin-bottom:22px}
.pv .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:18px}
.pv .panel h2{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-bottom:14px}
.pv .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.pv .card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.pv .card .lbl{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.pv .card .val{font-family:var(--mono);font-size:22px;font-weight:600;line-height:1.1}
.pv .card .note{font-size:11px;color:var(--dim);margin-top:4px}
.pv .green{color:var(--long)} .pv .red{color:var(--short)} .pv .amber{color:var(--amber)} .pv .ac{color:var(--accent)}
.pv table{width:100%;border-collapse:collapse;font-size:13px}
.pv th,.pv td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
.pv th{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:500}
.pv td{font-family:var(--mono)}
.pv tr.hl{background:var(--panel2)}
.pv .prose{color:var(--dim);font-size:13.5px;line-height:1.65}
.pv .prose strong{color:var(--ink)} .pv .prose code{font-family:var(--mono);color:var(--accent);background:var(--panel2);padding:1px 5px;border-radius:4px}
.pv .formula{font-family:var(--mono);font-size:13px;color:var(--ink);background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0;line-height:1.7}
/* engine links (hub) */
.pv .engines{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.pv a.eng{display:block;text-decoration:none;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:16px;transition:.15s}
.pv a.eng:hover{border-color:var(--line2);transform:translateY(-2px)}
.pv a.eng .t{font-family:var(--mono);font-size:14px;font-weight:700;color:var(--ink)}
.pv a.eng .d{font-size:12px;color:var(--dim);margin-top:5px;line-height:1.5}
.pv a.eng .u{font-size:11px;color:var(--accent);margin-top:8px;font-family:var(--mono)}
/* target corridor */
.pv .corridor{position:relative;height:74px;margin:26px 0 8px;border-radius:10px;overflow:hidden;
  background:linear-gradient(90deg, rgba(255,84,104,.22) 0%, rgba(255,84,104,.05) 18%, var(--panel2) 42%, var(--panel2) 70%, rgba(31,217,137,.10) 86%, rgba(31,217,137,.28) 100%)}
.pv .corridor .mark{position:absolute;top:0;bottom:0;width:2px}
.pv .corridor .mark.floor{left:6%;background:var(--short)}
.pv .corridor .mark.start{left:30%;background:var(--faint)}
.pv .corridor .mark.tgt{right:4%;background:var(--long)}
.pv .corridor .lab{position:absolute;font-family:var(--mono);font-size:11px;top:8px;white-space:nowrap}
.pv .corridor .lab.floor{left:6%;color:var(--short)} .pv .corridor .lab.start{left:31%;color:var(--ink)} .pv .corridor .lab.tgt{right:4%;color:var(--long);text-align:right}
.pv .corridor .sub{position:absolute;bottom:8px;font-family:var(--mono);font-size:10px;color:var(--dim)}
.pv .corridor .sub.floor{left:6%} .pv .corridor .sub.start{left:31%} .pv .corridor .sub.tgt{right:4%}
.pv .up{display:flex;gap:12px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--line)}
.pv .up:last-child{border-bottom:none}
.pv .up .num{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--accent);min-width:26px}
.pv .up .txt strong{color:var(--ink)} .pv .up .txt{font-size:13.5px;color:var(--dim);line-height:1.55}
.pv .up .txt .arrow{color:var(--long)}
</style>"""


def _card(lbl, val, note="", cls=""):
    return (f'<div class="card"><div class="lbl">{lbl}</div>'
            f'<div class="val {cls}">{val}</div>'
            f'<div class="note">{note}</div></div>')


def _err(path, label, m):
    return shell(path, label, f'<div class="pv"><div class="panel">error: {m.get("error")}</div></div>',
                 head_extra=_CSS)


# ── /prop — Goals hub ─────────────────────────────────────────────────────────
def goals_page():
    m = prop_metrics()
    if "error" in m:
        return _err("/prop", "Goals", m)
    a = m["account"]
    floor = round(a * (1 - m["dd_pct"] / 100))
    tgt = round(a * (1 + m["target_pct"] / 100))
    body = f"""
<div class="pv">
  <h1>Goals — the eval, visualised</h1>
  <div class="sub">${a:,.0f} eval · {HERO} @ {m['risk_pct']}% risk. Stay inside the corridor, reach the target. Pass odds ~<b class="green">{m['pass_pct']:.0f}%</b>.</div>

  <div class="panel">
    <h2>The target corridor</h2>
    <div class="corridor">
      <div class="mark floor"></div><div class="mark start"></div><div class="mark tgt"></div>
      <div class="lab floor">FLOOR</div><div class="lab start">START</div><div class="lab tgt">TARGET</div>
      <div class="sub floor">${floor:,} · −{m['dd_pct']:.0f}%</div>
      <div class="sub start">${a:,.0f}</div>
      <div class="sub tgt">${tgt:,} · +{m['target_pct']:.0f}%</div>
    </div>
    <div class="prose">Two kill-lines: touch <code>${floor:,}</code> (static floor) or lose {m['daily_pct']:.0f}% in a day.
      Win is <code>+{m['avg_win_pct']:.1f}%</code>, loss <code>{m['avg_loss_pct']:.1f}%</code> of the account — it takes
      <b>{m['bust_k']} losses in a row</b> to hit the floor (odds ≈ {m['bust_odds_pct']:.1f}%). You need about
      <b>{(m['target_pct']/m['avg_win_pct']):.0f} net wins</b> to pass. No time limit.</div>
  </div>

  <div class="panel">
    <h2>The 3 structural upgrades — and where each lives</h2>
    <div class="up"><div class="num">1</div><div class="txt"><strong>Equity curve + max-drawdown tracking</strong>
      <span class="arrow">→ replaces risk-of-ruin.</span> See it on <a href="/equity" class="ac">Equity Simulator</a> &amp; <a href="/survival" class="ac">Survival</a>.</div></div>
    <div class="up"><div class="num">2</div><div class="txt"><strong>Loss-streak stress testing</strong>
      <span class="arrow">→ replaces theoretical probability models.</span> See it on <a href="/survival" class="ac">Survival</a>.</div></div>
    <div class="up"><div class="num">3</div><div class="txt"><strong>Rule-based constraint layer</strong>
      <span class="arrow">→ makes it prop-firm realistic.</span> See it on <a href="/rules" class="ac">Prop Rules</a>.</div></div>
  </div>

  <div class="panel">
    <h2>The engines</h2>
    <div class="engines">
      <a class="eng" href="/strategy"><div class="t">Strategy</div><div class="d">WR {m['win_rate_pct']:.0f}% · {m['r_multiple']}R · expectancy {m['expectancy_r']}R</div><div class="u">open →</div></a>
      <a class="eng" href="/risk"><div class="t">Risk</div><div class="d">{m['risk_pct']}% / trade · {m['leverage']}x · sizing</div><div class="u">open →</div></a>
      <a class="eng" href="/survival"><div class="t">Survival</div><div class="d">floor {m['dd_pct']:.0f}% · bust at {m['bust_k']} losses · hist DD {m['max_hist_dd_pct']:.0f}%</div><div class="u">open →</div></a>
      <a class="eng" href="/rules"><div class="t">Prop Rules</div><div class="d">no time limit · no consistency · 3% daily</div><div class="u">open →</div></a>
      <a class="eng" href="/equity"><div class="t">Equity Simulator</div><div class="d">Monte Carlo paths vs the walls</div><div class="u">open →</div></a>
      <a class="eng" href="/regime"><div class="t">Regime</div><div class="d">is now a regime where the hero wins?</div><div class="u">open →</div></a>
    </div>
  </div>
</div>"""
    return shell("/prop", "Goals", body, head_extra=_CSS, meta="pass the eval")


# ── /strategy — Strategy Engine ───────────────────────────────────────────────
def _r_cols(rows, r_levels):
    """Cells for each R level: net R, green if profitable. The 'let winners run'
    sweep made visible — you can read straight across which R each one wins at."""
    by_r = {row["r"]: row for row in rows}
    out = ""
    for R in r_levels:
        row = by_r.get(R)
        if not row:
            out += "<td>·</td>"
            continue
        cls = "green" if row["net"] > 0 else "red"
        out += (f'<td class="{cls}" title="WR {row["wr"]}%">'
                f'{row["net"]:+.2f}</td>')
    return out


# mode -> (route, nav label, page title, blurb)
_BOARD_META = {
    "prop": ("/strategy", "Strategy", "Strategy Board — PROP",
             "Strategies for the <b>prop eval account</b> — the Asian-dip family, scored on the real 4H/1H backtest. "
             "These are <b>simulated</b> ranks over 7 yrs of candles, not your live results — those live on "
             '<a href="/edge" style="color:var(--accent)">Edge</a>. '
             "<b>thin</b> = the pattern fired &lt;40× in the entire history; too few occurrences to trust a rank "
             "(more samples need more history or a looser pattern, they can't be generated)."),
    "hedge": ("/strategy-hedge", "Board", "Strategy Board — HEDGE",
              "Strategies for the <b>hedge book</b> — 1h bar-context scalp setups. Simulated ranks, not live results "
              '(live = <a href="/edge" style="color:var(--accent)">Edge</a>).'),
}


def _board(results, mode, r_levels):
    ranked = sorted([o for o in results if o["mode"] == mode and not o["thin"]],
                    key=lambda x: x["rank"])
    thin = [o for o in results if o["mode"] == mode and o["thin"]]
    rcols_head = "".join(f"<th>{R:g}R</th>" for R in r_levels)
    body_rows = ""
    for o in ranked:
        hl = " class=\"hl\"" if o["top3"] else ""
        star = " ★" if o["top3"] else ""
        best = (f'<span class="green">{o["best_net"]:+.2f}R</span> @ {o["best_r"]:g}R'
                if o["best_net"] and o["best_net"] > 0
                else f'<span class="red">{o["best_net"]:+.2f}R</span>')
        body_rows += (
            f"<tr{hl}><td>{o['rank']}{star}</td>"
            f"<td>{o['name']}</td>"
            f"<td>{o['dir']}</td>"
            f"<td>{o['n']}</td>"
            f"<td>{o['sl']:.2f}%</td>"
            f"{_r_cols(o['rows'], r_levels)}"
            f"<td>{best}</td>"
            f"<td><b>{o['score']:.2f}</b></td></tr>")
    thin_note = ""
    if thin:
        thin_note = ('<div class="prose" style="margin-top:8px">thin (n&lt;40, not ranked): '
                     + ", ".join(f"{o['name']} (n={o['n']})" for o in thin) + "</div>")
    return f"""
  <div class="panel">
    <div style="overflow-x:auto"><table>
      <tr><th>#</th><th>strategy</th><th>dir</th><th>n</th><th>stop</th>
          {rcols_head}<th>best</th><th>score</th></tr>
      {body_rows}
    </table></div>
    {thin_note}
  </div>"""


def strategy_page(mode="prop"):
    from .strategy_eval import load_cache
    path, label, title, blurb = _BOARD_META[mode]
    d = load_cache()
    if not d:
        return shell(path, label,
                     f'<div class="pv"><h1>{title}</h1><div class="panel">'
                     'No rankings cached yet. Run <code>python3 -m app.strategy_eval</code> '
                     'to score every strategy.</div></div>',
                     head_extra=_CSS, meta="strategy board")
    rl = d["r_levels"]
    gen = d["generated_at"][:16].replace("T", " ")
    sub = (f'{blurb} Ranked after fees. '
           f'<span style="color:var(--faint)">R = {rl[0]:g}–{rl[-1]:g}, first-touch, net of {d["fee_pct"]}% round-trip · '
           f'{d["span"][0]} → {d["span"][1]} · refreshed {gen}</span>')
    body = f"""
<div class="pv">
  <h1>{title}</h1>
  <div class="sub">{sub}</div>
  {_board(d['results'], mode, rl)}
  <div class="panel"><h2>Read</h2><div class="prose">
    Each cell is <strong>net R per trade</strong> at that target multiple — green = profitable after fees.
    <strong>score</strong> sums the profitable cells weighted by R, so a strategy that still pays at 3R outranks
    one that only pays at 1R. Top 3 are highlighted.
    Mined in-sample; treat as a shortlist to forward-test, not a guarantee.</div></div>
</div>"""
    return shell(path, label, body, head_extra=_CSS, meta="strategy board")


# ── /risk — Risk Engine ───────────────────────────────────────────────────────
def risk_page():
    m = prop_metrics()
    if "error" in m:
        return _err("/risk", "Risk", m)
    a = m["account"]
    risk_usd = a * m["risk_pct"] / 100.0
    price = m.get("last_price")
    notional = risk_usd / (m["stop_pct"] / 100.0)        # full stop loses risk_usd
    units = (notional / price) if price else None
    stop_usd_move = (price * m["stop_pct"] / 100.0) if price else None
    cards = "".join([
        _card("Account", f"${a:,.0f}", "eval wallet (their capital)"),
        _card("Risk / trade", f"{m['risk_pct']}%", "of account", "amber"),
        _card("Risk / trade ($)", f"${risk_usd:,.0f}", "lost on a full stop", "amber"),
        _card("Stop distance", f"{m['stop_pct']}%", (f"≈ ${stop_usd_move:,.0f} on BTC ${price:,.0f}" if price else "fixed %, not ATR")),
        _card("Position (notional)", (f"${notional:,.0f}" + (f" · {units:.4f} ₿" if units else "")), "size that risks exactly risk$"),
        _card("Leverage", f"{m['leverage']}x", f"margin tool only · cap 5x · actual risk {m['actual_risk_pct']}%", "ac"),
    ])
    body = f"""
<div class="pv">
  <h1>Risk Engine</h1>
  <div class="sub">Sizing for survival on a {m['dd_pct']:.0f}% wall. Leverage is just the margin tool — risk % is the real dial.</div>
  <div class="panel"><h2>Sizing</h2><div class="grid">{cards}</div></div>
  <div class="panel"><h2>Position-size formula</h2>
    <div class="formula">
      risk$ = account × risk%&nbsp; = ${a:,.0f} × {m['risk_pct']}% = <b>${risk_usd:,.0f}</b><br>
      notional = risk$ ÷ stop% = ${risk_usd:,.0f} ÷ {m['stop_pct']}% = <b>${notional:,.0f}</b><br>
      leverage = notional ÷ account = <b>{m['leverage']}x</b> (capped at firm max 5x)
    </div>
    <div class="prose">A full stop-out loses exactly <code>${risk_usd:,.0f}</code> ({m['risk_pct']}%). The stop is a <strong>fixed {m['stop_pct']}%</strong>,
      not ATR-scaled — the edge is tuned to it (tighter stops got noise-hit in testing). On a {m['dd_pct']:.0f}% wall this {m['risk_pct']}% sizing
      is what buys the cushion: see <a href="/survival" class="ac">Survival</a>.</div></div>
</div>"""
    return shell("/risk", "Risk", body, head_extra=_CSS, meta="risk engine")


# ── /survival — Survival Engine ───────────────────────────────────────────────
def survival_page():
    m = prop_metrics()
    if "error" in m:
        return _err("/survival", "Survival", m)
    a = m["account"]
    rows = ""
    for r in m["loss_streak"]:
        cls = "red" if r["busted"] else ("amber" if r["dd_pct"] >= m["dd_pct"] * 0.66 else "green")
        hl = " hl" if (r["busted"] and r["k"] == m["bust_k"]) else ""
        rows += (f'<tr class="{hl.strip()}"><td>{r["k"]}</td>'
                 f'<td class="{cls}">${r["equity_usd"]:,}</td>'
                 f'<td class="{cls}">−{r["dd_pct"]}%</td>'
                 f'<td>{r["odds_pct"]}%</td>'
                 f'<td class="{"red" if r["busted"] else "green"}">{"✗ BUST" if r["busted"] else "✓ safe"}</td></tr>')
    cards = "".join([
        _card("Max DD limit", f"{m['dd_pct']:.0f}% static", f"floor ${round(a*(1-m['dd_pct']/100)):,}", "red"),
        _card("Max historical DD", f"{m['max_hist_dd_pct']:.0f}%", f"worst peak→trough, {m['months']}mo backtest"),
        _card("Busts at", f"{m['bust_k']} losses", "consecutive, from start", "red"),
        _card("Odds of that streak", f"{m['bust_odds_pct']:.1f}%", "on a fresh run", "amber"),
        _card("Days to breach", (f"~{m['days_to_breach']}" if m['days_to_breach'] else "—"), "at worst streak, back-to-back"),
        _card("MC fail (DD)", f"{m['fail_dd_pct']:.0f}%", "of paths bust · pass {:.0f}%".format(m['pass_pct'])),
    ])
    body = f"""
<div class="pv">
  <h1>Survival Engine</h1>
  <div class="sub">What actually busts you — the loss-streak stress test that replaces risk-of-ruin.</div>
  <div class="panel"><h2>Headline</h2><div class="grid">{cards}</div></div>
  <div class="panel"><h2>Loss-streak stress &amp; drawdown per streak</h2>
    <table><tr><th>Losses in a row</th><th>Account left</th><th>Drawdown</th><th>Odds of this streak</th><th>Status</th></tr>{rows}</table>
    <div class="prose" style="margin-top:12px">One loss ≈ <code>{m['avg_loss_pct']:.2f}%</code>; the floor is <code>−{m['dd_pct']:.0f}%</code>.
      So it takes <strong>{m['bust_k']} straight losses</strong> to bust (≈{m['bust_odds_pct']:.1f}% on a cold run){(' ≈ <strong>'+str(m['days_to_breach'])+' days</strong> back-to-back' if m['days_to_breach'] else '')}.
      Your worst historical drawdown was <strong>{m['max_hist_dd_pct']:.0f}%</strong> — comfortably inside the {m['dd_pct']:.0f}% wall at this sizing. Watch the live curve on <a href="/equity" class="ac">Equity Simulator</a>.</div></div>
</div>"""
    return shell("/survival", "Survival", body, head_extra=_CSS, meta="survival engine")


# ── /rules — Prop Rules Engine ────────────────────────────────────────────────
def rules_page():
    m = prop_metrics()
    if "error" in m:
        return _err("/rules", "Rules", m)
    a = m["account"]
    floor = round(a * (1 - m["dd_pct"] / 100))
    tgt = round(a * (1 + m["target_pct"] / 100))
    daily = round(a * m["daily_pct"] / 100)
    cards = "".join([
        _card("Daily loss limit", f"{m['daily_pct']:.0f}%", f"−${daily:,} · resets 00:30 UTC", "amber"),
        _card("Max loss (drawdown)", f"{m['dd_pct']:.0f}% static", f"floor ${floor:,} · never trails", "red"),
        _card("Profit target", f"+{m['target_pct']:.0f}%", f"pass at ${tgt:,}", "green"),
        _card("Minimum trading days", "NONE", "pass in one trade", "green"),
        _card("Consistency rule", "NONE", "one big win is fine", "green"),
        _card("Time limit", "NONE", "take months if needed", "green"),
        _card("News / weekend", "OK", "no holding restrictions", "green"),
        _card("Fees", "0.04%", "per side (maker+taker)"),
    ])
    body = f"""
<div class="pv">
  <h1>Prop Rules Engine</h1>
  <div class="sub">The constraint layer — Kraken Prop (Breakout), verified kraken.com/breakout 2026-06-17.</div>
  <div class="panel"><h2>The rules</h2><div class="grid">{cards}</div></div>
  <div class="panel"><h2>Read</h2><div class="prose">
    Only <strong>two kill conditions</strong>, both on <strong>live equity</strong> (open trades count): touch the
    <code>${floor:,}</code> static floor, or lose <code>${daily:,}</code> in one day. Everything else is permissive —
    no consistency rule (the dangerous one) means a single big winner can't void the eval. This is the layer that makes
    the sim <strong>prop-firm realistic</strong> rather than a generic backtest.</div></div>
</div>"""
    return shell("/rules", "Rules", body, head_extra=_CSS, meta="prop rules")


# ── /equity — Equity Curve Simulator (client canvas) ──────────────────────────
_EQ_CSS = _CSS.replace("</style>", r"""
.pv .controls{display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px}
.pv .ctl{display:flex;flex-direction:column;gap:4px}
.pv .ctl label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.pv input[type=number]{background:var(--panel2);color:var(--ink);border:1px solid var(--line);font-family:var(--mono);font-size:13px;padding:7px 10px;border-radius:6px;width:90px}
.pv canvas{width:100%;height:340px;display:block;background:var(--bg);border-radius:8px;border:1px solid var(--line);margin-top:6px}
.pv .tally{display:flex;gap:24px;margin-top:14px;font-family:var(--mono);font-size:14px;flex-wrap:wrap}
.pv .tally b{font-size:22px;display:block}
.pv .reset{font-size:11px;color:var(--accent);cursor:pointer;text-decoration:underline;background:none;border:none;font-family:var(--mono)}
</style>""")


def equity_page():
    m = prop_metrics()
    if "error" in m:
        return _err("/equity", "Equity", m)
    # defaults seeded from the live hero metrics
    body = f"""
<div class="pv">
  <h1>Equity Curve Simulator</h1>
  <div class="sub">Random trades from WR + R:R → equity paths, drawdown, and failure frequency vs the walls. Seeded with the live hero; tweak to ask "what if".</div>
  <div class="panel">
    <div class="controls">
      <div class="ctl"><label>Win rate %</label><input type="number" id="wr" value="{m['win_rate_pct']:.0f}" step="1" min="1" max="99"></div>
      <div class="ctl"><label>Win %</label><input type="number" id="win" value="{m['avg_win_pct']:.2f}" step="0.1"></div>
      <div class="ctl"><label>Loss %</label><input type="number" id="loss" value="{abs(m['avg_loss_pct']):.2f}" step="0.1"></div>
      <div class="ctl"><label>Floor % (DD)</label><input type="number" id="floor" value="{m['dd_pct']:.0f}" step="0.5"></div>
      <div class="ctl"><label>Target %</label><input type="number" id="tgt" value="{m['target_pct']:.0f}" step="0.5"></div>
      <div class="ctl"><label>Account $</label><input type="number" id="acct" value="{m['account']:.0f}" step="500"></div>
      <div class="ctl"><label>&nbsp;</label><button class="reset" id="rst">reset to hero</button></div>
    </div>
    <canvas id="cv"></canvas>
    <div class="tally">
      <div>pass <b class="green" id="tPass">–</b></div>
      <div>fail (DD) <b class="red" id="tFail">–</b></div>
      <div>median trades <b id="tMed">–</b></div>
      <div>worst drawdown <b class="amber" id="tDD">–</b></div>
    </div>
    <div class="prose" style="margin-top:10px">{m['paths'] if 'paths' in m else 400} Monte Carlo paths · compounding · each ends on the floor (fail), target (pass), or runs out. This is upgrade #1+#2 made visual.</div>
  </div>
</div>"""
    script = r"""
const D = {wr:_WR_, win:_WIN_, loss:_LOSS_, floor:_FLR_, tgt:_TGT_, acct:_ACCT_};
const MAXT = 60, N = 400;
const $ = id => document.getElementById(id);
function st(){ return {wr:+$('wr').value/100, win:+$('win').value/100, loss:+$('loss').value/100,
  floor:+$('floor').value/100, target:+$('tgt').value/100, acct:+$('acct').value}; }
function simPath(S){
  let eq=1, pts=[1], peak=1, dd=0;
  for(let t=0;t<MAXT;t++){
    eq *= (Math.random()<S.wr)?(1+S.win):(1-S.loss);
    peak=Math.max(peak,eq); dd=Math.max(dd,(peak-eq)/peak); pts.push(eq);
    if(eq<=1-S.floor) return {pts,res:'fail',n:t+1,dd};
    if(eq>=1+S.target) return {pts,res:'pass',n:t+1,dd};
  }
  return {pts,res:'open',n:MAXT,dd};
}
function draw(){
  const S=st(), cv=$('cv'), dpr=window.devicePixelRatio||1, W=cv.clientWidth, H=cv.clientHeight;
  cv.width=W*dpr; cv.height=H*dpr; const x=cv.getContext('2d'); x.scale(dpr,dpr); x.clearRect(0,0,W,H);
  const yLo=1-S.floor-0.01, yHi=1+S.target+0.02;
  const X=t=>40+(W-55)*(t/MAXT), Y=e=>(H-26)-(H-40)*((e-yLo)/(yHi-yLo));
  function hl(eq,c,l){ x.strokeStyle=c;x.lineWidth=1;x.setLineDash([5,4]);x.beginPath();x.moveTo(40,Y(eq));x.lineTo(W-15,Y(eq));x.stroke();x.setLineDash([]);x.fillStyle=c;x.font='11px monospace';x.fillText(l,44,Y(eq)-4); }
  const a=S.acct;
  hl(1+S.target,'#1fd989','+'+(S.target*100).toFixed(0)+'% target ($'+Math.round(a*(1+S.target)).toLocaleString()+')');
  hl(1,'#465064','start ($'+a.toLocaleString()+')');
  hl(1-S.floor,'#ff5468','−'+(S.floor*100).toFixed(0)+'% floor ($'+Math.round(a*(1-S.floor)).toLocaleString()+')');
  let pass=0,fail=0,worst=0; const ns=[];
  for(let i=0;i<N;i++){
    const p=simPath(S); worst=Math.max(worst,p.dd);
    if(p.res==='pass'){pass++;ns.push(p.n);} else if(p.res==='fail'){fail++;ns.push(p.n);}
    x.strokeStyle=p.res==='pass'?'rgba(31,217,137,.28)':p.res==='fail'?'rgba(255,84,104,.26)':'rgba(130,142,166,.16)';
    x.lineWidth=1;x.beginPath();p.pts.forEach((e,t)=>t===0?x.moveTo(X(t),Y(e)):x.lineTo(X(t),Y(e)));x.stroke();
  }
  ns.sort((u,v)=>u-v); const med=ns.length?ns[Math.floor(ns.length/2)]:0, res=pass+fail;
  $('tPass').textContent=(res?100*pass/res:0).toFixed(0)+'%';
  $('tFail').textContent=(res?100*fail/res:0).toFixed(0)+'%';
  $('tMed').textContent=med||'–';
  $('tDD').textContent='−'+(worst*100).toFixed(1)+'%';
}
['wr','win','loss','floor','tgt','acct'].forEach(id=>$(id).addEventListener('input',draw));
$('rst').addEventListener('click',()=>{ $('wr').value=(D.wr).toFixed(0);$('win').value=D.win.toFixed(2);
  $('loss').value=D.loss.toFixed(2);$('floor').value=D.floor.toFixed(0);$('tgt').value=D.tgt.toFixed(0);$('acct').value=D.acct; draw(); });
window.addEventListener('resize',draw);
draw();
"""
    script = (script.replace("_WR_", f"{m['win_rate_pct']:.0f}")
                    .replace("_WIN_", f"{m['avg_win_pct']:.2f}")
                    .replace("_LOSS_", f"{abs(m['avg_loss_pct']):.2f}")
                    .replace("_FLR_", f"{m['dd_pct']:.0f}")
                    .replace("_TGT_", f"{m['target_pct']:.0f}")
                    .replace("_ACCT_", f"{m['account']:.0f}"))
    return shell("/equity", "Equity", body, head_extra=_EQ_CSS, script=script, meta="equity simulator")
