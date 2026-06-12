"""One-off research: re-mine the real trades in ICT / visual-trading language.

edge_miner.py found WHAT contexts win (flush short, RSI/slope vetoes) but not
WHY you picked the 35 winning flushes out of ~1,400 occurrences. This script
adds ICT-style features (liquidity sweeps, prior-day-level raids, FVGs,
premium/discount of the dealing range, killzones, displacement) and asks two
questions:

  A. Across all closed real trades: which ICT contexts separate winners
     from losers? (same mining + robustness style as edge_miner v2)
  B. Across every mechanical flush-short occurrence (RSI<40 + 3 bear bars):
     which ICT features distinguish the occurrences you TOOK from the ones
     you SKIPPED — and does any ICT-filtered subset have *mechanical* edge
     at the exit geometry you actually traded (0.63% SL / 0.95% TP)?

Not wired into the app — pure analysis. Run: python3 ict_miner.py
"""
import datetime
import itertools

from trade_review import load_data, enrich, compute_ema, compute_rsi, bar_idx
from edge_miner import add_features, compute_atr, stats, WEEKDAYS

MIN_N = 20
MAX_CONDS = 3
TOP = 20

# Exit geometry the account actually realized (see LIVE_SCALP_v1)
SL_PCT, TP_PCT = 0.63, 0.95
FEE_MAKER, FEE_TAKER = 0.04, 0.30   # round-trip, in % of price move


# ── ICT feature computation ───────────────────────────────────────────────────

def killzone_of(hour):
    if 7 <= hour < 10:
        return "london_kz"
    if 13 <= hour < 16:
        return "ny_am_kz"
    if 18 <= hour < 21:
        return "ny_pm_kz"
    return "none"


def daily_levels(c1h):
    """Per 1h bar: (prior UTC day high, prior UTC day low)."""
    out = [None] * len(c1h)
    day_hi = {}
    day_lo = {}
    for ts, _o, hi, lo, _c, _v in c1h:
        d = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).date()
        day_hi[d] = max(day_hi.get(d, hi), hi)
        day_lo[d] = min(day_lo.get(d, lo), lo)
    for i, (ts, *_rest) in enumerate(c1h):
        d = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).date()
        prev = d - datetime.timedelta(days=1)
        if prev in day_hi:
            out[i] = (day_hi[prev], day_lo[prev])
    return out


def find_fvgs(c1h):
    """All 3-bar fair value gaps: list of (idx, 'bull'|'bear', top, bottom)."""
    gaps = []
    for k in range(2, len(c1h)):
        hi2, lo2 = c1h[k - 2][2], c1h[k - 2][3]
        hi0, lo0 = c1h[k][2], c1h[k][3]
        if lo0 > hi2:                       # bullish FVG (gap below price)
            gaps.append((k, "bull", lo0, hi2))
        elif hi0 < lo2:                     # bearish FVG (gap above price)
            gaps.append((k, "bear", lo2, hi0))
    return gaps


