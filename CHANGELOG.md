# LENS — Changelog

Dated build history, newest first. Forward-looking plan and open next-steps
live in `LENS_PLAN.md`; commit detail is in `git log`.

---

## 2026-07-24

**The genetic breeder is built — and it measured why its own premise fails**
(`app/strategy_breeder.py`, wishlist Item 1). Tournament GA over the `SLOTS`
vocabulary with geometry bred as part of the genome, `max_conditions=6`.
Fitness is **`min(train, holdout)`** of drawdown-penalised expectancy in R —
the clamp is inside selection, not a post-screen, so a genome that only works
in-sample is scored by its bad half and dies before it can win. Holdout `n ≥ 40`
or it is disqualified outright, however good the in-sample number looks.

**It ran, and the functional case did not survive contact.** The GA existed to
reach genomes with >3 conditions, which grid enumeration cannot afford. Of 103
viable genomes across 1h/4h/1d, **one** uses more than 3 conditions. Best
fitness is 0.028 — thin. Every top genome sits inside the region
`strategy_search3` already enumerates.

**Why, measured** — 120 random genomes per depth on 4h:

| conditions | viable | too few signals | thin holdout | median holdout n |
|---|---|---|---|---|
| 1 | 94 | 0 | 26 | 69 |
| 2 | 60 | 10 | 50 | 42 |
| 3 | 26 | 57 | 37 | 33 |
| 4 | 7 | 84 | 29 | 21 |
| 5 | **0** | 111 | 9 | 14 |
| 6 | **0** | 114 | 6 | 17 |

Depth doesn't fail on fitness — it fails on **data**. By 5 conditions the
combined filter selects under 40 bars in 30 months, so there is nothing to
backtest, let alone validate out-of-sample. `max_conditions=3` was never an
arbitrary cap on the grid: it is approximately where this window runs out of
evidence. A deeper search needs a longer window (the 7-year Binance set already
wired into `strategy_search3` stage 3), not a cleverer search algorithm.

**The strategy vault is genuinely diverse — the near-duplicate hypothesis was
wrong** (`app/strategy_dedup.py`, breeder wishlist Item 1 prerequisite). The
breeder doc assumed the 933 split-half survivors were "really ~20 ideas wearing
different labels", and rated dedup as higher value per hour than the GA itself.
Measured: **933 labels → 525 ideas**, and the 402 baseline-beaters → **230**.
The median pair of survivors shares **1.3%** of its entry bars and **0%** of its
realized trades. Nothing to unpack; the GA would be searching an already-wide
space.

Two measurements that cost more than the answer and matter more:

· **Correlation of equity curves — Algory's own diversity metric — is the wrong
instrument for this vault.** These survivors trade a median of 59 days out of
770, and the median pair shares *one* active day. With near-disjoint supports,
Pearson on daily pnl is dominated by mutual zeros; it reported 325 "ideas" off
pure sparsity. Correlating *cumulative* equity would be worse still — every
curve inherits BTC's uptrend, so everything correlates with everything. The
metric that works here is Jaccard overlap of the **entry masks**: which bars the
conditions select, before geometry or position state touches anything.

· **Geometry re-shuffles the realized trade set far more than expected.** Two
survivors with *identical* entry conditions, differing only 3.0R vs 5.0R, share
just **0.38** of their realized trades — a different take-profit frees the
position at a different bar, so a different set of later signals is taken rather
than blocked. This is why realized-trade overlap was also rejected as the
metric, and it constrains the breeder: `execution` genes are not a cosmetic tail
on the genome, so fitness must be scored per full genome, never by evaluating a
condition set once and sweeping geometry over it afterwards.

Counts are bounds, not a point estimate — mask overlap is the upper bound (it
under-merges when extra selected bars all land while a position is already
open), realized-trade overlap the lower. Both agree the vault is wide.
Results → `strategy_clusters_beats_baseline.json` / `_split_half.json`.

**Vetoed setups are logged instead of silently discarded** (breeder wishlist
Item 0). A setup that matched and was stood down by a veto rule left no row, no
trace and no notification: `emit_signals` dropped every non-clean match and
`run_scan_cli` filtered them out before it. Cost was double — the feed showed
longs only for 10 days while the engine was in fact working and correctly
refusing shorts, so it looked asleep; and with no row there was no
**denominator**, so "would taking the vetoed ones have made money?" could not be
asked (`/robustness`' veto counterfactual runs on closed trades and cannot see
setups that never became trades). They now persist as `rejected` rows with
reason `veto:<rules>`, deduped per bar+setup. Blocked is not actionable, so they
never notify — the push path only takes `pending`.

**`/signals` gained a `blocked` section** — setup ✓, which rules ✗, and the
realized ledger for that exact veto bucket via `setups.veto_bucket_stats()`
(re-read from the book every render; the numbers frozen into `VETO_LABELS` have
already drifted). Colour is inverted deliberately: a bucket in the red means the
veto saved you, a bucket in profit means the rule is costing you.

