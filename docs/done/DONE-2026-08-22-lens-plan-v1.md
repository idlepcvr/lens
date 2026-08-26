# DONE — LENS Build Plan v1 (archived 2026-08-22)

[Open as HTML](DONE-2026-08-22-lens-plan-v1.html)

*Archived, not deleted. This was the v1 build plan, written 2026-05-25 against
an 8-week target. v1 shipped; the loop has been live since 2026-06-16 and has
placed live orders since 2026-08-20.*

**Two reasons it is archived rather than updated.** Its open items were last
touched 2026-07-14 and every one of them has either shipped or moved to
`NEXT_SESSION.md`. And it contradicts itself on the goal — line ~20 calls
"50 BTC by 2028-12-31, goal_plan v1" settled, while the closing line says
"150 BTC @ €250k target". The second is the live one: `goal_plan` is at **v9**,
north star **150 ₿**, with 50 ₿ as the waypoint.

**Where its job went:** open work is `NEXT_SESSION.md`, shipped history is
`CHANGELOG.md`, and what the product *is* lives in `PRODUCT.md`. Three files with
one owner each, rather than a fourth drifting between them.

Kept because the reasoning below — especially "let the data do its job, don't
preempt v2 decisions" — is the reasoning the project has actually followed.

---

---

## Open items (2026-07-14)

1. **Run the loop.** Still the real bottleneck, not code — 4 of ~500 trades
   carry a signal link. Take the next valid alert, let it auto-tag on sync,
   accumulate tagged live trades toward the v4 re-mine (~3 months needed).
2. **Log a stack snapshot on `/goal`** (two minutes). The projection has a
   0 ₿ fallback since 2026-07-11, but real rung dates need a real snapshot.
3. **Retire the stale engine target** — `lens_config` still carries
   `€100 → €55,000 by 2026-12-31`; it feeds the /edge Fit sweep and
   `compute_goal`, so feasibility verdicts measure against a number nobody
   ratified. Pick an engine-equity target or delete it. (The stack-level goal
   is settled: 50 BTC by 2028-12-31, `goal_plan` v1.)
4. **Forward-test before any promotion** (~early Aug 2026) — the three v3
   search families stay shadow-registered until they hold on fresh data.
5. **Next dimension:** order-flow features (CVD, delta, funding, OI) — needs a
   data source first.

---

## What changed (and why)

PRISM v0.1 was a proof of concept. It validated that local SQLite + FastAPI + exchange sync works, that the goal calculator math is sound, and that a single-user trading dashboard can run on a miniPC without cloud dependencies. But the architecture grew around discoveries instead of intent — alerts were bolted on then ripped out, Supabase came and went, scope kept expanding.

LENS starts clean with a single intent: **build the dataset that makes month-6 predictive scoring possible.** Every architectural decision serves that one goal.

The mechanism: every trade decision in LENS originates from a Pine Script strategy that emits structured features. Every signal — taken or skipped — is stored as a row with the full feature schema. Every taken signal links to an executed trade via exchange sync, which attaches outcome data. After ~150–300 trades, the dataset (features → outcome) is ready to train predictive models on. Until then, per-strategy expectancy on real fills is the edge-discovery feedback loop.

---

## Scope

### In v1
- Local SQLite (port schema from v0.1)
- Kraken + Bybit sync (port from v0.1)
- Goal calculator + ATR-adaptive sizing (port from v0.1)
- Pine Script strategies emitting locked JSON schema
- Signal ingestion endpoint (webhook or alternative)
- `signals` table with full feature schema
- Pending-signals decision view (approve / reject)
- Signal → trade linking via symbol + timestamp match
- Per-strategy stats view (n, win rate, avg R, expectancy)
- Chart screenshot capture on approve
- Single-page dashboard on miniPC, accessed via LAN or tunnel
- **Persisted goal config + interactive goal dashboard at `/`** *(pulled forward from Wk 4 sizing dependency; added Wk 1)*
- **Server-side discipline filters in `/api/signals`** auto-reject Saturday / sub-5min cooldown / bleed hours / wrong venue *(added Wk 1 after PRISM fingerprint research showed bulk discretionary trading is break-even; selection discipline is the bottleneck)*
- **`/glossary` ("Learn") reference page** plain-English explainer for every goal-model / ticket metric — EV, R:R, leverage, notional, fee drag, account risk, true R:R, Kelly + sixth-Kelly, DD constraint, optimal-vs-required, expectancy/PF + a worked example *(added 2026-06-21 — static page on the shared .help-body style, no compute; serves the "I don't understand the elements" gap)*. Inline `?` badges (`.qh`) on `/goal` (EV / Actual R cards + Risk & Kelly title) and the order ticket (R:R, risk, full-ticket header on `/desk` + `/signals`) deep-link to the matching `/glossary#anchor`.

