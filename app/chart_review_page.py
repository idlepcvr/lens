"""LENS /chart-review — full-size, multi-timeframe chart review, pulled out
of the journal modal because there was no room to show RSI/MACD/levels
without squashing every pane unreadable (2026-08-27).

Multi-timeframe (2026-08-27b, direct ask: "it's locked to hourly... a
five-minute trade looks very different to a one-hour one"): the timeframe
defaults to what would actually have been on screen while the trade was
open — a duration rule (see review.auto_timeframe), not always 1h — and a
dropdown lets it be changed by hand. Every fetch is windowed to 100 bars
before entry / 30 after exit (review.get_ohlcv_window and friends), not the
whole multi-year history, so switching timeframe on an old trade doesn't
mean waiting on a giant payload.

Only 5m/15m/1h/4h/1d are offered. 1m is never cached anywhere (checked
directly against ohlcv_cache) — offering it would mean a slow live fetch
on every short-trade page load, so it's left out rather than shipped slow.

Entry is always a neutral marker (not direction-colored) and exit is
colored by win/loss — one consistent color legend instead of two
different colorings clashing on the same chart (direction on entry,
outcome on exit read as contradictory for a losing long or winning short).

Below the charts: the actual indicator readings AT entry and exit (RSI,
MACD, distance from each SMA) — so a pattern between the readings and
win/loss is at least visible by eye. Not yet a stored, backfilled,
correlation-tested dataset; see the module docstring in app/levels.py for
the same caveat applied here. An LLM-generated narrative per trade (asked
for separately) is not built here either — it's a distinct integration
(which model, on-demand vs cached, cost) that wants its own decision, not
a guess bolted onto this page.
"""
from .theme import shell

TF_SEC = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def render(trade_id: int | None, book: str = "hedge") -> str:
    tf_options = "".join(f'<option value="{tf}">{tf}</option>' for tf in TF_SEC)
    body = f"""
<div class="help-body" style="margin-bottom:12px">
<h4>What this page shows</h4>
<p>Price with the SMA 50/100/200 trend-confidence stack and Bollinger(20,2)
overlaid, resistance/support flips drawn as horizontal levels, and RSI(14) +
MACD(12,26,9) each in their own full-size pane below. Timeframe defaults to
what the trade's duration implies (a 10-minute scalp gets 5m candles, a
3-day swing gets 4h) — change it with the dropdown. Entry is a neutral
vertical line; exit is colored by win/loss. The table under the charts
reads off what each indicator actually was at entry and exit — eyeballing
it for now, not yet run through a permutation test the way the veto-combo
work was.</p>
</div>

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
const TF_SEC={{'5m':300,'15m':900,'1h':3600,'4h':14400,'1d':86400}};
let TRADES=[], WIN=null, CUR=null, TF=null, MANUAL_TF=false;
const $=id=>document.getElementById(id);

async function boot(){{
  $('cr-book').value=INIT_BOOK;
  await loadBook(INIT_BOOK);
  const t = INIT_TRADE!=null ? TRADES.find(x=>x.id===INIT_TRADE) : null;
  await show(t || TRADES[TRADES.length-1]);
  $('cr-book').onchange=async()=>{{await loadBook($('cr-book').value);MANUAL_TF=false;await show(TRADES[TRADES.length-1]);}};
  $('cr-tf').onchange=async()=>{{MANUAL_TF=true;TF=$('cr-tf').value;await render();}};
  $('cr-prev').onclick=()=>step(-1);
  $('cr-next').onclick=()=>step(1);
}}

async function loadBook(book){{
  const tr=await fetch('/api/review/trades?book='+book);
  TRADES=(await tr.json()).filter(t=>t.pnl!=null && t.ts_entry).sort((a,b)=>a.ts_entry-b.ts_entry);
}}

function step(d){{
  if(!CUR)return;
  const i=TRADES.findIndex(t=>t.id===CUR.id);
  const n=TRADES[i+d];
  if(n){{MANUAL_TF=false;show(n);}}
}}

// nearest indicator sample at or before a given unix time
function sampleAt(ts){{
  if(!WIN||!WIN.indicators||!ts)return null;
  const ind=WIN.indicators, arr=ind.time;
  let lo=0,hi=arr.length-1,idx=-1;
  while(lo<=hi){{const mid=(lo+hi)>>1; if(arr[mid]<=ts){{idx=mid;lo=mid+1;}}else hi=mid-1;}}
  if(idx<0)return null;
  return {{rsi:ind.rsi14[idx], macd:ind.macd_line[idx],
          sma50:ind.sma50[idx], sma100:ind.sma100[idx], sma200:ind.sma200[idx]}};
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
  fillReadout(t);
  charts.forEach(c=>{{try{{c.remove();}}catch(e){{}}}}); charts=[];
  document.querySelectorAll('#cr-chart,#cr-rsi,#cr-macd').forEach(el=>{{
    [...el.querySelectorAll('div')].forEach(d=>d.remove());
  }});
  try{{
    WIN=await fetch('/api/review/window?tf='+TF+'&entry='+t.ts_entry+(t.ts_exit?'&exit='+t.ts_exit:'')).then(r=>r.json());
  }}catch(e){{WIN=null;}}
  if(!window.LightweightCharts || !WIN || !WIN.ohlcv || !WIN.ohlcv.length)return;
  const CANDLES=WIN.ohlcv, INDICATORS=WIN.indicators, LEVELS=WIN.levels, tfSec=TF_SEC[TF];
  const L=LightweightCharts.LineStyle;
  const dark={{background:{{color:'#06080c'}},textColor:'#465064'}},
        grid={{vertLines:{{color:'#192232'}},horzLines:{{color:'#192232'}}}};
  const ENTRY_COLOR='#5b9dff';   // always neutral — direction is already in the title
  const EXIT_COLOR=t.pnl>=0?'#1fd989':'#ff5468';   // win/loss, the thing that matters

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
  if(LEVELS && LEVELS.length){{
    LEVELS.sort((a,b)=>Math.abs(a.level-t.entry)-Math.abs(b.level-t.entry)).slice(0,8)
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
    head = ('<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>'
            '<style>.cr-lbl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;padding:2px 8px;'
            'border:1px solid var(--line);border-top:0;border-bottom:0;background:var(--panel)}</style>')
    return shell("/chart-review", "Chart review", body, script=script, head_extra=head,
                 meta="entry/exit against RSI, MACD, SMA stack, levels")
