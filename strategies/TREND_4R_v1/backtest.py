#!/usr/bin/env python3
"""
TREND_4R_v1 — Python backtester
Replicates the Pine Script strategy logic exactly:
  - EMA20 / EMA50 trend filter
  - MACD histogram direction
  - 20-bar structure break
  - Fixed 1% stop / 4% TP off close
  - Skip Saturday, max 1 trade per UTC day
  - 0.15%/side commission (0.30% round trip)

Fetches BTC/USD 4H OHLCV from Kraken via ccxt.
Run: python3 strategies/TREND_4R_v1/backtest.py
"""

import sys
import datetime
import ccxt
import pandas as pd
import numpy as np

# ── Parameters (match Pine script defaults) ───────────────────────────────────
STOP_PCT    = 1.0    # % price move → SL
TP_PCT      = 4.0    # % price move → TP
LEVERAGE    = 10.0
EMA_FAST    = 20
EMA_SLOW    = 50
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIG    = 9
BRK_LOOKBACK = 20
REQUIRE_BREAK = True
REQUIRE_VOL   = False
VOL_MULT      = 1.5
SKIP_SAT      = True
ONCE_PER_DAY  = True
COMMISSION    = 0.0015   # 0.15% per side
INITIAL_CAP   = 360.0    # EUR / USD (matches Pine)
MONTHS_BACK   = 14       # fetch 14 months to ensure 12 clean months after warmup


def fetch_ohlcv(symbol="BTC/USD", timeframe="4h", months=MONTHS_BACK):
    print(f"Fetching {symbol} {timeframe} from Kraken ({months} months)…")
    exchange = ccxt.kraken({"enableRateLimit": True})
    since = exchange.parse8601(
        (datetime.datetime.utcnow() - datetime.timedelta(days=months * 31))
        .strftime("%Y-%m-%dT00:00:00Z")
    )
    bars = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=720)
        if not batch:
            break
        bars.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 720:
            break
    df = pd.DataFrame(bars, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    print(f"  {len(df)} bars fetched  ({df['ts'].iloc[0].date()} → {df['ts'].iloc[-1].date()})")
    return df


def compute_indicators(df):
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    ema12 = df["close"].ewm(span=MACD_FAST, adjust=False).mean()
    ema26 = df["close"].ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=MACD_SIG, adjust=False).mean()
    df["macd_hist"] = macd_line - signal_line
    df["hist_rising"]  = df["macd_hist"] > df["macd_hist"].shift(1)
    df["hist_falling"] = df["macd_hist"] < df["macd_hist"].shift(1)

    # structure break: close beyond the highest high / lowest low of the prior N bars
    df["brk_high"] = df["high"].shift(1).rolling(BRK_LOOKBACK).max()
    df["brk_low"]  = df["low"].shift(1).rolling(BRK_LOOKBACK).min()
    df["long_break"]  = df["close"] > df["brk_high"]
    df["short_break"] = df["close"] < df["brk_low"]

    # volume spike vs 20-bar SMA
    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_spike"] = df["volume"] > df["vol_sma"] * VOL_MULT

    df["dow"] = df["ts"].dt.dayofweek   # 5 = Saturday
    df["date"] = df["ts"].dt.date

    return df


