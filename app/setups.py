"""LENS_EDGE_v3 setup engine — the iterative loop's core.

Codifies the five robust setups (S1–S5) and seven vetoes mined from 464 real
trades (see strategies/LENS_EDGE_v3_ICT/FINDINGS.md). Three consumers:

  1. scan_and_signal()  — evaluate the latest closed 1h bar; matching setups
     land in the existing signals pipeline (pending → approve/reject on
     /signals). These are checklist prompts, NOT auto-trade triggers: the
     mined edge is discretionary selection inside these contexts.
  2. backfill_setup_tags() — classify every closed trade's entry context and
     write trades.setup_tag (S1..S5 / VETO:<rule> / NONE). New synced trades
     get tagged on the next call, so realized-vs-mined stats stay current.
  3. setup_scoreboard() — realized WR / expectancy per tag, split into
     old/new halves so drift from the mined numbers is visible. When enough
     tagged trades accumulate, re-mine (v4) against this ground truth.

Indicator math intentionally mirrors trade_review.py / ict_miner.py so tags
match the research that defined the setups.
"""
from __future__ import annotations

import bisect
import datetime
import os
import sqlite3
import uuid
from typing import Optional

from .database import DB_PATH

OHLCV_SYMBOL = "binance:BTC/USDT"

# LENS's own config file (no prism dependency). Holds API keys + LENS_* settings;
# also loaded by the systemd unit as EnvironmentFile, so env vars win at runtime.
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

# ⚠️ PLACEHOLDER exit geometry — NOT a validated edge. Pending decision on the
# real stop/target source (ATR vs env-config vs per-setup). Do not cite as fact.
SL_PCT, TP_PCT = 0.63, 0.95

# ── alert ticket sizing (tunable in .env; falls back to these defaults) ──
MM_RATE = 0.005                      # maintenance margin, Kraken BTC perp ~0.5%
SETUP_NAMES = {
    "S1": "NY AM flush · RSI<40, 13-16 UTC",
    "S2": "Premium + bearish displacement",
    "S3": "RSI>55 + buyside sweep (continuation)",
    "S4": "RSI<40 in discount, no recent sweep",
    "S5": "RSI>55 in London KZ 07-10 UTC",
    "TEST": "test signal",
}

SWEEP_LOOKBACK = 24                   # swing = extreme of prior 24 bars
SWEEP_RECENT = 3                      # raid counts if within last 3 bars
RANGE_BARS = 168                      # 7-day dealing range
FVG_WINDOW = 12                       # FVG relevant if formed in last 12 bars
WARMUP = RANGE_BARS + SWEEP_LOOKBACK + SWEEP_RECENT + 2


# ── indicators (same math as trade_review.py) ────────────────────────────────

def _ema(closes, period):
    k = 2 / (period + 1)
    out, avg = [], None
    for i, v in enumerate(closes):
        if i < period - 1:
            out.append(None)
        elif i == period - 1:
            avg = sum(closes[:period]) / period
            out.append(avg)
        else:
            avg = v * k + avg * (1 - k)
            out.append(avg)
    return out


