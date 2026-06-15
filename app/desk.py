"""LENS /desk — live entry checklist. One screen that answers: can I enter RIGHT NOW?

Renders desk_state() from app.setups: per-direction verdict (ENTER / BLOCKED /
STAND DOWN), the trade plan when clean, live S1–S5 condition checklists, active
vetoes, and the realized per-setup scoreboard. Styled to match the main LENS
pages (same :root vars + topbar as the landing page).
"""

DESK_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LENS // Desk</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#08080a;--s1:#0f0f12;--s2:#141418;
  --b1:#1e1e26;--b2:#28282e;--b3:#36363e;
  --t1:#eaeaee;--t2:#72728a;--t3:#3c3c48;--t4:#26262e;
  --ac:#5b8ef7;--adim:#121c36;
  --gr:#38c068;--re:#e8445a;--am:#e8a23d;
  --mono:'SF Mono',ui-monospace,'Cascadia Code',monospace;
  --ui:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
}
body{font-family:var(--ui);font-size:13px;line-height:1.5;background:var(--bg);color:var(--t1);-webkit-font-smoothing:antialiased}
.app{max-width:1180px;margin:0 auto;padding:0 22px 60px}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:18px 0 16px;border-bottom:1px solid var(--b1);margin-bottom:22px}
.brand{display:flex;align-items:baseline;gap:11px}
.brand-name{font-family:var(--mono);font-size:16px;font-weight:700;color:#fff;letter-spacing:.12em}
.brand-name b{color:var(--ac)}
.brand-sep{color:var(--t3);margin:0 2px}
.brand-page{font-family:var(--mono);font-size:14px;font-weight:600;color:var(--t2);letter-spacing:.08em}
.brand-meta{font-family:var(--mono);font-size:10px;color:var(--t3)}
.topnav{display:flex;gap:2px;flex-wrap:wrap}
.topnav a{font-size:12px;color:var(--t2);text-decoration:none;padding:5px 10px;border-radius:5px;transition:all .12s}
.topnav a:hover{color:var(--t1);background:var(--s2);text-decoration:none}
.topnav a.cur{color:var(--ac);background:var(--adim)}

.statusline{display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;font-family:var(--mono);font-size:11px;color:var(--t2);margin-bottom:18px}
.statusline .px{font-size:20px;color:var(--t1);font-weight:700}
.statusline .stale{color:var(--am)}

.verdicts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}
@media(max-width:760px){.verdicts{grid-template-columns:1fr}}
.vcard{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:16px 18px}
.vcard.enter{border-color:var(--gr);box-shadow:0 0 24px rgba(56,192,104,.12)}
.vcard.blocked,.vcard.veto{border-color:rgba(232,68,90,.4)}
.vhead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.vdir{font-family:var(--mono);font-size:12px;letter-spacing:.14em;color:var(--t2)}
.vstate{font-family:var(--mono);font-size:15px;font-weight:700}
.vstate.enter{color:var(--gr)}.vstate.veto,.vstate.blocked{color:var(--re)}.vstate.stand{color:var(--t3)}
.vreasons{font-size:11.5px;color:var(--t2)}
.vreasons li{margin-left:16px;margin-top:2px}

.plan{margin-top:12px;border-top:1px solid var(--b1);padding-top:12px}
.plan-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}
.pcell{background:var(--s2);border:1px solid var(--b1);border-radius:6px;padding:7px 9px}
.pcell .k{font-family:var(--mono);font-size:9px;color:var(--t2);letter-spacing:.1em;text-transform:uppercase}
.pcell .v{font-family:var(--mono);font-size:14px;font-weight:600}
.pcell .v.gr{color:var(--gr)}.pcell .v.re{color:var(--re)}
.sizer{display:flex;gap:10px;align-items:center;font-family:var(--mono);font-size:11px;color:var(--t2);flex-wrap:wrap}
.sizer input{width:74px;background:var(--bg);border:1px solid var(--b2);border-radius:5px;color:var(--t1);padding:4px 7px;font-family:var(--mono);font-size:12px}
.exit-note{margin-top:8px;font-size:11px;color:var(--am)}
.plan.dim{opacity:.45}
.plan-ref{font-family:var(--mono);font-size:10px;color:var(--t2);margin-bottom:8px}
.outcome{margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--t2)}
.outcome .gr-t{color:var(--gr)}.outcome .re-t{color:var(--re)}

.ctxrow{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}
.chip{background:var(--s1);border:1px solid var(--b1);border-radius:6px;padding:6px 11px;font-family:var(--mono);font-size:11px;color:var(--t2)}
.chip b{color:var(--t1);font-weight:600}
.chip.good{border-color:rgba(56,192,104,.45)}.chip.good b{color:var(--gr)}
.chip.bad{border-color:rgba(232,68,90,.45)}.chip.bad b{color:var(--re)}

