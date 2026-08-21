# DONE — 2026-08-22 · Track rebuilt, ladder phased and rounded

[Open as HTML](DONE-2026-08-22-track-rebuild-phased-ladder.html)

*Archived from `NEXT_SESSION.md`. Five commits, `3ca5619` → `9592c3c`, plus plan
versions v8 and v9 written to `goal_plan`.*

---

## What this was

Track opened as a page with two jobs it was doing badly: it duplicated `/today`'s
opening block, and everything below the rung was either a chart nobody could
zoom or prose nobody read. It now answers three questions and stops: what is the
rung, am I inside the band, what does the next trade have to make.

The ladder underneath it changed shape twice — first to real phases, then to
numbers a person can actually hold in their head.

---

## `/today` folded into `/hedge-track` — `3ca5619`

Both pages opened on the same block. `/hedge-track`'s version was strictly
richer, so `/today` was a day-old duplicate of a page that already existed.

What `/today` owned alone was the adherence count — signals fired against fills
that had a signal behind them. That survived; the rest went. `/today` 301s
through the existing `LEGACY_ROUTES` table rather than a new handler.

**Bug fixed on the way:** `/today`'s fill and orphan counts were never scoped to
`LENS_BOOK`, so they silently included every prop attempt — the same bug
`main.py` had already fixed for `/hedge-plan`. No prop trades fell inside the
window at the time, so the numbers did not move; the next eval would have moved
them.

---

## A real chart — `d91bb2e`

The fan was ~70 lines of hand-built SVG with three preset ranges and no way to
look closer. It now uses TradingView Lightweight Charts: drag to pan, scroll to
zoom, crosshair that reads out the band under the cursor.

**The library is vendored** at `app/vendor/` and served from `/assets`.
`/analytics` had been pulling it from unpkg, which contradicted the no-network
rule the rest of the app keeps — a chart that fails to load offline takes the
page's whole answer with it. That page loads the local copy now too.

Bands are painted as four opaque area series blended against the panel colour,
not as translucent overlays. An area series fills from its line to the bottom of
the pane, so translucent bands stack where they overlap and the P25–P75 core
comes out darker than its own edges. Painting p90/p75/p25/p10 in descending
order lets each repaint the region below it.

**Two bugs, both mine, both invisible:**

- `To the rung` called `fitContent()`, which fits *every* series — including a
  year of balance history. The cone was squashed into the right-hand edge behind
  a €10k spike from February. Each range now fits the projection's own span.
- The chart was sized from the element it then resized, so the observer read
  back its own output and the container ratcheted to 560px inside a 310px
  wrapper — horizontal scroll on a phone. It measures the wrapper now, whose
  width CSS owns and the chart cannot touch.

A third surfaced later: `.tk-fan{min-width:560px}` had survived from the SVG era,
which needed a scroll floor to stay readable. That was the *actual* source of
the overflow; the wrapper-sizing had been treating a symptom.

---

## A band for tomorrow — `d91bb2e`

`cone()` anchors at the month start and steps per trade, because that is the
horizon a milestone is measured on. That makes it useless for "where should
tomorrow land" — by the time it reaches tomorrow it has spent its variance on
days that are already history.

`cone.near()` anchors on today and steps per calendar **day**, converting a day
into an expected trade count from the measured trades-per-week rate. Days that
share a trade count share a band, so a day the rate says you would not trade
reads flat. A band that fanned out on a quiet Sunday would be a lie.

---

## Next steps — the rung divided by the trades left — `7ce35b1`

"62% of the way to M1" is true and useless at the moment of a trade. Nobody
sizes an entry against a percentage of a milestone.

`track.step_plan()` divides the rung by expected **trades** — `days_left ×
trades_per_day` — not by days, because a per-day figure assumes you trade every
day and the ledger says otherwise. Drawn as a staircase, because the point is
that the step is small and there is a countable number of them.

The staircase floor is anchored just under where the stack has been, not at
zero. Zero-anchored, twelve compounding 4% trades all land between 62% and 100%
of the height and render as twelve identical bars — flattening the exact thing
the section exists to show.

Everything is in **stack** euros. The rung is a BTC target and the stack is what
gets measured against it; a step in account-equity terms would answer a
different question than the hero above it asks.

---

## Cut to the three things it is for — `52a8bab`

Gone from the page: three paragraphs under the chart (the near-band summary, the
fan explainer, the ruin warning). The chart already draws the band and the ruin
floor is already a red line on it.

Also gone, to `/hedge-analytics` under a **Review** heading: signal adherence and
the 30-day score. Both answer "how have I been behaving", which is a review
question, not something consulted before an entry. Hedge-only there, since both
are scoped to `LENS_BOOK`.

