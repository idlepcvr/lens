"""LENS /philosophy — the system. Why he's doing it this way, and how.

Rewritten 2026-08-05 from dictation, alongside /about. The split is his: the
story (who, when, where) went to /about, and everything mechanical came here.
Before this, /philosophy held two ideas — cold vs hot, and stock-to-flow. Both
survive, because he didn't contradict either; they are now the middle and end
of a longer argument rather than the whole page.

The order is the order he dictated it in, which is also the order it makes
sense in:

  · FIRE, plainly. 25x spend, 4% a year. The only non-obvious bit is that
    crypto's volatility means he uses 50x, and that moving somewhere cheaper
    shrinks the target itself. This is why /about ends on geography.
  · The allocation map — seven classes, real target weights, read out of
    `~/mine/spec/seed_allocation.csv` (Compact!OB1:OE75 in the sheet). This
    section is the reason the page exists: the number that surprises people is
    that a bitcoin trader's target allocation is 12% crypto.
  · Cold vs hot. Unchanged in substance, but it now nests correctly — it is a
    split *inside* class 7, not a top-level worldview.
  · Stock-to-flow, and its failure. Unchanged.

⚠️ The target weights are DUPLICATED here as prose, not read from the CSV —
this app has no access to `~/mine`. They were correct at 2026-08-05 and are
covered by `tests/test_allocation.py` over there. If that seed file changes,
this page silently lies. The self-check at the bottom of this file catches a
bad edit here; it cannot catch drift over there.

⚠️ NOT called "the Adaptive Horizons Partnership GLTLP Trust Structure Service
Agreement", which is his own name for it. Deliberate. That phrasing is
general-partner/limited-partner language inherited from the dropped fund path,
and a public page that names a GP/LP trust structure reads as an offering
document to exactly the reader who should never read it that way — with a live
case and the securities question already flagged (memory
`securities-law-flag`), that is a needless risk to take for a naming choice.
The map's own root row calls it "Diversified Income Strategies", which is
accurate and is also his.

Same rules as /about: no P&L, no account size, no creditors or amounts owed,
no solicitation, no AKA Blockchains.
"""

from .site import site_shell

# Target weights, class level, from ~/mine/spec/seed_allocation.csv. Kept in one
# list so the sum is checkable at a glance and by the self-check below. Bitcoin
# cold storage is 10 of the 12 crypto points.
ALLOCATION = [
    ("Cash & liquidity", 15, "Two banks and money-market funds. Boring on purpose."),
    ("Savings & bonds", 20, "Deposits, government and corporate bonds, bond ETFs."),
    ("Core compounding", 20, "Index funds, dividend stocks, growth stocks."),
    ("Real estate", 15, "Direct property, REITs, land."),
    ("Alternatives", 8, "Precious metals, commodities, private loans."),
    ("Private equity / VC", 10, "Funds, venture, hedge funds."),
    ("Crypto", 12, "Of which ten points is bitcoin in cold storage."),
]

_CSS = r"""<style>
.alloc{margin:24px 0;border:1px solid var(--line)}
.alloc .r{display:grid;grid-template-columns:1fr auto;gap:4px 14px;
  align-items:baseline;padding:13px 15px;border-top:1px solid var(--line)}
.alloc .r:first-child{border-top:0}
.alloc .r.btc{background:var(--panel)}
.alloc .nm{font-family:var(--hud);font-weight:700;font-size:13.5px;
  letter-spacing:.03em;color:var(--ink)}
.alloc .r.btc .nm{color:var(--accent)}
.alloc .pc{font-family:var(--hud);font-weight:700;font-size:15px;color:var(--dim)}
.alloc .r.btc .pc{color:var(--accent)}
.alloc .nt{grid-column:1/-1;font-size:12.5px;line-height:1.5;color:var(--faint)}
/* the bar is the argument here — proportion, not decoration. 20% is the
   largest class, so 5x scales it to a full-width row and the rest read
   against it honestly. */
.alloc .br{grid-column:1/-1;height:3px;background:var(--line2);margin-top:4px}
.alloc .br i{display:block;height:100%;background:var(--dim)}
.alloc .r.btc .br i{background:var(--accent)}
.alloc .tot{display:flex;justify-content:space-between;padding:11px 15px;
  border-top:1px solid var(--line2);font-family:var(--mono);font-size:10px;
  letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
</style>"""


