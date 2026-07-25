"""LENS strategy search v2 — the automated version of /edge's build-your-own.

Sweeps entry-condition combos (up to 3 stacked conditions — more = curve-fit
bait) across every indicator family the engine knows:

  trend (EMA21/50) · candle colour · MACD histogram · RSI bands · BKK session
  windows · Bollinger band breaks · TD Sequential 9-counts · triple-MA stack
  (50/100/200) · volume spikes · ATR volatility regime

through the REAL backtest engine (same fills, fees + 0.03%/side slippage,
cooldown / once-per-day / skip-Saturday gates) at the validated geometry.

Three honesty gates, in order:
  1. split-half   — profitable in BOTH halves of the 30-month window, n≥40
  2. geometry     — SL×TP×leverage×ATR-floor sweep; a real edge is a green
                    neighbourhood, not one lucky cell
  3. deep history — re-run on 7 years of binance 1h data; must stay green
                    in both halves there too

Survivors get a Kelly fraction. Results → strategy_search.json.
Run from repo root (background, ~15 min): python3 -m app.strategy_search

NOT swept (and why): 2y-MA multiplier / 200w-MA exist as engine gates
(mayer_max/min, custom API) but a 30-month window barely covers half a cycle —
they'd degenerate into date filters. Fear&Greed / stock-to-flow / global
liquidity need external data feeds — wire a feed first if a macro gate is
worth testing. Power law on this window ≈ a date filter: skipped on purpose.
"""

import itertools
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .backtest_engine import load_ohlcv, add_indicators, _run_backtest
from .patterns import PATTERN_SLOTS, pattern_masks
from .paths import SEARCH_JSON

CAPITAL    = 1000.0
MONTHS     = 30
BASE_GEO   = {"stop_pct": 0.63, "tp_pct": 1.5, "leverage": 10.0, "slippage_pct": 0.03}
GEO_GRID   = [{"stop_pct": sl, "tp_pct": tp, "leverage": lev,
               "atr_floor_mult": af, "slippage_pct": 0.03}
              for sl in (0.5, 0.63, 1.0)
              for tp in (0.95, 1.5, 2.5, 4.0)
              for lev in (5.0, 10.0)
              for af in (0.0, 1.0)]
MIN_N      = 40
MAX_CONDS  = 3
TOP_STAGE2 = 20

# slot → (options, params-key builder for reproducing in the custom form)
SLOTS = {
    "trend":    ["up", "down"],
    "candle":   ["bull", "bear"],
    "macd":     ["bull", "bear"],
    "rsi":      [("rsi_max", 30), ("rsi_max", 40), ("rsi_min", 60), ("rsi_min", 70)],
    "hours":    [(6, 11), (14, 18), (19, 23)],
    "bb":       ["below_lower", "above_upper"],
    "td":       ["buy9", "sell9"],
    "ma_align": ["bull", "bear"],
    "vol":      [True],
    "atr":      ["low", "high"],
}

# Chart structure + higher-timeframe trend (see app/patterns.py). Merged rather
# than written inline so the vocabulary sits next to the code that computes it.
# This takes the grid search from 2,934 combos to 9,694 (×3.3) at MAX_CONDS=3;
# the breeder samples randomly so it pays nothing for the extra slots.
SLOTS.update(PATTERN_SLOTS)


