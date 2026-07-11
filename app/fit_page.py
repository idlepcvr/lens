"""/edge #fit — the Fit section fragment (form + optimal card + heatmap).

Stage A: sweep the strategy-shape parameters against a fixed goal and show the
region that can hit it. Returns (css, body, script) embedded into /edge by
edge_page.render_page, a fourth tense alongside past / board / backtest.

The server does the maths (app/fit_sweep.py). This is presentation: range form,
a /goal-style verdict card carrying THE optimal parameter set + the feasible
envelope, and the four heatmap slices (metric × axis-pair, switched client-side).
"""

CSS = r"""<style>
.fit-panel{padding:15px 17px}
.fit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:11px 22px}
.fit-row{display:flex;align-items:center;justify-content:space-between;gap:8px}
.fit-row label{font-size:11.5px;color:var(--dim)}
.fit-row label .hint{font-size:9px;color:var(--amber);margin-left:3px}
.fit-rng{display:flex;align-items:center;gap:5px;color:var(--faint);font-family:var(--mono);font-size:11px}
.fit-n{width:54px;background:var(--panel2);border:1px solid var(--line2);color:var(--ink);
  padding:4px 7px;border-radius:5px;font-family:var(--mono);font-size:11.5px;text-align:right}
.fit-n:focus{outline:none;border-color:var(--accent)}
.fit-goal{border-top:1px solid var(--line);margin-top:13px;padding-top:12px}
.fit-goal>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:11px;color:var(--dim)}
.fit-goal>summary::-webkit-details-marker{display:none}
.fit-goal>summary::before{content:"▸";color:var(--faint);font-size:11px}
.fit-goal[open]>summary::before{content:"▾"}
.fit-chip{font-family:var(--mono);font-size:10px;color:var(--dim);border:1px solid var(--line2);border-radius:4px;padding:2px 7px}
.fit-gform{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px 20px;margin-top:12px}
.fit-gf{display:flex;align-items:center;justify-content:space-between;gap:8px}
.fit-gf label{font-size:10.5px;color:var(--faint)}
.fit-gf input{width:110px;background:var(--panel2);border:1px solid var(--line2);color:var(--ink);
  padding:4px 7px;border-radius:5px;font-family:var(--mono);font-size:11px}
.fit-run{display:flex;gap:11px;align-items:center;margin-top:14px}
.fit-btn{padding:8px 18px;border-radius:6px;border:1px solid var(--accent);background:var(--accent-d);
  color:var(--accent);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;cursor:pointer;font-family:var(--hud)}
.fit-btn:hover{filter:brightness(1.3)} .fit-btn:disabled{opacity:.5;cursor:default}
.fit-prog{font-family:var(--mono);font-size:10.5px;color:var(--faint)}

/* verdict card — mirrors /goal .verdict */
.fit-verdict{border-radius:12px;padding:15px 17px;margin:14px 0 10px;display:flex;gap:12px;align-items:flex-start}
.fit-verdict .vi{font-size:20px;line-height:1;margin-top:1px}
.fit-verdict h3{font-size:15px;font-weight:600;margin:0 0 3px}
.fit-verdict p{font-size:12.5px;line-height:1.55;margin:0}
.fit-verdict.ok{background:rgba(31,217,137,.08);border:1px solid var(--long);color:var(--long)}
.fit-verdict.warn{background:rgba(246,173,60,.09);border:1px solid var(--amber);color:var(--amber)}
.fit-verdict.danger{background:var(--short-d);border:1px solid var(--short);color:var(--short)}
.fit-optset{display:flex;gap:8px;flex-wrap:wrap;margin:11px 0 2px}
.fit-opt{background:var(--panel2);border:1px solid var(--line2);border-radius:8px;padding:8px 12px;min-width:82px}
.fit-opt .l{font-family:var(--mono);font-size:8.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint)}
.fit-opt .n{font-family:var(--mono);font-size:17px;font-weight:700;margin-top:2px;color:var(--ink)}
.fit-env{font-size:12px;color:var(--dim);line-height:1.6;border-top:1px solid var(--line);margin-top:12px;padding-top:10px}
.fit-env b{color:var(--ink)}
.fit-env a{font-family:var(--mono);font-size:11px}
/* C4 — regime realism: feasible on paper vs on offer in the market */
.fit-real{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:11px;font-size:11.5px;color:var(--dim)}
.rbadge{font-family:var(--mono);font-size:9.5px;font-weight:800;letter-spacing:.1em;padding:2px 7px;border-radius:4px}
.rbadge.OFFERED{color:var(--long);border:1px solid var(--long)}
.rbadge.TIGHT{color:var(--amber);border:1px solid var(--amber)}
.rbadge.STARVED{color:var(--short);border:1px solid var(--short)}

/* your-strategy vs envelope comparison */
.fit-cmp{width:100%;border-collapse:collapse;margin-top:12px;font-size:11.5px}
.fit-cmp caption{caption-side:top;text-align:left;font-size:12px;color:var(--dim);padding:11px 0 3px}
.fit-cmp caption .dim{color:var(--faint)}
.fit-cmp th{text-align:right;color:var(--faint);font-weight:600;padding:5px 9px;border-bottom:1px solid var(--line);text-transform:uppercase;font-size:8.5px;letter-spacing:.06em}
.fit-cmp th:first-child,.fit-cmp td:first-child{text-align:left}
.fit-cmp td{text-align:right;padding:5px 9px;border-bottom:1px solid var(--line);font-family:var(--mono);color:var(--ink)}
.fit-cmp td.st{text-align:center} .fit-cmp .dim{color:var(--faint)}

/* heatmap — reuses the .hm grammar from the backtest fragment */
.fit-hm-head{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}
.fit-hm-title{font-size:14px;font-weight:700;color:var(--ink)}
.fit-hm-head select{background:var(--panel2);border:1px solid var(--line2);color:var(--ink);
  padding:6px 10px;border-radius:6px;font-family:var(--mono);font-size:11px;cursor:pointer}
.fit-hm{border-collapse:collapse;font-family:var(--mono)}
.fit-hm th{padding:5px 7px;font-size:9px;color:var(--dim);text-align:center;border:none}
.fit-hm th.corner,.fit-hm tbody th{text-align:right;color:var(--faint)}
.fit-hm td{width:52px;height:32px;text-align:center;font-size:10.5px;border:1px solid var(--line);color:var(--ink)}
.fit-hm td.best{outline:2px solid var(--ink);outline-offset:-2px;font-weight:700}
.fit-hm td.infeas{background-image:repeating-linear-gradient(45deg,transparent,transparent 4px,rgba(255,84,104,.10) 4px,rgba(255,84,104,.10) 6px)}
.fit-note{font-size:10.5px;color:var(--faint);margin-top:10px;line-height:1.55}
.fit-axnote{font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:7px}
.fit-help{margin:0 0 12px}
.fit-help>summary{cursor:pointer;list-style:none;font-family:var(--mono);font-size:11px;color:var(--dim)}
.fit-help>summary::-webkit-details-marker{display:none}
.fit-help[open]>summary{color:var(--accent)}
.fit-help .body{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:13px 15px;margin-top:8px;font-size:12px;line-height:1.6;color:var(--dim)}
.fit-help .body b{color:var(--ink)} .fit-help .body .g{color:var(--long)} .fit-help .body .r{color:var(--short)}
</style>"""


