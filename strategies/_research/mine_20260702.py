"""Strategy audit + miner — 2026-07-02.

Answers three questions on the full 1h history (2019-05 .. now, fee-honest):
  A. What is the OPTIMAL SL x TP geometry for every labeled setup (S1-S5,
     H6-H11)?  (strategy_eval only sweeps R at a p65 structural stop.)
  B. Are there UNMINED context combos with a mechanical edge? Systematic sweep
     of 1-2-3 feature conjunctions x direction x geometry grid.
  C. Do the winners survive robustness (old-half / new-half both positive)?

Method: first-touch on forward excursion matrices (stop checked first =
conservative), net of 0.30% round-trip fee. Unresolved-in-96h occurrences are
excluded but tracked (resolution rate must stay >= 0.7).

Run from repo root:  .venv/bin/python3 strategies/_research/mine_20260702.py
Output: strategies/_research/mine_20260702.json (+ stdout tables)
"""
import itertools
import json
import os
import sqlite3
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.database import DB_PATH                      # noqa: E402
from app.setups import SetupEngine, _load_candles    # noqa: E402

FEE_PCT   = 0.30          # round-trip, % of notional
FWD       = 96            # forward window, bars (~4 days)
WARMUP    = 200
MIN_N     = 100           # min occurrences for a mined combo
MIN_HALF  = 30            # min occurrences per time half
MIN_RES   = 0.70          # min fraction resolved inside FWD
SL_GRID   = [0.4, 0.63, 0.8, 1.0, 1.5, 2.0]
TP_GRID   = [0.6, 0.95, 1.5, 2.0, 3.0, 4.0, 6.0]

t0 = time.time()
conn = sqlite3.connect(DB_PATH)
c1h  = _load_candles(conn)
conn.close()
eng  = SetupEngine(c1h)
N    = len(c1h)
print(f"[{time.time()-t0:5.0f}s] {N} candles loaded")

closes = np.array([r[4] for r in c1h], dtype=np.float64)
highs  = np.array([r[2] for r in c1h], dtype=np.float64)
lows   = np.array([r[3] for r in c1h], dtype=np.float64)

# ── forward excursion matrices: % move of high/low k bars ahead ──────────────
# FH[i,k-1] = (high[i+k]-close[i])/close[i]*100 ; FL likewise with low.
FH = np.full((N, FWD), np.nan, dtype=np.float32)
FL = np.full((N, FWD), np.nan, dtype=np.float32)
for k in range(1, FWD + 1):
    FH[: N - k, k - 1] = ((highs[k:] - closes[:-k]) / closes[:-k] * 100)[: N - k]
    FL[: N - k, k - 1] = ((lows[k:]  - closes[:-k]) / closes[:-k] * 100)[: N - k]
print(f"[{time.time()-t0:5.0f}s] excursion matrices built")

# ── per-bar contexts once ─────────────────────────────────────────────────────
ctxs = [None] * N
for i in range(WARMUP, N - FWD):
    ctxs[i] = eng.context(i)
print(f"[{time.time()-t0:5.0f}s] contexts computed")

atr = np.array([eng.atr14[i] or np.nan for i in range(N)], dtype=np.float64)
atr_pct = atr / closes * 100
q_lo, q_hi = np.nanpercentile(atr_pct[WARMUP:N-FWD], [33, 66])

# ── primitive masks (each: name -> bool array over bars) ─────────────────────
valid = np.zeros(N, dtype=bool)
valid[WARMUP : N - FWD] = True
for i in range(WARMUP, N - FWD):
    if ctxs[i] is None or ctxs[i].rsi is None:
        valid[i] = False

def mask(fn):
    m = np.zeros(N, dtype=bool)
    for i in range(WARMUP, N - FWD):
        if valid[i] and fn(ctxs[i]):
            m[i] = True
    return m