def _masks(df) -> dict:
    """Vectorized condition arrays — one pass, then every combo is ANDs."""
    hour_bkk = (df.index.hour + 7) % 24
    c = df
    m = {
        ("trend", "up"):          (c["ema21"] > c["ema50"]).to_numpy(),
        ("trend", "down"):        (c["ema21"] < c["ema50"]).to_numpy(),
        ("candle", "bull"):       (c["close"] > c["open"]).to_numpy(),
        ("candle", "bear"):       (c["close"] < c["open"]).to_numpy(),
        ("macd", "bull"):         (c["macd_hist"] > 0).to_numpy(),
        ("macd", "bear"):         (c["macd_hist"] < 0).to_numpy(),
        ("rsi", ("rsi_max", 30)): (c["rsi14"] <= 30).to_numpy(),
        ("rsi", ("rsi_max", 40)): (c["rsi14"] <= 40).to_numpy(),
        ("rsi", ("rsi_min", 60)): (c["rsi14"] >= 60).to_numpy(),
        ("rsi", ("rsi_min", 70)): (c["rsi14"] >= 70).to_numpy(),
        ("bb", "below_lower"):    (c["close"] < c["bb_lower"]).to_numpy(),
        ("bb", "above_upper"):    (c["close"] > c["bb_upper"]).to_numpy(),
        ("td", "buy9"):           (c["td_buy"] >= 9).to_numpy(),
        ("td", "sell9"):          (c["td_sell"] >= 9).to_numpy(),
        ("ma_align", "bull"):     ((c["ema50"] > c["ema100"]) & (c["ema100"] > c["ema200"])).to_numpy(),
        ("ma_align", "bear"):     ((c["ema50"] < c["ema100"]) & (c["ema100"] < c["ema200"])).to_numpy(),
        ("vol", True):            c["vol_spike"].to_numpy(),
        ("atr", "low"):           (c["atr_pctv"] < c["atr_medv"]).to_numpy(),
        ("atr", "high"):          (c["atr_pctv"] >= c["atr_medv"]).to_numpy(),
    }
    for hf, ht in SLOTS["hours"]:
        m[("hours", (hf, ht))] = ((hour_bkk >= hf) & (hour_bkk <= ht))
    m.update(pattern_masks(df))
    return m


def _all_combos():
    """Every (direction, {slot: option}) with 1..MAX_CONDS active conditions."""
    slot_names = list(SLOTS)
    for r in range(1, MAX_CONDS + 1):
        for names in itertools.combinations(slot_names, r):
            for opts in itertools.product(*(SLOTS[n] for n in names)):
                active = dict(zip(names, opts))
                for direction in ("long", "short"):
                    yield direction, active


def _combo_mask(masks, n_bars, active):
    mask = np.ones(n_bars, dtype=bool)
    mask[:60] = False                      # same warm-up as _signal_custom
    for slot, opt in active.items():
        mask &= masks[(slot, opt)]
    return mask


def _sig_fn(mask, direction):
    def sig(df, i, params):
        return direction if mask[i] else None
    return sig


def combo_params(direction, active, tf) -> dict:
    """The custom-form params dict that reproduces this combo (also feeds the
    Pine exporter + a STRATEGIES registry entry)."""
    p = {"direction": direction, "timeframe": tf}
    for slot, opt in active.items():
        if slot == "rsi":
            p[opt[0]] = opt[1]
        elif slot == "hours":
            p["hour_from"], p["hour_to"] = opt
        elif slot == "vol":
            p["vol_spike"] = True
        elif slot == "atr":
            p["atr_regime"] = opt
        else:
            p[slot] = opt
    return p


def _describe(direction, active, tf):
    bits = [direction.upper(), tf]
    lab = {"trend": lambda o: f"trend {o}", "candle": lambda o: f"{o} bar",
           "macd": lambda o: f"MACD {o}",
           "rsi": lambda o: ("RSI≤" if o[0] == "rsi_max" else "RSI≥") + str(o[1]),
           "hours": lambda o: f"BKK {o[0]:02d}–{o[1]:02d}h",
           "bb": lambda o: "BB " + ("<lower" if o == "below_lower" else ">upper"),
           "td": lambda o: f"TD {o}", "ma_align": lambda o: f"MA-stack {o}",
           "vol": lambda o: "vol spike", "atr": lambda o: f"{o}-vol",
           "pattern": lambda o: o.replace("_", " "),
           "structure": lambda o: f"structure {o}",
           "breakout": lambda o: f"breakout {o}",
           "htf4h": lambda o: f"4h trend {o}",
           "htf1d": lambda o: f"1d trend {o}"}
    # A slot with no label must not crash the run. This cost a 14-minute breeder
    # run on 2026-07-25: the 1h phase completed, then _describe raised KeyError
    # on the new 'htf4h' slot while writing results, and every generation was
    # lost. Formatting is not worth a lost search.
    bits += [lab.get(s, lambda o, s=s: f"{s} {o}")(o) for s, o in active.items()]
    return " · ".join(bits)


