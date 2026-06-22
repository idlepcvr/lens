"""LENS /prop-income — the prop income / FIRE ladder.

A chained goal model: set ONE anchor rung + the fixed step ratios, and every other
rung derives (rent → net/gross salary → net/gross company income → trading capital
/mo → FAT FIRE /mo), plus the Trading AUM required to throw off that monthly
trading capital at a chosen annual return. EUR figures; BTC column tracks a live
(editable) BTCEUR price. This is the PROP-side goal — separate from the hedge goal.

Chain (each rung = ratio × the next bigger rung), from the user's sheet:
  rent          = 0.28  × net salary
  net salary    = 0.80  × gross salary
  gross salary  = 0.30  × net company income
  net company   = 0.875 × gross company income
  gross company = 0.30  × trading capital / mo
  trading cap   = 0.10  × FAT FIRE / mo
  Trading AUM   = trading capital/mo × 12 ÷ annual_return
"""

from .theme import shell

_CSS = r"""<style>
.pi h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pi .sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.pi .controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:14px 16px;margin-bottom:16px}
.pi .ctl{display:flex;flex-direction:column;gap:4px}
.pi .ctl label{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}
.pi .ctl input,.pi .ctl select{background:var(--panel2);border:1px solid var(--line2);color:var(--ink);padding:7px 10px;border-radius:6px;font-family:var(--mono);font-size:13px}
.pi .ctl input:focus,.pi .ctl select:focus{outline:none;border-color:var(--accent)}
.pi .ctl input.calc-on{border-color:var(--amber)!important;color:var(--amber)}
.pi .sb-wrap{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:4px 12px;overflow-x:auto}
.pi table{width:100%;border-collapse:collapse;font-size:13px}
.pi th,.pi td{text-align:right;padding:9px 10px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.pi th{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:500}
.pi th:first-child,.pi td:first-child{text-align:left}
.pi td.lbl{color:var(--ink)} .pi td.dim{color:var(--dim)} .pi td.eur{font-weight:700}
.pi tr.anchor td{background:var(--accent-d)}
.pi tr.anchor td:first-child{border-left:2px solid var(--accent)}
.pi tr.aum td{background:var(--panel2);border-top:1px solid var(--line2)}
.pi tr.aum td:first-child{color:var(--amber)}
.pi .note{color:var(--dim);font-size:12px;margin-top:12px;line-height:1.6}
.pi .note b{color:var(--ink)}
.pi .save{background:var(--accent-d);border:1px solid var(--accent);color:var(--accent);padding:7px 10px;border-radius:6px;font-family:var(--mono);font-size:12px;font-weight:700;cursor:pointer;transition:all .12s}
.pi .save:hover{background:var(--accent);color:#06080c}
.pi .save.ok{background:var(--long);border-color:var(--long);color:#06080c}
.pi .bdg{font-family:var(--mono);font-size:10px;color:var(--accent)}
</style>"""


