# LENS

**A personal cockpit for trading BTC perpetual futures with discipline.**

LENS runs locally on a miniPC (FastAPI + SQLite, no cloud) and you open it in a
browser. Nothing here trades for you — it's a thinking/measuring tool. You place
the trades on Kraken yourself.

It started as a "hold winners to 4R" discipline tool. Then we mined the actual
trade history (464 closed Kraken trades) and the data said something different —
so LENS now has a primary, evidence-based job and a secondary, still-unproven one:

1. **Trade the mapped edge (LENS_EDGE_v3)** — five setups and seven vetoes mined
   from the real fills, run as a live loop: hourly scanner → phone alert →
   `/desk` checklist → trade on Kraken → auto-tagged on sync → per-setup
   scoreboard → re-mine when enough data accumulates.
2. **The 4H/4R thesis (legacy track)** — plan/projection tooling for the
   "risk 10% to make 40%" idea. Still unproven; kept and clearly labelled.

---

## What the data actually said (LENS_EDGE_v3, 2026-06-12)

Mined from 464 real trades (41.8% WR, €+736) with outlier-trimming and
old-half/new-half robustness checks. Full detail:
`strategies/LENS_EDGE_v3_ICT/FINDINGS.md`.

**You are a momentum-continuation trader, not a reversal trader.**
Trading *with* a liquidity sweep: 50% WR, €+15/trade. Fading the sweep
(classic ICT turtle-soup): 33% WR. Displacement with you: 55%. Against: 35%.

**Five setups that survived everything** (realized/mined WR):

| ID | Setup | Direction | WR |
|---|---|---|---|
| S1 | NY AM killzone flush — RSI<40 + 3 bear bars, 13–16 UTC | short | 90.9% (n=11 tagged) |
| S2 | Premium of 7d range + bearish displacement | short | 65% |
| S3 | RSI>55 + buyside sweep (continuation) | long | 56.7% (n=30) |
| S4 | RSI<40 in discount, no recent sweep | long | 62% |
| S5 | RSI>55 in London killzone 07–10 UTC | long | 60% |

**Seven vetoes — where the account bleeds** (302 of 464 trades, −€1,760):
RSI 40–55 dead zone · 1h EMA21 slope against · fading a sweep · fading a
prior-day-level raid · displacement against · entering inside an FVG retrace ·
NY PM 18–21 UTC.

**Timeframe, settled by the fills:** 1H context, winners resolve in 2–8h
(+€1,552 at 50% WR). Sub-2h trades — over half of everything — bled −€747 at
34–35%. Not a 1m/5m scalper, not (yet) a 4H swing trader.

**The honest caveat that defines the whole design:** mechanically (take every
occurrence, no judgment) every setup is a coin flip at the realized
0.63% SL / 0.95% TP geometry. The 57–91% realized WR came from *discretionary
selection inside these contexts*. So LENS alerts and checklists — it never
auto-enters. Off-playbook trades ("NONE" tag) look profitable only because of
5 outlier wins; without them they're −€736.

---

## The loop (how it actually helps on a live trade)

```mermaid
flowchart TD
    CRON["hourly scanner\npython3 -m app.setups (cron)"]
    NTFY["phone push (ntfy)\n'S1 — SHORT setup live'\n+ TAKE A+ / TAKE / SKIP buttons"]
    DESK["/desk\nverdict + checklist + ticket in EUR"]
    ME["Me\ntap TAKE/SKIP on phone\n(or decide on /signals)"]
    KR["Kraken\nplace the trade"]
    DB["LENS server\nfills synced + auto setup_tag"]
    SB["scoreboard /api/stats/setups\nrealized vs mined WR, drift halves"]
    V4["re-mine (v4)\nwhen enough tagged trades"]

    CRON --> NTFY --> DESK --> ME -->|execute| KR -->|MANUAL sync| DB --> SB --> V4 -->|better setups| CRON
    CRON -->|pending signal| DB
    ME -.->|button POSTs decision| DB
```

