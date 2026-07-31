"""LENS / — the front door, drawn rather than written.

This page has exactly one job: someone who knows nothing about markets looks at
it once and understands what Lucky actually does. Not persuaded — *understood*,
in about thirty seconds, mostly without reading.

Who it is for, decided 2026-07-31. Not a stranger, and not an investor. The
reader is somebody who already cares about him — a partner, a parent — and
cannot picture his day. They are not evaluating an opportunity, they are
wondering whether he is okay. That single decision sets everything below:

  · They already care, so the page never argues. It shows.
  · They are glancing, not studying, so prose is the fallback and the diagram
    is the message. Every fold is one picture and one sentence.
  · The questions they are too polite to ask out loud are the actual outline:
    is he gambling · does he know what he's doing · could he lose it all
    overnight · is a machine doing this to him.

Rewritten 2026-07-31 (second pass). The first pass was five folds of prose. He
read it back and said a wall of text cannot do this job no matter how good the
sentences are, and he was right — the audience above does not read to be
reassured, they look.

⚠️ The "swing trading" fold was CUT in this pass, not translated. The prose
claimed "I hold for days or weeks, a day trader goes in and out several times a
day, that isn't what I do". Measured over all 496 hedge fills: median hold 2.1
hours, 32% closed inside the hour, 95% inside a day, and not one position ever
held past 3 days. The claim is false against his own ledger. It was survivable
as a loose sentence; as a diagram it would have been the most authoritative
looking element on the page and the only untrue one. There IS a real trend —
volume fell from 137 fills in Feb to 15 in Jul, mean hold roughly tripled since
May — but "moving toward swing trading" is a different sentence from "is a swing
trader", and this page cannot afford the second one. Do not restore the fold
without re-running the hold-time query first.

Rules carried over from the prose version, all still binding:

  · No performance numbers. Not P&L, not the win rate, not the fill count. A
    figure invites "are you any good?" and "how much have you got?", and this
    page must invite neither. The signal grid is the one count on the page and
    it counts DISCIPLINE, not money — every dot is a decision, none is a euro.

  · No trading jargon. No signal, edge, veto, R, drawdown, backtest. Words that
    survive get defined in the sentence that uses them or they don't appear.

  · It does NOT claim he makes money, and does NOT invite anyone to send any.
    He floated adding "give me a few dollars to trade on your behalf"
    (2026-07-31). Left off deliberately: AKA is in wind-down with ~179
    creditors and a live court case, and an open solicitation is the most
    quotable artefact a liquidator or creditor's solicitor could find. See
    memory `securities-law-flag`. Do not add it without a lawyer first.

Cost: one SQL read, no network, no JS. The diagrams are inline SVG and a span
grid — they render in a print view, a paused tab and a headless screenshot.

There is one way out of this page and it goes to the desk. /system — the
instrument plate that used to be "/" — was deleted 2026-07-31, not relinked:
it was a craft showcase aimed at nobody. Its whole content was gauges and a
P&L matrix, and every one of those is banned here by the no-numbers rule, so
there was nothing to fold in. Both books stay reachable from the nav. If you
want it back it is in git, at 43468ca and earlier.
"""

import sqlite3

from .database import DB_PATH
from .theme import shell

_FONT = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Libre+Caslon+Text:ital@0;1&display=swap" rel="stylesheet">'
)


def _decisions() -> list[str]:
    """Every setup LENS has ever spotted, oldest first, as a status per dot.

    Chronological on purpose. Sorting the dots into tidy blocks would draw a
    proportion that reads as a designed ratio; the real order reads as a
    record, which is what it is.
    """
    con = sqlite3.connect(DB_PATH)
    return [r[0] for r in con.execute(
        "SELECT status FROM signals ORDER BY COALESCE(received_at, rowid)")]


