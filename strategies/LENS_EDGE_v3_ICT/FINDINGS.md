# LENS_EDGE_v3 — Your trading, translated into ICT / visual language

> **STATUS — 2026-07-01: framework research is DONE. This is an execution problem now, not a build problem.**
> ICT / SMC / "smart money" / TFS-style frameworks are already fully mined and
> codified here (S1–S5 + 7 vetoes) and in `app/setups.py`. The mechanical SMC
> strategies (`SMC_LUX_4R_v1`, `SMC_SWEEP_v1`) were tested and retired. **Do not
> rebuild this** when a new framework shows up on Twitter — diff it against the
> setups/vetoes below; it will almost always be a reskin of what's already here.
> Key personal finding that overrides textbook ICT: **you are a continuation
> trader, not a reversal trader** — trade *with* the sweep (50% WR), never fade
> it (33% WR), and never enter inside an FVG retrace (38% WR). The remaining work
> is sticking to the checklist, not adding to it.

> Mined with `ict_miner.py` from 464 closed real trades (Apr 2025 – Jun 2026,
> baseline 41.8% WR, €+736) plus all 580 mechanical flush-short occurrences in
> the same window. Same robustness bar as v2: every rule below survived
> (a) dropping its 2 biggest wins and (b) old-half vs new-half WR ≥ 45%.

## The headline: you are a CONTINUATION trader, not a reversal trader

The single most important ICT finding, across all 464 trades:

| Liquidity context at entry | n | WR | exp/trade |
|---|---|---|---|
| **Sweep continuation** (trade *with* the raid) | 121 | **50%** | **€+15.4** |
| No recent sweep | 261 | 41% | €−4.4 |
| **Sweep reversal** (fade the raid — classic ICT) | 82 | **33%** | €+0.2 |

Textbook ICT says short the buyside sweep. **Your account says the opposite**:
when you fade a liquidity raid you win 1 in 3. When you trade in the raid's
direction you're at 50% with your best expectancy. Same story at prior-day
levels: raid-continuation 45% WR €+10.9 vs raid-reversal 37% WR €−6.7.
Displacement confirms it: entering *with* a displacement candle = 55% WR
(€+13.4); *against* it = 35% (€−6.5). Your edge lives in momentum, full stop.

## Named setups (robust, ranked)

### S1 — NY AM Killzone Flush Short ★ your best trade
**Short · RSI(14) < 40 · 13:00–16:00 UTC**
77.3% WR, n=22, €+21.14/trade, €+465 total.
This is v2's flush short sharpened: it isn't "NY session" (13–21), it's the
**NY AM killzone specifically**. Part B confirms you already sense this: you
took flushes in the NY AM killzone at 2× the rate you took them elsewhere
(31% of your entries vs 15% of skipped occurrences).
Exit like you actually do: +0.5–0.9%, not a 3.5% target.

### S2 — Premium Displacement Short
**Short in the premium of the 7-day range (price > 55% of dealing range) ·
after a displacement candle (range > 1.5× ATR14) in your direction · no FVG
retrace entry**
65–67% WR, n=21–23, **€+34–38/trade — your biggest expectancy** (€+790).
ICT-correct location (sell premium) but momentum-style trigger: you short the
break *down* from premium, you don't limit-fade into it.

### S3 — Continuation Long on Momentum
**Long · RSI(14) > 55 · recent sweep in trade direction · not entering inside
an FVG**
62.5% WR, n=40, €+22.87/trade (€+915 — biggest total PnL rule).
The long mirror of your edge: buy strength after buyside liquidity goes,
don't wait for the retrace.

### S4 — Discount Dip Long (quiet context)
**Long · RSI(14) < 40 · price in discount of 7-day range · no recent sweep**
62.1% WR, n=29, €+18.81/trade (€+546).
The one mean-reversion shape that works for you — but only in *discount* and
only when no liquidity raid is in play (no one to fade).

### S5 — London Momentum (from v2, now located)
**RSI > 55 · 07:00–10:00 UTC London killzone · no FVG entry**
63.6% WR, n=22, €+25.45/trade. v2 flagged this as weak; with the
killzone + no-FVG framing it now clears robustness.

