"""LENS /prop-ledger — the prop eval trade book.

Shows only `book='prop'` trades as a running equity ledger against the Breakout
eval walls: distance to the static floor, daily-loss used, progress to target,
plus real-trade analytics (peak/trough equity, max drawdown, time under water,
observed loss streak). Log prop trades by hand here (book='prop'); an API sync
can drop in later if Breakout exposes Kraken keys. Simulated loss-streak risk
lives on /survival — this page is the REALISED side.
"""

import datetime

from .database import get_trades
from .prop_eval import EVALS
from .prop_views import ACCOUNT, RISK, EVAL, HERO
from .theme import shell


def prop_ledger_data() -> dict:
    rule = EVALS[EVAL]
    rows = get_trades(limit=5000, book="prop")
    closed = [t for t in rows if t.pnl is not None]
    # chronological (oldest → newest) by close, fall back to open
    closed.sort(key=lambda t: (t.closed_at or t.opened_at or datetime.datetime.min))

    start = ACCOUNT
    risk_usd = ACCOUNT * RISK / 100.0
    eq = peak = trough = start
    maxdd = 0.0
    tuw = 0                    # trades spent below the prior peak
    cur_streak = max_loss_streak = 0
    wins = losses = 0
    gross_win = gross_loss = 0.0
    ledger = []

    for t in closed:
        eq += t.pnl
        peak = max(peak, eq)
        trough = min(trough, eq)
        dd = (peak - eq) / peak if peak else 0.0
        maxdd = max(maxdd, dd)
        if eq < peak - 1e-9:
            tuw += 1
        if t.pnl < 0:
            cur_streak += 1
            max_loss_streak = max(max_loss_streak, cur_streak)
            losses += 1
            gross_loss += -t.pnl
        else:
            cur_streak = 0
            wins += 1
            gross_win += t.pnl
        cdate = (t.closed_at or t.opened_at)
        ledger.append({
            "id": t.id,
            "date": cdate.strftime("%Y-%m-%d %H:%M") if hasattr(cdate, "strftime") else str(cdate),
            "direction": t.direction,
            "entry": t.entry, "exit": t.exit,
            "pnl": round(t.pnl, 2),
            "r": round(t.pnl / risk_usd, 2) if risk_usd else None,
            "equity": round(eq, 2),
            "dd_pct": round(dd * 100, 2),
            "setup_tag": t.setup_tag or "",
        })

    n = len(closed)
    floor = start * (1 - rule["max_dd_pct"] / 100)
    target = start * (1 + rule["profit_target_pct"] / 100)
    cur_dd = (peak - eq) / peak if peak else 0.0

    # today's realised PnL vs the daily wall (approx off start balance; the real
    # wall is measured off each eval-day's opening equity at 00:30 UTC)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    today_pnl = sum(
        t.pnl for t in closed
        if (t.closed_at and hasattr(t.closed_at, "strftime")
            and t.closed_at.strftime("%Y-%m-%d") == today)
    )
    daily_limit_usd = start * rule["daily_loss_pct"] / 100

    wr = (wins / n * 100) if n else 0.0
    avg_win = (gross_win / wins) if wins else 0.0
    avg_loss = (gross_loss / losses) if losses else 0.0
    expectancy = ((wr / 100) * avg_win - (1 - wr / 100) * avg_loss)
    total_r = round((eq - start) / risk_usd, 2) if risk_usd else None

    return {
        "eval": EVAL, "strategy": HERO,
        "account": start, "risk_pct": RISK, "risk_usd": round(risk_usd, 2),
        "n_trades": n,
        "equity": round(eq, 2),
        "peak": round(peak, 2), "trough": round(trough, 2),
        "max_dd_pct": round(maxdd * 100, 2),
        "cur_dd_pct": round(cur_dd * 100, 2),
        "tuw_trades": tuw, "tuw_pct": round(tuw / n * 100, 1) if n else 0.0,
        "max_loss_streak": max_loss_streak, "cur_loss_streak": cur_streak,
        "win_rate": round(wr, 1), "wins": wins, "losses": losses,
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "expectancy_usd": round(expectancy, 2), "total_r": total_r,
        "pnl_total": round(eq - start, 2),
        # walls
        "floor": round(floor, 2), "target": round(target, 2),
        "dd_limit_pct": rule["max_dd_pct"], "daily_limit_pct": rule["daily_loss_pct"],
        "target_pct": rule["profit_target_pct"],
        "to_floor_usd": round(eq - floor, 2),
        "to_floor_pct": round((eq - floor) / eq * 100, 2) if eq else 0.0,
        "to_target_usd": round(target - eq, 2),
        "progress_pct": round((eq - start) / (target - start) * 100, 1) if target > start else 0.0,
        "today_pnl": round(today_pnl, 2),
        "daily_limit_usd": round(daily_limit_usd, 2),
        "daily_used_pct": round(-today_pnl / daily_limit_usd * 100, 1) if (today_pnl < 0 and daily_limit_usd) else 0.0,
        "ledger": ledger,
    }


