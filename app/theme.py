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

import re

# ─────────────────────────────────────────────────────────────────────────────
# Nav — one list drives every page's nav bar. Add a page here once.
# LENS was hedge+prop in one app until the 2026-09-05 split: prop's own nav
# (NAV_PROP), its /prop-* routes and the PROP/HEDGE mode switch moved out —
# lens-prop is now a separate fork with its own copy of this file. LENS keeps
# the hedge book only; this file has one nav, not two.
# LEGACY_ROUTES in main.py 301s the old bare paths (/goal, /dashboard…) here, so
# old bookmarks and any href missed by a rename keep working.
# Order specified by Lucky, 2026-07-25 — his flow, not a derived one:
# overview → desk → plan → goal → position → journal → analytics → edge
# (signals merged into desk 2026-09-05, see note above). Every entry is a
# top-bar chip (HEDGE_MAIN below is the full set),
# because the previous 5-chip bar pushed half the book into a "more"
# footer: "the nav bar here is too small, it's too little".
# Calendar dropped 2026-08-28 — merged into Journal (same page now, calendar
# on top). Two nav entries pointing at the same job was itself the complaint.
# Signals dropped 2026-09-05 — merged into Desk (same data, same decide
# endpoint, cockpit-glance vs list-scan was the only difference). /signals
# 301s to /desk (see LEGACY_ROUTES in main.py).
# Plan dropped 2026-09-05 — /goal was already its explicit rebuild (same
# calculator, same hero cards, plus the milestone ladder); the two nav
# entries pointed at the same job, same as the Calendar/Journal merge above.
# /plan 301s to /goal (see LEGACY_ROUTES in main.py).
# Edge dropped 2026-09-05 — retrospective ("how did I actually do", Analytics)
# and prospective ("what could I test next", Edge) read as two dashboards
# answering the same underlying question, so Edge's four tabs (past/board/
# backtest/fit) became collapsible sections on /analytics instead of a mode
# switch. /edge 301s to /analytics (see LEGACY_ROUTES in main.py).
# No "hedge-" prefix, unlike prop — 2026-08-29: "I want to keep the hedge
# completely separate from the prop... I want to remove the prefix of hedge
# for everything... even if it's using the same engine I feel like the front
# end should be completely different to isolate them." Hedge is the default/
# primary identity of the site; prop is the isolated satellite, so it keeps
# marking itself. See LEGACY_ROUTES in main.py for the old /hedge-* 301s.
NAV_HEDGE = [
    ("/overview", "Overview"),
    ("/desk", "Desk"),
    ("/goal", "Goal"),
    ("/track", "Track"),
    ("/position", "Position"),
    ("/journal", "Journal"),
    ("/analytics", "Analytics"),
]
# Primary chips shown in the top nav; everything else in each mode drops to the
# footer ("more"). Pages stay reachable either way.
# The whole book is in the top bar. Previously five chips, with Journal,
# Analytics, Plan, Goal and Edge exiled to the footer — he asked for all of it
# up top. The bar already wraps (.nav flex-wrap at >=1080px) and scrolls
# horizontally below that, so a longer list costs layout nothing.
HEDGE_MAIN = {h for h, _ in NAV_HEDGE}

# Mode-neutral pages appended to every footer (also: ☰ in the top bar → /sitemap).
# /glossary is pure reference with no book — neutral, so neither nav owns it.
# Twelve entries became seven on 2026-08-03: Robustness/Research/Short are one
# argument (/evidence), Target is the other half of /geometry, and Learn was the
# glossary, now a tab of /manual. /about joined 2026-08-04 — the page for a
# reader who can judge the work, as distinct from "/" which is for someone who
# just wants to know he's okay.
# Geometry/Review/Audit dropped 2026-09-06 — all three merged into /evidence
# alongside Short/Robustness/Research: geometry+target are the sizing math,
# review is the live monthly workflow, audit is its own superseded history —
# four former pages plus the original three, one nav entry. /geometry,
# /review and /audit 301 to /evidence#<section> (see LEGACY_ROUTES in main.py).
NAV_NEUTRAL = [("/evidence", "Evidence"), ("/money", "Money"), ("/manual", "Manual"), ("/style", "Style"), ("/sitemap", "Sitemap"), ("/health", "Health")]

