"""LENS /edge — retired 2026-09-05, folded into /analytics as a "Research"
area (see analytics_page._research_section). /edge itself now just 301s to
/analytics (main.py LEGACY_ROUTES); render_page() below is no longer wired to
a route and is dead code kept only because analytics_page.py still imports
its building blocks (_CSS, _BOARD_CSS, _LIVE, SCRIPT, _MODE_JS, _board) —
don't call render_page() from a route again without re-reading why it went.

#past     — realised performance per setup family from YOUR live trades
            (auto-tagged on sync, verdict from expectancy · WR · sample).
#board    — the coded strategies replayed over the full candle history,
            hedge/prop toggle (was /strategy-hedge + /strategy; both redirect
            to /analytics#board now).
#backtest — the interactive runner + SL×TP sweep + build-your-own
            (was /backtest; redirects to /analytics#backtest now).

Live results, backtest ranks and the runner are different measurements of the
same question — "which setups pay?" — so they live on one page (/analytics).
"""

from .theme import shell

_CSS = """
<style>
.ed-sub{color:var(--dim);font-size:12px;margin:2px 0 14px}
.ed-anchors{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 18px}
.ed-anchors a{font-family:var(--mono);font-size:11px;color:var(--dim);text-decoration:none;padding:4px 12px;border:1px solid var(--line);border-radius:999px;background:var(--panel)}
.ed-anchors a:hover{color:var(--ink);border-color:var(--line2)}
.ed-h{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:26px 0 4px;scroll-margin-top:70px}
.ed-h:first-of-type{margin-top:0}
.ed-hs{color:var(--dim);font-size:12px;margin-bottom:12px}
.ed-mode{display:flex;gap:5px;margin:0 0 10px}
.ed-mode button{padding:3px 14px;border:1px solid var(--line2);background:transparent;color:var(--dim);font-size:11px;border-radius:4px;cursor:pointer;font-family:var(--mono)}
.ed-mode button.on{border-color:var(--accent);background:var(--accent);color:var(--bg);font-weight:700}
.ed-tbl{width:100%;border-collapse:collapse;font-size:13px}
.ed-tbl th{text-align:right;color:var(--dim);font-weight:600;padding:7px 10px;border-bottom:1px solid var(--line);text-transform:uppercase;font-size:9px;letter-spacing:.05em}
.ed-tbl th:first-child,.ed-tbl td:first-child{text-align:left}
.ed-tbl td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.ed-tbl tr.main td{font-weight:600}
.ed-gchip{display:inline-block;font-size:10px;padding:1px 6px;margin:3px 5px 0 0;border:1px solid var(--line2);border-radius:4px;color:var(--dim)}
.g{color:var(--long)} .r{color:var(--short)} .amb{color:var(--amber)} .dim{color:var(--dim)}

/* ── #past — visual primitives, same vocabulary as /analytics's vz-* set ── */
.ed-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.ed-card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:11px 13px;display:flex;flex-direction:column;gap:7px;min-width:0}
.ed-card.armed{border-color:var(--long)}
.ed-lbl{font-size:9px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ed-track{position:relative;height:22px;border-radius:6px;background:var(--bg);border:1px solid var(--line);overflow:hidden}
.ed-fill{position:absolute;top:0;bottom:0;left:0;border-radius:5px 0 0 5px}
.ed-fill-lbl{position:absolute;inset:0;display:flex;align-items:center;justify-content:flex-end;padding:0 8px;font-family:var(--mono);font-size:11px;font-weight:700;color:var(--ink)}
.ed-tick{position:absolute;top:-1px;bottom:-1px;width:2px;background:var(--ink);opacity:.6}
.ed-div{position:relative;height:22px;background:var(--bg);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.ed-div .mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line2)}
.ed-div .seg{position:absolute;top:1px;bottom:1px;border-radius:3px}
.ed-cap{font-family:var(--mono);font-size:9.5px;color:var(--faint)}
.ed-badge{display:inline-block;font-family:var(--mono);font-weight:800;font-size:11px;letter-spacing:.06em;padding:3px 9px;border-radius:5px;border:1px solid currentColor}
.ed-dead summary{list-style:none;cursor:pointer;padding:9px 12px;font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;display:flex;align-items:center;gap:8px;user-select:none}
.ed-dead summary::-webkit-details-marker{display:none}
.ed-dead summary::before{content:'▸';color:var(--faint);font-size:10px;transition:transform .15s}
.ed-dead[open] summary::before{transform:rotate(90deg)}
.ed-dead{border:1px solid var(--line);border-radius:8px;background:var(--panel2);margin-top:4px}
.ed-dead-body{padding:0 12px 12px}
.ed-dead-row{display:grid;grid-template-columns:70px 1fr 90px;align-items:center;gap:8px;margin-bottom:5px;font-size:11px}
.ed-dead-row .lbl{font-family:var(--mono);color:var(--dim)}
.ed-dead-row .trk{position:relative;height:12px;background:var(--bg);border-radius:3px;overflow:hidden}
.ed-dead-row .trk .mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line2)}
.ed-dead-row .trk .seg{position:absolute;top:1px;bottom:1px;border-radius:2px}
.ed-dead-row .val{font-family:var(--mono);text-align:right;color:var(--dim)}
</style>
"""

