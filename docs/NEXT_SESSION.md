# LENS — Next session

[Open as HTML](NEXT_SESSION.html)

*Written 2026-09-04. Previous list archived at
`docs/done/DONE-2026-08-26c-backlog-cleared.md`. Every item below is
unstarted, checked against the code or the database, not carried forward
on faith.*

---

## 🔴 The hedge/prop split — started, not finished. Start here.

The wiring is done: `~/lens-prop` exists as a real fork (own git history
from `5d37f7d` at `idlepcvr/lens-prop`), own systemd service
(`lens-prop.service`, port 8766), own start/stop scripts. Both `lens`
(8765) and `lens-prop` (8766) run independently and survive a reboot —
verified by stopping each and watching the other stay up.

**None of the actual code split has happened yet.** Both apps are still
byte-identical copies of everything. `lens-prop`'s `KRAKEN_FUTURES_SANDBOX`
is forced to `1` in `.env` — it still carries `execute.py` and the same
live Kraken keys as `lens`, so two processes able to place real orders on
one account is not safe until that's cut apart. **Do not flip it back to
live until step 4 below is done.**

Purpose, going forward: `lens` stays the personal engine, no further
deposits, holding to 2028. `lens-prop` is the eval → funded-account track,
meant to fund lifestyle spend if the eval passes.

The real work, in order:

1. **Strip prop-only code out of `lens`.** Ten modules, ~3,900 lines:
   `prop_dashboard.py`, `prop_desk.py`, `prop_eval.py`, `prop_goal.py`,
   `prop_income.py`, `prop_ledger.py`, `prop_scan.py`,
   `prop_signals_page.py`, `prop_track_page.py`, `prop_views.py`, plus the
   17 `/prop-*` and `/api/prop*` routes in `main.py` (of 136 total) and the
   `NAV_PROP`/`PROP_MAIN`/mode-switch machinery in `theme.py`.
2. **Strip hedge-only code out of `lens-prop`.** The mirror image: the
   hedge pages, `execute.py`, the Kraken live-trading path, `NAV_HEDGE`.
3. **Resolve the five cross-book imports** — each currently pulls the
   *other* side's data into a page that will no longer have it:
   - `overview.py` → imports `prop_ledger_data`
   - `edge_page.py` → imports `prop_views._board` **and its CSS**
   - `position_page.py` → imports `prop_config`, `EVALS`
   - `plan.py` → imports `get_prop_eval`
   - `regime.py` → imports `prop_eval`'s cached trade log for cross-book
     regime analysis
   Decide per page: drop the section, or keep a thin read against the
   other app's `/api/*` over the tailnet if the cross-book view is worth
   keeping. Don't guess — ask, these are real feature deletions.
4. **Un-force sandbox** in `lens-prop/.env` once `execute.py` and the
   Kraken live-trading path are actually gone from that copy, not before.
5. **Database**: currently one `lens.db`, shared by design (the `book`
   column already isolates hedge/prop rows, and today's cone.py bug was a
   missing `WHERE`, not a missing database). Revisit only if the split
   above makes a shared DB genuinely awkward — no reason to split it
   pre-emptively.

---

## 🔴 A decision, not a build: the prop eval

`/prop-survival#projection` shows both numbers live: **32.5% pass on
backtest, 0% measured on the 8 real trades taken so far** (12.5% WR,
0.99R — n too small to be a verdict, but the direction agrees with every
earlier finding this month). Not a coding task — the "deliberate
finish-or-close" call flagged back on 2026-08-05 and never made. Raise it
next session, don't build around it.

---

## 1 · Update the stack snapshot

Last one is `2026-08-09` (`0.00930603 ₿`) — **26+ days old and growing**
as of 2026-09-04, now visible in the footer on every page (added
2026-09-04). Every ₿→€ figure the app shows, and the whole milestone
ladder, is anchored to it. Needs a real number from Peter (total BTC held,
exchange + savings + cold — not derivable from `daily_snapshots`, which is
account balance only):

```
POST /api/stack  {"date": "2026-09-04", "btc_total": <the real number>}
```

Once it's in, re-check whether M2 (0.03 ₿ by Oct 1, set 2026-09-04 after
M1 was retired as missed) still reads the same.

---

## 2 · Sweep `--faint` as body text across the app

Six `theme.py` misuses were fixed 2026-08-26. The same bug — a
2.26–2.47:1 decoration token used as readable text — exists in roughly 30
other files (labels, table headers, footnotes): `analytics_page.py`,
`geometry_page.py`, `fit_page.py`, `prop_goal.py`, `prop_ledger.py`,
`site.py` (deleted 2026-09-03, so make this `~29` now), and more. Same fix
each time (`--faint` → `--dim`), but it touches nearly every page, so it
wants its own pass and a visual check, not a blind find-and-replace.

---

## Carried over — verified 2026-09-04

- **Partial exits leave no trace.** The trim works; the record does not.
  `_build_trades` aggregates fills into one open→close row.
- **`.env` has five unparseable lines** — 2, 5, 6, 31, 42. dotenv skips silently.
  (Note: `lens-prop/.env` inherited the same five, plus the new
  `KRAKEN_FUTURES_SANDBOX` override comment — check both copies now.)
- **A `post-commit` hook to draft CHANGELOG entries.** There is no automation and
  never was. Draft from commits since the last dated section and leave them to be
  sharpened — auto-appending subject lines produces a second `git log`, and what
  makes the file worth reading is the *why*.
- **Universal header/footer polish.** Functionality-first was the stated
  priority; the footer now exists everywhere (2026-09-04) but is plain —
  a UI pass was explicitly deferred, not forgotten.

## Fixed 2026-09-04 — no longer open

- ~~`tests/test_measured` fails on a full run~~ — fixed. Cause was
  `test_signal_link.py`/`test_excursion.py` reassigning the global
  `database.DB_PATH` at import time (they're scripts, not test functions;
  pytest still runs their body during collection). Suite is 54/54 clean.
- ~~Track has no footer~~ — `footer_html()` had returned `""` on every
  page since 2026-08-29. Fixed; now carries price/stack freshness.
- ~~`cone.py` has no book filter~~ — was mixing 15 prop trades into the
  hedge projection. Fixed, and a second bug it was masking
  (`_cum_by_day` double-counting pre-window P&L) fixed alongside it.

---

## Still to model

- **Past 150 ₿: 6% nominal, 4% withdrawn, 2% real.** The steady state after the
  north star. Wealthfolio holds the real retirement plan — **€23,496/mo**, FI at
  €13.82M ≈ 55 ₿, FAT FIRE €20.74M ≈ 83 ₿ — which is where the 150 ₿ north star
  comes from. LENS's `burn_monthly_eur` of €6,250 is the *current* burn and
  deliberately not the retirement figure; do not "correct" it.
- **The €250k/BTC assumption** currently lives in prose only. It belongs in
  `goal_plan` beside the numbers that depend on it.
