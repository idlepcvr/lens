"""Is the non-VETO short edge real, or a lucky partition?

short_edge.py established that non-VETO shorts clear four gates. All four share
a weakness: they take the non-VETO label as given. If you slice 91 trades out of
293 by ANY rule and the slice looks good, significance tests on the slice will
happily agree — the label was chosen partly because it looked good, and none of
the earlier gates can see that.

Three tests that can:

  1. LABEL PERMUTATION — shuffle the VETO/non-VETO labels across shorts a few
     thousand times, keeping the group sizes fixed, and ask how often chance
     alone splits the book this well. This is the direct test of "is the filter
     selecting, or did we find a good-looking subset?" It mirrors the method
     /robustness already uses on the discipline rules.

  2. SPLIT-POINT SWEEP — "positive in both halves" is one arbitrary cut. Sweep
     the split from 30% to 70% of the book and check whether both sides stay
     positive everywhere, or only at the 50% that happened to be reported.

  3. LEAVE-ONE-MONTH-OUT — drop each calendar month in turn and refit. If one
     month carries the whole result, that shows up as a collapse when it goes.

None of these can rescue the sample from being his own selection. They only
establish whether, within that sample, the filter is doing work.

    python3 research/short_robustness.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/research/", 1)[0])

from app.geometry import FRICTION_PCT, solve                     # noqa: E402
from app.paths import RESULTS                                    # noqa: E402
from research.entry_edge import load_bars, load_trades           # noqa: E402

N_PERM = 5000
SEED = 42


def outcomes(bars, ts_index, trades, sl, tp):
    """[(ts, is_win, is_non_veto)] — resolve each short once, then reuse."""
    import bisect
    out = []
    for t, d, entry, tag in trades:
        i = bisect.bisect_left(ts_index, t)
        if i >= len(bars) - 1:
            continue
        tpp, slp = entry * (1 - tp / 100), entry * (1 + sl / 100)   # short
        res = None
        for j in range(i, min(i + 24 * 60, len(bars))):
            _, hi, lo, _c = bars[j]
            if hi >= slp:
                res = False; break
            if lo <= tpp:
                res = True; break
        if res is not None:
            out.append((t, res, not str(tag).startswith("VETO")))
    return out


def net_of(rows, sl, tp, f=FRICTION_PCT):
    if not rows:
        return None, None
    w = sum(1 for r in rows if r[1]) / len(rows)
    return w, w * (tp - f) - (1 - w) * (sl + f)


def main() -> None:
    random.seed(SEED)
    bars = load_bars()
    ts_index = [b[0] for b in bars]
    trades = sorted(load_trades(), key=lambda t: t[0])
    sigma = json.load(open(RESULTS / "barrier_baseline.json"))["sigma"]
    g = solve(sigma, 2.5, 1.0)
    sl, tp = g["stop_pct"], g["target_pct"]

    shorts = [t for t in trades if t[1] == "short"]
    rows = outcomes(bars, ts_index, shorts, sl, tp)
    nv = [r for r in rows if r[2]]
    v = [r for r in rows if not r[2]]
    w_nv, net_nv = net_of(nv, sl, tp)
    w_v, net_v = net_of(v, sl, tp)
    observed = w_nv - w_v

    print(f"shorts resolved: {len(rows)}  ·  non-VETO {len(nv)}  VETO {len(v)}")
    print(f"  non-VETO {w_nv:.1%} (net {net_nv:+.3f}%) · VETO {w_v:.1%} "
          f"(net {net_v:+.3f}%) · gap {observed*100:+.1f}pp\n")

    # ── 1. label permutation ────────────────────────────────────────────────
    k = len(nv)
    flags = [r[1] for r in rows]
    ge = 0
    gaps = []
    for _ in range(N_PERM):
        random.shuffle(flags)
        a = flags[:k]
        b = flags[k:]
        gap = (sum(a) / len(a)) - (sum(b) / len(b))
        gaps.append(gap)
        if gap >= observed:
            ge += 1
    p = ge / N_PERM
    print(f"1. LABEL PERMUTATION ({N_PERM:,} shuffles, group sizes held)")
    print(f"   observed gap {observed*100:+.1f}pp · random gaps "
          f"mean {statistics.mean(gaps)*100:+.1f}pp sd {statistics.pstdev(gaps)*100:.1f}pp")
    print(f"   p = {p:.4f}  →  {'REAL — the filter is selecting' if p < 0.05 else 'NOT DISTINGUISHABLE from a lucky partition'}\n")

    # ── 2. split-point sweep ────────────────────────────────────────────────
    print("2. SPLIT-POINT SWEEP (non-VETO shorts, both sides must be positive)")
    nv_sorted = sorted(nv, key=lambda r: r[0])
    ok = bad = 0
    worst = None
    for frac in [x / 100 for x in range(30, 71, 5)]:
        c = int(len(nv_sorted) * frac)
        _, n1 = net_of(nv_sorted[:c], sl, tp)
        _, n2 = net_of(nv_sorted[c:], sl, tp)
        good = n1 is not None and n2 is not None and n1 > 0 and n2 > 0
        ok, bad = ok + good, bad + (not good)
        if worst is None or min(n1, n2) < worst[1]:
            worst = (frac, min(n1, n2))
        print(f"   split {frac:.0%}: early {n1:+.3f}%  late {n2:+.3f}%  "
              f"{'✓' if good else '✗'}")
    print(f"   → {ok}/{ok+bad} split points positive on both sides "
          f"(worst side {worst[1]:+.3f}% at {worst[0]:.0%})\n")

    # ── 3. leave-one-month-out ──────────────────────────────────────────────
    print("3. LEAVE-ONE-MONTH-OUT (non-VETO shorts)")
    by_month = defaultdict(list)
    for r in nv:
        m = datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_month[m].append(r)
    drops = []
    for m in sorted(by_month):
        rest = [r for r in nv if r not in by_month[m]]
        w2, n2 = net_of(rest, sl, tp)
        drops.append((m, len(by_month[m]), w2, n2))
    for m, cnt, w2, n2 in drops:
        flag = "  ← carries it" if n2 is not None and n2 <= 0 else ""
        print(f"   drop {m} (n={cnt:>2}): rest WR {w2:.1%} net {n2:+.3f}%{flag}")
    still = sum(1 for _, _, _, n2 in drops if n2 and n2 > 0)
    print(f"   → {still}/{len(drops)} months can be removed and the edge survives\n")

    verdict = (p < 0.05) and bad == 0 and still == len(drops)
    print("VERDICT: " + ("robust on all three" if verdict else
                         "NOT fully robust — see failures above"))

    with open(RESULTS / "short_robustness.json", "w") as fh:
        json.dump({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                   "n_shorts": len(rows), "n_non_veto": len(nv),
                   "gap_pp": observed * 100, "perm_p": p, "perm_n": N_PERM,
                   "splits_ok": ok, "splits_total": ok + bad,
                   "months_survived": still, "months_total": len(drops),
                   "wr_non_veto": w_nv, "net_non_veto": net_nv,
                   "robust": verdict}, fh, indent=2)
    print(f"→ wrote {RESULTS / 'short_robustness.json'}")


if __name__ == "__main__":
    main()