class IctContext:
    """Computes ICT features for any 1h bar index + trade direction."""

    SWEEP_LOOKBACK = 24    # swing = extreme of prior 24 bars
    SWEEP_RECENT = 3       # raid must be within last 3 bars
    RANGE_BARS = 168       # 7-day dealing range
    FVG_WINDOW = 12        # FVG formed within last 12 bars

    def __init__(self, c1h):
        self.c = c1h
        self.highs = [r[2] for r in c1h]
        self.lows = [r[3] for r in c1h]
        self.closes = [r[4] for r in c1h]
        self.atr = compute_atr(c1h)
        self.pdl = daily_levels(c1h)
        self.fvgs = find_fvgs(c1h)

    def _swept(self, i):
        """('buyside'|'sellside'|None) — liquidity raided in last few bars."""
        for k in range(i, max(i - self.SWEEP_RECENT, self.SWEEP_LOOKBACK), -1):
            sw_hi = max(self.highs[k - self.SWEEP_LOOKBACK:k])
            sw_lo = min(self.lows[k - self.SWEEP_LOOKBACK:k])
            if self.highs[k] > sw_hi:
                return "buyside"
            if self.lows[k] < sw_lo:
                return "sellside"
        return None

    def _pd_raid(self, i):
        """Prior-day high/low taken out within last few bars."""
        for k in range(i, max(i - self.SWEEP_RECENT, 0) - 1, -1):
            lv = self.pdl[k]
            if not lv:
                continue
            if self.highs[k] > lv[0]:
                return "pdh"
            if self.lows[k] < lv[1]:
                return "pdl"
        return None

    def _in_fvg(self, i, price, long_):
        """Entry price sitting inside a recent unfilled FVG in trade direction."""
        want = "bull" if long_ else "bear"
        for k, kind, top, bot in reversed(self.fvgs):
            if k > i:
                continue
            if k < i - self.FVG_WINDOW:
                break
            if kind != want:
                continue
            # unfilled: no bar after formation traded fully through the gap
            filled = any(
                (self.lows[j] <= bot if kind == "bull" else self.highs[j] >= top)
                for j in range(k + 1, i)
            )
            if not filled and bot <= price <= top:
                return True
        return False

    def features(self, i, price, long_):
        f = {}
        # liquidity sweep relative to trade: shorting after a buyside raid
        # (or longing after a sellside raid) = classic sweep-reversal
        sw = self._swept(i) if i > self.SWEEP_LOOKBACK + self.SWEEP_RECENT else None
        if sw is None:
            f["sweep"] = "none"
        elif (sw == "buyside") != long_:
            f["sweep"] = "reversal"
        else:
            f["sweep"] = "continuation"

        raid = self._pd_raid(i)
        if raid is None:
            f["pd_raid"] = "none"
        elif (raid == "pdh") != long_:
            f["pd_raid"] = "reversal"
        else:
            f["pd_raid"] = "continuation"

        f["fvg"] = "in_fvg" if self._in_fvg(i, price, long_) else "none"

        # premium/discount of 7-day dealing range
        f["pd_zone"] = None
        if i >= self.RANGE_BARS:
            hi = max(self.highs[i - self.RANGE_BARS:i + 1])
            lo = min(self.lows[i - self.RANGE_BARS:i + 1])
            if hi > lo:
                pos = (price - lo) / (hi - lo)
                zone = "premium" if pos > 0.55 else ("discount" if pos < 0.45 else "eq")
                f["pd_zone"] = zone
                # ICT-correct: sell premium, buy discount
                f["pd_ok"] = (zone == "discount") if long_ else (zone == "premium")

        # displacement: prior bar range > 1.5x ATR, signed vs trade
        f["displacement"] = "none"
        if self.atr[i - 1]:
            rng = self.highs[i - 1] - self.lows[i - 1]
            if rng > 1.5 * self.atr[i - 1]:
                bull = self.c[i - 1][4] >= self.c[i - 1][1]
                f["displacement"] = "with" if bull == long_ else "against"
        return f


# ── Part A: ICT mining over real trades ──────────────────────────────────────

ICT_FEATURES = {
    "sweep": ["reversal", "continuation", "none"],
    "pd_raid": ["reversal", "continuation", "none"],
    "fvg": ["in_fvg", "none"],
    "pd_zone": ["premium", "eq", "discount"],
    "pd_ok": [True, False],
    "displacement": ["with", "against", "none"],
    "killzone": ["london_kz", "ny_am_kz", "ny_pm_kz", "none"],
    # carried over so combos can mix visual + old context
    "direction": ["long", "short"],
    "rsi_zone": ["dip", "neutral", "momentum"],
    "slope_1h": ["with", "against"],
}


def robust(sel):
    """v2-style robustness: survives dropping 2 best wins + half-split."""
    if len(sel) < MIN_N:
        return False
    by_pnl = sorted(sel, key=lambda r: -(r["pnl"] or 0))
    trimmed = by_pnl[2:]
    if sum(r["pnl"] or 0 for r in trimmed) <= 0:
        return False
    by_ts = sorted(sel, key=lambda r: r["ts_entry"])
    half = len(by_ts) // 2
    for part in (by_ts[:half], by_ts[half:]):
        wr = sum(1 for r in part if (r["pnl"] or 0) > 0) / len(part)
        if wr < 0.45:
            return False
    return True


