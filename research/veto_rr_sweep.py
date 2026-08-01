import json, random, sys
sys.path.insert(0,'/home/mini/lens/.claude/worktrees/geometry-barrier-math')
from research.veto_scanner import load_rows, resolve, stats
from app.geometry import FRICTION_PCT, solve
from app.setups import SetupEngine, vetoes, WARMUP
random.seed(42)
rows=load_rows(); eng=SetupEngine(rows)
nv={"long":[],"short":[]}
for i in range(WARMUP,len(rows)-1):
    ctx=eng.context(i)
    for d in ("long","short"):
        if not vetoes(ctx,d): nv[d].append(i)
weeks=len(rows)/24/7; half=len(rows)//2
sigma=json.load(open('/home/mini/lens/.claude/worktrees/geometry-barrier-math/results/barrier_baseline.json'))['sigma']
print(f"{'R:R':>4} {'stop':>6} {'target':>7} {'dir':>6} {'allbars':>8} {'noVETO':>8} {'edge':>8} {'BE':>7} {'net':>9} {'/wk':>6} {'H1':>8} {'H2':>8}")
out=[]
for rr in (1.0,2.0,3.0,4.0,6.0,8.0):
    g=solve(sigma,2.5,rr); SL,TP=g['stop_pct'],g['target_pct']
    for d in ("long","short"):
        outc=resolve(rows,SL,TP,d)
        allsel=[i for i in range(WARMUP,len(rows)-1) if outc[i] is not None]
        b=stats(allsel,outc,SL,TP); c=stats(nv[d],outc,SL,TP)
        if not c: continue
        h1=stats([i for i in nv[d] if i<half],outc,SL,TP)
        h2=stats([i for i in nv[d] if i>=half],outc,SL,TP)
        be=(SL+FRICTION_PCT)/((TP-FRICTION_PCT)+(SL+FRICTION_PCT))
        flag=' <<<' if c['net_pct']>0 and h1['net_pct']>0 and h2['net_pct']>0 else ''
        print(f"{rr:>4.0f} {SL:>5.2f}% {TP:>6.2f}% {d:>6} {b['win_rate']:>7.2%} {c['win_rate']:>7.2%} "
              f"{(c['win_rate']-b['win_rate'])*100:>+7.2f}pp {be:>6.1%} {c['net_pct']:>+8.3f}% "
              f"{c['n']/weeks:>5.1f} {h1['net_pct']:>+7.3f}% {h2['net_pct']:>+7.3f}%{flag}")
        out.append({"rr":rr,"dir":d,"stop":SL,"target":TP,"all":b['win_rate'],"nv":c['win_rate'],
                    "net":c['net_pct'],"per_week":c['n']/weeks,"h1":h1['net_pct'],"h2":h2['net_pct'],"n":c['n']})
json.dump(out,open('/home/mini/lens/.claude/worktrees/geometry-barrier-math/results/veto_rr_sweep.json','w'),indent=2)
