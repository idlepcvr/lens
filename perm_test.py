"""
Permutation robustness check for the discipline filters (discipline.py).

Question: are the ledger-derived rules (09:00 BKK bleed hour, Saturday-is-fine)
signal, or the inevitable extremes of slicing ~200 trades into 24 hour buckets
/ 7 weekday buckets and picking the worst/best one?

Method: keep every trade's timestamp fixed, shuffle the P&L values across
trades N times, and ask how often chance alone produces:
  a) an hour-9 bucket as bad as the real one          (fixed bucket, no selection)
  b) ANY hour bucket as bad as the real worst hour    (selection-corrected —
     this is the honest number; the rule was found by picking the worst bucket)
  c) ANY weekday as good as the real Saturday         (selection-corrected)

Population mirrors the 2026-07-12 derivation: pnl NOT NULL, bucketed by
opened_at in Bangkok time (UTC+7), 2026-only primary, lifetime secondary.
Uses trades.pnl only — never balance_after (not account equity).

Run:  python3 perm_test.py            (~2s, prints report)
"""

import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DB = Path(__file__).parent / "lens.db"
N_SHUFFLES = 10_000
BKK = timedelta(hours=7)


def load(since: str | None):
    q = "SELECT opened_at, pnl FROM trades WHERE pnl IS NOT NULL"
    if since:
        q += f" AND opened_at >= '{since}'"
    rows = sqlite3.connect(DB).execute(q).fetchall()
    out = []
    for ts, pnl in rows:
        dt = datetime.fromisoformat(ts.replace("Z", "")) + BKK
        out.append((dt.hour, dt.weekday(), pnl))  # weekday: Mon=0 .. Sat=5
    return out


def bucket_sums(keys, pnls):
    s = defaultdict(float)
    for k, p in zip(keys, pnls):
        s[k] += p
    return s


def perm_test(trades, label):
    hours = [t[0] for t in trades]
    days = [t[1] for t in trades]
    pnls = [t[2] for t in trades]

    hr = bucket_sums(hours, pnls)
    dy = bucket_sums(days, pnls)
    obs_h9 = hr.get(9, 0.0)
    obs_worst_hr = min(hr.values())
    worst_hr = min(hr, key=hr.get)
    obs_sat = dy.get(5, 0.0)
    obs_best_day = max(dy.values())

    hits_h9 = hits_worst = hits_sat_best = 0
    shuffled = pnls[:]
    rng = random.Random(42)
    for _ in range(N_SHUFFLES):
        rng.shuffle(shuffled)
        h = bucket_sums(hours, shuffled)
        if h.get(9, 0.0) <= obs_h9:
            hits_h9 += 1
        if min(h.values()) <= obs_worst_hr:
            hits_worst += 1
        if max(bucket_sums(days, shuffled).values()) >= obs_sat:
            hits_sat_best += 1

    n9 = hours.count(9)
    print(f"\n=== {label} — {len(trades)} trades, {N_SHUFFLES} shuffles ===")
    print(f"09:00 BKK bucket:   {n9} trades, €{obs_h9:+,.0f}")
    print(f"  p (hour 9 this bad, fixed bucket)      = {hits_h9 / N_SHUFFLES:.4f}")
    print(f"  p (ANY hour this bad — honest number)  = {hits_worst / N_SHUFFLES:.4f}"
          f"   [real worst hour: {worst_hr:02d}:00 BKK €{obs_worst_hr:+,.0f}]")
    print(f"Saturday bucket:    {days.count(5)} trades, €{obs_sat:+,.0f}")
    print(f"  p (ANY weekday this good)              = {hits_sat_best / N_SHUFFLES:.4f}")
    return hits_h9 / N_SHUFFLES, hits_worst / N_SHUFFLES, hits_sat_best / N_SHUFFLES


def selftest():
    # equal pnls: every shuffle identical, all p-values must be 1.0
    fake = [(h % 24, h % 7, -10.0) for h in range(200)]
    assert perm_test(fake, "selftest: uniform pnl") == (1.0, 1.0, 1.0)
    print("selftest OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        perm_test(load("2026-01-01"), "2026 only (basis of the current rules)")
        perm_test(load(None), "lifetime")
        print("\nReading: p < 0.05 → rule beats luck. p > 0.2 → likely noise-mined;"
              "\nkeep collecting (rejected signals are stored) before trusting it.")
