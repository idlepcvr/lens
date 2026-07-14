"""LENS / — the front door, in plain English.

This page has exactly one job: a person who knows nothing about markets reads it
once and understands what Lucky does for a living. Not persuaded — *understood*.

Why it reads the way it does, so nobody "improves" it back into jargon:

  · No numbers. None. Not the ledger, not the fills, not the vetoes, not the
    win rate. The moment a figure appears, the reader stops reading and starts
    evaluating — and a figure invites the two questions this page must not
    invite: "are you any good?" and "how much have you got?"

  · No trading words. No signal, edge, veto, R, drawdown, position, backtest.
    Every one of them is a word that means something precise to him and nothing
    at all to her. A page that needs a glossary has failed before the glossary.

  · It borrows a schema instead of inventing one. "Doctor" is understood not
    because people know what doctors do all day, but because they have MET THE
    OUTPUT — they were sick, and then they were better. So the page leads with
    the one thing here that has a visible beneficiary: when a price is falling
    and a frightened person needs OUT, someone has to be willing to come IN, or
    they simply cannot leave. That someone is him. That is what he is paid for,
    and it is mechanically true of the strategies he actually runs (dips and
    pullbacks — he buys while it's falling).

  · The machine is introduced only after the job makes sense, and only as an
    answer to a problem the reader now feels: frightening-and-good and
    frightening-and-stupid are the same sensation in the body.

  · It does not claim he makes money. It explains the work. The ledger's own
    verdict on how the work is going lives on the pages that score it — not on
    the page he hands to someone he loves.

The instrument plate that used to live here now lives at /system, unchanged.
"""

from .theme import shell

_FONT = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Libre+Caslon+Text:ital@0;1&display=swap" rel="stylesheet">'
)

_CSS = r"""<style>
:root{--serif:'Libre Caslon Text',Georgia,serif}
.app{max-width:760px;padding-top:clamp(20px,4vw,54px)}
@media(max-width:679px){.app{max-width:100%}}

.ex{padding-bottom:40px}
.ex .mark{font-family:var(--mono);font-size:11px;letter-spacing:.34em;
  text-transform:uppercase;color:var(--faint);margin-bottom:clamp(40px,9vh,86px)}
.ex .mark b{color:var(--dim);font-weight:400}

/* the hero statement — the only place the serif is allowed to shout */
.ex h1{font-family:var(--serif);font-weight:400;color:var(--ink);
  font-size:clamp(30px,5.4vw,52px);line-height:1.18;letter-spacing:-.01em;
  margin:0 0 26px;max-width:16ch}
.ex h1 em{font-style:italic;color:var(--accent)}
.ex .lede{font-size:clamp(16px,2vw,19px);line-height:1.65;color:var(--dim);
  max-width:54ch;margin-bottom:clamp(52px,10vh,104px)}
.ex .lede b{color:var(--ink);font-weight:600}

/* each fold: a quiet mono label, a serif claim, then prose */
.ex section{padding:clamp(34px,6vw,54px) 0;border-top:1px solid var(--line)}
.ex .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--accent);margin-bottom:18px}
.ex h2{font-family:var(--serif);font-weight:400;color:var(--ink);
  font-size:clamp(22px,3.2vw,31px);line-height:1.3;margin:0 0 22px;max-width:22ch}
.ex p{font-size:clamp(15px,1.8vw,17px);line-height:1.72;color:var(--dim);
  max-width:58ch;margin:0 0 18px}
.ex p b{color:var(--ink);font-weight:600}
.ex p:last-child{margin-bottom:0}

/* the one pulled-out line per fold — the sentence she'd repeat to someone else */
.ex .pull{font-family:var(--serif);font-size:clamp(18px,2.4vw,23px);line-height:1.5;
  color:var(--ink);border-left:2px solid var(--accent);padding:2px 0 2px 20px;
  margin:30px 0;max-width:44ch}

/* --dim, never --faint: --faint is ~3.2:1 on this bg, under the 4.5:1 floor for
   body text. This fold is the honesty statement — it is the last thing that
   should be hard to read. */
.ex .plain{color:var(--dim);font-size:15px;line-height:1.72;max-width:58ch}
.ex .plain b{color:var(--ink);font-weight:600}

/* the door out — deliberately quiet. Nothing here is being sold. */
.ex .out{display:flex;flex-wrap:wrap;gap:10px;margin-top:34px}
.ex .out a{font-family:var(--mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--dim);border:1px solid var(--line);
  border-radius:999px;padding:10px 17px;transition:.15s}
.ex .out a:hover{border-color:var(--accent);color:var(--ink)}
.ex .out a span{color:var(--faint);margin-left:7px}

@media (prefers-reduced-motion:no-preference){
  .rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
  @keyframes rise{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
}
</style>"""


