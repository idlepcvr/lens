"""LENS /about — the story, drawn. Who he is, what it cost him, what he's owed himself.

Second pass 2026-08-05, same evening as the voice rewrite. The first pass got
the voice right and the form wrong: five sections of paragraphs. His read —
"nobody's reading all of that information... where are the visual hooks? most
people will not give a shit, so you might have to make it visually easy for
them so it fits into their schema."

So this page now works the way "/" already did, and should have from the start:

    label · picture · ONE sentence · the paragraph, quietly

The picture carries the story, the hook is the only line a skimmer reads, and
the prose he dictated survives underneath at 13.5px for whoever scrolls.
Nothing was deleted to make room — it was demoted. Read the folds' hooks in
order and you have the entire page: he lost fifty coins, he's climbing back to
fifty and pointing at a hundred and fifty, he moved east because it's cheaper,
and he isn't chasing a fortune.

Three cuts he asked for by name, all of them right:

  · The 2019–2021 rise-and-fall NARRATION is gone. The arc draws it. A
    paragraph that says what the picture already said is the definition of the
    thing he was complaining about.
  · No sermon. The old "what it actually taught me" fold and /philosophy's
    "skeptical of my own conclusions, on purpose" closer both read as piety —
    "you don't need to be like a fucking saint". Cut.
  · The loss is denominated in MONEY, not coins. "Fifty bitcoin" is not a
    quantity a normal reader has any feel for; a number with a currency sign
    lands instantly. See memory `feedback-explain-with-schemas` — borrow a
    schema already in the listener's head.

⚠️ That money figure is COMPUTED AT RENDER from `lens_config.btc_price_eur`,
never typed. Fifty coins is worth whatever fifty coins is worth today, and a
hard-coded "€2.9m" would be quietly wrong within the week. If the config price
is missing the clause drops out and the sentences still read — check
`_loss_in_money()` before touching it.

Rules, unchanged from the first pass and still binding:

  · No creditors, no obligations, no amounts owed, in any phrasing. His own
    50 BTC loss is in — that is his to tell. What he owes and to whom is not,
    including the dictated "getting back not only what is owed". Live case;
    see memory `securities-law-flag`.
  · No AKA Blockchains, by name or link.
  · No solicitation. The longer written breakdown is mentioned once, with no
    link, no price and no signup. "Nothing to buy here" stays until a lawyer
    has seen whatever replaces it.
  · No retyped statistics. /evidence recomputes them; this page links.
"""

import sqlite3

from .database import DB_PATH
from .site import site_shell

LOST_BTC = 50          # "more than fifty" — his figure, and the floor of it
GOAL_BTC = 50          # the hole he is filling
NORTH_STAR_BTC = 150   # the direction, held loosely


def _price_eur() -> float | None:
    """Last known BTC price in EUR, from the goal config he keeps current."""
    try:
        con = sqlite3.connect(DB_PATH)
        row = con.execute(
            "SELECT btc_price_eur FROM lens_config WHERE id=1").fetchone()
        return row[0] if row and row[0] and row[0] > 0 else None
    except sqlite3.Error:
        return None


def _held_btc() -> float:
    """Latest logged stack snapshot, for the 'you are here' mark on the ladder.

    Zero is a real answer and it renders as one. The whole page is built on
    saying the true thing; a marker nudged off the origin to look less bleak
    would be the one dishonest pixel on it.
    """
    try:
        con = sqlite3.connect(DB_PATH)
        row = con.execute(
            "SELECT btc_balance FROM stack_snapshot "
            "ORDER BY snapshot_date DESC LIMIT 1").fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    except sqlite3.Error:
        return 0.0


def _loss_in_money() -> str:
    """"— about €2.9m at today's price" or "", never a typed constant."""
    p = _price_eur()
    if not p:
        return ""
    m = LOST_BTC * p / 1_000_000
    return f" — about <b>€{m:.1f}m</b> at today's price"


# ── the arc · what happened ───────────────────────────────────────────────
# The one picture that has to do emotional work. Both halves are drawn: the
# run he was right about AND the drop he was not. Showing only the recovery
# would be the same lie as an equity curve with the drawdown cropped off.
_ARC_SVG = """
<svg viewBox="0 0 480 190" role="img" aria-label="Bitcoin's price from 2016:
      a long climb to a 2021 peak, then a crash through 2022, then a slow
      recovery. He bought near the start and lost more than fifty coins in
      the fall.">
  <!-- the fall, shaded, because it is the subject of the picture -->
  <rect x="232" y="20" width="72" height="130" fill="var(--short)" opacity=".09"/>
  <polyline points="30,150 60,146 90,139 120,131 150,110 180,80 205,54 232,32
                    252,58 270,94 288,124 304,142 340,144 380,137 415,130 452,120"
            fill="none" stroke="var(--dim)" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
  <line x1="20" y1="162" x2="462" y2="162" stroke="var(--line2)" stroke-width="1"/>

  <circle cx="30" cy="150" r="4.5" fill="var(--bg)" stroke="var(--ink)"
          stroke-width="1.6"/>
  <!-- clears the rising curve (y≈140 at x=85); do not drop this baseline -->
  <text x="30" y="128" class="lb on" text-anchor="start">bought in</text>

  <circle cx="304" cy="142" r="5" fill="var(--short)"/>
  <text x="268" y="26" class="lb" text-anchor="middle"
        fill="var(--short)">the fall</text>

  <text x="30" y="177" class="lb">2016</text>
  <text x="232" y="177" class="lb" text-anchor="middle">2021</text>
  <text x="304" y="177" class="lb" text-anchor="middle">2022</text>
  <text x="452" y="177" class="lb" text-anchor="end">now</text>
</svg>"""


