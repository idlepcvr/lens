"""LENS / — the front door.

A cockpit powers on: the aperture mark, the wordmark, a status line, and four
live gauges read straight off the ledger (one SQL each — no network, page stays
instant). Below: the two machines, then the feedback loop that explains the
whole system to a visitor in one row. Voice per BRAND.md: report state, let the
trader decide. No exclamation marks, verdicts uppercase.
"""

import sqlite3
from datetime import datetime, timedelta

from . import discipline
from .database import DB_PATH
from .theme import shell

ERA_START = "2026-07-01"   # analytics era (Q3) — keep in step with /analytics


def _gauges() -> dict:
    con = sqlite3.connect(DB_PATH)
    fills, last = con.execute(
        "SELECT COUNT(*), MAX(date(COALESCE(closed_at, opened_at))) "
        "FROM trades WHERE pnl IS NOT NULL").fetchone()
    era_n, era_pnl, era_w = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(pnl),0), COALESCE(SUM(pnl>0),0) "
        f"FROM trades WHERE pnl IS NOT NULL AND opened_at >= '{ERA_START}'").fetchone()
    return {
        "fills": fills, "last": last or "—",
        "era_n": era_n, "era_pnl": era_pnl,
        "era_wr": (100 * era_w / era_n) if era_n else None,
        "filters": len(discipline.settings()),
    }


_CSS = r"""<style>
.hero{display:flex;align-items:center;gap:26px;margin:34px 0 6px}
.hero .mark{flex:0 0 auto;width:118px;height:118px;position:relative}
.hero .mark svg{width:100%;height:100%;display:block}
.hero .mark .tick{transform-origin:16px 16px;animation:scopespin 90s linear infinite}
@media(prefers-reduced-motion:reduce){.hero .mark .tick{animation:none}}
@keyframes scopespin{to{transform:rotate(360deg)}}
.hero .word{min-width:0}
.hero .lens{font-family:'Chakra Petch',var(--mono);font-weight:700;font-size:56px;
  letter-spacing:.32em;color:var(--ink);line-height:1}
.hero .lens .s{color:var(--accent)}
.hero .thesis{font-size:14px;color:var(--dim);line-height:1.55;margin-top:10px;max-width:52ch}
.hero .thesis b{color:var(--ink)}
.statline{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);margin-top:14px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.statline .on{color:var(--long)}
.statline .on::before{content:'●';margin-right:6px;animation:pulse 2.4s ease-in-out infinite}
@media(prefers-reduced-motion:reduce){.statline .on::before{animation:none}}
@keyframes pulse{50%{opacity:.35}}

.gauges{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:26px}
@media(max-width:680px){.gauges{grid-template-columns:1fr 1fr}}
.gauge{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.gauge .k{font-family:var(--mono);font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
.gauge .v{font-family:var(--mono);font-size:19px;font-weight:700;color:var(--ink);margin-top:5px}
.gauge .v.g{color:var(--long)} .gauge .v.r{color:var(--short)}
.gauge .v small{font-size:11px;font-weight:500;color:var(--dim)}

.choose{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:26px}
@media(max-width:680px){.choose{grid-template-columns:1fr}}
.door{display:block;text-decoration:none;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:24px;transition:.18s}
.door:active{transform:scale(.985)}
.door h2{font-family:'Chakra Petch',var(--mono);font-size:21px;font-weight:700;letter-spacing:.1em;
  margin:4px 0 4px;color:var(--ink)}
.door .sub{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.18em;
  text-transform:uppercase;color:var(--dim)}
.door p{font-size:12.5px;line-height:1.55;color:var(--dim);margin:10px 0 0}
.door .go{font-family:var(--mono);font-size:11px;font-weight:700;margin-top:16px;color:var(--accent)}
.door.prop{border-top:3px solid var(--accent)}
.door.hedge{border-top:3px solid var(--amber)}
@media(hover:hover){.door:hover{border-color:var(--line2);transform:translateY(-2px)}}

.loop{margin-top:30px;background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px;overflow-x:auto}
.loop .t{font-family:var(--mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--faint);margin-bottom:12px}
.loop .row{display:flex;align-items:stretch;gap:0;min-width:560px}
.loop .st{flex:1;text-align:center;position:relative;padding:0 6px}
.loop .st .n{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink);
  letter-spacing:.08em}
.loop .st .d{font-size:10.5px;color:var(--dim);line-height:1.45;margin-top:5px}
.loop .st+.st::before{content:'→';position:absolute;left:-8px;top:0;
  font-family:var(--mono);color:var(--accent);font-size:13px}
.loop .back{font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:12px;
  text-align:center;letter-spacing:.06em}
.loop .back b{color:var(--accent);font-weight:700}

/* power-on: gauges and doors rise in sequence */
.rise{opacity:0;transform:translateY(7px);animation:rise .5s ease-out forwards}
@media(prefers-reduced-motion:reduce){.rise{opacity:1;transform:none;animation:none}}
@keyframes rise{to{opacity:1;transform:none}}
</style>"""

