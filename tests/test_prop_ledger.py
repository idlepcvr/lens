"""Guards the prop-eval breach + daily-wall math in prop_ledger_data().

Pure, offline (live=False → no Kraken). Points the DB layer at a throwaway file,
seeds closed prop trades, and asserts the verdict. Run: python3 test_prop_ledger.py
"""
import datetime
import os
import tempfile

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app import database
from app.models import TradeCreate

UTC = datetime.timezone.utc


def _reset_book():
    for t in database.get_trades(limit=5000, book="prop"):
        database.delete_trade(t.id)


def _add(pnl, closed_at):
    database.create_trade(TradeCreate(
        book="prop", direction="short", symbol="BTC/USD:USD",
        entry=60000, exit=60000, size=0.01, leverage=1, pnl=pnl, fees=0,
        closed_at=closed_at))


def main():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = path
    database.init_db()
    database.set_prop_eval(5000.0, 0.5, "BREAKOUT_1STEP_TURBO")  # floor 4850, daily 3%
    from app.prop_ledger import prop_ledger_data

    now = datetime.datetime.now(UTC)
    old = now - datetime.timedelta(days=5)   # before today's 00:30 UTC eval-day boundary

    # 1) empty book → clean start, nothing failed
    _reset_book()
    d = prop_ledger_data(live=False)
    assert d["n_trades"] == 0 and d["equity"] == 5000.0, d
    assert not d["failed"] and not d["passed"], d
    assert d["opening_eq"] == 5000.0, d

    # 2) loss below the static floor → floor breach latches FAILED
    _reset_book()
    _add(-200, old)                          # eq 4800 <= floor 4850
    d = prop_ledger_data(live=False)
    assert d["breach_floor"] and d["failed"], d
    assert not d["passed"], d

    # 3) wins to the +9% target → PASSED
    _reset_book()
    _add(+460, old)                          # eq 5460 >= target 5450
    d = prop_ledger_data(live=False)
    assert d["passed"] and not d["breach_floor"], d

    # 4) daily wall is measured off THIS eval-day's opening equity, not the $5k start
    _reset_book()
    _add(+400, old)                          # prior day: opening equity today = 5400
    _add(-170, now)                          # today: -170 vs 3% of 5400 = 162 → breach
    d = prop_ledger_data(live=False)
    assert abs(d["opening_eq"] - 5400.0) < 1e-6, d
    assert abs(d["daily_limit_usd"] - 162.0) < 1e-6, d
    assert d["breach_daily"] and d["failed"], d

    # 5) fee rides state → archive → summary, and survives a new eval
    _reset_book()
    _add(-200, old)                          # a losing run to archive
    database.set_prop_eval(5000.0, 0.5, "BREAKOUT_1STEP_TURBO", fee=20.0)
    assert database.get_prop_eval()["fee"] == 20.0
    from app.prop_ledger import archive_summaries
    database.archive_prop_trades(meta=database.get_prop_eval())
    database.set_prop_eval(10000.0, 0.5, "BREAKOUT_1STEP_TURBO", fee=48.0)
    arch = archive_summaries()
    assert len(arch) == 1 and arch[0]["fee"] == 20.0, arch
    assert arch[0]["verdict"] == "failed", arch
    assert database.get_prop_eval()["account"] == 10000.0, "new eval params live"
    # lifetime spend = archived fees + the fee already paid on the active eval
    assert sum(a["fee"] for a in arch) + database.get_prop_eval()["fee"] == 68.0

    os.remove(path)
    print("ok — prop_ledger breach + daily-wall logic holds; fee tracks across evals")


if __name__ == "__main__":
    main()
