"""LENS /hedge-track — the next rung, the band, and the day you're having.

/hedge-goal answers "is the whole plan still reachable?" — twelve rungs, scenario
ladders, coverage. That is a monthly question, and it reads like one. This page
answers the daily one: what is the NEXT rung, am I inside the band that gets me
there, and did today count.

So the ladder is deliberately demoted here. One rung is loud; the rest are a
strip at the bottom you can ignore. Focusing on rung 12 from rung 1 is how the
goal stops being motivating.

Nothing here is new maths. `plan.ladder()` owns the rungs, `cone.cone()` owns the
Monte-Carlo band, `track.py` owns the scoring. This module only draws.

The fan is inline SVG, not a chart library: eleven cone samples and one realised
line don't need 300 KB of canvas, and /analytics already pays that cost from a
CDN for the interactive version. Server-rendered means it also survives with no
network, which is the point of the box it runs on.
"""

from datetime import date, datetime

from .theme import shell
from .track import MAX_POINTS, WEIGHTS, track

# Plot geometry — one place, because the axis maths references it six times.
VB_W, VB_H = 720, 240
PAD_L, PAD_R, PAD_T, PAD_B = 52, 14, 16, 30
PLOT_W = VB_W - PAD_L - PAD_R
PLOT_H = VB_H - PAD_T - PAD_B

BANDS = ("p10", "p25", "p50", "p75", "p90")


def _eur(v, dp: int = 0) -> str:
    if v is None:
        return "—"
    return f"{'−' if v < 0 else ''}€{abs(v):,.{dp}f}"


def _btc(v) -> str:
    if v is None:
        return "—"
    return (f"{v:.4f}".rstrip("0").rstrip(".") or "0") + " ₿"


def _date_label(iso: str, year: bool = False) -> str:
    """`year=True` for the ladder, which spans three calendar years — "9 Dec"
    alone is genuinely ambiguous there. The fan is inside one horizon, so it
    doesn't need it."""
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return iso or "—"
    if year and d.year != date.today().year:
        return d.strftime("%-d %b %y")
    return d.strftime("%-d %b")


# ─── the fan ─────────────────────────────────────────────────────────────────

def _fan_svg(cone: dict, actual: list[dict], rung: dict) -> str:
    """Monte-Carlo percentile fan with the realised line drawn through it.

    Returns an empty-state panel when the cone has nothing to say — a blank axis
    is worse than a sentence explaining why it's blank.
    """
    points = cone.get("points") or []
    if not points or len(points) < 2:
        return ('<div class="tk-empty">No projection yet — the cone needs closed '
                'trades and a balance snapshot before it can draw a band.</div>')

    x0, x1 = points[0]["t"], points[-1]["t"]
    xspan = max(x1 - x0, 1)

    vals = [p[k] for p in points for k in BANDS if k in p]
    vals += [a["cum"] for a in actual] or []
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    def px(t):
        return PAD_L + (t - x0) / xspan * PLOT_W

    def py(v):
        return PAD_T + (hi - v) / (hi - lo) * PLOT_H

    def ribbon(k_lo: str, k_hi: str) -> str:
        up = " ".join(f"{px(p['t']):.1f},{py(p[k_hi]):.1f}" for p in points)
        dn = " ".join(f"{px(p['t']):.1f},{py(p[k_lo]):.1f}" for p in reversed(points))
        return f"{up} {dn}"

    def line(k: str) -> str:
        return " ".join(f"{px(p['t']):.1f},{py(p[k]):.1f}" for p in points)

    today_ts = int(datetime.now().timestamp())
    tx = min(max(px(today_ts), PAD_L), VB_W - PAD_R)

    # y gridlines: zero always, plus the two band edges at the horizon
    zero_y = py(0.0) if lo <= 0 <= hi else None
    grid = ""
    if zero_y is not None:
        grid = (f'<line x1="{PAD_L}" y1="{zero_y:.1f}" x2="{VB_W - PAD_R}" '
                f'y2="{zero_y:.1f}" class="tk-zero"/>'
                f'<text x="{PAD_L - 7}" y="{zero_y + 3.5:.1f}" class="tk-ax tk-ax-r">0</text>')

    act = ""
    if len(actual) > 1:
        pts = " ".join(f"{px(a['t']):.1f},{py(a['cum']):.1f}" for a in actual)
        last = actual[-1]
        act = (f'<polyline points="{pts}" class="tk-act"/>'
               f'<circle cx="{px(last["t"]):.1f}" cy="{py(last["cum"]):.1f}" r="3.6" '
               f'class="tk-act-dot"/>')

    hi_lbl = _eur(hi)
    lo_lbl = _eur(lo)
    end = points[-1]

    return f"""<svg viewBox="0 0 {VB_W} {VB_H}" class="tk-fan" role="img"
 aria-label="Projection fan: cumulative realised profit and loss from
 {cone.get('anchor')} to the {rung.get('label') or 'next'} rung on
 {rung.get('date')}. The realised line currently sits at
 {_eur(cone.get('now', {}).get('cum'))} against a median projection of
 {_eur(end.get('p50'))}.">
  <polygon points="{ribbon('p10', 'p90')}" class="tk-b10"/>
  <polygon points="{ribbon('p25', 'p75')}" class="tk-b25"/>
  {grid}
  <polyline points="{line('p50')}" class="tk-p50"/>
  {act}
  <line x1="{tx:.1f}" y1="{PAD_T}" x2="{tx:.1f}" y2="{PAD_T + PLOT_H}" class="tk-now"/>
  <text x="{tx:.1f}" y="{PAD_T + PLOT_H + 13}" class="tk-ax tk-ax-c">today</text>
  <text x="{VB_W - PAD_R}" y="{PAD_T + PLOT_H + 13}" class="tk-ax tk-ax-e">{_date_label(rung.get('date') or '')}</text>
  <text x="{PAD_L}" y="{PAD_T + PLOT_H + 13}" class="tk-ax">{_date_label(cone.get('anchor') or '')}</text>
  <text x="{PAD_L - 7}" y="{PAD_T + 4}" class="tk-ax tk-ax-r">{hi_lbl}</text>
  <text x="{PAD_L - 7}" y="{PAD_T + PLOT_H:.0f}" class="tk-ax tk-ax-r">{lo_lbl}</text>
</svg>"""


