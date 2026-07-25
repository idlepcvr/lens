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
from .patterns import PATTERN_SLOTS
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
    the user set them (handled by the base mask), so drop them from the sweep.

    Pattern/HTF slots are excluded unless explicitly asked for. The /edge form
    has no field to pin them, so sweeping them would mean every interactive
    search silently explores conditions the user cannot see or switch off — and
    multiplies the eval count against the cap (a fully-specified combo went from
    1 cell to 131). The research pipeline (grid search + breeder) reads SLOTS
    directly and does get the new vocabulary.

    ponytail: opt-in flag rather than UI work. Upgrade path — add the five
    selects to the /edge form, then default `patterns` to True and delete this.
    """
    free = set(pins)
    if req.get("rsi_max") is not None or req.get("rsi_min") is not None:
        free.add("rsi")
    if req.get("hour_from") is not None and req.get("hour_to") is not None:
        free.add("hours")
    if not req.get("patterns"):
        free |= set(PATTERN_SLOTS)
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
                                    # trades/week over the tested window — the envelope's cadence axis
                                    "freq": round(int(ev["n"]) / (months * 4.345), 2),
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


# ─── Stage B: score each result against the Fit envelope ─────────────────────
#
# Scored distance, not a hard box. "How close" is the useful information and a
# hard box throws it away — a strategy failing win rate by 1 point is a different
# animal from one failing by 15. Distance 0 on every axis = FITS.
#
# Only the axes the search actually varies are scored: win rate, R:R, cadence.
# Every backtest runs at the fixed 5× leverage of strategy_search3.RISK, so a
# leverage axis would pass or fail all 8,000 rows identically — that check belongs
# at the page level, once, not per row (SEARCH_LEVERAGE below).
SEARCH_LEVERAGE = RISK["leverage"]
_AXES = (
    #  key     envelope key   label            row value
    ("wr",    "wr",   "win rate",     lambda r: r["wr"] / 100.0),
    ("rr",    "rr",   "R:R",          lambda r: r["rr"]),
    ("freq",  "freq", "trades/week",  lambda r: r.get("freq")),
)


def _span(lo: float, hi: float) -> float:
    """Normalizer for one axis. A degenerate envelope (one feasible cell → lo==hi)
    would divide by zero, so fall back to a tenth of the bound's magnitude."""
    return (hi - lo) or max(abs(hi), 1e-6) * 0.1


def _fmt(axis: str, v: float) -> str:
    return f"{v*100:.0f}%" if axis == "wr" else f"{v:g}"


def score_row(row: dict, env: dict) -> dict:
    """Per-axis normalized distance outside the envelope; 0 = inside."""
    dist, fails = 0.0, []
    for key, ekey, label, get in _AXES:
        v = get(row)
        b = env.get(ekey)
        if v is None or not b:
            continue
        lo, hi = b["min"], b["max"]
        if v < lo:
            d, need = (lo - v) / _span(lo, hi), f"≥ {_fmt(key, lo)}"
        elif v > hi:
            d, need = (v - hi) / _span(lo, hi), f"≤ {_fmt(key, hi)}"
        else:
            continue
        dist += d
        fails.append({"axis": label, "needs": need, "has": _fmt(key, v), "d": round(d, 3)})
    return {"dist": round(dist, 3), "fits": not fails, "fails": fails}


def annotate(rows: list, env_row: dict | None) -> list:
    """Attach `fit` to every row. A stale or empty envelope annotates nothing —
    filtering on numbers nobody re-derived is worse than not filtering."""
    if not env_row or env_row["stale"] or not env_row["envelope"]:
        return rows
    for r in rows:
        r["fit"] = score_row(r, env_row["envelope"])
    return rows


def _realism(rows: list) -> None:
    """C4 — does the market actually offer each row's TP move often enough to
    feed its cadence? Its stop is k×ATR on its own timeframe, so its required
    move is k×ATR%×R. Best-effort: a dead candle feed must not break the search."""
    try:
        from .realism import badge, row_move_pct
    except Exception:
        return
    for r in rows:
        try:
            r["realism"] = badge(row_move_pct(r["k"], r["rr"], r["tf"]), r.get("freq"))
        except Exception:
            r["realism"] = None


def status() -> dict:
    from .fit_sweep import latest_envelope
    env_row = latest_envelope()
    with _lock:
        rows = list(_state["rows"])
    annotate(rows, env_row)
    usable = bool(env_row and not env_row["stale"] and env_row["envelope"])
    # near-misses still rank, just lower: FITS first, then the usual robust/net sort
    rows.sort(key=lambda x: ((x.get("fit") or {}).get("fits", False) if usable else False,
                             x["robust"], x["net_pct"]), reverse=True)
    top = rows[:50]
    _realism(top)   # C4 — only the rows we ship; the badge costs a candle load
    env_meta = None
    if env_row:
        lev = env_row["envelope"].get("lev")
        env_meta = {
            "created_at": env_row["created_at"], "age_days": env_row["age_days"],
            "stale": env_row["stale"], "usable": usable,
            "feasible_count": env_row["feasible_count"],
            "envelope": env_row["envelope"],
            # every backtest here runs at this leverage — one page-level check
            "search_leverage": SEARCH_LEVERAGE,
            "leverage_ok": (lev is None) or (lev["min"] <= SEARCH_LEVERAGE <= lev["max"]),
        }
    with _lock:
        return {"running": _state["running"], "done": _state["done"],
                "total": _state["total"], "error": _state["error"],
                "months": _state["months"], "found": len(_state["rows"]),
                "top": top, "env": env_meta,
                "fits_count": sum(1 for r in rows if (r.get("fit") or {}).get("fits"))}