def _rsi(closes, period=14):
    out = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = [max(0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    losses = [max(0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out[period] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
        avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        out[i] = 100 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def _atr(c1h, period=14):
    atr = [None] * len(c1h)
    trs = []
    for i in range(1, len(c1h)):
        hi, lo = c1h[i][2], c1h[i][3]
        prev_cl = c1h[i - 1][4]
        trs.append(max(hi - lo, abs(hi - prev_cl), abs(lo - prev_cl)))
        if i == period:
            atr[i] = sum(trs) / period
        elif i > period:
            atr[i] = (atr[i - 1] * (period - 1) + trs[-1]) / period
    return atr


def _killzone(hour):
    if 7 <= hour < 10:
        return "london_kz"
    if 13 <= hour < 16:
        return "ny_am_kz"
    if 18 <= hour < 21:
        return "ny_pm_kz"
    return "none"


# ── per-bar ICT context ───────────────────────────────────────────────────────

class BarContext:
    """All direction-independent features for one closed 1h bar."""

    def __init__(self, c1h, i, rsi14, ema21, atr14, day_levels, fvgs):
        self.i = i
        ts, o, hi, lo, cl, *_ = c1h[i]
        self.ts_ms = ts
        self.close = cl
        dt = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc)
        self.hour = dt.hour
        self.killzone = _killzone(dt.hour)
        self.rsi = rsi14[i]

        highs = [r[2] for r in c1h]
        lows = [r[3] for r in c1h]

        # EMA21 slope over last 3 bars: 'up' | 'down' | None
        self.slope = None
        if i >= 3 and ema21[i] and ema21[i - 3]:
            self.slope = "up" if ema21[i] > ema21[i - 3] else "down"

        # liquidity sweep in last few bars: 'buyside' | 'sellside' | None
        self.sweep = None
        if i > SWEEP_LOOKBACK + SWEEP_RECENT:
            for k in range(i, i - SWEEP_RECENT, -1):
                sw_hi = max(highs[k - SWEEP_LOOKBACK:k])
                sw_lo = min(lows[k - SWEEP_LOOKBACK:k])
                if highs[k] > sw_hi:
                    self.sweep = "buyside"
                    break
                if lows[k] < sw_lo:
                    self.sweep = "sellside"
                    break

        # prior-day high/low raid in last few bars: 'pdh' | 'pdl' | None
        self.pd_raid = None
        for k in range(i, max(i - SWEEP_RECENT, 0) - 1, -1):
            lv = day_levels[k]
            if not lv:
                continue
            if highs[k] > lv[0]:
                self.pd_raid = "pdh"
                break
            if lows[k] < lv[1]:
                self.pd_raid = "pdl"
                break

        # displacement on prior bar: 'bull' | 'bear' | None
        self.displacement = None
        if atr14[i - 1]:
            rng = highs[i - 1] - lows[i - 1]
            if rng > 1.5 * atr14[i - 1]:
                self.displacement = "bull" if c1h[i - 1][4] >= c1h[i - 1][1] else "bear"

        # position in 7-day dealing range: 'premium' | 'eq' | 'discount' | None
        self.pd_zone = None
        if i >= RANGE_BARS:
            r_hi = max(highs[i - RANGE_BARS:i + 1])
            r_lo = min(lows[i - RANGE_BARS:i + 1])
            if r_hi > r_lo:
                pos = (cl - r_lo) / (r_hi - r_lo)
                self.pd_zone = ("premium" if pos > 0.55
                                else "discount" if pos < 0.45 else "eq")

        # inside a recent unfilled FVG (per direction)
        self.in_fvg = {"long": False, "short": False}
        for k, kind, top, bot in reversed(fvgs):
            if k > i:
                continue
            if k < i - FVG_WINDOW:
                break
            filled = any(
                (lows[j] <= bot if kind == "bull" else highs[j] >= top)
                for j in range(k + 1, i)
            )
            if not filled and bot <= cl <= top:
                self.in_fvg["long" if kind == "bull" else "short"] = True

        # 3 consecutive bear/bull closes ending at this bar
        self.bear_streak3 = i >= 2 and all(c1h[k][4] < c1h[k][1] for k in (i, i - 1, i - 2))
        self.bull_streak3 = i >= 2 and all(c1h[k][4] > c1h[k][1] for k in (i, i - 1, i - 2))


def _day_levels(c1h):
    out = [None] * len(c1h)
    day_hi, day_lo = {}, {}
    for ts, _o, hi, lo, _c, *_ in c1h:
        d = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).date()
        day_hi[d] = max(day_hi.get(d, hi), hi)
        day_lo[d] = min(day_lo.get(d, lo), lo)
    for i, (ts, *_r) in enumerate(c1h):
        d = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).date()
        prev = d - datetime.timedelta(days=1)
        if prev in day_hi:
            out[i] = (day_hi[prev], day_lo[prev])
    return out


def _fvgs(c1h):
    gaps = []
    for k in range(2, len(c1h)):
        hi2, lo2 = c1h[k - 2][2], c1h[k - 2][3]
        hi0, lo0 = c1h[k][2], c1h[k][3]
        if lo0 > hi2:
            gaps.append((k, "bull", lo0, hi2))
        elif hi0 < lo2:
            gaps.append((k, "bear", lo2, hi0))
    return gaps


class SetupEngine:
    """Precomputes indicators once, then evaluates any bar index."""

    def __init__(self, c1h):
        self.c1h = c1h
        self.ts = [r[0] for r in c1h]
        closes = [r[4] for r in c1h]
        self.rsi14 = _rsi(closes, 14)
        self.ema21 = _ema(closes, 21)
        self.atr14 = _atr(c1h)
        self.day_levels = _day_levels(c1h)
        self.fvg_list = _fvgs(c1h)

    def context(self, i) -> BarContext:
        return BarContext(self.c1h, i, self.rsi14, self.ema21, self.atr14,
                          self.day_levels, self.fvg_list)

    def bar_for_ts(self, ts_ms) -> Optional[int]:
        i = bisect.bisect_right(self.ts, ts_ms) - 1
        return i if i >= WARMUP else None


# ── setup + veto rules (FINDINGS.md, mined values in comments) ───────────────

def vetoes(ctx: BarContext, direction: str) -> list[str]:
    long_ = direction == "long"
    v = []
    if ctx.rsi is not None and 40 <= ctx.rsi <= 55:
        v.append("rsi_neutral")                       # 34.7% WR, €−1,243
    if ctx.slope and (ctx.slope == "up") != long_:
        v.append("slope_against")                     # 38.1% WR, €−1,177
    if ctx.sweep and ((ctx.sweep == "buyside") != long_):
        v.append("sweep_fade")                        # fading the raid: 33% WR
    if ctx.pd_raid and ((ctx.pd_raid == "pdh") != long_):
        v.append("pd_raid_fade")                      # 37% WR, €−6.7/trade
    if ctx.displacement and ((ctx.displacement == "bull") != long_):
        v.append("displacement_against")              # 35% WR
    if ctx.in_fvg[direction]:
        v.append("fvg_entry")                         # 38% WR, €−15/trade
    if ctx.killzone == "ny_pm_kz":
        v.append("ny_pm_kz")                          # 39% WR, €−11.1/trade
    return v


def matched_setups(ctx: BarContext) -> list[dict]:
    """All S1–S5 matches on this bar, each with direction + checklist."""
    out = []
    rsi = ctx.rsi
    if rsi is None:
        return out

    # S1 — NY AM Killzone Flush Short (77.3% WR n=22 realized)
    if ctx.killzone == "ny_am_kz" and rsi < 40 and ctx.bear_streak3:
        out.append({"setup": "S1", "direction": "short",
                    "name": "NY AM Killzone Flush Short",
                    "checks": ["rsi<40", "13-16utc", "3 bear bars"]})

    # S2 — Premium Displacement Short (65.2% WR n=23, €+34/trade)
    if ctx.pd_zone == "premium" and ctx.displacement == "bear":
        out.append({"setup": "S2", "direction": "short",
                    "name": "Premium Displacement Short",
                    "checks": ["premium of 7d range", "bear displacement bar"]})

    # S3 — Continuation Long (62.5% WR n=40, €+915 total)
    if rsi > 55 and ctx.sweep == "buyside":
        out.append({"setup": "S3", "direction": "long",
                    "name": "Continuation Long",
                    "checks": ["rsi>55", "buyside sweep with trade"]})

    # S4 — Discount Dip Long, quiet context (62.1% WR n=29)
    if rsi < 40 and ctx.pd_zone == "discount" and ctx.sweep is None:
        out.append({"setup": "S4", "direction": "long",
                    "name": "Discount Dip Long",
                    "checks": ["rsi<40", "discount of 7d range", "no recent sweep"]})

    # S5 — London Momentum Long (63.6% WR n=22)
    if rsi > 55 and ctx.killzone == "london_kz":
        out.append({"setup": "S5", "direction": "long",
                    "name": "London Momentum Long",
                    "checks": ["rsi>55", "07-10utc london kz"]})

    return out


def classify(ctx: BarContext, direction: str) -> str:
    """Tag for a trade entered on this bar: 'S1[+S2]' / 'VETO:<rules>' / 'NONE'."""
    hits = [m["setup"] for m in matched_setups(ctx) if m["direction"] == direction]
    v = vetoes(ctx, direction)
    if hits and not v:
        return "+".join(hits)
    if hits and v:
        return "+".join(hits) + "|VETO:" + ",".join(v)
    if v:
        return "VETO:" + ",".join(v)
    return "NONE"


# ── consumers ─────────────────────────────────────────────────────────────────

def _load_candles(conn) -> list:
    return conn.execute(
        "SELECT ts, open, high, low, close, volume FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe='1h' ORDER BY ts",
        (OHLCV_SYMBOL,),
    ).fetchall()


def backfill_setup_tags(only_untagged: bool = True) -> dict:
    """Classify entry context of closed trades → trades.setup_tag."""
    conn = sqlite3.connect(DB_PATH)
    c1h = _load_candles(conn)
    eng = SetupEngine(c1h)

    where = "closed_at IS NOT NULL"
    if only_untagged:
        where += " AND (setup_tag IS NULL OR setup_tag = '')"
    trades = conn.execute(
        f"SELECT id, direction, opened_at FROM trades WHERE {where}"
    ).fetchall()

    tagged, skipped = 0, 0
    flagged = []   # newly tagged trades that land off-playbook (VETO*/NONE)
    for tid, direction, opened_at in trades:
        s = opened_at.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        i = eng.bar_for_ts(int(dt.timestamp() * 1000))
        if i is None:
            skipped += 1
            continue
        tag = classify(eng.context(i), direction)
        conn.execute("UPDATE trades SET setup_tag=? WHERE id=?", (tag, tid))
        tagged += 1
        if tag.startswith("VETO") or tag == "NONE":
            flagged.append((tid, direction, tag))
    conn.commit()   # tags are safe before any notify I/O

    # Accountability push: the loop alerts when a setup fires, but said nothing
    # when a trade was taken OFF-signal — that feedback never arrived (found
    # 2026-07-02: 11 of 13 post-go-live trades bypassed the loop). Incremental
    # sync path only, so a manual full re-tag doesn't spam the phone.
    if only_untagged and flagged:
        veto = conn.execute(
            "SELECT count(*), coalesce(round(sum(pnl)),0) FROM trades "
            "WHERE setup_tag LIKE 'VETO%' AND pnl IS NOT NULL"
        ).fetchone()
        lines = [f"#{tid} {direction} -> {tag}" for tid, direction, tag in flagged[:5]]
        lines.append(f"lifetime VETO bucket: {veto[0]} trades, EUR {veto[1]:+.0f}")
        _notify(
            f"OFF-PLAYBOOK trade{'s' if len(flagged) > 1 else ''} detected ({len(flagged)})",
            "\n".join(lines),
            tags="warning",
        )

    conn.close()
    return {"tagged": tagged, "skipped_no_candles": skipped,
            "off_playbook_flagged": len(flagged)}


def scan_latest() -> dict:
    """Evaluate the most recent CLOSED 1h bar; return matches + vetoes.

    Refreshes the ohlcv cache first (via backtest_engine.load_ohlcv) so the
    scan sees current price. Caller decides whether to emit signals.
    """
    from .backtest_engine import load_ohlcv
    load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=2, exchange_id="binance")

    conn = sqlite3.connect(DB_PATH)
    c1h = _load_candles(conn)
    conn.close()

    # last fully closed bar = second-to-last row if the last is still forming
    now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    i = len(c1h) - 1
    if c1h[i][0] + 3_600_000 > now_ms:
        i -= 1

    eng = SetupEngine(c1h)
    ctx = eng.context(i)
    matches = matched_setups(ctx)
    for m in matches:
        m["vetoes"] = vetoes(ctx, m["direction"])
        m["clean"] = not m["vetoes"]

    return {
        "bar_ts": datetime.datetime.fromtimestamp(
            ctx.ts_ms / 1000, tz=datetime.timezone.utc).isoformat(),
        "close": ctx.close,
        "rsi": round(ctx.rsi, 1) if ctx.rsi else None,
        "killzone": ctx.killzone,
        "pd_zone": ctx.pd_zone,
        "sweep": ctx.sweep,
        "displacement": ctx.displacement,
        "matches": matches,
    }