PRIMS = {  # name -> (dimension, mask)
    "rsi<30":      ("rsi",   mask(lambda c: c.rsi < 30)),
    "rsi30-40":    ("rsi",   mask(lambda c: 30 <= c.rsi < 40)),
    "rsi40-55":    ("rsi",   mask(lambda c: 40 <= c.rsi <= 55)),
    "rsi55-70":    ("rsi",   mask(lambda c: 55 < c.rsi <= 70)),
    "rsi>70":      ("rsi",   mask(lambda c: c.rsi > 70)),
    "london_kz":   ("kz",    mask(lambda c: c.killzone == "london_kz")),
    "ny_am_kz":    ("kz",    mask(lambda c: c.killzone == "ny_am_kz")),
    "ny_pm_kz":    ("kz",    mask(lambda c: c.killzone == "ny_pm_kz")),
    "asian_00_06": ("kz",    mask(lambda c: 0 <= c.hour < 6)),
    "premium":     ("pd",    mask(lambda c: c.pd_zone == "premium")),
    "discount":    ("pd",    mask(lambda c: c.pd_zone == "discount")),
    "eq":          ("pd",    mask(lambda c: c.pd_zone == "eq")),
    "sweep_buy":   ("sweep", mask(lambda c: c.sweep == "buyside")),
    "sweep_sell":  ("sweep", mask(lambda c: c.sweep == "sellside")),
    "no_sweep":    ("sweep", mask(lambda c: c.sweep is None)),
    "raid_pdh":    ("raid",  mask(lambda c: c.pd_raid == "pdh")),
    "raid_pdl":    ("raid",  mask(lambda c: c.pd_raid == "pdl")),
    "disp_bull":   ("disp",  mask(lambda c: c.displacement == "bull")),
    "disp_bear":   ("disp",  mask(lambda c: c.displacement == "bear")),
    "slope_up":    ("slope", mask(lambda c: c.slope == "up")),
    "slope_down":  ("slope", mask(lambda c: c.slope == "down")),
    "bear3":       ("streak", mask(lambda c: c.bear_streak3)),
    "bull3":       ("streak", mask(lambda c: c.bull_streak3)),
    "fvg_long":    ("fvg",   mask(lambda c: c.in_fvg["long"])),
    "fvg_short":   ("fvg",   mask(lambda c: c.in_fvg["short"])),
    "atr_low":     ("atr",   valid & (atr_pct < q_lo)),
    "atr_high":    ("atr",   valid & (atr_pct > q_hi)),
}
print(f"[{time.time()-t0:5.0f}s] {len(PRIMS)} primitive masks built")

HALF = (WARMUP + (N - FWD)) // 2   # time split for robustness

def evaluate(occ_idx, direction):
    """Best geometry for one occurrence set. Returns dict or None."""
    n = len(occ_idx)
    if n < MIN_N:
        return None
    fh, fl = FH[occ_idx], FL[occ_idx]          # (n, FWD)
    long_ = direction == "long"
    best = None
    for sl in SL_GRID:
        for tp in TP_GRID:
            if tp / sl < 0.8:                   # skip absurd inverse geometry
                continue
            if long_:
                tp_hit = fh >= tp
                sl_hit = fl <= -sl
            else:
                tp_hit = fl <= -tp
                sl_hit = fh >= sl
            # first index of touch; FWD if never
            tp_k = np.where(tp_hit.any(1), tp_hit.argmax(1), FWD)
            sl_k = np.where(sl_hit.any(1), sl_hit.argmax(1), FWD)
            resolved = (tp_k < FWD) | (sl_k < FWD)
            res_frac = resolved.mean()
            if res_frac < MIN_RES:
                continue
            win = (tp_k < sl_k) & resolved      # stop-first tie = loss (conservative)
            r = resolved.sum()
            if r < MIN_N:
                continue
            wr = win.sum() / r
            exp_pct = wr * tp - (1 - wr) * sl - FEE_PCT
            # split-half robustness
            first = occ_idx[resolved] < HALF
            w_res = win[resolved]
            n1, n2 = first.sum(), (~first).sum()
            if n1 < MIN_HALF or n2 < MIN_HALF:
                continue
            wr1 = w_res[first].mean()
            wr2 = w_res[~first].mean()
            e1 = wr1 * tp - (1 - wr1) * sl - FEE_PCT
            e2 = wr2 * tp - (1 - wr2) * sl - FEE_PCT
            score = min(e1, e2) * np.sqrt(r)    # robust: worst half, scaled by n
            if best is None or score > best["score"]:
                best = {"sl": sl, "tp": tp, "n": int(r), "wr": round(float(wr), 3),
                        "exp_pct": round(float(exp_pct), 3),
                        "exp_half1": round(float(e1), 3), "exp_half2": round(float(e2), 3),
                        "res_frac": round(float(res_frac), 2),
                        "score": round(float(score), 2)}
    return best

results = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "candles": N, "fee_pct": FEE_PCT, "labeled": [], "mined": []}

