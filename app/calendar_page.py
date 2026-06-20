"""LENS /calendar — hedge-book trade calendar + review.

Monthly P&L heatmap of the hedge trades (book='hedge'). Hover a day for a
transient breakdown, click to pin, click a trade to open the review modal:
an EDITABLE trade breakdown plus a structured review layer — execution grade,
recurring-mistake tags (Edgewonk-style), conviction, mental state, and
right/wrong/lesson reflection. Saved via PATCH /api/trades/{id}. Native LENS
page reading /api/trades — no cross-app.
"""

from .theme import shell

MISTAKES = ["chased", "early", "late", "oversized", "moved stop", "no stop",
            "revenge", "FOMO", "overheld", "cut early", "no setup"]
EMOTIONS = ["calm", "FOMO", "tilt", "fear", "greed", "bored"]
GRADES   = ["A", "B", "C", "D", "F"]

_CSS = """
<style>
.cal-wrap{display:flex;gap:0;align-items:flex-start}
.cal-main{flex:1;min-width:0}
.cal-side{width:240px;flex:0 0 auto;border-left:1px solid var(--line);padding:4px 0 4px 16px;margin-left:16px}
.cal-sub{color:var(--dim);font-size:12px;margin:2px 0 12px}
.cal-pills{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.cal-pill{font-family:var(--mono);font-size:11px;color:var(--dim);padding:4px 11px;border:1px solid var(--line);
  border-radius:20px;background:transparent;cursor:pointer;white-space:nowrap}
.cal-pill.cur{color:var(--bg);background:var(--accent);border-color:var(--accent);font-weight:700}
.cal-dow{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:4px}
.cal-dow span{text-align:center;font-size:10px;color:var(--dim);font-weight:600}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.cal-cell{aspect-ratio:1;border-radius:6px;border:1px solid var(--line);display:flex;flex-direction:column;
  align-items:center;justify-content:center;padding:4px;cursor:default}
.cal-cell.has{cursor:pointer}
.cal-cell.empty{border:none;opacity:0}
.cal-cell.sel{outline:2px solid var(--accent);outline-offset:1px}
.cal-cell .d{font-size:11px;color:var(--dim)}
.cal-cell.sel .d{color:var(--accent);font-weight:700}
.cal-cell .p{font-size:9px;font-family:var(--mono);font-weight:700;margin-top:2px}
.cal-cell .gr{font-size:8px;color:var(--dim);margin-top:1px}
.cal-sum .row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--line);font-size:12px}
.cal-sum .row .lbl{color:var(--dim)} .cal-sum .row .val{font-family:var(--mono);font-weight:600}
.cal-day-h{display:flex;justify-content:space-between;align-items:center;margin:14px 0 6px}
.cal-day-h .ttl{font-size:11px;font-weight:700;color:var(--ink)}
.cal-day-h .x{font-size:12px;color:var(--dim);background:none;border:none;cursor:pointer}
.cal-day-pnl{font-size:18px;font-weight:700;font-family:var(--mono);margin-bottom:2px}
.cal-day-meta{font-size:11px;color:var(--dim);margin-bottom:10px}
.cal-trow{font-size:11px;padding:7px 9px;border-radius:6px;margin-bottom:5px;border:1px solid var(--line);cursor:pointer}
.cal-trow:hover{border-color:var(--line2)}
.cal-trow .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px}
.cal-trow .dir{font-weight:700} .cal-trow .pnl{font-family:var(--mono);font-weight:700}
.cal-trow .sub{color:var(--dim);font-size:10px}
.cal-trow .rb{display:inline-block;font-size:9px;padding:0 4px;border-radius:3px;border:1px solid var(--line2);margin-left:4px;color:var(--dim)}
.g{color:var(--long)} .r{color:var(--short)} .amb{color:var(--amber)}
.cal-empty{font-size:11px;color:var(--dim);text-align:center;margin-top:24px}
/* modal */
.cal-modal-bg{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.6);backdrop-filter:blur(2px);
  display:flex;align-items:center;justify-content:center;padding:16px}
.cal-modal{width:min(560px,100%);max-height:92vh;overflow-y:auto;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:18px 20px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.cal-modal.long{border-left:4px solid var(--long)} .cal-modal.short{border-left:4px solid var(--short)}
.cal-m-h{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.cal-m-sym{font-size:16px;font-weight:700} .cal-m-pnl{font-size:26px;font-weight:700;font-family:var(--mono);margin-top:2px}
.cal-m-x{font-size:16px;color:var(--dim);background:none;border:none;cursor:pointer}
.cal-sec{font-size:10px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;
  margin:14px 0 6px;border-bottom:1px solid var(--line);padding-bottom:4px}
.cal-m-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px}
.cal-fld .fk{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}
.cal-fld .fv{font-size:12px;font-family:var(--mono);font-weight:600}
.cal-in,.cal-notes{width:100%;background:var(--panel2);border:1px solid var(--line);border-radius:6px;
  padding:5px 7px;color:var(--ink);font-size:12px;font-family:var(--mono);outline:none}
.cal-in:focus,.cal-notes:focus{border-color:var(--accent)}
.cal-notes{min-height:48px;resize:vertical}
.cal-derived{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--dim);margin-top:8px}
.cal-derived b{font-family:var(--mono)}
/* pick rows */
.cal-pickrow{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:8px}
.cal-pickrow .pl{font-size:11px;color:var(--dim);width:92px;flex:0 0 auto}
.cal-opt{padding:3px 9px;border-radius:5px;border:1px solid var(--line);font-size:11px;cursor:pointer;
  background:transparent;color:var(--dim);font-family:var(--mono)}
.cal-opt.on{border-color:var(--accent);background:var(--accent-d);color:var(--ink);font-weight:700}
.cal-opt.grade.on{border-color:var(--amber);color:var(--amber)}
.cal-opt.miss.on{border-color:var(--short);background:rgba(255,99,99,.12);color:var(--short)}
.cal-tri button.on-y{border-color:var(--long);background:var(--accent-d);color:var(--long)}
.cal-tri button.on-n{border-color:var(--short);background:var(--accent-d);color:var(--short)}
.cal-tri button.on-x{border-color:var(--line2);background:var(--panel2);color:var(--ink)}
.cal-acts{display:flex;gap:8px;margin-top:16px}
.cal-acts .save{flex:1;padding:9px 0;border-radius:6px;border:none;cursor:pointer;background:var(--accent);
  color:var(--bg);font-size:12px;font-weight:700}
.cal-acts .full{padding:9px 14px;border-radius:6px;border:1px solid var(--line);cursor:pointer;background:transparent;
  color:var(--dim);font-size:12px;text-decoration:none;display:flex;align-items:center}
#cal-chart{height:300px;border:1px solid var(--line);border-radius:8px;margin-bottom:12px}
@media(max-width:600px){
  /* portrait: stack the day panel under the calendar, and make the P&L legible
     on the colored heatmap cells (was colored-on-colored → blended in) */
  .cal-wrap{flex-direction:column}
  .cal-side{width:100%;border-left:none;border-top:1px solid var(--line);margin-left:0;padding:12px 0 0;margin-top:14px}
  .cal-cell{padding:3px}
  .cal-cell .d{color:var(--ink);font-weight:600}
  .cal-cell.sel .d{color:var(--accent)}
  .cal-cell .p{color:var(--ink) !important;font-size:9px;text-shadow:0 1px 2px rgba(0,0,0,.75)}
  .cal-modal{width:96vw;padding:14px 14px}
  #cal-chart{height:240px}
}
</style>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
"""

