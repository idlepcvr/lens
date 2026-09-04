"""LENS — Market Regime.

Ported from PRISM's quant.py: classify each BTC day into BULL / SIDEWAYS / BEAR
with K-Means(k=3) on (14d rolling return, 14d rolling vol) — pure Python, no
sklearn. Daily OHLCV from Bybit public API.

Was labelled a PROP analytic: a hero_by_regime() layer on top bucketed the
prop hero strategy's historical trades by regime → win-rate per regime,
answering "is right now a regime where ASIAN_RSI_DIP_v1 actually wins?" That
layer imported app.prop_eval, so it went with the 2026-09-05 hedge/prop split
— prop_eval.py is deleted and there's no hedge equivalent of a single "hero"
strategy to bucket (hedge trades are discretionary, not one coded strategy).
detect_regimes() itself was always book-agnostic BTC classification and stays.
"""

import math
import random
import statistics
import time
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


def _transition_stats(history: list[dict]) -> dict:
    """The Markov slice: P(next regime | current regime) from the ordered daily
    labels, how sticky each regime is, avg run length, and the current unbroken
    run. Pure counts off data detect_regimes already produces — no dependency."""
    names = ("BULL", "SIDEWAYS", "BEAR")
    idx = {n: i for i, n in enumerate(names)}
    counts = [[0, 0, 0] for _ in range(3)]
    seq = [h["regime"] for h in history if h["regime"] in idx]
    for a, b in zip(seq, seq[1:]):
        counts[idx[a]][idx[b]] += 1

    matrix, persistence = {}, {}
    for n in names:
        row = counts[idx[n]]
        tot = sum(row)
        matrix[n] = {names[j]: (round(row[j] / tot, 3) if tot else None) for j in range(3)}
        persistence[n] = round(row[idx[n]] / tot, 3) if tot else None

    runs = {n: [] for n in names}
    if seq:
        cur, length = seq[0], 1
        for r in seq[1:]:
            if r == cur:
                length += 1
            else:
                runs[cur].append(length)
                cur, length = r, 1
        runs[cur].append(length)
    avg_run = {n: (round(sum(v) / len(v), 1) if v else None) for n, v in runs.items()}

    current_run = 0
    if seq:
        last = seq[-1]
        for r in reversed(seq):
            if r != last:
                break
            current_run += 1

    return {"matrix": matrix, "persistence": persistence,
            "avg_run_days": avg_run, "current_run_days": current_run}


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
        "transitions": _transition_stats(history),
        "by_date": by_date,
    }


_PAYLOAD_TTL_S = 300
_payload_cache: tuple[float, dict] | None = None


def regime_payload() -> dict:
    """Everything the /regime page + API needs in one call.

    Cached for 5 minutes, not for the life of the process: unlike the backtest
    caches, this one reads LIVE market state, so freezing it until restart would
    make the page lie. Five minutes is safe because the classification runs a
    14-day window over DAILY candles — it cannot meaningfully move inside one.

    Without this, every hit re-fetched 1000 daily candles from Bybit and re-ran
    a 5-restart k-means over them in pure Python (~0.9s), to reach the same
    answer it reached a second ago. ponytail: a dict and a timestamp; if this
    ever needs to be shared across processes, that's when it earns a real cache.
    """
    global _payload_cache
    now = time.time()
    if _payload_cache and now - _payload_cache[0] < _PAYLOAD_TTL_S:
        return _payload_cache[1]

    reg = detect_regimes()
    reg.pop("by_date", None)   # internal only — don't ship the full map
    _payload_cache = (now, reg)
    return reg
