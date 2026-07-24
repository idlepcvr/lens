# NEXT SESSION — LENS: Structure-trailing + pyramiding eval for DAILY_BREAK_v1

> ## ✅ BUILT — 2026-07-24 (`1caa742`). Verdict: ❌ **NO-GO**.
>
> Full write-up in `strategies/DAILY_BREAK_v1/BASELINE.md`; summary in CHANGELOG.
>
> Deliverables 1–3 and 5 shipped: `backtest.py` (all five variants, real Bybit
> funding, per-unit fees, liquidation guard, the D4 risk-ledger invariant
> asserted on every add), `sweep.py` (54 cells, median-reported),
> `test_backtest.py`, BASELINE.md filled, CHANGELOG entry.
>
> **Deliverable 4 (`strategy.pine` v1.1.0) was correctly NOT built.** It was
> conditional on a variant winning by D7. None did, so the Pine stays at v1.0.0.
>
> **The answer is not the one D7 had a branch for.** The control loses money:
> variant A is PF 0.51 / WR 21.2% on n=104. Wins land at +2.85R and losses at
> −1.11R — exactly the geometry this spec designed, with fees behaving as
> modelled — so breakeven WR is 28.0% and it realizes 21.2%. **The entry is not
> selective enough; exits were never what was wrong.** All 54 sweep cells lose.
> Because A's PF is under 1, D7's "1.2× A's PF" gate sits *beneath breakeven*,
> so `verdict()` says that out loud rather than letting a losing variant print
> as ADOPT.
>
> The trail did work as specified — max drawdown 23.9% → 16.3%, giveback 1.32R →
> 2.10R. Pyramiding held its discipline: 11 adds taken, 9 refused by the
> invariant. Neither can rescue a negative-expectancy entry.
>
> Also worth knowing: built for the >24h hold bucket, the 1h version averages
> **14 hours** in trade. It never reached the bucket it was designed to exploit.
>
> *Everything below is the original 2026-07-14 spec, kept for provenance.*

---

*Handoff file. **Fable made every design call below on 2026-07-14**; Opus executes.
The previous spec (Goal Ladder, ✅ built 2026-07-09) lives in git history at
`e1e52cc^` and in CHANGELOG.*

---

## What this is and is NOT

**Is:** a backtest-only evaluation of two exit/add mechanics (Darvas-style
structure trailing, and pyramiding) against `DAILY_BREAK_v1`'s designed fixed-3R
exit. The strategy was specced 2026-06 but its `BASELINE.md` was never filled —
this build runs the baseline AND the variants in one pass.

**Is NOT:** a live change, a new page, auto-execution (never), or a reason to
trade. Measured live edge is −6.6%/mo; the #1 lever remains discipline, not
exits. This is strategy R&D that ends in a filled BASELINE.md and a go/no-go
paragraph. Paper only.

---

## Concepts being tested (context for the builder)

**Structure trailing (Darvas):** no fixed take-profit. After entry, the stop
ratchets up beneath each successive "box" the trend builds — here, each completed
UTC day's low (for longs). Exit happens when price falls back through the last
box floor. Winners are open-ended; the trend decides the exit, not a 3R limit.

**Pyramiding:** when the market builds a new box above the last one and breaks
out again, add to the position — but only when the trailed stop already locks
the earlier units at ≥ breakeven, so an add never puts back at risk what the
trade has banked. The invariant (below) formalizes this.

**Why it might beat fixed 3R here:** DAILY_BREAK_v1 was built for multi-day
holds (the PF 1.62 / WR 56% >24h bucket in the PRISM fingerprint). A fixed 3R
amputates exactly the multi-day runners the premise selects for. Whether the
giveback on retraces (amplified by leverage + funding on longer holds) eats
that benefit is an empirical question — that's what this backtest answers.

---

## Design decisions (all ANSWERED — do not re-open)

### D1 · The "box" = the completed UTC day
For longs: once a UTC day closes whose low is above the current stop, the stop
moves to `that day's low − 0.25 × ATR(14, 1h)` (buffer against wick-hunts).
Symmetric for shorts (day high + buffer). The stop only ratchets — never widens.
Why days, not pivots: the strategy's entry level is already the daily range;
using the same structural unit for exits keeps one concept, and 1h pivot-based
trails are noise on crypto. No Darvas "3-touch box confirmation" — a completed
day IS the box; don't add ceremony.

### D2 · Breakeven rule
When unrealized profit ≥ +1R (R = entry-to-initial-stop distance), stop moves to
entry + fees (breakeven-plus). This is a parameter (`be_at_r = 1.0`, `None`
disables) and one of the swept axes — at 10× leverage a full −1R giveback from
+1R open is a 20%-of-margin round trip, so test both.

### D3 · Variants (the whole matrix — 5 cells, no more)
| ID | Exit | Adds |
|---|---|---|
| A | fixed 3R (designed baseline) | none |
| B | pure trail (D1+D2), no TP | none |
| B+P | pure trail | pyramiding (D4) |
| C | 50% off at +2R, trail rest | none |
| C+P | 50% off at +2R, trail rest | pyramiding on remaining |

A is the control and fills the original BASELINE.md table. Do not invent
variant D.

### D4 · Pyramiding rules
- Trigger: while in a position, a NEW `DAILY_BREAK_v1` long signal fires (same
  entry logic: first 1h close above the now-current previous-day high, volume
  spike, gates all pass).
