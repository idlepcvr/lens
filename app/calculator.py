"""
Pure math engine — no I/O, no database, no FastAPI.

Model flow (EV-first — matches Lucky's spreadsheet):
  1.  Leverage = USER INPUT (exchange leverage setting, e.g. 10x)
  2.  per_trade_ev_required = (1 + weekly_rate)^(1/tpw) − 1   ← THE DRIVER
  3.  goal_pct = per_trade_ev_required + FEE_ROUNDTRIP × leverage
  4.  underlying_win_pct  = goal_pct / leverage                ← TP price move %
  5.  underlying_loss_pct = underlying_win_pct / rr_ratio      ← SL price move % (nominal RR)
  6.  acct_gain_win  = underlying_win_pct × leverage × fill    ← gross account gain per WIN
  7.  acct_loss_loss = (underlying_loss_pct + FEE) × leverage × fill  ← account loss per LOSS (incl. exit fee)
  8.  actual_rr = acct_gain_win / acct_loss_loss               ← true R:R after fee drag
  9.  Kelly/DD with actual_rr (ADVISORY — not the driver)
  10. risk_per_trade = acct_loss_loss  (derived from EV target)
"""

from math import exp, log, sqrt
from scipy.stats import norm
from datetime import date


class CalcError(ValueError):
    pass


# ─── Constants ────────────────────────────────────────────────────────────────
FEE_ROUNDTRIP       = 0.00075 * 2   # 0.0015 maker+taker (one entry + one exit)
POSITION_FEE_MARGIN = 0.0145        # Kraken position margin haircut
DAYS_PER_YEAR       = 365.25
DAYS_PER_WEEK       = 7.0
MONTHS_PER_YEAR     = 12.0
WEEKS_PER_YEAR      = DAYS_PER_YEAR / DAYS_PER_WEEK   # 52.18


# ─── Goal Tracker ─────────────────────────────────────────────────────────────