# ─── the streak strip ────────────────────────────────────────────────────────

def _strip(days: list[dict]) -> str:
    cells = []
    for d in days:
        pts, mx = d["points"], d["max_points"]
        if d["breaches"]:
            cls, why = "brk", f"{d['breaches']} off-plan"
        elif d["kept"]:
            cls, why = "kept", "kept"
        elif d["trades"] or d["decisions"]:
            cls, why = "part", "partial"
        else:
            cls, why = "idle", "nothing logged"
        # fill height carries the score; color carries the verdict
        h = 18 + round(pts / mx * 26)
        bits = [f"{d['date']}", why, f"{pts:g}/{mx} pts"]
        if d["trades"]:
            bits.append(f"{d['trades']} trade{'s' if d['trades'] != 1 else ''}")
        if d["decisions"]:
            bits.append(f"{d['decisions']} decided")
        if d["band_pct"]:
            bits.append(f"P{d['band_pct']}+ band")
        cells.append(f'<i class="tk-c {cls}" style="--h:{h}px" '
                     f'title="{" · ".join(bits)}"></i>')
    return '<div class="tk-strip">' + "".join(cells) + "</div>"


# ─── page ────────────────────────────────────────────────────────────────────

def _score_rows(days: list[dict]) -> str:
    n = len(days) or 1
    meta = [
        ("discipline", "No trade flagged off-plan.",
         "A breach zeroes the whole day — however well it went."),
        ("plan", "A trade taken that WAS the plan.",
         "Needs the trade marked followed-plan in the journal."),
        ("band", "Inside the projection band.",
         "Scaled by percentile: above P75 pays full, under P10 pays nothing."),
        ("decision", "A signal approved or rejected.",
         "Rejecting counts. Showing up is the point."),
    ]
    rows = []
    for key, what, note in meta:
        hit = sum(1 for d in days if d["parts"][key] > 0)
        got = sum(d["parts"][key] for d in days)
        cap = WEIGHTS[key] * n
        rows.append(
            f'<tr><td class="tk-w">{WEIGHTS[key]}</td>'
            f'<td class="tk-k">{key}<span class="tk-note">{note}</span></td>'
            f'<td class="tk-what">{what}</td>'
            f'<td class="tk-n">{hit}<span class="tk-of">/{n} d</span></td>'
            f'<td class="tk-n tk-tot">{got:g}<span class="tk-of">/{cap:g}</span></td></tr>')
    return "".join(rows)