def emit_signals(scan: dict) -> list[dict]:
    """Insert one pending signal per clean setup match (discipline applies)."""
    from . import discipline
    from .database import get_last_non_rejected_signal_for_symbol, insert_signal

    emitted = []
    for m in scan["matches"]:
        if not m["clean"]:
            continue
        price = scan["close"]
        long_ = m["direction"] == "long"
        sl = price * (1 - SL_PCT / 100) if long_ else price * (1 + SL_PCT / 100)
        tp = price * (1 + TP_PCT / 100) if long_ else price * (1 - TP_PCT / 100)
        payload = {
            "signal_id": f"v3-{m['setup']}-{uuid.uuid4().hex[:8]}",
            "strategy_name": "LENS_EDGE_v3",
            "strategy_version": "3.0",
            "symbol": "BTC/USD",
            "venue": "kraken_futures",
            "trigger_type": m["setup"],
            "direction": m["direction"],
            "entry_price": price,
            "stop_price": round(sl, 1),
            "target_price": round(tp, 1),
            "expected_rr": round(TP_PCT / SL_PCT, 2),
            "mtf_confluence": m["checks"],
            "confluence_count": min(len(m["checks"]), 5),
        }
        reason = discipline.evaluate(
            payload, get_last_non_rejected_signal_for_symbol(payload["symbol"]))
        emitted.append(insert_signal(payload, auto_rejection_reason=reason))
    return emitted