def render() -> str:
    body = """
<div class="ex">
  <div class="mark rise">LENS &nbsp;·&nbsp; <b>what this is</b></div>

  <h1 class="rise" style="animation-delay:.05s">When a price is falling,
    someone still has to <em>buy</em>.</h1>
  <p class="lede rise" style="animation-delay:.12s">That someone is me. It is a real job, it is
    older than the stock market, and it is almost entirely about knowing when <b>not</b> to do it.
    LENS is the machine I built to keep me honest about that.</p>

  <section>
    <div class="lbl">the job</div>
    <h2>Somebody wants out. I&nbsp;am the one coming in.</h2>
    <p>The price of bitcoin moves all day long. When it drops hard, a lot of people get
      frightened and want out — right now, at almost any price.</p>
    <p>Here is the part nobody thinks about: <b>for them to get out, someone has to be
      willing to come in.</b> A sale needs a buyer. If nobody is willing, the frightened
      person is simply stuck.</p>
    <p>So they take a worse price to get someone to step up. <b>That discount is what I'm
      paid.</b> I buy while it is still frightening, and I sell later, once it isn't.</p>
    <div class="pull">Nobody pays you for being clever. They pay you for being willing.</div>
    <p>It is the same trade as the person who buys a house in a crash, or buys the shop
      when the owner has had enough. They aren't smarter than the seller. They were just
      willing to be there on the bad day.</p>
  </section>

  <section>
    <div class="lbl">why it's hard</div>
    <h2>Frightening and stupid feel exactly the same.</h2>
    <p>A price falling because everyone is panicking, and a price falling because something
      is genuinely broken, look identical while it is happening. They feel identical too —
      same tight chest, same urge to do something.</p>
    <p><b>Your body cannot tell them apart.</b> Mine can't either. And it is worse than that:
      when I am bored I want to trade, and when I am losing I want to trade bigger. Both
      instincts are wrong, and both arrive at full volume at exactly the moment they will
      cost the most.</p>
    <div class="pull">The hard part was never the market. It was me.</div>
    <p>So I stopped trusting myself and wrote it down instead.</p>
  </section>

  <section>
    <div class="lbl">the machine</div>
    <h2>It has seen every trade I have ever made.</h2>
    <p>LENS watches the market and remembers everything I've done in it — every trade, and
      every time I was tempted and didn't. Before I'm allowed to buy, it checks this
      moment against all of them.</p>
    <p><b>Most of the time, it tells me no.</b> That is not the machine failing. That is the
      machine working. Almost every way to lose money at this involves doing it too often.</p>
    <div class="pull">Pilots fly on instruments for the same reason.</div>
    <p>In fog, the inner ear starts lying — it will calmly tell a pilot they are flying
      level while they are rolling into the ground. The training is to ignore what your
      body is screaming and believe the panel in front of you.</p>
    <p>The market is fog. <b>LENS is the panel. I am still the one flying.</b></p>
  </section>

  <section>
    <div class="lbl">what it isn't</div>
    <h2>Nothing here is for sale.</h2>
    <p class="plain">There is no product, no signup, no advice, and no offer. I'm not
      managing anyone's money and I'm not asking for any.<br><br>
      <b>The machine cannot place a trade.</b> It has no permission to — not as a policy,
      but as a fact of how it's built. It has no keys. Every single order is placed by me,
      by hand, after it has had its say.<br><br>
      And it is not a promise that any of this works. This is one of the few jobs where
      you can do everything right and still lose that day. <b>LENS doesn't remove that.
      It just makes sure that when I lose, I lost for a good reason.</b></p>
    <div class="out">
      <a href="/system">the instrument itself <span>→</span></a>
      <a href="/dashboard">go to the desk <span>→</span></a>
    </div>
  </section>
</div>
"""
    return shell("/", "What this is", body, head_extra=_FONT + _CSS, bare=True)
