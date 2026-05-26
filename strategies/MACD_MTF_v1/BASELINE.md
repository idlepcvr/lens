# MACD_MTF_v1 — Baseline

*Per LENS_PLAN.md Week 2 deliverable. Fill this in after running TradingView's Strategy Tester.*

## Strategy summary
- **Entry TF:** 15m
- **HTF bias:** 1h MACD direction
- **Long:** MACD line crosses above signal AND HTF MACD > HTF signal
- **Short:** MACD line crosses below signal AND HTF MACD < HTF signal
- **Stop:** entry ± 1.5 × ATR(14)
- **Target:** 3R from entry
- **Position:** 10% of equity per trade (Strategy Tester default — replaced live by `compute_position()`)

## Test setup
- **Symbol:** BTCUSDT.P (Bybit perp) — use Binance `BTCUSDT.P` ticker in TradingView for richer history
- **Range:** 6 months from today (2025-11-26 → 2026-05-26)
- **Commission:** 0.05% per side, slippage 2 ticks (matches Bybit taker)
- **Initial capital:** $1000

## Baseline results (fill in after Strategy Tester run)

| Metric | Value |
|---|---|
| Total trades (n) | |
| Win rate % | |
| Profit factor | |
| Net profit % | |
| Max drawdown % | |
| Sharpe ratio | |
| Avg trade % | |
| Avg bars in trade | |

## Schema validation
- [ ] Alert fires once per closed bar on entry signal
- [ ] Alert message is valid JSON
- [ ] JSON parses into `SignalIngest` (verify with `curl` against `/api/signals`)
- [ ] All locked-schema fields present (signal_id, strategy_name, strategy_version, symbol, trigger_type, direction, entry_price, stop_price, target_price)

## Notes / open questions

*Things worth changing in v1.0.1+ — leave for Week 8 retro.*

-
