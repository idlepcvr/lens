"""Honesty gates on the one candidate: funding collapse -> price UP."""
import numpy as np, pandas as pd
from math import sqrt, erfc
from app.backtest_engine import load_ohlcv, add_indicators, _run_backtest
from app.strategy_search import _sig_fn, CAPITAL, BASE_GEO

df = load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=84, exchange_id="binance")
df = pd.DataFrame({"open":df["open"].resample("4h").first(),"high":df["high"].resample("4h").max(),
                   "low":df["low"].resample("4h").min(),"close":df["close"].resample("4h").last(),
                   "volume":df["volume"].resample("4h").sum()}).dropna()
df = add_indicators(df)
n=len(df); fp=df["fund_pct"].to_numpy(); fr=df["fund_rate"].to_numpy()
def shift(a,k):
    o=np.full_like(a,np.nan); o[k:]=a[:-k]; return o
was_hot=np.zeros(n,bool)
for k in range(1,7): was_hot |= (shift(fp,k)>=0.95)
d3 = fr-shift(fr,3)
CAND={"flip hot->negative": was_hot&(fr<0), "funding falling hard": d3<-0.0002}

def trades(mask,d):
    mask=mask.copy(); mask[:60]=False
    return _run_backtest(df,_sig_fn(mask,d),{**BASE_GEO,"direction":d},CAPITAL)["trades"]
def wr(tr): 
    return (sum(1 for t in tr if t["pnl_pct"]>0)/len(tr)) if tr else float("nan")
def zt(k1,n1,k2,n2):
    p1,p2=k1/n1,k2/n2;p=(k1+k2)/(n1+n2);se=sqrt(p*(1-p)*(1/n1+1/n2)) or 1e-12
    return erfc(abs((p1-p2)/se)/sqrt(2))

mid = df.index[n//2]
print(f"split at {mid.date()}   (12 tests run earlier -> Bonferroni threshold p<0.0042)\n")
for lab,msk in CAND.items():
    for d in ("long","short"):
        tr=trades(msk,d); base=trades(np.ones(n,bool),d)
        if not tr: continue
        h1=[t for t in tr if pd.Timestamp(t["entry_ts"])<mid]
        h2=[t for t in tr if pd.Timestamp(t["entry_ts"])>=mid]
        b1=[t for t in base if pd.Timestamp(t["entry_ts"])<mid]
        b2=[t for t in base if pd.Timestamp(t["entry_ts"])>=mid]
        p_all=zt(sum(1 for t in tr if t["pnl_pct"]>0),len(tr),
                 sum(1 for t in base if t["pnl_pct"]>0),len(base))
        # label permutation: shuffle outcomes, how often does |diff| match?
        allpnl=np.array([t["pnl_pct"]>0 for t in base])
        obs=abs(wr(tr)-wr(base)); rng=np.random.default_rng(7); hits=0; N=2000
        for _ in range(N):
            s=rng.permutation(allpnl)[:len(tr)]
            if abs(s.mean()-allpnl.mean())>=obs: hits+=1
        print(f"{lab:<24}{d.upper():<6} n={len(tr):<4} WR={100*wr(tr):.1f}%  "
              f"base={100*wr(base):.1f}%  p={p_all:.3f}")
        print(f"{'':30}half1 n={len(h1):<3} WR={100*wr(h1):.1f}% (base {100*wr(b1):.1f}%)   "
              f"half2 n={len(h2):<3} WR={100*wr(h2):.1f}% (base {100*wr(b2):.1f}%)")
        print(f"{'':30}label-permutation p = {hits/N:.3f}   "
              f"{'SURVIVES Bonferroni' if p_all<0.0042 else 'fails Bonferroni'}\n")
