# LENS — Next session

[Open as HTML](DONE-2026-08-26c-backlog-cleared.html)

[Open as HTML](NEXT_SESSION.html)

*Archived 2026-08-26 — §1 (Track twin) is shipped as `/prop-track`, §2
(prop eval feasibility) is answered live on `/prop-survival#projection`,
and the three bug items in "carried over" are fixed. See CHANGELOG
2026-08-26c. Only genuinely unstarted items carry forward into the
current NEXT_SESSION.md.*

---

## 🔴 1 · Give Track a prop twin — SHIPPED

Built `app/prop_track_page.py` + `/prop-track`, reusing `prop_ledger_data()`
entirely — no new computation. `NAV_PROP` gained Track between Goal and
Position. `tests/test_nav_parity.py` converted to `test_nav_parity()` so
pytest collects it (was a standalone `main()`, silently never run).

Original scope, for the record: `tests/test_nav_parity.py` failed:
`hedge pages with no prop twin: ['Track']`.

---

## 2 · The prop evaluation, cold — ANSWERED

**Backtest cone: 32.5% pass** for the live $10k TURBO config (median 15
trades / 19 days to target if it passes). **Measured from the real ledger:
0% pass on n=8 trades** (12.5% WR, 0.99R) — flagged as too small a sample
to be a verdict, but consistent with the known finding that the strategies
haven't reproduced their backtest edge on real fills yet.

The backtest cone (`prop_goal.cone()`) already existed and was already
live at `/prop-survival#projection` and `/prop-goal`. What was actually
stale was the "measured" caveat: a hand-typed "1.5%, 2026-07-09" string
from `research/eval_mc.py`, run once with a hardcoded 10%/3% target/floor
that didn't even match TURBO's real 9%/3%. Fixed by parameterizing
`eval_mc.run()` and adding `prop_goal.measured_pass_pct()`, which
recomputes live from `_measured_geometry()` on every call — the number
can't go stale again the way the hardcoded one did.

Original scope, for the record: the question is not "how do I pass" but
"what does passing require, and how likely is that?" — modelled against
the same measured distribution the cone uses, not against hope.

---

## Carried over — verified 2026-08-22, three items closed 2026-08-26

- **Stack snapshot is 12 days old** (`2026-08-09`). Everything on Track measures
  from it. `daily_snapshots` already runs daily and holds the *account balance*
  automatically — the stack is the other number (total BTC, including what is not
  on the exchange) and only a human can supply it. Wire a weekly ntfy nudge; the
  `btc_balance` column in `daily_snapshots` exists and is unused, so part of it
  may be derivable.
- ~~`Log as open trade` writes rows nothing ever closes~~ **FIXED 2026-08-26** —
  button deleted, root cause was duplicating two things that already worked.
- **Partial exits leave no trace.** The trim works; the record does not.
  `_build_trades` aggregates fills into one open→close row.
- ~~`Trade.edit_order` is unwired~~ **FIXED 2026-08-26** — the SDK call
  already existed, wired via `execute.edit_order()` + `POST /api/orders/edit`.
- **`.env` has five unparseable lines** — 2, 5, 6, 31, 42. dotenv skips silently.
- ~~Six `--faint`-as-body-text rules in `theme.py`~~ **FIXED 2026-08-26** —
  the six documented plus one same-file miss now use `--dim`. ~30 other
  files still misuse `--faint` the same way — a much bigger sweep, flagged
  not started.
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
