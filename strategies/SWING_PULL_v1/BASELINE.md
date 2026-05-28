# SWING_PULL_v1 — Baseline (TBD)

*Fill this in after running TradingView Strategy Tester.*

---

## Strategy summary

4h EMA pullback trade in the direction of the daily 200 EMA trend.

- **Recommended TF:** 4h (natural hold: 1–5 days → targets the PRISM >24hr edge)
- **Entry:** 4h bar closes back above/below the 21 EMA after a pullback (≤3 bars),
  fast EMA (8) still aligned, EMA slope still rising/falling
- **HTF gate:** Daily 200 EMA — only long when close > D200, only short when below
- **Volume:** bar volume > 20-bar SMA × 1.2
- **Stop:** 1.5 × ATR(14) against entry
- **Target:** 3R — deliberately wide to allow multi-day holds where the edge is
- **Discipline:** No Saturday, no 02/11 UTC, 5-min cooldown (mirrors `app/discipline.py`)
- **Sizing:**
  - ≥4 confluence: 10× leverage / 5% account
  - 3 confluence: 7× leverage / 3% account
  - ≤2 confluence: 5× leverage / 2% account

### Confluence factors (max 5)
1. Volume spike
2. Daily 200 EMA aligned
3. EMA slope in trend direction
4. Weekly BTC trend aligned
5. Active session (London or NY)

---

## Why this premise should work

From PRISM fingerprint:
- >24hr holds: **WR 56%, PF 1.62** — the only consistently profitable duration
- 10–25× notional/balance: **WR 53%, PF 1.78** — conviction size wins
- The 4h EMA pullback on a trending market naturally produces 1–5 day holds
- 3R target at 1.5× ATR stop means price must move ~4.5 ATRs — takes days on 4h

---

## Test setup

- **Symbol:** BTCUSDT.P (or XBTUSD.P on Kraken — same price action)
- **TF:** 4h primary; also run 1h for comparison
- **Range:** Last 12 months (more bars = more reliable baseline than 6 months)
- **Commission:** 0.05% per side, slippage 2 ticks
- **Initial capital:** $1,000

---

## Baseline results

| Metric | 4h | 1h |
|---|---|---|
| Total trades (n) | | |
| Win rate % | | |
| Profit factor | | |
| Net profit | | |
| Max drawdown % | | |
| Avg win % | | |
| Avg loss % | | |
| Avg bars in trade | | |
| Trades/week (approx) | | |
| Max consecutive losses | | |

---

## What "good" looks like

- **PF ≥ 1.5** — must beat the PRISM conviction-filtered benchmark (PF 1.87)
- **WR ≥ 48%** — at 3R, breakeven WR ≈ 25%; 48%+ is strong
- **Trades/week 2–6** — sustainable; this is a swing strategy, not a signal factory
- **Avg bars in trade ≥ 6 bars (4h)** — confirms it's producing multi-day holds (6 × 4h = 24hr ✓)
- **Max DD ≤ 25%**
- **No 8+ consecutive losses**

---

## What to tune if results disappoint

1. **PF < 1.2:** Entry premise weak — try requiring 3 confluence minimum (no ≤2 tier)
2. **Too many signals (>8/week):** Tighten volume to 1.5×, or require weekly trend alignment
3. **Too few signals (<1/week):** Lower vol to 1.1×, extend lookback to 5, relax slope filter
4. **Short side dragging PF down:** Disable shorts, run long-only in bull market — test separately
5. **Avg hold too short (<6 bars):** TP being hit too quickly → raise rrTarget to 4.0

---

## Schema validation checklist

- [ ] Alert fires once per confirmed 4h close only
- [ ] Alert message is valid JSON (test with `python3 -c "import json,sys; json.loads(sys.stdin.read())"`)
- [ ] JSON parses into `SignalIngest` — curl test: `curl -X POST http://localhost:8765/api/signals -H "Content-Type: application/json" -d @<payload.json>`
- [ ] `confluence_count` reflects actual factors present (1–5 range)
- [ ] `suggested_leverage` matches confluence tier (5, 7, or 10)
- [ ] `trigger_type` is `"ema_pullback_long"` or `"ema_pullback_short"`