def compute_goal(
    start_balance:       float,
    target_balance:      float,
    target_date:         date,
    trades_per_week:     float,
    win_rate:            float,   # 0–1
    rr_ratio:            float,   # nominal reward:risk (e.g. 3.0)
    leverage:            float,   # exchange leverage setting (INPUT — e.g. 10x)
    # Risk constraints
    max_drawdown_allowed:    float = 0.50,
    losses_allowed:          int   = 20,
    fractional_kelly:        float = 1.0 / 6.0,  # sixth-Kelly default
    execution_fill_factor:   float = 1.0,
    slippage_pct:            float = 0.0,         # adverse price slip per round-trip (0.001 = 0.10%)
    risk_per_trade:          float = None,        # optional override of acct_loss_loss
    min_underlying_stop_pct: float = None,        # ATR noise floor: SL price move floor (Layer 2)
    # BTC projections
    btc_price_eur:           float = None,
    btc_growth_monthly:      float = 0.04,
) -> dict:
    """
    EV-first goal model. Compounding target drives all position parameters.
    Leverage is a user INPUT. risk_per_trade is DERIVED (or optionally overridden).
    Kelly/DD are ADVISORY checks on the derived risk.
    """

    # ── Validation ──────────────────────────────────────────────────────────
    if start_balance <= 0:
        raise CalcError("start_balance must be positive")
    if target_balance <= start_balance:
        raise CalcError("target_balance must exceed start_balance")
    if trades_per_week <= 0:
        raise CalcError("trades_per_week must be positive")
    if not (0 < win_rate < 1):
        raise CalcError("win_rate must be between 0 and 1 (exclusive)")
    if rr_ratio <= 0:
        raise CalcError("rr_ratio must be positive")
    if leverage <= 0:
        raise CalcError("leverage must be positive")
    if not (0 < max_drawdown_allowed < 1):
        raise CalcError("max_drawdown_allowed must be between 0 and 1")
    if losses_allowed < 1:
        raise CalcError("losses_allowed must be at least 1")
    if not (0 < fractional_kelly <= 1):
        raise CalcError("fractional_kelly must be between 0 and 1")
    if not (0 < execution_fill_factor <= 1):
        raise CalcError("execution_fill_factor must be between 0 and 1")
    if slippage_pct < 0:
        raise CalcError("slippage_pct must be non-negative")
    if risk_per_trade is not None and not (0 < risk_per_trade < 1):
        raise CalcError("risk_per_trade must be between 0 and 1 if provided")

    days_remaining = (target_date - date.today()).days
    if days_remaining <= 0:
        raise CalcError("target_date must be in the future")

    loss_rate = 1.0 - win_rate

    # Total per-trade frictional cost: exchange fees + adverse slippage.
    # Slippage degrades fills on both legs — modelled as extra round-trip cost,
    # so it widens losses AND raises the TP move needed to net the goal.
    friction = FEE_ROUNDTRIP + slippage_pct

    # ─── 1. Time rates ────────────────────────────────────────────────────
    total_interest   = target_balance / start_balance - 1
    weeks_remaining  = days_remaining / DAYS_PER_WEEK
    months_remaining = days_remaining / (DAYS_PER_YEAR / MONTHS_PER_YEAR)

    daily_rate     = (target_balance / start_balance) ** (1.0 / days_remaining) - 1
    weekly_rate    = (1 + daily_rate) ** DAYS_PER_WEEK - 1
    monthly_rate   = (1 + daily_rate) ** (DAYS_PER_YEAR / MONTHS_PER_YEAR) - 1
    quarterly_rate = (1 + daily_rate) ** (DAYS_PER_YEAR / 4) - 1
    annual_rate    = (1 + daily_rate) ** DAYS_PER_YEAR - 1

    # ─── 2. Guard: nominal positive-EV check (before fee drag) ───────────
    ev_denominator = win_rate * rr_ratio - loss_rate
    if ev_denominator <= 0:
        raise CalcError(
            f"Negative expected value: win_rate={win_rate:.0%}, R:R={rr_ratio} "
            f"→ unprofitable edge. Increase win_rate or R:R ratio."
        )

    # ─── 3. EV-first: compounding target drives position parameters ───────
    #
    # per_trade_ev_required: the per-trade geometric growth needed to hit the
    # goal by target_date given the number of trades per week.
    per_trade_ev_required = (1 + weekly_rate) ** (1.0 / trades_per_week) - 1

    # Gross account % target per winning trade (net EV + round-trip fee + slippage drag)
    goal_pct = per_trade_ev_required + friction * leverage

    # ATR adjustment tracking (populated only in primary path when noise floor triggered)
    atr_adjusted    = False
    original_sl_pct = None

    if risk_per_trade is not None:
        # ── Override path ─────────────────────────────────────────────────
        # User specifies the total account % loss on a losing trade (incl. fees)
        acct_loss_loss      = risk_per_trade
        underlying_loss_pct = (risk_per_trade / execution_fill_factor
                                / leverage - friction)
        if underlying_loss_pct <= 0:
            raise CalcError(
                "risk_per_trade override is too small to cover fees+slippage at this leverage."
            )
        underlying_win_pct = underlying_loss_pct * rr_ratio
        acct_gain_win      = underlying_win_pct * leverage * execution_fill_factor
        # What EV-first would have said (advisory comparison)
        ev_underlying_loss = goal_pct / (leverage * rr_ratio)
        required_risk_pct  = ((ev_underlying_loss + friction)
                               * leverage * execution_fill_factor)
    else:
        # ── Primary EV-first path ─────────────────────────────────────────
        # 4. TP price move: how far the market must move to net the goal
        underlying_win_pct  = goal_pct / leverage
        # 5. SL price move: TP move divided by nominal R:R
        underlying_loss_pct = underlying_win_pct / rr_ratio

        # ── Layer 2: ATR noise floor override ─────────────────────────────
        # If EV-derived SL < market noise floor, widen the stop (& TP to keep R:R).
        # This preserves win-rate assumptions by keeping stop outside typical variance.
        if (min_underlying_stop_pct is not None
                and underlying_loss_pct < min_underlying_stop_pct):
            atr_adjusted        = True
            original_sl_pct     = underlying_loss_pct
            underlying_loss_pct = min_underlying_stop_pct
            underlying_win_pct  = underlying_loss_pct * rr_ratio   # maintain nominal R:R

        # 6. Account gain on a WIN (gross — fee embedded in TP placement)
        acct_gain_win  = underlying_win_pct * leverage * execution_fill_factor
        # 7. Account loss on a LOSS (SL P&L + exit fee + slippage)
        acct_loss_loss = ((underlying_loss_pct + friction)
                           * leverage * execution_fill_factor)
        required_risk_pct = acct_loss_loss   # same as derived risk in primary path

    if acct_loss_loss >= 1.0:
        raise CalcError("Per-trade loss ≥ 100% of account — reduce leverage or risk.")

    # ─── 4. True R:R after fee drag ───────────────────────────────────────
    actual_rr = acct_gain_win / acct_loss_loss if acct_loss_loss > 0 else float('inf')

    # ─── 5. Kelly criterion (ADVISORY — uses actual_rr not nominal) ───────
    kelly_ev_denom = win_rate * actual_rr - loss_rate
    full_kelly     = (kelly_ev_denom / actual_rr) if kelly_ev_denom > 0 else 0.0
    kelly_risk     = full_kelly * fractional_kelly

    # ─── 6. DD constraint (advisory) ─────────────────────────────────────
    dd_risk_constraint = 1 - (1 - max_drawdown_allowed) ** (1.0 / losses_allowed)

    # ─── 7. Advisory optimal risk MIN(kelly, DD) ──────────────────────────
    optimal_risk_per_trade = min(kelly_risk, dd_risk_constraint)

    # ─── 8. Per-trade arithmetic EV (should ≈ per_trade_ev_required) ──────
    per_trade_ev = win_rate * acct_gain_win - loss_rate * acct_loss_loss

    # ─── 9. Advisory context (weeks_to_goal computed after analytics) ────
    market_move_needed = underlying_win_pct   # price % move needed (TP)

    # DD-implied leverage (advisory: at what leverage would DD constraint = acct_loss_loss?)
    dd_implied_leverage = (dd_risk_constraint / acct_loss_loss
                           ) if acct_loss_loss > 0 else None

    # ─── 10. Analytics ────────────────────────────────────────────────────

    # Log-return moments
    a       = log(1 + acct_gain_win)                          # typical win log-return
    b       = log(1 - acct_loss_loss)                         # typical loss log-return
    mu_log  = win_rate * a + loss_rate * b                    # mean log-return per trade
    var_log = win_rate * a**2 + loss_rate * b**2 - mu_log**2  # variance
    sigma   = sqrt(var_log) if var_log > 0 else 1e-9

    geometric_drift = exp(mu_log) - 1

    # Weeks to goal at actual geometric drift (compound — correct for long-run)
    if geometric_drift > 0:
        weeks_to_goal_actual = (
            log(target_balance / start_balance) / log(1 + geometric_drift) / trades_per_week
        )
    else:
        weeks_to_goal_actual = float('inf')

    # Actual trades in the period
    actual_trades = round(trades_per_week * weeks_remaining)
    actual_trades = max(1, actual_trades)

    # Theoretical trades to hit target at geometric drift
    if geometric_drift > 0:
        trades_needed = round(log(target_balance / start_balance) / log(1 + geometric_drift))
    else:
        trades_needed = round(log(target_balance / start_balance) / log(1 + per_trade_ev)
                              ) if per_trade_ev > 0 else 9999
    trades_needed = max(1, trades_needed)

    total_trades = actual_trades

    # Sharpe (per-trade, log-return basis)
    sharpe_ratio = mu_log / sigma if sigma > 0 else 0

    # Profit factor
    profit_factor = (
        (win_rate * acct_gain_win) / (loss_rate * acct_loss_loss)
        if acct_loss_loss > 0 else float('inf')
    )

    # Expectancy as fraction of nominal risk (× 100 for display)
    expectancy_pct_of_risk = ev_denominator   # win_rate*rr_ratio - loss_rate

    # Losses to max drawdown (using derived acct_loss_loss)
    losses_to_ruin = _roundup(
        log(max_drawdown_allowed) / log(1 - acct_loss_loss)
    ) if 0 < acct_loss_loss < 1 else float('inf')

    # Wins to recover from max drawdown
    wins_to_breakeven = _roundup(
        log(1 / (1 - max_drawdown_allowed)) / log(1 + acct_gain_win)
    )

    # Trades to double
    trades_to_double = (log(2) / log(1 + geometric_drift)
                        ) if geometric_drift > 0 else float('inf')

    # Risk of Ruin
    N = total_trades
    B = -log(1 - max_drawdown_allowed)   # ruin threshold in log-space
    if sigma > 0 and N > 0:
        z1 = -(B + mu_log * N) / (sigma * sqrt(N))
        z2 =  (B + mu_log * N) / (sigma * sqrt(N))
        ror_term1 = norm.cdf(z1)
        ror_term2 = exp(-2 * mu_log * B / var_log) * norm.cdf(z2) if var_log > 0 else 0
        risk_of_ruin = min(1.0, max(0.0, ror_term1 + ror_term2))
    else:
        risk_of_ruin = 1.0

    if sigma > 0 and N > 0:
        downside_distance = abs(-(B + mu_log * N) / (sigma * sqrt(N)))
        upside_distance   =    (B + mu_log * N)  / (sigma * sqrt(N))
    else:
        downside_distance = upside_distance = 0

    if risk_of_ruin <= 0.001:
        ror_label = "GOOD (very low)"
    elif risk_of_ruin <= 0.01:
        ror_label = "GOOD (low)"
    elif risk_of_ruin <= 0.05:
        ror_label = "OK (moderate)"
    else:
        ror_label = "BAD (high)"

    # Growth projections
    weekly_growth_eur    = start_balance * (1 + geometric_drift) ** WEEKS_PER_YEAR / WEEKS_PER_YEAR - start_balance / WEEKS_PER_YEAR
    monthly_growth_eur   = start_balance * (1 + geometric_drift) ** (DAYS_PER_YEAR / 30.44) - start_balance
    quarterly_growth_eur = start_balance * (1 + geometric_drift) ** (DAYS_PER_YEAR / 4) - start_balance

    # BTC projections
    btc_price_at_goal = target_aum_btc = None
    if btc_price_eur and btc_price_eur > 0:
        btc_price_at_goal = btc_price_eur * (1 + btc_growth_monthly) ** months_remaining
        target_aum_btc    = target_balance / btc_price_at_goal

    # Monte Carlo (log-normal approximation)
    if sigma > 0 and N > 0:
        mc_p05 = start_balance * exp(N * mu_log - 1.645 * sigma * sqrt(N))
        mc_p50 = start_balance * exp(N * mu_log)
        mc_p95 = start_balance * exp(N * mu_log + 1.645 * sigma * sqrt(N))
    else:
        mc_p05 = mc_p50 = mc_p95 = start_balance

    return {
        # ── Time ──────────────────────────────────────────────────────────
        "days_remaining":       days_remaining,
        "weeks_remaining":      round(weeks_remaining, 2),
        "months_remaining":     round(months_remaining, 2),
        "total_interest":       round(total_interest * 100, 4),         # %

        # ── Required growth rates (to hit goal by target_date) ─────────────
        "daily_rate":           round(daily_rate * 100, 6),
        "weekly_rate":          round(weekly_rate * 100, 4),
        "monthly_rate":         round(monthly_rate * 100, 4),
        "quarterly_rate":       round(quarterly_rate * 100, 4),
        "annual_rate":          round(annual_rate * 100, 4),

        # ── Per-trade model ────────────────────────────────────────────────
        "per_trade_ev":           round(per_trade_ev * 100, 6),           # % arithmetic EV
        "per_trade_ev_required":  round(per_trade_ev_required * 100, 6),  # % compounding driver
        "underlying_win_pct":     round(underlying_win_pct * 100, 4),     # TP price move %
        "underlying_loss_pct":    round(underlying_loss_pct * 100, 4),    # SL price move %
        "goal_pct":               round(goal_pct * 100, 6),               # gross acct target %
        "market_move_needed":     round(market_move_needed * 100, 4),     # = underlying_win_pct
        "actual_rr":              round(actual_rr, 4),                    # true R:R after fees
        "r_multiple":             round(actual_rr, 2),                    # alias (spreadsheet "R Multiple")
        "expectancy_pct_of_risk": round(expectancy_pct_of_risk * 100, 4),
        "total_trades":           total_trades,
        "trades_needed":          trades_needed,
        "trades_to_double":       round(trades_to_double, 1) if trades_to_double != float('inf') else None,

        # ── Leverage & Kelly / Risk (advisory) ─────────────────────────────
        "leverage":              round(leverage, 2),
        "full_kelly":            round(full_kelly * 100, 4),              # % (uses actual_rr)
        "fractional_kelly":      round(fractional_kelly * 100, 4),
        "kelly_risk":            round(kelly_risk * 100, 4),              # fractional Kelly %
        "dd_risk_constraint":    round(dd_risk_constraint * 100, 4),      # DD constraint %
        "dd_implied_leverage":   round(dd_implied_leverage, 2) if dd_implied_leverage else None,
        "optimal_risk_pct":      round(optimal_risk_per_trade * 100, 4),  # MIN(kelly, DD) advisory
        "risk_per_trade":        round(acct_loss_loss * 100, 4),          # derived acct loss %
        "required_risk_pct":     round(required_risk_pct * 100, 4) if required_risk_pct else None,
        "required_leverage":     None,   # n/a in EV-first model (leverage is the input)
        "weeks_to_goal_actual":  round(weeks_to_goal_actual, 1) if weeks_to_goal_actual != float('inf') else None,
        "execution_fill_factor": round(execution_fill_factor * 100, 1),
        "slippage_pct":          round(slippage_pct * 100, 4),
        "friction_pct":          round(friction * 100, 4),
        "max_drawdown_allowed":  round(max_drawdown_allowed * 100, 1),
        "losses_allowed":        losses_allowed,

        # ── Account impacts ────────────────────────────────────────────────
        "acct_gain_win":         round(acct_gain_win * 100, 4),           # % gain per win
        "acct_loss_loss":        round(acct_loss_loss * 100, 4),          # % loss per loss
        "geometric_drift":       round(geometric_drift * 100, 6),         # long-run avg growth

        # ── Risk analytics ─────────────────────────────────────────────────
        "typical_win":           round(a * 100, 4),
        "typical_loss":          round(b * 100, 4),
        "avg_growth_per_trade":  round(mu_log * 100, 6),
        "trade_volatility":      round(sigma * 100, 4),
        "ruin_threshold":        round(B, 6),
        "risk_of_ruin":          round(risk_of_ruin * 100, 4),
        "ror_label":             ror_label,
        "downside_distance":     round(downside_distance, 4),
        "upside_distance":       round(upside_distance, 4),
        "sharpe_ratio":          round(sharpe_ratio, 4),
        "profit_factor":         round(profit_factor, 4) if profit_factor != float('inf') else None,
        "losses_to_ruin":        int(losses_to_ruin) if losses_to_ruin != float('inf') else 999,
        "wins_to_breakeven":     int(wins_to_breakeven),

        # ── Growth projections ─────────────────────────────────────────────
        "weekly_growth_eur":     round(weekly_growth_eur, 2),
        "monthly_growth_eur":    round(monthly_growth_eur, 2),
        "quarterly_growth_eur":  round(quarterly_growth_eur, 2),
        "weekly_growth_pct":     round(weekly_rate * 100, 4),
        "monthly_growth_pct":    round(monthly_rate * 100, 4),
        "quarterly_growth_pct":  round(quarterly_rate * 100, 4),

        # ── BTC projections ────────────────────────────────────────────────
        "btc_price_at_goal":     round(btc_price_at_goal, 2) if btc_price_at_goal else None,
        "target_aum_btc":        round(target_aum_btc, 6)    if target_aum_btc else None,

        # ── Monte Carlo ────────────────────────────────────────────────────
        "mc_p05": round(mc_p05, 2),
        "mc_p50": round(mc_p50, 2),
        "mc_p95": round(mc_p95, 2),

        # ── ATR / Volatility adaptation (Layer 2) ──────────────────────────
        "atr_adjusted":    atr_adjusted,
        "original_sl_pct": round(original_sl_pct * 100, 4) if original_sl_pct is not None else None,
        "adjusted_sl_pct": round(underlying_loss_pct * 100, 4) if atr_adjusted else None,

        # ── Internal (for position calc) ───────────────────────────────────
        "_risk_per_trade_raw":   acct_loss_loss,
        "_underlying_risk_raw":  underlying_loss_pct,
        "_underlying_rew_raw":   underlying_win_pct,
        "_leverage_raw":         leverage,
        "_rr_ratio_raw":         rr_ratio,
    }