def _eval(res, mid_iso):
    tr = res["trades"]
    n = len(tr)
    if n == 0:
        return None
    wins = [t["pnl_pct"] for t in tr if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in tr if t["pnl_pct"] <= 0]
    gw, gl = sum(wins), -sum(losses)
    h1 = round(sum(t["pnl_pct"] for t in tr if t["entry_ts"] < mid_iso), 1)
    h2 = round(sum(t["pnl_pct"] for t in tr if t["entry_ts"] >= mid_iso), 1)
    peak, maxdd = CAPITAL, 0.0
    for t in tr:
        peak = max(peak, t["equity"])
        maxdd = max(maxdd, (peak - t["equity"]) / peak)
    wr = len(wins) / n
    avg_w = gw / len(wins) if wins else 0.0
    avg_l = gl / len(losses) if losses else 0.0
    rr = avg_w / avg_l if avg_l else 0.0
    kelly = wr - (1 - wr) / rr if rr else None   # fraction of stake, per Kelly
    return {
        "n": n, "wr": round(wr * 100, 1),
        "pf": round(gw / gl, 2) if gl else 99.0,
        "net_pct": round(res["final_equity"] / CAPITAL * 100 - 100, 1),
        "max_dd": round(maxdd * 100, 1),
        "half1": h1, "half2": h2,
        "kelly": round(kelly, 3) if kelly is not None else None,
        "robust": n >= MIN_N and h1 > 0 and h2 > 0,
    }


def _load_deep(tf: str):
    """7-year binance 1h window; resampled to 4h when needed."""
    df = load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=84, exchange_id="binance")
    if tf == "4h":
        df = pd.DataFrame({
            "open":   df["open"].resample("4h").first(),
            "high":   df["high"].resample("4h").max(),
            "low":    df["low"].resample("4h").min(),
            "close":  df["close"].resample("4h").last(),
            "volume": df["volume"].resample("4h").sum(),
        }).dropna()
    return add_indicators(df)


