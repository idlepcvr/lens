# NEXT SESSION — LENS

[Open as HTML](DONE-2026-07-31-front-door-rebuild-system-deletion-setup-disarm.html)

> **CLOSED SESSION — 2026-07-31.** Everything in this file is done, moot, or
> deliberately moved out of the repo. It was `NEXT_SESSION.md` at the root until
> its last item was built on 2026-07-31; it is archived here so that no file in
> this repository claims to be pending work when none is.
>
> **There is deliberately no `NEXT_SESSION.md` right now.** That is the honest
> state, not an oversight — see `## ▶ NOTHING IS PENDING IN THIS REPO` below.
> The next session that genuinely has scope should create a fresh one.
>
> Still worth reading here: the out-of-sample disarm of S2–S5, the short-side
> "no edge" finding, his recorded position on splitting the prop and hedge
> engines (raise only when he opens the topic), and the 2026-07-25 log.


*Revised 2026-07-31 — one priority only. Supersedes the 2026-07-25 spec, whose
public-exposure alarm was wrong (see below). Prior spec archived at
`docs/done/DONE-2026-07-24-short-gap-discipline-holes.md`.*

---

## ✅ DONE 2026-07-31 — negative-expectancy setups disarmed

Was the top item here. Built and deployed the same day, so it is no longer
pending. `app/setups.py` now carries `ARMED_SETUPS = frozenset({"S1"})`.

**Why.** S1–S5 were mined from 464 of his own trades and showed 57–91% win
rates *in that sample*. Scored out-of-sample over 63,270 candles, 2019-05 →
2026-07 (`results/strategy_scores.json`, 2026-07-26):

| setup | in-sample claim | out-of-sample net R | n | |
|---|---|---|---|---|
| S1 | 90.9% (n=11) | **+0.042** | 431 | armed — the only non-negative one |
| S2 | 65% (n=23) | −0.256 | 1,649 | disarmed |
| S3 | 56.7% (n=30) | −0.146 | 9,340 | disarmed |
| S4 | 62% (n=29) | −0.296 | 4,060 | disarmed |
| S5 | 60% (n=5) | −0.086 | 2,714 | disarmed |

The setups were fit to the data that produced them and the edge did not
survive. This is the mechanism behind the hedge book: 496 fills, 39.5% WR,
−€4,347. Measured effect of the change, over a 5,800-bar window: **1,588 live
signals → 30.**

**What was gated, and what deliberately was not.**

  · `scan_latest()` — the signals pipeline. Gated.
  · `desk_state()` — the ENTER / STAND DOWN verdict. Gated.
  · The desk labels no longer advertise the in-sample win rates. Each setup now
    reads `ARMED · +0.04R out-of-sample (n=431)` or `DISARMED · −0.26R …`.
  · `classify()` / `backfill_setup_tags()` — **NOT gated, on purpose.** They tag
    trades that already happened. Filtering them would silently rewrite every
    historical S2–S5 tag to NONE and destroy the realized-vs-mined scoreboard —
    which is the only evidence that could ever justify re-arming a setup.

`tests/test_armed_setups.py` locks both halves: the live surfaces must be gated,
the tagger must not be.

**To re-arm anything**, edit the one frozenset — but only against a fresh
`strategy_scores.json`, not against a realized run of 20 trades. The 57–91%
numbers came from exactly that mistake.

## ▶ NOTHING IS PENDING IN THIS REPO

That is the honest state as of 2026-07-31, and it is deliberate — the two things
that matter next are not LENS work:

1. **Months-of-burn.** One number, one hour. Kiki, not here (see below).
2. **Ten paper trades on `ASIAN_RSI_DIP_v1` as written** — 2x, killzone bars
   only. His desk work, not a Claude session. It is #1 of 27 by net R
   (+0.653R/trade); the busted eval ran it at 5x, 8 trades in 11 days, with
   1 of 8 following the plan.

⚠️ **Do not open this repo looking for something to build.** The pattern
`focus-doctrine-2026-07.md` names — converting "take a position" into "build an
instrument" — runs through a session that starts by hunting for work here.

