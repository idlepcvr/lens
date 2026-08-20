#!/usr/bin/env python3
"""Give every Markdown doc in this repo an HTML twin you can click and skim.

Same basename, same folder, and the Markdown links its twin at the top, so
neither half is ever orphaned. Output is offline-absolute — no CDN, no webfont,
no build step — and its colours mirror the LENS tokens in app/theme.py.

Stdlib only, deliberately: this repo is a live trading app, and a doc generator
is not a reason to add a dependency to the venv that runs it.

    python3 tools/md2html.py            # every *.md in the repo root
    python3 tools/md2html.py README.md  # just this one

Re-running is safe: it overwrites the twin and never double-inserts the link.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = "[Open as HTML]({name}.html)"

CSS = """
:root{--bg:#06080c;--panel:#0b0f16;--panel2:#10151e;--line:#192232;--line2:#28344a;
      --ink:#e8eef8;--dim:#828ea6;--long:#1fd989;--short:#ff5468;--amber:#f6ad3c;
      --accent:#5b9dff;
      --mono:'JetBrains Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--mono);
     font-size:14px;line-height:1.7;padding:40px 20px}
main{max-width:82ch;margin:0 auto}
h1{font-size:25px;letter-spacing:-.01em;margin:0 0 22px;line-height:1.25}
h2{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);
   margin:38px 0 13px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:15px;margin:26px 0 9px;color:var(--ink)}
h4{font-size:13px;margin:20px 0 7px;color:var(--dim)}
p{margin:0 0 13px}
ul,ol{margin:0 0 13px;padding-left:22px}
li{margin-bottom:7px}
li>ul,li>ol{margin:7px 0 0}
strong{color:var(--ink);font-weight:700}
em{color:var(--dim);font-style:italic}
a{color:var(--accent)}
code{background:var(--panel2);border:1px solid var(--line);border-radius:4px;
     padding:1px 5px;font-size:12.5px;color:var(--accent);word-break:break-word}
pre{background:var(--panel);border:1px solid var(--line);border-radius:8px;
    padding:13px 15px;overflow-x:auto;margin:0 0 15px}
pre code{background:none;border:0;padding:0;color:var(--ink);font-size:12.5px}
blockquote{margin:0 0 14px;padding:2px 0 2px 15px;border-left:1px solid var(--line2);
           color:var(--dim)}
hr{border:0;border-top:1px solid var(--line);margin:30px 0}
.tw{overflow-x:auto;margin:0 0 16px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-size:10px;letter-spacing:.1em;text-transform:uppercase;
   color:var(--dim);padding:0 14px 8px 0;border-bottom:1px solid var(--line);
   white-space:nowrap}
td{padding:8px 14px 8px 0;border-bottom:1px solid var(--line);
   color:var(--ink);vertical-align:top}
tr:last-child td{border-bottom:none}
footer{margin-top:46px;padding-top:14px;border-top:1px solid var(--line);
       color:var(--dim);font-size:11.5px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def inline(t: str) -> str:
    """Escape first, then re-introduce only the spans we mean. Code spans are
    pulled out before anything else so `**` inside them stays literal."""
    spans: list[str] = []

    def stash(m):
        spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(spans)-1}\x00"

    t = re.sub(r"`([^`]+)`", stash, t)
    t = html.escape(t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], t)


def _row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    list_stack: list[tuple[int, str]] = []          # (indent, tag)

    def close_lists(to_indent: int = -1):
        while list_stack and list_stack[-1][0] > to_indent:
            out.append(f"</{list_stack.pop()[1]}>")

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            close_lists()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            continue

        # table: a header row followed by a --- separator
        if (stripped.startswith("|") and i + 1 < n
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1])):
            close_lists()
            head = _row(line)
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(_row(lines[i]))
                i += 1
            t = ["<div class=tw><table><thead><tr>"]
            t += [f"<th>{inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue

        if not stripped:
            close_lists()
            i += 1
            continue

        if re.match(r"^(---+|\*\*\*+|___+)$", stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_lists()
            lvl = min(len(m.group(1)), 4)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if stripped.startswith("> "):
            close_lists()
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(buf)) + "</blockquote>")
            continue

        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            tag = "ul" if m.group(2) in "-*+" else "ol"
            close_lists(indent)
            if not list_stack or list_stack[-1][0] < indent:
                out.append(f"<{tag}>")
                list_stack.append((indent, tag))
            out.append(f"<li>{inline(m.group(3))}</li>")
            i += 1
            continue

        # paragraph — fold continuation lines, and lazy-continue a list item
        buf = [stripped]
        i += 1
        while i < n and lines[i].strip() and not re.match(
                r"^\s*([-*+]|\d+[.)])\s|^\s*(#{1,6})\s|^\s*```|^\s*\||^\s*>",
                lines[i]) and not re.match(r"^(---+|\*\*\*+|___+)$", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        text = inline(" ".join(buf))
        if list_stack and out and out[-1].endswith("</li>"):
            out[-1] = out[-1][:-5] + " " + text + "</li>"
        else:
            close_lists()
            out.append(f"<p>{text}</p>")

    close_lists()
    return "\n".join(out)


def page(title: str, body: str, src: str) -> str:
    return (f"<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            f"<title>LENS // {html.escape(title)}</title>\n<style>{CSS}</style></head>\n"
            f"<body><main>\n{body}\n<footer>Twin of <code>{html.escape(src)}</code> — "
            f"edit the Markdown, then run <code>python3 tools/md2html.py</code>.</footer>\n"
            f"</main></body></html>\n")


def ensure_link(path: Path) -> None:
    """Put the twin link under the first heading, once."""
    md = path.read_text(encoding="utf-8")
    link = LINK.format(name=path.stem)
    if link in md:
        return
    lines = md.split("\n")
    for idx, l in enumerate(lines):
        if l.startswith("# "):
            lines.insert(idx + 1, "\n" + link)
            path.write_text("\n".join(lines), encoding="utf-8")
            return
    path.write_text(link + "\n\n" + md, encoding="utf-8")


def build(path: Path) -> Path:
    ensure_link(path)
    md = path.read_text(encoding="utf-8")
    title = next((l[2:].strip() for l in md.split("\n") if l.startswith("# ")), path.stem)
    out = path.with_suffix(".html")
    out.write_text(page(title, convert(md), path.name), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or sorted(ROOT.glob("*.md"))
    for p in targets:
        if not p.exists():
            print(f"  skip {p} (missing)")
            continue
        print(f"  {p.name:16s} → {build(p).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
