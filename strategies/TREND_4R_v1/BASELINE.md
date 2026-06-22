# TREND_4R_v1 — Baseline ❌ KILLED (2026-06-22)

*This was the experiment that decides whether the whole compounding plan is real
or a fantasy. **Verdict: fantasy.** The data is in (two independent runs below),
the entry premise does not survive a 1% stop, and this track is retired.*

## VERDICT — retired 2026-06-22

> **20.9% win rate over 182 trades — below the 26% fee-adjusted breakeven.**
> Profit factor 0.75, max drawdown 100% (account → $0.20), 16 losses in a row.
> A 1% stop on 4H BTC gets wicked out by normal noise exactly as the honest prior
> below predicted. The 44–48% WR the compounding plan assumed does not exist at
> this geometry. **Do not trade this. Do not lift leverage to "fix" it — the
> problem is entry quality (WR), not sizing.** The surviving edges are the HEDGE
> S1–S5 discretionary contexts and the PROP `ASIAN_RSI_DIP_v1` grind, not this.

### Engine backtest — 2026-06-22 (the confirming run, n=182)

`app.backtest_engine run_strategy('TREND_4R_v1', months=30)` over 30 months of
4H BTC, fee-honest:

| Metric | Value | Read |
|---|---|---|
| Total trades (n) | 182 | 5.7× the TV sample — confidence is high |
| **Win rate %** | **20.9%** (38W / 144L) | confirms the 18.8% below; nowhere near 44% |
| Breakeven WR @4R (after fees) | 26.0% | **WR sits BELOW breakeven → structurally negative** |
| Avg R (per win) | 2.85 | <4 — TP rarely reached before reversal |
| Profit factor | 0.75 | < 1.0 floor: loses €0.25 per €1 risked |
| **Max drawdown %** | **100%** ($637 → $0.20) | total ruin at the locked 10x |
| Max consecutive losses | 16 | the kill streak |
| Avg hold | 24.4h | a 1–3 day swing, not a scalp (as expected) |
| Trades/week | 1.4 | as planned — cadence was never the problem |

Both samples agree: ~19–21% WR, PF < 1, account to zero. The premise is dead.

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

## Baseline results — earlier TradingView run (n=32, smaller sample, same conclusion)

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