# ── A. labeled setups on the geometry grid ────────────────────────────────────
LABELED = {
    "S1 NY-AM flush (short)":       ("short", PRIMS["ny_am_kz"][1] & (PRIMS["rsi<30"][1] | PRIMS["rsi30-40"][1]) & PRIMS["bear3"][1]),
    "S2 premium disp (short)":      ("short", PRIMS["premium"][1] & PRIMS["disp_bear"][1]),
    "S3 continuation (long)":       ("long",  (PRIMS["rsi55-70"][1] | PRIMS["rsi>70"][1]) & PRIMS["sweep_buy"][1]),
    "S4 discount dip (long)":       ("long",  (PRIMS["rsi<30"][1] | PRIMS["rsi30-40"][1]) & PRIMS["discount"][1] & PRIMS["no_sweep"][1]),
    "S5 London momentum (long)":    ("long",  (PRIMS["rsi55-70"][1] | PRIMS["rsi>70"][1]) & PRIMS["london_kz"][1]),
    "H6 bear3+eq (short)":          ("short", PRIMS["bear3"][1] & PRIMS["eq"][1]),
    "H7 rsi>70 no-sweep (long)":    ("long",  PRIMS["rsi>70"][1] & PRIMS["no_sweep"][1]),
    "H8 bear disp+rsi<30 (short)":  ("short", PRIMS["disp_bear"][1] & PRIMS["rsi<30"][1]),
    "H9 London sellsweep (short)":  ("short", PRIMS["london_kz"][1] & PRIMS["sweep_sell"][1]),
    "H11 hi-vol rsi55-70 (short)":  ("short", PRIMS["atr_high"][1] & PRIMS["rsi55-70"][1]),
}
for name, (direction, m) in LABELED.items():
    occ = np.flatnonzero(m)
    r = evaluate(occ, direction)
    results["labeled"].append({"name": name, "dir": direction,
                               "occurrences": int(m.sum()), **(r or {"thin": True})})
print(f"[{time.time()-t0:5.0f}s] labeled setups swept")

# ── B. mine pairs, then extend the best to triples ────────────────────────────
prims = list(PRIMS.items())
pair_results = []
for (na, (da, ma)), (nb, (db, mb)) in itertools.combinations(prims, 2):
    if da == db:
        continue                    # same dimension never co-occurs meaningfully
    m = ma & mb
    if m.sum() < MIN_N:
        continue
    occ = np.flatnonzero(m)
    for direction in ("long", "short"):
        r = evaluate(occ, direction)
        if r:
            pair_results.append({"combo": f"{na} & {nb}", "dir": direction,
                                 "prims": (na, nb), **r})
pair_results.sort(key=lambda x: -x["score"])
print(f"[{time.time()-t0:5.0f}s] {len(pair_results)} viable pairs")

triple_results = []
seen = set()
for p in pair_results[:25]:
    for nc, (dc, mc) in prims:
        if nc in p["prims"]:
            continue
        if dc in (PRIMS[p["prims"][0]][0], PRIMS[p["prims"][1]][0]):
            continue
        key = tuple(sorted([*p["prims"], nc])) + (p["dir"],)
        if key in seen:
            continue
        seen.add(key)
        m = PRIMS[p["prims"][0]][1] & PRIMS[p["prims"][1]][1] & mc
        if m.sum() < MIN_N:
            continue
        r = evaluate(np.flatnonzero(m), p["dir"])
        if r:
            triple_results.append({"combo": " & ".join(key[:3]), "dir": p["dir"], **r})
triple_results.sort(key=lambda x: -x["score"])
print(f"[{time.time()-t0:5.0f}s] {len(triple_results)} viable triples")

results["mined"] = pair_results[:40] + triple_results[:40]

out = os.path.join(os.path.dirname(__file__), "mine_20260702.json")
with open(out, "w") as f:
    json.dump(results, f, indent=1, default=str)

def show(rows, title, k=15):
    print(f"\n== {title} ==")
    print(f"{'combo/setup':44s} {'dir':5s} {'n':>5s} {'SL':>4s} {'TP':>4s} {'WR':>6s} {'exp%':>6s} {'h1':>6s} {'h2':>6s} {'score':>6s}")
    for r in rows[:k]:
        if r.get("thin"):
            print(f"{r['name']:44s} {r['dir']:5s}  thin ({r['occurrences']})")
            continue
        nm = r.get("combo") or r.get("name")
        print(f"{nm:44s} {r['dir']:5s} {r['n']:>5d} {r['sl']:>4.2f} {r['tp']:>4.2f} "
              f"{r['wr']*100:>5.1f}% {r['exp_pct']:>6.3f} {r['exp_half1']:>6.3f} {r['exp_half2']:>6.3f} {r['score']:>6.2f}")

show(results["labeled"], "LABELED SETUPS — best geometry (robust)", 15)
show(pair_results, "MINED PAIRS — top by worst-half expectancy x sqrt(n)", 15)
show(triple_results, "MINED TRIPLES", 15)
print(f"\n[{time.time()-t0:5.0f}s] done -> {out}")
