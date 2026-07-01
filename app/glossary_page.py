"""LENS /glossary — plain-English reference for every metric the goal model and
the signal tickets throw at you: EV, R, win rate, leverage, fees, account risk,
Kelly, and the drawdown (DD) constraint. Written to be read top-to-bottom once,
then dipped into. Pure static HTML on the shared .help-body explainer style — no
JS, no compute. Mirrors the chain in calculator.py so the words match the maths.
"""

from .theme import shell

BODY = r"""
<div class="help-body">

<p style="color:var(--ink);font-size:14px;margin-bottom:4px"><b>How to read this page</b></p>
<p>Two ideas drive everything below: an <b>edge</b> (do you make money on average per
trade?) and <b>survival</b> (can you take a losing streak without blowing up?). The
goal model turns your inputs into both. Read once top-to-bottom; the worked example
at the end ties it together.</p>

<h4 id="ev">EV per trade — "expected value"</h4>
<p>The <b>average</b> profit (or loss) of one trade, if you took it thousands of times.
Formula: <code>EV = win% × win$ − loss% × loss$</code>. If it's positive you have an
<span class="g">edge</span>; if negative, the trade <span class="r">loses money on
average</span> no matter how a single one turns out. In the goal model
"<b>per-trade EV required</b>" is run backwards: given your target balance and number
of trades, this is the average gain each trade <b>must</b> produce to get there.</p>

<h4 id="rr">R and R:R — your unit of risk</h4>
<p><b>R</b> = the amount you risk on a trade (your stop-loss distance in money). Every
outcome is then measured in Rs: a <b>+3R</b> winner makes 3× what you risked; a loss
is <b>−1R</b>. <b>R:R</b> (reward-to-risk, e.g. <code>3.0</code>) is your take-profit
distance divided by your stop distance. Thinking in R instead of dollars is the whole
game — it makes a $1k account and a $50k account behave identically on screen.</p>

<h4 id="winrate">Win rate</h4>
<p>The share of trades that hit take-profit, 0–1 (e.g. <code>0.44</code> = 44%). A low
win rate is <b>fine</b> if R:R is high — that's the core PRISM finding: moving 1.6R → 4R
matters far more than winning more often. Win rate and R:R together decide whether the
edge exists.</p>

<h4 id="leverage">Leverage</h4>
<p>How many dollars of BTC you control per dollar of account, e.g. <code>10×</code>. It's
an <b>input you choose</b> (the exchange setting), not something the model solves for.
Leverage multiplies <b>both</b> the price move <b>and the fees</b> into account terms —
which is why fees bite so hard (see below).</p>

<h4 id="notional">Notional</h4>
<p>The full position size in dollars = <code>account × leverage × fill</code>. With $1k at
10× that's ~$10k of BTC exposure. A 1% adverse price move on $10k notional = $100 = 10%
of a $1k account. That's leverage turning a small price move into a big account move.</p>

<h4 id="fill">Fill factor</h4>
<p>A haircut (slightly under 1.0) for the fact you don't get filled at the perfect price —
slippage and the position-margin margin. The model bakes it in so the numbers are what you
actually keep, not the ideal-world version.</p>

<h4 id="fees">Fee drag — the silent tax</h4>
<p>Round-trip fees (enter + exit) are small per trade (~0.15%) but get <b>multiplied by
leverage</b>. At 10× a 0.15% fee becomes <b>1.5% of your account every single trade</b>,
win or lose. This is what pushes "true R:R" below the nominal R:R you typed, and it's the
usual cause of the <span class="r">negative-Kelly</span> flag. Lower your assumed fee (or
leverage) and the flag often flips green.</p>

<h4 id="risk">Account risk per trade</h4>
<p>How much of your <b>whole account</b> a single loss costs, as a % — fees included. In
LENS this is <b>derived</b>: the model works out the risk needed to hit your EV goal, then
checks it against the two safety limits below. You can override it if you'd rather fix risk
first and see what return that implies.</p>

<h4 id="truerr">True R:R (actual_rr)</h4>
<p>Your reward-to-risk <b>after fees</b> = <code>gain-on-win ÷ loss-on-loss</code>. Always a
bit worse than the nominal R:R you entered, because fees eat both ends. This — not the
nominal number — is what Kelly is fed.</p>

<h4 id="kelly">Kelly — how big to bet</h4>
<p>The Kelly criterion is the mathematically "growth-optimal" fraction of your account to risk,
given your edge: <code>(win% × R − loss%) ÷ R</code>. It answers <b>"how hard can I press a
real edge?"</b> Two things to know:</p>
<ol>
<li>If the formula returns <b>≤ 0</b>, you have <b>no edge</b> — Kelly says <span class="r">don't bet at all</span>. That's the negative-Kelly warning.</li>
<li>Full Kelly is brutally swingy and assumes your win/R numbers are exactly right (they never are). So LENS uses <b>one-sixth Kelly</b> by default — a deliberately conservative fraction of the "optimal" size.</li>
</ol>
<p>Kelly here is <b>advisory</b>: a sanity check on the risk the goal model derived, not the thing that sets your size.</p>

<h4 id="dd">DD constraint — the survival limit ("DD" = drawdown)</h4>
<p>A <b>drawdown</b> is a peak-to-trough drop in your account. The DD constraint answers the
other question: <b>"what per-trade risk keeps me under my max-acceptable drawdown across a
losing streak?"</b> Formula: <code>1 − (1 − max_dd)^(1 / losses_in_a_row)</code>. Example:
to survive 10 losses in a row without dropping more than 30%, it caps each trade at roughly
3.5% risk. This is pure survival — it ignores your edge entirely.</p>

<h4 id="optimal">Optimal risk = the safer of the two</h4>
<p>The model takes <code>min(Kelly risk, DD risk)</code> — whichever number is <b>smaller /
more cautious</b> wins. Kelly stops you betting too big for your edge; DD stops you betting too
big for your nerves/account. Then it compares that <b>optimal</b> risk to the risk your goal
actually <b>requires</b>:</p>
<ol>
<li><b>Required ≤ optimal</b> → <span class="g">healthy</span>. Your goal is reachable within safe sizing.</li>
<li><b>Required &gt; optimal</b> → <span class="a">warning</span>. The only way to hit the goal is to bet bigger than is safe. Fix: extend the deadline, lower the target, or improve win%/R — don't just crank risk.</li>
</ol>

<h4 id="expectancy">Expectancy &amp; PF — scoring real results</h4>
<p>Once trades are logged, <b>expectancy</b> = average R per trade actually realised (the live
version of EV). <b>PF</b> (profit factor) = gross wins ÷ gross losses; <b>&gt;1 makes money</b>,
&lt;1 loses. These live on <code>/analytics</code> and <code>/edge</code> and are how you tell which
strategies have a real edge versus which just felt good.</p>

<h4>Worked example — $1k · 10× · 44% · 3R</h4>
<p>You risk ~3.5% ($35) per trade. A win at true-R:R ≈ 2.7 (after fees) makes ~$95; a loss costs
~$35. EV per trade = <code>0.44 × $95 − 0.56 × $35 ≈ +$22</code> → positive edge. Kelly on those
numbers might suggest ~6% risk; sixth-Kelly ≈ 1%; the DD limit ≈ 3.5%. Optimal = the smaller,
~1%. If your goal needs 3.5% risk to hit the deadline, that's the <span class="a">required &gt;
optimal</span> warning — the goal is aggressive for the edge, so stretch the timeline rather than
oversize.</p>

<h4 id="sharpe">Sharpe ratio — reward per unit of bumpiness</h4>
<p>Two strategies can both make 30% a year, but one gets there in a smooth line and the
other on a rollercoaster. <b>Sharpe</b> measures which is which: return divided by how much
the results <i>wobble</i>. Higher = smoother ride for the same money. Rough read:
<code>&lt;0</code> bad, <code>~1</code> solid, <code>&gt;2</code> excellent. It's the single
number quants use to compare two edges fairly — it punishes a strategy for being wild.</p>

<h4 id="sortino">Sortino ratio — Sharpe, but fairer to big winners</h4>
<p>Sharpe punishes <i>all</i> wobble, including the good kind (a huge winning trade counts
as "volatility" against you). <b>Sortino</b> fixes that by only counting the <b>downside</b>
wobble — the losses. For a high-R strategy like yours (small losses, occasional big wins),
Sortino is the more honest score, and it'll usually read higher than Sharpe. Same scale:
higher = better.</p>

<h4 id="calmar">Calmar ratio — return for the pain you sat through</h4>
<p>Annual return divided by your <b>worst drawdown</b> (the deepest hole the account fell
into). It answers "how much did I make for the scariest moment I had to stomach?" A Calmar
of <code>2</code> means you made 2× your worst peak-to-trough drop. High Calmar = you didn't
have to bleed much to earn it. This is the one that maps to whether you can actually <i>hold</i>
a strategy without panic-quitting.</p>

<h4 id="regime">Market regime — what "mood" BTC is in</h4>
<p>LENS sorts every day into one of three moods: <b class="g">BULL</b> (trending up),
<b class="a">SIDEWAYS</b> (chopping in a range), <b class="r">BEAR</b> (trending down), using
14-day return + volatility. It matters because your setups <b>don't win equally in all three</b>
— continuation setups starve in a range and print in a trend. The <code>/regime</code> page
tells you which mood is live and whether your hero strategy actually wins in it right now.</p>

<h4 id="transition">Transition matrix &amp; persistence — is the mood about to change?</h4>
<p>Knowing today's regime isn't enough; you want to know if it's about to flip. The
<b>transition matrix</b> is a small grid: "given BTC is BULL today, how often was it still
BULL tomorrow vs flipped to SIDEWAYS/BEAR?" — read straight from history. The diagonal of
that grid is <b>persistence</b>: how <i>sticky</i> a mood is (BTC regimes are very sticky,
~85–93% stay day-to-day). Paired with <b>average run length</b> (how many days a mood usually
lasts), it gives you a read like "we've been sideways 66 days vs a typical 13 — a break is
overdue." It doesn't predict <i>which</i> way, only that the range is stretched.</p>

<h4>How you're meant to use it</h4>
<ol>
<li><b>Set the goal once</b> on <code>/goal</code>: balance, target, date, trades/week, your honest win% and R:R.</li>
<li><b>Read the verdict banner</b> first — healthy / warning / infeasible.</li>
<li><b>Check the Risk &amp; Kelly card</b>: is required risk ≤ optimal? If not, adjust the goal, not the risk dial.</li>
<li><b>Per signal</b>, the ticket shows notional, leverage, and the win/lose balance — that's this same maths applied to one trade.</li>
<li><b>After trades log</b>, let <code>/analytics</code> + <code>/edge</code> replace your <i>assumed</i> win%/R with <i>real</i> expectancy, then refine the goal inputs. That feedback loop is the whole point of LENS.</li>
</ol>

</div>
"""


def render() -> str:
    return shell("/glossary", "Glossary", BODY, meta="reference")
