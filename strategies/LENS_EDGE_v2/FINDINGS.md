# LENS_EDGE_v2 — The Flush Short (mined from 464 real trades)

> ## ⚠️ Mechanical validation: FAILED — read this first
>
> The flush-short pattern was backtested mechanically over 30 months of 1h
> data (every occurrence, not just the ones you traded):
>
> - **1,413 signal occurrences**; you took ~35 of them (1 in 40)
> - Mean forward move after signal: **≈ 0%** (drifts slightly *up* — wrong
>   way for a short). First-touch ±0.5% race: shorts win **46%** (42% in NY)
>   — sub-coin-flip before fees
> - Full backtest at 1% SL / 3.5% TP: **22.4% WR vs 28.9% breakeven →
>   account to zero**. NY-only: same outcome.
>
> **Conclusion: the pattern itself has no edge. Your 60% WR came from
> discretionary selection of *which* flushes to short, plus early exits
> (your wins averaged +0.48%, not 3.5%).** Everything below describes when
> *your* trading wins — it is a personal checklist, NOT an auto-strategy.
> Do not trade the Pine signals mechanically.

## Source Data
- **464 closed trades** from Kraken futures, Apr 2025 – Jun 2026
- Base: 41.8% WR, €+736, exp €+1.59/trade
- Mined with `research/edge_miner.py`: 10 entry-context features, all 1–3 condition
  combos (n≥20), then **robustness-filtered** — every candidate had to survive
  (a) dropping its 2 biggest wins, (b) old-half vs new-half WR split, and
  (c) size-independent avg price move > 0.

## Why v2 exists

v1's € expectancy tables were contaminated: position size grew over time, so a
few late outlier wins made bad rules look good. Examples that **died** under
robustness checks:

| Candidate | Raw PnL | After dropping 2 best wins | Verdict |
|---|---|---|---|
| Tuesday shorts | €+1,378 | **€−139** (avg move −0.05%) | outlier artifact |
| Asia slope+streak | €+1,429 | **€−74** | outlier artifact |

## The one setup that survived everything: FLUSH SHORT

**RSI(14) < 40 + 3 consecutive bear bars + enter short on that 3rd bear bar.**

| Variant | n | WR | Avg price move | Old/new half WR |
|---|---|---|---|---|
| All sessions | 35 | **60.0%** | +0.48% | 69% / 53% |
| NY session (13–21 UTC) | 16 | **81.2%** | +0.92% | holds both halves |

Notes:
- Every one of the 35 trades was a short. This is **not** a dip-buy — it is
  shorting *into* an oversold flush while it's still falling. Momentum
  continuation, not mean reversion.
- The 1h EMA21 slope is always "with" the trade here (3 bear bars force the
  slope down) — no extra filter needed.
- 4H trend alignment does **not** improve it (58.3% aligned vs 60% all):
  the flush works with or against the 4H trend.
- The "extended past 4H EMA21" variant (EXT_RUN, 55.9% WR n=34) is 68% the
  same trades — not a separate setup.
- Long mirror (RSI>60 + 3 bull bars) has **zero occurrences** in your real
  trades. Untested. The Pine ships it as an off-by-default toggle only.

## Confirmed AVOID rules (robust and getting worse)

| Rule | n | WR | PnL | Old→new half |
|---|---|---|---|---|
| RSI 40–55 (neutral zone) | 176 | 34.7% | **€−1,243** | 39% → 30% |
| 1h EMA21 slope against trade | 202 | 38.1% | **€−1,177** | 42% → 34% |

These two filters alone remove most of the bleed. Both are *worsening* in the
recent half — the market is punishing these entries harder now.

## Secondary (weaker, keep an eye, don't size up)

- **Momentum in London** (RSI>55, 08–13 UTC): 64.7% WR n=34, but avg move only
  +0.33% and PnL dies when 2 best wins are removed. WR is real (56%→75% across
  halves) but wins are small — only worth it if held to full TP.
- v1's MOMENTUM setup (RSI>55 + 4H + aligned bar, 52.9%) still stands.

## Risk params — REVISED after mechanical validation
- The mechanical test at 1% SL / 3.5% TP went to zero. Holding flush shorts
  ~70h for a 3.5% target is **not** what you actually did when you won.
- Your winning behavior was: enter the flush, take +0.5–0.9% quickly. The
  early exits v1 called "cutting winners" were, on this setup, the edge.
- Open question for live review: what *did* you see in the 35 flushes you
  took that the other 1,378 occurrences lacked? That discriminator isn't in
  these 10 features — log it in trade notes going forward.

## What to do differently vs v1
1. The flush short describes when *your discretionary shorting* wins — it was
   invisible in v1 because "dip" reads as buy-the-dip. But it is context, not
   a trigger: mechanically the pattern is a coin flip.
2. Best window: NY session 13–21 UTC (81% WR on your trades there).
3. RSI 40–55: still dead. Slope against you: still dead. No exceptions —
   these are entry *vetoes* and they hold regardless of the setup debate.
4. On flush shorts, do NOT force the 3.5% TP — your realized edge lived in
   +0.5–0.9% exits. The 3.5% TP math belongs to the 4H trend thesis, not
   this scalp-like setup.
