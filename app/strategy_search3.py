"""LENS strategy search v3 — dynamic ATR geometry, risk-normalized.

v2's verdict ("no edge") only covered the tight-scalp regime: stage 1 filtered
every combo at fixed 0.63%/1.5%/10x, so entries that only work with wide,
volatility-scaled stops died before the geometry sweep ever saw them. v3 fixes
the structural bias his critique named:

  · geometry is PART of the stage-1 search space, not a post-filter sweep:
    stop = k × ATR(entry bar) (fully dynamic, replaces fixed %), TP = R × stop
  · risk-normalized sizing: every trade risks the same % of equity
    (per-trade leverage = risk/stop, capped) — wide and tight geometries
    become comparable in R terms, and the fee drag of tight stops is priced in
  · timeframes 1h / 4h / 1d (low-frequency regimes allowed)
  · stage 2 = the full (k × R) matrix on survivors — win rate, expectancy in
    R, n, drawdown, halves per cell, so the sweet spot is visible, not asserted

Same three honesty gates as v2: split-half (n≥40, both halves green) →
geometry-neighbourhood → 7-year deep confirmation AT THE COMBO'S OWN REGIME.

Entry conditions reused from v2 (same SLOTS); the new information here is
geometry. Order-flow / macro feeds still need a data source — not in scope.

Results → strategy_search.json (version 3).
Run from repo root (background): python3 -m app.strategy_search3
"""

import itertools
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .backtest_engine import load_ohlcv, add_indicators, _run_backtest
from .strategy_search import (CAPITAL, MONTHS, MIN_N, MAX_CONDS, SLOTS,
                              _masks, _combo_mask, _sig_fn, combo_params,
                              _describe, _eval)

RISK       = {"risk_pct": 2.0, "leverage": 5.0, "slippage_pct": 0.03,
              "stop_pct": 1.0, "tp_pct": 2.0}   # fixed-% fields unused when atr_stop_mult set
COARSE_K   = (0.75, 1.5, 2.5)
COARSE_R   = (1.5, 3.0, 5.0)
FINE_K     = (0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)
FINE_R     = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
TOP_STAGE2 = 15
TIMEFRAMES = ("1h", "4h", "1d")


def _geo(k, r):
    return {**RISK, "atr_stop_mult": k, "rr": r}


def _combos(tf):
    """v2's combo generator, minus the hours slot on 1d (daily bars share one
    timestamp hour — a session filter degenerates to all-or-nothing)."""
    slots = {n: o for n, o in SLOTS.items() if not (tf == "1d" and n == "hours")}
    names_all = list(slots)
    for r in range(1, MAX_CONDS + 1):
        for names in itertools.combinations(names_all, r):
            for opts in itertools.product(*(slots[n] for n in names)):
                active = dict(zip(names, opts))
                for direction in ("long", "short"):
                    yield direction, active


def _load(tf, months, exchange=None):
    if exchange == "binance":   # deep history: 7y of 1h spot, resampled up
        df = load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=months,
                        exchange_id="binance")
        if tf != "1h":
            df = pd.DataFrame({
                "open":   df["open"].resample(tf).first(),
                "high":   df["high"].resample(tf).max(),
                "low":    df["low"].resample(tf).min(),
                "close":  df["close"].resample(tf).last(),
                "volume": df["volume"].resample(tf).sum(),
            }).dropna()
        return add_indicators(df)
    return add_indicators(load_ohlcv(months=months, timeframe=tf))


def _cell(ev, k, r):
    # expectancy in R: mean pnl%/trade over the risk% per trade
    exp_r = round((ev["half1"] + ev["half2"]) / ev["n"] / RISK["risk_pct"], 2)
    return {"k": k, "rr": r, "exp_r": exp_r, **ev}


