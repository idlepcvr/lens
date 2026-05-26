# MACD_MTF_v1 — Baseline ⚠ DEPRECATED

**Result: no edge. Kept as a negative-baseline reference. Do not trade.**

Replacement strategy is being reverse-engineered from PRISM v0.1 fill history (see `strategies/<next>/`). MACD-cross + HTF alignment confirmed unsuitable for 15m BTC; ATR×1.5 stop too tight; no regime filter.

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

## Baseline results (Strategy Tester, 2026-05-26)

| Metric | Value |
|---|---|
| Total trades (n) | 1,151 |
| Win rate % | **14.9%** |
| Profit factor | **0.11** |
| Net profit | **−€946** on €1000 |
| Max drawdown % | **94.7%** |
| Avg win % | 0.22 |
| Avg loss % | −0.41 |
| Trades/week | 29.3 (target: 14) |
| Max consecutive losses | 44 |
| Symbol | BYBIT BTCUSD.P |
| Range | 2025-05-25 → 2026-02-24 |

## Schema validation
- [ ] Alert fires once per closed bar on entry signal
- [ ] Alert message is valid JSON
- [ ] JSON parses into `SignalIngest` (verify with `curl` against `/api/signals`)
- [ ] All locked-schema fields present (signal_id, strategy_name, strategy_version, symbol, trigger_type, direction, entry_price, stop_price, target_price)

## Notes / open questions

*Things worth changing in v1.0.1+ — leave for Week 8 retro.*

-
