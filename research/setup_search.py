"""Hunt mechanical setups — BOTH directions — that clear the validated geometry.

The frequency gap is the only open item: the edge on non-VETO shorts is
sufficient, but it fires 1.5×/week and the target needs ~7. That edge lives in
his head, so it cannot be scanned for. This searches for a MECHANICAL rule that
produces entries good enough to matter, at the geometry /short validated.

Both directions, deliberately. His historical longs were worse than random, but
that is a fact about the longs he took, not a proof that no long rule works —
and a trader who only ever shorts is half a trader. Long and short are searched
identically and the gates decide.

Architecture: the barrier outcome of entering at bar i is a property of the bar,
not of the rule that chose it. So every bar is resolved ONCE per direction, and
each candidate rule becomes a boolean mask over that precomputed array. 63k
walks up front buys an exhaustive rule search for nothing.

Gates, applied per cell:
  n >= MIN_N                     enough trades to say anything
  beats direction-matched random the same bar universe, same direction
  net > 0 after friction
  positive in BOTH halves        chronological, the S1-S5 test
  permutation p < 0.05           finalists only: is the RULE selecting, or did
                                 we just try enough masks? This is the
                                 multiple-comparisons guard, and without it a
                                 search over hundreds of cells WILL produce
                                 winners from noise.

    python3 research/setup_search.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from itertools import product

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.geometry import FRICTION_PCT      # noqa: E402
from app.paths import RESULTS              # noqa: E402

MIN_N = 40
MAX_HOURS = 24 * 60
N_PERM = 2000
SEED = 42
BKK = 7   # UTC+7


def resolve_all(df, sl_pct, tp_pct, direction):
    """Outcome of entering at each bar: True win / False loss / None unresolved."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(close)
    out = [None] * n
    long_ = direction == "long"
    for i in range(n - 1):
        e = close[i]
        if long_:
            tp, sl = e * (1 + tp_pct / 100), e * (1 - sl_pct / 100)
        else:
            tp, sl = e * (1 - tp_pct / 100), e * (1 + sl_pct / 100)
        end = min(i + 1 + MAX_HOURS, n)
        for j in range(i + 1, end):
            if (low[j] <= sl) if long_ else (high[j] >= sl):
                out[i] = False; break
            if (high[j] >= tp) if long_ else (low[j] <= tp):
                out[i] = True; break
    return out


def net_of(wins, total, sl, tp, f=FRICTION_PCT):
    if not total:
        return None, None
    w = wins / total
    return w, w * (tp - f) - (1 - w) * (sl + f)


