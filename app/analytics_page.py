"""LENS /analytics — performance dashboard you read in three seconds, not
one you read at all.

2026-09: THE READ (auto-generated prose paragraph + bullet insights) and the
two labeled-number stat-card grids are gone. The owner is dyslexic/ADHD and
was explicit: no paragraphs, no jargon labels he has to look up — everything
communicates through shape, color, size and position, with a number only as
a small secondary tag inside or beside the shape. The comment above each
builder function below is the design rationale for that encoding (why a bar
vs a gauge vs a diverging chart) — not a general changelog.

Equity curve (toggleable series) up top, then collapsible sections: when you
trade, how long you hold, the scorecard, excursions, cash flow — every one
now a bar/gauge/heat visual instead of a table of words. Data sources are
unchanged: /api/review/equity (curve + timing) and /api/review/analytics
(performance + risk + duration).

2026-09-05: /edge merged in as a "Research" area below the review sections —
Past (your live setup scorecard), Board (simulated strategy ranks), Backtest
(the runner + build-your-own) and Fit (the goal-constrained sweep), each a
collapsible `an-d` section like everything else on this page, not a second
mode switch. "How did I actually do" and "what could I test next" are one
scroll now. /edge 301s here (see main.py LEGACY_ROUTES); #past/#board/
#backtest/#fit keep working as anchors — see the hash-open snippet at the
top of SCRIPT below. Fit ships open by default: it's the one part of the old
Edge page the owner actually used day to day, everything else here starts
collapsed like the rest of the page.
"""

from .theme import shell

