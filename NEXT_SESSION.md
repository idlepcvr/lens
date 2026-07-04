# NEXT SESSION — /edge "Fit" section: goal-constrained parameter sweep (Stage A)

Decided 2026-07-04 (Fable session). Execute as specified; design questions are settled.

## The idea (why)

The /edge builder searches over *entry conditions* with geometry fixed. Lucky wants
the inverse: hold the **goal system** fixed (start €, target €, target date, Kelly
fraction, DD cap, execution fill, slippage, BTC growth — all already inputs to
`compute_goal`) and sweep the **strategy-shape parameters** to find which
parameter region can actually hit the goal at sane risk. Output = the same
heatmap grammar as the k×R sweep, one metric at a time, plus **THE optimal
parameter set** — which then defines what any candidate strategy must look like.

Two machines, one bridge: candle backtests *output* frequency/WR; the goal model
takes them as *inputs*. This feature sweeps the goal-model space (Stage A).
Stage B (NEXT next session, do NOT build now): filter the existing background
strategy-search results to combos whose realized WR / R / frequency / ATR
geometry land inside the feasible envelope Stage A finds.

## Settled decisions (do not re-open)

1. **WR and R:R are swept axes** — not pinned to live stats or board survivors.
   The envelope must say "any strategy with WR≥a at R≥b works", strategy-agnostic.
2. **Joint optimum, not per-dimension winners.** One composite feasibility/score
   over the full grid; argmax = THE optimal cell. Each heatmap is a 2D **slice
   through that optimum** (all non-shown axes pinned at their optimal values).
   Per-dimension optima don't compose (lev×freq×ruin interact).
3. **Stage A only.** No wiring into search_custom results yet.
4. **Keep the existing build-your-own UI.** New section is a sibling, nothing deleted.

## Grid

Swept axes (defaults; every lo/hi user-editable in the form, like the ATR range inputs):

| axis | default range | steps |
|---|---|---|
| leverage | 0.5 – 10 | ~20 (0.5 step) |
| trades/week | 0.5 – **historical yearly avg** | ~16 |
| win rate | 0.30 – 0.70 | 9 (0.05) |
| R:R | 1.0 – 5.0 | 9 (0.5) |
| ATR floor (`min_underlying_stop_pct`) | 0 – 2% | 4–5 values |

- Historical avg = closed trades in last 365d / 52 from lens.db
  (`SELECT COUNT(*) FROM trades WHERE pnl IS NOT NULL AND opened_at >= date('now','-365 days')`)
  — 421 → ≈8.1/wk as of 2026-07-04. **Compute live at request time**, prefill the
  hi box, never hardcode.
- Fixed per run (prefilled from `/api/config`, editable): start €, target €,
  target date, max DD, losses allowed, fractional Kelly, fill factor, slippage,
  BTC price/growth. Same field set as /goal's form — reuse its prefill pattern.
- Grid size ≈ 100–130k cells of pure `compute_goal` math. Run in a background
  thread with poll status, same pattern as `search_custom.py` (`start`/`status`,
  lock, single-flight). Cap at ~200k cells with the same "tighten your ranges"
  error message style as EVAL_CAP.
- `compute_goal` raises `CalcError` on infeasible cells (negative EV, lev≤0…):
  catch per cell, mark cell infeasible, continue. leverage/freq axes start >0.

## Per-cell evaluation

Call `compute_goal(...)` with the cell's (leverage, trades_per_week, win_rate,
rr_ratio, min_underlying_stop_pct) + the fixed goal params. Extract:

- `used = risk_per_trade`, `opt = optimal_risk_pct`, `ror = risk_of_ruin`,
  `sharpe_ratio`, `per_trade_ev`, `per_trade_ev_required`, `geometric_drift`.
- **feasible** = (used ≤ opt) AND (ror ≤ 1%) — exactly the /goal "✅ Within safe
  risk" verdict: the goal+date closes without exceeding Kelly/DD-capped risk.
- **score** (rank within feasible) = `opt / used` (risk headroom; higher = the
  goal closes with room to spare). Infeasible cells score by the same ratio so
  the "nearest miss" is well-defined when nothing is feasible.

