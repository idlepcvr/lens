# MOM_BREAK_v1 — Baseline (TBD)

*Fill this in after running TradingView's Strategy Tester.*

## Strategy summary

Consolidation-break scalp built from PRISM fingerprint findings (see `strategies/_research/prism_fingerprint.md`).

- **Entry TF:** 5m or 15m (test both)
- **HTF bias:** 1h EMA(200), can be required or context-only
- **Long:** close > highest(high[1], 15) AND volume > sma(volume, 20) × 1.5 AND HTF aligned (if required)
- **Short:** opposite
- **Stop:** entry ± 1.0 × ATR(14) — tighter than MACD_MTF_v1 because this is a scalp
- **Target:** 1.5R — modest, suits scalp hold targets
- **Built-in discipline (matches `app/discipline.py`):**
  - Skip Saturday
  - Skip 02:00 and 11:00 UTC (the only bleed hours stable across 2024/25/26 in PRISM)
  - Only fire 07:00–21:00 UTC (active sessions)
  - 5-min cooldown after each signal
- **Suggested size scales with confluence:**
  - ≥4 confluence: 10× leverage, 4% account
  - 3 confluence: 5× leverage, 2.5%
  - ≤2: 3× leverage, 1.5%

## Test setup
- **Symbol:** BTCUSDT.P (Bybit perp, but tag venue=kraken in inputs)
- **Range:** Last 6 months
- **Commission:** 0.05% per side, slippage 2 ticks
- **Initial capital:** $1000
- **Test on both 5m and 15m**, compare WR / PF / avg hold duration

## Baseline results

| Metric | 5m | 15m |
|---|---|---|
| Total trades (n) | | |
| Win rate % | | |
| Profit factor | | |
| Net profit | | |
| Max drawdown % | | |
| Avg win % | | |
| Avg loss % | | |
| Avg bars in trade | | |
| Trades/week | | |
| Max consecutive losses | | |

## What "good" looks like (based on PRISM benchmarks)

- PF ≥ 1.4 — beats the discipline-filtered PRISM bulk (PF 1.46 at notional ≥ 5×)
- WR ≥ 45% — at 1.5R, breakeven WR = 40%
- Trades/week 5–15 — sustainable, not over-trading
- Max DD ≤ 25% — survivable
- No 10+ consecutive losses

## What to tune if results disappoint

1. **PF < 1**: entry premise has no edge — try a different trigger (S/R bounce, FVG, OBR)
2. **WR > 45% but PF < 1.4**: target too tight — try rrTarget = 2.0 or 2.5
3. **Too few trades**: lower volMult to 1.2, or drop requireBias
4. **Too many trades**: raise volMult to 2.0, narrow session window
5. **Saturday/bleed-hour signals slip through**: check Pine date/time settings match exchange UTC

## Schema validation
- [ ] Alert fires once per closed bar
- [ ] Alert message is valid JSON
- [ ] JSON parses into `SignalIngest` (curl test against `/api/signals`)
- [ ] All 4 confluence factors flow through `mtf_confluence` array
- [ ] `suggested_leverage` reflects confluence tier
