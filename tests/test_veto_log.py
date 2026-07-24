"""Vetoed setups must leave a row.

The bug this locks down (2026-07-24): `emit_signals` dropped every non-clean
match and `run_scan_cli` filtered them out before it — a vetoed setup produced
no row, no notification, no trace. The feed showed longs only for 10 days while
the engine was working correctly, and the veto counterfactual had no
denominator: nobody could ask "would taking the vetoed ones have made money?"

Contract:
  · A vetoed match is STORED, as status='rejected' with reason `veto:<rules>`.
  · It is stored at most ONCE per bar+setup — a persistent context re-scanned
    hourly must not mint a row per run.
  · It is NEVER pending, so run_scan_cli's notify loop never pushes it.
    Blocked is not actionable. This is the line that keeps the phone quiet.
  · A clean match is untouched: still pending, still a fresh id every scan.

Runs against a throwaway DB — never your ledger.

Run: .venv/bin/python3 test_veto_log.py
"""
import os
import tempfile


import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
import app.database as database

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
database.DB_PATH = _tmp.name

import app.discipline as discipline
import app.setups as setups

setups.DB_PATH = _tmp.name          # setups imported the name, not the module
database.init_db()

# Discipline is stubbed to PASS so this file tests the veto path only. Left
# live, its filters are clock-dependent (bleed hours on the Bangkok clock, a
# 5-minute cooldown) and every clean-path assertion below would rot by the hour.
discipline.evaluate = lambda *_a, **_k: None


def scan(matches, bar="2026-07-14T14:00:00+00:00"):
    return {"bar_ts": bar, "close": 60000.0, "matches": matches}


def match(setup, direction, vetoes):
    return {"setup": setup, "direction": direction, "checks": ["a", "b"],
            "vetoes": vetoes, "clean": not vetoes}


# 1. THE BUG. A vetoed match is stored, not dropped, and it names its vetoes.
rows = setups.emit_signals(scan([match("S2", "short", ["slope_against", "pd_raid_fade"])]))
assert len(rows) == 1, f"a vetoed setup must leave a row, got {rows}"
assert rows[0]["status"] == "rejected", rows[0]["status"]
assert rows[0]["rejection_reason"] == "veto:slope_against,pd_raid_fade", rows[0]["rejection_reason"]
assert rows[0]["trigger_type"] == "S2", "the setup that matched must still be identifiable"

# 2. Blocked never notifies. run_scan_cli pushes only status == 'pending', so
#    the guarantee is simply that no vetoed row is ever pending.
assert rows[0]["status"] != "pending", "a blocked row must never enter the push path"

# 3. Same bar, re-scanned (cron retry, or a context that persists) → still one
#    row. Without the bar-stamped id this floods the feed hourly.
again = setups.emit_signals(scan([match("S2", "short", ["slope_against", "pd_raid_fade"])]))
assert again == [], f"same bar+setup must dedupe, got {again}"

# 4. Next bar → a new row. One row per bar per setup IS the denominator; dedupe
#    must not swallow the next hour's evidence.
nxt = setups.emit_signals(scan([match("S2", "short", ["slope_against"])],
                               bar="2026-07-14T15:00:00+00:00"))
assert len(nxt) == 1 and nxt[0]["rejection_reason"] == "veto:slope_against", nxt

# 5. Clean matches are unchanged — pending, and a fresh id every scan (the
#    hourly re-fire is one trade idea, clustered in the UI, not deduped in data).
c1 = setups.emit_signals(scan([match("S3", "long", [])]))
c2 = setups.emit_signals(scan([match("S3", "long", [])]))
assert c1[0]["status"] == "pending" and c2[0]["status"] == "pending", "clean stays pending"
assert c1[0]["signal_id"] != c2[0]["signal_id"], "clean matches keep per-scan ids"

# 6. Mixed bar: the vetoed one is logged AND the clean one still gets through.
#    The old code returned only the clean one; losing either is the regression.
mixed = setups.emit_signals(scan([match("S1", "short", ["ny_pm_kz"]),
                                  match("S5", "long", [])],
                                 bar="2026-07-14T18:00:00+00:00"))
assert len(mixed) == 2, f"both must be emitted, got {len(mixed)}"
assert {r["status"] for r in mixed} == {"rejected", "pending"}, [r["status"] for r in mixed]

# 7. Discipline still governs the clean path — logging vetoes must not become a
#    back door around the filters. And on a vetoed match the veto is the reason
#    reported, not whichever filter also happened to catch it: the reason string
#    is what /signals parses to build a blocked card.
discipline.evaluate = lambda *_a, **_k: "filter:saturday"
gov = setups.emit_signals(scan([match("S3", "long", []),
                                match("S1", "short", ["ny_pm_kz"])],
                               bar="2026-07-14T19:00:00+00:00"))
by_setup = {r["trigger_type"]: r for r in gov}
assert by_setup["S3"]["rejection_reason"] == "filter:saturday", by_setup["S3"]
assert by_setup["S1"]["rejection_reason"] == "veto:ny_pm_kz", by_setup["S1"]
discipline.evaluate = lambda *_a, **_k: None

# ── the ledger stat a blocked card cites ─────────────────────────────────────
conn = database._conn()
for tag, pnl in [("VETO:slope_against,pd_raid_fade", -100.0),
                 ("VETO:pd_raid_fade,slope_against", -54.0),   # same bucket, other order
                 ("S3|VETO:slope_against", 20.0),              # matched-but-vetoed counts
                 ("S1", 500.0)]:                               # clean — must NOT count
    conn.execute("INSERT INTO trades (direction, entry, size, leverage, opened_at, "
                 "closed_at, setup_tag, pnl) VALUES "
                 "('long', 1, 1, 1, '2026-07-01T00:00:00', '2026-07-01T01:00:00', ?, ?)",
                 (tag, pnl))
conn.commit()
conn.close()

stats = setups.veto_bucket_stats()
combo = stats["combos"]["pd_raid_fade,slope_against"]
assert combo["n"] == 2, f"rule order must not split the bucket: {stats['combos']}"
assert combo["pnl"] == -154, combo
assert stats["rules"]["slope_against"]["n"] == 3, "a rule counts every trade it appears in"
assert stats["rules"]["slope_against"]["pnl"] == -134, stats["rules"]["slope_against"]
assert stats["rules"]["slope_against"]["wr"] == 33, stats["rules"]["slope_against"]
assert "S1" not in stats["rules"], "clean trades must never enter the veto ledger"

os.unlink(_tmp.name)
print("ok — vetoed setups leave a row, dedupe per bar, never notify, and cite the ledger")
