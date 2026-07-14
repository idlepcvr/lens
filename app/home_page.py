"""LENS /system — the instrument plate.

This was "/" until 2026-07-14. It assumes the reader already knows what a trade
is, which turned out to be the whole problem: the one page he'd actually hand to
someone — a partner, a parent — was written for people who didn't need it. "/"
is now a plain-English explainer (explain_page.py) and this is the craft
showcase, reached from it. Nothing here changed; it just isn't the front door.

A scrolling instrument plate, not a pitch. Five folds:

  1. hero      — reticle frame, wordmark, the thesis, live statline
  2. ledger    — the real cumulative-P&L curve rendered as a dot-matrix halftone,
                 straight off the trades table, plus the four gauges
  3. loop      — SIGNAL → FILTERS → VERDICT → LEDGER → AUDIT
  4. doors     — PROP / HEDGE
  5. honesty   — watch-only, no keys, a pattern alone is a coin-flip

Voice per BRAND.md: report state, let the trader decide. No exclamation marks,
verdicts uppercase. The page never flatters the ledger — the drawdown is the
argument for the vetoes, so it is drawn at full size.

Type: the hero thesis is the one serif on the site (Libre Caslon Display — an
engraved, scientific-printing cut, not a fashion Didone). Everything else stays
Chakra Petch (chrome) + JetBrains Mono (data), per BRAND.md.

Cost: two SQL reads, no network. The matrix is built in Python and shipped as
static markup — no canvas, no JS.
"""

import sqlite3

from . import discipline
from .database import DB_PATH
from .theme import shell

ERA_START = "2026-07-01"   # analytics era (Q3) — keep in step with /analytics

# Matrix geometry. Two cuts of the same curve: the wide plate for desktop, and a
# coarse one for phones — at 150 cols a 390px screen renders 4px characters and
# the curve turns to dust. CSS picks one at 680px; no JS.
WIDE = (150, 36)
NARROW = (60, 22)


def _gauges() -> dict:
    con = sqlite3.connect(DB_PATH)
    fills, first, last = con.execute(
        "SELECT COUNT(*), MIN(date(COALESCE(closed_at, opened_at))), "
        "MAX(date(COALESCE(closed_at, opened_at))) "
        "FROM trades WHERE pnl IS NOT NULL").fetchone()
    # What the machine DOES — screened and blocked. No money on the front door:
    # P&L is not what this page is for, and it hands the owner's finances to
    # anyone he turns the screen toward. The books keep their own scoreboards.
    seen, blocked = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(status = 'rejected'), 0) FROM signals").fetchone()
    return {
        "fills": fills, "first": first, "last": last or "—",
        "seen": seen, "blocked": blocked,
        "filters": len(discipline.settings()),
    }


def _curve() -> list[float]:
    """Cumulative realised P&L of the HEDGE book, oldest fill first.

    Hedge only, on purpose. The prop rows are evaluation money — paper — and
    summing them into own-money P&L would be adding two different units.

    This is a P&L curve, NOT account equity: `trades.balance_after` is not
    account equity and is deliberately not used. It is also not a track record —
    deposits, withdrawals and a retired venue (the Bybit fills are no longer in
    the ledger) are not in it. The page therefore draws its SHAPE and never
    quotes a figure off it. Do not add axis numbers to this.
    """
    con = sqlite3.connect(DB_PATH)
    total = 0.0
    out = []
    for (pnl,) in con.execute(
            "SELECT pnl FROM trades WHERE pnl IS NOT NULL AND book = 'hedge' "
            "ORDER BY COALESCE(closed_at, opened_at)"):
        total += pnl
        out.append(total)
    return out


# Density ramp, sparse → solid. The eye reads the gradient as depth, so the
# fill under the curve fades out toward the zero line instead of slabbing.
_RAMP = "·:+*#"