# ─── Forward Projection (PARAMETER-FIRST — the "new method") ───────────────────

def compute_projection(
    start_balance:    float,
    stop_pct:         float,   # SL price move, as fraction (0.01 = 1%)
    tp_pct:           float,   # TP price move, as fraction (0.04 = 4%)
    leverage:         float,   # exchange leverage (10x)
    win_rate:         float,   # 0–1
    trades_per_week:  float,
    weeks:            float,   # horizon
    btc_price_eur:    float = None,
    max_drawdown:     float = 0.50,
    fee_roundtrip:    float = 0.003,   # 0.30% round trip = 0.15%/side (real Kraken taker)
) -> dict:
    """
    The inverse of compute_goal. Here the trade PARAMETERS are LOCKED inputs
    (1% stop, 4% TP, 10x, fixed risk) and the equity curve is PROJECTED forward
    at a given win rate. Answers "where do I land?" rather than "what do I need?".

    Win rate is NOT optimized — it's a dial you turn to see sensitivity. The
    edge here is R (tp_pct / stop_pct), driven by holding to target.
    """
    if start_balance <= 0:
        raise CalcError("start_balance must be positive")
    if stop_pct <= 0 or tp_pct <= 0:
        raise CalcError("stop_pct and tp_pct must be positive")
    if leverage <= 0:
        raise CalcError("leverage must be positive")
    if not (0 < win_rate < 1):
        raise CalcError("win_rate must be between 0 and 1 (exclusive)")
    if trades_per_week <= 0 or weeks <= 0:
        raise CalcError("trades_per_week and weeks must be positive")

    loss_rate = 1.0 - win_rate

    # ── Per-trade account impact (fee drag baked in, like compute_goal) ──────
    # At 10x/4%/1% with 0.30% round trip: win = +37% account, loss = -13% → ~2.85R
    acct_gain_win  = (tp_pct   - fee_roundtrip) * leverage
    acct_loss_loss = (stop_pct + fee_roundtrip) * leverage
    if acct_loss_loss >= 1.0:
        raise CalcError("Per-trade loss ≥ 100% of account — reduce leverage or stop.")
    if acct_gain_win <= 0:
        raise CalcError("Take-profit too small to clear fees at this leverage.")

    nominal_r = tp_pct / stop_pct
    actual_r  = acct_gain_win / acct_loss_loss

    per_trade_ev = win_rate * acct_gain_win - loss_rate * acct_loss_loss
    breakeven_wr = acct_loss_loss / (acct_gain_win + acct_loss_loss)

    # ── Log-return moments → geometric growth ────────────────────────────────
    a       = log(1 + acct_gain_win)
    b       = log(1 - acct_loss_loss)
    mu_log  = win_rate * a + loss_rate * b
    var_log = win_rate * a**2 + loss_rate * b**2 - mu_log**2
    sigma   = sqrt(var_log) if var_log > 0 else 1e-9
    geometric_drift = exp(mu_log) - 1

    trades_to_double = (log(2) / mu_log) if mu_log > 0 else None
    weeks_to_double  = (trades_to_double / trades_per_week) if trades_to_double else None

    # ── Risk of ruin over the whole horizon (to max_drawdown) ────────────────
    N_total = max(1, round(trades_per_week * weeks))
    B = -log(1 - max_drawdown)
    if sigma > 0:
        z1 = -(B + mu_log * N_total) / (sigma * sqrt(N_total))
        z2 =  (B + mu_log * N_total) / (sigma * sqrt(N_total))
        ror = norm.cdf(z1) + (exp(-2 * mu_log * B / var_log) * norm.cdf(z2) if var_log > 0 else 0)
        risk_of_ruin = min(1.0, max(0.0, ror))
    else:
        risk_of_ruin = 1.0 if mu_log <= 0 else 0.0

    # ── Week-by-week percentile bands (the "multicolour projection") ─────────
    def _band(N, z):
        return start_balance * exp(N * mu_log + z * sigma * sqrt(N))

    milestone_weeks = sorted({w for w in [1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 26, round(weeks)]
                              if 0 < w <= weeks})
    curve = []
    for w in milestone_weeks:
        N = trades_per_week * w
        p50 = _band(N, 0.0)
        row = {
            "week":   w,
            "trades": round(N),
            "p05":    round(_band(N, -1.645), 2),
            "p25":    round(_band(N, -0.674), 2),
            "p50":    round(p50, 2),
            "p75":    round(_band(N,  0.674), 2),
            "p95":    round(_band(N,  1.645), 2),
            "btc_p50": round(p50 / btc_price_eur, 4) if btc_price_eur else None,
        }
        curve.append(row)

    return {
        "inputs": {
            "start_balance": start_balance, "stop_pct": round(stop_pct * 100, 4),
            "tp_pct": round(tp_pct * 100, 4), "leverage": leverage,
            "win_rate": round(win_rate * 100, 2), "trades_per_week": trades_per_week,
            "weeks": weeks, "btc_price_eur": btc_price_eur,
        },
        "nominal_r":        round(nominal_r, 2),
        "actual_r":         round(actual_r, 2),
        "acct_gain_win":    round(acct_gain_win * 100, 2),
        "acct_loss_loss":   round(acct_loss_loss * 100, 2),
        "per_trade_ev":     round(per_trade_ev * 100, 3),
        "breakeven_wr":     round(breakeven_wr * 100, 2),
        "geometric_drift":  round(geometric_drift * 100, 3),
        "weeks_to_double":  round(weeks_to_double, 1) if weeks_to_double else None,
        "trades_to_double": round(trades_to_double, 1) if trades_to_double else None,
        "risk_of_ruin":     round(risk_of_ruin * 100, 2),
        "max_drawdown":     round(max_drawdown * 100, 0),
        "is_positive_ev":   per_trade_ev > 0,
        "curve":            curve,
    }


