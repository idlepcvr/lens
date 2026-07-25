# NEXT SESSION — LENS

*Written 2026-07-25. Supersedes the 2026-07-24 spec (short gap + discipline
holes), archived at `docs/NEXT_SESSION_20260724.md`. Full suite green
(24 test files).*

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

## Open decisions — asked, not yet answered

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