**Decide from the phone (no app-switch).** Each ntfy push carries three HTTP
action buttons — **TAKE A+** (approve, conviction 5), **TAKE** (approve,
conviction 3), **SKIP** (reject) — that POST straight to
`/api/signals/{id}/decide`. The *phone's* ntfy app makes that request, so the
LENS server must be reachable from the phone: works on home wifi (LAN), needs a
public tunnel on mobile data. Target URL is `LENS_BASE_URL` (see *Running it*).

**The one manual step:** the hourly cron does **not** pull your fills from
Kraken — `run_scan_cli` only scans, emits, notifies, and tags *already-synced*
untagged trades. After you place a trade you must run a Kraken sync
(`POST /api/sync/kraken`, or just open the dashboard) for the fill to land in
the DB and get its `setup_tag`. Automate it with the optional sync cron below.

Every signal — taken or skipped — lands in the `/signals` approve/reject flow
with discipline filters (no Saturday, bleed hours, cooldown). Every synced trade
gets a `setup_tag`. That tagged dataset is what v4 will mine — including new
feature candidates (order flow: CVD, delta, funding, open interest).

---

## The pages

Start the server (below), then visit **http://localhost:8765**. The home page
("/") is a **two-door mode chooser** — the app is split into two systems that
never share a nav (2026-06-17):

- **PROP** — pass the Kraken Prop eval. Nav: **Goals · Strategy · Risk ·
  Survival · Rules · Equity · Regime · Backtest**.
- **HEDGE** — discretionary own-money trading (the S1–S5 edge). Nav:
  **Dashboard · Desk · Signals · Review · Projection**.

A `◎ PROP | ▤ HEDGE | ⌂` switch sits above every nav; switching = jumping to
that mode's home (stateless).

### Web UI / design system (2026-06)

A shared, responsive **design system** lives in **`app/theme.py`** — the single
source of truth for the whole app:

- **`LENS_CSS`** — the dark "cockpit / HUD" theme. Design tokens (surfaces, text,
  accent + status colors, radii, glow elevation), the type system (Chakra Petch
  display + JetBrains Mono data), every component class, and responsive rules at
  680px / 1080px. Served **once** at `/assets/lens.css` and `<link>`ed by every
  page, so the browser caches it and there is exactly one place to change styling.
- **`shell(path, label, body, *, script, head_extra, meta)`** — the page
  template. Wraps any body in the standard head (fonts + favicon + css), the
  sticky top bar, and the **mode-aware** scroll-chip nav + PROP|HEDGE switch
  (current page auto-highlighted). Page-specific CSS goes in `head_extra`; JS in `script`.
- **`FAVICON_SVG`** — the brand mark (a scope / aperture iris; LENS = optics),
  served at `/assets/favicon.svg`.
- **`NAV_PROP` / `NAV_HEDGE`** — two lists, one per mode. `page_mode(path)` maps
  each route to its mode; `nav_html()` renders only that mode's chips. Add a page
  to the right list once and it appears in that mode's nav.

**To add a page:** `from .theme import shell` → build `body` (+ optional
`head_extra` CSS that aliases local var names onto shared tokens, e.g.
`--ac:var(--accent)`) → `return shell("/x", "X", body, ...)`. To restyle the
**entire** app, edit `LENS_CSS` once.

- **`/style`** — **living style guide.** Renders every token + component straight
  from `lens.css`, so it's both the design docs and a visual regression check.
  See also **`BRAND.md`** (logo, voice, palette in one page).
- **On `shell()`:** `/desk`, `/signals`, `/`, `/projection`, `/backtest`,
  `/montecarlo`, `/prop`, `/style` — all share the bar/nav and carry a
  collapsible "❔ how to read this …" explainer.