def run_search():
    t0 = time.time()
    all_rows, survivors = [], []

    coarse = [(k, r) for k in COARSE_K for r in COARSE_R]
    print(f"v3: geometry in stage 1 — {len(coarse)} (k×ATR, R) regimes × "
          f"combos × {TIMEFRAMES}, risk {RISK['risk_pct']}%/trade, "
          f"lev cap {RISK['leverage']}x, 0.03%/side slippage", flush=True)

    for tf in TIMEFRAMES:
        df = _load(tf, MONTHS)
        masks = _masks(df)
        nb = len(df)
        mid_iso = df.index[nb // 2].isoformat()
        combos = list(_combos(tf))
        print(f"[{tf}] {nb} bars {df.index[0].date()} → {df.index[-1].date()} "
              f"· {len(combos)} combos × {len(coarse)} regimes", flush=True)

        for ci, (direction, active) in enumerate(combos):
            mask = _combo_mask(masks, nb, active)
            if mask.sum() < MIN_N:
                continue
            sig = _sig_fn(mask, direction)
            for k, r in coarse:
                ev = _eval(_run_backtest(df, sig, _geo(k, r), CAPITAL), mid_iso)
                if ev is None:
                    continue
                row = {"tf": tf, "direction": direction, "k": k, "rr": r,
                       "params": {**combo_params(direction, active, tf),
                                  "atr_stop_mult": k, "rr": r},
                       "desc": f"{_describe(direction, active, tf)} · {k}×ATR stop · {r}R",
                       **ev}
                all_rows.append(row)
                if ev["robust"] and ev["net_pct"] > 0:
                    survivors.append((active, row))
            if ci % 500 == 0:
                print(f"[{tf}] {ci}/{len(combos)} · {time.time()-t0:.0f}s · "
                      f"survivors: {len(survivors)}", flush=True)

        # Stage 2 — full (k × R) matrix on this tf's best survivors: the
        # sweet-spot map he asked for. A real edge is a green neighbourhood.
        best = sorted([s for s in survivors if s[1]["tf"] == tf],
                      key=lambda s: s[1]["net_pct"], reverse=True)[:TOP_STAGE2]
        print(f"[{tf}] stage 2: {len(FINE_K)}×{len(FINE_R)} matrix × "
              f"{len(best)} survivors", flush=True)
        for active, row in best:
            sig = _sig_fn(_combo_mask(masks, nb, active), row["direction"])
            row["matrix"] = []
            for k in FINE_K:
                for r in FINE_R:
                    ev = _eval(_run_backtest(df, sig, _geo(k, r), CAPITAL), mid_iso)
                    if ev:
                        row["matrix"].append(_cell(ev, k, r))
            row["green_cells"] = sum(1 for c in row["matrix"]
                                     if c["robust"] and c["net_pct"] > 0)

        # Stage 3 — 7y deep confirmation at the combo's OWN surviving regime
        tf_surv = [s for s in survivors if s[1]["tf"] == tf]
        if tf_surv:
            ddf = _load(tf, 84, exchange="binance")
            dmasks = _masks(ddf)
            dmid = ddf.index[len(ddf) // 2].isoformat()
            for active, row in tf_surv:
                sig = _sig_fn(_combo_mask(dmasks, len(ddf), active),
                              row["direction"])
                ev = _eval(_run_backtest(ddf, sig, _geo(row["k"], row["rr"]),
                                         CAPITAL), dmid)
                row["deep"] = ev
                row["deep_confirmed"] = bool(ev and ev["robust"]
                                             and ev["net_pct"] > 0)

    surv_rows = sorted([r for _a, r in survivors],
                       key=lambda r: (r.get("deep_confirmed", False),
                                      r.get("green_cells", 0), r["net_pct"]),
                       reverse=True)
    out = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "version": 3, "months": MONTHS, "capital": CAPITAL,
        "risk": RISK, "coarse_regimes": coarse,
        "fine_k": FINE_K, "fine_rr": FINE_R,
        "min_n": MIN_N, "max_conditions": MAX_CONDS,
        "evaluated": len(all_rows),
        "survivors": surv_rows,
        "all": sorted(all_rows, key=lambda r: r["net_pct"], reverse=True)[:300],
    }
    with open("strategy_search.json", "w") as f:
        json.dump(out, f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))

    print(f"\n=== DONE in {time.time()-t0:.0f}s — {len(all_rows)} evaluated, "
          f"{len(surv_rows)} split-half survivors, "
          f"{sum(1 for r in surv_rows if r.get('deep_confirmed'))} deep-confirmed ===",
          flush=True)
    print(f"{'net%':>7} {'PF':>5} {'WR':>5} {'n':>5} {'DD':>5} {'h1':>7} {'h2':>7} "
          f"{'geo✓':>4} {'deep':>6} {'kelly':>6}  desc")
    for s in surv_rows[:30]:
        dp = s.get("deep") or {}
        print(f"{s['net_pct']:>7} {s['pf']:>5} {s['wr']:>5} {s['n']:>5} "
              f"{s['max_dd']:>5} {s['half1']:>7} {s['half2']:>7} "
              f"{s.get('green_cells','-'):>4} "
              f"{(str(dp.get('net_pct'))+'%') if dp else '—':>6} "
              f"{s.get('kelly') if s.get('kelly') is not None else '—':>6}  {s['desc']}")
    if not surv_rows:
        print("No combo survived split-half in ANY (k×ATR, R) regime — "
              "dynamic geometry included, this space holds no robust edge.")


