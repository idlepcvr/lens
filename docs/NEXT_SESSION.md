# LENS — Next session

[Open as HTML](NEXT_SESSION.html)

*Written 2026-08-26. Previous list archived at
`docs/done/DONE-2026-08-26c-backlog-cleared.md` — Track's prop twin, the
prop eval pass-probability, and three carried-over bugs are all closed.
Every item below is unstarted, checked against the code or the database,
not carried forward on faith.*

---

## 🔴 A decision, not a build: the prop eval

`/prop-survival#projection` now shows both numbers live: **32.5% pass on
backtest, 0% measured on the 8 real trades taken so far** (12.5% WR,
0.99R — n too small to be a verdict, but the direction agrees with every
earlier finding this month). This isn't a coding task. It's the
"deliberate finish-or-close" call flagged back on 2026-08-05 and never
made. Worth raising next session, not building around.

---

## 1 · Sweep `--faint` as body text across the app

Six `theme.py` misuses were fixed 2026-08-26. The same bug — a
2.26–2.47:1 decoration token used as readable text — exists in roughly 30
other files (labels, table headers, footnotes): `analytics_page.py`,
`geometry_page.py`, `fit_page.py`, `prop_goal.py`, `prop_ledger.py`,
`site.py`, and more. Same fix each time (`--faint` → `--dim`), but it
touches nearly every page, so it wants its own pass and a visual check,
not a blind find-and-replace.

---

## Carried over — verified 2026-08-22

- **Stack snapshot is 12 days old** (`2026-08-09`). Everything on Track measures
  from it. `daily_snapshots` already runs daily and holds the *account balance*
  automatically — the stack is the other number (total BTC, including what is not
  on the exchange) and only a human can supply it. Wire a weekly ntfy nudge; the
  `btc_balance` column in `daily_snapshots` exists and is unused, so part of it
  may be derivable.
- **Partial exits leave no trace.** The trim works; the record does not.
  `_build_trades` aggregates fills into one open→close row.
- **`.env` has five unparseable lines** — 2, 5, 6, 31, 42. dotenv skips silently.
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
