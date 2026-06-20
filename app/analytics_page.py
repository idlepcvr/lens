"""LENS /analytics — performance & risk dashboard from the hedge trade log.

Pure analytics surface (no charts — those live in the Journal/Calendar trade
modal). Fetches /api/review/analytics and renders performance, risk-adjusted
ratios, actual-vs-model, and the duration breakdown that shows where the edge
lives (long holds carry).
"""

from .theme import shell

_CSS = """
<style>
.an-sec{margin-bottom:20px}
.an-h{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:0 0 9px;
  border-bottom:1px solid var(--line);padding-bottom:5px}
.an-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:9px}
.an-card{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.an-card .k{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.an-card .v{font-size:19px;font-weight:700;font-family:var(--mono)}
.an-card .s{font-size:9px;color:var(--faint);margin-top:2px}
.an-tbl{width:100%;border-collapse:collapse;font-size:12px}
.an-tbl th{text-align:right;color:var(--dim);font-weight:600;padding:5px 9px;border-bottom:1px solid var(--line);text-transform:uppercase;font-size:9px}
.an-tbl th:first-child,.an-tbl td:first-child{text-align:left}
.an-tbl td{text-align:right;padding:5px 9px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.an-tbl tr.hot td{background:rgba(31,217,137,.10)}
.g{color:var(--long)} .r{color:var(--short)}
</style>
"""

BODY = """
<div id="analytics"><div style="padding:30px;color:var(--dim)">Loading analytics…</div></div>
"""

SCRIPT = r"""
const eur=v=>v==null?'—':(v>=0?'+':'')+'€'+Math.abs(v).toFixed(2);
const pc=v=>v>=0?'var(--long)':'var(--short)';
function render(a){
  const host=document.getElementById('analytics');
  if(!a||!a.n){host.innerHTML='<div style="padding:30px;color:var(--dim)">No closed trades yet.</div>';return;}
  const card=(k,v,s,col)=>`<div class="an-card"><div class="k">${k}</div><div class="v" style="color:${col||'var(--ink)'}">${v}</div>${s?`<div class="s">${s}</div>`:''}</div>`;
  const perf=`<div class="an-sec"><div class="an-h">Performance · live from trade log</div><div class="an-grid">`+
    card('Trades',a.n,a.open?a.open+' open':'')+
    card('Win Rate',a.wr+'%',a.long_wr!=null?`L ${a.long_wr}% · S ${a.short_wr}%`:'')+
    card('Net P&L',eur(a.total_pnl),'',pc(a.total_pnl))+
    card('Expectancy',eur(a.expectancy),'per trade',pc(a.expectancy))+
    card('Avg Win',eur(a.avg_win),'','var(--long)')+
    card('Avg Loss',eur(-a.avg_loss),'','var(--short)')+
    card('Actual R:R',a.rr!=null?a.rr+'×':'—','')+
    card('Profit Factor',a.profit_factor!=null?a.profit_factor:'—','',a.profit_factor>=1?'var(--long)':'var(--short)')+
    card('Total Fees',eur(-a.total_fees),'','var(--short)')+
    card('Avg Duration',a.avg_dur_h!=null?a.avg_dur_h+'h':'—','')+
    `</div></div>`;
  const risk=`<div class="an-sec"><div class="an-h">Risk-adjusted</div><div class="an-grid">`+
    card('Sharpe',a.sharpe,'per-trade · ann.',a.sharpe>=0?'var(--long)':'var(--short)')+
    card('Sortino',a.sortino,'',a.sortino>=0?'var(--long)':'var(--short)')+
    card('Max DD',eur(-a.max_dd_eur)+(a.max_dd_pct!=null?` · ${a.max_dd_pct}%`:''),'peak→trough','var(--short)')+
    card('Win Streak',a.win_streak,'','var(--long)')+
    card('Loss Streak',a.loss_streak,'','var(--short)')+
    (a.cum_return!=null?card('Cum Return',a.cum_return+'%','',pc(a.cum_return)):card('Cum Return','—','set capital base'))+
    (a.ann_return!=null?card('Ann Return',a.ann_return+'%','',pc(a.ann_return)):'')+
    (a.calmar!=null?card('Calmar',a.calmar,''):'')+
    `</div></div>`;
  const dWR=a.wr-(a.model_wr||0), dRR=(a.rr||0)-(a.model_rr||0);
  const avm=`<div class="an-sec"><div class="an-h">Actual vs Model</div><table class="an-tbl">
    <tr><th>Metric</th><th>Model</th><th>Actual</th><th>Δ</th></tr>
    <tr><td>Win Rate</td><td>${a.model_wr!=null?a.model_wr+'%':'—'}</td><td>${a.wr}%</td><td style="color:${pc(dWR)}">${dWR>=0?'+':''}${dWR.toFixed(1)}</td></tr>
    <tr><td>R:R</td><td>${a.model_rr!=null?a.model_rr+'×':'—'}</td><td>${a.rr!=null?a.rr+'×':'—'}</td><td style="color:${pc(dRR)}">${dRR>=0?'+':''}${dRR.toFixed(2)}</td></tr>
    </table></div>`;
  const dur=`<div class="an-sec"><div class="an-h">Trade Duration Breakdown <span style="color:var(--faint);text-transform:none;font-weight:400">— where the edge lives</span></div><table class="an-tbl">
    <tr><th>Duration</th><th>Count</th><th>W</th><th>L</th><th>Total P&L</th><th>Avg P&L</th></tr>`+
    a.duration.map(d=>`<tr class="${d.total>0&&d.n>=8?'hot':''}"><td>${d.label}</td><td>${d.n}</td><td>${d.w}</td><td>${d.l}</td>
      <td style="color:${pc(d.total)}">${eur(d.total)}</td><td style="color:${pc(d.avg)}">${eur(d.avg)}</td></tr>`).join('')+
    `</table></div>`;
  host.innerHTML=perf+risk+avm+dur;
}
fetch('/api/review/analytics').then(r=>r.json()).then(render).catch(e=>{
  document.getElementById('analytics').innerHTML='<div style="padding:30px;color:var(--short)">Load error: '+e.message+'</div>';});
"""

ANALYTICS_HTML = shell("/analytics", "Analytics", BODY, script=SCRIPT,
                       head_extra=_CSS, meta="how am I doing?")
