# PULLBACK_4R_v1 — Baseline

## Why this strategy exists

TREND_4R_v1 tested breakout entries (close above 20-bar high) and got 18.8% WR —
below the 20% theoretical breakeven, and well below the 31% real-fee breakeven.

Root cause: breakout entries enter at resistance AFTER the move. The stop at −1%
gets hit by the pullback that often follows a breakout.

PRISM fingerprint (2,315 trades) shows a real edge exists at 53.2% WR when
filtered to Kraken / conviction size / no Saturday / hold ≥ 60 min.
Those were pullback trades, not breakouts. This strategy encodes that.

## Entry logic

**EMA21 Touch & Go** — 4H timeframe

1. Daily EMA50 confirms the macro trend (gate filter)
2. 4H EMA21 > EMA50 (trend aligned on entry TF)
3. Previous 4H bar's LOW touched or pierced EMA21 (price dipped to support)
4. Current 4H bar CLOSES above EMA21 (confirmed bounce)
5. MACD histogram rising (momentum confirming the bounce)
6. Discipline: no Saturday, cooldown ≥ 4 bars, max 1 trade/day

**Why better than breakout:**
- Entering at support not resistance → stop has context
- Price has already proven it won't close below EMA21
- The 4% target has room ahead of it, not a "now what" after a spike

## Locked parameters

| Parameter | Value | Why |
|---|---|---|
| Stop | 1.0% | 10% account risk at 10x |
| Target | 4.0% | 40% account gain = 4R |
| Leverage | 10x | fixed in PRISM system |
| Fee | 0.15%/side | Kraken taker rate |

After fees: win = +37% account, loss = −13% account.
Breakeven WR (after fees) = ~31%.
Goal WR = 48% (hits €375k by Oct 1 from €637 at 5 trades/week).
PRISM conviction WR = 53% → 5pp margin.

## Test setup

- **Symbol:** PF_XBTUSD on Kraken — or BTCUSDT.P for longer history
- **Timeframe:** 4H
- **Range:** 24 months minimum (must include 2024 bull, 2024 chop, 2025 bear)
- **Commission:** 0.15% per side (already coded)
- **Initial capital:** 637 (real current balance in EUR)

## What to look for

| Metric | Target | Below this → |
|---|---|---|
| Win rate | ≥ 48% | Not enough edge for goal |
| Profit factor | ≥ 1.5 | Review entry filter tightness |
| Avg bars in trade | ≥ 6 (24h) | Confirms multi-day hold nature |
| Max DD % | < 60% | Ruin risk too high at 10x |
| Trades/week | 1–5 | More = overfit, fewer = fine |

## Variants to test (in order)

1. **v1 base**: daily EMA50 filter + MACD + no volume req
2. **v1 no-htf**: disable daily filter (more signals, lower selectivity)
3. **v1 vol**: enable volume spike requirement
4. **v1 shorts-only** / **v1 longs-only**: check directional bias

## Comparison target

TREND_4R_v1 baseline: 18.8% WR, PF 0.33, n=32
PULLBACK_4R_v1 needs: ≥ 48% WR, PF ≥ 1.5 to validate the plan.

## Schema validation (before going live)

- [ ] Alert JSON fires once per closed 4H bar (not on every tick)
- [ ] `signal_id` is unique per signal
- [ ] `direction` matches the actual trade direction
- [ ] `stop_price` / `target_price` match what the strategy executes at
- [ ] Paste one alert message into LENS `/api/signals` and confirm it ingests
