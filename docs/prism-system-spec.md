# PRISM Trading System — Architecture Specification

[Open as HTML](prism-system-spec.html)

## Overview

PRISM is a modular crypto trading system with four distinct components. Each component has a single responsibility and communicates through defined interfaces. This document is the source of truth for any developer or AI agent building on this system.

**Owner:** Lucky (solo trader, US LLC Wyoming structure)
**Market:** BTC perpetual futures (Kraken)
**Repository:** github.com/idlepcvr/prism

---

## System Components

### 1. PRISM Core — Trade Logger & Portfolio Engine
**Language:** Python (FastAPI) + Supabase
**Status:** Partially built
**Responsibility:** Logs real trades, tracks balances, calculates position sizing, shows per-setup expectancy on real fills.

**What it does:**
- Cross-venue balance aggregation
- Real fill logging with `setup_type` tag
- ATR-adaptive position sizing (Kelly Criterion)
- Equity curve vs balance separation
- Goal calculator (milestone tracking: 1 BTC → 50 BTC → 150 BTC)
- Manual edit lock for trade journal integrity

**What it does NOT do:**
- Signal detection (that's Lens)
- Chart rendering (that's TradingView)
- Alerting (that's Notify)

**Key data model:**
```
Trade {
  id, timestamp, exchange, pair,
  side (long/short), entry_price, exit_price,
  stop_loss, take_profit, leverage,
  position_size_usd, position_size_btc,
  setup_type (string — maps to Lens signal name),
  r_multiple (actual), pnl_usd, pnl_pct,
  fees, funding_cost, hold_duration,
  outcome (win/loss/breakeven)
}
```

---

### 2. Lens — Signal Detection Engine
**Language:** Pine Script (TradingView) for indicators + Python for backtesting
**Status:** Not yet built
**Responsibility:** Detects trade setups on the 4H timeframe, calculates entry/SL/TP, fires alerts.

**Trading Parameters (locked):**
- Timeframe: 4H candles
- Leverage: 10x (Kraken Perpetual)
- Stop Loss: 1% price move from entry
- Take Profit: 4% price move from entry (4R)
- Account risk per trade: 10%
- Account gain per trade: 40%
- Frequency: 1 trade per day maximum
- Hold time: 1-3 days typical

**Trailing Stop Rules (for future automation):**
| Price hits | Trail stop to | Locked in |
|------------|---------------|-----------|
| 1R (1%) | Entry (breakeven) | 0% |
| 2R (2%) | 1R below entry | +10% |
| 3R (3%) | 2R below entry | +20% |
| 4R (4%) | CLOSE | +40% |

**Entry Signal Logic (v1 — to be backtested and refined):**
- Trend: Price below 20 EMA AND 50 EMA on 4H (for shorts; inverse for longs)
- Momentum: MACD histogram declining (shorts) or rising (longs)
- Structure: Break of previous support/resistance level
- Confirmation: Volume spike on breakout candle
- ICT concepts (future): Order blocks, fair value gaps, liquidity sweeps

**Pine Script Indicator Output:**
- Visual: Entry arrow, SL line (red), TP line (green) drawn on chart
- Alert message format:
```
PRISM Signal: SHORT BTC
Entry: $71,100
SL: $71,811 (+1.0%)
TP: $68,256 (-4.0%)
Leverage: 10x
Risk: 10% account
R:R: 1:4
Setup: MA_MACD_Break_v1
```

**Pine Script Strategy Output (backtesting):**
- Same logic as indicator but with `strategy.entry()` and `strategy.exit()` calls
- Reports: win rate, average R, profit factor, max drawdown, equity curve
- Validation target: 44%+ WR at 4R = profit factor > 2.0

**Python Backtester (optional, for Monte Carlo):**
- Reads TradingView strategy export CSV
- Runs Monte Carlo simulation (5000 iterations)
- Reports: median outcome, P10/P90, ruin probability at 50% drawdown
- Uses actual win rate and R from backtest, not assumptions

---

### 3. Dashboard — Visual Interface
**Language:** React (Next.js) or vanilla SPA
**Status:** Vanilla HTML SPA exists in PRISM repo
**Responsibility:** Single screen to see everything — current position, recent trades, performance metrics, next signal.

**Views:**
1. **Active Position** — current trade with live P&L, SL/TP levels, time in trade
2. **Trade Journal** — list of all trades with setup_type, R multiple, outcome
3. **Performance Metrics:**
   - Win rate (overall and per setup_type)
   - Average R (overall and per setup_type)
   - Profit factor
   - Current streak (wins/losses)
   - Account equity curve
   - Milestone progress (current balance vs 1 BTC / 50 BTC / 150 BTC targets)
4. **Weekly Summary:**
   - Trades taken, wins, losses
   - Account change (€ and %)
   - Expected vs actual doubling time
   - Week-over-week comparison

**Does NOT need:**
- Chart rendering (use TradingView for that)
- Signal detection (that's Lens on TradingView)
- Complex analytics beyond what's listed above

---

### 4. Notify — Alert Pipeline
**Language:** Python (or shell script)
**Status:** ntfy already self-hosted on homelab (fox)
**Responsibility:** Receives TradingView webhook alerts, formats them, pushes to phone.

**Flow:**
```
TradingView Alert (webhook)
    → Notify endpoint on fox (via Cloudflare Tunnel)
    → Parse alert message
    → Push to ntfy topic (phone notification)
    → Log alert in Supabase (for correlation with actual trades)
```

**Alert types:**
- `SIGNAL` — new trade setup detected by Lens
- `TRAILING` — price hit trailing stop level (future)
- `CLOSED` — trade hit TP or SL
- `RISK` — drawdown warning (3+ consecutive losses)

---

## Data Flow

```
TradingView (Lens Pine Script)
    │
    ├── Visual: arrows + lines on chart (you look at this)
    ├── Alert webhook → Notify → phone notification
    │
    └── You decide: take trade or skip
            │
            ├── Execute on Kraken manually
            │
            └── PRISM Core logs the trade
                    │
                    └── Dashboard displays metrics
```

---

## Current Trading Metrics (Baseline — June 2026)

| Metric | Current | Target |
|--------|---------|--------|
| Win Rate | 44% | 44-54% |
| Average R | 1.58 | 4.0 |
| Profit Factor | 1.24 | 2.0+ |
| Leverage | 10x | 10x |
| Account Risk/Trade | 10% | 10% |
| Doubling Time | unknown | 1.6 weeks |
| Ruin Risk (50% DD) | unknown | <5% |

---

## Milestones

| Date | Target | Account Value |
|------|--------|---------------|
| Jun 2026 | First 4R trade | €504 ✅ |
| Dec 2026 | 1 BTC | ~€150,000 |
| Dec 2027 | 50 BTC | ~€7,500,000 |
| Dec 2028 | 150 BTC | ~€22,500,000 |

---

## Key Equations

**Account risk per trade:**
```
Account Risk % = Leverage × Stop Distance %
10% = 10x × 1%
```

**Expected value per trade:**
```
EV = (Win Rate × R × Risk%) - ((1 - Win Rate) × Risk%)
EV = (0.44 × 4.0 × 0.10) - (0.56 × 0.10) = +12.0% per trade
```

**Geometric mean per trade:**
```
Geo = (1 + Risk% × R)^WR × (1 - Risk%)^(1-WR)
Geo = 1.40^0.44 × 0.90^0.56 = 1.0931
```

**Trades to double:**
```
ln(2) / ln(Geo) = ln(2) / ln(1.0931) = 7.8 trades
```

**Breakeven R at 44% WR:**
```
Min R = (1 - WR) / WR = 0.56 / 0.44 = 1.27R
Below 1.27R at 44% WR = negative EV = losing money
```

---

## Rules for Claude Code

When working on this repository:

1. **Lens is Pine Script on TradingView.** Do not build chart analysis in Python or JavaScript. TradingView does this better than anything you can build.

2. **PRISM Core is the trade logger.** It does not detect signals. It records what actually happened.

3. **Dashboard is read-only.** It displays data from Supabase. It does not make decisions.

4. **Notify is a thin webhook relay.** TradingView → ntfy. Keep it simple.

5. **All position sizing uses the locked parameters:** 10x leverage, 1% stop, 4% TP, 10% account risk, 4R target.

6. **The trailing stop system is defined but not yet automated.** For now, trades use fixed SL/TP on Kraken. Trailing is a future feature.

7. **Monte Carlo validation is required before changing any parameter.** Run 5000 simulations with proposed changes and verify ruin risk stays below 5% at 50% drawdown threshold.

8. **Win rate optimization is secondary. R optimization is primary.** Any change that improves average R by 0.5 is worth more than a change that improves win rate by 10%.
