"""
LENS prop-firm evaluation simulator.

A SEPARATE objective from the hedge-fund LENS thesis. LENS-proper optimises
compounding on your own money (risk 10%/trade for 40%). A prop eval is the
opposite game: survive hard equity walls long enough to hit a modest target.
Blow the wall once and the account (and the eval fee) is gone.

This module reuses the backtest engine's data, indicators and strategy signal
functions, then re-simulates each strategy under a prop firm's eval rules at
*legal* position sizing, and reports PASS / FAIL — both on the single historical
path and as a Monte Carlo pass-rate.

Target firm: Breakout (Kraken-backed). Rules verified 2026-06 across 3 sources,
see strategies/_prop/BREAKOUT_5K_PLAN.md.

Usage:
    python3 -m app.prop_eval                 # full table, all strategies
    from app.prop_eval import simulate_eval, monte_carlo_eval
"""

from datetime import timedelta

import numpy as np
import pandas as pd

from app.backtest_engine import load_ohlcv, add_indicators, STRATEGIES

# ─── Eval rule sets ──────────────────────────────────────────────────────────
# daily_loss_pct : max equity drop in one eval-day, off that day's start balance
# max_dd_pct     : max overall drawdown
# max_dd_type    : "static" (locked to start) | "trailing" (chases peak balance)
# profit_target_pct : gain required to pass
# max_leverage   : firm leverage cap (BTC/ETH perps)
# reset_min_utc  : minute-of-day the daily window resets (Breakout: 00:30 UTC)

EVALS: dict = {
    # Kraken Prop / Breakout fee = 0.04%/side (maker+taker), confirmed
    # kraken.com/breakout 2026-06-17. The fee is a firm/venue property, so it
    # lives on the eval rule and overrides any per-strategy commission default.
    # swap_per_day = 0.033%/day per open position (notional), charged at 00:00 UTC
    # on positions open at that time. Confirmed Breakout Program Rules 2026-03-13.
    # Applied per-trade as overnights * swap_per_day * leverage (account %).
    "BREAKOUT_1STEP_CLASSIC": {  # "Starter" on the live page
        "daily_loss_pct": 3.0,
        "max_dd_pct": 6.0,
        "max_dd_type": "static",
        "profit_target_pct": 10.0,
        "max_leverage": 5.0,
        "reset_min_utc": 30,
        "commission_per_side": 0.0004,
        "swap_per_day": 0.00033,
    },
    "BREAKOUT_1STEP_PRO": {  # "Intermediate": 12% target / 5% DD
        "daily_loss_pct": 3.0,
        "max_dd_pct": 5.0,
        "max_dd_type": "static",
        "profit_target_pct": 12.0,
        "max_leverage": 5.0,
        "reset_min_utc": 30,
        "commission_per_side": 0.0004,
        "swap_per_day": 0.00033,
    },
    "BREAKOUT_1STEP_TURBO": {  # "Advanced": 9% target / 3% DD / 3% daily
        "daily_loss_pct": 3.0,
        "max_dd_pct": 3.0,
        "max_dd_type": "static",
        "profit_target_pct": 9.0,
        "max_leverage": 5.0,
        "reset_min_utc": 30,
        "commission_per_side": 0.0004,
        "swap_per_day": 0.00033,
    },
    "BREAKOUT_2STEP_CLASSIC": {
        # Phase-1 target modelled (5%); trailing floor caps at the start balance.
        "daily_loss_pct": 4.0,
        "max_dd_pct": 8.0,
        "max_dd_type": "trailing",
        "profit_target_pct": 5.0,
        "max_leverage": 5.0,
        "reset_min_utc": 30,
        "commission_per_side": 0.0004,
        "swap_per_day": 0.00033,
    },
}


# ─── Position sizing ─────────────────────────────────────────────────────────

def _legal_leverage(stop_pct: float, risk_per_trade_pct: float,
                    max_leverage: float) -> tuple:
    """Leverage so a full stop-out loses exactly risk_per_trade_pct of account,
    capped at the firm's max leverage. Returns (leverage, actual_risk_pct)."""
    want = risk_per_trade_pct / stop_pct
    lev = min(want, max_leverage)
    actual_risk = stop_pct * lev
    return lev, actual_risk


def _eval_day(ts, reset_min_utc: int):
    """The eval-day a bar belongs to, given the daily reset offset."""
    return (ts - timedelta(minutes=reset_min_utc)).date()


