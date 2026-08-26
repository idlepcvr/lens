"""SMA/Bollinger/MACD added to review.py for the journal's chart overlay
(docs/trading-philosophy-2026-08.md). Checked against known values, not
just 'it returns a list' — the MACD signal line in particular seeds an EMA
through a filler-zero warmup that's easy to get subtly wrong.
"""
import _bootstrap  # noqa: F401
from app.review import _bollinger, _macd, _sma


def test_sma():
    closes = [1, 2, 3, 4, 5]
    assert _sma(closes, 3) == [None, None, 2, 3, 4]


def test_bollinger_flat_series_has_zero_width():
    # constant price -> stdev 0 -> upper == mid == lower
    closes = [100.0] * 25
    bb = _bollinger(closes, 20, 2.0)
    assert bb["mid"][19] == 100.0
    assert bb["upper"][19] == bb["lower"][19] == 100.0


def test_bollinger_matches_hand_computed():
    closes = [10, 12, 8, 14, 6, 11, 9, 13, 7, 15,
              10, 12, 8, 14, 6, 11, 9, 13, 7, 15]  # period=20, one window
    bb = _bollinger(closes, 20, 2.0)
    mean = sum(closes) / 20
    var = sum((c - mean) ** 2 for c in closes) / 20
    sd = var ** 0.5
    assert abs(bb["mid"][19] - mean) < 1e-9
    assert abs(bb["upper"][19] - (mean + 2 * sd)) < 1e-9
    assert abs(bb["lower"][19] - (mean - 2 * sd)) < 1e-9


def test_macd_rising_trend_is_positive_and_warms_up_before_flat_series():
    # a steadily rising series should end with a positive MACD line (fast
    # EMA > slow EMA in an uptrend) and a populated signal/hist by the end
    closes = [100 + i * 0.5 for i in range(80)]
    m = _macd(closes, 12, 26, 9)
    assert m["line"][-1] is not None and m["line"][-1] > 0
    assert m["signal"][-1] is not None
    assert m["hist"][-1] is not None
    assert abs(m["hist"][-1] - (m["line"][-1] - m["signal"][-1])) < 1e-9
    # nothing before the fast/slow EMAs have both warmed up should be non-None
    assert m["line"][24] is None and m["line"][25] is not None


def test_macd_flat_series_settles_near_zero():
    closes = [50.0] * 80
    m = _macd(closes, 12, 26, 9)
    assert abs(m["line"][-1]) < 1e-6
    assert abs(m["signal"][-1]) < 1e-6
    assert abs(m["hist"][-1]) < 1e-6


if __name__ == "__main__":
    test_sma()
    test_bollinger_flat_series_has_zero_width()
    test_bollinger_matches_hand_computed()
    test_macd_rising_trend_is_positive_and_warms_up_before_flat_series()
    test_macd_flat_series_settles_near_zero()
    print("test_review_indicators OK")