def _matrix(cum: list[float], cols: int, rows: int) -> str:
    """Render the P&L curve as a dot-matrix halftone.

    Cells between the curve and the zero line are filled, densest at the curve
    edge. Above water is --long, below is --short: the color IS the sign, never
    decoration (BRAND.md). Everything else is graph-paper field.
    """
    if len(cum) < 2:
        return ""

    lo, hi = min(cum + [0.0]), max(cum + [0.0])
    span = (hi - lo) or 1.0

    def row_of(v: float) -> float:
        """Value → fractional row index (0 = top)."""
        return (hi - v) / span * (rows - 1)

    # Downsample the ledger to one column per x, taking the extreme of each
    # bucket so a sharp drawdown is never averaged away.
    step = len(cum) / cols
    series = []
    for x in range(cols):
        chunk = cum[int(x * step): max(int((x + 1) * step), int(x * step) + 1)]
        series.append(max(chunk, key=abs))

    zero = row_of(0.0)
    lines = []
    for r in range(rows):
        cells = []          # (char, css_class)
        for x, v in enumerate(series):
            cr = row_of(v)
            top, bot = sorted((cr, zero))
            if top - 0.5 <= r <= bot + 0.5:
                # inside the fill — density by distance from the curve edge
                d = abs(r - cr)
                depth = max(bot - top, 1.0)
                i = int((1 - min(d / depth, 1.0)) * (len(_RAMP) - 1))
                sign = "g" if v > 0 else "r"
                cells.append((_RAMP[i], sign + ("c" if d < 0.6 else "")))
            elif x % (cols // 30) == 0 and r % 3 == 0:
                cells.append(("·", "f"))     # graph-paper field
            else:
                cells.append((" ", "f"))
        lines.append(_runs(cells))
    return "\n".join(lines)


def _runs(cells: list[tuple[str, str]]) -> str:
    """Collapse a row of (char, class) into the fewest spans that render it."""
    out, buf, cur = [], [], cells[0][1]
    for ch, cls in cells:
        if cls != cur:
            out.append(f'<i class="{cur}">{"".join(buf)}</i>')
            buf, cur = [], cls
        buf.append(ch)
    out.append(f'<i class="{cur}">{"".join(buf)}</i>')
    return "".join(out)


# Libre Caslon *Text*, not Display: the Display cut ships no italic, and the
# thesis leans on a real italic. Caslon is the engraved, scientific-printing
# serif — the instrument-manual read, not a fashion Didone.
_FONT = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Libre+Caslon+Text:ital@0;1&display=swap" rel="stylesheet">'
)