BODY = r"""
<div class="ed-h" id="fit">Fit — what shape must the strategy be?</div>
<div class="ed-hs">No strategies here, on purpose. Fix the goal (start → target by date) and sweep the sizing &amp; cadence space; the feasible region is where the goal closes <b style="color:var(--ink)">in time, inside Kelly, at ruin ≤ 1%</b>. Whatever you trade next has to land in it.</div>

<details class="fit-help"><summary>❔ how to read this</summary><div class="body">
This is the inverse of the builder below. The builder searches <b>entry conditions</b> and reports what win rate / frequency they produced. Here those are <b>inputs you sweep</b> — because a win rate is an <i>output</i> of a strategy, not a dial. Each cell asks the goal model one question: at this leverage, cadence, win rate, R:R and stop floor, does the account reach the target by the date, and does the risk it forces stay under the Kelly/drawdown cap? <b class="g">Feasible</b> cells clear both; the <b>envelope</b> is their outer bounds — the shape any real strategy must have to hit this goal, and the table under it sits <b>your own measured trades</b> next to those bounds so you can see if what you actually trade lives inside the island. <b class="r">In-sample and model-only</b>: this says what edge you'd <i>need</i>, not that such an edge exists — that's the next step (filtering the real search by this envelope).
</div></details>

<div class="panel fit-panel">
  <div class="fit-grid">
    <div class="fit-row"><label>Leverage ×</label><span class="fit-rng"><input class="fit-n" id="fit-lev-lo" value="0.5">–<input class="fit-n" id="fit-lev-hi" value="10"></span></div>
    <div class="fit-row"><label>Trades / week <span class="hint" id="fit-freq-note"></span></label><span class="fit-rng"><input class="fit-n" id="fit-freq-lo" value="0.5">–<input class="fit-n" id="fit-freq-hi" value="8"></span></div>
    <div class="fit-row"><label>Win rate <span class="hint" style="color:var(--faint)">0–1</span></label><span class="fit-rng"><input class="fit-n" id="fit-wr-lo" value="0.30">–<input class="fit-n" id="fit-wr-hi" value="0.70"></span></div>
    <div class="fit-row"><label>R : R</label><span class="fit-rng"><input class="fit-n" id="fit-rr-lo" value="1.0">–<input class="fit-n" id="fit-rr-hi" value="5.0"></span></div>
    <div class="fit-row"><label>ATR floor % <span class="hint" style="color:var(--faint)">stop</span></label><span class="fit-rng"><input class="fit-n" id="fit-atr-lo" value="0">–<input class="fit-n" id="fit-atr-hi" value="2.0"></span></div>
  </div>
  <details class="fit-goal">
    <summary>Goal params<span class="fit-chip" id="fit-chip-tgt">—</span><span class="fit-chip" id="fit-chip-date">—</span><span class="fit-chip" id="fit-chip-kelly">—</span><span class="fit-chip" id="fit-chip-dd">—</span><span class="fit-chip" id="fit-chip-slip">—</span></summary>
    <div class="fit-gform">
      <div class="fit-gf"><label>Start €</label><input id="fit-start" inputmode="decimal"></div>
      <div class="fit-gf"><label>Target €</label><input id="fit-target" inputmode="decimal"></div>
      <div class="fit-gf"><label>Target date</label><input id="fit-date" type="date"></div>
      <div class="fit-gf"><label>Max drawdown</label><input id="fit-dd" inputmode="decimal"></div>
      <div class="fit-gf"><label>Losses allowed</label><input id="fit-losses" inputmode="decimal"></div>
      <div class="fit-gf"><label>Frac. Kelly</label><input id="fit-kelly" inputmode="decimal"></div>
      <div class="fit-gf"><label>Fill factor</label><input id="fit-fill" inputmode="decimal"></div>
      <div class="fit-gf"><label>Slippage</label><input id="fit-slip" inputmode="decimal"></div>
      <div class="fit-gf"><label>BTC price €</label><input id="fit-btcpx" inputmode="decimal"></div>
      <div class="fit-gf"><label>BTC growth /mo</label><input id="fit-btcg" inputmode="decimal"></div>
    </div>
  </details>
  <div class="fit-run">
    <button class="fit-btn" id="fit-run-btn">▶ Sweep the space</button>
    <span class="fit-prog" id="fit-prog">pure goal-model math · a few seconds</span>
  </div>
</div>

<div id="fit-verdict-wrap"></div>

<div class="panel" id="fit-heat-wrap" style="display:none">
  <div class="fit-hm-head">
    <div class="fit-hm-title">Sensitivity — slices through the optimum</div>
    <div style="display:flex;gap:8px">
      <select id="fit-metric">
        <option value="headroom">metric: risk headroom</option>
        <option value="ror">risk of ruin</option>
        <option value="sharpe">Sharpe</option>
        <option value="ev">EV / trade</option>
        <option value="drift">geometric drift</option>
      </select>
      <select id="fit-plane">
        <option value="lev_freq">axes: leverage × trades/wk</option>
        <option value="wr_rr">win rate × R:R</option>
        <option value="atr_lev">ATR floor × leverage</option>
        <option value="freq_wr">trades/wk × win rate</option>
      </select>
    </div>
  </div>
  <div style="overflow-x:auto"><table class="fit-hm" id="fit-hm"></table></div>
  <div class="fit-axnote" id="fit-axnote"></div>
  <div class="fit-note">Each cell colours by the chosen metric with the three unshown axes pinned at the joint optimum. <b class="g">Green</b> = better on that metric; <b>hatched</b> = infeasible (misses the date or busts Kelly/ruin). The <b style="color:var(--ink)">outlined</b> cell is the optimum. A real fit is a green <i>island</i>, not one lucky cell — same reading as the k×R sweep.</div>
</div>
"""