### Out of v1 (defer to v2+)
- ML prediction model — earn in at month 6 once dataset exists
- AI journaling layer (Claude API per trade) — earn in if v1 reveals discretionary trades that don't fit defined strategies
- Mobile app — TradingView app + LENS web view is enough
- Execution bot — never until edge is proven on n≥100 per strategy
- Client management — AKA is in CVL, not relevant
- Cloud sync of any kind — local-first by choice

### Hard constraints
- Local data only (no Supabase, no external DB)
- Existing v0.1 keeps running until v1 is cut over
- No work on LENS that doesn't appear in this plan without updating this plan first

---

## Architecture

```
                TradingView
                    │
                    │  Pine Script v5 strategy
                    │  emits JSON alert with full schema
                    ▼
              ╔═════════════╗
              ║  INGESTION  ║  (Cloudflare tunnel webhook
              ║   ENDPOINT  ║   OR email poll OR phone-tap URL)
              ╚══════╦══════╝
                     │
                     ▼
             ┌───────────────┐
             │ signals table │  pending → approved/rejected
             │   (SQLite)    │
             └───────┬───────┘
                     │
                     │  approve → create pending trade
                     │  link via symbol + ts window
                     ▼
             ┌───────────────┐
             │  trades table │ ← Kraken/Bybit sync attaches fills
             └───────┬───────┘
                     │
                     │  trade closes → outcome computed
                     ▼
             ┌───────────────┐
             │  stats engine │ → per-strategy WR, expectancy, R
             └───────────────┘
                     │
                     ▼
            month 6: train (features → outcome)
            classifier, feed prediction back to
            incoming signals
```

---

## Feature Schema (LOCKED — don't drift)

Every signal row must carry every field. Schema consistency is the lever for month-6 ML. If a field can't be filled, store `null` — don't omit the column.

```
# Identity
signal_id            UUID
strategy_name        TEXT  (e.g. "MACD_MTF_v1")
strategy_version     TEXT  (e.g. "v1.0.3")
received_at          TIMESTAMPTZ

# Context
symbol               TEXT  (e.g. "BTCUSDT.P")
venue                TEXT  (kraken | bybit)
session_utc          TEXT  (asia | london | ny | off-hours)
btc_1d_trend         TEXT  (up | down | range)
btc_1w_trend         TEXT  (up | down | range)
atr_14d_pct          NUMERIC

# Setup
trigger_type         TEXT  (macd_cross | bos | obr | fvg_fill | etc.)
htf_bias             TEXT  (bullish | bearish | neutral)
mtf_confluence       JSON  (array of confirming signals)
confluence_count     INT   (0–5)

# Trade plan
direction            TEXT  (long | short)
entry_price          NUMERIC
stop_price           NUMERIC
target_price         NUMERIC
suggested_size_pct   NUMERIC  (% of account at signal time)
suggested_leverage   NUMERIC
expected_rr          NUMERIC

# Decision (filled at approve/reject)
status               TEXT  (pending | approved | rejected | expired)
your_conviction      INT   (1–5, filled on approve)
rejection_reason     TEXT  (filled on reject)
decided_at           TIMESTAMPTZ

# Execution linkage (filled by sync)
linked_trade_id      INT   (FK to trades table)

# Outcome (filled when trade closes)
outcome              TEXT  (win | loss | breakeven | open)
r_realized           NUMERIC
pnl_eur              NUMERIC
hold_duration_min    INT

# Optional enrichment
screenshot_path      TEXT
notes                TEXT
```

This schema is the contract between Pine Script (producer) and LENS (consumer). Every Pine strategy must output every Setup + Trade plan field. Every LENS table column matches a schema field. Changes require a version bump on `strategy_version` and a migration entry in CHANGELOG.

---

## 8-Week Plan

### Week 1: Foundation (May 26 – Jun 1)
**Objective:** New repo, clean SQLite schema, sync ported from v0.1.

**Deliverables:**
- [ ] New repo `lens` initialized, README with one-paragraph mission
- [ ] SQLite schema migrated: `trades`, `signals`, `daily_snapshots`, `transfers`
- [x] Kraken sync ported, writes to LENS DB *(cron deferred — manual `/api/sync/kraken` works; timer to be added when needed)*
- [x] Bybit sync ported, writes to LENS DB
- [x] FastAPI scaffold, `/health` and `/api/trades` working
- [x] systemd user unit installed, runs on boot
- [x] **(bonus)** Interactive goal dashboard at `/` with persisted `lens_config`
- [x] **(bonus)** Server-side discipline filters auto-reject bad signals
- [x] **(bonus)** PRISM trade-history fingerprint analysis → `strategies/_research/prism_fingerprint.md`

**Definition of done:** ✅ `curl localhost:8765/api/trades` works; LENS persistent across reboots.

