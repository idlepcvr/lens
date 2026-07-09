"""
SQLite CRUD layer for LENS.

Tables (LENS v1 scope, per LENS_PLAN.md):
  trades, transfers, daily_snapshots, signals

Signal feature schema is locked — see LENS_PLAN.md `Feature Schema`.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from .models import TradeCreate, TradeUpdate, TradeResponse

DB_PATH = "lens.db"


# ─── Connection / schema ──────────────────────────────────────────────────────

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 10000")  # wait, don't instantly "database is locked"
    c.execute("PRAGMA journal_mode = WAL")    # readers + one writer coexist (sync loop vs UI writes)
    return c


def init_db():
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol            TEXT    NOT NULL DEFAULT 'BTC/USD:USD',
            direction         TEXT    NOT NULL,
            entry             REAL    NOT NULL,
            size              REAL    NOT NULL,
            leverage          REAL    NOT NULL,
            tp                REAL,
            sl                REAL,
            exit              REAL,
            pnl               REAL,
            fees              REAL,
            notes             TEXT,
            opened_at         TEXT    NOT NULL,
            closed_at         TEXT,
            followed_plan     INTEGER,
            followed_strategy INTEGER,
            balance_after     REAL,
            kraken_order_id   TEXT    UNIQUE,
            venue             TEXT    DEFAULT 'manual',
            contract          TEXT,
            market_type       TEXT,
            fill_type         TEXT,
            order_type        TEXT,
            funding_cost      REAL,
            fill_uuid         TEXT,
            fill_count        INTEGER,
            linked_signal_id  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trades_opened_at      ON trades(opened_at);
        CREATE INDEX IF NOT EXISTS idx_trades_closed_at      ON trades(closed_at);
        CREATE INDEX IF NOT EXISTS idx_trades_venue          ON trades(venue);
        CREATE INDEX IF NOT EXISTS idx_trades_linked_signal  ON trades(linked_signal_id);

        CREATE TABLE IF NOT EXISTS transfers (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            kraken_id     TEXT    UNIQUE,
            transfer_type TEXT,
            asset         TEXT,
            amount        REAL,
            balance_after REAL,
            ts            TEXT,
            venue         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_transfers_ts ON transfers(ts);

        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date    TEXT UNIQUE,
            eur_balance      REAL,
            btc_balance      REAL,
            btc_price_usd    REAL,
            portfolio_usd    REAL,
            unrealized_pnl   REAL,
            margin_used      REAL,
            available_margin REAL
        );

        -- Signals: locked schema per LENS_PLAN.md ─────────────────────────────
        CREATE TABLE IF NOT EXISTS signals (
            -- Identity
            signal_id         TEXT PRIMARY KEY,           -- UUID
            strategy_name     TEXT NOT NULL,
            strategy_version  TEXT NOT NULL,
            received_at       TEXT NOT NULL,

            -- Context
            symbol            TEXT NOT NULL,
            venue             TEXT,
            session_utc       TEXT,                       -- asia|london|ny|off-hours
            btc_1d_trend      TEXT,
            btc_1w_trend      TEXT,
            atr_14d_pct       REAL,

            -- Setup
            trigger_type      TEXT,
            htf_bias          TEXT,
            mtf_confluence    TEXT,                       -- JSON array
            confluence_count  INTEGER,

            -- Trade plan
            direction          TEXT,
            entry_price        REAL,
            stop_price         REAL,
            target_price       REAL,
            suggested_size_pct REAL,
            suggested_leverage REAL,
            expected_rr        REAL,

            -- Decision (filled at approve/reject)
            status            TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|expired
            your_conviction   INTEGER,                          -- 1-5
            rejection_reason  TEXT,
            decided_at        TEXT,

            -- Execution linkage (filled by sync, week 5)
            linked_trade_id   INTEGER,

            -- Outcome (filled when trade closes, week 5)
            outcome           TEXT,                              -- win|loss|breakeven|open
            r_realized        REAL,
            pnl_eur           REAL,
            hold_duration_min INTEGER,

            -- Optional enrichment (week 6)
            screenshot_path   TEXT,
            notes             TEXT,

            FOREIGN KEY (linked_trade_id) REFERENCES trades(id)
        );
        CREATE INDEX IF NOT EXISTS idx_signals_status        ON signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_strategy      ON signals(strategy_name);
        CREATE INDEX IF NOT EXISTS idx_signals_received_at   ON signals(received_at);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol        ON signals(symbol);

        -- Projection plans + actuals ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS projection_plans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'active',
            start_bal   REAL    NOT NULL,
            stop_pct    REAL    NOT NULL,
            tp_pct      REAL    NOT NULL,
            leverage    REAL    NOT NULL,
            win_rate    REAL    NOT NULL,
            tpw         REAL    NOT NULL,
            weeks       REAL    NOT NULL,
            btc_price   REAL    NOT NULL,
            fee_rt      REAL    NOT NULL,
            p50_final        REAL,
            plan_start_date  TEXT,
            curve_json       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_proj_plans_created ON projection_plans(created_at);

        CREATE TABLE IF NOT EXISTS projection_actuals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id     INTEGER NOT NULL REFERENCES projection_plans(id) ON DELETE CASCADE,
            date        TEXT    NOT NULL,
            balance     REAL    NOT NULL,
            note        TEXT,
            created_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_proj_actuals_plan ON projection_actuals(plan_id);

        -- Goal ladder: append-only plan versions + manual total-stack snapshots.
        -- Never UPDATE or DELETE a goal_plan row; amend = insert a new version.
        CREATE TABLE IF NOT EXISTS goal_plan (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            version           INTEGER NOT NULL,
            created_at        TEXT    NOT NULL,
            north_star_btc    REAL    NOT NULL,
            north_star_date   TEXT    NOT NULL,
            goal_btc          REAL    NOT NULL,
            goal_date         TEXT    NOT NULL,
            milestones        TEXT    NOT NULL,   -- JSON [{btc,label}]
            price_scenarios   TEXT    NOT NULL,   -- JSON {bear,base,bull} annual %
            burn_monthly_eur  REAL    NOT NULL,
            amendment_reason  TEXT,
            active            INTEGER NOT NULL DEFAULT 0
        );

        -- Stage B: the Fit sweep's feasible envelope, handed to the /edge search.
        -- One row per completed sweep; the search reads the newest and nudges for a
        -- re-run past FIT_STALE_DAYS rather than silently filtering on old numbers.
        CREATE TABLE IF NOT EXISTS fit_envelope (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            goal        TEXT    NOT NULL,   -- JSON goal-params snapshot
            envelope    TEXT    NOT NULL,   -- JSON {axis: {min,max}} — {} when nothing was feasible
            optimum     TEXT,               -- JSON the joint optimum (or nearest miss)
            feasible_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS stack_snapshot (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            btc_total   REAL    NOT NULL,
            note        TEXT,
            created_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_stack_date ON stack_snapshot(date);

        -- Single-row config (id=1) — drives goal/position calculator defaults
        CREATE TABLE IF NOT EXISTS lens_config (
            id                      INTEGER PRIMARY KEY,
            start_balance           REAL,
            target_balance          REAL,
            target_date             TEXT,
            trades_per_week         REAL,
            win_rate                REAL,
            rr_ratio                REAL,
            leverage                REAL,
            max_drawdown_allowed    REAL,
            losses_allowed          INTEGER,
            fractional_kelly        REAL,
            execution_fill_factor   REAL,
            slippage_pct            REAL,
            risk_per_trade          REAL,
            min_underlying_stop_pct REAL,
            btc_price_eur           REAL,
            btc_growth_monthly      REAL,
            updated_at              TEXT
        );
    """)

    # Migrations — add columns that may not exist on older DBs
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(projection_plans)").fetchall()}
    if "plan_start_date" not in existing_cols:
        c.execute("ALTER TABLE projection_plans ADD COLUMN plan_start_date TEXT")
    if "curve_json" not in existing_cols:
        c.execute("ALTER TABLE projection_plans ADD COLUMN curve_json TEXT")

    trade_cols = {row[1] for row in c.execute("PRAGMA table_info(trades)").fetchall()}
    if "setup_tag" not in trade_cols:
        c.execute("ALTER TABLE trades ADD COLUMN setup_tag TEXT")
    if "book" not in trade_cols:
        # 'hedge' (own money, S1–S5) | 'prop' (Breakout eval). Existing rows = hedge.
        c.execute("ALTER TABLE trades ADD COLUMN book TEXT DEFAULT 'hedge'")
    if "balance_before" not in trade_cols:
        # EUR balance just before the trade closed; sync already computes it.
        c.execute("ALTER TABLE trades ADD COLUMN balance_before REAL")
    if "merged_manual" not in trade_cols:
        # 1 = a manual entry the sync later matched to its exchange fill and
        # reconciled into this single row (review kept, numbers = exchange truth).
        c.execute("ALTER TABLE trades ADD COLUMN merged_manual INTEGER")
    if "manually_edited" not in trade_cols:
        # 1 = user hand-corrected the trade's numbers → sync must never
        # overwrite this row again (the 🔒 lock in the journal).
        c.execute("ALTER TABLE trades ADD COLUMN manually_edited INTEGER")
    # Review layer — execution grade, recurring-mistake tracking (Edgewonk-style),
    # conviction, mental state, and structured reflection. All nullable.
    for col, decl in (
        ("grade",      "TEXT"),     # A/B/C/D/F execution quality
        ("conviction", "INTEGER"),  # 1–5 confidence at entry
        ("emotion",    "TEXT"),     # calm/fomo/tilt/fear/bored
        ("mistakes",   "TEXT"),     # comma-separated mistake tags
        ("went_right", "TEXT"),
        ("went_wrong", "TEXT"),
        ("lesson",     "TEXT"),
    ):
        if col not in trade_cols:
            c.execute(f"ALTER TABLE trades ADD COLUMN {col} {decl}")

    cfg_cols = {row[1] for row in c.execute("PRAGMA table_info(lens_config)").fetchall()}
    if "slippage_pct" not in cfg_cols:
        c.execute("ALTER TABLE lens_config ADD COLUMN slippage_pct REAL")
    c.commit()

    # Seed default config row on first init
    row = c.execute("SELECT id FROM lens_config WHERE id = 1").fetchone()
    if not row:
        c.execute(
            """INSERT INTO lens_config (
                id, start_balance, target_balance, target_date,
                trades_per_week, win_rate, rr_ratio, leverage,
                max_drawdown_allowed, losses_allowed, fractional_kelly,
                execution_fill_factor, slippage_pct, btc_growth_monthly, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1000.0, 250000.0, "2028-12-31",
             14.0, 0.55, 3.0, 10.0,
             0.50, 20, 1.0 / 6.0,
             1.0, 0.0, 0.04, datetime.utcnow().isoformat()),
        )

    c.commit()
    c.close()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _parse_dt(v):
    if v is None or not isinstance(v, str):
        return v
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        return v


def _row_to_response(row: sqlite3.Row) -> TradeResponse:
    d = dict(row)
    d["is_open"] = d.get("exit") is None
    d["opened_at"] = _parse_dt(d["opened_at"])
    if d.get("closed_at"):
        d["closed_at"] = _parse_dt(d["closed_at"])
    for col in ("followed_plan", "followed_strategy"):
        if d.get(col) is not None:
            d[col] = bool(d[col])
    return TradeResponse(**{k: v for k, v in d.items() if k in TradeResponse.model_fields})


def _row_to_dict(row: sqlite3.Row, json_cols: tuple = ()) -> dict:
    d = dict(row)
    for col in json_cols:
        if col in d and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except Exception:
                pass
    return d


# ─── Trades ───────────────────────────────────────────────────────────────────

def create_trade(trade: TradeCreate) -> TradeResponse:
    now = trade.opened_at or datetime.utcnow()
    # Manual forms enter GROSS pnl + fees separately; store pnl NET so the column
    # means the same thing as synced trades (kraken_sync already bakes fees in).
    if trade.pnl is not None and trade.fees:
        trade.pnl = round(trade.pnl - trade.fees, 6)
    fp = int(trade.followed_plan)     if trade.followed_plan     is not None else None
    fs = int(trade.followed_strategy) if trade.followed_strategy is not None else None
    c = _conn()
    cur = c.execute("""
        INSERT INTO trades (symbol, direction, entry, size, leverage, tp, sl,
                            exit, pnl, fees, notes, opened_at, closed_at,
                            followed_plan, followed_strategy, balance_after,
                            linked_signal_id, setup_tag, book)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade.symbol, trade.direction, trade.entry, trade.size, trade.leverage,
        trade.tp, trade.sl, trade.exit, trade.pnl, trade.fees, trade.notes,
        _iso(now), _iso(trade.closed_at), fp, fs, trade.balance_after,
        trade.linked_signal_id, trade.setup_tag, trade.book or "hedge",
    ))
    c.commit()
    row = c.execute("SELECT * FROM trades WHERE id = ?", (cur.lastrowid,)).fetchone()
    c.close()
    return _row_to_response(row)


