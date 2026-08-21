# LENS — Next session

[Open as HTML](NEXT_SESSION.html)

*Written 2026-08-21 after LENS placed, bracketed, verified and trimmed its first
live orders. The previous list is archived at
`docs/DONE-2026-08-21-execution-live-orders-veto-override.md` — all five items
done, plus partial close.*

## The ladder is now phased — plan v7

North star moved to **150 BTC by 2028-12-31**, burn corrected to **€6,250/month**,
and the ladder runs three rates instead of one flat 41.3%.

| phase | from → to | rate | reaches |
|---|---|---|---|
| **1 · Acceleration** | 0.00931 → 1 BTC | **60%/mo** | Jun 2027 |
| **2 · Growth** | 1 → 50 BTC | **50%/mo** | Apr 2028 |
| **3 · Maintenance** | 50 → 150 BTC | **14%/mo** | Dec 2028 |

Next rung: **0.01489 BTC by 1 Sept**, and the stack is at 0.00931 — **62% of the
way with ten days left**.

### 🔴 Phase 2 is the whole plan, and it is not phase 1

Every combination was modelled against the 28-month horizon:

| phase 1 | phase 2 | reaches 50 | phase 3 then needs |
|---|---|---|---|
| 50% | 20% | — | **impossible** |
| 60% | 20% | — | **impossible** |
| 70% | 20% | — | **impossible** |
| 50% | 35% | Sep 2028 | 38%/mo |
| 60% | 35% | Jul 2028 | 24%/mo |
| 70% | 35% | Jun 2028 | 20%/mo |
| 60% | **50%** | Apr 2028 | **14%/mo** |
| 70% | 50% | Feb 2028 | 12%/mo |

Phase 1 barely moves the outcome — 50% to 70% changes it by under three months,
because 0.00931 → 1 BTC is only ~10 months at any rate in that band. **Phase 2
decides everything.** At 20%/month the horizon is unreachable no matter how fast
the acceleration goes. At 35% the "maintenance" phase needs 24%/month, which is
not maintenance — it is the hardest sprint of the plan arriving exactly where he
said he would slow down.

**So the load-bearing claim is 50%/month sustained for ten months on an account
between 1 and 50 BTC** — the stretch where size, not skill, starts to bind. That
is the number to watch, and the one to revisit first when reality disagrees.

### Still to build

- `goal_plan` has no `phases` field yet — the rates live only in the amendment
  reason. They should be structured so `/goal` and `/today` can show *this phase*
  and its rate rather than the 2028 number.
- The Monte Carlo still compounds one risk appetite to the horizon, which is why
  P95 goes astronomical. Cap it at each phase boundary.
- Past 150 BTC the plan is **5% nominal, 4% withdrawn, 1% real** — not modelled
  anywhere yet.
- **The $37.5M assumes BTC at $250,000** by end-2028, roughly 3.4× today's
  $72,648. That assumption should live in the plan, not inside a round number.

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
