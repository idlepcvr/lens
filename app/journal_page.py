"""LENS /journal — the trade Log.

Modular-journal best practice: this page is the LOG (capture + chronological
history), not analysis. A dense, spreadsheet-style table — charts-free — with a
compact filter bar and inline setup tagging. Click any row to open the big
trade modal (chart + breakdown + entry context + full review). Analytics live
on /analytics, the setup scoreboard on /edge.
"""

from .theme import shell

_CSS = """
<style>
.jr-bar{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;margin-bottom:12px}
.jr-bar select{background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:4px 8px;font-size:12px;font-family:var(--mono);cursor:pointer}
.jseg{display:flex;align-items:center;gap:3px}
.jseg b{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-right:2px}
.jseg button{padding:3px 9px;border:1px solid var(--line);background:transparent;color:var(--dim);font-size:11px;border-radius:5px;cursor:pointer;font-family:var(--mono)}
.jseg button.on{border-color:var(--accent);background:var(--accent);color:var(--bg);font-weight:700}
.jr-spacer{flex:1}
.jr-stat{font-size:11px;color:var(--dim);font-family:var(--mono)}
.jr-stat b{color:var(--ink)}
.jr-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:9px}
table.jr{width:100%;border-collapse:collapse;font-size:12px;min-width:760px}
table.jr th{position:sticky;top:0;background:var(--panel2);text-align:right;color:var(--dim);font-weight:600;
  font-size:9px;text-transform:uppercase;letter-spacing:.05em;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap;z-index:2}
table.jr th:first-child,table.jr td:first-child{text-align:left}
table.jr td{text-align:right;padding:6px 9px;border-bottom:1px solid var(--line);font-family:var(--mono);white-space:nowrap}
table.jr tbody tr{cursor:pointer}
table.jr tbody tr:hover{background:var(--panel2)}
.jr td.l{text-align:left}
.jr .dir-l{color:var(--long);font-weight:700}.jr .dir-s{color:var(--short);font-weight:700}
.jr .g{color:var(--long)}.jr .r{color:var(--short)}.jr .amb{color:var(--amber)}.jr .dim{color:var(--dim)}
.jr select.tagsel{background:var(--panel);border:1px solid var(--line);color:var(--ink);border-radius:4px;font-size:10px;font-family:var(--mono);padding:1px 3px;max-width:118px}
.jr .flag{display:inline-block;font-size:9px;padding:0 4px;border-radius:3px;border:1px solid var(--line2);margin-left:3px;color:var(--dim)}
.jr .flag.gr{border-color:var(--amber);color:var(--amber)}
.jr .flag.ms{border-color:var(--short);color:var(--short)}
table.jr thead th[data-k]{cursor:pointer;user-select:none}
table.jr thead th[data-k]:hover{color:var(--ink)}
table.jr thead th.sa::after{content:' ▲';font-size:7px;color:var(--accent)}
table.jr thead th.sd::after{content:' ▼';font-size:7px;color:var(--accent)}
.jr .bk{font-size:8px;font-weight:700;padding:1px 4px;border-radius:3px;border:1px solid var(--line2);letter-spacing:.03em}
.jr .bk.hedge{color:var(--accent);border-color:var(--accent)}
.jr .bk.prop{color:var(--amber);border-color:var(--amber)}
.jr .flag.auto{opacity:.95}
.jr .flag.auto.gA,.jr .flag.auto.gB{border-color:var(--long);color:var(--long)}
.jr .flag.auto.gC{border-color:var(--amber);color:var(--amber)}
.jr .flag.auto.gD,.jr .flag.auto.gF{border-color:var(--short);color:var(--short)}
.rv-badge{font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;margin-left:6px;letter-spacing:.03em}
.rv-badge.man{color:var(--long);border:1px solid var(--long)}
.rv-badge.auto{color:var(--amber);border:1px solid var(--amber)}
.auto-take{font-size:12px;color:var(--ink);background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--amber);border-radius:6px;padding:8px 11px;margin-bottom:6px;line-height:1.5}

/* big trade modal */
.bm-bg{position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.66);backdrop-filter:blur(3px);display:none;align-items:center;justify-content:center;padding:18px}
.bm-bg.open{display:flex}
.bm{width:min(1040px,96vw);max-height:92vh;overflow-y:auto;background:var(--panel);border:1px solid var(--line2);border-radius:12px;padding:16px 18px;box-shadow:0 24px 70px rgba(0,0,0,.6)}
.bm.long{border-left:4px solid var(--long)}.bm.short{border-left:4px solid var(--short)}
.bm-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.bm-t{font-size:16px;font-weight:700;font-family:var(--mono)}
.bm-x{font-size:18px;color:var(--dim);background:none;border:none;cursor:pointer}
#bm-chart{height:44vh;min-height:240px;border:1px solid var(--line);border-radius:8px;margin-bottom:12px}
.bm-cols{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:6px}
.bm-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px 14px;align-content:start}
.bm-fld .k{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:1px}
.bm-fld .v{font-size:12.5px;font-family:var(--mono);font-weight:600}
.bm-fld input{width:100%;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:4px 6px;color:var(--ink);font-size:12px;font-family:var(--mono);outline:none}
.bm-sec{font-size:10px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:14px 0 7px;border-bottom:1px solid var(--line);padding-bottom:4px}
.pickrow{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:8px}
.pickrow .pl{font-size:11px;color:var(--dim);width:100px;flex:0 0 auto}
.opt{padding:3px 9px;border-radius:5px;border:1px solid var(--line);font-size:11px;cursor:pointer;background:transparent;color:var(--dim);font-family:var(--mono)}
.opt.on{border-color:var(--accent);background:var(--accent);color:var(--bg);font-weight:700}
.opt.grade.on{border-color:var(--amber);background:transparent;color:var(--amber)}
.opt.miss.on{border-color:var(--short);background:rgba(255,84,104,.14);color:var(--short)}
.refl{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin-bottom:8px}
.refl textarea,#bm-notes{width:100%;min-height:46px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:5px 7px;color:var(--ink);font-size:12px;font-family:var(--mono);resize:vertical;outline:none}
.bm-save{margin-top:12px;padding:9px 18px;border:none;border-radius:6px;background:var(--accent);color:var(--bg);font-size:12px;font-weight:700;cursor:pointer}
.cols-cond{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-content:start}

@media(max-width:640px){
  .bm-cols{grid-template-columns:1fr}.bm-grid{grid-template-columns:repeat(2,1fr)}
  .refl{grid-template-columns:1fr}.bm{width:96vw;padding:14px}#bm-chart{height:36vh}
}
/* live open positions — detailed cards */
.op-wrap{margin-bottom:16px}
.op-hd{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.op-hd b{font-size:11px;letter-spacing:.04em;color:var(--ink)}
.op-hd .live{font-size:8px;text-transform:uppercase;letter-spacing:.1em;color:var(--long);border:1px solid var(--long);border-radius:4px;padding:1px 5px}
.opcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:10px}
.opcard{border:1px solid var(--line);border-radius:10px;background:var(--panel);overflow:hidden}
.opcard.long{border-left:3px solid var(--long)}.opcard.short{border-left:3px solid var(--short)}
.opcard .top{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border-bottom:1px solid var(--line);background:var(--panel2)}
.opcard .ven{font-size:8.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim)}
.opcard .mkt{font-size:13.5px;font-weight:700;color:var(--ink);font-family:var(--mono)}
.opcard .sd{font-size:10.5px;font-weight:700;font-family:var(--mono)}
.opcard .body{padding:7px 12px 11px}
.oprow{display:grid;grid-template-columns:auto 1fr;gap:8px;padding:2.5px 0;font-size:11.5px;align-items:baseline}
.oprow .l{color:var(--dim)}.oprow .v{font-family:var(--mono);color:var(--ink);text-align:right}
.oprow .v small{color:var(--dim);font-size:10px}
.opsec{font-size:8.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--faint);margin:9px 0 3px;border-top:1px solid var(--line);padding-top:8px}
.opcard .g{color:var(--long)}.opcard .r{color:var(--short)}.opcard .dim{color:var(--dim)}
</style>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
"""