---

### Week 2: Pine Script v1 (Jun 2 – Jun 8)  *(started early)*
**Objective:** First strategy emitting locked schema, baseline backtest captured.

**Deliverables:**
- [x] `MACD_MTF_v1` Pine v6 strategy file *(now DEPRECATED — baseline PF 0.11, no edge)*
- [x] `alert()` message emits full JSON matching Setup + Trade plan schema fields
- [x] Strategy Tester run on 9 months BYBIT BTCUSD.P 15m → see `MACD_MTF_v1/BASELINE.md` (failed)
- [x] Document baseline (failure documented as negative reference)
- [x] Manual webhook test: JSON shape validated against `/api/signals` → 201 round-trip works
- [ ] **`MOM_BREAK_v1` Pine v6 strategy** — consolidation-break scalp built from PRISM fingerprint, ready to backtest
- [ ] Strategy Tester run on `MOM_BREAK_v1` → fill `MOM_BREAK_v1/BASELINE.md`

**Definition of done:** `MOM_BREAK_v1` Strategy Tester baseline shows PF ≥ 1.4 and WR ≥ 45% over 6 months. If not, iterate or pivot entry premise.

---

### Week 3: Ingestion + signals table (Jun 9 – Jun 15)
**Objective:** TradingView → LENS database end-to-end.

**Decision before Week 3 starts:** ingestion path.
- (a) Cloudflare tunnel + webhook — cleanest, requires tunnel back up
- (b) Email-to-LENS — TradingView emails JSON, LENS polls Gmail
- (c) Phone-tap URL — alert opens `lens.local/signals/new?payload=...`

**Deliverables:**
- [ ] Ingestion path chosen + provisioned
- [ ] `POST /api/signals` endpoint validates JSON against schema, writes to DB
- [ ] Schema validation rejects malformed payloads with clear error
- [ ] End-to-end test: alert fires → row in `signals` table within 30 sec
- [ ] First 5–10 live signals captured (paper-mode strategy still fine)

**Definition of done:** signal arrives in LENS DB without manual intervention.

---

### Week 4: Decision view (Jun 16 – Jun 22)
**Objective:** Approve/reject UI with live context.

