# NEXT_SESSION — /edge search mode + risk envelope + goal wiring

Spec agreed with Lucky 2026-07-04 (AskUserQuestion, three answers pinned below).
Execute top to bottom; smallest diff; reuse the named modules. Delete this file
at session end. Do NOT: auto-register results, touch alerting, add new deps.

## The three pinned decisions (do not re-ask)

1. **Blank = search.** On /edge build-your-own, fields left on "any" are NOT
   "no filter" — they are dimensions to sweep. Pinned fields stay fixed.
   Output = ranked TABLE of the best condition-sets, not one scorecard.
2. **Risk envelope = ATR-based ranges.** User inputs ranges: ATR-stop k
   (from/to), R (from/to), risk %/trade (from/to). Search only tests geometry
   cells inside the envelope.
3. **Projections = goal-model wiring.** Any result row / scorecard gets a
   "→ Goal" action that opens /goal pre-filled with that strategy's real stats
   (WR, R, trade frequency). No new math — connect existing pieces.

## Step 1 — backend: POST /api/backtest/search

Reuse, don't rewrite: `app/strategy_search.py` already has `SLOTS`, `_masks`,
`_combo_mask`, `_sig_fn`, `combo_params`, `_describe`, `_eval`, `MIN_N`,
`MAX_CONDS`; v3 geometry merge pattern in `app/strategy_search3.py` (`_geo`,
`RISK`). The endpoint is a thin orchestrator:

- Request = BtCustomRequest fields (pinned conditions; None = sweep that slot)
  + `k_min,k_max`, `r_min,r_max`, `risk_min,risk_max` + `months`.
- Combo space: blank slots combine up to MAX_CONDS **additional** conditions on
  top of the pinned ones (pinned don't count toward the cap). Timeframe blank →
  sweep 1h/4h. Direction blank → both.
- Geometry: subset of FINE_K×FINE_R (strategy_search3) within [k_min,k_max]×
  [r_min,r_max]. Risk: test risk_min and risk_max only (2 points, not a grid —
  risk scales results monotonically, envelope ends suffice).
- Honesty gate kept: report `robust` (split-half n≥MIN_N both halves green)
  per row — same `_eval`. No deep-7y pass in the UI search (too slow); label
  column "30mo split-half" and note deep confirmation happens offline.
- **Runtime cap:** estimate combos×cells before running; if > ~8,000 evals,
  return an error telling the user to pin more fields (message includes the
  estimate). Typical pinned-2-fields search must finish in low minutes.
- Background job, same pattern as `_bt_cache`/`_bt_running` in main.py:
  POST starts thread, GET /api/backtest/search/status returns
  {running, done_evals, total_evals, top: [best 50 rows so far]}. UI polls 2s.
- Row shape: {desc, params, tf, direction, k, rr, risk, n, wr, pf, net_pct,
  max_dd, half1, half2, robust}. Sort: robust first, then net_pct.

## Step 2 — UI on /edge builder

- Geometry row becomes ranges: "ATR stop × [from]–[to]", "R [from]–[to]",
  "Risk %/trade [from]–[to]" (single-value = set from=to; keep old single
  inputs' ids working or migrate cleanly — Pine/single-run use the *from*
  values).
- New button **🔍 Search blanks** next to ▶ Backtest it. Progress line under
  it (done/total). Results = ranked table below (columns above; robust rows
  get the existing `win` styling). Click a row → fills the form with that
  combo (pins everything) so ▶ / ⊞ Sweep k×R / ⧉ Pine work on it instantly.
- Help text: one line — "blank fields are searched, set fields are pinned;
  green robust = profitable in both halves, still in-sample".

## Step 3 — "→ Goal" wiring

- Read `app/calculator.py` `compute_goal` + the /goal form field names first
  (main.py:949 region, `goal-form` at main.py:279).
- Add "→ Goal" link on: each search-result row, and the custom-run scorecard.
  It opens /goal with query params pre-filling: win rate, avg R (use the row's
  R), trades/week (n ÷ weeks in window), current account balance default
  untouched. /goal side: tiny JS on load — if query params present, fill the
  form fields and trigger recompute. No calculator changes.

## Step 4 — verify + housekeeping

1. Search with everything blank but direction=long pinned, k 1–2.5, R 2–5,
   risk 2–2: expect the cap error OR a run that surfaces the TREND_MOMO family
   near the top (trend up · MACD bull · vol spike must appear with net ≈ the
   registered numbers when tf=4h k=1.5 R=3).
2. Pin the exact DIP_BB_MASTACK_v3 conditions, search geometry only → its
   k=2.5/R=5 cell ≈ registry numbers.
3. "→ Goal" from that row → /goal opens with WR/R/freq filled, model computes.
4. One permanent check in test_atr_stop.py or a new small test: the search
   orchestrator on a tiny synthetic df returns rows with the declared shape.
5. README TODO + Kiki daily note + commit master (no push). Delete this file.

## Out of scope
- Deep-7y confirmation in the UI (offline scripts remain the tool).
- Auto-registering search hits, alerting, prop-board changes.
- Exit-mechanics sims, macro feeds (unchanged blockers).
