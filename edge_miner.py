"""One-off research: fingerprint the successful trades.

Enriches every closed real trade with entry-context features (more than
trade_review.py: session, weekday, EMA slope, distance from 4H EMA, ATR
regime, bar streak), then mines 1–3 condition combos ranked by win rate
and expectancy. Output = candidate setups for LENS_EDGE_v2.
Not wired into the app — pure analysis. Run: python3 edge_miner.py
"""
import itertools
from collections import defaultdict

from trade_review import load_data, enrich, compute_ema, parse_ts, bar_idx

MIN_N = 20          # min trades for a rule to count
MAX_CONDS = 3       # max conditions per rule
TOP = 25            # rules to print per board

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def session_of(hour):
    if hour < 8:
        return "asia"
    if hour < 13:
        return "london"
    if hour < 21:
        return "ny"
    return "late"


def compute_atr(c1h, period=14):
    """Wilder ATR on 1h candles → list aligned with c1h."""
    atr = [None] * len(c1h)
    trs = []
    for i in range(1, len(c1h)):
        _, _, hi, lo, cl, _ = c1h[i]
        prev_cl = c1h[i - 1][4]
        trs.append(max(hi - lo, abs(hi - prev_cl), abs(lo - prev_cl)))
        if i == period:
            atr[i] = sum(trs) / period
        elif i > period:
            atr[i] = (atr[i - 1] * (period - 1) + trs[-1]) / period
    return atr


