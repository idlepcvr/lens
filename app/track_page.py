"""LENS /hedge-track — the next rung, the band, and the day you're having.

/hedge-goal answers "is the whole plan still reachable?" — twelve rungs, scenario
ladders, coverage. That is a monthly question and it reads like one. This page
answers the daily one: what is the NEXT rung, am I inside the band that gets me
there, and did today count.

/today merged in here on 2026-08-21. It had been built the day before around the
same opening number — the next rung — so the two pages led with an identical
block and disagreed only in how much they said after it. What /today owned alone
was the adherence count: signals fired against fills that had a signal behind
them. That is the "Did the book follow the engine?" section, and it sits ABOVE
the fan on purpose. The fan asks whether the book is on pace; adherence asks
whether the book is running the system at all, and that question comes first.
Its trade side is scoped to LENS_BOOK, which /today never was — its fill and
orphan counts silently included every prop attempt.

Everything below the rung is COLLAPSED by default. At a glance you should see one
target and whether you are on pace for it; the 30-day detail and the rest of the
ladder are there when you go looking, not before. Native <details>, so the
collapse costs no JavaScript and keeps keyboard and screen-reader behaviour.

Amounts show in BTC and EUR together. BTC is the stored truth — the goal is 50 ₿,
not a euro figure — and EUR is a conversion at the price in lens_config, shown
with the rate so a stale price is visible rather than silently wrong.

The fan is drawn client-side from JSON embedded in the page: it needs to zoom and
rescale, which a server-rendered SVG can't do. Still no chart library and no CDN —
about 70 lines of plain SVG-building JS — so the page still works with no network.
"""

import json
from datetime import date, datetime

from .database import get_lens_config
from .theme import shell
from .track import MAX_POINTS, WEIGHTS, track

BANDS = ("p10", "p25", "p50", "p75", "p90")


def _px() -> float | None:
    """BTC price in EUR from lens_config — the same number /hedge-goal edits.

    ponytail: stored, not fetched. It avoids a network call on every render and
    there is already a field that maintains it; the page prints the rate next to
    the conversions so a stale one is obvious.
    """
    try:
        v = get_lens_config().get("btc_price_eur")
        return float(v) if v else None
    except Exception:
        return None


def _eur(v, dp: int = 0) -> str:
    if v is None:
        return "—"
    return f"{'−' if v < 0 else ''}€{abs(v):,.{dp}f}"


def _btc(v) -> str:
    if v is None:
        return "—"
    return (f"{v:.4f}".rstrip("0").rstrip(".") or "0") + " ₿"


def _eur_of(btc, px) -> str:
    return "—" if (btc is None or not px) else _eur(btc * px)


def _to_bal(v, cone: dict):
    """Cumulative-P&L value -> account equity, shifted by the balance the cone was
    anchored on. The projection is grown in P&L so deposits and withdrawals can't
    move it; this puts it back in the units you actually recognise."""
    if v is None:
        return None
    return (cone.get("base_balance") or 0) + (v - (cone.get("anchor_cum") or 0))


def _date_label(iso: str, year: bool = False) -> str:
    """`year=True` for the ladder, which spans three calendar years — "9 Dec"
    alone is genuinely ambiguous there. The fan sits inside one horizon."""
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return iso or "—"
    if year and d.year != date.today().year:
        return d.strftime("%-d %b %y")
    return d.strftime("%-d %b")


# ─── the streak strip ────────────────────────────────────────────────────────

def _strip(days: list[dict]) -> str:
    cells = []
    for d in days:
        pts, mx = d["points"], d["max_points"]
        if d["breaches"]:
            cls, why = "brk", f"{d['breaches']} off-plan"
        elif d["kept"]:
            cls, why = "kept", "kept"
        elif d["trades"] or d["decisions"]:
            cls, why = "part", "partial"
        else:
            cls, why = "idle", "nothing logged"
        h = 18 + round(pts / mx * 26)
        bits = [d["date"], why, f"{pts:g}/{mx} pts"]
        if d["trades"]:
            bits.append(f"{d['trades']} trade{'s' if d['trades'] != 1 else ''}")
        if d["decisions"]:
            bits.append(f"{d['decisions']} decided")
        if d["band_pct"]:
            bits.append(f"P{d['band_pct']}+ band")
        cells.append(f'<i class="tk-c {cls}" style="--h:{h}px" '
                     f'title="{" · ".join(bits)}"></i>')
    return '<div class="tk-strip">' + "".join(cells) + "</div>"


def _score_rows(days: list[dict]) -> str:
    n = len(days) or 1
    meta = [
        ("discipline", "No trade flagged off-plan.",
         "A breach zeroes the whole day — however well it went."),
        ("plan", "A trade taken that WAS the plan.",
         "Needs the trade marked followed-plan in the journal."),
        ("band", "Inside the projection band.",
         "Scaled by percentile: above P75 pays full, under P10 pays nothing."),
        ("decision", "A signal approved or rejected.",
         "Rejecting counts. Showing up is the point."),
    ]
    rows = []
    for key, what, note in meta:
        hit = sum(1 for d in days if d["parts"][key] > 0)
        got = sum(d["parts"][key] for d in days)
        cap = WEIGHTS[key] * n
        rows.append(
            f'<tr><td class="tk-w">{WEIGHTS[key]}</td>'
            f'<td class="tk-k">{key}<span class="tk-note">{note}</span></td>'
            f'<td class="tk-what">{what}</td>'
            f'<td class="tk-n">{hit}<span class="tk-of">/{n} d</span></td>'
            f'<td class="tk-n tk-tot">{got:g}<span class="tk-of">/{cap:g}</span></td></tr>')
    return "".join(rows)


# ─── adherence ───────────────────────────────────────────────────────────────
# Absorbed from /today on 2026-08-21. The score table below asks whether a trade
# obeyed its plan; this asks the blunter question underneath it — was there a
# signal at all. They are deliberately not merged into one number: a book can
# score full discipline while running entirely off-engine, and that is exactly
# the state this section exists to make visible.

