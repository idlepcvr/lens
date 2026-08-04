"""Two tests: funding TRANSITIONS (not levels), and funding x validated short."""
import sqlite3, numpy as np, pandas as pd
from math import sqrt, erfc
from app.backtest_engine import load_ohlcv, add_indicators, _run_backtest
from app.strategy_search import _masks, _sig_fn, _combo_mask, CAPITAL, BASE_GEO
from app.orderflow import load_funding
from app.paths import DB_PATH
import app.setups as S

def ztest(k1,n1,k2,n2):
    if n1==0 or n2==0: return 0.0,1.0
    p1,p2=k1/n1,k2/n2; p=(k1+k2)/(n1+n2)
    se=sqrt(p*(1-p)*(1/n1+1/n2)) or 1e-12
    z=(p1-p2)/se
    return z, erfc(abs(z)/sqrt(2))

def line(lab,k,n,bk,bn):
    if n==0: print(f"{lab:<44}{'no bars':>34}"); return
    z,pv=ztest(k,n,bk,bn)
    star="**SIG**" if pv<0.05 else ("~" if pv<0.15 else "")
    print(f"{lab:<44}{n:>6}{100*k/n:>8.1f}%{100*k/n-100*bk/bn:>+8.1f}pp  p={pv:<6.3f}{star}")

# ══ TEST 1 — funding transitions, 7y 4h ══════════════════════════════════════
print("="*96)
print("TEST 1 — funding TRANSITIONS (levels were noise; does the RESET fire?)")
print("="*96)
df = load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=84, exchange_id="binance")
df = pd.DataFrame({"open":df["open"].resample("4h").first(),"high":df["high"].resample("4h").max(),
                   "low":df["low"].resample("4h").min(),"close":df["close"].resample("4h").last(),
                   "volume":df["volume"].resample("4h").sum()}).dropna()
df = add_indicators(df)
n=len(df); fp=df["fund_pct"].to_numpy(); fr=df["fund_rate"].to_numpy()
print(f"bars={n}  {df.index[0].date()} → {df.index[-1].date()}\n")

def shift(a,k):
    o=np.full_like(a,np.nan); 
    if k>0: o[k:]=a[:-k]
    return o

was_hot = np.zeros(n,bool)          # pct>=0.95 anywhere in prior 6 bars (24h)
for k in range(1,7): was_hot |= (shift(fp,k)>=0.95)
was_cold = np.zeros(n,bool)
for k in range(1,7): was_cold |= (shift(fp,k)<=0.05)
d3 = fr - shift(fr,3)               # 12h rate-of-change

TRANS = {
 "reset from hot (was>=95th, now<50th)": was_hot & (fp<0.50),
 "flip hot->negative":                   was_hot & (fr<0),
 "reset from cold (was<=5th, now>50th)": was_cold & (fp>0.50),
 "flip cold->positive":                  was_cold & (fr>0),
 "funding falling hard (12h dROC<-0.02%)": d3 < -0.0002,
 "funding rising hard (12h dROC>+0.02%)":  d3 > +0.0002,
}
m=_masks(df)
def run(mask,d):
    mask=mask.copy(); mask[:60]=False
    tr=_run_backtest(df,_sig_fn(mask,d),{**BASE_GEO,"direction":d},CAPITAL)["trades"]
    if not tr: return 0,0,0.0
    w=sum(1 for t in tr if t["pnl_pct"]>0)
    return w,len(tr),sum(t["pnl_pct"] for t in tr)

for d in ("short","long"):
    bk,bn,_=run(np.ones(n,bool),d)
    print(f"--- {d.upper()}  (baseline {100*bk/bn:.1f}% on n={bn}) ---")
    print(f"{'condition':<44}{'n':>6}{'WR':>9}{'vs base':>10}")
    for lab,msk in TRANS.items():
        k,nn,_=run(msk,d); line(lab,k,nn,bk,bn)
    print()

# ══ TEST 2 — funding x validated short non-VETO ══════════════════════════════
print("="*96)
print("TEST 2 — funding x the VALIDATED short non-VETO setup (real setups.py)")
print("="*96)
conn=sqlite3.connect(DB_PATH); c1h=S._load_candles(conn); conn.close()
print(f"1h bars={len(c1h)}")
eng=S.SetupEngine(c1h)
ts=np.array([r[0] for r in c1h]); highs=np.array([r[2] for r in c1h])
lows=np.array([r[3] for r in c1h]); closes=np.array([r[4] for r in c1h])

# funding aligned to 1h bars (last settlement at or before bar)
ser=load_funding(refresh=False)
fser=pd.DataFrame({"fr":ser})
fser["fp"]=ser.rolling(90,min_periods=90).apply(lambda w:(w[:-1]<=w[-1]).mean(),raw=True)
idx=pd.to_datetime(ts,unit="ms",utc=True)
al=pd.merge_asof(pd.DataFrame(index=idx).sort_index(), fser.sort_index(),
                 left_index=True,right_index=True,direction="backward")
FR=al["fr"].to_numpy(); FP=al["fp"].to_numpy()

STOP=TGT=0.0283; MAXH=48
entries=[]
for i in range(S.WARMUP,len(c1h)-MAXH-1):
    ctx=eng.context(i)
    tag=S.classify(ctx,"short")
    if not tag or tag=="NONE" or "VETO" in tag: continue
    e=closes[i]; sl=e*(1+STOP); tp=e*(1-TGT); win=None
    for j in range(i+1,min(i+1+MAXH,len(c1h))):
        if highs[j]>=sl: win=False; break
        if lows[j]<=tp:  win=True;  break
    if win is None: win = closes[min(i+MAXH,len(c1h)-1)]<e
    entries.append((i,win,FR[i],FP[i]))

E=np.array([(w,fr,fp) for _,w,fr,fp in entries],dtype=float)
wins=E[:,0].astype(bool); FRe=E[:,1]; FPe=E[:,2]
bk,bn=int(wins.sum()),len(wins)
print(f"\nvalidated SHORT non-VETO, stop/target {STOP:.2%}, max {MAXH}h hold")
print(f"BASELINE: n={bn}  WR={100*bk/bn:.1f}%\n")
print(f"{'funding bucket at entry':<44}{'n':>6}{'WR':>9}{'vs base':>10}")
ok=~np.isnan(FPe)
BUCK={
 "funding hot (>=80th pct)":      ok&(FPe>=0.80),
 "funding extreme (>=95th)":      ok&(FPe>=0.95),
 "funding mid (20-80th)":         ok&(FPe>0.20)&(FPe<0.80),
 "funding cold (<=20th)":         ok&(FPe<=0.20),
 "funding positive (paid to short)": ~np.isnan(FRe)&(FRe>0),
 "funding negative (you PAY)":    ~np.isnan(FRe)&(FRe<0),
}
for lab,msk in BUCK.items():
    line(lab,int(wins[msk].sum()),int(msk.sum()),bk,bn)