_CSS = """
<script src="/assets/lightweight-charts.js"></script>
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
.g{color:var(--long)} .r{color:var(--short)}
/* status line — replaces the old "THE READ" prose box for loading/empty/error.
   A caption, not a paragraph: one line, no styled card. */
#status{font-size:12px;color:var(--dim);padding:6px 2px 14px}
#status a{color:var(--accent)}
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

/* ── visual-encoding primitives (replace labeled-number stat cards) ────────
   Every metric below is a shape: a filled track (proportion / gauge), a
   diverging bar (signed value either side of a zero line), a dot strip
   (streaks/counts), or a heat cell (magnitude by color+size). The number
   is always printed INSIDE or immediately beside the shape — never alone. */
.vz-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.vz-card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:11px 13px;display:flex;flex-direction:column;gap:7px;min-width:0}
.vz-card.sp2{grid-column:span 2}
.vz-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vz-hero{font-family:var(--mono);font-weight:800;font-size:28px;line-height:1;display:flex;align-items:center;gap:7px}
.vz-hero .arrow{font-size:19px}
.vz-cap{font-family:var(--mono);font-size:9.5px;color:var(--faint)}
/* proportional fill: 0→100%, gradient-capable, tick = reference marker */
.vz-track{position:relative;height:22px;border-radius:6px;background:var(--bg);border:1px solid var(--line);overflow:hidden}
.vz-fill{position:absolute;top:0;bottom:0;left:0;border-radius:5px 0 0 5px;transition:width .2s}
.vz-fill-lbl{position:absolute;inset:0;display:flex;align-items:center;justify-content:flex-end;padding:0 8px;
  font-family:var(--mono);font-size:11px;font-weight:700;color:var(--ink);z-index:2}
.vz-tick{position:absolute;top:-1px;bottom:-1px;width:2px;background:var(--ink);opacity:.6;z-index:3}
/* diverging: signed value drawn from a center zero-line, color = sign */
.vz-div{position:relative;height:22px;background:var(--bg);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.vz-div .mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line2);z-index:1}
.vz-div .seg{position:absolute;top:1px;bottom:1px;border-radius:3px}
.vz-pair{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px}
/* thin diverging row, used for by-hour / by-weekday / duration charts */
.vz-hrow{display:grid;grid-template-columns:52px 1fr 62px;align-items:center;gap:8px;margin-bottom:3px}
.vz-hrow .lbl{font-family:var(--mono);font-size:10px;color:var(--dim);text-align:right;white-space:nowrap}
.vz-hrow .trk{position:relative;height:13px;background:var(--bg);border-radius:3px;overflow:hidden}
.vz-hrow .trk .mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line2)}
.vz-hrow .trk .seg{position:absolute;top:1px;bottom:1px;border-radius:2px}
.vz-hrow .val{font-family:var(--mono);font-size:10px;text-align:right}
.vz-hrow.best .lbl,.vz-hrow.worst .lbl{font-weight:700;color:var(--ink)}
/* dot strip — win/loss streaks, counts */
.vz-dots{display:flex;gap:3px;flex-wrap:wrap;align-items:center}
.vz-dots i{width:9px;height:9px;border-radius:50%;display:inline-block}
.vz-dots .gap{width:8px}
/* badge — a verdict word standing in for a paragraph */
.vz-badge{display:inline-block;font-family:var(--mono);font-weight:800;font-size:11px;letter-spacing:.06em;
  padding:3px 9px;border-radius:5px;border:1px solid currentColor}
/* funnel — deposits/withdrawals/fees as one bar with a balance marker */
.vz-funnel{position:relative;height:24px;border-radius:6px;overflow:hidden;border:1px solid var(--line)}
.vz-funnel .base{position:absolute;inset:0;background:var(--long-d)}
.vz-funnel .out{position:absolute;top:0;bottom:0;right:0;background:var(--short)}
.vz-funnel .now{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--ink)}
.vz-funnel .txt{position:absolute;inset:0;display:flex;align-items:center;padding:0 9px;
  font-family:var(--mono);font-size:11px;font-weight:700;color:var(--ink);z-index:2}
@media(max-width:560px){ .vz-card.sp2{grid-column:span 1} .vz-hrow{grid-template-columns:44px 1fr 54px} }

/* review surfaces (moved off /track) — untouched by the 2026-09 visual
   redesign above; these already communicate mostly through bars/dots. */
.rq-top{display:flex;align-items:center;gap:18px 26px;flex-wrap:wrap;margin-bottom:11px}
.rq-rate{display:flex;flex-direction:column;gap:3px;flex:0 0 auto}
.rq-rate b{font-family:var(--mono);font-size:34px;font-weight:800;line-height:1;
  color:var(--ink);font-variant-numeric:tabular-nums}
.rq-rate>span{font-family:var(--mono);font-size:9.5px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--dim)}
.rq-nums{display:flex;flex-wrap:wrap;gap:10px 24px;flex:1 1 240px}
.rq-nums>div{display:flex;flex-direction:column;gap:1px}
.rq-nums span{font-family:var(--mono);font-size:9.5px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--dim)}
.rq-nums b{font-family:var(--mono);font-size:16px;font-weight:700;color:var(--ink)}
.rq-rate.rq-ok b{color:var(--long)} .rq-rate.rq-mid b{color:var(--amber)}
.rq-rate.rq-bad b{color:var(--short)} .rq-rate.rq-na b{color:var(--dim)}
.rq-nums b.rq-bad{color:var(--short)}
.an-d>summary .tag.rq-ok{color:var(--long)} .an-d>summary .tag.rq-mid{color:var(--amber)}
.an-d>summary .tag.rq-bad{color:var(--short)} .an-d>summary .tag.rq-na{color:var(--dim)}
.rq-bar{height:8px;border-radius:999px;background:var(--bg);border:1px solid var(--line);
  overflow:hidden;margin-bottom:11px}
.rq-bar>span{display:block;height:100%;border-radius:999px;background:var(--accent)}
.rq-bar>span.rq-ok{background:var(--long)} .rq-bar>span.rq-mid{background:var(--amber)}
.rq-bar>span.rq-bad{background:var(--short)} .rq-bar>span.rq-na{background:var(--line2)}
.rq-p{font-size:12px;line-height:1.55;color:var(--dim);margin:0 0 9px;max-width:74ch}
.rq-p b{color:var(--ink)}
.rq-dim{color:var(--dim);font-size:11px}
.rq-warn{color:var(--amber)}

.rq-strip{display:flex;align-items:flex-end;gap:3px;height:46px;margin-bottom:9px}
.rq-c{flex:1 1 0;min-width:3px;height:var(--h);border-radius:2px;display:block;
  background:var(--line)}
.rq-c.kept{background:var(--long)} .rq-c.part{background:var(--accent);opacity:.55}
.rq-c.brk{background:var(--short)}
.rq-legend{display:flex;flex-wrap:wrap;gap:5px 15px;align-items:center;
  font-family:var(--mono);font-size:10px;color:var(--dim);margin-bottom:12px}
.rq-legend span{display:flex;align-items:center;gap:5px}
.rq-legend .rq-c{flex:none;width:9px}

/* The score table has five columns and two of them are numeric pairs, which is
   wider than a phone. It used to just overflow its panel — the numbers ran out
   past the border. It scrolls inside its own box now instead. */
.rq-tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin-bottom:4px}
.rq-tab{width:100%;min-width:440px;border-collapse:collapse;font-size:12px}
.rq-tab th{font-family:var(--mono);font-size:9px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);text-align:left;font-weight:400;
  padding:0 8px 7px 0;border-bottom:1px solid var(--line);white-space:nowrap}
.rq-tab td{padding:9px 8px 9px 0;border-bottom:1px solid var(--line);vertical-align:top}
.rq-tab tfoot td{border-bottom:none;padding-top:11px}
.rq-w{font-family:var(--mono);font-size:13px;font-weight:800;color:var(--accent);width:26px}
.rq-k{font-weight:600;color:var(--ink);white-space:nowrap}
.rq-what{color:var(--dim);line-height:1.5}
.rq-n{font-family:var(--mono);text-align:right;color:var(--dim);white-space:nowrap}
.rq-tot{color:var(--ink);font-weight:700}
.rq-tab th:nth-child(4),.rq-tab th:nth-child(5){text-align:right}
@media(max-width:620px){ .rq-rate b{font-size:28px} }
</style>
"""

