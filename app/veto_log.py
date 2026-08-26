"""Record the trades he takes against the scanner's judgement, and why.

An outright block throws away the most interesting signal in the system. When
the scanner says NONE or VETO and he still wants in, his brain has picked up on
something the rules do not encode — and until now that read was either lost, or
executed on the phone where nothing could see it.

So the veto is a question, not a wall: state what you see, and the trade goes
through with the reasoning attached. Later that gives an answerable question
nothing else in LENS can ask — *do his overrides beat the rules, or fund them?*
Every row here is one labelled example, with the outcome arriving on sync.

# ponytail: table created on first write, not in init_db. It is append-only and
# read by nothing on the hot path, so a lazy CREATE costs one statement and
# avoids touching a schema every page load depends on.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .database import _conn

MIN_REASON = 15          # a shrug is not a thesis

_DDL = """
CREATE TABLE IF NOT EXISTS veto_overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    direction       TEXT,
    entry           REAL,
    size_btc        REAL,
    leverage        REAL,
    take_profit     REAL,
    stop_loss       REAL,
    setup_tag       TEXT,
    veto_reasons    TEXT,
    user_reason     TEXT    NOT NULL,
    context         TEXT,
    linked_trade_id INTEGER
)
"""


def valid_reason(reason: Optional[str]) -> bool:
    return bool(reason) and len(reason.strip()) >= MIN_REASON


def record(direction: str, size_btc: float, *, entry=None, leverage=None,
           take_profit=None, stop_loss=None, setup_tag=None,
           veto_reasons=None, user_reason: str = "", context: dict | None = None) -> int:
    c = _conn()
    c.execute(_DDL)
    cur = c.execute(
        """INSERT INTO veto_overrides
           (ts, direction, entry, size_btc, leverage, take_profit, stop_loss,
            setup_tag, veto_reasons, user_reason, context)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(), direction, entry, size_btc, leverage,
         take_profit, stop_loss, setup_tag,
         json.dumps(veto_reasons or []), (user_reason or "").strip(),
         json.dumps(context or {})))
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid


def _parse(rows) -> list[dict]:
    out = []
    for r in rows:
        d = dict(r)
        for k in ("veto_reasons", "context"):
            try:
                d[k] = json.loads(d[k] or "null")
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


def recent(limit: int = 50) -> list[dict]:
    c = _conn()
    c.execute(_DDL)
    rows = c.execute("SELECT * FROM veto_overrides ORDER BY id DESC LIMIT ?",
                     (limit,)).fetchall()
    c.close()
    return _parse(rows)


def for_trade(trade_id: int) -> dict | None:
    """The override record for one trade, if it exists — his typed reason for
    taking it against the scanner. Exposed via GET /api/veto-overrides before
    2026-08-27 only as a raw list with no per-trade filter and no page ever
    rendered it: "that information is lost in transit" (his words, correct)."""
    c = _conn()
    c.execute(_DDL)
    row = c.execute("SELECT * FROM veto_overrides WHERE linked_trade_id = ? "
                    "ORDER BY id DESC LIMIT 1", (trade_id,)).fetchone()
    c.close()
    return _parse([row])[0] if row else None
