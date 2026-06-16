"""LENS /style — living style guide. Renders every design token + component
straight from the shared system (app/theme.py LENS_CSS) so it doubles as
documentation AND a visual regression check: if lens.css changes, this page
shows it. Built on shell() like every other page.
"""

from .theme import shell

# ── token tables (mirror LENS_CSS :root — the single source of truth) ─────────
SURFACES = [
    ("--bg2", "#04050a", "page base / behind app"),
    ("--bg", "#06080c", "app background"),
    ("--panel", "#0b0f16", "card / panel"),
    ("--panel2", "#10151e", "raised panel"),
    ("--panel3", "#161d28", "row divider / inset"),
    ("--line", "#192232", "hairline border"),
    ("--line2", "#28344a", "stronger border"),
]
TEXT = [
    ("--ink", "#e8eef8", "primary text"),
    ("--dim", "#828ea6", "secondary / labels"),
    ("--faint", "#465064", "tertiary / captions"),
    ("--ghost", "#262f3e", "disabled / off"),
]
STATUS = [
    ("--accent", "#5b9dff", "interactive / brand"),
    ("--accent-d", "#10203f", "accent fill bg"),
    ("--long", "#1fd989", "long / positive / GO"),
    ("--long-d", "#0c3a28", "long fill bg"),
    ("--short", "#ff5468", "short / negative / STOP"),
    ("--short-d", "#43141d", "short fill bg"),
    ("--amber", "#f6ad3c", "warn / veto / caution"),
    ("--amber-d", "#3c2c0e", "amber fill bg"),
]


def _swatches(tokens):
    out = []
    for name, hexv, use in tokens:
        out.append(
            f'<div class="sw"><div class="sw-c" style="background:var({name})"></div>'
            f'<div class="sw-m"><span class="n">{name}</span>'
            f'<span class="h">{hexv}</span><span class="u">{use}</span></div></div>'
        )
    return '<div class="sg-grid">' + "".join(out) + "</div>"


_HEAD = r"""<style>
.sg-h{font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;
  color:var(--accent);margin:30px 2px 12px;display:flex;align-items:center;gap:10px}
.sg-h::after{content:"";flex:1;height:1px;background:var(--line)}
.sg-h:first-of-type{margin-top:8px}
.sg-sub{font-family:var(--mono);font-size:10px;color:var(--faint);letter-spacing:.1em;text-transform:uppercase;margin:18px 2px 8px}
.sg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.sw{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel)}
.sw-c{height:54px;border-bottom:1px solid var(--line)}
.sw-m{padding:8px 10px;font-family:var(--mono);font-size:10px;line-height:1.5}
.sw-m .n{color:var(--ink);font-weight:700;display:block}
.sw-m .h{color:var(--dim);display:block}
.sw-m .u{color:var(--faint);display:block;font-size:9px;margin-top:2px}
.sg-type > div{padding:7px 0;border-bottom:1px solid var(--panel3);display:flex;align-items:baseline;gap:14px}
.sg-type .tag{font-family:var(--mono);font-size:9px;color:var(--faint);width:120px;flex-shrink:0;letter-spacing:.08em}
.sg-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:4px 0 14px}
.sg-radii{display:flex;gap:14px;flex-wrap:wrap}
.sg-radii > div{width:66px;height:66px;background:var(--panel2);border:1px solid var(--line2);
  display:flex;align-items:flex-end;justify-content:center;font-family:var(--mono);font-size:9px;color:var(--dim);padding:5px}
.sg-elev{display:flex;gap:16px;flex-wrap:wrap}
.sg-elev > div{width:120px;height:70px;border-radius:12px;background:var(--panel);border:1px solid var(--line2);
  display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:9px;color:var(--dim);text-align:center;padding:6px}
.sg-mininav{display:flex;gap:6px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.sg-input{background:var(--bg);border:1px solid var(--line2);border-radius:7px;color:var(--ink);
  padding:8px 11px;font-family:var(--mono);font-size:13px;font-weight:700;width:120px}
.sg-input:focus{outline:none;border-color:var(--accent)}
.sg-card-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:640px){.sg-card-row{grid-template-columns:1fr}}
.sg-note{font-family:var(--mono);font-size:11px;color:var(--dim);line-height:1.7;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;padding:13px 15px}
.sg-note b{color:var(--ink)} .sg-note .g{color:var(--long)} .sg-note .r{color:var(--short)} .sg-note .a{color:var(--amber)}
</style>"""

