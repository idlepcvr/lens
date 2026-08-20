"""Guards the execution gates and the bracket it builds. No network: the client
is stubbed, so a regression that would send a real order fails here.

The expensive mistake this file exists to prevent is a stop on the wrong side of
the entry — the exchange accepts it and fills instantly at market.
"""
import os

import _bootstrap  # noqa: F401
from app import execute


class _FakeClient:
    single: list = []
    batch: list = []

    def create_order(self, **kw):
        _FakeClient.single.append(kw)
        return {"result": "success"}

    def create_batch_order(self, batchorder_list=None, **kw):
        _FakeClient.batch.append(batchorder_list)
        return {"result": "success", "batchStatus": [{"status": "placed"}]}


def _patch(cap="1.0"):
    _FakeClient.single, _FakeClient.batch = [], []
    execute._client = lambda account="personal": _FakeClient()
    os.environ["LENS_MAX_ORDER_BTC"] = cap
    os.environ["KRAKEN_FUTURES_SANDBOX"] = "1"


def _nothing_sent():
    return not _FakeClient.single and not _FakeClient.batch


def main():
    # sandbox defaults ON — a missing var must never mean live
    os.environ.pop("KRAKEN_FUTURES_SANDBOX", None)
    assert execute.sandbox() is True

    # 1) confirm required
    _patch()
    r = execute.execute("long", 0.01, mark=70000)
    assert r["sent"] is False and r["blocked"] == "not_confirmed" and _nothing_sent()

    # 2) size cap is hard
    _patch(cap="0.005")
    r = execute.execute("long", 0.01, confirm=True, mark=70000)
    assert r["blocked"].startswith("over_size_cap") and _nothing_sent(), r

    # 3) discipline veto blocks a confirmed, in-size order
    _patch()
    real = execute.discipline.evaluate
    execute.discipline.evaluate = lambda s, l: "filter:forced"
    try:
        r = execute.execute("long", 0.001, confirm=True, mark=70000)
        assert r["blocked"] == "filter:forced" and _nothing_sent(), r
    finally:
        execute.discipline.evaluate = real

    # 4) THE ONE THAT COSTS MONEY — stop on the wrong side is refused
    _patch()
    r = execute.execute("long", 0.001, confirm=True, mark=70000, stop_loss=71000)
    assert r["blocked"].startswith("sl_above_entry") and _nothing_sent(), r
    r = execute.execute("long", 0.001, confirm=True, mark=70000, take_profit=69000)
    assert r["blocked"].startswith("tp_below_entry") and _nothing_sent(), r
    r = execute.execute("short", 0.001, confirm=True, mark=70000, stop_loss=69000)
    assert r["blocked"].startswith("sl_below_entry") and _nothing_sent(), r
    r = execute.execute("short", 0.001, confirm=True, mark=70000, take_profit=71000)
    assert r["blocked"].startswith("tp_above_entry") and _nothing_sent(), r

    # 5) a limit order with no price is refused
    _patch()
    r = execute.execute("long", 0.001, confirm=True, order_type="lmt", mark=70000)
    assert r["blocked"] == "limit_price_required" and _nothing_sent(), r

    # 6) the bracket: entry + TP + SL, exits opposite side and reduce-only
    _patch()
    r = execute.execute("long", 0.002, confirm=True, order_type="lmt",
                        limit_price=70000, take_profit=72000, stop_loss=69000)
    assert r["sent"] is True, r
    assert len(_FakeClient.batch) == 1, _FakeClient.batch
    b = _FakeClient.batch[0]
    assert [o["order_tag"] for o in b] == ["entry", "tp", "sl"], b
    assert b[0]["side"] == "buy" and b[0]["limitPrice"] == 70000
    assert "reduceOnly" not in b[0], "the entry must not be reduce-only"
    for leg in b[1:]:
        assert leg["side"] == "sell", leg
        assert leg["reduceOnly"] is True, leg
        assert leg["triggerSignal"] == "mark", leg
    assert b[1]["stopPrice"] == 72000 and b[2]["stopPrice"] == 69000

    # 7) a bare entry uses create_order, not the batch endpoint
    _patch()
    r = execute.execute("short", 0.002, confirm=True, mark=70000, signal_id="sig-1")
    assert r["sent"] and len(_FakeClient.single) == 1 and not _FakeClient.batch
    o = _FakeClient.single[0]
    assert o["side"] == "sell" and o["cliOrdId"] == "sig-1" and "order_tag" not in o

    # 8) close() is opposite side, reduce-only, market, and drops any bracket
    _patch()
    r = execute.close("long", 0.043, confirm=True, mark=70000,
                      take_profit=99999, stop_loss=1)
    assert r["sent"] is True, r
    o = _FakeClient.single[0]
    assert o["side"] == "sell" and o["reduceOnly"] is True and o["orderType"] == "mkt"
    assert "stopPrice" not in o

    # 9) post_only forces the post type and still needs a price
    _patch()
    c = execute.check("long", 0.001, post_only=True, limit_price=70000, mark=70000)
    assert c["ok"] and c["order_type"] == "post" and c["orders"][0]["orderType"] == "post"

    # 10) check() never sends, and reports margin off the reference price
    _patch()
    c = execute.check("long", 0.001, mark=70000, leverage=10)
    assert _nothing_sent()
    assert c["notional_usd"] == 70.0 and c["required_margin_usd"] == 7.0, c

    print("test_execute OK")


if __name__ == "__main__":
    main()