def _ladder(rung: dict, days: list[dict]) -> str:
    from .plan import ladder as _l
    try:
        ms = _l()["milestones"]
    except Exception:
        return ""
    out = []
    for m in ms:
        if m["done"]:
            cls = "done"
        elif m["label"] == rung.get("label"):
            cls = "now"
        else:
            cls = ""
        out.append(f'<li class="{cls}"><b>{m["label"]}</b>'
                   f'<span class="tk-lb">{_btc(m["btc"])}</span>'
                   f'<span class="tk-ld">{_date_label(m["date"], year=True) if m["date"] else "—"}</span></li>')
    return '<ol class="tk-ladder">' + "".join(out) + "</ol>"


def parts() -> dict:
    T = track()
    R, S, C = T["rung"], T["streak"], T["cone"]
    sc = T["score"]
    status = (T["status"] or "—").upper()
    now = C.get("now") or {}

    pct = R.get("progress_pct")
    bar_pct = 0 if pct is None else max(0.0, min(100.0, pct))
    left = R.get("days_left")

    stale = ('<span class="tk-stale">stack snapshot is '
             f'{R.get("age_days")} d old</span>') if R.get("stale") else ""

    unrev = ""
    if sc["unreviewed"]:
        unrev = (f'<p class="tk-warn">{sc["unreviewed"]} trade'
                 f'{"s" if sc["unreviewed"] != 1 else ""} in this window '
                 'are unmarked, so discipline is scoring silence rather than '
                 'conduct. Mark them followed-plan or off-plan in the journal '
                 'and this number becomes real.</p>')

    body = f"""
<main class="tk">

  <section class="tk-hero" aria-label="Next milestone">
    <div class="tk-hero-top">
      <div>
        <span class="tk-eyebrow">next rung</span>
        <h1 class="tk-rung">{R.get('label') or 'No rung derivable'}</h1>
      </div>
      <span class="tk-status s-{status}">{status}</span>
    </div>

    <div class="tk-nums">
      <div><span class="tk-lab">stack</span><b>{_btc(R.get('stack_btc'))}</b></div>
      <div><span class="tk-lab">rung</span><b>{_btc(R.get('btc'))}</b></div>
      <div><span class="tk-lab">by</span><b>{_date_label(R.get('date') or '')}</b></div>
      <div><span class="tk-lab">days left</span><b>{left if left is not None else '—'}</b></div>
    </div>

    <div class="tk-bar" role="progressbar" aria-valuenow="{bar_pct:.0f}"
         aria-valuemin="0" aria-valuemax="100"
         aria-label="Progress to {R.get('label') or 'next rung'}">
      <span style="width:{bar_pct:.1f}%"></span>
    </div>
    <p class="tk-sub">{bar_pct:.0f}% of the way from {_btc(R.get('from_btc'))} to
       {_btc(R.get('btc'))} · {R.get('overall_pct') or 0}% of the {_btc(R.get('goal_btc'))} goal {stale}</p>
  </section>

  <section class="tk-panel" aria-label="Projection band">
    <header class="tk-h">
      <h2>Where you should be</h2>
      <span class="tk-badge">{C.get('badge') or 'no sample'}</span>
    </header>
    <div class="tk-fanwrap">{_fan_svg(C, T["actual"], R)}</div>
    <p class="tk-sub">Realised <b>{_eur(now.get('cum'), 2)}</b> against a P25–P75
       band of {_eur(now.get('p25'), 2)} – {_eur(now.get('p75'), 2)} today.
       The shaded fan is {C.get('paths') or 0} simulated paths drawn from your own
       closed trades, running to the rung date — not a straight line, because your
       equity curve isn't one.</p>
  </section>

  <section class="tk-panel" aria-label="Daily score">
    <header class="tk-h">
      <h2>The last {T['window_days']} days</h2>
      <span class="tk-streak"><b>{S['current']}</b> day streak
        <span class="tk-of">best {S['best']}</span></span>
    </header>
    {_strip(T['days'])}
    <div class="tk-legend">
      <span><i class="tk-c kept" style="--h:10px"></i>kept</span>
      <span><i class="tk-c part" style="--h:10px"></i>partial</span>
      <span><i class="tk-c brk" style="--h:10px"></i>breach</span>
      <span><i class="tk-c idle" style="--h:10px"></i>nothing logged</span>
      <span class="tk-of">bar height = points that day</span>
    </div>
    <table class="tk-score">
      <thead><tr><th>pts</th><th>component</th><th>earned when</th>
        <th>days</th><th>total</th></tr></thead>
      <tbody>{_score_rows(T['days'])}</tbody>
      <tfoot><tr><td class="tk-w">{MAX_POINTS}</td><td class="tk-k">score</td>
        <td class="tk-what">A streak day needs discipline kept AND something logged.</td>
        <td class="tk-n">{sc['traded_days']}<span class="tk-of">/{len(T['days'])} traded</span></td>
        <td class="tk-n tk-tot">{sc['earned']:g}<span class="tk-of">/{sc['possible']:g}</span></td></tr></tfoot>
    </table>
    {unrev}
  </section>

  <section class="tk-panel tk-rest" aria-label="Remaining rungs">
    <header class="tk-h"><h2>After that</h2>
      <span class="tk-of">the rest of the ladder, deliberately quiet</span></header>
    {_ladder(R, T['days'])}
  </section>

</main>"""

    css = """<style>
.tk{max-width:1000px;margin:0 auto;padding:0 14px 10px}
.tk-panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;
  padding:15px 16px 16px;margin-top:14px}
.tk-h{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.tk-h h2{font-family:var(--hud);font-size:14px;font-weight:600;letter-spacing:.02em;
  color:var(--ink);margin:0}
.tk-h .tk-of,.tk-badge{margin-left:auto}

/* hero — the one loud thing on the page */
.tk-hero{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:18px 18px 20px;margin-top:14px}
.tk-hero-top{display:flex;align-items:flex-start;gap:14px;justify-content:space-between}
.tk-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--faint);display:block;margin-bottom:5px}
.tk-rung{font-family:var(--hud);font-size:30px;font-weight:700;letter-spacing:.01em;
  color:var(--ink);margin:0;line-height:1.05;text-wrap:balance}
.tk-status{font-family:var(--mono);font-size:11px;font-weight:800;letter-spacing:.1em;
  padding:4px 9px;border-radius:999px;border:1px solid var(--line);color:var(--dim);
  white-space:nowrap;flex:none}
.tk-status.s-AHEAD,.tk-status.s-ON{color:var(--long);border-color:var(--long)}
.tk-status.s-BEHIND{color:var(--amber);border-color:var(--amber)}
.tk-status.s-OFF-PLAN{color:var(--short);border-color:var(--short)}

.tk-nums{display:flex;flex-wrap:wrap;gap:10px 26px;margin:16px 0 13px}
.tk-nums>div{display:flex;flex-direction:column;gap:2px}
.tk-lab{font-family:var(--mono);font-size:9.5px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--faint)}
.tk-nums b{font-family:var(--mono);font-size:16px;font-weight:700;color:var(--ink)}

.tk-bar{height:8px;border-radius:999px;background:var(--bg);border:1px solid var(--line);
  overflow:hidden}
.tk-bar>span{display:block;height:100%;background:var(--accent);border-radius:999px;
  transition:width .24s cubic-bezier(.22,1,.36,1)}
.tk-sub{font-size:12px;line-height:1.55;color:var(--dim);margin:9px 0 0;max-width:72ch}
.tk-sub b{color:var(--ink);font-family:var(--mono)}
.tk-stale{color:var(--amber);margin-left:6px}
.tk-warn{font-size:12px;line-height:1.55;color:var(--amber);margin:12px 0 0;max-width:72ch}
.tk-badge{font-family:var(--mono);font-size:10px;color:var(--faint)}

/* fan */
.tk-fan{width:100%;height:auto;display:block;overflow:visible}
.tk-b10{fill:var(--accent);opacity:.09}
.tk-b25{fill:var(--accent);opacity:.16}
.tk-p50{fill:none;stroke:var(--dim);stroke-width:1.3;stroke-dasharray:4 3}
.tk-act{fill:none;stroke:var(--long);stroke-width:2.1;stroke-linejoin:round;
  stroke-linecap:round}
.tk-act-dot{fill:var(--long)}
.tk-now{stroke:var(--faint);stroke-width:1;stroke-dasharray:2 3}
.tk-zero{stroke:var(--line);stroke-width:1}
.tk-ax{font-family:var(--mono);font-size:9px;fill:var(--faint)}
.tk-ax-r{text-anchor:end}.tk-ax-c{text-anchor:middle}.tk-ax-e{text-anchor:end}
.tk-empty{font-size:12.5px;color:var(--dim);padding:26px 4px;text-align:center;
  border:1px dashed var(--line);border-radius:10px}

/* streak strip */
.tk-strip{display:flex;align-items:flex-end;gap:3px;height:46px;margin-bottom:11px}
.tk-c{flex:1 1 0;min-width:4px;height:var(--h);border-radius:2px;display:block;
  background:var(--line);transition:transform .15s ease-out}
.tk-c.kept{background:var(--long)}
.tk-c.part{background:var(--accent);opacity:.55}
.tk-c.brk{background:var(--short)}
.tk-c.idle{background:var(--line)}
.tk-strip .tk-c:hover{transform:scaleY(1.09)}
.tk-legend{display:flex;flex-wrap:wrap;gap:5px 15px;align-items:center;
  font-family:var(--mono);font-size:10px;color:var(--dim);margin-bottom:14px}
.tk-legend span{display:flex;align-items:center;gap:5px}
.tk-legend .tk-c{flex:none;width:9px}
.tk-streak{font-family:var(--mono);font-size:11px;color:var(--dim)}
.tk-streak b{font-size:17px;color:var(--ink);font-weight:800}
.tk-of{color:var(--faint);font-family:var(--mono);font-size:10px;margin-left:5px}

/* score table */
.tk-score{width:100%;border-collapse:collapse;font-size:12px}
.tk-score th{font-family:var(--mono);font-size:9px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);text-align:left;font-weight:400;
  padding:0 8px 7px 0;border-bottom:1px solid var(--line)}
.tk-score td{padding:9px 8px 9px 0;border-bottom:1px solid var(--line);
  vertical-align:top}
.tk-score tfoot td{border-bottom:none;padding-top:11px}
.tk-w{font-family:var(--mono);font-size:13px;font-weight:800;color:var(--accent);width:26px}
.tk-k{font-family:var(--hud);font-weight:600;color:var(--ink);white-space:nowrap}
.tk-note{display:block;font-family:var(--hud);font-weight:400;font-size:10.5px;
  color:var(--faint);white-space:normal;max-width:30ch;margin-top:2px}
.tk-what{color:var(--dim);line-height:1.5}
.tk-n{font-family:var(--mono);text-align:right;color:var(--dim);white-space:nowrap}
.tk-tot{color:var(--ink);font-weight:700}
.tk-score th:nth-child(4),.tk-score th:nth-child(5){text-align:right}

/* the rest of the ladder — quiet on purpose */
.tk-rest{opacity:.86}
.tk-ladder{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:1px}
.tk-ladder li{display:flex;align-items:baseline;gap:10px;padding:7px 9px;
  border-radius:7px;font-size:12px;color:var(--dim)}
.tk-ladder li b{font-family:var(--hud);font-weight:600;color:var(--dim);flex:1 1 auto}
.tk-ladder li.done{color:var(--faint)}
.tk-ladder li.done b{color:var(--faint);text-decoration:line-through;
  text-decoration-color:var(--line)}
.tk-ladder li.now{background:var(--bg);border:1px solid var(--accent)}
.tk-ladder li.now b{color:var(--ink)}
.tk-lb,.tk-ld{font-family:var(--mono);font-size:11px}
.tk-ld{color:var(--faint);width:72px;text-align:right;flex:none;white-space:nowrap}

@media(max-width:720px){
  .tk-rung{font-size:24px}
  .tk-nums{gap:10px 20px}
  .tk-nums b{font-size:14px}
  .tk-strip{gap:2px}
  /* the fan stays legible by scrolling in its own track rather than being
     squashed to a 120px sliver — the axis labels are unreadable below ~180px */
  .tk-fanwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .tk-fan{min-width:560px}
  /* keep "earned when" (the useful half) and drop the parenthetical note,
     rather than keeping both and letting each wrap to five lines */
  .tk-note{display:none}
  .tk-k{white-space:normal}
}
@media(prefers-reduced-motion:reduce){
  .tk-bar>span,.tk-c{transition:none}
  .tk-strip .tk-c:hover{transform:none}
}
</style>"""
    return {"body": body, "css": css}


def render() -> str:
    p = parts()
    return shell("/hedge-track", "Track", p["body"], head_extra=p["css"],
                 meta="am I on pace?")