**Joint optimum** = argmax score over feasible cells; if none feasible, the
nearest-miss cell + a /goal-style danger banner ("no parameter combination
reaches €X by DATE inside Kelly — closest: …, short by …").

## UI (new /edge section, id `#fit`, between #board and #backtest; add anchor pill)

Header: "Fit — what shape must the strategy be?" Sub: sweep the sizing/cadence
space against the goal; the strategies are absent on purpose — this finds the
region any strategy must land in.

1. **Form**: two-column ranges for the 5 swept axes + collapsed "goal params"
   fieldset (prefilled from /api/config). Run button → POST, poll, progress line.
2. **Optimal card** (verdict-banner style): THE parameter set — lev, trades/wk,
   WR, R:R, ATR floor, risk %/trade (= the cell's used risk), plus ror, Sharpe,
   EV vs required. Below it the **envelope sentence**: from the feasible set,
   report per-axis min/max at-or-better than feasibility ("feasible: WR ≥ 45%
   with R ≥ 3, 2–6 trades/wk, lev ≤ 4, ATR floor ≥ 0.5%").
   Include the existing "→ Goal model" handoff link prefilled with the optimal
   cell's params (pattern already in the backtest scorecard, main.py ~1506).
3. **Heatmaps**: reuse the existing sweep heatmap renderer/CSS (`#sweep-wrap`
   grammar in `_backtest_fragment`). Two dropdowns:
   - **metric**: risk headroom (default) · risk of ruin · Sharpe · EV/trade ·
     geometric drift
   - **axes pair**: lev × trades/wk (default) · WR × R:R · ATR floor × lev ·
     trades/wk × WR
   Non-shown axes pinned at the joint optimum; optimal cell outlined; infeasible
   cells dimmed/hatched so the feasible region reads as an island.
   This gives every surface asked for: net/headroom, Sharpe, ruin, WR
   sensitivity (WR×R:R view), leverage scaling, weekly frequency.
4. Server returns the **full cell array** once (done state) — axis-pair/metric
   switching is client-side re-render, no re-run.

## API

- `POST /api/fit/run` — body = ranges + goal params; single-flight guard.
- `GET  /api/fit/status` — running/done/progress; on done: axes, cells
  (compact arrays, cast numpy→python — the v2 json gotcha), optimum, envelope.
- New module `app/fit_page.py` (or section builder) + `app/fit_sweep.py` for the
  worker. Wire into main.py + edge_page.py anchors.

## Checks

- `test_fit_sweep.py`: (1) a known-feasible toy goal (modest target, long date)
  yields a feasible optimum with used ≤ opt; (2) an impossible goal (10× in 30
  days) yields no feasible cells + nearest-miss present; (3) envelope bounds
  contain the optimum; (4) CalcError cells don't kill the run.
- Verify in the running app (`start.sh`, :8765/edge#fit) with the real config.

## Style (match the house, don't invent)

**Visual target: `docs/fit-mock.png`** — a Lucky-approved full-page mock of the
section (anchor pill, range form + goal-param chips, feasible verdict card with
the six-readout optimal set + envelope sentence, heatmap with metric/axes
dropdowns and the outlined optimum in a green island). Build to that picture;
its numbers are illustrative, its layout is the contract.

- Read `BRAND.md` + `app/theme.py` first. LENS is an instrument cluster: flat
  gauge readouts, no hype. All colors/typography via the `shell()` CSS vars
  (`--panel/--line/--accent/--long/--short/--amber/--dim`, `--mono` for numbers).
- The section header/sub must use the existing `.ed-h`/`.ed-hs` classes and the
  anchor-pill pattern already on /edge — it should read as a fourth tense of the
  same page, not a bolted-on widget.
- Optimal card = the /goal `verdict` banner component (danger/warn/ok variants),
  not a new card style. Form inputs = the existing builder's range-input idiom
  (`c-n` boxes, lo–hi pairs). Heatmap = the existing `#sweep-wrap` renderer,
  restyled by data only.
- Every metric/section gets the one-line plain-language "how to read this"
  treatment the rest of /edge uses (hover titles + a collapsed ❔ help block),
  in the same voice: honest about in-sample limits, no green-light language.

## Explicitly out of scope

- Stage B (filtering strategy-search results by the envelope) — next session.
- Any auto-execution (never).
- Touching /goal, /dashboard, or the existing builder/search behaviour.
