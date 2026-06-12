# LENS — Status & Progress

*Last updated: 2026-06-12*

## Where we are in one line

The edge is mapped: five robust setups (S1–S5) and seven vetoes mined from 464
real trades now run live — hourly scanner → phone alert → /desk checklist →
auto-tagged trades → per-setup scoreboard. Missing: the user-side crontab line
that schedules the scan, and ~3 months of tagged trades to mine v4.

---

## Shipped 2026-06-12 (LENS_EDGE_v3 + the loop)

- **`ict_miner.py`** — re-mined all 464 trades in ICT/visual language.
  Headline: user is a momentum-CONTINUATION trader (sweep-with 50% WR vs
  sweep-fade 33%). Five robust setups, seven vetoes. Mechanical first-touch
  at realized geometry (0.63% SL / 0.95% TP) is still coin-flip → setups are
  discretionary checklists, NOT bot signals.
- **`strategies/LENS_EDGE_v3_ICT/`** — FINDINGS.md (playbook + NONE-bucket
  autopsy: minus 5 outliers it's −€736 · hold-time table: 2–8h holds made
  +€1,552 at 50% WR, sub-2h bled −€747 at 34–35%) and indicator.pine
  (TradingView HUD: setup markers, veto shading, live checklist, alerts).
- **`app/setups.py`** — setup engine: hourly scan CLI (`python3 -m app.setups`),
  signals into the existing /signals approve/reject flow, ntfy phone push
  (`LENS_NTFY_TOPIC`), auto setup_tag backfill (464/464 tagged; VETO bucket
  = 302 trades, 36.4% WR, −€1,760), per-tag scoreboard with drift halves.
- **`/desk` page** — live verdict per direction (ENTER / BLOCKED / STAND
  DOWN), always-on trade ticket in € (size, margin at 10x, win/early-exit/
  stop outcomes, stop as % of account), live S1–S5 checklists, scoreboard.
- **`LIVE_SCALP_v1`** baseline in backtest engine + Monte Carlo input seeding
  from live trades or any backtest strategy.

**Open:** install the crontab line (permission-denied for the agent), set
`LENS_NTFY_TOPIC` in prism.env, then trade only S1–S5 and let tags accumulate.

The 4H/4R trend thesis below is a separate track and still unproven — v3
showed realized trading is 1H-context with 2–8h holds, not 4H swing.

---

## The locked thesis (decided 2026-06-02)

> Trade BTC perps on Kraken, with the 4H trend, risking a fixed **10% of account
> to make 40%** (a **4R** trade). The edge is **holding winners to target**, not
> win rate. 44% WR is fine — **R is the lever** because it's the exit choice you
> control.

Locked parameters: 4H · 10x (≡ 5x @ 2% stop) · 1% stop = 10% account risk ·
4% TP = 40% gain · ~1 trade/UTC day · skip Saturday.

**Honest correction made this session:** after real fees (0.30% round trip), the
clean "4R" is really **~2.85R** (win +37% / loss −13% of account). That is the
true number the tools now report.

---

## Shipped this session

- **`/projection` page (parameter-first)** — lock the params, dial the win rate,
  project the equity curve forward with P05–P95 bands + WR-vs-R sensitivity
  tables. Now uses the real **0.30% round-trip fee** (adjustable on the page).
  Lives alongside the original goal-first dashboard at `/`.
- **`compute_projection()`** in `app/calculator.py` — the math engine for the above.
- **`strategies/TREND_4R_v1/`** — Pine v6 strategy hard-wired to the thesis
  (4H, with-trend, fixed 1% / 4% / 10x, €360 base, 0.15%/side commission).
  `BASELINE.md` frames the experiment and how to read the Strategy Tester.
- **`MOM_BREAK_v1` marked on-hold** — scalping was rejected as incompatible with
  the account-risk math.
- **`start.sh`** prints the dashboard link (localhost + LAN) on launch.
- **README rewritten** — plain-English explanation, both pages, the 4R philosophy,
  flow diagram, run instructions, honesty section.
- **Research docs added** — `Compounding 10% returns over 120 trades.md`,
  `PRISM-SYSTEM-SPEC (1).md`.

---

## Validated vs. not

| | State |
|---|---|
| Goal calculator, projection, exchange sync, signal ingestion, discipline | ✅ working |
| Trade mechanics proven live (1 trade: €360 → €504) | ✅ but n = 1 |
| `TREND_4R_v1` strategy code | ✅ written, ❌ **not backtested** |
| **4R reachable at a 1% stop, at ~44% WR?** | ❌ **THE open question** |

The 44% WR is inherited from history at *wider* stops; a 1% stop is tight and may
lower it. Breakeven WR at this setup is **~26%** — that's survival; 44% is the hope.

---

## Next step (the one that matters)

1. Load `strategies/TREND_4R_v1/strategy.pine` on a **BTC perp 4H** chart in
   TradingView → Strategy Tester → ~12 months.
2. Fill in `BASELINE.md`: **win rate, avg-R, profit factor, max drawdown**.
3. Read the result against the bar in `BASELINE.md`:
   - WR ≥ ~35% & avg-R ≥ 3 → green light (forward-test, then wire Notify).
   - WR < 20% or PF < 1 → the 1% stop premise fails; fix entry quality, not leverage.

Everything downstream (alerts, the dataset, compounding) waits on that number.

---

## Decisions on record

- **Local SQLite only** — Supabase from the new spec was dropped (standing
  "local data only" constraint wins).
- Work lives on branch **`lens-4r-projection`** (direct pushes to `master` are
  blocked by review guard); merge to master when ready.
