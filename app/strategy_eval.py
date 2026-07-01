"""LENS strategy evaluation — rank every strategy by an R-sweep.

For each strategy (a bar-context predicate + direction) we:
  1. find all qualifying bars over the full candle history,
  2. set a tight structural stop = p65 of the 8h max-adverse-excursion,
  3. stretch the target across R = 1.0 … 3.0 and first-touch each one
     (stop checked first = conservative), net of round-trip fees,
  4. score it so that staying profitable at HIGHER R ("let winners run")
     is rewarded.

Output is cached to strategy_scores.json so the /strategy page never has to
re-scan 11k candles on a page load. Refresh with:  python3 -m app.strategy_eval
"""
import datetime as _dt
import json
import os
import sqlite3
import statistics as st

from .database import DB_PATH
from .setups import SetupEngine, _load_candles

FEE_PCT = 0.30                       # round-trip taker fee, % of notional
R_LEVELS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
FORWARD_BARS = 96                    # ~4 days, so even a 6R target gets a fair chance to fill
MAE_WINDOW = 8                       # bars used to size the structural stop
MIN_N = 40                           # below this a strategy is "thin", unranked

CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "strategy_scores.json")


# ── strategy registry ─────────────────────────────────────────────────────────

def _registry(atr_hi, atrpct_lo=None):
    """Every evaluatable strategy as a bar-context predicate. pred(ctx, atr)->bool.
    mode = prop | hedge; dir = long | short."""
    R = []
    def add(name, mode, direction, pred, note):
        R.append({"name": name, "mode": mode, "dir": direction,
                  "pred": pred, "note": note})

    # ── HEDGE: the existing S1–S5 setups ──
    add("S1 · NY-AM flush", "hedge", "short",
        lambda c, a: c.killzone == "ny_am_kz" and c.rsi is not None and c.rsi < 40 and c.bear_streak3,
        "RSI<40 + 3 bear closes in NY-AM killzone")
    add("S2 · premium displacement", "hedge", "short",
        lambda c, a: c.pd_zone == "premium" and c.displacement == "bear",
        "bear displacement bar in premium of range")
    add("S3 · continuation long", "hedge", "long",
        lambda c, a: c.rsi is not None and c.rsi > 55 and c.sweep == "buyside",
        "RSI>55 + buyside sweep")
    add("S4 · discount dip", "hedge", "long",
        lambda c, a: c.rsi is not None and c.rsi < 40 and c.pd_zone == "discount" and c.sweep is None,
        "RSI<40 in discount, no recent sweep")
    add("S5 · London momentum", "hedge", "long",
        lambda c, a: c.rsi is not None and c.rsi > 55 and c.killzone == "london_kz",
        "RSI>55 in London killzone")

    # ── HEDGE: mined candidates ──
    add("H6 · bear3 + equilibrium", "hedge", "short",
        lambda c, a: c.bear_streak3 and c.pd_zone == "eq",
        "3 bear closes in equilibrium zone")
    add("H7 · RSI>70 no-sweep", "hedge", "long",
        lambda c, a: c.rsi is not None and c.rsi > 70 and c.sweep is None,
        "strong momentum, no sweep yet")
    add("H8 · bear disp + RSI<30", "hedge", "short",
        lambda c, a: c.displacement == "bear" and c.rsi is not None and c.rsi < 30,
        "momentum-continuation short")
    add("H9 · London sellside sweep", "hedge", "short",
        lambda c, a: c.killzone == "london_kz" and c.sweep == "sellside",
        "London killzone after sellside sweep")
    add("H10 · bear FVG + RSI30-40", "hedge", "short",
        lambda c, a: c.in_fvg["short"] and c.rsi is not None and 30 <= c.rsi < 40,
        "inside bearish FVG, weak bounce")
    add("H11 · high-vol RSI55-70", "hedge", "short",
        lambda c, a: a and a > atr_hi and c.rsi is not None and 55 < c.rsi < 70,
        "high-vol fade from momentum")
    # ── mined 2026-07-02 (strategies/_research/STRATEGY_AUDIT_20260702.md) ──
    # atr% (not absolute ATR) so the low-vol regime is honest across price eras.
    add("H12 · quiet-uptrend grind", "hedge", "long",
        lambda c, a: (atrpct_lo and a and c.close
                      and (a / c.close * 100) < atrpct_lo
                      and c.pd_zone == "eq" and c.slope == "up"),
        "low-vol equilibrium + rising EMA21; mined +0.94%/tr @ 2/6")
    add("H13 · weak-bounce fade", "hedge", "short",
        lambda c, a: c.rsi is not None and c.rsi < 30 and c.pd_zone == "eq",
        "RSI<30 in equilibrium, continuation short; mined +0.50%/tr @ 2/3")

    # PROP strategies are evaluated through their real 4H/1H backtest engine
    # (see PROP_BACKTEST / _eval_prop), not this 1h bar-context proxy.
    return R


