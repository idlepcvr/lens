"""On-demand /edge search: blank builder fields = swept dimensions, pinned =
fixed. A thin orchestrator over the strategy_search machinery (vectorized masks,
combo generator, honest split-half `_eval`) crossed with the v3 ATR geometry.
Runs in one background thread, polled by the builder UI.

Not a rewrite: the entry-condition combinatorics, masks and evaluation are the
exact same code the offline v3 search used — this just lets Lucky steer *which*
slice runs, from the page, and pins the rest.
"""
import itertools
import threading
import time

import numpy as np

from .backtest_engine import load_ohlcv, add_indicators, _run_backtest
from .strategy_search import (CAPITAL, MIN_N, MAX_CONDS, SLOTS, _masks,
                              _combo_mask, _sig_fn, combo_params, _describe, _eval)
from .strategy_search3 import RISK, FINE_K, FINE_R

EVAL_CAP = 8000   # refuse bigger searches — tell the user to pin more fields
STD_SLOTS = ("trend", "candle", "macd", "bb", "td", "ma_align", "atr", "vol")

_state = {"running": False, "done": 0, "total": 0, "rows": [],
          "error": None, "months": 30, "started": 0.0}
_lock = threading.Lock()


def _pinned_std(req: dict) -> dict:
    """Standard-slot pins (fixed values with prebuilt masks) → {slot: option}."""
    a = {}
    for k in ("trend", "candle", "macd", "bb", "td", "ma_align"):
        if req.get(k):
            a[k] = req[k]
    if req.get("atr_regime"):
        a["atr"] = req["atr_regime"]
    if req.get("vol_spike"):
        a["vol"] = True
    return a


def _pinned_mask(df, req):
    """Base mask for pins the standard masks don't cover: arbitrary RSI / hour
    window (the user may type any threshold). Also carries the 60-bar warm-up."""
    n = len(df)
    m = np.ones(n, dtype=bool)
    m[:60] = False
    if req.get("rsi_max") is not None:
        m &= (df["rsi14"] <= req["rsi_max"]).to_numpy()
    if req.get("rsi_min") is not None:
        m &= (df["rsi14"] >= req["rsi_min"]).to_numpy()
    hf, ht = req.get("hour_from"), req.get("hour_to")
    if hf is not None and ht is not None:
        h = (df.index.hour + 7) % 24
        m &= ((h >= hf) & (h <= ht)) if hf <= ht else ((h >= hf) | (h <= ht))
    return m


def _grid(vals, lo, hi):
    """FINE geometry values inside [lo,hi]; if none land there, use the ends."""
    cells = [v for v in vals if lo <= v <= hi]
    return cells or sorted({round(lo, 3), round(hi, 3)})


def _blank_slots(req, pins):
    """Slots to sweep = every slot not pinned. RSI/hours count as pinned when
    the user set them (handled by the base mask), so drop them from the sweep."""
    free = set(pins)
    if req.get("rsi_max") is not None or req.get("rsi_min") is not None:
        free.add("rsi")
    if req.get("hour_from") is not None and req.get("hour_to") is not None:
        free.add("hours")
    return [s for s in SLOTS if s not in free]


def _combos(blank, directions):
    """Pinned conditions + 0..MAX_CONDS extra conditions drawn from blank slots,
    for each requested direction. r=0 yields the pinned-only combo."""
    for r in range(0, MAX_CONDS + 1):
        for names in itertools.combinations(blank, r):
            for opts in itertools.product(*(SLOTS[n] for n in names)):
                choice = dict(zip(names, opts))
                for d in directions:
                    yield d, choice