BODY = """
<div class="jr-bar">
  <select id="f-tag" onchange="applyF()"><option value="">All setups</option><option value="__none__">Untagged</option></select>
  <div class="jseg" data-k="dir"><b>Dir</b><button data-v="" class="on">All</button><button data-v="long">Long</button><button data-v="short">Short</button></div>
  <div class="jseg" data-k="result"><b>Res</b><button data-v="" class="on">All</button><button data-v="win">Win</button><button data-v="loss">Loss</button></div>
  <div class="jseg" data-k="rsi"><b>RSI</b><button data-v="" class="on">All</button><button data-v="dip">Dip</button><button data-v="momentum">Mom</button><button data-v="neutral">Neut</button></div>
  <div class="jseg" data-k="book"><b>Book</b><button data-v="" class="on">All</button><button data-v="hedge">Hedge</button><button data-v="prop">Prop</button></div>
  <div class="jseg" data-k="match"><b>Match</b><button data-v="" class="on">All</button><button data-v="1">⇄ Merged</button></div>
  <div class="jseg" data-k="rev"><b>Review</b><button data-v="" class="on">All</button><button data-v="manual">✍️ Mine</button><button data-v="auto">🤖 Auto</button></div>
  <div class="jr-spacer"></div>
  <button id="jr-sync" onclick="syncKraken()" style="padding:4px 11px;border:1px solid var(--accent);background:transparent;color:var(--accent);font-size:11px;border-radius:5px;cursor:pointer;font-family:var(--mono)">⟳ Sync Kraken</button>
  <div class="jr-stat" id="jr-stat">—</div>
</div>
<div id="open-pos"></div>
<div class="jr-wrap">
  <table class="jr">
    <thead><tr>
      <th data-k="opened_at">Date</th><th data-k="direction">Dir</th><th data-k="book">Book</th><th data-k="symbol">Sym</th><th data-k="entry">Entry</th><th data-k="exit">Exit</th><th data-k="pnl">P&L</th><th data-k="fees">Fees</th><th data-k="leverage">Lev</th><th data-k="R">R</th><th data-k="dur">Dur</th><th>Setup</th><th>Review</th>
    </tr></thead>
    <tbody id="jr-body"><tr><td colspan="13" class="dim l" style="padding:20px">Loading…</td></tr></tbody>
  </table>
</div>
<div id="modal"></div>
"""

