# DAILY_BREAK_v1 — Baseline + exit-mechanics evaluation

**Status: ❌ NO-GO — the premise does not hold. Do not trade this, do not wire it
live, do not tune it further.** Filled 2026-07-24 from
`strategies/DAILY_BREAK_v1/backtest.py` (specced in `NEXT_SESSION.md`, D1–D8).

Run it yourself:
```
python3 strategies/DAILY_BREAK_v1/backtest.py --baseline   # the three baseline columns
python3 strategies/DAILY_BREAK_v1/backtest.py              # the five exit variants + verdict
python3 strategies/DAILY_BREAK_v1/sweep.py                 # the D8 grid, median-reported
python3 strategies/DAILY_BREAK_v1/test_backtest.py         # harness self-check
```

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

**This is the part that did not survive contact with the data.** See
*Where the premise broke* below.

---

## Test setup (as run)

- **Symbol:** BTC/USDT:USDT perp, **Bybit** (Kraken's OHLC endpoint caps at ~720
  candles regardless of `since`; 24 months of 1h needs ~17,500 bars)
- **TF:** 1h primary, 4h secondary
- **Window:** 2024-07-10 → 2026-07-24 (24 months, after trimming 200 daily bars
  of warmup for the EMA200 gate)
- **Costs:** 0.05%/side on notional, per unit, per side
- **Funding:** real Bybit history, 2,232 stamps, mean **+0.0048%/8h** (longs pay)
- **Liquidation guard:** stop distance must stay under 0.8 × liq distance;
  leverage steps down a tier rather than accept a stop the exchange would reach first
- **Initial capital:** $1,000

Higher-timeframe values (prev-day levels, daily EMA200, weekly trend) are read
from the last **completed** daily/weekly bar. Pine's `request.security` with
`lookahead_off` behaves more loosely than that on realtime bars, so
TradingView's own tester may print slightly different numbers. The
completed-bar reading cannot look ahead, which is the property worth keeping.

---

## Baseline results — variant A (the designed fixed-3R exit)

| Metric | 1h (weekly on) | 1h (weekly off) | 4h |
|---|---|---|---|
| Total trades (n) | 104 | 156 | 47 |
| Win rate % | 21.2 | 24.4 | 21.3 |
| Profit factor | **0.51** | **0.64** | **0.63** |
| Net profit | −228 | −235 | −144 |
| Max drawdown % | 23.9 | 27.8 | 17.0 |
| Avg win (R) | +2.85 | +2.84 | +2.89 |
| Avg loss (R) | −1.11 | −1.11 | −1.06 |
| Avg bars in trade | 14.1 | 15.0 | 15.0 |
| Avg hours in trade | 14.1 | 15.0 | 60.0 |
| Trades/week | 1.05 | 1.51 | 0.47 |
| Max consecutive losses | 16 | 19 | 10 |

Against the original "what good looks like" bar: PF ≥ 1.5 → **got 0.51**.
WR ≥ 40% → **got 21.2%**. Trades/week 1–4 → **1.05, the one criterion it met.**
Max DD ≤ 30% → **23.9%, met.** Max consecutive losses ≤ 6 → **got 16.**

Turning the weekly gate off adds 50 trades and lifts PF from 0.51 to 0.64 —
still a losing system, and the extra trades come with a worse drawdown (27.8%)
and a 19-trade losing streak. It is not a fix.

---

## Exit variants (1h, weekly gate on, 24 months, same trade universe)

Defaults: `be_at_r=1.0`, `trail_buf=0.25×ATR`, `partial_at=2R`.

| ID | Exit | Adds | n | WR% | net PF | net | maxDD% | avg R | hold h | fees | funding | giveback R | adds taken |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | fixed 3R | none | 104 | 21.2 | **0.51** | −228 | 23.9 | −0.27 | 14.1 | 47 | 5 | 1.32 | 0 |
| **B** | pure trail | none | 97 | 19.6 | 0.50 | −163 | 16.3 | −0.24 | 18.4 | 44 | 5 | 2.10 | 0 |
| **B+P** | pure trail | pyramid | 97 | 18.6 | 0.52 | −161 | 16.1 | −0.25 | 18.4 | 45 | 5 | 2.19 | 11 |
| **C** | 50% @2R, trail rest | none | 97 | 27.8 | 0.54 | −152 | 16.4 | −0.21 | 18.4 | 45 | 4 | 1.54 | 0 |
| **C+P** | 50% @2R, trail rest | pyramid | 97 | 28.9 | **0.55** | −151 | 16.1 | −0.22 | 18.4 | 46 | 4 | 1.62 | 13 |

Pyramiding discipline held: **11 adds taken and 9 refused by the risk-ledger
invariant** in B+P, 13 taken and 7 refused in C+P. The liquidation guard never
had to fire — at 1.5×ATR the stop sits far inside liquidation at every tier.

