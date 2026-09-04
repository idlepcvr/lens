# LENS — Changelog

[Open as HTML](CHANGELOG.html)

Dated build history, newest first. Open next-steps live in
`NEXT_SESSION.md`; commit detail is in `git log`.

---

## 2026-09-04

**Track told the truth for the first time, and the hedge/prop split started.**

Four straight bugs in what `/track` was reporting as "on pace":

- Overdue rungs collapsed to `steps=1` and printed a fictitious "+61% next
  trade" quota. Now retires the missed rung outright (no dates move, no
  invented per-trade target) rather than pretending a single trade closes
  the whole gap.
- `cone.near()`'s trade rate is a **lifetime** average (543 trades ÷ 72
  weeks since April 2025 → 7.5/wk) — right for the Monte-Carlo drift, wrong
  for "what pace am I keeping now." `step_plan()` now counts a 30-day
  window directly (5.4/wk).
- `cone._trades()` had no book filter: 15 prop evaluation trades (−€452)
  sat inside the hedge projection the personal account is measured
  against. Filtered to `LENS_BOOK`. 543 → 529 trades.
- `track._cum_by_day()` double-counted all pre-window P&L — a `lead` term
  added history the running total had already summed. Read −€8,575 where
  the truth was −€4,288, exactly 2×. The offset hack in `track()` existed
  only to cancel this against the missing book filter above; with both
  fixed it computes to 0.0 and is gone.

Net effect on the reading: **−€294 below P50, outside the band** became
**−€95 below P50, inside P25–P50, status ON**. The prop trades were
pushing the hedge book out of its own band.

Also: the pace line itself didn't exist before today — `/track` drew a
five-band cone with no statement of which side of it you're on. Added an
ahead/behind headline plus a plain-English explainer of what P10/P50/P90
actually are. Real time-range buttons (1W/1M/3M/1Y) replaced two that
silently did the same thing.

**The site had no footer** since 2026-08-29 — `footer_html()` returned `""`
on every page once the neutral-page links were dropped from it, and
nothing was added back. It now always renders, carrying BTC-price age and
stack-snapshot age instead of a link farm — the two numbers every EUR
figure on every page is silently derived from. Currently reads the stack
snapshot as several weeks stale; updating it is the first open item below.

`tests/test_plan.py::test_measured` had failed on every full-suite run
this session (`assert 9 == 0`, passing standalone). Cause:
`test_signal_link.py` and `test_excursion.py` are scripts, not test
functions — pytest imports them during collection and their body runs,
reassigning the global `database.DB_PATH`. Whichever imported last owned
the database. Fixed on the victim with an autouse fixture rather than the
polluters, since their asserts running at import *is* their coverage.
Suite: 54 passed, 0 failed — first clean run all session.

**Hedge/prop split — started, not finished.** `~/lens-prop` forked from
`lens` at `5d37f7d` (own git history from here: `idlepcvr/lens-prop`), own
systemd service (`lens-prop.service`, port 8766), own start/stop scripts.
Both services verified to survive independent restart. `lens-prop`'s
`KRAKEN_FUTURES_SANDBOX` forced to `1` — it's still a byte-for-byte copy
carrying `execute.py` and the same live Kraken keys as `lens`, so two
processes able to place real orders on one account is not acceptable until
the code is actually cut apart. See `NEXT_SESSION.md` for the concrete
plan; the wiring above is the easy half, the code split is the real work.

---

## 2026-08-26c

**The rest of the backlog: three bugs, a Track twin, and an honest pass-rate.**

Bugs: `--faint` (2.3:1 contrast) swapped for `--dim` (5.5-6.1:1) on the six
documented body-text misuses in `theme.py` plus one same-file miss
(`.mgsec > .mgh`) — ~30 other files use `--faint` the same wrong way,
flagged not swept. `Log as open trade` deleted from `position_page.py`:
it duplicated kraken_sync's auto-sync for hedge and duplicated
`/prop-ledger`'s complete log+close flow for prop — root cause was two
already-working things, not a missing close button. `Trade.edit_order`
wired: the kraken-futures SDK already has `edit_order`, it was just never
called — added `execute.edit_order()`, `POST /api/orders/edit`, an edit
button on TP/SL rows, verified against real Kraken.

