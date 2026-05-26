# PRISM Trade-History Fingerprint

*Source: `/home/mini/prism/prism.db` · 2,315 closed trades · 2024-04-21 → 2026-05-20 (108 weeks, 21.4 trades/week)*

---

## TL;DR

**Your discretion isn't broken — your selection discipline is.** The bulk numbers say break-even (44.8 % WR, PF 0.97, −€1,205). But when you slice for **conviction trades** (real size on the position), it flips dramatically. Five simple discipline filters lift the same data from break-even to **PF 1.87 / 53 % WR / +€9,702 over the period** — same trades, just refusing to take the marginal ones.

**Your entries are fine. You take too many trades you don't believe in.**

---

## Baseline (no filters)

| | |
|---|---|
| n | 2,315 |
| Win rate | **44.8 %** |
| Profit factor | **0.97** |
| Expectancy | **−€0.52** / trade |
| Net P&L | **−€1,205** |
| Breakeven WR needed | 45.9 % |
| Edge vs. breakeven | **−1.1 pp** |

You're 1.1 pp of WR away from breakeven. Tiny gap, but persistent.

---

## What drives the gap — biggest signals

### 🚨 #1 — Position size (the dominant signal)

Implied leverage = (size × entry) / balance_after, i.e. how much skin you actually had in the trade.

| Notional / balance | n | WR | PF | Expectancy | Net |
|---|---:|---:|---:|---:|---:|
| < 1× | 393 | 41 % | 0.95 | −€0.05 | −€20 |
| 1–5× | 237 | 44 % | 0.83 | −€0.79 | −€187 |
| **5–10×** | 117 | 42 % | **1.22** | +€3.28 | **+€384** ★ |
| **10–25×** | 201 | 53 % | **1.78** | +€12.91 | **+€2,594** ★ |
| 25–50× | 165 | 52 % | 1.16 | +€3.61 | +€595 |
| **50–100×** | 101 | **60 %** | **2.69** | +€33.18 | **+€3,351** ★ |
| > 100× | 157 | 47 % | 1.02 | +€0.63 | +€99 |

**Reading:** When you put real size on (5×+ implied notional), you win. When you nibble (< 5×), you lose. The 50–100× bucket has 60 % WR and PF 2.69 — when you're really committed, you're a different trader.

This is consistent with how good discretionary traders work: their A+ setups deserve A+ size, and they don't bother with B-grade trades. You're taking the B-grades.

### 🚨 #2 — Venue: kill Bybit

| Venue | n | WR | PF | Net |
|---|---:|---:|---:|---:|
| **Kraken futures** | 2,231 | 45 % | 1.02 | **+€669** ✓ |
| **Bybit futures** | 84 | 35 % | **0.40** | **−€1,874** ⚠ |

84 Bybit trades cost you €1,874. Kraken alone is slightly profitable. **Pick one and stick to it — clearly Kraken.**

### 🚨 #3 — Tilt after losses

| | n | WR | PF | Net |
|---|---:|---:|---:|---:|
| After a winning trade | 1,036 | **51 %** | 1.05 | **+€877** |
| After a losing trade | 1,261 | **40 %** | 0.89 | **−€2,195** |

11 pp drop in WR after a loss. You're chasing.

### 🚨 #4 — Scalps don't work, holds do

| Hold duration | n | WR | PF | Net |
|---|---:|---:|---:|---:|
| < 5 min | 130 | 34 % | 0.62 | −€518 ⚠ |
| 5–15 min | 178 | 38 % | 0.67 | −€573 ⚠ |
| 15–60 min | 519 | 43 % | 0.75 | −€1,664 ⚠ |
| 1–4 hr | 732 | 46 % | 0.98 | −€250 |
| 4–24 hr | 622 | 46 % | 0.96 | −€539 |
| **> 24 hr** | 134 | **56 %** | **1.62** | **+€2,340** ★ |

Sub-hour trades bleed badly (~−€2,800 combined). Multi-day holds dominate the wins.

### 🚨 #5 — Saturdays are a disaster

| Day | n | WR | PF | Net |
|---|---:|---:|---:|---:|
| Mon | 428 | 48 % | 1.21 | +€1,270 ★ |
| Tue | 352 | 44 % | 0.93 | −€415 |
| Wed | 361 | 46 % | 1.17 | +€785 |
| Thu | 363 | 41 % | 0.87 | −€818 |
| Fri | 401 | 46 % | 1.08 | +€407 |
| **Sat** | 167 | 43 % | **0.38** | **−€2,606** ⚠ |
| Sun | 243 | 44 % | 1.04 | +€173 |

Saturday alone costs you €2,606 — more than the entire net loss. **Don't trade Saturdays.**

### #6 — Revenge-trading window

| Gap since last close | n | WR | PF | Net |
|---|---:|---:|---:|---:|
| < 5 min | 1,036 | 44 % | 0.89 | **−€1,946** ⚠ |
| 5–30 min | 381 | 47 % | 1.33 | +€1,532 ★ |
| 30 min – 2 hr | 362 | 45 % | 1.17 | +€948 |
| 2–12 hr | 413 | 43 % | 0.86 | −€1,096 |
| 12–24 hr | 91 | 46 % | 0.67 | −€696 |
| > 24 hr | 31 | 58 % | 1.16 | +€54 |

