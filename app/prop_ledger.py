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
from .prop_views import HERO, prop_config
from .theme import shell


def _as_utc(dt):
    """Trade timestamps may be naive (stored UTC) or aware — normalise to aware UTC."""
    if dt is None or not hasattr(dt, "tzinfo"):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def _open_upnl(book: str = "prop"):
    """Unrealised PnL across logged-open prop positions, marked to live Kraken
    price. Returns (upnl_usd, live_bool). Breakout's kill-lines are on LIVE equity
    (open trades count), so the ledger must fold this into the breach check."""
    opens = [t for t in get_trades(limit=5000, book=book) if t.pnl is None]
    if not opens:
        return 0.0, False
    from . import kraken_sync
    mark = None
    try:
        key, secret = kraken_sync.get_api_keys("personal")
        mark = kraken_sync.fetch_market_btc(key, secret).get("mark")
    except Exception:
        pass
    if not mark:
        return 0.0, False
    total = 0.0
    for t in opens:
        entry = float(t.entry or 0); size = abs(float(t.size or 0))
        if not entry or not size:
            continue
        total += (float(mark) - entry) * size * (-1 if t.direction == "short" else 1)
    return total, True


def prop_ledger_data(live: bool = True) -> dict:
    cfg = prop_config()
    ACCOUNT, RISK, EVAL = cfg["account"], cfg["risk"], cfg["eval_name"]
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

    # ── live equity = realised + open unrealised. The eval's kill-lines watch
    # LIVE equity, so a deep open drawdown can blow it before any trade closes.
    open_upnl, live_feed = _open_upnl() if live else (0.0, False)
    live_eq = eq + open_upnl
    live_dd = (peak - live_eq) / peak if peak else 0.0
    cur_dd = max((peak - eq) / peak if peak else 0.0, live_dd)
    eff_maxdd = max(maxdd, live_dd)

    # ── daily wall off THIS eval-day's opening equity (00:30 UTC reset), not the
    # static start. Day P&L = realised since the boundary + current open uPnL.
    now = datetime.datetime.now(datetime.timezone.utc)
    reset_min = rule.get("reset_min_utc", 30)
    boundary = now.replace(hour=0, minute=reset_min, second=0, microsecond=0)
    if now < boundary:
        boundary -= datetime.timedelta(days=1)
    day_realised = sum(t.pnl for t in closed
                       if _as_utc(t.closed_at) and _as_utc(t.closed_at) >= boundary)
    opening_eq = eq - day_realised               # equity at the eval-day open
    day_pnl = day_realised + open_upnl            # live intraday move
    daily_limit_usd = opening_eq * rule["daily_loss_pct"] / 100

    # verdict: BLOWN the moment max DD (incl. open) touches the limit, live equity
    # is at/under the floor, or the daily wall breaks. Never un-fails on recovery.
    breach_dd = eff_maxdd * 100 >= rule["max_dd_pct"]
    breach_floor = trough <= floor or live_eq <= floor
    breach_daily = day_pnl < 0 and -day_pnl >= daily_limit_usd
    failed = breach_dd or breach_floor or breach_daily
    passed = eq >= target

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
        "live_equity": round(live_eq, 2), "open_upnl": round(open_upnl, 2),
        "live_feed": live_feed,
        "peak": round(peak, 2), "trough": round(trough, 2),
        "max_dd_pct": round(eff_maxdd * 100, 2),
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
        "to_floor_usd": round(live_eq - floor, 2),
        "to_floor_pct": round((live_eq - floor) / live_eq * 100, 2) if live_eq else 0.0,
        "to_target_usd": round(target - eq, 2),
        "progress_pct": round((eq - start) / (target - start) * 100, 1) if target > start else 0.0,
        "today_pnl": round(day_pnl, 2),
        "opening_eq": round(opening_eq, 2),
        "daily_limit_usd": round(daily_limit_usd, 2),
        "daily_used_pct": round(-day_pnl / daily_limit_usd * 100, 1) if (day_pnl < 0 and daily_limit_usd) else 0.0,
        "failed": failed, "passed": passed,
        "breach_dd": breach_dd, "breach_floor": breach_floor, "breach_daily": breach_daily,
        "ledger": ledger,
    }


