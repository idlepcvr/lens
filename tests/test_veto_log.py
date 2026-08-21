"""The veto override is a record, not a rubber stamp — so the rules that decide
what counts as a reason, and that the record survives, get a test."""
import os, sqlite3, tempfile

import _bootstrap  # noqa: F401


def main():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    sqlite3.connect(db).close()

    import app.database as database
    database.DB_PATH = db
    import importlib, app.veto_log as vl
    importlib.reload(vl)

    # a shrug is not a thesis
    assert vl.valid_reason(None) is False
    assert vl.valid_reason("") is False
    assert vl.valid_reason("felt good") is False, "too short must not pass"
    assert vl.valid_reason("momentum break above 75.3k with the daily trend") is True

    rid = vl.record("long", 0.056, entry=75321, leverage=10,
                    take_profit=76134.5, stop_loss=74914.3,
                    setup_tag="no_setup [NONE: 98 trades]",
                    veto_reasons=["entry inside FVG retrace"],
                    user_reason="momentum break above 75.3k with the daily trend",
                    context={"rsi": 78.5, "killzone": "none"})
    assert rid == 1

    rows = vl.recent()
    assert len(rows) == 1
    r = rows[0]
    assert r["direction"] == "long" and r["size_btc"] == 0.056
    assert r["veto_reasons"] == ["entry inside FVG retrace"], r["veto_reasons"]
    assert r["context"]["rsi"] == 78.5
    assert r["user_reason"].startswith("momentum break")
    assert r["linked_trade_id"] is None, "outcome is attached later, on sync"

    # append-only: a second override does not disturb the first
    vl.record("short", 0.01, user_reason="fading the sweep into the prior day high")
    rows = vl.recent()
    assert len(rows) == 2 and rows[-1]["id"] == 1

    print("test_veto_log OK")


if __name__ == "__main__":
    main()
