"""NEXT_SESSION.md #1: point the miner at the VETO population itself.

Question: does any veto combination (trades.setup_tag = 'VETO:...') beat the
rest of the book on GROSS pnl, robustly? Reuses the permutation-bootstrap gate
from filter_significance.py and adds a leave-one-month-out check (same spirit
as short_edge.py's 4-gate elimination, scoped to this narrower question).

Run: python3 research/override_miner.py
"""
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd

DB = "file:/home/mini/lens/data/lens.db?mode=ro"
MIN_N = 15

c = sqlite3.connect(DB, uri=True)
rows = c.execute(
    """SELECT id, pnl, fees, opened_at, setup_tag
       FROM trades WHERE exit IS NOT NULL AND pnl IS NOT NULL"""
).fetchall()
c.close()

d = pd.DataFrame(rows, columns=["id", "pnl", "fees", "opened", "tag"])
d["opened"] = pd.to_datetime(d["opened"], utc=True, format="mixed")
d["fees"] = d["fees"].fillna(0.0)
d["gross"] = d["pnl"] + d["fees"]
d["month"] = d["opened"].dt.to_period("M")
d["combo"] = d["tag"].where(d["tag"].str.startswith("VETO:", na=False)).str.slice(5)


def boot(mask, lab, col="gross", N=20000):
    a = d.loc[mask, col].to_numpy()
    b = d.loc[~mask, col].to_numpy()
    if len(a) < MIN_N:
        return None
    obs = a.mean() - b.mean()
    rng = np.random.default_rng(11)
    pool = np.concatenate([a, b])
    na = len(a)
    diffs = np.empty(N)
    for i in range(N):
        p = rng.permutation(pool)
        diffs[i] = p[:na].mean() - p[na:].mean()
    p_val = (np.abs(diffs) >= abs(obs)).mean()

    # leave-one-month-out: of months this combo fired, how many are net-positive gross?
    sub = d.loc[mask]
    by_month = sub.groupby("month")["gross"].sum()
    months_up = int((by_month > 0).sum())
    months_total = len(by_month)

    star = "**SIGNIFICANT**" if p_val < 0.05 else ("marginal" if p_val < 0.15 else "noise")
    print(
        f"{lab:<48} n={len(a):<5} kept EUR{a.mean():>7.2f}/tr  "
        f"rest EUR{b.mean():>7.2f}/tr  diff{obs:>+8.2f}  p={p_val:.4f}  "
        f"months {months_up}/{months_total} up  {star}"
    )
    return p_val


print("=" * 110)
print("OVERRIDE MINER — every VETO combo with n>=15, gross EUR vs the rest of the book")
print("=" * 110)

combo_counts = d["combo"].value_counts()
for combo, n in combo_counts.items():
    if n < MIN_N:
        continue
    boot(d["combo"] == combo, combo, col="gross")

print(f"\nBonferroni threshold for {sum(combo_counts >= MIN_N)} combos tested: "
      f"p < {0.05 / max(sum(combo_counts >= MIN_N), 1):.4f}")