**Deliverables:**
- [ ] `/signals` page lists pending signals
- [ ] Each row shows: full feature JSON, live-balance-adjusted size in EUR, strategy historical stats (even if n<20)
- [ ] APPROVE button: requires conviction score (1–5), creates pending trade record, links signal_id
- [ ] REJECT button: requires reason text, marks signal rejected
- [ ] Auto-expire signals older than 30 min (status → `expired`)
- [ ] Mobile-responsive layout (you'll use this on phone)

**Definition of done:** end-to-end: signal arrives → you see it on phone → tap approve → trade record created in `trades` with `linked_signal_id` set.

---

### Week 5: Linking + outcomes (Jun 23 – Jun 29)
**Objective:** Real fills auto-link to signals, outcomes compute.

**Deliverables:**
- [ ] Sync job matches new fills to approved signals: symbol match + entry within ±10 min of approval timestamp
- [ ] Match confidence score logged; ambiguous matches flagged for manual review
- [ ] Trade close → outcome computed: win/loss/BE, R realized, PnL EUR, hold duration
- [ ] Signal record updated with outcome
- [ ] Backfill: link any historical signals from week 3–4 to their trades

**Definition of done:** trade closes on Kraken → within 1 sync cycle, signal row shows outcome + R realized.

---

### Week 6: Stats + polish (Jun 30 – Jul 6)
**Objective:** Per-strategy stats view, screenshot field, UI cleanup.

**Deliverables:**
- [ ] `/stats` page: per `strategy_name` table showing n, WR%, avg R, expectancy, current streak
- [ ] Below n=20 shows "building sample" — no stats until threshold
- [ ] Approve flow accepts chart screenshot upload (optional)
- [ ] Screenshots stored at `data/screenshots/{signal_id}.png`
- [ ] Equity curve chart for taken trades
- [ ] Cutover plan written: how to transition off v0.1 (v0.1 stops, LENS becomes primary)

**Definition of done:** stats view reflects week 4–5 live signals correctly.

---

### Week 7: Go live (Jul 7 – Jul 13)
**Objective:** LENS becomes the system you trade through.

**Deliverables:**
- [ ] PRISM v0.1 stopped (kept for read-only reference)
- [ ] All trading goes through LENS Pine alerts → decision view → execution
- [ ] Daily review: any UX friction logged in `SCRATCHPAD.md`
- [ ] Hot fixes only — no scope expansion this week

**Definition of done:** 7 days of live trading exclusively through LENS, ~15 signals captured, 0 manual paste workarounds.

---

### Week 8: Iteration + second strategy (Jul 14 – Jul 20)
**Objective:** Add strategy #2, fix anything painful from week 7.

**Deliverables:**
- [ ] `MACD_MTF_BOS_v1` strategy (MACD MTF + Break of Structure confirmation)
- [ ] BASELINE.md for new strategy
- [ ] Address top 3 friction points from week 7 SCRATCHPAD
- [ ] Retro: write `RETRO_W8.md` covering what shipped, what was harder than expected, what changed about your understanding

**Definition of done:** Two strategies live in PRISM, 30+ signals captured with full schema, retro published.

---

## Workflow

### Daily (15 min, morning)
- Check last 24h signals: any expired due to slow decision? any rejected — note why
- Skim `SCRATCHPAD.md`, add any new friction items
- Pick one critical-path task from current week, time-box one focused block
- Don't context-switch to a different week's task — finish current week first

### Weekly retro (Sunday, 30 min)
- Update `PROGRESS.md` with the week's actuals (use format below)
- Mark shipped vs not-shipped from week's deliverables
- For not-shipped: write the reason (one sentence) and decide: roll forward, deprioritize, or kill
- Identify top 3 tasks for next week, write them at the bottom of `PROGRESS.md`
- If blocked on a decision, write the decision needed at the top of next week's section

### Monthly (last Sunday of month)
- Per-strategy stats review (once any strategy has n≥20)
- Decide: keep firing / kill / version-bump and adjust
- Architecture review: anything to retire from this plan? anything to add?
- Update this PLAN.md file directly if scope changes — don't let scope drift silently

### Anti-rituals (things NOT to do)
- No rebuilding or "refactoring while you're there" — only the deliverables on the plan ship
- No new feature ideas committed mid-week — they go in `IDEAS.md`, reviewed monthly
- No comparing to PRISM v0.1's UX — v1 is a different system, decide on its own merits

---

## Metrics

### Lead metrics (weeks 1–6 — build phase)
- Weekly objectives shipped % (target: ≥80% per week)
- Days since last commit (target: ≤2)
- Signals ingested per week (track from week 3, expect 0 → 15 by week 7)

### Lag metrics (weeks 7+ — live phase)
- Signals per week (expect 15–20 given your ~63 trades/mo cadence)
- Approve rate vs reject rate (no target, just observe)
- Per-strategy expectancy after n≥20 — this is the real edge signal
- Rolling 30-trade win rate (compare to v0.1's 43.1% baseline; improvement = selection working)

### Health checks (always on)
- Sync failures > 0 in 24h = drop everything, fix
- Signals stuck `pending` > 1h = ingestion broken or you stopped looking
- Trades without `linked_signal_id` after week 7 = either manual entry (note in notes field) or linking is broken

---

## Progress Tracking

### File: `PROGRESS.md` (in repo root)

Append a section per week, append-only, never edit history:

```markdown
## Week N: [start date] – [end date]

### Shipped
- [x] task 1
- [x] task 2

### Not shipped
- [ ] task 3 — reason: blocked on tunnel decision

### Blockers
- decision needed on X

### Decisions made
- chose option (a) for ingestion because...

### Top 3 for next week
1. ...
2. ...
3. ...
```

### File: `SCRATCHPAD.md`

Append-only daily notes. Friction, ideas, bugs, dead-ends. Reviewed during weekly retro.

### File: `IDEAS.md`

Park lot for v2+ ideas. Reviewed monthly. If nothing's been added in a month, the system is too constrained — relax. If it's filling up weekly, scope is being threatened — be ruthless.

---

## Open decisions (need answer before Week 1)

- [ ] **Project name confirmed?** Default: LENS. Alternatives: HELM, AXIS.
- [ ] **Ingestion path for Week 3?** (a) Cloudflare tunnel + webhook | (b) email poll | (c) phone-tap URL.
- [ ] **First Pine strategy:** MACD MTF alone, or MACD MTF + BOS combined as v1? Recommend alone first — cleaner baseline.
- [ ] **Cutover behavior:** v0.1 keeps logging in parallel during weeks 7–8, or stops on day 1 of week 7? Recommend parallel — fallback if LENS breaks.

---

## What this plan is not

It's not the final architecture. It's the smallest version that builds the dataset. v2 decisions (ML model, AI journaling, mobile app, execution bot) get made based on what v1 data shows you. Don't preempt those decisions now — let the data do its job.

If at week 8 the data says one strategy works and others don't: kill the others, specialize, scale that one. If nothing works: the methodology is the problem, not the tooling, and you go reread ICT or pivot to a different framework. Either way, you have evidence instead of guesses, which is the whole point.

---

*Goal remains: 150 BTC @ €250k target by 31 Dec 2028.*
*v0.1 proved the system can run locally. v1 proves the system can identify edge. v2+ proves the system can scale it.*
