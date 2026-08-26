"""LENS /chart-review — full-size chart review, pulled out of the journal
modal because there was no room to show RSI/MACD/levels without squashing
every pane unreadable (2026-08-27, direct ask: "why did you put it on
journal... make it significantly bigger").

Price + SMA/Bollinger/levels in one large pane, RSI and MACD each get
their own full-height pane below. Entry/exit are vertical time-markers
with a label (time + price) beside them, on all three panes at once —
not the small arrow+letter markers the journal modal still uses for its
quick preview.

Below the charts: the actual indicator readings AT entry and exit (RSI,
MACD, distance from each SMA) — so a pattern between the readings and
win/loss is at least visible by eye. Not yet a stored, backfilled,
correlation-tested dataset; see the module docstring in app/levels.py for
the same caveat applied here.
"""
from .theme import shell


def render(trade_id: int | None, book: str = "hedge") -> str:
    body = f"""
<div class="help-body" style="margin-bottom:12px">
<h4>What this page shows</h4>
<p>Price with the SMA 50/100/200 trend-confidence stack and Bollinger(20,2)
overlaid, resistance/support flips drawn as horizontal levels, and RSI(14) +
MACD(12,26,9) each in their own full-size pane below. Entry and exit are
vertical lines with the time and price labelled beside them on every pane.
The table under the charts reads off what each indicator actually was at
entry and exit — eyeballing it for now, not yet run through a permutation
test the way the veto-combo work was.</p>
</div>

<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
  <button class="btn ghost" id="cr-prev">&larr; prev trade</button>
  <span id="cr-title" class="mono" style="font-size:13px;font-weight:700">&mdash;</span>
  <button class="btn ghost" id="cr-next">next trade &rarr;</button>
  <span style="flex:1"></span>
  <select id="cr-book" class="mono" style="background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:5px 8px;font-size:12px">
    <option value="hedge">hedge</option>
    <option value="prop">prop</option>
  </select>
</div>

<div id="cr-wrap" style="position:relative">
  <div id="cr-chart" style="height:58vh;min-height:340px;border:1px solid var(--line);border-radius:8px 8px 0 0;border-bottom:0;position:relative"></div>
  <div class="cr-lbl">RSI(14)</div>
  <div id="cr-rsi" style="height:16vh;min-height:110px;border:1px solid var(--line);border-top:1px dashed var(--line2);position:relative"></div>
  <div class="cr-lbl">MACD(12,26,9)</div>
  <div id="cr-macd" style="height:16vh;min-height:110px;border:1px solid var(--line);border-top:1px dashed var(--line2);border-radius:0 0 8px 8px;position:relative;margin-bottom:14px"></div>
</div>

<div class="sb-wrap" style="margin-bottom:12px">
<table class="sb" id="cr-readout">
<tr><th colspan="7">Indicator reading at entry / exit</th></tr>
<tr><th></th><th>price</th><th>RSI(14)</th><th>MACD line</th><th>vs SMA50</th><th>vs SMA100</th><th>vs SMA200</th></tr>
<tr><td>Entry</td><td colspan="6" class="m">load pending&hellip;</td></tr>
<tr><td>Exit</td><td colspan="6" class="m">load pending&hellip;</td></tr>
</table>
</div>
"""
    script = f"""
const INIT_TRADE={trade_id if trade_id else 'null'}, INIT_BOOK={book!r};
let TRADES=[], CANDLES=[], INDICATORS=null, LEVELS=[], CUR=null;
const $=id=>document.getElementById(id);

async function boot(){{
  $('cr-book').value=INIT_BOOK;
  await loadBook(INIT_BOOK);
  const t = INIT_TRADE!=null ? TRADES.find(x=>x.id===INIT_TRADE) : null;
  show(t || TRADES[TRADES.length-1]);
  $('cr-book').onchange=async()=>{{await loadBook($('cr-book').value);show(TRADES[TRADES.length-1]);}};
  $('cr-prev').onclick=()=>step(-1);
  $('cr-next').onclick=()=>step(1);
}}

async function loadBook(book){{
  const [tr,ca,ind,lv]=await Promise.all([
    fetch('/api/review/trades?book='+book), fetch('/api/review/ohlcv'),
    fetch('/api/review/indicators'), fetch('/api/review/levels')]);
  TRADES=(await tr.json()).filter(t=>t.pnl!=null && t.ts_entry).sort((a,b)=>a.ts_entry-b.ts_entry);
  try{{CANDLES=await ca.json();}}catch(e){{CANDLES=[];}}
  try{{INDICATORS=await ind.json();}}catch(e){{INDICATORS=null;}}
  try{{LEVELS=await lv.json();}}catch(e){{LEVELS=[];}}
}}

function step(d){{
  if(!CUR)return;
  const i=TRADES.findIndex(t=>t.id===CUR.id);
  const n=TRADES[i+d];
  if(n)show(n);
}}

// nearest indicator sample at or before a given unix time
function sampleAt(ts){{
  if(!INDICATORS||!ts)return null;
  const arr=INDICATORS.time;
  let lo=0,hi=arr.length-1,idx=-1;
  while(lo<=hi){{const mid=(lo+hi)>>1; if(arr[mid]<=ts){{idx=mid;lo=mid+1;}}else hi=mid-1;}}
  if(idx<0)return null;
  return {{rsi:INDICATORS.rsi14[idx], macd:INDICATORS.macd_line[idx],
          sma50:INDICATORS.sma50[idx], sma100:INDICATORS.sma100[idx], sma200:INDICATORS.sma200[idx]}};
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

let charts=[];
function vMarker(container, chart, time, label, color){{
  const line=document.createElement('div');
  line.style.cssText=`position:absolute;top:0;bottom:0;width:1px;background:${{color}};pointer-events:none;z-index:5`;
  const lbl=document.createElement('div');
  lbl.style.cssText=`position:absolute;top:2px;font-size:9px;font-family:var(--mono);color:${{color}};background:#06080ccc;padding:1px 4px;border-radius:3px;white-space:nowrap;pointer-events:none;z-index:6;transform:translateX(3px)`;
  lbl.textContent=label;
  container.appendChild(line); container.appendChild(lbl);
  // timeToCoordinate only resolves EXACT bar times — an entry/exit
  // timestamp with real seconds/minutes on it returns null forever, not a
  // timing race (verified directly: still null after 12s wait with a
  // correct, settled visible range). Snap to the 1h bar grid for the
  // lookup; the label still shows the real unsnapped time.
  const snapped=Math.floor(time/3600)*3600;
  let tries=0;
  function reposition(){{
    const x=chart.timeScale().timeToCoordinate(snapped);
    if(x===null){{
      // setVisibleRange settles ~600-1000ms after a 13k-candle setData —
      // measured directly — so a short retry window covers that genuine gap.
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

function show(t){{
  if(!t)return; CUR=t;
  $('cr-title').textContent=(t.direction||'').toUpperCase()+' #'+t.id+' · '+eur(t.pnl)+' · '+(t.opened_at||'').slice(0,16).replace('T',' ');
  fillReadout(t);
  charts.forEach(c=>{{try{{c.remove();}}catch(e){{}}}}); charts=[];
  document.querySelectorAll('#cr-chart,#cr-rsi,#cr-macd').forEach(el=>{{
    [...el.querySelectorAll('div')].forEach(d=>d.remove());
  }});
  if(!window.LightweightCharts||!CANDLES.length)return;
  const L=LightweightCharts.LineStyle;
  const dark={{background:{{color:'#06080c'}},textColor:'#465064'}},
        grid={{vertLines:{{color:'#192232'}},horzLines:{{color:'#192232'}}}};
  const range={{from:t.ts_entry-72*3600,to:(t.ts_exit||t.ts_entry)+36*3600}};
  const ec=t.direction==='long'?'#1fd989':'#ff5468';

  // price
  const pEl=$('cr-chart');
  const pChart=LightweightCharts.createChart(pEl,{{layout:dark,grid,rightPriceScale:{{borderColor:'#192232'}},timeScale:{{borderColor:'#192232',timeVisible:true,secondsVisible:false}}}});
  charts.push(pChart);
  const cs=pChart.addCandlestickSeries({{upColor:'#1fd989',downColor:'#ff5468',borderUpColor:'#1fd989',borderDownColor:'#ff5468',wickUpColor:'#1fd989',wickDownColor:'#ff5468'}});
  cs.setData(CANDLES);
  if(t.tp)cs.createPriceLine({{price:t.tp,color:'#1fd989',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'TP'}});
  if(t.sl)cs.createPriceLine({{price:t.sl,color:'#ff5468',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'SL'}});
  if(INDICATORS){{
    const it=INDICATORS.time;
    pChart.addLineSeries({{color:'#f6ad3c',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.sma50));
    pChart.addLineSeries({{color:'#5b9dff',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.sma100));
    pChart.addLineSeries({{color:'#ff5468',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.sma200));
    pChart.addLineSeries({{color:'#465064',lineWidth:1,lineStyle:L.Dotted,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.bb_upper));
    pChart.addLineSeries({{color:'#465064',lineWidth:1,lineStyle:L.Dotted,priceLineVisible:false,lastValueVisible:false}}).setData(toLine(it,INDICATORS.bb_lower));
  }}
  if(LEVELS.length){{
    LEVELS.filter(f=>f.confirm_time>=range.from&&f.confirm_time<=range.to)
      .sort((a,b)=>Math.abs(a.level-t.entry)-Math.abs(b.level-t.entry)).slice(0,8)
      .forEach(f=>{{
        const isR2S=f.kind==='r2s';
        cs.createPriceLine({{price:f.level,color:isR2S?'#1fd98999':'#ff546899',lineWidth:1,
          lineStyle:L.Dashed,axisLabelVisible:true,title:isR2S?'R\\u2192S':'S\\u2192R'}});
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
      c.timeScale().setVisibleRange(range);
    }});
    // timeToCoordinate() right after applyOptions/setVisibleRange reads the
    // PRE-layout position — the resize/range change hasn't painted yet.
    // requestAnimationFrame doesn't reliably fire under headless/virtual-time
    // Chrome (screenshot testing showed it stuck at a stale coordinate every
    // time) — a second real timer tick is the wait that actually works both
    // in a real browser and under headless.
    setTimeout(()=>{{
    if(t.ts_entry){{
      vMarker(pEl,pChart,t.ts_entry,'ENTRY '+t.entry.toFixed(0)+' \\u00b7 '+new Date(t.ts_entry*1000).toISOString().slice(11,16),ec);
      vMarker(rEl,rChart,t.ts_entry,'',ec);
      vMarker(mEl,mChart,t.ts_entry,'',ec);
    }}
    if(t.ts_exit){{
      const xc=t.pnl>=0?'#1fd989':'#ff5468';
      vMarker(pEl,pChart,t.ts_exit,'EXIT '+t.exit.toFixed(0)+' \\u00b7 '+new Date(t.ts_exit*1000).toISOString().slice(11,16),xc);
      vMarker(rEl,rChart,t.ts_exit,'',xc);
      vMarker(mEl,mChart,t.ts_exit,'',xc);
    }}
    }},80);
  }},60);
}}
function eur(v){{return (v>=0?'+':'\\u2212')+'\\u20ac'+Math.abs(v).toFixed(2);}}
boot();
"""
    head = ('<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>'
            '<style>.cr-lbl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;padding:2px 8px;'
            'border:1px solid var(--line);border-top:0;border-bottom:0;background:var(--panel)}</style>')
    return shell("/chart-review", "Chart review", body, script=script, head_extra=head,
                 meta="entry/exit against RSI, MACD, SMA stack, levels")
