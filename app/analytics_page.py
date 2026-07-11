"""LENS /analytics — performance dashboard that reads itself.

Leads with THE READ: a plain-language interpretation of the trade log + the one
iterative move the data argues for. Below it, an equity curve (toggleable series)
and collapsible sections grouped by question: when you trade, how long you hold,
the scorecard. Data from /api/review/equity (curve + timing) and
/api/review/analytics (performance + risk + duration).
"""

from .theme import shell

_CSS = """
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
.an-sec{margin-bottom:16px}
.an-h{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:0 0 9px;
  border-bottom:1px solid var(--line);padding-bottom:5px}
/* collapsible section — native <details>, summary is the header */
details.an-d{margin-bottom:16px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);overflow:hidden}
details.an-d>summary{list-style:none;cursor:pointer;padding:11px 13px;font-size:11px;font-weight:700;color:var(--dim);
  text-transform:uppercase;letter-spacing:.08em;display:flex;align-items:center;gap:8px;user-select:none}
details.an-d>summary::-webkit-details-marker{display:none}
details.an-d>summary::before{content:'▸';color:var(--faint);font-size:10px;transition:transform .15s}
details.an-d[open]>summary::before{transform:rotate(90deg)}
details.an-d>summary .sub{font-weight:400;text-transform:none;letter-spacing:0;color:var(--faint);font-size:10px}
details.an-d>summary .tag{margin-left:auto;font-family:var(--mono);font-size:11px;font-weight:700}
.an-d-body{padding:0 13px 13px}
.an-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:9px}
.an-card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.an-card .k{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.an-card .v{font-size:19px;font-weight:700;font-family:var(--mono)}
.an-card .s{font-size:9px;color:var(--faint);margin-top:2px}
.an-tbl{width:100%;border-collapse:collapse;font-size:12px}
.an-tbl th{text-align:right;color:var(--dim);font-weight:600;padding:5px 9px;border-bottom:1px solid var(--line);text-transform:uppercase;font-size:9px}
.an-tbl th:first-child,.an-tbl td:first-child{text-align:left}
.an-tbl td{text-align:right;padding:5px 9px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.an-tbl tr.hot td{background:rgba(31,217,137,.10)}
.g{color:var(--long)} .r{color:var(--short)}
/* THE READ */
.read{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:14px 16px;margin-bottom:18px}
.read h3{font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.1em;margin:0 0 10px}
.read .lede{font-size:14px;line-height:1.5;color:var(--ink);margin:0 0 10px}
.read ul{margin:0 0 12px;padding-left:18px}
.read li{font-size:12.5px;line-height:1.55;color:var(--dim);margin-bottom:3px}
.read li b{color:var(--ink);font-weight:600}
.read .move{background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:11px 13px}
.read .move .lbl{font-size:9px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px}
.read .move p{margin:0;font-size:13px;line-height:1.5;color:var(--ink)}
.read .pos{color:var(--long)} .read .neg{color:var(--short)}
/* equity chart */
.an-chart-wrap{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px 12px 6px}
#eqchart{height:300px;width:100%}
.an-tog{display:flex;gap:16px;font-size:11px;color:var(--dim);margin:2px 2px 8px;flex-wrap:wrap;align-items:center}
.an-tog label{display:inline-flex;align-items:center;gap:6px;cursor:pointer}
.an-tog .sw{display:inline-block;width:11px;height:3px;border-radius:2px}
.an-tog b{font-family:var(--mono);font-weight:700}
.an-rng{display:flex;gap:4px;margin-left:auto}
.an-rng button{padding:2px 9px;border:1px solid var(--line2);background:transparent;color:var(--dim);
  font-size:10px;border-radius:4px;cursor:pointer;font-family:var(--mono)}
.an-rng button.on{border-color:var(--accent);background:var(--accent);color:var(--bg);font-weight:700}
/* projection cone — the honesty surface */
.cone-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--dim);
  background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:7px 11px;margin:0 0 9px}
.cone-word{font-family:var(--mono);font-size:11px;font-weight:800;letter-spacing:.09em;padding:2px 7px;border-radius:4px}
.cone-word.AHEAD,.cone-word.ON{color:var(--long);border:1px solid var(--long)}
.cone-word.BEHIND{color:var(--amber);border:1px solid var(--amber)}
.cone-word.OFF-PLAN{color:var(--short);border:1px solid var(--short)}
.cone-bar .badge{font-family:var(--mono);font-size:10px;color:var(--faint)}
.cone-bar .badge.plan{color:var(--amber)}
.cone-bar .sp{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--faint)}
</style>
"""

