# NEXT SESSION — LENS

> ## ✅ BUILT — 2026-07-09. Every phase below shipped; see CHANGELOG.
>
> C1+C2 `44cfb85` · C5 `def9ea2` · C3 cone `520fb81` · Stage B `3fb4eee` ·
> C4 `5dbc7d8` · C6 `e77e71f` · C3 stack projection `a220aa7`.
>
> Three things were built differently than specced, on purpose:
> · **Coverage counts €0 prop payouts.** Evaluation P&L isn't cash and there's no
>   funded account; counting it would let a paper account pay the rent.
> · **The journal has no weekly-review row**, so the status word went in its
>   header rather than inventing the row.
> · **The cone bootstraps EUR P&L, not per-trade returns.** `trades.balance_after`
>   is not account equity on this ledger (70/489 rows imply |return| > 60%).
>
> Open follow-ups, in order:
> 1. **Log a stack snapshot** on `/goal` — until then milestone dates and the
>    stack projection have nothing to derive from.
> 2. Forward-test the live loop (README `## Next` item 1) — still outranks
>    anything below.
> 3. C4's day-range proxy ignores intraday path; upgrade to session-window ranges
>    only if the badge misleads in practice.
>
> *Everything below is the original 2026-07-06 spec, kept for provenance.*

---

*Handoff file. Opus briefs the problem → **Fable decides the design** → Opus
executes it. **Fable made all calls below on 2026-07-06** (inside the closing
Fable window). Opus: build in the phase order at the bottom, verify each phase
in-browser before the next. No new dependencies, no new frameworks — SQLite
tables + existing pages extended.*

**Why this exists (doctrine):** Lucky re-writes the plan every iteration while
the goal never moves. This build cages plan-churn: goal locked + amendment log,
milestones as the progress surface, projection cone as the honesty surface,
regime-realism so Fit stops proposing corridors the market isn't offering.
Decisions it changes: (1) weekly — "am I inside the cone?" instead of "should I
rewrite the plan?"; (2) at Fit time — "is this envelope actually on offer in
this regime?"

---

## Stage B — Fit envelope → search filter (decisions ANSWERED)

1. **Where the filter lives:** a "Feasible only" toggle on the existing `/edge`
   search (`app/search_custom.py`). No new surface.
2. **Envelope membership:** scored distance, not a hard box. Normalize each axis
   (WR / R / trades-per-week / geometry) to the envelope's min–max span; distance
   0 = inside → "FITS" badge. Near-misses still rank (lower), each showing which
   axis fails and by how much. The most useful information is *how close*, a hard
   box throws it away.
3. **Envelope handoff:** Fit persists a machine-readable envelope on every sweep —
   JSON row in SQLite (`fit_envelope`: id, created_at, goal-params snapshot,
   min/max per axis). Search consumes the latest; stale (>7 days) shows a
   "re-run Fit" nudge instead of silently filtering on old numbers.
4. **Empty-result UX:** the most valuable state, say it plainly:
   *"The corridor is empty — nothing in the strategy library fits this envelope.
   At these constraints the goal is not reachable with anything you can currently
   trade. Nearest miss: <strategy> (fails on <axis>: needs X, has Y)."*
   Plus the Stage C4 realism badge, so an envelope that is populated on paper but
   regime-starved is also called out.

---

## Stage C — the Goal Ladder (locked plan · milestones · cone · realism)

### Lucky's ratified inputs (2026-07-06 — these are the plan, not suggestions)
- **North star:** 150 BTC by 2032-12-31.
- **Goal:** 50 BTC by **2028-12-31** (hard date).
- **Milestone "income complete":** ~5 BTC / ≈€300k — 4% covers rent/net-salary
  needs; the FIRE-lite threshold.
- **Two-level tracking:** projection cone tracks the ENGINE (LENS equity + prop
  payouts — where the math is real); milestone ladder tracks the TOTAL STACK
  (existing BTC + savings + engine inflows). Engines are inputs, the stack is
  the score.