# ─── Per-trade outcome extraction ────────────────────────────────────────────

def _trade_log(df, signal_fn, params, eval_rule, risk_per_trade_pct):
    """Walk the data once, return an ordered list of closed trades:
    {eval_day, pnl_pct} where pnl_pct is net % of account at legal sizing.
    SL-first (conservative). Honours the strategy's own discipline gates."""
    stop_pct   = params.get("stop_pct", 1.0) / 100
    tp_pct     = params.get("tp_pct", 4.0) / 100
    # Firm fee (eval rule) wins over the strategy's own default — the venue
    # sets commissions, not the setup. Breakout = 0.0004/side.
    commission = eval_rule.get("commission_per_side", params.get("commission", 0.0015))
    # 0.033%/day per open position (notional), charged at 00:00 UTC. Cost in
    # account terms scales with leverage: swap_per_day * lev per overnight held.
    swap_per_day = eval_rule.get("swap_per_day", 0.0)
    skip_sat   = params.get("skip_sat", True)
    cooldown   = params.get("cooldown_bars", 4)
    once_per_day = params.get("once_per_day", True)

    lev, _ = _legal_leverage(params.get("stop_pct", 1.0),
                             risk_per_trade_pct, eval_rule["max_leverage"])
    reset = eval_rule["reset_min_utc"]

    win_pct  =  tp_pct   * lev - commission * 2 * lev
    loss_pct = -(stop_pct * lev + commission * 2 * lev)
    swap_lev = swap_per_day * lev   # cost per 00:00-UTC crossing, account fraction

    trades = []
    in_trade = False
    direction = None
    entry_price = 0.0
    entry_ts = None
    last_entry_bar = -999
    last_trade_day = None

    for i in range(1, len(df)):
        ts = df.index[i]
        if in_trade:
            hi, lo = df["high"].iloc[i], df["low"].iloc[i]
            sl_long  = entry_price * (1 - stop_pct)
            tp_long  = entry_price * (1 + tp_pct)
            sl_short = entry_price * (1 + stop_pct)
            tp_short = entry_price * (1 - tp_pct)
            result = None
            if direction == "long":
                if lo <= sl_long:   result = "loss"
                elif hi >= tp_long: result = "win"
            else:
                if hi >= sl_short:  result = "loss"
                elif lo <= tp_short: result = "win"
            if result:
                # swap: one charge per 00:00-UTC boundary the position was open
                # across (entry .date() -> exit .date(), both UTC).
                overnights = (ts.date() - entry_ts.date()).days
                swap_cost = overnights * swap_lev
                base = win_pct if result == "win" else loss_pct
                trades.append({
                    "eval_day": _eval_day(ts, reset),
                    "pnl_pct": (base - swap_cost) * 100,
                    # worst adverse excursion before the trade resolves, in account
                    # %: a full move to the price stop (fees not yet paid intra-trade).
                    # Even eventual winners transiently dip ~this far → Breakout
                    # checks LIVE equity, so this is what can trip a wall mid-trade.
                    "dip_pct": stop_pct * lev * 100,
                })
                in_trade = False
            continue

        dow = ts.weekday()
        if skip_sat and dow == 5:
            continue
        trade_day = _eval_day(ts, reset)
        if once_per_day and last_trade_day == trade_day:
            continue
        if i - last_entry_bar < cooldown:
            continue

        sig = signal_fn(df, i, params)
        if sig in ("long", "short"):
            in_trade = True
            direction = sig
            entry_price = df["close"].iloc[i]
            entry_ts = ts
            last_entry_bar = i
            last_trade_day = trade_day

    return trades