# ── diagram 1 · what a trade actually is ──────────────────────────────────
# The literacy gap nobody addresses: the reader may genuinely not know what a
# trade IS. Two of them, side by side, one of each outcome. Drawn as a matched
# pair on purpose — showing only the winner would be the single most dishonest
# thing this page could do.
def _trade_svg(win: bool) -> str:
    if win:
        path = "20,100 45,96 70,104 95,88 120,92 145,70 170,76 195,52 220,44 240,38"
        buy, sell, col = (45, 96), (220, 44), "var(--long)"
        label = "A trade that worked: bought low, the price rose, sold higher."
    else:
        path = "20,45 45,50 70,42 95,58 120,54 145,72 170,68 195,86 220,94 240,100"
        buy, sell, col = (45, 50), (220, 94), "var(--short)"
        label = "A trade that did not work: bought, the price fell, sold lower."
    top, bot = sorted((buy[1], sell[1]))
    return f"""
<svg viewBox="0 0 260 130" role="img" aria-label="{label}">
  <rect x="{buy[0]}" y="{top}" width="{sell[0] - buy[0]}" height="{bot - top}"
        fill="{col}" opacity=".07"/>
  <line x1="{buy[0]}" y1="{buy[1]}" x2="{sell[0]}" y2="{buy[1]}"
        stroke="var(--ghost)" stroke-width="1" stroke-dasharray="2 3"/>
  <line x1="{buy[0]}" y1="{sell[1]}" x2="{sell[0]}" y2="{sell[1]}"
        stroke="var(--ghost)" stroke-width="1" stroke-dasharray="2 3"/>
  <polyline points="{path}" fill="none" stroke="var(--dim)" stroke-width="1.6"
            stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{buy[0]}" cy="{buy[1]}" r="4.5" fill="var(--bg)"
          stroke="var(--ink)" stroke-width="1.6"/>
  <circle cx="{sell[0]}" cy="{sell[1]}" r="4.5" fill="{col}"/>
  <text x="{buy[0]}" y="{buy[1] + (16 if win else -9)}" class="lb"
        text-anchor="middle">bought</text>
  <text x="{sell[0]}" y="{sell[1] + (-9 if win else 17)}" class="lb"
        text-anchor="middle" fill="{col}">sold</text>
</svg>"""


# ── diagram 2 · it cannot press the button ────────────────────────────────
# The reassurance the audience actually needs, and the one claim on the page
# that is architectural rather than a promise. Drawn as a severed link: the
# route that exists goes the long way round, through him.
_KEYS_SVG = """
<svg viewBox="0 0 440 200" role="img" aria-label="LENS has no connection to the exchange.
      It reports to me, and I place every order by hand.">
  <g class="bx">
    <rect x="8" y="16" width="120" height="46" rx="3"/>
    <text x="68" y="44" class="bt" text-anchor="middle">LENS</text>
  </g>
  <g class="bx">
    <rect x="312" y="16" width="120" height="46" rx="3"/>
    <text x="372" y="44" class="bt" text-anchor="middle">THE EXCHANGE</text>
  </g>
  <g class="bx me">
    <rect x="160" y="138" width="120" height="46" rx="3"/>
    <text x="220" y="166" class="bt" text-anchor="middle">ME</text>
  </g>

  <!-- the link that does not exist -->
  <line x1="128" y1="39" x2="312" y2="39" stroke="var(--short)" stroke-width="1.4"
        stroke-dasharray="4 5" opacity=".5"/>
  <g stroke="var(--short)" stroke-width="2.2" stroke-linecap="round">
    <line x1="212" y1="31" x2="228" y2="47"/><line x1="228" y1="31" x2="212" y2="47"/>
  </g>
  <text x="220" y="70" class="lb" text-anchor="middle" fill="var(--short)">no keys</text>

  <!-- the route that does -->
  <path d="M68 62 L68 120 Q68 138 86 138 L160 138" fill="none"
        stroke="var(--accent)" stroke-width="1.5"/>
  <path d="M280 161 L354 161 Q372 161 372 143 L372 62" fill="none"
        stroke="var(--accent)" stroke-width="1.5"/>
  <path d="M368 70 L372 62 L376 70" fill="none" stroke="var(--accent)"
        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="76" y="104" class="lb">it tells me</text>
  <text x="364" y="104" class="lb" text-anchor="end">I place the order</text>
</svg>"""

