"""Funding must be causal, and the search must agree with the replay.

Two failure modes are worth a test here, and only one of them is obvious.

The obvious one is lookahead. Funding settles every 8h; bars are 1h/4h/1d. If a
bar is joined to the funding rate settled DURING or AFTER it, the backtest
enters trades knowing a number the market had not published yet, and the search
returns a beautiful edge that cannot be traded. So: every bar's fund_rate must
be a settlement at or before that bar's own timestamp.

The non-obvious one is drift between the two code paths. The grid search scores
combos through vectorized masks in strategy_search._masks; the winner is then
replayed bar-by-bar through backtest_engine._signal_custom, exported to Pine,
and eventually traded. Those are two independent implementations of the same
condition. If they disagree by one bar or one comparison operator, the search
finds an edge the engine cannot reproduce and nobody notices, because both
halves run green on their own. This test asserts they agree bar-for-bar on real
cached data.

Run: python3 -m pytest tests/test_orderflow.py -q
"""

import numpy as np
import pandas as pd
import pytest

from tests._bootstrap import *          # noqa: F401,F403  (repo-root sys.path)

from app import orderflow
from app.backtest_engine import _signal_custom
from app.strategy_search import _masks, SLOTS

FUNDING_OPTS = ("hot", "extreme", "cold", "neg")


def _synthetic_funding(n=400, seed=0):
    """8h settlements with a known shape — no network, deterministic."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="8h", tz="UTC")
    return pd.Series(rng.normal(0.0001, 0.0002, n), index=idx)


def _bars_from(ser, freq="4h"):
    idx = pd.date_range(ser.index[0], ser.index[-1], freq=freq, tz="UTC")
    return pd.DataFrame({"close": np.linspace(50000, 60000, len(idx))}, index=idx)


# ── causality ────────────────────────────────────────────────────────────────

def test_no_lookahead_every_bar():
    """Each bar's funding rate was published at or before that bar."""
    ser = _synthetic_funding()
    df = _bars_from(ser)
    monkey = orderflow.load_funding
    orderflow.load_funding = lambda refresh=True: ser
    try:
        out = orderflow.funding_columns(df.copy(), refresh=False)
    finally:
        orderflow.load_funding = monkey

    for ts, rate in out["fund_rate"].items():
        if rate != rate:                       # NaN before the first settlement
            continue
        eligible = ser[ser.index <= ts]
        assert eligible.iloc[-1] == rate, f"{ts} used a rate it could not have seen"


def test_bars_before_first_settlement_are_nan():
    ser = _synthetic_funding()
    df = _bars_from(ser)
    df = pd.concat([pd.DataFrame({"close": [1.0]},
                                 index=[ser.index[0] - pd.Timedelta("1D")]), df])
    orig = orderflow.load_funding
    orderflow.load_funding = lambda refresh=True: ser
    try:
        out = orderflow.funding_columns(df.copy(), refresh=False)
    finally:
        orderflow.load_funding = orig
    assert np.isnan(out["fund_rate"].iloc[0])


def test_percentile_is_rank_in_trailing_window():
    """fund_pct is the rate's rank among the PRIOR PCT_WINDOW settlements."""
    ser = _synthetic_funding()
    df = _bars_from(ser)
    orig = orderflow.load_funding
    orderflow.load_funding = lambda refresh=True: ser
    try:
        out = orderflow.funding_columns(df.copy(), refresh=False)
    finally:
        orderflow.load_funding = orig

    pct = out["fund_pct"].dropna()
    assert len(pct), "percentile never warmed up"
    assert pct.between(0.0, 1.0).all()

    # spot-check one bar against a hand-computed rank
    ts = pct.index[len(pct) // 2]
    rate = out.loc[ts, "fund_rate"]
    pos = ser.index.get_indexer([ser[ser.index <= ts].index[-1]])[0]
    window = ser.iloc[pos - orderflow.PCT_WINDOW + 1: pos]
    assert abs(pct.loc[ts] - (window <= rate).mean()) < 1e-9


# ── the two code paths must agree ────────────────────────────────────────────

def test_masks_match_signal_custom_on_synthetic():
    ser = _synthetic_funding(n=800, seed=3)
    df = _bars_from(ser)
    orig = orderflow.load_funding
    orderflow.load_funding = lambda refresh=True: ser
    try:
        df = orderflow.funding_columns(df, refresh=False)
    finally:
        orderflow.load_funding = orig
    # _masks needs the columns it reads; only the funding keys are exercised here
    fr, fp = df["fund_rate"].to_numpy(), df["fund_pct"].to_numpy()
    built = {"hot": fp >= 0.80, "extreme": fp >= 0.95,
             "cold": fp <= 0.20, "neg": fr < 0}

    for opt in FUNDING_OPTS:
        params = {"funding": opt, "direction": "short"}
        replay = np.array([_signal_custom(df, i, params) is not None
                           for i in range(len(df))])
        expected = built[opt].copy()
        expected[:60] = False              # _signal_custom's warm-up
        assert (replay == expected).all(), \
            f"mask and replay disagree on funding={opt}: " \
            f"{int((replay != expected).sum())} bars"


def test_nan_funding_never_enters():
    """Missing data must FAIL the entry, not silently pass it."""
    df = pd.DataFrame({
        "close": np.ones(100), "open": np.ones(100),
        "fund_rate": np.full(100, np.nan), "fund_pct": np.full(100, np.nan),
    }, index=pd.date_range("2024-01-01", periods=100, freq="4h", tz="UTC"))
    for opt in FUNDING_OPTS:
        assert all(_signal_custom(df, i, {"funding": opt}) is None
                   for i in range(60, 100)), f"NaN passed funding={opt}"


def test_funding_slot_registered():
    assert SLOTS["funding"] == list(FUNDING_OPTS)


# ── live data, if the cache has it ───────────────────────────────────────────

def test_masks_match_replay_on_real_data():
    """Same agreement check against the real cached feed and real indicators."""
    from app.backtest_engine import load_ohlcv, add_indicators
    try:
        df = add_indicators(load_ohlcv(months=6, timeframe="4h"))
    except Exception as e:
        pytest.skip(f"no market data available: {e}")
    if "fund_pct" not in df or df["fund_pct"].notna().sum() < 50:
        pytest.skip("funding cache not warmed")

    m = _masks(df)
    for opt in FUNDING_OPTS:
        params = {"funding": opt, "direction": "short"}
        replay = np.array([_signal_custom(df, i, params) is not None
                           for i in range(len(df))])
        expected = m[("funding", opt)].copy()
        expected[:60] = False
        assert (replay == expected).all(), \
            f"real-data disagreement on funding={opt}: " \
            f"{int((replay != expected).sum())} bars"
