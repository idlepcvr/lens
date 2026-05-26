from datetime import date, datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ─── Goal Tracker ─────────────────────────────────────────────────────────────

class GoalRequest(BaseModel):
    start_balance:   float
    target_balance:  float
    target_date:     date
    trades_per_week: float
    win_rate:        float
    rr_ratio:        float
    leverage:        float
    max_drawdown_allowed:  float          = 0.50
    losses_allowed:        int            = 20
    fractional_kelly:      float          = 1.0 / 6.0
    execution_fill_factor: float          = 1.0
    risk_per_trade:          Optional[float] = None
    btc_price_eur:           Optional[float] = None
    btc_growth_monthly:      float          = 0.04
    min_underlying_stop_pct: Optional[float] = None   # ATR noise floor

    @field_validator("win_rate")
    @classmethod
    def win_rate_range(cls, v):
        if not (0 < v < 1):
            raise ValueError("win_rate must be between 0 and 1")
        return v

    @field_validator("rr_ratio", "trades_per_week", "start_balance",
                     "target_balance", "leverage")
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("must be positive")
        return v


class GoalResponse(BaseModel):
    # Time
    days_remaining:   int
    weeks_remaining:  float
    months_remaining: float
    total_interest:   float
    # Growth rates (%)
    daily_rate:     float
    weekly_rate:    float
    monthly_rate:   float
    quarterly_rate: float
    annual_rate:    float
    # Per-trade model
    per_trade_ev:           float
    per_trade_ev_required:  float
    underlying_win_pct:     float
    underlying_loss_pct:    float
    goal_pct:               float
    market_move_needed:     float
    actual_rr:              float
    r_multiple:             float
    expectancy_pct_of_risk: float
    total_trades:           int
    trades_needed:          int
    trades_to_double:       Optional[float]
    # Leverage / Kelly / risk
    leverage:              float
    full_kelly:            float
    fractional_kelly:      float
    kelly_risk:            float
    dd_risk_constraint:    float
    dd_implied_leverage:   Optional[float]
    optimal_risk_pct:      float
    risk_per_trade:        float
    required_risk_pct:     Optional[float]
    required_leverage:     Optional[float]
    weeks_to_goal_actual:  Optional[float]
    execution_fill_factor: float
    # Account impacts
    acct_gain_win:    float
    acct_loss_loss:   float
    geometric_drift:  float
    # Risk analytics
    typical_win:           float
    typical_loss:          float
    avg_growth_per_trade:  float
    trade_volatility:      float
    ruin_threshold:        float
    risk_of_ruin:          float
    ror_label:             str
    downside_distance:     float
    upside_distance:       float
    sharpe_ratio:          float
    profit_factor:         Optional[float]
    losses_to_ruin:        int
    wins_to_breakeven:     int
    max_drawdown_allowed:  float
    losses_allowed:        int
    # Growth projections
    weekly_growth_eur:    float
    monthly_growth_eur:   float
    quarterly_growth_eur: float
    weekly_growth_pct:    float
    monthly_growth_pct:   float
    quarterly_growth_pct: float
    # BTC projections
    btc_price_at_goal: Optional[float]
    target_aum_btc:    Optional[float]
    # Monte Carlo
    mc_p05: float
    mc_p50: float
    mc_p95: float
    # ATR adaptation (Layer 2)
    atr_adjusted:    bool           = False
    original_sl_pct: Optional[float] = None
    adjusted_sl_pct: Optional[float] = None


# ─── Position Calculator ──────────────────────────────────────────────────────

class PositionRequest(BaseModel):
    # Goal inputs (recomputed server-side — keeps API stateless)
    start_balance:   float
    target_balance:  float
    target_date:     date
    trades_per_week: float
    win_rate:        float
    rr_ratio:        float
    leverage:        float
    max_drawdown_allowed:  float          = 0.50
    losses_allowed:        int            = 20
    fractional_kelly:      float          = 1.0 / 6.0
    execution_fill_factor: float          = 1.0
    risk_per_trade:        Optional[float] = None
    # Position inputs
    entry_price:    float
    direction:      Literal["long", "short"]
    balance_eur:    float
    btc_price_eur:  float
    btc_std_dev:    float = 0.0356


class PositionResponse(BaseModel):
    entry:       float
    breakeven:   float
    hurdle_cost_pct: float
    liquidation: float
    tp:          float
    sl:          float
    direction:   str
    tp_pct:  float
    sl_pct:  float
    liq_pct: float
    position_size_btc:      float
    position_size_eur:      float
    current_trade_size_btc: float
    current_trade_size_eur: float
    cost_btc:   float
    cost_usd:   float
    notional_btc: float
    notional_eur: float
    risk_eur:     float
    expected_8hr_high: float
    expected_8hr_low:  float
    std_8hr_usd:       float


# ─── Trade Log ────────────────────────────────────────────────────────────────

