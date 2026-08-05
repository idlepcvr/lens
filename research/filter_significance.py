"""Which of the candidate filters actually survives a significance check?
Bootstrap on GROSS per-trade, because fees are a separate (larger) problem.
"""
import sqlite3, numpy as np, pandas as pd

DB = 'file:/home/mini/lens/data/lens.db?mode=ro'
c = sqlite3.connect(DB, uri=True)
rows = c.execute("""SELECT id,direction,entry,size,pnl,fees,opened_at,setup_tag
                    FROM trades WHERE exit IS NOT NULL AND pnl IS NOT NULL
                    ORDER BY opened_at""").fetchall()
c.close()
d = pd.DataFrame(rows, columns=["id","dir","entry","size","pnl","fees","opened","tag"])
d["opened"] = pd.to_datetime(d["opened"], utc=True, format='mixed')
d["fees"] = d["fees"].fillna(0.0)
d["gross"] = d["pnl"] + d["fees"]
d["tag"] = d["tag"].fillna("(untagged)")

from app.backtest_engine import load_ohlcv
px = load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=84, exchange_id="binance")
daily = px["close"].resample("1D").last().dropna()
score = pd.Series(0, index=daily.index, dtype=float)
for n in (5, 10, 21, 42):
    score += np.sign(daily - daily.shift(n))
mom = pd.DataFrame({"score": score}).dropna().shift(1).dropna()
if mom.index.tz is None:
    mom.index = mom.index.tz_localize("UTC")
mom.index = mom.index.as_unit("ns")
left = pd.DataFrame(index=pd.DatetimeIndex(d["opened"]).as_unit("ns")).sort_index()
d = d.sort_values("opened").reset_index(drop=True)
d["score"] = pd.merge_asof(left, mom.sort_index(), left_index=True,
                           right_index=True, direction="backward")["score"].to_numpy()

from app.orderflow import load_funding
ser = load_funding(refresh=False)
f = pd.DataFrame({"fr": ser})
f["fp"] = ser.rolling(90, min_periods=90).apply(lambda w: (w[:-1] <= w[-1]).mean(), raw=True)
f.index = f.index.as_unit("ns")
al = pd.merge_asof(left, f.sort_index(), left_index=True, right_index=True,
                   direction="backward")
d["fr"], d["fp"] = al["fr"].to_numpy(), al["fp"].to_numpy()
d = d.dropna(subset=["score"])


def boot(mask, lab, col="gross", N=20000):
    """Bootstrap the difference in mean per-trade between mask and ~mask."""
    a = d.loc[mask, col].to_numpy()
    b = d.loc[~mask, col].to_numpy()
    if len(a) < 10 or len(b) < 10:
        print(f"{lab:<38} n={len(a):<5} too few"); return
    obs = a.mean() - b.mean()
    rng = np.random.default_rng(11)
    pool = np.concatenate([a, b]); na = len(a)
    diffs = np.empty(N)
    for i in range(N):
        p = rng.permutation(pool)
        diffs[i] = p[:na].mean() - p[na:].mean()
    p_val = (np.abs(diffs) >= abs(obs)).mean()
    star = "**SIGNIFICANT**" if p_val < 0.05 else ("marginal" if p_val < 0.15 else "noise")
    print(f"{lab:<38} n={len(a):<5} kept EUR{a.mean():>7.2f}/tr  "
          f"rest EUR{b.mean():>7.2f}/tr  diff{obs:>+8.2f}  p={p_val:.4f}  {star}")


print("="*104)
print("PERMUTATION TEST — GROSS EUR per trade, filter vs everything else  (520 trades)")
print("="*104)
boot(d.score.abs() == 4,                      "|score|=4  all 4 horizons agree")
boot(d.score.abs() <= 1,                      "|score|<=1 chop (expect NEGATIVE diff)")
boot(np.where(d["dir"] == "long", d.score > 0, d.score < 0), "trade agrees with trend direction")
boot(d.fr > 0,                                "funding positive at entry")
boot(d.fp >= 0.80,                            "funding hot (>=80th pct)")
boot(d.fp <= 0.20,                            "funding cold (<=20th pct)")
boot((d.fp >= 0.80) | (d.fp <= 0.20),         "funding EXTREME (either tail)")
boot(d.tag.str.contains("VETO", na=False),    "system said VETO (expect NEGATIVE)")
boot((~d.tag.str.contains("VETO", na=False)) & (d.tag != "NONE") & (d.tag != "(untagged)"),
                                              "system said SETUP")

print("\n" + "="*104)
print("SAME TESTS ON *NET* EUR per trade — what actually hit the account")
print("="*104)
boot(d.score.abs() == 4,                      "|score|=4  all 4 horizons agree", col="pnl")
boot(d.fp <= 0.20,                            "funding cold (<=20th pct)", col="pnl")
boot((d.fp >= 0.80) | (d.fp <= 0.20),         "funding EXTREME (either tail)", col="pnl")
boot(d.tag.str.contains("VETO", na=False),    "system said VETO (expect NEGATIVE)", col="pnl")
boot((~d.tag.str.contains("VETO", na=False)) & (d.tag != "NONE") & (d.tag != "(untagged)"),
                                              "system said SETUP", col="pnl")

print("\n" + "="*104)
print("COUNTERFACTUAL — what the account would have done under each filter (NET, after fees)")
print("="*104)
print(f"{'rule':<44}{'trades':>8}{'net EUR':>12}{'EUR/trade':>12}{'fees paid':>12}")
def cf(mask, lab):
    g = d[mask]
    print(f"{lab:<44}{len(g):>8}{g.pnl.sum():>12,.0f}{g.pnl.mean():>12,.2f}{g.fees.sum():>12,.0f}")
cf(d.id == d.id,                                    "take everything (what he did)")
cf(d.score.abs() == 4,                              "only |score|=4")
cf((d.fp >= 0.80) | (d.fp <= 0.20),                 "only funding extremes")
cf(~d.tag.str.contains("VETO", na=False),           "obey his own VETO")
setup = (~d.tag.str.contains("VETO", na=False)) & (d.tag != "NONE") & (d.tag != "(untagged)")
cf(setup,                                           "only his own SETUP tag")
cf(setup & (d.score.abs() == 4),                    "SETUP and |score|=4")
cf(setup & ((d.fp >= 0.80) | (d.fp <= 0.20)),       "SETUP and funding extreme")

assert abs(d.gross.sum() - (d.pnl.sum() + d.fees.sum())) < 1e-6
print("\nself-check OK")
