"""LENS /research — the lab notebook, rendered live from disk.

Every experiment in research/ documents itself: the module docstring states
the question (and, once run, the verdict), and its results/<name>.json holds
the numbers that back it. Until now both lived only in the repo, so "tested,
it failed" was an act of faith for anyone not reading source. This page
renders the pairing straight from disk — same philosophy as /manual: a live
read can't go stale, and an evidence page that lies is worse than none.

Layout: one card per experiment, newest first. The card's first line is the
script's own opening sentence — the question it asked. Expanders hold the
full writeup and the raw JSON. Scripts that haven't produced a results file
yet are listed at the bottom as "no artifact yet"; results whose script has
been deleted still render (the evidence outlives the tool).
"""
import ast
import html
import json

from .paths import RESULTS, ROOT
from .theme import shell

RESEARCH = ROOT / "research"
INLINE_CAP = 100_000   # bigger results render as a link to the raw file, not inline


def _docstring(py_path):
    try:
        return ast.get_docstring(ast.parse(py_path.read_text())) or ""
    except (OSError, SyntaxError):
        return ""


def _experiments():
    """[{name, generated, summary, doc, json_text}] newest first, plus the
    list of scripts with no results artifact yet."""
    cards, no_artifact = [], []
    seen = set()
    for jp in sorted(RESULTS.glob("*.json")):
        name = jp.stem
        seen.add(name)
        try:
            raw = jp.read_text()
            data = json.loads(raw)
        except (OSError, ValueError):
            raw, data = "", {}
        gen = data.get("generated", "") if isinstance(data, dict) else ""
        doc = _docstring(RESEARCH / f"{name}.py")
        summary = doc.strip().splitlines()[0] if doc.strip() else "(no writeup — script missing or undocumented)"
        cards.append({
            "name": name,
            "generated": gen or "",
            "mtime": jp.stat().st_mtime,
            "summary": summary,
            "doc": doc,
            "data": data,
            "json_text": json.dumps(data, indent=2) if data else raw,
        })
    for sp in sorted(RESEARCH.glob("*.py")):
        if sp.stem.startswith("_") or sp.stem in seen:
            continue
        doc = _docstring(sp)
        no_artifact.append({
            "name": sp.stem,
            "summary": doc.strip().splitlines()[0] if doc.strip() else "(undocumented)",
            "doc": doc,
        })
    cards.sort(key=lambda c: (c["generated"], c["mtime"]), reverse=True)
    return cards, no_artifact


def _card(c) -> str:
    date = f'<span class="rs-date">{html.escape(c["generated"])}</span>' if c["generated"] else ""
    doc_block = (f'<details><summary>full writeup</summary>'
                 f'<pre class="rs-doc">{html.escape(c["doc"])}</pre></details>'
                 if c["doc"] else "")
    if not c["json_text"]:
        json_block = ""
    elif len(c["json_text"]) > INLINE_CAP:
        json_block = (f'<div class="rs-none"><a href="/api/research/{html.escape(c["name"])}.json">'
                      f'raw result — results/{html.escape(c["name"])}.json '
                      f'({len(c["json_text"]) // 1024} KB)</a></div>')
    else:
        json_block = (f'<details><summary>raw result — results/{html.escape(c["name"])}.json</summary>'
                      f'<pre class="rs-json">{html.escape(c["json_text"])}</pre></details>')
    # A one-word verdict badge, same vocabulary as /evidence's other sections
    # (badge.approved/rejected on /evidence#luck) — decision-useful because it
    # answers "did this one land?" without opening the JSON, for the one field
    # that recurs often enough across ad-hoc experiments to be worth a scan:
    # an explicit survived/passed flag, or common p-value fields.
    verdict = _verdict_badge(c.get("data") if isinstance(c.get("data"), dict) else None)
    return (f'<div class="rs-card {verdict["cls"]}">'
            f'<div class="rs-head"><b>{html.escape(c["name"])}</b>{verdict["badge"]}{date}</div>'
            f'<div class="rs-sum">{html.escape(c["summary"])}</div>'
            f'{doc_block}{json_block}</div>')


def _verdict_badge(data: dict | None) -> dict:
    """Best-effort read of a survived/p-value field, so a card that already
    states its own verdict shows it as a colored badge instead of requiring a
    click into raw JSON. Most experiments have no such field — that's the
    normal case, not a failure, and gets no badge at all rather than a guess."""
    if not data:
        return {"cls": "", "badge": ""}
    for key in ("survived", "passed", "beats_luck"):
        v = data.get(key)
        if isinstance(v, bool):
            return ({"cls": "rs-ok", "badge": ' <span class="badge approved">survived</span>'}
                    if v else
                    {"cls": "rs-bad", "badge": ' <span class="badge rejected">did not survive</span>'})
    for key in ("p", "p_value", "perm_p"):
        v = data.get(key)
        if isinstance(v, (int, float)):
            return ({"cls": "rs-ok", "badge": ' <span class="badge approved">beats luck</span>'}
                    if v < 0.05 else
                    {"cls": "rs-bad", "badge": ' <span class="badge rejected">could be luck</span>'})
    return {"cls": "", "badge": ""}


CSS = """
.rs-intro{color:var(--dim);max-width:72ch;margin-bottom:18px}
.rs-card{border:1px solid var(--line);border-left:3px solid var(--line);border-radius:8px;padding:12px 14px;margin-bottom:12px}
.rs-card.rs-ok{border-left-color:var(--long)}
.rs-card.rs-bad{border-left-color:var(--short)}
.rs-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.rs-date{color:var(--faint);font-size:12px;white-space:nowrap}
.rs-sum{color:var(--dim);margin:4px 0 6px}
.rs-card details{margin-top:6px}
.rs-card summary{cursor:pointer;color:var(--accent);font-size:13px}
.rs-doc,.rs-json{white-space:pre-wrap;overflow-x:auto;font-size:12px;line-height:1.5;
  background:var(--bg2,rgba(128,128,128,.07));border-radius:6px;padding:10px;margin-top:6px}
.rs-none{color:var(--faint);font-size:13px;margin:4px 0}
"""


def parts() -> dict:
    """Body + CSS. CSS is returned separately rather than inlined in the body
    so the merge can scope it to its own section."""
    cards, pending = _experiments()
    body = ['<div class="rs-intro">Every experiment run against the book or the candle history, '
            'newest first — the question it asked in its own words, and the raw numbers it produced. '
            'Rendered live from <code>research/</code> and <code>results/</code> on every load; '
            'nothing here is summarised by hand.</div>']
    body += [_card(c) for c in cards]
    if pending:
        body.append('<h4 style="margin-top:22px">scripts with no result artifact yet</h4>')
        for p in pending:
            body.append(f'<div class="rs-none"><b>{html.escape(p["name"])}</b> — '
                        f'{html.escape(p["summary"])}</div>')
    body.append(f'<div class="foot">{len(cards)} experiments with artifacts · '
                f'{len(pending)} scripts without · CLI twins live in research/</div>')
    return {"body": "\n".join(body), "css": "<style>" + CSS + "</style>"}


def render() -> str:
    p = parts()
    return shell("/research", "Research", p["body"], head_extra=p["css"],
                 meta="the lab notebook")