_PAGE_MODE = {h: "hedge" for h, _ in NAV_HEDGE}

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — 2026-09-06. The top nav bar (above) stopped being enough once
# several pages became small books in themselves (Analytics = Regime+Review+
# Research, Goal = a stack of fold cards, Evidence = seven merged sections):
# a flat row of page chips had no room for "and jump to the bit of THIS page
# I want." PAGE_ANCHORS is the map of (page path -> its in-page sections) that
# drives the nested sub-list sidebar_html() renders under whichever page is
# current. Anchor ids must match real ids in that page's markup (a `<details
# id=…>`, or a `.card.fold` id, or a plain section id) — sidebar_html() does
# not check, so a renamed section id here silently drops that entry.
PAGE_ANCHORS: dict[str, list[tuple[str, str]]] = {
    "/analytics": [
        ("regime", "Market regime"),
        ("review", "Review"),
        ("past", "Past"),
        ("board", "Board"),
        ("backtest", "Backtest"),
        ("fit", "Fit"),
    ],
    "/goal": [
        ("rk-card", "Risk & Kelly"),
        ("stats-card", "Risk analytics"),
        ("acct-card", "Account impact / trade"),
        ("mc-card", "Monte Carlo / BTC"),
        ("wrs-card", "Win-rate sensitivity"),
        ("rtgt-card", "R-target scenarios"),
        ("sladder-card", "Scenario ladder"),
        ("ladder-card", "Milestone ladder"),
        ("plan-card", "The plan"),
    ],
    "/evidence": [
        ("review", "This month · review"),
        ("verdict", "The verdict"),
        ("luck", "Is it luck?"),
        ("geometry", "What this configuration earns"),
        ("target", "What a named target demands"),
        ("audit", "Audit · superseded"),
        ("notebook", "The notebook"),
    ],
}


def sidebar_html(current_path: str) -> str:
    """The sidebar/drawer: Core (the 7 book pages) + Reference (Evidence and
    the utility pages), with the current page's in-page anchors (if any)
    nested directly under its own link. Same `cur` class the old top nav
    used, so existing current-page styling/tests keep working."""
    current_path = current_path.split("?")[0]

    def item(href: str, label: str) -> str:
        cur = href == current_path
        cls = "side-a cur" if cur else "side-a"
        html = f'<a href="{href}" class="{cls}">{label}</a>'
        anchors = PAGE_ANCHORS.get(href) if cur else None
        if anchors:
            subs = "".join(
                f'<a href="#{aid}" class="side-suba">{alabel}</a>'
                for aid, alabel in anchors
            )
            html += f'<div class="side-sub">{subs}</div>'
        return html

    core = "".join(item(h, l) for h, l in NAV_HEDGE)
    ref = "".join(item(h, l) for h, l in NAV_NEUTRAL)
    return (
        '<aside class="side" id="lens-side">'
        '<div class="side-hd">'
        '<a href="/" class="side-logo">LEN<span class="s">S</span></a>'
        '<button type="button" class="side-x" id="lens-side-close" aria-label="close menu">&#10005;</button>'
        '</div>'
        '<nav class="side-nav">'
        '<div class="side-grp">Core</div>' + core +
        '<div class="side-grp">Reference</div>' + ref +
        '</nav>'
        '</aside>'
    )


