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
from .track import MAX_POINTS, NEAR_DAYS, WEIGHTS, track

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

def _steps(S: dict) -> str:
    if not S.get("ok"):
        return ""
    px, tgt = S.get("px"), S.get("target_btc") or 0
    if not tgt:
        return ""

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

    when = f' · {_date_label(S["date"])}' if S.get("date") else ""
    left = S.get("days_left")
    dtxt = (f"{left} days left" if left is not None and left >= 0
            else "overdue" if left is not None else "no date")

    return f"""
  <section class="tk-panel tk-stp" aria-label="The next trade">
    <header class="tk-h">
      <h2>The next trade</h2>
      <span class="tk-badge">{S['steps']} trades to {S.get('label') or 'the rung'}{when}
        · {dtxt}</span>
    </header>

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
        var d=(range==="90"?90:30)*86400;
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

    # The near band, said in words. The chart shows the shape; this says what
    # tomorrow actually means in euros, because a band you have to read off an
    # axis is a band nobody reads.
    N = T.get("near") or {}
    near_line = ""
    if N.get("points"):
        tm = N.get("tomorrow") or {}
        nb = lambda v: (N.get("base_balance") or 0) + (v - (N.get("anchor_cum") or 0))
        lo, mid, hi = nb(tm.get("p25", 0)), nb(tm.get("p50", 0)), nb(tm.get("p75", 0))
        near_ruin = ""
        nf = N.get("floor")
        if nf is not None:
            hit = next((q for q in N["points"]
                        if q.get("p10") is not None and q["p10"] <= nf + 1e-6), None)
            if hit:
                when = _date_label(datetime.utcfromtimestamp(hit["t"]).date().isoformat())
                near_ruin = (f' <span class="tk-amber">One path in ten is already at the '
                             f'ruin floor by {when}.</span>')
        near_line = (
            f'<p class="tk-sub">At <b>{N.get("trades_per_day", 0):.2f}</b> trades a day '
            f'measured off your own ledger, <b>tomorrow</b> lands between '
            f'<b>{_eur(lo, 2)}</b> and <b>{_eur(hi, 2)}</b> with a midpoint of '
            f'<b>{_eur(mid, 2)}</b>. A flat stretch is a day the rate says you would '
            f'not normally trade — no expected trades, no expected spread.{near_ruin}</p>')

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

  <section class="tk-panel" aria-label="Projection band">
    <header class="tk-h">
      <h2>Where you should be</h2>
      <span class="tk-badge">{C.get('badge') or 'no sample'}</span>
    </header>
    <div class="tk-ctl" role="group" aria-label="Chart controls">
      <span class="tk-seg" role="group" aria-label="Time range">
        <button type="button" data-range="next" class="on">Next {NEAR_DAYS} days</button>
        <button type="button" data-range="rung">To the rung</button>
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
    <div class="tk-fanwrap"><div id="fan" class="tk-fan" role="img"
      aria-label="Projection band with the realised line drawn through it.
      Drag to pan, scroll to zoom."></div></div>
    <p class="tk-hint">Drag to pan · scroll to zoom · hover a day for its band
       <button type="button" class="tk-btn tk-fitbtn" id="fan-fit">Reset view</button>
       <span class="tk-credit">chart: TradingView Lightweight Charts (Apache-2.0), served locally</span></p>
    {near_line}
    <p class="tk-sub">Balance <b>{_eur(bal_now, 2)}</b> today, against a P25–P75 band of
       {_eur(_to_bal(now.get('p25'), C), 2)} – {_eur(_to_bal(now.get('p75'), C), 2)}.
       The shaded fan is {C.get('paths') or 0} simulated paths drawn from your own closed
       trades — not a straight line, because your equity curve isn't one. Switch to
       <b>Realised P&amp;L</b> for the cone's native axis, where deposits and withdrawals
       can't move the line.</p>
    {ruin}
  </section>
{_steps(T['step'])}


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

{_adherence(T['adherence'])}
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
</main>"""

    script = ("const FAN=" + fan_data + ";const NEAR=" + near_data +
              ";const NEAR_DAYS=" + str(NEAR_DAYS) +
              ";const PX=" + json.dumps(px) + ";" + _JS)
    return {"body": body, "css": _CSS, "script": script}


def render() -> str:
    p = parts()
    # The library is a blocking <script> in <head> so it is defined by the time
    # the page script runs. Vendored locally — see main.charts_js.
    head = '<script src="/assets/lightweight-charts.js"></script>' + p["css"]
    return shell("/hedge-track", "Track", p["body"], head_extra=head,
                 script=p["script"], meta="am I on pace?")