_MARK = """
<svg viewBox="0 0 32 32" aria-hidden="true">
  <circle cx="16" cy="16" r="9.5" fill="none" stroke="#5b9dff" stroke-width="1.6"/>
  <circle cx="16" cy="16" r="13.4" fill="none" stroke="#192232" stroke-width="1"/>
  <circle cx="16" cy="16" r="3" fill="#1fd989"/>
  <g class="tick">
    <path d="M16 1.4v4M16 26.6v4M1.4 16h4M26.6 16h4" stroke="#5b9dff"
          stroke-width="1.2" stroke-linecap="round"/>
  </g>
</svg>"""


def render() -> str:
    g = _gauges()
    wr = f"{g['era_wr']:.0f}<small>%</small>" if g["era_wr"] is not None else "—"
    pnl_cls = "g" if g["era_pnl"] > 0 else "r" if g["era_pnl"] < 0 else ""

    body = f"""
<div class="hero">
  <div class="mark">{_MARK}</div>
  <div class="word">
    <div class="lens">LEN<span class="s">S</span></div>
    <p class="thesis">A BTC-perp <b>instrument cluster</b>. It reads market state,
    filters every signal through ledger-derived vetoes, and reports the verdict flat
    — <b>the trader decides</b>.</p>
    <div class="statline">
      <span class="on">system online</span>
      <span>{g['filters']} vetoes armed</span>
      <span>last fill {g['last']}</span>
    </div>
  </div>
</div>

<div class="gauges">
  <div class="gauge rise" style="animation-delay:.05s"><div class="k">ledger</div>
    <div class="v">{g['fills']:,}<small> fills</small></div></div>
  <div class="gauge rise" style="animation-delay:.15s"><div class="k">this era · q3</div>
    <div class="v {pnl_cls}">€{g['era_pnl']:+,.0f}</div></div>
  <div class="gauge rise" style="animation-delay:.25s"><div class="k">q3 win rate</div>
    <div class="v">{wr}</div></div>
  <div class="gauge rise" style="animation-delay:.35s"><div class="k">rules audit</div>
    <div class="v"><a href="/robustness" style="color:var(--amber);text-decoration:none">SUGGESTIVE</a></div></div>
</div>

<div class="choose">
  <a class="door prop rise" style="animation-delay:.45s" href="/prop-dashboard">
    <div class="sub">pass the eval</div>
    <h2>PROP</h2>
    <p>Kraken Prop $10k Advanced. 0.5% risk per trade — survive the 3% floor,
       hit +9%, scale to firm capital. Goal · Ledger · Desk · Queue · Survival.</p>
    <div class="go">ENTER →</div>
  </a>
  <a class="door hedge rise" style="animation-delay:.55s" href="/dashboard">
    <div class="sub">trade your edge</div>
    <h2>HEDGE</h2>
    <p>Own-money discretionary book. Mined setups S1–S5, the vetoes that kill the
       bleed, sizing and journal. Plan · Position · Desk · Signals · Journal.</p>
    <div class="go">ENTER →</div>
  </a>
</div>

<div class="loop rise" style="animation-delay:.65s">
  <div class="t">how it runs</div>
  <div class="row">
    <div class="st"><div class="n">SIGNAL</div><div class="d">setup fires on live Kraken data</div></div>
    <div class="st"><div class="n">FILTERS</div><div class="d">bleed hours, cooldown, venue — auto-veto</div></div>
    <div class="st"><div class="n">VERDICT</div><div class="d">ENTER or BLOCKED, sized to the plan</div></div>
    <div class="st"><div class="n">LEDGER</div><div class="d">every fill and rejection stored</div></div>
    <div class="st"><div class="n">AUDIT</div><div class="d">analytics re-derive the rules from results</div></div>
  </div>
  <div class="back">└─ what the audit learns <b>re-arms the filters</b> — the loop is the system ─┘</div>
</div>
"""
    return shell("/", "Home", body, head_extra=_CSS, meta="pick a machine")