_LIVE = """
<div id="edge-armed"></div>
<details class="ed-dead" id="edge-dead-wrap"><summary>Disarmed setups <span id="edge-dead-tag" class="ed-cap" style="margin-left:auto"></span></summary>
  <div class="ed-dead-body" id="edge-dead"></div>
</details>
"""

SCRIPT = r"""
const ARMED_SETUPS=new Set(['S1']);
function edgeFamily(tag){
  if(!tag) return '(untagged)';
  if(tag.startsWith('VETO:')) return 'VETO';
  if(tag.includes('|VETO:')) return tag.split('|')[0]+' (vetoed)';
  return tag;
}
function edgeIsArmed(k){ return ARMED_SETUPS.has(k.split(' ')[0]); }
function edgeVerdict(n,wr,exp){
  if(n<8)               return ['THIN','var(--dim)'];
  if(exp<=0)            return ['CUT','var(--short)'];
  if(exp>=10&&n>=12&&wr>=45) return ['SIZE-UP','var(--long)'];
  return ['KEEP','var(--amber)'];
}
function edgeQuery(k){
  return k==='(untagged)'?'__none__':k==='VETO'?'VETO:':k.endsWith(' (vetoed)')?k.split(' ')[0]+'|':k;
}
function render(trades){
  const g={};
  trades.filter(t=>t.pnl!=null).forEach(t=>{
    const k=edgeFamily(t.setup_tag);
    if(!g[k]) g[k]={n:0,wins:0,total:0};
    g[k].n++; if((t.pnl||0)>0)g[k].wins++; g[k].total+=t.pnl||0;
  });
  const rows=Object.entries(g).map(([k,d])=>{
    const exp=d.total/d.n, wr=d.wins/d.n*100;
    const [vl,vc]=edgeVerdict(d.n,wr,exp);
    return {k,d,exp,wr,vl,vc};
  }).sort((a,b)=>b.d.total-a.d.total);

  const armed=rows.filter(r=>edgeIsArmed(r.k));
  const dead=rows.filter(r=>!edgeIsArmed(r.k));

  document.getElementById('edge-armed').innerHTML=armed.length?('<div class="ed-row">'+armed.map(r=>{
    const {k,d,exp,wr,vl,vc}=r;
    const wrColor=wr>=50?'var(--long)':wr>=35?'var(--amber)':'var(--short)';
    const q=edgeQuery(k);
    return `<div class="ed-card armed" style="grid-column:span 2">`+
      `<div class="ed-lbl"><a href="/journal?setup=${encodeURIComponent(q)}" style="color:inherit;text-decoration:none" title="these trades in the journal →">${k} — live, armed</a> <span class="ed-badge" style="color:${vc}">${vl}</span></div>`+
      `<div class="ed-track"><div class="ed-fill" style="width:${Math.max(0,Math.min(100,wr))}%;background:${wrColor}"></div>`+
      `<div class="ed-fill-lbl">${wr.toFixed(0)}% WR</div></div>`+
      `<div class="ed-cap">n=${d.n} · avg ${exp>=0?'+':''}${exp.toFixed(0)}€/trade · total <span style="color:${d.total>=0?'var(--long)':'var(--short)'}">${d.total>=0?'+':''}${d.total.toFixed(0)}€</span></div>`+
      `</div>`;
  }).join('')+'</div>'):'<div class="ed-cap" style="margin-bottom:12px">No S1 trades yet.</div>';

  const deadMaxAbs=Math.max(1,...dead.map(r=>Math.abs(r.d.total)));
  document.getElementById('edge-dead-tag').textContent=dead.length+' family'+(dead.length===1?'':'ies')+' · proven losing / unranked, not worth reading row-by-row';
  document.getElementById('edge-dead').innerHTML=dead.map(r=>{
    const {k,d,exp,wr,vl,vc}=r;
    const w=deadMaxAbs>0?Math.min(50,Math.abs(d.total)/deadMaxAbs*50):0, pos=d.total>=0;
    const seg=pos?`left:50%;width:${w}%;background:var(--long)`:`right:50%;width:${w}%;background:var(--short)`;
    const q=edgeQuery(k);
    return `<div class="ed-dead-row"><a class="lbl" href="/journal?setup=${encodeURIComponent(q)}" style="text-decoration:none" title="these trades in the journal →">${k}</a>`+
      `<div class="trk"><div class="mid"></div><div class="seg" style="${seg}"></div></div>`+
      `<span class="val">${wr.toFixed(0)}%WR · n${d.n} · <b style="color:${vc}">${vl}</b></span></div>`;
  }).join('')||'<div class="ed-cap">Nothing to show.</div>';
}
fetch('/api/review/trades').then(r=>r.json()).then(render).catch(e=>{
  document.getElementById('edge-armed').innerHTML='<div class="r ed-cap">Load error: '+e.message+'</div>';});
"""