`/prop-track` shipped: NEXT_SESSION's Track twin, built entirely on
`prop_ledger_data()` (zero new computation) reframed around today. NAV_PROP
gains Track between Goal and Position. `test_nav_parity.py` converted from
a standalone `main()` to `test_nav_parity()` so pytest actually collects it.

Pass-probability: the backtest cone (32.5% pass, live TURBO config)
already existed. What was stale was the "measured" caveat — a hand-typed
"1.5%, 2026-07-09" string from a script with a hardcoded 10%/3% target/floor
that didn't match TURBO's real 9%/3%. Parameterized `eval_mc.run()`,
added `prop_goal.measured_pass_pct()` (recomputes live from the real
ledger each call), wired into the cone response and its caveat.
**Today's honest number: 0% measured pass rate on 8 real trades (12.5% WR,
0.99R) vs 32.5% on backtest** — n=8 is flagged as too small to be a verdict,
but the direction matches what's already known: the strategies haven't
reproduced their backtest edge on real fills.

Full suite: 53 passed (up from 52 — nav_parity is now collected), same
one pre-existing flake (`test_measured`, fails on a full run only).

## 2026-08-26b

**`/review` shipped — NEXT_SESSION.md's monthly review, item #1.** New
`app/review_page.py`: a month's closed trades grouped live by what the
scanner said at entry (setup fired / nothing / VETO), plus a per-VETO-combo
breakdown (n≥5) so the split that used to be computed by hand in sqlite is
now read off the page. A `review_verdicts` table (append-only, same pattern
as `veto_log.py`) records a keep/tune/retire call on a combo with a date and
a reason — the way a plan amendment does — via `POST /api/review/verdict`
(422 under a 10-char reason). `POST /api/review/notify` sends the ntfy
nudge; cron fires it `0 8 1 * *`, same local-curl pattern as the other jobs.
Nav: `/review` joins `NAV_NEUTRAL` between Geometry and Money. First real
verdict recorded live: `slope_against` kept as VETO (p=0.44, not
significant — see the override-miner finding above). Full suite: 52 passed,
1 pre-existing flake (`test_measured`, fails on a full run only — documented
in NEXT_SESSION's carried-over list, not from this change).

## 2026-08-26

**Root cleaned up: BRAND/CHANGELOG/PRODUCT/NEXT_SESSION (md+html) moved into
`docs/`**, joining the DONE-* history already there (now under
`docs/done/`). README stays at repo
root. `app/docs_page.py` and README's two internal links updated to match;
`/manual` verified live on all five docs post-restart. Dead root `lens.db`
(the 0-byte stray the `.gitignore` already called out) deleted — `data/lens.db`
remains the real, gitignored, movable copy.

**`research/override_miner.py`: no VETO combination survives permutation
testing.** Answers NEXT_SESSION.md §1. Every combo with n≥15 run through the
`filter_significance.py` gate plus a leave-one-month-out check; nothing
clears p<0.05, let alone the Bonferroni bar. `slope_against` — the candidate
flagged as most credible on 2026-08-22 — comes back p=0.44, positive only
3 of 8 months. Result archived at
`docs/done/DONE-2026-08-26-override-miner-no-survivor.md`; NEXT_SESSION.md
rewritten with the monthly review (old §2) now first.

## 2026-08-22

**The ladder got phases, and then got rounded.** The rates had run 100/50/10
since v7 but lived only as prose inside `amendment_reason`, so nothing could read
them and no page could say which phase you were in. `goal_plan.phases` is a real
column now — `[{name, to_btc, rate_monthly}]` — carried through `amend()` with an
additive migration; NULL parses as `[]`, since every plan up to v7 genuinely was
one flat rate.

**v8 compounded exactly and produced rungs like `0.01489`, `1.90592`,
`73.26997`.** Correct and unusable — a rung is something you hold in your head
between now and hitting it. v9 snaps each target to the nearest human number the
phase rate implies, ties rounding **up** so no step is quietly made easier. The
standard 1‑1.5‑2‑3‑5‑7.5 log-scale mantissa set reproduces his own sequence
exactly; phase 3 snaps to multiples of five instead, since that set is far too
coarse to land a 10% step at 50–150 ₿.

⚠️ **Rungs overshoot phase boundaries rather than being capped at them.** Capping
discards the growth above the boundary — at 0.95 ₿ a double gives 1.9, and a
ladder insisting the rung is "1.0" is behind reality the moment it clears. But
rounding costs the schedule the other way: v8 reached 150 in 24 steps *only* by
overshooting 50 to 73.3, so the rounded ladder is genuinely slower and the final
rung is dated to the north star date rather than a month past it.

**The cone stopped quoting nine figures.** It compounds one risk appetite to the
horizon, so upper percentiles run away. Reported percentiles now bend toward a
€40M ceiling — below a €20M knee they pass through untouched, above it they
approach and never arrive. Applied to the **reported** percentiles, not the
simulation: capping the paths themselves would change the odds the band claims to
describe while still calling it a percentile.

---

## 2026-08-21 (later) — Track rebuilt

**`/today` folded into `/hedge-track` one day after being built.** Both opened on
the same block and `/hedge-track`'s was strictly richer. What `/today` owned alone
was the signal-adherence count; that survived, the duplicate did not. It 301s
through the existing `LEGACY_ROUTES` table rather than a new handler.

⚠️ `/today`'s fill and orphan counts were never scoped to `LENS_BOOK`, so they
silently included every prop attempt — the same bug `main.py` had already fixed
for `/hedge-plan`. No prop trades fell in the window, so the numbers did not
move; the next eval would have moved them.

**The fan became a real chart.** TradingView Lightweight Charts, **vendored** into
`app/vendor/` and served from `/assets` — `/analytics` had been pulling it from a
CDN, which contradicted the no-network rule the rest of the app keeps. Drag to
pan, scroll to zoom, crosshair that reads the band under the cursor.

Bands are four **opaque** area series blended against the panel colour, not
translucent overlays: an area series fills to the bottom of the pane, so
translucent bands stack where they overlap and the P25–P75 core comes out darker
than its own edges.

**New `Next 14 days` range.** `cone()` anchors at the month start and steps per
trade, which makes it useless for "where should tomorrow land" — by the time it
reaches tomorrow it has spent its variance on days already past. `cone.near()`
anchors on today and steps per calendar **day**. Days sharing a trade count share
a band, so a day the measured rate says he would not trade reads flat.

**`Next steps` — the rung divided by the trades left.** "62% of the way to M1" is
true and useless at the moment of a trade. `track.step_plan()` divides by expected
**trades** (`days_left × trades_per_day`), not days, because a per-day figure
assumes he trades every day and the ledger says otherwise. Drawn as a staircase:
the point is that the step is small and countable.

⚠️ Three chart bugs, all self-inflicted and all invisible: `fitContent()` on the
rung range fitted *every* series including a year of balance history, squashing
the cone behind a €10k spike from February; the chart was sized from the element
it then resized, so the observer read back its own output and ratcheted to 560px
inside a 310px wrapper; and `.tk-fan{min-width:560px}` had survived from the SVG
era, which was the *actual* source of the phone overflow the wrapper-sizing had
been treating as a symptom.

**Track cut to three things.** Three paragraphs of prose under the chart deleted —
it already draws the band and the ruin floor. Signal adherence and the 30-day
score moved to `/hedge-analytics` under **Review**: they answer "how have I been
behaving", which is not a question to read before an entry. Renamed to what things
are rather than the question they were built to answer — **Tracker**, **Next
steps**, **Milestones**, **Edit milestones**, **Signal quality**. Every section
collapses and remembers its state.

⚠️ Ten rules painted read text with `--faint`, documented in `theme.py` as a
decoration token at 2.26–2.47:1 against `PRODUCT.md`'s 4.5:1 requirement. All
moved to `--dim`.

---

## 2026-08-21 — LENS places orders

**Watch-only honesty retired as a design principle.** The ledger had 147 signals
fired against 4 acted on: a decision made twice is a decision usually not made,
and the cost of that gap was larger than the risk the rule guarded. LENS now
places HEDGE entries with bracketed reduce-only TP/SL, every gate evaluated
before send, nothing sent without an explicit confirm.

**"Sent" is no longer the claim.** After a send the page polls the exchange for
5s and reports what actually changed, or warns that nothing did. A rejected order
used to report as sent.

**Partial close, and a live ticker in the ticket.** Before this, Close shut the
entire position — the dialog offered no size but all of it. It now carries the
amount with 25/50/all and relabels itself **Trim** vs **Close**.

⚠️ **The journal was borrowing plans from other trades.** Matching was direction +
recency only, so a 15-day-old plan claimed a current position. A logged plan must
now be ≤7 days old and within 5% of the actual fill. Three phantom rows (#940,
#860, #784) from `Log as open trade` were deleted — that button still writes rows
nothing ever closes.

⚠️ **Size ceiling was computed on total balance, not free margin.** Corrected.

---

## 2026-08-09

**`/hedge-track` added** — the next rung, the projection band, and whether today
counted, with everything below the rung collapsed by default. The ladder became
editable inline, posting the whole milestone list through the same versioned,
reason-required amendment path as any other plan change.

**README rewritten as the thing it describes** rather than a deploy note.

---

## 2026-08-01 → 2026-08-06 — the edge, measured properly

**The geometry was derived instead of fitted:** 0.63/1.5 → 1.42/5.66. Replaying
514 real entries showed the edge sits at *low* R:R and dies out of sample.

**One edge survived all four gates** — non-VETO shorts at R:R 1, through
permutation, sweep and leave-one-month-out. Everything else did not.

⚠️ **`FRICTION_PCT` was 0.30 against a measured 0.085**, and three tests had
encoded the old value. The desk ticket quoted maker fees while the book paid
taker. Both surfaces now price measured friction.

⚠️ **The 68.1% counted trades he could not have taken** — one position at a time
is a real constraint and the backtest had ignored it.

**Chart patterns tested as a cadence fix:** 1 survivor in 318 cells. Trade-every-
clean-bar fails sequentially at every cap and fee model — the selection *before*
the veto filter is load-bearing.

**Public site split out of the cockpit** — `/about` is the story, `/philosophy`
the system, both drawn rather than written.

---

## 2026-07-25 → 2026-07-31

**S2–S5 disarmed: the mined edge did not survive out of sample.** The front door
was redrawn around five pictures and the claim the ledger denies was cut.

**The breeder's champions must now beat a direction-matched baseline** — beating
one is not the same as making money.

**The VETO rules were tested as the scanner itself.** They cannot be, and the
reason is now recorded rather than assumed.

⚠️ **Veto stats now come from the ledger.** The frozen ones had inverted the
finding.

---

## 2026-07-24 (later)

**The breeder now runs on the 7-year window, and the depth hypothesis held.**
The first pass concluded that depth failed on *data*, not on search — so the
default window moved from 30 months of Bybit perp to the 84-month Binance spot
set `strategy_search3` stage 3 already used for deep confirmation (2.8× the
bars: 15,623 vs 5,580 on 4h). Window is now a parameter (`--window w30|deep`)
and every result records which one produced it, because they are **different
instruments**, not just different lengths — spot has no funding and a different
microstructure, so the two are never comparable bar-for-bar.

**The prediction was falsifiable and it survived.** Genomes above 3 conditions
went from **1 of 103** viable to **25 of 78** — 1% to 32%, the region grid
enumeration cannot reach. Best fitness went 0.028 → **0.112**, and holdout
samples went from a median of 33 trades to 62–187. `max_conditions=3` was a
data limit, exactly as measured; it was never a property of the search.

**⚠ The champions are NOT validated, and the top of the table should be read
with suspicion.** Two reasons, both structural:
· **65 of 78 viable genomes are LONG**, on *spot*, over a window starting
June 2019 — a period in which BTC went up roughly an order of magnitude. The
dedup pass already warned that every equity curve here inherits BTC's trend.
· **The breeder's fitness contains no baseline comparison at all.**
`strategy_search3` scores survivors against a buy-every-bar baseline and carries
a `beats_baseline` flag precisely to catch this; the GA's fitness is raw
drawdown-penalised expectancy. So "LONG · 1d · trend up · 5.0R, +185%" has not
yet been asked the only question that matters — *did it beat simply holding?*

The depth result stands on its own. The genomes are leads, not findings, until
they go through the baseline gate.

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
