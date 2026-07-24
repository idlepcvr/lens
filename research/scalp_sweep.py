"""One-off research: sweep scalp entry filters × SL/TP to find what beats the
realized 41.8% WR baseline. Reuses the live backtest engine (same fills, same
fee model). Not wired into the app — pure analysis.
Run from the repo root:  python3 research/scalp_sweep.py"""
import sqlite3

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd; precedes `app`
import pandas as pd

from app.paths import DB_PATH
from app.backtest_engine import add_indicators, _run_backtest, _compute_metrics

MONTHS = 30


def load_cache(cache_symbol="binance:BTC/USDT", timeframe="1h"):
    c = sqlite3.connect(DB_PATH)
    rows = c.execute(
        "SELECT ts,open,high,low,close,volume FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe=? ORDER BY ts ASC",
        (cache_symbol, timeframe),
    ).fetchall()
    c.close()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    unit = "ms" if df["ts"].iloc[0] > 1e12 else "s"
    df.index = pd.to_datetime(df["ts"], unit=unit, utc=True)
    return df.drop(columns="ts")


df = add_indicators(load_cache())
# last MONTHS of data
cutoff = df.index.max() - pd.Timedelta(days=MONTHS * 30)
df = df[df.index >= cutoff]

NY_HOURS   = set(range(13, 21))      # 13:00–20:59 UTC = US session (documented drag)
ASIAN_HOURS = set(range(0, 8))       # 00:00–07:59 UTC


def make_signal(variant):
    def sig(d, i, p):
        ts = d.index[i]
        h  = ts.hour
        o_prev, c_prev = d["open"].iloc[i-1], d["close"].iloc[i-1]
        up = c_prev > o_prev
        dn = c_prev < o_prev
        # session gates
        if variant.get("skip_ny") and h in NY_HOURS:   return None
        if variant.get("asian_only") and h not in ASIAN_HOURS: return None
        # higher-TF trend (4H ema21 vs ema50)
        trend_up = d["h4_ema21"].iloc[i] > d["h4_ema50"].iloc[i]
        kind = variant["kind"]
        if kind == "mom":            # follow prior candle
            base = "long" if up else ("short" if dn else None)
        elif kind == "meanrev":      # fade prior candle
            base = "short" if up else ("long" if dn else None)
        elif kind == "rsi":          # fade RSI extremes
            r = d["rsi14"].iloc[i]
            base = "long" if r < 35 else ("short" if r > 65 else None)
        else:
            base = None
        if base is None: return None
        # trend alignment filter
        if variant.get("trend_align"):
            if base == "long" and not trend_up:  return None
            if base == "short" and trend_up:     return None
        if variant.get("trend_counter"):  # only counter-trend (mean reversion bias)
            if base == "long" and trend_up:      return None
            if base == "short" and not trend_up: return None
        if variant.get("long_only") and base != "long":  return None
        return base
    return sig


def run(name, variant, stop, tp, cooldown=6):
    params = {"stop_pct": stop, "tp_pct": tp, "leverage": 1.0,
              "commission": 0.0002, "skip_sat": False,
              "cooldown_bars": cooldown, "once_per_day": False}
    res = _run_backtest(df, make_signal(variant), params, 637.0)
    m = _compute_metrics(res, 637.0, MONTHS)
    if m.get("n", 0) < 20:
        return None
    return (name, f"{stop}/{tp}", m["n"], m["win_rate"], m["avg_r"],
            m["profit_factor"], m["trades_per_week"], m["net_pct"], m["max_drawdown_pct"])


EXPERIMENTS = [
    ("baseline-mom",        {"kind": "mom"}),
    ("mom+trend",           {"kind": "mom", "trend_align": True}),
    ("mom+skipNY",          {"kind": "mom", "skip_ny": True}),
    ("mom+trend+skipNY",    {"kind": "mom", "trend_align": True, "skip_ny": True}),
    ("mom+asian",           {"kind": "mom", "asian_only": True}),
    ("meanrev",             {"kind": "meanrev"}),
    ("meanrev+counter",     {"kind": "meanrev", "trend_counter": True}),
    ("rsi-fade",            {"kind": "rsi"}),
    ("rsi-fade+counter",    {"kind": "rsi", "trend_counter": True}),
    ("rsi-fade+asian",      {"kind": "rsi", "asian_only": True}),
]

# SL/TP combos: (stop, tp) -> RR
SLTP = [(0.63, 0.95), (0.6, 1.2), (0.5, 1.0), (0.4, 1.2), (0.5, 1.5), (0.8, 0.8)]

rows = []
print(f"{'strategy':22}{'SL/TP':10}{'n':>6}{'WR%':>7}{'avgR':>7}{'PF':>6}{'t/wk':>7}{'net%':>9}{'mdd%':>7}", flush=True)
print("-"*82, flush=True)
for name, variant in EXPERIMENTS:
    for stop, tp in SLTP:
        r = run(name, variant, stop, tp)
        if not r:
            continue
        rows.append(r)
        nm, sltp, n, wr, ar, pf, tpw, net, mdd = r
        flag = "  << PROFITABLE" if pf > 1.0 else ""
        print(f"{nm:22}{sltp:10}{n:>6}{wr:>7.1f}{ar:>7.2f}{pf:>6.2f}{tpw:>7.1f}{net:>9.1f}{mdd:>7.1f}{flag}", flush=True)

print("\n=== TOP 8 by profit factor ===", flush=True)
for r in sorted(rows, key=lambda x: x[5], reverse=True)[:8]:
    nm, sltp, n, wr, ar, pf, tpw, net, mdd = r
    print(f"{nm:22}{sltp:10} PF={pf:.2f} WR={wr:.1f}% avgR={ar:.2f} n={n} t/wk={tpw:.1f} net={net:.0f}%", flush=True)
