"""Correlation dedup — how many IDEAS are in the 933 survivors, really?

`strategy_search3` reported 933 split-half survivors, 402 of which beat their
random-entry baseline. That count is label variety, not idea variety: a combo
and the same combo plus one near-redundant condition are two rows in the JSON
and one idea in the market. A vault full of near-duplicates lies about its own
diversity — and it is the space a genetic breeder would search next, so its
real width matters before anyone builds the breeder.

Method: re-run each survivor at its own (tf, k, R) and compare what it actually
selected and traded on the chart — never its condition names.

**Why not correlation of daily returns.** That was the first cut (Algory's
"correlation from actual equity curves") and it is the wrong instrument for
THIS vault, measured: these survivors trade a median of 59 days out of 770, and
the median pair shares **one** active day. With near-disjoint supports, Pearson
on daily pnl is dominated by mutual zeros, so it reported 402 labels → 325
"ideas" — an artifact of sparsity, not a finding. Correlating *cumulative*
equity instead would be worse: every curve inherits BTC's uptrend and everything
correlates with everything.

**Why not overlap of realized trades either.** Second cut, also measured, also
rejected: two survivors with *identical entry conditions* differing only 3.0R
vs 5.0R share just 0.38 of their realized trades. Nothing about the idea
changed — a different take-profit exits at a different bar, so a different set
of later signals is blocked by an already-open position. Realized-trade overlap
measures that scheduling side-effect, not whether two labels are the same idea.

So the primary metric is **Jaccard overlap of the entry masks**: the set of
(bar hour, direction) the conditions select, before geometry or position
state touches anything. Two labels that are one redundant condition apart
select nearly the same bars and score ~1.0; genuinely different ideas score ~0.
Both rejected metrics are still computed and reported per cluster — realized
trade overlap and daily correlation — because the gap between them and the mask
overlap is itself the finding.

ponytail: mask overlap under-merges in one known case — two condition sets can
select different bars yet trade identically, when the extra bars all land while
a position is already open (clusters 16/17 of the 402 run: same n, PF, net and
drawdown to the decimal, split apart). So this is an upper bound on the idea
count; realized-trade overlap is the lower. Both are reported. Reconciling them
needs a metric that intersects mask-with-position-state, which is a bigger build
than the answer justifies — the two bounds already agree on the conclusion.

The survivors JSON stores summary stats and a geometry matrix but no trades,
so the re-run is unavoidable; masks and OHLCV are loaded once per timeframe.

Results → strategy_clusters_<scope>.json. Run from repo root (needs .venv):
    .venv/bin/python -m app.strategy_dedup          # the 402 baseline-beaters
    .venv/bin/python -m app.strategy_dedup --all    # all 933 split-half survivors
"""

import json
import sys
import time
from collections import defaultdict

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from .backtest_engine import _run_backtest
from .strategy_search import CAPITAL, MONTHS, SLOTS, _combo_mask, _masks, _sig_fn
from .strategy_search3 import _geo, _load
from .paths import SEARCH_JSON, clusters_json

THRESHOLD = 0.9    # mask overlap ≥ this ⇒ same idea. See _cluster().


def _active(params: dict) -> dict:
    """Inverse of `combo_params` — the params dict back to the {slot: option}
    the mask builder wants. Geometry and direction/timeframe are not slots."""
    active = {}
    for slot in SLOTS:
        if slot == "rsi":
            for field in ("rsi_max", "rsi_min"):
                if field in params:
                    active["rsi"] = (field, params[field])
        elif slot == "hours":
            if "hour_from" in params:
                active["hours"] = (params["hour_from"], params["hour_to"])
        elif slot == "vol":
            if params.get("vol_spike"):
                active["vol"] = True
        elif slot == "atr":
            if "atr_regime" in params:
                active["atr"] = params["atr_regime"]
        elif slot in params:
            active[slot] = params[slot]
    return active


def _replay(survivors):
    """Re-run every survivor; keep what it traded.

    Three views per survivor: the set of (bar hour, direction) its conditions
    SELECT — the clustering metric — the set it actually TRADED, and a daily
    pnl_pct series. The last two are reported, not clustered on. Bars bucket to
    the hour so a 1h and a 4h survivor firing on the same bar are seen to agree;
    daily is the coarsest of the three timeframes and the only bucket all of
    them can share without upsampling 1d bars into fiction."""
    curves, t0 = [], time.time()
    by_tf = defaultdict(list)
    for i, s in enumerate(survivors):
        by_tf[s["tf"]].append(i)

    for tf, idxs in by_tf.items():
        df = _load(tf, MONTHS)
        masks, nb = _masks(df), len(df)
        print(f"[{tf}] {nb} bars · re-running {len(idxs)} survivors", flush=True)
        for j, i in enumerate(idxs):
            s = survivors[i]
            mask = _combo_mask(masks, nb, _active(s["params"]))
            selected = {(ts.isoformat()[:13], s["direction"])
                        for ts in df.index[mask]}
            res = _run_backtest(df, _sig_fn(mask, s["direction"]),
                                _geo(s["k"], s["rr"]), CAPITAL)
            daily = defaultdict(float)
            traded = set()
            for t in res["trades"]:
                daily[t["entry_ts"][:10]] += t["pnl_pct"]
                traded.add((t["entry_ts"][:13], s["direction"]))
            curves.append((i, dict(daily), selected, traded, len(res["trades"])))
            if j % 100 == 0:
                print(f"[{tf}] {j}/{len(idxs)} · {time.time()-t0:.0f}s", flush=True)
    return curves


def _matrix(curves):
    days = sorted({d for _i, c, _s, _t, _n in curves for d in c})
    col = {d: k for k, d in enumerate(days)}
    m = np.zeros((len(curves), len(days)))
    for row, (_i, c, _s, _t, _n) in enumerate(curves):
        for d, v in c.items():
            m[row, col[d]] = v
    return m, days


