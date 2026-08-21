"""Every filesystem path LENS uses, anchored to the repo root.

Before this (2026-07-24) the database path was defined three times — a bare
relative "lens.db" in database.py plus two independent
`Path(__file__).parent.parent / "lens.db"` computations — and the generated
JSONs were opened by bare relative name in five modules. That worked only
because everything ran from the repo root, and it silently made the whole app
cwd-dependent: a cron job or a script one directory down opened a DIFFERENT
(empty) database rather than failing loudly, which is the worst way for this
particular bug to behave.

Anchoring to `__file__` instead of the cwd means every path resolves the same
from anywhere. Define new paths here rather than composing them at the call
site.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"          # the ledger — the one irreplaceable thing here
RESULTS = ROOT / "results"    # generated output: searches, scores, clusters
LOGS = ROOT / "logs"          # systemd + the cron jobs redirect here

DB_PATH = str(DATA / "lens.db")

# Third-party JS served from /assets. Vendored rather than fetched from a CDN:
# this box may have no network, and a chart that silently fails to load takes
# the page's whole answer with it. Apache-2.0, see the file header.
CHARTS_JS = str(ROOT / "app" / "vendor" / "lightweight-charts.js")

# Generated result files. All are rewritten wholesale by their producer, so
# nothing here is precious — but strategy_scores.json IS read live by the
# strategy board on every page render, so it is not merely an artifact.
SEARCH_JSON = str(RESULTS / "strategy_search.json")
SCORES_JSON = str(RESULTS / "strategy_scores.json")
BREEDER_JSON = str(RESULTS / "strategy_breeder.json")


def clusters_json(scope: str) -> str:
    return str(RESULTS / f"strategy_clusters_{scope}.json")


for _d in (DATA, RESULTS, LOGS):
    _d.mkdir(exist_ok=True)
