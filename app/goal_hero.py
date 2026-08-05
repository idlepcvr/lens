"""Shared four-pillar hero + one-line status strip for the goal calculator.

Used by both /goal (goal_page.py) and /dashboard "Plan" (main.py). One source so
the two pages can't drift. Each pillar answers one goal-critical question and
carries pass/fail three ways at once — colour bar + icon-word chip + threshold —
so meaning never rides on colour alone (see PRODUCT.md accessibility rule).

Both host pages must provide: a form with id="goal-form" whose fields include
start_balance / target_balance / target_date, and the /api/goal response `g`.
Styling uses base LENS theme tokens directly, so it needs no page-local aliases.
"""

# ── CSS (no <style> wrapper — host injects it inside its own <style>) ──────────
HERO_CSS = r"""
.hero{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
@media(max-width:960px){.hero{grid-template-columns:repeat(2,1fr)}}
.hcard{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 14px 14px;position:relative;overflow:hidden;transition:background .18s ease,border-color .18s ease}
.hcard::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--line2);transition:background .18s ease}
.hcard.pos::after{background:var(--long)}.hcard.neg::after{background:var(--short)}.hcard.warn::after{background:var(--amber)}
.hcard.neg{border-color:color-mix(in srgb,var(--short) 45%,var(--line))}
.hstate{position:absolute;top:11px;right:11px;display:inline-flex;align-items:center;gap:4px;font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:.07em}
.hstate .ic{width:14px;height:14px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:9px;font-weight:900}
.hcard.pos .hstate{color:var(--long)}.hcard.pos .hstate .ic{background:rgba(31,217,137,.15)}
.hcard.neg .hstate{color:var(--short)}.hcard.neg .hstate .ic{background:rgba(255,84,104,.15)}
.hcard.warn .hstate{color:var(--amber)}.hcard.warn .hstate .ic{background:rgba(246,173,60,.15)}
.hbig{font-family:var(--mono);font-size:19px;font-weight:700;color:var(--ink);margin-top:20px;line-height:1.05}
.hlbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--dim);margin-top:8px}
.hsub{font-size:9.5px;color:var(--faint);margin-top:3px;font-family:var(--mono)}
.statusline{display:flex;align-items:center;gap:10px;padding:9px 13px;border-radius:8px;border:1px solid var(--line);background:var(--panel);font-size:12px;line-height:1.45;transition:background .18s ease,border-color .18s ease}
.statusline .sl-dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
.statusline .sl-txt{color:var(--dim)}.statusline .sl-txt b{color:var(--ink);font-weight:700}
.statusline.danger{border-color:var(--short);background:var(--short-d)}.statusline.danger .sl-dot{background:var(--short);box-shadow:0 0 7px var(--short)}
.statusline.warn{border-color:var(--amber);background:var(--amber-d)}.statusline.warn .sl-dot{background:var(--amber);box-shadow:0 0 7px var(--amber)}
.diverge{margin-top:9px;padding:10px 13px;border-radius:8px;border:1px solid var(--amber);
  background:var(--amber-d);font-size:12.5px;line-height:1.55;color:var(--ink)}
.diverge b{font-weight:700}.diverge .dsub{color:var(--dim);font-size:11.5px;display:block;margin-top:4px}
.statusline.ok .sl-dot{background:var(--long);box-shadow:0 0 7px var(--long)}
@media(prefers-reduced-motion:reduce){.hcard,.hcard::after,.statusline{transition:none}}
"""

# ── markup — four pillars then the one-line status strip ──────────────────────
HERO_HTML = r"""
    <div class="hero">
      <div class="hcard" id="hc-time"><span class="hstate" id="st-time"></span><div class="hbig" id="h-arr">—</div><div class="hlbl">On time?</div><div class="hsub" id="h-arr-sub">—</div></div>
      <div class="hcard" id="hc-ev"><span class="hstate" id="st-ev"></span><div class="hbig" id="h-ev">—</div><div class="hlbl">Edge / trade<a class="qh" href="/glossary#ev" target="_blank" rel="noopener" title="what is this?">?</a></div><div class="hsub" id="h-ev-sub">—</div></div>
      <div class="hcard" id="hc-ror"><span class="hstate" id="st-ror"></span><div class="hbig" id="h-ror">—</div><div class="hlbl">Risk of ruin</div><div class="hsub" id="h-ror-sub">—</div></div>
      <div class="hcard" id="hc-size"><span class="hstate" id="st-size"></span><div class="hbig" id="h-size">—</div><div class="hlbl">Risk sizing<a class="qh" href="/glossary#kelly" target="_blank" rel="noopener" title="used vs optimal risk">?</a></div><div class="hsub" id="h-size-sub">—</div></div>
    </div>
    <div id="statusline" class="statusline ok"><span class="sl-dot"></span><span class="sl-txt">enter your parameters…</span></div>
    <div id="divergence" class="diverge" hidden></div>
"""