# _board/_r_cols/_BOARD_CSS were in prop_views.py (a leftover from when it was
# the only backtest-board page) despite rendering BOTH boards on /edge — moved
# here on the 2026-09-05 hedge/prop split, deleting prop_views.py would have
# taken the hedge board's renderer down with it. Purely a rendering helper:
# it just filters `results` by `mode` ("hedge" | "prop") and ranks a table —
# "prop" here labels the 4H/1H Asian-dip strategy FAMILY in the backtest
# candidate set, not the (now-deleted) prop-eval account tracking, so the
# HEDGE/PROP board toggle stays; it's two strategy families, not two books.
_BOARD_CSS = r"""<style>
.pv .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:18px}
.pv .prose{color:var(--dim);font-size:13.5px;line-height:1.65}
.pv .prose strong{color:var(--ink)}
.pv .green{color:var(--long)} .pv .red{color:var(--short)}

/* one row per strategy: rank + name, a bar sized by score (the "does it pay"
   read), then a strip of heat cells — one per R level, colored like the
   backtest SL×TP sweep — so the per-R detail survives without a numbers grid. */
.pv-row{display:grid;grid-template-columns:26px 1fr 96px;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}
.pv-row:last-child{border-bottom:none}
.pv-row.top .name{font-weight:700;color:var(--ink)}
.pv-rank{font-family:var(--mono);font-size:12px;color:var(--dim);text-align:right}
.pv-row.top .pv-rank{color:var(--long)}
.pv-main{min-width:0}
.pv-name{display:flex;align-items:baseline;gap:7px;font-size:12.5px;margin-bottom:5px;flex-wrap:wrap}
.pv-dir{font-family:var(--mono);font-size:9px;letter-spacing:.06em;padding:1px 6px;border-radius:3px;border:1px solid var(--line2);color:var(--dim)}
.pv-meta{font-family:var(--mono);font-size:10px;color:var(--faint)}
.pv-bar{position:relative;height:10px;background:var(--bg);border:1px solid var(--line);border-radius:5px;overflow:hidden;margin-bottom:5px}
.pv-bar>span{display:block;height:100%;border-radius:4px}
.pv-heat{display:flex;gap:2px}
.pv-heat i{flex:1 1 0;height:14px;border-radius:2px;min-width:8px}
.pv-best{font-family:var(--mono);font-size:11px;text-align:right;white-space:nowrap}
</style>"""