# ── page ──────────────────────────────────────────────────────────────────────
_CSS = r"""<style>
.pl h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pl .sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.pl .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px;margin-bottom:16px}
.pl .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;position:relative;overflow:hidden}
.pl .card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--line2)}
.pl .card.g::after{background:var(--long)} .pl .card.r::after{background:var(--short)} .pl .card.a::after{background:var(--amber)} .pl .card.b::after{background:var(--accent)}
.pl .card .lbl{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.pl .card .val{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1.05;color:var(--ink)}
.pl .card .note{font-size:10.5px;color:var(--dim);margin-top:4px}
.pl .green{color:var(--long)} .pl .red{color:var(--short)} .pl .amber{color:var(--amber)} .pl .ac{color:var(--accent)}
/* wall corridor */
.pl .corridor{position:relative;height:58px;border-radius:9px;overflow:hidden;margin:4px 0 16px;
  background:linear-gradient(90deg,rgba(255,84,104,.22),rgba(255,84,104,.04) 20%,var(--panel2) 50%,rgba(31,217,137,.06) 80%,rgba(31,217,137,.24))}
.pl .corridor .you{position:absolute;top:0;bottom:0;width:3px;background:var(--ink);box-shadow:0 0 10px var(--ink)}
.pl .corridor .you .tag{position:absolute;top:6px;left:6px;font-family:var(--mono);font-size:10px;color:var(--ink);white-space:nowrap}
.pl .corridor .end{position:absolute;font-family:var(--mono);font-size:10px;bottom:6px}
.pl .corridor .end.l{left:6px;color:var(--short)} .pl .corridor .end.r{right:6px;color:var(--long);text-align:right}
.pl table{width:100%;border-collapse:collapse;font-size:12px}
.pl th,.pl td{text-align:right;padding:6px 9px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.pl th{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:500}
.pl th:first-child,.pl td:first-child{text-align:left}
.pl td.g{color:var(--long)} .pl td.r{color:var(--short)} .pl td.dim{color:var(--dim)}
.pl .sb-wrap{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:4px 10px;overflow-x:auto}
.pl .empty{text-align:center;padding:30px 18px;color:var(--dim);border:1px dashed var(--line2);border-radius:11px}
/* log form */
.pl form.log{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:9px;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:14px 16px;margin-bottom:6px}
.pl .lf{display:flex;flex-direction:column;gap:3px}
.pl .lf label{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.pl .lf input,.pl .lf select{background:var(--panel2);border:1px solid var(--line2);color:var(--ink);padding:6px 9px;border-radius:6px;font-family:var(--mono);font-size:12px}
.pl .lf input:focus,.pl .lf select:focus{outline:none;border-color:var(--accent)}
.pl .lf.full{grid-column:1/-1}
.pl .logbtn{background:var(--accent-d);color:var(--accent);border:1px solid var(--line2);border-radius:6px;padding:8px 16px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;cursor:pointer;align-self:end}
.pl .logbtn:hover{filter:brightness(1.3)}
</style>"""


