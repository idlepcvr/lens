# LENS — Changelog

Dated build history, newest first. Forward-looking plan lives in
`LENS_PLAN.md`; open next-steps live in the README's **Next** section; commit
detail is in `git log`.

---

## 2026-07-09

**The Goal Ladder is finished.** The whole NEXT_SESSION build, phases C1 → C6,
in the ratified order. The plan is now caged: it can only change through a
versioned amendment with a reason, and everything else derives from it.

**C5 · Scenario ladder** (`/goal`). A win-rate × realized-R grid, client-side.
Each cell is EV in R and the monthly % it implies at the current risk and
cadence; the amber line is the breakeven frontier `WR = (1+feeR)/(1+R)`. Two
pins — **M**easured (ledger) and **P**lan (typed) — make the gap between what
he claims and what he's shown a single glance. Today: M at 39.3%/1.31R, P at
39.5%/3.0R.

**C3 · Projection cone** (`app/cone.py`, `/analytics`). P10/P25/P50/P75/P90
bootstrapped from realized EUR P&L, 2000 paths, anchored monthly (daily
re-anchoring hides drift), running to the next milestone's derived date. n<30
falls back to plan params and badges itself. One status word — AHEAD / ON /
BEHIND / OFF-PLAN — computed in one place and quoted by /analytics, /goal,
/calendar and /journal.
⚠️ Two ledger traps found here: `trades.balance_after` is **not** account equity
(70 of 489 rows imply |return| > 60%, dozens exactly −100%), and normalizing P&L
by the daily snapshot flips the sign of the mean depending on the outlier cap.
The cone therefore bootstraps EUR P&L directly and rescales by one robust
scalar. Don't reintroduce per-trade returns from `balance_after`.

**C3 · Stack projection** (`app/stack_proj.py`, `/goal`). Dates the 5 BTC and
50 BTC rungs, measured vs plan, under bear/base/bull CAGRs. Personal equity
compounds; the prop leg is a linear payout stream (payout × take-home − burn).
No funded account → payout €0 → surplus is −burn and the stack drains.
⚠️ **Bear lands first**: rungs are in BTC, so EUR income buys more coin cheap.
A bull run pushes a BTC target *further* away. Counterintuitive, and correct.

**Stage B · The envelope filters the search.** Fit persists its feasible envelope
(`fit_envelope` table) on every sweep; `/edge` scores each search result against
it by normalized distance — 0 = inside = FITS, near-misses rank lower and name
the axis they fail. "Feasible only" toggle; stale (>7d) or empty envelopes
disable it rather than filter on dead numbers. Empty corridor gets the plain
verdict plus the nearest miss. Only wr/rr/freq are scored per row: every backtest
runs at a fixed 5× leverage, so that check is page-level.

**C4 · Regime realism** (`app/realism.py`). Counts days in the last 90 whose
range cleared the required TP move — overall and *within the current regime* —
and holds the offered setups/week against the needed trades/week:
**OFFERED** (≥1.5×) / **TIGHT** (0.75–1.5×) / **STARVED** (<0.75×). It
immediately caught the pathology it was written for: a "feasible" optimum needing
a 7.50% move 7.5× a week, which SIDEWAYS offered on **1 of the last 90 days**.

**C6 · Surfacing.** `/goal` ladder hero (stage, next rung, progress, status word,
coverage). "Income complete" fires on 6 consecutive months of engine cash flow ≥
burn — not 4% withdrawal math. The honest bar is printed: at the current €5,000
funded size, covering €2,800/mo needs **~70%/mo**. Prop payouts count €0 —
evaluation P&L isn't cash. Calendar carries month-end P50 vs actual; journal
carries the status word beside the execution grade.

---

## 2026-07-04

**Alerts got situational awareness.** Alerts carry a "⏱ Live now" price+drift
line; pending signals auto-expire when price runs >0.5% past entry (before
pushing); same-idea signals (same direction, entry ±0.5%, approved <6h)
auto-approve quietly — on `/signals`, no phone buzz. Verified live on a real
repeat S3.

**One geometry everywhere.** `_board_geo` returns SL_PCT/TP_PCT (0.63/1.5);
the board picks WHICH strategy, never levels; `/desk` help text fixed.

**Automated strategy search v2 → superseded by v3.** `app/strategy_search.py`:
≤3-condition combos across trend/candle/MACD/RSI/BKK-sessions/Bollinger/
TD-Sequential-9/triple-MA-stack/vol-spike/ATR-regime, real engine + 0.03%/side
slippage, split-half filter, SL×TP×lev×ATR-floor sweep, 7y-binance deep
confirmation, Kelly. v2 found 0 deep-confirmed — but that verdict was scoped to
the tight-scalp regime (stage 1 filtered everything at 0.63/1.5/10x).

