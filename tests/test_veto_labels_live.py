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


# ── era scoping (added 2026-07-25) ───────────────────────────────────────
# 469 of 509 trades predate the signal loop. Pooling them is how "fvg_entry is
# the only veto in profit, +€2,010" got reported; live-era only it is -€79 over
# 10 trades. The pre-system trades are NOT deleted — they are the sample the
# veto rules were mined from — they are just not the system's track record.
import sqlite3          # noqa: E402
import tempfile         # noqa: E402
import os               # noqa: E402

from app.setups import SYSTEM_START   # noqa: E402
import app.setups as setups           # noqa: E402

fd, tmp = tempfile.mkstemp(suffix=".db")
os.close(fd)
c = sqlite3.connect(tmp)
c.execute("CREATE TABLE trades (setup_tag TEXT, pnl REAL, opened_at TEXT)")
c.executemany("INSERT INTO trades VALUES (?,?,?)", [
    ("VETO:fvg_entry", 500.0, "2025-05-01"),   # pre-system winner
    ("VETO:fvg_entry", 500.0, "2025-06-01"),   # pre-system winner
    ("VETO:fvg_entry", -20.0, "2026-07-01"),   # live-era loser
])
c.commit(); c.close()

_real, setups.DB_PATH = setups.DB_PATH, tmp
try:
    live = setups.veto_bucket_stats("live")["rules"]["fvg_entry"]
    allt = setups.veto_bucket_stats("all")["rules"]["fvg_entry"]
    # the exact shape of the 2026-07-25 false finding: pooled looks great,
    # live-era says otherwise, and the default must be the honest one
    assert allt == {"n": 3, "pnl": 980, "wr": 67}, allt
    assert live == {"n": 1, "pnl": -20, "wr": 0}, live
    assert setups.veto_bucket_stats()["rules"]["fvg_entry"] == live, \
        "default era must be 'live' — the system's own record, not the mining sample"
    try:
        setups.veto_bucket_stats("recent")
        raise AssertionError("a typo'd era must raise, not silently pool everything")
    except ValueError:
        pass
finally:
    setups.DB_PATH = _real
    os.unlink(tmp)

assert SYSTEM_START == "2026-06-16"
print("ok — veto stats default to the live era; pre-system trades kept, not counted")