def _walk_eval(daily_trades, account, eval_rule, open_equity=True, path=None):
    """Replay an ordered list of (eval_day -> [(pnl_pct, dip_pct),...]) under the
    eval rules. Returns (result, final_balance, n_trades, fail_reason).

    Pass `path` (a list) to have the balance after every closed trade appended —
    that's what the /prop-goal cone samples. Kept as an out-param so the hot MC
    loop allocates nothing when it isn't asked for.

    open_equity=True (default) also tests each trade's intra-trade trough (a full
    adverse move to its price stop) against the floor + daily wall BEFORE the
    closed result is applied — Breakout checks live equity, so a trade that ends
    a winner can still bust the eval if it dipped through a wall on the way.
    Set False for the old closed-PnL-only behaviour (optimistic)."""
    daily = eval_rule["daily_loss_pct"] / 100
    max_dd = eval_rule["max_dd_pct"] / 100
    target = eval_rule["profit_target_pct"] / 100
    trailing = eval_rule["max_dd_type"] == "trailing"

    balance = account
    peak = account
    floor = account * (1 - max_dd)
    target_balance = account * (1 + target)
    n = 0

    for day_pnls in daily_trades:
        day_start = balance
        for item in day_pnls:
            pnl, dip = item if isinstance(item, tuple) else (item, 0.0)
            # open-equity: transient low-water mark before this trade resolves
            if open_equity and dip:
                trough = balance * (1 - dip / 100)
                if trough <= floor:
                    return "FAIL", trough, n + 1, "max_drawdown_intratrade"
                if trough <= day_start * (1 - daily):
                    return "FAIL", trough, n + 1, "daily_loss_intratrade"
            balance *= (1 + pnl / 100)
            n += 1
            if path is not None:
                path.append(balance)
            if trailing:
                if balance > peak:
                    peak = balance
                # Breakout 2-step floor trails peak but caps at start balance
                floor = min(account, peak * (1 - max_dd))
            if balance <= floor:
                return "FAIL", balance, n, "max_drawdown"
            if balance <= day_start * (1 - daily):
                return "FAIL", balance, n, "daily_loss"
            if balance >= target_balance:
                return "PASS", balance, n, None
    return "INCOMPLETE", balance, n, "ran_out_of_data"


def _group_by_day(trades):
    """[{eval_day, pnl_pct, dip_pct}] -> ordered [[(pnl, dip),...] per day]."""
    out, cur_day, bucket = [], None, []
    for t in trades:
        if t["eval_day"] != cur_day:
            if bucket:
                out.append(bucket)
            bucket, cur_day = [], t["eval_day"]
        bucket.append((t["pnl_pct"], t.get("dip_pct", 0.0)))
    if bucket:
        out.append(bucket)
    return out


# ─── Public: single historical path ──────────────────────────────────────────

def simulate_eval(strategy_name, eval_name="BREAKOUT_1STEP_CLASSIC",
                  account=5000.0, risk_per_trade_pct=1.0, months=30,
                  open_equity=True, df=None):
    if strategy_name not in STRATEGIES:
        return {"error": f"unknown strategy: {strategy_name}"}
    if eval_name not in EVALS:
        return {"error": f"unknown eval: {eval_name}"}

    strat = STRATEGIES[strategy_name]
    rule = EVALS[eval_name]
    tf = strat.get("timeframe", "4h")
    if df is None:
        df = add_indicators(load_ohlcv(months=months, timeframe=tf))

    trades = _trade_log(df, strat["signal_fn"], strat["params"], rule,
                        risk_per_trade_pct)
    daily_trades = _group_by_day(trades)
    result, final, n, reason = _walk_eval(daily_trades, account, rule, open_equity)

    lev, actual_risk = _legal_leverage(strat["params"].get("stop_pct", 1.0),
                                       risk_per_trade_pct, rule["max_leverage"])
    return {
        "strategy": strategy_name,
        "eval": eval_name,
        "account": account,
        "risk_per_trade_pct": risk_per_trade_pct,
        "legal_leverage": round(lev, 2),
        "actual_risk_pct": round(actual_risk, 2),
        "result": result,
        "final_balance": round(final, 2),
        "trades_to_result": n,
        "total_trades_available": len(trades),
        "fail_reason": reason,
    }


# ─── Monte Carlo core ────────────────────────────────────────────────────────

def _run_mc(daily_trades, account, rule, paths, max_days, seed, open_equity=True):
    """Bootstrap whole eval-days (preserves intraday clustering for the daily
    limit) and resample until PASS / FAIL / out of days."""
    rng = np.random.default_rng(seed)
    n_days = len(daily_trades)
    passes = fails_dd = fails_daily = incomplete = 0
    trades_to_resolve = []
    for _ in range(paths):
        idx = rng.integers(0, n_days, size=max_days)
        path_days = [daily_trades[k] for k in idx]
        result, _, n, reason = _walk_eval(path_days, account, rule, open_equity)
        if result == "PASS":
            passes += 1
            trades_to_resolve.append(n)
        elif result == "FAIL" and reason in ("max_drawdown", "max_drawdown_intratrade"):
            fails_dd += 1
            trades_to_resolve.append(n)
        elif result == "FAIL" and reason in ("daily_loss", "daily_loss_intratrade"):
            fails_daily += 1
            trades_to_resolve.append(n)
        else:
            incomplete += 1
    return {
        "paths": paths,
        "pass_rate_pct": round(passes / paths * 100, 1),
        "fail_max_dd_pct": round(fails_dd / paths * 100, 1),
        "fail_daily_pct": round(fails_daily / paths * 100, 1),
        "incomplete_pct": round(incomplete / paths * 100, 1),
        "median_trades_to_resolve": int(np.median(trades_to_resolve)) if trades_to_resolve else None,
    }


