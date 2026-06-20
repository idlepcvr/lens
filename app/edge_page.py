"""LENS /edge — setup-edge scoreboard.

Realised performance per setup family (S1..S5 / vetoed / VETO / NONE) with a
KEEP / CUT / SIZE-UP / THIN verdict from expectancy·WR·sample, plus a grade
split so you can see whether a setup's edge is the setup or your execution.
Fed by /api/review/trades (auto-tagged on sync).
"""

from .theme import shell

_CSS = """
<style>
.ed-sub{color:var(--dim);font-size:12px;margin:2px 0 14px}
.ed-tbl{width:100%;border-collapse:collapse;font-size:13px}
.ed-tbl th{text-align:right;color:var(--dim);font-weight:600;padding:7px 10px;border-bottom:1px solid var(--line);text-transform:uppercase;font-size:9px;letter-spacing:.05em}
.ed-tbl th:first-child,.ed-tbl td:first-child{text-align:left}
.ed-tbl td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.ed-tbl tr.main td{font-weight:600}
.ed-gchip{display:inline-block;font-size:10px;padding:1px 6px;margin:3px 5px 0 0;border:1px solid var(--line2);border-radius:4px;color:var(--dim)}
.g{color:var(--long)} .r{color:var(--short)} .amb{color:var(--amber)} .dim{color:var(--dim)}
</style>
"""

BODY = """
<div class="ed-sub">Per-setup realised edge · auto-tagged on sync · verdict from expectancy · WR · sample</div>
<div class="panel" style="overflow-x:auto">
  <table class="ed-tbl">
    <thead><tr><th>Setup</th><th>n</th><th>WR</th><th>Avg€</th><th>Total€</th><th>Verdict</th></tr></thead>
    <tbody id="edge-body"><tr><td colspan="6" class="dim" style="padding:20px">Loading…</td></tr></tbody>
  </table>
</div>
"""

SCRIPT = r"""
function edgeFamily(tag){
  if(!tag) return '(untagged)';
  if(tag.startsWith('VETO:')) return 'VETO';
  if(tag.includes('|VETO:')) return tag.split('|')[0]+' (vetoed)';
  return tag;
}
function edgeVerdict(n,wr,exp){
  if(n<8)               return ['THIN','var(--dim)'];
  if(exp<=0)            return ['CUT','var(--short)'];
  if(exp>=10&&n>=12&&wr>=45) return ['SIZE-UP','var(--long)'];
  return ['KEEP','var(--amber)'];
}
function render(trades){
  const g={};
  trades.filter(t=>t.pnl!=null).forEach(t=>{
    const k=edgeFamily(t.setup_tag);
    if(!g[k]) g[k]={n:0,wins:0,total:0,byGrade:{}};
    g[k].n++; if((t.pnl||0)>0)g[k].wins++; g[k].total+=t.pnl||0;
    const gr=t.grade||'—';
    if(!g[k].byGrade[gr]) g[k].byGrade[gr]={n:0,wins:0,total:0};
    g[k].byGrade[gr].n++; if((t.pnl||0)>0)g[k].byGrade[gr].wins++; g[k].byGrade[gr].total+=t.pnl||0;
  });
  const rows=Object.entries(g).sort((a,b)=>b[1].total-a[1].total);
  document.getElementById('edge-body').innerHTML=rows.map(([k,d])=>{
    const exp=d.total/d.n, wr=d.wins/d.n*100;
    const [vl,vc]=edgeVerdict(d.n,wr,exp);
    const grades=Object.entries(d.byGrade).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
    const sub=grades.length>1?grades.map(([gr,gd])=>
      `<span class="ed-gchip">${gr}: ${gd.n}·${(gd.wins/gd.n*100).toFixed(0)}%·<span style="color:${gd.total>=0?'var(--long)':'var(--short)'}">${gd.total>=0?'+':''}${gd.total.toFixed(0)}€</span></span>`).join(''):'';
    return `<tr class="main"><td>${k}</td><td>${d.n}</td><td>${wr.toFixed(0)}%</td>
      <td style="color:${exp>=0?'var(--long)':'var(--short)'}">${exp>=0?'+':''}${exp.toFixed(0)}€</td>
      <td style="color:${d.total>=0?'var(--long)':'var(--short)'}">${d.total>=0?'+':''}${d.total.toFixed(0)}€</td>
      <td><b style="color:${vc}">${vl}</b></td></tr>`+
      (sub?`<tr><td colspan="6" style="padding:0 0 6px 10px">${sub}</td></tr>`:'');
  }).join('');
}
fetch('/api/review/trades').then(r=>r.json()).then(render).catch(e=>{
  document.getElementById('edge-body').innerHTML='<tr><td colspan="6" class="r" style="padding:20px">Load error: '+e.message+'</td></tr>';});
"""

EDGE_HTML = shell("/edge", "Edge", BODY, script=SCRIPT, head_extra=_CSS, meta="which setups pay?")
