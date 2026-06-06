# TREND_4R_v1 — Baseline (TBD)

*Run TradingView's Strategy Tester and fill this in. This is the experiment that
decides whether the whole compounding plan is real or a fantasy.*

## The question this strategy exists to answer

> Does a 4H entry signal reach **+4%** (4R) before getting wicked out at **−1%**,
> and what is the **real win rate** at that tight a stop?

The 44% WR in the PRISM history came from trades at **wider** stops. A 1% stop on
4H BTC is tight — it gets hit by normal noise. So the honest prior is: **win rate
will be lower than 44% here.** This backtest tells us by how much, and whether
what's left still clears breakeven.

**Breakeven WR at 4R:** `1 / (1 + 4) = 20%`. Below 20% WR, the system loses money
no matter the leverage. That's the bar to clear. (The plan's 44% is the *hope*,
20% is *survival*.)

## Strategy summary

- **Timeframe:** 4H (the locked TF — do not test this on 5m/15m; scalping was rejected)
- **Direction:** with-trend only. Long when `close > EMA20 > EMA50` + MACD hist rising;
  short when `close < EMA20 < EMA50` + MACD hist falling. Counter-trend excluded.
- **Structure:** require close beyond the 20-bar high/low (toggle `requireBreak`)
- **Stop:** FIXED 1.0% price move
- **Target:** FIXED 4.0% price move (= 4R)
- **Leverage input:** 10x — drives the equity curve so max DD / ruin read true
- **Discipline:** skip Saturday, ≤1 trade per UTC day

## Test setup

- **Symbol:** BTCUSD perp on Kraken (or BTCUSDT.P) — tag `venue=kraken`
- **Timeframe:** 4H
- **Range:** last 12 months minimum (needs both trend and chop regimes)
- **Commission:** 0.15%/side = **0.30% round trip**, slippage 2 ticks (already set in the script)
- **Initial capital:** $360 (matches the real starting base)

⚠️ **Funding cost is NOT modelled by the Strategy Tester.** A 1–3 day perp hold
pays funding (~the 1.5% you flagged). Mentally haircut the result, or subtract
funding when the real fills land in PRISM Core.

## Baseline results

| Metric | Value | Read |
|---|---|---|
| Total trades (n) | 32 | want ≥ 40 for any confidence |
| **Win rate %** | 18.8% | **the headline — is it anywhere near 44%, or nearer 20%?** |
| **Avg R (avg win % ÷ avg loss %)** | 3.7 | should sit near 4.0 if exits are clean; <4 means TP rarely reached |
| Profit factor | 0.33 | want > 2.0 (the plan's target); > 1.0 is the floor |
| Net profit | -296.0 EUR | ignore the raw number — leverage inflates it |
| **Max drawdown %** | -91.2% | **the ruin read — at 10x this is where blow-up shows** |
| Max consecutive losses | 14 | 7 in a row ≈ −50% account at 10x/1% |
| Avg bars in trade | 6.8 (27h) | ×4h = hold time; confirms it's a 1–3 day swing not a scalp |
| Trades/week | | want 2–3; the plan assumes ~1/day max |

## How to read the outcome

- **WR ≥ ~35% AND avg-R ≥ 3:** the premise holds — proceed to forward-test and
  wire up Notify. This is the green light.
- **WR 20–35%:** marginal. The 1% stop is bleeding you on noise. Try: widen stop
  to 1.5–2% (drop leverage to keep 10% account risk), or require volume + a
  cleaner break to cut low-quality entries.
- **WR < 20% OR PF < 1:** the entry premise does **not** survive a 1% stop. This is
  the most important thing to learn and it's better learnt here than with money.
  The fix is entry quality (the ICT / order-flow ideas), not leverage.

## What to tune if results disappoint

1. **WR too low (getting wicked):** the stop is too tight for the entry. Widen it
   and re-derive leverage so account risk stays 10% — this is the 4x/5x-at-2%
   conversation made concrete.
2. **Avg R well below 4:** price rarely travels 4% before reversing on 4H within a
   few days → 4R may be the wrong target for this TF; test 2.5–3R.
3. **Too few trades:** drop `requireBreak`, or loosen the trend filter to `close`
   vs one EMA.
4. **Equity curve explodes then craters:** that's the 10x ruin signature — note
   the max DD and feed the real WR/R into a Monte Carlo before trusting it.

## Schema validation (before any live alert)

- [ ] Alert fires once per closed 4H bar
- [ ] Alert message is valid JSON
- [ ] JSON parses into `SignalIngest` (curl against `/api/signals` → 201)
- [ ] `expected_rr` ≈ 4.0, `suggested_leverage` = 10, `suggested_size_pct` = 10
- [ ] `direction` matches the trend filter (never counter-trend)
