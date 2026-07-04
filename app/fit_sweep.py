"""/edge #fit — goal-constrained parameter sweep (Stage A).

The inverse of the strategy search: hold the GOAL fixed (start/target/date, Kelly
fraction, DD cap, execution, slippage) and sweep the strategy-SHAPE parameters
(leverage · trades/week · win rate · R:R · ATR floor) to find which region of
that space can actually reach the goal at sane risk.

Each cell is one `compute_goal(...)` call — pure math, no candles. A cell is
FEASIBLE on two gates, both required:
  1. CLOSES — the cell's geometric drift reaches the target BY the date
     (weeks_to_goal ≤ weeks_remaining). /goal's verdict banner skips this — it
     only judges risk — so a 77× goal reads "safe" there while the edge reaches
     it in 48 weeks with 13 left. The whole point of this page is "can it
     actually hit the goal", so sufficiency is gated here.
  2. SANE — used risk ≤ the Kelly/DD-capped optimal risk AND risk-of-ruin ≤ 1%
     (that is /goal's "✅ Within safe risk").
The joint optimum = the feasible cell with the most risk headroom (opt/used); its
axis values pin the heatmap slices. The envelope = per-axis bounds of the whole
feasible set — "any strategy inside these bounds can hit the goal in time at sane
risk". When nothing is feasible, the nearest miss is surfaced instead. Alongside
it, `measured` places YOUR real closed-trade stats (win rate · R:R · cadence ·
risk/trade) in the same coordinates, so the page can say whether what you
actually trade lands inside that envelope.

Runs in one background thread, polled by the page. Same start/status/lock
single-flight shape as search_custom.py. Stage B (filtering the real strategy
search by this envelope) is deliberately NOT here.
"""
import threading
import time
from datetime import date

from .calculator import CalcError, compute_goal
from .database import _conn, get_actual_stats

CELL_CAP = 200_000   # refuse bigger grids — tell the user to tighten ranges

# Swept-axis defaults (lo, hi, step). Every bound is user-editable in the form;
# these only seed it. trades/week hi is replaced by the live historical average.
AXIS_DEFAULTS = {
    "leverage":  (0.5, 10.0, 0.5),
    "freq":      (0.5,  8.0, 0.5),   # trades/week; hi := historical avg at request time
    "wr":        (0.30, 0.70, 0.05),
    "rr":        (1.0,  5.0, 0.5),
    "atr":       (0.0,  0.02, 0.005),  # ATR floor as a price-move fraction (0.5% = 0.005)
}

_state = {"running": False, "done": 0, "total": 0, "error": None,
          "started": 0.0, "result": None}
_lock = threading.Lock()


def historical_freq_per_week() -> float:
    """Closed trades in the last 365 days ÷ 52 — the real weekly cadence, used to
    cap the trades/week axis. Live from the DB so it tracks as trades accrue."""
    try:
        con = _conn()
        n = con.execute(
            "SELECT COUNT(*) FROM trades WHERE pnl IS NOT NULL "
            "AND opened_at >= date('now','-365 days')"
        ).fetchone()[0]
        con.close()
        return round(max(n, 1) / 52.0, 2)
    except Exception:
        return AXIS_DEFAULTS["freq"][1]


def _axis(lo: float, hi: float, step: float) -> list:
    """Inclusive [lo, hi] grid at `step`, rounded to kill float dust. Always ≥1
    value; if lo>hi, just [lo]."""
    if step <= 0 or hi < lo:
        return [round(lo, 4)]
    out, v, i = [], lo, 0
    while v <= hi + 1e-9:
        out.append(round(v, 4))
        i += 1
        v = lo + i * step
    return out


