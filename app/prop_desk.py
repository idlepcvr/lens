"""LENS /prop-desk — live entry read for the PROP hero strategy (ASIAN_RSI_DIP_v1).

The other prop pages model the eval (pass odds, survival, equity sim). This is
the missing live feed: it evaluates the hero's signal on the freshest CLOSED 4H
bar and says ENTER / STAND DOWN, with the trade ticket sized at *legal prop*
leverage (risk% capped at the firm's 5x). Same "can I enter now?" idea as the
HEDGE /desk, but for the prop strategy + prop walls. Read-only — you place the
order on Kraken yourself.

The hero only fires on Asian-session bar closes (00:00 / 04:00 UTC): long when
RSI crosses back up through 40 in a 4H + daily uptrend; short on the 60 mirror in
a downtrend. So ENTER is only ever live right after one of those two bars closes.
"""

import datetime

import pandas as pd

from .backtest_engine import STRATEGIES, add_indicators, load_ohlcv
from .prop_eval import EVALS, _legal_leverage
from .prop_views import HERO, prop_config
from .theme import shell

# Bar length per timeframe. The desk drops a still-forming last bar, so this MUST
# match the strategy's own timeframe — a 4h constant on a 1h strategy discards the
# freshest closed bar and reads a stale one.
_TF_MS_BY_TF = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000,
                "4h": 14_400_000, "1d": 86_400_000}


def _tf_ms(tf: str) -> int:
    return _TF_MS_BY_TF.get(tf, 14_400_000)


def _next_asian_close(now: datetime.datetime) -> datetime.datetime:
    """Next UTC time the hero can fire. The signal evaluates bars whose OPEN hour
    is 00:00 / 04:00 (Asian) — those bars CLOSE at 04:00 / 08:00, which is when the
    desk flips to ENTER. So the next opportunity is the next 04:00 or 08:00 close."""
    cands = []
    for add_day in (0, 1):
        for h in (4, 8):
            t = (now + datetime.timedelta(days=add_day)).replace(
                hour=h, minute=0, second=0, microsecond=0)
            if t > now:
                cands.append(t)
    return min(cands)


def _stand_down_reason(strategy, asian_family, is_asian, up, down, dbull, dbear,
                       rsi, rsi_prv, daily_ema50):
    """The FIRST unmet gate, in plain words. Ordered outermost-first (session →
    daily trend → 4H trend → trigger) so it names the thing actually blocking the
    trade, not the last condition that happened to be false."""
    if asian_family and not is_asian:
        return "not an Asian bar — the setup only evaluates the 00:00 / 04:00 UTC closes"
    if asian_family:
        if not dbull and not dbear:
            return "daily trend flat — no directional bias to trade with"
        if dbull and not up:
            return "daily is bullish but 4H trend hasn't turned up (EMA21 below EMA50)"
        if dbear and not down:
            return "daily is bearish but 4H trend hasn't turned down (EMA21 above EMA50)"
        lvl = f" (needs a daily close above ${daily_ema50:,.0f})" if daily_ema50 and dbear else ""
        if dbull:
            return (f"trend aligned long, waiting on the RSI dip-recovery: "
                    f"needs prev < 40 then ≥ 40, now {rsi_prv} → {rsi}")
        return (f"daily is bearish{lvl}, so longs are gated; the short needs an RSI "
                f"fade from > 60 down through 60, now {rsi_prv} → {rsi}")
    return f"{strategy}: entry conditions not met on this bar"


def _checklist(is_asian, up, down, dbull, dbear, rsi, rsi_prv):
    """Per-direction condition rows mirroring _signal_asian_rsi_dip_v1."""
    long_conds = [
        {"label": "Asian bar (00 / 04 UTC)", "ok": is_asian},
        {"label": "4H uptrend · EMA21 > EMA50", "ok": bool(up)},
        {"label": "Daily uptrend · close > EMA50", "ok": bool(dbull)},
        {"label": "RSI dip-recovery · prev < 40, now ≥ 40",
         "ok": bool(rsi_prv is not None and rsi is not None and rsi_prv < 40 and rsi >= 40)},
    ]
    short_conds = [
        {"label": "Asian bar (00 / 04 UTC)", "ok": is_asian},
        {"label": "4H downtrend · EMA21 < EMA50", "ok": bool(down)},
        {"label": "Daily downtrend · close < EMA50", "ok": bool(dbear)},
        {"label": "RSI fade · prev > 60, now ≤ 60",
         "ok": bool(rsi_prv is not None and rsi is not None and rsi_prv > 60 and rsi <= 60)},
    ]
    return {"long": long_conds, "short": short_conds}


