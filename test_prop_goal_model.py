"""Guards the /prop-goal metrics model.

Two bugs this locks down, both found the hard way:

  1. compute_goal returns PERCENTAGES, not fractions (verified against the live
     /goal page: per_trade_ev 7.542 == the page's "7.542%"). Multiplying by 100
     produced a 3717% probability of touching the floor.

  2. compute_goal derives the underlying stop as risk/fill/leverage - friction.
     Passing the firm's 5x CAP as leverage implies a 0.1% price stop that fees
     swallow whole -> CalcError. The real legal leverage at 0.5% risk on a 1%
     stop is 0.5x.

Also pins the semantics of losses_to_floor, which calculator's losses_to_ruin
gets wrong for small drawdown caps (it means "equity falls TO 3% of start").

Offline maths only. Run: .venv/bin/python test_prop_goal_model.py
"""
import datetime as dt

from app.calculator import CalcError, compute_goal
from app.prop_goal import _losses_to_floor


def main():
    # 1) units: reproduce the hedge /goal screenshot exactly
    r = compute_goal(100, 55000, dt.date(2026, 12, 31), 5, 0.5, 4, 5,
                     max_drawdown_allowed=0.25, losses_allowed=4, fractional_kelly=0.25,
                     execution_fill_factor=0.8, slippage_pct=0.0015,
                     min_underlying_stop_pct=0.01357,
                     btc_price_eur=55000, btc_growth_monthly=0.036)
    assert abs(r["per_trade_ev"] - 7.542) < 0.01, r["per_trade_ev"]
    assert abs(r["risk_of_ruin"] - 12.31) < 0.05, r["risk_of_ruin"]
    assert abs(r["optimal_risk_pct"] - 6.94) < 0.01, r["optimal_risk_pct"]
    # every one of these is a PERCENT — a value <= 1.0 would mean fractions
    assert r["per_trade_ev"] > 1.0 and r["risk_of_ruin"] > 1.0

    # 2) the 5x cap is NOT the leverage to pass — it implies a stop fees eat
    kw = dict(max_drawdown_allowed=0.03, losses_allowed=6, fractional_kelly=0.25,
              execution_fill_factor=1.0, slippage_pct=0.0, risk_per_trade=0.005,
              min_underlying_stop_pct=0.01)
    d = dt.date.today() + dt.timedelta(days=63)
    try:
        compute_goal(10000, 10900, d, 1.657, 0.333, 3.52, 5.0, **kw)
        raise AssertionError("expected CalcError when passing the 5x firm cap")
    except CalcError as e:
        assert "too small to cover fees" in str(e), e

    # legal leverage (risk/stop = 0.5/1.0) works
    g = compute_goal(10000, 10900, d, 1.657, 0.333, 3.52, 0.5, **kw)
    assert 0 < g["risk_of_ruin"] <= 100, g["risk_of_ruin"]
    assert 0 < g["per_trade_ev"] < 5, f"EV/trade at 0.5% risk should be sub-1%: {g['per_trade_ev']}"

    # 3) ruin integrates against the DRAWDOWN cap, so it IS the floor-touch prob:
    #    a tighter floor must be strictly easier to touch.
    tight = compute_goal(10000, 10900, d, 1.657, 0.333, 3.52, 0.5,
                         **{**kw, "max_drawdown_allowed": 0.02})
    loose = compute_goal(10000, 10900, d, 1.657, 0.333, 3.52, 0.5,
                         **{**kw, "max_drawdown_allowed": 0.06})
    assert tight["risk_of_ruin"] > loose["risk_of_ruin"], (tight["risk_of_ruin"], loose["risk_of_ruin"])

    # 4) losses_to_floor: 0.5% stops into a 3% floor. calculator's losses_to_ruin
    #    says 700 here (it means "equity falls TO 3% of start"). Ours says 7.
    assert _losses_to_floor(0.03, 0.005) == 7, _losses_to_floor(0.03, 0.005)
    assert g["losses_to_ruin"] > 100, "calculator's losses_to_ruin is the other meaning"
    #    sanity: 6 straight stops stay inside the floor, the 7th breaches it
    assert (1 - 0.005) ** 6 > 0.97 and (1 - 0.005) ** 7 < 0.97
    assert _losses_to_floor(0.25, 0.0663) == 5, "hedge-shaped inputs stay sane"
    assert _losses_to_floor(0.03, 0) == 0, "degenerate risk → 0, no ZeroDivision"

    # 5) raising risk cannot buy edge — EV/trade is flat in risk, ruin is not.
    lo = compute_goal(10000, 10900, d, 1.657, 0.333, 3.52, 0.5, **kw)
    hi = compute_goal(10000, 10900, d, 1.657, 0.333, 3.52, 2.0,
                      **{**kw, "risk_per_trade": 0.02})
    assert hi["risk_of_ruin"] > lo["risk_of_ruin"], "more risk must raise floor-touch prob"

    print("ok — compute_goal units are percent; legal leverage required; "
          "ruin == floor-touch; losses_to_floor derived correctly")


if __name__ == "__main__":
    main()