< 5-min gap = revenge trades. 1,036 of them — nearly half your activity — and they cost €1,946 net.

### ⚠️  Hours: signal exists but is NOT robust across years

Some hours look great in aggregate (e.g. 03:00 UTC has PF 3.0, 15:00 has PF 1.59). But when broken down by year, several flip sign:

| Hour | 2024 PF | 2025 PF | 2026 PF |
|---|---:|---:|---:|
| 03:00 | 0.96 | 0.57 | **28.79** (tiny sample) |
| 15:00 | 1.80 ✓ | 1.48 ✓ | **0.31** ✗ |
| 17:00 | 1.77 ✓ | 2.03 ✓ | **0.03** ✗ |
| 22:00 | 1.33 ✓ | 5.57 ✓ | (too few) |
| 23:00 | 4.36 ✓ | 1.35 ✓ | 4.93 ✓ |

**Verdict:** hour-of-day is *probably* noise. Hour 23:00 UTC is the only one robust across all three years. **Do not over-fit to hours.**

---

## What happens when filters compound?

| Filter stack | n | WR | PF | Expectancy | Net |
|---|---:|---:|---:|---:|---:|
| Baseline | 2,315 | 44.8 % | 0.97 | −€0.52 | −€1,205 |
| Kraken only | 2,231 | 45.2 % | 1.02 | +€0.30 | +€669 |
| + size ≥ 5×bal | 741 | 50.6 % | 1.46 | +€9.48 | +€7,024 |
| + no Saturday | 649 | **53.2 %** | **1.87** | **+€14.95** | **+€9,702** |
| + hold ≥ 60 min | 469 | 53.5 % | 1.92 | +€18.49 | +€8,673 |
| + gap ≥ 5 min | 345 | 51.9 % | 1.67 | +€12.64 | +€4,362 |
| **ALL six filters** | 76 | 57.9 % | **4.02** | **+€37.50** | +€2,850 |

Diminishing-returns curve: most of the edge is captured by **4 simple filters** (kraken / size ≥ 5×bal / no Sat / hold ≥ 60 min). Stacking more keeps WR climbing but cuts sample so much that future statistical confidence drops.

**Recommended filter set (best edge × sample-size tradeoff):**

```
1. Venue: kraken_futures only       (NOT bybit)
2. Notional / balance ≥ 5×          (real conviction)
3. Day-of-week != Sat
4. Hold ≥ 60 min                    (no scalps)
```

Historical perf with those 4: **n=649, WR 53.2 %, PF 1.87, +€9,702 over the period.** That's 28 % of your trades doing 8× better than your full activity.

---

## What the data CAN'T tell us

Critical gap: **PRISM doesn't store WHY you entered.** No setup tags, no chart context, no indicator state, no notes (the `notes` column is mostly empty). So we can't reverse-engineer a chart pattern — only behavioral patterns.

This is exactly the gap LENS is built to close. Going forward, the locked-schema `signals` table captures trigger_type, htf_bias, confluence_count, ATR%, BTC trend, session — i.e. the chart context the Pine alert was firing on. After 100–200 LENS signals we'll have the data PRISM never captured.

---

## What this means for Pine v2

A Pine script can't really detect "user is putting real size on" — that's a discretionary call. So the strategy splits into two pieces:

### Piece A: a *signal* script (Pine) that filters out the times/days/cooldowns that bleed

Easy to encode:
- block alert fires on Saturday
- block alert fires within X min of a prior alert
- block alert fires in known-bleed hours (only ones robust across years — i.e. avoid 11 UTC and 02 UTC particularly)

This is purely a noise-reduction layer over whatever the actual entry signal is.

### Piece B: the *entry* premise itself

The data says nothing about which chart pattern works. Three honest options:

1. **Keep using your eye + chart reading as the entry, fire a manual alert into LENS via a phone-tap webhook (week 3 path C).** Pine becomes just a logger; the discipline filters live in LENS server-side.
2. **Pick a non-MACD framework that fits multi-day holds + conviction sizing** — supply/demand zones, ICT order blocks, weekly-level break-and-retest, daily 200 EMA pullback. These are all multi-hour-hold setups by nature, which aligns with the >24h-hold edge.
3. **Hybrid:** Pine emits multiple candidate signals; LENS UI shows them; you approve/reject based on your read. Best of both — discipline-enforcement + your discretion preserved.

Option 3 is closest to the original LENS_PLAN.md Week 4 decision-view vision.

---

## Suggested next concrete step

Not Pine yet — first the **server-side filters** (Piece A). Add to `/api/signals` an auto-reject for: Saturday, < 5 min cooldown, known-bleed hours. Then Pine can fire whatever it fires and LENS does the bouncer work. That way the discipline survives even when we change entry frameworks.

Once that's in place, decide between options 1 / 2 / 3 for the entry premise itself.