def get_trades(
    limit: int = 100,
    offset: int = 0,
    venue: Optional[str] = None,
    direction: Optional[str] = None,
    result: Optional[str] = None,
    period: Optional[int] = None,
    book: Optional[str] = None,
) -> list[TradeResponse]:
    where = []
    params: list = []
    if venue:
        where.append("venue = ?"); params.append(venue)
    if book:
        where.append("book = ?"); params.append(book)
    if direction:
        where.append("direction = ?"); params.append(direction)
    if result == "win":
        where.append("pnl > 0")
    elif result == "loss":
        where.append("pnl < 0")
    if period:
        cutoff = (datetime.utcnow() - timedelta(days=int(period))).strftime("%Y-%m-%d")
        where.append("(closed_at >= ? OR closed_at IS NULL)")
        params.append(cutoff)
    sql = "SELECT * FROM trades"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY opened_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    c = _conn()
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [_row_to_response(r) for r in rows]


def get_trade(trade_id: int) -> Optional[TradeResponse]:
    c = _conn()
    row = c.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    c.close()
    return _row_to_response(row) if row else None


_EXCHANGE_TRUTH_COLS = ("entry", "exit", "size", "leverage", "pnl", "fees",
                        "funding_cost", "opened_at", "closed_at")


def update_trade(trade_id: int, data: TradeUpdate) -> Optional[TradeResponse]:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        return get_trade(trade_id)
    # Hand-editing a number the sync owns locks the row (🔒) so the next sync
    # doesn't overwrite the correction with exchange data.
    if any(k in updates for k in _EXCHANGE_TRUTH_COLS):
        updates["manually_edited"] = 1
    for ts_col in ("opened_at", "closed_at"):
        if ts_col in updates:
            updates[ts_col] = _iso(updates[ts_col])
    for col in ("followed_plan", "followed_strategy"):
        if col in updates and isinstance(updates[col], bool):
            updates[col] = int(updates[col])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [trade_id]
    c = _conn()
    c.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)
    c.commit()
    row = c.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    c.close()
    return _row_to_response(row) if row else None