def archive_summaries() -> list:
    """Past eval attempts: one row per archived run, scored under the params it
    actually ran with (from prop_eval_archive). `net` folds in the entry fee — a
    run that "only" lost the fee still cost you the fee."""
    from .database import get_prop_archives, prop_archive_books
    metas = {m["tag"]: m for m in get_prop_archives()}
    cfg = prop_config()                       # fallback for runs archived pre-metadata
    out = []
    for tag in prop_archive_books():
        meta = metas.get(tag) or {"account": cfg["account"], "risk": cfg["risk"],
                                  "eval_name": cfg["eval_name"], "fee": 0.0}
        ts = [t for t in get_trades(limit=20000, book=tag) if t.pnl is not None]
        if not ts:
            continue
        ts.sort(key=lambda t: (t.closed_at or t.opened_at or datetime.datetime.min))
        acct = meta["account"] or 5000.0
        plan = EVALS.get(meta["eval_name"] or "", {})
        floor = acct * (1 - plan.get("max_dd_pct", 3) / 100)
        target = acct * (1 + plan.get("profit_target_pct", 9) / 100)
        eq = acct; trough = acct; maxdd = 0.0; peak = acct
        for t in ts:
            eq += t.pnl; peak = max(peak, eq); trough = min(trough, eq)
            maxdd = max(maxdd, (peak - eq) / peak if peak else 0.0)
        verdict = "passed" if eq >= target else (
            "failed" if (trough <= floor or maxdd * 100 >= plan.get("max_dd_pct", 3)) else "incomplete")
        dates = [t.closed_at or t.opened_at for t in ts if (t.closed_at or t.opened_at)]
        span = ""
        if dates:
            span = min(dates).strftime("%Y-%m-%d") + " → " + max(dates).strftime("%Y-%m-%d")
        out.append({
            "tag": tag, "eval_name": meta["eval_name"], "account": acct,
            "n_trades": len(ts), "final_equity": round(eq, 2),
            # pnl is PAPER — eval equity is never yours, pass or fail. The only cash
            # that ever moved is the fee, so that's the only thing summed as cost.
            "pnl": round(eq - acct, 2), "max_dd_pct": round(maxdd * 100, 2),
            "verdict": verdict, "span": span,
            "fee": round(meta.get("fee") or 0.0, 2),
        })
    return out


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
/* open prop positions — live-marked cards (mirrors /journal) */
.op-wrap{margin-bottom:16px}
.op-hd{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.op-hd b{font-size:11px;letter-spacing:.04em;color:var(--ink)}
.op-hd .live{font-size:8px;text-transform:uppercase;letter-spacing:.1em;color:var(--long);border:1px solid var(--long);border-radius:4px;padding:1px 5px}
.opcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:10px}
.opcard{border:1px solid var(--line);border-radius:10px;background:var(--panel);overflow:hidden}
.opcard.long{border-left:3px solid var(--long)}.opcard.short{border-left:3px solid var(--short)}
.opcard .top{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border-bottom:1px solid var(--line);background:var(--panel2)}
.opcard .ven{font-size:8.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim)}
.opcard .mkt{font-size:13.5px;font-weight:700;color:var(--ink);font-family:var(--mono)}
.opcard .sd{font-size:10.5px;font-weight:700;font-family:var(--mono)}
.opcard .body{padding:7px 12px 11px}
.oprow{display:grid;grid-template-columns:auto 1fr;gap:8px;padding:2.5px 0;font-size:11.5px;align-items:baseline}
.oprow .l{color:var(--dim)}.oprow .v{font-family:var(--mono);color:var(--ink);text-align:right}
.oprow .v small{color:var(--dim);font-size:10px}
.opsec{font-size:8.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--faint);margin:9px 0 3px;border-top:1px solid var(--line);padding-top:8px}
.opcard .g{color:var(--long)}.opcard .r{color:var(--short)}.opcard .dim{color:var(--dim)}
.opcard{cursor:pointer}.opcard:hover{border-color:var(--accent)}
.opclose{width:100%;margin-top:9px;background:var(--accent-d);color:var(--accent);border:1px solid var(--line2);border-radius:6px;padding:7px;font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;cursor:pointer}
.opclose:hover{filter:brightness(1.3)}
.pl tbody tr{cursor:pointer}.pl tbody tr:hover td{background:var(--panel2)}
/* verdict banner */
.verdict{border-radius:11px;padding:13px 16px;margin-bottom:16px;display:flex;align-items:center;gap:12px;font-family:var(--mono)}
.verdict.fail{background:rgba(255,84,104,.1);border:1px solid var(--short)}
.verdict.pass{background:rgba(31,217,137,.1);border:1px solid var(--long)}
.verdict .tag{font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 9px;border-radius:5px}
.verdict.fail .tag{background:var(--short);color:#fff}.verdict.pass .tag{background:var(--long);color:#021}
.verdict .why{font-size:11.5px;color:var(--ink)}
/* edit modal */
.ovl{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:50}
.ovl.on{display:flex}
.modal{background:var(--panel);border:1px solid var(--line2);border-radius:13px;padding:18px 20px;width:min(440px,92vw);max-height:90vh;overflow:auto}
.modal h2{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin:0 0 12px}
.modal .grid2{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.modal .lf{display:flex;flex-direction:column;gap:3px}.modal .lf.full{grid-column:1/-1}
.modal .lf label{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.modal .lf input,.modal .lf select{background:var(--panel2);border:1px solid var(--line2);color:var(--ink);padding:6px 9px;border-radius:6px;font-family:var(--mono);font-size:12px}
.modal .acts{display:flex;gap:9px;margin-top:14px}
.modal button{border:1px solid var(--line2);border-radius:6px;padding:8px 16px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;cursor:pointer}
.modal .save{background:var(--accent-d);color:var(--accent);flex:1}
.modal .del{background:rgba(255,84,104,.12);color:var(--short)}
.modal .cancel{background:var(--panel2);color:var(--dim)}
.modal button:hover{filter:brightness(1.3)}
.pl .neweval{margin-left:8px;background:var(--panel2);color:var(--dim);border:1px solid var(--line2);border-radius:6px;padding:3px 10px;font-family:var(--mono);font-size:10px;cursor:pointer}
.pl .neweval:hover{color:var(--accent);border-color:var(--accent)}
</style>"""


def ledger_page() -> str:
    body = r"""
<div class="pl">
  <h1>Prop Ledger</h1>
  <div class="sub">Realised <b>ASIAN_RSI_DIP_v1</b> trades on the Breakout eval book — equity vs the walls. Simulated streak risk lives on <a href="/survival" class="ac">Survival</a>.
    <button type="button" class="neweval" onclick="newEval()">↻ start new eval</button></div>

  <div id="verdict"></div>
  <div id="prop-open"></div>
  <div id="lock-note"></div>

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

  <div class="sect closed" id="h-arch" onclick="tog('arch');loadArchives()"><span class="caret">▾</span><span class="ttl">past attempts <span id="acount" class="dim" style="font-weight:400"></span></span><span class="line"></span></div>
  <div class="sec-body closed" id="s-arch"><div id="archives"></div></div>
</div>

<div class="ovl" id="ovl" onclick="if(event.target===this)closeEdit()">
  <div class="modal">
    <h2 id="m-title">Edit trade</h2>
    <input type="hidden" id="m-id">
    <div class="grid2">
      <div class="lf"><label>Direction</label><select id="m-dir"><option value="long">long</option><option value="short">short</option></select></div>
      <div class="lf"><label>Size ₿</label><input id="m-size" type="number" step="any"></div>
      <div class="lf"><label>Entry $</label><input id="m-entry" type="number" step="any"></div>
      <div class="lf"><label>Exit $</label><input id="m-exit" type="number" step="any" placeholder="set to close"></div>
      <div class="lf"><label>PnL $ (net)</label><input id="m-pnl" type="number" step="any" placeholder="set to close"></div>
      <div class="lf"><label>Fees $</label><input id="m-fees" type="number" step="any"></div>
      <div class="lf"><label>Opened</label><input id="m-open" type="datetime-local"></div>
      <div class="lf"><label>Closed</label><input id="m-close" type="datetime-local"></div>
      <div class="lf full"><label>Note</label><input id="m-note" type="text"></div>
    </div>
    <div class="acts">
      <button class="save" type="button" onclick="saveEdit()">Save</button>
      <button class="del" type="button" onclick="delEdit()">Delete</button>
      <button class="cancel" type="button" onclick="closeEdit()">Cancel</button>
    </div>
  </div>
</div>

<div class="ovl" id="nev-ovl" onclick="if(event.target===this)closeNewEval()">
  <div class="modal">
    <h2>Start new eval</h2>
    <div class="sub" style="font-size:11px;margin:-6px 0 12px">Archives the current run (kept, not deleted) and resets the ledger to your chosen start. Walls recompute from the plan.</div>
    <div class="grid2">
      <div class="lf"><label>Account size $</label><input id="nev-acct" type="number" step="any" value="5000"></div>
      <div class="lf"><label>Risk / trade %</label><input id="nev-risk" type="number" step="any" value="0.5"></div>
      <div class="lf"><label>Fee paid $</label><input id="nev-fee" type="number" step="any" value="0"></div>
      <div class="lf"><label>Plan</label><select id="nev-plan"></select></div>
      <div class="lf full"><div id="nev-preview" class="sub" style="font-size:11px;margin:0"></div></div>
    </div>
    <div class="acts">
      <button class="save" type="button" onclick="submitNewEval()">Start eval</button>
      <button class="cancel" type="button" onclick="closeNewEval()">Cancel</button>
    </div>
  </div>
</div>"""
    cfg = prop_config()
    body = body.replace("{RISK}", str(cfg["risk"])).replace("{RISK_USD}", str(round(cfg["account"] * cfg["risk"] / 100)))

    script = r"""
const $=id=>document.getElementById(id);
function tog(id){ $('h-'+id).classList.toggle('closed'); $('s-'+id).classList.toggle('closed'); }
function money(n){ return (n==null)?'—':Number(n).toLocaleString(undefined,{maximumFractionDigits:0}); }
function card(lbl,val,note,cls){ return `<div class="card ${cls||''}"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="note">${note||''}</div></div>`; }

function render(d){
  // latched verdict — the page's own walls, checked. This is what was missing.
  let v='';
  const hasOpen = !!d.open_upnl;
  const liveEq = hasOpen ? d.live_equity : d.equity;   // breach math uses live equity
  if(d.failed){
    const why=[]; if(d.breach_dd)why.push('max DD −'+d.max_dd_pct+'% hit the '+d.dd_limit_pct+'% limit');
    if(d.breach_floor)why.push('equity $'+money(liveEq)+' at/under floor $'+money(d.floor));
    if(d.breach_daily)why.push('daily loss limit breached');
    v=`<div class="verdict fail"><span class="tag">Eval failed</span><span class="why">${why.join(' · ')}</span></div>`;
  } else if(d.passed){
    v=`<div class="verdict pass"><span class="tag">Target hit</span><span class="why">equity $${money(d.equity)} reached target $${money(d.target)}</span></div>`;
  }
  $('verdict').innerHTML=v;

  // #3 lock: no new trades on a blown eval (closing/editing existing still works)
  const logEls=document.querySelectorAll('#logform input,#logform select,#logform button');
  if(d.failed){
    $('lock-note').innerHTML=`<div class="verdict fail" style="margin-top:-8px"><span class="tag">Locked</span><span class="why">New trades blocked on a failed eval — close/edit open positions above, or <a href="#" class="ac" onclick="newEval();return false">start a new eval</a>.</span></div>`;
    logEls.forEach(e=>e.disabled=true);
  } else { $('lock-note').innerHTML=''; logEls.forEach(e=>e.disabled=false); }

  const eqCls = liveEq>=d.account?'g':'r';
  const ddCls = d.cur_dd_pct>=d.dd_limit_pct*0.66?'r':d.cur_dd_pct>0?'a':'b';
  const eqNote = hasOpen
    ? ('real $'+money(d.equity)+' · open '+(d.open_upnl>=0?'+':'')+'$'+money(d.open_upnl))
    : ((d.pnl_total>=0?'+':'')+'$'+money(d.pnl_total)+' · '+(d.total_r!=null?d.total_r+'R':'—'));
  $('cards').className='grid';
  $('cards').innerHTML =
      card(hasOpen?'Equity (live)':'Equity','$'+money(liveEq), eqNote, eqCls)
    + card('To target','$'+money(d.to_target_usd), d.progress_pct+'% there · target $'+money(d.target),'b')
    + card('To floor','$'+money(d.to_floor_usd), d.to_floor_pct+'% cushion · floor $'+money(d.floor),'r')
    + card('Current DD','−'+d.cur_dd_pct+'%', 'limit '+d.dd_limit_pct+'% · max hit −'+d.max_dd_pct+'%', ddCls)
    + card('Daily used', d.daily_used_pct+'%', 'of '+d.daily_limit_pct+'% · today '+(d.today_pnl>=0?'+':'')+'$'+money(d.today_pnl)+' (open $'+money(d.opening_eq)+')', d.daily_used_pct>=66?'r':'a')
    + card('Loss streak', d.cur_loss_streak+' now', 'worst '+d.max_loss_streak+' · WR '+d.win_rate+'%', d.cur_loss_streak>=3?'r':'b')
    + card('Peak / trough','$'+money(d.peak), '$'+money(d.trough)+' trough · '+d.tuw_pct+'% TUW','b')
    + card('Expectancy', (d.expectancy_usd>=0?'+':'')+'$'+d.expectancy_usd, d.wins+'W / '+d.losses+'L · '+d.n_trades+' trades', d.expectancy_usd>=0?'g':'r');

  // corridor: floor … LIVE equity … target
  if(d.n_trades>0){
    const lo=d.floor, hi=d.target, pos=Math.max(0,Math.min(100,(liveEq-lo)/(hi-lo)*100));
    $('corridor').style.display='';
    $('corridor').innerHTML =
        `<div class="end l">FLOOR $${money(d.floor)}</div>`
      + `<div class="end r">TARGET $${money(d.target)}</div>`
      + `<div class="you" style="left:${pos}%"><div class="tag">$${money(liveEq)}</div></div>`;
  }

  $('tcount').textContent = d.n_trades?('· '+d.n_trades):'';
  if(!d.ledger.length){
    $('ledger').innerHTML = '<div class="empty"><b>No prop trades yet</b><br>Log your first eval trade above — equity starts at $'+money(d.account)+'.</div>';
    return;
  }
  const rows = d.ledger.slice().reverse().map(t=>`<tr onclick="openEdit(${t.id})">
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

async function goalLevels(){
  // expected TP/SL move % from the Goal model (config-driven), overlaid on the position
  try{
    const cfg=await fetch('/api/config').then(r=>r.json());
    const g=await fetch('/api/goal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)}).then(r=>r.json());
    if(g&&g.underlying_win_pct!=null) return {tp:g.underlying_win_pct/100, sl:g.underlying_loss_pct/100, rr:g.actual_rr};
  }catch(e){}
  return null;
}
async function loadPropOpen(){
  const el=$('prop-open');
  try{
    const [d,lvl]=await Promise.all([fetch('/api/prop/positions/open').then(r=>r.json()), goalLevels()]);
    const ps=d.positions||[];
    if(!ps.length){ el.innerHTML=''; return; }
    const u=(v,dp=0)=>v==null?'—':'$'+Number(v).toLocaleString('en',{maximumFractionDigits:dp});
    const sU=(v)=>v==null?'—':(v>=0?'+':'-')+'$'+Math.abs(v).toLocaleString('en',{maximumFractionDigits:2});
    const pc=(v)=>v==null?'—':(v>=0?'+':'')+Number(v).toFixed(2)+'%';
    const row=(l,v,c)=>`<div class="oprow"><span class="l">${l}</span><span class="v ${c||''}">${v}</span></div>`;
    const cards=ps.map(p=>{
      const isL=p.direction==='long', up=p.upnl_usd||0;
      let plan='';
      if(lvl){
        const tp=isL?p.entry*(1+lvl.tp):p.entry*(1-lvl.tp);
        const sl=isL?p.entry*(1-lvl.sl):p.entry*(1+lvl.sl);
        const win=(p.cost_usd||0)*lvl.tp, loss=(p.cost_usd||0)*lvl.sl;
        plan=`<div class="opsec">Plan — from Goal</div>`
          +row('Take profit',`${u(tp,1)} <small>+${(lvl.tp*100).toFixed(1)}%</small>`,'g')
          +row('Stop loss',`${u(sl,1)} <small>-${(lvl.sl*100).toFixed(1)}%</small>`,'r')
          +row('Expected win',`${sU(win)} <small>${pc(lvl.tp*100)}</small>`,'g')
          +row('Expected loss',`${sU(-loss)} <small>${pc(-lvl.sl*100)}</small>`,'r')
          +row('R:R',lvl.rr!=null?lvl.rr.toFixed(2):(lvl.tp/lvl.sl).toFixed(2),'dim');
      } else { plan=`<div class="opsec">Plan</div>`+row('levels','set Goal config to see plan','dim'); }
      return `<div class="opcard ${isL?'long':'short'}" onclick="openEdit(${p.id})" title="click to edit / close / cancel">
        <div class="top"><div><div class="ven">${p.venue}</div><div class="mkt">${p.symbol}</div></div>
          <div class="sd ${isL?'g':'r'}">${isL?'▲ LONG':'▼ SHORT'} · ${p.leverage}×</div></div>
        <div class="body">
          ${row('Opening price',u(p.entry))}
          ${row('Last price',`${u(p.mark)} <small>move ${pc(p.move_pct)}</small>`,(p.move_pct||0)>=0?'g':'r')}
          ${row('Base qty',p.size+' ₿')}
          ${row('Quote qty / value',u(p.quote_qty))}
          ${row('Initial margin',u(p.margin_usd))}
          ${row('Unrealised P&L',`${sU(up)} <small>${pc(p.upnl_pct)}</small>`,up>=0?'g':'r')}
          ${row('RoE',pc(p.roe_pct),(p.roe_pct||0)>=0?'g':'r')}
          ${row('Est. liquidation',u(p.liquidation),'r')}
          ${row('Funding rate',p.funding!=null?p.funding.toFixed(6):'—','dim')}
          ${plan}
          ${p.live?`<button class="opclose" onclick="event.stopPropagation();closeAtMark(${p.id},${p.mark},${up})">Close at ${u(p.mark)} (${sU(up)})</button>`:''}
        </div></div>`;
    }).join('');
    const tag=ps[0].live?'<span class="live">● live</span>'
      :'<span class="live" style="color:var(--amber);border-color:var(--amber)">○ no feed</span>';
    el.innerHTML=`<div class="op-wrap"><div class="op-hd"><b>Open prop positions</b>${tag}<span class="dim" style="font-size:10px">your logged fill marked to live Kraken price · drops into the ledger once you add an exit</span></div><div class="opcards">${cards}</div></div>`;
  }catch(e){ el.innerHTML=''; }
}
async function load(){
  loadPropOpen();
  try{ const r=await fetch('/api/prop/ledger'); render(await r.json()); }
  catch(e){ $('cards').innerHTML='<div class="empty" style="color:var(--amber)">failed to load</div>'; }
}

function toISO(v){ return v ? new Date(v).toISOString() : null; }
async function submitLog(ev){
  ev.preventDefault();
  const btn=ev.target.querySelector('button[type=submit]');
  if(btn&&btn.disabled) return false;          // guard: kills the double-submit dup
  const entry=parseFloat($('f-entry').value);
  if(!entry){ alert('entry price required'); return false; }
  if(btn) btn.disabled=true;
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
  finally{ if(btn) btn.disabled=false; }
  return false;
}

// ── edit / close / cancel modal (reuses PATCH+DELETE /api/trades/{id}) ──
function toLocal(iso){ if(!iso) return ''; const d=new Date(iso); if(isNaN(d)) return '';
  return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16); }
async function openEdit(id){
  const t=await fetch('/api/trades/'+id).then(r=>r.json());
  $('m-id').value=t.id;
  $('m-title').textContent=(t.pnl==null?'Open position #':'Trade #')+t.id;
  $('m-dir').value=t.direction||'short'; $('m-size').value=t.size??'';
  $('m-entry').value=t.entry??''; $('m-exit').value=t.exit??'';
  $('m-pnl').value=t.pnl??''; $('m-fees').value=t.fees??0;
  $('m-open').value=toLocal(t.opened_at); $('m-close').value=toLocal(t.closed_at);
  $('m-note').value=t.notes||'';
  $('ovl').classList.add('on');
}
function closeEdit(){ $('ovl').classList.remove('on'); }
async function closeAtMark(id,mark,upnl){
  // close an open position at the live mark — exit=mark, pnl=shown uPnL (gross;
  // tweak in the edit modal if you want fees netted). Drops it into the ledger.
  if(!confirm('Close #'+id+' at $'+money(mark)+' for '+(upnl>=0?'+':'')+'$'+money(upnl)+'? It moves into the realised ledger.')) return;
  const r=await fetch('/api/trades/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({exit:mark, pnl:Math.round(upnl*100)/100, closed_at:new Date().toISOString()})});
  if(!r.ok){ alert('close failed'); return; }
  load();
}
async function saveEdit(){
  const id=$('m-id').value;
  const num=id=>$(id).value!==''?parseFloat($(id).value):null;
  const payload={
    direction:$('m-dir').value, size:num('m-size'),
    entry:num('m-entry'), exit:num('m-exit'),
    pnl:num('m-pnl'), fees:num('m-fees'),
    opened_at:toISO($('m-open').value), closed_at:toISO($('m-close').value),
    notes:$('m-note').value||null,
  };
  // ponytail: PATCH ignores nulls, so blank fields stay as-is — fine for our edits
  const r=await fetch('/api/trades/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok){ alert('save failed'); return; }
  closeEdit(); load();
}
async function delEdit(){
  const id=$('m-id').value;
  if(!confirm('Delete trade #'+id+'? This removes it from the eval book.')) return;
  const r=await fetch('/api/trades/'+id,{method:'DELETE'});
  if(!r.ok){ alert('delete failed'); return; }
  closeEdit(); load();
}

let NEV_PLANS={};
async function newEval(){
  const d=await fetch('/api/prop/config').then(r=>r.json());
  NEV_PLANS=d.plans||{};
  $('nev-acct').value=d.config.account; $('nev-risk').value=d.config.risk; $('nev-fee').value=0;
  $('nev-plan').innerHTML=Object.entries(NEV_PLANS).map(([k,v])=>
    `<option value="${k}">${k} — +${v.profit_target_pct}% target · ${v.max_dd_pct}% DD · ${v.daily_loss_pct}% daily</option>`).join('');
  $('nev-plan').value=d.config.eval_name;
  $('nev-plan').onchange=$('nev-acct').oninput=nevPreview; nevPreview();
  $('nev-ovl').classList.add('on');
}
function nevPreview(){
  const a=parseFloat($('nev-acct').value)||0, p=NEV_PLANS[$('nev-plan').value]; if(!p) return;
  const floor=Math.round(a*(1-p.max_dd_pct/100)), tgt=Math.round(a*(1+p.profit_target_pct/100)), daily=Math.round(a*p.daily_loss_pct/100);
  $('nev-preview').innerHTML=`floor <b style="color:var(--short)">$${floor.toLocaleString()}</b> · target <b style="color:var(--long)">$${tgt.toLocaleString()}</b> · daily limit −$${daily.toLocaleString()}`;
}
function closeNewEval(){ $('nev-ovl').classList.remove('on'); }
async function submitNewEval(){
  const account=parseFloat($('nev-acct').value), risk=parseFloat($('nev-risk').value), eval_name=$('nev-plan').value;
  const fee=parseFloat($('nev-fee').value)||0;
  if(!account||!risk){ alert('account and risk required'); return; }
  if(!confirm('Start new eval at $'+account.toLocaleString()+' (fee $'+fee+')? Current run is archived.')) return;
  const r=await fetch('/api/prop/new-eval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account,risk,eval_name,fee})});
  if(!r.ok){ alert('failed to start new eval'); return; }
  const d=await r.json(); closeNewEval(); ARCH_LOADED=false; alert('New eval started — '+d.archived+' trade(s) archived.'); load();
}

let ARCH_LOADED=false;
async function loadArchives(force){
  if(ARCH_LOADED && !force) return; ARCH_LOADED=true;
  try{
    const d=await fetch('/api/prop/archives').then(r=>r.json());
    const a=d.archives||[];
    $('acount').textContent=a.length?('· '+a.length):'';
    const cost=`<div class="sub" style="font-size:11px;margin:8px 0 0">
      <b>${d.attempts}</b> attempt(s) incl. the live one · <b class="red">$${money(d.spent)}</b> paid in fees
      <span class="dim">(current eval $${money(d.active_fee)})</span>.
      Eval P&amp;L below is <b>paper</b> — it never settles to you. Fees are the only cash that moved.</div>`;
    if(!a.length){ $('archives').innerHTML='<div class="empty">No past attempts yet. Starting a new eval archives the current run here.</div>'+cost; return; }
    const vc={passed:'g',failed:'r',incomplete:'dim'};
    const rows=a.map(x=>`<tr>
      <td class="dim">${x.span||'—'}</td>
      <td>${x.eval_name||'—'}</td>
      <td>$${money(x.account)}</td>
      <td>${x.n_trades}</td>
      <td class="${x.pnl>=0?'g':'r'}">${x.pnl>=0?'+':''}$${money(x.pnl)}</td>
      <td>$${money(x.final_equity)}</td>
      <td class="dim">−${x.max_dd_pct}%</td>
      <td class="r">${x.fee?('−$'+money(x.fee)):'—'}</td>
      <td class="${vc[x.verdict]||'dim'}">${x.verdict.toUpperCase()}</td></tr>`).join('');
    $('archives').innerHTML=`<div class="sb-wrap"><table>
      <tr><th>span</th><th>plan</th><th>start</th><th>trades</th><th>paper pnl</th><th>final</th><th>maxdd</th><th>fee</th><th>verdict</th></tr>
      ${rows}</table></div>`+cost;
  }catch(e){ $('archives').innerHTML='<div class="empty" style="color:var(--amber)">failed to load</div>'; }
}

(function(){ const n=new Date(),f=d=>d.toISOString().slice(0,16); $('f-open').value=f(n); $('f-close').value=f(n); })();
load();
"""
    return shell("/prop-ledger", "Ledger", body, script=script, head_extra=_CSS, meta="eval book")
