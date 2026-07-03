"""LENS strategy search — the automated version of /edge's build-your-own.

Stage 1: every entry-condition combo (timeframe × direction × trend × candle ×
MACD × RSI band × BKK-hour window) runs through the REAL backtest engine
(_run_backtest: same fills, fees, cooldown / once-per-day / skip-Saturday
gates) at the validated geometry (SL 0.63% / TP 1.5% / 10x).

Curve-fit filter = split-half: a combo only survives if it made money in BOTH
halves of the window AND fired ≥40 times total. One lucky regime doesn't rank.

Stage 2: SL×TP geometry sweep over the stage-1 survivors — the edge has to be
a green neighbourhood, not one lucky cell.

Writes strategy_search.json (all results + ranked survivors); prints progress
and a final table. Run from repo root, ideally in the background:

    python3 -m app.strategy_search

ponytail: 1h + 4h only (what ohlcv_cache holds); once-per-day gate already
approximates a daily cadence. Add a resampled 1d pass if these two ever
produce a survivor worth confirming on dailies.
"""

import itertools
import json
import time
from datetime import datetime, timezone

import numpy as np

from .backtest_engine import load_ohlcv, add_indicators, _run_backtest

CAPITAL   = 1000.0
MONTHS    = 30
BASE_GEO  = {"stop_pct": 0.63, "tp_pct": 1.5, "leverage": 10.0}
GEO_GRID  = [(sl, tp) for sl in (0.5, 0.63, 1.0) for tp in (0.95, 1.5, 2.5, 4.0)]
MIN_N     = 40
TOP_STAGE2 = 20

TRENDS  = [None, "up", "down"]
CANDLES = [None, "bull", "bear"]
MACDS   = [None, "bull", "bear"]
RSIS    = [None, ("rsi_max", 30), ("rsi_max", 40), ("rsi_min", 60), ("rsi_min", 70)]
HOURS   = [None, (6, 11), (14, 18), (19, 23)]   # BKK: Asia morning / London / NY


def _masks(df) -> dict:
    """Vectorized condition arrays — one pass, then every combo is ANDs."""
    hour_bkk = (df.index.hour + 7) % 24
    m = {
        ("trend", "up"):    (df["ema21"] > df["ema50"]).to_numpy(),
        ("trend", "down"):  (df["ema21"] < df["ema50"]).to_numpy(),
        ("candle", "bull"): (df["close"] > df["open"]).to_numpy(),
        ("candle", "bear"): (df["close"] < df["open"]).to_numpy(),
        ("macd", "bull"):   (df["macd_hist"] > 0).to_numpy(),
        ("macd", "bear"):   (df["macd_hist"] < 0).to_numpy(),
        ("rsi_max", 30):    (df["rsi14"] <= 30).to_numpy(),
        ("rsi_max", 40):    (df["rsi14"] <= 40).to_numpy(),
        ("rsi_min", 60):    (df["rsi14"] >= 60).to_numpy(),
        ("rsi_min", 70):    (df["rsi14"] >= 70).to_numpy(),
    }
    for hf, ht in [h for h in HOURS if h]:
        m[("hours", (hf, ht))] = ((hour_bkk >= hf) & (hour_bkk <= ht))
    return m


def _combo_mask(masks, n_bars, trend, candle, macd, rsi, hours):
    mask = np.ones(n_bars, dtype=bool)
    mask[:60] = False                      # same warm-up as _signal_custom
    if trend:  mask &= masks[("trend", trend)]
    if candle: mask &= masks[("candle", candle)]
    if macd:   mask &= masks[("macd", macd)]
    if rsi:    mask &= masks[rsi]
    if hours:  mask &= masks[("hours", hours)]
    return mask


def _sig_fn(mask, direction):
    def sig(df, i, params):
        return direction if mask[i] else None
    return sig


def _describe(tf, direction, trend, candle, macd, rsi, hours, sl, tp):
    bits = [direction.upper(), tf]
    if trend:  bits.append(f"trend {trend}")
    if candle: bits.append(f"{candle} bar")
    if macd:   bits.append(f"MACD {macd}")
    if rsi:    bits.append(("RSI≤" if rsi[0] == "rsi_max" else "RSI≥") + str(rsi[1]))
    if hours:  bits.append(f"BKK {hours[0]:02d}–{hours[1]:02d}h")
    bits.append(f"SL {sl:g}% · TP {tp:g}%")
    return " · ".join(bits)


