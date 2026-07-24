"""Genetic strategy breeder — searches deeper genomes than the grid can reach.

`strategy_search3` enumerated 43,703 combos and stopped at `max_conditions=3`
because grid enumeration explodes, not because 4+ conditions are uninteresting.
A GA walks the space instead of enumerating it, so depth costs population, not
factorial time. That is the whole functional case, and after the 2026-07-24
dedup it is the ONLY case: the vault is not full of near-duplicates
(933 labels → 525 distinct ideas), so there is nothing here to unpack — only
deeper genomes to reach.

**Fitness is measured out-of-sample, and that is not negotiable.** A GA is an
overfitting machine pointed at a fitness function; score it in-sample and it
breeds a curve-fit champion every generation and reports it proudly. Here a
genome's fitness is `min(train_score, holdout_score)` over a split-half of the
window — a genome that only works in-sample scores its (bad) holdout number and
dies in selection, not in a post-screen after it has already won.

Score is **drawdown-penalised expectancy in R** (ratified 2026-07-24): mean R
per trade divided by max drawdown in R. Raw profit factor was rejected — it is
blind to path, so it happily crowns a genome with one catastrophic hole.
`MIN_N` trades required in the holdout half, matching `strategy_search3`'s
split-half gate; six-trade wonders score -inf.

**Geometry genes are not cosmetic.** Measured during the dedup: two genomes with
identical entry conditions at 3.0R vs 5.0R share only 0.38 of their realized
trades, because a different exit frees the position at a different bar and a
different set of later signals gets taken. So `k` and `rr` are bred as part of
the genome and every genome is scored whole — never a condition set scored once
with geometry swept over it afterwards.

**The window is the lever, not the population** (changed 2026-07-24, second
pass). The first run on 30 months found exactly ONE viable genome above 3
conditions out of 103, and the depth profile said why: at 5 conditions, 111 of
120 random genomes selected under 40 bars in the whole window. Depth was not
failing on fitness or on search — it was failing on evidence. Scaling the
population would have searched the same empty room with more agents. So the
default window is now the 7-year Binance set that `strategy_search3` stage 3
already used for deep confirmation: ~2.8x the bars, which is what moves a
condition set from untestable to testable.

The price is that `deep` is Binance **spot** while `w30` is Bybit **perp** —
no funding, different microstructure. Both windows stay runnable (`--window`)
and every result records which one produced it, because they are different
instruments and must never be compared bar-for-bar.

Paper-only R&D. Auto-execution is not in scope and never will be.

Results → strategy_breeder.json. Run from repo root (needs .venv):
    .venv/bin/python -m app.strategy_breeder                  # 84mo Binance spot
    .venv/bin/python -m app.strategy_breeder --window w30     # 30mo Bybit perp
    .venv/bin/python -m app.strategy_breeder --tf 4h --generations 20
"""

import argparse
import json
import random
import time
from datetime import datetime, timezone

import numpy as np

from .backtest_engine import _run_backtest
from .strategy_search import (CAPITAL, MIN_N, MONTHS, SLOTS, _combo_mask,
                              _describe, _masks, _sig_fn, combo_params)
from .strategy_search3 import RISK, _geo, _load
from .paths import BREEDER_JSON

MAX_CONDS   = 6       # the point of the GA — grid search stopped at 3
POP         = 60
GENERATIONS = 12

# Window. The 2026-07-24 run measured that depth fails on DATA, not on search:
# at 5 conditions, 111 of 120 random genomes selected under 40 bars in 30
# months, so there was nothing to score, let alone validate out-of-sample.
# More population searches the same empty room. More bars is the actual lever,
# so the deep window is now the default (2026-07-24).
#
# ⚠ The two windows are NOT the same instrument. "w30" is Bybit BTC/USDT perp;
# "deep" is Binance BTC/USDT SPOT resampled up from 1h — spot has no funding and
# a different microstructure, which is the price of the extra history (the same
# trade `strategy_search3` stage 3 already makes for deep confirmation). Compare
# the two windows as separate evidence, never bar-for-bar.
WINDOWS = {
    "w30":  {"months": MONTHS, "exchange": None,      "desc": "Bybit BTC/USDT perp"},
    "deep": {"months": 84,     "exchange": "binance", "desc": "Binance BTC/USDT spot, 1h resampled"},
}
DEFAULT_WINDOW = "deep"
ELITE       = 6       # copied to the next generation untouched
TOURNAMENT  = 3
P_CROSSOVER = 0.7
P_MUTATE    = 0.9     # per child, then one of several mutation kinds
GEO_K       = (0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)
GEO_R       = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)


