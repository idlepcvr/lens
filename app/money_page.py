"""LENS /money — how much real cash went into trading, and when it's back to net.

PERSONAL = EUR transfers already synced into the transfers table (kraken_spot).
BUSINESS = the separate Kraken Futures biz account; its account log is pulled on
"↻ refresh biz" and stored with venue='kraken_futures_biz' (review.py's personal
cash-flow query excludes that venue).
TOTAL    = both, plus the gap to breakeven and a straight-line "when am I back
to net" projection from the last 30 days of the combined curve.

ponytail: biz equity history ≈ cumulative net transfers (no biz trade sync);
good enough while the biz account isn't actively traded. Add a real biz curve
if that changes.
"""

import datetime as _dt
import sqlite3

from .database import DB_PATH, upsert_transfer
from .theme import shell

BIZ_VENUE = "kraken_futures_biz"
_EUR = "('eur','ZEUR','EUR')"


def refresh_biz() -> dict:
    """Pull the biz futures account log and persist its transfers (deduped)."""
    from . import kraken_sync
    key, secret = kraken_sync.get_api_keys("biz")
    user = kraken_sync.User(key=key, secret=secret)
    eur_usd = kraken_sync._get_eur_usd(kraken_sync.Market(key=key, secret=secret))
    _timeline, raw_logs = kraken_sync._build_eur_timeline(user, eur_usd)
    imported = 0
    for tf in kraken_sync._build_transfers(raw_logs):
        tf["venue"] = BIZ_VENUE
        if upsert_transfer(tf):
            imported += 1
    return {"imported": imported}


def money_data(refresh: bool = False) -> dict:
    out: dict = {}
    if refresh:
        try:
            out["biz_sync"] = refresh_biz()
        except Exception as e:
            out["biz_sync_error"] = str(e)

    conn = sqlite3.connect(DB_PATH)

    def flows(where, params):
        dep, wd = conn.execute(
            f"SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0),"
            f"       COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0)"
            f" FROM transfers WHERE asset IN {_EUR} AND {where}", params).fetchone()
        rows = conn.execute(
            f"SELECT ts, transfer_type, amount FROM transfers "
            f"WHERE asset IN {_EUR} AND {where} ORDER BY ts", params).fetchall()
        return round(dep, 2), round(wd, 2), rows

    p_dep, p_wd, p_rows = flows("COALESCE(venue,'') <> ?", (BIZ_VENUE,))
    b_dep, b_wd, b_rows = flows("venue = ?", (BIZ_VENUE,))
    snaps = conn.execute(
        "SELECT snapshot_date, eur_balance FROM daily_snapshots "
        "WHERE eur_balance IS NOT NULL ORDER BY snapshot_date").fetchall()
    conn.close()

    # live balances; fall back to last snapshot (personal) / net transfers (biz)
    per_bal = snaps[-1][1] if snaps else 0.0
    biz_bal = b_dep - b_wd
    try:
        from . import kraken_sync
        for acct in ("personal", "biz"):
            k, s = kraken_sync.get_api_keys(acct)
            b = kraken_sync.fetch_live_balance(k, s)
            if "error" not in b and b.get("eur_balance"):
                if acct == "personal":
                    per_bal = b["eur_balance"]
                else:
                    biz_bal = b["eur_balance"]
    except Exception:
        pass

    # combined daily curve: personal snapshots + biz cumulative net transfers,
    # step-forward-filled per day
    biz_steps = []          # (date, cum_net)
    cum = 0.0
    for ts, _ty, amt in b_rows:
        cum += amt
        biz_steps.append((str(ts)[:10], round(cum, 2)))
    curve = []
    bi = 0
    b_cum = 0.0
    for d, bal in snaps:
        while bi < len(biz_steps) and biz_steps[bi][0] <= d:
            b_cum = biz_steps[bi][1]
            bi += 1
        curve.append({"date": d, "total": round(bal + b_cum, 2)})

    net_p = round(p_dep - p_wd, 2)
    net_b = round(b_dep - b_wd, 2)
    net_t = round(net_p + net_b, 2)
    total_bal = round(per_bal + biz_bal, 2)
    gap = round(net_t - total_bal, 2)   # >0 = still underwater by this much

    # projection: last-30d slope of the combined curve → breakeven date
    proj = None
    if len(curve) >= 8 and gap > 0:
        cutoff = (_dt.date.fromisoformat(curve[-1]["date"]) - _dt.timedelta(days=30)).isoformat()
        win = [c for c in curve if c["date"] >= cutoff]
        if len(win) >= 2:
            d0 = _dt.date.fromisoformat(win[0]["date"])
            d1 = _dt.date.fromisoformat(win[-1]["date"])
            days = (d1 - d0).days or 1
            slope = (win[-1]["total"] - win[0]["total"]) / days   # €/day
            if slope > 0.01:
                eta = round(gap / slope)
                proj = {"slope_day": round(slope, 2), "days": eta,
                        "date": (_dt.date.today() + _dt.timedelta(days=eta)).isoformat()}
            else:
                proj = {"slope_day": round(slope, 2), "days": None, "date": None}

    def _xf(rows, book):
        return [{"ts": str(t)[:10], "type": ty, "amount": round(a, 2), "book": book}
                for t, ty, a in rows]
    xfers = sorted(_xf(p_rows, "personal") + _xf(b_rows, "business"),
                   key=lambda x: x["ts"], reverse=True)[:60]

    out.update({
        "personal": {"deposits": p_dep, "withdrawals": p_wd, "net": net_p,
                     "balance": round(per_bal, 2), "pnl": round(per_bal - net_p, 2)},
        "business": {"deposits": b_dep, "withdrawals": b_wd, "net": net_b,
                     "balance": round(biz_bal, 2), "pnl": round(biz_bal - net_b, 2)},
        "total":    {"deposits": round(p_dep + b_dep, 2),
                     "withdrawals": round(p_wd + b_wd, 2), "net": net_t,
                     "balance": total_bal, "pnl": round(total_bal - net_t, 2),
                     "gap": gap},
        "curve": curve, "projection": proj, "transfers": xfers,
        "biz_synced": bool(b_rows),
    })
    return out


