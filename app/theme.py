"""LENS design system — single source of truth for the whole web app.

- LENS_CSS  : the cockpit theme (tokens + components + responsive). Served once at
              /assets/lens.css and <link>ed by every page, so the browser caches it
              and there is exactly one place to change styling.
- shell()   : the page template. Wraps body HTML in the standard <head> (fonts +
              css), sticky top bar, scroll-chip nav (current page highlighted),
              and the .app container. Every page is built the same way.

Components available to any page (class names): .tape .gauge .ticket .tg .sizer
.sect/.sec-body (collapsible) .chip/.chips .scard .sb (table) .btn (.skip/.take/
.aplus/.ghost) .actions (sticky thumb bar) .toast .panel .badge .grid-2/.grid-auto
plus utilities (.mono .dim .g .r .a .big .kv .muted). Responsive at 680px / 1080px.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Nav — one list drives every page's nav bar. Add a page here once.
# PROP mirrors HEDGE one-for-one, in the same order, so the two modes are learnable
# as one layout. Every prop page has its OWN URL (a /prop-* twin) — no ?book= toggle.
# The twin routes call the same render() with book="prop" hard-locked, so hedge and
# prop share one codebase and can never drift, but read as fully separate pages.
#   hedge          prop                    render
#   /dashboard  →  /prop-dashboard         own page
#   /goal       →  /prop-goal              own page
#   /desk       →  /prop-desk              own page
#   /signals    →  /prop-signals           own page
#   /journal    →  /prop-journal           shared render, book="prop" locked
#   /calendar   →  /prop-calendar          shared render, book="prop" locked
#   /analytics  →  /prop-analytics         shared render, book="prop" locked
#   /position   →  /prop-position          shared render, book="prop" locked
#   /edge       →  /prop-edge              shared render, book="prop" locked
NAV_PROP = [
    ("/overview", "Overview"),
    ("/prop-dashboard", "Plan"),
    ("/prop-goal", "Goal"),
    ("/prop-cone", "Cone"),
    ("/prop-position", "Position"),
    ("/prop-desk", "Desk"),
    ("/prop-signals", "Signals"),
    ("/prop-calendar", "Calendar"),
    ("/prop-analytics", "Analytics"),
    ("/prop-journal", "Journal"),
    ("/prop-edge", "Edge"),
    ("/prop", "Engines"),
    ("/prop-ledger", "Ledger"),
    ("/prop-income", "Income"),
    # Strategy / Risk / Survival / Rules / Equity / Regime deliberately have no
    # nav entry — they're the engine cards on /prop. Their pages still render
    # with the prop nav (page_mode defaults to prop).
]
NAV_HEDGE = [
    ("/overview-hedge", "Overview"),
    ("/dashboard", "Plan"),
    ("/goal", "Goal"),
    ("/position", "Position"),
    ("/desk", "Desk"),
    ("/signals", "Signals"),
    ("/calendar", "Calendar"),
    ("/analytics", "Analytics"),
    ("/journal", "Journal"),
    ("/edge", "Edge"),
]
# Primary chips shown in the top nav; everything else in each mode drops to the
# footer ("more"). Pages stay reachable either way.
PROP_MAIN  = {"/overview", "/prop-dashboard", "/prop-desk", "/prop-ledger", "/prop-calendar"}
HEDGE_MAIN = {"/overview-hedge", "/dashboard", "/position", "/calendar"}

# Mode-neutral pages appended to every footer (also: ☰ in the top bar → /sitemap).
# /glossary is pure reference with no book — neutral, so neither nav owns it.
NAV_NEUTRAL = [("/glossary", "Learn"), ("/robustness", "Robustness"), ("/money", "Money"), ("/audit", "Audit"), ("/style", "Style"), ("/sitemap", "Sitemap"), ("/health", "Health")]

# Home ("/") is the neutral mode chooser; /style defaults to the PROP nav.
_PAGE_MODE = {h: "prop" for h, _ in NAV_PROP}
_PAGE_MODE.update({h: "hedge" for h, _ in NAV_HEDGE})


def page_mode(path: str) -> str:
    """Which mode a page lives in (defaults to prop for neutral pages).

    A shared page (/position, /edge, /journal…) belongs to whichever mode you
    arrived from, so `?book=` on the path wins over the static table. Without this
    a prop user clicking "Position" would be dumped into the hedge nav."""
    if "book=prop" in path:
        return "prop"
    if "book=hedge" in path:
        return "hedge"
    return _PAGE_MODE.get(path, "prop")

# ─────────────────────────────────────────────────────────────────────────────
# Brand mark — a scope/aperture iris (LENS = optics; concentric reads as a
# target/scope at 16px). Served at /assets/favicon.svg, <link>ed by shell().
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="7" fill="#06080c"/>'
    '<circle cx="16" cy="16" r="9.5" fill="none" stroke="#5b9dff" stroke-width="2"/>'
    '<circle cx="16" cy="16" r="3" fill="#1fd989"/>'
    '<path d="M16 2.5v4M16 25.5v4M2.5 16h4M25.5 16h4" stroke="#5b9dff" '
    'stroke-width="1.6" stroke-linecap="round"/>'
    '</svg>'
)

FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">'
)

# ─────────────────────────────────────────────────────────────────────────────
LENS_CSS = r"""
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#06080c; --bg2:#04050a;
  --panel:#0b0f16; --panel2:#10151e; --panel3:#161d28;
  --line:#192232; --line2:#28344a;
  --ink:#e8eef8; --dim:#828ea6; --faint:#465064; --ghost:#262f3e;
  --long:#1fd989; --long-d:#0c3a28;
  --short:#ff5468; --short-d:#43141d;
  --amber:#f6ad3c; --amber-d:#3c2c0e;
  --accent:#5b9dff; --accent-d:#10203f;
  --hud:'Chakra Petch',-apple-system,system-ui,sans-serif;
  --mono:'JetBrains Mono','SF Mono',ui-monospace,monospace;
  --glow-g:0 0 30px -6px rgba(31,217,137,.55);
  --glow-r:0 0 30px -6px rgba(255,84,104,.5);
}
html,body{background:var(--bg2)}
body{
  font-family:var(--hud); color:var(--ink); font-size:14px; line-height:1.45;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  padding-bottom:env(safe-area-inset-bottom);
  background:
    radial-gradient(900px 500px at 50% -8%, rgba(91,157,255,.10), transparent 60%),
    radial-gradient(700px 600px at 100% 100%, rgba(31,217,137,.05), transparent 55%),
    var(--bg);
  min-height:100vh;
}
/* faint cockpit grid */
body::before{
  content:""; position:fixed; inset:0; pointer-events:none; z-index:0; opacity:.4;
  background-image:
    linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);
  background-size:34px 34px;
  -webkit-mask-image:radial-gradient(circle at 50% 30%,#000,transparent 90%);
          mask-image:radial-gradient(circle at 50% 30%,#000,transparent 90%);
}
.app{position:relative; z-index:1; max-width:460px; margin:0 auto; padding:0 14px 120px}
a{color:var(--accent);text-decoration:none}

/* ── help / explainer panel ── */
.help-body{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 16px;font-size:13px;line-height:1.6;color:var(--dim)}
.help-body h4{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:14px 0 5px;font-weight:700}
.help-body h4:first-child{margin-top:0}
.help-body b{color:var(--ink);font-weight:700}
.help-body .g{color:var(--long)} .help-body .r{color:var(--short)} .help-body .a{color:var(--amber)}
.help-body code{font-family:var(--mono);font-size:11.5px;background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:1px 6px;color:var(--ink)}
.help-body ol{margin:4px 0 0 18px} .help-body ol li{margin:3px 0}

/* ── inline glossary help badge (?) — links to /glossary#anchor ── */
.qh{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;
  border-radius:50%;border:1px solid var(--line2);color:var(--dim);font-family:var(--mono);
  font-size:9px;font-weight:700;text-decoration:none;margin-left:5px;vertical-align:baseline;
  line-height:1;flex:0 0 auto}
.qh:active{transform:scale(.9)}
@media (hover:hover){ .qh:hover{color:var(--accent);border-color:var(--accent)} }

/* ── top bar ── */
.bar{display:flex;align-items:center;justify-content:space-between;
  padding:16px 2px 12px;position:sticky;top:0;z-index:30;
  background:linear-gradient(var(--bg) 72%,transparent);backdrop-filter:blur(4px)}
.logo{font-family:var(--hud);font-weight:700;font-size:17px;letter-spacing:.32em;color:#fff}
.logo .s{color:var(--accent)}
.logo .pg{color:var(--dim);font-weight:500;letter-spacing:.22em;font-size:13px;margin-left:2px}
.live{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10px;
  letter-spacing:.14em;color:var(--dim);text-transform:uppercase}
.dot{width:8px;height:8px;border-radius:50%;background:var(--long);
  box-shadow:0 0 0 0 rgba(31,217,137,.6);animation:pulse 2.4s infinite}
.dot.stale{background:var(--amber);animation:none;box-shadow:0 0 8px var(--amber)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(31,217,137,.55)}70%{box-shadow:0 0 0 9px rgba(31,217,137,0)}100%{box-shadow:0 0 0 0 rgba(31,217,137,0)}}

/* ── nav: horizontal scroll chips ── */
.nav{display:flex;gap:6px;overflow-x:auto;padding:0 2px 14px;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.nav::-webkit-scrollbar{display:none}
.nav a{flex:0 0 auto;font-family:var(--mono);font-size:11px;color:var(--dim);
  padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--panel);
  letter-spacing:.04em;transition:.15s}
.nav a.cur{color:var(--bg);background:var(--accent);border-color:var(--accent);font-weight:700}
.nav a:active{transform:scale(.95)}
/* ── mode switch: the two doors (PROP / HEDGE) ── */
.modesw{display:flex;gap:5px;padding:0 2px 10px}
.modesw a{flex:0 0 auto;font-family:var(--mono);font-size:11px;font-weight:700;
  letter-spacing:.1em;color:var(--dim);text-decoration:none;padding:6px 16px;
  border:1px solid var(--line2);border-radius:7px;transition:.15s}
.modesw a.home{padding:6px 11px;letter-spacing:0;font-size:13px}
.modesw a:active{transform:scale(.95)}
.modesw a.on{color:var(--bg)}
.modesw a:nth-child(1).on{background:var(--accent);border-color:var(--accent)}
.modesw a:nth-child(2).on{background:var(--amber);border-color:var(--amber)}
@media (hover:hover){ .modesw a:hover{color:var(--ink);border-color:var(--line2)} }

/* ── price strip ── */
.tape{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap;
  padding:6px 4px 16px;border-bottom:1px solid var(--line);margin-bottom:18px}
.px{font-family:var(--mono);font-weight:800;font-size:30px;letter-spacing:-.01em;line-height:1}
.px .c{color:var(--dim);font-size:15px;font-weight:500}
.tape .meta{font-family:var(--mono);font-size:10.5px;color:var(--dim);line-height:1.7;
  margin-left:auto;text-align:right}
.tape .meta b{color:var(--ink);font-weight:700}
.tape .meta .stale{color:var(--amber)}

/* ── verdict gauge (hero) ── */
.gauge{position:relative;border-radius:16px;padding:20px 18px 18px;margin-bottom:14px;
  background:linear-gradient(160deg,var(--panel2),var(--panel));border:1px solid var(--line2);overflow:hidden}
.gauge::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--faint)}
.gauge.enter{border-color:rgba(31,217,137,.5);box-shadow:var(--glow-g)}
.gauge.enter::before{background:var(--long)}
.gauge.enter .verdict{color:var(--long)}
.gauge.blocked,.gauge.veto{border-color:rgba(255,84,104,.4)}
.gauge.blocked::before,.gauge.veto::before{background:var(--short)}
.gauge.blocked .verdict,.gauge.veto .verdict{color:var(--short)}
.gauge.stand_down{opacity:.92}
.gauge.stand_down::before{background:var(--ghost)}
.gauge.stand_down .verdict{color:var(--dim)}
.g-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.g-dir{font-family:var(--mono);font-size:12px;letter-spacing:.22em;color:var(--dim)}
.g-dir .arrow{font-weight:800}
.g-dir.long .arrow{color:var(--long)} .g-dir.short .arrow{color:var(--short)}
.g-setup{font-family:var(--mono);font-size:10.5px;color:var(--dim);padding:3px 9px;
  border:1px solid var(--line2);border-radius:999px}
