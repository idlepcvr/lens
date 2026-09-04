"""LENS — /regime page (server-rendered).

Market regime (BULL/SIDEWAYS/BEAR), pure BTC classification. Was labelled a
PROP analytic — a "hero strategy win-rate per regime" layer sat on top,
answering whether *now* was a regime where the prop hero strategy actually
won. That layer went with the 2026-09-05 hedge/prop split (see app/regime.py).
"""

from .theme import shell

_HEAD = r"""<style>
:root{ --bull:var(--long); --side:var(--amber); --bear:var(--short); }
.rg h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.rg .sub{color:var(--dim);font-size:13px;margin-bottom:22px}
.rg .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:20px}
.rg .panel h2{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-bottom:14px}
.rg .now{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
.rg .now .badge{font-family:var(--mono);font-size:34px;font-weight:800;letter-spacing:.04em;padding:6px 20px;border-radius:12px}
.rg .now .meta{color:var(--dim);font-size:13px;font-family:var(--mono)}
.rg .bull{color:var(--bull)} .rg .side{color:var(--side)} .rg .bear{color:var(--bear)}
.rg .bg-bull{background:rgba(31,217,137,.13);color:var(--bull);border:1px solid var(--bull)}
.rg .bg-side{background:rgba(246,173,60,.13);color:var(--side);border:1px solid var(--side)}
.rg .bg-bear{background:rgba(255,84,104,.13);color:var(--bear);border:1px solid var(--bear)}
.rg .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media(max-width:680px){.rg .grid3{grid-template-columns:1fr}}
.rg .card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:16px}
.rg .card.cur{box-shadow:0 0 0 2px var(--accent) inset}
.rg .card .lbl{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:8px}
.rg .card .wr{font-family:var(--mono);font-size:30px;font-weight:700;line-height:1}
.rg .card .n{font-size:12px;color:var(--dim);margin-top:6px}
.rg .strip{display:flex;gap:2px;flex-wrap:wrap}
.rg .strip span{width:11px;height:22px;border-radius:2px;display:inline-block}
.rg .strip .b-bull{background:var(--bull)} .rg .strip .b-side{background:var(--side)} .rg .strip .b-bear{background:var(--bear)}
.rg table{width:100%;border-collapse:collapse;font-size:13px}
.rg th,.rg td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
.rg th{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:500}
.rg td{font-family:var(--mono)}
.rg .prose{color:var(--dim);font-size:13.5px;line-height:1.65}
.rg .prose strong{color:var(--ink)}
.rg .prose code{font-family:var(--mono);color:var(--accent);background:var(--panel2);padding:1px 5px;border-radius:4px}
.rg .verdict{border-left:3px solid var(--accent);padding:10px 16px;background:var(--panel2);border-radius:0 8px 8px 0;font-size:14px;color:var(--ink);margin-top:8px}
.rg .cur-tag{font-size:10px;font-weight:700;letter-spacing:.1em;color:var(--accent);margin-left:6px}
</style>"""

_CLS = {"BULL": "bull", "SIDEWAYS": "side", "BEAR": "bear"}
_BG = {"BULL": "bg-bull", "SIDEWAYS": "bg-side", "BEAR": "bg-bear"}


