"""LENS /manual — the repo's markdown files, rendered in the cockpit.

Not `/docs`: FastAPI owns that path for the OpenAPI reference, and the README
sends people there. Registering a second route on it does not error, it just
silently loses — the Swagger page renders instead of yours.

Renders live from disk rather than generating static HTML copies, for one
reason: a copy is wrong the moment CHANGELOG.md is appended to, and a docs page
that lies is worse than no docs page. Same reasoning as `/style`, which BRAND.md
already points at as its live twin.

The markdown subset is deliberately small — headings, tables, fenced code,
blockquotes, lists, rules, and inline bold/italic/code/links. That is exactly
what these five files use (checked, not assumed). A full CommonMark dependency
in a trading app, for a documentation page, is weight this repo doesn't need;
`requirements.txt` is short on purpose. If a doc ever needs more than this,
the honest fix is to add the dependency, not to keep growing the renderer.
"""
import html
import re

from .paths import ROOT
from .theme import shell

DOCS = [
    ("readme",    "README",    "README.md",     "what it is, how to run it"),
    ("plan",      "Plan",      "LENS_PLAN.md",  "the build plan + open items"),
    ("changelog", "Changelog", "CHANGELOG.md",  "what shipped, and what broke"),
    ("product",   "Product",   "PRODUCT.md",    "who it's for, what it's for"),
    ("brand",     "Brand",     "BRAND.md",      "how it should look and sound"),
]
BY_KEY = {k: (label, fn, blurb) for k, label, fn, blurb in DOCS}


# ── markdown ─────────────────────────────────────────────────────────────────

def _inline(s: str) -> str:
    """Inline spans, on already-escaped text. Code first — its contents must not
    then be re-processed for bold/italic, or `**kwargs` in a code span renders
    as bold."""
    out, parts = [], re.split(r"(`[^`]+`)", s)
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{part[1:-1]}</code>")
            continue
        part = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', part)
        part = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", part)
        part = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", part)
        out.append(part)
    return "".join(out)


def _table(rows: list[str]) -> str:
    """rows[1] is the |---|---| separator, which carries no content."""
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]
    head = "".join(f"<th>{_inline(c)}</th>" for c in cells(rows[0]))
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells(r)) + "</tr>"
        for r in rows[2:])
    return f'<div class="tw"><table><tr>{head}</tr>{body}</table></div>'


