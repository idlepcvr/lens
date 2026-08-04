import sqlite3, numpy as np, pandas as pd
from math import sqrt, erfc
from app.orderflow import load_funding

DB='file:/home/mini/lens/data/lens.db?mode=ro'
c=sqlite3.connect(DB,uri=True)
rows=c.execute("""SELECT id,direction,pnl,fees,funding_cost,opened_at,setup_tag,book
                  FROM trades WHERE exit IS NOT NULL AND pnl IS NOT NULL
                  ORDER BY opened_at""").fetchall()
c.close()
df=pd.DataFrame(rows,columns=["id","dir","pnl","fees","fund","opened","tag","book"])
df["opened"]=pd.to_datetime(df["opened"],utc=True,format='mixed')
df["tag"]=df["tag"].fillna("(untagged)")
def cls(t):
    if t=="(untagged)": return "(untagged)"
    if "VETO" in t: return "VETO"
    if t=="NONE": return "NONE"
    return "SETUP"
df["k"]=df["tag"].apply(cls)
df["win"]=df["pnl"]>0
print(f"closed trades: {len(df)}   {df.opened.min().date()} → {df.opened.max().date()}")
print(f"total P&L: €{df.pnl.sum():,.2f}   fees €{df.fees.sum():,.2f}\n")

def blk(g,lab):
    if not len(g): return
    print(f"{lab:<34}{len(g):>5}{100*g.win.mean():>8.1f}%{g.pnl.sum():>12,.2f}{g.pnl.mean():>10,.2f}")

print(f"{'WHAT THE SYSTEM SAID':<34}{'n':>5}{'WR':>9}{'P&L €':>12}{'€/trade':>10}")
for k in ["SETUP","NONE","VETO","(untagged)"]:
    blk(df[df.k==k],k)
print()
print(f"{'BY DIRECTION x TAG':<34}{'n':>5}{'WR':>9}{'P&L €':>12}{'€/trade':>10}")
for d in ("short","long"):
    for k in ("SETUP","NONE","VETO"):
        blk(df[(df.k==k)&(df["dir"]==d)],f"  {d} · {k}")
print()

# which veto rules cost the most
print(f"{'VETO RULE (trades may carry several)':<34}{'n':>5}{'WR':>9}{'P&L €':>12}{'€/trade':>10}")
rules={}
for _,r in df[df.k=="VETO"].iterrows():
    for rule in r.tag.split("VETO:")[-1].split(","):
        rules.setdefault(rule.strip(),[]).append(r)
for rule,rs in sorted(rules.items(),key=lambda x:sum(r.pnl for r in x[1])):
    g=pd.DataFrame(rs); blk(g,f"  {rule}")
print()

# era split — did it get worse after the system went live 2026-06-16?
LIVE=pd.Timestamp("2026-06-16",tz="UTC")
print(f"{'ERA':<34}{'n':>5}{'WR':>9}{'P&L €':>12}{'€/trade':>10}")
blk(df[df.opened<LIVE],"before system (pre 2026-06-16)")
blk(df[df.opened>=LIVE],"since system live")
print()
for k in ("SETUP","VETO"):
    blk(df[(df.opened>=LIVE)&(df.k==k)],f"  since live · {k}")
print()

# ── his question: were the losers funding flips? ──────────────────────────────
ser=load_funding(refresh=False)
f=pd.DataFrame({"fr":ser}); f["fp"]=ser.rolling(90,min_periods=90).apply(lambda w:(w[:-1]<=w[-1]).mean(),raw=True)
f.index=f.index.as_unit("ns")
d2=df.sort_values("opened").reset_index(drop=True)
left=pd.DataFrame(index=pd.DatetimeIndex(d2["opened"]).as_unit("ns")).sort_index()
al=pd.merge_asof(left,f.sort_index(),left_index=True,right_index=True,direction="backward")
d2["fr"]=al["fr"].to_numpy(); d2["fp"]=al["fp"].to_numpy()
# was funding hot in prior 24h then negative at entry?
fs=ser.copy()
def flipped(ts):
    w=fs[(fs.index<=ts)&(fs.index>ts-pd.Timedelta("24h"))]
    pv=f["fp"].reindex(w.index)
    return bool(len(w)) and bool((pv>=0.95).any()) and bool(w.iloc[-1]<0)
d2["flip"]=[flipped(t) for t in d2.opened]
print(f"{'FUNDING AT ENTRY':<34}{'n':>5}{'WR':>9}{'P&L €':>12}{'€/trade':>10}")
blk(d2[d2.fr>0],"funding positive")
blk(d2[d2.fr<0],"funding negative")
blk(d2[d2.fp>=0.80],"funding hot (>=80th)")
blk(d2[d2.flip],"FLIP: hot in 24h then negative")
blk(d2[~d2.flip],"not a flip")
print()
for d in ("short","long"):
    blk(d2[(d2.flip)&(d2["dir"]==d)],f"  flip · {d}")