_PROP_EVAL_DEFAULT = {"account": 5000.0, "risk": 0.5, "eval_name": "BREAKOUT_1STEP_TURBO"}


def get_prop_eval() -> dict:
    """Active prop-eval parameters (account size, risk %, plan). Single row,
    lazily created — defaults to the Turbo 5k that was hardcoded before."""
    c = _conn()
    c.execute("""CREATE TABLE IF NOT EXISTS prop_eval_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        account REAL, risk REAL, eval_name TEXT)""")
    row = c.execute("SELECT account, risk, eval_name FROM prop_eval_state WHERE id = 1").fetchone()
    c.close()
    if not row:
        return dict(_PROP_EVAL_DEFAULT)
    return {"account": row["account"], "risk": row["risk"], "eval_name": row["eval_name"]}


def set_prop_eval(account: float, risk: float, eval_name: str) -> dict:
    c = _conn()
    c.execute("""CREATE TABLE IF NOT EXISTS prop_eval_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        account REAL, risk REAL, eval_name TEXT)""")
    c.execute("""INSERT INTO prop_eval_state (id, account, risk, eval_name) VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET account=excluded.account, risk=excluded.risk, eval_name=excluded.eval_name""",
        (account, risk, eval_name))
    c.commit()
    c.close()
    return {"account": account, "risk": risk, "eval_name": eval_name}