_SIDEBAR_JS = r"""
(function(){
  var side=document.getElementById('lens-side'), scrim=document.getElementById('lens-side-scrim'),
      burger=document.getElementById('lens-side-burger'), close=document.getElementById('lens-side-close');
  function open(){ if(side){side.classList.add('open');} if(scrim){scrim.classList.add('show');} }
  function shut(){ if(side){side.classList.remove('open');} if(scrim){scrim.classList.remove('show');} }
  if(burger) burger.addEventListener('click', function(){
    if(side && side.classList.contains('open')) shut(); else open();
  });
  if(close) close.addEventListener('click', shut);
  if(scrim) scrim.addEventListener('click', shut);
  if(side) side.querySelectorAll('a').forEach(function(a){ a.addEventListener('click', shut); });

  // Reveal whatever collapsed section a #hash names — both the <details>-based
  // folds (merged()/evidence, analytics' an-d) and Goal's older .card.fold.col
  // toggle-by-class pattern, so one sidebar link works against every page's
  // own collapse mechanism instead of needing three copies of this.
  function openAnchor(id){
    if(!id) return;
    var el=document.getElementById(id);
    if(!el) return;
    var n=el;
    while(n){
      if(n.tagName==='DETAILS') n.open=true;
      if(n.classList && n.classList.contains('fold')) n.classList.remove('col');
      n=n.parentElement;
    }
    if(el.querySelectorAll){
      el.querySelectorAll('details').forEach(function(d){ d.open=true; });
      el.querySelectorAll('.fold').forEach(function(f){ f.classList.remove('col'); });
    }
    if(el.tagName==='DETAILS') el.open=true;
    if(el.classList && el.classList.contains('fold')) el.classList.remove('col');
    setTimeout(function(){ el.scrollIntoView({block:'start'}); }, 0);
  }
  function fromHash(){ openAnchor((location.hash||'').slice(1)); }
  if(location.hash) fromHash();
  window.addEventListener('hashchange', fromHash);
})();
"""


def page_book(path: str) -> str | None:
    """'hedge' | None — which BOOK a page belongs to, or None if it belongs to
    neither (glossary, system, health…). One book now; kept as a lookup (not a
    constant) so a page not in NAV_HEDGE still reads as unbooked."""
    return _PAGE_MODE.get(path.split("?")[0])


def page_mode(path: str) -> str:
    """Every page is 'hedge' now — one book, one nav. Kept as a function (not a
    constant) so call sites from the hedge/prop era didn't all need rewriting."""
    return "hedge"

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
  /* Spacing scale. Added 2026-08-21: there wasn't one, so every page invented
     its own gaps. Additive — nothing existing reads these, so adopting them is
     page by page. */
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
  --r1:6px; --r2:9px; --r3:12px;
  /* --faint measured 2.26–2.47:1 against every surface: below the 4.5 this
     product requires of body text. It is a DECORATION token — borders, rules,
     disabled fills — never text a user has to read. --dim (5.5–6.1:1) is the
     quiet text colour. */
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
  min-height:100vh; min-height:100dvh;
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
.bar{display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:16px 2px 12px;position:sticky;top:0;z-index:30;
  background:linear-gradient(var(--bg) 72%,transparent);backdrop-filter:blur(4px)}