def mine_ict(rows):
    found = []
    keys = list(ICT_FEATURES)
    for r in range(1, MAX_CONDS + 1):
        for combo in itertools.combinations(keys, r):
            for vals in itertools.product(*(ICT_FEATURES[k] for k in combo)):
                rule = tuple(zip(combo, vals))
                sel = [t for t in rows if all(t.get(k) == v for k, v in rule)]
                if len(sel) < MIN_N:
                    continue
                s = stats(sel)
                s["robust"] = robust(sel)
                found.append((s["wr"], rule, s))
    return found


def print_board(found, rows):
    base = stats(rows)
    print(f"\nBASELINE: {base['wr']:.1f}% WR, €{base['pnl']:+.0f}, exp €{base['exp']:+.2f}, n={base['n']}")
    print(f"\n=== Part A: top ICT rules by win rate (n≥{MIN_N}, ✓ = robust) ===")
    seen, shown = set(), 0
    for _wr, rule, s in sorted(found, key=lambda x: -x[0]):
        sig = frozenset(rule)
        if sig in seen:
            continue
        seen.add(sig)
        cond = " & ".join(f"{k}={v}" for k, v in rule)
        mark = "✓" if s["robust"] else " "
        print(f"{mark} {s['wr']:5.1f}%  n={s['n']:<4} exp=€{s['exp']:+6.2f} pnl=€{s['pnl']:+8.0f}  {cond}")
        shown += 1
        if shown >= TOP:
            break

    print("\n=== Part A: single ICT features (n≥10) ===")
    for k, vals in ICT_FEATURES.items():
        if k in ("direction", "rsi_zone", "slope_1h"):
            continue
        parts = []
        for v in vals:
            sel = [t for t in rows if t.get(k) == v]
            if len(sel) >= 10:
                s = stats(sel)
                parts.append(f"{v}: {s['wr']:.0f}% (n={s['n']}, exp€{s['exp']:+.1f})")
        print(f"  {k:13} " + " | ".join(parts))


# ── Part B: taken vs skipped flush occurrences ───────────────────────────────

def flush_occurrences(c1h, rsi14):
    """All bar indices where RSI(14)<40 and bars i-2..i are bear closes."""
    occ = []
    for i in range(3, len(c1h)):
        if rsi14[i] is None or rsi14[i] >= 40:
            continue
        if all(c1h[k][4] < c1h[k][1] for k in (i, i - 1, i - 2)):
            occ.append(i)
    return occ


def first_touch_short(c1h, i, fee_pct):
    """Short at close[i]; walk forward; +1 win / 0 loss / None unresolved.
    Both barriers in same bar counts as loss (conservative)."""
    entry = c1h[i][4]
    tp = entry * (1 - TP_PCT / 100)
    sl = entry * (1 + SL_PCT / 100)
    for j in range(i + 1, min(i + 200, len(c1h))):
        hit_sl = c1h[j][2] >= sl
        hit_tp = c1h[j][3] <= tp
        if hit_sl:
            return 0
        if hit_tp:
            return 1
    return None