def archive_prop_trades(meta: dict = None) -> int:
    """Start a fresh eval: re-tag the current prop run to a dated archive book so
    the live ledger (book='prop') resets to the start. Move-never-delete — the old
    run stays queryable under its archive tag. `meta` records the account/risk/plan
    the run used (trades don't carry it), so the history view can score it later."""
    tag = "prop_arch_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    c = _conn()
    c.execute("""CREATE TABLE IF NOT EXISTS prop_eval_archive (
        tag TEXT PRIMARY KEY, account REAL, risk REAL, eval_name TEXT, created_at TEXT)""")
    if meta:
        c.execute("INSERT OR REPLACE INTO prop_eval_archive (tag, account, risk, eval_name, created_at) VALUES (?,?,?,?,?)",
                  (tag, meta.get("account"), meta.get("risk"), meta.get("eval_name"), datetime.utcnow().isoformat()))
    cur = c.execute("UPDATE trades SET book = ? WHERE book = 'prop'", (tag,))
    c.commit()
    c.close()
    return cur.rowcount


def prop_archive_books() -> list[str]:
    """Distinct archive book tags present in the trades table (source of truth —
    catches runs archived before metadata stamping existed)."""
    c = _conn()
    rows = c.execute("SELECT DISTINCT book FROM trades WHERE book LIKE 'prop_arch_%' ORDER BY book DESC").fetchall()
    c.close()
    return [r[0] for r in rows]


