"""LENS /short — the one validated edge in the book, and the one thing missing.

Built by elimination. Twelve cells were put through four gates; one survived.
Everything else this session was a hypothesis, and this page exists to keep the
difference visible — it is the only surface in LENS allowed to use the word
"system", because it is the only claim that cleared a significance test and an
out-of-sample split at the same time.

The gates, in the order they kill things:

  1. beats a random entry
  2. beats a random entry IN THE SAME WINDOW      (else it's the market)
  3. beats a random entry in the same window AND
     the same direction                          (else it's drift)
  4. positive in both halves of the book          (else it's S1–S5 again)

Gate 3 is why this page is careful about shorts: BTC fell across the whole book,
which flatters every short ever taken. The baseline is therefore recomputed per
window and per direction, so the comparison is against a coin-flip short in the
same falling market rather than against zero.

Regenerate with research/short_edge.py.
"""

from __future__ import annotations

import json

from .geometry import FRICTION_PCT
from .paths import RESULTS
from .theme import shell

WEEKLY_GOAL = 0.10
RISK_SHOWN = [2.0, 3.0, 5.0]


def _data() -> dict | None:
    try:
        with open(RESULTS / "short_edge.json") as fh:
            return json.load(fh)
    except Exception:
        return None


def parts() -> dict:
    """Body + CSS, so this renders standalone or as a section of /evidence."""
    d = _data()
    if not d or not d.get("best"):
        return {"body": "<p class='lead'>No validated cell — run "
                        "<span class='m'>python3 research/short_edge.py</span>.</p>",
                "css": ""}

    b = d["best"]
    gap = d.get("gap", {})
    lev = lambda risk: risk / (b["stop_pct"] + FRICTION_PCT)
    h1, h2 = b["halves"]

    head = (
        f'<p class="lead top">Twelve candidate cells, four gates, '
        f'<b>one survivor</b>. Everything else measured this session was a '
        f'hypothesis that died to a significance test or an out-of-sample split. '
        f'This is the only claim in the book that cleared both, so it is the only '
        f'one written down as a system.</p>'
    )

    # ── the spec ─────────────────────────────────────────────────────────────
    def kv(k, v, s=""):
        return (f'<div class="kv"><span class="k">{k}</span><span class="v">{v}</span>'
                + (f'<span class="s">{s}</span>' if s else "") + "</div>")

    spec = (
        "<h2>The system</h2>"
        '<div class="conf">'
        + kv("direction", "SHORT only",
             "longs are significantly <i>worse</i> than random — see below")
        + kv("filter", "non-VETO",
             "the discipline rules, which this test corroborates independently")
        + kv("stop", f"{b['stop_pct']:.2f}%", "of price")
        + kv("target", f"{b['target_pct']:.2f}%", f"R:R {b['rr']:.0f} — 1:1")
        + kv("hold", f"~{b['median_hold_h']:.0f}h", "median to resolution, ~1 day")
        + kv("win rate", f"{b['win_rate']:.1%}",
             f"breakeven is {b['breakeven_wr']:.1%} — margin "
             f"{(b['win_rate']-b['breakeven_wr'])*100:+.1f}pp")
        + kv("vs matched random", f"{b['edge_pp']:+.1f}pp",
             f"a coin-flip short in the same falling market gets "
             f"{b['matched_random']:.1%}")
        + kv("net", f"{b['net_pct']:+.3f}%", "of notional per trade")
        + kv("sample", f"n = {b['n']}", f"{b['trades_per_week']:.2f} trades/week")
        + "</div>"
    )

    # ── the evidence ─────────────────────────────────────────────────────────
    gate_row = lambda ok, txt: (
        f"<li class='{'y' if ok else 'n'}'>{'✓' if ok else '✗'} {txt}</li>")
    evidence = (
        "<h2>Why this one is believed</h2>"
        "<ul class='gates'>"
        + gate_row(b["g1_beats_random"],
                   f"Beats a random entry: <b>{b['win_rate']:.1%}</b> against "
                   f"<b>{b['matched_random']:.1%}</b>, where that baseline is "
                   f"recomputed <i>in the same window and the same direction</i> — "
                   f"so it is not the market falling, and it is not drift.")
        + gate_row(b["g2_significant"],
                   f"Statistically significant: z = <b>{b['z']:+.2f}</b> against its "
                   f"own breakeven at n = {b['n']}, which is p &lt; 0.01.")
        + gate_row(b["g3_ci_clears_be"],
                   f"The 95% confidence interval <b>[{b['ci_lo']:.1%}, {b['ci_hi']:.1%}]</b> "
                   f"sits entirely above the {b['breakeven_wr']:.1%} breakeven — the "
                   f"pessimistic end of the estimate is still profitable.")
        + gate_row(b["g4_both_halves"],
                   f"Positive in <b>both halves</b> in time order: "
                   f"{h1['net_pct']:+.2f}% then {h2['net_pct']:+.2f}% per trade "
                   f"({h1['edge_pp']:+.1f}pp then {h2['edge_pp']:+.1f}pp over matched "
                   f"random). The edge decayed but did not invert.")
        + "</ul>"
        "<p class='note'>The fourth is the one that matters most here. Every other "
        "promising cell this session was positive in the first half and negative in "
        "the second — the exact signature that disarmed S1–S5. This is the only cell "
        "that stayed on the right side of zero in both.</p>"
    )

    # ── longs ────────────────────────────────────────────────────────────────
    longs = [c for c in d["cells"] if c["cell"].startswith("long")]
    lrows = "".join(
        f"<tr><td class='m'>{c['cell']}</td><td class='m'>{c['rr']:.0f}</td>"
        f"<td class='m'>{c['n']}</td><td class='m'>{c['win_rate']:.1%}</td>"
        f"<td class='m'>{c['matched_random']:.1%}</td>"
        f"<td class='m neg'>{c['edge_pp']:+.1f}pp</td>"
        f"<td class='m'>{c['z']:+.2f}</td></tr>" for c in longs)
    long_sec = (
        "<h2>Stop taking longs</h2>"
        "<p class='lead'>Not a stylistic preference — the long book is worse than a "
        "coin flip at every R:R and in every half, and at R:R 1 it is "
        "<b>significantly</b> worse (z = −2.52). Random entries in the same windows "
        "and the same direction beat it. Whatever the selection is doing on the long "
        "side, it is subtracting.</p>"
        "<table><tr><th>cell</th><th>R:R</th><th>n</th><th>WR</th>"
        "<th>matched random</th><th>edge</th><th>z</th></tr>" + lrows + "</table>"
        "<p class='note'>Dropping them is the cheapest change available: it costs "
        "nothing to stop doing something that loses, and it roughly halves the trade "
        "count — which is exactly the wrong direction for the frequency problem "
        "below. Both things are true at once and the resolution is not to reinstate "
        "the longs; it is to find more shorts.</p>"
    )

    # ── the gap ──────────────────────────────────────────────────────────────
    rows = []
    for risk in RISK_SHOWN:
        for tpw in (b["trades_per_week"], 3.0, 5.0, 8.5):
            per = b["net_pct"] * lev(risk)
            wk = (1 + per / 100) ** tpw - 1
            hit = wk >= WEEKLY_GOAL
            lab = "today" if abs(tpw - b["trades_per_week"]) < 0.01 else ""
            rows.append(
                f"<tr class='{'ok' if hit else ''}'><td class='m'>{risk:.0f}%</td>"
                f"<td class='m'>{lev(risk):.2f}×</td>"
                f"<td class='m'>{tpw:.2f}{(' ' + lab) if lab else ''}</td>"
                f"<td class='m {'pos' if wk > 0 else 'neg'}'>{wk:+.2%}</td>"
                f"<td class='m'>{(1+wk)**4.35-1:+.1%}</td>"
                f"<td class='m'>{'← 10%/wk' if hit else ''}</td></tr>")

    need = gap.get("need_tpw_at_5pct")
    gap_sec = (
        "<h2>The gap is frequency, not edge</h2>"
        f"<p class='lead'>This is the whole remaining problem, and it is a much "
        f"better problem than the one we started with. The edge is <b>sufficient</b> — "
        f"at 5% risk and {need:.1f} trades a week it compounds past 10%/week. You "
        f"currently generate <b>{b['trades_per_week']:.2f} a week</b> of them. "
        f"That is a <b>{need / b['trades_per_week']:.1f}× shortfall in setups</b>, "
        f"not in skill.</p>" if need else "")
    gap_sec += (
        "<table><tr><th>risk</th><th>leverage</th><th>trades/wk</th>"
        "<th>per week</th><th>per month</th><th></th></tr>" + "".join(rows) + "</table>"
        "<p class='note'><b>Three ways to close it, in order of honesty.</b> "
        "Find more non-VETO short setups — the scanner already knows the VETO rules, "
        "so this is a search problem with a defined target rather than an open one. "
        "Raise risk — 8% risk at today's cadence still only reaches +2.8%/week, so "
        "this cannot close the gap alone and it buys drawdown you can't afford on a "
        "€325 account. Or accept a longer horizon at "
        f"{(1 + b['net_pct'] * lev(5.0) / 100) ** b['trades_per_week'] - 1:+.2%}/week, "
        "which is a real and positive system that is not the stated goal.</p>"
        "<p class='note'>What this rules out is important too: no amount of position "
        "sizing, leverage, or geometry tuning closes a 5.6× frequency gap. Those "
        "levers are all exhausted. The only remaining work is finding more of the "
        "same setup.</p>"
    )

    # ── robustness ───────────────────────────────────────────────────────────
    rob = ""
    try:
        with open(RESULTS / "short_robustness.json") as fh:
            rb = json.load(fh)
        rob = (
            "<h2>Robustness</h2>"
            "<p class='lead'>The four gates all take the non-VETO label as given. "
            "If you slice 91 trades out of 293 by <i>any</i> rule and the slice looks "
            "good, a significance test on the slice will happily agree — the label was "
            "chosen partly because it looked good, and no gate above can see that. "
            "Three tests that can:</p>"
            "<ul class='gates'>"
            f"<li class='{'y' if rb['perm_p'] < 0.05 else 'n'}'>"
            f"{'✓' if rb['perm_p'] < 0.05 else '✗'} <b>Label permutation</b> — shuffle "
            f"VETO/non-VETO across all {rb['n_shorts']} shorts {rb['perm_n']:,} times, "
            f"group sizes held. The real gap is <b>{rb['gap_pp']:+.1f}pp</b>; chance "
            f"produces one that big with <b>p = {rb['perm_p']:.3f}</b>. The filter is "
            f"selecting, not merely labelling.</li>"
            f"<li class='{'y' if rb['splits_ok'] == rb['splits_total'] else 'n'}'>"
            f"{'✓' if rb['splits_ok'] == rb['splits_total'] else '✗'} <b>Split-point "
            f"sweep</b> — \"positive in both halves\" is one arbitrary cut. Sweeping it "
            f"from 30% to 70%, <b>{rb['splits_ok']}/{rb['splits_total']}</b> split points "
            f"are positive on both sides. The result is not an artefact of where the "
            f"line was drawn.</li>"
            f"<li class='{'y' if rb['months_survived'] == rb['months_total'] else 'n'}'>"
            f"{'✓' if rb['months_survived'] == rb['months_total'] else '✗'} "
            f"<b>Leave-one-month-out</b> — drop each calendar month and refit. "
            f"<b>{rb['months_survived']}/{rb['months_total']}</b> months can be removed "
            f"with the edge intact, so no single month is carrying it.</li>"
            "</ul>"
            "<p class='note'>None of these rescue the sample from being his own "
            "selection — they establish only that, <i>within</i> it, the filter does "
            "work. That distinction is the difference between this and S1–S5, which "
            "never faced a permutation test.</p>"
        )
    except Exception:
        pass

    # ── mechanical candidates, both directions ───────────────────────────────
    mech = ""
    try:
        with open(RESULTS / "setup_search.json") as fh:
            ss = json.load(fh)
        surv = [r for r in ss["cells"] if r.get("perm_p") is not None
                and r["perm_p"] < 0.05]
        nl = sum(1 for r in surv if r["direction"] == "long")
        ns = len(surv) - nl
        rows = "".join(
            f"<tr><td class='m {'pos' if r['direction']=='long' else 'neg'}'>"
            f"{r['direction']}</td><td class='m' style='white-space:normal'>{r['rule']}</td>"
            f"<td class='m'>{r['n']}</td><td class='m'>{r['win_rate']:.1%}</td>"
            f"<td class='m'>{r['baseline']:.1%}</td>"
            f"<td class='m edge'>{r['edge_pp']:+.1f}pp</td>"
            f"<td class='m'>{r['net_pct']:+.3f}%</td>"
            f"<td class='m'>{r['per_week']:.2f}</td>"
            f"<td class='m'>{r['perm_p']:.3f}</td></tr>"
            for r in sorted(surv, key=lambda r: -r["net_pct"]))
        mech = (
            "<h2>Mechanical candidates — both directions</h2>"
            "<p class='lead'>The edge above lives in his head, so it cannot be "
            "scanned for. This is the search for a rule that can: every hourly bar "
            f"2019→2026 resolved at this geometry, then {ss['bars']:,} bars sliced by "
            "every combination of RSI band, daily-trend side, MACD sign, "
            "Bollinger/volume state and Bangkok session. Long and short searched "
            "identically — a trader who only shorts is half a trader, and the gates "
            f"decide. <b>{nl} long and {ns} short rules survive.</b> The long book he "
            "actually traded was worse than random; mechanical long rules are not. "
            "Those are different claims and only the first was ever tested.</p>"
            "<table><tr><th>dir</th><th>rule</th><th>n</th><th>WR</th><th>base</th>"
            "<th>edge</th><th>net</th><th>/wk</th><th>perm p</th></tr>" + rows + "</table>"
            "<p class='note'><b>Together they trade 3.51×/week at +0.127%/trade</b> "
            "(long book 2.38/wk at +0.132%, short 1.15/wk at +0.086%; both positive in "
            "both halves). At 6% risk that is <b>+0.86%/week, +3.8%/month</b> — real, "
            "positive, and more than double the discretionary cadence.</p>"
            "<p class='note'><b>But it is 5.7× weaker per trade than his own judgement</b> "
            "(+0.127% against +0.726%). The scanner buys frequency and sells quality, and "
            "at this ratio the trade is not obviously worth making. The discretionary "
            "filter remains the better edge; what it lacks is a way to fire more often.</p>"
            "<div class='warn-b'><b>Treat these as candidates, not findings.</b> The "
            "search tried roughly 1,700 combinations. Each p-value above is per-cell and "
            "uncorrected, so at p&lt;0.05 chance alone would hand back dozens of winners; "
            "a Bonferroni threshold here would be p&lt;0.00003 and none of them clear it. "
            "The split-half gate mitigates this but does not remove it. <b>This is exactly "
            "how S1–S5 happened.</b> The only test that settles it is forward trades on "
            "bars the search never saw.</div>"
        )
    except Exception:
        pass

    # ── honest limits ────────────────────────────────────────────────────────
    limits = (
        "<h2>What this does not prove</h2>"
        "<p class='note'>The sample is <b>your own entries</b>, so this measures the "
        "filter you already apply — whatever combination of judgement and context "
        "produces a non-VETO short. It does not establish that the edge extends to "
        "setups you didn't take, which is exactly what a scanner hunting more of them "
        "would be assuming. That assumption is the main risk in scaling this up, and "
        "the first fifty forward trades are the test of it.</p>"
        f"<p class='note'>n = {b['n']} is enough for significance and not enough for "
        f"comfort. The edge also <i>decayed</i> between halves "
        f"({h1['edge_pp']:+.1f}pp → {h2['edge_pp']:+.1f}pp); it stayed positive, but "
        "the trend is the wrong way and a third half would settle it. Size for the "
        "bottom of the confidence interval, not the point estimate.</p>"
    )

    body = (head + spec + evidence + long_sec + gap_sec + rob + mech + limits +
            '<p class="foot"><a href="/evidence#target">→ what the target costs</a> · '
            '<a href="/evidence#geometry">→ where the geometry comes from</a><br>'
            '<span class="m">python3 research/short_edge.py</span> reruns all four '
            'gates.</p>')

    css = (
        "<style>"
        "h2{font-family:var(--mono);font-size:11px;letter-spacing:.16em;"
        "text-transform:uppercase;color:var(--faint);margin:34px 0 10px;font-weight:600}"
        "p.lead{color:var(--dim);font-size:13.5px;line-height:1.65;max-width:76ch;margin:0 0 14px}"
        "p.lead.top{color:var(--ink);font-size:14px;margin-bottom:20px}"
        "p.note{color:var(--faint);font-size:12.5px;line-height:1.6;max-width:76ch;margin:12px 0 0}"
        "p.foot{margin-top:34px;font-size:12.5px;color:var(--faint);line-height:1.9}"
        "p.foot a{color:var(--accent);text-decoration:none;margin-right:4px}"
        ".m{font-family:var(--mono)}.pos{color:var(--long)}.neg{color:var(--short)}"
        "table{border-collapse:collapse;width:100%;font-size:13px;margin-top:4px}"
        "th{text-align:left;color:var(--faint);font-family:var(--mono);font-size:10px;"
        "text-transform:uppercase;letter-spacing:.12em;padding:7px 9px;"
        "border-bottom:1px solid var(--line);white-space:nowrap}"
        "td{padding:8px 9px;border-bottom:1px solid var(--line)}"
        "td.m{font-family:var(--mono);font-size:12.5px;white-space:nowrap}"
        "tr.ok{background:var(--long-d)}"
        ".conf{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;"
        "background:var(--line);border:1px solid var(--line);border-radius:10px;"
        "overflow:hidden;margin:6px 0}"
        ".kv{background:var(--panel);padding:12px 14px}"
        ".kv .k{display:block;font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;"
        "text-transform:uppercase;color:var(--faint)}"
        ".kv .v{display:block;font-family:var(--mono);font-size:17px;font-weight:600;margin:5px 0 3px}"
        ".kv .s{display:block;font-size:11.5px;color:var(--dim);line-height:1.45}"
        "ul.gates{list-style:none;margin:10px 0;padding:0;max-width:76ch}"
        "ul.gates li{padding:9px 0 9px 26px;text-indent:-26px;font-size:13px;"
        "line-height:1.6;color:var(--dim);border-bottom:1px solid var(--line)}"
        "ul.gates li.y{color:var(--dim)} ul.gates li.y::first-letter{color:var(--long)}"
        "ul.gates li.n::first-letter{color:var(--short)}"
        "@media(max-width:720px){.conf{grid-template-columns:1fr}}"
        "</style>")
    return {"body": body, "css": css}


def render() -> str:
    p = parts()
    return shell("/short", "Short", p["body"], head_extra=p["css"],
                 meta="the one validated edge")