class TradeCreate(BaseModel):
    symbol:    str = "BTC/USD"
    direction: Literal["long", "short"]
    entry:     float
    size:      float
    leverage:  float
    tp:        Optional[float] = None
    sl:        Optional[float] = None
    exit:      Optional[float] = None
    pnl:       Optional[float] = None
    fees:      Optional[float] = None
    notes:     Optional[str]   = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    followed_plan:     Optional[bool]  = None
    followed_strategy: Optional[bool]  = None
    balance_after:     Optional[float] = None
    # Exchange metadata (None for manual trades)
    venue:        Optional[str] = None
    contract:     Optional[str] = None
    market_type:  Optional[str] = None
    fill_type:    Optional[str] = None
    order_type:   Optional[str] = None
    funding_cost: Optional[float] = None
    fill_uuid:    Optional[str] = None
    fill_count:   Optional[int] = None
    # LENS: back-link to originating signal (UUID)
    linked_signal_id: Optional[str] = None


class TradeUpdate(BaseModel):
    entry:        Optional[float] = None
    exit:         Optional[float] = None
    pnl:          Optional[float] = None
    fees:         Optional[float] = None
    tp:           Optional[float] = None
    sl:           Optional[float] = None
    size:         Optional[float] = None
    leverage:     Optional[float] = None
    funding_cost: Optional[float] = None
    direction:   Optional[Literal["long", "short"]] = None
    symbol:      Optional[str] = None
    venue:       Optional[str] = None
    market_type: Optional[str] = None
    order_type:  Optional[str] = None
    fill_count:  Optional[int] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    notes:             Optional[str]   = None
    followed_plan:     Optional[bool]  = None
    followed_strategy: Optional[bool]  = None
    balance_after:     Optional[float] = None
    linked_signal_id:  Optional[str]   = None


class TradeResponse(TradeCreate):
    id:        int
    opened_at: datetime
    is_open:   bool


# ─── Signals (LENS feature schema — locked) ───────────────────────────────────

class SignalIngest(BaseModel):
    """Payload sent by TradingView Pine Script alert webhook.

    Every Setup + Trade plan field is required so the dataset is complete.
    Context + outcome fields are filled later in the lifecycle.
    """
    # Identity
    signal_id:        str
    strategy_name:    str
    strategy_version: str
    received_at:      Optional[datetime] = None     # server-side default if absent

    # Context
    symbol:        str
    venue:         Optional[str] = None             # kraken | bybit
    session_utc:   Optional[Literal["asia", "london", "ny", "off-hours"]] = None
    btc_1d_trend:  Optional[Literal["up", "down", "range"]] = None
    btc_1w_trend:  Optional[Literal["up", "down", "range"]] = None
    atr_14d_pct:   Optional[float] = None

    # Setup
    trigger_type:     str
    htf_bias:         Optional[Literal["bullish", "bearish", "neutral"]] = None
    mtf_confluence:   Optional[list[str]] = None
    confluence_count: Optional[int] = Field(default=None, ge=0, le=5)

    # Trade plan (REQUIRED — drives sizing + outcome calc)
    direction:          Literal["long", "short"]
    entry_price:        float
    stop_price:         float
    target_price:       float
    suggested_size_pct: Optional[float] = None
    suggested_leverage: Optional[float] = None
    expected_rr:        Optional[float] = None


class SignalDecision(BaseModel):
    status:           Literal["approved", "rejected"]
    your_conviction:  Optional[int] = Field(default=None, ge=1, le=5)
    rejection_reason: Optional[str] = None


class SignalResponse(BaseModel):
    signal_id:        str
    strategy_name:    str
    strategy_version: str
    received_at:      str

    symbol:        str
    venue:         Optional[str] = None
    session_utc:   Optional[str] = None
    btc_1d_trend:  Optional[str] = None
    btc_1w_trend:  Optional[str] = None
    atr_14d_pct:   Optional[float] = None

    trigger_type:     Optional[str] = None
    htf_bias:         Optional[str] = None
    mtf_confluence:   Optional[Any] = None
    confluence_count: Optional[int] = None

    direction:          Optional[str] = None
    entry_price:        Optional[float] = None
    stop_price:         Optional[float] = None
    target_price:       Optional[float] = None
    suggested_size_pct: Optional[float] = None
    suggested_leverage: Optional[float] = None
    expected_rr:        Optional[float] = None

    status:           str
    your_conviction:  Optional[int] = None
    rejection_reason: Optional[str] = None
    decided_at:       Optional[str] = None

    linked_trade_id:   Optional[int] = None
    outcome:           Optional[str] = None
    r_realized:        Optional[float] = None
    pnl_eur:           Optional[float] = None
    hold_duration_min: Optional[int] = None

    screenshot_path: Optional[str] = None
    notes:           Optional[str] = None