def render(p: dict) -> str:
    cur = p.get("current_regime", "UNKNOWN")
    cur_cls = _CLS.get(cur, "")
    cur_bg = _BG.get(cur, "")
    stats = p.get("regime_stats", {})

    # 60-day strip
    chips = "".join(
        f'<span class="b-{_CLS.get(h["regime"], "side")}" title="{h["date"]} {h["regime"]} {h["ret14_pct"]}%"></span>'
        for h in p.get("history", [])
    )

    # Market stats table
    rows = ""
    for r in ("BULL", "SIDEWAYS", "BEAR"):
        s = stats.get(r, {})
        rows += (
            f'<tr><td class="{_CLS[r]}">{r}</td><td>{s.get("count", 0)}</td>'
            f'<td>{s.get("avg_ret14_pct", 0)}%</td><td>{s.get("avg_vol14_pct", 0)}%</td></tr>'
        )

    # Regime persistence / transition panel (the Markov slice)
    tr = p.get("transitions", {})
    persist_panel = ""
    if tr and tr.get("matrix"):
        mtx, persist, avg_run = tr["matrix"], tr["persistence"], tr["avg_run_days"]
        cur_run = tr.get("current_run_days", 0)
        cur_avg = avg_run.get(cur)

        def _pct(x):
            return f"{x*100:.0f}%" if x is not None else "—"

        run_note = ""
        if cur_avg and cur_run:
            ratio = cur_run / cur_avg
            if ratio >= 1.8:
                run_note = (f"You've been in <strong class='{cur_cls}'>{cur}</strong> for <strong>{cur_run} days</strong> — "
                            f"about <strong>{ratio:.1f}×</strong> the typical {cur_avg}-day {cur} stretch. This regime is "
                            f"running long; a change is statistically overdue.")
            else:
                run_note = (f"You've been in <strong class='{cur_cls}'>{cur}</strong> for <strong>{cur_run} days</strong>, "
                            f"vs a typical {cur_avg}-day stretch — within the normal range.")

        nd = mtx.get(cur, {})
        nd_txt = " · ".join(f'<b class="{_CLS[r]}">{r} {_pct(nd.get(r))}</b>' for r in ("BULL", "SIDEWAYS", "BEAR"))
        mrows = ""
        for frm in ("BULL", "SIDEWAYS", "BEAR"):
            row = mtx.get(frm, {})
            mark = ' <span class="cur-tag">◀ NOW</span>' if frm == cur else ""
            cells = "".join(f'<td>{_pct(row.get(to))}</td>' for to in ("BULL", "SIDEWAYS", "BEAR"))
            mrows += f'<tr><td class="{_CLS[frm]}">{frm}{mark}</td>{cells}<td>{avg_run.get(frm) or "—"}d</td></tr>'

        persist_panel = f"""
  <div class="panel">
    <h2>Regime persistence — how sticky is now?</h2>
    <div class="verdict">{run_note}</div>
    <div class="prose" style="margin:14px 0 4px">Tomorrow from <strong class="{cur_cls}">{cur}</strong>: {nd_txt}</div>
    <table style="margin-top:12px">
      <tr><th>From ↓ / To →</th><th>BULL</th><th>SIDEWAYS</th><th>BEAR</th><th>Avg run</th></tr>
      {mrows}
    </table>
    <div class="prose" style="margin-top:12px">Each row: given <strong>today's</strong> regime, the chance of each regime <strong>tomorrow</strong> (rows sum to 100%). The diagonal is <strong>persistence</strong> — how often a regime repeats day-to-day (BTC regimes are sticky, ~85–93%). "Avg run" = how many days that regime usually lasts before it flips.</div>
  </div>"""

    body = f"""
<div class="rg">
  <h1>Market Regime — BTCUSD daily</h1>
  <div class="sub">K-Means(k=3) on 14-day return + 14-day volatility.</div>

  <div class="panel">
    <h2>Current regime</h2>
    <div class="now">
      <div class="badge {cur_bg}">{cur}</div>
      <div class="meta">14d return <b class="{cur_cls}">{p.get('current_ret14_pct', 0)}%</b> &nbsp;·&nbsp; 14d vol {p.get('current_vol14_pct', 0)}%/day &nbsp;·&nbsp; {p.get('current_date', '')}</div>
    </div>
  </div>
{persist_panel}
  <div class="panel">
    <h2>Last 60 days</h2>
    <div class="strip">{chips}</div>
    <div class="prose" style="margin-top:12px"><span class="bull">■</span> BULL &nbsp; <span class="side">■</span> SIDEWAYS &nbsp; <span class="bear">■</span> BEAR</div>
  </div>

  <div class="panel">
    <h2>Per-regime market stats (full window)</h2>
    <table>
      <tr><th>Regime</th><th>Days</th><th>Avg 14d ret</th><th>Avg 14d vol</th></tr>
      {rows}
    </table>
  </div>
</div>"""
    return shell("/regime", "Regime", body, head_extra=_HEAD, meta="market regime")
