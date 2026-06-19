"""LENS /calendar — hedge-book trade calendar.

Monthly P&L heatmap of the hedge trades (book='hedge'). Hover a day for a
transient breakdown, click to pin it, click a trade to open a modal with the
full trade shape + inline review (followed plan/strategy + notes), saved via
PATCH /api/trades/{id}. Native LENS page — reads /api/trades, no cross-app.
"""

from .theme import shell

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
.g{color:var(--long)} .r{color:var(--short)}
.cal-empty{font-size:11px;color:var(--dim);text-align:center;margin-top:24px}
/* modal */
.cal-modal-bg{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.6);backdrop-filter:blur(2px);
  display:flex;align-items:center;justify-content:center;padding:16px}
.cal-modal{width:min(520px,100%);max-height:90vh;overflow-y:auto;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:18px 20px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.cal-modal.long{border-left:4px solid var(--long)} .cal-modal.short{border-left:4px solid var(--short)}
.cal-m-h{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.cal-m-sym{font-size:16px;font-weight:700} .cal-m-pnl{font-size:26px;font-weight:700;font-family:var(--mono);margin-top:2px}
.cal-m-x{font-size:16px;color:var(--dim);background:none;border:none;cursor:pointer}
.cal-m-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px}
.cal-sec{grid-column:1/-1;font-size:10px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;
  margin:6px 0 2px;border-bottom:1px solid var(--line);padding-bottom:4px}
.cal-f .fk{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:1px}
.cal-f .fv{font-size:12px;font-family:var(--mono);font-weight:600}
.cal-tri{display:flex;align-items:center;gap:6px;margin-bottom:8px}
.cal-tri .tl{font-size:11px;color:var(--dim);width:100px;flex:0 0 auto}
.cal-tri button{padding:3px 8px;border-radius:4px;border:1px solid var(--line);font-size:11px;cursor:pointer;
  background:transparent;color:var(--dim)}
.cal-tri button.on-y{border-color:var(--long);background:var(--accent-d);color:var(--long)}
.cal-tri button.on-n{border-color:var(--short);background:var(--accent-d);color:var(--short)}
.cal-tri button.on-x{border-color:var(--line2);background:var(--panel2);color:var(--ink)}
.cal-notes{width:100%;min-height:64px;margin-top:4px;background:var(--panel2);border:1px solid var(--line);
  border-radius:8px;padding:6px 8px;color:var(--ink);font-size:12px;font-family:var(--mono);resize:vertical;outline:none}
.cal-acts{display:flex;gap:8px;margin-top:14px}
.cal-acts .save{flex:1;padding:8px 0;border-radius:6px;border:none;cursor:pointer;background:var(--accent);
  color:var(--bg);font-size:12px;font-weight:700}
.cal-acts .full{padding:8px 14px;border-radius:6px;border:1px solid var(--line);cursor:pointer;background:transparent;
  color:var(--dim);font-size:12px;text-decoration:none;display:flex;align-items:center}
</style>
"""

BODY = """
<div class="cal-sub">Monthly hedge-book heatmap · hover a day, click to pin · click a trade for breakdown & review</div>
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
let TRADES=[], MONTH='', SELDAY=null, HOVDAY=null;
const $=id=>document.getElementById(id);
const eur=(v,d=2)=>(v<0?'-':'')+'€'+Math.abs(v).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});
const usd=(v,d=0)=>v==null?'—':'$'+Number(v).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});
const num=(v,d=2)=>v==null?'—':Number(v).toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d});