def get_prop_archives() -> list[dict]:
    """Archived eval runs (tag + the params they ran under), newest first."""
    c = _conn()
    c.execute("""CREATE TABLE IF NOT EXISTS prop_eval_archive (
        tag TEXT PRIMARY KEY, account REAL, risk REAL, eval_name TEXT, created_at TEXT)""")
    rows = c.execute("SELECT tag, account, risk, eval_name, created_at FROM prop_eval_archive ORDER BY tag DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]


def delete_trade(trade_id: int) -> bool:
    c = _conn()
    # un-link any signal pointing here first — the FK has no cascade, and the
    # signal should outlive its trade (just lose the link), not block the delete.
    c.execute("UPDATE signals SET linked_trade_id = NULL WHERE linked_trade_id = ?", (trade_id,))
    cur = c.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    c.commit()
    c.close()
    return cur.rowcount > 0


# Signal→fill linkage. Ground truth from the two rows linked by hand:
# the fill lands 15s–10min after decided_at, and its entry sits up to 1.12% off
# the signal's quoted price (different venues quote different books). So the key
# is decision-precedes-fill + direction; entry is only a sanity guard, wide
# enough to admit that 1.12% and tight enough to reject a cross-symbol signal
# quoting a 24%-away price.
# ponytail: symbol is deliberately NOT matched — trades carry BTC/USD:USD and
# signals carry BTCUSDT.P for the same instrument. LENS is BTC-only; add a
# symbol predicate the day a second instrument exists, not before.
_SIGNAL_WINDOW_DAYS = 0.25    # 6h: a decision older than this didn't cause this fill
_SIGNAL_ENTRY_TOL   = 0.025   # 2.5%


def _link_signal(c, trade_id: int, direction: str, entry: float, opened_at: str) -> Optional[str]:
    """Claim the nearest approved, unclaimed signal whose decision precedes this
    fill. One signal → one trade: the claim is guarded by linked_trade_id IS NULL
    so two fills of a split order can't both take credit for the same signal.
    Returns the signal_id claimed, or None. Never raises — a missed link must
    not fail a sync."""
    if not (direction and entry and opened_at):
        return None
    # a hand-logged link is truth; never re-point it or burn a signal on it
    cur = c.execute("SELECT linked_signal_id FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if cur is None or cur["linked_signal_id"]:
        return None
    row = c.execute("""
        SELECT signal_id FROM signals
         WHERE status = 'approved' AND direction = ?
           AND linked_trade_id IS NULL AND decided_at IS NOT NULL
           AND julianday(?) >= julianday(decided_at)
           AND julianday(?) - julianday(decided_at) <= ?
           AND entry_price > 0 AND ABS(? - entry_price) / entry_price < ?
      ORDER BY julianday(decided_at) DESC LIMIT 1
    """, (direction, opened_at, opened_at, _SIGNAL_WINDOW_DAYS,
          entry, _SIGNAL_ENTRY_TOL)).fetchone()
    if not row:
        return None
    sid = row["signal_id"]
    c.execute("UPDATE signals SET linked_trade_id = ? "
              "WHERE signal_id = ? AND linked_trade_id IS NULL", (trade_id, sid))
    c.execute("UPDATE trades SET linked_signal_id = ? "
              "WHERE id = ? AND linked_signal_id IS NULL", (sid, trade_id))
    return sid


def backfill_signal_links() -> int:
    """One-shot: link historical fills the same way sync now does. Oldest fill
    first, so when two fills of one order contend for a signal the earlier one
    claims it. Returns links made. Idempotent."""
    c = _conn()
    rows = c.execute(
        "SELECT id, direction, entry, opened_at FROM trades "
        "WHERE linked_signal_id IS NULL AND entry > 0 ORDER BY opened_at"
    ).fetchall()
    n = sum(bool(_link_signal(c, r["id"], r["direction"], r["entry"], r["opened_at"]))
            for r in rows)
    c.commit()
    c.close()
    return n


def upsert_exchange_trade(trade_dict: dict) -> Optional[TradeResponse]:
    """Used by kraken_sync + bybit_sync — dedups on kraken_order_id column
    (reused as a generic exchange_order_id for both venues)."""
    order_id = trade_dict.get("kraken_order_id")
    c = _conn()
    if order_id:
        existing = c.execute(
            "SELECT id, manually_edited FROM trades WHERE kraken_order_id = ?", (order_id,)
        ).fetchone()
        if existing:
            # Exchange numbers are truth: refresh them in place (a fixed sync
            # rebuild must be able to repair old rows). Review fields, notes and
            # setup_tag stay; a 🔒 hand-edited row is never touched.
            if not existing["manually_edited"]:
                # merged rows keep the hand-logged leverage (sync's is a
                # margin-math estimate, the manual log is what he actually set)
                c.execute("""
                    UPDATE trades SET
                        entry=?, exit=?, size=?,
                        leverage=CASE WHEN merged_manual=1 THEN leverage ELSE ? END,
                        pnl=?, fees=?,
                        opened_at=?, closed_at=?, balance_after=?, balance_before=?,
                        funding_cost=?, fill_type=?, order_type=?, fill_uuid=?, fill_count=?
                    WHERE id=?
                """, (
                    trade_dict["entry"], trade_dict.get("exit"), trade_dict["size"],
                    trade_dict.get("leverage", 1.0), trade_dict.get("pnl"), trade_dict.get("fees"),
                    _iso(trade_dict.get("opened_at")), _iso(trade_dict.get("closed_at")),
                    trade_dict.get("balance_after"), trade_dict.get("balance_before"),
                    trade_dict.get("funding_cost"), trade_dict.get("fill_type"),
                    trade_dict.get("order_type"), trade_dict.get("fill_uuid"),
                    trade_dict.get("fill_count"), existing["id"],
                ))
                c.commit()
            c.close()
            return None   # not newly imported

    # Manual-twin merge: a manual entry with no exchange id, same direction &
    # symbol, entry within 1% → reconcile into that row rather than inserting a
    # duplicate. Closed manual rows match within ±2 days; still-OPEN manual rows
    # (he logs the plan at entry, never closes it by hand) within ±6 hours of
    # the fill. Exchange numbers become truth; the manual row's notes/setup/
    # review are left untouched; flag merged_manual.
    if order_id and trade_dict.get("exit") is not None:
        opened_iso = _iso(trade_dict.get("opened_at")) or datetime.utcnow().isoformat()
        twin = c.execute("""
            SELECT id FROM trades
            WHERE kraken_order_id IS NULL
              AND (venue IS NULL OR venue = 'manual')
              AND direction = ? AND symbol = ?
              AND entry > 0
              AND ABS(entry - ?) / entry < 0.01
              AND ABS(julianday(opened_at) - julianday(?)) < (CASE WHEN exit IS NULL THEN 0.25 ELSE 2 END)
            ORDER BY ABS(julianday(opened_at) - julianday(?)) LIMIT 1
        """, (trade_dict["direction"], trade_dict.get("symbol", "BTC/USD"),
              trade_dict["entry"], opened_iso, opened_iso)).fetchone()
        if twin:
            c.execute("""
                UPDATE trades SET
                    entry=?, exit=?, size=?,
                    leverage=COALESCE(leverage, ?),
                    pnl=?, fees=?,
                    opened_at=?, closed_at=?, kraken_order_id=?, balance_after=?, balance_before=?,
                    venue=?, contract=?, market_type=?, fill_type=?, order_type=?,
                    funding_cost=?, fill_uuid=?, fill_count=?, merged_manual=1
                WHERE id=?
            """, (
                trade_dict["entry"], trade_dict.get("exit"), trade_dict["size"],
                trade_dict.get("leverage", 1.0), trade_dict.get("pnl"), trade_dict.get("fees"),
                opened_iso, _iso(trade_dict.get("closed_at")), order_id,
                trade_dict.get("balance_after"), trade_dict.get("balance_before"),
                trade_dict.get("venue", "kraken_futures"), trade_dict.get("contract"),
                trade_dict.get("market_type"), trade_dict.get("fill_type"),
                trade_dict.get("order_type"), trade_dict.get("funding_cost"),
                trade_dict.get("fill_uuid"), trade_dict.get("fill_count"), twin["id"],
            ))
            _link_signal(c, twin["id"], trade_dict["direction"],
                         trade_dict["entry"], opened_iso)
            c.commit()
            row = c.execute("SELECT * FROM trades WHERE id = ?", (twin["id"],)).fetchone()
            c.close()
            return _row_to_response(row)

    cur = c.execute("""
        INSERT INTO trades (symbol, direction, entry, size, leverage, tp, sl,
                            exit, pnl, fees, notes, opened_at, closed_at,
                            kraken_order_id, balance_after, balance_before,
                            venue, contract, market_type, fill_type, order_type,
                            funding_cost, fill_uuid, fill_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_dict.get("symbol", "BTC/USD"),
        trade_dict["direction"],
        trade_dict["entry"],
        trade_dict["size"],
        trade_dict.get("leverage", 1.0),
        trade_dict.get("tp"),
        trade_dict.get("sl"),
        trade_dict.get("exit"),
        trade_dict.get("pnl"),
        trade_dict.get("fees"),
        trade_dict.get("notes"),
        _iso(trade_dict.get("opened_at")) or datetime.utcnow().isoformat(),
        _iso(trade_dict.get("closed_at")),
        order_id,
        trade_dict.get("balance_after"),
        trade_dict.get("balance_before"),
        trade_dict.get("venue", "kraken_futures"),
        trade_dict.get("contract"),
        trade_dict.get("market_type"),
        trade_dict.get("fill_type"),
        trade_dict.get("order_type"),
        trade_dict.get("funding_cost"),
        trade_dict.get("fill_uuid"),
        trade_dict.get("fill_count"),
    ))
    _link_signal(c, cur.lastrowid, trade_dict["direction"], trade_dict["entry"],
                 _iso(trade_dict.get("opened_at")) or datetime.utcnow().isoformat())
    c.commit()
    row = c.execute("SELECT * FROM trades WHERE id = ?", (cur.lastrowid,)).fetchone()
    c.close()
    return _row_to_response(row)


def clear_synced_open_positions(venue: Optional[str] = None) -> int:
    """Delete auto-synced open-position rows so each sync can re-insert the
    current live positions cleanly. Open positions carry no exchange order_id,
    so they can't be deduped on insert; instead we wipe-and-replace them every
    sync. Real closed trades (exit IS NOT NULL, with an order_id) are untouched,
    and so are manually-entered trades (different notes). Returns rows deleted."""
    c = _conn()
    match = ("notes = 'auto-synced open position' "
             "AND exit IS NULL AND kraken_order_id IS NULL")
    params: tuple = ()
    if venue:
        match += " AND venue = ?"
        params = (venue,)
    # signals may back-link to an open row (no FK cascade) — unlink first
    c.execute(f"UPDATE signals SET linked_trade_id = NULL WHERE linked_trade_id IN "
              f"(SELECT id FROM trades WHERE {match})", params)
    cur = c.execute(f"DELETE FROM trades WHERE {match}", params)
    c.commit()
    n = cur.rowcount
    c.close()
    return n


# ─── Transfers ────────────────────────────────────────────────────────────────

def get_transfers(limit: int = 200) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM transfers ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return [_row_to_dict(r) for r in rows]


def upsert_transfer(transfer_dict: dict) -> bool:
    kid = transfer_dict.get("kraken_id")
    c = _conn()
    if kid:
        existing = c.execute(
            "SELECT id FROM transfers WHERE kraken_id = ?", (kid,)
        ).fetchone()
        if existing:
            c.close()
            return False

    ts = _iso(transfer_dict.get("ts"))
    c.execute("""
        INSERT INTO transfers (kraken_id, transfer_type, asset, amount, balance_after, ts, venue)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        transfer_dict.get("kraken_id", str(ts)),
        transfer_dict.get("transfer_type", "unknown"),
        transfer_dict.get("asset", "eur"),
        float(transfer_dict.get("amount", 0)),
        transfer_dict.get("balance_after"),
        ts,
        transfer_dict.get("venue", "kraken_spot"),
    ))
    c.commit()
    c.close()
    return True


# ─── Daily snapshots ──────────────────────────────────────────────────────────

_DSNAP_COLS = ("snapshot_date", "eur_balance", "btc_balance", "btc_price_usd",
               "portfolio_usd", "unrealized_pnl", "margin_used", "available_margin")


def upsert_daily_snapshot(snapshot: dict) -> dict:
    payload = {k: snapshot.get(k) for k in _DSNAP_COLS}
    if not payload.get("snapshot_date"):
        raise ValueError("snapshot_date is required")
    c = _conn()
    existing = c.execute(
        "SELECT id FROM daily_snapshots WHERE snapshot_date = ?",
        (payload["snapshot_date"],),
    ).fetchone()
    if existing:
        set_clause = ", ".join(f"{k} = ?" for k in _DSNAP_COLS if k != "snapshot_date")
        c.execute(
            f"UPDATE daily_snapshots SET {set_clause} WHERE snapshot_date = ?",
            [payload[k] for k in _DSNAP_COLS if k != "snapshot_date"]
            + [payload["snapshot_date"]],
        )
    else:
        cols = list(_DSNAP_COLS)
        placeholders = ", ".join("?" for _ in cols)
        c.execute(
            f"INSERT INTO daily_snapshots ({', '.join(cols)}) VALUES ({placeholders})",
            [payload[k] for k in cols],
        )
    c.commit()
    row = c.execute(
        "SELECT * FROM daily_snapshots WHERE snapshot_date = ?",
        (payload["snapshot_date"],),
    ).fetchone()
    c.close()
    return _row_to_dict(row)


def get_daily_snapshots(limit: int = 90) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM daily_snapshots ORDER BY snapshot_date DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return [_row_to_dict(r) for r in rows]


# ─── Signals ──────────────────────────────────────────────────────────────────

_SIGNAL_COLS = (
    "signal_id", "strategy_name", "strategy_version", "received_at",
    "symbol", "venue", "session_utc", "btc_1d_trend", "btc_1w_trend", "atr_14d_pct",
    "trigger_type", "htf_bias", "mtf_confluence", "confluence_count",
    "direction", "entry_price", "stop_price", "target_price",
    "suggested_size_pct", "suggested_leverage", "expected_rr",
)


def insert_signal(signal: dict, auto_rejection_reason: Optional[str] = None) -> dict:
    """Insert a new signal. signal_id must be supplied.

    If `auto_rejection_reason` is provided (from discipline filters), the row is
    stored with status='rejected' and rejection_reason set, instead of 'pending'.
    """
    if not signal.get("signal_id"):
        raise ValueError("signal_id is required")

    payload = {k: signal.get(k) for k in _SIGNAL_COLS}
    payload["received_at"] = _iso(payload.get("received_at")) or datetime.utcnow().isoformat()

    mtf = payload.get("mtf_confluence")
    if mtf is not None and not isinstance(mtf, str):
        payload["mtf_confluence"] = json.dumps(mtf)

    cols = list(_SIGNAL_COLS)
    extra_cols: list[str] = []
    extra_vals: list = []
    if auto_rejection_reason:
        extra_cols = ["status", "rejection_reason", "decided_at"]
        extra_vals = ["rejected", auto_rejection_reason, datetime.utcnow().isoformat()]

    all_cols = cols + extra_cols
    placeholders = ", ".join("?" for _ in all_cols)
    c = _conn()
    try:
        c.execute(
            f"INSERT INTO signals ({', '.join(all_cols)}) VALUES ({placeholders})",
            [payload[k] for k in cols] + extra_vals,
        )
        c.commit()
    except sqlite3.IntegrityError as e:
        c.close()
        raise ValueError(f"Duplicate signal_id: {payload['signal_id']}") from e
    row = c.execute("SELECT * FROM signals WHERE signal_id = ?",
                    (payload["signal_id"],)).fetchone()
    c.close()
    return _row_to_dict(row, json_cols=("mtf_confluence",))


def get_last_non_rejected_signal_for_symbol(symbol: str) -> Optional[dict]:
    """Most-recent pending|approved signal for cooldown checks."""
    c = _conn()
    row = c.execute(
        """SELECT * FROM signals
           WHERE symbol = ? AND status IN ('pending', 'approved')
           ORDER BY received_at DESC LIMIT 1""",
        (symbol,),
    ).fetchone()
    c.close()
    return _row_to_dict(row, json_cols=("mtf_confluence",)) if row else None


def get_signals(
    status: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    where = []
    params: list = []
    if status:
        where.append("status = ?"); params.append(status)
    if strategy:
        where.append("strategy_name = ?"); params.append(strategy)
    sql = "SELECT * FROM signals"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY received_at DESC LIMIT ?"
    params.append(limit)
    c = _conn()
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [_row_to_dict(r, json_cols=("mtf_confluence",)) for r in rows]


def get_signal(signal_id: str) -> Optional[dict]:
    c = _conn()
    row = c.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
    c.close()
    return _row_to_dict(row, json_cols=("mtf_confluence",)) if row else None


def decide_signal(
    signal_id: str,
    status: str,                       # approved | rejected
    your_conviction: Optional[int] = None,
    rejection_reason: Optional[str] = None,
) -> Optional[dict]:
    if status not in ("approved", "rejected"):
        raise ValueError("status must be 'approved' or 'rejected'")
    if status == "approved" and not your_conviction:
        raise ValueError("your_conviction (1-5) required to approve")
    if status == "rejected" and not rejection_reason:
        raise ValueError("rejection_reason required to reject")

    c = _conn()
    c.execute(
        """UPDATE signals
           SET status = ?, your_conviction = ?, rejection_reason = ?, decided_at = ?
           WHERE signal_id = ? AND status = 'pending'""",
        (status, your_conviction, rejection_reason,
         datetime.utcnow().isoformat(), signal_id),
    )
    c.commit()
    row = c.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,)).fetchone()
    c.close()
    return _row_to_dict(row, json_cols=("mtf_confluence",)) if row else None