# ─── Public: Monte Carlo pass-rate (single strategy) ──────────────────────────

def monte_carlo_eval(strategy_name, eval_name="BREAKOUT_1STEP_CLASSIC",
                     account=5000.0, risk_per_trade_pct=1.0, months=30,
                     paths=5000, max_days=252, seed=42, open_equity=True, df=None):
    if strategy_name not in STRATEGIES:
        return {"error": f"unknown strategy: {strategy_name}"}
    rule = EVALS[eval_name]
    strat = STRATEGIES[strategy_name]
    tf = strat.get("timeframe", "4h")
    if df is None:
        df = add_indicators(load_ohlcv(months=months, timeframe=tf))
    trades = _trade_log(df, strat["signal_fn"], strat["params"], rule,
                        risk_per_trade_pct)
    daily_trades = _group_by_day(trades)
    if not daily_trades:
        return {"error": "no trades", "strategy": strategy_name}
    mc = _run_mc(daily_trades, account, rule, paths, max_days, seed, open_equity)
    mc.update({
        "strategy": strategy_name,
        "eval": eval_name,
        "risk_per_trade_pct": risk_per_trade_pct,
        "legal_leverage": round(_legal_leverage(strat["params"].get("stop_pct", 1.0), risk_per_trade_pct, rule["max_leverage"])[0], 2),
    })
    return mc


# ─── Single-call summary for the /prop page (AUTO mode) ───────────────────────

_DF_CACHE: dict = {}

def _cached_df(months, tf):
    """Load OHLCV+indicators once per (months, timeframe); reused across API
    calls so the page stays snappy on repeated config changes."""
    key = (months, tf)
    if key not in _DF_CACHE:
        _DF_CACHE[key] = add_indicators(load_ohlcv(months=months, timeframe=tf))
    return _DF_CACHE[key]


def eval_summary(strategy_name, eval_name="BREAKOUT_1STEP_CLASSIC", account=5000.0,
                 risk_per_trade_pct=2.0, months=30, paths=3000, open_equity=True):
    """Everything the /prop page needs for one config in a single dict: real
    open-equity pass%, the eval walls, measured WR/R, sizing, and est months.
    Source of truth — the page reads this so its numbers can never go stale."""
    if strategy_name not in STRATEGIES:
        return {"error": f"unknown strategy: {strategy_name}"}
    if eval_name not in EVALS:
        return {"error": f"unknown eval: {eval_name}"}
    strat = STRATEGIES[strategy_name]
    rule = EVALS[eval_name]
    tf = strat.get("timeframe", "4h")
    df = _cached_df(months, tf)
    trades = _trade_log(df, strat["signal_fn"], strat["params"], rule, risk_per_trade_pct)
    n = len(trades)
    daily = _group_by_day(trades)
    wins = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    wr = (len(wins) / n * 100) if n else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    mc = _run_mc(daily, account, rule, paths, 252, 42, open_equity) if daily else {}
    lev, actual = _legal_leverage(strat["params"].get("stop_pct", 1.0),
                                  risk_per_trade_pct, rule["max_leverage"])
    tpm = (n / months) if months else 0.0
    med = mc.get("median_trades_to_resolve")
    est_mo = round(med / tpm, 1) if med and tpm else None
    stop = strat["params"].get("stop_pct", 1.0)
    tp = strat["params"].get("tp_pct", 4.0)
    return {
        "strategy": strategy_name, "eval": eval_name, "tf": tf,
        "account": account, "risk_pct": risk_per_trade_pct,
        "months": months, "open_equity": open_equity,
        "pass_pct": mc.get("pass_rate_pct"),
        "fail_dd_pct": mc.get("fail_max_dd_pct"),
        "fail_daily_pct": mc.get("fail_daily_pct"),
        "incomplete_pct": mc.get("incomplete_pct"),
        "median_trades": med, "est_months": est_mo,
        "trades_total": n, "trades_per_month": round(tpm, 2),
        "win_rate_pct": round(wr, 1),
        "avg_win_pct": round(avg_win, 2), "avg_loss_pct": round(avg_loss, 2),
        "stop_pct": stop, "tp_pct": tp,
        "r_multiple": round(tp / stop, 1) if stop else None,
        "leverage": round(lev, 2), "actual_risk_pct": round(actual, 2),
        "target_pct": rule["profit_target_pct"], "daily_pct": rule["daily_loss_pct"],
        "dd_pct": rule["max_dd_pct"], "dd_type": rule["max_dd_type"],
    }