def _jaccard(entry_sets):
    """|A∩B| / |A∪B| over the (bar hour, direction) sets. A survivor with an
    empty set overlaps with nothing, including another empty one."""
    n = len(entry_sets)
    j = np.eye(n)
    for a in range(n):
        for b in range(a + 1, n):
            sa, sb = entry_sets[a], entry_sets[b]
            union = len(sa | sb)
            j[a, b] = j[b, a] = len(sa & sb) / union if union else 0.0
    return j


def _correlation(m):
    """Pearson on daily pnl — reported, not clustered on. See module docstring."""
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.nan_to_num(np.corrcoef(m), nan=0.0)
    np.fill_diagonal(corr, 1.0)
    return corr


def _cluster(sim, threshold=THRESHOLD):
    """Average-linkage on 1 − similarity.

    Average linkage, not single: single-linkage chains two unrelated genomes
    together through one intermediate that half-overlaps with both, which is
    exactly the near-duplicate structure being measured.
    ponytail: one threshold, no sweep — rerun with a different THRESHOLD if the
    cluster count looks implausible."""
    dist = np.clip(1.0 - sim, 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2                  # kill float asymmetry
    z = linkage(squareform(dist, checks=False), method="average")
    return fcluster(z, t=1.0 - threshold, criterion="distance")


def run(only_baseline_beaters=True):
    with open(SEARCH_JSON) as f:
        out = json.load(f)
    surv = out["survivors"]
    if only_baseline_beaters:
        surv = [s for s in surv if s.get("beats_baseline")]
    print(f"dedup: {len(surv)} survivors "
          f"({'baseline-beaters' if only_baseline_beaters else 'all split-half'})"
          f" · entry-mask overlap ≥ {THRESHOLD} ⇒ same idea", flush=True)

    curves = _replay(surv)
    order = [i for i, _c, _s, _t, _n in curves]
    m, days = _matrix(curves)
    sel = _jaccard([s for _i, _c, s, _t, _n in curves])   # the metric
    trd = _jaccard([t for _i, _c, _s, t, _n in curves])   # reported only
    corr = _correlation(m)                                # reported only
    labels = _cluster(sel)

    groups = defaultdict(list)
    for row, lab in enumerate(labels):
        groups[int(lab)].append(order[row])
    # survivors[] is already ranked, so the lowest index in a cluster is its best
    ranked = sorted(groups.values(), key=lambda idxs: min(idxs))

    row_of = {i: row for row, i in enumerate(order)}

    def _mean_pairwise(mat, idxs):
        rows = [row_of[i] for i in idxs]
        pairs = [mat[a, b] for a in rows for b in rows if a < b]
        return round(float(np.mean(pairs)), 3) if pairs else None

    clusters = []
    for rank, idxs in enumerate(ranked, 1):
        rep = surv[min(idxs)]
        clusters.append({
            "cluster": rank, "size": len(idxs),
            "representative": rep["desc"],
            "rep_net_pct": rep["net_pct"], "rep_n": rep["n"],
            "rep_pf": rep["pf"], "rep_max_dd": rep["max_dd"],
            "mean_mask_overlap": _mean_pairwise(sel, idxs),
            "mean_trade_overlap": _mean_pairwise(trd, idxs),
            "mean_daily_corr": _mean_pairwise(corr, idxs),
            "members": [surv[i]["desc"] for i in sorted(idxs)],
        })

    iu = np.triu_indices(len(surv), 1)
    result = {
        "ran_at": out["ran_at"], "source": "strategy_search.json",
        "scope": "beats_baseline" if only_baseline_beaters else "split_half",
        "metric": "jaccard(entry_mask_hour, direction)", "threshold": THRESHOLD,
        "days": len(days),
        "median_active_days": float(np.median((m != 0).sum(1))),
        "median_pair_mask_overlap": round(float(np.median(sel[iu])), 3),
        "median_pair_trade_overlap": round(float(np.median(trd[iu])), 3),
        "median_pair_daily_corr": round(float(np.median(corr[iu])), 3),
        "labels_in": len(surv), "ideas_out": len(clusters),
        "clusters": clusters,
    }
    out_path = clusters_json(result["scope"])
    with open(out_path, "w") as f:
        json.dump(result, f, indent=1)

    print(f"\n=== {len(surv)} labels → {len(clusters)} ideas "
          f"at entry-mask overlap ≥ {THRESHOLD} ===")
    print(f"{'#':>4} {'size':>5} {'net%':>7} {'PF':>5} {'n':>5} {'DD':>5} "
          f"{'mask':>5} {'trade':>5} {'corr':>5}  representative")
    for c in clusters[:30]:
        d = "—"
        print(f"{c['cluster']:>4} {c['size']:>5} {c['rep_net_pct']:>7} "
              f"{c['rep_pf']:>5} {c['rep_n']:>5} {c['rep_max_dd']:>5} "
              f"{c['mean_mask_overlap'] if c['size'] > 1 else d:>5} "
              f"{c['mean_trade_overlap'] if c['size'] > 1 else d:>5} "
              f"{c['mean_daily_corr'] if c['size'] > 1 else d:>5}  "
              f"{c['representative']}")
    sizes = [c["size"] for c in clusters]
    print(f"\n{sizes.count(1)} clusters of one · largest cluster {max(sizes)} "
          f"labels · median pair: mask {result['median_pair_mask_overlap']} · "
          f"trades {result['median_pair_trade_overlap']} · "
          f"daily corr {result['median_pair_daily_corr']} "
          f"→ {out_path}")


if __name__ == "__main__":
    run(only_baseline_beaters="--all" not in sys.argv)