## Hard vetoes — your visual anti-checklist

These are where your €−2,400+ of bleed lives. Skip the trade if ANY is true:

1. **Fading a sweep** (sweep-reversal context): 33% WR. You are not a
   turtle-soup trader. If liquidity just got raided, trade with it or stand down.
2. **Entering inside an FVG retrace**: 38% WR, €−15/trade. The "wait for the
   gap fill" entry doesn't work for you — by the time price retraces, your
   momentum is gone.
3. **Fading a prior-day high/low raid**: 37% WR, €−6.7/trade.
4. **RSI 40–55 neutral zone** (v2, still holds): 34.7% WR, €−1,243.
5. **1h EMA21 slope against you** (v2, still holds): 38.1% WR, €−1,177.
6. **Displacement candle against your direction**: 35% WR.
7. **NY PM killzone (18–21 UTC)**: 39% WR, €−11.1/trade — your worst window.

## ⚠️ Honest mechanical section (the v2 lesson, re-checked)

Every flush occurrence was first-touch tested at your *real* exit geometry
(0.63% SL / 0.95% TP — breakeven 42.4% maker / 58.9% taker):

- ALL 580 occurrences: 41.9% WR — coin flip, as v2 found.
- Occurrences **you took**: 44.8% first-touch — yet your realized WR on them
  was 60%. **The gap is your exits**, again: you bank +0.5–0.9% before the
  mechanical TP/SL race resolves.
- No single ICT filter turns the mechanical entry profitable. Best was
  pd_raid=none at 45.2% (barely clears maker breakeven, both halves) —
  not tradeable on its own, and *nothing* clears taker fees.

So, same conclusion as v2 but now with the discriminator partly found:
**S1–S5 are entry checklists for your discretionary trading, not bot
signals.** The mechanical residual (what you see that the features still
don't capture) remains real — your taken flushes beat skipped ones even
first-touch (44.8% vs 41.9%), and within NY AM killzone your selection
turned a 35.1% mechanical context into 77% realized.

## Addendum (2026-06-12): NONE bucket + timeframe, from first principles

**The NONE bucket is not a hidden setup.** 88 untagged trades show €+1,169 —
but one short (2026-02-24, +€1,283) plus the next 4 winners account for
+€1,905 of it. Remove those 5 and NONE is 83 trades, 36% WR, **−€736** — the
same outlier artifact v2 caught in the Tuesday-shorts rule. Verdict: trades
outside S1–S5 lose as a class. If you take one anyway, you MUST write what
you saw in the notes — that's the only way an S6 ever gets discovered.

**Your timeframe, settled by your own fills** (hold-time × outcome):

| Hold | n | WR | PnL |
|---|---|---|---|
| < 30min | 100 | 34% | €−357 |
| 30m–2h | 143 | 35% | €−390 |
| **2h–8h** | **144** | **50%** | **€+1,552** |
| 8h–24h | 61 | 46% | €−299 |
| > 1day | 16 | 62% | €+230 |

You are a **1H-context trader whose winners resolve in 2–8 hours**. The 243
sub-2h trades (more than half of everything) are collectively −€747 — that's
the panic-scalp/revenge zone, not an edge. Nothing in the data supports 1m/5m
trading; 15m is at most an entry-timing lens, never a signal source. The 4H
belongs only to the separate (still unproven) TREND_4R thesis.

This refines the exit rule: take +0.5–0.9% **when the move gives it to you
within hours** — but a trade that needs 5 minutes to judge was a bad entry,
not a good exit.

## Operational next steps

1. **Tag every new trade** with its setup (`setup_tag` column already exists
   in lens.db, currently 0/465 filled): `S1`–`S5`, or `NONE` if it matches no
   setup. Three months of tags = ground truth v4 can mine.
2. At entry, the checklist is 6 questions: direction-with-momentum? sweep
   with you (not faded)? displacement with you? right killzone? RSI out of
   40–55? slope with you?
3. Exits: keep doing what you do on scalps (+0.5–0.9%). The 3.5% TP belongs
   only to the separate 4H trend thesis.