_CFG_COLS = (
    "start_balance", "target_balance", "target_date",
    "trades_per_week", "win_rate", "rr_ratio", "leverage",
    "max_drawdown_allowed", "losses_allowed", "fractional_kelly",
    "execution_fill_factor", "slippage_pct", "risk_per_trade", "min_underlying_stop_pct",
    "btc_price_eur", "btc_growth_monthly",
)


def get_lens_config() -> dict:
    c = _conn()
    row = c.execute("SELECT * FROM lens_config WHERE id = 1").fetchone()
    c.close()
    return _row_to_dict(row) if row else {}


def upsert_lens_config(updates: dict) -> dict:
    """Partial update — keeps existing values for keys not in `updates`."""
    payload = {k: v for k, v in updates.items() if k in _CFG_COLS}
    payload["updated_at"] = datetime.utcnow().isoformat()
    c = _conn()
    existing = c.execute("SELECT id FROM lens_config WHERE id = 1").fetchone()
    if existing:
        set_clause = ", ".join(f"{k} = ?" for k in payload)
        c.execute(
            f"UPDATE lens_config SET {set_clause} WHERE id = 1",
            list(payload.values()),
        )
    else:
        cols = ["id"] + list(payload.keys())
        vals = [1] + list(payload.values())
        placeholders = ", ".join("?" for _ in cols)
        c.execute(
            f"INSERT INTO lens_config ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
    c.commit()
    row = c.execute("SELECT * FROM lens_config WHERE id = 1").fetchone()
    c.close()
    return _row_to_dict(row)


# ─── Projection plans ─────────────────────────────────────────────────────────

def save_projection_plan(params: dict) -> dict:
    now = datetime.utcnow().isoformat()
    c = _conn()
    cur = c.execute(
        """INSERT INTO projection_plans
           (label, created_at, status, start_bal, stop_pct, tp_pct,
            leverage, win_rate, tpw, weeks, btc_price, fee_rt, p50_final, plan_start_date, curve_json)
           VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            params.get("label", ""),
            now,
            params["start_bal"], params["stop_pct"], params["tp_pct"],
            params["leverage"], params["win_rate"], params["tpw"],
            params["weeks"], params["btc_price"], params["fee_rt"],
            params.get("p50_final"),
            params.get("plan_start_date"),
            params.get("curve_json"),
        ),
    )
    c.commit()
    row = c.execute("SELECT * FROM projection_plans WHERE id = ?", (cur.lastrowid,)).fetchone()
    c.close()
    return _row_to_dict(row)


def get_projection_plans() -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM projection_plans ORDER BY created_at DESC"
    ).fetchall()
    c.close()
    return [_row_to_dict(r) for r in rows]


def get_projection_plan(plan_id: int) -> Optional[dict]:
    c = _conn()
    row = c.execute("SELECT * FROM projection_plans WHERE id = ?", (plan_id,)).fetchone()
    c.close()
    return _row_to_dict(row) if row else None


def update_projection_plan(plan_id: int, updates: dict) -> Optional[dict]:
    allowed = {"label", "status", "plan_start_date", "curve_json"}
    payload = {k: v for k, v in updates.items() if k in allowed}
    if not payload:
        return get_projection_plan(plan_id)
    set_clause = ", ".join(f"{k} = ?" for k in payload)
    c = _conn()
    c.execute(
        f"UPDATE projection_plans SET {set_clause} WHERE id = ?",
        list(payload.values()) + [plan_id],
    )
    c.commit()
    row = c.execute("SELECT * FROM projection_plans WHERE id = ?", (plan_id,)).fetchone()
    c.close()
    return _row_to_dict(row) if row else None


def delete_projection_plan(plan_id: int) -> bool:
    c = _conn()
    cur = c.execute("DELETE FROM projection_plans WHERE id = ?", (plan_id,))
    c.commit()
    c.close()
    return cur.rowcount > 0


# ─── Projection actuals ────────────────────────────────────────────────────────

def add_projection_actual(plan_id: int, date: str, balance: float, note: Optional[str]) -> dict:
    now = datetime.utcnow().isoformat()
    c = _conn()
    cur = c.execute(
        "INSERT INTO projection_actuals (plan_id, date, balance, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (plan_id, date, balance, note, now),
    )
    c.commit()
    row = c.execute("SELECT * FROM projection_actuals WHERE id = ?", (cur.lastrowid,)).fetchone()
    c.close()
    return _row_to_dict(row)


def get_projection_actuals(plan_id: int) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM projection_actuals WHERE plan_id = ? ORDER BY date ASC",
        (plan_id,),
    ).fetchall()
    c.close()
    return [_row_to_dict(r) for r in rows]


def delete_projection_actual(actual_id: int) -> bool:
    c = _conn()
    cur = c.execute("DELETE FROM projection_actuals WHERE id = ?", (actual_id,))
    c.commit()
    c.close()
    return cur.rowcount > 0


def autofill_projection_actuals(plan_id: int) -> int:
    """Pull daily_snapshots with eur_balance >= plan.created_at date and insert as actuals.
    Skips dates already present. Returns count of new rows inserted."""
    c = _conn()
    plan = c.execute("SELECT created_at, plan_start_date FROM projection_plans WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        c.close()
        return 0
    since = plan["plan_start_date"] or plan["created_at"][:10]  # YYYY-MM-DD
    existing = {
        row["date"]
        for row in c.execute(
            "SELECT date FROM projection_actuals WHERE plan_id = ?", (plan_id,)
        ).fetchall()
    }
    snapshots = c.execute(
        "SELECT snapshot_date, eur_balance FROM daily_snapshots "
        "WHERE snapshot_date >= ? AND eur_balance IS NOT NULL ORDER BY snapshot_date ASC",
        (since,),
    ).fetchall()
    now = datetime.utcnow().isoformat()
    count = 0
    for row in snapshots:
        d = row["snapshot_date"]
        if d in existing:
            continue
        c.execute(
            "INSERT INTO projection_actuals (plan_id, date, balance, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (plan_id, d, row["eur_balance"], "auto: daily snapshot", now),
        )
        count += 1
    c.commit()
    c.close()
    return count


def get_actual_stats() -> dict:
    """Live trading stats for the projection feedback loop."""
    c = _conn()
    row = c.execute('''
        SELECT
            COUNT(*)                                              AS total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)            AS wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END)            AS losses,
            ROUND(AVG(CASE WHEN pnl > 0 THEN pnl END), 2)       AS avg_win_eur,
            ROUND(AVG(CASE WHEN pnl < 0 THEN pnl END), 2)       AS avg_loss_eur,
            ROUND(SUM(CASE WHEN pnl IS NOT NULL THEN pnl ELSE 0 END), 2) AS total_pnl,
            MIN(closed_at)                                       AS first_close,
            MAX(closed_at)                                       AS last_close
        FROM trades WHERE closed_at IS NOT NULL AND pnl IS NOT NULL
    ''').fetchone()
    snap = c.execute(
        'SELECT eur_balance, snapshot_date FROM daily_snapshots ORDER BY snapshot_date DESC LIMIT 1'
    ).fetchone()
    c.close()

    total = row['total_trades'] or 0
    wins  = row['wins']  or 0
    avg_win  = row['avg_win_eur']
    avg_loss = row['avg_loss_eur']

    # Realized reward:risk = avg win / |avg loss|
    actual_rr = round(avg_win / abs(avg_loss), 2) if avg_win and avg_loss else None

    # Trade frequency over the closed-trade span
    trades_per_week = None
    if total >= 2 and row['first_close'] and row['last_close']:
        try:
            span_days = (datetime.fromisoformat(row['last_close'])
                         - datetime.fromisoformat(row['first_close'])).days
            if span_days >= 7:
                trades_per_week = round(total / (span_days / 7), 1)
        except (ValueError, TypeError):
            pass

    return {
        'total_trades':    total,
        'wins':            wins,
        'losses':          row['losses'] or 0,
        'actual_wr':       round(wins / total * 100, 1) if total > 0 else None,
        'actual_rr':       actual_rr,
        'trades_per_week': trades_per_week,
        'avg_win_eur':     avg_win,
        'avg_loss_eur':    avg_loss,
        'total_pnl':       row['total_pnl'],
        'current_balance': snap['eur_balance']    if snap else None,
        'balance_date':    snap['snapshot_date']  if snap else None,
    }


def expire_stale_signals(older_than_minutes: int = 30) -> int:
    """Mark pending signals older than N minutes as 'expired'. Returns count updated."""
    cutoff = (datetime.utcnow() - timedelta(minutes=older_than_minutes)).isoformat()
    c = _conn()
    cur = c.execute(
        "UPDATE signals SET status = 'expired' WHERE status = 'pending' AND received_at < ?",
        (cutoff,),
    )
    c.commit()
    n = cur.rowcount
    c.close()
    return n