def run_search():
    t0 = time.time()
    all_rows, survivors = [], []
    data, deep = {}, {}

    for tf in ("1h", "4h"):
        data[tf] = add_indicators(load_ohlcv(months=MONTHS, timeframe=tf))

    combos = list(_all_combos())
    print(f"{len(combos)} combos × 2 timeframes, engine geometry "
          f"{BASE_GEO['stop_pct']}%/{BASE_GEO['tp_pct']}% + 0.03% slippage/side", flush=True)

    for tf in ("1h", "4h"):
        df = data[tf]
        masks = _masks(df)
        nb = len(df)
        mid_iso = df.index[nb // 2].isoformat()
        print(f"[{tf}] {nb} bars {df.index[0].date()} → {df.index[-1].date()}", flush=True)

        for k, (direction, active) in enumerate(combos):
            mask = _combo_mask(masks, nb, active)
            if mask.sum() < MIN_N:
                continue
            res = _run_backtest(df, _sig_fn(mask, direction), dict(BASE_GEO), CAPITAL)
            ev = _eval(res, mid_iso)
            if ev is None:
                continue
            row = {"tf": tf, "direction": direction,
                   "params": combo_params(direction, active, tf),
                   "desc": _describe(direction, active, tf), **ev}
            all_rows.append(row)
            if ev["robust"] and ev["net_pct"] > 0:
                survivors.append((active, row))
            if k % 1000 == 0:
                print(f"[{tf}] {k}/{len(combos)} · {time.time()-t0:.0f}s · "
                      f"survivors: {len(survivors)}", flush=True)

        # Stage 2 — geometry sweep on this timeframe's best survivors
        best = sorted([s for s in survivors if s[1]["tf"] == tf],
                      key=lambda s: s[1]["net_pct"], reverse=True)[:TOP_STAGE2]
        print(f"[{tf}] stage 2: geometry × {len(best)} survivors", flush=True)
        for active, row in best:
            mask = _combo_mask(masks, nb, active)
            row["geometry"] = []
            for g in GEO_GRID:
                ev = _eval(_run_backtest(df, _sig_fn(mask, row["direction"]),
                                         dict(g), CAPITAL), mid_iso)
                if ev:
                    row["geometry"].append({**{k: g[k] for k in
                                               ("stop_pct", "tp_pct", "leverage", "atr_floor_mult")},
                                            **ev})
            row["green_cells"] = sum(1 for g in row["geometry"]
                                     if g["robust"] and g["net_pct"] > 0)

        # Stage 3 — deep-history confirmation (7y binance)
        if any(s[1]["tf"] == tf for s in survivors):
            if tf not in deep:
                deep[tf] = _load_deep(tf)
            ddf = deep[tf]
            dmasks = _masks(ddf)
            dmid = ddf.index[len(ddf) // 2].isoformat()
            for active, row in [s for s in survivors if s[1]["tf"] == tf]:
                mask = _combo_mask(dmasks, len(ddf), active)
                ev = _eval(_run_backtest(ddf, _sig_fn(mask, row["direction"]),
                                         dict(BASE_GEO), CAPITAL), dmid)
                row["deep"] = ev
                row["deep_confirmed"] = bool(ev and ev["robust"] and ev["net_pct"] > 0)

    surv_rows = sorted([r for _a, r in survivors],
                       key=lambda r: (r.get("deep_confirmed", False),
                                      r.get("green_cells", 0), r["net_pct"]),
                       reverse=True)
    out = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "version": 2, "months": MONTHS, "capital": CAPITAL,
        "base_geometry": BASE_GEO, "min_n": MIN_N, "max_conditions": MAX_CONDS,
        "combos_per_tf": len(combos), "evaluated": len(all_rows),
        "survivors": surv_rows,
        "all": sorted(all_rows, key=lambda r: r["net_pct"], reverse=True)[:300],
    }
    with open(SEARCH_JSON, "w") as f:
        # numpy scalars (from the ATR-floor path) aren't JSON-serializable
        json.dump(out, f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))

    print(f"\n=== DONE in {time.time()-t0:.0f}s — {len(all_rows)} evaluated, "
          f"{len(surv_rows)} split-half survivors, "
          f"{sum(1 for r in surv_rows if r.get('deep_confirmed'))} deep-confirmed ===", flush=True)
    print(f"{'net%':>7} {'PF':>5} {'WR':>5} {'n':>5} {'DD':>5} {'h1':>7} {'h2':>7} "
          f"{'geo✓':>4} {'deep':>5} {'kelly':>6}  desc")
    for s in surv_rows[:25]:
        dp = s.get("deep") or {}
        print(f"{s['net_pct']:>7} {s['pf']:>5} {s['wr']:>5} {s['n']:>5} "
              f"{s['max_dd']:>5} {s['half1']:>7} {s['half2']:>7} "
              f"{s.get('green_cells','-'):>4} "
              f"{(str(dp.get('net_pct'))+'%') if dp else '—':>5} "
              f"{s.get('kelly') if s.get('kelly') is not None else '—':>6}  {s['desc']}")
    if not surv_rows:
        print("No combo survived the split-half filter — the honest result: "
              "nothing in this space is robustly profitable at this geometry.")


if __name__ == "__main__":
    run_search()
