"""The watcher must tell a fill from a cancel. Both make a resting order vanish;
only one of them moved the position, and announcing a cancel as a take profit
would be worse than saying nothing."""
import json, os, tempfile
from pathlib import Path

import _bootstrap  # noqa: F401
from app import watch


class _Stub:
    orders: list = []
    size: float = 0.0
    eur: float = 100.0
    pushed: list = []


def _wire(tmp):
    watch.STATE = Path(tmp) / "state.json"
    watch.fetch_open_orders = lambda k, s, a="": list(_Stub.orders)
    watch.fetch_open_positions_enriched = lambda k, s, a="": (
        [{"size": _Stub.size}] if _Stub.size else [])
    watch.fetch_live_balance = lambda k, s: {"eur_balance": _Stub.eur}
    watch.get_api_keys = lambda a="personal": ("k", "s")
    import app.setups as setups
    setups._notify = lambda t, b, signal_id=None, tags=None: _Stub.pushed.append((t, b))


def main():
    tmp = tempfile.mkdtemp()
    _wire(tmp)
    tp = {"order_id": "a", "role": "take_profit", "trigger": 78200}
    sl = {"order_id": "b", "role": "stop_loss", "trigger": 74000}

    # first run just records; it must not announce orders it has never seen before
    _Stub.orders, _Stub.size, _Stub.eur, _Stub.pushed = [tp, sl], 0.045, 100.0, []
    r = watch.check()
    assert r["fired"] == [], "a first run must not announce pre-existing orders"

    # the take profit fills: it leaves the book AND the position shrinks
    _Stub.orders, _Stub.size, _Stub.eur = [sl], 0.0, 141.2
    r = watch.check()
    assert len(r["fired"]) == 1, r
    assert r["fired"][0]["title"] == "Take profit hit", r
    assert "+€41.20" in r["fired"][0]["body"], r["fired"][0]["body"]
    assert "flat" in r["fired"][0]["body"]

    # a cancel also removes the order — but the position did not move, so silence
    _Stub.orders, _Stub.size, _Stub.pushed = [tp, sl], 0.045, []
    watch.check()
    _Stub.orders = [tp]                       # sl cancelled by hand, size unchanged
    r = watch.check()
    assert r["fired"] == [], "a cancel must never be announced as a fill"
    assert _Stub.pushed == [], "and must push nothing"

    # a stop fill is labelled as one
    _Stub.orders, _Stub.size, _Stub.eur = [tp, sl], 0.045, 100.0
    watch.check()
    _Stub.orders, _Stub.size, _Stub.eur = [tp], 0.0, 71.6
    r = watch.check()
    assert r["fired"][0]["title"] == "Stop hit", r
    assert "-€28.40" in r["fired"][0]["body"] or "−€28.40" in r["fired"][0]["body"], \
        r["fired"][0]["body"]

    # the daily rung check fires at most once a day
    st = json.loads(watch.STATE.read_text())
    assert "orders" in st and "size" in st, "state must persist across runs"

    print("test_watch OK")


if __name__ == "__main__":
    main()