def build_axes(req: dict) -> dict:
    """Resolve the five swept axes from the request (lo/hi/step per axis), filling
    from AXIS_DEFAULTS. freq hi defaults to the live historical average."""
    d = AXIS_DEFAULTS
    def ax(name, dlo, dhi, dstep):
        lo = req.get(f"{name}_min", dlo)
        hi = req.get(f"{name}_max", dhi)
        st = req.get(f"{name}_step", dstep)
        return _axis(float(lo), float(hi), float(st))
    freq_hi_default = req.get("freq_max", historical_freq_per_week())
    return {
        "leverage": ax("lev", *d["leverage"]),
        "freq":     _axis(float(req.get("freq_min", d["freq"][0])),
                          float(freq_hi_default),
                          float(req.get("freq_step", d["freq"][2]))),
        "wr":       ax("wr",  *d["wr"]),
        "rr":       ax("rr",  *d["rr"]),
        "atr":      ax("atr", *d["atr"]),
    }


def _goal_params(req: dict) -> dict:
    """The fixed goal params (everything the sweep does NOT vary), from the
    request, which the page prefills from /api/config."""
    td = req.get("target_date")
    if isinstance(td, str):
        td = date.fromisoformat(td)
    return {
        "start_balance":         float(req["start_balance"]),
        "target_balance":        float(req["target_balance"]),
        "target_date":           td,
        "max_drawdown_allowed":  float(req.get("max_drawdown_allowed", 0.50)),
        "losses_allowed":        int(req.get("losses_allowed", 20)),
        "fractional_kelly":      float(req.get("fractional_kelly", 1.0 / 6.0)),
        "execution_fill_factor": float(req.get("execution_fill_factor", 1.0)),
        "slippage_pct":          float(req.get("slippage_pct", 0.0)),
        "btc_price_eur":         req.get("btc_price_eur"),
        "btc_growth_monthly":    float(req.get("btc_growth_monthly", 0.04)),
    }


def total_cells(axes: dict) -> int:
    n = 1
    for v in axes.values():
        n *= len(v)
    return n


def _eval_cell(lev, freq, wr, rr, atr, weeks_remaining, gp) -> dict | None:
    """One goal-model evaluation → the compact per-cell record, or None if the
    parameters make the model itself invalid (CalcError). atr floor of 0 = off."""
    try:
        g = compute_goal(
            gp["start_balance"], gp["target_balance"], gp["target_date"],
            trades_per_week=freq, win_rate=wr, rr_ratio=rr, leverage=lev,
            max_drawdown_allowed=gp["max_drawdown_allowed"],
            losses_allowed=gp["losses_allowed"],
            fractional_kelly=gp["fractional_kelly"],
            execution_fill_factor=gp["execution_fill_factor"],
            slippage_pct=gp["slippage_pct"],
            min_underlying_stop_pct=(atr if atr > 0 else None),
            btc_price_eur=gp["btc_price_eur"],
            btc_growth_monthly=gp["btc_growth_monthly"],
        )
    except (CalcError, ArithmeticError, ValueError):
        # CalcError = model says infeasible params; Overflow/ValueError = a cell
        # pushed the maths into a numerical corner (absurd target/date). Skip the
        # cell, never crash the sweep.
        return None
    used = g["risk_per_trade"]        # % account loss on a losing trade (derived)
    opt = g["optimal_risk_pct"]       # % MIN(Kelly, DD cap) — advisory ceiling
    ror = g["risk_of_ruin"]           # % over the horizon
    headroom = (opt / used) if used > 0 else 0.0
    # gate 1 — sufficiency: does this edge's geometric drift reach the target in
    # time? (None weeks = drift ≤ 0 → never). This is the check /goal omits.
    wtg = g["weeks_to_goal_actual"]   # None when drift ≤ 0
    closes = wtg is not None and wtg <= weeks_remaining
    # gate 2 — risk sanity (= /goal's "within safe risk")
    sane = (used <= opt) and (ror <= 1.0)
    return {
        # axis coordinates (native floats — json can't take numpy)
        "lev": float(lev), "freq": float(freq), "wr": float(wr),
        "rr": float(rr), "atr": float(atr),
        # metrics
        "used": round(used, 4), "opt": round(opt, 4), "ror": round(float(ror), 4),
        "headroom": round(headroom, 4),
        "sharpe": float(g["sharpe_ratio"]),
        "ev": float(g["per_trade_ev"]),
        "ev_req": float(g["per_trade_ev_required"]),
        "drift": float(g["geometric_drift"]),
        "actual_rr": float(g["actual_rr"]),
        "weeks_to_goal": (round(float(wtg), 1) if wtg is not None else None),
        "closes": bool(closes),
        "sane": bool(sane),
        "feasible": bool(closes and sane),
    }