# PROP universe: the real backtest strategies on 4h/1h timeframes (the 5m/15m
# ones are a different microstructure and slow to sweep, so excluded here).
PROP_BACKTEST = [
    "ASIAN_RSI_DIP_v1", "ASIAN_RSI_DIP_1H_v1", "ASIAN_PULLBACK_v1", "ASIAN_PULLBACK_v2",
    "KZ_RSI_DIP_1H_v1", "RSI_DIP_v1", "1H_RSI_DIP_v1", "1H_PULLBACK_v1",
    "PULLBACK_4R_v1", "TREND_4R_v1", "MACD_CROSS_v1", "ENGULF_v1",
    "CONVICTION_STACK_v1", "CONVICTION_STACK_v2",
]


# ── evaluation ─────────────────────────────────────────────────────────────────

def _pctl(v, p):
    if not v:
        return float("nan")
    v = sorted(v)
    k = (len(v) - 1) * p / 100
    f = int(k)
    return v[f] if f + 1 >= len(v) else v[f] + (v[f + 1] - v[f]) * (k - f)


def _first_touch(c1h, N, idx, long_, sl_pct, tp_pct):
    """+1 target hit first, 0 stop hit first, None unresolved in window."""
    e = c1h[idx][4]
    if long_:
        sl, tp = e * (1 - sl_pct / 100), e * (1 + tp_pct / 100)
    else:
        sl, tp = e * (1 + sl_pct / 100), e * (1 - tp_pct / 100)
    for j in range(idx + 1, min(idx + 1 + FORWARD_BARS, N)):
        hi, lo = c1h[j][2], c1h[j][3]
        if (lo <= sl) if long_ else (hi >= sl):
            return 0
        if (hi >= tp) if long_ else (lo <= tp):
            return 1
    return None


def _evaluate(c1h, N, ctxs, atr14, strat):
    long_ = strat["dir"] == "long"
    pred = strat["pred"]
    occ = [i for i in range(60, N - 1 - FORWARD_BARS)
           if ctxs[i] is not None and ctxs[i].rsi is not None and pred(ctxs[i], atr14[i])]

    base = {"name": strat["name"], "mode": strat["mode"], "dir": strat["dir"],
            "note": strat["note"], "n": len(occ)}
    if len(occ) < MIN_N:
        return {**base, "thin": True, "sl": None, "rows": [],
                "score": -99.0, "best_r": None, "best_net": None, "best_wr": None}

    # tight structural stop from the 8h adverse excursion
    mae = []
    for i in occ:
        e = c1h[i][4]
        fwd = c1h[i + 1:i + 1 + MAE_WINDOW]
        hi = max(b[2] for b in fwd)
        lo = min(b[3] for b in fwd)
        mae.append((e - lo) / e * 100 if long_ else (hi - e) / e * 100)
    sl = max(round(_pctl(mae, 65), 2), 0.4)

    rows = []
    score = 0.0
    best = (None, -99.0, None)
    for R in R_LEVELS:
        tp = sl * R
        res = [_first_touch(c1h, N, i, long_, sl, tp) for i in occ]
        dec = [r for r in res if r is not None]
        wr = sum(dec) / len(dec) if dec else 0.0
        net = wr * R - (1 - wr) - FEE_PCT / sl          # net R per trade, after fees
        rows.append({"r": R, "wr": round(wr * 100, 1),
                     "net": round(net, 3), "resolved": len(dec)})
        if net > 0:
            score += net * R                            # reward profit at higher R
        if net > best[1]:
            best = (R, net, wr * 100)

    return {**base, "thin": False, "sl": sl, "rows": rows,
            "score": round(score, 3), "best_r": best[0],
            "best_net": round(best[1], 3),
            "best_wr": round(best[2], 1) if best[2] is not None else None}


def _eval_prop(name):
    """R-sweep a prop strategy through its real backtest engine: vary tp_pct to
    hit each R multiple, take the backtest's win rate, then score it under the
    same fee + let-winners-run model the hedge harness uses."""
    from .backtest_engine import STRATEGIES, run_strategy
    if name not in STRATEGIES:
        return None
    strat = STRATEGIES[name]
    stop = strat["params"].get("stop_pct")
    note = strat.get("description", "")[:80]
    base = {"name": name, "mode": "prop", "dir": "long", "note": note}
    if not stop:
        return {**base, "n": 0, "thin": True, "sl": None, "rows": [],
                "score": -99.0, "best_r": None, "best_net": None, "best_wr": None}

    orig_tp = strat["params"].get("tp_pct")
    rows, score, best, n_last = [], 0.0, (None, -99.0, None), 0
    try:
        for R in R_LEVELS:
            strat["params"]["tp_pct"] = round(stop * R, 3)
            m = run_strategy(name, months=30).get("metrics", {})
            n_last = m.get("n", 0)
            wr = (m.get("win_rate") or 0.0) / 100.0
            net = wr * R - (1 - wr) - FEE_PCT / stop
            rows.append({"r": R, "wr": round(wr * 100, 1),
                         "net": round(net, 3), "resolved": n_last})
            if net > 0:
                score += net * R
            if net > best[1]:
                best = (R, net, wr * 100)
    finally:
        strat["params"]["tp_pct"] = orig_tp

    if n_last < MIN_N:
        return {**base, "n": n_last, "thin": True, "sl": stop, "rows": rows,
                "score": -99.0, "best_r": None, "best_net": None, "best_wr": None}
    return {**base, "n": n_last, "thin": False, "sl": stop, "rows": rows,
            "score": round(score, 3), "best_r": best[0],
            "best_net": round(best[1], 3),
            "best_wr": round(best[2], 1) if best[2] is not None else None}