# ─── Position Calculator ──────────────────────────────────────────────────────

def compute_position(
    entry_price:   float,
    direction:     str,       # "long" or "short"
    balance_eur:   float,
    btc_price_eur: float,
    goal:          dict,
    btc_std_dev:   float = 0.0356,
) -> dict:
    """
    All price levels and sizing — derived from goal outputs.
    TP/SL use underlying_win/loss_pct from EV-first computation.
    """
    if direction not in ("long", "short"):
        raise CalcError("direction must be 'long' or 'short'")
    if entry_price <= 0:
        raise CalcError("entry_price must be positive")
    if balance_eur <= 0:
        raise CalcError("balance_eur must be positive")
    if btc_price_eur <= 0:
        raise CalcError("btc_price_eur must be positive")

    leverage         = goal["_leverage_raw"]
    underlying_risk  = goal["_underlying_risk_raw"]   # price % for SL
    underlying_rew   = goal["_underlying_rew_raw"]    # price % for TP
    risk_per_trade   = goal["_risk_per_trade_raw"]    # account fraction at risk

    is_long = direction == "long"

    # ── Expected 8hr range ────────────────────────────────────────────────
    std_8hr_usd       = btc_std_dev * entry_price * sqrt(8 / 24)
    expected_8hr_high = entry_price + std_8hr_usd
    expected_8hr_low  = entry_price - std_8hr_usd

    # ── Breakeven (fee drag) ──────────────────────────────────────────────
    if is_long:
        breakeven = entry_price * (1 + FEE_ROUNDTRIP)
    else:
        breakeven = entry_price * (1 - FEE_ROUNDTRIP)
    hurdle_cost = abs(breakeven - entry_price) / entry_price

    # ── Liquidation price ─────────────────────────────────────────────────
    if is_long:
        liquidation = entry_price * (1 - 0.5 / leverage)
    else:
        liquidation = entry_price * (1 + 0.5 / leverage)

    # ── TP / SL prices ────────────────────────────────────────────────────
    if is_long:
        tp = entry_price * (1 + underlying_rew)
        sl = entry_price * (1 - underlying_risk)
    else:
        tp = entry_price * (1 - underlying_rew)
        sl = entry_price * (1 + underlying_risk)

    # ── Position sizing ───────────────────────────────────────────────────
    balance_btc            = balance_eur / btc_price_eur
    position_size_btc      = balance_btc * leverage * (1 - POSITION_FEE_MARGIN)
    position_size_eur      = position_size_btc * btc_price_eur
    current_trade_size_btc = balance_btc * leverage * (1 - 0.04)
    current_trade_size_eur = current_trade_size_btc * btc_price_eur
    notional_btc           = balance_btc * leverage
    notional_eur           = notional_btc * btc_price_eur
    cost_btc               = position_size_btc
    cost_usd               = cost_btc * entry_price
    risk_eur               = balance_eur * risk_per_trade   # € at risk if SL hits

    return {
        "entry":             round(entry_price, 2),
        "breakeven":         round(breakeven, 2),
        "hurdle_cost_pct":   round(hurdle_cost * 100, 4),
        "liquidation":       round(liquidation, 2),
        "tp":                round(tp, 2),
        "sl":                round(sl, 2),
        "direction":         direction,
        "tp_pct":            round(underlying_rew  * 100, 4),
        "sl_pct":            round(underlying_risk * 100, 4),
        "liq_pct":           round(abs(liquidation - entry_price) / entry_price * 100, 4),
        "position_size_btc":       round(position_size_btc, 6),
        "position_size_eur":       round(position_size_eur, 2),
        "current_trade_size_btc":  round(current_trade_size_btc, 6),
        "current_trade_size_eur":  round(current_trade_size_eur, 2),
        "cost_btc":          round(cost_btc, 6),
        "cost_usd":          round(cost_usd, 2),
        "notional_btc":      round(notional_btc, 6),
        "notional_eur":      round(notional_eur, 2),
        "risk_eur":          round(risk_eur, 2),
        "expected_8hr_high": round(expected_8hr_high, 2),
        "expected_8hr_low":  round(expected_8hr_low, 2),
        "std_8hr_usd":       round(std_8hr_usd, 2),
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _roundup(x: float) -> int:
    import math
    return math.ceil(x) if x > 0 else math.floor(x)