# The four heatmap planes the UI offers: (y-axis, x-axis). Every other axis is
# pinned at the joint optimum, so each plane is a 2D slice through it.
PLANES = [
    ("lev_freq", "leverage", "freq"),   # leverage scaling × weekly frequency
    ("wr_rr",    "wr",       "rr"),      # win-rate sensitivity × reward:risk
    ("atr_lev",  "atr",      "leverage"),
    ("freq_wr",  "freq",     "wr"),
]
_AXIS_KEY = {"leverage": "lev", "freq": "freq", "wr": "wr", "rr": "rr", "atr": "atr"}


def _build_planes(cells: list, optimum: dict, axes: dict) -> dict:
    """For each offered plane, the 2D grid of cells with the three off-plane axes
    pinned at the optimum. This is all the client needs — shipping the full
    ~100k-cell grid would be tens of MB; the planes are a few hundred cells each.
    Metric/axis-pair switching is then a client-side re-render, no re-run."""
    if optimum is None:
        return {}
    out = {}
    for name, yaxis, xaxis in PLANES:
        ykey, xkey = _AXIS_KEY[yaxis], _AXIS_KEY[xaxis]
        pins = {_AXIS_KEY[a]: optimum[_AXIS_KEY[a]]
                for a in axes if a != yaxis and a != xaxis}
        plane_cells = [
            c for c in cells
            if all(abs(c[k] - v) < 1e-6 for k, v in pins.items())
        ]
        out[name] = {
            "y": ykey, "x": xkey,
            "ys": axes[yaxis], "xs": axes[xaxis],
            "cells": plane_cells,
        }
    return out


def _envelope(feasible: list) -> dict:
    """Per-axis min/max over the feasible set — the bounds any viable strategy
    must land inside. Empty when nothing is feasible."""
    if not feasible:
        return {}
    env = {}
    for k in ("lev", "freq", "wr", "rr", "atr"):
        vals = [c[k] for c in feasible]
        env[k] = {"min": min(vals), "max": max(vals)}
    return env


def _measured(gp: dict) -> dict | None:
    """Your REAL strategy, measured from closed trades, in the same coordinates as
    the envelope — so the page can answer "is what I actually trade inside the
    feasible island?". Win rate / R:R / cadence come straight from get_actual_stats;
    risk/trade is the realised account loss on an average loser (|avg loss| ÷
    balance); the Kelly cap is what MIN(Kelly, DD) allows AT your measured edge
    (leverage-independent). None when there are no closed trades to measure."""
    s = get_actual_stats()
    n = s.get("total_trades") or 0
    if n < 1:
        return None
    wr = (s["actual_wr"] / 100.0) if s.get("actual_wr") is not None else None
    rr = s.get("actual_rr")
    freq = s.get("trades_per_week")
    bal, avg_loss = s.get("current_balance"), s.get("avg_loss_eur")
    risk_pct = (abs(avg_loss) / bal * 100.0) if (bal and avg_loss) else None
    kelly_cap = None
    if wr is not None and rr:
        try:
            g = compute_goal(
                gp["start_balance"], gp["target_balance"], gp["target_date"],
                trades_per_week=(freq or 1.0), win_rate=wr, rr_ratio=rr, leverage=1.0,
                max_drawdown_allowed=gp["max_drawdown_allowed"],
                losses_allowed=gp["losses_allowed"],
                fractional_kelly=gp["fractional_kelly"],
                execution_fill_factor=gp["execution_fill_factor"],
                slippage_pct=gp["slippage_pct"],
                btc_price_eur=gp["btc_price_eur"],
                btc_growth_monthly=gp["btc_growth_monthly"],
            )
            kelly_cap = g["optimal_risk_pct"]
        except (CalcError, ArithmeticError, ValueError):
            kelly_cap = None
    kelly_util = (risk_pct / kelly_cap * 100.0) if (risk_pct and kelly_cap) else None
    return {
        "n": n, "wr": wr, "rr": rr, "freq": freq,
        "risk_pct":      (round(risk_pct, 2) if risk_pct is not None else None),
        "kelly_cap_pct": (round(kelly_cap, 2) if kelly_cap is not None else None),
        "kelly_util":    (round(kelly_util, 1) if kelly_util is not None else None),
    }


