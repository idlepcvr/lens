# LENS — Next session

[Open as HTML](DONE-2026-08-26b-monthly-review-shipped.html)

[Open as HTML](NEXT_SESSION.html)

*Archived 2026-08-26 — §1 below is now shipped: `/review` (see CHANGELOG
2026-08-26b). Kept as-is for the record; §2 and §3 carried forward
unchanged into the current NEXT_SESSION.md.*

---

## 🔴 1 · A monthly review that actually exists — SHIPPED

**Built:** `app/review_page.py` + `/review` route. A month's closed trades
grouped live by what the scanner said at entry (setup fired / nothing /
VETO), a per-VETO-combo breakdown at n≥5, a `review_verdicts` table
(keep/tune/retire + reason, min 10 chars) written via
`POST /api/review/verdict`, and `POST /api/review/notify` firing from cron
`0 8 1 * *` — same local-curl pattern as the other jobs, same ntfy topic.
First real verdict recorded: `slope_against` kept as VETO (p=0.44, not
significant).

Original scope, for the record:

There is no surface and no ritual for reviewing the book. Consequences, both
already visible:

- **511 of 528 hedge trades have `followed_plan IS NULL`** — 3.2% reviewed. The
  discipline score is measuring silence.
- The setup-tag split (scanner-fired trades +€3,853 vs VETO trades −€5,944)
  sat in a column that has been populated the whole time and nobody looked.

What to build, in rough order of value:

- A **monthly review page** — the month's trades grouped by `setup_tag`, with
  that split computed live rather than by hand in sqlite.
- A cadence that fires: cron → ntfy on the 1st, same topic as everything else.
- Somewhere to record the verdict, so a tuned or retired veto has a date and a
  reason the way a plan amendment does.

The gates need tuning against evidence, not memory. A monthly pass is where
that happens.

---

## 2 · Give Track a prop twin

`tests/test_nav_parity.py` fails: `hedge pages with no prop twin: ['Track']`.

Two fixes, and the second matters more:

1. Build `/prop-track` — the prop book has a goal, a ladder and a horizon too,
   and the evaluation has never had the surface the hedge book got.
2. **Make the failure visible.** The file is a standalone `main()`, so pytest
   collects nothing from it and reports the suite green while the check fails.
   Every "52 passed" logged on 2026-08-22 was true and misleading at once. A
   check nothing runs is not a check.

---

## 3 · The prop evaluation, cold

Deferred deliberately to its own session.

The question is not "how do I pass" but **"what does passing require, and how
likely is that?"** The eval needs roughly **10–12% to cover expenses** — that
number wants modelling against the same measured distribution the cone uses,
not against hope. `/prop-survival` and the prop simulator already exist; the
honest version of this is a pass-probability, and it may come back low.

Worth doing before more time goes into the evaluation, not after.

---

## Carried over — verified 2026-08-22

- **Stack snapshot is 12 days old** (`2026-08-09`). Everything on Track measures
  from it. `daily_snapshots` already runs daily and holds the *account balance*
  automatically — the stack is the other number (total BTC, including what is not
  on the exchange) and only a human can supply it. Wire a weekly ntfy nudge; the
  `btc_balance` column in `daily_snapshots` exists and is unused, so part of it
  may be derivable.
- **`Log as open trade` writes rows nothing ever closes** — three phantom trades
  poisoned journal matching for weeks. Button still live at
  `position_page.py:523`.
- **Partial exits leave no trace.** The trim works; the record does not.
  `_build_trades` aggregates fills into one open→close row.
- **`Trade.edit_order` is unwired** — zero references in `app/`. Moving a stop
  means cancel-and-replace.
- **`.env` has five unparseable lines** — 2, 5, 6, 31, 42. dotenv skips silently.
- **Six `--faint`-as-body-text rules in `theme.py`** at 2.3:1: `.muted` `.foot`
  `.badge.expired` `.cond.no` `.tg .sub` `.sect .caret`.
- **A `post-commit` hook to draft CHANGELOG entries.** There is no automation and
  never was. Draft from commits since the last dated section and leave them to be
  sharpened — auto-appending subject lines produces a second `git log`, and what
  makes the file worth reading is the *why*.
- **`tests/test_measured`** fails on a full run, passes alone — earlier tests seed
  the shared database.

---

## Still to model

- **Past 150 ₿: 6% nominal, 4% withdrawn, 2% real.** The steady state after the
  north star. Wealthfolio holds the real retirement plan — **€23,496/mo**, FI at
  €13.82M ≈ 55 ₿, FAT FIRE €20.74M ≈ 83 ₿ — which is where the 150 ₿ north star
  comes from. LENS's `burn_monthly_eur` of €6,250 is the *current* burn and
  deliberately not the retirement figure; do not "correct" it.
- **The €250k/BTC assumption** currently lives in prose only. It belongs in
  `goal_plan` beside the numbers that depend on it.