_CSS = """<style>
.mo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:16px}
.mo-book{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 18px}
.mo-book.total{border-color:var(--accent)}
.mo-book h3{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}
.mo-kv{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;color:var(--dim)}
.mo-kv b{font-family:var(--mono);color:var(--ink)}
.mo-kv b.pos{color:var(--long)}.mo-kv b.neg{color:var(--short)}
.mo-verdict{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 18px;margin-bottom:16px;font-size:13px;line-height:1.6;color:var(--dim)}
.mo-verdict b{color:var(--ink)}
.mo-tbl{width:100%;border-collapse:collapse;font-size:12px}
.mo-tbl th{text-align:left;color:var(--faint);font-size:9px;text-transform:uppercase;letter-spacing:.08em;padding:6px 10px;border-bottom:1px solid var(--line)}
.mo-tbl td{padding:5px 10px;border-bottom:1px solid var(--line);font-family:var(--mono)}
canvas#mo-chart{width:100%;height:220px;display:block}
button.mo-btn{background:var(--panel);border:1px solid var(--line2);color:var(--dim);border-radius:6px;padding:6px 14px;font-size:11px;cursor:pointer;font-family:var(--mono)}
button.mo-btn:hover{color:var(--ink)}
</style>"""

_SCRIPT = r"""
function eur(v){return '€'+Math.round(v).toLocaleString('en');}
function cls(v){return v>=0?'pos':'neg';}
function book(id,d){
  document.getElementById(id).innerHTML =
    '<div class="mo-kv"><span>deposited</span><b>'+eur(d.deposits)+'</b></div>'+
    '<div class="mo-kv"><span>withdrawn</span><b>'+eur(d.withdrawals)+'</b></div>'+
    '<div class="mo-kv"><span>net funded</span><b>'+eur(d.net)+'</b></div>'+
    '<div class="mo-kv"><span>balance now</span><b>'+eur(d.balance)+'</b></div>'+
    '<div class="mo-kv"><span>P&L vs funded</span><b class="'+cls(d.pnl)+'">'+eur(d.pnl)+'</b></div>';
}
function draw(curve, netLine, proj){
  var c=document.getElementById('mo-chart'), ctx=c.getContext('2d');
  var dpr=window.devicePixelRatio||1;
  c.width=c.offsetWidth*dpr; c.height=220*dpr; ctx.scale(dpr,dpr);
  var W=c.offsetWidth, H=220;
  if(curve.length<2) return;
  var vals=curve.map(function(p){return p.total;});
  var extra = (proj&&proj.days&&proj.days<730)?proj.days:0;
  var N=curve.length-1+extra;
  var mn=Math.min.apply(null,vals.concat([netLine])), mx=Math.max.apply(null,vals.concat([netLine]));
  var pad=(mx-mn)*0.08||1; mn-=pad; mx+=pad;
  function px(i){return i/N*(W-20)+10;}
  function py(v){return H-20-((v-mn)/(mx-mn))*(H-40);}
  // net-funded line
  ctx.strokeStyle='rgba(255,180,80,.7)'; ctx.setLineDash([5,4]); ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(10,py(netLine)); ctx.lineTo(W-10,py(netLine)); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle='rgba(255,180,80,.9)'; ctx.font='10px monospace';
  ctx.fillText('net funded '+eur(netLine), 14, py(netLine)-5);
  // equity
  ctx.beginPath(); ctx.strokeStyle='#5b9dff'; ctx.lineWidth=1.5;
  ctx.moveTo(px(0),py(vals[0]));
  for(var i=1;i<vals.length;i++) ctx.lineTo(px(i),py(vals[i]));
  ctx.stroke();
  // projection extension
  if(extra){
    ctx.beginPath(); ctx.strokeStyle='rgba(91,157,255,.45)'; ctx.setLineDash([4,4]);
    ctx.moveTo(px(vals.length-1),py(vals[vals.length-1]));
    ctx.lineTo(px(N),py(netLine)); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle='rgba(91,157,255,.8)';
    ctx.fillText('→ '+proj.date, Math.min(px(N)-70,W-80), py(netLine)+14);
  }
  ctx.fillStyle='#828ea6';
  ctx.fillText(curve[0].date, 10, H-6);
  ctx.fillText(curve[curve.length-1].date, px(curve.length-1)-60, H-6);
}
function load(refresh){
  var stat=document.getElementById('mo-status');
  stat.textContent = refresh?'pulling biz account log…':'loading…';
  fetch('/api/money'+(refresh?'?refresh=1':'')).then(function(r){return r.json();}).then(function(d){
    stat.textContent = d.biz_sync_error ? ('biz sync failed: '+d.biz_sync_error)
      : (d.biz_sync ? ('biz: '+d.biz_sync.imported+' new transfers') : '');
    book('mo-p', d.personal); book('mo-b', d.business); book('mo-t', d.total);
    var t=d.total, v;
    if(t.gap>0){
      v='You\'ve put <b>'+eur(t.net)+'</b> of real cash into trading and hold <b>'+eur(t.balance)+
        '</b> — still <b class="neg" style="color:var(--short)">'+eur(t.gap)+' below breakeven</b>. ';
      if(d.projection&&d.projection.days) v+='At your last-30-day pace ('+eur(d.projection.slope_day)+
        '/day) you\'re back to net in <b>~'+d.projection.days+' days</b> ('+d.projection.date+').';
      else if(d.projection) v+='Your last-30-day pace is flat/negative — at this pace there is no breakeven date; the plan has to change, not the projection.';
      else v+='Not enough curve history yet for a pace estimate.';
    } else {
      v='You\'ve put <b>'+eur(t.net)+'</b> in and hold <b>'+eur(t.balance)+'</b> — '+
        '<b style="color:var(--long)">'+eur(-t.gap)+' above breakeven</b>. Everything from here is profit.';
    }
    if(!d.biz_synced) v+=' <span style="color:var(--faint)">(business transfers not pulled yet — hit ↻ refresh biz once)</span>';
    document.getElementById('mo-verdict').innerHTML=v;
    draw(d.curve, t.net, d.projection);
    document.getElementById('mo-xfers').innerHTML = d.transfers.map(function(x){
      return '<tr><td>'+x.ts+'</td><td>'+x.book+'</td><td>'+x.type+'</td>'+
             '<td style="color:var(--'+(x.amount>=0?'long':'short')+')">'+eur(x.amount)+'</td></tr>';
    }).join('');
  }).catch(function(e){stat.textContent='failed: '+e;});
}
load(false);
"""