# --------------------------------------------------------------------------
# genome

def _random_genome(rng, tf):
    slots = [s for s in SLOTS if not (tf == "1d" and s == "hours")]
    n = rng.randint(1, MAX_CONDS)
    chosen = rng.sample(slots, min(n, len(slots)))
    return {
        "direction": rng.choice(["long", "short"]),
        "conds": {s: rng.choice(SLOTS[s]) for s in chosen},
        "k": rng.choice(GEO_K),
        "rr": rng.choice(GEO_R),
    }


def _key(g):
    """Identity of a genome — two genomes with the same key are the same
    strategy, so the evaluation cache can skip the second one."""
    return (g["direction"], g["k"], g["rr"],
            tuple(sorted((s, str(o)) for s, o in g["conds"].items())))


def _crossover(a, b, rng):
    """Uniform crossover on conditions, independent draw on each geometry gene.

    Conditions merge per slot rather than splicing a list: a genome is a SET of
    conditions, so a positional splice would be arbitrary. Over-long children
    get trimmed back to MAX_CONDS."""
    child = {"direction": rng.choice([a["direction"], b["direction"]]),
             "k": rng.choice([a["k"], b["k"]]),
             "rr": rng.choice([a["rr"], b["rr"]]),
             "conds": {}}
    for slot in set(a["conds"]) | set(b["conds"]):
        have = [g["conds"][slot] for g in (a, b) if slot in g["conds"]]
        if len(have) == 2 or rng.random() < 0.5:
            child["conds"][slot] = rng.choice(have)
    if len(child["conds"]) > MAX_CONDS:
        keep = rng.sample(sorted(child["conds"]), MAX_CONDS)
        child["conds"] = {s: child["conds"][s] for s in keep}
    if not child["conds"]:                      # never breed the empty genome
        slot = rng.choice(sorted(set(a["conds"]) | set(b["conds"])))
        child["conds"][slot] = rng.choice(SLOTS[slot])
    return child


def _mutate(g, rng, tf):
    """One of: add a condition, drop one, swap one's option, or nudge geometry.
    Geometry nudges step to a NEIGHBOURING k/R rather than jumping at random —
    a real edge is a green neighbourhood, so local steps are the useful move."""
    g = {"direction": g["direction"], "conds": dict(g["conds"]),
         "k": g["k"], "rr": g["rr"]}
    slots = [s for s in SLOTS if not (tf == "1d" and s == "hours")]
    free = [s for s in slots if s not in g["conds"]]
    kinds = ["geometry", "option", "direction"]
    if free and len(g["conds"]) < MAX_CONDS:
        kinds.append("add")
    if len(g["conds"]) > 1:
        kinds.append("drop")

    kind = rng.choice(kinds)
    if kind == "add":
        s = rng.choice(free)
        g["conds"][s] = rng.choice(SLOTS[s])
    elif kind == "drop":
        del g["conds"][rng.choice(sorted(g["conds"]))]
    elif kind == "option":
        s = rng.choice(sorted(g["conds"]))
        g["conds"][s] = rng.choice(SLOTS[s])
    elif kind == "direction":
        g["direction"] = "short" if g["direction"] == "long" else "long"
    else:
        for gene, grid in (("k", GEO_K), ("rr", GEO_R)):
            if rng.random() < 0.5:
                i = grid.index(g[gene])
                g[gene] = grid[max(0, min(len(grid) - 1,
                                          i + rng.choice([-1, 1])))]
    return g


# --------------------------------------------------------------------------
# fitness