- **Unit:** milestones in **BTC units**, fiat converts at spot when stacked —
  tracking needs no price forecast. Price scenarios appear ONLY in projections.
- **Lock mechanic:** amendment log (versioned, reason required, history shown).

### C1 · Locked plan + amendment log
- New table `goal_plan`: id, version, created_at, north_star_btc, north_star_date,
  goal_btc, goal_date, milestones (JSON array of {btc, label}), price_scenarios
  (JSON {bear, base, bull} annual %), **burn_monthly_eur** (seed ≈ €2,800 ≈ $3,000 —
  amendable like everything else), amendment_reason, active (bool).
  Versions are append-only; never delete. Seed v1 with the ratified inputs.
- Default milestone ladder (BTC): **0.1 → 0.25 → 0.5 → 1 → 2 → 3.5 → 5
  ("income complete") → 8 → 12 → 20 → 32 → 50** — roughly geometric so each
  stage is a similar % climb, i.e. similar *felt* difficulty. Labels/gamified
  stage names: Opus's call, keep them short.
- Milestone **dates** are derived, not stored: constant-CAGR interpolation from
  (current stack, today) → (50, 2028-12-31), recomputed only when a snapshot or
  amendment lands. The dates move with reality; the BTC rungs never do.
- `/goal` gets a **"Use measured" button** (Lucky's request 2026-07-06): fills
  win_rate, realized R (avg_win/avg_loss), trades_per_week, and fee drag from
  the trade ledger (n-guarded: greyed out with "n=X, need 30+" below threshold;
  optional 90-day / all-time toggle). Typed assumptions stay possible but the
  UI labels each field **typed** vs **measured** — the whole point is making
  the two visually impossible to confuse.
- `/goal` gets a **Plan panel**: read-only current plan + "Amend" flow that
  requires a reason (min 20 chars) and bumps version. Panel permanently shows
  *"v<N> · amended <N-1> times · last: <reason>"*. That line is the cage.

### C2 · Stack snapshots
- New table `stack_snapshot`: date, btc_total, note. Manual entry, monthly
  cadence (form on `/goal`; nag on the goal hero if >40 days stale).
- Engine equity already exists via kraken/bybit sync + `/money` — reuse, don't
  duplicate.

### C3 · Projection cone on the equity curve (`/analytics`)
- Monte Carlo bands **P10 / P25 / P50 / P75 / P90** from actual trade history
  (realized expectancy, variance, actual trades/wk). **n-guard:** if n < 30
  trades, fall back to plan parameters and badge the cone "plan-assumed —
  insufficient sample (n=X)". Never show a history-based cone on 6 trades.
- Cone runs today → next milestone's derived date, drawn on the existing equity
  curve. **Re-anchor monthly, not daily** — daily re-anchoring hides drift;
  monthly keeps deviation visible (this is the Bollinger-band feel he asked for,
  but anchored to plan, not to price).
- One status word derived from position vs bands: **AHEAD** (>P75) / **ON**
  (P25–P75) / **BEHIND** (P10–P25) / **OFF-PLAN** (<P10). This word is reused by
  C5 everywhere; compute it in one place.
- Stack-level projection (on `/goal` only): engine cone → EUR → BTC at the three
  flat-CAGR price scenarios from `goal_plan` (defaults bear −20% / base +15% /
  bull +50% p.a.) → shows the *range* of dates 5 BTC and 50 BTC land. Three
  lines, no extra Monte Carlo.
- **Two curve shapes, don't conflate them (2026-07-06):** prop accounts are a
  linear PAYOUT STREAM — profit is withdrawn, the account never compounds;
  monthly surplus = payout × take-home − burn, converted to BTC at spot and
  added to the stack. Personal accounts (Kraken) COMPOUND. The stack projection
  sums both: Σ(prop surpluses)/price + personal-equity growth. A `n_accounts`
  multiplier (default 1) on the prop stream is enough to model scaling —
  do NOT build a prop-firm scaling-plan simulator.
  Honest baseline this encodes: one 200k account at the 45%/2.5R cell stacks
  ~2.4 BTC in 24 months — the ladder's derived dates must be allowed to say
  "5 BTC ≈ 2031" without anyone re-typing the goal.

### C4 · Regime-realism check on Fit (pairs with Stage B)
- The complaint this fixes: Fit says "7 trades/wk at 7% moves, 2× lev" — feasible
  on paper, unavailable in the market actually on offer.
- Inputs already exist: `regime.py` (current regime + history) and
  `volatility.py` (daily range distribution).
- Check: for the envelope's required TP move (underlying_win_pct from the goal
  model), compute the fraction of the last 90 days — AND of days within the
  current regime — whose range ≥ that move. Convert to offered-setups/week and
  compare to the envelope's required trades/week.