BODY = """
<div id="read"></div>
<div class="an-sec">
  <div class="an-h">Equity Curve</div>
  <div id="cone-bar" style="display:none"></div>
  <div class="an-chart-wrap">
    <div class="an-tog">
      <label><input type="checkbox" id="t-cum" checked><span class="sw" style="background:var(--accent)"></span>Cumulative realised P&amp;L <b id="lg-cum">—</b></label>
      <label><input type="checkbox" id="t-bal" checked><span class="sw" style="background:var(--dim)"></span>Daily balance <b id="lg-bal">—</b></label>
      <label><input type="checkbox" id="t-cone" checked><span class="sw" style="background:var(--amber)"></span>Projection cone <b id="lg-cone">—</b></label>
      <div class="an-rng" id="rng">
        <button data-d="7">1W</button><button data-d="30">1M</button><button data-d="91">3M</button>
        <button data-d="182">6M</button><button data-d="ytd">YTD</button><button data-d="365">1Y</button>
        <button data-d="all" class="on">ALL</button>
      </div>
    </div>
    <div id="eqchart"></div>
  </div>
</div>
<div id="sections"><div style="padding:24px;color:var(--dim)">Loading…</div></div>
"""

SCRIPT = r"""
const eur=v=>v==null?'—':(v>=0?'+':'−')+'€'+Math.abs(v).toFixed(0);
const eur2=v=>v==null?'—':(v>=0?'+':'−')+'€'+Math.abs(v).toFixed(2);
const pc=v=>v>=0?'var(--long)':'var(--short)';
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let cumSeries=null, balSeries=null, coneSeries=[], CHART=null, CONE_END=0;

Promise.all([
  // book-scoped. Unscoped, this silently folded every prop attempt's trades into
  // the hedge P&L, win-rate and drawdown.
  fetch('/api/review/equity?book='+BOOK).then(r=>r.json()),
  fetch('/api/review/analytics?book='+BOOK).then(r=>r.json()),
  // cone + excursion are the HEDGE book only (the BTC-stack goal cone, hedge trade
  // geometry). On prop they'd be foreign data, so skip them — the panels self-hide.
  BOOK==='prop' ? Promise.resolve(null) : fetch('/api/cone').then(r=>r.json()).catch(()=>null),
  BOOK==='prop' ? Promise.resolve(null) : fetch('/api/excursion').then(r=>r.json()).catch(()=>null),
]).then(([E,A,C,X])=>{
  if(!E||!E.n){document.getElementById('read').innerHTML='<div class="read"><p class="lede">No closed trades yet.</p></div>';return;}
  drawEquity(E);
  drawCone(C);
  renderRead(E,A);
  renderSections(E,A,X);
}).catch(e=>{
  document.getElementById('read').innerHTML='<div class="read"><p class="lede" style="color:var(--short)">Load error: '+e.message+'</p></div>';
});

// ── projection cone (C3) — bands on the same cum-P&L axis as the equity curve ──
function drawCone(C){
  const box=document.getElementById('cone-bar');
  if(!C||!C.n||!CHART){ document.getElementById('t-cone').closest('label').style.display='none'; return; }
  const amber=cssv('--amber')||'#f6ad3c', faint=cssv('--faint')||'#4a5568';
  // P50 solid, the quartiles dashed, the P10/P90 tails dotted — spread reads as depth
  const spec=[['p90',faint,3],['p75',amber,2],['p50',amber,0],['p25',amber,2],['p10',faint,3]];
  coneSeries=spec.map(([k,color,style])=>{
    const s=CHART.addLineSeries({color,lineWidth:k==='p50'?2:1,lineStyle:style,
      priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false,
      priceFormat:{type:'price',precision:0,minMove:1}});
    s.setData(C.points.map(p=>({time:p.t,value:p[k]})));
    return s;
  });
  document.getElementById('t-cone').onchange=e=>coneSeries.forEach(s=>s.applyOptions({visible:e.target.checked}));
  document.getElementById('lg-cone').textContent=eur(C.now.p50)+' P50';
  CONE_END=C.points[C.points.length-1].t;

  const w=C.status, N=C.now;
  box.className='cone-bar'; box.style.display='';
  box.innerHTML=
    `<span class="cone-word ${w}">${w}</span>`+
    `<span>Realised <b style="color:var(--ink)">${eur2(N.cum)}</b> vs a P25–P75 band of `+
    `<b style="color:var(--ink)">${eur(N.p25)} … ${eur(N.p75)}</b> for today.</span>`+
    `<span class="badge ${C.source==='plan'?'plan':''}">${C.badge}</span>`+
    `<span class="sp">anchored ${C.anchor} · €${C.base_balance} base · ${C.paths} paths · `+
    `→ ${C.horizon} (${C.milestone})</span>`;
  CHART.timeScale().fitContent();   // the cone extends past the last trade
}

// ── equity chart ────────────────────────────────────────────────────────────
function drawEquity(d){
  const accent=cssv('--accent')||'#1fd989', dim=cssv('--dim')||'#7a8699', line=cssv('--line')||'#1c2430';
  const el=document.getElementById('eqchart');
  const chart=CHART=LightweightCharts.createChart(el,{
    width:el.clientWidth,height:300,
    layout:{background:{color:'transparent'},textColor:dim,fontFamily:cssv('--mono')||'monospace'},
    grid:{vertLines:{color:line},horzLines:{color:line}},
    rightPriceScale:{borderColor:line},timeScale:{borderColor:line,timeVisible:false},
    crosshair:{mode:0},
  });
  cumSeries=chart.addAreaSeries({lineColor:accent,topColor:accent+'44',bottomColor:accent+'05',
    lineWidth:2,priceLineVisible:false,priceFormat:{type:'price',precision:0,minMove:1}});
  cumSeries.setData(d.equity.map(p=>({time:p.t,value:p.cum})));
  if(d.daily&&d.daily.length){
    balSeries=chart.addLineSeries({color:dim,lineWidth:1,lineStyle:2,priceLineVisible:false,
      priceFormat:{type:'price',precision:0,minMove:1}});
    balSeries.setData(d.daily.map(p=>({time:p.t,value:p.bal})));
    document.getElementById('lg-bal').textContent='€'+d.daily[d.daily.length-1].bal.toFixed(0);
  }
  const lc=d.equity[d.equity.length-1].cum, lgc=document.getElementById('lg-cum');
  lgc.textContent=eur(lc); lgc.style.color=pc(lc);
  chart.timeScale().fitContent();
  new ResizeObserver(()=>chart.applyOptions({width:el.clientWidth})).observe(el);
  document.getElementById('t-cum').onchange=e=>cumSeries&&cumSeries.applyOptions({visible:e.target.checked});
  document.getElementById('t-bal').onchange=e=>balSeries&&balSeries.applyOptions({visible:e.target.checked});
  // range selector — last data point anchors the window; the cone's horizon
  // extends `to`, otherwise every range but ALL would clip the projection off
  const last=d.equity[d.equity.length-1].t;
  document.querySelectorAll('#rng button').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('#rng button').forEach(x=>x.classList.toggle('on',x===b));
    const v=b.dataset.d;
    if(v==='all'){chart.timeScale().fitContent();return;}
    const from=v==='ytd'?Date.UTC(new Date(last*1000).getUTCFullYear(),0,1)/1000:last-(+v)*86400;
    chart.timeScale().setVisibleRange({from,to:Math.max(last,CONE_END||0)});
  });
}

// ── THE READ — interpret the numbers ────────────────────────────────────────
function renderRead(E,A){
  const active=x=>x.n>=3;                       // ignore near-empty buckets
  const hods=E.hod.filter(active), dows=E.dow.filter(x=>x.n);
  const bestH=hods.slice().sort((a,b)=>b.total-a.total)[0];
  const worstH=hods.slice().sort((a,b)=>a.total-b.total)[0];
  const bestD=dows.slice().sort((a,b)=>b.total-a.total)[0];
  const worstD=dows.slice().sort((a,b)=>a.total-b.total)[0];
  const hh=h=>String(h).padStart(2,'0')+':00';
  // duration edge
  const dur=(A.duration||[]).filter(x=>x.n);
  const bleed=dur.filter(x=>x.total<0).sort((a,b)=>a.total-b.total);
  const carry=dur.filter(x=>x.total>0).sort((a,b)=>b.total-a.total);
  const worstDur=bleed[0], bestDur=carry[0];
  const bleedSum=bleed.reduce((s,x)=>s+x.total,0);

  // sober headline
  const dep=E.net_deposit, bal=E.cur_bal, cum=E.cum_pnl;
  let head;
  if(dep>0){
    const gone=Math.max(0,dep-bal), pct=Math.round(gone/dep*100);
    head=`You've deposited <b>€${E.deposits.toFixed(0)}</b> and withdrawn <b>€${E.withdrawals.toFixed(0)}</b> — `+
      `net <b>€${dep.toFixed(0)}</b> of real cash into this account. The balance today is <b>€${bal.toFixed(0)}</b> — `+
      `<span class="neg">~${pct}% of net funding is gone</span>. Realised P&L across ${A.n} closed trades is `+
      `<span class="neg">${eur2(cum)}</span>. This isn't noise; it's the strategy set not paying.`;
  } else {
    head=`Realised P&L across ${A.n} closed trades is <span class="${cum>=0?'pos':'neg'}">${eur2(cum)}</span>.`;
  }

  const li=[];
  if(bestH&&worstH) li.push(`<b>Hours matter most.</b> Your money is made entering around <b>${hh(bestH.hour)}</b> `+
    `(<span class="pos">${eur(bestH.total)}</span>) and lost around <b>${hh(worstH.hour)}</b> (<span class="neg">${eur(worstH.total)}</span>), Bangkok time.`);
  if(bestD&&worstD&&bestD.label!==worstD.label) li.push(`<b>${bestD.label}</b> is your best weekday `+
    `(<span class="pos">${eur(bestD.total)}</span>); <b>${worstD.label}</b> is the worst (<span class="neg">${eur(worstD.total)}</span>).`);
  if(worstDur&&bestDur) li.push(`<b>Hold time splits you.</b> <b>${worstDur.label}</b> trades bleed `+
    `(<span class="neg">${eur(worstDur.total)}</span>) while <b>${bestDur.label}</b> holds carry (<span class="pos">${eur(bestDur.total)}</span>).`);
  if(A.profit_factor!=null) li.push(`Profit factor <b>${A.profit_factor}</b> and expectancy <b class="${A.expectancy>=0?'pos':'neg'}">${eur2(A.expectancy)}/trade</b> — `+
    `${A.profit_factor>=1?'above':'below'} the line you need to grow.`);

  // THE MOVE — the single iterative test the data argues for
  let move;
  const greenHrs=hods.filter(x=>x.total>0).sort((a,b)=>b.total-a.total).slice(0,3).map(x=>hh(x.hour));
  if(bleedSum<-200 && greenHrs.length){
    move=`For the next 2 weeks, run a <b>subtraction test</b>: only take entries in your green windows `+
      `(<b>${greenHrs.join(', ')}</b>)`+
      (worstDur?` and stop closing in the <b>${worstDur.label}</b> band — either scratch faster or let it run past that`:'')+
      `. Skip <b>${worstD?worstD.label:'your worst day'}</b> entirely. Then reopen this page — if the curve flattens, the bleed was timing, not the market.`;
  } else {
    move=`The edge is thin but not negative everywhere. Concentrate size into your best hour (<b>${bestH?hh(bestH.hour):'—'}</b>) `+
      `and weekday (<b>${bestD?bestD.label:'—'}</b>), and treat everything else as sub-scale until it earns more trades.`;
  }

  document.getElementById('read').innerHTML=
    `<div class="read"><h3>The Read</h3>`+
    `<p class="lede">${head}</p>`+
    `<ul>${li.map(x=>`<li>${x}</li>`).join('')}</ul>`+
    `<div class="move"><div class="lbl">The move · one iterative test</div><p>${move}</p></div></div>`;
}

// ── collapsible sections ────────────────────────────────────────────────────
function det(title,sub,tag,tagcol,body,open){
  return `<details class="an-d"${open?' open':''}><summary>${title}`+
    (sub?` <span class="sub">${sub}</span>`:'')+
    (tag?`<span class="tag" style="color:${tagcol||'var(--dim)'}">${tag}</span>`:'')+
    `</summary><div class="an-d-body">${body}</div></details>`;
}
function renderSections(E,A,X){
  const maxAbs=arr=>Math.max(1,...arr.map(x=>Math.abs(x.total)));
  const bar=(v,mx)=>`<div style="height:4px;border-radius:2px;width:${Math.min(100,Math.abs(v)/mx*100)}%;background:${pc(v)};opacity:.7"></div>`;
  const card=(k,v,s,col)=>`<div class="an-card"><div class="k">${k}</div><div class="v" style="color:${col||'var(--ink)'}">${v}</div>${s?`<div class="s">${s}</div>`:''}</div>`;
  // when you trade — scoreboard first: best/worst hour & day (n>=3 so one fluke can't win)
  const hh=h=>String(h).padStart(2,'0')+':00';
  const hodsA=E.hod.filter(x=>x.n>=3), dowsA=E.dow.filter(x=>x.n>=3);
  const bH=hodsA.slice().sort((a,b)=>b.total-a.total)[0], wH=hodsA.slice().sort((a,b)=>a.total-b.total)[0];
  const bD=dowsA.slice().sort((a,b)=>b.total-a.total)[0], wD=dowsA.slice().sort((a,b)=>a.total-b.total)[0];
  const board=(bH?card('Best hour',hh(bH.hour),eur(bH.total)+' · '+bH.n+' trades','var(--long)'):'')+
    (wH?card('Worst hour',hh(wH.hour),eur(wH.total)+' · '+wH.n+' trades','var(--short)'):'')+
    (bD?card('Best day',bD.label,eur(bD.total)+' · '+bD.n+' trades','var(--long)'):'')+
    (wD?card('Worst day',wD.label,eur(wD.total)+' · '+wD.n+' trades','var(--short)'):'');
  const dmx=maxAbs(E.dow), hmx=maxAbs(E.hod);
  const dowRows=E.dow.filter(x=>x.n).map(x=>`<tr><td>${x.label}</td><td>${x.n}</td>
    <td style="color:${pc(x.total)}">${eur(x.total)}</td><td style="color:${pc(x.avg)}">${eur2(x.avg)}</td><td>${bar(x.total,dmx)}</td></tr>`).join('');
  const hodRows=E.hod.filter(x=>x.n).map(x=>`<tr><td>${String(x.hour).padStart(2,'0')}:00</td><td>${x.n}</td>
    <td style="color:${pc(x.total)}">${eur(x.total)}</td><td style="color:${pc(x.avg)}">${eur2(x.avg)}</td><td>${bar(x.total,hmx)}</td></tr>`).join('');
  const P=E.periods, perCard=(lbl,p)=>!p?'':`<div class="an-card"><div class="k">${lbl} · avg</div>`+
    `<div class="v" style="color:${pc(p.avg)}">${eur2(p.avg)}</div><div class="s">best ${p.best?p.best.k+' '+eur(p.best.v):'—'} · worst ${p.worst?eur(p.worst.v):'—'}</div></div>`;
  const timingBody=
    `<div class="an-grid" style="margin-bottom:14px">${board}</div>`+
    `<div class="an-grid" style="margin-bottom:14px">${perCard('Per day',P.day)}${perCard('Per week',P.week)}${perCard('Per month',P.month)}</div>`+
    `<div class="an-h">By weekday <span style="color:var(--faint);text-transform:none;font-weight:400">— entry day, Bangkok</span></div>`+
    `<table class="an-tbl"><tr><th>Day</th><th>Trades</th><th>Total</th><th>Avg</th><th style="width:30%">·</th></tr>${dowRows}</table>`+
    `<div class="an-h" style="margin-top:14px">By hour <span style="color:var(--faint);text-transform:none;font-weight:400">— entry hour, Bangkok</span></div>`+
    `<table class="an-tbl"><tr><th>Hour</th><th>Trades</th><th>Total</th><th>Avg</th><th style="width:30%">·</th></tr>${hodRows}</table>`;

  // how long you hold
  const dur=A.duration||[];
  const durRows=dur.map(d=>`<tr class="${d.total>0&&d.n>=8?'hot':''}"><td>${d.label}</td><td>${d.n}</td><td>${d.w}</td><td>${d.l}</td>
    <td style="color:${pc(d.total)}">${eur2(d.total)}</td><td style="color:${pc(d.avg)}">${eur2(d.avg)}</td></tr>`).join('');
  const durBody=`<table class="an-tbl"><tr><th>Duration</th><th>Count</th><th>W</th><th>L</th><th>Total P&L</th><th>Avg P&L</th></tr>${durRows}</table>`;

  // scorecard
  const perf=`<div class="an-grid">`+
    card('Trades',A.n,A.open?A.open+' open':'')+
    card('Win Rate',A.wr+'%',A.long_wr!=null?`L ${A.long_wr}% · S ${A.short_wr}%`:'')+
    card('Net P&L',eur2(A.total_pnl),'',pc(A.total_pnl))+
    card('Expectancy',eur2(A.expectancy),'per trade',pc(A.expectancy))+
    card('Avg Win',eur2(A.avg_win),'','var(--long)')+
    card('Avg Loss',eur2(-A.avg_loss),'','var(--short)')+
    card('Actual R:R',A.rr!=null?A.rr+'×':'—','')+
    card('Profit Factor',A.profit_factor!=null?A.profit_factor:'—','',A.profit_factor>=1?'var(--long)':'var(--short)')+
    card('Total Fees',eur2(-A.total_fees),'','var(--short)')+
    card('Avg Duration',A.avg_dur_h!=null?A.avg_dur_h+'h':'—','')+`</div>`;
  const dWR=A.wr-(A.model_wr||0), dRR=(A.rr||0)-(A.model_rr||0);
  const risk=`<div class="an-h" style="margin-top:14px">Risk-adjusted</div><div class="an-grid">`+
    card('Sharpe',A.sharpe,'per-trade · ann.',A.sharpe>=0?'var(--long)':'var(--short)')+
    card('Sortino',A.sortino,'',A.sortino>=0?'var(--long)':'var(--short)')+
    card('Max DD',eur2(-A.max_dd_eur)+(A.max_dd_pct!=null?` · ${A.max_dd_pct}%`:''),'peak→trough','var(--short)')+
    card('Win Streak',A.win_streak,'','var(--long)')+
    card('Loss Streak',A.loss_streak,'','var(--short)')+
    (A.cum_return!=null?card('Cum Return',A.cum_return+'%','',pc(A.cum_return)):card('Cum Return','—','set capital base'))+
    (A.ann_return!=null?card('Ann Return',A.ann_return+'%','',pc(A.ann_return)):'')+
    (A.calmar!=null?card('Calmar',A.calmar,''):'')+`</div>`;
  const avm=`<div class="an-h" style="margin-top:14px">Actual vs Model</div><table class="an-tbl">
    <tr><th>Metric</th><th>Model</th><th>Actual</th><th>Δ</th></tr>
    <tr><td>Win Rate</td><td>${A.model_wr!=null?A.model_wr+'%':'—'}</td><td>${A.wr}%</td><td style="color:${pc(dWR)}">${dWR>=0?'+':''}${dWR.toFixed(1)}</td></tr>
    <tr><td>R:R</td><td>${A.model_rr!=null?A.model_rr+'×':'—'}</td><td>${A.rr!=null?A.rr+'×':'—'}</td><td style="color:${pc(dRR)}">${dRR>=0?'+':''}${dRR.toFixed(2)}</td></tr></table>`;

  // cash flow — every EUR deposit/withdrawal, the "what did I actually put in" ledger
  const xf=E.transfers||[];
  const xfRows=xf.map(t=>`<tr><td>${t.ts}</td><td>${t.type}</td>
    <td style="color:${pc(t.amount)}">${eur2(t.amount)}</td></tr>`).join('');
  const nDep=xf.filter(t=>t.amount>0).length, nWd=xf.filter(t=>t.amount<0).length;
  const cashBody=
    `<div class="an-grid" style="margin-bottom:14px">`+
    card('Deposited',eur(E.deposits),nDep+' deposits','var(--long)')+
    card('Withdrawn',eur(-E.withdrawals),nWd+' withdrawals','var(--short)')+
    card('Net funded',eur(E.net_deposit),'deposits − withdrawals',pc(E.net_deposit))+
    (E.cur_bal!=null?card('Balance now','€'+E.cur_bal.toFixed(0),'','var(--ink)'):'')+`</div>`+
    `<table class="an-tbl"><tr><th>Date</th><th>Type</th><th>Amount</th></tr>${xfRows}</table>`;

  // ── MAE / MFE — exits or selection? ──
  const pct=v=>v==null?'—':v.toFixed(2)+'%';
  let exBody='', exHead='', exCol='';
  if(X&&X.n){
    const sel=X.verdict.startsWith('SELECTION'), exi=X.verdict.startsWith('EXITS');
    exHead=X.verdict.split(' — ')[0]; exCol=sel||exi?'var(--short)':'var(--dim)';
    exBody=`<div class="an-grid">`+
      card('Median MFE',pct(X.median_mfe_pct),'best move offered','var(--long)')+
      card('Median MAE',pct(X.median_mae_pct),'worst heat taken','var(--short)')+
      card('Capture on winners',X.median_capture_on_winners!=null?(100*X.median_capture_on_winners).toFixed(0)+'%':'—','of the best move banked','var(--long)')+
      card('MFE on losers',pct(X.median_mfe_on_losers_pct),'how far losers ran your way','var(--short)')+
      card('Never reached TP',X.pct_never_reached_tp+'%','of all trades, vs '+X.tp_pct+'% target','var(--short)')+
      card('Losers that touched TP',X.pct_losers_that_touched_tp+'%','giveback rate','var(--dim)')+
      `</div>`+
      (X.reach?`<p class="s" style="margin-top:10px;line-height:1.5">`+
        `<b style="color:${X.reach.badge==='STARVED'?'var(--short)':'var(--long)'}">`+
        `${X.reach.badge} — win-rate ceiling ${(100*X.reach.reach).toFixed(0)}% `+
        `vs ${(100*X.reach.breakeven_wr).toFixed(0)}% needed to break even</b><br>`+
        `<span style="color:var(--dim)">At the live ${X.tp_pct}% TP / ${X.sl_pct}% SL `+
        `(${X.reach.rr}R), only ${X.reach.hit} of ${X.reach.n} fills ever travelled far `+
        `enough to win — and that ignores whether the stop was hit first, so the true `+
        `ceiling is lower. Fees push breakeven to ${(100*X.reach.breakeven_wr).toFixed(0)}%. `+
        `A ceiling under the breakeven line means no amount of entry skill makes this `+
        `geometry pay.</span></p>`:'')+
      `<p class="s" style="margin-top:10px;color:var(--dim);line-height:1.5">`+
      `<b style="color:${exCol}">${X.verdict}</b><br>`+
      `Capture is the fraction of the best available move banked on trades that worked; `+
      `it is meaningless on losers, so it is measured on winners only. Excursions are `+
      `percent of entry, not R — no trade in the ledger carries a stop, so there is no `+
      `risk denominator to divide by. ${X.n_5m} of ${X.n} trades measured at 5m resolution, `+
      `the rest at 1h.</p>`;
  }

  document.getElementById('sections').innerHTML=
    det('When you trade','timing edge — hours &amp; days',
        (bH?'best '+hh(bH.hour):'')+(bD?' · '+bD.label:''),
        'var(--long)',timingBody,true)+
    det('How long you hold','duration breakdown — where the edge lives','',
        '',durBody,false)+
    (exBody?det('Excursions','MAE / MFE — exits or selection?',exHead,exCol,exBody,false):'')+
    det('Scorecard','performance · risk · vs model',eur(A.total_pnl),pc(A.total_pnl),perf+risk+avm,false)+
    det('Cash flow','every EUR deposit &amp; withdrawal',eur(E.net_deposit)+' in',pc(E.net_deposit),cashBody,false);
}
"""

def render(book: str = "hedge") -> str:
    """One page, two books. 'prop' spans every eval attempt (see review.book_filter)
    — the current eval alone is /prop-ledger."""
    book = "prop" if book == "prop" else "hedge"
    other = "prop" if book == "hedge" else "hedge"
    path = "/prop-analytics" if book == "prop" else "/analytics"
    eval_cone = ('' if book != "prop"
                 else ' · <a href="/prop-goal" class="ac">eval projection cone → /prop-goal</a>')
    body = (f'<div class="sub" style="color:var(--dim);font-size:12px;margin:-8px 0 14px">'
            f'<b>{book}</b> book{" · all eval attempts" if book == "prop" else ""} · '
            f'<a href="{"/analytics" if book == "prop" else "/prop-analytics"}" class="ac">'
            f'switch to {other}</a>{eval_cone}</div>') + BODY
    return shell(path, "Analytics", body,
                 script=f"const BOOK={book!r};\n".replace("'", '"') + SCRIPT,
                 head_extra=_CSS, meta="how am I doing?")


ANALYTICS_HTML = render("hedge")   # back-compat for importers