def rescore_baselines():
    """Gate 4 — beat random entry. Wide-stop LONGs ride BTC drift: on the 7y
    window buy-every-bar at 2.5×ATR is itself split-half green, so 'deep
    confirmed' alone over-credits longs. Rescore every survivor against the
    every-bar baseline at its own (tf, k, R) on both windows; a survivor only
    counts if its per-trade expectancy beats the baseline's on BOTH."""
    with open("strategy_search.json") as f:
        out = json.load(f)
    surv = out["survivors"]
    regimes = sorted({(s["tf"], s["direction"], s["k"], s["rr"]) for s in surv})
    every = lambda d: (lambda df, i, p: d if i >= 60 else None)
    per_trade = lambda ev: (ev["half1"] + ev["half2"]) / ev["n"] if ev and ev["n"] else None

    base = {}
    for window, months, exch in (("w30", MONTHS, None), ("deep", 84, "binance")):
        for tf in sorted({t for t, *_ in regimes}):
            df = _load(tf, months, exchange=exch)
            mid = df.index[len(df) // 2].isoformat()
            for t, d, k, r in regimes:
                if t != tf:
                    continue
                ev = _eval(_run_backtest(df, every(d), _geo(k, r), CAPITAL), mid)
                base[(window, t, d, k, r)] = ev
                print(f"baseline {window} {t} {d} k={k} R={r}: "
                      f"net {ev['net_pct'] if ev else '—'}%", flush=True)

    for s in surv:
        key = (s["tf"], s["direction"], s["k"], s["rr"])
        b30, bdeep = base[("w30", *key)], base[("deep", *key)]
        s["baseline_30"] = {"net_pct": b30["net_pct"], "exp_t": round(per_trade(b30), 3)} if b30 else None
        s["baseline_deep"] = {"net_pct": bdeep["net_pct"], "exp_t": round(per_trade(bdeep), 3)} if bdeep else None
        e30 = per_trade(s) - (per_trade(b30) or 0.0) if per_trade(s) is not None else None
        dp = s.get("deep")
        edeep = (per_trade(dp) - (per_trade(bdeep) or 0.0)) if dp and per_trade(dp) is not None else None
        s["edge_30"] = round(e30, 3) if e30 is not None else None
        s["edge_deep"] = round(edeep, 3) if edeep is not None else None
        s["beats_baseline"] = bool(s.get("deep_confirmed")
                                   and e30 is not None and e30 > 0
                                   and edeep is not None and edeep > 0)

    out["survivors"] = sorted(surv, key=lambda s: (s.get("beats_baseline", False),
                                                   s.get("deep_confirmed", False),
                                                   s.get("green_cells", 0) or 0,
                                                   s["net_pct"]), reverse=True)
    out["baselines"] = [{"window": w, "tf": t, "direction": d, "k": k, "rr": r, **ev}
                        for (w, t, d, k, r), ev in base.items() if ev]
    out["final_survivors"] = sum(1 for s in surv if s.get("beats_baseline"))
    with open("strategy_search.json", "w") as f:
        json.dump(out, f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\n=== gate 4: {out['final_survivors']} of {len(surv)} survivors "
          f"beat their random-entry baseline on both windows ===", flush=True)
    top = [s for s in out["survivors"] if s.get("beats_baseline")][:25]
    for s in top:
        print(f"edge30 {s['edge_30']:>6} edgeDeep {s['edge_deep']:>6} "
              f"net {s['net_pct']:>6}% deep {s['deep']['net_pct']:>7}% "
              f"n={s['n']:>4}  {s['desc']}")


if __name__ == "__main__":
    import sys
    if "--rescore" in sys.argv:
        rescore_baselines()
    else:
        run_search()
        rescore_baselines()