def render_md(text: str) -> str:
    lines = html.escape(text).split("\n")
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):                      # fenced code, verbatim
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            i += 1
            continue

        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i + 1]):
            buf = []
            while i < len(lines) and lines[i].startswith("|"):
                buf.append(lines[i]); i += 1
            out.append(_table(buf))
            continue

        if re.match(r"^(-{3,}|_{3,})\s*$", ln):
            out.append("<hr>"); i += 1; continue

        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>"); i += 1; continue

        if ln.startswith("&gt; "):                    # blockquote (escaped '>')
            buf = []
            while i < len(lines) and lines[i].startswith("&gt;"):
                buf.append(lines[i][5:] if lines[i].startswith("&gt; ") else lines[i][4:])
                i += 1
            out.append(f"<blockquote>{render_md_inline_block(buf)}</blockquote>")
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", ln)
        if m:
            ordered = not m.group(2) in ("-", "*")
            tag = "ol" if ordered else "ul"
            buf = []
            while i < len(lines):
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not mm:
                    # a wrapped continuation line belongs to the previous item
                    if buf and lines[i].strip() and lines[i].startswith(" "):
                        buf[-1] += " " + lines[i].strip(); i += 1; continue
                    break
                buf.append(mm.group(3)); i += 1
            items = "".join(f"<li>{_inline(b)}</li>" for b in buf)
            out.append(f"<{tag}>{items}</{tag}>")
            continue

        if not ln.strip():
            i += 1; continue

        buf = []                                      # paragraph
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,6} |\||```|&gt; |-{3,}$|\s*([-*]|\d+\.)\s)", lines[i]):
            buf.append(lines[i]); i += 1
        out.append(f"<p>{_inline(' '.join(buf))}</p>")

    return "\n".join(out)


def render_md_inline_block(lines: list[str]) -> str:
    """Blockquote bodies: recurse so a quote can hold headings and lists (the
    ✅ BUILT banners in the archived specs are exactly that)."""
    return render_md("\n".join(lines))


# ── page ─────────────────────────────────────────────────────────────────────

CSS = """
<style>
.docwrap{max-width:860px;margin:0 auto;padding:0 4px 60px}
.docwrap h1{font-size:22px;margin:18px 0 10px;letter-spacing:.02em}
.docwrap h2{font-size:17px;margin:26px 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line2)}
.docwrap h3{font-size:14px;margin:20px 0 6px;color:var(--accent)}
.docwrap h4{font-size:13px;margin:16px 0 4px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.docwrap p{margin:9px 0;line-height:1.65;color:var(--ink)}
.docwrap li{margin:4px 0;line-height:1.6}
.docwrap ul,.docwrap ol{margin:8px 0 8px 20px}
.docwrap code{background:var(--panel3);padding:1px 5px;border-radius:3px;font-size:12px;color:var(--accent)}
.docwrap pre{background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:12px;overflow-x:auto;margin:12px 0}
.docwrap pre code{background:none;padding:0;color:var(--ink);font-size:12px;line-height:1.5}
.docwrap blockquote{border-left:3px solid var(--accent);background:var(--panel);padding:2px 14px;margin:14px 0;border-radius:0 6px 6px 0}
.docwrap hr{border:0;border-top:1px solid var(--line2);margin:22px 0}
.docwrap .tw{overflow-x:auto;margin:12px 0}
.docwrap table{border-collapse:collapse;width:100%;font-size:12px}
.docwrap th{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);color:var(--dim);
  text-transform:uppercase;font-size:10px;letter-spacing:.05em;white-space:nowrap}
.docwrap td{padding:7px 9px;border-bottom:1px solid var(--line2);vertical-align:top}
.docwrap a{color:var(--accent)}
.docnav{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 18px}
.docnav a{padding:6px 12px;border:1px solid var(--line2);border-radius:20px;font-size:12px;
  color:var(--dim);text-decoration:none}
.docnav a.on{border-color:var(--accent);color:var(--accent);background:var(--accent-d)}
.docmeta{font-size:11px;color:var(--dim);margin:0 0 16px}
</style>
"""


def render(doc: str = "readme") -> str:
    if doc not in BY_KEY and doc != "glossary":
        doc = "readme"

    if doc == "glossary":
        # The glossary was its own route until the 2026-08-03 merge. It is the
        # one tab whose source isn't a file on disk — it's static HTML that
        # mirrors calculator.py — so it can't go through render_md().
        from .glossary_page import BODY
        body, meta = BODY, "plain-English reference · every metric in the model"
    else:
        label, filename, _ = BY_KEY[doc]
        path = ROOT / filename
        try:
            body = render_md(path.read_text())
            meta = f"{filename} · {len(path.read_text().splitlines())} lines"
        except OSError as e:
            body = f"<p class='r'>Could not read {html.escape(filename)}: {html.escape(str(e))}</p>"
            meta = filename

    tabs = [(k, lbl, b) for k, lbl, _fn, b in DOCS]
    tabs.append(("glossary", "Glossary", "what every metric means, in English"))
    nav = "".join(
        f'<a href="/manual?doc={k}" class="{"on" if k == doc else ""}" title="{b}">{lbl}</a>'
        for k, lbl, b in tabs)

    return shell("/manual", "Manual",
                 CSS + f'<div class="docnav">{nav}</div>'
                 f'<div class="docmeta">{meta}'
                 + ('' if doc == "glossary" else
                    ' — rendered live from the repo, so it cannot go stale')
                 + '</div>'
                 f'<div class="docwrap">{body}</div>',
                 meta="the written record")