BODY = """
<div id="status"></div>
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
// anchor from a bookmark/link — /edge#fit 301s to /analytics and the browser
// re-attaches the #fit fragment itself (no fragment on the redirect target),
// so this just has to open + reveal whichever Research section it names.
// Runs immediately: Past/Board/Backtest/Fit are static markup in the initial
// HTML, not injected after a fetch like the sections below.
(function(){
  const id=(location.hash||'').slice(1);
  if(!id) return;
  const el=document.getElementById(id);
  if(el && el.tagName==='DETAILS'){ el.open=true; setTimeout(()=>el.scrollIntoView({block:'start'}),0); }
})();
const eur=v=>v==null?'—':(v>=0?'+':'−')+'€'+Math.abs(v).toFixed(0);
const eur2=v=>v==null?'—':(v>=0?'+':'−')+'€'+Math.abs(v).toFixed(2);
const pc=v=>v>=0?'var(--long)':'var(--short)';
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let cumSeries=null, balSeries=null, coneSeries=[], CHART=null, CONE_END=0;

// era: fresh scoreboard since review.ERA_START by default; ?era=all = lifetime
const ERA=new URLSearchParams(location.search).get('era')||'current';

Promise.all([
  // book-scoped. Unscoped, this silently folded every prop attempt's trades into
  // the hedge P&L, win-rate and drawdown.
  fetch('/api/review/equity?book='+BOOK+'&era='+ERA).then(r=>r.json()),
  fetch('/api/review/analytics?book='+BOOK+'&era='+ERA).then(r=>r.json()),
  // cone + excursion are the HEDGE book only (the BTC-stack goal cone, hedge trade
  // geometry). On prop they'd be foreign data, so skip them — the panels self-hide.
  BOOK==='prop' ? Promise.resolve(null) : fetch('/api/cone').then(r=>r.json()).catch(()=>null),
  BOOK==='prop' ? Promise.resolve(null) : fetch('/api/excursion').then(r=>r.json()).catch(()=>null),
]).then(([E,A,C,X])=>{
  if(!E||!E.n){
    const hint=E&&E.era_start
      ?'No closed trades yet in the current era (since '+E.era_start+'). The old book is the baseline, not the scoreboard — <a href="?era=all">lifetime view</a>.'
      :'No closed trades yet.';
    document.getElementById('status').innerHTML=hint;return;}
  drawEquity(E);
  drawCone(C);
  renderSections(E,A,X);
}).catch(e=>{
  document.getElementById('status').innerHTML='<span style="color:var(--short)">Load error: '+e.message+'</span>';
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

  // AHEAD/BEHIND/OFF-PLAN as a colored word, not a sentence — the badge already
  // used to carry the meaning; the surrounding numbers are just its receipts.
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
// Baseline series (not a plain area) — it shades green above zero and red
// below zero on its own, so "ahead" / "behind" reads from the fill color
// without a caption. This is the single biggest signal on the page.
function drawEquity(d){
  const accent=cssv('--accent')||'#1fd989', dim=cssv('--dim')||'#7a8699', line=cssv('--line')||'#1c2430',
        long=cssv('--long')||'#1fd989', short=cssv('--short')||'#ff5468';
  const el=document.getElementById('eqchart');
  const chart=CHART=LightweightCharts.createChart(el,{
    width:el.clientWidth,height:300,
    layout:{background:{color:'transparent'},textColor:dim,fontFamily:cssv('--mono')||'monospace'},
    grid:{vertLines:{color:line},horzLines:{color:line}},
    rightPriceScale:{borderColor:line},timeScale:{borderColor:line,timeVisible:false},
    crosshair:{mode:0},
  });
  cumSeries=chart.addBaselineSeries({
    baseValue:{type:'price',price:0},
    topLineColor:long,topFillColor1:long+'44',topFillColor2:long+'05',
    bottomLineColor:short,bottomFillColor1:short+'05',bottomFillColor2:short+'33',
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

// ── visual-primitive builders ───────────────────────────────────────────────
// card(label, innerHTML, span2?) — the shared frame every metric sits in.
function vcard(lbl,inner,sp2){ return `<div class="vz-card${sp2?' sp2':''}"><div class="vz-lbl">${lbl}</div>${inner}</div>`; }

// fillBar — a proportion 0..100%. Used for win rate and profit factor. `tick`
// draws a thin reference marker (e.g. the model's number, or the 1.0×
// breakeven line) so "good vs. plan" is a bar-vs-marker comparison, not math.
function fillBar(pct,color,label,tick){
  const t=tick!=null?`<div class="vz-tick" style="left:${Math.max(0,Math.min(100,tick))}%"></div>`:'';
  return `<div class="vz-track"><div class="vz-fill" style="width:${Math.max(0,Math.min(100,pct))}%;background:${color}"></div>${t}<div class="vz-fill-lbl">${label}</div></div>`;
}

// divBar — a signed value drawn out from a center zero-line. Used everywhere
// a number can be win or lose: expectancy, Sharpe, by-hour/day/duration rows.
function divBar(val,maxAbs,label){
  const w=maxAbs>0?Math.min(50,Math.abs(val)/maxAbs*50):0, pos=val>=0;
  const seg=pos?`left:50%;width:${w}%;background:${cssv('--long')}`:`right:50%;width:${w}%;background:${cssv('--short')}`;
  return `<div class="vz-div"><div class="mid"></div><div class="seg" style="${seg}"></div></div>`+
    (label!=null?`<div class="vz-cap" style="text-align:${pos?'right':'left'};color:${pc(val)}">${label}</div>`:'');
}

// dots — a streak or small count as a row of colored dots, capped so a long
// streak reads as "a lot" by row length rather than forcing an exact count.
function dots(n,color,cap){ cap=cap||14; const k=Math.min(n,cap); let s=''; for(let i=0;i<k;i++) s+=`<i style="background:${color}"></i>`; if(n>cap) s+=`<span class="vz-cap" style="margin-left:3px">+${n-cap}</span>`; return s; }

// hrow — one line of a diverging bar chart (by-hour / by-weekday / duration).
// Replaces a table row: label, centered bar sized+colored by total P&L, value.
function hrow(label,total,maxAbs,cls){
  const w=maxAbs>0?Math.min(50,Math.abs(total)/maxAbs*50):0, pos=total>=0;
  const seg=pos?`left:50%;width:${w}%;background:${cssv('--long')}`:`right:50%;width:${w}%;background:${cssv('--short')}`;
  return `<div class="vz-hrow${cls?' '+cls:''}"><span class="lbl">${label}</span>`+
    `<div class="trk"><div class="mid"></div><div class="seg" style="${seg}"></div></div>`+
    `<span class="val" style="color:${pc(total)}">${eur(total)}</span></div>`;
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
  const hh=h=>String(h).padStart(2,'0')+':00';

  // ── When you trade — a diverging bar per hour and per weekday. Best/worst
  // get a bold label so the extremes still jump out inside the full chart. ──
  const hodsA=E.hod.filter(x=>x.n>=3), dowsA=E.dow.filter(x=>x.n>=3);
  const bH=hodsA.slice().sort((a,b)=>b.total-a.total)[0], wH=hodsA.slice().sort((a,b)=>a.total-b.total)[0];
  const bD=dowsA.slice().sort((a,b)=>b.total-a.total)[0], wD=dowsA.slice().sort((a,b)=>a.total-b.total)[0];
  const dmx=maxAbs(E.dow), hmx=maxAbs(E.hod);
  const dowRows=E.dow.filter(x=>x.n).map(x=>hrow(x.label,x.total,dmx,bD&&x===bD?'best':wD&&x===wD?'worst':'')).join('');
  const hodRows=E.hod.filter(x=>x.n).map(x=>hrow(hh(x.hour),x.total,hmx,bH&&x===bH?'best':wH&&x===wH?'worst':'')).join('');
  const P=E.periods;
  const perCard=(lbl,p)=>!p?'':vcard(lbl,`<div class="vz-hero" style="font-size:18px;color:${pc(p.avg)}">${eur2(p.avg)}</div>`+
    `<div class="vz-cap">best ${p.best?p.best.k+' '+eur(p.best.v):'—'} · worst ${p.worst?eur(p.worst.v):'—'}</div>`);
  const timingBody=
    `<div class="vz-row">${perCard('Avg / day',P.day)}${perCard('Avg / week',P.week)}${perCard('Avg / month',P.month)}</div>`+
    `<div class="an-h">By weekday <span style="color:var(--faint);text-transform:none;font-weight:400">— entry day, Bangkok</span></div>`+
    dowRows+
    `<div class="an-h" style="margin-top:14px">By hour <span style="color:var(--faint);text-transform:none;font-weight:400">— entry hour, Bangkok</span></div>`+
    hodRows;

  // ── How long you hold — same diverging chart, one bar per duration bucket.
  // A thin win/loss dot pair rides beside it so mix-of-outcomes shows without
  // a W/L column to read. ──
  const dur=A.duration||[];
  const dmax=maxAbs(dur);
  const durRows=dur.map(d=>{
    const hot=d.total>0&&d.n>=8;
    return `<div class="vz-hrow${hot?' best':''}"><span class="lbl">${d.label}</span>`+
      `<div class="trk"><div class="mid"></div><div class="seg" style="${d.total>=0?`left:50%;width:${dmax>0?Math.min(50,Math.abs(d.total)/dmax*50):0}%;background:var(--long)`:`right:50%;width:${dmax>0?Math.min(50,Math.abs(d.total)/dmax*50):0}%;background:var(--short)`}"></div></div>`+
      `<span class="val" style="color:${pc(d.total)}">${eur2(d.total)}</span></div>`+
      `<div class="vz-dots" style="margin:0 0 7px 60px">${dots(d.w,cssv('--long'),20)}<span class="gap"></span>${dots(d.l,cssv('--short'),20)}</div>`;
  }).join('');
  const durBody=durRows||'<div class="vz-cap">No closed trades yet.</div>';

  // ── Scorecard — one visual per metric, cut list applied. ──
  // Trades: context only (n= line), not a card — count alone isn't a signal.
  // Win Rate: gradient fill bar, tick = model win rate (was "Actual vs Model").
  // Net P&L: the hero — the one number allowed to be big, color+arrow do the
  //   telling. Expectancy: a small diverging mini-bar (same shape as by-hour).
  // Avg Win/Avg Loss/Actual R:R: one diverging bar, win right, loss left —
  //   the shape IS the R:R, the × is just a caption.
  // Profit Factor: fill bar capped at 3×, tick at 1.0 (breakeven line).
  // Fees: a thin bar sized against gross P&L movement — a cost, not a KPI,
  //   so it gets the smallest shape on the board.
  // Cut entirely: Avg Duration (the duration chart below already answers
  //   "how long", per-bucket, which this single average can't), Sortino
  //   (Sharpe already gives one risk-adjusted read; a second version of the
  //   same idea is exactly the jargon-pile the owner rejected), Cum Return /
  //   Ann Return / Calmar (the equity curve already tells the growth story —
  //   shading above/below zero IS the return; a duplicate % label teaches
  //   nothing new), and the separate "Actual vs Model" table (folded into
  //   the Win Rate tick mark instead).
  const wr=A.wr, wrColor=wr>=50?cssv('--long'):wr>=35?cssv('--amber'):cssv('--short');
  const winRateCard=vcard('Win Rate',
    fillBar(wr,wrColor,wr+'%',A.model_wr!=null?A.model_wr:null)+
    (A.model_wr!=null?`<div class="vz-cap">tick = model ${A.model_wr}%</div>`:''));
  const pnlCard=vcard('Net P&amp;L',
    `<div class="vz-hero" style="color:${pc(A.total_pnl)}"><span class="arrow">${A.total_pnl>=0?'▲':'▼'}</span>${eur2(A.total_pnl)}</div>`+
    `<div class="vz-cap">${A.n} trades${A.open?' · '+A.open+' open':''}</div>`,true);
  const expMax=Math.max(Math.abs(A.expectancy||0),A.avg_win||0,A.avg_loss||0,1);
  const expCard=vcard('Expectancy / trade',divBar(A.expectancy,expMax,eur2(A.expectancy)));
  const rr=A.rr!=null?A.rr+'×':'—';
  const wlMax=Math.max(A.avg_win||0,A.avg_loss||0,1);
  const wlCard=vcard('Avg Win vs Avg Loss <span class="vz-cap">'+rr+'</span>',
    `<div class="vz-div"><div class="mid"></div>`+
    `<div class="seg" style="right:50%;width:${Math.min(50,(A.avg_loss||0)/wlMax*50)}%;background:${cssv('--short')}"></div>`+
    `<div class="seg" style="left:50%;width:${Math.min(50,(A.avg_win||0)/wlMax*50)}%;background:${cssv('--long')}"></div></div>`+
    `<div class="vz-pair"><span style="color:var(--short)">${eur2(-(A.avg_loss||0))}</span><span style="color:var(--long)">${eur2(A.avg_win||0)}</span></div>`,true);
  const pf=A.profit_factor;
  const pfCard=pf==null?'':vcard('Profit Factor',
    fillBar(Math.min(pf,3)/3*100,pf>=1?cssv('--long'):cssv('--short'),pf+'×',1/3*100)+
    `<div class="vz-cap">tick = 1.0× breakeven</div>`);
  const grossMove=Math.abs(A.total_pnl||0)+(A.total_fees||0)+1;
  const feesCard=vcard('Fees',
    fillBar(Math.min(100,(A.total_fees||0)/grossMove*100),cssv('--short'),eur2(-(A.total_fees||0))));
  const sharpe=A.sharpe;
  const shMax=Math.max(Math.abs(sharpe||0),2,1);
  const shCard=sharpe==null?'':vcard('Sharpe',divBar(sharpe,shMax,sharpe.toFixed(2)));
  const ddPct=A.max_dd_pct, ddColor=cssv('--short');
  const ddCard=vcard('Max Drawdown',
    fillBar(Math.min(100,(ddPct||0)/50*100),ddColor,(ddPct!=null?ddPct+'%':eur2(-(A.max_dd_eur||0))))+
    `<div class="vz-cap">${eur2(-(A.max_dd_eur||0))} peak→trough</div>`);
  const streakCard=vcard('Streaks',
    `<div class="vz-dots">${dots(A.win_streak||0,cssv('--long'))}<span class="gap"></span>${dots(A.loss_streak||0,cssv('--short'))}</div>`+
    `<div class="vz-pair"><span style="color:var(--long)">W ${A.win_streak||0}</span><span style="color:var(--short)">L ${A.loss_streak||0}</span></div>`);
  const perf=`<div class="vz-row">${pnlCard}${winRateCard}${pfCard}${wlCard}${expCard}${shCard}${ddCard}${streakCard}${feesCard}</div>`;

  // ── Cash flow / eval spend — one bar: base = money in, red overlay = money
  // out, a marker = where the balance sits today. "Am I above or below what
  // I put in" is a marker-vs-bar-edge read, not four separate stat cards. ──
  let cashBody, cashTitle, cashSub, cashTag;
  if(E.prop_cash){
    const P=E.prop_cash;
    const total=Math.max(P.fees_total,1);
    const nowPct=E.cur_bal!=null?Math.min(100,Math.max(0,E.cur_bal/total*100)):null;
    const aRows=P.attempts.map(a=>`<div class="vz-hrow"><span class="lbl">${a.ts||'—'}</span>`+
      `<div class="trk"><div class="mid"></div><div class="seg" style="right:50%;width:${Math.min(50,(a.fee||0)/total*50)}%;background:${a.status==='live'?'var(--long)':'var(--short)'}"></div></div>`+
      `<span class="val" style="color:${a.status==='live'?'var(--long)':'var(--short)'}">−$${(a.fee||0).toFixed(0)}</span></div>`).join('');
    cashBody=
      `<div class="vz-funnel" style="margin-bottom:11px"><div class="base"></div>`+
      `<div class="out" style="width:100%;background:var(--short)"></div>`+
      (nowPct!=null?`<div class="now" style="left:${nowPct}%"></div>`:'')+
      `<div class="txt">$${P.fees_total.toFixed(0)} in fees${P.payouts?' · $'+P.payouts.toFixed(0)+' paid out':''}${E.cur_bal!=null?' · eval equity now $'+E.cur_bal.toFixed(0):''}</div></div>`+
      aRows;
    cashTitle='Eval spend'; cashSub='fees — the only real cash';
    cashTag='−$'+P.fees_total.toFixed(0);
  } else {
    const xf=E.transfers||[];
    const total=Math.max(E.deposits,1);
    const outPct=Math.min(100,(E.withdrawals||0)/total*100);
    const nowPct=E.cur_bal!=null?Math.min(100,Math.max(0,E.cur_bal/total*100)):null;
    const xfRows=xf.map(t=>{
      const w=Math.min(50,Math.abs(t.amount)/total*50);
      return `<div class="vz-hrow"><span class="lbl">${t.ts}</span>`+
        `<div class="trk"><div class="mid"></div><div class="seg" style="${t.amount>=0?`left:50%;width:${w}%;background:var(--long)`:`right:50%;width:${w}%;background:var(--short)`}"></div></div>`+
        `<span class="val" style="color:${pc(t.amount)}">${eur2(t.amount)}</span></div>`;
    }).join('');
    cashBody=
      `<div class="vz-funnel" style="margin-bottom:11px"><div class="base"></div>`+
      `<div class="out" style="width:${outPct}%"></div>`+
      (nowPct!=null?`<div class="now" style="left:${nowPct}%"></div>`:'')+
      `<div class="txt">€${E.deposits.toFixed(0)} in · €${E.withdrawals.toFixed(0)} out · net ${eur(E.net_deposit)}${E.cur_bal!=null?' · balance now €'+E.cur_bal.toFixed(0):''}</div></div>`+
      xfRows;
    cashTitle='Cash flow'; cashSub='every EUR deposit &amp; withdrawal';
    cashTag=eur(E.net_deposit)+' in';
  }

  // ── MAE / MFE — exits or selection? The verdict becomes a badge (like the
  // cone's AHEAD/BEHIND word) instead of a paragraph explaining terminology;
  // the reach ceiling becomes a fill bar against the breakeven tick. ──
  const pct=v=>v==null?'—':v.toFixed(0)+'%';
  let exBody='', exHead='', exCol='';
  if(X&&X.n){
    exHead=X.verdict.split(' — ')[0];
    exCol=(exHead.startsWith('SELECTION')||exHead.startsWith('EXITS'))?cssv('--short'):cssv('--dim');
    let reachBar='';
    if(X.reach){
      const starved=X.reach.badge==='STARVED';
      if(starved){ exHead='STARVED'; exCol=cssv('--short'); }
      const reachPct=100*X.reach.reach, needPct=100*X.reach.breakeven_wr;
      reachBar=vcard('Win-rate ceiling <span class="vz-badge" style="color:'+(starved?cssv('--short'):cssv('--long'))+'">'+X.reach.badge+'</span>',
        fillBar(reachPct,starved?cssv('--short'):cssv('--long'),reachPct.toFixed(0)+'%',needPct)+
        `<div class="vz-cap">tick = ${needPct.toFixed(0)}% needed to break even at ${X.reach.rr}R</div>`,true);
    }
    const capPct=X.median_capture_on_winners!=null?100*X.median_capture_on_winners:null;
    exBody=`<div class="vz-row">`+
      (reachBar||'')+
      vcard('Median MFE / MAE',divBar(X.median_mfe_pct,Math.max(X.median_mfe_pct||0,Math.abs(X.median_mae_pct||0),1),pct(X.median_mfe_pct))+
        divBar(-(X.median_mae_pct||0),Math.max(X.median_mfe_pct||0,Math.abs(X.median_mae_pct||0),1),pct(-(X.median_mae_pct||0))))+
      (capPct!=null?vcard('Capture on winners',fillBar(capPct,cssv('--long'),capPct.toFixed(0)+'%')):'')+
      vcard('Never reached TP',fillBar(X.pct_never_reached_tp,cssv('--short'),X.pct_never_reached_tp+'%',X.tp_pct))+
      vcard('Losers that touched TP',fillBar(X.pct_losers_that_touched_tp,cssv('--amber'),X.pct_losers_that_touched_tp+'%'))+
      `</div>`+
      `<div class="vz-cap">${X.n_5m} of ${X.n} trades at 5m resolution, rest at 1h.</div>`;
  }

  document.getElementById('sections').innerHTML=
    det('When you trade','timing edge — hours &amp; days',
        (bH?'best '+hh(bH.hour):'')+(bD?' · '+bD.label:''),
        'var(--long)',timingBody,true)+
    det('How long you hold','duration breakdown — where the edge lives','',
        '',durBody,false)+
    (exBody?det('Excursions','MAE / MFE — exits or selection?',exHead,exCol,exBody,false):'')+
    det('Scorecard','performance · risk',eur(A.total_pnl),pc(A.total_pnl),perf,false)+
    det(cashTitle,cashSub,cashTag,E.prop_cash?'var(--short)':pc(E.net_deposit),cashBody,false);
}
"""