SCRIPT = r"""
(function(){
  var METRICS = {
    headroom:{lbl:'risk headroom', mid:1, fmt:function(v){return v.toFixed(2)}, hi:'good', inv:false},
    ror:     {lbl:'risk of ruin',  mid:1, fmt:function(v){return v.toFixed(1)+'%'}, inv:true},
    sharpe:  {lbl:'Sharpe',        mid:0, fmt:function(v){return v.toFixed(2)}, inv:false},
    ev:      {lbl:'EV / trade',    mid:0, fmt:function(v){return v.toFixed(2)+'%'}, inv:false},
    drift:   {lbl:'geom drift',    mid:0, fmt:function(v){return v.toFixed(1)+'%'}, inv:false}
  };
  var AXLBL = {lev:'leverage', freq:'trades/wk', wr:'win rate', rr:'R:R', atr:'ATR floor'};
  var el=function(id){return document.getElementById(id)};
  var pct=function(x){return (x*100).toFixed(0)+'%'};
  var PROP=(typeof FIT_BOOK!=='undefined'&&FIT_BOOK==='prop');
  var CUR=PROP?'$':'€';   // eval is USD, hedge is EUR
  var eur=function(x){return CUR+Math.round(x).toLocaleString('en-US')};
  var DATA=null, PROP_RISK=null;

  // ── prefill goal params + historical frequency ──────────────────────────
  function prefill(d){
    var c=d.config||{};
    var set=function(id,v){ if(v!=null) el(id).value=v; };
    set('fit-start', c.start_balance); set('fit-target', c.target_balance);
    set('fit-date', c.target_date); set('fit-dd', c.max_drawdown_allowed);
    set('fit-losses', c.losses_allowed); set('fit-kelly', c.fractional_kelly);
    set('fit-fill', c.execution_fill_factor); set('fit-slip', c.slippage_pct);
    set('fit-btcpx', c.btc_price_eur); set('fit-btcg', c.btc_growth_monthly);
    if(d.freq_per_week){ el('fit-freq-hi').value=d.freq_per_week;
      el('fit-freq-note').textContent=(PROP?'basket avg ':'yr avg ')+d.freq_per_week; }
    if(PROP){
      PROP_RISK=c.risk_per_trade||0.005;
      // the firm fixes everything but the date and the strategy shape:
      // lock the goal inputs, cap the leverage axis at the firm's max,
      // and blank the BTC fields (a USD eval doesn't ride BTC).
      if(c.leverage) el('fit-lev-hi').value=c.leverage;
      el('fit-btcpx').value=''; el('fit-btcg').value=c.btc_growth_monthly||0;
      ['fit-start','fit-target','fit-dd','fit-losses','fit-kelly','fit-fill','fit-slip','fit-btcpx','fit-btcg']
        .forEach(function(id){ el(id).readOnly=true; el(id).style.opacity=.55; });
      var note=document.createElement('div');
      note.style.cssText='grid-column:1/-1;font-size:10px;color:var(--amber)';
      note.textContent='⚿ Fixed by the firm + your plan (risk '+(PROP_RISK*100).toFixed(2)+'%/trade) — only the target date is yours to move.';
      document.querySelector('.fit-gform').prepend(note);
    }
    chips();
  }
  function chips(){
    var s=el('fit-start').value, t=el('fit-target').value;
    el('fit-chip-tgt').textContent=(s?eur(+s):'—')+' → '+(t?eur(+t):'—');
    el('fit-chip-date').textContent='by '+(el('fit-date').value||'—');
    el('fit-chip-kelly').textContent=(+el('fit-kelly').value||0).toFixed(3)+' Kelly';
    el('fit-chip-dd').textContent='DD '+pct(+el('fit-dd').value||0);
    el('fit-chip-slip').textContent=PROP&&PROP_RISK
      ? 'risk '+(PROP_RISK*100).toFixed(2)+'% fixed'
      : 'slip '+((+el('fit-slip').value||0)*100).toFixed(2)+'%';
  }
  ['fit-start','fit-target','fit-date','fit-kelly','fit-dd','fit-slip'].forEach(function(id){
    el(id).addEventListener('input',chips);
  });

  // ── build the run payload ───────────────────────────────────────────────
  function num(id){ var v=parseFloat(el(id).value); return isFinite(v)?v:null; }
  function payload(){
    return {
      lev_min:num('fit-lev-lo'), lev_max:num('fit-lev-hi'),
      freq_min:num('fit-freq-lo'), freq_max:num('fit-freq-hi'),
      wr_min:num('fit-wr-lo'), wr_max:num('fit-wr-hi'),
      rr_min:num('fit-rr-lo'), rr_max:num('fit-rr-hi'),
      atr_min:(num('fit-atr-lo')||0)/100, atr_max:(num('fit-atr-hi')||0)/100,
      start_balance:num('fit-start'), target_balance:num('fit-target'),
      target_date:el('fit-date').value,
      max_drawdown_allowed:num('fit-dd'), losses_allowed:num('fit-losses'),
      fractional_kelly:num('fit-kelly'), execution_fill_factor:num('fit-fill'),
      slippage_pct:num('fit-slip'), btc_price_eur:num('fit-btcpx'),
      btc_growth_monthly:num('fit-btcg'),
      risk_per_trade:PROP?PROP_RISK:null, book:PROP?'prop':null
    };
  }

  // ── run + poll ──────────────────────────────────────────────────────────
  var btn=el('fit-run-btn'), prog=el('fit-prog'), poll=null;
  btn.addEventListener('click', function(){
    var body=payload();
    if(body.start_balance==null||body.target_balance==null||!body.target_date){
      prog.textContent='Set start, target and date first.'; return; }
    btn.disabled=true; prog.textContent='starting…';
    el('fit-verdict-wrap').innerHTML=''; el('fit-heat-wrap').style.display='none';
    fetch('/api/fit/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(function(r){return r.json()}).then(function(d){
        if(d.error){ prog.textContent=d.error; btn.disabled=false; return; }
        prog.textContent='sweeping ~'+(d.total_est||0).toLocaleString()+' cells…';
        poll=setInterval(checkStatus,500);
      }).catch(function(e){ prog.textContent='error: '+e.message; btn.disabled=false; });
  });
  function checkStatus(){
    fetch('/api/fit/status').then(function(r){return r.json()}).then(function(d){
      if(d.error){ clearInterval(poll); prog.textContent=d.error; btn.disabled=false; return; }
      if(d.running){ if(d.total) prog.textContent='sweeping… '+Math.round(100*d.done/d.total)+'%'; return; }
      clearInterval(poll); btn.disabled=false;
      if(d.result){ DATA=d.result; prog.textContent='done · '+DATA.evaluated.toLocaleString()+' cells · '+DATA.feasible_count.toLocaleString()+' feasible'; render(); }
    }).catch(function(e){ clearInterval(poll); prog.textContent='error: '+e.message; btn.disabled=false; });
  }

  // ── verdict card + optimal set + envelope ───────────────────────────────
  function render(){
    var o=DATA.optimum, env=DATA.envelope, g=DATA.goal;
    var lvl,icon,title,msg;
    if(!o){ lvl='danger'; icon='⛔'; title='Nothing evaluated'; msg='Every cell hit a model error — widen the ranges.'; }
    else if(o.feasible){
      var frac=DATA.evaluated? (100*DATA.feasible_count/DATA.evaluated):0;
      lvl='ok'; icon='◎'; title='Feasible — the goal closes at sane risk in '+frac.toFixed(1)+'% of the space';
      msg='Best cell risks '+o.used.toFixed(2)+'%/trade where '+o.opt.toFixed(2)+'% is allowed — '+o.headroom.toFixed(1)+'× headroom. Ruin '+o.ror.toFixed(2)+'%.';
    } else if(o.closes){
      lvl='warn'; icon='⚠️'; title='Reachable only past safe risk';
      msg='No parameter set closes '+eur(g.target_balance)+' by '+g.target_date+' inside Kelly. The closest still forces '+o.used.toFixed(2)+'%/trade where only '+o.opt.toFixed(2)+'% is safe ('+(o.used/o.opt).toFixed(1)+'× over). Ruin '+o.ror.toFixed(2)+'%.';
    } else {
      lvl='danger'; icon='⛔'; title='Out of reach by the date';
      msg='No parameter combination reaches '+eur(g.target_balance)+' by '+g.target_date+' — the best case still needs '+(o.weeks_to_goal!=null?o.weeks_to_goal+' weeks':'more time')+' with '+DATA.weeks_remaining+' left. Push the date out or cut the target.';
    }
    var tiles=[['Leverage',o?o.lev+'×':'—'],['Trades/wk',o?o.freq:'—'],['Win rate',o?pct(o.wr):'—'],
               ['R:R',o?o.rr.toFixed(1):'—'],['ATR floor',o?(o.atr*100).toFixed(2)+'%':'—'],['Risk/trade',o?o.used.toFixed(2)+'%':'—']];
    var opth = o? '<div class="fit-optset">'+tiles.map(function(t){
      return '<div class="fit-opt"><div class="l">'+t[0]+'</div><div class="n">'+t[1]+'</div></div>'; }).join('')+'</div>' : '';
    var envh='';
    if(o && Object.keys(env).length){
      var goalHref='/goal?win_rate='+o.wr.toFixed(4)+'&rr_ratio='+o.rr.toFixed(2)+'&trades_per_week='+o.freq+'&leverage='+o.lev;
      envh='<div class="fit-env"><b>The envelope:</b> every feasible cell has WR '+pct(env.wr.min)+'–'+pct(env.wr.max)+
        ' at R '+env.rr.min.toFixed(1)+'–'+env.rr.max.toFixed(1)+' · '+env.freq.min+'–'+env.freq.max+' trades/wk · leverage '+
        env.lev.min+'–'+env.lev.max+'× · ATR floor '+(env.atr.min*100).toFixed(2)+'–'+(env.atr.max*100).toFixed(2)+'%. '+
        'A strategy outside these bounds can\'t reach '+eur(g.target_balance)+' by the date at sane risk. &nbsp;'+
        '<a href="'+goalHref+'" target="_blank" title="open the optimum in the Goal model">→ Goal model</a></div>';
    } else if(o){
      envh='<div class="fit-env">No feasible envelope — nothing in the swept space both reaches the goal in time and stays inside Kelly. The tiles above are the <b>nearest miss</b>. Push the date, cut the target, or loosen the risk caps.</div>';
    }
    // your real, measured strategy sat next to the envelope — only meaningful when
    // a feasible island exists to compare against.
    var m=DATA.measured, cmph='';
    if(o && Object.keys(env).length && m){
      var fails=0;
      var band=function(v,lo,hi){ return v!=null && v>=lo-1e-9 && v<=hi+1e-9; };
      var rows=[
        ['Win rate',          pct(env.wr.min)+'–'+pct(env.wr.max),                     m.wr!=null?pct(m.wr):null,               m.wr!=null?band(m.wr,env.wr.min,env.wr.max):null],
        ['R : R',             env.rr.min.toFixed(1)+'–'+env.rr.max.toFixed(1),         m.rr!=null?m.rr.toFixed(2):null,         m.rr!=null?band(m.rr,env.rr.min,env.rr.max):null],
        ['Trades / week',     env.freq.min+'–'+env.freq.max,                           m.freq!=null?(''+m.freq):null,          m.freq!=null?band(m.freq,env.freq.min,env.freq.max):null],
        ['Risk / trade',      m.kelly_cap_pct!=null?'≤ '+m.kelly_cap_pct.toFixed(2)+'%':'—', m.risk_pct!=null?m.risk_pct.toFixed(2)+'%':null, (m.risk_pct!=null&&m.kelly_cap_pct!=null)?m.risk_pct<=m.kelly_cap_pct+1e-9:null],
        ['Kelly utilization', '< 100%',                                                m.kelly_util!=null?m.kelly_util.toFixed(0)+'%':null, m.kelly_util!=null?m.kelly_util<100:null]
      ];
      var trs=rows.map(function(r){
        if(r[3]===false) fails++;
        var your=r[2]==null?'<span class="dim">—</span>':r[2];
        var st=r[3]===null?'<span class="dim">—</span>':(r[3]?'✅':'❌');
        return '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td><td>'+your+'</td><td class="st">'+st+'</td></tr>';
      }).join('');
      var cap=fails===0
        ? 'Your measured strategy is living <b style="color:var(--long)">inside the feasible island</b>.'
        : 'Your measured strategy is <b style="color:var(--short)">outside the island</b> on '+fails+' ax'+(fails>1?'es':'is')+'.';
      cmph='<table class="fit-cmp"><caption>'+cap+' <span class="dim">n='+m.n+' closed trades</span></caption>'+
        '<thead><tr><th>Metric</th><th>Required envelope</th><th>Your strategy</th><th>Status</th></tr></thead>'+
        '<tbody>'+trs+'</tbody></table>';
    }
    // C4 — the envelope may be populated on paper and starved in the market
    var R=DATA.realism, realh='';
    if(o && R){
      realh='<div class="fit-real"><span class="rbadge '+R.badge+'">'+R.badge+'</span>'+
        '<span>The optimum needs a <b style="color:var(--ink)">'+R.move_pct.toFixed(2)+'%</b> move '+
        R.needs+'× a week. In the current <b style="color:var(--ink)">'+R.regime+'</b> regime the market '+
        'offered that on '+R.hit+' of the last '+R.days+' days — <b style="color:var(--ink)">~'+R.offers+'/wk</b>'+
        (R.badge==='STARVED'?' — the corridor exists on paper, not on the tape.'
         :R.badge==='TIGHT'?' — barely enough; a quiet fortnight breaks it.'
         :' — the market is handing you more setups than the plan needs.')+'</span></div>';
    }
    el('fit-verdict-wrap').innerHTML='<div class="fit-verdict '+lvl+'"><div class="vi">'+icon+
      '</div><div style="flex:1"><h3>'+title+'</h3><p>'+msg+'</p>'+opth+envh+realh+cmph+'</div></div>';
    el('fit-heat-wrap').style.display='';
    drawHeat();
  }

  // ── heatmap ─────────────────────────────────────────────────────────────
  el('fit-metric').addEventListener('change',drawHeat);
  el('fit-plane').addEventListener('change',drawHeat);
  function drawHeat(){
    if(!DATA||!DATA.planes) return;
    var pname=el('fit-plane').value, mkey=el('fit-metric').value;
    var p=DATA.planes[pname], m=METRICS[mkey], o=DATA.optimum;
    var map={}; p.cells.forEach(function(c){ map[c[p.y]+'|'+c[p.x]]=c; });
    var vals=p.cells.map(function(c){return c[mkey]}).filter(function(v){return isFinite(v)});
    var maxAbs=Math.max.apply(null, vals.map(function(v){return Math.abs(v-m.mid)}).concat([1e-6]));
    var h='<thead><tr><th class="corner">'+AXLBL[p.y]+' ╲ '+AXLBL[p.x]+'</th>';
    p.xs.forEach(function(x){ h+='<th>'+fmtAx(p.x,x)+'</th>'; }); h+='</tr></thead><tbody>';
    p.ys.forEach(function(y){
      h+='<tr><th>'+fmtAx(p.y,y)+'</th>';
      p.xs.forEach(function(x){
        var c=map[y+'|'+x];
        if(!c){ h+='<td style="color:var(--faint)">—</td>'; return; }
        var v=c[mkey], t=(v-m.mid)/maxAbs; if(m.inv) t=-t;
        t=Math.max(-1,Math.min(1,t)); var hue=t>=0?150:5;
        var cls='';
        if(!c.feasible) cls+=' infeas';
        if(o && Math.abs(c[p.y]-o[p.y])<1e-6 && Math.abs(c[p.x]-o[p.x])<1e-6) cls+=' best';
        var tip=AXLBL[p.y]+' '+fmtAx(p.y,y)+' · '+AXLBL[p.x]+' '+fmtAx(p.x,x)+
          ' — used '+c.used.toFixed(2)+'% / opt '+c.opt.toFixed(2)+'% · ruin '+c.ror.toFixed(2)+
          '% · '+(c.feasible?'feasible':c.closes?'busts risk':'misses date')+
          (c.weeks_to_goal!=null?' · reaches in '+c.weeks_to_goal+'w':'');
        h+='<td class="'+cls+'" style="background:hsla('+hue+',72%,45%,'+(0.10+0.5*Math.abs(t))+')" title="'+tip+'">'+m.fmt(v)+'</td>';
      });
      h+='</tr>';
    });
    el('fit-hm').innerHTML=h+'</tbody>';
    // pinned-axes note
    var shown=[p.y,p.x], pins=['lev','freq','wr','rr','atr'].filter(function(k){return shown.indexOf(k)<0;});
    el('fit-axnote').textContent='colour: '+m.lbl+' · pinned at optimum — '+pins.map(function(k){
      return AXLBL[k]+' '+fmtAx(k,o?o[k]:0); }).join(' · ');
  }
  function fmtAx(k,v){
    if(k==='wr') return pct(v);
    if(k==='atr') return (v*100).toFixed(2)+'%';
    if(k==='lev') return v+'×';
    if(k==='rr') return v.toFixed(1)+'R';
    return ''+v;
  }

  // prop eval is USD → relabel the € goal inputs to $ (values come from the eval)
  if(FIT_BOOK==='prop'){ document.querySelectorAll('.fit-gf label').forEach(function(l){ l.textContent=l.textContent.replace('€','$'); }); }
  fetch('/api/fit/defaults?book='+FIT_BOOK).then(function(r){return r.json()}).then(prefill).catch(function(){});
})();
"""


def fragment(book: str = "hedge"):
    """Return (css, body, script) for embedding in /edge. `book` picks the goal the
    sweep is constrained by: hedge = the BTC-stack goal, prop = the eval (+target%
    before -DD%). It only changes the prefilled defaults; the sweep math is the same."""
    script = (f'var FIT_BOOK={book!r};\n'.replace("'", '"')) + SCRIPT
    return CSS, BODY, script