def plan(req: dict):
    """Resolve the search space + eval count without running (used for the cap
    check and for tests). Returns (directions, tfs, pins, blank, ks, rs, risks,
    total)."""
    directions = [req["direction"]] if req.get("direction") else ["long", "short"]
    tfs = [req["timeframe"]] if req.get("timeframe") else ["1h", "4h"]
    pins = _pinned_std(req)
    blank = _blank_slots(req, pins)
    ks = _grid(FINE_K, req.get("k_min", 0.0), req.get("k_max", 3.0))
    rs = _grid(FINE_R, req.get("r_min", 1.0), req.get("r_max", 5.0))
    risks = sorted({req.get("risk_min", 2.0), req.get("risk_max", 2.0)})
    n_combos = sum(1 for _ in _combos(blank, directions))
    total = n_combos * len(tfs) * len(ks) * len(rs) * len(risks)
    return directions, tfs, pins, blank, ks, rs, risks, total


def _worker(req: dict):
    try:
        directions, tfs, pins, blank, ks, rs, risks, total = plan(req)
        months = int(req.get("months", 30))
        cell_n = len(ks) * len(rs) * len(risks)
        with _lock:
            _state.update(total=total, months=months)

        for tf in tfs:
            df = add_indicators(load_ohlcv(months=months, timeframe=tf))
            masks = _masks(df)
            nb = len(df)
            mid = df.index[nb // 2].isoformat()
            base = _pinned_mask(df, req)

            for d, choice in _combos(blank, directions):
                active = {**pins, **choice}
                mask = base.copy()
                for slot, opt in active.items():
                    mask &= masks[(slot, opt)]
                if mask.sum() < MIN_N:              # too few entries to ever be robust
                    with _lock:
                        _state["done"] += cell_n
                    continue
                sig = _sig_fn(mask, d)
                new_rows = []
                for k in ks:
                    for r in rs:
                        for risk in risks:
                            geo = {**RISK, "atr_stop_mult": k, "rr": r, "risk_pct": risk}
                            ev = _eval(_run_backtest(df, sig, geo, CAPITAL), mid)
                            if ev is not None:
                                p = combo_params(d, active, tf)
                                p.update({"atr_stop_mult": k, "rr": r, "risk_pct": risk,
                                          "leverage": RISK["leverage"],
                                          "slippage_pct": RISK["slippage_pct"]})
                                new_rows.append({
                                    "desc": f"{_describe(d, active, tf)} · {k:g}×ATR · {r:g}R · {risk:g}% risk",
                                    "params": p, "tf": tf, "direction": d,
                                    "k": float(k), "rr": float(r), "risk": float(risk),
                                    # cast off numpy scalars — json.dumps can't serialize them (the v2 gotcha)
                                    "n": int(ev["n"]), "wr": float(ev["wr"]), "pf": float(ev["pf"]),
                                    "net_pct": float(ev["net_pct"]), "max_dd": float(ev["max_dd"]),
                                    "half1": float(ev["half1"]), "half2": float(ev["half2"]),
                                    "robust": bool(ev["robust"]),
                                })
                with _lock:
                    _state["rows"].extend(new_rows)
                    _state["done"] += cell_n
    except Exception as e:
        with _lock:
            _state["error"] = str(e)
    finally:
        with _lock:
            _state["running"] = False


def start(req: dict) -> dict:
    with _lock:
        if _state["running"]:
            return {"error": "a search is already running"}
    _, _, _, _, _, _, _, total = plan(req)
    if total > EVAL_CAP:
        return {"error": f"search too large: ~{total:,} backtests (cap {EVAL_CAP:,}). "
                         f"Pin more fields — set a direction, a timeframe, or a "
                         f"condition or two — then search the rest."}
    if total == 0:
        return {"error": "empty search space — check the geometry ranges."}
    with _lock:
        _state.update(running=True, done=0, total=0, rows=[], error=None, started=time.time())
    threading.Thread(target=_worker, args=(req,), daemon=True).start()
    return {"started": True, "total_est": total}


def status() -> dict:
    with _lock:
        rows = sorted(_state["rows"], key=lambda x: (x["robust"], x["net_pct"]), reverse=True)[:50]
        return {"running": _state["running"], "done": _state["done"],
                "total": _state["total"], "error": _state["error"],
                "months": _state["months"], "found": len(_state["rows"]), "top": rows}
