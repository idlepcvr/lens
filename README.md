# LENS

**A cockpit for trading BTC perpetual futures with discipline.**

I trade crypto with my own money. LENS is the system I'm building to help me do
that well — it scans, alerts, checklists, journals and measures, so the decisions
are mine but the record isn't a guess. Slow and steady wins the race: the goal is
50 ₿ by the end of 2028, reached one rung at a time, not one heroic month.

The money philosophy underneath is FIRE, extended past index funds — bitcoin is
the engine, but the plan only works with an understanding of the other asset
classes around it, a burn rate that's actually known, and income that survives a
bad quarter. That's the whole of personal finance in a paragraph: spend less than
you make, know your number, own assets that compound, and don't blow up.

LENS runs on the miniPC (FastAPI + SQLite, no cloud dependencies) — open
**https://lens.restedpc.com** from the tailnet, or http://localhost:8765 on the
box.

![Home](docs/home.png)

## Two books, one front door

Each has its own nav, ledger and maths:

- **HEDGE** — discretionary own-money trading on the mined edge
  (`LENS_EDGE_v3`: five momentum-continuation setups + seven vetoes, mined
  from the real fill history). Playbook:
  [`strategies/LENS_EDGE_v3_ICT/FINDINGS.md`](strategies/LENS_EDGE_v3_ICT/FINDINGS.md).
- **PROP** — surviving a Breakout (Kraken Prop) evaluation, which is the
  opposite game: pass-probability against equity walls, not expectancy. Its
  own simulator, ledger (`book='prop'`), desk and goal pages.

## The goal, and how it's tracked

50 ₿ by 2028-12-31, broken into rungs that get harder at a constant rate rather
than a constant size — each one is a similar percentage climb, so each one feels
about the same. Rung dates are derived from where the stack actually is, except
where I've pinned one; a pinned date is never recomputed and the rungs beneath it
compress to fit.

`/hedge-track` is the daily surface for that: the next rung and nothing else at a
glance, with the rest folded away until I go looking.

![Track](docs/track.png)

The fan is a Monte-Carlo projection bootstrapped from my own closed trades, not a
tidy Gaussian — so the expectancy and the variance are the ones I really trade.
The red line is the point where the account is gone, and it's drawn on purpose:
a projection that hides its own ruin cases isn't honest.

Underneath it is a daily score. Four components, and discipline is a gate rather
than the heaviest weight — a day with an off-plan trade scores zero however
profitable it was, because the thing that costs me money is frequency and
rule-breaking, not being wrong.

## The loop

Scanner cron → ntfy push with one-tap **TAKE / SKIP** buttons → `/hedge-desk`
checklist → trade on Kraken → hourly sync pulls the fill, auto-tags it and links
it to the signal that caused it → per-setup scoreboard → re-mine when enough
tagged trades accumulate. Signals pass discipline filters (bleed-hour veto,
cooldown) before they reach the phone.

**LENS does not place trades today.** Every order is typed into Kraken by hand.
That's a current fact, not a permanent law — see below.

![Desk](docs/desk.png)

## Where it's going

- **Order routing, at 10%.** Bridging the gap between an approved signal and a
  placed order — I decide, LENS sends. Not autonomous trading: a human decision
  with a machine hand. It ships behind a scale model — 10% of volume through the
  system, 90% by hand — and the ratio only moves when the record earns it.
  Needs a trade-scoped API key, OCO/reduce-only brackets so a filled take-profit
  can't leave a live stop behind, a `cancel-after` dead-man's switch, and a hard
  trades-per-day cap.
- **One venue.** Kraken for everything; Bybit comes out. Two price sources in one
  system is two clocks, and a dashboard with two clocks can't be trusted.
- **My vocabulary, not the tool's.** Renaming everything I wouldn't say out loud,
  and deleting what I never use. A cockpit whose labels need translating is one I
  can't fly under pressure.
- **Paper first.** `kraken paper` runs approved tickets against live prices with
  no keys and no money — the cheap way to prove the loop before it holds a real
  credential.