# ─── review surfaces, moved off /track 2026-08-21 ──────────────────────
# Both answer "how have I been behaving", which is a review question. Track is
# read before an entry — the rung, the band, the next step — and these were
# sitting in front of that. They belong on the page you open when you want to
# look back, which is this one.
#
# Hedge-only: adherence and the daily score are both scoped to LENS_BOOK, so the
# prop view does not render them rather than showing hedge numbers under a prop
# heading.

def _grade(rate):
    """(class, word). Never colour alone — the word carries the same meaning."""
    if rate is None:
        return "na", "nothing to grade"
    if rate >= 0.70:
        return "ok", "following the engine"
    if rate >= 0.40:
        return "mid", "drifting off the engine"
    return "bad", "running off-engine"


def _day(iso):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime("%-d %b")
    except Exception:
        return str(iso or "—")


def _signal_quality(A):
    w, y = A["window"], A["yesterday"]
    cls, word = _grade(w["rate"])
    pct = "—" if w["rate"] is None else f"{w['rate'] * 100:.0f}%"
    bar = 0.0 if w["rate"] is None else max(0.0, min(1.0, w["rate"])) * 100
    yd = _day(A["yesterday_date"])
    ytxt = (f"Yesterday · {yd} — {y['fired']} fired, {y['fills']} "
            f"fill{'' if y['fills'] == 1 else 's'}, {y['orphan']} with no signal"
            if (y["fired"] or y["fills"])
            else f"Yesterday · {yd} — nothing fired, nothing filled")
    return f"""
<details class="an-d" id="a-signal">
  <summary>Signal quality<span class="sub"> · did the book take what the engine
    fired?</span><span class="tag rq-{cls}">{pct}</span></summary>
  <div class="an-d-body">
    <div class="rq-top">
      <div class="rq-rate rq-{cls}"><b>{pct}</b><span>on-signal</span></div>
      <div class="rq-nums">
        <div><span>signals fired</span><b>{w['fired']}</b></div>
        <div><span>fills</span><b>{w['fills']}</b></div>
        <div><span>no signal</span><b class="rq-bad">{w['orphan']}</b></div>
      </div>
    </div>
    <div class="rq-bar"><span class="rq-{cls}" style="width:{bar:.1f}%"></span></div>
    <p class="rq-p"><b>{word}</b> — {w['fills'] - w['orphan']} of {w['fills']} fills
       had an approved signal behind them. {ytxt}.</p>
    <p class="rq-p rq-dim">A fill counts as on-signal when a signal was approved,
       same direction, entry within tolerance. A signal left pending or expired
       never links, so a low rate can mean signals were never <em>decided</em> as
       much as never followed. Fills are the hedge book; signals have no book.</p>
  </div>
</details>"""