**Search v3 — dynamic ATR geometry** (`app/strategy_search3.py`), 43,703
evaluated. Geometry inside stage 1: stop = k×ATR, TP = R×stop, risk-normalized
2%/trade (engine: `atr_stop_mult`, `rr`, `risk_pct`; self-check
`test_atr_stop.py`). Four gates: split-half n≥40 → 7×7 (k,R) matrix
neighbourhood → 7y deep at own geometry → beats random-entry baseline per-trade
on both windows (gate 4 exists because buy-every-bar long at 2.5×ATR is itself
green on 7y — drift). **Verdict: 374 distinct survivors clear all four gates**
(330 long / 44 short; tight stops stay dead — fee floor ~0.72R/trade at 0.5%
stop vs ~0.1R at 2.5×ATR). Three families: 4h trend+MACD momentum longs
(1.5×ATR, 3–5R, BKK-evening strongest) · 1h dip-buys in bull structure
(RSI≤30/BB<lower + MA-stack bull, 2.5×ATR, 5R) · SHORT capitulation fades
(BB<lower + vol spike — biggest edge over baseline, +2.08%/trade). Full report
(HTML+MD): Kiki `03 - Resources/lens-strategy-search-v3-202607.*`. Results:
`strategy_search.json` v3. Shadow-registered 1 rep per family —
`TREND_MOMO_VOLSPIKE_v3` / `DIP_BB_MASTACK_v3` / `CAPITULATION_FADE_SHORT_v3`
in `STRATEGIES` (never-alert: the setups.py hero path doesn't iterate the
registry; they surface only in the `/strategy` dropdown's unranked section,
like `ASIAN_MORNING_LONG_v1`). Pine exporter speaks `atr_stop_mult` (k×ATR
entry stop, rr×stop TP). Both covered by `test_atr_stop.py`.

**`/edge` became a steerable search, not just a form** (`app/search_custom.py`,
`POST /api/backtest/search` + `/search/status`). Blank builder fields = swept
dimensions, set fields = pinned; direction/timeframe have an "any (search)"
option. Risk envelope entered as ranges (ATR-stop k, R, risk %/trade —
from–to), swept over the FINE_K×FINE_R matrix inside the bounds. Background
thread, UI polls, ranked table (robust-first, then net%); click a row → loads it
into the builder for ▶/⊞/⧉. 8k-eval cap returns a "pin more fields" message.
Every result row + the single-run scorecard carry a **→ Goal** link that opens
`/goal` prefilled with that strategy's WR / R / trades-per-week (query-param
handoff, no calc changes). Verified end-to-end in-browser: TREND family
reproduces +67.7% at k1.5/R3, goal handoff computes (2.76R, 89d). Honesty
caveat: 30mo split-half only; deep-7y confirmation stays offline.

**Data reconciliation verified.** `/calendar` + `/overview-hedge` match DB
exactly (484 / −4405.83); `/overview` prop n=0 correct (book archived 06-30).

## 2026-07-02

**Strategy audit (geometry + mining, full history).**
`strategies/_research/STRATEGY_AUDIT_20260702.md`. Headlines: S1 is the only
mechanically-alive labeled setup; the 0.63% stop is right but the 0.95% target
is too tight (real winners run to 1.5–2%); two mined candidates (H12
quiet-uptrend grind, H13 weak-bounce fade) now tracked by the Monday re-rank —
promote to shadow signals only if they hold on fresh data for ~a month.

**Data layer fixed.** Balance timeline now reads both cash wallets (account is
USD-settled; old code filtered to EUR) *and* account-log pagination actually
works (old cursor bug capped history at 1000 entries). Backfill endpoint
repaired all 481 closed trades — 0 NULL balances, real leverage.

**Housekeeping.** README trued up + restructured (at-a-glance table,
screenshots, history trimmed); `prism.env` retired (everything reads `.env`);
orphan pages (Style / Sitemap / Health) added to both mode footers; branded 404
page; `/mvp` dropped (covered by `/position` + `/overview-hedge`; `mvp-executor`
branch kept as local archive).

## 2026-06-22

`TREND_4R_v1` (4H/4R thesis) backtested → 20.9% WR over 182 trades, below the
26% fee-adjusted breakeven, PF 0.75, account to zero. **Retired.** The "risk 10%
to make 40%" compounding plan rested on a 44–48% WR at 4R that the data says
doesn't exist. See `strategies/TREND_4R_v1/BASELINE.md`.

## 2026-06-16 — 06-21

First real S1 short emitted + pushed (06-16). Alert became a lean lock-screen
ticket (06-21). Two-door PROP|HEDGE mode split (06-17). Full mobile audit,
phone-first (06-19). `/prop-signals` prop review queue added (06-21).