_CSS = r"""<style>
:root{--serif:'Libre Caslon Text',Georgia,serif}
.app{max-width:1120px;padding-top:clamp(18px,3vw,42px)}
@media(max-width:1079px){.app{max-width:720px}}
@media(max-width:679px){.app{max-width:460px}}

/* ── reticle: the page reads as an instrument plate, so it gets a plate's
      chrome — corner crosshairs and a focal scale, not decorative rules ── */
.plate{position:relative;padding:clamp(30px,6vw,68px) clamp(14px,3.4vw,42px)}
.plate::before,.plate::after{content:"";position:absolute;left:0;right:0;height:1px;
  background:var(--line);opacity:.75}
.plate::before{top:0} .plate::after{bottom:0}
.xh{position:absolute;width:11px;height:11px;pointer-events:none;opacity:.55}
.xh::before,.xh::after{content:"";position:absolute;background:var(--accent)}
.xh::before{left:5px;top:0;width:1px;height:11px}
.xh::after{top:5px;left:0;height:1px;width:11px}
.xh.tl{top:-5.5px;left:-5.5px} .xh.tr{top:-5.5px;right:-5.5px}
.xh.bl{bottom:-5.5px;left:-5.5px} .xh.br{bottom:-5.5px;right:-5.5px}
/* focal scale down the left gutter — real ticks, minor + major */
.scale{position:absolute;left:-26px;top:12%;bottom:12%;width:12px;display:none;
  background:repeating-linear-gradient(to bottom,var(--ghost) 0 1px,transparent 1px 13px);
  -webkit-mask-image:linear-gradient(transparent,#000 18%,#000 82%,transparent);
          mask-image:linear-gradient(transparent,#000 18%,#000 82%,transparent)}
@media(min-width:1180px){.scale{display:block}}

/* ── fold 1 · hero ── */
.hero{display:grid;grid-template-columns:1fr;gap:clamp(22px,3vw,34px);align-items:start}
@media(min-width:900px){.hero{grid-template-columns:auto 1fr;gap:clamp(30px,4vw,58px)}}
.hero .iris{width:clamp(74px,9vw,104px);height:clamp(74px,9vw,104px)}
.hero .iris svg{width:100%;height:100%;display:block}
.hero .tick{transform-origin:16px 16px;animation:scopespin 120s linear infinite}
@keyframes scopespin{to{transform:rotate(360deg)}}
.wordmark{font-family:var(--hud);font-weight:700;font-size:clamp(20px,2.2vw,26px);
  letter-spacing:.42em;color:#fff;line-height:1;margin-bottom:clamp(18px,2.4vw,26px)}
.wordmark .s{color:var(--accent)}
.thesis{font-family:var(--serif);font-weight:400;
  font-size:clamp(2.05rem,4.6vw,4.15rem);line-height:1.06;letter-spacing:-.015em;
  color:var(--ink);text-wrap:balance;max-width:16ch}
.thesis em{font-style:italic;color:var(--accent)}
.sub{font-family:var(--mono);font-size:clamp(12px,1.05vw,13.5px);line-height:1.75;
  color:var(--dim);margin-top:clamp(18px,2.2vw,26px);max-width:62ch;text-wrap:pretty}
.sub b{color:var(--ink);font-weight:500}
.statline{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim);margin-top:clamp(20px,2.6vw,30px);
  display:flex;gap:9px 22px;flex-wrap:wrap;align-items:center}
.statline .on{color:var(--long)}
.statline .on::before{content:'●';margin-right:7px;animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{50%{opacity:.35}}

/* ── fold 2 · the ledger, drawn ── */
.sechead{font-family:var(--hud);font-weight:700;font-size:clamp(19px,2vw,25px);
  letter-spacing:.01em;color:var(--ink);margin-bottom:10px}
.secbody{font-family:var(--mono);font-size:12.5px;line-height:1.75;color:var(--dim);
  max-width:66ch;text-wrap:pretty}
.secbody b{color:var(--ink);font-weight:500}
.secbody .g{color:var(--long)} .secbody .r{color:var(--short)}

.matrix{margin:clamp(26px,3.4vw,42px) 0 0;overflow:hidden;position:relative}
.matrix pre{font-family:var(--mono);font-weight:500;line-height:1.02;letter-spacing:0;
  white-space:pre;margin:0 auto;width:max-content;max-width:100%}
/* one grid per viewport: 150 cols needs ~12px cells to read, 60 cols suits a phone */
.matrix .wide{display:none;font-size:min(1.02vw,12px)}
.matrix .narrow{font-size:min(2.5vw,11px)}
@media(min-width:680px){
  .matrix .wide{display:block} .matrix .narrow{display:none}
}
/* A scope sweep passes over the plate once, left→right. It is ADDITIVE — the
   curve is fully painted without it. Never gate the artwork behind an
   animation: a paused tab, a print view or a headless render would ship the
   page's whole argument blank. */
.matrix::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(90deg,transparent,rgba(91,157,255,.10) 45%,
    rgba(232,238,248,.16) 50%,rgba(91,157,255,.10) 55%,transparent);
  transform:translateX(-100%);animation:sweep 1.7s cubic-bezier(.33,1,.68,1) .15s 1}
@keyframes sweep{to{transform:translateX(100%)}}
.matrix i{font-style:normal}
.matrix .f{color:var(--ghost)}
.matrix .g{color:var(--long);opacity:.42}
.matrix .r{color:var(--short);opacity:.42}
.matrix .gc{color:var(--long);text-shadow:0 0 10px rgba(31,217,137,.55)}
.matrix .rc{color:var(--short);text-shadow:0 0 10px rgba(255,84,104,.5)}
.mcap{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;
  font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim);margin-top:14px;padding-top:11px;border-top:1px solid var(--line)}

.gauges{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;margin-top:clamp(26px,3.4vw,40px);
  background:var(--line);border:1px solid var(--line)}
@media(min-width:760px){.gauges{grid-template-columns:repeat(4,1fr)}}
.gauge{background:var(--bg);padding:16px 18px 18px}
.gauge .k{font-family:var(--mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--faint)}
.gauge .v{font-family:var(--mono);font-size:clamp(20px,2vw,25px);font-weight:800;color:var(--ink);
  margin-top:8px;letter-spacing:-.01em}
.gauge .v.g{color:var(--long)} .gauge .v.r{color:var(--short)} .gauge .v.a{color:var(--amber)}
.gauge .v small{font-size:12px;font-weight:500;color:var(--dim);letter-spacing:0}
.gauge .n{font-family:var(--mono);font-size:9.5px;color:var(--dim);margin-top:6px;line-height:1.5}
.gauge a{color:inherit;text-decoration:none;border-bottom:1px solid rgba(246,173,60,.35)}

/* ── fold 3 · the loop ── */
.loop{display:grid;grid-template-columns:1fr;gap:1px;margin-top:clamp(24px,3vw,36px);
  background:var(--line);border:1px solid var(--line)}
@media(min-width:680px){.loop{grid-template-columns:repeat(5,1fr)}}
.st{background:var(--bg);padding:18px 16px 20px;position:relative}
.st .n{font-family:var(--mono);font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--ink)}
.st .d{font-size:12px;color:var(--dim);line-height:1.55;margin-top:8px;font-family:var(--mono)}
.st::after{content:'';position:absolute;right:-1px;top:50%;width:5px;height:5px;
  border-top:1px solid var(--accent);border-right:1px solid var(--accent);
  transform:translate(50%,-50%) rotate(45deg);background:var(--bg);z-index:2}
.st:last-child::after{display:none}
@media(max-width:679px){.st::after{right:50%;top:auto;bottom:-1px;
  transform:translate(50%,50%) rotate(135deg)}}
.rearm{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim);margin-top:14px;text-align:center}
.rearm b{color:var(--accent);font-weight:700}

/* ── fold 4 · the two doors ── */
.doors{display:grid;grid-template-columns:1fr;gap:1px;margin-top:clamp(24px,3vw,36px);
  background:var(--line);border:1px solid var(--line)}
@media(min-width:760px){.doors{grid-template-columns:1fr 1fr}}
.door{display:block;text-decoration:none;background:var(--bg);
  padding:clamp(24px,3vw,34px);position:relative;transition:background .18s}
.door .sub{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim)}
.door h3{font-family:var(--hud);font-size:clamp(26px,3vw,36px);font-weight:700;letter-spacing:.1em;
  margin:10px 0 0;color:var(--ink);line-height:1}
.door p{font-family:var(--mono);font-size:12px;line-height:1.7;color:var(--dim);margin:14px 0 0;max-width:44ch}
.door .pages{font-family:var(--mono);font-size:10px;color:var(--dim);margin-top:12px;letter-spacing:.06em}
.door .go{font-family:var(--mono);font-size:11px;font-weight:700;margin-top:22px;color:var(--accent);
  display:flex;align-items:center;gap:8px}
.door .go span{display:inline-block;transition:transform .22s cubic-bezier(.22,1,.36,1)}
.door::before{content:'';position:absolute;left:0;top:0;right:0;height:2px;transform:scaleX(0);
  transform-origin:left;transition:transform .28s cubic-bezier(.22,1,.36,1)}
.door.prop::before{background:var(--accent)}
.door.hedge::before{background:var(--amber)}
.door:active{background:var(--panel)}
@media(hover:hover){
  .door:hover{background:var(--panel)}
  .door:hover::before{transform:scaleX(1)}
  .door:hover .go span{transform:translateX(5px)}
}

/* ── fold 5 · honesty ── */
.honesty{font-family:var(--mono);font-size:12.5px;line-height:1.85;color:var(--dim);
  max-width:60ch;text-wrap:pretty}
.honesty b{color:var(--ink);font-weight:500}
.honesty .no{color:var(--short)}

/* ── entrances: staggered, and safe — content is visible without them ── */
@keyframes rise{from{opacity:0;transform:translateY(9px)}}
.rise{animation:rise .62s cubic-bezier(.22,1,.36,1) both}

@media(prefers-reduced-motion:reduce){
  .tick,.statline .on::before,.rise{animation:none}
  .matrix::after{display:none}          /* the sweep is the only pure decoration */
  .door .go span,.door::before{transition:none}
}
</style>"""

