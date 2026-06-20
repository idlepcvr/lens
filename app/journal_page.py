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
</style>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
"""

BODY = """
<div class="jr-bar">
  <select id="f-tag" onchange="applyF()"><option value="">All setups</option><option value="__none__">Untagged</option></select>
  <div class="jseg" data-k="dir"><b>Dir</b><button data-v="" class="on">All</button><button data-v="long">Long</button><button data-v="short">Short</button></div>
  <div class="jseg" data-k="result"><b>Res</b><button data-v="" class="on">All</button><button data-v="win">Win</button><button data-v="loss">Loss</button></div>
  <div class="jseg" data-k="rsi"><b>RSI</b><button data-v="" class="on">All</button><button data-v="dip">Dip</button><button data-v="momentum">Mom</button><button data-v="neutral">Neut</button></div>
  <div class="jr-spacer"></div>
  <div class="jr-stat" id="jr-stat">—</div>
</div>
<div class="jr-wrap">
  <table class="jr">
    <thead><tr>
      <th>Date</th><th>Dir</th><th>Sym</th><th>Entry</th><th>Exit</th><th>P&L</th><th>R</th><th>Dur</th><th>Setup</th><th>Review</th>
    </tr></thead>
    <tbody id="jr-body"><tr><td colspan="10" class="dim l" style="padding:20px">Loading…</td></tr></tbody>
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
const F={dir:'',result:'',rsi:''};
const $=id=>document.getElementById(id);
const eur=(v,d=2)=>v==null?'—':(v<0?'-':'+')+'€'+Math.abs(v).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});
const usd=(v)=>v==null?'—':'$'+Number(v).toLocaleString('en',{maximumFractionDigits:0});

async function load(){
  const [tr,ca]=await Promise.all([fetch('/api/review/trades'),fetch('/api/review/ohlcv')]);
  TRADES=(await tr.json()).filter(t=>t.pnl!=null);
  try{CANDLES=await ca.json();}catch(e){CANDLES=[];}
  const tagsel=$('f-tag'); [...new Set(TRADES.map(t=>t.setup_tag).filter(Boolean))].sort().forEach(tg=>{
    const o=document.createElement('option'); o.value=o.textContent=tg; tagsel.appendChild(o);});
  document.querySelectorAll('.jseg').forEach(seg=>seg.querySelectorAll('button').forEach(b=>b.onclick=()=>{
    F[seg.dataset.k]=b.dataset.v; seg.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b)); applyF();}));
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
    if(F.result==='win' && (t.pnl||0)<=0) return false;
    if(F.result==='loss' && (t.pnl||0)>=0) return false;
    return true;
  });
  renderTable();
}
function rOf(t){ if(t.entry&&t.sl&&t.exit){const rp=Math.abs(t.entry-t.sl),mp=(t.exit-t.entry)*(t.direction==='long'?1:-1); if(rp>0)return mp/rp;} return null; }
function durOf(t){ if(t.ts_entry&&t.ts_exit){const m=(t.ts_exit-t.ts_entry)/60; return m>=1440?(m/1440).toFixed(1)+'d':m>=60?(m/60).toFixed(1)+'h':Math.round(m)+'m';} return '—'; }
function renderTable(){
  const n=VISIBLE.length, w=VISIBLE.filter(t=>t.pnl>0).length, tot=VISIBLE.reduce((s,t)=>s+t.pnl,0);
  $('jr-stat').innerHTML=`<b>${n}</b> trades · WR <b>${n?(w/n*100).toFixed(0):0}%</b> · net <b style="color:${tot>=0?'var(--long)':'var(--short)'}">${eur(tot)}</b>`;
  const opts=tg=>['',...SETUPS].map(s=>`<option value="${s}" ${(tg||'')===s?'selected':''}>${s||'—'}</option>`).join('');
  $('jr-body').innerHTML=VISIBLE.slice().reverse().map(t=>{
    const r=rOf(t), R=r==null?'—':(r>=0?'+':'')+r.toFixed(1)+'R';
    const flags=(t.grade?`<span class="flag gr">${t.grade}</span>`:'')+(t.mistakes?`<span class="flag ms">⚠${t.mistakes.split(',').length}</span>`:'')+(t.notes||t.lesson?'<span class="flag">📝</span>':'');
    return `<tr data-id="${t.id}">
      <td class="l dim">${(t.opened_at||'').slice(0,16).replace('T',' ')}</td>
      <td class="l ${t.direction==='long'?'dir-l':'dir-s'}">${t.direction==='long'?'▲ L':'▼ S'}</td>
      <td class="l dim">${(t.symbol||'BTC').replace('/USD','')}</td>
      <td>${usd(t.entry)}</td><td>${usd(t.exit)}</td>
      <td class="${t.pnl>=0?'g':'r'}">${eur(t.pnl)}</td>
      <td class="${r==null?'dim':r>=0?'g':'r'}">${R}</td>
      <td class="dim">${durOf(t)}</td>
      <td><select class="tagsel" data-id="${t.id}" onclick="event.stopPropagation()" onchange="saveTag(${t.id},this.value)">${opts(t.setup_tag)}</select></td>
      <td class="l">${flags||'<span class="dim">—</span>'}</td>
    </tr>`;}).join('') || '<tr><td colspan="10" class="dim l" style="padding:20px">No trades match</td></tr>';
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
      </div>
      <div class="cols-cond">
        ${fv('Entry bar',t.bar_dir?t.bar_dir.toUpperCase()+(t.bar_aligned?' ✓':' ✗'):'—',t.bar_dir?(t.bar_aligned?'g':'r'):'')}
        ${fv('4H trend',t.trend_4h?t.trend_4h.toUpperCase()+(t.trend_aligned?' ✓':' ✗'):'—',t.trend_4h?(t.trend_aligned?'g':'r'):'')}
        ${fv('RSI @ entry',t.rsi!=null?t.rsi+' '+(t.rsi_zone||''):'—')}
        ${fv('Move %',t.move_pct!=null?t.move_pct+'%':'—',(t.move_pct||0)>=0?'g':'r')}
      </div>
    </div>
    <div class="bm-sec">Review</div>
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
load();
"""

JOURNAL_HTML = shell("/journal", "Journal", BODY, script=SCRIPT, head_extra=_CSS, meta="what did I do?")