# ── the ladder · what he's climbing ───────────────────────────────────────
def _ladder_svg() -> str:
    """0 → 50 → 150, with the two phases as two stretches of one climb."""
    held = _held_btc()
    x0, x1, span = 40.0, 448.0, float(NORTH_STAR_BTC)
    x = lambda btc: x0 + (x1 - x0) * min(btc, span) / span   # noqa: E731
    xg, xh = x(GOAL_BTC), x(held)
    return f"""
<svg viewBox="0 0 480 130" role="img" aria-label="A scale from zero to 150
      bitcoin. Phase one runs from where he is now to 50 coins, the amount he
      lost. Phase two runs from 50 to 150, the north star.">
  <line x1="{x0}" y1="56" x2="{x1}" y2="56" stroke="var(--line2)"
        stroke-width="7" stroke-linecap="round"/>
  <line x1="{x0}" y1="56" x2="{xg}" y2="56" stroke="var(--accent)"
        stroke-width="7" stroke-linecap="round"/>

  <line x1="{xg}" y1="40" x2="{xg}" y2="72" stroke="var(--ink)" stroke-width="1.5"/>
  <text x="{xg}" y="88" class="lb on" text-anchor="middle">50 ₿</text>
  <text x="{xg}" y="101" class="lb" text-anchor="middle">what I lost</text>

  <line x1="{x1}" y1="40" x2="{x1}" y2="72" stroke="var(--dim)" stroke-width="1.5"/>
  <text x="{x1}" y="88" class="lb on" text-anchor="end">150 ₿</text>
  <text x="{x1}" y="101" class="lb" text-anchor="end">north star</text>

  <!-- Anchored to the OUTER ends and kept SHORT. At the mobile label size the
       two long forms ("build it back" / "spread it out") total ~412 user units
       against a 408-unit track and collide into "backphase". The paragraph
       under this diagram spells both phases out in full; the picture doesn't
       have to. Budget is ~200 units per label — count characters before
       lengthening either one. -->
  <text x="{x0}" y="30" class="lb" text-anchor="start"
        fill="var(--accent)">phase one · climb</text>
  <text x="{x1}" y="30" class="lb" text-anchor="end">phase two · spread out</text>

  <circle cx="{xh}" cy="56" r="6" fill="var(--bg)" stroke="var(--ink)" stroke-width="2"/>
  <text x="{xh}" y="120" class="lb on" text-anchor="middle">today</text>
  <line x1="{xh}" y1="66" x2="{xh}" y2="108" stroke="var(--line2)"
        stroke-width="1" stroke-dasharray="2 3"/>
</svg>"""


# ── the journey · why he lives here ───────────────────────────────────────
# One line whose HEIGHT is the cost of living, so the argument is the shape:
# it rises to New York and then falls off a cliff eastward. No figures on it —
# the claim is directional and drawing it with invented numbers would be
# precision he hasn't earned.
_JOURNEY_SVG = """
<svg viewBox="0 0 480 150" role="img" aria-label="His moves from west to east —
      Ireland, New York, Arizona, Germany and France, then Bangkok — plotted
      against cost of living, which peaks in New York and falls sharply
      eastward.">
  <!-- axis label sits BELOW the plot: at the mobile label size it collides
       with the New York peak label if kept at the top left. -->
  <text x="14" y="120" class="lb">cost of living</text>
  <line x1="20" y1="30" x2="20" y2="104" stroke="var(--line2)" stroke-width="1"/>

  <polyline points="52,62 148,34 226,74 316,66 444,104" fill="none"
            stroke="var(--dim)" stroke-width="1.8" stroke-linejoin="round"/>

  <circle cx="52" cy="62" r="4" fill="var(--bg)" stroke="var(--dim)" stroke-width="1.6"/>
  <circle cx="148" cy="34" r="4" fill="var(--bg)" stroke="var(--dim)" stroke-width="1.6"/>
  <circle cx="226" cy="74" r="4" fill="var(--bg)" stroke="var(--dim)" stroke-width="1.6"/>
  <circle cx="316" cy="66" r="4" fill="var(--bg)" stroke="var(--dim)" stroke-width="1.6"/>
  <circle cx="444" cy="104" r="5.5" fill="var(--accent)"/>

  <text x="52" y="52" class="lb" text-anchor="middle">Ireland</text>
  <text x="148" y="24" class="lb" text-anchor="middle">New York</text>
  <text x="226" y="92" class="lb" text-anchor="middle">Arizona</text>
  <text x="316" y="56" class="lb" text-anchor="middle">Germany · France</text>
  <text x="444" y="122" class="lb on" text-anchor="end" fill="var(--accent)">Bangkok</text>

  <line x1="20" y1="134" x2="462" y2="134" stroke="var(--line2)" stroke-width="1"/>
  <text x="20" y="148" class="lb">west</text>
  <text x="462" y="148" class="lb" text-anchor="end">east</text>
</svg>"""