def run_backtest(df):
    equity  = INITIAL_CAP
    trades  = []
    last_trade_date = None

    for i, row in df.iterrows():
        if i < max(EMA_SLOW, MACD_SLOW + MACD_SIG, BRK_LOOKBACK) + 2:
            continue  # warmup

        long_trend  = row["close"] > row["ema_fast"] and row["ema_fast"] > row["ema_slow"]
        short_trend = row["close"] < row["ema_fast"] and row["ema_fast"] < row["ema_slow"]
        hist_rising  = row["hist_rising"]
        hist_falling = row["hist_falling"]

        brk_ok_long  = (not REQUIRE_BREAK) or row["long_break"]
        brk_ok_short = (not REQUIRE_BREAK) or row["short_break"]
        vol_ok        = (not REQUIRE_VOL)  or row["vol_spike"]

        pass_day     = (not SKIP_SAT)      or row["dow"] != 5
        pass_daycap  = (not ONCE_PER_DAY)  or (last_trade_date is None) or (row["date"] != last_trade_date)

        long_sig  = long_trend  and hist_rising  and brk_ok_long  and vol_ok and pass_day and pass_daycap
        short_sig = short_trend and hist_falling and brk_ok_short and vol_ok and pass_day and pass_daycap

        if not (long_sig or short_sig):
            continue

        direction = "long" if long_sig else "short"
        entry     = row["close"]

        if direction == "long":
            sl = entry * (1 - STOP_PCT / 100)
            tp = entry * (1 + TP_PCT / 100)
        else:
            sl = entry * (1 + STOP_PCT / 100)
            tp = entry * (1 - TP_PCT / 100)

        # find outcome: walk forward bars until SL or TP is hit
        outcome = None
        bars_held = 0
        exit_price = None
        for j in range(i + 1, len(df)):
            fut = df.iloc[j]
            bars_held += 1
            if direction == "long":
                if fut["low"] <= sl:
                    outcome = "loss"
                    exit_price = sl
                    break
                if fut["high"] >= tp:
                    outcome = "win"
                    exit_price = tp
                    break
            else:
                if fut["high"] >= sl:
                    outcome = "loss"
                    exit_price = sl
                    break
                if fut["low"] <= tp:
                    outcome = "win"
                    exit_price = tp
                    break

        if outcome is None:
            continue  # trade still open at end of data — skip

        # P&L with commission
        if direction == "long":
            raw_pct = (exit_price - entry) / entry
        else:
            raw_pct = (entry - exit_price) / entry

        pnl_pct_leveraged = raw_pct * LEVERAGE
        commission_drag   = COMMISSION * 2 * LEVERAGE  # round trip, leveraged
        net_pct           = pnl_pct_leveraged - commission_drag

        pnl_eur   = equity * net_pct
        equity   += pnl_eur

        r_realized = net_pct / (STOP_PCT / 100 * LEVERAGE)

        last_trade_date = row["date"]
        trades.append({
            "ts":         row["ts"],
            "direction":  direction,
            "entry":      entry,
            "exit":       exit_price,
            "outcome":    outcome,
            "net_pct":    net_pct,
            "pnl_eur":    pnl_eur,
            "r_realized": r_realized,
            "bars_held":  bars_held,
            "equity":     equity,
        })

    return pd.DataFrame(trades)