.verdict{font-family:var(--hud);font-weight:700;font-size:34px;letter-spacing:.02em;line-height:1.05}
.verdict-sub{font-family:var(--mono);font-size:11.5px;color:var(--dim);margin-top:4px}
.vetolist{list-style:none;margin-top:12px;display:flex;flex-direction:column;gap:5px}
.vetolist li{font-family:var(--mono);font-size:11px;color:var(--short);
  padding-left:16px;position:relative;line-height:1.4}
.vetolist li::before{content:"\2715";position:absolute;left:0;color:var(--short);font-size:10px;top:1px}

/* ── ticket ── */
.ticket{margin-top:16px;border-top:1px dashed var(--line2);padding-top:14px}
.ticket.dim{opacity:.5}
.ticket-ref{font-family:var(--mono);font-size:10px;color:var(--amber);margin-bottom:10px;line-height:1.4}
.tg{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.tg .cell{background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:9px 10px}
.tg .k{font-family:var(--mono);font-size:8.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.tg .v{font-family:var(--mono);font-size:16px;font-weight:700;margin-top:3px}
.tg .v.g{color:var(--long)} .tg .v.r{color:var(--short)}
.tg .sub{font-family:var(--mono);font-size:9px;color:var(--faint);margin-top:1px}
.sizer{display:flex;align-items:center;gap:9px;margin-top:12px;
  font-family:var(--mono);font-size:11px;color:var(--dim);flex-wrap:wrap}
.sizer label{letter-spacing:.06em}
.sizer input{width:84px;background:var(--bg);border:1px solid var(--line2);border-radius:7px;
  color:var(--ink);padding:7px 9px;font-family:var(--mono);font-size:14px;font-weight:700}
.sizer input:focus{outline:none;border-color:var(--accent)}
.size-out{font-family:var(--mono);font-size:11px;color:var(--ink);margin-top:9px;line-height:1.6}
.outcome{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:7px;line-height:1.7}
.outcome b.g{color:var(--long)} .outcome b.r{color:var(--short)}
.exit-note{margin-top:10px;font-family:var(--mono);font-size:10px;color:var(--amber);
  line-height:1.5;background:var(--amber-d);border-radius:8px;padding:8px 10px;opacity:.92}

/* ── collapsible sections ── */
.sect{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim);margin:24px 4px 11px;display:flex;align-items:center;gap:10px;
  cursor:pointer;-webkit-tap-highlight-color:transparent;user-select:none}
.sect:active{color:var(--ink)}
.sect .caret{font-size:11px;transition:transform .2s;color:var(--faint)}
.sect.closed .caret{transform:rotate(-90deg)}
.sect .ttl::after{content:"";display:inline-block;width:8px}
.sect .line{flex:1;height:1px;background:var(--line)}
.sec-body{overflow:hidden;transition:max-height .25s ease;max-height:5000px}
.sec-body.closed{max-height:0;margin:0}

/* ── chips ── */
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{font-family:var(--mono);font-size:11px;color:var(--dim);background:var(--panel);
  border:1px solid var(--line);border-radius:8px;padding:7px 10px}
.chip b{color:var(--ink);font-weight:700}
.chip.good{border-color:rgba(31,217,137,.4)} .chip.good b{color:var(--long)}
.chip.bad{border-color:rgba(255,84,104,.4)} .chip.bad b{color:var(--short)}

/* ── cards ── */
.scard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:10px;transition:.2s}
.scard.active{border-color:rgba(31,217,137,.55);box-shadow:var(--glow-g)}
.scard.vetoed{border-color:rgba(246,173,60,.5)}
.sh{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:2px}
.sid{font-family:var(--mono);font-weight:800;font-size:14px}
.sid .d-long{color:var(--long)} .sid .d-short{color:var(--short)}
.swr{font-family:var(--mono);font-size:10px;color:var(--dim)}
.sname{font-size:12.5px;color:var(--dim);margin-bottom:9px}
.cond{display:flex;gap:9px;font-family:var(--mono);font-size:11.5px;padding:3px 0;align-items:baseline}
.cond .tk{width:13px;flex:0 0 13px;font-weight:700}
.cond.ok{color:var(--ink)} .cond.ok .tk{color:var(--long)}
.cond.no{color:var(--faint)} .cond.no .tk{color:var(--ghost)}
.sflag{margin-top:10px;font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.04em}
.sflag.go{color:var(--long)} .sflag.veto{color:var(--amber)}

