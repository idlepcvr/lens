"""Two tests against the real LENS ledger:
  1. multi-horizon momentum score (ManAHL style) at entry vs realised P&L
  2. funding/crowding at entry vs realised P&L
Both reported NET and GROSS of fees, because the book's whole loss is fees.
"""
import sqlite3, numpy as np, pandas as pd
from math import sqrt

DB = 'file:/home/mini/lens/data/lens.db?mode=ro'
c = sqlite3.connect(DB, uri=True)
rows = c.execute("""SELECT id,direction,entry,exit,size,leverage,pnl,fees,funding_cost,
                           opened_at,setup_tag,book,venue
                    FROM trades WHERE exit IS NOT NULL AND pnl IS NOT NULL
                    ORDER BY opened_at""").fetchall()
c.close()
d = pd.DataFrame(rows, columns=["id","dir","entry","exit","size","lev","pnl","fees",
                                "fund","opened","tag","book","venue"])
d["opened"] = pd.to_datetime(d["opened"], utc=True, format='mixed')
d["fees"] = d["fees"].fillna(0.0)
d["gross"] = d["pnl"] + d["fees"]          # pnl is NET (database.py:353)
d["notional"] = d["size"] * d["entry"]
d["fee_pct"] = 100 * d["fees"] / d["notional"]

print("="*78)
print("FEE DRAG — the headline")
print("="*78)
print(f"closed trades      {len(d)}   {d.opened.min().date()} -> {d.opened.max().date()}")
print(f"NET P&L            EUR {d.pnl.sum():>12,.2f}")
print(f"fees paid          EUR {d.fees.sum():>12,.2f}")
print(f"GROSS P&L          EUR {d.gross.sum():>12,.2f}   <- before fees")
print(f"gross per trade    EUR {d.gross.mean():>12,.2f}")
print(f"fee   per trade    EUR {d.fees.mean():>12,.2f}")
print(f"fees / gross edge  {d.fees.sum()/abs(d.gross.sum()):>12,.1f}x")
print(f"median fee as % of notional  {d.fee_pct.median():.4f}%  "
      f"(round-trip taker on Kraken futures ~0.10%)")
print(f"total notional traded  EUR {d.notional.sum():>14,.0f}")
print(f"fees / notional        {100*d.fees.sum()/d.notional.sum():.4f}%")

# ---------------------------------------------------------------- momentum
from app.backtest_engine import load_ohlcv
px = load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=84, exchange_id="binance")
daily = px["close"].resample("1D").last().dropna()

score = pd.Series(0, index=daily.index, dtype=float)
for n in (5, 10, 21, 42):
    score += np.sign(daily - daily.shift(n))
mom = pd.DataFrame({"close": daily, "score": score}).dropna()
# shift by 1 day: a trade at time t may only use the close of the PREVIOUS day
mom = mom.shift(1).dropna()
mom.index = mom.index.tz_localize("UTC") if mom.index.tz is None else mom.index
mom.index = mom.index.as_unit("ns")

left = pd.DataFrame(index=pd.DatetimeIndex(d["opened"]).as_unit("ns")).sort_index()
d2 = d.sort_values("opened").reset_index(drop=True)
al = pd.merge_asof(left, mom.sort_index(), left_index=True, right_index=True,
                   direction="backward")
d2["score"] = al["score"].to_numpy()
d2 = d2.dropna(subset=["score"])
d2["win"] = d2.pnl > 0
# does the trade agree with the trend the score describes?
d2["with_trend"] = np.where(d2["dir"] == "long", d2.score > 0, d2.score < 0)
d2["agree"] = np.where(d2.score == 0, "flat",
                np.where(d2.with_trend, "with trend", "against trend"))

def blk(g, lab):
    if not len(g):
        return
    print(f"{lab:<30}{len(g):>5}{100*g.win.mean():>8.1f}%"
          f"{g.pnl.sum():>12,.0f}{g.gross.sum():>12,.0f}{g.gross.mean():>10,.2f}")