BODY = """
<div class="cal-sub">Monthly hedge-book heatmap · hover a day, click to pin · click a trade to review</div>
<div class="cal-wrap">
  <div class="cal-main">
    <div class="cal-pills" id="pills"></div>
    <div class="cal-dow"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span></div>
    <div class="cal-grid" id="grid"></div>
  </div>
  <div class="cal-side" id="side"></div>
</div>
<div id="modal"></div>
"""

SCRIPT = r"""
const MISTAKES=__MISTAKES__, EMOTIONS=__EMOTIONS__, GRADES=__GRADES__;
let TRADES=[], MONTH='', SELDAY=null, HOVDAY=null, CANDLES=[];
const $=id=>document.getElementById(id);
const eur=(v,d=2)=>(v<0?'-':'')+'€'+Math.abs(v||0).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});
const num=(v,d=2)=>v==null||v===''?'':Number(v).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});
const toLocal=s=>{if(!s)return'';const d=new Date(s);if(isNaN(d))return'';const p=n=>String(n).padStart(2,'0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;};

async function load(){
  // /api/trades = full trade incl review fields + is_open + ISO dates (primary).
  // /api/review/trades = indicator context at entry (bar/4H trend/RSI/move) — merged
  // in by id so the modal matches the /review page's richness.
  const [tr,er,ca]=await Promise.all([fetch('/api/trades?limit=2000'),fetch('/api/review/trades'),fetch('/api/review/ohlcv')]);
  const j=await tr.json(); let ej=[]; try{ej=await er.json();}catch(e){}
  try{CANDLES=await ca.json();}catch(e){CANDLES=[];}
  const ctx={}; (Array.isArray(ej)?ej:(ej.trades||[])).forEach(t=>ctx[t.id]={
    bar_dir:t.bar_dir, bar_aligned:t.bar_aligned, trend_4h:t.trend_4h,
    trend_aligned:t.trend_aligned, ctx_rsi:t.rsi, rsi_zone:t.rsi_zone, move_pct:t.move_pct,
    ts_entry:t.ts_entry, ts_exit:t.ts_exit});
  TRADES=(j.trades||[]).filter(t=>!t.is_open && t.pnl!=null && t.closed_at)
                       .map(t=>Object.assign(t,ctx[t.id]||{}));
  if(TRADES.length){ MONTH=TRADES.reduce((a,b)=>a.closed_at>b.closed_at?a:b).closed_at.slice(0,7); }
  render();
}
function dayMap(){
  const m={};
  TRADES.forEach(t=>{const d=t.closed_at.slice(0,10);
    (m[d]=m[d]||{date:d,pnl:0,trades:[],wins:0,losses:0});
    m[d].pnl+=t.pnl; m[d].trades.push(t); (t.pnl>0?m[d].wins++:m[d].losses++);});
  return m;
}
function render(){
  const dm=dayMap();
  const months=[...new Set(TRADES.map(t=>t.closed_at.slice(0,7)))].sort().reverse();
  $('pills').innerHTML=months.map(m=>`<button class="cal-pill ${m===MONTH?'cur':''}" data-m="${m}">${new Date(m+'-01').toLocaleDateString('en',{month:'short',year:'numeric'})}</button>`).join('');
  $('pills').querySelectorAll('button').forEach(b=>b.onclick=()=>{MONTH=b.dataset.m;SELDAY=null;render();});
  const [y,mo]=MONTH.split('-').map(Number);
  const daysIn=new Date(y,mo,0).getDate();
  const off=(new Date(y,mo-1,1).getDay()+6)%7;
  const maxAbs=Math.max(1,...Object.values(dm).map(d=>Math.abs(d.pnl)));
  let cells='';
  for(let i=0;i<off;i++) cells+='<div class="cal-cell empty"></div>';
  for(let d=1;d<=daysIn;d++){
    const ds=`${y}-${String(mo).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const c=dm[ds]; const sel=SELDAY===ds?'sel':'';
    let bg='transparent';
    if(c){const inten=Math.min(Math.abs(c.pnl)/maxAbs,1);
      bg=c.pnl>0?`rgba(31,217,137,${0.1+inten*0.7})`:`rgba(255,99,99,${0.1+inten*0.7})`;}
    cells+=`<div class="cal-cell ${c?'has':''} ${sel}" data-d="${ds}" style="background:${bg}">
      <div class="d">${d}</div>${c?`<div class="p ${c.pnl>=0?'g':'r'}">${c.pnl>=0?'+':''}€${Math.abs(c.pnl).toFixed(0)}</div>`:''}</div>`;
  }
  $('grid').innerHTML=cells;
  $('grid').querySelectorAll('.cal-cell.has').forEach(el=>{
    const ds=el.dataset.d;
    el.onclick=()=>{SELDAY=SELDAY===ds?null:ds;render();};
    // hover previews a day's trades; the list then STAYS (last-hovered) so you can
    // move the cursor into the panel and click a trade. Clearing on mouseleave made
    // the rows vanish under the cursor — only a pinned (clicked) day stayed usable.
    el.onmouseenter=()=>{HOVDAY=ds;renderSide();};
  });
  renderSide();
}
function renderSide(){
  const dm=dayMap();
  const cells=Object.values(dm).filter(d=>d.date.slice(0,7)===MONTH);
  const mPnl=cells.reduce((s,c)=>s+c.pnl,0), mT=cells.reduce((s,c)=>s+c.trades.length,0), mW=cells.reduce((s,c)=>s+c.wins,0);
  let h=`<div class="cal-sum"><div style="font-size:12px;font-weight:700;color:var(--ink);margin-bottom:8px">${new Date(MONTH+'-01').toLocaleDateString('en',{month:'long',year:'numeric'})}</div>`;
  h+=`<div class="row"><span class="lbl">Net P&L</span><span class="val ${mPnl>=0?'g':'r'}">${mPnl>=0?'+':''}${eur(mPnl)}</span></div>`;
  h+=`<div class="row"><span class="lbl">Trades</span><span class="val">${mT}</span></div>`;
  h+=`<div class="row"><span class="lbl">Win Rate</span><span class="val">${mT?(mW/mT*100).toFixed(1)+'%':'—'}</span></div></div>`;
  const pd=SELDAY?dm[SELDAY]:(HOVDAY?dm[HOVDAY]:null);
  if(pd&&pd.trades.length){
    h+=`<div class="cal-day-h"><span class="ttl">${new Date(pd.date+'T12:00:00').toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'})}</span>`;
    h+=(SELDAY===pd.date?`<button class="x" id="unpin">✕</button>`:'')+`</div>`;
    h+=`<div class="cal-day-pnl ${pd.pnl>=0?'g':'r'}">${pd.pnl>=0?'+':''}${eur(pd.pnl)}</div>`;
    h+=`<div class="cal-day-meta">${pd.trades.length} trade${pd.trades.length!=1?'s':''} · ${pd.wins}W / ${pd.losses}L</div>`;
    pd.trades.forEach(t=>{
      const tm=new Date(t.opened_at).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
      h+=`<div class="cal-trow" data-id="${t.id}">
        <div class="top"><span class="dir ${t.direction==='long'?'g':'r'}">${t.direction==='long'?'▲':'▼'} ${(t.direction||'').toUpperCase()}</span>
        <span class="pnl ${t.pnl>=0?'g':'r'}">${t.pnl>=0?'+':''}${eur(t.pnl)}</span></div>
        <div class="sub">${tm}${t.leverage?` · ${t.leverage}×`:''}${t.setup_tag?` · ${t.setup_tag}`:''}
          ${t.grade?`<span class="rb amb">${t.grade}</span>`:''}${t.mistakes?`<span class="rb r">⚠ ${t.mistakes.split(',').length}</span>`:''}</div>
      </div>`;
    });
  } else if(MONTH){ h+=`<div class="cal-empty">Hover or click a day to see its trades</div>`; }
  $('side').innerHTML=h;
  const up=$('unpin'); if(up) up.onclick=()=>{SELDAY=null;render();};
  $('side').querySelectorAll('.cal-trow').forEach(el=>el.onclick=()=>openModal(+el.dataset.id));
}

function openModal(id){
  const t=TRADES.find(x=>x.id===id); if(!t) return;
  const isL=t.direction==='long', win=t.pnl>=0;
  // review state
  let st={grade:t.grade||null, conviction:t.conviction||null, emotion:t.emotion||null,
          mistakes:new Set((t.mistakes||'').split(',').map(s=>s.trim()).filter(Boolean)),
          fp:t.followed_plan??null, fs:t.followed_strategy??null};
  const num2=(v,d=2)=>v==null?'':v;
  const inp=(id,val,ph='',step='any')=>`<input class="cal-in" id="${id}" type="number" step="${step}" value="${val??''}" placeholder="${ph}">`;
  const dtin=(id,val)=>`<input class="cal-in" id="${id}" type="datetime-local" value="${toLocal(val)}" style="color-scheme:dark">`;
  const fld=(k,inner)=>`<div class="cal-fld"><div class="fk">${k}</div>${inner}</div>`;
  const optrow=(label,key,opts,cur,cls='')=>{
    return `<div class="cal-pickrow" data-key="${key}"><span class="pl">${label}</span>`+
      opts.map(o=>`<button class="cal-opt ${cls} ${String(cur)===String(o)?'on':''}" data-v="${o}">${o}</button>`).join('')+`</div>`;
  };
  const tri=(label,key,val)=>`<div class="cal-pickrow cal-tri" data-key="${key}"><span class="pl">${label}</span>
    <button data-v="null" class="cal-opt ${val===null?'on-x':''}">—</button>
    <button data-v="true" class="cal-opt ${val===true?'on-y':''}">✓ Yes</button>
    <button data-v="false" class="cal-opt ${val===false?'on-n':''}">✗ No</button></div>`;
  const misschips=`<div class="cal-pickrow" id="missrow"><span class="pl">Mistakes</span>`+
    MISTAKES.map(m=>`<button class="cal-opt miss ${st.mistakes.has(m)?'on':''}" data-m="${m}">${m}</button>`).join('')+`</div>`;

  $('modal').innerHTML=`<div class="cal-modal-bg" id="mbg"><div class="cal-modal ${isL?'long':'short'}">
    <div class="cal-m-h"><div>
      <div class="cal-m-sym ${isL?'g':'r'}">${isL?'▲ LONG':'▼ SHORT'} ${t.symbol||''} ${t.setup_tag?`<span class="rb">${t.setup_tag}</span>`:''}</div>
      <div class="cal-m-pnl ${win?'g':'r'}">${win?'+':''}${eur(Math.abs(t.pnl))}</div>
    </div><button class="cal-m-x" id="mx">✕</button></div>

    <div id="cal-chart"></div>

    <div class="cal-sec">Breakdown · editable</div>
    <div class="cal-m-grid">
      ${fld('Entry $',inp('f-entry',t.entry))}
      ${fld('Exit $',inp('f-exit',t.exit))}
      ${fld('TP $',inp('f-tp',t.tp))}
      ${fld('SL $',inp('f-sl',t.sl))}
      ${fld('Size',inp('f-size',t.size))}
      ${fld('Leverage ×',inp('f-lev',t.leverage))}
      ${fld('P&L €',inp('f-pnl',t.pnl))}
      ${fld('Fees €',inp('f-fees',t.fees))}
      ${fld('Opened',dtin('f-open',t.opened_at))}
      ${fld('Closed',dtin('f-close',t.closed_at))}
    </div>
    <div class="cal-derived" id="derived"></div>

    ${(t.bar_dir||t.trend_4h||t.ctx_rsi!=null||t.move_pct!=null)?`
    <div class="cal-sec">Context · at entry</div>
    <div class="cal-m-grid">
      ${fld('Entry bar',`<div class="fv ${t.bar_dir?(t.bar_aligned?'g':'r'):''}">${t.bar_dir?t.bar_dir.toUpperCase()+' '+(t.bar_aligned?'✓':'✗'):'—'}</div>`)}
      ${fld('4H trend',`<div class="fv ${t.trend_4h?(t.trend_aligned?'g':'r'):''}">${t.trend_4h?t.trend_4h.toUpperCase()+' '+(t.trend_aligned?'✓':'✗'):'—'}</div>`)}
      ${fld('RSI @ entry',`<div class="fv">${t.ctx_rsi!=null?t.ctx_rsi+' '+(t.rsi_zone||''):'—'}</div>`)}
      ${fld('Move %',`<div class="fv ${(t.move_pct||0)>=0?'g':'r'}">${t.move_pct!=null?t.move_pct+'%':'—'}</div>`)}
    </div>`:''}

    <div class="cal-sec">Review</div>
    ${optrow('Grade','grade',GRADES,st.grade,'grade')}
    ${optrow('Conviction','conviction',[1,2,3,4,5],st.conviction)}
    ${optrow('Emotion','emotion',EMOTIONS,st.emotion)}
    ${misschips}
    ${tri('Followed plan?','fp',st.fp)}
    ${tri('Followed strat?','fs',st.fs)}

    <div class="cal-sec">Reflection</div>
    <div class="cal-fld" style="margin-bottom:8px"><div class="fk">What went right</div><textarea class="cal-notes" id="f-right">${t.went_right||''}</textarea></div>
    <div class="cal-fld" style="margin-bottom:8px"><div class="fk">What went wrong</div><textarea class="cal-notes" id="f-wrong">${t.went_wrong||''}</textarea></div>
    <div class="cal-fld" style="margin-bottom:8px"><div class="fk">Lesson / takeaway</div><textarea class="cal-notes" id="f-lesson">${t.lesson||''}</textarea></div>
    <div class="cal-fld"><div class="fk">Notes</div><textarea class="cal-notes" id="f-notes">${t.notes||''}</textarea></div>

    <div class="cal-acts">
      <button class="save" id="msave">💾 Save review</button>
      <a class="full" href="/journal">Journal →</a>
    </div>
  </div></div>`;

  let calChart=null;
  const close=()=>{if(calChart){try{calChart.remove();}catch(e){}calChart=null;}$('modal').innerHTML='';document.onkeydown=null;};
  $('mbg').onclick=e=>{if(e.target.id==='mbg')close();};
  $('mx').onclick=close;
  document.onkeydown=e=>{if(e.key==='Escape')close();};

  // derived R + duration, recompute on input
  const derive=()=>{
    const e=parseFloat($('f-entry').value), x=parseFloat($('f-exit').value), s=parseFloat($('f-sl').value);
    let R='—'; if(e&&x&&s){const rp=Math.abs(e-s),mp=(x-e)*(isL?1:-1); if(rp>0)R=(mp/rp).toFixed(2)+'R';}
    const o=$('f-open').value,cl=$('f-close').value; let hold='—';
    if(o&&cl){const ms=new Date(cl)-new Date(o),hh=ms/3.6e6; if(!isNaN(hh)&&hh>=0)hold=hh>=24?(hh/24).toFixed(1)+'d':hh>=1?hh.toFixed(1)+'h':Math.round(ms/6e4)+'m';}
    $('derived').innerHTML=`<span>R: <b class="${R.startsWith('-')?'r':'g'}">${R}</b></span><span>Hold: <b>${hold}</b></span>`;
  };
  ['f-entry','f-exit','f-sl','f-open','f-close'].forEach(i=>$(i).oninput=derive); derive();

  // option rows (single-select; re-click clears, except the always-set tri rows)
  const parseV=s=>s==='null'?null:s==='true'?true:s==='false'?false:s;
  $('modal').querySelectorAll('.cal-pickrow[data-key]').forEach(row=>{
    const key=row.dataset.key, isTri=key==='fp'||key==='fs';
    const paint=()=>row.querySelectorAll('.cal-opt[data-v]').forEach(x=>{
      let cls=x.classList.contains('grade')?'cal-opt grade':'cal-opt';
      const xv=parseV(x.dataset.v);
      if(String(st[key])===String(xv)) cls+=isTri?(xv===null?' on-x':xv?' on-y':' on-n'):' on';
      x.className=cls;
    });
    row.querySelectorAll('.cal-opt[data-v]').forEach(b=>b.onclick=()=>{
      const v=parseV(b.dataset.v);
      st[key]=(!isTri && String(st[key])===String(v)) ? null : v;   // re-click toggles off
      paint();
    });
  });
  // mistake multi-select
  $('missrow').querySelectorAll('.cal-opt').forEach(b=>b.onclick=()=>{
    const m=b.dataset.m; if(st.mistakes.has(m)){st.mistakes.delete(m);b.classList.remove('on');}
    else{st.mistakes.add(m);b.classList.add('on');}
  });

  $('msave').onclick=async()=>{
    $('msave').textContent='Saving…'; $('msave').disabled=true;
    const fv=id=>{const v=parseFloat($(id).value);return isNaN(v)?undefined:v;};
    const dv=id=>{const v=$(id).value;return v?new Date(v).toISOString():undefined;};
    const payload={
      entry:fv('f-entry'), exit:fv('f-exit'), tp:fv('f-tp'), sl:fv('f-sl'),
      size:fv('f-size'), leverage:fv('f-lev'), pnl:fv('f-pnl'), fees:fv('f-fees'),
      opened_at:dv('f-open'), closed_at:dv('f-close'),
      grade:st.grade??undefined, conviction:st.conviction??undefined, emotion:st.emotion??undefined,
      mistakes:[...st.mistakes].join(',')||undefined,
      went_right:$('f-right').value||undefined, went_wrong:$('f-wrong').value||undefined,
      lesson:$('f-lesson').value||undefined, notes:$('f-notes').value||undefined,
    };
    if(st.fp!==null)payload.followed_plan=st.fp; if(st.fs!==null)payload.followed_strategy=st.fs;
    Object.keys(payload).forEach(k=>payload[k]===undefined&&delete payload[k]);
    try{
      const r=await fetch('/api/trades/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const u=await r.json();
      const idx=TRADES.findIndex(x=>x.id===id); if(idx>=0)TRADES[idx]={...TRADES[idx],...u};
      close(); render();
    }catch(e){console.error(e);$('msave').textContent='Error — retry';$('msave').disabled=false;}
  };

  // price chart of the trade (ENTRY/EXIT lines, TP/SL dotted, E/X markers)
  const chartEl=$('cal-chart');
  if(chartEl && window.LightweightCharts && CANDLES.length){
    calChart=LightweightCharts.createChart(chartEl,{layout:{background:{color:'#06080c'},textColor:'#465064'},
      grid:{vertLines:{color:'#192232'},horzLines:{color:'#192232'}},
      rightPriceScale:{borderColor:'#192232'},timeScale:{borderColor:'#192232',timeVisible:true,secondsVisible:false}});
    const s=calChart.addCandlestickSeries({upColor:'#1fd989',downColor:'#ff5468',borderUpColor:'#1fd989',borderDownColor:'#ff5468',wickUpColor:'#1fd989',wickDownColor:'#ff5468'});
    s.setData(CANDLES);
    const L=LightweightCharts.LineStyle, ec=isL?'#1fd989':'#ff5468';
    if(t.entry) s.createPriceLine({price:t.entry,color:ec,lineWidth:1,lineStyle:L.Solid,axisLabelVisible:true,title:'ENTRY'});
    if(t.exit)  s.createPriceLine({price:t.exit,color:'#828ea6',lineWidth:1,lineStyle:L.Dashed,axisLabelVisible:true,title:'EXIT'});
    if(t.tp)    s.createPriceLine({price:t.tp,color:'#1fd989',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'TP'});
    if(t.sl)    s.createPriceLine({price:t.sl,color:'#ff5468',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'SL'});
    const ms=[];
    if(t.ts_entry) ms.push({time:t.ts_entry,position:isL?'belowBar':'aboveBar',color:ec,shape:isL?'arrowUp':'arrowDown',text:'E',size:1.5});
    if(t.ts_exit)  ms.push({time:t.ts_exit,position:isL?'aboveBar':'belowBar',color:isL?'#ff5468':'#1fd989',shape:isL?'arrowDown':'arrowUp',text:'X',size:1.5});
    s.setMarkers(ms);
    setTimeout(()=>{ if(!calChart)return; calChart.applyOptions({width:chartEl.clientWidth,height:chartEl.clientHeight});
      if(t.ts_entry) calChart.timeScale().setVisibleRange({from:t.ts_entry-48*3600,to:(t.ts_exit||t.ts_entry)+24*3600}); },40);
  }
}
load();
"""

import json as _json

CALENDAR_HTML = shell(
    "/calendar", "Calendar", BODY,
    script=(SCRIPT
            .replace("__MISTAKES__", _json.dumps(MISTAKES))
            .replace("__EMOTIONS__", _json.dumps(EMOTIONS))
            .replace("__GRADES__",   _json.dumps(GRADES))),
    head_extra=_CSS, meta="review my trades",
)