def emit_board_signals() -> list[dict]:
    """Board-driven hedge emit: trade the Strategy Board's top-3 HEDGE strategies,
    each at its OWN derived geometry — stop = p65 of historical adverse excursion,
    target = stop × the strategy's board-optimal R. Session/quality discipline
    still applies. Highest-ranked match wins the bar (one signal), deduped per
    bar+strategy. No global SL/TP — every level comes from what made money in
    backtest. Falls back to the legacy S1–S5 emit only if the board has no cache."""
    from . import discipline
    from .backtest_engine import load_ohlcv
    from .database import get_last_non_rejected_signal_for_symbol, insert_signal
    from .strategy_eval import live_matches, tradeable

    book = tradeable("hedge")
    if not book:
        return emit_signals(scan_latest())     # graceful fallback, never silent-dead

    load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=2, exchange_id="binance")
    conn = sqlite3.connect(DB_PATH)
    c1h = _load_candles(conn)
    conn.close()
    eng = SetupEngine(c1h)
    now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    i = len(c1h) - 1
    if c1h[i][0] + 3_600_000 > now_ms:         # drop a still-forming bar
        i -= 1

    geo = {b["name"]: b for b in book}
    matches = live_matches(eng, i, [b["name"] for b in book])
    if not matches:
        return []

    price = c1h[i][4]
    bar_ms = c1h[i][0]
    bar_tag = datetime.datetime.fromtimestamp(
        bar_ms / 1000, tz=datetime.timezone.utc).strftime("%Y%m%d%H")

    emitted = []
    for mtc in matches:                        # ranked order — first one wins the bar
        name = mtc["name"]
        long_ = mtc["dir"] == "long"
        sl_pct = geo[name]["sl_pct"]
        R = geo[name]["target_r"]
        sl = price * (1 - sl_pct / 100) if long_ else price * (1 + sl_pct / 100)
        tp = price * (1 + sl_pct * R / 100) if long_ else price * (1 - sl_pct * R / 100)
        payload = {
            "signal_id": f"hedge-{name.split(' ')[0]}-{bar_tag}",
            "strategy_name": name,
            "strategy_version": "board",
            "symbol": "BTC/USD",
            "venue": "kraken_futures",
            "trigger_type": name,
            "direction": mtc["dir"],
            "entry_price": round(price, 1),
            "stop_price": round(sl, 1),
            "target_price": round(tp, 1),
            "expected_rr": round(R, 2),
            "mtf_confluence": [f"board top-{geo[name]['rank']} hedge",
                               f"stop {sl_pct:.2f}% (p65 MAE)", f"{R:g}R target"],
            "confluence_count": 2,
        }
        reason = discipline.evaluate(
            payload, get_last_non_rejected_signal_for_symbol(payload["symbol"]))
        try:
            row = insert_signal(payload, auto_rejection_reason=reason)
        except ValueError:
            continue                            # already emitted this bar+strategy
        emitted.append(row)
        break                                   # one signal per bar, highest rank
    return emitted


