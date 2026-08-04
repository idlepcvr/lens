"""LENS /about — the page for someone who wants to know if this is real.

Different reader from "/". The front door is for somebody who already cares
about him and is wondering whether he is okay; it never argues, it shows. This
page is for a friend who is capable of judging the work and will not be
flattered by a diagram — somebody who might ask "so are you actually making
money?" and deserves a straight answer.

The temptation with a page like this is to lead with the best number. That is
exactly what makes it read as a pitch, and a sharp reader discounts everything
after it. So the structure is inverted on purpose: the claim is stated once, in
its narrowest true form, and then most of the page is what has NOT worked. A
75,000-combination search that returned nothing is better evidence of honest
method than any equity curve, because nobody fabricates their own null results.

The thesis he wanted stated plainly, and it happens to be true: this is not
special. A small repeatable edge, applied consistently, with enough capital
behind it, is the entire mechanism. Every number below is from the ledger or
the research runs — nothing here is aspirational, and the losing numbers are on
the page next to the winning ones.

Pure static HTML on the shared .help-body explainer style. No JS, no compute,
nothing that can drift out of date silently — figures are dated where they
matter, so a stale number reads as stale rather than as current.
"""

from .theme import shell

BODY = r"""
<div class="help-body">

<p style="color:var(--ink);font-size:14px;margin-bottom:4px"><b>What this is</b></p>
<p>LENS is a trading cockpit for one person and one market — Bitcoin perpetual
futures. It holds the strategy research, the risk model, the trade journal and the
goal arithmetic in one place, so that every claim on it can be checked against the
ledger underneath it rather than remembered generously.</p>

<p>It exists because trading discretionarily and reviewing it from memory is how
people lose money slowly while believing they are doing well. Everything here is an
attempt to make self-deception expensive.</p>

<h4 id="claim">The claim, stated narrowly</h4>

<p>Not "I make X% a month." The honest sentence is smaller and more specific:</p>

<blockquote style="border-left:2px solid var(--accent);padding-left:14px;margin:14px 0;color:var(--ink)">
There is one validated short-side setup. Over <b>n=91</b> occurrences it won
<b>68.1%</b> of the time against a matched-random baseline of <b>51.9%</b> — a
<b>+16.3 point</b> difference, significant at <b>p&lt;0.01</b>. It is positive in both
halves of the sample, and it survives label permutation and leave-one-month-out
testing. Its geometry is a 2.83% stop against a 2.83% target, held about 21 hours.
</blockquote>

<p>That is the whole edge. It is one setup, on one side of the market, and it fires
about <b>1.5 times a week</b>. Everything else on this site is either supporting
machinery or a record of things that did not work.</p>

<h4 id="failures">What hasn't worked — the actual credibility</h4>

<p>Anyone can show you a winning strategy. The useful question is what happened to
all the others, so here they are.</p>

<p><b>The 75,000-combination search returned nothing.</b> Every combination of RSI,
moving averages, MACD, Bollinger bands, TD Sequential, chart patterns and
higher-timeframe trend, across three timeframes and a full stop/target geometry
matrix, filtered through split-half testing and out-of-sample confirmation. Nothing
survived that wasn't already known. That result is on the site, not buried.</p>

<p><b>The positioning research failed too (August 2026).</b> The reasoning was sound:
every input above is a rearrangement of the same price candles, so the search could
only recombine what price had already said. Funding rate — what the crowd pays to
hold its position — is genuinely different data, seven years of it. It was wired in
and tested properly. Result: no funding condition beat its baseline win rate once
corrected for the number of conditions tested, and the one candidate signal pointed
at the <i>opposite</i> side of the market from the validated edge. Open interest
turned out to be impossible to test at all — exchanges retain only about 30 days of
it, which is roughly 180 bars, far too few to conclude anything from.</p>

<p><b>The most common "obvious" idea is backwards.</b> The intuition that a crowded
market can be faded — everyone is long, so sell — predicted nothing at all
(p=0.91). What the data shows instead is that by the time the crowd visibly gets
punished, the move has already happened. Being contrarian at the top works. Being
contrarian after the crash is just being late.</p>

<h4 id="constraint">The real constraint, and it isn't cleverness</h4>

<p>The edge is not the bottleneck. Two other things are, and both are arithmetic
rather than skill:</p>

<p><b>Frequency.</b> A setup that fires 1.5 times a week produces about 78 chances a
year. That is not enough trades for a small account to compound meaningfully, no
matter how good each one is. Most of the research effort goes into finding more
valid signals, not better ones.</p>

<p><b>Capital.</b> This is the part people skip. A 68% edge on a small account and the
same 68% edge on a large one are the identical system and completely different
outcomes. At a working account size, one or two good trades a week is a living. At a
small one, the same trades are rounding errors, and the temptation to overtrade to
compensate is the single most expensive mistake available — because fees are charged
per trade regardless of whether the trade should have been taken.</p>

<p>Measured on the live ledger: across 520 closed trades, the ones that matched the
system's criteria were profitable, and the ones taken against its explicit warnings
were not. The gap between those two groups is larger than any indicator ever found.
Discipline outperformed cleverness by a wide margin, and it wasn't close.</p>

<h4 id="philosophy">Where this sits — the wider picture</h4>

<p>Trading is one drawer, not the whole cabinet. The underlying view is ordinary and
deliberately boring: hold a spread of assets, keep costs low, let time compound, and
withdraw a small fraction each year once the pile is large enough to live on. None of
that is original — the safe-withdrawal-rate research it rests on is public and
decades old, and the calculators are free.</p>

<p>The one part that isn't standard is treating <b>crypto as two asset classes rather
than one</b>, because the two halves behave nothing alike:</p>

<p><b>Cold storage — the patient half.</b> Bitcoin held long-term in self-custody,
never traded, sized to survive being wrong for years. It isn't income and isn't meant
to be. It only works if it is never touched, so the discipline it asks for is
inaction.</p>

<p><b>Hot wallet — the active half.</b> A funded exchange account running one
specific short-side strategy on a defined risk budget. <b>This is the part LENS
governs, and the only part attempting to produce income.</b> It is also the only part
that can be lost quickly, which is why it gets all of the measurement and all of the
rules.</p>

<p>Keeping those two separated is most of the discipline. Money meant to sit still
and money meant to work are different money, and the failure mode is letting the
second borrow from the first after a bad week.</p>

<h4 id="history">What changed my mind</h4>

<p>The starting position, in 2019, was the <b>stock-to-flow model</b> — the argument
that Bitcoin's price could be predicted from its programmed scarcity and halving
schedule. It was compelling, it was quantitative, and for a while it looked
extraordinarily accurate.</p>

<p><b>It then failed badly, and that failure is the most useful thing that has
happened to my thinking.</b> Its projections diverged from reality by orders of
magnitude after 2021. In hindsight it had a suspiciously perfect backtest, a story
that explained everything, and no mechanism that survived contact with the future —
which is a precise description of every over-fitted model I have since learned to
throw away.</p>

<p>That is why this site is built the way it is: why the search publishes its
failures, why a result has to survive permutation testing and out-of-sample data
before it counts, and why the claim at the top of this page is one sentence rather
than a narrative. Having believed a beautiful model that turned out to be curve-fitted
is a better teacher than never having been wrong.</p>

<p style="color:var(--faint);font-size:12px">Primary sources, rather than my summary
of them: <a href="https://bitcoin.org/bitcoin.pdf">the Bitcoin whitepaper</a> ·
<a href="https://medium.com/@100trillionUSD/modeling-bitcoins-value-with-scarcity-91fa0fc03e25">the
original 2019 stock-to-flow thesis</a> ·
<a href="https://medium.com/@100trillionUSD/bitcoin-stock-to-flow-cross-asset-model-50d260feed12">its
cross-asset extension</a> ·
<a href="https://www.bitcoinmagazinepro.com/charts/stock-to-flow-model/">the model
charted against what actually happened</a> ·
<a href="https://bitbo.io/calendar/2020-halving/">the 2020 halving</a>.
The fourth link is the one that matters — it is the model next to reality rather than
the model on its own.</p>

<h4 id="notspecial">Why this isn't special</h4>

<p>There is no secret. The mechanism is boring and entirely public:</p>

<p><b>A small edge, repeated consistently, with enough capital behind it.</b> That's
it. A strategy that wins slightly more than it loses, executed the same way every
time, on an account large enough for the results to matter. No prediction, no
insight into where the market is going, no signal nobody else has.</p>

<p>The hard parts are not intellectual. They are: proving the edge is real rather
than a pattern found by looking too hard; taking every valid signal and no invalid
ones for months on end; and surviving the losing streaks that a 68% win rate
guarantees will happen. The research is the easy half.</p>

<h4 id="falsify">What would prove this wrong</h4>

<p>A claim you can't kill isn't worth much, so: the edge should be considered dead if
the validated setup's win rate falls to its random baseline over the next 50
occurrences, or if it is positive in one half of a future sample and negative in the
other. Both are checked continuously, and both are visible on this site rather than
reported selectively.</p>

<p>The honest current status is that the edge is validated but under-deployed —
correct, rare, and not yet running on enough capital to be a living. That is the
actual problem being worked on, and stating it plainly is the point of this page.</p>

</div>
"""


def render() -> str:
    return shell("/about", "About", BODY)