- **Recolor exception:** `/review` keeps its bespoke full-viewport 3-pane chart
  workstation layout (doesn't fit the scrolling shell), but uses the shared
  palette + fonts.
- **Compare routes** (throwaway, delete on signoff): `/desk-old`, `/signals-classic`.

Built phone-first — open it on the iPhone (Safari → Add to Home Screen for a
fullscreen app feel), it reflows for iPad / desktop.

### `/desk` — **the live one. "Can I enter right now?"**
Per-direction verdict (ENTER / BLOCKED / STAND DOWN) with the active vetoes
spelled out, live S1–S5 condition checklists (✓/✗ per condition), and an
always-on trade ticket in money: entry/stop/target/R:R, position size from your
risk €, margin at 10x, and the three outcomes — if target / if +0.7% early
exit / if stopped (as % of account). A collapsible **"how to read this desk"**
panel explains it in plain English. When a signal is pending, a thumb-zone
**TAKE A+ / TAKE / SKIP** bar decides it in place. Refreshes every 60s.

### `/signals` — approve/reject queue
Scanner-emitted (and Pine-webhook) signals land here as pending, each with
inline **TAKE A+ (conv 5) / TAKE (conv 3) / SKIP** buttons (same decision path
as the desk + the ntfy phone alert → `POST /api/signals/{id}/decide`).
Decisions, conviction, and rejection reasons are stored — skipped signals are
data too. Recent decisions listed below the queue.

### `/review` — replay real trades on an ICT-style chart
Every closed fill with its entry context computed. Where v1→v3 came from.

### `/` Dashboard + `/projection` — the 4R planning track (legacy)
Goal-first ("what does each trade need to do?") and parameter-first ("where do
locked params land?") calculators with percentile bands, fee-honest R, ruin %.

### `/backtest` + `/montecarlo` — pressure-testing
Backtest engine over cached OHLCV (includes `LIVE_SCALP_v1`, a baseline that
reproduces the realized ~42% WR from pure SL/TP geometry — the bar any
strategy must beat). Monte Carlo can seed its inputs from live trades or any
backtest strategy.

### PROP mode — the eval cockpit, split into engines
`/prop` is the **Goals hub**: a visual target corridor (floor ── start ──
target) + the 3 structural upgrades, each linking to its engine page. The
engines (all fed by one `prop_views.prop_metrics()` so no two views drift):
**`/strategy`** (WR · R · expectancy R/%), **`/risk`** (risk %/$, stop,
position-size formula, leverage), **`/survival`** (DD limit · max historical DD ·
loss-streak stress table · days-to-breach), **`/rules`** (the live constraint
layer), **`/equity`** (Monte Carlo equity sim from WR+RR — paths, drawdown,
failure frequency), **`/regime`** (BULL/SIDEWAYS/BEAR + hero WR per regime). See
the **Prop track** section below.

### `/style` — living style guide
Every design token + component rendered straight from `lens.css` — the design
docs and a visual regression check in one page. Brand/logo/voice, the full
colour palette, type scale, spacing, and all components. Written companion:
**`BRAND.md`**.

---

## Prop track — Kraken Prop Trading (via Breakout) ✅ BUILT

A **separate system** from the hedge-fund thesis above. LENS-proper maximises
compounding on your own money (risk 10%/trade for 40%). A prop eval is the
opposite game: **survive hard equity walls to a modest target.** Risk 10%/trade
and one stop blows the whole eval. So the prop track has its own objective
function — **pass-probability, not expectancy** — and its own simulator + page.

Firm: **Kraken Prop**, powered by **Breakout** (the prop firm Kraken acquired
Sept 2025). Funds you up to **$200,000**. Rules verified live at
**kraken.com/breakout, 2026-06-17.**

### What's built (`/prop` engine pages + `app/prop_eval.py`)

- **Eval rules engine** — `EVALS` dict: Breakout 1-Step Classic / Pro / Turbo +
  2-Step, each with daily-loss / max-drawdown / target / leverage cap **and the
  per-side fee** (`commission_per_side` — the fee is a venue property, so it
  lives on the eval rule and overrides any strategy default).
- **Eval simulator** — replays any LENS strategy at *legal* sizing under the
  walls, **open-equity** (each trade's worst adverse excursion is tested against
  the live walls, not just its closed PnL). `simulate_eval()` + bootstrapped
  `monte_carlo_eval()` + `eval_summary()` (the one source of truth for the pages).
- **Full sweep** — `python3 -m app.prop_eval sweep` (one eval) or `sweep-all`
  (every eval) ranks strategy × risk by pass%.
- **Engine pages** (see PROP mode above) — Goals hub + Strategy / Risk / Survival
  / Rules / Equity / Regime, all fed by `prop_views.prop_metrics()`.

### Verified rules — the constraint layer

Kraken Prop is unusually permissive — the dangerous gotchas **don't exist**:

| | Value |
|---|---|
| Time limit | **NONE** |
| Consistency rule | **NONE** (one big win can't void the eval) |
| Minimum trading days | **NONE** (pass in a single trade) |
| Daily loss | 3%, resets 00:30 UTC |
| Max drawdown | static (does NOT trail) — 6% Starter / 5% Intermediate / **3% Advanced** |
| Profit target | 10% Starter / 12% Intermediate / **9% Advanced** |
| Leverage cap | 5x BTC (2–3x alts) |
| Fees | **0.04%/side** (maker+taker) |
| News / weekend holding | allowed |

Plan ↔ page names: **Starter = `CLASSIC`**, Intermediate = `PRO`,
**Advanced = `TURBO`**. Two kill conditions only, both on **live equity**: touch
the static floor, or lose the daily limit in one day.

### The locked plan (budget-driven: €20 = Advanced)

> **`ASIAN_RSI_DIP_v1`** — 4H, Asian killzone (00:00+04:00 UTC), 1% stop / 4% TP (4R).
> - Eval fees scale with **plan × wallet**. The cheapest eval is the **5k Advanced
>   at €20** (Starter/Classic 5k = $45). With only €20 → **Advanced, one shot, no
>   retry budget** → optimise *single-attempt pass*, not expected-cost-over-retries.
> - **On a 3% static wall, risk % is everything.** Single-shot pass for the hero:

| Risk / trade | Leverage | Pass % | |
|---|---|---|---|
| **0.5%** | 0.5x | **~89%** | **the play** — one loss is tiny, survives a cold start |
| 0.75% | 0.75x | ~74% | faster, still solid |
| 1.0% | 1.0x | ~59% | risky on a 3% wall |
| 2.0% | 2.0x | ~35% | two losses ≈ bust — don't |

> **DECISION: buy the €20 5k Advanced, trade the hero @ 0.5% risk → ~89% one-shot.**
> It's a slow grind (~1.5 trades/mo, no time limit). Ladder up by buying bigger
> Advanced evals **from profit** (200k Advanced = $660). Only a **higher-WR entry**
> lifts the ceiling past 89% — 4R @ 1% stop is already dial-tuned (6R/8R/tighter
> stops all tested worse).

Mechanic at 0.5% on $5k: WR ~41%, win +1.96%, loss −0.54% of account, ~1.5
trades/mo. It takes **~6 losses in a row** to hit the floor (≈4% odds). The
hero's edge is regime-dependent — **BULL ~50% WR vs BEAR ~25%** (see `/regime`),
and with no time limit, waiting for a kinder regime is a free lever.

### Steps taken (2026-06-17)
1. **Verified live rules** at kraken.com/breakout — no time limit / consistency /
   min-days; fees 0.04%/side (sim was modelling 0.15% → ~3.6pts pessimistic, fixed).
2. **Pivoted to the €20 Advanced plan** (3% DD) and found **risk % is the whole
   game** — 0.5% = ~89% single-shot, 2% = ~35%.
3. **Split the app into PROP / HEDGE modes**; rebuilt `/prop` into a Goals hub +
   engine pages (Strategy / Risk / Survival / Rules / Equity).
4. **Ported the market-regime analytic** (`/regime`) and added hero WR-per-regime.

### Next (later)
- [ ] **Forward-test** ASIAN_RSI_DIP_v1 @ 0.5% on demo before paying the €20.
- [ ] Long game: lift WR via the **HEDGE** discretionary edge (real flush WR ~60%
      vs 40% mechanical) → the only way past the 89% ceiling.

Full detail: [`strategies/_prop/BREAKOUT_5K_PLAN.md`](strategies/_prop/BREAKOUT_5K_PLAN.md).

**Sources:** thetrustedprop.com/prop-firms/breakout-prop ·
quantvps.com/blog/breakout-crypto-prop-firm-rules ·
proptradingvibes.com/blog/breakout-faq · **verify on the Breakout dashboard before trading.**

---

## Strategies (the TradingView side)

`strategies/` holds Pine Script. Load in TradingView → Pine Editor.

- **`LENS_EDGE_v3_ICT/indicator.pine`** — **the current one.** Not a strategy:
  a HUD. S1–S5 markers, veto background shading, ghost-marks where a setup
  fired but was vetoed, live checklist table, per-setup alerts.
- `LENS_EDGE_v2/` — the flush short + the mechanical-validation failure that
  taught us setups are contexts, not triggers. Kept for the paper trail.
- `TREND_4R_v1/` — the 4H/4R thesis strategy. Still not validated.
- Older experiments (`PULLBACK_*`, `MOM_BREAK_v1`, …) — see `strategies/README.md`.

---

## Running it

```bash
./start.sh     # starts the server, prints the dashboard link
./stop.sh      # stops it
```

First-time setup:

```bash
pip install -r requirements.txt
cp prism.env .env       # exchange keys etc.
```

**Enable the loop (two one-time steps):**

```bash
# 1. schedule the hourly scanner (minute 2, right after the 1H bar closes)
(crontab -l 2>/dev/null; echo '2 * * * * cd /home/mini/lens && /home/mini/prism/.venv/bin/python3 -m app.setups >> setup_scan.log 2>&1') | crontab -

# 2. phone alerts: install the ntfy app, subscribe to a topic you invent,
#    then add it to prism.env:
echo 'LENS_NTFY_TOPIC=your-secret-topic-name' >> prism.env

# 3. (for the TAKE/SKIP buttons) tell the push where the LENS server lives,
#    as seen FROM THE PHONE. LAN address for home wifi; a public tunnel URL
#    if you want the buttons to work on mobile data.
echo 'LENS_BASE_URL=http://192.168.1.47:8765' >> prism.env

# 4. (optional, closes the loop) auto-pull Kraken fills every hour so trades
#    self-tag without you opening the dashboard:
(crontab -l 2>/dev/null; echo '5 * * * * curl -s -X POST http://localhost:8765/api/sync/kraken >/dev/null') | crontab -
```

Health check: `curl localhost:8765/health` · API docs: http://localhost:8765/docs

Useful API: `POST /api/setups/scan` (scan now) ·
`GET /api/setups/state` (desk JSON) · `GET /api/stats/setups` (scoreboard) ·
`POST /api/setups/backfill-tags` (re-tag trades).

---

## Status / honesty

- ✅ v3 edge mapped and live: setup engine, /desk, phone alerts with one-tap
  TAKE/SKIP buttons, auto-tagging, scoreboard. All 464 historical trades tagged.
- ✅ Exchange sync, signal ingestion, discipline filters, projection/goal math.
- ✅ Loop is live: hourly scanner cron installed and firing (first real S1 short
  emitted + pushed 2026-06-16). Decisions post back from the phone buttons.
- ⚠️ Kraken fill sync is **manual** (or the optional hourly sync cron above) —
  the scanner cron does not pull fills itself.
- ⚠️ Phone buttons reach the server over LAN only unless `LENS_BASE_URL` points
  at a public tunnel.
- ⏳ v4 needs ~3 months of tagged trades; candidate new features: order-flow
  data (CVD, delta, funding, OI).
- 🧪 `TREND_4R_v1` (4H/4R thesis) — still not backtested; separate track.
- ⚠️ Setup WRs are realized-history numbers, not promises. Mechanical
  occurrence of any setup is ~coin-flip — the edge is selection inside the
  context. Funding cost on multi-day holds is not modelled.

Current progress snapshot: **`STATUS.md`** (read first). Full playbook:
`strategies/LENS_EDGE_v3_ICT/FINDINGS.md`. Build plan history: `LENS_PLAN.md`,
`PRISM-SYSTEM-SPEC (1).md`.

## Working across machines

Active line is **`master`** (the old `lens-4r-projection` branch was merged).

```bash
git pull                              # pick up where you left off
git add -A && git commit -m "..." && git push
```
