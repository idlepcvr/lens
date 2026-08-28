"""LENS /chart-review — the one trade-detail page. Journal is the sortable
log; clicking a row lands here. Used to be two things (journal's small
modal chart, and this page) that both showed a version of the same trade
and disagreed with each other — direct ask: "the review chart and review
should almost be the same." journal_page.py's modal (chart + grading +
notes) is gone; this page now carries all of it, plus what the modal never
had room for.

Multi-timeframe: the timeframe defaults to what would actually have been
on screen while the trade was open — a duration rule (review.auto_timeframe:
1m under 30min, up through 1d for multi-week swings) — with a dropdown to
override. Every fetch is windowed to 100 bars before entry / 30 after exit
(review.get_ohlcv_window and friends), not the whole multi-year history.
1m is a genuine bounded live fetch (backtest_engine.fetch_window) rather
than a rolling cache — one fast request for exactly this trade's ~150
bars, not a backfill, since the earlier "1m is never cached, would be
slow" reasoning was about caching the FULL history, which was never the
actual requirement.

Entry is always a neutral marker (not direction-colored) and exit is
colored by win/loss — one consistent color legend instead of two
different colorings clashing on the same chart.

The verdict badge (grade/emoji/one-liner) is journal's existing
autoReview() computation, ported here and made the first thing on the
page instead of small text buried in a table cell — "if it's not
visually displayed, the [computation] doesn't matter."

Not built here: an LLM-generated narrative per trade (a distinct
integration — which model, on-demand vs cached, cost — wants its own
decision) and a stored, backfilled, cross-trade correlation dataset
(schema + backfill + the same permutation-test discipline as
research/override_miner.py). Both flagged, neither guessed at.
"""
from .theme import shell