_CSS = r"""<style>
:root{--serif:'Libre Caslon Text',Georgia,serif}
.app{max-width:820px;padding-top:clamp(20px,4vw,54px)}
@media(max-width:679px){.app{max-width:100%}}

.ex{padding-bottom:44px}
.ex .mark{font-family:var(--mono);font-size:11px;letter-spacing:.34em;
  text-transform:uppercase;color:var(--faint);margin-bottom:clamp(34px,7vh,64px)}
.ex .mark b{color:var(--dim);font-weight:400}

/* the hero statement — the only place the serif is allowed to shout */
.ex h1{font-family:var(--serif);font-weight:400;color:var(--ink);
  font-size:clamp(30px,5.4vw,52px);line-height:1.18;letter-spacing:-.01em;
  margin:0 0 22px;max-width:17ch}
.ex h1 em{font-style:italic;color:var(--accent)}
.ex .lede{font-size:clamp(16px,2vw,19px);line-height:1.6;color:var(--dim);
  max-width:52ch;margin:0}
.ex .lede b{color:var(--ink);font-weight:600}

/* every fold below the hero is the same shape: label · picture · one line */
.ex section{padding:clamp(30px,5.5vw,48px) 0;border-top:1px solid var(--line)}
.ex section:first-of-type{margin-top:clamp(40px,8vh,80px)}
.ex .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--accent);margin-bottom:22px}
/* the caption IS the copy — one sentence, and it sits under its picture */
.ex .cap{font-size:clamp(15px,1.9vw,18px);line-height:1.6;color:var(--dim);
  max-width:50ch;margin:24px 0 0}
.ex .cap b{color:var(--ink);font-weight:600}

/* ── the pair of trades ── */
.pair{display:grid;grid-template-columns:1fr;gap:24px}
@media(min-width:620px){.pair{grid-template-columns:1fr 1fr;gap:clamp(20px,4vw,44px)}}
.pair figure{margin:0}
.pair svg{width:100%;height:auto;display:block;overflow:visible}
.pair figcaption{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);margin-top:12px}
.lb{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;fill:var(--dim)}

/* ── the loop ── */
.loop{display:grid;grid-template-columns:1fr;gap:1px;
  background:var(--line);border:1px solid var(--line)}
@media(min-width:680px){.loop{grid-template-columns:repeat(4,1fr)}}
.stp{background:var(--bg);padding:16px 15px 18px;position:relative}
.stp .w{font-family:var(--mono);font-size:9px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--faint)}
.stp .n{font-family:var(--hud);font-weight:700;font-size:15px;letter-spacing:.04em;
  color:var(--dim);margin-top:9px;line-height:1.25}
/* his step is the argument of the whole diagram, so it is the only lit cell */
.stp.mine{background:var(--panel)}
.stp.mine .w{color:var(--accent)}
.stp.mine .n{color:var(--ink)}
.stp::after{content:'';position:absolute;right:-1px;top:50%;width:5px;height:5px;
  border-top:1px solid var(--line2);border-right:1px solid var(--line2);
  transform:translate(50%,-50%) rotate(45deg);background:var(--bg);z-index:2}
.stp:last-child::after{display:none}
@media(max-width:679px){.stp::after{right:50%;top:auto;bottom:-1px;
  transform:translate(50%,50%) rotate(135deg)}}
.again{font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);margin-top:12px;text-align:center}
.again b{color:var(--accent);font-weight:700}

/* ── the decision grid ── */
.grid{display:flex;flex-wrap:wrap;gap:5px;max-width:640px}
.grid i{width:9px;height:9px;border-radius:50%;background:var(--ghost);
  display:block;flex:0 0 auto}
/* No glow. A bloom on the lit dots makes a quarter of them read as nearer a
   half, which quietly argues against the caption sitting under the grid. The
   proportion IS the message here, so nothing may inflate it. */
.grid i.ok{background:var(--long)}
.key{display:flex;gap:20px;flex-wrap:wrap;font-family:var(--mono);font-size:10px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-top:18px}
.key i{width:8px;height:8px;border-radius:50%;display:inline-block;
  margin-right:7px;background:var(--ghost);vertical-align:middle}
.key i.ok{background:var(--long)}

/* ── the no-keys plate ── */
.keys{max-width:520px}
.keys svg{width:100%;height:auto;display:block;overflow:visible}
.keys .bx rect{fill:var(--panel);stroke:var(--line2);stroke-width:1}
.keys .bx.me rect{fill:var(--accent-d);stroke:var(--accent)}
.keys .bt{font-family:var(--hud);font-weight:700;font-size:12px;
  letter-spacing:.16em;fill:var(--dim)}
.keys .bx.me .bt{fill:var(--ink)}
/* SVG text scales with the viewBox, so on a phone the 440-unit plate shrinks
   to ~0.8x and these drop under 8px. Bump them in user units to compensate. */
@media(max-width:520px){
  .keys .lb{font-size:12px} .keys .bt{font-size:14px}
}

/* the closing note — --dim, never --faint: --faint is ~3.2:1 on this bg,
   under the 4.5:1 floor, and this is the last thing that should be hard to read */
.ex .plain{color:var(--dim);font-size:15px;line-height:1.72;max-width:56ch;margin:0}
.ex .plain b{color:var(--ink);font-weight:600}

/* the door out — deliberately quiet. Nothing here is being sold. */
.ex .out{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px}
.ex .out a{font-family:var(--mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--dim);border:1px solid var(--line);
  border-radius:999px;padding:10px 17px;transition:.15s}
.ex .out a:hover{border-color:var(--accent);color:var(--ink)}
.ex .out a span{color:var(--faint);margin-left:7px}

/* The entrance moves, it never fades. `both` fill-mode applies the from-state
   during the delay, so an opacity:0 keyframe means a headless screenshot, a
   print view or a paused tab ships the hero — the one line that has to land —
   completely blank. Animation is additive here, never load-bearing. */
@media (prefers-reduced-motion:no-preference){
  .rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
  @keyframes rise{from{transform:translateY(9px)}to{transform:none}}
}
</style>"""