def _grade(rate: float | None) -> tuple[str, str]:
    """(class, word). Never colour alone — the word carries the same meaning."""
    if rate is None:
        return "na", "nothing to grade"
    if rate >= 0.70:
        return "ok", "following the engine"
    if rate >= 0.40:
        return "mid", "drifting off the engine"
    return "bad", "running off-engine"


def _adherence(A: dict) -> str:
    w, y = A["window"], A["yesterday"]
    cls, word = _grade(w["rate"])
    pct = "—" if w["rate"] is None else f"{w['rate'] * 100:.0f}%"
    bar = 0.0 if w["rate"] is None else max(0.0, min(1.0, w["rate"])) * 100

    yd = _date_label(A["yesterday_date"])
    ytxt = (f"Yesterday · {yd} — {y['fired']} fired, {y['fills']} "
            f"fill{'' if y['fills'] == 1 else 's'}, {y['orphan']} with no signal"
            if (y["fired"] or y["fills"])
            else f"Yesterday · {yd} — nothing fired, nothing filled")

    return f"""
  <section class="tk-panel tk-adh" aria-label="Signal adherence">
    <header class="tk-h">
      <h2>Did the book follow the engine?</h2>
      <span class="tk-badge">last {A['window_days']} days</span>
    </header>

    <div class="tk-adh-top">
      <div class="tk-adh-rate g-{cls}">
        <b>{pct}</b>
        <span class="tk-lab">on-signal</span>
        <div class="tk-bar" role="progressbar" aria-valuenow="{bar:.0f}"
             aria-valuemin="0" aria-valuemax="100"
             aria-label="Share of fills that had a signal behind them">
          <span class="g-{cls}" style="width:{bar:.1f}%"></span>
        </div>
      </div>
      <div class="tk-nums tk-adh-nums">
        <div><span class="tk-lab">signals fired</span><b>{w['fired']}</b>
             <span class="tk-eu">engine output</span></div>
        <div><span class="tk-lab">fills</span><b>{w['fills']}</b>
             <span class="tk-eu">hedge book</span></div>
        <div><span class="tk-lab">no signal</span><b class="g-bad">{w['orphan']}</b>
             <span class="tk-eu">off-engine</span></div>
      </div>
    </div>

    <p class="tk-sub"><b>{word}</b> — {w['fills'] - w['orphan']} of {w['fills']}
       fills had an approved signal behind them. {ytxt}.</p>
    <p class="tk-sub tk-adh-note">A fill counts as on-signal when
       <code>database._link_signal</code> claimed one: an <b>approved</b> signal, same
       direction, entry within tolerance. A signal left pending or expired never
       links, so a low rate can mean signals were never <em>decided</em> as much as
       never followed. Fills are the hedge book; <b>signals have no book</b> — the
       engine fires once — so treat fired as the cross-book total, not a hedge-only
       denominator. Counts only, no P&amp;L attribution.</p>
  </section>
"""


# ─── the ladder, and the editor for it ───────────────────────────────────────

def _ladder_rows(ms: list[dict], rung: dict, px) -> str:
    out = []
    for m in ms:
        if m["done"]:
            cls = "done"
        elif m["label"] == rung.get("label"):
            cls = "now"
        else:
            cls = ""
        pin = '<span class="tk-pin" title="date you pinned">pinned</span>' if m.get("pinned") else ""
        out.append(
            f'<li class="{cls}"><b>{m["label"]}</b>'
            f'<span class="tk-lb">{_btc(m["btc"])}</span>'
            f'<span class="tk-le">{_eur_of(m["btc"], px)}</span>'
            f'<span class="tk-ld">{_date_label(m["date"], year=True) if m["date"] else "—"}{pin}</span></li>')
    return '<ol class="tk-ladder">' + "".join(out) + "</ol>"


def _editor(ms: list[dict], px) -> str:
    """Inline rung editor. Posts the WHOLE milestone list to /api/plan/amend,
    which already accepts `milestones` — no new endpoint, and every save goes
    through the same versioned, reason-required amendment path as any other plan
    change, so the ladder keeps its audit trail."""
    rows = []
    for m in ms:
        rows.append(
            '<tr class="tk-er">'
            f'<td><input class="e-label" type="text" value="{m["label"]}"></td>'
            f'<td><input class="e-btc" type="text" inputmode="decimal" value="{m["btc"]}"></td>'
            '<td class="e-eur">—</td>'
            f'<td><input class="e-by" type="date" value="{m.get("by") or ""}"></td>'
            '<td><button type="button" class="tk-x" title="remove rung">×</button></td>'
            '</tr>')
    return f"""
<div class="tk-editor">
  <p class="tk-sub">Type a target in ₿ (EUR follows at the rate below). Leave the
     date blank to let it be derived; set one to <b>pin</b> it — pinned dates are
     never recomputed, and the rungs beneath them compress to fit.</p>
  <div class="tk-etw">
  <table class="tk-etab">
    <thead><tr><th>rung</th><th>₿ target</th><th>≈ EUR</th><th>by (optional)</th><th></th></tr></thead>
    <tbody id="e-body">{"".join(rows)}</tbody>
  </table>
  </div>
  <div class="tk-erow">
    <button type="button" class="tk-btn" id="e-add">+ Add rung</button>
    <input type="text" id="e-reason" placeholder="Why are you changing the plan? (20 chars min)">
    <button type="button" class="tk-btn prim" id="e-save">Save plan</button>
  </div>
  <p class="tk-msg" id="e-msg"></p>
</div>"""


# ─── client ──────────────────────────────────────────────────────────────────
# Plain SVG-building. No library, no CDN — the box this runs on may have no
# network, and eleven cone samples never justified a canvas engine.