def list_configs():
    """Dropdown metadata for the page: every strategy (with tf + R) + every eval
    (with its walls)."""
    strusing = []
    for name, s in STRATEGIES.items():
        p = s.get("params", {})
        stop, tp = p.get("stop_pct"), p.get("tp_pct")
        strusing.append({
            "name": name, "tf": s.get("timeframe", "4h"),
            "r": round(tp / stop, 1) if stop and tp else None,
        })
    evs = [{
        "name": k, "target_pct": v["profit_target_pct"], "daily_pct": v["daily_loss_pct"],
        "dd_pct": v["max_dd_pct"], "dd_type": v["max_dd_type"],
    } for k, v in EVALS.items()]
    return {"strategies": strusing, "evals": evs}


# ─── Portfolio: multiple strategies, one account, shared walls ────────────────

def _portfolio_daily_trades(strategy_names, rule, risk_per_trade_pct, months,
                            _df_cache=None):
    """Merge several strategies' trade logs onto one timeline, grouped per
    eval-day. All strategies share the same account, so a day's drawdown is the
    sum of every strategy's trades that day — that's where stacking can either
    speed the pass or trip the daily wall."""
    if _df_cache is None:
        _df_cache = {}
    all_trades = []
    for name in strategy_names:
        if name not in STRATEGIES:
            # Not a real backtest strategy (no signal_fn) → skip. Prop trades only
            # strategies the engine can actually fire; hedge bar-context setups are
            # not portable to the eval (no backtest), so they never enter a basket.
            continue
        strat = STRATEGIES[name]
        tf = strat.get("timeframe", "4h")
        if tf not in _df_cache:
            _df_cache[tf] = add_indicators(load_ohlcv(months=months, timeframe=tf))
        t = _trade_log(_df_cache[tf], strat["signal_fn"], strat["params"],
                       rule, risk_per_trade_pct)
        all_trades.extend(t)
    # Sort onto one timeline so same-day trades from different strategies group.
    all_trades.sort(key=lambda x: x["eval_day"])
    return _group_by_day(all_trades), len(all_trades)


def portfolio_eval(strategy_names, eval_name="BREAKOUT_1STEP_CLASSIC",
                   account=5000.0, risk_per_trade_pct=0.5, months=30,
                   open_equity=True):
    """Single historical path for a basket of strategies on one account."""
    rule = EVALS[eval_name]
    daily_trades, n = _portfolio_daily_trades(strategy_names, rule,
                                              risk_per_trade_pct, months)
    result, final, nt, reason = _walk_eval(daily_trades, account, rule, open_equity)
    return {
        "strategies": strategy_names,
        "eval": eval_name,
        "result": result,
        "final_balance": round(final, 2),
        "trades_to_result": nt,
        "total_trades_available": n,
        "trades_per_month": round(n / months, 2),
        "fail_reason": reason,
    }