def add_features(rows, trades_raw, c1h, c4h):
    """Extend enrich() output with extra entry-context features."""
    ts1h = [r[0] for r in c1h]
    open1h = [r[1] for r in c1h]
    clos1h = [r[4] for r in c1h]
    ema21_1h = compute_ema(clos1h, 21)
    atr = compute_atr(c1h)
    atr_pct_vals = sorted(
        a / c1h[i][4] for i, a in enumerate(atr) if a is not None
    )
    lo_cut = atr_pct_vals[len(atr_pct_vals) // 3]
    hi_cut = atr_pct_vals[2 * len(atr_pct_vals) // 3]

    ts4h = [r[0] for r in c4h]
    clos4h = [r[4] for r in c4h]
    ema21_4h = compute_ema(clos4h, 21)

    import datetime
    for row in rows:
        dt = datetime.datetime.fromtimestamp(
            row["ts_entry"], tz=datetime.timezone.utc
        )
        row["hour"] = dt.hour
        row["session"] = session_of(dt.hour)
        row["weekday"] = WEEKDAYS[dt.weekday()]
        row["hold_min"] = (row["ts_exit"] - row["ts_entry"]) // 60

        i1 = bar_idx(ts1h, row["ts_entry"] * 1000)
        i4 = bar_idx(ts4h, row["ts_entry"] * 1000)
        long_ = row["direction"] == "long"

        # 1h EMA21 slope over last 3 bars, aligned with trade direction
        row["slope_1h"] = None
        if i1 is not None and i1 >= 3 and ema21_1h[i1] and ema21_1h[i1 - 3]:
            rising = ema21_1h[i1] > ema21_1h[i1 - 3]
            row["slope_1h"] = "with" if rising == long_ else "against"

        # consecutive same-direction 1h bars before entry (0..3+)
        row["streak"] = None
        if i1 is not None and i1 >= 3:
            n = 0
            ref = clos1h[i1] >= open1h[i1]
            for k in range(i1, max(i1 - 3, 0), -1):
                if (clos1h[k] >= open1h[k]) == ref:
                    n += 1
                else:
                    break
            row["streak"] = min(n, 3)

        # ATR regime at entry
        row["vol"] = None
        if i1 is not None and atr[i1]:
            p = atr[i1] / clos1h[i1]
            row["vol"] = "low" if p < lo_cut else ("high" if p > hi_cut else "mid")

        # distance of price from 4H EMA21, signed toward trade direction
        row["ext_4h"] = None
        if i4 is not None and ema21_4h[i4] and row["entry"]:
            d = (row["entry"] - ema21_4h[i4]) / ema21_4h[i4] * 100
            if not long_:
                d = -d
            # extended = chasing (>1.5% past EMA in trade direction)
            row["ext_4h"] = "extended" if d > 1.5 else ("discount" if d < 0 else "near")

    return rows


# ── rule mining ───────────────────────────────────────────────────────────────

FEATURES = {
    "bar_aligned": [True, False],
    "trend_aligned": [True, False],
    "rsi_zone": ["dip", "neutral", "momentum"],
    "session": ["asia", "london", "ny", "late"],
    "weekday": WEEKDAYS,
    "direction": ["long", "short"],
    "slope_1h": ["with", "against"],
    "streak": [0, 1, 2, 3],
    "vol": ["low", "mid", "high"],
    "ext_4h": ["discount", "near", "extended"],
}


def stats(rows):
    n = len(rows)
    wins = [r for r in rows if (r["pnl"] or 0) > 0]
    pnl = sum(r["pnl"] or 0 for r in rows)
    weeks = (
        max(r["ts_entry"] for r in rows) - min(r["ts_entry"] for r in rows)
    ) / 604800 or 1
    return {
        "n": n,
        "wr": len(wins) / n * 100,
        "pnl": pnl,
        "exp": pnl / n,
        "tpw": n / max(weeks, 1),
    }


def fmt(rule, s):
    cond = " & ".join(f"{k}={v}" for k, v in rule)
    return (
        f"{s['wr']:5.1f}%  n={s['n']:<4} exp=€{s['exp']:+6.2f} "
        f"pnl=€{s['pnl']:+8.0f} tpw={s['tpw']:4.1f}  {cond}"
    )


def mine(rows):
    boards = {"wr": [], "exp": []}
    keys = list(FEATURES)
    for r in range(1, MAX_CONDS + 1):
        for combo in itertools.combinations(keys, r):
            for vals in itertools.product(*(FEATURES[k] for k in combo)):
                rule = tuple(zip(combo, vals))
                sel = [
                    t for t in rows
                    if all(t.get(k) == v for k, v in rule)
                ]
                if len(sel) < MIN_N:
                    continue
                s = stats(sel)
                boards["wr"].append((s["wr"], rule, s))
                boards["exp"].append((s["exp"], rule, s))
    return boards


def single_feature_table(rows):
    print(f"\n=== Single features (winners vs losers, n={len(rows)}) ===")
    base = stats(rows)
    print(f"BASELINE: {base['wr']:.1f}% WR, €{base['pnl']:+.0f}, exp €{base['exp']:+.2f}\n")
    for k, vals in FEATURES.items():
        parts = []
        for v in vals:
            sel = [t for t in rows if t.get(k) == v]
            if len(sel) >= 10:
                s = stats(sel)
                parts.append(f"{v}: {s['wr']:.0f}% (n={s['n']}, exp€{s['exp']:+.1f})")
        print(f"  {k:14} " + " | ".join(parts))


def main():
    c1h, c4h, trades_raw = load_data()
    rows = enrich(trades_raw, c1h, c4h)
    rows = add_features(rows, trades_raw, c1h, c4h)
    rows = [r for r in rows if r["pnl"] is not None]

    single_feature_table(rows)

    boards = mine(rows)
    for name, title in [("wr", "win rate"), ("exp", "expectancy €/trade")]:
        print(f"\n=== Top {TOP} rules by {title} (n≥{MIN_N}) ===")
        seen = set()
        shown = 0
        for score, rule, s in sorted(boards[name], key=lambda x: -x[0]):
            sig = frozenset(rule)
            if sig in seen:
                continue
            seen.add(sig)
            print(fmt(rule, s))
            shown += 1
            if shown >= TOP:
                break

    print(f"\n=== Worst 10 rules by expectancy (what to STOP doing) ===")
    seen = set()
    shown = 0
    for score, rule, s in sorted(boards["exp"], key=lambda x: x[0]):
        sig = frozenset(rule)
        if sig in seen:
            continue
        seen.add(sig)
        print(fmt(rule, s))
        shown += 1
        if shown >= 10:
            break


if __name__ == "__main__":
    main()