def main() -> None:
    import numpy as np  # noqa: F401
    from app.backtest_engine import add_indicators, load_ohlcv

    cfg = json.load(open(RESULTS / "short_edge.json"))["best"]
    SL, TP = cfg["stop_pct"], cfg["target_pct"]
    print(f"geometry from /short: stop {SL:.2f}% / target {TP:.2f}% (R:R {cfg['rr']:.0f})")

    df = add_indicators(load_ohlcv(symbol="BTC/USDT", timeframe="1h",
                                   months=90, exchange_id="binance"))
    df = df.dropna(subset=["rsi14", "daily_ema50", "bb_upper", "macd_hist"])
    print(f"{len(df):,} bars {df.index[0]:%Y-%m-%d} → {df.index[-1]:%Y-%m-%d}\n")

    # ── conditions, evaluated once ──────────────────────────────────────────
    c, rsi = df["close"], df["rsi14"]
    hour = np.asarray((df.index.hour + BKK) % 24)
    C = {
        "rsi<30":      (rsi < 30).to_numpy(),
        "rsi30-45":    ((rsi >= 30) & (rsi < 45)).to_numpy(),
        "rsi45-55":    ((rsi >= 45) & (rsi <= 55)).to_numpy(),
        "rsi55-70":    ((rsi > 55) & (rsi <= 70)).to_numpy(),
        "rsi>70":      (rsi > 70).to_numpy(),
        "above_d50":   (c > df["daily_ema50"]).to_numpy(),
        "below_d50":   (c < df["daily_ema50"]).to_numpy(),
        "macd_bull":   (df["macd_hist"] > 0).to_numpy(),
        "macd_bear":   (df["macd_hist"] < 0).to_numpy(),
        "bb_over":     (c > df["bb_upper"]).to_numpy(),
        "bb_under":    (c < df["bb_lower"]).to_numpy(),
        "vol_spike":   df["vol_spike"].to_numpy(),
        "bkk_asia":    (hour >= 6) & (hour < 14),
        "bkk_london":  (hour >= 14) & (hour < 20),
        "bkk_ny":      (hour >= 20) | (hour < 3),
    }
    RSI = ["rsi<30", "rsi30-45", "rsi45-55", "rsi55-70", "rsi>70", None]
    TREND = ["above_d50", "below_d50", None]
    MOM = ["macd_bull", "macd_bear", None]
    EXTRA = ["bb_over", "bb_under", "vol_spike", None]
    SESSION = ["bkk_asia", "bkk_london", "bkk_ny", None]

    random.seed(SEED)
    half = len(df) // 2
    results = []

    for direction in ("long", "short"):
        print(f"resolving every bar {direction}…", flush=True)
        outc = resolve_all(df, SL, TP, direction)
        idx = [i for i, o in enumerate(outc) if o is not None]
        wins = [outc[i] for i in idx]
        base_w = sum(wins) / len(wins)
        print(f"  baseline {direction}: {base_w:.2%} over {len(idx):,} resolved bars")

        for combo in product(RSI, TREND, MOM, EXTRA, SESSION):
            parts = [p for p in combo if p]
            if not parts:
                continue
            mask = C[parts[0]].copy()
            for p in parts[1:]:
                mask &= C[p]
            sel = [i for i in idx if mask[i]]
            if len(sel) < MIN_N:
                continue
            sw = sum(outc[i] for i in sel)
            w, net = net_of(sw, len(sel), SL, TP)
            if net is None or net <= 0 or w <= base_w:
                continue
            a = [i for i in sel if i < half]
            b = [i for i in sel if i >= half]
            if len(a) < 10 or len(b) < 10:
                continue
            _, na = net_of(sum(outc[i] for i in a), len(a), SL, TP)
            _, nb = net_of(sum(outc[i] for i in b), len(b), SL, TP)
            if na is None or nb is None or na <= 0 or nb <= 0:
                continue
            results.append({
                "direction": direction, "rule": " + ".join(parts),
                "n": len(sel), "win_rate": w, "baseline": base_w,
                "edge_pp": (w - base_w) * 100, "net_pct": net,
                "h1_net": na, "h2_net": nb,
                "per_week": len(sel) / (len(df) / 24 / 7),
            })

        # ── permutation on finalists: guard against the search itself ───────
        fin = sorted([r for r in results if r["direction"] == direction],
                     key=lambda r: -r["net_pct"])[:10]
        for r in fin:
            k = r["n"]
            pool = list(wins)
            ge = 0
            for _ in range(N_PERM):
                if sum(random.sample(pool, k)) / k >= r["win_rate"]:
                    ge += 1
            r["perm_p"] = ge / N_PERM

    survivors = [r for r in results if r.get("perm_p") is not None
                 and r["perm_p"] < 0.05]
    print(f"\n{len(results)} cells passed the basic gates · "
          f"{len(survivors)} also clear permutation p<0.05\n")

    if results:
        print(f"  {'dir':>5} {'rule':>46} {'n':>5} {'WR':>7} {'base':>7} "
              f"{'edge':>8} {'net':>9} {'/wk':>6} {'perm p':>8}")
        for r in sorted(results, key=lambda r: -r["net_pct"])[:20]:
            p = r.get("perm_p")
            star = " ✓" if p is not None and p < 0.05 else ""
            print(f"  {r['direction']:>5} {r['rule']:>46} {r['n']:>5} "
                  f"{r['win_rate']:>6.1%} {r['baseline']:>6.1%} "
                  f"{r['edge_pp']:>+7.1f}pp {r['net_pct']:>+8.3f}% "
                  f"{r['per_week']:>5.2f} "
                  f"{(f'{p:.3f}' if p is not None else '—'):>8}{star}")

    with open(RESULTS / "setup_search.json", "w") as fh:
        json.dump({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                   "stop_pct": SL, "target_pct": TP, "bars": len(df),
                   "min_n": MIN_N, "perm_n": N_PERM,
                   "n_passed_basic": len(results), "n_survivors": len(survivors),
                   "cells": sorted(results, key=lambda r: -r["net_pct"])[:60]},
                  fh, indent=2)
    print(f"\n→ wrote {RESULTS / 'setup_search.json'}")
    if not survivors:
        print("  No rule survives the permutation guard. With this many cells "
              "tried,\n  that is the expected result when no real mechanical "
              "edge is present.")


if __name__ == "__main__":
    main()
