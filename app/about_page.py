"""LENS /about — who he is, when he started, and what it cost him.

Rewritten 2026-08-05 from dictation. The previous version was the evidence
page in prose: the edge stated once, then four sections of null results. It
was accurate and it was not his voice — his words, "the public website is not
an accurate representation of my voice". Read back, the old page argued like a
paper and he talks like a person who lost a lot of money and learned from it.

So the public site now splits the way the dictation did, cleanly:

  "/"          somebody who already cares about him and wants to know he's okay.
  /about       the story — who, when, what happened, where. THIS page.
  /philosophy  the system — why and how. FIRE arithmetic, the allocation map,
               and the model he was wrong about.
  /evidence    the numbers. Recomputed from the ledger and the research runs,
               including every experiment that failed.

⚠️ No statistics on this page, deliberately, and this is a change of rule
rather than an oversight. The old version restated a win rate, a sample size
and a p-value inline. Those are computed by research runs, and a figure typed
into a prose file goes stale silently the next time one is re-run — a public
page quoting a win rate that the evidence page no longer agrees with is worse
than a page with no number on it. The claim here is one sentence and a link.
If you want a number on this page, read it out of the run, don't retype it.

Rules, inherited and one of them tightened:

  · No creditors, no obligations, no amounts owed. His decision, 2026-08-05:
    the 50 BTC he lost may be named, because it is his own loss and the size
    of the hole is the point of the story. What he owes and to whom may NOT
    appear, in any phrasing, including the dictated "getting back not only
    what is owed". AKA is in wind-down with a live case (HP2025/6818, damages
    hearing ~late 2026); see memory `securities-law-flag`. The sentence "I
    intend to recover more than what is owed" is the single most quotable
    thing this site could publish, and it is not here.
  · No AKA Blockchains, by name or link.
  · No solicitation. The longer written breakdown is mentioned once, at the
    very end, with no link, no price and no signup — his call, 2026-08-05. The
    moment it becomes a link with a price, the "nothing to buy here" guarantee
    that is currently doing legal work for him is gone. Get that wording
    checked before you add it.
"""

from .site import site_shell

BODY = r"""
<h1>I lost more than fifty bitcoin. Getting them back is the
<em>slow</em> part.</h1>

<p class="lede">I'm twenty-five, born and raised in Ireland, and I have a
bachelor's degree in microbiology that I worked out fairly early was never going
to pay for the life I wanted. So I started investing instead, and I've been doing
the same thing for a long time now. <b>It isn't about being smart. It's about
being consistent.</b></p>

<section>
  <div class="lbl">when it started</div>
  <h2>2016, with bitcoin somewhere around three thousand dollars.</h2>

  <p>I bought some, I sold some, and I didn't really know what I was doing. It
  properly started for me in <b>2019</b>, just before COVID — that's when I became
  the bitcoin guy, the one people asked about it. From 2019 to 2021 we saw an
  enormous rise, and I was right about it.</p>

  <p>Being right about the rise is the easy half, and nobody tells you that until
  afterwards.</p>
</section>

<section>
  <div class="lbl">and then the part I don't skip</div>
  <h2>The fall came, I made a lot of mistakes, and almost all of it went.</h2>

  <p><b>More than fifty bitcoin.</b> I'm not going to dress that up as a market
  event or bad luck or a lesson the universe had in store for me. The market did
  what markets do. The mistakes were mine, they were avoidable, and I made them
  because I was naive and because I was in a hurry.</p>

  <p>That's the whole reason any of this exists. Not the winning — the losing. I
  don't think you build a system like this off the back of a good year. You build
  it after a bad one, because a bad one is the only thing that makes you
  suspicious enough of yourself to bother.</p>
</section>

<section>
  <div class="lbl">what it actually taught me</div>
  <h2>Most of the time the answer isn't a trade. It's not taking one.</h2>

  <p>The way it works now: the computer spots something. It hands me a signal and
  I take it or I leave it. It writes down what I did, and later we both go back
  and check — so I can improve what it looks for, and it can show me where I was
  wrong about myself.</p>

  <p><b>There's no large language model in any of this</b>, and there doesn't need
  to be. I'm the one who has to get better. The system's job is to make that
  measurable, not to do it for me.</p>

  <p>And the thing it can't ever do for me is tell me when there is no edge. A
  computer will always find you something; that's what they're for. Knowing when
  the honest answer is <em>nothing today</em> takes discernment and it takes
  history, and both of those are mine to carry.</p>
</section>

<section>
  <div class="lbl">where</div>
  <h2>West to east — and it was arithmetic, not wanderlust.</h2>

  <p>I left Ireland and went to the US first, New York and Arizona, and thought
  for a while I'd live there. With everything going on I decided to look globally
  instead: Germany, France, and eventually Southeast Asia, where I am now.</p>

  <p><b>The reason is boring and it's the entire point.</b> Every target on the
  next page is a multiple of what I spend, not a fixed sum. Cut the spend and the
  pile you need shrinks with it. The same freedom that costs a fortune in New York
  is affordable here, and moving was the cheapest way I know to buy years.</p>
</section>

<section>
  <div class="lbl">the goal</div>
  <h2>Fifty back. A hundred and fifty is the north star.</h2>

  <p>Getting back to <b>50 BTC</b> is the real goal — that's the hole, and filling
  it is what I'm actually doing. <b>150 BTC</b> is the north star, and I hold it
  loosely: it's a direction, not a plan.</p>

  <p>There are two phases and they ask for different people. <b>Phase one</b> uses
  bitcoin's asymmetry to accumulate — a large upside against a downside I've
  chosen and sized in advance. <b>Phase two</b> is de-risking out of it into
  everything else, which is what the allocation on
  <a href="/philosophy">the next page</a> is for.</p>

  <p>I'm not trying to be a billionaire. I want to be able to afford my life,
  wherever I decide to live it, without having to ask anyone. That's the ceiling
  on the ambition and I'm comfortable with it.</p>
</section>

<section>
  <div class="lbl">is any of this real</div>
  <h2>One idea survived testing. Everything else died, and the corpses are
  published.</h2>

  <p>I'm not restating the statistics here, because numbers typed into a page go
  stale and the page keeps saying them anyway. Twelve ideas were tested properly.
  One survived. The rest — including a search over tens of thousands of
  combinations that returned nothing at all, and a funding-rate study that failed
  in August 2026 — are written up next to it, whichever way they landed.</p>

  <p><a href="/evidence">The evidence page</a> recomputes all of it from the
  ledger and the research runs. <b>If it disagrees with anything I've said here,
  believe it and not me.</b></p>

  <p class="small">Slow and steady wins the race isn't a slogan I picked because
  it sounds humble. It's the only thing that has ever worked for me, and I have an
  expensive counter-example to prove it. I'm writing up the longer version of how
  this was actually done — the mistakes in detail, not the highlights — and it
  isn't ready yet. <b>There's nothing to buy here and nothing to sign up for.</b></p>
</section>
"""


def render() -> str:
    return site_shell("/about", "About", BODY)