def compute_all():
    """Evaluate every strategy; rank within each mode by score.
    HEDGE = 1h bar-context first-touch harness. PROP = real 4H/1H backtest."""
    conn = sqlite3.connect(DB_PATH)
    c1h = _load_candles(conn)
    conn.close()
    N = len(c1h)
    eng = SetupEngine(c1h)
    atrs = [a for a in eng.atr14 if a]
    _, atr_hi = st.quantiles(atrs, n=3)
    atr_pcts = [a / r[4] * 100 for a, r in zip(eng.atr14, c1h) if a and r[4]]
    atrpct_lo, _ = st.quantiles(atr_pcts, n=3)

    ctxs = [None] * N
    for i in range(60, N):
        try:
            ctxs[i] = eng.context(i)
        except Exception:
            ctxs[i] = None

    results = [_evaluate(c1h, N, ctxs, eng.atr14, s) for s in _registry(atr_hi, atrpct_lo)]
    results += [r for r in (_eval_prop(n) for n in PROP_BACKTEST) if r]
    results.sort(key=lambda x: -x["score"])
    for mode in ("hedge", "prop"):
        rank = 0
        for o in results:
            if o["mode"] != mode:
                continue
            if o["thin"]:
                o["rank"] = None
                o["top3"] = False
            else:
                rank += 1
                o["rank"] = rank
                o["top3"] = rank <= 3
    span = (_dt.datetime.fromtimestamp(c1h[0][0] / 1000, _dt.timezone.utc).date().isoformat(),
            _dt.datetime.fromtimestamp(c1h[-1][0] / 1000, _dt.timezone.utc).date().isoformat())
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "candles": N, "span": span, "fee_pct": FEE_PCT, "r_levels": R_LEVELS,
        "forward_bars": FORWARD_BARS, "results": results,
    }


def refresh_cache():
    data = compute_all()
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2)
    return data


def load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ── live wiring: let the scanners trade the board's top-3 ──────────────────────

def tradeable(mode):
    """The board's ranked top-3 for a mode, ready to trade:
    [{name, dir, sl_pct, target_r, rank}] in rank order. Empty if no cache."""
    d = load_cache()
    if not d:
        return []
    top = sorted([o for o in d["results"]
                  if o["mode"] == mode and o.get("top3") and o.get("best_r") and o.get("sl")],
                 key=lambda x: x["rank"])
    return [{"name": o["name"], "dir": o["dir"], "sl_pct": float(o["sl"]),
             "target_r": float(o["best_r"]), "rank": o["rank"]} for o in top]


def live_matches(eng, i, names):
    """Of the given strategy names, which match on bar i — in the order given.
    Returns [{name, dir}]. Lets a live scanner evaluate the same predicates the
    board ranked, so what fires is exactly what was scored."""
    atrs = [a for a in eng.atr14 if a]
    if not atrs:
        return []
    _, atr_hi = st.quantiles(atrs, n=3)
    atr_pcts = [a / r[4] * 100 for a, r in zip(eng.atr14, eng.c1h) if a and r[4]]
    atrpct_lo, _ = st.quantiles(atr_pcts, n=3)
    reg = {s["name"]: s for s in _registry(atr_hi, atrpct_lo)}
    ctx = eng.context(i)
    a = eng.atr14[i]
    out = []
    for name in names:
        s = reg.get(name)
        if s and ctx.rsi is not None and s["pred"](ctx, a):
            out.append({"name": name, "dir": s["dir"]})
    return out


if __name__ == "__main__":
    d = refresh_cache()
    print(f"scored {len(d['results'])} strategies over {d['candles']} candles "
          f"({d['span'][0]} → {d['span'][1]})\n")
    print(f"{'rank':>4} {'mode':5} {'strategy':28} {'n':>5} {'SL%':>4} "
          f"{'bestR':>5} {'WR@best':>7} {'netR':>6} {'score':>6}")
    for o in sorted(d["results"], key=lambda x: (x["mode"], x["rank"] or 999)):
        if o["thin"]:
            print(f"{'—':>4} {o['mode']:5} {o['name']:28} {o['n']:>5}  thin (<{MIN_N})")
            continue
        star = " ★" if o["top3"] else ""
        print(f"{o['rank']:>4} {o['mode']:5} {o['name']:28} {o['n']:>5} {o['sl']:>4.2f} "
              f"{o['best_r']:>5.1f} {o['best_wr']:>6.1f}% {o['best_net']:>+6.2f} {o['score']:>6.2f}{star}")