SCRIPT = r"""
const MISTAKES=["chased","early","late","oversized","moved stop","no stop","revenge","FOMO","overheld","cut early","no setup"];
const EMOTIONS=["calm","FOMO","tilt","fear","greed","bored"];
const GRADES=["A","B","C","D","F"];
const SETUPS=["S1","S2","S3","S4","S5","NONE"];
let TRADES=[], CANDLES=[], VISIBLE=[], SEL=null;
const F={dir:'',result:'',rsi:'',book:'',match:'',rev:''};
let SORT={k:'opened_at',dir:-1}, GOALLVL=null;
const $=id=>document.getElementById(id);
const eur=(v,d=2)=>v==null?'—':(v<0?'-':'+')+'€'+Math.abs(v).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});
const usd=(v)=>v==null?'—':'$'+Number(v).toLocaleString('en',{maximumFractionDigits:0});

async function goalLevels(){
  // expected TP/SL move % from the Goal model (config-driven), overlaid on live positions
  try{
    const cfg=await fetch('/api/config').then(r=>r.json());
    const g=await fetch('/api/goal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)}).then(r=>r.json());
    if(g&&g.underlying_win_pct!=null) return {tp:g.underlying_win_pct/100, sl:g.underlying_loss_pct/100, rr:g.actual_rr};
  }catch(e){}
  return null;
}
async function loadOpenPositions(){
  const el=document.getElementById('open-pos');
  try{
    const [d,lvl]=await Promise.all([fetch('/api/positions/live').then(r=>r.json()), goalLevels()]);
    const ps=d.positions||[];
    if(!ps.length){ el.innerHTML=''; return; }
    const usd=(v,d=2)=>v==null?'—':'$'+Number(v).toLocaleString('en',{maximumFractionDigits:d});
    const eu=(v)=>v==null?'—':(v<0?'-':'')+'€'+Math.abs(v).toLocaleString('en',{maximumFractionDigits:2});
    const sUsd=(v)=>v==null?'—':(v>=0?'+':'-')+'$'+Math.abs(v).toLocaleString('en',{maximumFractionDigits:2});
    const pc=(v)=>v==null?'—':(v>=0?'+':'')+Number(v).toFixed(2)+'%';
    const row=(l,v,c)=>`<div class="oprow"><span class="l">${l}</span><span class="v ${c||''}">${v}</span></div>`;
    const cards=ps.map(p=>{
      const isL=p.direction==='long', up=p.upnl_usd||0;
      let plan='';
      if(lvl){
        const tp=isL?p.entry*(1+lvl.tp):p.entry*(1-lvl.tp);
        const sl=isL?p.entry*(1-lvl.sl):p.entry*(1+lvl.sl);
        const win=(p.cost_usd||0)*lvl.tp, loss=(p.cost_usd||0)*lvl.sl;
        plan=`<div class="opsec">Plan — from Goal</div>`
          +row('Take profit',`${usd(tp,1)} <small>+${(lvl.tp*100).toFixed(1)}%</small>`,'g')
          +row('Stop loss',`${usd(sl,1)} <small>-${(lvl.sl*100).toFixed(1)}%</small>`,'r')
          +row('Expected win',`${sUsd(win)} <small>${pc(lvl.tp*100)}</small>`,'g')
          +row('Expected loss',`${sUsd(-loss)} <small>${pc(-lvl.sl*100)}</small>`,'r')
          +row('R:R',lvl.rr!=null?lvl.rr.toFixed(2):(lvl.tp/lvl.sl).toFixed(2),'dim');
      } else { plan=`<div class="opsec">Plan</div>`+row('levels','set Goal config to see plan','dim'); }
      return `<div class="opcard ${isL?'long':'short'}">
        <div class="top"><div><div class="ven">${p.venue}</div><div class="mkt">${p.symbol}</div></div>
          <div class="sd ${isL?'g':'r'}">${isL?'▲ LONG':'▼ SHORT'} · ${p.leverage}×</div></div>
        <div class="body">
          ${row('Opening price',usd(p.entry))}
          ${row('Last price',`${usd(p.mark)} <small>move ${pc(p.move_pct)}</small>`,(p.move_pct||0)>=0?'g':'r')}
          ${row('Base qty',p.size+' ₿')}
          ${row('Quote qty',usd(p.quote_qty))}
          ${row('Value',`${eu(p.value_eur)} <small>${usd(p.quote_qty)}</small>`)}
          ${row('Initial margin',`${usd(p.margin_usd)} <small>${eu(p.margin_eur)}</small>`)}
          ${row('Unrealised P&L',`${sUsd(up)} <small>${eu(p.upnl_eur)} · ${pc(p.upnl_pct)}</small>`,up>=0?'g':'r')}
          ${row('RoE',pc(p.roe_pct),(p.roe_pct||0)>=0?'g':'r')}
          ${row('Est. liquidation',usd(p.liquidation),'r')}
          ${row('Funding',p.funding!=null?p.funding.toFixed(4):'—','dim')}
          ${plan}
        </div></div>`;
    }).join('');
    el.innerHTML=`<div class="op-wrap"><div class="op-hd"><b>Open positions</b><span class="live">● live</span><span class="dim" style="font-size:10px">live from Kraken · drops into the log once closed</span></div><div class="opcards">${cards}</div></div>`;
  }catch(e){ el.innerHTML=''; }
}
async function load(){
  loadOpenPositions();
  GOALLVL=await goalLevels();
  const [tr,ca]=await Promise.all([fetch('/api/review/trades'),fetch('/api/review/ohlcv')]);
  TRADES=(await tr.json()).filter(t=>t.pnl!=null);
  computeAutoGrades();
  try{CANDLES=await ca.json();}catch(e){CANDLES=[];}
  const tagsel=$('f-tag'); [...new Set(TRADES.map(t=>t.setup_tag).filter(Boolean))].sort().forEach(tg=>{
    const o=document.createElement('option'); o.value=o.textContent=tg; tagsel.appendChild(o);});
  document.querySelectorAll('.jseg').forEach(seg=>seg.querySelectorAll('button').forEach(b=>b.onclick=()=>{
    F[seg.dataset.k]=b.dataset.v; seg.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b)); applyF();}));
  document.querySelectorAll('table.jr thead th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; SORT.dir=(SORT.k===k)?-SORT.dir:(['opened_at','pnl','R'].includes(k)?-1:1); SORT.k=k;
    document.querySelectorAll('table.jr thead th').forEach(x=>x.classList.remove('sa','sd'));
    th.classList.add(SORT.dir>0?'sa':'sd'); renderTable();});
  applyF();
  const q=new URLSearchParams(location.search).get('trade');
  if(q && TRADES.some(t=>String(t.id)===String(q))) openTrade(parseInt(q));
}
function applyF(){
  const tag=$('f-tag').value;
  VISIBLE=TRADES.filter(t=>{
    if(F.dir && t.direction!==F.dir) return false;
    const tg=t.setup_tag||'';
    if(tag==='__none__' && tg) return false;
    if(tag && tag!=='__none__' && tg!==tag) return false;
    if(F.rsi && t.rsi_zone!==F.rsi) return false;
    if(F.book && (t.book||'hedge')!==F.book) return false;
    if(F.match==='1' && !t.merged_manual) return false;
    if(F.rev==='manual' && !isManual(t)) return false;
    if(F.rev==='auto' && isManual(t)) return false;
    if(F.result==='win' && (t.pnl||0)<=0) return false;
    if(F.result==='loss' && (t.pnl||0)>=0) return false;
    return true;
  });
  renderTable();
}
function sortVal(t,k){
  if(k==='opened_at') return t.opened_at||'';
  if(k==='direction') return t.direction||'';
  if(k==='book') return t.book||'hedge';
  if(k==='symbol') return t.symbol||'';
  if(k==='R'){ const r=rOf(t); return r==null?-1e9:r; }
  if(k==='dur') return (t.ts_entry&&t.ts_exit)?(t.ts_exit-t.ts_entry):-1;
  const v=t[k]; return v==null?-1e9:v;
}
function applySort(){ VISIBLE.sort((a,b)=>{ const x=sortVal(a,SORT.k),y=sortVal(b,SORT.k); return (x>y?1:x<y?-1:0)*SORT.dir; }); }
function rOf(t){ if(t.entry&&t.sl&&t.exit){const rp=Math.abs(t.entry-t.sl),mp=(t.exit-t.entry)*(t.direction==='long'?1:-1); if(rp>0)return mp/rp;} return null; }
function durOf(t){ if(t.ts_entry&&t.ts_exit){const m=(t.ts_exit-t.ts_entry)/60; return m>=1440?(m/1440).toFixed(1)+'d':m>=60?(m/60).toFixed(1)+'h':Math.round(m)+'m';} return '—'; }
// has the user reviewed this trade by hand?
function isManual(t){ return !!(t.grade||t.went_right||t.went_wrong||t.lesson||t.mistakes||t.emotion||t.conviction!=null||t.followed_plan!=null||t.followed_strategy!=null); }
// R proxy: stored stop if present, else realised move vs the book's stop (prop 1%, hedge = Goal SL%)
function rVal(t){
  let r=rOf(t);
  if(r==null && t.move_pct!=null){
    const slp=(t.book==='prop')?1.0:((GOALLVL&&GOALLVL.sl>0)?GOALLVL.sl*100:1.78);
    r=t.move_pct/slp;
  }
  return r==null?0:r;
}
// Grade each trade RELATIVE to your own distribution (within win/loss), so the best
// and worst actually stand out instead of everything flattening to C. Sets t._ag.
function computeAutoGrades(){
  const wins=TRADES.filter(t=>(t.pnl||0)>0).map(t=>({t,r:rVal(t)})).sort((a,b)=>b.r-a.r);
  const los =TRADES.filter(t=>(t.pnl||0)<=0).map(t=>({t,r:rVal(t)})).sort((a,b)=>b.r-a.r);
  wins.forEach((x,i)=>{ const p=wins.length?i/wins.length:0; x.t._ag=p<0.20?'A':p<0.50?'B':'C'; });
  los.forEach((x,i)=>{ const p=los.length?i/los.length:0; x.t._ag=p<0.40?'C':p<0.80?'D':'F'; });
}
function autoReview(t){
  const win=(t.pnl||0)>0, ta=t.trend_aligned, r=rVal(t), grade=t._ag||'C';
  const rtxt=r?` ${(r>=0?'+':'')+r.toFixed(1)}R`:'';
  const imp=(t.pnl!=null&&t.balance_before)?Math.abs(t.pnl/t.balance_before*100):null;
  const bits=[];
  if(win) bits.push((grade==='A'?'Top winner':grade==='B'?'Good win':'Modest win')+rtxt);
  else bits.push((grade==='F'?'Worst-tier loss':grade==='D'?'Heavy loss':'Contained loss')+rtxt+(imp!=null?` · ${imp.toFixed(0)}% of acct`:''));
  if(ta===true)bits.push('with 4H trend'); else if(ta===false)bits.push('counter-trend');
  if(t.rsi_zone)bits.push('RSI '+t.rsi_zone);
  const emoji={A:'🟢',B:'🟩',C:'🟡',D:'🟠',F:'🔴'}[grade]||'⚪';
  return {grade,emoji,take:bits.join(' · ')};
}
function renderTable(){
  const n=VISIBLE.length, w=VISIBLE.filter(t=>t.pnl>0).length, tot=VISIBLE.reduce((s,t)=>s+t.pnl,0);
  $('jr-stat').innerHTML=`<b>${n}</b> trades · WR <b>${n?(w/n*100).toFixed(0):0}%</b> · net <b style="color:${tot>=0?'var(--long)':'var(--short)'}">${eur(tot)}</b>`;
  const opts=tg=>['',...SETUPS].map(s=>`<option value="${s}" ${(tg||'')===s?'selected':''}>${s||'—'}</option>`).join('');
  applySort();
  $('jr-body').innerHTML=VISIBLE.map(t=>{
    const r=rOf(t), R=r==null?'—':(r>=0?'+':'')+r.toFixed(1)+'R';
    const bk=(t.book||'hedge'), ar=autoReview(t), man=isManual(t);
    const gradeBadge=t.grade?`<span class="flag gr" title="your grade">${t.grade}</span>`:`<span class="flag auto g${ar.grade}" title="LENS auto-review: ${ar.take}">${ar.emoji}${ar.grade}</span>`;
    const flags=gradeBadge+(t.mistakes?`<span class="flag ms">⚠${t.mistakes.split(',').length}</span>`:'')+(t.notes||t.lesson?'<span class="flag">📝</span>':'')+(t.followed_plan===false?'<span class="flag ms" title="did not follow plan">✗plan</span>':'')+(t.merged_manual?'<span class="flag" title="manual entry reconciled with exchange fill">⇄</span>':'');
    return `<tr data-id="${t.id}">
      <td class="l dim">${(t.opened_at||'').slice(0,16).replace('T',' ')}</td>
      <td class="l ${t.direction==='long'?'dir-l':'dir-s'}">${t.direction==='long'?'▲ L':'▼ S'}</td>
      <td class="l"><span class="bk ${bk}">${bk==='prop'?'PROP':'HEDGE'}</span></td>
      <td class="l dim">${(t.symbol||'BTC').replace('/USD','')}</td>
      <td>${usd(t.entry)}</td><td>${usd(t.exit)}</td>
      <td class="${t.pnl>=0?'g':'r'}">${eur(t.pnl)}</td>
      <td class="dim">${t.fees!=null?eur(-Math.abs(t.fees)):'—'}</td>
      <td class="dim">${t.leverage!=null?(+t.leverage).toFixed(0)+'×':'—'}</td>
      <td class="${r==null?'dim':r>=0?'g':'r'}">${R}</td>
      <td class="dim">${durOf(t)}</td>
      <td><select class="tagsel" data-id="${t.id}" onclick="event.stopPropagation()" onchange="saveTag(${t.id},this.value)">${opts(t.setup_tag)}</select></td>
      <td class="l">${flags||'<span class="dim">—</span>'}</td>
    </tr>`;}).join('') || '<tr><td colspan="13" class="dim l" style="padding:20px">No trades match</td></tr>';
  $('jr-body').querySelectorAll('tr[data-id]').forEach(tr=>tr.onclick=()=>openTrade(+tr.dataset.id));
}
async function saveTag(id,val){
  const t=TRADES.find(x=>x.id===id); if(t)t.setup_tag=val;
  try{await fetch('/api/trades/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({setup_tag:val||null})});}catch(e){console.error(e);}
  renderTable();
}

// ── big modal ────────────────────────────────────────────────────────────────
let bmChart=null;
function openTrade(id){
  const t=TRADES.find(x=>x.id===id); if(!t)return; SEL=t;
  const isL=t.direction==='long', win=t.pnl>=0;
  let st={grade:t.grade||null,conviction:t.conviction||null,emotion:t.emotion||null,
          mistakes:new Set((t.mistakes||'').split(',').map(s=>s.trim()).filter(Boolean)),
          fp:t.followed_plan??null,fs:t.followed_strategy??null};
  const inp=(id,v)=>`<input id="${id}" type="number" step="any" value="${v??''}">`;
  const fld=(k,inner)=>`<div class="bm-fld"><div class="k">${k}</div>${inner}</div>`;
  const fv=(k,v,c)=>`<div class="bm-fld"><div class="k">${k}</div><div class="v ${c||''}">${v}</div></div>`;
  const optrow=(lbl,key,opts,cur,cls='')=>`<div class="pickrow" data-key="${key}"><span class="pl">${lbl}</span>`+
    opts.map(o=>`<button class="opt ${cls} ${String(cur)===String(o)?'on':''}" data-v="${o}">${o}</button>`).join('')+`</div>`;
  const tri=(lbl,key,val)=>`<div class="pickrow" data-key="${key}"><span class="pl">${lbl}</span>
    <button class="opt ${val===null?'on':''}" data-v="null">—</button>
    <button class="opt ${val===true?'on':''}" data-v="true">✓ Yes</button>
    <button class="opt ${val===false?'on':''}" data-v="false">✗ No</button></div>`;
  const miss=`<div class="pickrow" id="missrow"><span class="pl">Mistakes</span>`+
    MISTAKES.map(m=>`<button class="opt miss ${st.mistakes.has(m)?'on':''}" data-m="${m}">${m}</button>`).join('')+`</div>`;
  const r=rOf(t), R=r==null?'—':(r>=0?'+':'')+r.toFixed(2)+'R';
  $('modal').innerHTML=`<div class="bm-bg open" id="mbg"><div class="bm ${isL?'long':'short'}">
    <div class="bm-h"><div class="bm-t"><span class="${isL?'g':'r'}">${isL?'▲ LONG':'▼ SHORT'}</span> ${t.symbol||'BTC/USD'} · #${t.id}
      · <span class="${win?'g':'r'}">${eur(t.pnl)}</span>${t.setup_tag?` · <span class="amb">${t.setup_tag}</span>`:''}</div>
      <button class="bm-x" id="mx">✕</button></div>
    <div id="bm-chart"></div>
    <div class="bm-cols">
      <div class="bm-grid">
        ${fld('Entry $',inp('f-entry',t.entry))}${fld('Exit $',inp('f-exit',t.exit))}
        ${fld('TP $',inp('f-tp',t.tp))}${fld('SL $',inp('f-sl',t.sl))}
        ${fld('Size',inp('f-size',t.size))}${fld('Lev ×',inp('f-lev',t.leverage))}
        ${fld('P&L €',inp('f-pnl',t.pnl))}${fld('Fees €',inp('f-fees',t.fees))}
        ${fv('R multiple',R,r==null?'dim':r>=0?'g':'r')}${fv('Duration',durOf(t))}
        ${fv('Bal before',t.balance_before!=null?eur(t.balance_before).replace(/^[+]/,''):'—','dim')}${fv('Bal after',t.balance_after!=null?eur(t.balance_after).replace(/^[+]/,''):'—',t.balance_after!=null&&t.balance_before!=null?(t.balance_after>=t.balance_before?'g':'r'):'')}
        ${fv('Notional',t.entry&&t.size?'$'+Math.round(t.entry*t.size).toLocaleString('en'):'—','dim')}${fv('Acct impact',t.pnl!=null&&t.balance_before?((t.pnl/t.balance_before*100>=0?'+':'')+(t.pnl/t.balance_before*100).toFixed(2)+'%'):'—',t.pnl>=0?'g':'r')}
      </div>
      <div class="cols-cond">
        ${fv('Entry bar',t.bar_dir?t.bar_dir.toUpperCase()+(t.bar_aligned?' ✓':' ✗'):'—',t.bar_dir?(t.bar_aligned?'g':'r'):'')}
        ${fv('4H trend',t.trend_4h?t.trend_4h.toUpperCase()+(t.trend_aligned?' ✓':' ✗'):'—',t.trend_4h?(t.trend_aligned?'g':'r'):'')}
        ${fv('RSI @ entry',t.rsi!=null?t.rsi+' '+(t.rsi_zone||''):'—')}
        ${fv('Move %',t.move_pct!=null?t.move_pct+'%':'—',(t.move_pct||0)>=0?'g':'r')}
      </div>
    </div>
    <div class="bm-sec">Assessment ${isManual(t)?'<span class="rv-badge man">✍️ reviewed by you</span>':'<span class="rv-badge auto">🤖 auto</span>'}</div>
    <div class="auto-take"><span style="font-size:15px">${autoReview(t).emoji}</span> <b>${autoReview(t).grade}</b> — ${autoReview(t).take}${isManual(t)?'':' <span class="dim">· grade/notes below override this</span>'}</div>
    <div class="bm-sec">Your review</div>
    ${optrow('Grade','grade',GRADES,st.grade,'grade')}
    ${optrow('Conviction','conviction',[1,2,3,4,5],st.conviction)}
    ${optrow('Emotion','emotion',EMOTIONS,st.emotion)}
    ${miss}
    ${tri('Followed plan?','fp',st.fp)}
    ${tri('Followed strat?','fs',st.fs)}
    <div class="bm-sec">Reflection</div>
    <div class="refl">
      <textarea id="bm-right" placeholder="what went right…">${t.went_right||''}</textarea>
      <textarea id="bm-wrong" placeholder="what went wrong…">${t.went_wrong||''}</textarea>
      <textarea id="bm-lesson" placeholder="lesson…">${t.lesson||''}</textarea>
    </div>
    <textarea id="bm-notes" placeholder="notes…">${t.notes||''}</textarea>
    <div><button class="bm-save" id="msave">💾 Save review</button></div>
  </div></div>`;
  const close=()=>{if(bmChart){try{bmChart.remove();}catch(e){}bmChart=null;}$('modal').innerHTML='';document.onkeydown=null;if(location.search.includes('trade='))history.replaceState(null,'','/journal');};
  $('mbg').onclick=e=>{if(e.target.id==='mbg')close();}; $('mx').onclick=close;
  document.onkeydown=e=>{if(e.key==='Escape')close();};
  // chart
  const el=$('bm-chart');
  if(window.LightweightCharts && CANDLES.length){
    bmChart=LightweightCharts.createChart(el,{layout:{background:{color:'#06080c'},textColor:'#465064'},grid:{vertLines:{color:'#192232'},horzLines:{color:'#192232'}},rightPriceScale:{borderColor:'#192232'},timeScale:{borderColor:'#192232',timeVisible:true,secondsVisible:false}});
    const s=bmChart.addCandlestickSeries({upColor:'#1fd989',downColor:'#ff5468',borderUpColor:'#1fd989',borderDownColor:'#ff5468',wickUpColor:'#1fd989',wickDownColor:'#ff5468'});
    s.setData(CANDLES); const L=LightweightCharts.LineStyle, ec=isL?'#1fd989':'#ff5468';
    if(t.entry)s.createPriceLine({price:t.entry,color:ec,lineWidth:1,lineStyle:L.Solid,axisLabelVisible:true,title:'ENTRY'});
    if(t.exit)s.createPriceLine({price:t.exit,color:'#828ea6',lineWidth:1,lineStyle:L.Dashed,axisLabelVisible:true,title:'EXIT'});
    if(t.tp)s.createPriceLine({price:t.tp,color:'#1fd989',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'TP'});
    if(t.sl)s.createPriceLine({price:t.sl,color:'#ff5468',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'SL'});
    const ms=[]; if(t.ts_entry)ms.push({time:t.ts_entry,position:isL?'belowBar':'aboveBar',color:ec,shape:isL?'arrowUp':'arrowDown',text:'E',size:1.5});
    if(t.ts_exit)ms.push({time:t.ts_exit,position:isL?'aboveBar':'belowBar',color:isL?'#ff5468':'#1fd989',shape:isL?'arrowDown':'arrowUp',text:'X',size:1.5});
    s.setMarkers(ms);
    setTimeout(()=>{if(!bmChart)return;bmChart.applyOptions({width:el.clientWidth,height:el.clientHeight});if(t.ts_entry)bmChart.timeScale().setVisibleRange({from:t.ts_entry-48*3600,to:(t.ts_exit||t.ts_entry)+24*3600});},40);
  }
  // pick rows
  const pv=s=>s==='null'?null:s==='true'?true:s==='false'?false:s;
  $('modal').querySelectorAll('.pickrow[data-key]').forEach(row=>{
    const key=row.dataset.key, isTri=key==='fp'||key==='fs';
    row.querySelectorAll('.opt[data-v]').forEach(b=>b.onclick=()=>{
      const v=pv(b.dataset.v); st[key]=(!isTri&&String(st[key])===String(v))?null:v;
      row.querySelectorAll('.opt[data-v]').forEach(x=>x.classList.toggle('on',String(st[key])===String(pv(x.dataset.v))));
    });
  });
  $('missrow').querySelectorAll('.opt').forEach(b=>b.onclick=()=>{const m=b.dataset.m;
    if(st.mistakes.has(m)){st.mistakes.delete(m);b.classList.remove('on');}else{st.mistakes.add(m);b.classList.add('on');}});
  $('msave').onclick=async()=>{
    $('msave').textContent='Saving…';$('msave').disabled=true;
    const nf=id=>{const v=parseFloat($(id).value);return isNaN(v)?undefined:v;};
    const p={manually_edited:true,entry:nf('f-entry'),exit:nf('f-exit'),tp:nf('f-tp'),sl:nf('f-sl'),
      size:nf('f-size'),leverage:nf('f-lev'),pnl:nf('f-pnl'),fees:nf('f-fees'),
      mistakes:[...st.mistakes].join(',')||undefined,went_right:$('bm-right').value||undefined,
      went_wrong:$('bm-wrong').value||undefined,lesson:$('bm-lesson').value||undefined,notes:$('bm-notes').value||undefined};
    if(st.grade!=null)p.grade=st.grade; if(st.conviction!=null)p.conviction=st.conviction; if(st.emotion!=null)p.emotion=st.emotion;
    if(st.fp!==null)p.followed_plan=st.fp; if(st.fs!==null)p.followed_strategy=st.fs;
    Object.keys(p).forEach(k=>p[k]===undefined&&delete p[k]);
    try{const r=await fetch('/api/trades/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
      const u=await r.json(); Object.assign(t,u); close(); applyF();
    }catch(e){console.error(e);$('msave').textContent='Error';$('msave').disabled=false;}
  };
}
async function syncKraken(){
  const b=document.getElementById('jr-sync'); b.disabled=true; const t=b.textContent; b.textContent='⟳ syncing…';
  try{
    await fetch('/api/sync/kraken',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    // sync runs in the background — poll its result, then reload trades
    for(let i=0;i<25;i++){ await new Promise(r=>setTimeout(r,1500));
      const s=await fetch('/api/sync/kraken/result?account=personal').then(r=>r.json());
      if(s.running===false){ b.textContent=s.imported!=null?('✓ +'+s.imported):'✓ done'; await load(); loadOpenPositions(); break; }
    }
  }catch(e){ b.textContent='✗ failed'; }
  setTimeout(()=>{ b.textContent=t; b.disabled=false; },2500);
}
load();
"""

JOURNAL_HTML = shell("/journal", "Journal", BODY, script=SCRIPT, head_extra=_CSS, meta="what did I do?")