/* ── generic panel + table ── */
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 16px;margin-bottom:12px}
.sb{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:11px}
.sb th{color:var(--dim);text-align:left;font-weight:500;padding:7px 8px;border-bottom:1px solid var(--line);
  letter-spacing:.04em;font-size:9.5px;text-transform:uppercase}
.sb td{padding:7px 8px;border-bottom:1px solid var(--panel3);color:var(--ink)}
.sb td.g{color:var(--long)} .sb td.r{color:var(--short)} .sb td.m{color:var(--dim)}
.sb-wrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:4px 8px;overflow-x:auto}

/* ── status badges ── */
.badge{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:10px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;padding:4px 9px;border-radius:999px;border:1px solid var(--line2);color:var(--dim)}
.badge.pending{color:var(--amber);border-color:rgba(246,173,60,.5);background:var(--amber-d)}
.badge.approved{color:var(--long);border-color:rgba(31,217,137,.5);background:var(--long-d)}
.badge.rejected{color:var(--short);border-color:rgba(255,84,104,.45);background:var(--short-d)}
.badge.expired{color:var(--faint)}

/* ── key/value list ── */
.kv{display:flex;justify-content:space-between;gap:12px;font-family:var(--mono);font-size:12px;padding:5px 0;border-bottom:1px solid var(--panel3)}
.kv:last-child{border-bottom:none}
.kv .k{color:var(--dim)} .kv .v{color:var(--ink);font-weight:700}