_JS = r"""
(function(){
  var SVG="http://www.w3.org/2000/svg", W=720, H=260;
  var L=54, Rt=16, Tp=16, Bt=32, PW=W-L-Rt, PH=H-Tp-Bt;
  var svg=document.getElementById("fan"); if(!svg) return;
  var range="rung", mode="bal";
  var readEl=document.getElementById("fan-read");

  function eur(v,dp){ dp=dp||0;
    return (v<0?"−":"")+"€"+Math.abs(v).toLocaleString("en-GB",
      {minimumFractionDigits:dp,maximumFractionDigits:dp}); }
  function fmt(v){ return mode==="pct" ? (v>=0?"+":"−")+Math.abs(v).toFixed(1)+"%" : eur(v); }
  // % mode measures the swing SINCE THE ANCHOR as a share of the account, so it
  // starts at 0 and reads like a return. Dividing raw cumulative P&L by the
  // account instead gives −1000%+, because the cumulative runs from the first
  // trade ever while the account is today's. A log axis is not an option here:
  // cumulative P&L goes negative, where log is undefined.
  // Three ways to read the same projection.
  //   bal — account equity. The cone is grown in cumulative P&L because
  //         deposits and withdrawals must not move it, but equity is the number
  //         you actually recognise, so shift it by the balance it was anchored
  //         on. Both series meet at the anchor by construction, and the ruin
  //         floor lands on a literal zero.
  //   eur — raw cumulative realised P&L, the cone's native axis.
  //   pct — the swing since the anchor as a share of the account.
  function conv(v){
    if(mode==="bal") return (FAN.base||0) + (v-(FAN.anchorCum||0));
    if(mode==="pct") return FAN.base ? (v-(FAN.anchorCum||0))/FAN.base*100 : 0;
    return v; }
  // the ruin floor in whatever unit is on screen
  function floorVal(){
    if(FAN.floor==null) return null;
    return mode==="bal" ? 0 : (mode==="pct" ? -100 : FAN.floor); }
  function el(n,a){ var e=document.createElementNS(SVG,n);
    for(var k in a) e.setAttribute(k,a[k]); return e; }

  function windowTs(){
    var now=Date.now()/1000|0;
    if(range==="rung") return [FAN.points.length?FAN.points[0].t:now,
                               FAN.points.length?FAN.points[FAN.points.length-1].t:now];
    var d=(range==="90"?90:30)*86400;
    return [now-d, now+d/3];
  }

  function draw(){
    while(svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute("viewBox","0 0 "+W+" "+H);
    var pts=FAN.points||[], act=FAN.actual||[];
    if(pts.length<2){
      svg.appendChild(el("text",{x:W/2,y:H/2,class:"tk-ax tk-ax-c"})).textContent=
        "No projection yet — needs closed trades and a balance snapshot.";
      return;
    }
    var w=windowTs(), x0=w[0], x1=w[1];
    var vis=pts.filter(function(p){return p.t>=x0-86400*7 && p.t<=x1+86400*7;});
    if(vis.length<2) vis=pts;
    var va=act.filter(function(a){return a.t>=x0 && a.t<=x1;});

    // In balance mode the realised line is the REAL equity snapshots, not the
    // band's transform — actual money beats a derivation, and the two agree at
    // the anchor anyway.
    var vb = mode==="bal"
      ? (FAN.balances||[]).filter(function(b){return b.t>=x0 && b.t<=x1;})
      : [];

    var vals=[];
    vis.forEach(function(p){ ["p10","p25","p50","p75","p90"].forEach(function(k){
      if(p[k]!=null) vals.push(conv(p[k])); }); });
    if(mode==="bal"){ vb.forEach(function(b){ vals.push(b.v); }); }
    else { va.forEach(function(a){ vals.push(conv(a.cum)); }); }
    var fv0=floorVal(); if(fv0!=null) vals.push(fv0);
    if(!vals.length) return;
    var lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
    if(hi-lo<1e-9){ lo-=1; hi+=1; }
    var pad=(hi-lo)*0.08; lo-=pad; hi+=pad;
    // an account cannot hold less than nothing, so the balance axis stops at 0
    if(mode==="bal") lo=Math.max(lo,0);

    function px(t){ return L+(t-x0)/Math.max(x1-x0,1)*PW; }
    function pyRaw(v){ return Tp+(hi-v)/(hi-lo)*PH; }
    function py(v){ return pyRaw(conv(v)); }

    function ribbon(a,b){
      var up=vis.map(function(p){return px(p.t).toFixed(1)+","+py(p[b]).toFixed(1);}).join(" ");
      var dn=vis.slice().reverse().map(function(p){return px(p.t).toFixed(1)+","+py(p[a]).toFixed(1);}).join(" ");
      return up+" "+dn;
    }
    svg.appendChild(el("polygon",{points:ribbon("p10","p90"),class:"tk-b10"}));
    svg.appendChild(el("polygon",{points:ribbon("p25","p75"),class:"tk-b25"}));

    // gridlines: five ticks, labelled in the active unit
    for(var i=0;i<=4;i++){
      var v=lo+(hi-lo)*i/4, y=Tp+(hi-v)/(hi-lo)*PH;
      svg.appendChild(el("line",{x1:L,y1:y.toFixed(1),x2:W-Rt,y2:y.toFixed(1),
        class:(Math.abs(v)<1e-9?"tk-zero":"tk-grid")}));
      var t=el("text",{x:L-7,y:(y+3.5).toFixed(1),class:"tk-ax tk-ax-r"});
      t.textContent=mode==="pct"?(v>=0?"+":"−")+Math.abs(v).toFixed(1)+"%":eur(v);
      svg.appendChild(t);
    }

    // The ruin floor. A fan drawn without it looks like a spread of outcomes;
    // with it you can see how much of the spread is "account gone".
    if(FAN.floor!=null){
      var fv=floorVal(), fy=Tp+(hi-fv)/(hi-lo)*PH;
      if(fy>=Tp-2&&fy<=Tp+PH+2){
        svg.appendChild(el("line",{x1:L,y1:fy.toFixed(1),x2:W-Rt,y2:fy.toFixed(1),class:"tk-floor"}));
        var ft=el("text",{x:W-Rt,y:(fy-5).toFixed(1),class:"tk-ax tk-ax-e tk-ax-bad"});
        ft.textContent=mode==="bal"?"account gone (€0)":"account gone"; svg.appendChild(ft);
      }
    }
    svg.appendChild(el("polyline",{class:"tk-p50",
      points:vis.map(function(p){return px(p.t).toFixed(1)+","+py(p.p50).toFixed(1);}).join(" ")}));

    var line = mode==="bal"
      ? vb.map(function(b){return {t:b.t, y:pyRaw(b.v)};})
      : va.map(function(a){return {t:a.t, y:py(a.cum)};});
    if(line.length>1){
      svg.appendChild(el("polyline",{class:"tk-act",
        points:line.map(function(q){return px(q.t).toFixed(1)+","+q.y.toFixed(1);}).join(" ")}));
      var last=line[line.length-1];
      svg.appendChild(el("circle",{cx:px(last.t).toFixed(1),cy:last.y.toFixed(1),
        r:3.8,class:"tk-act-dot"}));
    }

    var now=Date.now()/1000|0, nx=px(now);
    if(nx>=L&&nx<=W-Rt){
      svg.appendChild(el("line",{x1:nx.toFixed(1),y1:Tp,x2:nx.toFixed(1),y2:Tp+PH,class:"tk-now"}));
      var tn=el("text",{x:nx.toFixed(1),y:Tp+PH+13,class:"tk-ax tk-ax-c"});
      tn.textContent="today"; svg.appendChild(tn);
    }
    // rung deadline, when it is inside the window
    if(FAN.rung && FAN.rung.date){
      var rt=Date.parse(FAN.rung.date+"T00:00:00Z")/1000, rx=px(rt);
      if(rx>=L&&rx<=W-Rt){
        svg.appendChild(el("line",{x1:rx.toFixed(1),y1:Tp,x2:rx.toFixed(1),y2:Tp+PH,class:"tk-rungline"}));
        // anchor flips near the edges or the label clips out of the viewBox
        var anc=rx>W-Rt-40?"tk-ax-e":(rx<L+40?"":"tk-ax-c");
        var tr=el("text",{x:rx.toFixed(1),y:Tp+PH+26,class:"tk-ax tk-ax-hl "+anc});
        tr.textContent=FAN.rung.label||"rung"; svg.appendChild(tr);
      }
    }
    var d0=el("text",{x:L,y:Tp+PH+13,class:"tk-ax"});
    d0.textContent=new Date(x0*1000).toLocaleDateString("en-GB",{day:"numeric",month:"short"});
    svg.appendChild(d0);
    var d1=el("text",{x:W-Rt,y:Tp+PH+13,class:"tk-ax tk-ax-e"});
    d1.textContent=new Date(x1*1000).toLocaleDateString("en-GB",{day:"numeric",month:"short"});
    svg.appendChild(d1);

    // hover readout — the "more detail" that a static image can't give
    var hit=el("rect",{x:L,y:Tp,width:PW,height:PH,fill:"transparent"});
    svg.appendChild(hit);
    var cross=el("line",{class:"tk-cross",x1:0,y1:Tp,x2:0,y2:Tp+PH,style:"display:none"});
    svg.appendChild(cross);
    hit.addEventListener("mousemove",function(ev){
      var r=svg.getBoundingClientRect(), sx=(ev.clientX-r.left)/r.width*W;
      if(sx<L||sx>W-Rt) return;
      cross.setAttribute("x1",sx); cross.setAttribute("x2",sx);
      cross.style.display="";
      var t=x0+(sx-L)/PW*(x1-x0), near=null, dmin=1e18;
      vis.forEach(function(p){ var d=Math.abs(p.t-t); if(d<dmin){dmin=d;near=p;} });
      var na=null; dmin=1e18;
      va.forEach(function(a){ var d=Math.abs(a.t-t); if(d<dmin){dmin=d;na=a;} });
      if(!near) return;
      var s=new Date(near.t*1000).toLocaleDateString("en-GB",{day:"numeric",month:"short"})+
        "  P10 "+fmt(conv(near.p10))+"  P50 "+fmt(conv(near.p50))+"  P90 "+fmt(conv(near.p90));
      if(mode==="bal"){
        var nb=null, bmin=1e18;
        vb.forEach(function(b){ var d=Math.abs(b.t-t); if(d<bmin){bmin=d;nb=b;} });
        if(nb) s+="   ·  you "+eur(nb.v);
      } else if(na) s+="   ·  you "+fmt(conv(na.cum));
      readEl.textContent=s;
    });
    hit.addEventListener("mouseleave",function(){ cross.style.display="none"; readEl.textContent=""; });
  }

  document.querySelectorAll("[data-range]").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll("[data-range]").forEach(function(o){o.classList.remove("on");});
      b.classList.add("on"); range=b.dataset.range; draw(); }); });
  document.querySelectorAll("[data-mode]").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll("[data-mode]").forEach(function(o){o.classList.remove("on");});
      b.classList.add("on"); mode=b.dataset.mode; draw(); }); });
  draw();
  addEventListener("resize",draw);
})();

// ── rung editor ─────────────────────────────────────────────────────────────
(function(){
  var body=document.getElementById("e-body"); if(!body) return;

  // "Edit ladder" points at a collapsed <details>; a fragment link scrolls to it
  // but does not open it, so open it here and on any later hash change.
  function openIfTargeted(){
    if(location.hash!=="#edit") return;
    var d=document.getElementById("edit");
    if(d){ d.open=true; d.scrollIntoView({block:"start",behavior:"smooth"}); }
  }
  addEventListener("hashchange",openIfTargeted);
  openIfTargeted();
  var msg=document.getElementById("e-msg");

  function eurCells(){
    body.querySelectorAll("tr").forEach(function(tr){
      var v=parseFloat(tr.querySelector(".e-btc").value);
      var c=tr.querySelector(".e-eur");
      c.textContent=(PX&&isFinite(v))
        ? "€"+(v*PX).toLocaleString("en-GB",{maximumFractionDigits:0}) : "—";
    });
  }
  function wire(tr){
    tr.querySelector(".e-btc").addEventListener("input",eurCells);
    tr.querySelector(".tk-x").addEventListener("click",function(){ tr.remove(); eurCells(); });
  }
  body.querySelectorAll("tr").forEach(wire);
  eurCells();

  document.getElementById("e-add").addEventListener("click",function(){
    var tr=document.createElement("tr"); tr.className="tk-er";
    tr.innerHTML='<td><input class="e-label" type="text" value="New rung"></td>'+
      '<td><input class="e-btc" type="text" inputmode="decimal" value=""></td>'+
      '<td class="e-eur">—</td>'+
      '<td><input class="e-by" type="date" value=""></td>'+
      '<td><button type="button" class="tk-x" title="remove rung">×</button></td>';
    body.appendChild(tr); wire(tr); eurCells();
    tr.querySelector(".e-btc").focus();
  });

  document.getElementById("e-save").addEventListener("click",function(){
    var out=[], bad=null;
    body.querySelectorAll("tr").forEach(function(tr){
      var label=tr.querySelector(".e-label").value.trim();
      var btc=parseFloat(tr.querySelector(".e-btc").value);
      var by=tr.querySelector(".e-by").value;
      if(!label||!isFinite(btc)||btc<=0){ bad=label||"a rung"; return; }
      var m={btc:btc,label:label};
      if(by) m.by=by;
      out.push(m);
    });
    if(bad){ msg.className="tk-msg bad";
      msg.textContent="“"+bad+"” needs a name and a positive ₿ target."; return; }
    if(!out.length){ msg.className="tk-msg bad"; msg.textContent="Keep at least one rung."; return; }
    out.sort(function(a,b){ return a.btc-b.btc; });
    var reason=document.getElementById("e-reason").value.trim();
    msg.className="tk-msg"; msg.textContent="Saving…";
    fetch("/api/plan/amend",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({milestones:out,reason:reason})})
      .then(function(r){ return r.json().then(function(j){ return {ok:r.ok,j:j}; }); })
      .then(function(res){
        if(!res.ok){ msg.className="tk-msg bad";
          msg.textContent=(res.j && res.j.detail) || "Save failed."; return; }
        msg.className="tk-msg good"; msg.textContent="Saved — reloading…";
        setTimeout(function(){ location.reload(); },500);
      })
      .catch(function(){ msg.className="tk-msg bad"; msg.textContent="Save failed — no response."; });
  });
})();
"""


