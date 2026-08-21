# LENS — Next session

[Open as HTML](NEXT_SESSION.html)

*Written 2026-08-22. Previous list archived at
`docs/DONE-2026-08-22-track-rebuild-phased-ladder.md`. Every item checked against
the code or the database, not carried forward on faith.*

---

## 🔴 1 · Point the miner at the overrides

**This is the whole next session. Everything else here can wait.**

### What was found on 2026-08-22

Splitting the hedge book by `setup_tag` — what the scanner saw at the moment each
trade was opened:

| scanner said | trades | total | avg/trade | win rate |
|---|---|---|---|---|
| **a setup fired** | 93 | **+€3,853** | **+€41.43** | **57.0%** |
| nothing | 97 | −€2,440 | −€25.16 | 35.1% |
| **VETO — do not take** | 337 | **−€5,944** | −€17.64 | 35.3% |

**The system's edge is strongly positive.** The aggregate is negative only
because 434 of 527 trades were taken outside it. Any earlier note in this repo
claiming "the measured edge is negative, you need 5R" was reading one number
across three populations — it is wrong and this table supersedes it.

### Where the overrides split

| veto combination | n | total | avg | win% |
|---|---|---|---|---|
| `rsi_neutral,fvg_entry` | 13 | +€1,329 | +€102.22 | 30.8% |
| `slope_against` | 23 | +€265 | +€11.53 | 47.8% |
| `rsi_neutral` | 57 | −€13 | −€0.23 | 38.6% |
| `slope_against,sweep_fade,pd_raid_fade` | 46 | −€1,925 | −€41.84 | 32.6% |
| `ny_pm_kz` | 14 | −€1,434 | −€102.40 | 35.7% |
| `slope_against,pd_raid_fade` | 15 | −€1,753 | −€116.89 | 20.0% |

⚠️ **`rsi_neutral,fvg_entry` does not survive inspection.** Two trades
(2026-02-23 +€792, 2026-02-28 +€1,030, both shorts, five days apart) carry the
whole result. The other eleven total **−€493**. It is one good week, not a setup.
11 of the 13 were shorts and all three longs lost.

`slope_against` alone is the more credible candidate *because* it is
unspectacular — 23 trades, no single trade carrying it, win rate near coin-flip
with a positive tail.

### The job

Point `research/edge_miner.py` at the **override population specifically** and
run it through the gates that already exist — `perm_test.py`,
`filter_significance.py`, the sweep and leave-one-month-out. The question is
narrow and has a yes/no answer:

> Does any veto combination survive permutation testing when overridden?

**This is not "build more strategies."** That is the job that cannot be started.
This is a script run against data already on disk, and it returns either a name
or a no. The machinery was built in early August — see the commits *"Find the one
edge that survives all four gates"* and *"Robustness: the non-VETO short filter
survives permutation, sweep and LOMO"*. It has never been aimed here.

Anything that survives becomes a named setup, which turns an override into a
signal — and the override stops being a rule-break.

---

## 2 · A monthly review that actually exists

There is no surface and no ritual for reviewing the book. Consequences, both
already visible:

- **511 of 528 hedge trades have `followed_plan IS NULL`** — 3.2% reviewed. The
  discipline score is measuring silence.
- The finding in §1 sat in a column that has been populated the whole time and
  nobody looked.

What to build, in rough order of value:

- A **monthly review page** — the month's trades grouped by `setup_tag`, with the
  §1 table computed live rather than by hand in sqlite.
- A cadence that fires: cron → ntfy on the 1st, same topic as everything else.
- Somewhere to record the verdict, so a tuned or retired veto has a date and a
  reason the way a plan amendment does.

The gates need tuning against evidence, not memory. A monthly pass is where that
happens.

---

## 3 · Give Track a prop twin

`tests/test_nav_parity.py` fails: `hedge pages with no prop twin: ['Track']`.

Two fixes, and the second matters more:

1. Build `/prop-track` — the prop book has a goal, a ladder and a horizon too,
   and the evaluation has never had the surface the hedge book got.
2. **Make the failure visible.** The file is a standalone `main()`, so pytest
   collects nothing from it and reports the suite green while the check fails.
   Every "52 passed" logged on 2026-08-22 was true and misleading at once. A
   check nothing runs is not a check.

---

## 4 · The prop evaluation, cold

Deferred deliberately to its own session, ~next week.

The question is not "how do I pass" but **"what does passing require, and how
likely is that?"** The eval needs roughly **10–12% to cover expenses** — that
number wants modelling against the same measured distribution the cone uses, not
against hope. `/prop-survival` and the prop simulator already exist; the honest
version of this is a pass-probability, and it may come back low.

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
