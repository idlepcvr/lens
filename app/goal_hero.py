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

  // 1 · On time? — reach the target inside the window
  setTxt("h-arr", projD?fmtMY(projD):"never");
  setTxt("h-arr-sub",(tgtDate?"target "+fmtMY(tgtDate):"—")+(g.days_remaining!=null?" · "+fmtInt(g.days_remaining)+"d left":""));
  setHero("hc-time","st-time", !insufficient, insufficient?"Behind":"On time");
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
