"""Veto stats are read from the ledger, never baked into the label.

The bug this locks down (2026-07-24): VETO_LABELS carried its numbers inline,
frozen from the original mining pass. `fvg_entry` still read "38% WR,
−€15/trade" on /desk long after the live book had that bucket at +€2,000 over
26 trades — the most-fired veto, and the only one in profit, reported as a
loser. /signals had already worked around it by splitting the stat off the
string; /desk printed it as-is.

Contract:
  · No VETO_LABELS value contains a stat. Any future edit that bakes one in
    fails here rather than drifting silently for a month.
  · veto_label_live() appends the LIVE ledger figures for a known rule.
  · An unseen rule degrades to the bare description — no "0% WR, €0 over 0".

Runs on a hand-built ledger dict — never touches your DB.

Run: .venv/bin/python3 tests/test_veto_labels_live.py
"""
import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd

from app.setups import VETO_LABELS, veto_label_live

# a stat that drifts is the whole bug — none may hide in the descriptions
for rule, desc in VETO_LABELS.items():
    for marker in ("€", "WR", "%", "—"):
        assert marker not in desc, f"{rule} label carries a frozen stat: {desc!r}"

LEDGER = {"rules": {"fvg_entry":   {"n": 26, "pnl": 2000, "wr": 62},
                    "ny_pm_kz":    {"n": 9,  "pnl": -430, "wr": 39}},
          "combos": {}}

# the regression case: profitable bucket must read positive, from the ledger
assert veto_label_live("fvg_entry", LEDGER) == \
    "entry inside FVG retrace — 62% WR, €+2,000 over 26"

# a losing bucket keeps its sign
assert veto_label_live("ny_pm_kz", LEDGER) == \
    "NY PM 18–21 UTC, your worst hours — 39% WR, €-430 over 9"

# known rule, no trades yet → description only, no fake zeroes
assert veto_label_live("sweep_fade", LEDGER) == "fading a liquidity sweep"

# unknown rule → its own name, never a KeyError on a live desk render
assert veto_label_live("not_a_rule", LEDGER) == "not_a_rule"

# empty ledger (the DB-read-failed path) degrades every rule, blanks nothing
for rule in VETO_LABELS:
    assert veto_label_live(rule, {"rules": {}, "combos": {}}) == VETO_LABELS[rule]

print("ok — veto labels carry no frozen stats; live figures come from the ledger")