**What the replay already says**, over the last 30 days of bars:
· **S4 is dead code** — 25 matches, **25 vetoed, zero emitted**. It's a long on
`rsi<40` in discount, which trips `slope_against` structurally every time.
· **S2 is effectively dead** — 5 matches, 5 vetoed (as suspected 2026-07-18),
though by varying rules rather than one structural pair.
· **`fvg_entry` is the most-fired veto (69 hits) and the only one in profit** —
+€2,000 over 26 trades, while its frozen label still reads "−€15/trade". It is
blocking the most and justifying it the least. Worth a hard look.

**DAILY_BREAK_v1 evaluated and retired — ❌ NO-GO.** The 2026-07-14 spec asked
whether Darvas-style structure trailing or pyramiding beats the designed fixed-3R
exit. New perp-aware harness (`strategies/DAILY_BREAK_v1/backtest.py`): Bybit 1h,
24 months, all five variants (A / B / B+P / C / C+P), real Bybit funding (2,232
stamps, +0.0048%/8h), per-unit fees on notional, a liquidation guard, and the D4
risk-ledger invariant asserted on every add. Plus `sweep.py` (54 cells,
median-reported) and a `test_backtest.py` self-check.

**The answer is not "fixed 3R stands" — it's that the premise fails.** Variant A
nets PF **0.51** / WR **21.2%** on n=104. Wins land at +2.85R and losses at
−1.11R, exactly the designed geometry, so breakeven WR is 28% and the strategy
gets 21%. The entry isn't selective enough; exits were never the problem. All 54
sweep cells lose (best 0.68). D7's "1.2× A's PF" test was reported but is
meaningless against a losing control — a bar beneath breakeven. The trail did
work as designed (max DD 23.9% → 16.3%, giveback 1.32R → 2.10R); it just can't
rescue a negative-expectancy entry. **`strategy.pine` untouched at v1.0.0** —
deliverable 4 was conditional on a variant winning, and none did.

Side note: designed for the >24h hold bucket, the 1h version averages **14 hours**
in trade — it was never reaching the bucket it was built to exploit.

## 2026-07-13 → 14

**Landing page rebuilt as the cockpit front door.** Aperture mark scaled into
the hero (slow crosshair spin, reduced-motion respected), thesis line, live
status line, ledger-derived gauges (one SQL each, ~13ms render), the two
machine doors, and a how-it-runs pipeline row. Then **money came off the front
door entirely**: the gauges report what the instrument does (fills logged,
vetoes armed, signals screened/blocked, rules-audit verdict), not what the
owner is worth — zero currency figures on the page.

**README rewritten as a production front page** (what it is, the loop, how to
run it, docs map). The detail it used to carry lives here and in
`LENS_PLAN.md` now.

## 2026-07-12

**Discipline filters re-derived from the actual ledger** — the originals were
folklore. The **Saturday rule is GONE** (Saturday is the best day in the
fills); the only bleed hour is **09:00 BKK**; cooldown is 60m. `prop_scan` now
runs the discipline filters too — prop signals had been bypassing them
entirely.

**Era scoreboard.** Analytics defaults to trades since **2026-07-01** (Q3, the
era the re-derived filters apply to); `?era=all` shows lifetime. The old ~500
trades stay as the baseline, not the scorecard.

**`/robustness`** — permutation verdict on the discipline filters (are they
signal or noise?) plus a conviction-calibration tracker, and a veto
counterfactual panel.

**Prop ticket** split risk from leverage and gained a stop-% what-if dial.

## 2026-07-10 → 11

**Prop round 2 — the eval cockpit got its own physics.** Fit sweep under real
prop constraints, `/prop-cone`, position overrides, Fit→prop-goal handoff,
prop cash flow, nav declutter; the stale-$5k EVAL/ACCOUNT/RISK constants
deleted (`prop_views`). Context: the **$48 Breakout $10k Advanced Eval 2 was
purchased 2026-07-10** (`BREAKOUT_1STEP_TURBO` @ 0.5% risk) — superseding the
README's old €20 5k plan.

**Stack projection unblocked** (0 ₿ fallback + live € spot) and the goal
sidebar auto-fills (ATR floor · BTC price · BTC growth) on `/goal` +
`/prop-goal`. A real stack snapshot is still wanted for real rung dates.

**Exit mechanics exonerated:** MAE/MFE shows the low realized R is a
*selection* problem, not an exit problem; reachability grades the book against
the TP it actually trades. Exit-mechanics sims retired.

## 2026-07-09

**G3 · The signal loop is instrumented.** Exchange fills now claim the nearest
approved, unclaimed signal whose decision precedes them (`_link_signal`, both
sync paths). One signal → one trade, so a split order's second fill can't take
credit twice; a hand-logged link is never re-pointed.
⚠️ The spec's 1% entry box was wrong — trade 550 sits **1.12%** off its signal's
quoted price, and symbol equality matches *nothing* (trades carry `BTC/USD:USD`,
signals `BTCUSDT.P`). Tolerance is 2.5%, symbol is deliberately unmatched.
⚠️ Backfill made **1** link: coverage is 2 → **3 of 499**. G3's ≥90% target is
not reachable by backfill and never was — the ledger is full of trades taken
*outside* the loop. Only forward flow can move that number, which makes coverage
a usage metric, not a code one.

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