def _pick_optimum(cells: list) -> dict | None:
    """The joint optimum, or the nearest miss when nothing is feasible. Layered so
    the fallback degrades along the axis that's failing:
      1. feasible (closes + sane) → most risk headroom (gentlest sizing that works)
      2. else cells that CLOSE the goal but bust risk → most headroom (closest to sane)
      3. else no cell closes in time → the one that gets closest (min weeks-to-goal)"""
    if not cells:
        return None
    feasible = [c for c in cells if c["feasible"]]
    if feasible:
        return max(feasible, key=lambda c: c["headroom"])
    closes = [c for c in cells if c["closes"]]
    if closes:
        return max(closes, key=lambda c: c["headroom"])
    withdrift = [c for c in cells if c["weeks_to_goal"] is not None]
    if withdrift:
        return min(withdrift, key=lambda c: c["weeks_to_goal"])
    return max(cells, key=lambda c: c["headroom"])


def evaluate(req: dict, progress=None) -> dict:
    """Synchronous full sweep — the testable core. Returns axes, all cells, the
    joint optimum (or nearest miss), the feasible envelope, and counts.
    `progress(done, total)` is called periodically if given."""
    axes = build_axes(req)
    gp = _goal_params(req)
    weeks_remaining = max((gp["target_date"] - date.today()).days, 0) / 7.0
    total = total_cells(axes)
    cells, done = [], 0
    for lev in axes["leverage"]:
        for freq in axes["freq"]:
            for wr in axes["wr"]:
                for rr in axes["rr"]:
                    for atr in axes["atr"]:
                        c = _eval_cell(lev, freq, wr, rr, atr, weeks_remaining, gp)
                        done += 1
                        if c is not None:
                            cells.append(c)
                        if progress and done % 4000 == 0:
                            progress(done, total)
    if progress:
        progress(done, total)
    feasible = [c for c in cells if c["feasible"]]
    optimum = _pick_optimum(cells)
    return {
        "axes": axes,
        "planes": _build_planes(cells, optimum, axes),
        "optimum": optimum,
        "feasible_count": len(feasible),
        "closes_count": sum(1 for c in cells if c["closes"]),
        "evaluated": len(cells),
        "total": total,
        "weeks_remaining": round(weeks_remaining, 1),
        "envelope": _envelope(feasible),
        "measured": _measured(gp),
        "goal": {"start_balance": gp["start_balance"],
                 "target_balance": gp["target_balance"],
                 "target_date": gp["target_date"].isoformat()},
    }


def _worker(req: dict):
    try:
        def prog(done, total):
            with _lock:
                _state["done"], _state["total"] = done, total
        result = evaluate(req, progress=prog)
        with _lock:
            _state["result"] = result
    except Exception as e:
        with _lock:
            _state["error"] = str(e)
    finally:
        with _lock:
            _state["running"] = False


def start(req: dict) -> dict:
    with _lock:
        if _state["running"]:
            return {"error": "a sweep is already running"}
    axes = build_axes(req)
    total = total_cells(axes)
    if total > CELL_CAP:
        return {"error": f"grid too large: ~{total:,} cells (cap {CELL_CAP:,}). "
                         f"Tighten a range or coarsen a step — widen the leverage "
                         f"or R:R step, or narrow the win-rate band."}
    if total == 0:
        return {"error": "empty grid — check the axis ranges."}
    with _lock:
        _state.update(running=True, done=0, total=total, error=None,
                      result=None, started=time.time())
    threading.Thread(target=_worker, args=(req,), daemon=True).start()
    return {"started": True, "total_est": total}


def status() -> dict:
    with _lock:
        return {"running": _state["running"], "done": _state["done"],
                "total": _state["total"], "error": _state["error"],
                "result": _state["result"]}