def monte_carlo_portfolio(strategy_names, eval_name="BREAKOUT_1STEP_CLASSIC",
                          account=5000.0, risk_per_trade_pct=0.5, months=30,
                          paths=5000, max_days=252, seed=42, open_equity=True):
    """Monte Carlo pass-rate for a basket + estimated months to pass, derived
    from median trades-to-pass over the basket's real trade frequency."""
    rule = EVALS[eval_name]
    daily_trades, n = _portfolio_daily_trades(strategy_names, rule,
                                              risk_per_trade_pct, months)
    if not daily_trades:
        return {"error": "no trades", "strategies": strategy_names}
    mc = _run_mc(daily_trades, account, rule, paths, max_days, seed, open_equity)
    tpm = n / months
    med = mc["median_trades_to_resolve"]
    mc.update({
        "strategies": strategy_names,
        "eval": eval_name,
        "risk_per_trade_pct": risk_per_trade_pct,
        "trades_per_month": round(tpm, 2),
        "est_months_to_pass": round(med / tpm, 1) if med and tpm else None,
    })
    return mc


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _print_table(eval_name="BREAKOUT_1STEP_CLASSIC", account=5000.0,
                 risk_per_trade_pct=1.0, months=30, paths=3000):
    rule = EVALS[eval_name]
    print(f"\n{'='*92}")
    print(f"PROP EVAL: {eval_name}  |  account ${account:,.0f}  |  "
          f"risk {risk_per_trade_pct}%/trade")
    print(f"rules: {rule['profit_target_pct']}% target, "
          f"{rule['daily_loss_pct']}% daily, {rule['max_dd_pct']}% "
          f"{rule['max_dd_type']} DD, {rule['max_leverage']}x cap")
    print(f"{'='*92}")
    print(f"{'strategy':<22}{'lev':>5}{'hist':>7}{'pass%':>8}"
          f"{'failDD%':>9}{'failDay%':>10}{'incmp%':>9}{'med.trd':>9}")
    print(f"{'-'*92}")
    rows = []
    for name in STRATEGIES:
        mc = monte_carlo_eval(name, eval_name, account, risk_per_trade_pct,
                              months, paths=paths)
        if "error" in mc:
            continue
        hist = simulate_eval(name, eval_name, account, risk_per_trade_pct, months)
        rows.append((mc["pass_rate_pct"], name, mc, hist))
    for _, name, mc, hist in sorted(rows, reverse=True):
        print(f"{name:<22}{mc['legal_leverage']:>4.1f}x"
              f"{hist['result'][:4]:>7}{mc['pass_rate_pct']:>8}"
              f"{mc['fail_max_dd_pct']:>9}{mc['fail_daily_pct']:>10}"
              f"{mc['incomplete_pct']:>9}"
              f"{str(mc['median_trades_to_resolve']):>9}")
    print(f"{'-'*92}\n")


def _search_portfolios(eval_name="BREAKOUT_1STEP_CLASSIC", account=5000.0,
                       months=30, paths=4000, min_pass=90.0):
    """Search single + stacked baskets across risk levels for the fastest config
    that still clears min_pass%. The whole point of stacking: more trades/month
    without adding per-trade risk → shorter eval."""
    baskets = [
        ["ASIAN_RSI_DIP_v1"],
        ["ASIAN_PULLBACK_v2"],
        ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v2"],
        ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v1"],
        ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v2", "ASIAN_PULLBACK_v1"],
    ]
    risks = [0.5, 0.75, 1.0]
    rule = EVALS[eval_name]
    print(f"\n{'='*100}")
    print(f"PORTFOLIO SEARCH: {eval_name}  |  ${account:,.0f}  |  target ≥{min_pass}% pass")
    print(f"rules: {rule['profit_target_pct']}% target, {rule['daily_loss_pct']}% daily, "
          f"{rule['max_dd_pct']}% {rule['max_dd_type']} DD")
    print(f"{'='*100}")
    print(f"{'basket':<46}{'risk%':>6}{'pass%':>8}{'failDay%':>10}"
          f"{'trd/mo':>8}{'medTrd':>8}{'~months':>9}")
    print(f"{'-'*100}")
    rows = []
    for basket in baskets:
        for r in risks:
            mc = monte_carlo_portfolio(basket, eval_name, account, r, months,
                                       paths=paths)
            if "error" in mc:
                continue
            label = "+".join(s.replace("ASIAN_", "").replace("_v", "v")
                             for s in basket)
            rows.append((mc, label, r))
    # Sort: clears bar first, then fastest (fewest months)
    def keyf(x):
        mc = x[0]
        clears = mc["pass_rate_pct"] >= min_pass
        months_to = mc["est_months_to_pass"] or 999
        return (not clears, months_to)
    for mc, label, r in sorted(rows, key=keyf):
        flag = "✓" if mc["pass_rate_pct"] >= min_pass else " "
        print(f"{flag}{label:<45}{r:>6}{mc['pass_rate_pct']:>8}"
              f"{mc['fail_daily_pct']:>10}{mc['trades_per_month']:>8}"
              f"{str(mc['median_trades_to_resolve']):>8}"
              f"{str(mc['est_months_to_pass']):>9}")
    print(f"{'-'*100}")
    print("✓ = clears pass bar. Sorted: clears-bar first, then fastest.\n")


