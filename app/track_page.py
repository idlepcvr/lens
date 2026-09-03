"""LENS /track — the next rung, the band, and the day you're having.

/goal answers "is the whole plan still reachable?" — twelve rungs, scenario
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
from .track import NEAR_DAYS, track

BANDS = ("p10", "p25", "p50", "p75", "p90")


def _px() -> float | None:
    """BTC price in EUR from lens_config — the same number /goal edits.

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


# ─── the step ladder ─────────────────────────────────────────────────────────
# The hero says "62% of the way to the rung". This says what the next trade has
# to make. Same gap, but a percentage of a milestone is not something anyone can
# size an entry against, and this is the surface that gets read at the moment of
# a trade.
#
# Drawn as bars rather than written as a sentence on purpose: the whole point is
# that the step is small and there are a countable number of them. A staircase
# shows that in one look; a paragraph makes you do the arithmetic that the
# staircase already did.

def _pace(P: dict, C: dict) -> str:
    """Ahead or behind, said in words, plus what the band actually is.

    The cone was drawn with no key: five shaded percentiles and a line through
    them, and no statement anywhere of which side of it you're on. The band
    points were always scored (score_day awards on exactly this), the answer
    just never left track.py.
    """
    if not P or P.get("vs_p50") is None:
        return ('<p class="tk-sub tk-pace">No band today — the projection is anchored '
                'monthly, so the first days of a window have nothing to compare against.</p>')

    v, pct = P["vs_p50"], P.get("pct")
    slice_txt = {75: "P75–P90 (top quarter)", 50: "P50–P75 (upper half)",
                 25: "P25–P50 (lower half)", 10: "P10–P25 (bottom quarter)"}.get(
                     pct, "under P10 (outside the band)")
    ahead = v >= 0
    word = "AHEAD of" if ahead else "BEHIND"
    cls = "ok" if ahead else ("warn" if pct is not None else "bad")

    return f"""
    <div class="tk-pace {cls}">
      <b>{word} the median path</b> — realised P&amp;L is
      <b>{_eur(abs(v), 0)} {'above' if ahead else 'below'} P50</b>, sitting in {slice_txt}.
    </div>
    <p class="tk-sub tk-pacenote"><b>What the band is:</b> {C.get('paths', 0):,} simulated
       futures, each one resampled from your {C.get('n', 0)} real closed trades
       ({C.get('badge') or 'no sample'}) — not a forecast, a spread of what this
       ledger has actually been capable of. <b>P50</b> is the middle path: half the
       simulations land above it, half below. <b>P90/P10</b> are the outer edges —
       a good and a bad run, not a ceiling or a floor. The solid line is what
       really happened; where it sits between them is whether you're on track.</p>"""


