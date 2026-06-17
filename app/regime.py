"""LENS — Market Regime (PROP analytic).

Ported from PRISM's quant.py: classify each BTC day into BULL / SIDEWAYS / BEAR
with K-Means(k=3) on (14d rolling return, 14d rolling vol) — pure Python, no
sklearn. Daily OHLCV from Bybit public API.

The PROP-specific layer on top: bucket the hero strategy's historical trades by
the regime on their entry day → win-rate per regime. Answers the real question
for the eval — "is right now a regime where ASIAN_RSI_DIP_v1 actually wins?"
"""

import math
import random
import statistics
from datetime import datetime, timezone

import requests

_BYBIT_KLINE = "https://api.bybit.com/v5/market/kline"


def _fetch_ohlcv(symbol: str = "BTCUSD", interval: str = "D", limit: int = 1000) -> list[dict]:
    """Daily OHLCV from Bybit public kline API, oldest → newest."""
    try:
        resp = requests.get(
            _BYBIT_KLINE,
            params={"category": "inverse", "symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        rows = (resp.json().get("result") or {}).get("list") or []
        candles = []
        for r in rows:
            try:
                candles.append({"ts": int(r[0]), "close": float(r[4])})
            except (IndexError, ValueError):
                continue
        candles.sort(key=lambda x: x["ts"])   # Bybit returns newest-first
        return candles
    except Exception:
        return []


def _compute_features(candles: list[dict], window: int = 14) -> list[dict]:
    closes = [c["close"] for c in candles]
    daily_rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    features = []
    for i in range(window, len(candles)):
        window_rets = daily_rets[i - window: i]
        ret14 = (closes[i] - closes[i - window]) / closes[i - window]
        vol14 = statistics.pstdev(window_rets) if len(window_rets) >= 2 else 0.0
        dt = datetime.fromtimestamp(candles[i]["ts"] // 1000, tz=timezone.utc)
        features.append({"date": dt.strftime("%Y-%m-%d"), "close": closes[i],
                         "ret14": ret14, "vol14": vol14})
    return features


def _dist(a: tuple, b: tuple) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _kmeans(points: list[tuple], k: int = 3, iters: int = 40) -> list[int]:
    """Lloyd's K-Means++ on 2D normalised points."""
    if len(points) < k:
        return [0] * len(points)
    centroids = [random.choice(points)]
    for _ in range(k - 1):
        dists = [min(_dist(p, c) ** 2 for c in centroids) for p in points]
        total = sum(dists)
        r, cumul = random.random() * total, 0.0
        for p, d in zip(points, dists):
            cumul += d
            if cumul >= r:
                centroids.append(p)
                break
        else:
            centroids.append(points[-1])
    labels = [0] * len(points)
    for _ in range(iters):
        new_labels = [min(range(k), key=lambda j: _dist(p, centroids[j])) for p in points]
        if new_labels == labels:
            break
        labels = new_labels
        for j in range(k):
            cluster = [points[i] for i, lbl in enumerate(labels) if lbl == j]
            if cluster:
                centroids[j] = tuple(sum(p[d] for p in cluster) / len(cluster) for d in range(2))
    return labels


def detect_regimes(limit: int = 1000) -> dict:
    """Classify the full daily window into BULL/SIDEWAYS/BEAR.
    Returns current regime, 60d history, per-regime stats, and a full
    date→regime map (used to bucket the hero's trades)."""
    random.seed(42)   # determinism across requests
    candles = _fetch_ohlcv(limit=limit)
    if len(candles) < 20:
        return {"current_regime": "UNKNOWN", "history": [], "regime_stats": {}, "by_date": {}}
    features = _compute_features(candles, window=14)
    if not features:
        return {"current_regime": "UNKNOWN", "history": [], "regime_stats": {}, "by_date": {}}

    rets = [f["ret14"] for f in features]
    vols = [f["vol14"] for f in features]
    ret_mu, ret_sd = statistics.mean(rets), statistics.pstdev(rets) or 1.0
    vol_mu, vol_sd = statistics.mean(vols), statistics.pstdev(vols) or 1.0
    points = [((f["ret14"] - ret_mu) / ret_sd, (f["vol14"] - vol_mu) / vol_sd) for f in features]

    best_labels, best_inertia = None, float("inf")
    for _ in range(5):
        labels = _kmeans(points, k=3, iters=40)
        centroids = []
        for j in range(3):
            cluster = [points[i] for i, lbl in enumerate(labels) if lbl == j]
            centroids.append(tuple(sum(p[d] for p in cluster) / len(cluster) for d in range(2))
                             if cluster else (0.0, 0.0))
        inertia = sum(_dist(points[i], centroids[labels[i]]) ** 2 for i in range(len(points)))
        if inertia < best_inertia:
            best_inertia, best_labels = inertia, labels
    labels = best_labels

    cluster_mean_ret = {
        j: (statistics.mean([points[i][0] for i, lbl in enumerate(labels) if lbl == j]) or 0.0)
        for j in range(3)
    }
    order = sorted(cluster_mean_ret, key=lambda j: cluster_mean_ret[j])
    cluster_name = {order[0]: "BEAR", order[1]: "SIDEWAYS", order[2]: "BULL"}

    history = [
        {"date": f["date"], "close": round(f["close"], 2), "regime": cluster_name[labels[i]],
         "ret14_pct": round(f["ret14"] * 100, 2), "vol14_pct": round(f["vol14"] * 100, 4)}
        for i, f in enumerate(features)
    ]
    by_date = {h["date"]: h["regime"] for h in history}

    regime_stats = {}
    for rname in ("BULL", "SIDEWAYS", "BEAR"):
        days = [h for h in history if h["regime"] == rname]
        regime_stats[rname] = {
            "count": len(days),
            "avg_ret14_pct": round(statistics.mean([d["ret14_pct"] for d in days]), 2) if days else 0,
            "avg_vol14_pct": round(statistics.mean([d["vol14_pct"] for d in days]), 4) if days else 0,
        }

    last = history[-1] if history else {}
    return {
        "current_regime": last.get("regime", "UNKNOWN"),
        "current_ret14_pct": last.get("ret14_pct", 0.0),
        "current_vol14_pct": last.get("vol14_pct", 0.0),
        "current_date": last.get("date", ""),
        "history": history[-60:],
        "regime_stats": regime_stats,
        "by_date": by_date,
    }


def hero_by_regime(by_date: dict, strategy: str = "ASIAN_RSI_DIP_v1",
                   eval_name: str = "BREAKOUT_1STEP_TURBO", months: int = 30) -> dict:
    """Bucket the hero strategy's historical trades by the regime on their entry
    day. Win/loss is the sign of pnl_pct (sizing-independent). Returns per-regime
    {n, wins, wr_pct}. This is the prop-relevant tailoring of the regime view."""
    # Imported here to avoid a circular import at module load.
    from app.prop_eval import _trade_log, EVALS
    from app.backtest_engine import load_ohlcv, add_indicators, STRATEGIES

    out = {r: {"n": 0, "wins": 0, "wr_pct": None} for r in ("BULL", "SIDEWAYS", "BEAR")}
    if strategy not in STRATEGIES or eval_name not in EVALS or not by_date:
        return out
    strat = STRATEGIES[strategy]
    tf = strat.get("timeframe", "4h")
    try:
        df = add_indicators(load_ohlcv(months=months, timeframe=tf))
        trades = _trade_log(df, strat["signal_fn"], strat["params"], EVALS[eval_name], 0.5)
    except Exception:
        return out
    for t in trades:
        d = t["eval_day"].strftime("%Y-%m-%d")
        reg = by_date.get(d)
        if reg in out:
            out[reg]["n"] += 1
            if t["pnl_pct"] > 0:
                out[reg]["wins"] += 1
    for r, v in out.items():
        if v["n"]:
            v["wr_pct"] = round(100 * v["wins"] / v["n"], 1)
    return out


def regime_payload() -> dict:
    """Everything the /regime page + API needs in one call."""
    reg = detect_regimes()
    reg["hero_by_regime"] = hero_by_regime(reg.get("by_date", {}))
    reg.pop("by_date", None)   # internal only — don't ship the full map
    return reg
