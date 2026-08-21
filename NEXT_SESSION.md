# LENS — Next session

[Open as HTML](NEXT_SESSION.html)

*Written 2026-08-21 after LENS placed, bracketed, verified and trimmed its first
live orders. The previous list is archived at
`docs/DONE-2026-08-21-execution-live-orders-veto-override.md` — all five items
done, plus partial close.*

## The main piece: three phases, not one climb

The ladder is now 28 even monthly rungs at 35.9%/month, which is honest arithmetic
but a single undifferentiated slope. It isn't one journey. It's three, and they
demand completely different behaviour:

| phase | from → to | duration at 35.9%/mo | what it actually is |
|---|---|---|---|
| **1 · Acceleration** | 0.00931 → **1 BTC** | ~15 months | the hard part. Small account, every rung a large % move, no margin for a bad week |
| **2 · Growth** | 1 → **50 BTC** | ~13 months | the same rate on a base that can absorb a loss. Position sizing stops being the constraint |
| **3 · Maintenance** | 50 → **150 BTC** | 48 months | **2.32%/month, 32%/year.** No longer a trading problem |

Then it stops being growth at all. At 150 BTC the plan is **5% nominal return,
4% withdrawal, 1% real** — inflation plus living, nothing more. Not a target to
beat.

**Why this matters more than it looks.** The Monte Carlo goes astronomical at P95
because it models one risk appetite forever. It doesn't know he stops. Phasing
the model is what makes the tail believable, and a believable tail is what lets
him hold a month-to-month structure without reaching for the account-blowing
trade to close a gap that only exists in an unphased projection.

**To build:**
- `goal_plan` grows a `phases` field: boundaries, the rate each demands, and the
  behaviour that belongs to it.
- `/goal` and `/today` show *this phase*, not the 2032 number.
- The Monte Carlo caps risk appetite at each phase boundary rather than
  compounding one assumption to the horizon.

**Open decisions — his, not to be assumed:**
- He said "North Star, 150 BTC by the end of 2028". Current plan is 150 by
  **2032-12-31** with 50 by 2028-12-31. 150 by 2028 compresses all three phases
  into 28 months. Confirm which he means before amending.
- **150 BTC is $10.9M at today's $72,648.** The $40M figure needs BTC at
  **$266,667**. That is a price assumption doing the heavy lifting and it should
  be stated in the plan rather than sitting inside a round number.
- Real inflation rather than the assumed 4% — from actual spending, not a
  headline rate.

---

## Carried over, still true

- **`Log as open trade` writes rows nothing ever closes.** It made three phantom
  trades (#940, #860, #784) that poisoned the journal's plan matching for weeks.
  Deleted; the button remains. Fix it or remove it.
- **Partial exits leave no trace.** Kraken reports fills and `_build_trades`
  aggregates them into one open→close row, so today's trim shows only in the
  final size. A partial exit is a decision that records nothing.
- **Working orders cannot be edited**, only cancelled. `Trade.edit_order(orderId,
  limitPrice, stopPrice, size)` exists and is unwired, so moving a stop means
  cancel-and-replace or the website.
- `.env` lines 2, 5 and 6 do not parse; dotenv skips them silently.
- Six rules in `lens.css` still use `--faint` as readable text at 2.3:1:
  `.muted` `.foot` `.badge.expired` `.cond.no` `.tg .sub` `.sect .caret`.
- `tests/test_nav_parity.py` fails: `Track` has no prop twin.
- `docs/` has seven `.md` with no HTML twins — `python3 tools/md2html.py docs/*.md`.

## The one that isn't code

The veto override now records his reasoning against the scanner's verdict, and
the market briefing states the case before he commits. Nothing has been written
to `veto_overrides` yet.

The first row in that table is worth more than anything on this list. It is the
first labelled example in the only experiment that matters: **do his
discretionary reads beat the rules, or fund them?** `NONE` currently stands at 98
trades, 34.7% win rate, −€2,472 — undifferentiated. Overrides with a stated
reason are a separate population, and now a measurable one.