async function load(){
  const r=await fetch('/api/trades?limit=2000'); const j=await r.json();
  TRADES=(j.trades||[]).filter(t=>!t.is_open && t.pnl!=null && t.closed_at);
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
    const c=dm[ds];
    const sel=SELDAY===ds?'sel':'';
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
    el.onmouseenter=()=>{HOVDAY=ds;renderSide();};
    el.onmouseleave=()=>{HOVDAY=null;renderSide();};
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
        <div class="sub">${tm}${t.leverage?` · ${t.leverage}×`:''}${t.setup_tag?` · ${t.setup_tag}`:''}</div>
        ${t.notes?`<div class="sub" style="font-style:italic;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.notes}</div>`:''}
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
  let R='—';
  if(t.entry&&t.sl&&t.exit){const rp=Math.abs(t.entry-t.sl),mp=(t.exit-t.entry)*(isL?1:-1); if(rp>0)R=(mp/rp).toFixed(2)+'R';}
  let hold='—';
  if(t.opened_at&&t.closed_at){const ms=new Date(t.closed_at)-new Date(t.opened_at),hh=ms/3.6e6;
    hold=hh>=24?(hh/24).toFixed(1)+'d':hh>=1?hh.toFixed(1)+'h':Math.round(ms/6e4)+'m';}
  const dt=s=>s?new Date(s).toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'—';
  const F=(k,v,cls='')=>`<div class="cal-f"><div class="fk">${k}</div><div class="fv ${cls}">${v}</div></div>`;
  let fp=t.followed_plan??null, fs=t.followed_strategy??null;
  const tri=(label,key,val)=>`<div class="cal-tri" data-key="${key}"><span class="tl">${label}</span>
    <button data-v="null" class="${val===null?'on-x':''}">—</button>
    <button data-v="true" class="${val===true?'on-y':''}">✓ Yes</button>
    <button data-v="false" class="${val===false?'on-n':''}">✗ No</button></div>`;

  $('modal').innerHTML=`<div class="cal-modal-bg" id="mbg"><div class="cal-modal ${isL?'long':'short'}" id="mbox">
    <div class="cal-m-h"><div>
      <div class="cal-m-sym ${isL?'g':'r'}">${isL?'▲ LONG':'▼ SHORT'} ${t.symbol||''}</div>
      <div class="cal-m-pnl ${win?'g':'r'}">${win?'+':''}${eur(Math.abs(t.pnl))}</div>
    </div><button class="cal-m-x" id="mx">✕</button></div>
    <div class="cal-m-grid">
      <div class="cal-sec">Trade Identity</div>
      ${F('Direction',isL?'▲ Long':'▼ Short',isL?'g':'r')}
      ${F('Venue',t.venue||'—')}
      ${F('Setup',t.setup_tag||'—')}
      ${F('Market · Order',`${t.market_type||'—'}${t.order_type?' · '+t.order_type:''}`)}
      <div class="cal-sec">Prices & Sizing</div>
      ${F('Entry → Exit',`${usd(t.entry)} → ${usd(t.exit)}`)}
      ${F('R multiple',R,R.startsWith('-')?'r':(R==='—'?'':'g'))}
      ${F('TP · SL (plan)',`${usd(t.tp)} · ${usd(t.sl)}`)}
      ${F('Size · Lev',`${num(t.size,4)}${t.leverage?' · '+t.leverage+'×':''}`)}
      ${F('P&L',eur(t.pnl),win?'g':'r')}
      ${F('Fees · Funding',`${eur(t.fees||0)} · ${eur(t.funding_cost||0,4)}`,'r')}
      ${F('Bal Before → After',`${eur(t.balance_before||0)} → ${eur(t.balance_after||0)}`)}
      <div class="cal-sec">Timestamps</div>
      ${F('Opened',dt(t.opened_at))}
      ${F('Closed',dt(t.closed_at))}
      ${F('Duration',hold)}
    </div>
    <div class="cal-sec" style="margin-top:14px">Journal & Adherence</div>
    ${tri('Followed Plan?','fp',fp)}
    ${tri('Followed Strat?','fs',fs)}
    <textarea class="cal-notes" id="mnotes" placeholder="Trade notes…">${t.notes||''}</textarea>
    <div class="cal-acts">
      <button class="save" id="msave">💾 Save review</button>
      <a class="full" href="/review">Review page →</a>
    </div>
  </div></div>`;

  const close=()=>{$('modal').innerHTML='';};
  $('mbg').onclick=e=>{if(e.target.id==='mbg')close();};
  $('mx').onclick=close;
  document.onkeydown=e=>{if(e.key==='Escape')close();};
  $('modal').querySelectorAll('.cal-tri').forEach(row=>{
    row.querySelectorAll('button').forEach(b=>b.onclick=()=>{
      const v=b.dataset.v==='null'?null:b.dataset.v==='true';
      if(row.dataset.key==='fp')fp=v; else fs=v;
      row.querySelectorAll('button').forEach(x=>x.className='');
      b.className=v===null?'on-x':v?'on-y':'on-n';
    });
  });
  $('msave').onclick=async()=>{
    $('msave').textContent='Saving…'; $('msave').disabled=true;
    const payload={manually_edited:true,notes:$('mnotes').value||null};
    if(fp!==null)payload.followed_plan=fp; if(fs!==null)payload.followed_strategy=fs;
    try{
      const r=await fetch('/api/trades/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const u=await r.json();
      const idx=TRADES.findIndex(x=>x.id===id); if(idx>=0)TRADES[idx]={...TRADES[idx],...u};
      close(); render();
    }catch(e){console.error(e);$('msave').textContent='Error';$('msave').disabled=false;}
  };
}

load();
"""

CALENDAR_HTML = shell("/calendar", "Calendar", BODY, script=SCRIPT,
                      head_extra=_CSS, meta="when did I trade?")
"""end"""
