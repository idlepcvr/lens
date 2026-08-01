import json, random, sys
sys.path.insert(0,'/home/mini/lens/.claude/worktrees/geometry-barrier-math')
from research.veto_scanner import load_rows, resolve, stats
from app.geometry import FRICTION_PCT, solve
from app.setups import SetupEngine, vetoes, WARMUP
random.seed(42)
rows=load_rows(); eng=SetupEngine(rows)
sigma=json.load(open('/home/mini/lens/.claude/worktrees/geometry-barrier-math/results/barrier_baseline.json'))['sigma']
sets={}
for i in range(WARMUP,len(rows)-1):
    c=eng.context(i)
    for d in ("long","short"):
        if vetoes(c,d): continue
        sets.setdefault((d,'noveto'),[]).append(i)
        if c.killzone=='ny_am_kz': sets.setdefault((d,'nyam'),[]).append(i)
        if c.killzone=='london_kz': sets.setdefault((d,'london'),[]).append(i)
        if c.rsi is not None and c.rsi<40: sets.setdefault((d,'nyam+rsi40'),[]).append(i) if c.killzone=='ny_am_kz' else None
weeks=len(rows)/24/7; half=len(rows)//2
print(f"{'R:R':>4} {'dir':>6} {'filter':>12} {'n':>6} {'WR':>7} {'BE':>7} {'net':>9} {'/wk':>6} {'H1':>8} {'H2':>8} {'p':>7}")
res=[]
for rr in (1.0,2.0,4.0):
    g=solve(sigma,2.5,rr); SL,TP=g['stop_pct'],g['target_pct']
    be=(SL+FRICTION_PCT)/((TP-FRICTION_PCT)+(SL+FRICTION_PCT))
    for d in ("long","short"):
        outc=resolve(rows,SL,TP,d)
        pool=[outc[i] for i in sets[(d,'noveto')] if outc[i] is not None]
        for key in ('noveto','nyam','london','nyam+rsi40'):
            sel=sets.get((d,key))
            if not sel: continue
            s=stats(sel,outc,SL,TP)
            if not s or s['n']<40: continue
            h1=stats([i for i in sel if i<half],outc,SL,TP); h2=stats([i for i in sel if i>=half],outc,SL,TP)
            k=s['n']; ge=sum(1 for _ in range(2000) if sum(random.sample(pool,k))/k>=s['win_rate'])
            p=ge/2000
            ok = s['net_pct']>0 and h1 and h2 and h1['net_pct']>0 and h2['net_pct']>0
            print(f"{rr:>4.0f} {d:>6} {key:>12} {s['n']:>6} {s['win_rate']:>6.2%} {be:>6.1%} "
                  f"{s['net_pct']:>+8.3f}% {s['n']/weeks:>5.2f} {h1['net_pct']:>+7.3f}% {h2['net_pct']:>+7.3f}% "
                  f"{p:>6.3f}{'  <<< POSITIVE' if ok else ''}")
            res.append({"rr":rr,"dir":d,"filter":key,"n":s['n'],"wr":s['win_rate'],"be":be,
                        "net":s['net_pct'],"per_week":s['n']/weeks,"h1":h1['net_pct'],"h2":h2['net_pct'],"p":p,"positive":ok})
json.dump(res,open('/home/mini/lens/.claude/worktrees/geometry-barrier-math/results/veto_killzone.json','w'),indent=2)
