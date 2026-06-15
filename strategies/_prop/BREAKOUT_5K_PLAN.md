# Breakout 1-Step Classic — $5k eval plan

*A SEPARATE track from the hedge-fund LENS thesis. Different objective: survive
hard equity walls to a modest target, not maximise compounding. Built/validated
2026-06-15 with `app/prop_eval.py`.*

## Why a separate system

The locked LENS thesis (risk 10%/trade for 40%, 1% stop @ 10x) is **suicide on a
prop eval**: one full stop = −10% of account, which breaches Breakout's 3% daily
AND 6% total walls in a single fill. Proven below — `TREND_4R_v1` passes the eval
only 19.6% of the time. Hedge-fund optimum ≠ prop optimum.

## The firm rules (Breakout 1-Step Classic, verified 3 sources)

| Rule | Value |
|---|---|
| Max drawdown | 6% **static**, locked to start → $5k floor = **$4,700**, fixed |
| Daily loss | 3% off prior day's close → **$150/day** |
| Profit target | 10% → **$5,500** to pass |
| Leverage cap | 5x (BTC/ETH perps) |
| Daily reset | 00:30 UTC |
| Time limit | none known — CONFIRM in dashboard |

Two kill conditions, both live: touch $4,700 ever, OR lose $150 in one day.

## The LOCKED config (decided 2026-06-15)

> **Strategy: `ASIAN_RSI_DIP_v1`** — RSI back-above-40 in Asian session, **4H chart,
> killzone bars 00:00+04:00 UTC only**, 4H+daily trend gate. 1% stop / 4% TP (4R).
>
> - **Eval phase (pass it): 2% risk/trade (2x lev) → ~70% pass in ~2 months.**
> - **Funded phase (earn): drop to 1% risk (1x lev) for survival.**

Same strategy on $5k and $200k — rules are %-based, so **odds are identical at any
account size.** Pass the cheap $5k first, then buy the biggest eval direct (don't
ladder).

### Why 2% to pass (the speed/probability frontier)

Exhaustive sweep (25 strategies × 5 risk levels, `prop_eval.py sweep`):

| Pass within | Best pass% | Config |
|---|---|---|
| 1 month | 45% | ASIAN_PULLBACK_v1 @2% — coin flip, reject |
| **2 months** | **70%** | **ASIAN_RSI_DIP_v1 @2% — the play** |
| 6 months | 76% | ASIAN_RSI_DIP_v1 @1.5% |
| 9 months | 91% | ASIAN_RSI_DIP_v1 @0.75% |

+10% in a month while dodging −6% needs an edge BTC mean-reversion doesn't have.
Evals are cheap (~$20), so **expected time favours 2%**: ~70% × 2mo + retries ≈
**~3 months & ~$29 to funded**. The 9-month / 0.75% plan only saves ~$7 in fees.

### The pass/fail mechanic (2% risk, $5k)

WR 40% · WIN = **+7.4% / +$370** · LOSS = **−2.6% / −$130** · floor **$4,700** ·
target **$5,500** · ~1.5 trades/mo (~3 trades in 2mo).

- Loss path: 5000 → 4870 → 4743 → **4620 ❌** (3rd loss busts)
- Win path: 5000 → 5370 → **5767 ✅** (2 wins clears)
- **You only fail on a cold 3-loss start (~0.6³ ≈ 22%).** One win → static-floor
  cushion absorbs ~5 losses → cruise home. That's why ~70%.

### Funded income (after split, ~1.5 trades/mo)

Per-win ≠ income. Expectancy = 40%(+7.4%) + 60%(−2.6%) = **+1.4%/trade**.

| Account | Per win (7.4%, 80%) | ~Monthly @2% | ~Monthly @1% safe |
|---|---|---|---|
| $100k | $5,920 | ~$1,680 | ~$840 |
| $200k | $11,840 | **~$3,360** | ~$1,680 |

Income is **lumpy** (a $200k month ≈ −$8k to +$26k, avg +$3.4k). The lever for
more is **WR & R** (the LENS discretionary edge ~60% vs 40% mechanical), not size.

### Stacking REJECTED (sim disproved it)

Hypothesis was: trade ASIAN_RSI_DIP_v1 + ASIAN_PULLBACK strategies together for
more trades/month → faster eval. Portfolio search (`prop_eval.py search`) killed
it: stacking triples frequency (eval in <1mo) but **craters pass to 46–72%** —
the pullback strategies are lower-WR, so mixing dilutes quality and hits the 6%
wall more. **For an eval, trade quality > quantity.** No stacked basket clears 90%.
Solo ASIAN_RSI_DIP_v1 is the only config that does. Lesson logged.

Monte Carlo (5k bootstrapped paths, 30mo BTC history):

| Risk/trade | Pass% | Fail-DD% | Fail-Daily% |
|---|---|---|---|
| **0.5%** | **97.4** | 2.6 | 0 |
| 0.75% | 91.6 | 8.4 | 0 |
| 1.0% | 84.7 | 15.3 | 0 |
| 1.5% | 75.4 | 24.6 | 0 |

Lower risk = more losses absorbed before the 6% wall = higher pass. The daily
limit never binds (once-per-day, ~1% moves); the 6% total is the only real killer.

## Full strategy ranking @ 1% risk (why this one)

ASIAN_RSI_DIP_v1 84.6 · ASIAN_PULLBACK_v2 56.2 · ASIAN_PULLBACK_v1 52.5 ·
PULLBACK_6R 34.7 · RSI_DIP 29.1 · ... · TREND_4R 19.6 · MACD_CROSS 13.8 ·
LIVE_SCALP 8.9 (dies on daily limit: multi-trade/day at 1.6x). High-WR,
short-loss-streak strategies win the eval; high-expectancy compounders lose it.

## Honest caveats (read before paying the $20)

1. **Thin sample.** ASIAN_RSI_DIP_v1 = only **44 trades in 30 months** (~1.5/mo).
   Shape is trustworthy (high WR, short streaks); exact 97% is not gospel.
2. **Closed-trade approximation.** The sim checks walls on closed PnL. Breakout
   checks **equity incl. open trades** — real eval is slightly harsher on
   intra-trade drawdown. Treat pass-rates as optimistic by a few points.
3. **Regime assumption.** Bootstrap assumes future BTC ≈ 30mo history. Regime
   shift breaks it.
4. **Fees assumed 0.15%/side.** Confirm Breakout's actual schedule.
5. **Patience.** ~1.5 trades/mo → eval takes months. Fine IF no time limit.

## Next steps

- [ ] Confirm Breakout: time limit? exact fees? min trading days?
- [ ] Forward-test ASIAN_RSI_DIP_v1 @ 0.5% on Breakout demo/paper before paying
- [ ] Add open-equity (intra-trade) drawdown to `prop_eval.py` for a harsher,
      truer sim
- [ ] Only then pay the $20 1-Step Classic eval