- Output: a badge on Fit results + `/edge` search rows:
  **OFFERED** (supply ≥ 1.5× need) / **TIGHT** (0.75–1.5×) / **STARVED** (<0.75×),
  always with the numbers: *"needs 7/wk · regime offers ~2/wk"*.
- ponytail: day-range vs required-move is a proxy (ignores intraday path and
  session timing). Ship the proxy; upgrade to session-window ranges only if the
  badge misleads in practice.

### C5 · Scenario Ladder on `/goal` (Lucky's request 2026-07-06)
- A 2-D matrix card, pure client-side math (no API changes — the one-axis
  sensitivity tables already on `/goal` are the pattern; this is their 2-D
  sibling):
  - **Rows:** win rate 25% → 55%, step 5. **Cols:** realized R = 1, 1.5, 2,
    2.5, 3, 3.5, 4.
  - **Cell:** EV/trade after fees = `WR×(1+R) − 1 − fee_R`, and the monthly %
    it implies at current risk-per-trade and trades/month:
    `(1 + risk × EV)^tpm − 1`. Show monthly % big, EV small.
  - Color by sign; draw the **breakeven frontier** (WR = (1+fee_R)/(1+R)) as
    the visible boundary between red and green cells.
  - Pin two markers: **MEASURED** (WR + realized R from the ledger, n-guarded,
    same source as the "Use measured" button) and **PLAN** (the typed
    assumptions). The entire argument "what I claim vs what I've shown" is
    the distance between those two pins — make it visible at a glance.
- ponytail: static grid, no interactivity beyond the existing form inputs
  driving fee_R/risk/tpm; add per-cell tooltips only if asked later.

### C6 · Surfacing (small, last)
- **Goal hero** (`goal_hero.py`): current stage, next milestone + derived date,
  progress %, the C3 status word, and the **coverage ratio** = trailing-3mo
  engine cash flow (prop payouts + LENS realized P&L) ÷ `burn_monthly_eur`.
  "Income complete" (the 5-BTC-adjacent milestone) fires on coverage ≥ 1.0 for
  6 consecutive months — per the doctrine's stress-test rule 3, NOT on 4%
  withdrawal math. Context line under it: required return at current funded
  size to cover burn (e.g. "$200k × 80% take-home → needs ~1.9%/mo") — the
  honest bar, so the UI never lets 5–9%/mo become the silent assumption.
- **Calendar**: month header gets month-end P50 target vs actual, colored by the
  status word.
- **Journal**: weekly review row gets "vs plan: <status word>" next to the
  existing execution grade — "executed correctly" and "on plan" are different
  questions; show both.

---

## Build order (each phase verified in-browser before the next)

1. **C1 + C2** — tables, seed v1 plan, Plan panel + "Use measured" button, snapshot form. Small, unblocks everything.
2. **C5** — Scenario Ladder grid on /goal (client-side only; pairs naturally with the "Use measured" pin, so build it right after C1).
3. **C3** — cone on analytics + the status word.
4. **B** — envelope persistence + "Feasible only" toggle + empty-state.
5. **C4** — realism badge (needs B's envelope).
6. **C6** — hero/calendar/journal surfacing.

Out of scope, explicitly: auto-execution (never), new pages beyond the Plan
panel, daily re-anchoring, per-strategy cones, any ML. Forward-testing the live
loop (README `## Next` item 1) still outranks this build if time is short.
