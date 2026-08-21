# LENS — Next session

[Open as HTML](NEXT_SESSION.html)

*Written 2026-08-22. The previous list is archived at
`docs/DONE-2026-08-22-track-rebuild-phased-ladder.md` — Track rebuilt, the ladder
phased and rounded to plan v9, the cone given a ceiling. Every item below was
checked against the code or the database on 2026-08-22, not carried forward on
faith.*

---

## 🔴 The only thing that matters

The ladder needs **+2.14% per trade** through Acceleration. The ledger says the
edge is negative:

| | measured | expectancy |
|---|---|---|
| all time (527 trades) | WR 39.1%, RR 1.32 | **−0.206 R/trade** |
| last 90 days (84) | WR 32.1%, RR 1.54 | **−0.260 R/trade** |

No position size converts a negative expectancy into a positive one — it only
changes how fast it plays out. At the measured 39% win rate, risking 2% per
trade:

| RR | per trade | |
|---|---|---|
| 1.32 (current) | −0.41% | |
| 2.00 | +0.12% | 18× short of what the ladder needs |
| 3.00 | +0.90% | |
| 5.00 | **+2.47%** | clears it |

**The lever is the reward multiple, not the risk amount.** Everything else on
this list is instrumentation; none of it moves this number.

The `veto_overrides` table now has **4 rows** — the first labelled examples in
the only experiment that matters: do the discretionary reads beat the rules, or
fund them? Four is not yet a population. It is a start.

---

## Still to model

- **Past 150 BTC: 6% nominal, 4% withdrawn, 2% real.** The steady state after
  the north star — withdraw 4% a year, grow 2%, stop. Not modelled anywhere.
  *(Revised 2026-08-22 from the earlier 5/4/1.)*
- **The $37.5M figure assumes BTC at $250,000** by end-2028, roughly 3.4× the
  price at the time it was written. That assumption should live in the plan,
  not inside a round number.

---

## Carried over — verified still true 2026-08-22

- **`Log as open trade` writes rows nothing ever closes.** It made three phantom
  trades (#940, #860, #784) that poisoned the journal's plan matching for weeks.
  Deleted; the button is still live at `position_page.py:523`. Fix it or remove
  it.
- **Partial exits leave no trace.** The trim itself works — one was placed
  through LENS on 2026-08-21. What does not exist is the *record*:
  `_build_trades` aggregates fills into one open→close row, so a partial exit
  shows only as a smaller final size. A decision that records nothing.
- **Working orders cannot be edited**, only cancelled. `Trade.edit_order` has
  zero references anywhere in `app/`, so moving a stop means cancel-and-replace
  or the website.
- **`.env` has five unparseable lines, not three** — 2, 5, 6, **31, 42**. dotenv
  skips them silently.
- **Six rules in the shared stylesheet still use `--faint` as readable text** at
  2.3:1: `.muted` `.foot` `.badge.expired` `.cond.no` `.tg .sub` `.sect .caret`.
  Track's own CSS was fixed on 2026-08-22; `theme.py` was not.

---

## ⚠️ A failing check the test suite cannot see

`tests/test_nav_parity.py` **fails** — `hedge pages with no prop twin: ['Track']`.

It is written as a standalone `main()` rather than pytest functions, so pytest
collects nothing from it and reports the suite green while the check is failing.
Every "52 passed" recorded during the 2026-08-22 session was true and misleading
at the same time.

Two separate fixes, and the second matters more than the first:

1. Give `Track` a prop twin, or record why it should not have one.
2. Make the file pytest-shaped so a failure is *visible*. A check nothing runs is
   not a check.

`tests/test_measured` also fails on a full-suite run and passes alone — earlier
tests seed rows into the shared database. Pre-existing, and the reason a single
run cannot tell a regression from a flake.