def _steps(S: dict) -> str:
    if not S.get("ok"):
        return ""
    px, tgt = S.get("px"), S.get("target_btc") or 0
    if not tgt:
        return ""

    phase_txt = ""
    if S.get("phase"):
        rate = S.get("phase_rate")
        phase_txt = (f'<b class="tk-phase">{S["phase"]}</b> · '
                     f'{rate * 100:.0f}%/mo to {_btc(S["phase_to"])} · '
                     if rate else f'<b class="tk-phase">{S["phase"]}</b> · ')
    when = f' · {_date_label(S["date"])}' if S.get("date") else ""

    if S.get("projected"):
        # Overdue: there is no next-trade quota to hit — the RUNG missed its
        # date, not the next trade. A fictitious "+2.2% needed" invented by
        # dividing the gap into equal steps is worse than no number; show the
        # rate that's actually being kept (trades/week) and where it lands.
        per_wk = round(S["trades_per_day"] * 7, 1)
        dtxt = f"overdue · at {per_wk}/wk → {_date_label(S['eta_date'])}"
        return f"""
  <details class="tk-panel tk-det tk-stp" id="s-steps" aria-label="Next steps" open>
    <summary><span class="tk-sum-h">Next steps</span>
      <span class="tk-badge">{phase_txt}{S.get('label') or 'the rung'} missed{when} · {dtxt}</span></summary>

    <div class="tk-nums tk-stp-nums">
      <div><span class="tk-lab">now</span><b>{_eur(S['cur_eur'], 0)}</b>
           <span class="tk-eu">{_btc(S['cur_btc'])}</span></div>
      <div><span class="tk-lab">{S.get('label') or 'rung'}</span>
           <b>{_eur(S['target_eur'], 0)}</b>
           <span class="tk-eu">{_btc(S['target_btc'])}</span></div>
      <div><span class="tk-lab">gap</span><b>{S['total_pct']:.0f}%</b></div>
    </div>

    <p class="tk-sub">{S.get('label') or 'The rung'} was due{when} and wasn't
       hit — that's the plan running behind, not the next trade. No per-trade
       target: at your kept rate of <b>{per_wk}/wk</b>, closing the
       <b>{S['total_pct']:.0f}%</b> gap to this rung projects to
       <b>{_date_label(S['eta_date'])}</b>, assuming the
       {S.get('phase') or "phase"}'s {S['phase_rate']*100:.0f}%/mo holds.
       Stack euros at {_eur(px)}/₿.</p>
  </details>
"""

    floor = S.get("prev_btc")
    if floor is None or floor >= S["cur_btc"]:
        floor = S["cur_btc"] * 0.55
    floor *= 0.92
    span = max(tgt - floor, 1e-12)

    def h(btc):
        return 0.0 if not btc else max(3.0, min(100.0, (btc - floor) / span * 100.0))

    bars = []
    if S.get("prev_btc") is not None:
        bars.append(("was", S["prev_btc"], "was", ""))
    bars.append(("now", S["cur_btc"], "now", ""))

    step, cur = S["per_step_pct"] / 100.0, S["cur_btc"]
    n = S["steps"]
    for i in range(1, n + 1):
        v = cur * (1 + step) ** i
        if i == 1:
            bars.append(("next", v, "next", "1"))
        elif i == n:
            bars.append(("goal", tgt, S.get("label") or "rung", str(i)))
        else:
            bars.append(("todo", v, "", str(i)))

    cells = []
    for cls, v, lab, num in bars:
        title = f"{_btc(v)} · {_eur_of(v, px)}"
        if num:
            title = f"trade {num} — {title}"
        cells.append(
            f'<div class="tk-st {cls}" style="--h:{h(v):.1f}%" title="{title}">'
            f'<i></i>{f"<span>{lab}</span>" if lab else ""}</div>')

    left = S.get("days_left")
    dtxt = (f"{left} days left" if left is not None and left >= 0
            else "overdue" if left is not None else "no date")

    return f"""
  <details class="tk-panel tk-det tk-stp" id="s-steps" aria-label="Next steps" open>
    <summary><span class="tk-sum-h">Next steps</span>
      <span class="tk-badge">{phase_txt}{S['steps']} trades to
        {S.get('label') or 'the rung'}{when} · {dtxt}</span></summary>

    <div class="tk-stp-top">
      <div class="tk-stp-big">
        <b>+{_eur(S['gain_eur'], 0)}</b>
        <span class="tk-lab">next trade · +{S['per_step_pct']:.1f}%</span>
      </div>
      <div class="tk-nums tk-stp-nums">
        <div><span class="tk-lab">was</span><b>{_eur(S['prev_eur'], 0)}</b>
             <span class="tk-eu">{_btc(S['prev_btc'])}</span></div>
        <div><span class="tk-lab">now</span><b>{_eur(S['cur_eur'], 0)}</b>
             <span class="tk-eu">{_btc(S['cur_btc'])}</span></div>
        <div><span class="tk-lab">next</span><b class="tk-hit">{_eur(S['next_eur'], 0)}</b>
             <span class="tk-eu">{_btc(S['next_btc'])}</span></div>
        <div><span class="tk-lab">{S.get('label') or 'rung'}</span>
             <b>{_eur(S['target_eur'], 0)}</b>
             <span class="tk-eu">{_btc(S['target_btc'])}</span></div>
      </div>
    </div>

    <div class="tk-stair" role="img"
         aria-label="Stack in euros now, and the {S['steps']} trades between it
         and {S.get('label') or 'the rung'}, each compounding {S['per_step_pct']:.1f} percent.">
      <span class="tk-goalline"><i></i><em>{S.get('label') or 'rung'} {_eur(S['target_eur'], 0)}</em></span>
      {"".join(cells)}
    </div>

    <p class="tk-sub">Clearing {S.get('label') or 'the rung'} means growing the stack
       <b>{S['total_pct']:.0f}%</b>. Split across the <b>{S['steps']}</b> trades your
       measured rate ({S['trades_per_day']}/day) expects in {dtxt}, each one needs
       <b>+{S['per_step_pct']:.1f}%</b> — <b>{_eur(S['gain_eur'], 2)}</b> on the next one.
       Stack euros at {_eur(px)}/₿, which is what the rung is measured in — not
       account equity.</p>
  </details>
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
  var el=document.getElementById("fan");
  if(!el) return;
  if(!window.LightweightCharts){
    el.innerHTML='<p class="tk-sub">Chart library failed to load. '+
      'The numbers above and below are unaffected.</p>';
    return;
  }
  var LC=window.LightweightCharts, cs=getComputedStyle(document.documentElement);
  function V(n){ return cs.getPropertyValue(n).trim(); }

  // Opaque band fills, blended against the panel colour rather than layered as
  // translucent areas. An area series fills from its line to the bottom of the
  // pane, so translucent bands stack where they overlap and the P25-P75 core
  // comes out darker than either edge. Painting p90/p75/p25/p10 in that order
  // with solid colours lets each one repaint the region below it, which leaves
  // exactly the two nested bands the eye expects.
  function hex(v){ if(v[0]!=="#") return v;
    return v.length===4 ? "#"+v[1]+v[1]+v[2]+v[2]+v[3]+v[3] : v; }
  function rgb(h){ h=hex(h);
    return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]; }
  function mix(a,b,t){ var A=rgb(a),B=rgb(b),o="#",i,c;
    for(i=0;i<3;i++){ c=Math.round(A[i]+(B[i]-A[i])*t).toString(16);
      o+=c.length<2?"0"+c:c; } return o; }

  var PANEL=V("--panel"), ACCENT=V("--accent"), INK=V("--ink"), DIM=V("--dim");
  var LINE=V("--line"), LONG=V("--long"), SHORT=V("--short"), AMBER=V("--amber");
  var OUTER=mix(PANEL,ACCENT,.13), INNER=mix(PANEL,ACCENT,.26);

  var range="next", mode="bal";
  var readEl=document.getElementById("fan-read");

  function eur(v,dp){ dp=dp==null?0:dp;
    return (v<0?"−":"")+"€"+Math.abs(v).toLocaleString("en-GB",
      {minimumFractionDigits:dp,maximumFractionDigits:dp}); }
  function fmt(v){ return v==null?"—":(mode==="pct"
    ? (v>=0?"+":"−")+Math.abs(v).toFixed(1)+"%" : eur(v)); }

  // Which projection this range is reading. They are NOT interchangeable: NEAR
  // is anchored on today and stepped per day, FAN on the month start and
  // stepped per trade, so each carries its own base for the balance transform.
  function src(){ return range==="next" && NEAR && NEAR.points && NEAR.points.length
    ? NEAR : FAN; }
  function base(){ var s=src();
    return s===NEAR ? (NEAR.base_balance||0) : (FAN.base||0); }
  function anchorCum(){ var s=src();
    return s===NEAR ? (NEAR.anchor_cum||0) : (FAN.anchorCum||0); }

  function conv(v){
    if(v==null) return null;
    if(mode==="bal") return base()+(v-anchorCum());
    if(mode==="pct") return base() ? (v-anchorCum())/base()*100 : 0;
    return v; }
  function floorVal(){
    var f = src()===NEAR ? NEAR.floor : FAN.floor;
    if(f==null) return null;
    return mode==="bal" ? 0 : (mode==="pct" ? -100 : f); }

  var chart=LC.createChart(el,{
    layout:{ background:{color:"transparent"}, textColor:DIM, attributionLogo:false,
             fontFamily:"'JetBrains Mono','SF Mono',ui-monospace,monospace", fontSize:10 },
    grid:{ vertLines:{color:LINE}, horzLines:{color:LINE} },
    rightPriceScale:{ borderColor:LINE, scaleMargins:{top:.12,bottom:.08} },
    timeScale:{ borderColor:LINE, timeVisible:false, secondsVisible:false,
                rightOffset:4, fixLeftEdge:false, lockVisibleTimeRangeOnResize:true },
    crosshair:{ mode:LC.CrosshairMode.Normal,
      vertLine:{color:ACCENT,width:1,style:LC.LineStyle.Dotted,labelBackgroundColor:ACCENT},
      horzLine:{color:ACCENT,width:1,style:LC.LineStyle.Dotted,labelBackgroundColor:ACCENT} },
    handleScroll:true, handleScale:true,
    localization:{ priceFormatter:function(v){ return fmt(v); } }
  });

  function area(color){ return chart.addAreaSeries({
    topColor:color, bottomColor:color, lineColor:color, lineWidth:1,
    priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false }); }
  function line(color,w,style){ return chart.addLineSeries({
    color:color, lineWidth:w, lineStyle:style==null?LC.LineStyle.Solid:style,
    priceLineVisible:false, lastValueVisible:false,
    crosshairMarkerVisible:false, lineJoin:"round" }); }

  // paint order matters — see the note on mix() above
  var s90=area(OUTER), s75=area(INNER), s25=area(OUTER), s10=area(PANEL);
  var s50=line(DIM,1,LC.LineStyle.Dashed);
  var sFloor=line(SHORT,1,LC.LineStyle.Dashed);
  var sReal=line(LONG,2);

  function dedupe(rows){
    var out=[],seen={},i;
    rows.sort(function(a,b){ return a.time-b.time; });
    for(i=0;i<rows.length;i++){ if(rows[i].value==null||isNaN(rows[i].value)) continue;
      if(seen[rows[i].time]) continue; seen[rows[i].time]=1; out.push(rows[i]); }
    return out; }

  function bandRows(key){
    return dedupe((src().points||[]).map(function(p){
      return {time:p.t, value:conv(p[key])}; })); }

  // The realised line. In balance mode these are the actual daily equity
  // snapshots rather than the band's own transform: real money beats a
  // derivation, and the two meet at the anchor by construction anyway.
  function realRows(){
    var rows = mode==="bal"
      ? (FAN.balances||[]).map(function(b){ return {time:b.t, value:b.v}; })
      : (FAN.actual||[]).map(function(a){ return {time:a.t, value:conv(a.cum)}; });
    if(range==="next"){
      var cut=(Date.now()/1000|0)-NEAR_DAYS*86400*1.2;
      rows=rows.filter(function(r){ return r.time>=cut; });
    }
    return dedupe(rows); }

  function floorRows(){
    var fv=floorVal(), pts=src().points||[];
    if(fv==null||!pts.length) return [];
    return dedupe(pts.map(function(p){ return {time:p.t, value:fv}; })); }

  function paint(){
    s90.setData(bandRows("p90")); s75.setData(bandRows("p75"));
    s25.setData(bandRows("p25")); s10.setData(bandRows("p10"));
    s50.setData(bandRows("p50"));
    sFloor.setData(floorRows());
    sReal.setData(realRows());
    applyRange();
    readout(null);
  }

  function applyRange(){
    var ts=chart.timeScale(), pts=src().points||[], now=Date.now()/1000|0;
    if(!pts.length){ ts.fitContent(); return; }
    // NEVER fitContent on the rung range. The realised series carries the whole
    // balance history — a year of it — so fitting every series squashes the
    // cone into the right-hand edge behind whatever the account's largest past
    // swing was. Fit the PROJECTION's own span instead and let panning reach
    // the history, which is what panning is for.
    try{
      if(range==="rung"){
        ts.setVisibleRange({from:pts[0].t-30*86400, to:pts[pts.length-1].t});
      } else if(range==="next"){
        ts.setVisibleRange({from:pts[0].t-NEAR_DAYS*86400, to:pts[pts.length-1].t});
      } else {
        var d=(parseInt(range,10)||30)*86400;
        ts.setVisibleRange({from:now-d, to:Math.min(pts[pts.length-1].t, now+d/3)});
      }
    }catch(e){ ts.fitContent(); }
  }

  // The readout is the whole reason the crosshair exists here: hovering a day
  // should say what that day means, not just show a price label.
  function readout(param){
    if(!readEl) return;
    var pts=src().points||[], p=null, i, best=Infinity, d;
    if(param&&param.time){
      for(i=0;i<pts.length;i++){ d=Math.abs(pts[i].t-param.time);
        if(d<best){ best=d; p=pts[i]; } }
      // past the last sample the band has nothing to say — don't quote the
      // final point as though it applied to a date it never covered
      if(best>86400*10) p=null;
    }
    if(!p){
      var tm = src()===NEAR ? (NEAR.tomorrow||null) : null;
      readEl.textContent = tm
        ? "tomorrow "+fmt(conv(tm.p25))+" … "+fmt(conv(tm.p75))+"  (P25–P75)"
        : "drag to pan · scroll to zoom";
      return;
    }
    var d=new Date(p.t*1000);
    readEl.textContent = d.toLocaleDateString("en-GB",{day:"numeric",month:"short"})+
      "  "+fmt(conv(p.p25))+" … "+fmt(conv(p.p75))+
      "   P50 "+fmt(conv(p.p50));
  }
  chart.subscribeCrosshairMove(readout);

  var wrap=el.parentElement;
  function size(){
    var w=wrap.clientWidth, h=window.innerWidth<620?240:300;
    if(w>0){ el.style.width=w+"px"; chart.applyOptions({width:w, height:h}); }
  }
  if(window.ResizeObserver) new ResizeObserver(size).observe(wrap);
  else window.addEventListener("resize",size);
  size();


  document.querySelectorAll("[data-range]").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll("[data-range]").forEach(function(o){ o.classList.remove("on"); });
      b.classList.add("on"); range=b.getAttribute("data-range"); paint(); }); });
  document.querySelectorAll("[data-mode]").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll("[data-mode]").forEach(function(o){ o.classList.remove("on"); });
      b.classList.add("on"); mode=b.getAttribute("data-mode"); paint(); }); });

  var fit=document.getElementById("fan-fit");
  if(fit) fit.addEventListener("click",function(){ applyRange(); });

  paint();
  size();
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
.tk-pace{margin:11px 0 0;padding:10px 13px;border-radius:9px;font-size:12.5px;
  color:var(--ink);background:var(--panel);border:1px solid var(--line);border-left-width:3px}
.tk-pace.ok{border-left-color:var(--long)}
.tk-pace.warn{border-left-color:var(--amber)}
.tk-pace.bad{border-left-color:var(--short)}
.tk-pacenote{margin-top:7px}
.tk-sub b{color:var(--ink);font-family:var(--mono)}
.tk-stale{color:var(--amber);margin-left:6px}
.tk-warn{font-size:12px;line-height:1.55;color:var(--amber);margin:12px 0 0;max-width:74ch}
.tk-badge{font-family:var(--mono);font-size:10px;color:var(--dim)}

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

/* the step ladder */
.tk-stp-top{display:flex;align-items:stretch;gap:var(--s5);flex-wrap:wrap;
  margin-bottom:var(--s5)}
.tk-stp-big{display:flex;flex-direction:column;flex:0 0 auto;min-width:150px}
.tk-stp-big b{font-family:var(--mono);font-size:46px;font-weight:800;line-height:.92;
  color:var(--long);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.tk-stp-big .tk-lab{margin-top:var(--s2)}
.tk-stp-nums{margin:0;flex:1 1 320px;align-items:center;gap:var(--s3) var(--s5);
  padding-left:var(--s5);border-left:1px solid var(--line)}
.tk-nums b.tk-hit{color:var(--long)}

/* the staircase: one bar per expected trade between here and the rung */
.tk-stair{position:relative;display:flex;align-items:flex-end;gap:4px;
  height:190px;padding-top:18px;margin-bottom:var(--s4)}
.tk-st{flex:1 1 0;min-width:0;display:flex;flex-direction:column;
  justify-content:flex-end;align-items:center;height:100%;position:relative}
.tk-st>i{display:block;width:100%;height:var(--h);border-radius:3px 3px 0 0;
  background:var(--panel3);border:1px solid var(--line2);border-bottom:0}
.tk-st>span{position:absolute;bottom:-15px;font-family:var(--mono);font-size:9px;
  letter-spacing:.06em;color:var(--dim);white-space:nowrap}
.tk-st.was>i{background:var(--panel2);border-color:var(--line)}
.tk-st.now>i{background:var(--accent-d);border-color:var(--accent)}
.tk-st.next>i{background:var(--long);border-color:var(--long);box-shadow:var(--glow-g)}
.tk-st.next>span{color:var(--long);font-weight:700}
.tk-st.goal>i{background:var(--panel3);border-color:var(--accent)}
.tk-st.goal>span{color:var(--accent)}
.tk-stair{padding-bottom:16px}
.tk-goalline{position:absolute;left:0;right:0;top:16px;pointer-events:none}
.tk-goalline>i{display:block;border-top:1px dashed var(--accent);opacity:.55}
.tk-goalline>em{position:absolute;right:0;top:-14px;font-style:normal;background:var(--panel);padding-left:6px;
  font-family:var(--mono);font-size:9.5px;color:var(--accent)}
@media (max-width:620px){
  .tk-stp-big{flex:1 1 100%;min-width:0}
  .tk-stp-big b{font-size:38px}
  .tk-stp-nums{flex-basis:100%;padding-left:0;padding-top:var(--s4);
    border-left:0;border-top:1px solid var(--line)}
  .tk-stair{height:150px;gap:2px}
  .tk-st>span{font-size:8px}
}

/* fan — the library paints into a canvas, so the container carries the size
   and nothing here can reach the series. Series colours are read from the
   design tokens in JS instead, which keeps theme.py the single source. */
.tk-fanwrap{position:relative}
.tk-fanwrap{overflow:hidden}
.tk-fan{max-width:100%;min-width:0;height:300px}
.tk-hint{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap;
  font-family:var(--mono);font-size:10px;color:var(--dim);margin:var(--s2) 0 0}
.tk-fitbtn{padding:3px 9px;font-size:10px}
.tk-amber{color:var(--amber)}
.tk-phase{color:var(--accent);font-weight:700}
.tk-credit{margin-left:auto;color:var(--dim);font-size:9.5px}
@media (max-width:620px){ .tk-fan{height:240px} }

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
.tk-det>summary .tk-badge{margin-left:0}
.tk-sum-h{font-family:var(--hud);font-size:14px;font-weight:600;color:var(--ink);
  transition:color .15s ease-out}
.tk-det>*:not(summary){margin-left:16px;margin-right:16px}
.tk-det>*:last-child{margin-bottom:16px}

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
  .tk-read{margin-left:0;text-align:left;flex-basis:100%}
  .tk-le{display:none}
}
@media(prefers-reduced-motion:reduce){
  .tk-bar>span,.tk-seg button,.tk-btn,.tk-x,.tk-sum-h{transition:none}
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

    # the near band still feeds the chart's Next range, even though its
    # prose summary is gone
    N = T.get("near") or {}

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
    near_data = json.dumps(N)

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
        <a class="tk-edit-link" href="#edit">Edit milestones</a>
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

  <details class="tk-panel tk-det" id="s-tracker" aria-label="Tracker" open>
    <summary><span class="tk-sum-h">Tracker</span>
      <span class="tk-badge">{C.get('badge') or 'no sample'}</span></summary>
    <div class="tk-ctl" role="group" aria-label="Chart controls">
      <span class="tk-seg" role="group" aria-label="Time range">
        <button type="button" data-range="next" class="on">Next {NEAR_DAYS}d</button>
        <button type="button" data-range="rung">To the rung</button>
        <button type="button" data-range="7">1W</button>
        <button type="button" data-range="30">1M</button>
        <button type="button" data-range="90">3M</button>
        <button type="button" data-range="365">1Y</button>
      </span>
      <span class="tk-seg" role="group" aria-label="What to plot">
        <button type="button" data-mode="bal" class="on">Balance €</button>
        <button type="button" data-mode="eur">Realised P&amp;L</button>
        <button type="button" data-mode="pct">% of account</button>
      </span>
      <span class="tk-read" id="fan-read" aria-live="polite"></span>
    </div>
    <div class="tk-fanwrap"><div id="fan" class="tk-fan" role="img"
      aria-label="Projection band with the realised line drawn through it.
      Drag to pan, scroll to zoom."></div></div>
    {_pace(T.get('pace') or {}, C)}
    <p class="tk-hint">Drag to pan · scroll to zoom · hover a day for its band
       <button type="button" class="tk-btn tk-fitbtn" id="fan-fit">Reset view</button>
       <span class="tk-credit">chart: TradingView Lightweight Charts (Apache-2.0), served locally</span></p>
  </details>
{_steps(T['step'])}


  <details class="tk-panel tk-det" id="s-milestones" aria-label="Milestones">
    <summary><span class="tk-sum-h">Milestones</span>
      <span class="tk-of">the rest of the ladder</span></summary>
    {_ladder_rows(ms, R, px)}
  </details>

  <details class="tk-panel tk-det" id="edit" aria-label="Edit milestones">
    <summary><span class="tk-sum-h">Edit milestones</span>
      <span class="tk-of">rungs, targets and the dates you pin</span></summary>
    {_editor(ms, px)}
  </details>

</main>"""

    collapse_js = '\n// Collapse state, per section, remembered. A section you have to re-minimise on\n// every load is not really minimisable. Wrapped because storage throws outright\n// in some privacy modes rather than merely returning null.\n(function(){\n  var KEY="lens.track.open";\n  var state={};\n  try{ state=JSON.parse(localStorage.getItem(KEY)||"{}")||{}; }catch(e){ state={}; }\n  document.querySelectorAll("details[id^=\'s-\']").forEach(function(d){\n    if(Object.prototype.hasOwnProperty.call(state,d.id)) d.open=!!state[d.id];\n    d.addEventListener("toggle",function(){\n      state[d.id]=d.open;\n      try{ localStorage.setItem(KEY,JSON.stringify(state)); }catch(e){}\n    });\n  });\n})();\n'
    script = ("const FAN=" + fan_data + ";const NEAR=" + near_data +
              ";const NEAR_DAYS=" + str(NEAR_DAYS) +
              ";const PX=" + json.dumps(px) + ";" + _JS + collapse_js)
    return {"body": body, "css": _CSS, "script": script}


def render() -> str:
    p = parts()
    # The library is a blocking <script> in <head> so it is defined by the time
    # the page script runs. Vendored locally — see main.charts_js.
    head = '<script src="/assets/lightweight-charts.js"></script>' + p["css"]
    return shell("/track", "Track", p["body"], head_extra=head,
                 script=p["script"], meta="am I on pace?")