def _alloc_html() -> str:
    rows = "".join(
        f'<div class="r{" btc" if nm == "Crypto" else ""}">'
        f'<div class="nm">{nm}</div><div class="pc">{pc}%</div>'
        f'<div class="nt">{note}</div>'
        f'<div class="br"><i style="width:{pc * 5}%"></i></div></div>'
        for nm, pc, note in ALLOCATION)
    return (f'<div class="alloc">{rows}'
            f'<div class="tot"><span>seven classes</span>'
            f'<span>{sum(p for _, p, _ in ALLOCATION)}%</span></div></div>')


BODY = f"""
<h1>Most of what I believe about money is <em>deliberately</em> boring.</h1>

<p class="lede">Hold a spread of assets, keep the costs low, let time do the
compounding, and withdraw a small fraction each year once the pile is big enough
to live on. <b>None of that is mine and none of it is original</b> — the research
is public, decades old, and the calculators are free. What follows is how I
actually apply it, including the two places I deviate.</p>

<section>
  <div class="lbl">the arithmetic underneath everything</div>
  <h2>Financial independence is one multiplication, and everyone makes it
  harder than it is.</h2>

  <p>FIRE — financially independent, retire early. The whole principle of personal
  finance is making more than you spend; FIRE is just the version where your
  investments cover your spending permanently. The number is
  <b>25 times your annual spend</b>, which is the same thing as withdrawing
  <b>4% a year</b>.</p>

  <p><b>The first deviation: I use 50x, not 25x.</b> The 4% rule was measured on
  stock and bond portfolios. Crypto is far more volatile than anything in that
  research, and a withdrawal rate that survives a normal recession will not
  survive an 80% drawdown that lasts two years. Doubling the multiple is what it
  costs to hold a volatile asset and be honest about it.</p>

  <p>This is also why where you live is a financial decision and not a lifestyle
  one. <b>50x is a multiple of your spend, not a fixed sum.</b> Fifty times a
  Southeast Asian year is a dramatically smaller number than fifty times a New
  York one, for a life I happen to prefer anyway. That isn't a trick — it's the
  only lever in the equation that works immediately.</p>
</section>

<section>
  <div class="lbl">where it all actually goes</div>
  <h2>The number that surprises people: the target is 12% crypto.</h2>

  <p>Everything gets allocated across seven classes. This is the map I keep, and
  these are targets rather than a description of where I am today — the distance
  between the two is the thing I'm managing.</p>

  {_alloc_html()}

  <p>People assume someone who trades bitcoin is entirely in bitcoin. <b>The
  target is twelve points of crypto, ten of which is bitcoin sitting in cold
  storage doing nothing at all.</b> The other six classes are the point of the
  exercise. Phase one uses bitcoin to reach a number that matters; phase two is
  spending years moving it into these rows, until I never have to be right about
  anything again.</p>
</section>

<section>
  <div class="lbl">the second deviation</div>
  <h2>Crypto isn't one asset class. It's two, and they behave nothing alike.</h2>

  <div class="stat two">
    <div><div class="k">cold storage · the patient half</div>
      <div class="v q">Held long-term in self-custody. Never traded. Sized to
        survive being wrong for years. It isn't income and isn't meant to be —
        it only works if it is never touched, so the discipline it asks for is
        <b>inaction</b>.</div></div>
    <div><div class="k">hot wallet · the active half</div>
      <div class="v q">A funded exchange account running one specific strategy on
        a defined risk budget. This is the part LENS governs, and the only part
        attempting to produce <b>income</b> — and the only part that can be lost
        quickly.</div></div>
  </div>

  <p>That second sentence is why all of the measurement, all of the rules and all
  of the research sit on one side. The patient half needs a hardware wallet and
  the ability to do nothing. The active half needs an instrument panel, because it
  is the half that can be destroyed in a week.</p>

  <p><b>Keeping the two separated is most of the discipline.</b> Money meant to sit
  still and money meant to work are different money. The failure mode — the one
  that ends people — is letting the active side borrow from the patient side after
  a bad run, to make it back. Once that happens there is only one pot, and it is
  being managed by whoever you are on your worst day.</p>
</section>

<section>
  <div class="lbl">how, unglamorously</div>
  <h2>Ten or twenty a day, on a regulated exchange, for years.</h2>

  <p>The mechanism is asymmetry and time. What I can lose on bitcoin is bounded by
  what I choose to put in; what it has historically returned has not been bounded
  the same way, and it has compounded faster than anything else available to me.
  That asymmetry is the entire reason it's in the plan — and it's also the reason
  it's capped at twelve points.</p>

  <p>The rest is dollar-cost averaging. <b>Ten or twenty a day, on a regulated
  exchange, whatever the price happens to be that morning.</b> That's an
  unimpressive sentence and I'm leaving it in, because it's the realistic one. It
  needs an income to sustain and it needs years to matter, and I haven't found a
  faster door that doesn't eventually charge you for having used it.</p>

  <p class="small">What I track alongside it, because none of the above works
  without the actual numbers: net worth, monthly income and spend, the emergency
  fund and the short, medium and long-term savings behind it, debt to income — and
  then the plan itself, which is which country, at what age, at what withdrawal
  rate, and therefore what the invested total and the monthly contribution have to
  be. Yearly expenses sit underneath all of it as the quiet metric that changes
  everything, because budgeting is where the leverage actually is.</p>
</section>

<section>
  <div class="lbl">what changed my mind</div>
  <h2>I believed a beautiful model. It was wrong, and that's the most useful
  thing that's happened to my thinking.</h2>

  <p>The starting position, in 2019, was the <b>stock-to-flow model</b> — the
  argument that bitcoin's price could be predicted from its programmed scarcity and
  its halving schedule. It was compelling. It was quantitative. For a while it
  looked extraordinarily accurate, and I was far from the only person convinced.</p>

  <p><b>Then it failed, badly.</b> Its projections diverged from reality by orders
  of magnitude after 2021. In hindsight the warning signs are the ones I now spend
  most of my time looking for: a suspiciously perfect fit to history, a story that
  explained everything and therefore forbade nothing, and no mechanism that survived
  contact with data it hadn't already seen.</p>

  <div class="stat three">
    <div><div class="k">what it had</div>
      <div class="v q">A near-perfect backtest</div></div>
    <div><div class="k">what it lacked</div>
      <div class="v q">Any out-of-sample test</div></div>
    <div><div class="k">what that is</div>
      <div class="v q">The definition of over-fitting</div></div>
  </div>

  <p>That is the whole reason this site is built the way it is. Why the search
  publishes its failures instead of its winners. Why a result has to survive
  permutation testing and data it has never seen before it counts as anything.
  And why <a href="/about">the claim on the about page</a> is one sentence and a
  link rather than a narrative with numbers in it.</p>

  <p><b>Having believed a beautiful model that turned out to be curve-fitted is a
  better teacher than never having been wrong.</b> It is also the honest answer to
  why I distrust my own good ideas: I have had a very convincing one before.</p>

  <p class="small">Primary sources rather than my summary of them:
  <a href="https://bitcoin.org/bitcoin.pdf">the bitcoin whitepaper</a> ·
  <a href="https://medium.com/@100trillionUSD/modeling-bitcoins-value-with-scarcity-91fa0fc03e25">the
  original 2019 stock-to-flow thesis</a> ·
  <a href="https://medium.com/@100trillionUSD/bitcoin-stock-to-flow-cross-asset-model-50d260feed12">its
  cross-asset extension</a> ·
  <a href="https://www.bitcoinmagazinepro.com/charts/stock-to-flow-model/">the model
  charted against what actually happened</a> ·
  <a href="https://bitbo.io/calendar/2020-halving/">the 2020 halving</a>.
  The fourth is the one worth your time — it is the model next to reality, rather
  than the model on its own.</p>
</section>

<section>
  <div class="lbl">where that leaves me</div>
  <h2>Skeptical of my own conclusions, on purpose.</h2>

  <p>The practical result is a system built to disagree with me. It records what it
  thought before I acted, so I can't rewrite the memory afterwards. It scores ideas
  against random chance rather than against my expectations. And it keeps every
  failed experiment visible, because a research record that only contains successes
  is not a record, it's an advertisement.</p>

  <p>That is not humility as a personality trait. It is the only defence I know of
  against being convinced by something as elegant and as wrong as the model I
  started with. <b>Slow and steady wins the race</b> — and the reason I say that so
  often is that I have already paid for the alternative.</p>
</section>
"""


def render() -> str:
    return site_shell("/philosophy", "Philosophy", BODY, extra_css=_CSS)


if __name__ == "__main__":
    # ponytail: the one thing on this page that can go wrong silently is the
    # allocation drifting out of sync with ~/mine/spec/seed_allocation.csv. A
    # page showing seven weights that sum to 97% is worse than no page at all.
    assert len(ALLOCATION) == 7, ALLOCATION
    assert sum(p for _, p, _ in ALLOCATION) == 100, ALLOCATION
    assert dict((n, p) for n, p, _ in ALLOCATION)["Crypto"] == 12
    # and the two publishing rules that are load-bearing rather than editorial
    body = BODY.lower()
    assert "gltlp" not in body and "adaptive horizons" not in body
    assert "owed" not in body and "creditor" not in body
    print("ok")