- Add size: **0.5 × initial unit** (in risk terms). Max **2 adds** per position.
- After an add, the D1 trail governs the ENTIRE position at one stop.
- **Risk-ledger invariant (the core rule):** an add is permitted only if, at the
  current trailed stop, total position P&L-if-stopped (all units, entry fees +
  exit fees + funding accrued included) ≥ **−1R of the ORIGINAL unit**. The
  trade's worst case never exceeds what was risked at entry — adds are financed
  by locked-in trend profit, never by new account risk. Assert this in code on
  every add; it is the difference between pyramiding and martingale-adjacent
  size creep.

### D5 · Leverage / perp mechanics the backtest MUST model
These are why equity-market Darvas doesn't transfer for free:
- **Fees on notional:** 0.05%/side (Bybit taker-ish). At 10× that's 0.5% of
  margin per side, ×2 sides, ×(1 + adds) entries. Pyramiding multiplies fee
  events — model per-unit.
- **Funding:** perps pay/receive every 8h on notional. Multi-day trail holds
  make this material: at a typical +0.01%/8h a 5-day 10× long pays ~1.5% of
  margin in funding alone. Use **Bybit historical funding** via ccxt
  `fetch_funding_rate_history` (BTCUSDT); fall back to flat ±0.01%/8h
  (parameter) if the fetch is painful. Longs PAY positive funding — do not
  model it as free, and do not assume it nets to zero.
- **Liquidation guard:** at 10× isolated, liq ≈ 9.5% adverse (1/lev − ~0.5%
  maintenance). Assert `stop distance < 0.8 × liq distance` at entry and after
  every add (adds raise average entry → move liq closer). If violated, skip the
  add / reduce leverage tier — never let the exchange be the stop.
- Confluence sizing tiers from the strategy (10×/5%, 7×/3%, 5×/2%) apply to the
  INITIAL unit; adds inherit the position's leverage.

### D6 · Data + harness
- **Copy the pattern from `strategies/TREND_4R_v1/backtest.py`** (ccxt fetch →
  indicator frame → bar loop → results table). Same style, same repo
  conventions. New file: `strategies/DAILY_BREAK_v1/backtest.py`.
- **⚠ Fetch 1h OHLCV from BYBIT, not Kraken.** Kraken's OHLC endpoint caps at
  ~720 candles regardless of `since` — 12 months of 1h needs ~8,760 bars.
  Bybit paginates fine in ccxt. (TREND_4R got away with Kraken only because
  4h × 720 nearly covered its window.)
- Range: 24 months (regime diversity: chop + trend legs). Warmup-trim the first
  200 daily bars for the 200-EMA gate.
- Replicate the Pine gates exactly: prev-day H/L break with `[1]` first-cross
  guard, vol > 1.4× 20-SMA, min prev-day range 0.4%, daily-200-EMA bias,
  weekly-trend gate, skip Sat, skip 02/11 UTC, 07–21 UTC session, 60-min
  cooldown. Intrabar fill rule: same as TREND_4R harness (stop checked against
  bar low/high, conservative ordering — if both stop and box-break hit in one
  bar, stop first).

### D7 · Success criteria (write the verdict against these, no vibes)
Adopt a trail variant over A only if, on the same trade set:
1. Net PF (after fees + funding) ≥ **1.2 × A's net PF**, and
2. Max drawdown ≤ **1.25 × A's max DD**, and
3. n ≥ 30 closed trades in the window (else verdict = "insufficient sample",
   full stop).
Otherwise the verdict is "fixed 3R stands" — that is a fully successful
outcome, record it and stop. No parameter-fishing beyond the declared sweep.

### D8 · Sweep (bounded)
One sweep file (`sweep.py`, TREND_4R pattern): `be_at_r ∈ {None, 0.5, 1.0}`,
trail buffer ∈ {0.15, 0.25, 0.40} × ATR, partial-at ∈ {1.5R, 2R} (C only).
That's it. Report the median cell, not the best cell — the best cell of a
45-cell sweep is noise.

---

## Deliverables
1. `strategies/DAILY_BREAK_v1/backtest.py` — variants A/B/B+P/C/C+P, funding +
   fee + liq modeling per D5, invariant assertions per D4.
2. `strategies/DAILY_BREAK_v1/sweep.py` — D8 grid, median-reported.
3. `strategies/DAILY_BREAK_v1/BASELINE.md` — filled: the original baseline
   table (variant A) + a variants table (net PF, WR, max DD, avg hold, funding
   paid, fees paid, avg MFE-giveback) + the D7 verdict paragraph.
4. ONLY IF a variant wins by D7: `strategy.pine` v1.1.0 adding trail/pyramid as
   input-gated options (default OFF; Pine needs `pyramiding=2` in the
   `strategy()` declaration or adds are silently ignored — known gotcha).
   Version bump per strategies/README rules. If no variant wins, do not touch
   the Pine.
5. One line in CHANGELOG. Commit to master (repo convention), do not push.

## Build order
1. Harness with variant A only → sanity: trades fire, fills look right,
   fees/funding sum plausibly. Fill original BASELINE table.
2. Add D1/D2 trail → variant B, C.
3. Add D4 pyramiding + invariant asserts → B+P, C+P.
4. Sweep, BASELINE.md verdict, CHANGELOG.

Out of scope, explicitly: live wiring, signal-schema changes, new app pages,
other strategies, auto-execution (never), funding-arb ideas, any ML.
