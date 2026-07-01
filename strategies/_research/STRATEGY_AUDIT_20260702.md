# Strategy Audit — 2026-07-02

Full-history audit (62,671 × 1h candles, 2019-05 → 2026-07, fee-honest at 0.30%
round-trip) + the 481 real Kraken trades. Three engines: the weekly R-sweep
(`strategy_eval`), a new SL×TP geometry miner (`mine_20260702.py`, first-touch
on forward-excursion matrices, stop-checked-first), and MAE/MFE analysis of the
real fills. Every number below survived an old-half/new-half split unless
flagged.

## TL;DR — what to actually do

1. **Your stop is right, your target is too tight.** Real-fill MAE says the
   0.63% stop keeps ~85% of playbook winners. Real-fill MFE says half your
   playbook winners ran to **+1.5%** and a quarter past **+2.0%** — the 0.95%
   target captures barely half the available move. The mechanical grid agrees:
   every surviving setup optimizes at TP ≥ 2%.
2. **S1 is the only labeled setup with a mechanical edge** (+0.21%/trade at
   2%/2%, 62.7% WR, both halves positive, n=410). S2–S5 are mechanically dead
   at *every* geometry — their realized profit is your selection, full stop.
3. **Best unmined candidate: `atr_low & eq & slope_up` → LONG, SL 2% / TP 6%**
   (+0.94%/trade, halves +2.27/+0.60, n=825). Theme: quiet-regime equilibrium
   in an uptrend, let it run. The whole `atr_low` family points the same way —
   the edge lives in LOW-volatility regimes with wide targets, the exact
   opposite of the sub-2h scalping that bled −€747.
4. **None of this overrides the discipline finding**: VETO bucket = 314 real
   trades, −€2,254, 36% WR in BOTH halves. No mined setup beats the expectancy
   of simply not taking those.

## Honesty box (read before trusting anything)

- **Baseline check passed**: enter-long-on-every-bar LOSES at every tested
  geometry (−0.29 to −0.47%/trade). The mined edges are context selection, not
  BTC drift.
- **Multiple comparisons**: ~600 pairs + 151 triples × 42 geometries were
  tested. The split-half guard filters most flukes but not all; treat mined
  combos as *candidates to forward-test*, not proven edges.
- **Funding not modeled**: a 6% target at 1h holds multi-day; perp funding can
  eat ~0.01–0.03%/8h. Real expectancy on wide-target setups is somewhat lower.
- **First-touch on 1h bars is conservative** (stop checked first inside a bar)
  but can't see intra-bar sequencing.
- Resolution window 96 bars (~4 days); unresolved occurrences excluded
  (resolution ≥ 70% enforced).

## Part 1 — verdicts on the labeled setups

Mechanical = best geometry found on full history; Realized = your actual fills.

| Setup | Mechanical verdict | Realized (n, WR, €) |
|---|---|---|
| S1 NY-AM flush short | ✅ **+0.21%** @ 2/2, 62.7% WR — real | 11, 90.9%, +116 |
| S2 premium disp short | ❌ negative at every geometry | 7*, 57%, +17 |
| S3 continuation long | ❌ negative at every geometry | 35, 45.7%, **+614** |
| S4 discount dip long | ❌ negative at every geometry | 7*, 71%, +18 |
| S5 London momentum long | ❌ negative at every geometry | 5, 60%, +337 |
| H6 bear3+eq short | ❌ | — |
| H7 rsi>70 no-sweep long | ✅ +0.25% @ 2/4, both halves | — |
| H8 bear-disp+rsi<30 short | ⚠️ +0.04% — marginal | — |
| H9 London sellsweep short | ❌ | — |
| H11 hi-vol rsi55-70 short | ❌ | — |

\* mostly vetoed variants. **Interpretation**: S3/S5 earn real money for you
despite no mechanical edge → the entry *timing inside the context* (your
discretion) is the edge. That's why LENS alerts instead of auto-entering, and
why the off-playbook push matters — the same discretion without the context is
the −€2,254 bucket.

## Part 2 — geometry (the SL/TP question)

From your real fills (n=392 with excursion data):

| Metric | Playbook trades |
|---|---|
| Winners' MAE p65 / p80 / p90 | 0.41% / 0.54% / 0.67% |
| Winners' MFE p50 / p75 / p90 | **1.49% / 2.01% / 2.72%** |
| Losers' MFE p50 / p75 | 0.20% / 0.56% |

- **Stop 0.63%**: keeps ~85% of winners. Fine. Widening to 0.7% buys ~5 points
  of winner retention; not the lever.
- **Target 0.95% → 1.5%**: half of current winners already reach it. At the
  realized ~46–58% context WR, 0.63/1.5 ≈ 2.4R vs today's 1.5R — this is the
  single biggest expectancy lever inside the current playbook.
- **Break-even rule**: only 25% of losers ever go +0.56% in your favor → moving
  the stop to entry after +0.6% scratches ~¼ of losers while touching few
  winners (their p50 path runs much higher). Cheap risk reduction.

## Part 3 — mined candidates (forward-test before trusting)

Top survivors (both halves positive, n ≥ 100, beats baseline by ≥ 0.4 pts):

| Candidate | Dir | SL/TP | n | WR | exp% | halves |
|---|---|---|---|---|---|---|
| **atr_low & eq & slope_up** | long | 2/6 | 825 | 40.5% | **+0.94** | +2.27 / +0.60 |
| atr_low & eq & raid_pdh | long | 2/6 | 340 | 42.4% | +1.09 | +3.00 / +0.56 |
| rsi>70 & atr_low | long | 1.5/6 | 747 | 30.9% | +0.52 | +0.76 / +0.45 |
| rsi>70 & disp_bear (dip-buy in momentum) | long | 2/4 | 111 | 49.5% | +0.67 | +0.52 / +0.80 |
| rsi<30 & eq | short | 2/3 | 148 | 56.1% | +0.50 | +0.58 / +0.42 |
| rsi>70 & slope_up (huge n) | long | 2/4 | 3551 | 41.2% | +0.17 | +0.17 / +0.18 |

Theme is consistent: **momentum continuation with wide targets in calm
regimes** — the same conclusion FINDINGS.md reached from your fills
("momentum-continuation trader, not reversal"), now confirmed mechanically and
extended to the volatility dimension. Note every candidate's first half beats
its second half — the edge decayed as BTC matured; forward-testing is not
optional.

**Wired into tracking (H12/H13 in `strategy_eval`)**: the two strongest are now
in the weekly R-sweep registry so `/strategy` re-ranks them every Monday
against live-updated candles. NOT wired into the alert path — that happens only
after they hold up for some weeks of fresh data.

## Part 4 — what happens next

1. Trade the playbook with the wider target (1.5% zone) + BE-move rule; keep
   respecting vetoes — the off-playbook push (2026-07-02) polices this.
2. Watch H12/H13 in the Monday re-ranks; if they stay positive on fresh bars
   for ~a month, promote to scanner shadow-signals (emit + tag, no phone alert)
   to build a forward record.
3. Re-run `mine_20260702.py` after the v4 tagged-trade corpus exists — the
   miner answers "what contexts work mechanically"; only tagged live trades
   answer "what contexts work *for you*."

Raw output: `mine_20260702.json` · miner: `mine_20260702.py`