def _last_days(T):
    from .track import MAX_POINTS, WEIGHTS
    days, sc, S = T["days"], T["score"], T["streak"]
    cells = []
    for d in days:
        if d["breaches"]:
            cls, why = "brk", f"{d['breaches']} off-plan"
        elif d["kept"]:
            cls, why = "kept", "kept"
        elif d["trades"] or d["decisions"]:
            cls, why = "part", "partial"
        else:
            cls, why = "idle", "nothing logged"
        h = 18 + round(d["points"] / d["max_points"] * 26)
        bits = [d["date"], why, f"{d['points']:g}/{d['max_points']} pts"]
        if d["trades"]:
            bits.append(f"{d['trades']} trade{'s' if d['trades'] != 1 else ''}")
        if d["decisions"]:
            bits.append(f"{d['decisions']} decided")
        cells.append(f'<i class="rq-c {cls}" style="--h:{h}px" '
                     f'title="{" · ".join(bits)}"></i>')

    meta = [("discipline", "No trade flagged off-plan."),
            ("plan", "A trade taken that WAS the plan."),
            ("band", "Inside the projection band."),
            ("decision", "A signal approved or rejected.")]
    n = len(days) or 1
    rows = []
    for key, what in meta:
        hit = sum(1 for d in days if d["parts"][key] > 0)
        got = sum(d["parts"][key] for d in days)
        rows.append(f'<tr><td class="rq-w">{WEIGHTS[key]}</td><td class="rq-k">{key}</td>'
                    f'<td class="rq-what">{what}</td>'
                    f'<td class="rq-n">{hit}/{n} d</td>'
                    f'<td class="rq-n rq-tot">{got:g}/{WEIGHTS[key] * n:g}</td></tr>')

    unrev = ""
    if sc["unreviewed"]:
        unrev = (f'<p class="rq-p rq-warn">{sc["unreviewed"]} trade'
                 f'{"s" if sc["unreviewed"] != 1 else ""} in this window are unmarked, '
                 'so discipline is scoring silence rather than conduct.</p>')

    return f"""
<details class="an-d" id="a-days">
  <summary>The last {T['window_days']} days<span class="sub"> · daily discipline
    score</span><span class="tag">{S['current']}d streak</span></summary>
  <div class="an-d-body">
    <div class="rq-strip">{"".join(cells)}</div>
    <div class="rq-legend">
      <span><i class="rq-c kept" style="--h:10px"></i>kept</span>
      <span><i class="rq-c part" style="--h:10px"></i>partial</span>
      <span><i class="rq-c brk" style="--h:10px"></i>breach</span>
      <span><i class="rq-c idle" style="--h:10px"></i>nothing logged</span>
      <span class="rq-dim">bar height = points · best streak {S['best']}d</span>
    </div>
    <div class="rq-tw"><table class="rq-tab">
      <thead><tr><th>pts</th><th>component</th><th>earned when</th>
        <th>days</th><th>total</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
      <tfoot><tr><td class="rq-w">{MAX_POINTS}</td><td class="rq-k">score</td>
        <td class="rq-what">Streak needs discipline kept AND something logged.</td>
        <td class="rq-n">{sc['traded_days']}/{len(days)}</td>
        <td class="rq-n rq-tot">{sc['earned']:g}/{sc['possible']:g}</td></tr></tfoot>
    </table></div>
    {unrev}
  </div>
</details>"""


