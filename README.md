# LENS

**A watch-only cockpit for trading BTC perpetual futures with discipline.**

LENS runs on the miniPC (FastAPI + SQLite, no cloud dependencies) — open
**https://lens.restedpc.com** from the tailnet, or http://localhost:8765 on the
box. It never places a trade: it scans, alerts, checklists, journals and
measures. You place every trade on Kraken yourself.

![Home](docs/home.png)

Two machines behind one front door, each with its own nav, ledger and math:

- **HEDGE** — discretionary own-money trading on the mined edge
  (`LENS_EDGE_v3`: five momentum-continuation setups + seven vetoes, mined
  from the real fill history). Playbook:
  [`strategies/LENS_EDGE_v3_ICT/FINDINGS.md`](strategies/LENS_EDGE_v3_ICT/FINDINGS.md).
- **PROP** — surviving a Breakout (Kraken Prop) evaluation, which is the
  opposite game: pass-probability against equity walls, not expectancy. Its
  own simulator, ledger (`book='prop'`), desk and goal pages.

## The loop

Scanner cron → ntfy push with one-tap **TAKE / SKIP** buttons → `/desk`
checklist → trade on Kraken → hourly sync pulls the fill, auto-tags it and
links it to the signal that caused it → per-setup scoreboard → re-mine when
enough tagged trades accumulate. Signals pass discipline filters (bleed-hour
veto, cooldown) before they reach the phone. LENS never auto-enters — the
mined edge is discretionary selection inside contexts, so the tool alerts and
measures, nothing more.

## Running it

```bash
pip install -r requirements.txt   # first time; then create .env (see app/setups.py header)
./start.sh                        # prints the dashboard link
./stop.sh
```

The crons that keep the loop alive (installed on the miniPC):

```bash
# hourly HEDGE scanner (minute 2, right after the 1H close)
2 * * * *  cd /home/mini/lens && /home/mini/lens/.venv/bin/python3 -m app.setups >> logs/setup_scan.log 2>&1
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
tests/        assert-based self-checks, run directly (no framework)
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
open `lens.db` by its bare relative name, which only works from the root. Run
them from anywhere:

```bash
.venv/bin/python3 tests/test_veto_log.py
for t in tests/test_*.py; do .venv/bin/python3 "$t" || echo "FAIL $t"; done
```

## Docs

| File | What |
|---|---|
| `CHANGELOG.md` | Dated build history — what shipped, when, and the gotchas |
| `LENS_PLAN.md` | Roadmap and open next-steps |
| `strategies/LENS_EDGE_v3_ICT/FINDINGS.md` | The mined edge, full detail |
| `PRODUCT.md` / `BRAND.md` / `/style` | Product definition · brand voice · living style guide |
| `strategies/README.md` | Pine Script side (TradingView HUD indicator) |

## Status (2026-07-14)

The build is ahead of the usage, deliberately. The loop has been live since
2026-06-16 (crons firing, phone buttons working); the bottleneck is reps —
taking the alerts, letting trades tag themselves, accumulating the dataset the
v4 re-mine needs. Open items live in `LENS_PLAN.md`.

Development is on **`master`** — pull, commit, push.