# ── behaviour — call renderPillars(g) after each /api/goal response ────────────
# Self-contained: reads the form itself, defines its own formatters. Safe to drop
# into an f-string host (interpolated braces aren't re-parsed) or a raw string.
HERO_JS = r"""
function renderPillars(g){
  const F=document.getElementById("goal-form");
  const val=n=>{const e=F&&F.elements.namedItem(n);return e?e.value:"";};
  const num=n=>{const v=Number(val(n));return Number.isFinite(v)&&v!==0?v:null;};
  const fmtInt=v=>v==null?"—":Math.round(v).toLocaleString();
  const fmtEur=v=>v==null?"—":"€"+v.toLocaleString("en-US",{maximumFractionDigits:0});
  const fmtPct=v=>v==null?"—":v.toFixed(2)+"%";
  const sgnp=x=>x==null?"—":(x>=0?"+":"")+x.toFixed(3)+"%";
  const fmtMY=d=>d?d.toLocaleDateString("en-GB",{month:"short",year:"numeric"}):"—";
  const projDate=w=>{if(w==null||!isFinite(w))return null;const d=new Date();d.setDate(d.getDate()+Math.round(w*7));return d;};
  const setTxt=(id,t)=>{const e=document.getElementById(id);if(e)e.textContent=t;};
  function setHero(cardId,stateId,state,word){           // state: true | "warn" | false
    const cls=state===true?"pos":state==="warn"?"warn":"neg";
    const ic =state===true?"✓":state==="warn"?"!":"✕";
    const c=document.getElementById(cardId);if(c)c.className="hcard "+cls;
    const s=document.getElementById(stateId);if(s)s.innerHTML=`<span class="ic">${ic}</span>${word}`;
  }
  const used=g.risk_per_trade??0, opt=g.optimal_risk_pct??0, ror=g.risk_of_ruin??0;
  const over=opt>0?used/opt:Infinity;
  const start=num("start_balance"), tgt=num("target_balance");
  const eurOf=p=>(start!=null&&p!=null)?fmtEur(p/100*start):null;
  const withEur=p=>fmtPct(p)+(eurOf(p)?" ("+eurOf(p)+")":"");
  const tgtRaw=val("target_date"), tgtDate=tgtRaw?new Date(tgtRaw):null;
  const projD=projDate(g.weeks_to_goal_actual);
  const arrival=projD?("around "+fmtMY(projD)):"never at this edge (drift ≤ 0)";
  const insufficient=g.trades_needed>g.total_trades;   // ⟺ arrival past the deadline (same drift)

  // 1 · On time? — reach the target inside the window.
  //
  // Gated against the ledger. The arrival date is computed from whatever win
  // rate is in the form, and win rate is the one input nothing on this page can
  // check — so a typed 55% at a geometry that has only ever produced 35% used
  // to light this card green and call the plan reachable. It is not a plan, it
  // is a wish with a date on it. When the typed rate is materially above what
  // the entries have actually done AT THIS GEOMETRY, the card degrades to
  // "Unproven": the arithmetic closes, the evidence does not.
  //
  // Loading a measured source (validated cell, or a swept geometry cell) is not
  // typing, so those are exempt — the gate compares against them, it does not
  // fire on them.
  const wrGate=(function(){
    try{
      const f=document.getElementById("goal-form")||document.forms[0];
      if(!f) return null;
      const wr=parseFloat(f.elements.win_rate?.value),
            rr=parseFloat(f.elements.rr_ratio?.value);
      if(!isFinite(wr)||!isFinite(rr)) return null;
      const V=window.VALIDATED, GM=window.GEOM, M=window.MEAS;
      const near=(a,b)=>Math.abs(a-b)<1e-6;
      // exempt: this IS a measured cell, not a typed one
      if(V&&V.n&&near(wr,V.win_rate)&&near(rr,V.rr_ratio)) return null;
      const cells=(GM&&GM.cells)||[];
      if(cells.some(c=>near(wr,c.win_rate)&&near(rr,c.rr))) return null;
      // Closest measured evidence to the geometry actually typed. Compare on the
      // stop as well as the R:R — a win rate belongs to both barriers, so the
      // nearest R:R at a wildly different stop is not the right yardstick. Falls
      // back to the whole book only when the sweep has produced nothing.
      const stopTyped=parseFloat(f.elements.min_underlying_stop_pct?.value)*100;
      let ref=null, best=Infinity;
      for(const c of (GM&&GM.reference)||[]){
        const d=Math.abs(c.rr-rr)+(isFinite(stopTyped)?Math.abs(c.stop_pct-stopTyped)/2:0);
        if(d<best){ best=d; ref={wr:c.win_rate,lbl:`${c.group} ${c.stop_pct}/${c.target_pct} @ ${c.hold_h}h`,n:c.n}; }
      }
      if(!ref&&M&&M.n&&M.win_rate!=null) ref={wr:M.win_rate,lbl:"the whole book",n:M.n};
      if(!ref) return null;
      const gap=(wr-ref.wr)*100;
      return gap>5 ? {gap:gap, ref:ref, typed:wr} : null;
    }catch(e){ return null; }
  })();
  setTxt("h-arr", projD?fmtMY(projD):"never");
  setTxt("h-arr-sub",(tgtDate?"target "+fmtMY(tgtDate):"—")+(g.days_remaining!=null?" · "+fmtInt(g.days_remaining)+"d left":""));
  if(insufficient)      setHero("hc-time","st-time", false, "Behind");
  else if(wrGate)       setHero("hc-time","st-time", "warn", "Unproven");
  else                  setHero("hc-time","st-time", true,  "On time");
  if(wrGate) setTxt("h-arr-sub",
    `typed WR ${(wrGate.typed*100).toFixed(1)}% vs ${(wrGate.ref.wr*100).toFixed(1)}% measured `
    +`(${wrGate.ref.lbl}, n=${wrGate.ref.n}) — +${wrGate.gap.toFixed(1)}pp unproven`);
  // 2 · Edge / trade — per-trade EV vs what the goal needs (colour matches the two numbers)
  const evOk=g.per_trade_ev!=null&&g.per_trade_ev_required!=null&&g.per_trade_ev>=g.per_trade_ev_required;
  setTxt("h-ev", sgnp(g.per_trade_ev));
  setTxt("h-ev-sub","need "+sgnp(g.per_trade_ev_required));
  setHero("hc-ev","st-ev", evOk, evOk?"Enough":"Short");
  // 3 · Risk of ruin
  setTxt("h-ror", fmtPct(ror));
  setTxt("h-ror-sub", g.ror_label??"");
  setHero("hc-ror","st-ror", ror<=1?true:ror<=5?"warn":false, ror<=1?"Safe":ror<=5?"Elevated":"High");
  // 4 · Risk sizing — used vs optimal
  setTxt("h-size", isFinite(over)?over.toFixed(1)+"×":"∞");
  setTxt("h-size-sub", fmtPct(used)+" vs "+fmtPct(opt)+" opt");

  // 5 · Typed-vs-measured divergence.
  // The hero cards are computed from whatever is in the form. If the typed R:R
  // or win rate is well above what the ledger has ever produced, "Enough" is a
  // statement about the typing, not about the edge — so say so rather than let
  // a green card confirm a payoff that has never been taken.
  (function(){
    const box=document.getElementById("divergence");
    if(!box) return;
    const M=window.MEAS;
    const f=document.getElementById("goal-form")||document.forms[0];
    if(!M||!M.n||M.rr_ratio==null||!f){ box.hidden=true; return; }
    // "validated" is measured too — on the surviving cell rather than the whole
    // book — so the typed-vs-measured warning would be wrong. Different note.
    // Detect the validated source from the VALUES, not from a flag: recompute()
    // re-renders and any flag set before it gets clobbered. Comparing the form
    // to the validated triple is stateless and cannot drift out of sync.
    const Vv=window.VALIDATED;
    const isVal = Vv && Vv.n
      && Math.abs(parseFloat(f.elements.win_rate?.value)-Vv.win_rate)<1e-6
      && Math.abs(parseFloat(f.elements.rr_ratio?.value)-Vv.rr_ratio)<1e-6;
    if(isVal){
      const V=Vv;
      box.innerHTML="◆ <b>Running on the validated cell, not the whole book.</b> "
        +(V?("<b>"+V.cell+"</b>, n="+V.n+" — the only cell to clear every gate. "):"")
        +"The whole book (n="+M.n+") is <b>"+(M.win_rate*M.rr_ratio-(1-M.win_rate)).toFixed(3)
        +"R</b> per trade because it averages the long side and the VETO contexts in."
        +"<span class='dsub'>Legitimate, but it assumes you trade <i>only</i> that cell"
        +(V?" — and it fires <b>"+V.trades_per_week+"/wk</b>, not the ~7 the target needs. "
            +"Cadence here is what you generate, not what you need.":"")+"</span>";
      box.hidden=false; return;
    }
    const tR=parseFloat(f.elements.rr_ratio?.value), tW=parseFloat(f.elements.win_rate?.value);
    if(!isFinite(tR)||!isFinite(tW)){ box.hidden=true; return; }
    const bits=[];
    if(tR>M.rr_ratio*1.15)
      bits.push("R:R <b>"+tR+"</b> is <b>"+(tR/M.rr_ratio).toFixed(1)+"×</b> your measured <b>"+M.rr_ratio+"</b>");
    if(tW>M.win_rate+0.03)
      bits.push("win rate <b>"+(tW*100).toFixed(1)+"%</b> vs measured <b>"+(M.win_rate*100).toFixed(1)+"%</b>");
    if(!bits.length){ box.hidden=true; return; }
    // Per-trade edge in R at the MEASURED pair — the number the cards would show
    // if the form held what the ledger actually did.
    const mEdge=M.win_rate*M.rr_ratio-(1-M.win_rate);
    box.innerHTML="⚠ <b>These cards are computed from typed values, not measured ones.</b> "
      +bits.join(", ")+"."
      +"<span class='dsub'>At the measured pair the per-trade edge is <b>"
      +(mEdge>=0?"+":"")+mEdge.toFixed(3)+"R</b>"
      +(mEdge<=0?" — negative, so no risk level reaches the target and the sizing "
                 +"below is solving an unsolvable problem":"")
      +". n="+M.n+". Press <b>Use measured</b> to see it.</span>";
    box.hidden=false;
  })();
  setHero("hc-size","st-size", over<=1.5?true:over<=3?"warn":false, over<=1.5?"Sane":over<=3?"Hot":"Reckless");

  // status line — one-sentence takeaway on the binding constraint
  let sl,slcls;
  if(insufficient){
    slcls="danger";
    sl=`<b>Behind.</b> Your edge reaches ${tgt?("€"+fmtInt(tgt)):"the target"} <b>${arrival}</b>${tgtDate?", past your "+fmtMY(tgtDate)+" target":""} — raise WR/R, trade more, or move the date.`;
  } else if(ror>5||over>3){
    slcls="danger";
    sl=`<b>Reachable, but reckless.</b> The math only closes at ${withEur(used)}/trade — ${isFinite(over)?over.toFixed(1)+"×":"∞"} over optimal, risk of ruin ${fmtPct(ror)}.`;
  } else if(ror>1||over>1.5){
    slcls="warn";
    sl=`<b>On track, sized hot.</b> Reaches goal ${arrival}, but risk is ${isFinite(over)?over.toFixed(1)+"×":"∞"} optimal (ruin ${fmtPct(ror)}) — trim or extend the date.`;
  } else {
    slcls="ok";
    sl=`<b>On track.</b> Reaches ${tgt?("€"+fmtInt(tgt)):"the target"} ${arrival} at safe risk (ruin ${fmtPct(ror)}).`;
  }
  const slEl=document.getElementById("statusline");
  if(slEl){ slEl.className="statusline "+slcls; slEl.querySelector(".sl-txt").innerHTML=sl; }
}
"""