VETO_LABELS = {
    "rsi_neutral":          "RSI 40–55 dead zone — 34.7% WR, −€1,243",
    "slope_against":        "1h EMA21 slope against trade — 38.1% WR, −€1,177",
    "sweep_fade":           "fading a liquidity sweep — 33% WR",
    "pd_raid_fade":         "fading a prior-day level raid — 37% WR",
    "displacement_against": "displacement candle against trade — 35% WR",
    "fvg_entry":            "entry inside FVG retrace — 38% WR, −€15/trade",
    "ny_pm_kz":             "NY PM 18–21 UTC, your worst hours — 39% WR",
}


def _setup_checklists(ctx: BarContext) -> list[dict]:
    rsi_ok = ctx.rsi is not None
    return [
        {"id": "S1", "name": "NY AM Killzone Flush Short", "direction": "short",
         "wr": "90.9% realized (n=11)",
         "conds": [
             {"label": "RSI(14) < 40 (oversold flush)", "ok": rsi_ok and ctx.rsi < 40},
             {"label": "NY AM killzone — 13:00–16:00 UTC", "ok": ctx.killzone == "ny_am_kz"},
             {"label": "3 consecutive bear closes", "ok": ctx.bear_streak3},
         ]},
        {"id": "S2", "name": "Premium Displacement Short", "direction": "short",
         "wr": "65% mined (n=23)",
         "conds": [
             {"label": "price in premium of 7d range (>55%)", "ok": ctx.pd_zone == "premium"},
             {"label": "bearish displacement bar (range >1.5× ATR)", "ok": ctx.displacement == "bear"},
         ]},
        {"id": "S3", "name": "Continuation Long", "direction": "long",
         "wr": "56.7% realized (n=30)",
         "conds": [
             {"label": "RSI(14) > 55 (momentum)", "ok": rsi_ok and ctx.rsi > 55},
             {"label": "buyside sweep — trade WITH the raid", "ok": ctx.sweep == "buyside"},
         ]},
        {"id": "S4", "name": "Discount Dip Long", "direction": "long",
         "wr": "62% mined (n=29)",
         "conds": [
             {"label": "RSI(14) < 40 (oversold)", "ok": rsi_ok and ctx.rsi < 40},
             {"label": "price in discount of 7d range (<45%)", "ok": ctx.pd_zone == "discount"},
             {"label": "no recent liquidity sweep (quiet)", "ok": ctx.sweep is None},
         ]},
        {"id": "S5", "name": "London Momentum Long", "direction": "long",
         "wr": "60% realized (n=5)",
         "conds": [
             {"label": "RSI(14) > 55 (momentum)", "ok": rsi_ok and ctx.rsi > 55},
             {"label": "London killzone — 07:00–10:00 UTC", "ok": ctx.killzone == "london_kz"},
         ]},
    ]


def _board_geo(direction: str) -> tuple[float, float]:
    """(sl_pct, tp_pct) for the /desk ticket of a direction — pulled from the
    board's top hedge strategy of that direction, so the desk shows the same
    money-derived geometry the scanner fires. Falls back to a tight 0.6%/1.2%
    only if the board has no cache yet."""
    try:
        from .strategy_eval import tradeable
        for b in tradeable("hedge"):
            if b["dir"] == direction:
                return b["sl_pct"], round(b["sl_pct"] * b["target_r"], 2)
    except Exception:
        pass
    return 0.6, 1.2