def _score(trades, capital=CAPITAL):
    """Drawdown-penalised expectancy in R over one slice of trades.

    Both terms are in R so the ratio is unit-free and comparable across
    geometries — the whole reason risk-normalized sizing exists upstream."""
    n = len(trades)
    if n == 0:
        return None
    risk = RISK["risk_pct"]
    exp_r = sum(t["pnl_pct"] for t in trades) / n / risk
    peak, maxdd = trades[0]["equity"], 0.0
    for t in trades:
        peak = max(peak, t["equity"])
        maxdd = max(maxdd, (peak - t["equity"]) / peak)
    dd_r = maxdd * 100 / risk
    # ponytail: floor the denominator at 1R. Without it a genome with a
    # 0.1R drawdown scores 10× on noise; 1R is "one losing trade", the
    # smallest drawdown that means anything.
    return {"n": n, "exp_r": round(exp_r, 4),
            "dd_r": round(dd_r, 2),
            "score": round(exp_r / max(dd_r, 1.0), 5)}


def _fitness(genome, ctx):
    """min(train, holdout) — the anti-overfit clamp. See module docstring."""
    df, masks, nb, mid = ctx["df"], ctx["masks"], ctx["nb"], ctx["mid"]
    mask = _combo_mask(masks, nb, genome["conds"])
    if mask.sum() < MIN_N:
        return {"fitness": -9e9, "reason": "too few signals"}
    res = _run_backtest(df, _sig_fn(mask, genome["direction"]),
                        _geo(genome["k"], genome["rr"]), CAPITAL)
    tr = res["trades"]
    train = _score([t for t in tr if t["entry_ts"] < mid])
    hold = _score([t for t in tr if t["entry_ts"] >= mid])
    if not train or not hold:
        return {"fitness": -9e9, "reason": "no trades in a half"}
    if hold["n"] < MIN_N:
        return {"fitness": -9e9, "reason": f"holdout n={hold['n']} < {MIN_N}",
                "train": train, "holdout": hold}
    return {"fitness": min(train["score"], hold["score"]),
            "train": train, "holdout": hold,
            "n": len(tr),
            "net_pct": round(res["final_equity"] / CAPITAL * 100 - 100, 1)}


# --------------------------------------------------------------------------
# the loop

def _select(pop, rng):
    """Tournament — cheap, and it keeps some diversity that pure truncation
    selection would strip out by generation three."""
    return max(rng.sample(pop, TOURNAMENT), key=lambda p: p["ev"]["fitness"])