_BODY = f"""
<p class="sg-note" style="margin-top:6px">Every token + component below renders live from <b>/assets/lens.css</b>
(source: <b>app/theme.py · LENS_CSS</b>). Change the stylesheet once → the whole app and this page move together.
Build any page with <b>shell(path, label, body)</b>.</p>

<!-- ── BRAND ── -->
<div class="sg-h">Brand · Logo</div>
<div class="sg-row" style="align-items:flex-end;gap:26px">
  <span class="logo" style="font-size:30px">LEN<span class="s">S</span></span>
  <span class="logo" style="font-size:17px">LEN<span class="s">S</span> <span class="pg">Page</span></span>
  <img src="/assets/favicon.svg" width="40" height="40" alt="LENS mark" style="border-radius:9px">
  <img src="/assets/favicon.svg" width="16" height="16" alt="LENS mark 16">
</div>
<div class="sg-sub">Voice</div>
<div class="sg-note">
  <b>Instrument cluster, not a hype deck.</b> LENS reads market state and reports it flat — no exclamation, no "to the moon".<br>
  · Terse + mechanical: <span class="g">ENTER</span> / <span class="r">BLOCKED</span> / STAND DOWN, not "Great setup!!".<br>
  · Numbers first, prose second. Monospace for anything you'd read off a gauge.<br>
  · Honest about edge: a pattern is a <b>coin-flip alone</b> — say so. Never imply certainty.<br>
  · Lowercase labels, UPPERCASE verdicts. The interface whispers; the verdict speaks.
</div>

<!-- ── COLOR ── -->
<div class="sg-h">Colors · Surfaces</div>
{_swatches(SURFACES)}
<div class="sg-h">Colors · Text</div>
{_swatches(TEXT)}
<div class="sg-h">Colors · Accent + Status</div>
{_swatches(STATUS)}

<!-- ── TYPE ── -->
<div class="sg-h">Type · Scale</div>
<div class="sg-type">
  <div><span class="tag">px / 30 · mono 800</span><span class="px">$64,210<span class="c"> BTC</span></span></div>
  <div><span class="tag">verdict / 34 · hud 700</span><span class="verdict g">ENTER</span></div>
  <div><span class="tag">big / 24 · mono 800</span><span class="big">+1.51R</span></div>
  <div><span class="tag">logo / 17 · hud 700</span><span class="logo">LEN<span class="s">S</span></span></div>
  <div><span class="tag">body / 14 · hud 400</span><span>The quick brown fox holds winners to target.</span></div>
  <div><span class="tag">mono / 12 · 500</span><span class="mono">entry 64210 · stop 63806 · target 64820</span></div>
  <div><span class="tag">nav / 11 · mono 500</span><span class="mono dim">DESK · SIGNALS · DASHBOARD</span></div>
  <div><span class="tag">label / 10 · mono 700</span><span class="mono dim" style="letter-spacing:.16em;text-transform:uppercase">how to read this</span></div>
</div>
<div class="sg-h">Type · Weights + Families</div>
<div class="sg-row">
  <span style="font-family:var(--hud);font-weight:400">Chakra 400</span>
  <span style="font-family:var(--hud);font-weight:500">Chakra 500</span>
  <span style="font-family:var(--hud);font-weight:600">Chakra 600</span>
  <span style="font-family:var(--hud);font-weight:700">Chakra 700</span>
</div>
<div class="sg-row">
  <span class="mono" style="font-weight:400">JetBrains 400</span>
  <span class="mono" style="font-weight:500">JetBrains 500</span>
  <span class="mono" style="font-weight:700">JetBrains 700</span>
  <span class="mono" style="font-weight:800">JetBrains 800</span>
</div>
<div class="sg-sub">Semantic utilities</div>
<div class="sg-row">
  <span class="g">.g long</span><span class="r">.r short</span><span class="a">.a amber</span>
  <span class="dim">.dim</span><span class="muted">.muted</span><span class="mono">.mono</span>
</div>

<!-- ── SPACING ── -->
<div class="sg-h">Spacing · Radii</div>
<div class="sg-radii">
  <div style="border-radius:7px">7</div>
  <div style="border-radius:9px">9</div>
  <div style="border-radius:10px">10</div>
  <div style="border-radius:12px">12</div>
  <div style="border-radius:13px">13</div>
  <div style="border-radius:16px">16</div>
  <div style="border-radius:999px">999</div>
</div>
<div class="sg-h">Spacing · Elevation</div>
<div class="sg-elev">
  <div style="border:1px solid var(--line)">flat · --line</div>
  <div style="border-color:rgba(31,217,137,.5);box-shadow:var(--glow-g)">glow-g (enter)</div>
  <div style="border-color:rgba(255,84,104,.4);box-shadow:var(--glow-r)">glow-r (stop)</div>
</div>
<div class="sg-sub">Scale — section rhythm uses 8 / 10 / 12 / 14 / 18 / 22 / 24px gaps; app column max 460 → 720 → 1120 at the 680/1080 breakpoints.</div>

<!-- ── COMPONENTS ── -->
<div class="sg-h">Components · Badges</div>
<div class="sg-row">
  <span class="badge pending">pending</span>
  <span class="badge approved">approved</span>
  <span class="badge rejected">rejected</span>
  <span class="badge expired">expired</span>
  <span class="badge">neutral</span>
</div>

<div class="sg-h">Components · Buttons</div>
<div class="sg-row" style="max-width:460px">
  <div class="act-row" style="flex:1">
    <button class="btn skip">SKIP<span class="cap">reject</span></button>
    <button class="btn take">TAKE<span class="cap">conv 3</span></button>
    <button class="btn aplus">TAKE A+<span class="cap">conv 5</span></button>
  </div>
</div>
<div class="sg-row"><button class="btn ghost">ghost / secondary</button></div>

<div class="sg-h">Components · Chips</div>
<div class="sg-row chips">
  <div class="chip">RSI <b>38</b></div>
  <div class="chip good">killzone <b>NY AM</b></div>
  <div class="chip bad">3× bear <b>yes</b></div>
</div>

<div class="sg-h">Components · Inputs</div>
<div class="sg-row">
  <input class="sg-input" value="64210" inputmode="numeric">
  <input class="sg-input" value="focus me" placeholder="focus">
</div>

<div class="sg-h">Components · Topbar + Nav</div>
<div class="sg-mininav">
  <span class="logo" style="font-size:15px;margin-right:8px">LEN<span class="s">S</span></span>
  <a class="chip" style="border-color:var(--accent);background:var(--accent);color:var(--bg);font-weight:700">Desk</a>
  <a class="chip">Signals</a><a class="chip">Dashboard</a><a class="chip">Review</a>
</div>

<div class="sg-h">Components · Cards</div>
<div class="sg-card-row">
  <div class="scard active">
    <div class="sh"><span class="sid">S1 <span class="d-short">SHORT</span></span><span class="swr">90.9% WR</span></div>
    <div class="sname">NY-AM killzone flush</div>
    <div class="cond ok"><span class="tk">✓</span>RSI &lt; 40</div>
    <div class="cond ok"><span class="tk">✓</span>3 bear bars</div>
    <div class="cond no"><span class="tk">·</span>displacement</div>
    <div class="sflag go">● LIVE — context active now</div>
  </div>
  <div class="panel">
    <div class="kv"><span class="k">Win rate</span><span class="v">44%</span></div>
    <div class="kv"><span class="k">Actual R</span><span class="v">1.51</span></div>
    <div class="kv"><span class="k">EV / trade</span><span class="v">+0.21%</span></div>
    <div class="kv"><span class="k">Risk of ruin</span><span class="v">3.2%</span></div>
  </div>
</div>

<div class="sg-h">Components · Table</div>
<div class="sb-wrap">
  <table class="sb">
    <tr><th>tag</th><th>n</th><th>WR</th><th>PnL €</th></tr>
    <tr><td>S1</td><td>22</td><td class="g">90%</td><td class="g">+1552</td></tr>
    <tr><td>VETO</td><td class="r">302</td><td>33%</td><td class="r">−1760</td></tr>
    <tr><td class="m">NONE</td><td>140</td><td>41%</td><td class="m">+96</td></tr>
  </table>
</div>

<div class="foot">LENS design system · one stylesheet, one shell, every page. Edit <b>app/theme.py</b> to move it all.</div>
"""

STYLE_HTML = shell("/style", "Style", _BODY, head_extra=_HEAD, meta="design system")
