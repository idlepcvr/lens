"""LENS /about — for a reader who can judge the work.

Three public pages, three readers:

  "/"          somebody who already cares about him and wants to know he's okay.
               Never argues, shows. No numbers at all.
  /about       a friend or peer capable of evaluating this, who would be
               insulted by reassurance and will discount anything that reads
               as a pitch. Numbers allowed, and required.
  /philosophy  the same reader, one level down: what he believes about money,
               and the model he was wrong about.

The structural decision, and the whole reason this page works: the claim is
stated ONCE, in its narrowest true form, and then most of the page is what has
NOT worked. A 75,000-combination search that returned nothing is better evidence
of honest method than any equity curve, because nobody fabricates their own null
results. Leading with the best number is what makes a page read as a pitch, and
a sharp reader discounts everything after it.

Rules, inherited from "/" and tightened:

  · No P&L, no account size, no returns. The claim is about a WIN RATE against
    a matched-random baseline — a statement about method, not about money. The
    moment a euro figure appears the page is answering "how rich are you", which
    is a different and much worse conversation.
  · No solicitation of any kind. AKA is in wind-down with a live case and ~179
    creditors; see memory `securities-law-flag`. An open invitation to send
    money is the most quotable artefact a creditor's solicitor could find.
  · No AKA Blockchains, by name or link. Its history belongs to a wound-down
    entity in live litigation, and a personal credibility page is the wrong
    surface for it.
  · Every number here is from the ledger or a research run, and the losing ones
    are on the page next to the winning ones.
"""

from .site import site_shell

BODY = r"""
<h1>I found <em>one</em> edge, and most of this page is the things that
didn't work.</h1>

<p class="lede">I trade bitcoin with my own money, using a system I built to stop
myself from lying to myself about it. <b>Nothing here is a secret method.</b> The
mechanism is a small statistical edge, applied the same way every time, and the
honest status is that it works and is not yet running on enough money to matter.</p>

<section>
  <div class="lbl">the claim, stated once</div>
  <h2>One setup. One side of the market. Ninety-one occurrences.</h2>

  <blockquote>Over <b>n=91</b> occurrences, one short-side setup won <b>68.1%</b>
  of the time against a matched-random baseline of <b>51.9%</b> — a <b>+16.3 point</b>
  difference, significant at <b>p&lt;0.01</b>. Positive in both halves of the sample.
  Survives label permutation and leave-one-month-out testing.</blockquote>

  <p>That is the entire edge. Not a philosophy, not a read on where bitcoin is
  going — one specific, repeatable situation that resolves in my favour more often
  than chance, and which I can describe precisely enough that a computer spots it
  without me.</p>

  <div class="stat three">
    <div><div class="k">how often it fires</div>
      <div class="v">~1.5 times a week</div></div>
    <div><div class="k">how long it's held</div>
      <div class="v">about 21 hours</div></div>
    <div><div class="k">risked vs targeted</div>
      <div class="v">2.83% against 2.83%</div></div>
  </div>

  <p>Everything else on this site is either the machinery that finds situations
  like that, or the record of the ones that turned out not to be real.</p>
</section>

<section>
  <div class="lbl">what didn't work</div>
  <h2>Anyone can show you a winner. The useful question is what happened to
  everything else.</h2>

  <p><b>A 75,000-combination search returned nothing.</b> Every arrangement of
  RSI, moving averages, MACD, Bollinger bands, TD Sequential, chart patterns and
  higher-timeframe trend, across three timeframes and a full matrix of stop and
  target geometries, each one filtered through split-half testing and out-of-sample
  confirmation. Nothing survived that wasn't already known. That result is
  published here rather than quietly dropped.</p>

  <p><b>The positioning research failed too, in August 2026.</b> The reasoning was
  sound: everything above is a rearrangement of the same price candles, so a search
  over them can only recombine what price already said. The funding rate — what
  the crowd pays to hold its position — is genuinely different data, and seven
  years of it exists. It was wired in and tested properly. No funding condition
  beat its baseline once corrected for the number of conditions tested, and the one
  near-miss pointed at the <em>opposite</em> side of the market from the edge above.</p>

  <p><b>A related idea turned out to be untestable at all.</b> Open interest — how
  much money is committed to the market — is retained by exchanges for only about
  thirty days. That is roughly 180 bars, far too few to conclude anything from. It
  is now being collected daily, so the question becomes answerable in about a year
  and a half. It is not answerable today, and saying so is cheaper than pretending
  otherwise.</p>

  <p><b>And the most intuitive idea in trading is backwards.</b> The belief that a
  crowded market can be faded — everyone is buying, so sell — predicted <em>nothing</em>
  (p=0.91). What the data shows instead is that by the time a crowd visibly gets
  punished, the move has already happened. Being contrarian at the top works. Being
  contrarian after the crash is just being late.</p>
</section>

<section>
  <div class="lbl">the real constraint</div>
  <h2>The bottleneck isn't cleverness. It's arithmetic.</h2>

  <p><b>Frequency.</b> A setup that fires 1.5 times a week offers about 78 chances a
  year. That is not many opportunities to compound, no matter how good each one is.
  Most of the research effort goes into finding <em>more valid signals</em>, not
  better ones.</p>

  <p><b>Capital.</b> The part people skip. The same edge on a small account and on a
  large one is the identical system and a completely different life. At a working
  size, one or two good trades a week is a living. At a small size the same trades
  are rounding errors — and the temptation to trade more to compensate is the single
  most expensive mistake available, because fees are charged per trade whether or not
  the trade should have been taken.</p>

  <p><b>Discipline, measured.</b> Across 520 closed trades, the ones that matched the
  system's criteria were profitable and the ones taken against its explicit warnings
  were not. The gap between those two groups is larger than any indicator I have ever
  found. That is not a motivational point, it is the largest measured effect in the
  entire dataset.</p>
</section>

<section>
  <div class="lbl">why this isn't special</div>
  <h2>A small edge, repeated, with enough behind it. That's the whole mechanism.</h2>

  <p>There is no secret and there is no prediction. A strategy that wins slightly
  more than it loses, executed identically every time, on an account large enough for
  the result to matter. No insight into where the market is going, no signal nobody
  else has, nothing that stops working if I describe it out loud.</p>

  <p>The hard parts aren't intellectual. They are: proving an edge is real rather
  than a pattern found by looking too hard; taking every valid signal and no invalid
  ones for months at a time; and surviving the losing streaks a 68% win rate
  guarantees. <b>The research is the easy half.</b></p>
</section>

<section>
  <div class="lbl">what would prove me wrong</div>
  <h2>A claim you can't kill isn't worth much.</h2>

  <p>The edge should be considered dead if its win rate falls to the random baseline
  over the next fifty occurrences, or if it comes out positive in one half of a future
  sample and negative in the other. Both are checked continuously, and both appear
  here whichever way they land.</p>

  <p>The honest current status: <b>validated but under-deployed.</b> Correct, rare,
  and not yet running on enough capital to be a living. That is the actual problem
  being worked on, and stating it plainly is the point of this page.</p>

  <p class="small">Every figure above comes from the trade ledger or a research run,
  and can be traced on <a href="/evidence">the evidence page</a>, which includes the
  experiments that failed. There is nothing to buy here and nothing to sign up for.</p>
</section>
"""


def render() -> str:
    return site_shell("/about", "About", BODY)
