# Trading philosophy — source: DataDash "Trading Tips" playlist

[Open as HTML](trading-philosophy-2026-08.html)

Extracted 2026-08-27 from 18 of 20 videos in the playlist (auto-captions
pulled and cleaned; #17 "How To Use The RSI" and #19 "How To Use The MACD"
have no captions available anywhere — see **Gaps** below, these are exactly
the two most relevant to what you described). Channel: DataDash / Nicolas
Merton, videos dated September–October 2017. Quoted/paraphrased close to
source; nothing invented.

**Read this first:** the playlist is 2017-era retail technical analysis —
price levels, moving averages, candlestick patterns, Bollinger mean
reversion, and a lot of trader-psychology philosophy. **RSI/MACD
divergence — price making a new high/low while the oscillator doesn't — is
never mentioned once in the 18 available videos.** If divergence is the
core of your setup, it either lives in the two missing videos or it's
something you layered on yourself later. Don't assume it's in here; ask
yourself directly (see Gaps).

---

## 1. Core setups, as taught

**Moving averages — the SMA 50/100/200 stack (daily), same logic on the
hourly for day trading (50h/100h/200h).** This is the closest thing to a
central framework in the whole series:
- Price holding above the 50-day = "confidence in the market," bullish continuation.
- A pullback that breaks the 50 but holds the 100 = normal correction, not a trend change.
- A break down through the 100 to the 200-day = "full-scale pullback mode," real fear, deeper reversal likely.
- The bigger the gap between the 50/100 cluster and the 200, the more confidence in the trend.

**The 21-day MA as a momentum/exuberance gauge**, distinct from the
50/100/200 stack — used on fast-moving names specifically: if price holds
above the 21-day even through a sharp run, that's read as a strong
continuation signal ("a serious sign of optimism… exuberant nature").

**The 9-day MA for scaling out of winners** — not a support level, a
profit-taking trigger: sell a partial position (his own habit: 40–50% off
the first break) every time price closes below the 9-day on a fast mover;
if it reclaims the 9-day, the rule re-arms for the next leg. Explicitly
crypto-specific ("stocks don't move this fast"); on stocks he'd use the 50-day
for the same job.

**Bollinger Bands (20 SMA basis).** Two uses:
1. **Squeeze → expect a move.** Bands narrowing after a volatile period signals
   lower volatility, and lower volatility is read as "loading" for the next
   move — direction unconfirmed until it breaks.
2. **Mean reversion.** ~98% of price action stays inside the bands; multiple
   closes outside them = overextended, expect reversion. Explicitly paired
   with wedges — a Bollinger squeeze and a price wedge are described as the
   same phenomenon seen two ways.

**MACD — only ever described in passing** (inside the day-trading video, #05),
never its own lesson here: "blue line crosses over the orange line" =
bullish; opposite = bearish. No divergence, no histogram detail, no specific
settings mentioned. Treat this as under-documented until you fill the gap.

**RSI — only ever described in passing**, same video: "overbought/oversold"
zones used as one of three same-direction confirmations (with Bollinger
squeeze + MACD cross) before taking a bearish day-trade. No specific
thresholds given anywhere in the 18 videos.

**Chart patterns:**
- **Wedges** — coiling price action, drawn as two converging trendlines.
  A **descending wedge** (support falling slower than resistance) is read
  bullish — "oversold, ready for a breakout." An **ascending wedge**
  (resistance flat/falling slower while support rises fast) is read
  bearish — "too fast a run-up, resistance too strong." A symmetric wedge
  is direction-neutral until it breaks.
- **Bullish/bearish engulfing candle** — a 2-candle pattern: the second
  candle's range must fully contain the first candle's range *and* close
  beyond it. Bullish version flagged as common before uptrends.
- **Hammer / bearish hammer reversal** — small body, long wick opposite the
  reversal direction, short wick on the confirming side. Multiple hammers
  clustering at a level treated as a stronger signal than one alone.
- **Head and shoulders** — mentioned once, standard reversal read, no
  specific rules beyond "look for the shape."
- **Topping pattern** — a candle whose wick is 2–3x its real body in the
  direction of the prior move; read as failed follow-through / exhaustion.

**Fibonacci retracement** — drawn top (older high) to bottom (more recent
low). Used specifically to **stage partial sell orders on the way back up**:
a portion off just before 38.2%, another just before 50%, another just
before 61.8% — never all at one level, and always placed *a little before*
the exact level ("less greedy than the other guy"). A break clean through
all three levels is read as high odds of continuing to the prior high.

**Volume** — a cluster of same-size buy orders repeating at one price level
(visible order-by-order on the tape, not just the volume bar) is read as one
or a few large holders accumulating a position; trade idea: enter near that
zone, stop just below it, target the prior high — low risk because the
accumulator has an incentive to defend that price. Also: volume must be
checked against a real exchange, not a market-maker-inflated one.

**"Big even numbers"** — round price levels (e.g. $3,000, $5,000, round
satoshi levels) act as psychological support/resistance because retail
orders cluster there; a repeated rule: place a sell a little *before* a big
even number, not at it, and re-enter above it if price clears through.

**"Previous resistance becomes support"** (and the mirror on the way down)
— the single most repeated line in the entire series, appearing in nearly
every video regardless of topic. Treated as close to a first principle.

**Order book reading** — used only as a trader's tool (not for long-term
holds): estimate how much volume is needed to clear through to a target
price, and place sells just ahead of a visible sell-wall cluster rather
than behind it.