.logo{font-family:var(--hud);font-weight:700;font-size:17px;letter-spacing:.32em;color:#fff;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.logo .s{color:var(--accent)}
.logo .pg{color:var(--dim);font-weight:500;letter-spacing:.22em;font-size:13px;margin-left:2px}
.live{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10px;
  letter-spacing:.14em;color:var(--dim);text-transform:uppercase;flex:0 0 auto;
  max-width:38vw;min-width:0}
/* text-overflow on .live itself never engaged — it's a flex container with a
   dot span + text span, and ellipsis only truncates single inline content.
   The dot needs to stay fixed-size; only the text should shrink+ellipsize. */
.live .dot{flex:0 0 auto}
.live span:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
/* the burger takes room the bar didn't need to budget for before — the page
   label (already shown via the sidebar's own current-page highlight) is the
   one thing here that can drop without losing information, so it's what
   goes first rather than letting the logo or live-status text wrap/overlap. */
@media (max-width:679px){
  .logo .pg{display:none}
}
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
.tg .sub{font-family:var(--mono);font-size:9px;color:var(--dim);margin-top:1px}
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
.sect .caret{font-size:11px;transition:transform .2s;color:var(--dim)}
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
.cond.no{color:var(--dim)} .cond.no .tk{color:var(--ghost)}
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
.badge.expired{color:var(--dim)}

/* ── key/value list ── */
.kv{display:flex;justify-content:space-between;gap:12px;font-family:var(--mono);font-size:12px;padding:5px 0;border-bottom:1px solid var(--panel3)}
.kv:last-child{border-bottom:none}
.kv .k{color:var(--dim)} .kv .v{color:var(--ink);font-weight:700}

.foot{margin-top:22px;font-family:var(--mono);font-size:10px;color:var(--dim);line-height:1.6;padding:0 2px}

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
.mono{font-family:var(--mono)} .dim{color:var(--dim)} .muted{color:var(--dim)}
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

/* ── sidebar (2026-09-06, replaces the top nav chips) ──
   Mobile-first: off-canvas drawer by default, slides in over a dimmed scrim.
   Persistent column from 1080px — that breakpoint already meant "desktop" for
   the nav bar wrapping, so the sidebar takes the same threshold rather than
   inventing a new one. */
.shell{display:flex;min-height:100vh;min-height:100dvh;position:relative;z-index:1}
.side{position:fixed;top:0;left:0;bottom:0;width:82vw;max-width:290px;z-index:100;
  background:var(--panel);border-right:1px solid var(--line2);overflow-y:auto;
  transform:translateX(-100%);transition:transform .22s ease;
  padding:16px 0 24px;-webkit-overflow-scrolling:touch}
.side.open{transform:translateX(0)}
.side-scrim{position:fixed;inset:0;z-index:90;background:rgba(3,5,9,.6);
  opacity:0;pointer-events:none;transition:opacity .2s}
.side-scrim.show{opacity:1;pointer-events:auto}
.side-hd{display:flex;align-items:center;justify-content:space-between;padding:2px 18px 16px}
.side-logo{font-family:var(--hud);font-weight:700;font-size:17px;letter-spacing:.32em;color:#fff}
.side-logo .s{color:var(--accent)}
.side-x{background:none;border:none;color:var(--dim);font-size:16px;line-height:1;
  padding:6px;cursor:pointer;-webkit-tap-highlight-color:transparent;touch-action:manipulation;
  min-width:44px;min-height:44px;display:inline-flex;align-items:center;justify-content:center}
.side-nav{display:flex;flex-direction:column;padding:0 10px}
.side-grp{font-family:var(--mono);font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--faint);padding:14px 10px 6px}
.side-grp:first-child{padding-top:2px}
.side-a{font-family:var(--hud);font-size:14px;color:var(--dim);text-decoration:none;
  padding:9px 10px;border-radius:8px;display:block;transition:.15s;
  -webkit-tap-highlight-color:transparent;touch-action:manipulation}
.side-a.cur{color:var(--bg);background:var(--accent);font-weight:700}
.side-a:active{transform:scale(.98)}
.side-sub{display:flex;flex-direction:column;margin:2px 0 6px 14px;
  border-left:1px solid var(--line2);padding-left:10px}
.side-suba{font-family:var(--mono);font-size:11.5px;color:var(--dim);text-decoration:none;
  padding:6px 6px;border-radius:6px;-webkit-tap-highlight-color:transparent;touch-action:manipulation}
.side-suba:active{transform:scale(.98)}
@media (hover:hover){
  .side-a:not(.cur):hover{color:var(--ink);background:var(--panel3)}
  .side-suba:hover{color:var(--accent)}
}
.side-burger{background:var(--panel);border:1px solid var(--line);color:var(--ink);
  font-size:16px;line-height:1;border-radius:8px;padding:7px 11px;cursor:pointer;
  -webkit-tap-highlight-color:transparent;touch-action:manipulation;flex:0 0 auto;
  min-width:44px;min-height:44px;display:inline-flex;align-items:center;justify-content:center}
.side-burger:active{transform:scale(.94)}
.shell>.app{flex:1;min-width:0}
@media (min-width:1080px){
  .side{position:sticky;top:0;left:auto;height:100vh;height:100dvh;width:230px;max-width:230px;
    transform:none;flex:0 0 230px}
  .side-scrim{display:none!important}
  .side-burger{display:none}
}
"""


def nav_html(current_path: str) -> str:
    """The nav bar: a home/sitemap chip pair, then the hedge chips.
    Was a PROP|HEDGE mode switch before the 2026-09-05 split; one book now."""
    out = []
    for href, label in NAV_HEDGE:
        if href not in HEDGE_MAIN:
            continue
        cur = " cur" if href == current_path else ""
        out.append('<a href="%s" class="%s">%s</a>' % (href, cur.strip(), label))
    sw = (
        '<div class="modesw">'
        '<a href="/sitemap" class="home">☰</a>'
        '<a href="/" class="home">⌂</a>'
        '</div>'
    )
    return sw + '<nav class="nav">' + "".join(out) + "</nav>"


def footer_html(current_path: str) -> str:
    """Secondary (non-top-bar) pages, in one labelled group.

    Previously one undifferentiated run of 14 links: the five remaining TRADING
    pages (Journal, Analytics, Plan, Goal, Edge) sat next to nine utility pages
    (Style, Sitemap, Health, Manual, Audit…) with nothing to tell them apart, so
    finding Edge meant reading the whole strip. The split is purely visual —
    every page stays exactly as reachable as it was."""
    items = NAV_HEDGE
    main = HEDGE_MAIN
    link = lambda href, label: '<a href="%s" class="%s">%s</a>' % (
        href, "cur" if href == current_path else "", label)

    book = [link(h, l) for h, l in items if h not in main]
    # NAV_NEUTRAL (About/Evidence/Geometry/Manual/Style/Health…) dropped from
    # the footer 2026-08-29 — "I haven't looked at this once." Pages aren't
    # deleted (real content, some of it personal) — reachable via /sitemap,
    # just not stamped on every single screen any more.
    #
    # That left `book` empty on every page, so from 2026-08-29 to 2026-09-03
    # this function returned "" everywhere and the site had no footer at all.
    # It now always renders, but carries FRESHNESS rather than more links:
    # every ₿→€ figure on every page is derived from the stored price and the
    # last stack snapshot, and a stale one of either is wrong silently. The
    # links that remain are the three that are useful from anywhere.
    more = ('<span class="ftl">more</span>' + "".join(book)) if book else ""
    stamp = _freshness_html()
    return ('<footer class="navftr">' + more +
            '<span class="ftmeta">' + stamp + '</span>'
            '<span class="ftlinks">'
            '<a href="/sitemap">sitemap</a><a href="/health">health</a></span>'
            '</footer>')


def _freshness_html() -> str:
    """BTC price + how old it and the stack snapshot are.

    Cheap on purpose — two indexed reads — because it runs on every page render.
    Never raises: a footer that can blank a page is worse than one that omits a
    number, so any failure degrades to the wordmark alone.
    """
    from datetime import date, datetime

    def _age(iso: str, dateonly: bool = False):
        try:
            d = (date.fromisoformat(iso[:10]) if dateonly
                 else datetime.fromisoformat(iso).date())
            n = (date.today() - d).days
            return "today" if n <= 0 else ("1d" if n == 1 else f"{n}d")
        except Exception:
            return None

    try:
        from .database import _conn, get_lens_config
        from .plan import STALE_DAYS
        g = get_lens_config() or {}
        px = g.get("btc_price_eur")
        px_age = _age(g.get("updated_at") or "")
        c = _conn()
        row = c.execute("SELECT date, btc_total FROM stack_snapshot "
                        "ORDER BY date DESC LIMIT 1").fetchone()
        c.close()
        out = []
        if px:
            out.append(f'₿ €{float(px):,.0f}' + (f' · {px_age}' if px_age else ''))
        if row:
            n = (date.today() - date.fromisoformat(row["date"][:10])).days
            cls = ' class="stale"' if n > STALE_DAYS else ""
            out.append(f'<span{cls}>stack {row["btc_total"]:.4f} ₿ · '
                       f'{_age(row["date"], True)} old</span>')
        return " · ".join(out)
    except Exception:
        return ""


def _booked(path: str, label: str) -> str:
    """"HEDGE — Overview"; neutral pages keep a bare label.

    Applied centrally rather than at ~25 call sites: every page already passes
    its own label to shell(), so one place decides how a book is announced and
    no page can forget. Idempotent — a label that already names its book is left
    alone, so a page may still hard-code a special one."""
    book = page_book(path)
    if not book or label.upper().startswith(book.upper()):
        return label
    return f"{book.upper()} — {label}"


_MERGE_CSS = """<style>
.mgsub{position:sticky;top:0;z-index:30;display:flex;flex-wrap:wrap;gap:4px 6px;
  background:var(--bg);border-bottom:1px solid var(--line);padding:9px 14px;margin-bottom:4px}
.mgsub a{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--dim);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.mgsub a:hover{color:var(--accent);border-color:var(--accent)}
.mgsec{scroll-margin-top:52px;padding-top:6px}
.mgsec + .mgsec{border-top:1px solid var(--line);margin-top:34px;padding-top:26px}
.mgsec > .mgh{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--dim);max-width:1000px;margin:0 auto 10px;padding:0 14px}
</style>"""


_FOLD_CSS = """<style>
details.mfold{margin:14px 0;border:1px solid var(--line);border-radius:8px;background:var(--panel2);overflow:hidden}
details.mfold>summary{list-style:none;cursor:pointer;padding:11px 13px;font-size:11px;font-weight:700;color:var(--dim);
  text-transform:uppercase;letter-spacing:.08em;display:flex;align-items:center;gap:8px;user-select:none}
