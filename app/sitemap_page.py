"""LENS /sitemap — every page in one place.

Built from the live route table (passed in) cross-referenced against the nav
list, so it auto-includes pages that aren't in the nav (the orphans).
"""

from .theme import shell, NAV_HEDGE

_CSS = r"""<style>
.sm{max-width:1000px;margin:0 auto;padding:6px 14px 60px}
.sm h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.sm .sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.sm .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.sm .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:15px 17px}
.sm .card-title{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--dim);padding-bottom:9px;border-bottom:1px solid var(--line);margin-bottom:10px}
.sm a.row{display:flex;justify-content:space-between;align-items:baseline;gap:10px;padding:5px 0;text-decoration:none;color:var(--ink);font-size:13px}
.sm a.row:hover{color:var(--accent)}
.sm a.row .p{font-family:var(--mono);font-size:11px;color:var(--faint)}
</style>"""


def _label(path: str, labels: dict) -> str:
    if path in labels:
        return labels[path]
    return path.strip("/").replace("-", " ").replace("/", " · ").title() or "Home"


def render(paths: list[str]) -> str:
    labels = dict(NAV_HEDGE)
    hedge = {h for h, _ in NAV_HEDGE}

    # Pages with no nav chip on purpose (engine cards, not chips).
    # /regime retired 2026-09-05 — merged into /analytics, see LEGACY_ROUTES
    # in main.py. Kept as an empty set (not deleted) in case a future page
    # earns this category again.
    ENGINES: set[str] = set()

    groups: dict[str, list[str]] = {
        "Hedge": [], "Engines": [], "Reference": []
    }
    for p in paths:
        if p in hedge:
            groups["Hedge"].append(p)
        elif p in ENGINES:
            groups["Engines"].append(p)
        else:
            groups["Reference"].append(p)

    cards = []
    for title in ("Hedge", "Engines", "Reference"):
        items = sorted(groups[title], key=lambda p: _label(p, labels).lower())
        if not items:
            continue
        rows = "".join(
            f'<a class="row" href="{p}"><span>{_label(p, labels)}</span><span class="p">{p}</span></a>'
            for p in items
        )
        cards.append(f'<div class="card"><div class="card-title">{title}</div>{rows}</div>')

    body = f"""
<div class="sm">
  <h1>Sitemap</h1>
  <div class="sub">Every page in LENS.</div>
  <div class="grid">{''.join(cards)}</div>
</div>"""
    return shell("/sitemap", "Sitemap", body, head_extra=_CSS, meta="all pages")