def prop_desk_state(refresh: bool = True, strategy: str = HERO) -> dict:
    strat = STRATEGIES[strategy]
    params = strat["params"]
    tf = strat.get("timeframe") or "4h"
    # Live eval params, not the import-time defaults — the desk must size to the
    # account you actually bought, or every ticket on it is half the real trade.
    cfg = prop_config()
    EVAL, ACCOUNT, RISK = cfg["eval_name"], cfg["account"], cfg["risk"]
    rule = EVALS[EVAL]

    # Fresh bars (incremental fetch); on failure load_ohlcv still returns cache.
    df = add_indicators(load_ohlcv(months=2, timeframe=tf))
    if df is None or len(df) < 61:
        return {"error": "not enough bars"}

    tf_ms = _tf_ms(tf)
    now = datetime.datetime.now(datetime.timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    i = len(df) - 1
    last_ms = int(df.index[-1].value // 1_000_000)
    if last_ms + tf_ms > now_ms:    # drop a still-forming last bar if present
        i -= 1
    ts = df.index[i]
    bar_ms = int(ts.value // 1_000_000)

    price = float(df["close"].iloc[i])
    e21, e50 = float(df["ema21"].iloc[i]), float(df["ema50"].iloc[i])
    up, down = e21 > e50, e21 < e50
    d_close = df["daily_close"].iloc[i]
    d_ema50 = df["daily_ema50"].iloc[i]
    dbull = bool(not pd.isna(d_ema50) and d_close > d_ema50)
    dbear = bool(not pd.isna(d_ema50) and d_close < d_ema50)
    rsi = None if pd.isna(df["rsi14"].iloc[i]) else round(float(df["rsi14"].iloc[i]), 1)
    rsi_prv = None if pd.isna(df["rsi14"].iloc[i - 1]) else round(float(df["rsi14"].iloc[i - 1]), 1)
    hour = int(ts.hour)
    is_asian = hour in (0, 4)

    direction = strat["signal_fn"](df, i, params)   # "long"/"short"/None
    shown = direction or ("long" if up else "short" if down else "long")

    # ── prop-legal sizing ─────────────────────────────────────────────────────
    stop_pct = float(params.get("stop_pct", 1.0))
    tp_pct = float(params.get("tp_pct", 4.0))
    fee_rt = rule.get("commission_per_side", 0.0004)
    lev, actual_risk = _legal_leverage(stop_pct, RISK, rule["max_leverage"])
    risk_usd = ACCOUNT * RISK / 100.0
    notional = risk_usd / (stop_pct / 100.0)
    units = notional / price if price else None
    fee_usd = notional * fee_rt * 2
    win_usd = notional * (tp_pct / 100.0) - fee_usd
    loss_usd = risk_usd + fee_usd

    def plan(long_: bool):
        return {
            "entry": round(price, 1),
            "stop": round(price * (1 - stop_pct / 100) if long_ else price * (1 + stop_pct / 100), 1),
            "target": round(price * (1 + tp_pct / 100) if long_ else price * (1 - tp_pct / 100), 1),
            "sl_pct": stop_pct, "tp_pct": tp_pct, "rr": round(tp_pct / stop_pct, 2),
        }

    # ── trade assumptions (everything needed to actually place the order) ──────
    atr = df["atr14"].iloc[i]
    atr = None if pd.isna(atr) else float(atr)
    mm_rate = 0.005   # maintenance-margin assumption (Kraken BTC perp ~0.5%, adjustable on the desk)
    rt_fee = fee_rt * 2

    def _breakeven(long_):
        return round(price * (1 + rt_fee) if long_ else price * (1 - rt_fee), 1)

    def _liq(long_, L):
        # isolated-margin liquidation; below ~1x you can't be liquidated (stop hits first)
        if not L or L <= 1:
            return None
        v = price * (1 - 1 / L + mm_rate) if long_ else price * (1 + 1 / L - mm_rate)
        return round(v, 1) if v > 0 else None

    assumptions = {
        "atr": round(atr, 1) if atr else None,
        "atr_pct": round(atr / price * 100, 2) if atr else None,
        "range_low": round(price - atr, 1) if atr else None,
        "range_high": round(price + atr, 1) if atr else None,
        "mm_rate_pct": round(mm_rate * 100, 2),
        "rt_fee_pct": round(rt_fee * 100, 3),
        "margin_usd": round(notional / lev, 2) if lev else None,
        "long": {"entry": round(price, 1), "breakeven": _breakeven(True),
                 "stop": plan(True)["stop"], "target": plan(True)["target"],
                 "liq": _liq(True, lev)},
        "short": {"entry": round(price, 1), "breakeven": _breakeven(False),
                  "stop": plan(False)["stop"], "target": plan(False)["target"],
                  "liq": _liq(False, lev)},
    }

    # Asian-session framing only describes the ASIAN_* family. For any other
    # strategy the hour gate and the hero's condition rows are meaningless, so we
    # omit them rather than render a checklist that belongs to a different setup.
    asian_family = strategy.startswith("ASIAN_")
    nxt = _next_asian_close(now)
    return {
        "strategy": strategy, "eval": EVAL, "tf": tf,
        "asian_family": asian_family,
        "bar_ts": ts.isoformat(),
        "bar_age_min": max(0, int((now_ms - (bar_ms + tf_ms)) / 60000)),
        "stale_after_min": int(tf_ms / 60000 * 1.25),
        "close": round(price, 1),
        "account": ACCOUNT, "risk_pct": RISK,
        "is_asian": is_asian, "hour": hour,
        "next_asian_iso": nxt.isoformat() if asian_family else None,
        "next_asian_in_min": int((nxt - now).total_seconds() / 60) if asian_family else None,
        "direction": direction, "shown_dir": shown,
        "trend": "up" if up else "down" if down else "flat",
        "verdict": "enter" if direction else "stand_down",
        # why it stood down, in the strategy's own terms — so silence is legible
        "stand_down_reason": None if direction else _stand_down_reason(
            strategy, asian_family, is_asian, up, down, dbull, dbear, rsi, rsi_prv,
            float(df["daily_ema50"].iloc[i]) if not pd.isna(df["daily_ema50"].iloc[i]) else None),
        "context": {"rsi": rsi, "rsi_prv": rsi_prv, "up4h": up, "down4h": down,
                    "daily_bull": dbull, "daily_bear": dbear, "hour": hour},
        "checklist": _checklist(is_asian, up, down, dbull, dbear, rsi, rsi_prv) if asian_family else None,
        "sizing": {
            "leverage": round(lev, 2), "actual_risk_pct": round(actual_risk, 2),
            "risk_usd": round(risk_usd, 2), "notional": round(notional, 2),
            "units": round(units, 5) if units else None,
            "win_usd": round(win_usd, 2), "loss_usd": round(loss_usd, 2),
            "fee_rt": fee_rt,
        },
        "assumptions": assumptions,
        "plan": {"long": plan(True), "short": plan(False)},
    }


# ── page ──────────────────────────────────────────────────────────────────────
RIGHT = '<div class="live"><span class="dot" id="dot"></span><span id="livetxt">live</span></div>'

BODY = r"""
<div id="body"><div class="skeleton">reading prop hero state…</div></div>
<div class="foot">
  Live read of the hero <b>ASIAN_RSI_DIP_v1</b> on the latest closed 4H bar. It only
  fires on Asian-session closes (00 / 04 UTC). ENTER = the rule triggered this bar —
  size it at the locked prop risk and place it on Kraken yourself. Refreshes every 60s ·
  <a href="#" id="refresh">refresh now</a>
</div>
<div class="toast" id="toast"></div>
"""

SCRIPT = r"""
const $ = id => document.getElementById(id);
const VLAB = {long:"LONG", short:"SHORT"}, ARROW = {long:"▲", short:"▼"};
let RISKPCT = null, MMPCT = null;
function money(n){ return (n==null)?'—':Number(n).toLocaleString(undefined,{maximumFractionDigits:0}); }
function chip(l,v,c){ return `<div class="chip ${c||''}">${l} <b>${v}</b></div>`; }
function secHead(id,t){ return `<div class="sect" id="h-${id}" onclick="tog('${id}')"><span class="caret">▾</span><span class="ttl">${t}</span><span class="line"></span></div>`; }
function tog(id){ $('h-'+id).classList.toggle('closed'); $('s-'+id).classList.toggle('closed'); }
function fmtClock(min){ if(min<60) return min+'m'; const h=Math.floor(min/60); return h+'h '+(min%60)+'m'; }
// Bangkok = UTC+7, no DST. Show both so the UTC bar times aren't a mental-math tax.
function bkk(iso){ const d=new Date(iso.endsWith('Z')||iso.includes('+')?iso:iso+'Z'); return new Date(d.getTime()+7*3600000).toISOString().slice(11,16); }

function render(d){
  if(d.error){ $('body').innerHTML = `<div class="skeleton" style="color:var(--amber)">${d.error}</div>`; return; }
  const stale = d.bar_age_min > 300;            // 4h bar → stale after ~5h
  $('dot').className = 'dot' + (stale?' stale':'');
  $('livetxt').textContent = stale ? 'stale' : 'live';
  const dir = d.shown_dir, enter = d.verdict === 'enter';
  const p = d.plan[dir], s = d.sizing;

  let h = `<div class="tape">
    <div class="px">$${d.close.toLocaleString()}<span class="c"> BTC</span></div>
    <div class="meta">
      4H bar <b>${d.bar_ts.slice(11,16)}</b> UTC · <b>${bkk(d.bar_ts)}</b> BKK<br>
      <span class="${stale?'stale':''}">${stale?'⚠ stale · ':''}closed <b>${d.bar_age_min}m</b> ago</span><br>
      eval wallet <b>$${d.account.toLocaleString()}</b> · risk <b>${d.risk_pct}%</b>
    </div>
  </div>`;

  // help
  h += `<div class="sect closed" id="h-help" onclick="tog('help')"><span class="caret">▾</span><span class="ttl">❔ how to read this prop desk</span><span class="line"></span></div>`
    + `<div class="sec-body closed" id="s-help"><div class="help-body">`
    + `<h4>what this is</h4>The live trigger for your <b>prop eval</b> hero, ASIAN_RSI_DIP_v1 — not the eval math (that's <a href="/prop">Goals</a>). It answers: <b>did the rule fire on the bar that just closed?</b>`
    + `<h4>why it's usually STAND DOWN</h4>The hero only fires on the <b>00:00 / 04:00 UTC</b> 4H closes (Asian session). Outside those two bars it can't trigger — the countdown shows the next window.`
    + `<h4>sizing</h4>Locked to the prop plan: <b>${d.risk_pct}% of $${d.account.toLocaleString()}</b> at a ${p.sl_pct}% stop → legal leverage ${s.leverage}x (firm cap 5x). A full stop loses ~$${money(s.loss_usd)}.`
    + `<h4>you place it</h4>LENS is read-only. Execute on Kraken; sync pulls the fill back.`
    + `</div></div>`;

  // gauge
  const gcls = enter ? 'enter' : 'stand_down';
  const sub = enter
    ? 'the hero fired this bar — real prop signal'
    : (d.is_asian ? 'Asian bar closed but the rule did not trigger' : `not an Asian bar — next window in ${fmtClock(d.next_asian_in_min)}`);
  h += `<div class="gauge ${gcls}">
    <div class="g-top">
      <span class="g-dir ${dir}"><span class="arrow">${ARROW[dir]}</span> ${VLAB[dir]}</span>
      <span class="g-setup">ASIAN_RSI_DIP</span>
    </div>
    <div class="verdict">${enter?'ENTER':'STAND DOWN'}</div>
    <div class="verdict-sub">${sub}<br><span style="color:var(--faint)">4H bar closed ${d.bar_ts.slice(11,16)} UTC (${bkk(d.bar_ts)} BKK) · ${d.bar_age_min}m ago · trend ${d.trend}</span></div>`;

  // ticket (reference when not ENTER)
  h += `<div class="ticket ${enter?'':'dim'}">
    ${enter?'':'<div class="ticket-ref">reference only — no trigger this bar. if it fires, this is the shape:</div>'}
    <div class="tg">
      <div class="cell"><div class="k">entry</div><div class="v">${money(p.entry)}</div></div>
      <div class="cell"><div class="k">R : R</div><div class="v">${p.rr}<span class="sub" style="display:inline"> reward/risk</span></div></div>
      <div class="cell"><div class="k">stop</div><div class="v r">${money(p.stop)}</div><div class="sub">−${p.sl_pct}% · ${s.leverage}x</div></div>
      <div class="cell"><div class="k">target</div><div class="v g">${money(p.target)}</div><div class="sub">+${p.tp_pct}%</div></div>
    </div>
    <div class="sizer"><label>risk %</label>
      <input type="number" id="riskpct" value="${RISKPCT ?? d.risk_pct}" step="0.1" inputmode="decimal">
      <label style="margin-left:4px">MM %</label>
      <input type="number" id="mmpct" value="${MMPCT ?? d.assumptions.mm_rate_pct}" step="0.1" inputmode="decimal" style="width:60px">
      <span class="size-out" id="size-out"></span></div>
    <div class="outcome" id="out"></div>
    <div class="exit-note">Locked prop sizing. Full stop ≈ <b>−$${money(s.loss_usd)}</b> (${d.risk_pct}% of wallet). Target ≈ <b>+$${money(s.win_usd)}</b>. Walls: 3% static DD / 3% daily — see <a href="/survival">Survival</a>.</div>
  </div></div>`;

  // context chips
  const c = d.context;
  h += secHead('ctx','context — why') + `<div class="sec-body" id="s-ctx"><div class="chips">`
    + chip('RSI now', c.rsi==null?'—':c.rsi, (c.rsi!=null&&c.rsi<40)?'good':(c.rsi!=null&&c.rsi>60)?'bad':'')
    + chip('RSI prev', c.rsi_prv==null?'—':c.rsi_prv)
    + chip('4H trend', d.trend, d.trend==='up'?'good':d.trend==='down'?'bad':'')
    + chip('daily', c.daily_bull?'bull':c.daily_bear?'bear':'flat', c.daily_bull?'good':c.daily_bear?'bad':'')
    + chip('bar hour', c.hour+':00 UTC · '+((c.hour+7)%24)+':00 BKK', d.is_asian?'good':'')
    + `</div></div>`;

  // checklist for shown direction
  const cl = d.checklist[dir];
  h += secHead('chk',`${VLAB[dir]} checklist`) + `<div class="sec-body" id="s-chk"><div class="scard ${enter?'active':''}">`
    + cl.map(x=>`<div class="cond ${x.ok?'ok':'no'}"><span class="tk">${x.ok?'✓':'·'}</span>${x.label}</div>`).join('')
    + `<div class="sflag ${enter?'go':'veto'}">${enter?'● LIVE — hero fired':'— waiting for all conditions'}</div>`
    + `</div></div>`;

  // trade assumptions — everything to place the order
  h += secHead('asm','📐 trade assumptions') + `<div class="sec-body" id="s-asm"><div id="asm-body"></div></div>`;

  // next window
  h += `<div class="panel" style="margin-top:14px"><div class="kv"><span class="k">next Asian close</span><span class="v">${d.next_asian_iso.slice(11,16)} UTC (${bkk(d.next_asian_iso)} BKK) · in ${fmtClock(d.next_asian_in_min)}</span></div></div>`;

  $('body').innerHTML = h;
  wireSizer(d);
  renderAssumptions(d);
  $('mmpct') && $('mmpct').addEventListener('input', ()=>{ MMPCT = parseFloat($('mmpct').value)||MMPCT; renderAssumptions(d); });
}

function renderAssumptions(d){
  const el = $('asm-body'); if(!el) return;
  const rp = parseFloat($('riskpct') && $('riskpct').value) || d.risk_pct;
  const mm = (parseFloat($('mmpct') && $('mmpct').value) || d.assumptions.mm_rate_pct) / 100;
  const fee = d.sizing.fee_rt || 0.0004, price = d.close, a = d.assumptions;
  function calc(dir){
    const long_ = dir==='long', p = d.plan[dir];
    const lev = Math.min(rp/p.sl_pct, 5);
    const be = long_ ? price*(1+2*fee) : price*(1-2*fee);
    let liq = null;
    if(lev > 1){ liq = long_ ? price*(1-1/lev+mm) : price*(1+1/lev-mm); if(long_ && liq<=0) liq = null; }
    const risk = d.account*rp/100, notional = risk/(p.sl_pct/100);
    return {p, lev, be, liq, risk, notional, margin:notional/lev, size:notional/price};
  }
  const L = calc('long'), S = calc('short');
  const liqCell = v => v ? ('$'+money(v)) : '<span class="dim">n/a &lt;1x</span>';
  const row = (lbl,lv,sv,cls)=>`<tr><td class="dim">${lbl}</td><td class="${cls||''}">${lv}</td><td class="${cls||''}">${sv}</td></tr>`;
  el.innerHTML =
    `<div class="panel" style="margin-bottom:10px">
      <div class="kv"><span class="k">current price</span><span class="v">$${money(price)}</span></div>
      <div class="kv"><span class="k">expected range · 1 ATR (4H)</span><span class="v">${a.range_low?('$'+money(a.range_low)+' – $'+money(a.range_high)+' <span class="dim">±'+a.atr_pct+'%</span>'):'—'}</span></div>
      <div class="kv"><span class="k">expected hold · backtest</span><span class="v">~1 day <span class="dim">wins 1.3d · losses 0.9d · max 3d · ~1 swap</span></span></div>
      <div class="kv"><span class="k">notional · margin</span><span class="v">$${money(L.notional)} · $${money(L.margin)} <span class="dim">@ ${L.lev.toFixed(2)}x</span></span></div>
      <div class="kv"><span class="k">size · risk</span><span class="v">${L.size.toFixed(4)} ₿ · $${money(L.risk)} <span class="dim">(${rp}%)</span></span></div>
    </div>
    <div class="sb-wrap"><table class="sb">
      <tr><th>level</th><th>LONG</th><th>SHORT</th></tr>
      ${row('entry', money(L.p.entry), money(S.p.entry))}
      ${row('breakeven · after '+a.rt_fee_pct+'% fee', money(L.be), money(S.be), 'a')}
      ${row('target · TP +'+L.p.tp_pct+'%', money(L.p.target), money(S.p.target), 'g')}
      ${row('stop · SL −'+L.p.sl_pct+'%', money(L.p.stop), money(S.p.stop), 'r')}
      ${row('est. liquidation', liqCell(L.liq), liqCell(S.liq))}
    </table></div>
    <div class="outcome" style="margin-top:8px">MM ${(mm*100).toFixed(2)}% · at ${L.lev.toFixed(2)}x the <b>stop hits long before liquidation</b> — liquidation only bites if you push risk toward the 5x cap.</div>`;
}

function wireSizer(d){
  const inp = $('riskpct'); if(!inp) return;
  const p = d.plan[d.shown_dir];
  const upd = ()=>{
    const rp = parseFloat(inp.value)||0; RISKPCT = rp;
    const lev = Math.min(rp/p.sl_pct, 5);
    const risk = d.account*rp/100, notional = risk/(p.sl_pct/100), units = notional/d.close;
    const fee = notional*(d.sizing.fee_rt||0.0004)*2;
    const win = notional*(p.tp_pct/100)-fee, loss = risk+fee;
    $('size-out').innerHTML = `→ $${money(notional)} <span style="color:var(--dim)">(${units.toFixed(4)} BTC · ${lev.toFixed(2)}x · cap 5x)</span>`;
    $('out').innerHTML = `target <b class="g">+$${money(win)}</b> · stop <b class="r">−$${money(loss)}</b> <span style="color:var(--dim)">· ${(loss/d.account*100).toFixed(2)}% of wallet</span>`;
    renderAssumptions(d);
  };
  inp.addEventListener('input',upd); upd();
}

async function load(){
  try{
    const r = await fetch('/api/prop/desk');
    render(await r.json());
  }catch(e){
    $('body').innerHTML = '<div class="skeleton" style="color:var(--amber)">failed to load — candle fetch offline?</div>';
  }
}
$('refresh').addEventListener('click', e=>{e.preventDefault(); load();});
load();
setInterval(load, 60000);
"""

PROP_DESK_HTML = shell("/prop-desk", "Live", BODY, script=SCRIPT, right=RIGHT, meta="can I enter?")