def _score_bar(score, max_score):
    """Score as a filled bar, 0..max across the ranked set — length answers
    'how much does this one pay' at a glance, the number is just the caption."""
    pct = max(0, min(100, score / max_score * 100)) if max_score > 0 else 0
    color = "var(--long)" if score > 0 else "var(--short)"
    return f'<div class="pv-bar"><span style="width:{pct:.1f}%;background:{color}"></span></div>'


def _r_heat(rows, r_levels):
    """One cell per R level, colored like the backtest SL×TP heatmap (green =
    profitable, red = not, opacity = magnitude) — the per-R breakdown without
    a row of numbers to read."""
    by_r = {row["r"]: row for row in rows}
    max_abs = max([abs(r["net"]) for r in rows] + [1])
    out = ""
    for R in r_levels:
        row = by_r.get(R)
        if not row:
            out += '<i style="background:var(--panel2)" title="no data"></i>'
            continue
        t = max(-1, min(1, row["net"] / max_abs))
        hue = 150 if t >= 0 else 5
        out += (f'<i style="background:hsla({hue},72%,45%,{0.15+0.6*abs(t):.2f})" '
                f'title="{R:g}R: {row["net"]:+.2f} net · {row["wr"]}% WR"></i>')
    return out


def _board(results, mode, r_levels):
    ranked = sorted([o for o in results if o["mode"] == mode and not o["thin"]],
                    key=lambda x: x["rank"])
    thin = [o for o in results if o["mode"] == mode and o["thin"]]
    max_score = max([o["score"] for o in ranked] + [1])
    body_rows = ""
    for o in ranked:
        top = " top" if o["top3"] else ""
        star = " ★" if o["top3"] else ""
        best = (f'<span class="green">{o["best_net"]:+.2f}R</span> @ {o["best_r"]:g}R'
                if o["best_net"] and o["best_net"] > 0
                else f'<span class="red">{o["best_net"]:+.2f}R</span>')
        body_rows += (
            f'<div class="pv-row{top}">'
            f'<div class="pv-rank">{o["rank"]}{star}</div>'
            f'<div class="pv-main">'
            f'<div class="pv-name"><span>{o["name"]}</span>'
            f'<span class="pv-dir">{o["dir"]}</span>'
            f'<span class="pv-meta">n={o["n"]} · stop {o["sl"]:.2f}% · score {o["score"]:.2f}</span></div>'
            f'{_score_bar(o["score"], max_score)}'
            f'<div class="pv-heat">{_r_heat(o["rows"], r_levels)}</div>'
            f'</div>'
            f'<div class="pv-best">{best}</div>'
            f'</div>')
    thin_note = ""
    if thin:
        thin_note = ('<div class="prose" style="margin-top:8px">thin (n&lt;40, not ranked): '
                     + ", ".join(f"{o['name']} (n={o['n']})" for o in thin) + "</div>")
    return f"""
  <div class="panel">
    {body_rows}
    {thin_note}
  </div>"""