h2{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--t2);margin:26px 0 12px}
.setups{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.scard{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:13px 15px}
.scard.active{border-color:var(--gr)}
.scard.vetoed{border-color:var(--am)}
.shead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px}
.sid{font-family:var(--mono);font-weight:700;font-size:13px}
.sid .dir-long{color:var(--gr)}.sid .dir-short{color:var(--re)}
.swr{font-family:var(--mono);font-size:10px;color:var(--t2)}
.sname{font-size:12px;color:var(--t2);margin-bottom:8px}
.cond{display:flex;gap:8px;font-family:var(--mono);font-size:11px;padding:2px 0}
.cond .tick{width:14px}
.cond.ok{color:var(--t1)}.cond.ok .tick{color:var(--gr)}
.cond.no{color:var(--t3)}.cond.no .tick{color:var(--t3)}
.sflag{margin-top:8px;font-family:var(--mono);font-size:10px}
.sflag.go{color:var(--gr)}.sflag.veto{color:var(--am)}

table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:11.5px}
th{color:var(--t2);text-align:left;font-weight:500;padding:6px 10px;border-bottom:1px solid var(--b1);letter-spacing:.06em}
td{padding:6px 10px;border-bottom:1px solid var(--t4);color:var(--t1)}
td.gr{color:var(--gr)}td.re{color:var(--re)}td.mut{color:var(--t2)}
.sb-wrap{background:var(--s1);border:1px solid var(--b1);border-radius:10px;padding:6px 8px;overflow-x:auto}
.foot{margin-top:22px;font-size:11px;color:var(--t3)}
</style>
</head>
<body>
<div class="app">
  <div class="topbar">
    <div class="brand">
      <div class="brand-name">LE<b>N</b>S</div>
      <span class="brand-sep">·</span>
      <div class="brand-page">Desk</div>
      <div class="brand-meta">can I enter right now?</div>
    </div>
    <nav class="topnav">
      <a href="/">Dashboard</a>
      <a href="/desk" class="cur">Desk</a>
      <a href="/signals">Signals</a>
      <a href="/projection">Projection</a>
      <a href="/backtest">Backtest</a>
      <a href="/review">Review</a>
      <a href="/montecarlo">Monte Carlo</a>
      <a href="/prop">Prop</a>
    </nav>
  </div>

  <div class="statusline" id="statusline">loading market state…</div>
  <div class="verdicts" id="verdicts"></div>
  <div class="ctxrow" id="ctxrow"></div>

  <h2>Setup checklists — live</h2>
  <div class="setups" id="setups"></div>

  <h2>Realized scoreboard (auto-tagged trades)</h2>
  <div class="sb-wrap"><table id="sb"></table></div>

  <div class="foot">
    Patterns are mechanical coin-flips on their own — the realized win rates came from
    <i>your selection inside these contexts</i> plus fast exits. ENTER means "the context
    where you historically win is live", not "guaranteed trade".
    Refreshes every 60s · <a href="#" id="refresh">refresh now</a>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const VLAB = {long:"LONG", short:"SHORT"};

function chip(label, val, cls) {
  return `<div class="chip ${cls||''}">${label} <b>${val}</b></div>`;
}