def desk_state(refresh: bool = True) -> dict:
    """Everything the /desk page needs to say ENTER / BLOCKED / STAND DOWN."""
    if refresh:
        try:
            from .backtest_engine import load_ohlcv
            load_ohlcv(symbol="BTC/USDT", timeframe="1h", months=2, exchange_id="binance")
        except Exception:
            pass  # offline: evaluate the freshest cached bar instead

    conn = sqlite3.connect(DB_PATH)
    c1h = _load_candles(conn)
    bal_row = conn.execute(
        "SELECT balance_after FROM trades WHERE balance_after IS NOT NULL "
        "AND balance_after > 0 ORDER BY closed_at DESC LIMIT 1").fetchone()
    conn.close()

    now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    i = len(c1h) - 1
    if c1h[i][0] + 3_600_000 > now_ms:
        i -= 1
    eng = SetupEngine(c1h)
    ctx = eng.context(i)

    checklists = _setup_checklists(ctx)
    v_long = vetoes(ctx, "long")
    v_short = vetoes(ctx, "short")

    verdicts = {}
    for direction, v in (("long", v_long), ("short", v_short)):
        active = [c for c in checklists
                  if c["direction"] == direction and all(x["ok"] for x in c["conds"])]
        for c in checklists:
            if c["direction"] == direction:
                c["active"] = all(x["ok"] for x in c["conds"])
                c["vetoed"] = c["active"] and bool(v)
        price = ctx.close
        long_ = direction == "long"
        # ticket is always computed — when blocked it renders as reference-only
        verdicts[direction] = {
            "state": ("enter" if active and not v
                      else "blocked" if active and v
                      else "veto" if v else "stand_down"),
            "setups": [c["id"] for c in active],
            "vetoes": [VETO_LABELS[k] for k in v],
            "plan": (lambda slp, tpp: {
                "entry": round(price, 1),
                "stop": round(price * (1 - slp / 100) if long_ else price * (1 + slp / 100), 1),
                "target": round(price * (1 + tpp / 100) if long_ else price * (1 - tpp / 100), 1),
                "sl_pct": slp, "tp_pct": tpp,
                "rr": round(tpp / slp, 2) if slp else 0,
            })(*_board_geo(direction)),
        }

    bar_dt = datetime.datetime.fromtimestamp(ctx.ts_ms / 1000, tz=datetime.timezone.utc)
    return {
        "bar_ts": bar_dt.isoformat(),
        "bar_age_min": max(0, int((now_ms - (ctx.ts_ms + 3_600_000)) / 60000)),
        "close": ctx.close,
        "balance": bal_row[0] if bal_row else None,
        "context": {
            "rsi": round(ctx.rsi, 1) if ctx.rsi is not None else None,
            "rsi_zone": (None if ctx.rsi is None else
                         "flush" if ctx.rsi < 40 else
                         "momentum" if ctx.rsi > 55 else "dead"),
            "killzone": ctx.killzone,
            "pd_zone": ctx.pd_zone,
            "sweep": ctx.sweep,
            "pd_raid": ctx.pd_raid,
            "displacement": ctx.displacement,
            "slope": ctx.slope,
            "bear_streak3": ctx.bear_streak3,
        },
        "verdicts": verdicts,
        "checklists": checklists,
        "scoreboard": setup_scoreboard(),
    }


def _envcfg(key: str, default: str) -> str:
    """Read a config value from the environment, falling back to LENS's own .env,
    then the supplied default. Mirrors how _notify resolves the ntfy creds so the
    hourly cron (which doesn't source .env) still picks up overrides."""
    v = os.environ.get(key)
    if v is not None and v != "":
        return v
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return default


_BAL_CACHE: dict = {"v": None, "ts": 0.0}
_BAL_TTL = 60.0  # seconds — don't hammer the Kraken API on every render


def _live_account() -> Optional[float]:
    """Real account size for ticket sizing (EUR). Tries true live Kraken equity
    first (flex portfolioValue, includes unrealized PnL), cached for 60s; falls
    back to the balance after the most recent closed trade — the same source the
    /desk page uses. Returns None only when there's neither live equity nor a
    synced trade balance (fresh DB / no keys / offline)."""
    now = datetime.datetime.now().timestamp()
    if _BAL_CACHE["v"] is not None and now - _BAL_CACHE["ts"] < _BAL_TTL:
        return _BAL_CACHE["v"]

    bal: Optional[float] = None

    # 1) true live equity from Kraken Futures
    try:
        from .kraken_sync import get_api_keys, fetch_live_balance
        key, secret = get_api_keys("personal")
        res = fetch_live_balance(key, secret)
        if res.get("eur_balance"):
            bal = float(res["eur_balance"])
    except Exception:
        bal = None

    # 2) fall back to the last closed-trade balance (offline-safe, local)
    if bal is None:
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT balance_after FROM trades WHERE balance_after IS NOT NULL "
                "AND balance_after > 0 ORDER BY closed_at DESC LIMIT 1").fetchone()
            conn.close()
            if row and row[0]:
                bal = float(row[0])
        except Exception:
            pass

    if bal is not None:
        _BAL_CACHE["v"] = bal
        _BAL_CACHE["ts"] = now
    return bal