_MODE_JS = r"""
(function(){
  const btns=document.querySelectorAll('.ed-mode button');
  function setMode(m){
    btns.forEach(b=>b.classList.toggle('on',b.dataset.m===m));
    document.getElementById('board-hedge').style.display=m==='hedge'?'':'none';
    document.getElementById('board-prop').style.display=m==='prop'?'':'none';
    try{localStorage.setItem('edge-board-mode',m);}catch(e){}
  }
  btns.forEach(b=>b.onclick=()=>setMode(b.dataset.m));
  let m='hedge'; try{m=localStorage.getItem('edge-board-mode')||'hedge';}catch(e){}
  setMode(m);
})();
"""


def render_page(bt_css: str = "", bt_body: str = "", bt_script: str = "",
                book: str = "hedge") -> str:
    """bt_* = the backtest-runner fragment (built in main.py, embedded as #backtest).
    `book` only picks which nav to render — the page shows both boards regardless."""
    from .strategy_eval import load_cache
    from .fit_page import fragment as _fit_fragment

    fit_css, fit_body, fit_script = _fit_fragment(book)

    d = load_cache()
    if d:
        rl = d["r_levels"]
        gen = d["generated_at"][:16].replace("T", " ")
        board = (
            f'<div class="ed-h" id="board">Simulated — the rules replayed</div>'
            f'<div class="ed-hs">Same question, no you in it: each coded strategy run over the full '
            f'candle history ({d["span"][0]} → {d["span"][1]}), ranked by net R after {d["fee_pct"]}% '
            f'round-trip fees · first-touch at R = {rl[0]:g}–{rl[-1]:g} · refreshed {gen}. '
            f'Same engine and scoring for both books, different candidate sets: '
            f'<b>hedge</b> = 1h bar-context scalp setups, <b>prop</b> = the 4H/1H Asian-dip family. '
            f'<b>thin</b> = the pattern fired &lt;40× in the entire history — too few occurrences to '
            f'rank (samples can\'t be generated, only more history or a looser pattern creates them).</div>'
            f'<div class="ed-mode">'
            f'<button data-m="hedge">HEDGE</button><button data-m="prop">PROP</button></div>'
            f'<div class="pv">'
            f'<div id="board-hedge">{_board(d["results"], "hedge", rl)}</div>'
            f'<div id="board-prop" style="display:none">{_board(d["results"], "prop", rl)}</div>'
            f'<div class="panel"><h2>Read</h2><div class="prose">'
            f'Each cell is <strong>net R per trade</strong> at that target multiple — green = profitable '
            f'after fees. <strong>score</strong> sums the profitable cells weighted by R, so a strategy '
            f'that still pays at 3R outranks one that only pays at 1R. Top 3 are highlighted. '
            f'Mined in-sample; treat as a shortlist to forward-test, not a guarantee.</div></div>'
            f'</div>'
        )
        head = _CSS + _BOARD_CSS + fit_css + bt_css
        script = SCRIPT + _MODE_JS + fit_script + bt_script
    else:
        board = ('<div class="ed-h" id="board">Simulated — the rules replayed</div>'
                 '<div class="ed-hs">No rankings cached yet — run '
                 '<code>python3 -m app.strategy_eval</code>.</div>')
        head = _CSS + fit_css + bt_css
        script = SCRIPT + fit_script + bt_script

    fit_label = "eval-constrained sweep" if book == "prop" else "goal-constrained sweep"
    anchors = ('<div class="ed-anchors">'
               f'<a href="#fit" style="color:var(--accent);border-color:var(--accent)">↓ Fit · {fit_label}</a>'
               '<a href="#backtest">↓ Backtest · run &amp; build</a>'
               '<a href="#board">↓ Board · simulated ranks</a>'
               '<a href="#past">↓ Past · live results</a></div>')
    body = ('<div class="ed-sub">Which setups pay? One page, four tenses: what shape the strategy '
            'must be, a runner to test the next idea, what the coded rules would have done, and what '
            'your trades actually did.</div>'
            + anchors + fit_body + bt_body + board + _LIVE)
    path = "/prop-edge" if book == "prop" else "/edge"
    return shell(path, "Edge", body, script=script, head_extra=head, meta="which setups pay?")
