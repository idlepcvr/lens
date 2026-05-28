# DAILY_BREAK_v1 — Baseline (TBD)

*Fill this in after running TradingView Strategy Tester.*

---

## Strategy summary

Previous-day high/low breakout with volume confirmation, daily 200 EMA bias gate,
weekly trend alignment. Designed for multi-day swing holds (12–72 hours typical).

- **Recommended TF:** 1h primary; also test 4h
- **Entry:** First bar close above previous day's high (long) or below previous day's low (short),
  on volume spike > 20-bar SMA × 1.4, with daily EMA and weekly trend aligned
- **Stop:** 1.5 × ATR(14) against entry
- **Target:** 3R — wide enough that holds naturally extend to >24hr (the PRISM edge zone)
- **Level gate:** Previous day's range must be ≥ 0.4% of price (filters out flat inside days)
- **Cooldown:** 60 min (one trade per level per day — not a scalp machine)
- **Discipline:** No Saturday, no 02/11 UTC (mirrors `app/discipline.py`)
- **Sizing:**
  - ≥4 confluence: 10× leverage / 5% account
  - 3 confluence:  7× leverage / 3% account
  - ≤2 confluence: 5× leverage / 2% account

### Confluence factors (max 5)
1. Volume spike (> 1.4× 20-bar SMA)
2. Daily 200 EMA aligned
3. Weekly BTC trend aligned
4. Active session (London or NY)
5. Wide previous day (range > 0.6% of price)

---

## Why this premise should work

From PRISM fingerprint:
- >24hr holds: **WR 56%, PF 1.62** — the real edge bucket
- Monday: **WR 48%, PF 1.21** — daily breaks often resolve Monday/Tuesday  
- Daily high/low levels are real structural anchors — institutions watch them
- 3R target at 1.5× ATR stop on 1h → TP typically 12–48 hours away
- Volume gate filters out fake breaks (low conviction moves that reverse)

The daily breakout premise is one of the few mechanically clean setups that
naturally produces multi-day holds without having to "hold through noise" —
the position is either right from the open or stopped quickly, keeping hold
duration distribution healthy.

---

## Test setup

- **Symbol:** BTCUSDT.P (or XBTUSD.P)
- **TF:** 1h primary (also test 4h)
- **Range:** Last 12 months
- **Commission:** 0.05% per side, slippage 2 ticks
- **Initial capital:** $1,000
- **Test variants:**
  1. `reqWeekly=true` (default) — trend-filtered
  2. `reqWeekly=false` — see if the weekly filter helps or hurts

---

## Baseline results

| Metric | 1h (weekly on) | 1h (weekly off) | 4h |
|---|---|---|---|
| Total trades (n) | | | |
| Win rate % | | | |
| Profit factor | | | |
| Net profit | | | |
| Max drawdown % | | | |
| Avg win % | | | |
| Avg loss % | | | |
| Avg bars in trade | | | |
| Trades/week (approx) | | | |
| Max consecutive losses | | | |

---

## What "good" looks like

- **PF ≥ 1.5** — daily level breaks should outperform random entries
- **WR ≥ 40%** — at 3R, breakeven WR = 25%; anything above 40% is excellent
- **Trades/week 1–4** — this is a low-frequency swing strategy by design
- **Avg bars ≥ 12 (1h) / ≥ 6 (4h)** — confirms 12h+ holds (the edge zone)
- **Max DD ≤ 30%** — wider acceptable here since trades/week is low
- **Consecutive losses ≤ 6**

---

## What to tune if results disappoint

1. **Too many false breaks (PF < 1.2):** Raise `volMult` to 1.6, or require `prevDRangePct > 0.6`
2. **Not enough signals (<1/week):** Disable `reqWeekly`, lower `volMult` to 1.2
3. **Short side dragging results:** Test long-only first — BTC is primarily a long market
4. **Stops too tight:** Raise `atrSl` to 2.0 — might improve WR at cost of TP distance
5. **Breakout reversals (entry ok, reversed immediately):** Add a "retest" requirement —
   wait for price to retest the break level before confirming entry (would require code change)

---

## Schema validation checklist

- [ ] Alert fires once per confirmed bar close only
- [ ] Alert message is valid JSON
- [ ] `trigger_type` is `"prev_day_high_break"` or `"prev_day_low_break"`
- [ ] `confluence_count` is 1–5
- [ ] `suggested_leverage` matches confluence tier (5, 7, or 10)
- [ ] curl test: `curl -X POST http://localhost:8765/api/signals -H "Content-Type: application/json" -d @<payload.json>`
