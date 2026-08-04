"""LENS /philosophy — what he believes about money, and the model he was wrong about.

Split out of /about on 2026-08-04. /about answers "is this real?" and has to
stay short enough to be read in one sitting by someone deciding whether to take
it seriously. This page is for the reader who already decided yes and wants the
worldview underneath.

Two sections, and the second is the important one:

  · The structure. Ordinary FIRE arithmetic, plus the one non-standard idea:
    crypto is TWO asset classes, not one. Cold storage is patient money whose
    discipline is inaction; the hot wallet is active money and the only part
    attempting income. LENS governs the second. Keeping them apart is most of
    the discipline, and the failure mode is named out loud.

  · Stock-to-flow, and its failure. Told as the origin of the method rather
    than as a confession. S2F had a perfect backtest, a story that explained
    everything, and no mechanism that survived 2021 — which is the exact shape
    of every over-fitted model the search now discards. Having believed a
    beautiful wrong model is a better credential than never having been wrong,
    and it is the honest answer to "why do you test things this way".

Links go to primary sources, including the chart of the model against what
actually happened. That link is deliberately the one called out: it is the model
next to reality rather than the model on its own.

Same rules as /about: no P&L, no solicitation, no AKA Blockchains.
"""

from .site import site_shell

BODY = r"""
<h1>Most of what I believe about money is <em>deliberately</em> boring.</h1>

<p class="lede">Hold a spread of assets, keep costs low, let time compound, and
withdraw a small fraction each year once the pile is large enough to live on.
<b>None of that is original</b> — the research it rests on is public, decades old,
and the calculators are free. The interesting part is one distinction most people
collapse.</p>

<section>
  <div class="lbl">the one non-standard idea</div>
  <h2>Crypto isn't one asset class. It's two, and they behave nothing alike.</h2>

  <div class="stat two">
    <div><div class="k">cold storage · the patient half</div>
      <div class="v q">Held long-term in self-custody. Never traded. Sized to
        survive being wrong for years. It isn't income and isn't meant to be —
        it only works if it is never touched, so the discipline it asks for is
        <b>inaction</b>.</div></div>
    <div><div class="k">hot wallet · the active half</div>
      <div class="v q">A funded exchange account running one specific short-side
        strategy on a defined risk budget. This is the part LENS governs, and the
        only part attempting to produce <b>income</b> — and the only part that can
        be lost quickly.</div></div>
  </div>

  <p>That second sentence is why all of the measurement, all of the rules and all
  of the research sit on one side. The patient half needs a hardware wallet and the
  ability to do nothing. The active half needs an instrument panel, because it is
  the half that can be destroyed in a week.</p>

  <p><b>Keeping the two separated is most of the discipline.</b> Money meant to sit
  still and money meant to work are different money. The failure mode — the one that
  ends people — is letting the active side borrow from the patient side after a bad
  run, to make it back. Once that happens there is only one pot, and it is being
  managed by whoever you are on your worst day.</p>
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
  Why <a href="/about">the claim on the about page</a> is one sentence rather than
  a narrative, and why it is followed immediately by everything that didn't work.</p>

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

  <p>The practical result is a system that is built to disagree with me. It records
  what it thought before I acted, so I can't rewrite the memory afterwards. It scores
  ideas against random chance rather than against my expectations. And it keeps every
  failed experiment visible, because a research record that only contains successes
  is not a record, it's an advertisement.</p>

  <p>That is not humility as a personality trait. It is the only defence I know of
  against being convinced by something as elegant and as wrong as the model I started
  with.</p>
</section>
"""


def render() -> str:
    return site_shell("/philosophy", "Philosophy", BODY)