.foot{margin-top:22px;font-family:var(--mono);font-size:10px;color:var(--faint);line-height:1.6;padding:0 2px}

/* ── sticky action bar (thumb zone) ── */
.actions{position:fixed;left:0;right:0;bottom:0;z-index:40;
  padding:12px 14px calc(12px + env(safe-area-inset-bottom));
  background:linear-gradient(transparent,var(--bg2) 26%);display:none}
.actions.show{display:block}
.actions-inner{max-width:460px;margin:0 auto}
.act-label{font-family:var(--mono);font-size:10px;color:var(--dim);text-align:center;
  margin-bottom:9px;letter-spacing:.08em}
.act-label b{color:var(--ink)}
.act-row{display:grid;grid-template-columns:1fr 1.1fr 1.1fr;gap:8px}
.btn{font-family:var(--hud);font-weight:700;font-size:14px;letter-spacing:.04em;
  border:none;border-radius:13px;padding:16px 8px;cursor:pointer;color:#fff;
  -webkit-tap-highlight-color:transparent;transition:transform .08s,filter .15s}
.btn:active{transform:scale(.96)}
.btn .cap{display:block;font-family:var(--mono);font-size:9px;font-weight:500;opacity:.8;margin-top:2px}
.btn.skip{background:var(--panel3);color:var(--dim);border:1px solid var(--line2)}
.btn.take{background:linear-gradient(150deg,#1fd989,#13a567);box-shadow:var(--glow-g)}
.btn.aplus{background:linear-gradient(150deg,#2ee89a,#0e8f5b);box-shadow:0 0 26px -4px rgba(31,217,137,.7);
  border:1px solid rgba(255,255,255,.2)}
.btn.ghost{background:transparent;border:1px solid var(--line2);color:var(--ink);padding:11px 14px;font-size:12px}
.btn:disabled{filter:grayscale(.7) brightness(.6);box-shadow:none}

/* ── toast ── */
.toast{position:fixed;left:50%;bottom:120px;transform:translateX(-50%) translateY(20px);
  z-index:60;font-family:var(--mono);font-size:13px;font-weight:700;padding:13px 22px;
  border-radius:12px;opacity:0;pointer-events:none;transition:.3s;white-space:nowrap}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.toast.ok{background:var(--long-d);color:var(--long);border:1px solid var(--long)}
.toast.no{background:var(--short-d);color:var(--short);border:1px solid var(--short)}
.toast.err{background:var(--amber-d);color:var(--amber);border:1px solid var(--amber)}

.skeleton{color:var(--dim);font-family:var(--mono);font-size:12px;padding:40px 0;text-align:center}

/* ── utilities ── */
.mono{font-family:var(--mono)} .dim{color:var(--dim)} .muted{color:var(--faint)}
.g{color:var(--long)} .r{color:var(--short)} .a{color:var(--amber)}
.big{font-size:24px;font-weight:800;font-family:var(--mono)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}

/* ── responsive: phone → tablet → desktop ── */
.gauges{display:grid;grid-template-columns:1fr;gap:14px}
.setups-grid{display:grid;grid-template-columns:1fr;gap:10px}
.grid-2{display:grid;grid-template-columns:1fr;gap:12px}
.grid-auto{display:grid;grid-template-columns:1fr;gap:10px}

/* tablet / iPad */
@media (min-width:680px){
  .app{max-width:720px;padding:0 22px 130px}
  .gauges{grid-template-columns:1fr 1fr;align-items:start}
  .setups-grid{grid-template-columns:1fr 1fr}
  .grid-2{grid-template-columns:1fr 1fr}
  .grid-auto{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
  .px{font-size:36px}
  .verdict{font-size:38px}
  .tg{grid-template-columns:repeat(4,1fr)}
  .actions-inner{max-width:560px}
}
/* desktop */
@media (min-width:1080px){
  .app{max-width:1120px;padding:0 28px 130px}
  .setups-grid{grid-template-columns:repeat(3,1fr)}
  .nav{flex-wrap:wrap;overflow:visible}
  .verdict{font-size:42px}
  .tg{grid-template-columns:repeat(2,1fr)}
}
@media (hover:hover){ .nav a:hover{color:var(--ink);border-color:var(--line2)} .sect:hover{color:var(--ink)} }
"""


def nav_html(current_path: str) -> str:
    """Mode-aware nav: a PROP|HEDGE switch, then only the current mode's chips.
    Switching modes just navigates to that mode's home — stateless, no cookie."""
    mode = page_mode(current_path)
    items = NAV_PROP if mode == "prop" else NAV_HEDGE
    main = PROP_MAIN if mode == "prop" else HEDGE_MAIN
    out = []
    for href, label in items:
        if href not in main:
            continue
        cur = " cur" if href == current_path else ""
        out.append('<a href="%s" class="%s">%s</a>' % (href, cur.strip(), label))
    sw = (
        '<div class="modesw">'
        '<a href="/overview" class="%s">◎ PROP</a>'
        '<a href="/overview-hedge" class="%s">▤ HEDGE</a>'
        '<a href="/sitemap" class="home">☰</a>'
        '<a href="/" class="home">⌂</a>'
        '</div>'
    ) % ("on" if mode == "prop" else "", "on" if mode == "hedge" else "")
    return sw + '<nav class="nav">' + "".join(out) + "</nav>"


def footer_html(current_path: str) -> str:
    """Secondary pages for the current mode — the chips not in the top nav."""
    mode = page_mode(current_path)
    items = NAV_PROP if mode == "prop" else NAV_HEDGE
    main = PROP_MAIN if mode == "prop" else HEDGE_MAIN
    out = ['<a href="%s" class="%s">%s</a>' % (href, "cur" if href == current_path else "", label)
           for href, label in items if href not in main]
    out += ['<a href="%s" class="%s">%s</a>' % (href, "cur" if href == current_path else "", label)
            for href, label in NAV_NEUTRAL]
    if not out:
        return ""
    return '<footer class="navftr"><span class="ftl">more</span>' + "".join(out) + "</footer>"


def shell(current_path: str, page_label: str, body: str, *,
          script: str = "", right: str = "", head_extra: str = "",
          meta: str = "can I trade?") -> str:
    """Build a full standardized page. `body` and `script` are inserted verbatim
    (may contain braces / template literals — no .format is run on them)."""
    head = (
        "<!DOCTYPE html><html lang=\"en\"><head>"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, "
        "maximum-scale=1.0, user-scalable=no\">"
        "<meta name=\"theme-color\" content=\"#06080c\">"
        "<title>LENS // " + page_label + "</title>"
        + FONT_LINKS +
        "<link rel=\"icon\" type=\"image/svg+xml\" href=\"/assets/favicon.svg\">"
        "<link rel=\"apple-touch-icon\" href=\"/assets/favicon.svg\">"
        "<link rel=\"stylesheet\" href=\"/assets/lens.css\">"
        "<style>"
        "footer.navftr{max-width:1000px;margin:38px auto 0;padding:13px 14px 44px;"
        "border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:7px 15px;align-items:center}"
        "footer.navftr .ftl{font-family:var(--mono);font-size:9px;letter-spacing:.18em;"
        "text-transform:uppercase;color:var(--faint);margin-right:4px}"
        "footer.navftr a{color:var(--dim);font-size:11.5px;text-decoration:none}"
        "footer.navftr a:hover{color:var(--ink)}"
        "footer.navftr a.cur{color:var(--accent)}"
        "</style>"
        + head_extra +
        "</head><body><div class=\"app\">"
        "<div class=\"bar\">"
        "<div class=\"logo\">LEN<span class=\"s\">S</span> "
        "<span class=\"pg\">" + page_label + "</span></div>"
        + (right or ("<div class=\"live\"><span class=\"dot\"></span>" + meta + "</div>")) +
        "</div>"
        + nav_html(current_path)
    )
    tail = footer_html(current_path) + "</div>" + (("<script>" + script + "</script>") if script else "") + "</body></html>"
    return head + body + tail