def ledger_page() -> str:
    body = r"""
<div class="pl">
  <h1>Prop Ledger</h1>
  <div class="sub">Realised <b>ASIAN_RSI_DIP_v1</b> trades on the Breakout eval book — equity vs the walls. Simulated streak risk lives on <a href="/survival" class="ac">Survival</a>.</div>

  <div id="cards"></div>
  <div class="corridor" id="corridor" style="display:none"></div>

  <div class="sect" id="h-log" onclick="tog('log')"><span class="caret">▾</span><span class="ttl">＋ log a prop trade</span><span class="line"></span></div>
  <div class="sec-body closed" id="s-log">
  <form class="log" id="logform" onsubmit="return submitLog(event)">
    <div class="lf"><label>Direction</label><select id="f-dir"><option value="long">long</option><option value="short">short</option></select></div>
    <div class="lf"><label>Entry $</label><input id="f-entry" type="number" step="any" placeholder="62800"></div>
    <div class="lf"><label>Exit $</label><input id="f-exit" type="number" step="any" placeholder="65300"></div>
    <div class="lf"><label>Size ₿</label><input id="f-size" type="number" step="any" placeholder="0.04"></div>
    <div class="lf"><label>PnL $</label><input id="f-pnl" type="number" step="any" placeholder="+98"></div>
    <div class="lf"><label>Fees $</label><input id="f-fees" type="number" step="any" placeholder="1" value="0"></div>
    <div class="lf"><label>Opened</label><input id="f-open" type="datetime-local"></div>
    <div class="lf"><label>Closed</label><input id="f-close" type="datetime-local"></div>
    <div class="lf full"><label>Note</label><input id="f-note" type="text" placeholder="optional"></div>
    <button class="logbtn" type="submit">Log prop trade</button>
  </form>
  <div class="sub" style="font-size:11px;margin:6px 0 0">PnL is the realised account move. Leave it blank to auto-estimate from entry/exit/size. R is computed off the locked {RISK}% risk (${RISK_USD}).</div>
  </div>

  <div class="sect" id="h-trades" onclick="tog('trades')"><span class="caret">▾</span><span class="ttl">trades <span id="tcount" class="dim" style="font-weight:400"></span></span><span class="line"></span></div>
  <div class="sec-body" id="s-trades"><div id="ledger"></div></div>
</div>"""
    body = body.replace("{RISK}", str(RISK)).replace("{RISK_USD}", str(round(ACCOUNT * RISK / 100)))

    script = r"""
const $=id=>document.getElementById(id);
function tog(id){ $('h-'+id).classList.toggle('closed'); $('s-'+id).classList.toggle('closed'); }
function money(n){ return (n==null)?'—':Number(n).toLocaleString(undefined,{maximumFractionDigits:0}); }
function card(lbl,val,note,cls){ return `<div class="card ${cls||''}"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="note">${note||''}</div></div>`; }

function render(d){
  const eqCls = d.equity>=d.account?'g':'r';
  const ddCls = d.cur_dd_pct>=d.dd_limit_pct*0.66?'r':d.cur_dd_pct>0?'a':'b';
  $('cards').className='grid';
  $('cards').innerHTML =
      card('Equity','$'+money(d.equity), (d.pnl_total>=0?'+':'')+'$'+money(d.pnl_total)+' · '+(d.total_r!=null?d.total_r+'R':'—'), eqCls)
    + card('To target','$'+money(d.to_target_usd), d.progress_pct+'% there · target $'+money(d.target),'b')
    + card('To floor','$'+money(d.to_floor_usd), d.to_floor_pct+'% cushion · floor $'+money(d.floor),'r')
    + card('Current DD','−'+d.cur_dd_pct+'%', 'limit '+d.dd_limit_pct+'% · max hit −'+d.max_dd_pct+'%', ddCls)
    + card('Daily used', d.daily_used_pct+'%', 'of '+d.daily_limit_pct+'% · today '+(d.today_pnl>=0?'+':'')+'$'+money(d.today_pnl), d.daily_used_pct>=66?'r':'a')
    + card('Loss streak', d.cur_loss_streak+' now', 'worst '+d.max_loss_streak+' · WR '+d.win_rate+'%', d.cur_loss_streak>=3?'r':'b')
    + card('Peak / trough','$'+money(d.peak), '$'+money(d.trough)+' trough · '+d.tuw_pct+'% TUW','b')
    + card('Expectancy', (d.expectancy_usd>=0?'+':'')+'$'+d.expectancy_usd, d.wins+'W / '+d.losses+'L · '+d.n_trades+' trades', d.expectancy_usd>=0?'g':'r');

  // corridor: floor … equity … target
  if(d.n_trades>0){
    const lo=d.floor, hi=d.target, pos=Math.max(0,Math.min(100,(d.equity-lo)/(hi-lo)*100));
    $('corridor').style.display='';
    $('corridor').innerHTML =
        `<div class="end l">FLOOR $${money(d.floor)}</div>`
      + `<div class="end r">TARGET $${money(d.target)}</div>`
      + `<div class="you" style="left:${pos}%"><div class="tag">$${money(d.equity)}</div></div>`;
  }

  $('tcount').textContent = d.n_trades?('· '+d.n_trades):'';
  if(!d.ledger.length){
    $('ledger').innerHTML = '<div class="empty"><b>No prop trades yet</b><br>Log your first eval trade above — equity starts at $'+money(d.account)+'.</div>';
    return;
  }
  const rows = d.ledger.slice().reverse().map(t=>`<tr>
    <td class="dim">${t.date}</td>
    <td class="${t.direction==='long'?'g':'r'}">${t.direction.toUpperCase()}</td>
    <td>${money(t.entry)}</td>
    <td>${t.exit?money(t.exit):'—'}</td>
    <td class="${t.r>=0?'g':'r'}">${t.r!=null?(t.r>=0?'+':'')+t.r+'R':'—'}</td>
    <td class="${t.pnl>=0?'g':'r'}">${t.pnl>=0?'+':''}$${money(t.pnl)}</td>
    <td>$${money(t.equity)}</td>
    <td class="dim">−${t.dd_pct}%</td>
  </tr>`).join('');
  $('ledger').innerHTML = `<div class="sb-wrap"><table>
    <tr><th>closed</th><th>dir</th><th>entry</th><th>exit</th><th>R</th><th>pnl</th><th>equity</th><th>dd</th></tr>
    ${rows}</table></div>`;
}

async function load(){
  try{ const r=await fetch('/api/prop/ledger'); render(await r.json()); }
  catch(e){ $('cards').innerHTML='<div class="empty" style="color:var(--amber)">failed to load</div>'; }
}

function toISO(v){ return v ? new Date(v).toISOString() : null; }
async function submitLog(ev){
  ev.preventDefault();
  const entry=parseFloat($('f-entry').value);
  if(!entry){ alert('entry price required'); return false; }
  const payload={
    book:'prop', direction:$('f-dir').value, symbol:'BTC/USD:USD',
    entry, exit:parseFloat($('f-exit').value)||null,
    size:parseFloat($('f-size').value)||0.001, leverage:1,
    pnl:$('f-pnl').value!==''?parseFloat($('f-pnl').value):null,
    fees:parseFloat($('f-fees').value)||0,
    opened_at:toISO($('f-open').value), closed_at:toISO($('f-close').value),
    notes:$('f-note').value||null,
  };
  try{
    const r=await fetch('/api/prop/trades',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!r.ok){ const e=await r.json(); throw new Error(JSON.stringify(e.detail||e)); }
    ['f-entry','f-exit','f-size','f-pnl','f-note'].forEach(id=>$(id).value='');
    load();
  }catch(e){ alert('log failed: '+e.message); }
  return false;
}

(function(){ const n=new Date(),f=d=>d.toISOString().slice(0,16); $('f-open').value=f(n); $('f-close').value=f(n); })();
load();
"""
    return shell("/prop-ledger", "Ledger", body, script=script, head_extra=_CSS, meta="eval book")