**Market cycle psychology** (Wall Street Cheat Sheet framework: disbelief →
hope → optimism → belief → thrill → euphoria → complacency → anxiety →
denial → panic → capitulation → anger → depression) — used for macro
position sizing and when to de-risk into altcoins vs. hold Bitcoin, not for
individual trade entries.

---

## 2. Multi-timeframe logic, as taught

Thinner than you might expect — the series never lays out a formal
"confirm on X, trigger on Y" framework. What is explicit:

- **Always start on the daily chart** to read "the general tone of the
  market" before looking at anything shorter — described as a deliberate
  discipline against jumping straight to the 5/15-minute chart.
- The **same MA-stack logic (50/100/200) is applied identically on the
  hourly** for day trading — it's the same rule re-applied on a faster
  clock, not a different rule.
- No explicit rule for "timeframe A confirms, timeframe B triggers" beyond
  that daily-first habit. If your actual practice uses a real
  higher-timeframe-confirms / lower-timeframe-triggers structure, that's
  either from the two missing videos or something you built on top of this
  later.

---

## 3. What's genuinely new vs. already tested and dead in LENS

LENS's `research/edge_miner.py` already mined `rsi_zone` (dip/neutral/
momentum via RSI bands), `slope_1h` (EMA21 1h slope, i.e. a single-MA trend
filter), `vol` (ATR regime), `ext_4h` (distance from 4H EMA21),
`trend_aligned`, `bar_aligned`, `session`, `weekday`, `streak` — combinations
of these across 1–3 conditions, and a much broader 20k-permutation search
elsewhere found **zero robust survivors**. The one edge that did survive
permutation testing lifetime was non-VETO shorts at R:R 1 — not a generic
indicator combo.

So: **a single RSI zone, and a single EMA slope, are already tried and
dead.** What is genuinely untested in LENS:

- **RSI/MACD divergence specifically** — price vs. oscillator disagreement,
  not just an RSI level or a MACD cross. This playlist doesn't define it
  (see Gaps), so it needs your own definition before it can be built.
- **The real 50/100/200 MA STACK as a joint condition** — not one EMA slope,
  but "price above 50 AND 50 above 100 AND 100 above 200" (or the inverse)
  as a single trend-regime filter, exactly as taught.
- **Bollinger squeeze + wedge as a joint setup** — band-width contraction
  paired with a converging price wedge, tested as one condition, not as
  two separate ones.
- **Chart pattern detection** — engulfing candles, hammers, wedges. None of
  this exists as computed logic anywhere in the codebase yet.
- **Fibonacci retracement zones** as entry/exit levels off a defined swing.
- **The 9-day-MA partial-exit rule** — this one is structurally different
  from anything in LENS: it's an *exit/scaling* rule, not an entry filter,
  and LENS's discipline model currently has no such staged-exit concept.

---

## 4. Gaps

- **#17 (RSI) and #19 (MACD) have no transcript anywhere** — YouTube has no
  auto-captions and none were ever manually added, and these are the two
  most directly relevant to what you described (oscillation, divergence,
  MACD/RSI as your main tools). Everything above about RSI and MACD comes
  from one passing mention in the day-trading video, not from either
  dedicated lesson.
- **Recommendation:** give me 3–5 sentences on your actual RSI/MACD rules —
  specifically the divergence setup (bullish/bearish, regular/hidden?,
  which timeframe, confirmed by what) and any specific thresholds you use
  (RSI 30/70? something else?). That closes the one real hole in this
  document, and it's the piece that isn't recoverable from the source
  material at all.

---

## 5. Recommended next step

Don't build the chart overlay or the divergence detector yet — define
divergence precisely first (from your manual notes above), then add it as
ONE new feature to `edge_miner.py`'s `FEATURES` dict (e.g.
`rsi_divergence: [None, "bullish", "bearish"]`) and the 50/100/200 stack as
another (`ma_stack: ["bull", "bear", "mixed"]`), and run them through the
**same gates already built and proven** — `research/perm_test.py` /
`research/filter_significance.py`'s permutation-bootstrap, split-half, and
the Bonferroni correction used in `research/override_miner.py`. If either
survives on your real trade history, *then* it earns a visual overlay on
the journal chart and a place in the scanner. Build the visual last, not
first — the codebase's whole track record this year is generic indicator
ideas looking convincing and then failing that gate.