def income_page() -> str:
    body = r"""
<div class="pi">
  <h1>Prop Income Ladder</h1>
  <div class="sub">The prop goal — what trading is <i>for</i>. Set one anchor; the ladder derives the rest by your fixed step ratios. BTC column tracks the live (editable) BTCEUR price.</div>

  <div class="controls">
    <div class="ctl"><label>Anchor rung</label>
      <select id="anchor">
        <option value="0">Rent</option>
        <option value="1" selected>Net income — salary</option>
        <option value="2">Gross income — salary</option>
        <option value="3">Net company income</option>
        <option value="4">Gross company income</option>
        <option value="5">Trading capital / mo</option>
        <option value="6">FAT FIRE / mo</option>
      </select></div>
    <div class="ctl"><label>Anchor € / mo</label><input id="aval" class="calc" type="text" inputmode="decimal" value="1786"></div>
    <div class="ctl"><label>BTCEUR price</label><input id="btceur" class="calc" type="text" inputmode="decimal" value="54875"></div>
    <div class="ctl"><label>AUM annual return %</label><input id="ret" class="calc" type="text" inputmode="decimal" value="4"></div>
    <div class="ctl"><label>&nbsp;</label><button id="save" class="save">Save ✓</button></div>
  </div>

  <div class="sb-wrap"><table id="ladder"></table></div>
  <div class="note" id="aum-note"></div>
  <div class="note">Ratios (each rung ÷ the next): rent <b>28%</b> · net salary <b>80%</b> · gross salary <b>30%</b> · net company <b>87.5%</b> · gross company <b>30%</b> · trading capital <b>10%</b>. Trading AUM = trading-capital/mo × 12 ÷ annual return. Edit the anchor or any input — everything recomputes.</div>
</div>"""

    script = r"""
const $=id=>document.getElementById(id);
const RUNGS=[
  {label:'Rent',                 r:0.28},
  {label:'Net income — salary',  r:0.80},
  {label:'Gross income — salary',r:0.30},
  {label:'Net company income',   r:0.875},
  {label:'Gross company income', r:0.30},
  {label:'Trading capital / mo', r:0.10},
  {label:'FAT FIRE / mo',        r:null},
];
const eur=v=>'€'+Math.round(v).toLocaleString('en-US');
const btc=(v,p)=> (p>0? (v/p).toFixed(v/p<1?4:3):'—')+' ₿';
const pct=r=> r==null?'—':(r*100).toFixed(r*100%1?1:0)+'%';

function compute(a,V){
  const v=new Array(RUNGS.length);
  v[a]=V;
  for(let i=a+1;i<RUNGS.length;i++) v[i]=v[i-1]/RUNGS[i-1].r;  // up the chain
  for(let i=a-1;i>=0;i--)          v[i]=v[i+1]*RUNGS[i].r;     // down the chain
  return v;
}

function render(){
  const a=parseInt($('anchor').value), V=parseFloat($('aval').value)||0;
  const price=parseFloat($('btceur').value)||0, ret=(parseFloat($('ret').value)||0)/100;
  const v=compute(a,V);
  let rows='<tr><th>rung</th><th>€ / mo</th><th>₿ / mo</th><th>ratio →</th></tr>';
  RUNGS.forEach((R,i)=>{
    rows+=`<tr class="${i===a?'anchor':''}">
      <td class="lbl">${R.label}${i===a?' <span class="bdg">anchor</span>':''}</td>
      <td class="eur">${eur(v[i])}</td>
      <td class="dim">${btc(v[i],price)}</td>
      <td class="dim">${R.r==null?Math.round(1/RUNGS[5].r)+'× trad cap':pct(R.r)}</td></tr>`;
  });
  const cap=v[5];                       // trading capital / mo
  const aum= ret>0 ? cap*12/ret : 0;
  const aumMult= ret>0 ? `×12÷${$('ret').value||0}% = ${Math.round(12/ret)}×` : '∞';
  rows+=`<tr class="aum"><td class="lbl">Trading AUM <span class="bdg">@ ${($('ret').value||0)}%/yr</span></td>
      <td class="eur">${eur(aum)}</td><td class="dim">${btc(aum,price)}</td><td class="dim">${aumMult}</td></tr>`;
  $('ladder').innerHTML=rows;
  $('aum-note').innerHTML = `To draw <b>${eur(cap)}/mo</b> of trading capital at <b>${$('ret').value||0}%</b> annual you need <b>${eur(aum)}</b> (${btc(aum,price)}) under management — that's the prop end-goal the eval scales toward.`;
}

// ── persistence (localStorage — personal tool, no backend round-trip needed) ──
const KEYS=['anchor','aval','btceur','ret'];
(function restore(){ try{ const o=JSON.parse(localStorage.getItem('lens_prop_income')||'{}');
  KEYS.forEach(k=>{ if(o[k]!=null&&o[k]!=='') $(k).value=o[k]; }); }catch(e){} })();
$('save').addEventListener('click',()=>{
  const o={}; KEYS.forEach(k=>o[k]=$(k).value); localStorage.setItem('lens_prop_income',JSON.stringify(o));
  const b=$('save'); b.classList.add('ok'); b.textContent='Saved ✓';
  setTimeout(()=>{ b.classList.remove('ok'); b.textContent='Save ✓'; },1400);
});
KEYS.forEach(id=>$(id).addEventListener('input',render));

// calculator — type 300*0.1 → Enter → 30
document.querySelectorAll('.pi input.calc').forEach(inp=>{
  function tryCalc(){
    const v=inp.value.trim(); if(!v) return;
    try{ const r=Function('"use strict";return('+v.replace(/[^0-9+\-*/.() \t]/g,'')+')')();
      if(isFinite(r)){ inp.value=parseFloat(r.toFixed(8)); inp.classList.remove('calc-on'); render(); } }catch(e){}
  }
  inp.addEventListener('input',()=>inp.classList.toggle('calc-on', /[+*\/]/.test(inp.value)));
  inp.addEventListener('blur',tryCalc);
  inp.addEventListener('keydown',e=>{ if(e.key==='Enter'){ tryCalc(); e.preventDefault(); } });
});
render();
"""
    return shell("/prop-income", "Income", body, script=script, head_extra=_CSS, meta="prop goal")