hdr = f"{'':<30}{'n':>5}{'WR':>9}{'NET':>12}{'GROSS':>12}{'gross/tr':>10}"
print("\n" + "="*78)
print("TEST 1 — multi-horizon momentum score at entry (ManAHL style)")
print("="*78)
print(hdr)
for s in sorted(d2.score.unique()):
    blk(d2[d2.score == s], f"  score = {s:+.0f}")
print()
for a in ("with trend", "against trend", "flat"):
    blk(d2[d2.agree == a], a)
print()
print("  |score| = conviction / horizon agreement")
blk(d2[d2.score.abs() == 4], "  |score|=4  all agree")
blk(d2[d2.score.abs() == 2], "  |score|=2  mixed")
blk(d2[d2.score.abs() <= 1], "  |score|<=1 chop")

# t-test: with-trend vs against-trend on GROSS per trade
a = d2[d2.agree == "with trend"].gross
b = d2[d2.agree == "against trend"].gross
if len(a) > 2 and len(b) > 2:
    t = (a.mean()-b.mean()) / sqrt(a.var(ddof=1)/len(a) + b.var(ddof=1)/len(b))
    print(f"\n  with-trend vs against-trend, GROSS per trade: "
          f"diff EUR {a.mean()-b.mean():+.2f}  t = {t:+.2f}")

# ---------------------------------------------------------------- funding
print("\n" + "="*78)
print("TEST 2 — funding / crowding at entry, on GROSS (fee-independent)")
print("="*78)
from app.orderflow import load_funding
ser = load_funding(refresh=False)
f = pd.DataFrame({"fr": ser})
f["fp"] = ser.rolling(90, min_periods=90).apply(lambda w: (w[:-1] <= w[-1]).mean(), raw=True)
f.index = f.index.as_unit("ns")
al2 = pd.merge_asof(left, f.sort_index(), left_index=True, right_index=True,
                    direction="backward")
d2["fr"] = al2["fr"].to_numpy()
d2["fp"] = al2["fp"].to_numpy()
print(hdr)
blk(d2[d2.fr > 0], "funding positive")
blk(d2[d2.fr < 0], "funding negative")
blk(d2[d2.fp >= 0.80], "funding hot (>=80th pct)")
blk(d2[d2.fp <= 0.20], "funding cold (<=20th pct)")
print()
for dd in ("long", "short"):
    blk(d2[(d2.fr < 0) & (d2["dir"] == dd)], f"  funding negative . {dd}")
    blk(d2[(d2.fr > 0) & (d2["dir"] == dd)], f"  funding positive . {dd}")

a = d2[d2.fr > 0].gross
b = d2[d2.fr < 0].gross
t = (a.mean()-b.mean()) / sqrt(a.var(ddof=1)/len(a) + b.var(ddof=1)/len(b))
print(f"\n  funding+ vs funding-, GROSS per trade: "
      f"diff EUR {a.mean()-b.mean():+.2f}  t = {t:+.2f}")

# ---------------------------------------------------------------- combined
print("\n" + "="*78)
print("BOTH FILTERS TOGETHER (gross)")
print("="*78)
print(hdr)
keep = d2[(d2.agree != "flat") & (d2.with_trend) & (d2.fr > 0)]
blk(keep, "with-trend AND funding+")
blk(d2[~d2.index.isin(keep.index)], "everything else")
print(f"\nfee per trade EUR {d2.fees.mean():.2f} — a filter only pays if the "
      f"trades it keeps clear that.")


def demo():
    """ponytail: one self-check that the fee/gross algebra holds."""
    t = d2.iloc[0]
    assert abs((t.pnl + t.fees) - t.gross) < 1e-9
    assert abs(d.gross.sum() - (d.pnl.sum() + d.fees.sum())) < 1e-6
    assert d2.score.between(-4, 4).all()
    assert set(d2.agree) <= {"with trend", "against trend", "flat"}
    print("\nself-check OK")


demo()
