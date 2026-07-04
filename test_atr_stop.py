"""Self-check for the v3 engine additions: atr_stop_mult + risk_pct.

Synthetic tape: price grinds up so a long entered anywhere hits TP.
Asserts (1) dynamic stop = k×ATR of the entry bar, TP = rr×stop;
(2) risk-normalized leverage → win pnl ≈ rr×risk − fee drag, and the fee
drag scales with leverage (tight stop pays more).
Run: python3 test_atr_stop.py
"""
import numpy as np
import pandas as pd

from app.backtest_engine import add_indicators, _run_backtest

n = 400
idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
close = pd.Series(100.0 * (1.002 ** np.arange(n)), index=idx)  # steady +0.2%/bar
df = pd.DataFrame({
    "open": close.shift(1).fillna(100.0),
    "high": close * 1.004,   # range → nonzero ATR, enough to tag a 2R TP over bars
    "low":  close * 0.999,   # never deep enough to tag the stop
    "close": close,
    "volume": 1000.0,
}, index=idx)
df = add_indicators(df)

sig = lambda d, i, p: "long" if i == 100 else None
RISK, K, RR = 2.0, 1.5, 2.0
params = {"atr_stop_mult": K, "rr": RR, "risk_pct": RISK, "leverage": 5.0,
          "slippage_pct": 0.03, "skip_sat": False, "once_per_day": False}
res = _run_backtest(df, sig, params, 1000.0)
assert len(res["trades"]) == 1, res["trades"]
t = res["trades"][0]

atr_pct = (df["atr14"] / df["close"]).iloc[100]
stop = K * atr_pct
lev = min(5.0, RISK / 100 / stop)
# exit price ≈ entry × (1 + rr×stop) → dynamic TP honoured
assert abs(t["exit_px"] / t["entry_px"] - (1 + RR * stop)) < 1e-4, (t, stop)
# win pnl = rr×stop×lev − 2×(0.15%+0.03%)×lev, all in % of equity
expect = (RR * stop - 2 * 0.0018) * lev * 100
assert abs(t["pnl_pct"] - expect) < 0.01, (t["pnl_pct"], expect)
# risk-normalized: a loss would cost ≈ RISK% + fees — implied by lev = risk/stop
assert abs(stop * lev * 100 - RISK) < 1e-9 or lev == 5.0

# fee drag comparison: same R, tight fixed stop vs wide — tight pays more lev×fees
tight = _run_backtest(df, sig, {"stop_pct": 0.5, "tp_pct": 1.0, "risk_pct": RISK,
                                "leverage": 10.0, "slippage_pct": 0.03,
                                "skip_sat": False, "once_per_day": False}, 1000.0)
wide = _run_backtest(df, sig, {"stop_pct": 2.0, "tp_pct": 4.0, "risk_pct": RISK,
                               "leverage": 10.0, "slippage_pct": 0.03,
                               "skip_sat": False, "once_per_day": False}, 1000.0)
assert wide["trades"][0]["pnl_pct"] > tight["trades"][0]["pnl_pct"], (
    "wide stop should net more at equal risk — fee drag scales with leverage")

print("ok — atr_stop geometry, risk-normalized leverage, fee-drag ordering all hold")
