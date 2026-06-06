#!/usr/bin/env python3
"""
Parameter sweep: test multiple stop widths / RR ratios
to find where WR crosses viability on real BTC/USD 4H data.
"""

import datetime
import sys
import ccxt
import pandas as pd
import numpy as np

EMA_FAST     = 20
EMA_SLOW     = 50
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIG     = 9
BRK_LOOKBACK = 20
REQUIRE_BREAK = True
REQUIRE_VOL   = False
SKIP_SAT      = True
ONCE_PER_DAY  = True
COMMISSION    = 0.0015
INITIAL_CAP   = 360.0


def _fetch_chunk(exchange, symbol, timeframe, start_str, end_str=None):
    since = exchange.parse8601(start_str)
    until = exchange.parse8601(end_str) if end_str else None
    bars  = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        if until:
            batch = [b for b in batch if b[0] < until]
        bars.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000 or (until and since >= until):
            break
    return bars


def fetch_ohlcv_multi(symbol="BTC/USDT:USDT", timeframe="4h"):
    print(f"Fetching {symbol} {timeframe} from Bybit (Jan 2023 → now)…", end=" ", flush=True)
    exchange = ccxt.bybit({"enableRateLimit": True})
    bars = (
        _fetch_chunk(exchange, symbol, timeframe, "2023-01-01T00:00:00Z", "2024-06-01T00:00:00Z")
        + _fetch_chunk(exchange, symbol, timeframe, "2024-06-01T00:00:00Z", "2025-06-01T00:00:00Z")
        + _fetch_chunk(exchange, symbol, timeframe, "2025-06-01T00:00:00Z")
    )
    df = pd.DataFrame(bars, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    print(f"{len(df)} bars  ({df['ts'].iloc[0].date()} → {df['ts'].iloc[-1].date()})")
    return df


def compute_indicators(df):
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    ema12 = df["close"].ewm(span=MACD_FAST, adjust=False).mean()
    ema26 = df["close"].ewm(span=MACD_SLOW, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=MACD_SIG, adjust=False).mean()
    df["macd_hist"]   = macd - sig
    df["hist_rising"]  = df["macd_hist"] > df["macd_hist"].shift(1)
    df["hist_falling"] = df["macd_hist"] < df["macd_hist"].shift(1)

    df["brk_high"] = df["high"].shift(1).rolling(BRK_LOOKBACK).max()
    df["brk_low"]  = df["low"].shift(1).rolling(BRK_LOOKBACK).min()
    df["long_break"]  = df["close"] > df["brk_high"]
    df["short_break"] = df["close"] < df["brk_low"]

    df["vol_sma"]   = df["volume"].rolling(20).mean()
    df["vol_spike"] = df["volume"] > df["vol_sma"] * 1.5
    df["dow"]  = df["ts"].dt.dayofweek
    df["date"] = df["ts"].dt.date
    return df


def backtest(df, stop_pct, rr_ratio, leverage):
    tp_pct = stop_pct * rr_ratio
    equity = INITIAL_CAP
    trades = []
    last_trade_date = None
    warmup = max(EMA_SLOW, MACD_SLOW + MACD_SIG, BRK_LOOKBACK) + 2

    for i in range(warmup, len(df)):
        row = df.iloc[i]
        long_trend  = row["close"] > row["ema_fast"] and row["ema_fast"] > row["ema_slow"]
        short_trend = row["close"] < row["ema_fast"] and row["ema_fast"] < row["ema_slow"]
        pass_day    = (not SKIP_SAT)     or row["dow"] != 5
        pass_cap    = (not ONCE_PER_DAY) or (last_trade_date is None) or (row["date"] != last_trade_date)

        long_sig  = long_trend  and row["hist_rising"]  and row["long_break"]  and pass_day and pass_cap
        short_sig = short_trend and row["hist_falling"] and row["short_break"] and pass_day and pass_cap

        if not (long_sig or short_sig):
            continue

        direction = "long" if long_sig else "short"
        entry = row["close"]
        sl = entry * (1 - stop_pct/100) if direction == "long" else entry * (1 + stop_pct/100)
        tp = entry * (1 + tp_pct/100)   if direction == "long" else entry * (1 - tp_pct/100)

        outcome = None
        bars_held = 0
        exit_price = None
        for j in range(i + 1, len(df)):
            fut = df.iloc[j]
            bars_held += 1
            if direction == "long":
                if fut["low"]  <= sl: outcome = "loss"; exit_price = sl; break
                if fut["high"] >= tp: outcome = "win";  exit_price = tp; break
            else:
                if fut["high"] >= sl: outcome = "loss"; exit_price = sl; break
                if fut["low"]  <= tp: outcome = "win";  exit_price = tp; break

        if outcome is None:
            continue

        raw_pct = ((exit_price - entry) / entry) * (1 if direction == "long" else -1)
        net_pct = raw_pct * leverage - COMMISSION * 2 * leverage
        pnl     = equity * net_pct
        equity += pnl
        r_real  = net_pct / (stop_pct / 100 * leverage)

        last_trade_date = row["date"]
        trades.append({"outcome": outcome, "net_pct": net_pct, "pnl": pnl,
                        "r_real": r_real, "equity": equity})

    if not trades:
        return None

    t  = pd.DataFrame(trades)
    n  = len(t)
    wins   = t[t["outcome"] == "win"]
    losses = t[t["outcome"] == "loss"]
    wr  = len(wins) / n * 100
    avg_r   = wins["r_real"].mean()  if len(wins)  else 0
    gp  = wins["pnl"].sum()
    gl  = abs(losses["pnl"].sum())
    pf  = gp / gl if gl > 0 else float("inf")
    net = t["pnl"].sum()

    eq  = np.concatenate([[INITIAL_CAP], t["equity"].values])
    rm  = np.maximum.accumulate(eq)
    max_dd = ((eq - rm) / rm * 100).min()

    consec = max_c = 0
    for o in t["outcome"]:
        consec = consec + 1 if o == "loss" else 0
        max_c  = max(max_c, consec)

    be_wr = 100 / (1 + rr_ratio)  # breakeven WR for this RR
    viable = wr >= 35 and pf >= 1.5
    marginal = (not viable) and wr >= be_wr

    return dict(n=n, wr=wr, avg_r=avg_r, pf=pf, net=net,
                max_dd=max_dd, max_c=max_c, be_wr=be_wr,
                viable=viable, marginal=marginal)


SWEEP = [
    # (stop_pct, rr_ratio, leverage, label)
    (1.0, 4.0, 10.0, "1.0% stop / 4R / 10x  [original]"),
    (1.0, 3.0,  8.0, "1.0% stop / 3R /  8x"),
    (1.5, 4.0,  6.7, "1.5% stop / 4R /  6.7x"),
    (1.5, 3.0,  6.7, "1.5% stop / 3R /  6.7x"),
    (2.0, 4.0,  5.0, "2.0% stop / 4R /  5x"),
    (2.0, 3.0,  5.0, "2.0% stop / 3R /  5x"),
    (2.5, 4.0,  4.0, "2.5% stop / 4R /  4x"),
    (2.5, 3.0,  4.0, "2.5% stop / 3R /  4x"),
    (3.0, 3.0,  3.3, "3.0% stop / 3R /  3.3x"),
]


if __name__ == "__main__":
    df = fetch_ohlcv_multi()
    df = compute_indicators(df)

    print()
    print(f"{'Config':<35} {'n':>4} {'WR%':>6} {'BE%':>5} {'AvgR':>5} {'PF':>5} {'MaxDD%':>7} {'MaxC':>5} {'Net€':>7}  Status")
    print("─" * 110)

    for stop_pct, rr, lev, label in SWEEP:
        r = backtest(df, stop_pct, rr, lev)
        if r is None:
            print(f"  {label:<33}  no trades")
            continue
        status = "✅ GREEN" if r["viable"] else ("⚠  MARGINAL" if r["marginal"] else "❌ FAIL")
        print(
            f"  {label:<33} {r['n']:>4} {r['wr']:>6.1f} {r['be_wr']:>5.1f} "
            f"{r['avg_r']:>5.2f} {r['pf']:>5.2f} {r['max_dd']:>7.1f} "
            f"{r['max_c']:>5} {r['net']:>7.0f}  {status}"
        )

    print()
    print("Account risk stays ~10% across all rows (lev × stop% = 10%).")
    print("Green = WR ≥ 35% AND PF ≥ 1.5  |  Marginal = WR ≥ breakeven  |  Fail = bleeding money")