def _fold(title, sub, tag, tagcol, body, open_=False, id_=None) -> str:
    """Server-rendered twin of the JS `det()` builder above — same `an-d`
    markup, used for the Research sections below because their content is
    static HTML (client-side data fetches fill it in), not JS-injected like
    the equity-derived sections."""
    idattr = f' id="{id_}"' if id_ else ""
    openattr = " open" if open_ else ""
    subhtml = f' <span class="sub">{sub}</span>' if sub else ""
    taghtml = f'<span class="tag" style="color:{tagcol or "var(--dim)"}">{tag}</span>' if tag else ""
    return (f'<details class="an-d"{idattr}{openattr}><summary>{title}{subhtml}{taghtml}</summary>'
            f'<div class="an-d-body">{body}</div></details>')


def _research_section(book: str, bt_css: str, bt_body: str, bt_script: str):
    """Ex-/edge — Past / Board / Backtest / Fit — as four `an-d` sections
    instead of a second page with its own mode switch. Same three tenses of
    "which setups pay?" (past/board/backtest) plus the goal-constrained sweep
    (fit), now reachable by scrolling past the review sections rather than a
    page load. Returns (css, body, script) to fold into render()'s shell()."""
    from .edge_page import _CSS as ED_CSS, _BOARD_CSS, _LIVE, SCRIPT as ED_SCRIPT, _MODE_JS, _board
    from .fit_page import fragment as fit_fragment
    from .strategy_eval import load_cache

    fit_css, fit_body, fit_script = fit_fragment(book)
    fit_sub = "eval-constrained sweep" if book == "prop" else "goal-constrained sweep — what shape must the strategy be?"

    d = load_cache()
    if d:
        rl = d["r_levels"]
        gen = d["generated_at"][:16].replace("T", " ")
        ranked_n = len([o for o in d["results"] if not o["thin"]])
        board_body = (
            f'<div class="ed-hs">Same question, no you in it: each coded strategy run over the full '
            f'candle history ({d["span"][0]} → {d["span"][1]}), ranked by net R after {d["fee_pct"]}% '
            f'round-trip fees · first-touch at R = {rl[0]:g}–{rl[-1]:g} · refreshed {gen}. '
            f'Same engine and scoring for both books, different candidate sets: '
            f'<b>hedge</b> = 1h bar-context scalp setups, <b>prop</b> = the 4H/1H Asian-dip family. '
            f'<b>thin</b> = the pattern fired &lt;40× in the entire history — too few occurrences to '
            f'rank (samples can\'t be generated, only more history or a looser pattern creates them).</div>'
            f'<div class="ed-mode">'
            f'<button data-m="hedge">HEDGE</button><button data-m="prop">PROP</button></div>'
            f'<div class="pv">'
            f'<div id="board-hedge">{_board(d["results"], "hedge", rl)}</div>'
            f'<div id="board-prop" style="display:none">{_board(d["results"], "prop", rl)}</div>'
            f'<div class="panel"><h2>Read</h2><div class="prose">'
            f'Each cell is <strong>net R per trade</strong> at that target multiple — green = profitable '
            f'after fees. <strong>score</strong> sums the profitable cells weighted by R, so a strategy '
            f'that still pays at 3R outranks one that only pays at 1R. Top 3 are highlighted. '
            f'Mined in-sample; treat as a shortlist to forward-test, not a guarantee.</div></div>'
            f'</div>'
        )
        board_tag = f'{ranked_n} ranked'
        mode_script = _MODE_JS
    else:
        board_body = ('<div class="ed-hs">No rankings cached yet — run '
                      '<code>python3 -m app.strategy_eval</code>.</div>')
        board_tag = ""
        mode_script = ""

    sections = (
        _fold("Fit", fit_sub, "", "", fit_body, open_=True, id_="fit") +
        _fold("Backtest", "run &amp; build your own — locked, mechanical, no discretion", "", "",
              bt_body, open_=False, id_="backtest") +
        _fold("Board", "simulated — the coded rules replayed over the full candle history",
              board_tag, "var(--dim)", board_body, open_=False, id_="board") +
        _fold("Past", "your live trades — realised edge per setup family", "", "",
              _LIVE, open_=False, id_="past")
    )
    css = ED_CSS + _BOARD_CSS + fit_css + bt_css
    body = (
        '<div class="an-sec">'
        '<div class="an-h">Research — what could I test next?</div>'
        '<div class="rq-p" style="max-width:none">Live results, backtest ranks and the runner are three '
        'tenses of the same question — <b>which setups pay?</b> Same visual language as everything above, '
        'just prospective instead of retrospective.</div>'
        + sections +
        '</div>'
    )
    script = ED_SCRIPT + mode_script + fit_script + bt_script
    return css, body, script