_CSS = """<style>
.tk{max-width:1000px;margin:0 auto;padding:0 14px 10px}
.tk-panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;
  padding:15px 16px 16px;margin-top:14px}
.tk-h{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.tk-h h2{font-family:var(--hud);font-size:14px;font-weight:600;color:var(--ink);margin:0}
.tk-h .tk-badge{margin-left:auto}

/* hero */
.tk-hero{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:18px 18px 20px;margin-top:14px}
.tk-hero-top{display:flex;align-items:flex-start;gap:14px;justify-content:space-between}
.tk-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--dim);display:block;margin-bottom:5px}
.tk-rung{font-family:var(--hud);font-size:30px;font-weight:700;color:var(--ink);
  margin:0;line-height:1.05;text-wrap:balance}
.tk-status{font-family:var(--mono);font-size:11px;font-weight:800;letter-spacing:.1em;
  padding:4px 9px;border-radius:999px;border:1px solid var(--line);color:var(--dim);
  white-space:nowrap;flex:none}
.tk-status.s-AHEAD,.tk-status.s-ON{color:var(--long);border-color:var(--long)}
.tk-status.s-BEHIND{color:var(--amber);border-color:var(--amber)}
.tk-status.s-OFF-PLAN{color:var(--short);border-color:var(--short)}
.tk-nums{display:flex;flex-wrap:wrap;gap:12px 30px;margin:16px 0 13px}
.tk-nums>div{display:flex;flex-direction:column;gap:1px}
.tk-lab{font-family:var(--mono);font-size:9.5px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--dim)}
.tk-nums b{font-family:var(--mono);font-size:17px;font-weight:700;color:var(--ink)}
.tk-eu{font-family:var(--mono);font-size:11px;color:var(--dim)}
.tk-bar{height:8px;border-radius:999px;background:var(--bg);border:1px solid var(--line);
  overflow:hidden}
.tk-bar>span{display:block;height:100%;background:var(--accent);border-radius:999px;
  transition:width .24s cubic-bezier(.22,1,.36,1)}
.tk-sub{font-size:12px;line-height:1.55;color:var(--dim);margin:9px 0 0;max-width:74ch}
.tk-sub b{color:var(--ink);font-family:var(--mono)}
.tk-stale{color:var(--amber);margin-left:6px}
.tk-warn{font-size:12px;line-height:1.55;color:var(--amber);margin:12px 0 0;max-width:74ch}
.tk-badge{font-family:var(--mono);font-size:10px;color:var(--dim)}

/* adherence — absorbed from /today 2026-08-21. Uses the spacing and radius
   scale theme.py added the same day; the rest of this file predates it and
   still hard-codes its gaps. The rate keeps its own bar rather than one
   spanning the panel, which read as an underline of the first count instead
   of a gauge for the percentage.
   NB: never write the scale's token names with a star-slash in a comment —
   the slash closes the comment early and silently eats the rules below it. */
.tk-adh-top{display:flex;align-items:stretch;gap:var(--s5);flex-wrap:wrap;
  margin-bottom:var(--s4)}
.tk-adh-rate{display:flex;flex-direction:column;flex:0 0 auto;min-width:158px}
.tk-adh-rate b{font-family:var(--mono);font-size:46px;font-weight:800;line-height:.92;
  color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.tk-adh-rate .tk-lab{margin-top:var(--s2)}
.tk-adh-rate .tk-bar{margin-top:auto}
.tk-adh-nums{margin:0;flex:1 1 320px;align-items:center;gap:var(--s3) var(--s5);
  padding-left:var(--s5);border-left:1px solid var(--line)}
.tk-adh-note{color:var(--dim);margin-top:var(--s3)}
.tk-adh-note code{font-family:var(--mono);font-size:11px;background:var(--bg);
  border:1px solid var(--line);border-radius:var(--r1);padding:1px 5px;color:var(--dim)}
/* grade carries in colour AND in the word beside it, never colour alone */
.tk-adh-rate.g-ok b{color:var(--long)}
.tk-adh-rate.g-mid b{color:var(--amber)}
.tk-adh-rate.g-bad b{color:var(--short)}
.tk-adh-rate.g-na b{color:var(--dim)}
.tk-nums b.g-bad{color:var(--short)}
.tk-bar>span.g-ok{background:var(--long)}
.tk-bar>span.g-mid{background:var(--amber)}
.tk-bar>span.g-bad{background:var(--short)}
.tk-bar>span.g-na{background:var(--line2)}
@media (max-width:620px){
  .tk-adh-rate{flex:1 1 100%;min-width:0}
  .tk-adh-rate .tk-bar{margin-top:var(--s3)}
  .tk-adh-rate b{font-size:38px}
  .tk-adh-nums{flex-basis:100%;padding-left:0;padding-top:var(--s4);
    border-left:0;border-top:1px solid var(--line)}
}
/* chart controls */
.tk-ctl{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin-bottom:8px}
.tk-seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.tk-seg button{font-family:var(--mono);font-size:10.5px;letter-spacing:.04em;
  background:transparent;color:var(--dim);border:0;padding:5px 10px;cursor:pointer;
  transition:background .15s ease-out,color .15s ease-out}
.tk-seg button+button{border-left:1px solid var(--line)}
.tk-seg button:hover{color:var(--ink)}
.tk-seg button.on{background:var(--accent);color:#04070d;font-weight:700}
.tk-seg button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.tk-read{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-left:auto;
  min-height:14px;text-align:right}

/* fan */
.tk-fanwrap{overflow-x:auto}
.tk-fan{width:100%;height:auto;display:block;min-height:210px}
.tk-b10{fill:var(--accent);opacity:.09}
.tk-b25{fill:var(--accent);opacity:.17}
.tk-p50{fill:none;stroke:var(--dim);stroke-width:1.3;stroke-dasharray:4 3}
.tk-act{fill:none;stroke:var(--long);stroke-width:2.1;stroke-linejoin:round;stroke-linecap:round}
.tk-act-dot{fill:var(--long)}
.tk-now{stroke:var(--faint);stroke-width:1;stroke-dasharray:2 3}
.tk-rungline{stroke:var(--accent);stroke-width:1;stroke-dasharray:3 3;opacity:.7}
.tk-cross{stroke:var(--dim);stroke-width:1;stroke-dasharray:2 2;opacity:.7}
.tk-zero{stroke:var(--line);stroke-width:1.2}
.tk-grid{stroke:var(--line);stroke-width:.6;opacity:.5}
.tk-ax{font-family:var(--mono);font-size:9px;fill:var(--dim)}
.tk-ax-r{text-anchor:end}.tk-ax-c{text-anchor:middle}.tk-ax-e{text-anchor:end}
.tk-ax-hl{fill:var(--accent)}
.tk-ax-bad{fill:var(--short)}
.tk-floor{stroke:var(--short);stroke-width:1.1;stroke-dasharray:5 3;opacity:.85}

/* collapsible sections */
.tk-det{padding:0}
.tk-det>summary{list-style:none;cursor:pointer;padding:15px 16px;display:flex;
  align-items:baseline;gap:12px;flex-wrap:wrap;border-radius:13px}
.tk-det>summary::-webkit-details-marker{display:none}
.tk-det>summary::after{content:"+";font-family:var(--mono);color:var(--dim);
  margin-left:auto;font-size:14px;line-height:1}
.tk-det[open]>summary::after{content:"−"}
.tk-det>summary:hover .tk-sum-h{color:var(--accent)}
.tk-det>summary:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.tk-sum-h{font-family:var(--hud);font-size:14px;font-weight:600;color:var(--ink);
  transition:color .15s ease-out}
.tk-det>*:not(summary){margin-left:16px;margin-right:16px}
.tk-det>*:last-child{margin-bottom:16px}

/* streak strip */
.tk-strip{display:flex;align-items:flex-end;gap:3px;height:46px;margin-bottom:11px}
.tk-c{flex:1 1 0;min-width:4px;height:var(--h);border-radius:2px;display:block;
  background:var(--line);transition:transform .15s ease-out}
.tk-c.kept{background:var(--long)}
.tk-c.part{background:var(--accent);opacity:.55}
.tk-c.brk{background:var(--short)}
.tk-strip .tk-c:hover{transform:scaleY(1.09)}
.tk-legend{display:flex;flex-wrap:wrap;gap:5px 15px;align-items:center;
  font-family:var(--mono);font-size:10px;color:var(--dim);margin-bottom:14px}
.tk-legend span{display:flex;align-items:center;gap:5px}
.tk-legend .tk-c{flex:none;width:9px}
.tk-streak{font-family:var(--mono);font-size:11px;color:var(--dim)}
.tk-streak b{font-size:17px;color:var(--ink);font-weight:800}
.tk-of{color:var(--dim);font-family:var(--mono);font-size:10px;margin-left:5px}

/* score table */
.tk-score{width:100%;border-collapse:collapse;font-size:12px}
.tk-score th{font-family:var(--mono);font-size:9px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);text-align:left;font-weight:400;
  padding:0 8px 7px 0;border-bottom:1px solid var(--line)}
.tk-score td{padding:9px 8px 9px 0;border-bottom:1px solid var(--line);vertical-align:top}
.tk-score tfoot td{border-bottom:none;padding-top:11px}
.tk-w{font-family:var(--mono);font-size:13px;font-weight:800;color:var(--accent);width:26px}
.tk-k{font-family:var(--hud);font-weight:600;color:var(--ink);white-space:nowrap}
.tk-note{display:block;font-family:var(--hud);font-weight:400;font-size:10.5px;
  color:var(--dim);white-space:normal;max-width:30ch;margin-top:2px}
.tk-what{color:var(--dim);line-height:1.5}
.tk-n{font-family:var(--mono);text-align:right;color:var(--dim);white-space:nowrap}
.tk-tot{color:var(--ink);font-weight:700}
.tk-score th:nth-child(4),.tk-score th:nth-child(5){text-align:right}

/* ladder */
.tk-ladder{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:1px}
.tk-ladder li{display:flex;align-items:baseline;gap:10px;padding:7px 9px;
  border-radius:7px;font-size:12px;color:var(--dim)}
.tk-ladder li b{font-family:var(--hud);font-weight:600;color:var(--dim);flex:1 1 auto}
.tk-ladder li.done{color:var(--faint)}
.tk-ladder li.done b{color:var(--faint);text-decoration:line-through;
  text-decoration-color:var(--line)}
.tk-ladder li.now{background:var(--bg);border:1px solid var(--accent)}
.tk-ladder li.now b{color:var(--ink)}
.tk-lb{font-family:var(--mono);font-size:11px;width:74px;text-align:right;flex:none}
.tk-le{font-family:var(--mono);font-size:11px;color:var(--dim);width:70px;
  text-align:right;flex:none}
.tk-ld{font-family:var(--mono);font-size:11px;color:var(--dim);width:96px;
  text-align:right;flex:none;white-space:nowrap}
.tk-pin{color:var(--accent);font-size:9px;margin-left:5px}

/* editor */
.tk-editor{margin-top:2px}
.tk-hero-r{display:flex;flex-direction:column;align-items:flex-end;gap:7px;flex:none}
.tk-edit-link{font-family:var(--mono);font-size:10.5px;color:var(--dim);
  text-decoration:none;border-bottom:1px solid var(--line);padding-bottom:1px}
.tk-edit-link:hover{color:var(--accent);border-color:var(--accent)}
.tk-etw{overflow-x:auto}
.tk-etab{width:100%;border-collapse:collapse;font-size:12px;margin:10px 0;min-width:460px}
.tk-etab th{font-family:var(--mono);font-size:9px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);text-align:left;font-weight:400;
  padding:0 6px 6px 0}
.tk-etab td{padding:3px 6px 3px 0}
.tk-etab input{background:var(--bg);border:1px solid var(--line);border-radius:6px;
  color:var(--ink);font-family:var(--mono);font-size:12px;padding:5px 7px;width:100%}
.tk-etab input:focus{outline:none;border-color:var(--accent)}
.tk-etab .e-eur{font-family:var(--mono);font-size:11px;color:var(--dim);white-space:nowrap}
.tk-x{background:transparent;border:1px solid var(--line);border-radius:6px;
  color:var(--dim);cursor:pointer;font-size:13px;line-height:1;padding:4px 8px;
  transition:color .15s ease-out,border-color .15s ease-out}
.tk-x:hover{color:var(--short);border-color:var(--short)}
.tk-erow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px}
.tk-erow input{flex:1 1 240px;background:var(--bg);border:1px solid var(--line);
  border-radius:8px;color:var(--ink);font-size:12px;padding:7px 10px}
.tk-erow input:focus{outline:none;border-color:var(--accent)}
.tk-btn{font-family:var(--mono);font-size:11px;background:transparent;
  border:1px solid var(--line);border-radius:8px;color:var(--dim);padding:7px 12px;
  cursor:pointer;transition:color .15s ease-out,border-color .15s ease-out}
.tk-btn:hover{color:var(--ink);border-color:var(--dim)}
.tk-btn.prim{border-color:var(--accent);color:var(--accent)}
.tk-btn.prim:hover{background:var(--accent);color:#04070d}
.tk-msg{font-family:var(--mono);font-size:11px;color:var(--dim);margin:9px 0 0;min-height:14px}
.tk-msg.bad{color:var(--short)}
.tk-msg.good{color:var(--long)}

@media(max-width:720px){
  .tk-rung{font-size:24px}
  .tk-nums{gap:12px 22px}
  .tk-nums b{font-size:15px}
  .tk-strip{gap:2px}
  .tk-fan{min-width:560px}
  .tk-note{display:none}
  .tk-k{white-space:normal}
  .tk-read{margin-left:0;text-align:left;flex-basis:100%}
  .tk-le{display:none}
}
@media(prefers-reduced-motion:reduce){
  .tk-bar>span,.tk-c,.tk-seg button,.tk-btn,.tk-x,.tk-sum-h{transition:none}
  .tk-strip .tk-c:hover{transform:none}
}
</style>"""


