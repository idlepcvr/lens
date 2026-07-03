"""Self-check for kraken_sync._build_trades — the partial-close bug (trade 574
logged only the last 0.0004 slice of a 0.1644 short, dropping ~€77 of loss).
Run: python3 test_kraken_sync.py
"""
from datetime import datetime, timezone, timedelta

from app.kraken_sync import _build_trades

T0 = datetime(2026, 7, 1, 23, 53, tzinfo=timezone.utc)


def f(mins, side, size, price):
    return {"fill_id": "f", "order_id": "o" + str(mins), "symbol": "PF_XBTUSD",
            "side": side, "order_type": "market", "size": size, "price": price,
            "fee_pct": 0.0005, "fill_type": "taker", "pos_size_after": 0,
            "funding": 0, "fill_time": T0 + timedelta(minutes=mins)}


def test_partial_close_full_roundtrip():
    # short 0.1644, closed in two chunks — must emit ONE trade over full size
    fills = [f(0, "sell", 0.1644, 59997), f(160, "buy", 0.164, 60545), f(165, "buy", 0.0004, 60333)]
    tl    = [(T0 - timedelta(hours=1), 904.02), (T0 + timedelta(minutes=165), 827.2)]
    fund  = [(T0 + timedelta(minutes=60), -0.5)]        # paid $0.50 funding
    (t,)  = _build_trades(fills, tl, 1.17, fund)
    assert t["size"] == 0.1644
    assert abs(t["pnl"] - ((59997 - 60544.48) * 0.1644 / 1.17 - t["fees"])) < 0.5
    assert t["balance_before"] == 904.02 and t["balance_after"] == 827.2
    assert t["funding_cost"] > 0.4          # positive = cost
    assert t["fill_count"] == 3 and t["leverage"] == 9


def test_flip_in_one_fill():
    fills = [f(0, "buy", 0.1, 60000), f(10, "sell", 0.15, 60100), f(20, "buy", 0.05, 60050)]
    a, b  = _build_trades(fills, [], 1.17, [])
    assert a["direction"] == "long" and a["size"] == 0.1
    assert b["direction"] == "short" and b["size"] == 0.05


if __name__ == "__main__":
    test_partial_close_full_roundtrip()
    test_flip_in_one_fill()
    print("OK")