details.mfold>summary::-webkit-details-marker{display:none}
details.mfold>summary::before{content:'▸';color:var(--faint);font-size:10px;transition:transform .15s}
details.mfold[open]>summary::before{transform:rotate(90deg)}
details.mfold>summary .sub{font-weight:400;text-transform:none;letter-spacing:0;color:var(--faint);font-size:10px}
.mfold-body{padding:4px 13px 13px}
</style>"""

_FOLD_OPEN_JS = """
(function(){
  function openTo(id){
    if(!id) return;
    var el = document.getElementById(id);
    if(!el) return;
    var d = el.closest ? el.closest('details') : null;
    while(d){ d.open = true; d = d.parentElement ? d.parentElement.closest('details') : null; }
    if (el.querySelectorAll) el.querySelectorAll('details').forEach(function(x){ x.open = true; });
  }
  if (location.hash) openTo(location.hash.slice(1));
  window.addEventListener('hashchange', function(){ openTo(location.hash.slice(1)); });
})();
"""


def fold(title: str, body: str, *, sub: str = "", open_: bool = False, id_: str | None = None) -> str:
    """A native <details> collapsible, same visual language as analytics_page's
    `an-d` sections — for wrapping a whole merged-in section (superseded
    content, a deep appendix) so it doesn't read as equal-weight with the live
    workflow sections around it. `merged()` always ships the CSS and the
    hash-opens-ancestor-details script this depends on."""
    idattr = f' id="{id_}"' if id_ else ""
    openattr = " open" if open_ else ""
    subhtml = f' <span class="sub">{sub}</span>' if sub else ""
    return (f'<details class="mfold"{idattr}{openattr}><summary>{title}{subhtml}</summary>'
            f'<div class="mfold-body">{body}</div></details>')


_AT_UNSCOPED = ("@keyframes", "@-webkit-keyframes", "@font-face", "@import", "@charset")
_AT_NESTED = ("@media", "@supports", "@container", "@layer")


def scope_css(css: str, sel: str) -> str:
    """Prefix every rule in `css` with `sel`, so two merged pages can each keep
    their own `.conf` without one silently restyling the other.

    Geometry and Target collided on sixteen class names — `.conf`, `.kv`, `.m`,
    `.lead`… — which is why this exists rather than hand-renaming. `:root` and
    `body` map to the scope itself: a section can't restyle the document.
    """
    css = re.sub(r"</?style[^>]*>", "", css)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, n = [], 0, len(css)
    while i < n:
        brace = css.find("{", i)
        if brace == -1:
            break
        head = css[i:brace].strip()
        # walk to the matching close brace, so nested @media blocks stay whole
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        block = css[brace + 1:j - 1]
        if head.startswith(_AT_UNSCOPED):
            out.append(f"{head}{{{block}}}")
        elif head.startswith(_AT_NESTED):
            out.append(f"{head}{{{scope_css(block, sel)}}}")
        elif head:
            parts = []
            for one in head.split(","):
                one = one.strip()
                if not one:
                    continue
                parts.append(sel if one in (":root", "html", "body") else f"{sel} {one}")
            out.append(f"{','.join(parts)}{{{block}}}")
        i = j
    return "".join(out)


def merged(current_path: str, page_label: str, sections: list[dict], *,
           meta: str = "can I trade?", intro: str = "") -> str:
    """One page built from several former pages, stacked as anchored sections.

    Each section is {"id","label","body"} plus optional "css"/"script". These
    used to be separate routes; nothing about their markup changed, so the
    merge can't silently drop content — it only re-wraps it.

    Scripts are wrapped in an IIFE apiece. Merging two pages that each declare
    a top-level `const c = canvas` is otherwise an instant SyntaxError, and the
    pages being merged here have no inline on* handlers that would need the
    old global scope back.
    """
    # A section id that already exists inside one of the bodies silently wins
    # getElementById, because the <section> comes first in document order. That
    # is how id="cone" handed the cone's drawCone() a <section> instead of its
    # <canvas> — no console error until the first paint. Fail loudly instead.
    ids = set()
    for s in sections:
        ids |= set(re.findall(r'id="([^"]+)"', s["body"]))
    clash = ids & {s["id"] for s in sections}
    if clash:
        raise ValueError(
            "merged(%s): section id(s) %s already used by an element inside a "
            "section body — rename the section." % (current_path, sorted(clash)))

    nav = "".join('<a href="#%s">%s</a>' % (s["id"], s["label"]) for s in sections)
    css = _MERGE_CSS + _FOLD_CSS + "<style>" + "".join(
        scope_css(s["css"], "#" + s["id"]) for s in sections if s.get("css")
    ) + "</style>"
    script = _FOLD_OPEN_JS + "".join(
        "\n;(function(){\n%s\n})();\n" % s["script"] for s in sections if s.get("script")
    )
    # Sections whose body already opens with its own <h1> pass heading=False,
    # or the eyebrow just says the same thing twice.
    body = (intro or "") + '<div class="mgsub">' + nav + "</div>" + "".join(
        '<section id="%s" class="mgsec">%s%s</section>'
        % (s["id"],
           ('<div class="mgh">%s</div>' % s["label"]) if s.get("heading", True) else "",
           s["body"])
        for s in sections
    )
    return shell(current_path, page_label, body,
                 head_extra=css, script=script, meta=meta)


def shell(current_path: str, page_label: str, body: str, *,
          script: str = "", right: str = "", head_extra: str = "",
          meta: str = "can I trade?", bare: bool = False) -> str:
    """Build a full standardized page. `body` and `script` are inserted verbatim
    (may contain braces / template literals — no .format is run on them).

    bare=True drops the top bar and nav chips — for "/", which is the front door
    and carries its own wordmark and its own doors. The footer still lists every
    page, so nothing becomes unreachable."""
    head = (
        "<!DOCTYPE html><html lang=\"en\"><head>"
        "<meta charset=\"UTF-8\">"
        # 2026-09-06: dropped maximum-scale=1.0 + user-scalable=no after direct
        # phone feedback ("issues with zooming in and out ... not responsive on
        # mobile"). That combo blocks pinch-zoom outright on most Android/Chrome
        # builds, and even where the OS overrides it for accessibility (iOS 10+
        # always allows pinch regardless of the meta tag), a page authored
        # assuming scale is locked can render fixed-position chrome (the sticky
        # bar, the drawer, the scrim) misaligned once the OS zooms anyway — the
        # exact "sidebar doesn't work" symptom. No screen here needs zoom
        # blocked, and the owner reads better zoomed in sometimes, so let the
        # browser's native pinch-zoom behave normally.
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<meta name=\"theme-color\" content=\"#06080c\">"
        "<title>LENS // " + _booked(current_path, page_label) + "</title>"
        + FONT_LINKS +
        "<link rel=\"icon\" type=\"image/svg+xml\" href=\"/assets/favicon.svg\">"
        "<link rel=\"apple-touch-icon\" href=\"/assets/favicon.svg\">"
        "<link rel=\"stylesheet\" href=\"/assets/lens.css\">"
        "<style>"
        "footer.navftr{max-width:1000px;margin:38px auto 0;padding:13px 14px 44px;"
        "border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:7px 15px;align-items:center}"
        "footer.navftr .ftl{font-family:var(--mono);font-size:10px;letter-spacing:.18em;"
        "text-transform:uppercase;color:var(--dim);margin-right:4px}"
        # the SYSTEM group starts a new line so the trading pages above it read
        # as their own set — the whole point of splitting the strip in two
        "footer.navftr .ftl2{flex-basis:100%;margin-top:9px;padding-top:9px;"
        "border-top:1px solid var(--line)}"
        "footer.navftr a{color:var(--dim);font-size:11.5px;text-decoration:none}"
        "footer.navftr a:hover{color:var(--ink)}"
        "footer.navftr a.cur{color:var(--accent)}"
        # freshness on the left, links pushed right; both wrap together on a
        # phone rather than the links stranding on their own line
        "footer.navftr .ftmeta{font-family:var(--mono);font-size:10.5px;"
        "color:var(--faint);letter-spacing:.02em}"
        "footer.navftr .ftmeta .stale{color:var(--amber)}"
        "footer.navftr .ftlinks{margin-left:auto;display:flex;gap:14px}"
        "@media(max-width:560px){footer.navftr .ftlinks{margin-left:0}}"
        "</style>"
        + head_extra +
        "</head><body>"
    )
    if bare:
        head += "<div class=\"app\">"
        shell_close = "</div>"
    else:
        head += (
            "<div class=\"shell\">"
            + sidebar_html(current_path)
            + "<div class=\"side-scrim\" id=\"lens-side-scrim\"></div>"
            + "<div class=\"app\">"
            + "<div class=\"bar\">"
            "<button type=\"button\" class=\"side-burger\" id=\"lens-side-burger\" "
            "aria-label=\"open menu\">&#9776;</button>"
            "<div class=\"logo\">LEN<span class=\"s\">S</span> "
            "<span class=\"pg\">" + _booked(current_path, page_label) + "</span></div>"
            + (right or ("<div class=\"live\"><span class=\"dot\"></span><span>" + meta + "</span></div>")) +
            "</div>"
        )
        shell_close = "</div></div>"
    full_script = (_SIDEBAR_JS if not bare else "") + script
    tail = (footer_html(current_path) + shell_close +
            (("<script>" + full_script + "</script>") if full_script else "") +
            "</body></html>")
    return head + body + tail