TF_SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def render(trade_id: int | None, book: str = "hedge") -> str:
    tf_options = "".join(f'<option value="{tf}">{tf}</option>' for tf in TF_SEC)
    body = f"""
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
  <button class="btn ghost" id="cr-prev">&larr; prev trade</button>
  <span id="cr-title" class="mono" style="font-size:13px;font-weight:700">&mdash;</span>
  <button class="btn ghost" id="cr-next">next trade &rarr;</button>
  <span style="flex:1"></span>
  <span id="cr-auto" class="m" style="font-size:11px"></span>
  <select id="cr-tf" class="mono" style="background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:5px 8px;font-size:12px">
    {tf_options}
  </select>
  <select id="cr-book" class="mono" style="background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:5px 8px;font-size:12px">
    <option value="hedge">hedge</option>
    <option value="prop">prop</option>
  </select>
  <button class="btn ghost" id="cr-fit" title="reset zoom to fit the trade">&#8862; Fit</button>
  <button class="btn ghost" id="cr-log" title="toggle logarithmic price scale">Log</button>
</div>

<div id="cr-verdict"></div>
<div id="cr-critique"></div>

<div id="cr-wrap" style="position:relative">
  <div id="cr-chart" style="height:56vh;min-height:320px;border:1px solid var(--line);border-radius:8px 8px 0 0;border-bottom:0;position:relative"></div>
  <div class="cr-lbl">RSI(14)</div>
  <div id="cr-rsi" style="height:15vh;min-height:100px;border:1px solid var(--line);border-top:1px dashed var(--line2);position:relative"></div>
  <div class="cr-lbl">MACD(12,26,9)</div>
  <div id="cr-macd" style="height:15vh;min-height:100px;border:1px solid var(--line);border-top:1px dashed var(--line2);border-radius:0 0 8px 8px;position:relative;margin-bottom:14px"></div>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb" id="cr-readout">
<tr><th colspan="7">Indicator reading at entry / exit</th></tr>
<tr><th></th><th>price</th><th>RSI(14)</th><th>MACD line</th><th>vs SMA50</th><th>vs SMA100</th><th>vs SMA200</th></tr>
<tr><td>Entry</td><td colspan="6" class="m">load pending&hellip;</td></tr>
<tr><td>Exit</td><td colspan="6" class="m">load pending&hellip;</td></tr>
</table>
</div>

<div id="cr-fields"></div>
"""
    script = f"""
const INIT_TRADE={trade_id if trade_id else 'null'}, INIT_BOOK={book!r};
const TF_SEC={{'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400,'1d':86400}};
const MISTAKES=["chased","early","late","oversized","moved stop","no stop","revenge","FOMO","overheld","cut early","no setup"];
const EMOTIONS=["calm","FOMO","tilt","fear","greed","bored"];
const GRADES=["A","B","C","D","F"];
let TRADES=[], WIN=null, CUR=null, TF=null, MANUAL_TF=false, GOALLVL=null, ST=null, LOGSCALE=false;
const $=id=>document.getElementById(id);

async function boot(){{
  $('cr-book').value=INIT_BOOK;
  GOALLVL=await goalLevels();
  await loadBook(INIT_BOOK);
  const t = INIT_TRADE!=null ? TRADES.find(x=>x.id===INIT_TRADE) : null;
  await show(t || TRADES[TRADES.length-1]);
  $('cr-book').onchange=async()=>{{await loadBook($('cr-book').value);MANUAL_TF=false;await show(TRADES[TRADES.length-1]);}};
  $('cr-tf').onchange=async()=>{{MANUAL_TF=true;TF=$('cr-tf').value;await render();}};
  $('cr-prev').onclick=()=>step(-1);
  $('cr-next').onclick=()=>step(1);
  $('cr-fit').onclick=()=>charts.forEach(c=>c.timeScale().fitContent());
  $('cr-log').onclick=()=>{{LOGSCALE=!LOGSCALE;$('cr-log').classList.toggle('on',LOGSCALE);render();}};
}}

async function goalLevels(){{
  try{{
    const cfg=await fetch('/api/config').then(r=>r.json());
    const g=await fetch('/api/goal',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(cfg)}}).then(r=>r.json());
    if(g&&g.underlying_win_pct!=null) return {{tp:g.underlying_win_pct/100, sl:g.underlying_loss_pct/100, rr:g.actual_rr}};
  }}catch(e){{}}
  return null;
}}

async function loadBook(book){{
  const tr=await fetch('/api/review/trades?book='+book);
  TRADES=(await tr.json()).filter(t=>t.pnl!=null && t.ts_entry).sort((a,b)=>a.ts_entry-b.ts_entry);
  computeAutoGrades();
}}

function step(d){{
  if(!CUR)return;
  const i=TRADES.findIndex(t=>t.id===CUR.id);
  const n=TRADES[i+d];
  if(n){{MANUAL_TF=false;show(n);}}
}}

// ── carried over from journal_page.py's modal (now the only home for it) ──
function computeAutoGrades(){{
  const wins=TRADES.filter(t=>(t.pnl||0)>0).map(t=>({{t,r:rVal(t)}})).sort((a,b)=>b.r-a.r);
  const los =TRADES.filter(t=>(t.pnl||0)<=0).map(t=>({{t,r:rVal(t)}})).sort((a,b)=>b.r-a.r);
  wins.forEach((x,i)=>{{ const p=wins.length?i/wins.length:0; x.t._ag=p<0.20?'A':p<0.50?'B':'C'; }});
  los.forEach((x,i)=>{{ const p=los.length?i/los.length:0; x.t._ag=p<0.40?'C':p<0.80?'D':'F'; }});
}}
function rOf(t){{ if(t.entry&&t.sl&&t.exit){{const rp=Math.abs(t.entry-t.sl),mp=(t.exit-t.entry)*(t.direction==='long'?1:-1); if(rp>0)return mp/rp;}} return null; }}
function rVal(t){{
  let r=rOf(t);
  if(r==null && GOALLVL && GOALLVL.sl && t.entry && t.exit){{
    const rp=t.entry*GOALLVL.sl, mp=(t.exit-t.entry)*(t.direction==='long'?1:-1);
    if(rp>0) r=mp/rp;
  }}
  return r??0;
}}
function planLvl(t){{
  if(!GOALLVL||!t.entry) return {{tp:null,sl:null}};
  const L=t.direction==='long';
  return {{tp:t.entry*(1+(L?1:-1)*GOALLVL.tp), sl:t.entry*(1-(L?1:-1)*GOALLVL.sl)}};
}}
function durOf(t){{ if(t.ts_entry&&t.ts_exit){{const m=(t.ts_exit-t.ts_entry)/60; return m>=1440?(m/1440).toFixed(1)+'d':m>=60?(m/60).toFixed(1)+'h':Math.round(m)+'m';}} return '&mdash;'; }}
function isManual(t){{ return !!(t.grade||t.went_right||t.went_wrong||t.lesson||t.mistakes||t.emotion||t.conviction!=null||t.followed_plan!=null||t.followed_strategy!=null); }}
function autoReview(t){{
  const win=(t.pnl||0)>0, ta=t.trend_aligned, r=rVal(t), grade=t._ag||'C';
  const rtxt=r?` ${{(r>=0?'+':'')+r.toFixed(1)}}R`:'';
  const imp=(t.pnl!=null&&t.balance_before)?Math.abs(t.pnl/t.balance_before*100):null;
  const bits=[];
  if(win) bits.push((grade==='A'?'Top winner':grade==='B'?'Good win':'Modest win')+rtxt);
  else bits.push((grade==='F'?'Worst-tier loss':grade==='D'?'Heavy loss':'Contained loss')+rtxt+(imp!=null?` &middot; ${{imp.toFixed(0)}}% of acct`:''));
  if(ta===true)bits.push('with 4H trend'); else if(ta===false)bits.push('counter-trend');
  if(t.rsi_zone)bits.push('RSI '+t.rsi_zone);
  const emoji={{A:'\\ud83d\\udfe2',B:'\\ud83d\\udfe9',C:'\\ud83d\\udfe1',D:'\\ud83d\\udfe0',F:'\\ud83d\\udd34'}}[grade]||'\\u26aa';
  return {{grade,emoji,take:bits.join(' &middot; ')}};
}}

function renderVerdict(t){{
  const win=(t.pnl||0)>=0, ar=autoReview(t);
  $('cr-verdict').innerHTML=`
    <div class="sb-wrap" style="margin-bottom:12px;padding:12px 16px;display:flex;align-items:center;gap:14px;border-left:4px solid ${{win?'var(--long)':'var(--short)'}}">
      <span style="font-size:26px">${{ar.emoji}}</span>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:800;color:${{win?'var(--long)':'var(--short)'}}">${{t.grade||ar.grade}} &mdash; ${{ar.take}}</div>
        <div class="m" style="font-size:11px;margin-top:2px">${{isManual(t)?'reviewed by you':'auto — grade it below to override'}}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:18px;font-weight:800" class="${{win?'g':'r'}}">${{eur(t.pnl)}}</div>
        <div class="m" style="font-size:11px">${{durOf(t)}} &middot; ${{(t.direction||'').toUpperCase()}}</div>
      </div>
    </div>
    <div id="cr-veto"></div>`;
  fetch('/api/veto-overrides/for-trade?trade_id='+t.id).then(r=>r.json()).then(d=>{{
    if(!d.override) return;
    const o=d.override;
    $('cr-veto').innerHTML=`<div class="sb-wrap" style="margin-bottom:12px;padding:10px 14px;border-left:3px solid var(--accent)">
      <b style="color:var(--accent)">&#9888; Taken against the scanner</b>
      ${{o.veto_reasons&&o.veto_reasons.length?` &middot; scanner said: <span class="m">${{o.veto_reasons.join(', ')}}</span>`:''}}
      <div style="margin-top:5px;font-size:12.5px">${{(o.user_reason||'').replace(/</g,'&lt;')}}</div>
    </div>`;
  }}).catch(()=>{{}});
}}

// nearest indicator sample at or before a given unix time
function sampleAt(ts){{
  if(!WIN||!WIN.indicators||!ts)return null;
  const ind=WIN.indicators, arr=ind.time;
  let lo=0,hi=arr.length-1,idx=-1;
  while(lo<=hi){{const mid=(lo+hi)>>1; if(arr[mid]<=ts){{idx=mid;lo=mid+1;}}else hi=mid-1;}}
  if(idx<0)return null;
  return {{rsi:ind.rsi14[idx], macd:ind.macd_line[idx], macd_sig:ind.macd_signal[idx],
          sma50:ind.sma50[idx], sma100:ind.sma100[idx], sma200:ind.sma200[idx],
          bb_up:ind.bb_upper[idx], bb_lo:ind.bb_lower[idx]}};
}}

// ── automated context/critique — "what could we have looked at" instead of
// a blank reflection box. Deterministic, from indicators/levels already
// fetched for this trade (no LLM call, no extra request). One read per
// point (entry/exit): RSI zone, MACD cross state, SMA trend stack, Bollinger
// position, nearest support/resistance flip — then a confluence count so
// "was this a good entry" has a number behind it, not just a feeling.
function nearestLevel(price){{
  if(!WIN||!WIN.levels||!WIN.levels.length||!price) return null;
  let best=null,bd=Infinity;
  WIN.levels.forEach(f=>{{const d=Math.abs(f.level-price)/price; if(d<bd){{bd=d;best=f;}}}});
  return best?{{...best,dist:bd}}:null;
}}
function readPoint(price,s,dir){{
  if(!s) return {{bits:[],score:null}};
  const bits=[], L=dir==='long';
  const rsiZone=s.rsi==null?null:s.rsi>=70?'overbought':s.rsi<=30?'oversold':'neutral';
  if(s.rsi!=null) bits.push(`RSI ${{s.rsi.toFixed(0)}} (${{rsiZone}})`);
  const rsiOk = s.rsi==null?null: L? s.rsi<70 : s.rsi>30;   // not already exhausted your way
  const macdBull = s.macd!=null && s.macd_sig!=null ? s.macd>s.macd_sig : null;
  if(macdBull!=null) bits.push(`MACD ${{macdBull?'bullish':'bearish'}} (line ${{s.macd.toFixed(0)}} vs signal ${{s.macd_sig.toFixed(0)}})`);
  const macdOk = macdBull==null?null: L?macdBull:!macdBull;
  const stackBull = s.sma50!=null&&s.sma100!=null&&s.sma200!=null ? (s.sma50>s.sma100&&s.sma100>s.sma200) : null;
  const stackBear = s.sma50!=null&&s.sma100!=null&&s.sma200!=null ? (s.sma50<s.sma100&&s.sma100<s.sma200) : null;
  if(stackBull!=null) bits.push(`SMA stack ${{stackBull?'bullish':stackBear?'bearish':'mixed'}}`);
  const stackOk = stackBull==null?null: L?stackBull:stackBear;
  let bbBit=null;
  if(s.bb_up!=null&&price!=null){{
    bbBit = price>s.bb_up?'above upper Bollinger band (extended)':price<s.bb_lo?'below lower Bollinger band (extended)':'inside Bollinger bands';
    bits.push(bbBit);
  }}
  const lvl=nearestLevel(price);
  let lvlOk=null;
  if(lvl){{
    const dir2=lvl.kind==='r2s'?'flipped support':'flipped resistance';
    bits.push(`nearest level ${{lvl.level.toFixed(0)}} (${{dir2}}, ${{(lvl.dist*100).toFixed(2)}}% away)`);
    // a flipped-support level below you (long) or flipped-resistance above you (short) is in your favour
    if(lvl.dist<0.01) lvlOk = L ? lvl.kind==='r2s' : lvl.kind==='s2r';
  }}
  const flags=[rsiOk,macdOk,stackOk,lvlOk].filter(x=>x!=null);
  const score = flags.length ? flags.filter(Boolean).length+'/'+flags.length : null;
  return {{bits,score}};
}}
function autoCritique(t){{
  if(!t.ts_entry) return '';
  const en=readPoint(t.entry,sampleAt(t.ts_entry),t.direction);
  const ex=t.ts_exit?readPoint(t.exit,sampleAt(t.ts_exit),t.direction):null;
  const fillNote = t.fill_count>2 ? `<div class="m" style="margin-top:6px">Built across ${{t.fill_count}} fills — scaled in/out, not one clean entry/exit.</div>` : '';
  const entryLine = en.bits.length
    ? `<div><b>Entry context</b>${{en.score?` &middot; <span style="color:${{en.score.split('/')[0]===en.score.split('/')[1]?'var(--long)':en.score[0]==='0'?'var(--short)':'var(--amber)'}}">${{en.score}} aligned</span>`:''}}</div>
       <div class="m" style="margin:3px 0 8px">${{en.bits.join(' &middot; ')}}</div>`
    : '<div class="m">No indicator data at entry time.</div>';
  const exitLine = ex && ex.bits.length
    ? `<div><b>Exit context</b>${{ex.score?` &middot; <span style="color:${{ex.score.split('/')[0]===ex.score.split('/')[1]?'var(--long)':ex.score[0]==='0'?'var(--short)':'var(--amber)'}}">${{ex.score}} still aligned</span>`:''}}</div>
       <div class="m" style="margin:3px 0 0">${{ex.bits.join(' &middot; ')}}</div>`
    : '';
  return `<div class="sb-wrap" style="margin-bottom:12px;padding:12px 16px">
    <div style="font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Automated — computed from this trade's own chart, not typed by you</div>
    ${{entryLine}}${{exitLine}}${{fillNote}}
  </div>`;
}}
const pf=v=>v==null?'&mdash;':v.toFixed(1);
const dpct=(price,ma)=>ma==null?'&mdash;':(((price-ma)/ma*100).toFixed(2)+'%');

function fillReadout(t){{
  const en=sampleAt(t.ts_entry), ex=sampleAt(t.ts_exit);
  const row=(lbl,price,s)=>s?`<tr><td>${{lbl}}</td><td class="mono">${{price?price.toFixed(0):'&mdash;'}}</td>`+
    `<td class="mono">${{pf(s.rsi)}}</td><td class="mono">${{pf(s.macd)}}</td>`+
    `<td class="mono">${{dpct(price,s.sma50)}}</td><td class="mono">${{dpct(price,s.sma100)}}</td>`+
    `<td class="mono">${{dpct(price,s.sma200)}}</td></tr>`
    : `<tr><td>${{lbl}}</td><td colspan="6" class="m">no indicator data for this time</td></tr>`;
  document.querySelectorAll('#cr-readout tr').forEach((tr,i)=>{{if(i>=2)tr.remove();}});
  $('cr-readout').insertAdjacentHTML('beforeend', row('Entry', t.entry, en)+row('Exit', t.exit, ex));
}}

// ── grading panel (moved from journal_page.py's modal) ──────────────────
function renderFields(t){{
  ST={{grade:t.grade||null,conviction:t.conviction||null,emotion:t.emotion||null,
      mistakes:new Set((t.mistakes||'').split(',').map(s=>s.trim()).filter(Boolean)),
      fp:t.followed_plan??null,fs:t.followed_strategy??null}};
  const inp=(id,v,ph)=>`<input id="${{id}}" type="number" step="any" value="${{v??''}}" ${{ph!=null?`placeholder="${{ph}}" title="expected from Goal plan — type to store on the trade"`:''}}>`;
  const plan=planLvl(t);
  const fld=(k,inner)=>`<div class="bm-fld"><div class="k">${{k}}</div>${{inner}}</div>`;
  const fv=(k,v,c)=>`<div class="bm-fld"><div class="k">${{k}}</div><div class="v ${{c||''}}">${{v}}</div></div>`;
  const optrow=(lbl,key,opts,cur,cls)=>`<div class="pickrow" data-key="${{key}}"><span class="pl">${{lbl}}</span>`+
    opts.map(o=>`<button class="opt ${{cls||''}} ${{String(cur)===String(o)?'on':''}}" data-v="${{o}}">${{o}}</button>`).join('')+`</div>`;
  const tri=(lbl,key,val)=>`<div class="pickrow" data-key="${{key}}"><span class="pl">${{lbl}}</span>
    <button class="opt ${{val===null?'on':''}}" data-v="null">&mdash;</button>
    <button class="opt ${{val===true?'on':''}}" data-v="true">&check; Yes</button>
    <button class="opt ${{val===false?'on':''}}" data-v="false">&cross; No</button></div>`;
  const miss=`<div class="pickrow" id="missrow"><span class="pl">Mistakes</span>`+
    MISTAKES.map(m=>`<button class="opt miss ${{ST.mistakes.has(m)?'on':''}}" data-m="${{m}}">${{m}}</button>`).join('')+`</div>`;
  const r=rOf(t), R=r==null?'&mdash;':(r>=0?'+':'')+r.toFixed(2)+'R';
  $('cr-fields').innerHTML=`
    <div class="bm-cols">
      <div class="bm-grid">
        ${{fld('Entry $',inp('f-entry',t.entry))}}${{fld('Exit $',inp('f-exit',t.exit))}}
        ${{fld('TP $',inp('f-tp',t.tp,plan.tp!=null?plan.tp.toFixed(0):null))}}${{fld('SL $',inp('f-sl',t.sl,plan.sl!=null?plan.sl.toFixed(0):null))}}
        ${{fld('Size',inp('f-size',t.size))}}${{fld('Lev ×',inp('f-lev',t.leverage))}}
        ${{fld('P&L €',inp('f-pnl',t.pnl))}}${{fld('Fees €',inp('f-fees',t.fees))}}
        ${{fv('R multiple',R,r==null?'dim':r>=0?'g':'r')}}${{fv('Duration',durOf(t))}}
        ${{fv('Bal before',t.balance_before!=null?eur(t.balance_before).replace(/^[+]/,''):'&mdash;','dim')}}${{fv('Bal after',t.balance_after!=null?eur(t.balance_after).replace(/^[+]/,''):'&mdash;',t.balance_after!=null&&t.balance_before!=null?(t.balance_after>=t.balance_before?'g':'r'):'')}}
        ${{fv('Notional',t.entry&&t.size?'$'+Math.round(t.entry*t.size).toLocaleString('en'):'&mdash;','dim')}}${{fv('Acct impact',t.pnl!=null&&t.balance_before?((t.pnl/t.balance_before*100>=0?'+':'')+(t.pnl/t.balance_before*100).toFixed(2)+'%'):'&mdash;',t.pnl>=0?'g':'r')}}
      </div>
      <div class="cols-cond">
        ${{fv('Entry bar',t.bar_dir?t.bar_dir.toUpperCase()+(t.bar_aligned?' &check;':' &cross;'):'&mdash;',t.bar_dir?(t.bar_aligned?'g':'r'):'')}}
        ${{fv('4H trend',t.trend_4h?t.trend_4h.toUpperCase()+(t.trend_aligned?' &check;':' &cross;'):'&mdash;',t.trend_4h?(t.trend_aligned?'g':'r'):'')}}
        ${{fv('RSI @ entry',t.rsi!=null?t.rsi+' '+(t.rsi_zone||''):'&mdash;')}}
        ${{fv('Move %',t.move_pct!=null?t.move_pct+'%':'&mdash;',(t.move_pct||0)>=0?'g':'r')}}
        ${{fv('Funding €',t.funding_cost!=null?eur(-t.funding_cost):'&mdash;','dim')}}
        ${{fv('Venue',({{kraken_futures:'Kraken',bybit:'Bybit',manual:'Manual'}})[t.venue]||t.venue||'&mdash;','dim')}}
      </div>
    </div>
    <div class="bm-sec">Your review</div>
    ${{optrow('Grade','grade',GRADES,ST.grade,'grade')}}
    ${{optrow('Conviction','conviction',[1,2,3,4,5],ST.conviction)}}
    ${{optrow('Emotion','emotion',EMOTIONS,ST.emotion)}}
    ${{miss}}
    ${{tri('Followed plan?','fp',ST.fp)}}
    ${{tri('Followed strat?','fs',ST.fs)}}
    <div class="bm-sec">Reflection</div>
    <div class="refl">
      <textarea id="bm-right" placeholder="what went right…">${{t.went_right||''}}</textarea>
      <textarea id="bm-wrong" placeholder="what went wrong…">${{t.went_wrong||''}}</textarea>
      <textarea id="bm-lesson" placeholder="lesson…">${{t.lesson||''}}</textarea>
    </div>
    <textarea id="bm-notes" placeholder="notes…">${{t.notes||''}}</textarea>
    <div><button class="bm-save" id="msave">&#128190; Save review</button></div>
  `;
  const pv=s=>s==='null'?null:s==='true'?true:s==='false'?false:s;
  $('cr-fields').querySelectorAll('.pickrow[data-key]').forEach(row=>{{
    const key=row.dataset.key, isTri=key==='fp'||key==='fs';
    row.querySelectorAll('.opt[data-v]').forEach(b=>b.onclick=()=>{{
      const v=pv(b.dataset.v); ST[key]=(!isTri&&String(ST[key])===String(v))?null:v;
      row.querySelectorAll('.opt[data-v]').forEach(x=>x.classList.toggle('on',String(ST[key])===String(pv(x.dataset.v))));
    }});
  }});
  $('missrow').querySelectorAll('.opt').forEach(b=>b.onclick=()=>{{const m=b.dataset.m;
    if(ST.mistakes.has(m)){{ST.mistakes.delete(m);b.classList.remove('on');}}else{{ST.mistakes.add(m);b.classList.add('on');}}}});
  $('msave').onclick=async()=>{{
    $('msave').textContent='Saving…';$('msave').disabled=true;
    const nf=id=>{{const v=parseFloat($(id).value);return isNaN(v)?undefined:v;}};
    const p={{manually_edited:true,entry:nf('f-entry'),exit:nf('f-exit'),tp:nf('f-tp'),sl:nf('f-sl'),
      size:nf('f-size'),leverage:nf('f-lev'),pnl:nf('f-pnl'),fees:nf('f-fees'),
      mistakes:[...ST.mistakes].join(',')||undefined,went_right:$('bm-right').value||undefined,
      went_wrong:$('bm-wrong').value||undefined,lesson:$('bm-lesson').value||undefined,notes:$('bm-notes').value||undefined}};
    if(ST.grade!=null)p.grade=ST.grade; if(ST.conviction!=null)p.conviction=ST.conviction; if(ST.emotion!=null)p.emotion=ST.emotion;
    if(ST.fp!==null)p.followed_plan=ST.fp; if(ST.fs!==null)p.followed_strategy=ST.fs;
    Object.keys(p).forEach(k=>p[k]===undefined&&delete p[k]);
    try{{
      const r=await fetch('/api/trades/'+t.id,{{method:'PATCH',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(p)}});
      const u=await r.json(); Object.assign(t,u);
      $('msave').textContent='\\u2713 Saved';
      renderVerdict(t);
      setTimeout(()=>{{$('msave').textContent='\\ud83d\\udcbe Save review';$('msave').disabled=false;}},1200);
    }}catch(e){{console.error(e);$('msave').textContent='Error';$('msave').disabled=false;}}
  }};
}}

let charts=[];
function vMarker(container, chart, time, label, color, tfSec){{
  const line=document.createElement('div');
  line.style.cssText=`position:absolute;top:0;bottom:0;width:1px;background:${{color}};pointer-events:none;z-index:5`;
  const lbl=document.createElement('div');
  lbl.style.cssText=`position:absolute;top:2px;font-size:9px;font-family:var(--mono);color:${{color}};background:#06080ccc;padding:1px 4px;border-radius:3px;white-space:nowrap;pointer-events:none;z-index:6;transform:translateX(3px)`;
  lbl.textContent=label;
  container.appendChild(line); container.appendChild(lbl);
  // timeToCoordinate only resolves EXACT bar times — snap to this
  // timeframe's bar grid for the lookup; the label keeps the real time.
  const snapped=Math.floor(time/tfSec)*tfSec;
  let tries=0;
  function reposition(){{
    const x=chart.timeScale().timeToCoordinate(snapped);
    if(x===null){{
      line.style.display=lbl.style.display='none';
      if(tries++<20) setTimeout(reposition,100);
      return;
    }}
    line.style.display=lbl.style.display='block';
    line.style.left=x+'px'; lbl.style.left=x+'px';
  }}
  reposition();
  chart.timeScale().subscribeVisibleTimeRangeChange(reposition);
  return reposition;
}}

function toLine(times,vals){{const o=[];for(let i=0;i<times.length;i++)if(vals[i]!=null)o.push({{time:times[i],value:vals[i]}});return o;}}

async function show(t){{
  if(!t)return; CUR=t;
  $('cr-title').textContent=(t.direction||'').toUpperCase()+' #'+t.id+' · '+eur(t.pnl)+' · '+(t.opened_at||'').slice(0,16).replace('T',' ');
  renderVerdict(t);
  renderFields(t);
  if(!MANUAL_TF){{
    const r=await fetch('/api/review/auto-timeframe?entry='+t.ts_entry+(t.ts_exit?'&exit='+t.ts_exit:'')).then(r=>r.json());
    TF=r.timeframe;
  }}
  $('cr-tf').value=TF;
  await render();
}}

async function render(){{
  const t=CUR; if(!t)return;
  $('cr-auto').textContent=MANUAL_TF?'':'(auto, from trade duration)';
  charts.forEach(c=>{{try{{c.remove();}}catch(e){{}}}}); charts=[];
  document.querySelectorAll('#cr-chart,#cr-rsi,#cr-macd').forEach(el=>{{
    [...el.querySelectorAll('div')].forEach(d=>d.remove());
  }});
  try{{
    WIN=await fetch('/api/review/window?tf='+TF+'&entry='+t.ts_entry+(t.ts_exit?'&exit='+t.ts_exit:'')).then(r=>r.json());
  }}catch(e){{WIN=null;}}
  fillReadout(t);   // after WIN loads — sampleAt() reads WIN.indicators
  $('cr-critique').innerHTML=autoCritique(t);   // same reason — needs WIN.levels too
  if(!window.LightweightCharts || !WIN || !WIN.ohlcv || !WIN.ohlcv.length)return;
  const CANDLES=WIN.ohlcv, INDICATORS=WIN.indicators, LEVELS=WIN.levels, tfSec=TF_SEC[TF];
  const L=LightweightCharts.LineStyle;
  const dark={{background:{{color:'#06080c'}},textColor:'#465064',attributionLogo:false}},
        grid={{vertLines:{{color:'#192232'}},horzLines:{{color:'#192232'}}}};
  const ENTRY_COLOR='#5b9dff';   // always neutral — direction is already in the title
  const EXIT_COLOR=t.pnl>=0?'#1fd989':'#ff5468';   // win/loss, the thing that matters

  // price
  const pEl=$('cr-chart');
  const pChart=LightweightCharts.createChart(pEl,{{layout:dark,grid,
    rightPriceScale:{{borderColor:'#192232',mode:LOGSCALE?1:0}},
    timeScale:{{borderColor:'#192232',timeVisible:true,secondsVisible:false}}}});
  charts.push(pChart);
  const cs=pChart.addCandlestickSeries({{upColor:'#1fd989',downColor:'#ff5468',borderUpColor:'#1fd989',borderDownColor:'#ff5468',wickUpColor:'#1fd989',wickDownColor:'#ff5468',lastValueVisible:false}});
  cs.setData(CANDLES);
  if(t.tp)cs.createPriceLine({{price:t.tp,color:'#1fd989',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'TP'}});
  if(t.sl)cs.createPriceLine({{price:t.sl,color:'#ff5468',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'SL'}});
  if(INDICATORS){{
    const it=INDICATORS.time;
    // an SMA with <40% coverage of this window (e.g. SMA200 on a short
    // trade) still starts abruptly mid-chart — dim it so that reads as
    // "fading in from insufficient history" instead of a broken line
    const cov=vals=>vals.filter(v=>v!=null).length/vals.length;
    const smaLine=(vals,color)=>pChart.addLineSeries({{color:cov(vals)<0.4?color+'55':color,lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,vals));
    smaLine(INDICATORS.sma50,'#f6ad3c');
    smaLine(INDICATORS.sma100,'#5b9dff');
    smaLine(INDICATORS.sma200,'#ff5468');
    pChart.addLineSeries({{color:'#465064',lineWidth:1,lineStyle:L.Dotted,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.bb_upper));
    pChart.addLineSeries({{color:'#465064',lineWidth:1,lineStyle:L.Dotted,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.bb_lower));
  }}
  if(LEVELS && LEVELS.length){{
    // dedupe near-identical levels (flips that clustered within 0.3%) before
    // picking nearest — otherwise 3 near-duplicates eat all 4 label slots
    const kept=[];
    LEVELS.sort((a,b)=>Math.abs(a.level-t.entry)-Math.abs(b.level-t.entry)).forEach(f=>{{
      if(!kept.some(k=>Math.abs(k.level-f.level)/f.level<0.003)) kept.push(f);
    }});
    // only 4 labels ever draw (2 nearest each side) — the rest still mark
    // the level but stay label-free so they don't stack on the price axis
    kept.slice(0,12).forEach((f,i)=>{{
      const isR2S=f.kind==='r2s', showLabel=i<4;
      cs.createPriceLine({{price:f.level,color:isR2S?'#1fd98999':'#ff546899',lineWidth:1,
        lineStyle:L.Dashed,axisLabelVisible:showLabel,title:showLabel?(isR2S?'R\\u2192S':'S\\u2192R'):''}});
    }});
  }}

  // RSI
  const rEl=$('cr-rsi');
  const rChart=LightweightCharts.createChart(rEl,{{layout:dark,grid,rightPriceScale:{{borderColor:'#192232'}},timeScale:{{borderColor:'#192232',timeVisible:true,secondsVisible:false,visible:false}}}});
  charts.push(rChart);
  if(INDICATORS){{
    const rs=rChart.addLineSeries({{color:'#5b9dff',lineWidth:1,priceLineVisible:false,lastValueVisible:true}});
    rs.setData(toLine(INDICATORS.time,INDICATORS.rsi14));
    rs.createPriceLine({{price:70,color:'#ff5468',lineWidth:1,lineStyle:L.Dashed,axisLabelVisible:false}});
    rs.createPriceLine({{price:30,color:'#1fd989',lineWidth:1,lineStyle:L.Dashed,axisLabelVisible:false}});
  }}

  // MACD
  const mEl=$('cr-macd');
  const mChart=LightweightCharts.createChart(mEl,{{layout:dark,grid,rightPriceScale:{{borderColor:'#192232'}},timeScale:{{borderColor:'#192232',timeVisible:true,secondsVisible:false}}}});
  charts.push(mChart);
  if(INDICATORS){{
    mChart.addHistogramSeries({{priceLineVisible:false,lastValueVisible:false}})
      .setData(INDICATORS.macd_hist.map((v,i)=>v==null?null:{{time:INDICATORS.time[i],value:v,color:v>=0?'#1fd98966':'#ff546866'}}).filter(Boolean));
    mChart.addLineSeries({{color:'#5b9dff',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(INDICATORS.time,INDICATORS.macd_line));
    mChart.addLineSeries({{color:'#f6ad3c',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(INDICATORS.time,INDICATORS.macd_signal));
  }}

  setTimeout(()=>{{
    [[pChart,pEl],[rChart,rEl],[mChart,mEl]].forEach(([c,el])=>{{
      c.applyOptions({{width:el.clientWidth,height:el.clientHeight}});
      // data is already windowed to this trade server-side — fit it all,
      // no manual range math that can drift out of sync with the fetch.
      c.timeScale().fitContent();
    }});
    setTimeout(()=>{{
      if(t.ts_entry){{
        vMarker(pEl,pChart,t.ts_entry,'ENTRY '+t.entry.toFixed(0)+' \\u00b7 '+new Date(t.ts_entry*1000).toISOString().slice(11,16),ENTRY_COLOR,tfSec);
        vMarker(rEl,rChart,t.ts_entry,'',ENTRY_COLOR,tfSec);
        vMarker(mEl,mChart,t.ts_entry,'',ENTRY_COLOR,tfSec);
      }}
      if(t.ts_exit){{
        vMarker(pEl,pChart,t.ts_exit,'EXIT '+t.exit.toFixed(0)+' \\u00b7 '+new Date(t.ts_exit*1000).toISOString().slice(11,16),EXIT_COLOR,tfSec);
        vMarker(rEl,rChart,t.ts_exit,'',EXIT_COLOR,tfSec);
        vMarker(mEl,mChart,t.ts_exit,'',EXIT_COLOR,tfSec);
      }}
    }},80);
  }},60);
}}
function eur(v){{return (v>=0?'+':'\\u2212')+'\\u20ac'+Math.abs(v).toFixed(2);}}
boot();
"""
    css = """<style>
#cr-log.on{border-color:var(--accent);background:var(--accent);color:var(--bg);font-weight:700}
.cr-lbl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;padding:2px 8px;border:1px solid var(--line);border-top:0;border-bottom:0;background:var(--panel)}
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
@media(max-width:640px){.bm-cols{grid-template-columns:1fr}.bm-grid{grid-template-columns:repeat(2,1fr)}.refl{grid-template-columns:1fr}}
</style>"""
    head = ('<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>' + css)
    return shell("/chart-review", "Chart review", body, script=script, head_extra=head,
                 meta="entry/exit against RSI, MACD, SMA stack, levels")
