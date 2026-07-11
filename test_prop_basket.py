"""Guards the prop basket + stand-down-reason logic.

The bug this locks down: run_prop_scan_cli() used to gate every signal on
`state["is_asian"]`, which made it impossible for a non-Asian strategy in the
basket to EVER emit. Each signal_fn already enforces its own session rule, so the
gate was redundant for ASIAN_* and fatal for everything else.

Offline (no Kraken, no network). Run: .venv/bin/python test_prop_basket.py
"""
import os
import tempfile

from app import database


def main():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = path
    database.init_db()
    database.set_prop_eval(10000.0, 0.5, "BREAKOUT_1STEP_TURBO", fee=48.0)

    from app.prop_scan import prop_tradeable
    from app.prop_desk import _stand_down_reason, _tf_ms

    # 1) no basket saved → falls back to the board top-3 (old behaviour preserved)
    assert database.get_prop_eval()["basket"] is None
    fallback = prop_tradeable()
    assert len(fallback) == 3, fallback

    # 2) an explicit basket wins, and rides through to prop_tradeable
    picked = ["ASIAN_RSI_DIP_v1", "PULLBACK_4R_v1", "ENGULF_v1"]
    database.set_prop_basket(picked)
    assert database.get_prop_eval()["basket"] == picked
    names = [n for n, _ in prop_tradeable()]
    assert names == picked, names

    # 3) junk entries are dropped — a name with no signal_fn would silently never
    #    fire, which is worse than not being in the basket at all
    database.set_prop_basket(["ASIAN_RSI_DIP_v1", "S1 · NY-AM flush", "NOT_A_STRAT"])
    assert [n for n, _ in prop_tradeable()] == ["ASIAN_RSI_DIP_v1"]

    # 4) swapping the basket must NOT disturb the running eval's money fields
    cfg = database.get_prop_eval()
    assert cfg["account"] == 10000.0 and cfg["fee"] == 48.0 and cfg["risk"] == 0.5, cfg

    # 5) timeframe-aware bar length (a 4h constant on a 1h strategy read a stale bar)
    assert _tf_ms("1h") == 3_600_000 and _tf_ms("4h") == 14_400_000
    assert _tf_ms("weird") == 14_400_000, "unknown tf falls back to 4h"

    # 6) stand-down reason names the OUTERMOST unmet gate, not the last false one.
    #    Non-Asian bar beats every downstream condition.
    r = _stand_down_reason("ASIAN_RSI_DIP_v1", True, False, True, False, True, False, 45, 35, None)
    assert "not an Asian bar" in r, r
    #    On an Asian bar in a daily downtrend, longs are gated and it says so.
    r = _stand_down_reason("ASIAN_RSI_DIP_v1", True, True, False, True, False, True, 69.5, 69.8, 65368.0)
    assert "daily is bearish" in r and "65,368" in r, r
    #    Non-Asian strategies get a generic reason, never the hero's conditions.
    r = _stand_down_reason("PULLBACK_4R_v1", False, False, True, False, True, False, 50, 50, None)
    assert "PULLBACK_4R_v1" in r and "Asian" not in r, r

    # 7) the digest builds a body and pushes exactly once
    import app.prop_scan as ps
    sent = []
    ps._notify = lambda title, body, **kw: sent.append((title, body)) or True
    ok = ps._push_stand_down([("ASIAN_RSI_DIP_v1", {"close": 63977.7,
                                                    "stand_down_reason": "daily is bearish"})])
    assert ok and len(sent) == 1, sent
    assert "daily is bearish" in sent[0][1] and "63,978" in sent[0][1], sent[0][1]
    assert not ps._push_stand_down([]), "no states → no push"

    os.remove(path)
    print("ok — basket precedence, tf-aware bars, stand-down reasons, digest push")


if __name__ == "__main__":
    main()