_BODY = """
<div class="ed-sub" style="color:var(--dim);font-size:12px;margin:2px 0 14px">
  Real cash in, real cash out — personal, business, and the one number that matters:
  how far from breakeven, and when the current pace gets there.
  <button class="mo-btn" onclick="load(true)" style="margin-left:10px">↻ refresh biz</button>
  <span id="mo-status" style="color:var(--accent);font-size:11px;margin-left:8px"></span>
</div>
<div class="mo-verdict" id="mo-verdict">…</div>
<div class="mo-grid">
  <div class="mo-book"><h3>Personal — hedge</h3><div id="mo-p"></div></div>
  <div class="mo-book"><h3>Business</h3><div id="mo-b"></div></div>
  <div class="mo-book total"><h3>Total</h3><div id="mo-t"></div></div>
</div>
<div class="mo-book" style="margin-bottom:16px">
  <h3>Combined equity vs net funded</h3>
  <canvas id="mo-chart"></canvas>
  <div style="font-size:10px;color:var(--faint);margin-top:8px">
    Blue = personal balance + business cumulative net transfers · amber dash = total net funded
    (the breakeven line) · blue dash = straight-line projection at your last-30-day pace.</div>
</div>
<div class="mo-book">
  <h3>Cash movements — last 60</h3>
  <div style="overflow-x:auto;max-height:360px;overflow-y:auto">
  <table class="mo-tbl">
    <thead><tr><th>Date</th><th>Book</th><th>Type</th><th>Amount</th></tr></thead>
    <tbody id="mo-xfers"></tbody>
  </table></div>
</div>
"""


def render_page() -> str:
    return shell("/money", "Money", _BODY, script=_SCRIPT, head_extra=_CSS,
                 meta="am I back to net?")
