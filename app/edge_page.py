"""LENS /edge — THE strategy page, one question in three tenses.

#past     — realised performance per setup family from YOUR live trades
            (auto-tagged on sync, verdict from expectancy · WR · sample).
#board    — the coded strategies replayed over the full candle history,
            hedge/prop toggle (was /strategy-hedge + /strategy; both redirect here).
#backtest — the interactive runner + SL×TP sweep + build-your-own
            (was /backtest; redirects here).

Live results, backtest ranks and the runner are different measurements of the
same question — "which setups pay?" — so they live on one page.
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
</style>
"""

_LIVE = """
<div class="ed-h" id="past">Past — your live trades</div>
<div class="ed-hs">Realised edge per setup family · auto-tagged on sync · verdict from expectancy · WR · sample</div>
<div class="panel" style="overflow-x:auto">
  <table class="ed-tbl">
    <thead><tr><th>Setup</th><th>n</th><th>WR</th><th>Avg€</th><th>Total€</th><th>Verdict</th></tr></thead>
    <tbody id="edge-body"><tr><td colspan="6" class="dim" style="padding:20px">Loading…</td></tr></tbody>
  </table>
</div>
"""

SCRIPT = r"""
function edgeFamily(tag){
  if(!tag) return '(untagged)';
  if(tag.startsWith('VETO:')) return 'VETO';
  if(tag.includes('|VETO:')) return tag.split('|')[0]+' (vetoed)';
  return tag;
}
function edgeVerdict(n,wr,exp){
  if(n<8)               return ['THIN','var(--dim)'];
  if(exp<=0)            return ['CUT','var(--short)'];
  if(exp>=10&&n>=12&&wr>=45) return ['SIZE-UP','var(--long)'];
  return ['KEEP','var(--amber)'];
}
function render(trades){
  const g={};
  trades.filter(t=>t.pnl!=null).forEach(t=>{
    const k=edgeFamily(t.setup_tag);
    if(!g[k]) g[k]={n:0,wins:0,total:0,byGrade:{}};
    g[k].n++; if((t.pnl||0)>0)g[k].wins++; g[k].total+=t.pnl||0;
    const gr=t.grade||'—';
    if(!g[k].byGrade[gr]) g[k].byGrade[gr]={n:0,wins:0,total:0};
    g[k].byGrade[gr].n++; if((t.pnl||0)>0)g[k].byGrade[gr].wins++; g[k].byGrade[gr].total+=t.pnl||0;
  });
  const rows=Object.entries(g).sort((a,b)=>b[1].total-a[1].total);
  document.getElementById('edge-body').innerHTML=rows.map(([k,d])=>{
    const exp=d.total/d.n, wr=d.wins/d.n*100;
    const [vl,vc]=edgeVerdict(d.n,wr,exp);
    const grades=Object.entries(d.byGrade).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
    const sub=grades.length>1?grades.map(([gr,gd])=>
      `<span class="ed-gchip">${gr}: ${gd.n}·${(gd.wins/gd.n*100).toFixed(0)}%·<span style="color:${gd.total>=0?'var(--long)':'var(--short)'}">${gd.total>=0?'+':''}${gd.total.toFixed(0)}€</span></span>`).join(''):'';
    const q=k==='(untagged)'?'__none__':k==='VETO'?'VETO:':k.endsWith(' (vetoed)')?k.split(' ')[0]+'|':k;
    return `<tr class="main"><td><a href="/journal?setup=${encodeURIComponent(q)}" style="color:inherit;text-decoration:none" title="these trades in the journal →">${k} <span style="color:var(--dim);font-size:9px">→</span></a></td><td>${d.n}</td><td>${wr.toFixed(0)}%</td>
      <td style="color:${exp>=0?'var(--long)':'var(--short)'}">${exp>=0?'+':''}${exp.toFixed(0)}€</td>
      <td style="color:${d.total>=0?'var(--long)':'var(--short)'}">${d.total>=0?'+':''}${d.total.toFixed(0)}€</td>
      <td><b style="color:${vc}">${vl}</b></td></tr>`+
      (sub?`<tr><td colspan="6" style="padding:0 0 6px 10px">${sub}</td></tr>`:'');
  }).join('');
}
fetch('/api/review/trades').then(r=>r.json()).then(render).catch(e=>{
  document.getElementById('edge-body').innerHTML='<tr><td colspan="6" class="r" style="padding:20px">Load error: '+e.message+'</td></tr>';});
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
.pv table{width:100%;border-collapse:collapse;font-size:13px}
.pv th,.pv td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
.pv th{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:500}
.pv td{font-family:var(--mono)}
.pv tr.hl{background:var(--panel2)}
.pv .green{color:var(--long)} .pv .red{color:var(--short)}
.pv .prose{color:var(--dim);font-size:13.5px;line-height:1.65}
.pv .prose strong{color:var(--ink)}
</style>"""


def _r_cols(rows, r_levels):
    """Cells for each R level: net R, green if profitable. The 'let winners run'
    sweep made visible — you can read straight across which R each one wins at."""
    by_r = {row["r"]: row for row in rows}
    out = ""
    for R in r_levels:
        row = by_r.get(R)
        if not row:
            out += "<td>·</td>"
            continue
        cls = "green" if row["net"] > 0 else "red"
        out += (f'<td class="{cls}" title="WR {row["wr"]}%">'
                f'{row["net"]:+.2f}</td>')
    return out


def _board(results, mode, r_levels):
    ranked = sorted([o for o in results if o["mode"] == mode and not o["thin"]],
                    key=lambda x: x["rank"])
    thin = [o for o in results if o["mode"] == mode and o["thin"]]
    rcols_head = "".join(f"<th>{R:g}R</th>" for R in r_levels)
    body_rows = ""
    for o in ranked:
        hl = " class=\"hl\"" if o["top3"] else ""
        star = " ★" if o["top3"] else ""
        best = (f'<span class="green">{o["best_net"]:+.2f}R</span> @ {o["best_r"]:g}R'
                if o["best_net"] and o["best_net"] > 0
                else f'<span class="red">{o["best_net"]:+.2f}R</span>')
        body_rows += (
            f"<tr{hl}><td>{o['rank']}{star}</td>"
            f"<td>{o['name']}</td>"
            f"<td>{o['dir']}</td>"
            f"<td>{o['n']}</td>"
            f"<td>{o['sl']:.2f}%</td>"
            f"{_r_cols(o['rows'], r_levels)}"
            f"<td>{best}</td>"
            f"<td><b>{o['score']:.2f}</b></td></tr>")
    thin_note = ""
    if thin:
        thin_note = ('<div class="prose" style="margin-top:8px">thin (n&lt;40, not ranked): '
                     + ", ".join(f"{o['name']} (n={o['n']})" for o in thin) + "</div>")
    return f"""
  <div class="panel">
    <div style="overflow-x:auto"><table>
      <tr><th>#</th><th>strategy</th><th>dir</th><th>n</th><th>stop</th>
          {rcols_head}<th>best</th><th>score</th></tr>
      {body_rows}
    </table></div>
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