Renamed to what things are rather than to the question they were built to
answer: **Tracker**, **Next steps**, **Milestones**, **Edit milestones**, and
**Signal quality**. Every section collapses, and the state is remembered per
section in `localStorage` — a section you have to re-minimise on every load is
not really minimisable.

**Bug fixed:** the score table has five columns and ran past its panel border on
a phone. It scrolls inside its own container now.

**Contrast:** ten rules on Track painted read text with `--faint`, which
`theme.py` documents as a decoration token at 2.26–2.47:1 while `PRODUCT.md`
requires 4.5:1 of body text. All moved to `--dim`. Struck-through cleared rungs
keep `--faint` deliberately — line-through already carries "cleared", so colour
is not the only signal.

---

## The ladder got phases — `9592c3c`, plan v8

The ladder had run three different rates since v7, but the rates lived only as
prose inside `amendment_reason`. Nothing could read them, so no page could say
which phase you were in.

`goal_plan.phases` is now a real column — `[{name, to_btc, rate_monthly}]` —
carried through `amend()` like any other amendable field, with an additive
migration. NULL parses as `[]`, since every plan up to v7 genuinely was one flat
rate.

**Rates: 100% / 50% / 10%.** Phase 1 doubles to 1 BTC rather than running 60%:
the gap from here to 1 BTC is small in absolute terms, so the rate that clears
it costs little risk per trade, and reaching phase 2 sooner matters more than
the rate inside phase 1.

**Rungs overshoot phase boundaries rather than being capped at them.** Capping
discards the growth above the boundary — if you are at 0.95 ₿ and double, you
have 1.9, and a ladder insisting your rung is "1.0" is behind reality the moment
you clear it. Capping cost roughly five months to the north star.

---

## The cone stopped quoting nine figures — `9592c3c`

The projection compounds one risk appetite to the horizon, so upper percentiles
run away. P90 in the tens of millions says nothing except that exponentials are
exponential.

Reported percentiles are bent toward a €40M ceiling: below a €20M knee they pass
through untouched, above it they approach and never arrive. Applied to the
**reported** percentiles, not the simulation — capping the paths themselves
would change the odds the band claims to describe while still calling it a
percentile.

---

## Plan v9 — every rung a number a person aims at

v8 compounded exactly and produced `0.01489`, `1.90592`, `73.26997`.
Arithmetically correct and unusable: a rung is something you hold in your head
between now and hitting it.

v9 snaps each target to the nearest human number the phase rate implies, ties
rounding **up** so no step is quietly made easier. The standard 1‑1.5‑2‑3‑5‑7.5
log-scale mantissa set reproduces his own sequence exactly. Phase 3 snaps to
multiples of five instead — the mantissa set is far too coarse to land a 10%
step at that scale.

```
0.015 → 0.03 → 0.05 → 0.1 → 0.2 → 0.5 → 1
   → 1.5 → 2 → 3 → 5 → 7.5 → 10 → 15 → 20 → 30 → 50
      → 55 → 60 → 65 → 70 → 75 → 85 → 95 → 105 → 115 → 125 → 140 → 150
```

| | |
|---|---|
| Whole coin | 2027-03-01 |
| GOAL 50 | 2028-01-01 |
| NORTH STAR 150 | **2028-12-31** |

Rounding costs the schedule. v8 reached 150 in 24 steps only by overshooting 50
to 73.3; landing exactly on 1 and 50 is rounder and slower. The final rung is
dated to the north star date rather than a month past it — the last step is +7%,
so pulling it a day earlier costs nothing real.

**`0.2 → 0.5` is +150%,** the one rung harder than its own phase rate. Kept
because 0.5 is the target that means something and 0.4 is not.

### What the ladder actually asks for

| phase | steps | geo mean/mo | min | max | per trade |
|---|---|---|---|---|---|
| Acceleration | 6 | **101%** | 67% | 150% | 2.14% |
| Growth | 10 | **48%** | 33% | 67% | 1.19% |
| Maintenance | 12 | **10%** | 7% | 13% | 0.28% |
| whole ladder | 28 | **39%** | 7% | 150% | |

Median month 33%. Only **5 of 28 months** ever ask for 100% or more, and the
last is 2027-03. Per-trade figures assume the measured 1.08 trades/day.

---

## 🔴 The finding that outranks everything above

The ladder needs **+2.14% per trade** through Acceleration. The ledger says:

| | | expectancy |
|---|---|---|
| all time (527) | WR 39.1%, RR 1.32 | **−0.206 R/trade** |
| last 90d (84) | WR 32.1%, RR 1.54 | **−0.260 R/trade** |

The measured edge is **negative**, and no position size converts that. At 39%
win rate risking 2%, RR 2.0 returns +0.12% per trade against the 2.14% needed —
18× short. Roughly **5R** clears it. The lever is the reward multiple, not the
risk amount.

Everything in this document is instrumentation. None of it changes that number.