def review_sections() -> str:
    """Both hedge review surfaces, or nothing if the ledger cannot answer."""
    try:
        from .track import track
        T = track()
    except Exception:
        return ""
    out = ""
    try:
        out += _signal_quality(T["adherence"])
    except Exception:
        pass
    try:
        out += _last_days(T)
    except Exception:
        pass
    return f'<div class="an-sec"><div class="an-h">Review</div>{out}</div>' if out else ""


def render(book: str = "hedge", bt_css: str = "", bt_body: str = "", bt_script: str = "") -> str:
    """One page, two books. 'prop' spans every eval attempt (see review.book_filter)
    — the current eval alone is /prop-ledger. bt_* = the backtest-runner fragment
    (built in main.py, embedded as the Research → Backtest section) — passed in
    the same way /edge used to take it, main.py's /analytics route builds it."""
    book = "prop" if book == "prop" else "hedge"
    other = "prop" if book == "hedge" else "hedge"
    path = "/prop-analytics" if book == "prop" else "/analytics"
    eval_cone = ('' if book != "prop"
                 else ' · <a href="/prop-survival#projection" class="ac">eval projection cone →</a>')
    body = (f'<div class="sub" style="color:var(--dim);font-size:12px;margin:-8px 0 14px">'
            f'<b>{book}</b> book{" · all eval attempts" if book == "prop" else ""} · '
            f'<a href="{"/analytics" if book == "prop" else "/prop-analytics"}" class="ac">'
            f'switch to {other}</a>{eval_cone}</div>') + BODY
    if book == "hedge":
        body += review_sections()
    research_css, research_body, research_script = _research_section(book, bt_css, bt_body, bt_script)
    body += research_body
    return shell(path, "Analytics", body,
                 script=f"const BOOK={book!r};\n".replace("'", '"') + SCRIPT + research_script,
                 head_extra=_CSS + research_css, meta="how am I doing?")


ANALYTICS_HTML = render("hedge")   # back-compat for importers
