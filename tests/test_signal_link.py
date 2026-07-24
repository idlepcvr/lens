"""G3 — fills auto-link to the signal that caused them.

Cases are lifted from the two links Lucky made by hand; the tolerances exist
because of them. Run: python test_signal_link.py
"""
import os, tempfile, sqlite3

_tmp = tempfile.mkdtemp()

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
import app.database as db
db.DB_PATH = os.path.join(_tmp, "t.db")
db.init_db()


def _signal(sid, direction, entry, decided_at, status="approved"):
    c = db._conn()
    c.execute(
        "INSERT INTO signals (signal_id, strategy_name, strategy_version, received_at,"
        " symbol, direction, entry_price, status, decided_at)"
        " VALUES (?,'S1','v1',?,'BTC/USD',?,?,?,?)",
        (sid, decided_at, direction, entry, status, decided_at))
    c.commit(); c.close()


def _fill(direction, entry, opened_at, order_id):
    return db.upsert_exchange_trade({
        "direction": direction, "entry": entry, "size": 0.01, "exit": entry * 1.01,
        "opened_at": opened_at, "closed_at": opened_at, "kraken_order_id": order_id,
        "symbol": "BTC/USD:USD", "pnl": 1.0, "fees": 0.1,
    })


def _linked(tid):
    c = db._conn()
    r = c.execute("SELECT linked_signal_id FROM trades WHERE id=?", (tid,)).fetchone()
    c.close(); return r["linked_signal_id"]


# 1. the real trade-550 case: fill 15s after the decision, entry 1.12% away.
#    A 1% tolerance (the original spec) would miss this. It must link.
_signal("s-550", "short", 61078.0, "2026-06-24T16:33:18.058284")
t = _fill("short", 60392.0, "2026-06-24T16:33:33.387000+00:00", "o550")
assert _linked(t.id) == "s-550", "1.12% entry drift must still link"

# 2. one signal, one trade: a split order's second fill can't re-claim it.
t2 = _fill("short", 60390.0, "2026-06-24T16:34:00+00:00", "o550b")
assert _linked(t2.id) is None, "signal already claimed"

# 3. a decision AFTER the fill did not cause the fill.
_signal("s-late", "long", 60000.0, "2026-07-01T12:00:00")
t3 = _fill("long", 60000.0, "2026-07-01T11:00:00+00:00", "o-late")
assert _linked(t3.id) is None, "decision must precede fill"

# 4. cross-symbol signal quoting a far-away book (the 95234-vs-76655 case).
_signal("s-far", "short", 95234.5, "2026-05-26T04:51:36")
t4 = _fill("short", 76655.0, "2026-05-26T09:00:09+00:00", "o-far")
assert _linked(t4.id) is None, "24% entry gap is not the same trade"

# 5. opposite direction never links.
_signal("s-dir", "long", 62000.0, "2026-07-02T10:00:00")
t5 = _fill("short", 62000.0, "2026-07-02T10:05:00+00:00", "o-dir")
assert _linked(t5.id) is None, "direction must match"

# 6. stale decision (>6h) didn't cause this fill.
_signal("s-stale", "long", 62000.0, "2026-07-03T01:00:00")
t6 = _fill("long", 62000.0, "2026-07-03T09:00:00+00:00", "o-stale")
assert _linked(t6.id) is None, "6h window"

# 7. non-approved signals are invisible.
_signal("s-rej", "long", 63000.0, "2026-07-04T10:00:00", status="rejected")
t7 = _fill("long", 63000.0, "2026-07-04T10:05:00+00:00", "o-rej")
assert _linked(t7.id) is None, "only approved signals link"

# 8. backfill is idempotent and never re-points a link.
before = _linked(t.id)
assert db.backfill_signal_links() == 0, "nothing left to link"
assert _linked(t.id) == before, "backfill must not re-point an existing link"

# 9. both sides of the link agree.
c = db._conn()
assert c.execute("SELECT linked_trade_id FROM signals WHERE signal_id='s-550'"
                 ).fetchone()["linked_trade_id"] == t.id, "signal must point back"
c.close()

print("ok — 9 checks passed")