def render() -> str:
    seen = _decisions()
    took = sum(s == "approved" for s in seen)
    dots = "".join('<i class="ok"></i>' if s == "approved" else "<i></i>"
                   for s in seen)

    body = f"""
<div class="ex">
  <div class="mark rise">LENS &nbsp;·&nbsp; <b>what this is</b></div>

  <h1 class="rise" style="animation-delay:.05s">I trade bitcoin
    with <em>my own</em> money.</h1>
  <p class="lede rise" style="animation-delay:.12s">Buy low, sell high. That is genuinely the
    whole idea, and it hasn't changed in four hundred years. What takes the work is doing it
    <b>the same way every single time</b>. LENS is the system I built so that I do.</p>

  <section>
    <div class="lbl">what a trade is</div>
    <div class="pair">
      <figure>{_trade_svg(True)}<figcaption>this one worked</figcaption></figure>
      <figure>{_trade_svg(False)}<figcaption>this one didn't</figcaption></figure>
    </div>
    <p class="cap">I buy at one price and sell at another. That gap is the entire job —
      and <b>it goes the wrong way often</b>. Anyone who tells you otherwise is selling
      something.</p>
  </section>

  <section>
    <div class="lbl">how one gets made</div>
    <div class="loop">
      <div class="stp"><div class="w">the computer</div>
        <div class="n">spots one</div></div>
      <div class="stp mine"><div class="w">me</div>
        <div class="n">takes it,<br>or leaves it</div></div>
      <div class="stp"><div class="w">the computer</div>
        <div class="n">writes it down</div></div>
      <div class="stp"><div class="w">the computer</div>
        <div class="n">checks later<br>if I was right</div></div>
    </div>
    <div class="again">└─ and whatever that teaches me <b>changes the rules</b> ─┘</div>
    <p class="cap">The machine does the watching, because if I had to watch for it myself
      I'd start seeing it in places it isn't. <b>But it never decides.</b> That part is
      mine, every single time.</p>
  </section>

  <section>
    <div class="lbl">most of the answers are no</div>
    <div class="grid" role="img" aria-label="Every setup the system has spotted, one dot
      each: {len(seen)} in total, of which {took} passed the rules and the rest were turned
      down or timed out.">{dots}</div>
    <div class="key"><span><i class="ok"></i>passed the rules</span>
      <span><i></i>turned down, or the moment passed</span></div>
    <p class="cap">Every setup it has ever found, one dot each. <b>Most of them never
      became a trade.</b> That isn't the system failing — nearly every way to lose money at
      this comes down to trading too often.</p>
  </section>

  <section>
    <div class="lbl">it cannot press the button</div>
    <div class="keys">{_KEYS_SVG}</div>
    <p class="cap">LENS holds no keys and has no way to reach the exchange. Not as a
      policy — as a fact of how it's built. <b>Every order is placed by me, by hand</b>,
      after it has had its say.</p>
  </section>

  <section>
    <div class="lbl">what it isn't</div>
    <p class="plain">There is no product, no signup, no advice, and no offer. I'm not
      managing anyone's money and I'm not asking for any.<br><br>
      None of this is a promise that it works. This is one of the few jobs where you can do
      everything right and still lose that day. <b>LENS doesn't remove that. It makes sure
      that when I lose, I lost for a reason I can point at.</b></p>
    <div class="out">
      <a href="/dashboard">go to the desk <span>&rarr;</span></a>
    </div>
  </section>
</div>
"""
    return shell("/", "What this is", body, head_extra=_FONT + _CSS, bare=True)