def part_b(c1h, rows, ctx):
    closes = [r[4] for r in c1h]
    ts1h = [r[0] for r in c1h]
    rsi14 = compute_rsi(closes, 14)
    occ = flush_occurrences(c1h, rsi14)

    # label taken: a real SHORT entry during bar i or i+1
    short_entries = sorted(r["ts_entry"] * 1000 for r in rows if r["direction"] == "short")
    taken_idx = set()
    for i in occ:
        lo, hi = ts1h[i], ts1h[i] + 2 * 3600 * 1000
        import bisect
        p = bisect.bisect_left(short_entries, lo)
        if p < len(short_entries) and short_entries[p] < hi:
            taken_idx.add(i)

    feats = {i: ctx.features(i, closes[i], long_=False) for i in occ}
    for i in occ:
        dt = datetime.datetime.fromtimestamp(ts1h[i] / 1000, tz=datetime.timezone.utc)
        feats[i]["killzone"] = killzone_of(dt.hour)
        feats[i]["ny_session"] = 13 <= dt.hour < 21

    print(f"\n=== Part B: flush-short occurrences — taken vs skipped ===")
    print(f"occurrences={len(occ)}, taken={len(taken_idx)}")

    fkeys = ["sweep", "pd_raid", "fvg", "pd_zone", "pd_ok", "displacement",
             "killzone", "ny_session"]
    print(f"\n{'feature=value':28} {'taken%':>7} {'skip%':>7}  edge")
    for k in fkeys:
        vals = sorted({feats[i].get(k) for i in occ if feats[i].get(k) is not None},
                      key=str)
        for v in vals:
            t = sum(1 for i in taken_idx if feats[i].get(k) == v)
            s = sum(1 for i in occ if i not in taken_idx and feats[i].get(k) == v)
            tp_ = t / max(len(taken_idx), 1) * 100
            sp_ = s / max(len(occ) - len(taken_idx), 1) * 100
            flag = "  ◀ over-selected" if tp_ > sp_ * 1.5 and t >= 5 else ""
            print(f"{k}={v!s:<{26 - len(k)}} {tp_:6.1f}% {sp_:6.1f}%{flag}")

    # mechanical first-touch test at the realized geometry, per ICT filter
    be_maker = (SL_PCT + FEE_MAKER) / (SL_PCT + TP_PCT) * 100
    be_taker = (SL_PCT + FEE_TAKER) / (SL_PCT + TP_PCT) * 100
    print(f"\n=== Part B: mechanical first-touch, short @ {SL_PCT}% SL / {TP_PCT}% TP ===")
    print(f"breakeven WR: {be_maker:.1f}% maker / {be_taker:.1f}% taker\n")

    def test(label, idxs):
        res = [first_touch_short(c1h, i, 0) for i in idxs]
        res = [r for r in res if r is not None]
        if len(res) < 15:
            return
        wr = sum(res) / len(res) * 100
        half = len(idxs) // 2
        wr_halves = []
        for part in (idxs[:half], idxs[half:]):
            pr = [first_touch_short(c1h, i, 0) for i in part]
            pr = [r for r in pr if r is not None]
            wr_halves.append(sum(pr) / len(pr) * 100 if pr else 0)
        mark = "✓" if wr > be_maker and min(wr_halves) > be_maker else " "
        print(f"{mark} {wr:5.1f}% WR  n={len(res):<5} halves {wr_halves[0]:.0f}/{wr_halves[1]:.0f}  {label}")

    test("ALL occurrences (v2 baseline, new geometry)", occ)
    test("taken by you", sorted(taken_idx))
    for k in ["sweep", "pd_raid", "fvg", "pd_ok", "displacement", "killzone", "ny_session"]:
        for v in sorted({feats[i].get(k) for i in occ if feats[i].get(k) is not None}, key=str):
            idxs = [i for i in occ if feats[i].get(k) == v]
            test(f"{k}={v}", idxs)
    # the obvious stacked candidates
    test("sweep=reversal & ny_session",
         [i for i in occ if feats[i]["sweep"] == "reversal" and feats[i]["ny_session"]])
    test("pd_ok & displacement=with",
         [i for i in occ if feats[i].get("pd_ok") and feats[i]["displacement"] == "with"])
    test("pd_raid=reversal & pd_ok",
         [i for i in occ if feats[i]["pd_raid"] == "reversal" and feats[i].get("pd_ok")])


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    c1h, c4h, trades_raw = load_data()
    rows = enrich(trades_raw, c1h, c4h)
    rows = add_features(rows, trades_raw, c1h, c4h)
    rows = [r for r in rows if r["pnl"] is not None]

    ctx = IctContext(c1h)
    ts1h = [r[0] for r in c1h]
    for row in rows:
        i = bar_idx(ts1h, row["ts_entry"] * 1000)
        if i is None or i <= ctx.RANGE_BARS:
            continue
        row.update(ctx.features(i, row["entry"] or c1h[i][4],
                                long_=row["direction"] == "long"))
        row["killzone"] = killzone_of(
            datetime.datetime.fromtimestamp(
                row["ts_entry"], tz=datetime.timezone.utc).hour)

    found = mine_ict(rows)
    print_board(found, rows)
    part_b(c1h, rows, ctx)


if __name__ == "__main__":
    main()