## ⤴ MOVED OUT: months-of-burn is not a LENS task

Previously listed here as the top priority. It does not belong in this repo and
cannot be computed from `lens.db`. `/money` tracks **Kraken transfers** —
€51,783 deposited, −€11,334 withdrawn — i.e. cash in and out of the exchange.
There is no expenses table, no rent, no food, no visa, no spending of any kind.

It is a personal-finance item and belongs in Kiki. Still outstanding since
2026-07-06, still worth an hour, still not this repo's job.

## ✅ RESOLVED: the public-exposure alarm above was wrong

The previous version of this file opened with a 🔴 "lens.restedpc.com is public
and unauthenticated, measured not theoretical". **It is not.** Public DNS
resolves `lens.restedpc.com` to `fox.tail390a75.ts.net` → `100.103.43.66`, which
is CGNAT and unroutable off-tailnet. The original `curl` was run from inside the
tailnet, so it only ever proved the service was up. Corrected 2026-07-31.

Still worth doing cheaply when convenient — `FastAPI(docs_url=None,
redoc_url=None, openapi_url=None)` stops advertising the surface — but it is
housekeeping, not an emergency, and it is **not** this session's job.

## 📌 Findings from 2026-07-31 — already answered, do not re-derive

- **The eval busted, it did not stall.** 8 trades, 9–20 Jul, −$301.59 = −6.03%
  against `BREAKOUT_1STEP_CLASSIC`'s 6.0% static wall. Account closed.
- **It was never a strategy failure — the strategy was never run.** Trade 1 has
  `followed_plan=1, followed_strategy=1` and is the only winner (+$49.79). The
  other seven are `None`/`0` and all lost. Trade 3's own note: *"No signal."*
  Six of eight ran **5x** leverage against a plan that specifies **2x**, and he
  took **8 trades in 11 days** against a model of **~1.5/month**.