def _body() -> str:
    return f"""
<h1>I lost more than fifty bitcoin. Getting them back is the
<em>slow</em> part.</h1>

<p class="lede">I'm twenty-five, born and raised in Ireland, with a
microbiology degree I worked out early was never going to pay for the life I
wanted. So I invested instead. <b>It isn't about being smart. It's about being
consistent.</b></p>

<section>
  <div class="lbl">what happened</div>
  <figure>{_ARC_SVG}</figure>
  <p class="hook">Fifty bitcoin{_loss_in_money()}. The mistakes were
  <em>mine</em>.</p>

  <p class="detail">I'm not going to dress it up as a market event or bad luck.
  The market did what markets do. I was naive, I was in a hurry, and almost all
  of it went.</p>

  <p class="detail">That's the whole reason this system exists. Not the winning
  — the losing. You don't build something like this after a good year. You build
  it after a bad one, because a bad one is the only thing that makes you
  suspicious enough of yourself to bother.</p>
</section>

<section>
  <div class="lbl">what I'm doing about it</div>
  <figure>{_ladder_svg()}</figure>
  <p class="hook">Fifty back is the goal. A hundred and fifty is just the
  <em>direction</em>.</p>

  <p class="detail"><b>Phase one</b> uses bitcoin to climb — a large upside
  against a downside I size and choose in advance. <b>Phase two</b> is years of
  moving it back out into everything else, so that eventually I don't have to be
  right about anything. <a href="/philosophy">That split is on the next
  page</a>, and it's the only idea on it.</p>
</section>

<section>
  <div class="lbl">why I live where I live</div>
  <figure>{_JOURNEY_SVG}</figure>
  <p class="hook">I moved east because freedom is <em>cheaper</em> here.</p>

  <p class="detail">Not wanderlust — arithmetic. What I need to stop working is
  a multiple of what I spend, never a fixed sum, so cutting the spending shrinks
  the finish line itself. Moving was the fastest way I've found to buy years,
  and I prefer the life anyway.</p>
</section>

<section>
  <div class="lbl">what I'm actually after</div>
  <p class="hook">Not a fortune. Just being able to <em>afford my life</em>
  without asking anyone.</p>

  <p class="detail">That's the ceiling on the ambition and I'm comfortable with
  it. Slow and steady wins the race isn't a slogan I picked because it sounds
  humble — it's the only thing that's ever worked for me, and I have an
  expensive counter-example.</p>

  <p class="small">One trading idea has survived proper testing; everything else
  I tried died, and the failures are published beside it on
  <a href="/evidence">the evidence page</a>, which recomputes the numbers rather
  than repeating mine. If it disagrees with anything here, believe it and not me.
  I'm writing up the longer version of how this was actually done, mistakes and
  all — it isn't ready. <b>There's nothing to buy here and nothing to sign up
  for.</b></p>
</section>
"""


def render() -> str:
    return site_shell("/about", "About", _body())


if __name__ == "__main__":
    # ponytail: the money clause is the only computed string on the page, and
    # a wrong one is a public lie about how much he lost. Check both branches.
    import re
    html = render()
    assert "<h1>" in html and "hook" in html
    assert html.count("<figure>") == 3, "three drawings expected"
    # Word boundaries, and against the COPY not the shell: "allowed" in a CSS
    # comment contains "owed", and a check that cries wolf gets deleted.
    for banned in ("owed", "creditor", "creditors", "gltlp"):
        assert not re.search(rf"\b{banned}\b", _body().lower()), banned
    p = _price_eur()
    if p:
        assert f"€{LOST_BTC * p / 1_000_000:.1f}m" in html
        print(f"ok — price €{p:,.0f}, loss rendered as €{LOST_BTC * p / 1e6:.1f}m")
    else:
        assert "at today's price" not in html, "clause must drop out cleanly"
        print("ok — no config price, money clause correctly omitted")