_IRIS = """
<svg viewBox="0 0 32 32" aria-hidden="true">
  <circle cx="16" cy="16" r="9.5" fill="none" stroke="#5b9dff" stroke-width="1.3"/>
  <circle cx="16" cy="16" r="13.4" fill="none" stroke="#192232" stroke-width="1"/>
  <circle cx="16" cy="16" r="3" fill="#1fd989"/>
  <g class="tick">
    <path d="M16 1.4v4M16 26.6v4M1.4 16h4M26.6 16h4" stroke="#5b9dff"
          stroke-width="1.1" stroke-linecap="round"/>
  </g>
</svg>"""

_XH = ('<i class="xh tl"></i><i class="xh tr"></i>'
       '<i class="xh bl"></i><i class="xh br"></i>')


def render() -> str:
    g = _gauges()
    cum = _curve()

    span = f"{g['first'][:7]} → {g['last'][:7]}" if g["first"] else "—"

    body = f"""
<section class="plate">{_XH}<i class="scale"></i>
  <div class="hero">
    <div class="iris">{_IRIS}</div>
    <div>
      <div class="wordmark rise">LEN<span class="s">S</span></div>
      <h1 class="thesis rise" style="animation-delay:.06s">An instrument that reads
        the market and <em>refuses</em> to trade it.</h1>
      <p class="sub rise" style="animation-delay:.14s">It reads live Kraken state, filters every
        signal through vetoes derived from its own ledger, and reports the verdict flat —
        <b>ENTER</b> or <b>BLOCKED</b>, sized to the plan. The trader places every order.
        In {g['fills']:,} fills, LENS has never placed one.</p>
      <div class="statline rise" style="animation-delay:.22s">
        <span class="on">system online</span>
        <span>{g['filters']} vetoes armed</span>
        <span>{g['fills']:,} fills logged</span>
        <span>last fill {g['last']}</span>
      </div>
    </div>
  </div>
</section>

<section class="plate">{_XH}
  <h2 class="sechead">The ledger is the argument.</h2>
  <p class="secbody">Every fill is stored, and the curve below is all of them. It ran up,
    gave it back, and went under. That collapse is not a footnote — it is the training set.
    Every veto LENS arms was derived from these trades, not from a book.</p>

  <div class="matrix"
       aria-label="The shape of realised profit and loss across {len(cum)} fills on the hedge book: a long flat stretch, a run up, then a deeper collapse below the starting line."><pre
       class="wide" aria-hidden="true">{_matrix(cum, *WIDE)}</pre><pre
       class="narrow" aria-hidden="true">{_matrix(cum, *NARROW)}</pre>
    <div class="mcap">
      <span>realised p&amp;l · hedge book · {len(cum):,} fills · {span}</span>
      <span>shape, not a track record — unscaled, no axis</span>
    </div>
  </div>

  <div class="gauges">
    <div class="gauge"><div class="k">ledger</div>
      <div class="v">{g['fills']:,}<small> fills</small></div>
      <div class="n">every fill and every rejection</div></div>
    <div class="gauge"><div class="k">vetoes</div>
      <div class="v">{g['filters']}<small> armed</small></div>
      <div class="n">derived from the curve, not a book</div></div>
    <div class="gauge"><div class="k">signals</div>
      <div class="v">{g['seen']}<small> screened</small></div>
      <div class="n">{g['blocked']} blocked by a veto</div></div>
    <div class="gauge"><div class="k">rules audit</div>
      <div class="v a"><a href="/robustness">SUGGESTIVE</a></div>
      <div class="n">not yet significant — say so</div></div>
  </div>
</section>

<section class="plate">{_XH}
  <h2 class="sechead">How it runs.</h2>
  <p class="secbody">One loop, closed. Nothing in it asks for permission to act, because
    nothing in it can act.</p>
  <div class="loop">
    <div class="st"><div class="n">SIGNAL</div>
      <div class="d">a mined setup fires on live Kraken data</div></div>
    <div class="st"><div class="n">FILTERS</div>
      <div class="d">bleed hours, cooldown, venue — auto-veto</div></div>
    <div class="st"><div class="n">VERDICT</div>
      <div class="d">ENTER or BLOCKED, sized to the plan</div></div>
    <div class="st"><div class="n">LEDGER</div>
      <div class="d">every fill and every rejection stored</div></div>
    <div class="st"><div class="n">AUDIT</div>
      <div class="d">analytics re-derive the rules from results</div></div>
  </div>
  <div class="rearm">└─ what the audit learns <b>re-arms the filters</b> — the loop is the system ─┘</div>
</section>

<section class="plate">{_XH}
  <h2 class="sechead">Two books. One instrument.</h2>
  <div class="doors">
    <a class="door prop" href="/prop-dashboard">
      <div class="sub">pass the eval</div>
      <h3>PROP</h3>
      <p>Kraken Prop $10k Advanced. 0.5% risk a trade — survive the 3% floor, reach +9%,
         scale to firm capital.</p>
      <div class="pages">goal · ledger · desk · queue · survival</div>
      <div class="go">ENTER <span>→</span></div>
    </a>
    <a class="door hedge" href="/dashboard">
      <div class="sub">trade your edge</div>
      <h3>HEDGE</h3>
      <p>Own-money discretionary book. Mined setups S1–S5, the vetoes that kill the bleed,
         sizing and journal.</p>
      <div class="pages">plan · position · desk · signals · journal</div>
      <div class="go">ENTER <span>→</span></div>
    </a>
  </div>
</section>

<section class="plate">{_XH}
  <p class="honesty">A pattern alone is a coin-flip, and LENS says so on the page that
    scores it. It reports the odds it can measure and nothing further.<br><br>
    <span class="no">No order endpoint. No trade keys. No opinion it can act on.</span>
    <b>Watch-only, by construction.</b></p>
</section>
"""
    return shell("/system", "System", body, head_extra=_FONT + _CSS, bare=True)