- **The "which eval can I afford" question is closed.** `BREAKOUT_5K_PLAN.md`
  (15 Jun): *"rules are %-based, so odds are identical at any account size. Pass
  the cheap $5k first, then buy the biggest eval direct (don't ladder)."* Evals
  are ~$20. No hedge-book grinding is needed to afford one.
- **His action, not a Claude session:** run `ASIAN_RSI_DIP_v1` as written — 2x,
  killzone bars only — on paper for 10 trades. Kraken CLI has a free
  paper-trading mode against live prices with no API keys. If he can follow it
  for ten, buy the $20 eval. If not, the eval was never the problem.
- ⚠️ **Do not wire order placement into LENS.** The front door's "LENS holds no
  keys, it cannot place an order" is now a drawn diagram on `/`. Giving Kraken
  CLI trade-permissioned keys makes that page false.

## 🗑️ Deleted 2026-07-31

`/system` and `app/home_page.py` are gone — the instrument plate was a craft
showcase with no audience. `/` is now five diagrams; its only exit is `/dashboard`.
The dot-matrix renderer lives in git at `43468ca` if it ever wants a home.

## His stated position on the architecture (2026-07-25) — recorded, not actioned

Venting captured verbatim in intent so it stops occupying his head. **He
explicitly said he is NOT asking for this to be fixed now.** Do not start it;
raise it when he opens the topic.

> "I almost feel like I should have two separate engines… almost have them just
> be two separate websites. One for prop and one for hedge. While they might use
> the same tool, same library, same things, it just feels so different."

Worth taking seriously rather than filing as a mood: the prop book is an
evaluation with hard drawdown walls and a pass/fail end state, the hedge book is
his own money with a 150 BTC end state. They share code but almost no decisions,
and the mode switcher exists precisely because one interface kept having to be
two. `test_nav_parity` currently *enforces* that the two modes mirror each other
— if the split happens, that test is the first thing to reconsider.

**His page-by-page complaints, all verified as real:**

| page | what it actually is | verdict |
|---|---|---|
| `/audit` | plain-English view of the **2026-07-02** audit vs current config | dated document, nothing actionable |
| `/audit-report` | serves the static `strategies/_research/STRATEGY_AUDIT_20260702.html` | merge with `/audit` or archive |
| `/docs/oauth2-redirect` | **not a page** — FastAPI Swagger helper | disappears when docs are disabled |
| `/money` | only sees the `transfers` table (kraken_spot EUR + biz futures) | reports a PARTIAL number as a TOTAL — he wants to supply the real figure and have it stored |
| `/prop-cone` | Monte-Carlo cone for the eval: pass odds, milestone ladder, basket | genuinely prop-only; but `/goal` + `/prop-goal` + `/prop-cone` is three goal pages |
| `/robustness` | permutation test, 4,000 shuffles: how often does chance beat the rule | honest, but **40 live trades cannot answer it** — label it, don't delete |
| `/risk` `/rules` `/survival` | prop engine cards, deliberately no nav entry | fine as-is |
| `/strategy` `/strategy-hedge` `/prop-goal-old` | **301 redirects**, legacy URLs kept so bookmarks survive | not pages at all |

**The reframe that matters:** five of the nine are not destinations — three are
redirect stubs, two are framework endpoints. **The sitemap advertises routes,
not pages.** Teaching it to skip redirects and framework routes removes most of
the complaint without deleting anything. Do that before proposing deletions.

**⚠ He wants to redo the hedge nav himself.** Today's commit already reorders it
(Desk · Signals first, footer split MORE/SYSTEM) — tell him it is already in
PR #1 so he does not redo work, then leave the nav to him.

---

## The headline: the short side has no edge

The previous spec called the short gap a **coverage bug** — LENS is structurally
long-only outside 13:00–16:00 UTC, so it "cannot speak". Correct but incomplete.
Given a vocabulary for chart structure and higher timeframes, the breeder still
cannot find a short worth taking:

| window | viable | beat baseline | tradeable | tradeable SHORTS |
|---|---|---|---|---|
| deep (7y Binance spot) | 74 | 43 | 39 | **0** |
| w30 (30mo Bybit perp) | 60 | 41 | 23 | **0** |

**32 viable shorts bred across both windows. Not one is tradeable** (beats an
every-bar baseline at its own geometry AND ends the window up). Treat "add a
short setup" as answered: the mechanism was missing, and so is the edge.

Next place to look: **his own executed shorts** — six since the loop went live.
If those made money, the edge is in something he sees that is not in this
feature set, and mining is the wrong tool for finding it.

---

## ✅ Open decisions — ALL THREE CLOSED 2026-07-31

  1. **The front door** — answered. `/` was rebuilt as five diagrams
     (`explain_page.py`); `/system` and `app/home_page.py` were deleted outright
     rather than moved, so "which page did he mean" is moot. No `/about`, no
     cockpit: he asked for one visual front door and one exit to the desk.
  2. **Cockpit content** — moot, nothing was built. The two rules survive in
     `explain_page.py`: no P&L or balance on the front door, and if a verdict
     ever appears there it reuses `desk_state(refresh=False)` rather than
     re-deriving one that could disagree with `/desk`.
  3. **Kill S4 and S2?** — **answered: yes, plus S3 and S5.** "Raised twice, not
     decided" is now decided on out-of-sample evidence rather than on how often
     the vetoes were catching them. See the disarm section at the top.

The original text of all three, as written 2026-07-25:

## Open decisions — as asked on 2026-07-25 (kept for the reasoning)

**1. The front door.** `/` is `explain_page.py`: a plain-English explainer, no
numbers, no jargon, written to his own brief for a non-trading reader (a
partner, a parent). He called it "too much fluff" — but he is not its reader, he
just lands on it daily.

  · Recommendation: move the explainer to `/about` intact, put a cockpit on `/`.
  · **Ask which page he meant** before editing: `/` (explainer) or `/system`
    (`home_page.py` — the instrument plate, which genuinely IS a pitch page:
    wordmark, animated thesis, marketing prose, dot-matrix curve).
  · ⚠ On 2026-07-25 I gutted `/system` believing it was the homepage, then
    reverted it. Confirm the target first.

**2. Cockpit content**, if built. Proposed, unanswered: verdict per direction,
open position, signals awaiting decision, link coverage. The reverted sketch's
one keepable idea: reuse `desk_state(refresh=False)` rather than re-deriving a
verdict, so the front door can never disagree with `/desk`. **No P&L or balance
on the front door** — `_gauges()` set that rule deliberately, so the page stays
safe to turn a screen toward.

**3. Kill S4 and S2?** Both read as active and structurally cannot fire (S4
matched 25 times in 30 days, vetoed 25; S2 vetoed 5 of 5). S4 is the direct
cause of his "LENS told me to go long into a collapse" complaint: it proposed a
long every hour for nine hours while price fell, and the vetoes killed every
one. The vetoes worked — the desk showed him the blocked cards. Raised twice,
not decided.

---

## Done 2026-07-25

- **Veto labels read live.** `VETO_LABELS` baked in frozen stats; `fvg_entry`
  rendered "−€15/trade" on `/desk` while the ledger said otherwise. Labels are
  description-only now; stats come from `veto_bucket_stats()`.
- **Era scoping.** `veto_bucket_stats(era="live")` is the default;
  `SYSTEM_START = 2026-06-16`. 469 of 509 trades predate the system, and pooling
  them produced the false "fvg_entry is the only veto in profit, +€2,011"
  finding — live-era it is −€79 over 10. **Do not delete the pre-system trades**
  (he asked about this): they are the sample the vetoes were mined from, and
  this scoping is the alternative that keeps them.
- **Pattern + HTF vocabulary** (`app/patterns.py`): double top/bottom, structure,
  breakout, 4h/1d trend, merged into `SLOTS` so grid search, breeder and board
  all gain them. Grid search 2,934 → 9,694 combos. Causality proven by
  truncation in `tests/test_patterns.py`.
- **Lookahead bug fixed** in `add_indicators`: `h4_*` was resampled and ffilled
  with no shift, so 3 of every 4 1h bars knew their own 4h close. Only
  `research/scalp_sweep.py` consumed it — that script's past results were
  inflated.
- **Breeder baseline** (`beats_baseline`, then `tradeable`). It had none, so a
  7-year run returning 65 longs of 78 read as a finding. 0 of 74 beat
  buy-and-hold. `tradeable` exists because five w30 SHORTS beat a
  direction-matched baseline while losing 24–48%.
- **Linker fixed.** It required the decision to PRECEDE the fill; across the live
  era 24 of 27 unlinked fills have the decision AFTER — he trades, then approves.
  Symmetric ±6h window, ordered by absolute gap. Links 5 → 8 of 40. Deliberately
  not widened further: the gaps jump to 20h/60h/300h+, and a false link corrupts
  the dataset the system exists to build.
- **Nav** leads with Desk and Signals in both modes, ordered by the daily loop;
  footer split into MORE (book pages) and SYSTEM (utilities).

---

## Standing context

- Auto-execution is never in scope.
- **The goal is 150 BTC valued at current spot. He has confirmed the config is
  fine and does NOT want a fixed €37.5M target — do not re-litigate it.**
  `LENS_PLAN.md` line 18 still says "50 BTC" and line 395 "150 BTC @ €250k";
  the config is what grades feasibility. Reconcile those two lines, nothing more.
- **Buy-and-hold is not the benchmark.** The goal is a BTC count and he is
  accumulating, not trying to beat holding over four years. Use `tradeable`
  (beats baseline + ends up) as the gate instead.
- The live era is **40 trades, 8 linked, 1–17 trades per veto rule**. Almost
  nothing is statistically significant. The highest-value work is whatever
  raises the linked-trade count, because an unlinked trade cannot answer "does
  following LENS beat ignoring it" — the only question that matters.
- The 7-year window is Binance **spot**; the 30-month is Bybit **perp**. Never
  compare them bar-for-bar.