# ─── page ────────────────────────────────────────────────────────────────────

def parts() -> dict:
    T = track()
    R, S, C = T["rung"], T["streak"], T["cone"]
    sc = T["score"]
    px = _px()
    status = (T["status"] or "—").upper()
    now = C.get("now") or {}

    from .plan import ladder as _l
    try:
        ms = _l()["milestones"]
    except Exception:
        ms = []

    bal_now = T["balances"][-1]["v"] if T["balances"] else None
    bar_pct = 0.0 if R.get("progress_pct") is None else max(0.0, min(100.0, R["progress_pct"]))
    left = R.get("days_left")
    stale = (f'<span class="tk-stale">stack snapshot is {R.get("age_days")} d old</span>'
             if R.get("stale") else "")

    unrev = ""
    if sc["unreviewed"]:
        unrev = (f'<p class="tk-warn">{sc["unreviewed"]} trade'
                 f'{"s" if sc["unreviewed"] != 1 else ""} in this window are unmarked, '
                 'so discipline is scoring silence rather than conduct. Mark them '
                 'followed-plan or off-plan in the journal and this number becomes real.</p>')

    # When the median simulated path reaches the ruin floor, the fan is not a
    # spread of outcomes any more — most of it is the account being gone. That
    # cannot be left to the reader to infer off a shaded polygon.
    ruin = ""
    floor = C.get("floor")
    pts = C.get("points") or []
    if floor is not None and pts:
        hit = next((p for p in pts if p.get("p50") is not None
                    and p["p50"] <= floor + 1e-6), None)
        if hit:
            when = _date_label(datetime.utcfromtimestamp(hit["t"]).date().isoformat())
            ruin = (f'<p class="tk-warn">Read this before the shape: the <b>median</b> '
                    f'simulated path reaches the ruin floor by <b>{when}</b>. More than '
                    'half of the runs drawn from your own closed trades end with the '
                    'account gone before this rung is due. The status word grades where '
                    'today sits inside that band — it is not a verdict on the band.</p>')

    fan_data = json.dumps({
        "points": C.get("points") or [],
        "actual": T["actual"],
        "balances": T["balances"],
        "base": C.get("base_balance") or 0,
        "rung": {"date": R.get("date"), "label": R.get("label")},
        "anchor": C.get("anchor"),
        "anchorCum": C.get("anchor_cum") or 0,
        "floor": C.get("floor"),
        "paths": C.get("paths") or 0,
    })

    body = f"""
<main class="tk">

  <section class="tk-hero" aria-label="Next milestone">
    <div class="tk-hero-top">
      <div>
        <span class="tk-eyebrow">next rung</span>
        <h1 class="tk-rung">{R.get('label') or 'No rung derivable'}</h1>
      </div>
      <div class="tk-hero-r">
        <span class="tk-status s-{status}">{status}</span>
        <a class="tk-edit-link" href="#edit">Edit ladder</a>
      </div>
    </div>

    <div class="tk-nums">
      <div><span class="tk-lab">stack</span><b>{_btc(R.get('stack_btc'))}</b>
           <span class="tk-eu">{_eur_of(R.get('stack_btc'), px)}</span></div>
      <div><span class="tk-lab">rung</span><b>{_btc(R.get('btc'))}</b>
           <span class="tk-eu">{_eur_of(R.get('btc'), px)}</span></div>
      <div><span class="tk-lab">by</span><b>{_date_label(R.get('date') or '')}</b>
           <span class="tk-eu">{left if left is not None else '—'} days left</span></div>
      <div><span class="tk-lab">to go</span>
           <b>{_eur_of((R.get('btc') or 0) - (R.get('stack_btc') or 0), px)}</b>
           <span class="tk-eu">{_btc((R.get('btc') or 0) - (R.get('stack_btc') or 0))}</span></div>
    </div>

    <div class="tk-bar" role="progressbar" aria-valuenow="{bar_pct:.0f}"
         aria-valuemin="0" aria-valuemax="100"
         aria-label="Progress to {R.get('label') or 'next rung'}">
      <span style="width:{bar_pct:.1f}%"></span>
    </div>
    <p class="tk-sub">{bar_pct:.0f}% of the way from {_btc(R.get('from_btc'))} to
       {_btc(R.get('btc'))} · {R.get('overall_pct') or 0}% of the {_btc(R.get('goal_btc'))} goal
       · EUR at {_eur(px)}/₿ {stale}</p>
  </section>

{_adherence(T['adherence'])}
  <section class="tk-panel" aria-label="Projection band">
    <header class="tk-h">
      <h2>Where you should be</h2>
      <span class="tk-badge">{C.get('badge') or 'no sample'}</span>
    </header>
    <div class="tk-ctl" role="group" aria-label="Chart controls">
      <span class="tk-seg" role="group" aria-label="Time range">
        <button type="button" data-range="rung" class="on">To the rung</button>
        <button type="button" data-range="90">90d</button>
        <button type="button" data-range="30">30d</button>
      </span>
      <span class="tk-seg" role="group" aria-label="What to plot">
        <button type="button" data-mode="bal" class="on">Balance €</button>
        <button type="button" data-mode="eur">Realised P&amp;L</button>
        <button type="button" data-mode="pct">% of account</button>
      </span>
      <span class="tk-read" id="fan-read" aria-live="polite"></span>
    </div>
    <div class="tk-fanwrap"><svg id="fan" class="tk-fan" role="img"
      aria-label="Projection fan: simulated cumulative profit and loss from
      {C.get('anchor')} to the {R.get('label') or 'next'} rung, with the realised
      line drawn through it."></svg></div>
    <p class="tk-sub">Balance <b>{_eur(bal_now, 2)}</b> today, against a P25–P75 band of
       {_eur(_to_bal(now.get('p25'), C), 2)} – {_eur(_to_bal(now.get('p75'), C), 2)}.
       The shaded fan is {C.get('paths') or 0} simulated paths drawn from your own closed
       trades — not a straight line, because your equity curve isn't one. Switch to
       <b>Realised P&amp;L</b> for the cone's native axis, where deposits and withdrawals
       can't move the line.</p>
    {ruin}
  </section>

  <details class="tk-panel tk-det" aria-label="Daily score">
    <summary><span class="tk-sum-h">The last {T['window_days']} days</span>
      <span class="tk-streak"><b>{S['current']}</b> day streak
        <span class="tk-of">best {S['best']}</span></span></summary>
    {_strip(T['days'])}
    <div class="tk-legend">
      <span><i class="tk-c kept" style="--h:10px"></i>kept</span>
      <span><i class="tk-c part" style="--h:10px"></i>partial</span>
      <span><i class="tk-c brk" style="--h:10px"></i>breach</span>
      <span><i class="tk-c idle" style="--h:10px"></i>nothing logged</span>
      <span class="tk-of">bar height = points that day</span>
    </div>
    <table class="tk-score">
      <thead><tr><th>pts</th><th>component</th><th>earned when</th>
        <th>days</th><th>total</th></tr></thead>
      <tbody>{_score_rows(T['days'])}</tbody>
      <tfoot><tr><td class="tk-w">{MAX_POINTS}</td><td class="tk-k">score</td>
        <td class="tk-what">A streak day needs discipline kept AND something logged.</td>
        <td class="tk-n">{sc['traded_days']}<span class="tk-of">/{len(T['days'])} traded</span></td>
        <td class="tk-n tk-tot">{sc['earned']:g}<span class="tk-of">/{sc['possible']:g}</span></td></tr></tfoot>
    </table>
    {unrev}
  </details>

  <details class="tk-panel tk-det" aria-label="Remaining rungs">
    <summary><span class="tk-sum-h">After that</span>
      <span class="tk-of">the rest of the ladder</span></summary>
    {_ladder_rows(ms, R, px)}
  </details>

  <details class="tk-panel tk-det" id="edit" aria-label="Edit the ladder">
    <summary><span class="tk-sum-h">Edit the ladder</span>
      <span class="tk-of">rungs, targets and the dates you pin</span></summary>
    {_editor(ms, px)}
  </details>

</main>"""

    script = "const FAN=" + fan_data + ";const PX=" + json.dumps(px) + ";" + _JS
    return {"body": body, "css": _CSS, "script": script}


def render() -> str:
    p = parts()
    return shell("/hedge-track", "Track", p["body"], head_extra=p["css"],
                 script=p["script"], meta="am I on pace?")
