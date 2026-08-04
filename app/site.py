"""The public site — the half of LENS that isn't the cockpit.

Two audiences had been sharing one set of chrome, badly. The cockpit (hedge,
prop, evidence, desk) is an instrument panel for one operator who already knows
what every abbreviation means. The public pages are for a reader who arrived
from a link and owes this nothing: they need a masthead, a nav they recognise
from every other website they have used, and prose set for reading rather than
scanning.

Before this, /about was written in `.help-body` — the in-app explainer style —
which made it read as a settings screen with paragraphs in it. Correct
information, wrong object. His words: "a shitty addition to the actual app".

So the public pages get their own shell:

  · the front door's typography (Libre Caslon for anything that speaks, the
    mono face for labels only), lifted from explain_page's established look so
    the site reads as one thing
  · a real nav — Home · About · Philosophy — sticky, three items, no book
    switching, no ?book= state, nothing that assumes you know what a book is
  · `bare=True` on the underlying shell, so none of the cockpit's chips or
    mode chrome appear
  · one deliberate door into the app at the end of the footer, styled quieter
    than the nav, because the cockpit is where this goes but not what a first
    reader should be handed

explain_page ("/") keeps its own CSS untouched and only imports the nav — its
layout was designed as a single scroll and is the thing everything else here is
matching, so it is the last file that should be refactored to match anything.
"""

SITE_NAV = [("/", "Home"), ("/about", "About"), ("/philosophy", "Philosophy")]

FONT = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Libre+Caslon+Text:ital@0;1&display=swap" rel="stylesheet">'
)

# Nav only — safe to drop into any public page, including "/" whose own CSS
# must not be touched.
NAV_CSS = r"""<style>
.snav{position:sticky;top:0;z-index:40;background:rgba(6,8,12,.82);
  backdrop-filter:blur(9px);border-bottom:1px solid var(--line);
  margin:0 0 clamp(26px,5vh,52px)}
.snav .in{max-width:820px;margin:0 auto;padding:13px 16px;
  display:flex;align-items:baseline;gap:clamp(14px,3vw,28px)}
.snav .wm{font-family:var(--mono);font-size:11px;letter-spacing:.3em;
  text-transform:uppercase;color:var(--dim);text-decoration:none;margin-right:auto}
.snav .wm:hover{color:var(--ink)}
.snav a.l{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--faint);text-decoration:none;
  padding-bottom:2px;border-bottom:1px solid transparent}
.snav a.l:hover{color:var(--dim)}
.snav a.l.on{color:var(--accent);border-bottom-color:var(--accent)}
@media(max-width:520px){.snav .in{gap:14px;padding:11px 13px}
  .snav .wm{letter-spacing:.2em;font-size:10px}}
.sftr{max-width:820px;margin:0 auto;padding:26px 16px 54px;
  border-top:1px solid var(--line);display:flex;flex-wrap:wrap;
  gap:8px 18px;align-items:baseline}
.sftr a{font-family:var(--mono);font-size:10px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--faint);text-decoration:none}
.sftr a:hover{color:var(--dim)}
.sftr .sp{margin-left:auto}
.sftr .sp a{color:var(--accent-d)}
.sftr .sp a:hover{color:var(--accent)}
</style>"""

# Typography for the public pages that are mostly prose. "/" does NOT use this.
PAGE_CSS = r"""<style>
:root{--serif:'Libre Caslon Text',Georgia,serif}
.app{max-width:820px;padding-top:0}
@media(max-width:679px){.app{max-width:100%}}
.pg{padding:0 16px 20px}
.pg h1{font-family:var(--serif);font-weight:400;color:var(--ink);
  font-size:clamp(28px,4.8vw,46px);line-height:1.16;letter-spacing:-.01em;
  margin:0 0 20px;max-width:19ch}
.pg h1 em{font-style:italic;color:var(--accent)}
.pg .lede{font-size:clamp(16px,2vw,19px);line-height:1.62;color:var(--dim);
  max-width:54ch;margin:0}
.pg .lede b{color:var(--ink);font-weight:600}
.pg section{padding:clamp(28px,5vw,46px) 0;border-top:1px solid var(--line)}
.pg section:first-of-type{margin-top:clamp(34px,7vh,68px)}
.pg .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--accent);margin-bottom:20px}
.pg h2{font-family:var(--serif);font-weight:400;font-size:clamp(21px,3vw,29px);
  line-height:1.25;color:var(--ink);margin:0 0 16px;max-width:24ch}
.pg p{font-size:clamp(14.5px,1.75vw,16.5px);line-height:1.68;color:var(--dim);
  max-width:60ch;margin:0 0 15px}
.pg p b{color:var(--ink);font-weight:600}
.pg p a{color:var(--accent);text-decoration:none;border-bottom:1px solid var(--accent-d)}
.pg p a:hover{border-bottom-color:var(--accent)}
.pg .small{font-size:12.5px;line-height:1.6;color:var(--faint);max-width:66ch}
.pg .small a{color:var(--faint);border-bottom:1px solid var(--line2)}
.pg .small a:hover{color:var(--dim)}
/* the one claim allowed to be set apart */
.pg blockquote{margin:22px 0;padding:0 0 0 20px;border-left:2px solid var(--accent);
  font-family:var(--serif);font-size:clamp(15.5px,2vw,18px);line-height:1.55;
  color:var(--ink);max-width:56ch}
.pg blockquote b{font-weight:600}
/* a fact stated on its own, used where a paragraph would bury it */
.pg .stat{display:grid;grid-template-columns:1fr;gap:1px;background:var(--line);
  border:1px solid var(--line);margin:22px 0}
@media(min-width:620px){.pg .stat.two{grid-template-columns:1fr 1fr}
  .pg .stat.three{grid-template-columns:repeat(3,1fr)}}
.pg .stat div{background:var(--bg);padding:15px 16px 17px}
.pg .stat .k{font-family:var(--mono);font-size:9px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--faint);margin-bottom:7px}
.pg .stat .v{font-family:var(--hud);font-weight:700;font-size:15px;
  line-height:1.35;color:var(--ink)}
.pg .stat .v.q{color:var(--dim);font-weight:400;font-size:14px}
</style>"""


def nav_html(current: str) -> str:
    links = "".join(
        f'<a class="l{" on" if h == current else ""}" href="{h}">{lbl}</a>'
        for h, lbl in SITE_NAV)
    return ('<nav class="snav"><div class="in">'
            '<a class="wm" href="/">LENS</a>' + links + '</div></nav>')


def footer_html() -> str:
    """Public footer. The cockpit link is last and quieter than everything
    else on purpose — it is a door, not an invitation."""
    return ('<footer class="sftr">'
            '<a href="/">Home</a><a href="/about">About</a>'
            '<a href="/philosophy">Philosophy</a>'
            '<span class="sp"><a href="/evidence">The evidence →</a></span>'
            '</footer>')


def site_shell(path: str, label: str, body: str, *, extra_css: str = "") -> str:
    """A public page: front-door typography, public nav, no cockpit chrome."""
    from .theme import shell
    return shell(path, label,
                 nav_html(path) + '<div class="pg">' + body + '</div>' + footer_html(),
                 head_extra=FONT + NAV_CSS + PAGE_CSS + extra_css,
                 bare=True)