def _full_sweep(eval_name="BREAKOUT_1STEP_CLASSIC", account=5000.0, months=30,
                paths=3000, fast_months=2.0):
    """Exhaustive: every strategy in the registry × every risk level. Reports
    pass% + est months to pass. Two views: the whole frontier, then ONLY the
    configs that pass in <= fast_months, ranked by pass%."""
    rule = EVALS[eval_name]
    risks = [0.5, 0.75, 1.0, 1.5, 2.0]
    print(f"\n{'#'*104}")
    print(f"# FULL SWEEP: {eval_name}  ${account:,.0f}  | "
          f"{rule['profit_target_pct']}% target, {rule['daily_loss_pct']}% daily, "
          f"{rule['max_dd_pct']}% {rule['max_dd_type']} DD | {len(STRATEGIES)} strategies")
    print(f"{'#'*104}")
    rows = []
    _df_cache: dict = {}  # timeframe → OHLCV+indicators, loaded once (not per risk)
    for name in STRATEGIES:
        tf = STRATEGIES[name].get("timeframe", "4h")
        if tf not in _df_cache:
            _df_cache[tf] = add_indicators(load_ohlcv(months=months, timeframe=tf))
        df = _df_cache[tf]
        for r in risks:
            mc = monte_carlo_eval(name, eval_name, account, r, months, paths=paths, df=df)
            if "error" in mc:
                continue
            sim = simulate_eval(name, eval_name, account, r, months, df=df)
            tpm = sim["total_trades_available"] / months
            med = mc["median_trades_to_resolve"]
            mo = round(med / tpm, 1) if med and tpm else None
            rows.append({
                "strategy": name, "tf": STRATEGIES[name].get("timeframe", "4h"),
                "risk": r, "pass": mc["pass_rate_pct"],
                "failday": mc["fail_daily_pct"], "tpm": round(tpm, 2),
                "med": med, "months": mo,
            })

    def show(rs, title):
        print(f"\n{title}")
        print(f"{'strategy':<28}{'tf':>4}{'risk%':>6}{'pass%':>7}"
              f"{'failDay%':>9}{'trd/mo':>8}{'~months':>9}")
        print("-" * 71)
        for x in rs:
            print(f"{x['strategy']:<28}{x['tf']:>4}{x['risk']:>6}{x['pass']:>7}"
                  f"{x['failday']:>9}{x['tpm']:>8}{str(x['months']):>9}")

    # View 1: configs that pass within fast_months, best pass% first
    fast = [x for x in rows if x["months"] is not None and x["months"] <= fast_months]
    fast.sort(key=lambda x: -x["pass"])
    show(fast or [], f"### PASSES IN <= {fast_months} MONTHS (ranked by pass%) — "
                     f"{len(fast)} configs")
    if not fast:
        print("  (none — no config clears the target that fast)")

    # View 2: overall best pass% regardless of speed
    top = sorted(rows, key=lambda x: -x["pass"])[:12]
    show(top, "### TOP 12 BY PASS% (any speed)")

    # View 3: the speed/probability frontier — best pass% at each month bucket
    print("\n### FRONTIER: best pass% achievable at each speed")
    print(f"{'within months':>14}{'best pass%':>12}{'config':>40}")
    print("-" * 66)
    for cap in [1, 2, 3, 6, 9, 12]:
        cand = [x for x in rows if x["months"] is not None and x["months"] <= cap]
        if cand:
            b = max(cand, key=lambda x: x["pass"])
            print(f"{cap:>14}{b['pass']:>12}{b['strategy']+' @'+str(b['risk'])+'%':>40}")
    print()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "table"
    if mode == "sweep":
        _full_sweep()
    elif mode == "sweep-all":
        # Every strategy × every risk × EVERY eval — open-equity re-confirm.
        for ev in EVALS:
            _full_sweep(eval_name=ev)
    elif mode == "search":
        _search_portfolios()
    else:
        eval_name = sys.argv[1] if len(sys.argv) > 1 else "BREAKOUT_1STEP_CLASSIC"
        risk = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
        _print_table(eval_name=eval_name, risk_per_trade_pct=risk)