function render(d) {
  const stale = d.bar_age_min > 130;
  $('statusline').innerHTML =
    `<span class="px">$${d.close.toLocaleString()}</span>` +
    `<span>BTC · 1H bar ${d.bar_ts.slice(11,16)} UTC</span>` +
    `<span class="${stale?'stale':''}">${stale?'⚠ candle data stale — ':''}bar closed ${d.bar_age_min} min ago</span>` +
    (d.balance ? `<span>account €${d.balance.toFixed(0)}</span>` : '');

  // verdict cards
  let vh = '';
  for (const dir of ['long','short']) {
    const v = d.verdicts[dir];
    const stateTxt = {enter:'ENTER — '+v.setups.join(' + '),
                      blocked:'BLOCKED — setup live but vetoed',
                      veto:'NO — veto active',
                      stand_down:'STAND DOWN — no setup'}[v.state];
    const stateCls = {enter:'enter',blocked:'blocked',veto:'veto',stand_down:'stand'}[v.state];
    let body = '';
    if (v.vetoes.length)
      body += `<ul class="vreasons">` + v.vetoes.map(x=>`<li>${x}</li>`).join('') + `</ul>`;
    if (v.plan) {
      const p = v.plan;
      const live = v.state === 'enter';
      body += `<div class="plan ${live?'':'dim'}">
        ${live?'':'<div class="plan-ref">reference only — context says NO. If price gets here clean, this is the shape:</div>'}
        <div class="plan-grid">
        <div class="pcell"><div class="k">entry</div><div class="v">$${p.entry.toLocaleString()}</div></div>
        <div class="pcell"><div class="k">stop −${p.sl_pct}%</div><div class="v re">$${p.stop.toLocaleString()}</div></div>
        <div class="pcell"><div class="k">target +${p.tp_pct}%</div><div class="v gr">$${p.target.toLocaleString()}</div></div>
        <div class="pcell"><div class="k">R:R</div><div class="v">${p.rr}</div></div></div>
        <div class="sizer">risk € <input type="number" id="risk-${dir}" value="${d.balance?Math.max(1,Math.round(d.balance*0.1)):10}">
          <span id="size-${dir}"></span></div>
        <div class="outcome" id="outcome-${dir}"></div>
        <div class="exit-note">⏱ winners resolve in 2–8h (50% WR, +€1,552). Trades closed &lt;2h ran 34–35% WR (−€747). Take +0.5–0.9% when it's there — but don't panic-scalp out in minutes.</div>
      </div>`;
    }
    vh += `<div class="vcard ${stateCls}"><div class="vhead">
      <span class="vdir">${VLAB[dir]}</span>
      <span class="vstate ${stateCls}">${stateTxt}</span></div>${body}</div>`;
  }
  $('verdicts').innerHTML = vh;
  for (const dir of ['long','short']) {
    const inp = $('risk-'+dir);
    if (!inp) continue;
    const upd = () => {
      const risk = parseFloat(inp.value)||0;
      const p = d.verdicts[dir].plan;
      const notional = risk / (p.sl_pct/100);
      const btc = notional / d.close;
      const fee = notional * 0.0004;                      // maker round trip
      const win  = notional * (p.tp_pct/100) - fee;
      const earlyWin = notional * 0.007 - fee;            // realistic +0.7% exit
      const loss = risk + fee;
      $('size-'+dir).textContent =
        `→ position €${notional.toFixed(0)} (${btc.toFixed(4)} BTC) · €${(notional/10).toFixed(0)} margin @10x`;
      $('outcome-'+dir).innerHTML =
        `if target: <b class="gr-t">+€${win.toFixed(2)}</b> · if +0.7% early exit: <b class="gr-t">+€${earlyWin.toFixed(2)}</b> · if stopped: <b class="re-t">−€${loss.toFixed(2)}</b>` +
        (d.balance ? ` · stop = ${(loss/d.balance*100).toFixed(1)}% of account` : '');
    };
    inp.addEventListener('input', upd); upd();
  }

  // context chips
  const c = d.context;
  const kzName = {london_kz:'London 07–10',ny_am_kz:'NY AM 13–16 ★',ny_pm_kz:'NY PM 18–21 ☠',none:'—'}[c.killzone];
  $('ctxrow').innerHTML =
    chip('RSI', c.rsi===null?'—':c.rsi+' '+(c.rsi_zone==='dead'?'☠':c.rsi_zone), c.rsi_zone==='dead'?'bad':(c.rsi_zone?'good':'')) +
    chip('killzone', kzName, c.killzone==='ny_am_kz'?'good':c.killzone==='ny_pm_kz'?'bad':'') +
    chip('7d range', c.pd_zone||'—') +
    chip('sweep', c.sweep?c.sweep+' taken':'none') +
    chip('prior-day raid', c.pd_raid||'none') +
    chip('displacement', c.displacement||'—') +
    chip('EMA21 slope', c.slope||'flat') +
    chip('bear streak ×3', c.bear_streak3?'yes':'no');

  // setup cards
  $('setups').innerHTML = d.checklists.map(s => {
    const cls = s.active ? (s.vetoed ? 'vetoed' : 'active') : '';
    const flag = s.active ? (s.vetoed
        ? `<div class="sflag veto">▲ conditions met but VETOED — stand down</div>`
        : `<div class="sflag go">● LIVE — context active now</div>`) : '';
    return `<div class="scard ${cls}"><div class="shead">
      <span class="sid">${s.id} <span class="dir-${s.direction}">${s.direction.toUpperCase()}</span></span>
      <span class="swr">${s.wr}</span></div>
      <div class="sname">${s.name}</div>` +
      s.conds.map(x=>`<div class="cond ${x.ok?'ok':'no'}"><span class="tick">${x.ok?'✓':'·'}</span>${x.label}</div>`).join('') +
      flag + `</div>`;
  }).join('');

  // scoreboard
  const rows = Object.entries(d.scoreboard);
  $('sb').innerHTML = `<tr><th>tag</th><th>n</th><th>win rate</th><th>PnL €</th><th>exp €/trade</th><th>halves</th></tr>` +
    rows.map(([k,s]) => `<tr>
      <td class="${k==='VETO'?'re':k==='NONE'?'mut':''}">${k}</td><td>${s.n}</td>
      <td class="${s.wr>=50?'gr':s.wr<40?'re':''}">${s.wr??'—'}%</td>
      <td class="${s.pnl>=0?'gr':'re'}">${s.pnl>=0?'+':''}${s.pnl.toFixed(0)}</td>
      <td>${s.exp??'—'}</td><td class="mut">${(s.wr_halves||[]).join(' / ')}</td></tr>`).join('');
}

async function load() {
  try {
    const r = await fetch('/api/setups/state');
    render(await r.json());
  } catch (e) {
    $('statusline').innerHTML = '<span class="stale">failed to load state — is the candle fetch offline?</span>';
  }
}
$('refresh').addEventListener('click', e => { e.preventDefault(); load(); });
load();
setInterval(load, 60000);
</script>
</body>
</html>"""