---

## Sweep (D8) — median cell, not best cell

`be_at_r ∈ {None, 0.5, 1.0}` × `trail_buf ∈ {0.15, 0.25, 0.40}` ×
`partial_at ∈ {1.5, 2.0}` (C only). 54 cells.

| variant | cells | med PF | med DD% | med net | best PF | worst PF | spread |
|---|---|---|---|---|---|---|---|
| B | 9 | 0.48 | 16.8 | −168 | 0.62 | 0.36 | 0.25 |
| B+P | 9 | 0.50 | 16.7 | −167 | 0.65 | 0.34 | 0.31 |
| C | 18 | 0.52 | 16.8 | −158 | 0.65 | 0.45 | 0.20 |
| C+P | 18 | 0.50 | 16.6 | −157 | 0.68 | 0.42 | 0.27 |

**Every one of the 54 cells loses money.** The best cell in the whole grid is
PF 0.68 — a 32% loss rate on gross, before you account for the fact that it was
selected by looking at 54 tries.

The one parameter with a consistent signature: `be_at_r = 0.5` beats both
`None` and `1.0` in every variant, and `trail_buf = 0.15` is worst everywhere.
That is a coherent shape rather than noise, but it moves PF from ~0.48 to ~0.65
— it changes how fast the thing loses, not whether it loses.

---

## Verdict (D7)

**PREMISE FAILS. Not "fixed 3R stands" — something worse.**

D7 asked whether a trail variant beats variant A by ≥1.2× net PF within 1.25×
its drawdown, on n ≥ 30. The sample is sufficient (n = 104 for A, 97 for the
variants), so the test is valid — but it answers a question that turned out not
to matter, because **the control itself is not profitable.** At PF 0.51, the
D7 bar of "1.2 × A's PF" is 0.61: a threshold beneath breakeven. A variant
could clear it and still lose money every single month. Reporting "B+P clears
D7" would have been technically true and completely worthless.

So the honest verdict is the one D7 didn't have a branch for: **no exit mechanic
is adoptable here, because exits are not what is wrong.**

**Do not** write the trail/pyramid options into `strategy.pine`. Deliverable 4
in `NEXT_SESSION.md` was conditional on a variant winning by D7. None did, so
the Pine file is untouched and stays at v1.0.0.

### Where the premise broke

The setup produces winners at **+2.85R** and losers at **−1.11R** — exactly the
3R geometry it was designed for, with fees behaving as modelled. Breakeven win
rate at that payoff is **28.0%**. The strategy realized **21.2%**. It is not an
exit problem, a fee problem, or a funding problem (funding totalled €5 across
104 trades — the holds are far too short for carry to matter). **The entry is
simply not selective enough**: roughly one break in five follows through, and
one in four is needed.

And the premise's own mechanism didn't appear. DAILY_BREAK_v1 was built for the
>24h hold bucket (PF 1.62 in the PRISM fingerprint), but on 1h the average hold
is **14 hours**, and even the pure trail with no take-profit only stretches that
to 18. The strategy was never getting into the bucket it was designed to
exploit. On 4h the holds do reach 60 hours — and PF is still 0.63.

The trail did what a trail does: it cut drawdown hard (23.9% → 16.3%) and gave
back more of each winner (giveback 1.32R → 2.10R). Both effects are real and
correctly modelled. Neither can rescue a negative-expectancy entry.

### What this cost, and what it bought

One evaluation, no live changes, no Pine edits, paper only — as scoped. What it
bought is a strategy retired on evidence rather than left in the drawer looking
plausible, plus a reusable perp-aware harness (real Bybit funding, per-unit fees,
liquidation guard, risk-ledger invariant) that the next exit question can run on
in minutes.

### Explicitly not doing

- No further parameter fishing. The declared sweep ran; every cell lost. Widening
  the grid until something prints PF > 1 is how a backtest starts lying.
- No entry-side rework in this pass. If DAILY_BREAK is ever revisited, the
  question is selectivity of the break (retest confirmation, a wider prev-day
  range floor), not the exit — but the standing context still applies: measured
  live edge is −6.6%/mo and the #1 lever is not trading VETO contexts. A better
  breakout filter does not fix a discipline problem.

---

## Schema validation checklist

Not run — the strategy is NO-GO, so nothing is being wired to the ingest
endpoint. Left here for the record in case the entry is ever rebuilt.

- [ ] Alert fires once per confirmed bar close only
- [ ] Alert message is valid JSON
- [ ] `trigger_type` is `"prev_day_high_break"` or `"prev_day_low_break"`
- [ ] `confluence_count` is 1–5
- [ ] `suggested_leverage` matches confluence tier (5, 7, or 10)
- [ ] curl test: `curl -X POST http://localhost:8765/api/signals -H "Content-Type: application/json" -d @<payload.json>`
