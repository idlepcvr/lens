"""Guards book scoping across trades + review analytics.

The bug this locks down: /dashboard and /analytics queried trades with NO book
filter, so hedge's stats silently included every prop attempt. And max_dd_pct was
divided by lens_config.start_balance — which is 100.0, the Goal model's seed —
producing "max drawdown −9512%".

Offline. Run: .venv/bin/python test_book_scope.py
"""
import datetime
import os
import tempfile

from app import database
from app.models import TradeCreate

UTC = datetime.timezone.utc


def _add(book, pnl, day):
    # fees=0: create_trade nets fees INTO pnl on insert (database.py, "store pnl
    # NET so the column means the same thing as synced trades"). Keeping fees at
    # zero lets these assertions talk about pnl directly.
    database.create_trade(TradeCreate(
        book=book, direction="long", symbol="BTC/USD:USD",
        entry=60000, exit=60000 + pnl, size=0.01, leverage=1, pnl=pnl, fees=0,
        opened_at=day, closed_at=day))


def main():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = path
    import app.review as review
    review.DB_PATH = path
    database.init_db()

    d0 = datetime.datetime(2026, 6, 1, 12, tzinfo=UTC)
    day = lambda k: d0 + datetime.timedelta(days=k)

    _add("hedge", +100, day(0))
    _add("hedge", -50, day(1))
    _add("prop", -30, day(2))                    # the live eval
    _add("prop_arch_20260630_175919", -20, day(3))  # an archived attempt

    # 1) exact vs prefix match on the trades query
    assert len(database.get_trades(limit=99, book="hedge")) == 2
    assert len(database.get_trades(limit=99, book="prop")) == 1, "exact: live eval only"
    assert len(database.get_trades(limit=99, book="prop*")) == 2, "prefix: live + archived"
    assert len(database.get_trades(limit=99)) == 4, "no book → every book"

    # 2) review_analytics scopes the same way; 'prop' spans attempts by design
    h = review.review_analytics(book="hedge", era="all")
    p = review.review_analytics(book="prop", era="all")
    a = review.review_analytics(era="all")
    assert h["n"] == 2 and abs(h["total_pnl"] - 50) < 1e-6, h
    assert p["n"] == 2 and abs(p["total_pnl"] + 50) < 1e-6, p   # -30 + -20
    assert a["n"] == 4, a
    # the contamination this whole change exists to prevent:
    assert h["total_pnl"] != a["total_pnl"], "hedge stats must exclude prop trades"

    # 3) a credible capital base → a real drawdown %, measured off peak EQUITY
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("UPDATE lens_config SET start_balance = 100.0 WHERE id = 1")
    conn.commit()
    ok = review.review_analytics(book="hedge", era="all")
    assert ok["max_dd_eur"] == 50.0, ok["max_dd_eur"]
    assert ok["capital_base"] == 100.0, "base 100 > 50 drawdown → credible"
    # peak equity = 100 + 100 = 200; trough 150 → 25%, NOT 50/100 = 50% of the seed
    assert abs(ok["max_dd_pct"] - 25.0) < 0.05, ok["max_dd_pct"]

    # 4) drawdown exceeds the base → % is suppressed, not faked as "−9512%"
    _add("hedge", -500, day(4))
    bad = review.review_analytics(book="hedge", era="all")
    assert bad["max_dd_eur"] > 100, bad["max_dd_eur"]
    assert bad["max_dd_pct"] is None, f"expected suppressed %, got {bad['max_dd_pct']}"
    assert bad["capital_base"] is None
    assert "fiction" in bad["capital_note"], bad["capital_note"]

    conn.close()
    os.remove(path)
    print("ok — book scoping (exact/prefix) holds; fake drawdown % suppressed")


if __name__ == "__main__":
    main()