def _trade_shape(sig: dict) -> dict:
    """Turn a signal's entry/stop/target into a full order ticket: position size,
    cost, breakeven, liquidation, and the leverage-amplified account swing. Sized
    all-in (margin = full account) at LENS_LEVERAGE; tune via .env:
    LENS_ACCOUNT_USD, LENS_LEVERAGE, LENS_FEE_RT_PCT.

    Account size = your real synced balance. LENS_ACCOUNT_USD, if explicitly set,
    is an override for what-if sizing; the $1000 default is only used when there
    is no real balance and no override."""
    entry = float(sig["entry_price"])
    stop = float(sig["stop_price"])
    tgt = float(sig["target_price"])
    long_ = sig["direction"] == "long"

    override = _envcfg("LENS_ACCOUNT_USD", "")
    if override:
        acct = float(override)
    else:
        acct = _live_account()
        if acct is None:
            acct = 1000.0
    lev = float(_envcfg("LENS_LEVERAGE", "10"))
    fee_rt = float(_envcfg("LENS_FEE_RT_PCT", "0.30")) / 100.0   # round-trip fraction

    win_move = abs(tgt - entry) / entry          # underlying move, fraction
    loss_move = abs(entry - stop) / entry

    margin = acct                                # all-in single position
    notional = margin * lev
    size_btc = notional / entry if entry else 0
    cost_btc = margin / entry if entry else 0
    fee_usd = notional * fee_rt                  # round-trip fee in $ ("hurdle")

    breakeven = entry * (1 + fee_rt) if long_ else entry * (1 - fee_rt)
    liq = entry * (1 - 1 / lev + MM_RATE) if long_ else entry * (1 + 1 / lev - MM_RATE)
    liq = liq if liq and liq > 0 else None

    reward_usd = notional * win_move - fee_usd
    risk_usd = notional * loss_move + fee_usd

    return {
        "entry": entry, "stop": stop, "target": tgt, "long": long_,
        "account": acct, "leverage": lev, "fee_rt_pct": fee_rt * 100,
        "size_btc": size_btc, "cost_btc": cost_btc, "margin_usd": margin,
        "notional": notional, "hurdle_usd": fee_usd,
        "breakeven": breakeven, "liq": liq,
        "win_move_pct": win_move * 100, "loss_move_pct": loss_move * 100,
        "reward_usd": reward_usd, "risk_usd": risk_usd,
        "gain_pct": reward_usd / acct * 100 if acct else 0,
        "loss_pct": risk_usd / acct * 100 if acct else 0,
        "rr": round(abs(tgt - entry) / abs(entry - stop), 2) if entry != stop else 0,
    }


def _alert_message(sig: dict, price: float = None) -> tuple[str, str, str]:
    """Build (title, body, tag-emoji) for a setup push. A deliberately lean
    lock-screen ticket: identity, the three levels, win/lose balance, notional,
    leverage, risk — enough to decide TAKE/SKIP and place the order. The full
    breakdown (breakeven, liquidation, Kelly, drift) lives on /desk. Title stays
    ASCII (ntfy headers are latin-1); colour emoji rides the Tags header; the
    UTF-8 body carries the per-line emoji and ₿/×/− glyphs."""
    s = _trade_shape(sig)
    setup = sig.get("trigger_type", "?")
    name = SETUP_NAMES.get(setup, setup)
    long_ = s["long"]
    arrow = "▲" if long_ else "▼"
    side = "LONG" if long_ else "SHORT"
    tag = "green_circle" if long_ else "red_circle"
    acct = s["account"]

    def m(x):
        return f"{x:,.0f}" if x is not None else "—"

    MINUS = "−"
    head_emoji = "\U0001F7E2" if long_ else "\U0001F534"   # 🟢 / 🔴
    win_bal = acct + s["reward_usd"]
    lose_bal = acct - s["risk_usd"]

    W = 13   # label column width — values line up regardless of label length
    def L(em, lab, val):
        return f"{em} {lab:<{W}}{val}\n"

    title = f"{setup} {side} BTC {m(s['entry'])}"
    body = (
        f"{head_emoji} {setup} · {side} · BTC/USD {arrow}\n"
        f"\U0001F9E0 {name}\n"                                                               # 🧠
        "\n"
        + L("\U0001F4E5", "Entry (in)", m(s["entry"]))                                       # 📥
        + L("\U0001F3AF", "TP  (out)", f"{m(s['target'])} · +{s['win_move_pct']:.2f}%")      # 🎯
        + L("\U0001F6D1", "SL  (out)", f"{m(s['stop'])} · {MINUS}{s['loss_move_pct']:.2f}%")  # 🛑
        + "\n"
        + L("\U0001F4C8", "Win bal", f"${m(win_bal)}  (+${m(s['reward_usd'])})")             # 📈
        + L("\U0001F4C9", "Lose bal", f"${m(lose_bal)}  ({MINUS}${m(s['risk_usd'])})")       # 📉
        + "\n"
        + L("\U0001F4E6", "Notional", f"${m(s['notional'])}")                                # 📦
        + L("⚡", "Leverage", f"{s['leverage']:.0f}×")                              # ⚡
        + L("\U0001F6A6", "Risk", f"${m(s['risk_usd'])} · {s['loss_pct']:.1f}%")             # 🚦
        + "\n"
        + "\U0001F4DD /desk for the full ticket"                                             # 📝
    )
    return title, body, tag


