"""The briefing decides whether he overrides a veto, so the stance logic gets a
test: a reading that calls overbought bullish would argue for the wrong trade."""
import _bootstrap  # noqa: F401
from app import market_read as mr


def main():
    # RSI stance: extremes are warnings, not confirmations
    closes = [100.0] * 20
    assert mr._rsi(closes) is not None

    rising = [100 + i for i in range(40)]
    falling = [140 - i for i in range(40)]
    assert mr._rsi(rising) > 90, "a straight ramp up must read overbought"
    assert mr._rsi(falling) < 10, "a straight ramp down must read oversold"

    # EMA tracks and is shorter-period-faster
    assert mr._ema(rising, 5) > mr._ema(rising, 20), "faster EMA leads in an uptrend"
    assert mr._ema(rising, 100) is None, "not enough bars must return None, not a guess"

    assert abs(mr._stdev([2, 2, 2, 2])) < 1e-9
    assert mr._stdev([1, 3]) == 1.0

    # the live read is shaped as the UI expects, and never raises
    r = mr.read("long")
    assert set(("ok",)) <= set(r)
    if r["ok"]:
        assert r["readings"] and r["agree"] + r["against"] <= len(r["readings"])
        for x in r["readings"]:
            assert set(x) == {"name", "value", "stance", "note"}, x
            assert x["stance"] in ("bull", "bear", "flat"), x
        # overbought must never be counted as agreeing with a long
        rsi = next((x for x in r["readings"] if x["name"].startswith("RSI")), None)
        if rsi and float(rsi["value"]) >= 70:
            assert rsi["stance"] == "bear", "overbought is a warning, not a buy signal"

    bad = mr.read("sideways")           # nonsense direction must not explode
    assert "ok" in bad

    print("test_market_read OK")


if __name__ == "__main__":
    main()
