# WISHLIST — Strategy breeder + veto visibility

*Captured 2026-07-18 from the Algory 2.0 teardown (algory.app). This is a
**wishlist, not a ratified spec** — design calls marked OPEN are still open.
Separate file on purpose: `NEXT_SESSION.md` holds the DAILY_BREAK_v1
trailing/pyramiding spec, still unbuilt, untouched by this.*

---

## Item 0 · Log vetoed setups (small, approved, do first)

**Problem, measured.** Last short signal fired 2026-07-08. Replaying the 10 days
after it: only 5 short-setup matches existed at all, and the 2 that weren't
already emitted (both S2, 2026-07-14 14:00 and 18:00 UTC) were vetoed and
**silently discarded**. `app/setups.py:435` — `if not m["clean"]: continue`.
No row, no notification, no trace. The feed showed longs only, so the engine
looked asleep when it was in fact working.

The vetoes were correct. From his own ledger:

| short bucket | n | pnl |
|---|---|---|
| `slope_against,sweep_fade,pd_raid_fade` (killed 07-14 #1) | 24 | −€1,254 |
| `slope_against,pd_raid_fade` (killed 07-14 #2) | 13 | −€1,833 |
| S1 clean | 12 | +€956 |

Being right is not the issue. Being invisible is.

**Build:** persist vetoed matches instead of dropping them. `insert_signal()`
already takes `auto_rejection_reason` and the veto list is already computed
(`vetoes(ctx, direction)`), so this is a status, not a new pipeline. Show them
in the signals feed as blocked cards: setup ✓ / which filters ✗ / the realized
ledger stat for that veto bucket. No notification (blocked ≠ actionable).

**Why it matters beyond UX:** with no log of blocked setups there is no
denominator. Nobody can ask "would I have made money taking the vetoed ones?"
`/robustness` has a veto counterfactual panel but it runs on closed trades —
it cannot see setups that never became trades.

⚠️ Also check whether S2 is dead code. Its definition (premium of 7d range +
bear displacement) structurally implies up-slope + fresh PDH raid, which trips
`slope_against` + `pd_raid_fade` automatically. Both 07-14 candidates died that
exact way. Either S2 or those vetoes is wrong for shorts. Item 0's log is what
produces the evidence to decide.

---

## Item 1 · Genetic strategy breeder

**Why, functionally.** `strategy_search3` evaluated 43,703 combos → 933
survivors, but is capped at `max_conditions=3` — because grid enumeration
explodes, not because 4+ conditions are uninteresting. A GA searches deeper
genomes without enumerating the space. That is the whole functional case.

**Not in scope:** Algory's visual layer. No neural map, no orbiting nodes, no
helix, no embers. Functional only.

**Reuse, do not rebuild** (most of this exists):
- `app/backtest_engine.py` — real fills, fees, slippage. The fitness evaluator.
- `app/strategy_search3.py` — `SLOTS` condition vocabulary = the gene pool;
  dynamic ATR geometry (`k`, `rr`) = genes, not post-filters.
- The three honesty gates (split-half n≥40 · geometry neighbourhood · 7-year
  deep confirm) — these become the **fitness function**, not a post-screen.

**Genome shape** (borrowed from Algory's gene categories, mapped to LENS):
`signals` (entry conditions from SLOTS) · `bias` (direction, timeframe) ·
`filters` (session window, vol regime) · `execution` (k × ATR stop, R multiple) ·
`management` (cooldown, once-per-day, skip-Saturday).

**The one non-negotiable design constraint.** Fitness must be measured
**out-of-sample**. A GA is an overfitting machine pointed at a fitness function;
if fitness is in-sample PF, it will breed a curve-fit champion every time and
report it proudly. Even Algory's own page cites "actual out-of-sample trades" of
strategies under test. Concretely: evolve on the first half, score on the held-out
second half, and confirm on the 7-year deep set — a genome that only wins
in-sample gets culled, not vaulted.

**Related, worth stealing (functional):** Algory's diversity tracker computes
correlation from *actual equity curves*, not strategy labels — "real correlation,
not label variety." A vault of 933 survivors is almost certainly full of
near-duplicates. Correlation-based deduplication of survivors is probably higher
value per hour than the GA itself, and is a much smaller build. **Consider doing
this before Item 1** — it may reveal that the 933 are really ~20 ideas.

> **DONE 2026-07-24 — and the hypothesis was wrong.** `app/strategy_dedup.py`.
> The 933 are **525 ideas**, not ~20; the 402 baseline-beaters are **230**. The
> median pair of survivors shares **1.3% of its entry bars** and 0% of its
> realized trades. This vault is not full of near-duplicates — it is genuinely
> wide, and the GA is therefore searching a space that is already diverse
> rather than one that needs unpacking.
>
> Two things the build settled that the breeder must inherit:
>
> 1. **Correlation of equity curves is the wrong instrument here**, measured,
>    not argued. These survivors trade ~59 days out of 770 and the median pair
>    shares *one* active day, so Pearson on daily pnl is dominated by mutual
>    zeros. Algory can use it because Algory's strategies trade often; LENS's
>    do not. The diversity tracker must use entry-mask overlap.
> 2. **Geometry re-shuffles realized trades far more than expected.** Two
>    genomes with *identical* entry conditions differing only 3.0R vs 5.0R
>    share just 0.38 of their realized trades — a different exit frees the
>    position at a different bar, so a different set of later signals gets
>    taken. Consequence for the GA: `execution` genes are not a cosmetic tail
>    on the genome, they materially change which trades exist. Fitness must be
>    evaluated per full genome, never by scoring a condition set once and
>    sweeping geometry over it afterwards.
>
> Counts are bounds, not a point estimate: mask overlap (525/230) is the upper
> bound, realized-trade overlap the lower. Both agree the vault is wide.

### Design calls — RATIFIED 2026-07-24
1. Population size, generations, mutation/crossover rates, cull fraction —
   **left to the builder.** Tuning knobs, cheap to change after the first run;
   not worth blocking on. Start small enough that a generation runs in minutes.
2. Fitness scalar — **drawdown-penalised expectancy in R**: mean R per trade
   over max drawdown in R, scored out-of-sample. Raw PF was rejected because it
   is blind to path and will happily breed a champion with one catastrophic hole.
3. Minimum `n` per genome — **n ≥ 40 out-of-sample**, matching the split-half
   gate already in `strategy_search3`. One standard, not two.
4. Paper-only R&D. **Confirmed.** Auto-execution is never in scope.
5. Output — **still open.** Dedup writes `strategy_clusters_<scope>.json`
   alongside `strategy_search.json` rather than extending it; the breeder can
   follow that pattern or claim a vault table. Decide when there is output.

Still genuinely unbuilt: everything in Item 1 above. The dedup was the
prerequisite, and it is done.

### Standing context for whoever builds this
Measured live edge is −6.6%/mo geometric; mining says the #1 lever is not
trading VETO contexts. A better strategy generator does not fix a discipline
problem. Ship Item 0 first — it is small, it is already agreed, and it produces
the data the breeder's fitness function should ultimately answer to.