Open items live in [`LENS_PLAN.md`](LENS_PLAN.md); shipped history in
[`CHANGELOG.md`](CHANGELOG.md).

## Running it

```bash
pip install -r requirements.txt   # first time; then create .env (see app/setups.py header)
./start.sh                        # prints the dashboard link
./stop.sh
```

The crons that keep the loop alive (installed on the miniPC):

```bash
# hourly HEDGE scanner (minute 2, right after the 1H close)
2 * * * *  /home/mini/lens/.venv/bin/python3 -m app.setups >> logs/setup_scan.log 2>&1
# hourly Kraken fill sync (closes the loop — trades self-tag)
5 * * * *  curl -s -X POST http://localhost:8765/api/sync/kraken >/dev/null
# PROP scanner on 4H closes (gates internally to the Asian 00/04 UTC windows)
5 3,7,11,15,19,23 * * *  cd /home/mini/lens && /home/mini/lens/.venv/bin/python3 -m app.prop_scan >> logs/prop_scan.log 2>&1
# weekly strategy R-sweep re-rank (Mon 04:17)
17 4 * * 1  cd /home/mini/lens && .venv/bin/python3 -m app.strategy_eval >> logs/strategy_eval.log 2>&1
```

Phone alerts need `LENS_NTFY_TOPIC` and `LENS_BASE_URL` (the server address
*as seen from the phone* — the TAKE/SKIP buttons POST to it) in `.env`.

Health: `curl localhost:8765/health` · API docs: http://localhost:8765/docs ·
deploy: `systemctl --user restart lens.service`

## Layout

```
app/          the server — FastAPI, pages, engines, scanners
strategies/   Pine strategies, one folder each + BASELINE/FINDINGS
research/     one-off analysis scripts, not wired into the app. They import
              each other by bare name (edge_miner, ict_miner and trade_review
              are one family), so they have to share a directory
tests/        assert-based self-checks
docs/         reference docs, screenshots, and completed build specs
data/         lens.db — the ledger. The one irreplaceable thing here.
              Gitignored, backups in data/backups/
results/      generated output: searches, breeder runs, dedup clusters.
              strategy_scores.json is the live board cache the app reads
logs/         everything systemd and cron redirect into
```

Every path is defined once in `app/paths.py`, anchored to the repo root via
`__file__` rather than the cwd. That matters more than tidiness: the database
path used to be a bare relative `"lens.db"`, so a script run from the wrong
directory silently opened a **different, empty** database instead of failing.

Reading the docs: **`/manual`** renders README, the plan, the changelog,
PRODUCT and BRAND live from disk, in the app's own theme. (`/docs` is FastAPI's
API reference — different thing, same-sounding name.)

Scripts in `research/` and `tests/` open with `import _bootstrap`, which puts
the repo root on `sys.path` and makes it the cwd — they import `app` and some
open `lens.db` by its bare relative name, which only works from the root.

```bash
.venv/bin/python3 -m pytest tests/ -q
```

## Docs

| File | What |
|---|---|
| `CHANGELOG.md` | Dated build history — what shipped, when, and the gotchas |
| `LENS_PLAN.md` | Roadmap and open next-steps |
| `strategies/LENS_EDGE_v3_ICT/FINDINGS.md` | The mined edge, full detail |
| `PRODUCT.md` / `BRAND.md` / `/style` | Product definition · brand voice · living style guide |
| `strategies/README.md` | Pine Script side (TradingView HUD indicator) |

## Status (2026-08-09)

The build is ahead of the usage, deliberately. The loop has been live since
2026-06-16 — crons firing, phone buttons working — and the bottleneck is reps:
taking the alerts, letting trades tag themselves, accumulating the dataset the
v4 re-mine needs.

The book is gross-profitable. What it loses to is cost × frequency, which is
why the daily score punishes rule-breaking rather than rewarding activity, and
why every routing feature above arrives with a cap attached.

Development is on **`master`** — one branch, no ceremony.