def _notify(title: str, body: str, signal_id: str = None, tags: str = None) -> bool:
    """Push to phone via ntfy.sh if LENS_NTFY_TOPIC is set (env or .env).

    If signal_id is given, attach TAKE / SKIP action buttons that POST the
    approve/reject decision straight to the LENS server. The phone's ntfy app
    makes the HTTP request, so the target must be reachable from the phone:
    LENS_BASE_URL (default the LAN address) — works on home wifi; for mobile
    data point it at a public tunnel.
    """
    import os
    import urllib.request
    cfg = {"LENS_NTFY_TOPIC": os.environ.get("LENS_NTFY_TOPIC"),
           "LENS_NTFY_SERVER": os.environ.get("LENS_NTFY_SERVER"),
           "LENS_NTFY_TOKEN": os.environ.get("LENS_NTFY_TOKEN"),
           "LENS_NTFY_USER": os.environ.get("LENS_NTFY_USER"),
           "LENS_NTFY_PASS": os.environ.get("LENS_NTFY_PASS"),
           "LENS_BASE_URL": os.environ.get("LENS_BASE_URL")}
    if not all(cfg.values()):
        try:
            with open(ENV_FILE) as f:
                for line in f:
                    for k in cfg:
                        if not cfg[k] and line.startswith(k + "="):
                            cfg[k] = line.split("=", 1)[1].strip()
        except OSError:
            pass
    topic = cfg["LENS_NTFY_TOPIC"]
    if not topic:
        return False
    server = (cfg["LENS_NTFY_SERVER"] or "https://ntfy.sh").rstrip("/")
    # HTTP headers are latin-1 only; ntfy title may carry em dash / unicode.
    safe_title = title.replace("—", "-").replace("–", "-")
    safe_title = safe_title.encode("ascii", "replace").decode("ascii")
    # notify.restedpc.com is behind Cloudflare; default urllib UA is 403'd (err 1010).
    headers = {"Title": safe_title, "Priority": "high",
               "Tags": tags or "chart_with_upwards_trend",
               "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LENS/3.0"}
    if signal_id:
        base_url = (cfg["LENS_BASE_URL"] or "http://192.168.1.47:8765").rstrip("/")
        decide = f"{base_url}/api/signals/{signal_id}/decide"
        # ntfy http action: the request is made by the phone app, so base_url
        # must be reachable from the phone. ASCII labels only (header is latin-1).
        # Approving requires your_conviction (1-5) — captured by the button, so
        # the conviction-WR metric stays honest. Body wrapped in single quotes
        # so the JSON comma needs no escaping. Max 3 actions per ntfy message.
        def _act(label, body):
            return (f"http, {label}, {decide}, method=POST, "
                    f"headers.Content-Type=application/json, "
                    f"body='{body}', clear=true")
        actions = "; ".join([
            _act("TAKE A+", '{"status":"approved","your_conviction":5}'),
            _act("TAKE",    '{"status":"approved","your_conviction":3}'),
            _act("SKIP",    '{"status":"rejected","rejection_reason":"skipped from phone"}'),
        ])
        headers["Actions"] = actions.encode("ascii", "replace").decode("ascii")
    if cfg["LENS_NTFY_USER"] and cfg["LENS_NTFY_PASS"]:
        import base64
        creds = f"{cfg['LENS_NTFY_USER']}:{cfg['LENS_NTFY_PASS']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(creds).decode()
    elif cfg["LENS_NTFY_TOKEN"]:
        headers["Authorization"] = f"Bearer {cfg['LENS_NTFY_TOKEN']}"
    req = urllib.request.Request(
        f"{server}/{topic}", data=body.encode(), headers=headers)
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except OSError:
        return False


def run_scan_cli():
    """Hourly cron entry point: scan, emit signals, notify, tag trades, expire stale.

    Run from repo root: python3 -m app.setups
    """
    from .database import expire_stale_signals, init_db
    init_db()
    scan = scan_latest()                       # still drives /desk checklists + scoreboard
    emitted = emit_board_signals()             # board-driven emit (per-strategy geometry)
    for s in emitted:
        if s["status"] == "pending":
            title, body, tag = _alert_message(s)
            _notify(title, body, signal_id=s["signal_id"], tags=tag)
    tags = backfill_setup_tags(only_untagged=True)
    expired = expire_stale_signals(older_than_minutes=180)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    names = [f"{s['signal_id']}:{s['status']}" for s in emitted] or ["none"]
    from .strategy_eval import tradeable
    book = [b["name"].split(" ")[0] for b in tradeable("hedge")]
    print(f"[{stamp}] bar={scan['bar_ts']} close={scan['close']} rsi={scan['rsi']} "
          f"kz={scan['killzone']} book={book} "
          f"signals={','.join(names)} tagged={tags['tagged']} expired={expired}")


def setup_scoreboard() -> dict:
    """Realized stats per setup_tag family, halves split for drift checks."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT setup_tag, pnl, opened_at FROM trades "
        "WHERE closed_at IS NOT NULL AND pnl IS NOT NULL AND setup_tag IS NOT NULL "
        "ORDER BY opened_at"
    ).fetchall()
    conn.close()

    def family(tag):
        if tag.startswith("VETO:"):
            return "VETO"
        if "|VETO:" in tag:
            return tag.split("|")[0] + "(vetoed)"
        return tag

    groups: dict[str, list] = {}
    for tag, pnl, opened in rows:
        groups.setdefault(family(tag), []).append((pnl, opened))

    out = {}
    for fam, items in sorted(groups.items()):
        n = len(items)
        wins = sum(1 for p, _ in items if p > 0)
        half = n // 2
        halves = []
        for part in (items[:half], items[half:]):
            if part:
                halves.append(round(sum(1 for p, _ in part if p > 0) / len(part) * 100))
        out[fam] = {
            "n": n,
            "wr": round(wins / n * 100, 1) if n else None,
            "pnl": round(sum(p for p, _ in items), 2),
            "exp": round(sum(p for p, _ in items) / n, 2) if n else None,
            "wr_halves": halves,
        }
    return out


if __name__ == "__main__":
    run_scan_cli()