def _eval(res, mid_iso):
    """Cheap screening metrics from the trade list (full metrics only matter
    for survivors — run those through run_custom on /edge to inspect)."""
    tr = res["trades"]
    n = len(tr)
    if n == 0:
        return None
    wins = sum(1 for t in tr if t["result"] == "win")
    gw = sum(t["pnl_pct"] for t in tr if t["pnl_pct"] > 0)
    gl = -sum(t["pnl_pct"] for t in tr if t["pnl_pct"] <= 0)
    h1 = round(sum(t["pnl_pct"] for t in tr if t["entry_ts"] < mid_iso), 1)
    h2 = round(sum(t["pnl_pct"] for t in tr if t["entry_ts"] >= mid_iso), 1)
    peak, maxdd = CAPITAL, 0.0
    for t in tr:
        peak = max(peak, t["equity"])
        maxdd = max(maxdd, (peak - t["equity"]) / peak)
    return {
        "n": n, "wr": round(wins / n * 100, 1),
        "pf": round(gw / gl, 2) if gl else 99.0,
        "net_pct": round(res["final_equity"] / CAPITAL * 100 - 100, 1),
        "max_dd": round(maxdd * 100, 1),
        "half1": h1, "half2": h2,
        "robust": n >= MIN_N and h1 > 0 and h2 > 0,
    }


def run_search():
    t0 = time.time()
    all_rows, survivors = [], []

    for tf in ("1h", "4h"):
        df = add_indicators(load_ohlcv(months=MONTHS, timeframe=tf))
        masks = _masks(df)
        nb = len(df)
        mid_iso = df.index[nb // 2].isoformat()
        combos = [c for c in itertools.product(
                      ("long", "short"), TRENDS, CANDLES, MACDS, RSIS, HOURS)
                  if any(c[1:])]           # at least one entry condition
        print(f"[{tf}] {nb} bars {df.index[0].date()} → {df.index[-1].date()}, "
              f"{len(combos)} combos", flush=True)

        for k, (direction, trend, candle, macd, rsi, hours) in enumerate(combos):
            mask = _combo_mask(masks, nb, trend, candle, macd, rsi, hours)
            if mask.sum() < MIN_N:          # can't possibly reach MIN_N trades
                continue
            res = _run_backtest(df, _sig_fn(mask, direction), dict(BASE_GEO), CAPITAL)
            ev = _eval(res, mid_iso)
            if ev is None:
                continue
            row = {"tf": tf, "direction": direction, "trend": trend,
                   "candle": candle, "macd": macd,
                   "rsi": list(rsi) if rsi else None,
                   "hours": list(hours) if hours else None,
                   "sl": BASE_GEO["stop_pct"], "tp": BASE_GEO["tp_pct"],
                   "desc": _describe(tf, direction, trend, candle, macd, rsi,
                                     hours, BASE_GEO["stop_pct"], BASE_GEO["tp_pct"]),
                   **ev}
            all_rows.append(row)
            if ev["robust"] and ev["net_pct"] > 0:
                survivors.append(row)
            if k % 200 == 0:
                print(f"[{tf}] {k}/{len(combos)} · {time.time()-t0:.0f}s · "
                      f"survivors so far: {len(survivors)}", flush=True)

        # Stage 2 — geometry sweep on this timeframe's best survivors
        best = sorted([s for s in survivors if s["tf"] == tf],
                      key=lambda r: r["net_pct"], reverse=True)[:TOP_STAGE2]
        print(f"[{tf}] stage 2: sweeping geometry on {len(best)} survivors", flush=True)
        for s in best:
            rsi = tuple(s["rsi"]) if s["rsi"] else None
            hours = tuple(s["hours"]) if s["hours"] else None
            mask = _combo_mask(masks, nb, s["trend"], s["candle"], s["macd"], rsi, hours)
            s["geometry"] = []
            for sl, tp in GEO_GRID:
                p = {"stop_pct": sl, "tp_pct": tp, "leverage": 10.0}
                ev = _eval(_run_backtest(df, _sig_fn(mask, s["direction"]), p, CAPITAL),
                           mid_iso)
                if ev:
                    s["geometry"].append({"sl": sl, "tp": tp, **ev})
            s["green_cells"] = sum(1 for g in s["geometry"] if g["robust"] and g["net_pct"] > 0)

    survivors.sort(key=lambda r: (r.get("green_cells", 0), r["net_pct"]), reverse=True)
    out = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "months": MONTHS, "capital": CAPITAL, "base_geometry": BASE_GEO,
        "combos_tested": len(all_rows), "min_n": MIN_N,
        "survivors": survivors,
        "all": sorted(all_rows, key=lambda r: r["net_pct"], reverse=True)[:200],
    }
    with open("strategy_search.json", "w") as f:
        json.dump(out, f, indent=1)

    print(f"\n=== DONE in {time.time()-t0:.0f}s — {len(all_rows)} combos evaluated, "
          f"{len(survivors)} robust survivors ===", flush=True)
    print(f"{'net%':>7} {'PF':>5} {'WR':>5} {'n':>5} {'DD':>5} {'h1':>7} {'h2':>7} {'geo✓':>4}  desc")
    for s in survivors[:25]:
        print(f"{s['net_pct']:>7} {s['pf']:>5} {s['wr']:>5} {s['n']:>5} "
              f"{s['max_dd']:>5} {s['half1']:>7} {s['half2']:>7} "
              f"{s.get('green_cells','-'):>4}  {s['desc']}")
    if not survivors:
        print("No combo survived the split-half filter — the honest result: "
              "nothing in this space is robustly profitable at these geometries.")


if __name__ == "__main__":
    run_search()