def evolve(tf, generations=GENERATIONS, pop_size=POP, seed=0, verbose=True,
           window=DEFAULT_WINDOW):
    rng = random.Random(seed)
    w = WINDOWS[window]
    df = _load(tf, w["months"], exchange=w["exchange"])
    ctx = {"df": df, "masks": _masks(df), "nb": len(df),
           "mid": df.index[len(df) // 2].isoformat()}
    cache, t0 = {}, time.time()

    def ev(g):
        k = _key(g)
        if k not in cache:
            cache[k] = _fitness(g, ctx)
        return cache[k]

    pop = []
    while len(pop) < pop_size:
        g = _random_genome(rng, tf)
        pop.append({"g": g, "ev": ev(g)})

    history = []
    for gen in range(1, generations + 1):
        pop.sort(key=lambda p: p["ev"]["fitness"], reverse=True)
        best = pop[0]
        alive = sum(1 for p in pop if p["ev"]["fitness"] > -9e8)
        history.append({"gen": gen, "best": best["ev"]["fitness"],
                        "viable": alive, "evaluated": len(cache)})
        if verbose:
            print(f"[{tf}] gen {gen:>3} · best {best['ev']['fitness']:>8.5f} "
                  f"· viable {alive:>3}/{pop_size} · cache {len(cache):>5} "
                  f"· {time.time()-t0:.0f}s", flush=True)

        nxt = pop[:ELITE]
        while len(nxt) < pop_size:
            a, b = _select(pop, rng), _select(pop, rng)
            child = _crossover(a["g"], b["g"], rng) if rng.random() < P_CROSSOVER \
                else dict(a["g"], conds=dict(a["g"]["conds"]))
            if rng.random() < P_MUTATE:
                child = _mutate(child, rng, tf)
            nxt.append({"g": child, "ev": ev(child)})
        pop = nxt

    pop.sort(key=lambda p: p["ev"]["fitness"], reverse=True)
    return pop, history, cache


def _row(p, tf):
    g, e = p["g"], p["ev"]
    return {
        "tf": tf, "direction": g["direction"], "k": g["k"], "rr": g["rr"],
        "conditions": len(g["conds"]),
        "params": {**combo_params(g["direction"], g["conds"], tf),
                   "atr_stop_mult": g["k"], "rr": g["rr"]},
        "desc": f"{_describe(g['direction'], g['conds'], tf)} · "
                f"{g['k']}×ATR stop · {g['rr']}R",
        "fitness": e["fitness"], "n": e.get("n"),
        "net_pct": e.get("net_pct"),
        "train": e.get("train"), "holdout": e.get("holdout"),
    }


def run(timeframes=("1h", "4h", "1d"), generations=GENERATIONS,
        pop_size=POP, seed=0, window=DEFAULT_WINDOW, out=BREEDER_JSON):
    w = WINDOWS[window]
    t0, out_rows, hist = time.time(), [], {}
    print(f"breeder: pop {pop_size} × {generations} gens × {list(timeframes)} "
          f"· ≤{MAX_CONDS} conditions · fitness = min(train, holdout) of "
          f"expectancy-R / drawdown-R · holdout n ≥ {MIN_N}", flush=True)
    print(f"window: {window} — {w['months']} months, {w['desc']}", flush=True)

    for tf in timeframes:
        pop, history, cache = evolve(tf, generations, pop_size, seed, window=window)
        hist[tf] = history
        seen = set()
        for p in pop:
            if p["ev"]["fitness"] <= -9e8:
                continue
            k = _key(p["g"])
            if k in seen:
                continue
            seen.add(k)
            out_rows.append(_row(p, tf))

    out_rows.sort(key=lambda r: r["fitness"], reverse=True)
    result = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        # Window is recorded because the two are different instruments, not just
        # different lengths — without this the two output files are
        # indistinguishable and silently non-comparable.
        "window": window, "months": w["months"], "data": w["desc"],
        "capital": CAPITAL, "risk": RISK,
        "max_conditions": MAX_CONDS, "min_n_holdout": MIN_N,
        "population": pop_size, "generations": generations, "seed": seed,
        "fitness": "min(train, holdout) of expectancy_R / max(drawdown_R, 1)",
        "history": hist,
        "n_viable": len(out_rows),
        "genomes": out_rows[:200],
    }
    with open(out, "w") as f:
        json.dump(result, f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))

    print(f"\n=== DONE in {time.time()-t0:.0f}s — {len(out_rows)} viable "
          f"genomes (holdout n ≥ {MIN_N}, both halves scored) ===")
    if not out_rows:
        print("No genome survived out-of-sample. That is a result, not a bug — "
              "the fitness clamp is doing its job.")
        return result
    print(f"{'fit':>9} {'trainR':>7} {'holdR':>7} {'n':>5} {'net%':>7} "
          f"{'cond':>4}  desc")
    for r in out_rows[:25]:
        print(f"{r['fitness']:>9.5f} {r['train']['exp_r']:>7} "
              f"{r['holdout']['exp_r']:>7} {r['n']:>5} {r['net_pct']:>7} "
              f"{r['conditions']:>4}  {r['desc']}")
    deep = [r for r in out_rows if r["conditions"] > 3]
    print(f"\n{len(deep)} of {len(out_rows)} viable genomes use >3 conditions "
          f"— the region grid search could not reach → {out}")
    print(f"(w30 baseline for this line was 1 of 103. If this window did not "
          f"move it, depth is not a data problem after all.)")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", nargs="*", default=["1h", "4h", "1d"])
    ap.add_argument("--generations", type=int, default=GENERATIONS)
    ap.add_argument("--pop", type=int, default=POP)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--window", choices=sorted(WINDOWS), default=DEFAULT_WINDOW,
                    help="deep = 84mo Binance spot (default); w30 = 30mo Bybit perp")
    ap.add_argument("--out", default=None,
                    help="output json (defaults to strategy_breeder[_w30].json)")
    a = ap.parse_args()
    out = a.out or ("strategy_breeder.json" if a.window == "deep"
                    else f"strategy_breeder_{a.window}.json")
    run(tuple(a.tf), a.generations, a.pop, a.seed, window=a.window, out=out)