def print_results(trades_df, initial_cap=INITIAL_CAP):
    n = len(trades_df)
    if n == 0:
        print("\n⚠  No trades generated — check parameters / data range.")
        return

    wins  = trades_df[trades_df["outcome"] == "win"]
    losses = trades_df[trades_df["outcome"] == "loss"]
    wr    = len(wins) / n * 100

    avg_win_pct  = wins["net_pct"].mean()  * 100 if len(wins)  else 0
    avg_loss_pct = losses["net_pct"].mean() * 100 if len(losses) else 0
    avg_r        = wins["r_realized"].mean()  if len(wins)  else 0
    avg_r_loss   = losses["r_realized"].mean() if len(losses) else 0

    gross_profit = wins["pnl_eur"].sum()
    gross_loss   = abs(losses["pnl_eur"].sum())
    pf           = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    net_profit   = trades_df["pnl_eur"].sum()

    equity_curve = np.concatenate([[initial_cap], trades_df["equity"].values])
    rolling_max  = np.maximum.accumulate(equity_curve)
    drawdowns    = (equity_curve - rolling_max) / rolling_max * 100
    max_dd       = drawdowns.min()

    consec_loss = 0
    max_consec  = 0
    for o in trades_df["outcome"]:
        if o == "loss":
            consec_loss += 1
            max_consec = max(max_consec, consec_loss)
        else:
            consec_loss = 0

    avg_bars   = trades_df["bars_held"].mean()
    avg_hours  = avg_bars * 4
    trades_week = n / (len(trades_df) > 0 and
                       (trades_df["ts"].iloc[-1] - trades_df["ts"].iloc[0]).days / 7 or 1)

    print("\n" + "═" * 56)
    print("  TREND_4R_v1 — BACKTEST RESULTS")
    print("═" * 56)
    print(f"  Period         {trades_df['ts'].iloc[0].date()} → {trades_df['ts'].iloc[-1].date()}")
    print(f"  Total trades   {n}    (want ≥ 40)")
    print(f"  Win rate       {wr:.1f}%   (break-even: ~20%,  plan: 44%)")
    print(f"  Avg R (wins)   {avg_r:.2f}     (target: ~4.0)")
    print(f"  Avg R (losses) {avg_r_loss:.2f}")
    print(f"  Profit factor  {pf:.2f}    (floor: 1.0,  target: >2.0)")
    print(f"  Net profit     {net_profit:+.0f} EUR  (starting {initial_cap:.0f})")
    print(f"  Max drawdown   {max_dd:.1f}%  (ruin read at 10x)")
    print(f"  Max consec loss {max_consec}    (7 in a row ≈ −50% at 10x)")
    print(f"  Avg hold       {avg_hours:.0f} hrs  ({avg_bars:.1f} bars)")
    print(f"  Trades/week    {trades_week:.1f}")
    print("═" * 56)

    # verdict
    print()
    if wr >= 35 and avg_r >= 3:
        verdict = "GREEN LIGHT — premise holds. Proceed to forward-test + ingestion."
    elif 20 <= wr < 35:
        verdict = "MARGINAL — 1% stop bleeding on noise. Try wider stop (1.5–2%) + lower leverage."
    else:
        verdict = "FAILED — WR below breakeven. Entry quality does not survive 1% stop. Fix entries."
    print(f"  Verdict: {verdict}")
    print()

    return {
        "n": n, "wr_pct": round(wr, 1), "avg_r": round(avg_r, 2),
        "pf": round(pf, 2), "net_eur": round(net_profit, 0),
        "max_dd_pct": round(max_dd, 1), "max_consec_loss": max_consec,
        "avg_hold_hrs": round(avg_hours, 0),
    }


if __name__ == "__main__":
    df = fetch_ohlcv()
    df = compute_indicators(df)
    trades = run_backtest(df)
    results = print_results(trades)

    if results:
        # write numbers into BASELINE.md table
        import re, pathlib
        baseline_path = pathlib.Path(__file__).parent / "BASELINE.md"
        content = baseline_path.read_text()

        def fill(metric_pattern, value):
            return re.sub(
                rf"(\|\s*{metric_pattern}\s*\|)[^|]*(\|)",
                rf"\1 {value} \2",
                content,
            )

        # non-destructive: only fill if still blank
        if "| n | " not in content:
            content = content  # baseline still has blank cells — fill them
            rows = [
                (r"Total trades \(n\)", results["n"]),
                (r"\*\*Win rate %\*\*", f"{results['wr_pct']}%"),
                (r"\*\*Avg R.*?\*\*", f"{results['avg_r']}"),
                (r"Profit factor", results["pf"]),
                (r"Net profit", f"{results['net_eur']} EUR"),
                (r"\*\*Max drawdown %\*\*", f"{results['max_dd_pct']}%"),
                (r"Max consecutive losses", results["max_consec_loss"]),
                (r"Avg bars in trade", f"{results['avg_hold_hrs']/4:.1f} ({results['avg_hold_hrs']:.0f}h)"),
            ]
            for pattern, val in rows:
                new = re.sub(
                    rf"(\| {pattern}[^|]*\|)[^|]*(\|[^|]*\|)",
                    rf"\1 {val} \2",
                    content,
                )
                if new != content:
                    content = new

            baseline_path.write_text(content)
            print(f"  BASELINE.md updated: {baseline_path}")
        else:
            print("  BASELINE.md already filled — not overwritten.")
