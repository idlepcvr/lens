#!/usr/bin/env python3
"""
DAILY_BREAK_v1 — Python backtester: fixed 3R vs structure-trailing vs pyramiding

Spec: NEXT_SESSION.md (2026-07-14, every design call answered there — D1..D8).
This is backtest-only strategy R&D. It is NOT a live change and NOT a reason to
trade: measured live edge is −6.6%/mo and the #1 lever is discipline, not exits.

Variants (D3):
  A    fixed 3R take-profit (the designed baseline, the control)
  B    pure structure trail, no TP
  B+P  pure trail + pyramiding
  C    50% off at +2R, trail the rest
  C+P  C + pyramiding on the remainder

Replicates strategy.pine exactly: prev-day H/L break with the [1] first-cross
guard, volume > 1.4x 20-SMA, min prev-day range 0.4%, daily-200-EMA bias,
weekly-trend gate, skip Saturday, skip 02/11 UTC, 07-21 UTC session, 60-min
cooldown, confluence sizing tiers.

Perp mechanics that equity-market Darvas doesn't have to pay for (D5): fees on
notional per side per unit, Bybit historical funding every 8h, and a liquidation
guard so the exchange is never the stop.

Run: python3 strategies/DAILY_BREAK_v1/backtest.py
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ── Pine defaults (strategy.pine inputs — do not drift from these) ────────────
VOL_MULT      = 1.4      # volume spike x 20-bar SMA
MIN_RANGE_PCT = 0.4      # min prev-day range as % of price
ATR_LEN       = 14
ATR_SL        = 1.5      # stop = ATR x this
RR_TARGET     = 3.0      # variant A take-profit, in R
HTF_EMA_LEN   = 200      # daily EMA bias gate
SKIP_SAT      = True
SKIP_BAD_HRS  = (2, 11)
SESS_START    = 7        # 07:00-21:00 UTC only
SESS_END      = 21
COOLDOWN_MIN  = 60

# ── Perp mechanics (D5) ──────────────────────────────────────────────────────
FEE_PER_SIDE  = 0.0005   # 0.05% of notional, Bybit taker-ish
MAINT_MARGIN  = 0.005    # ~0.5%, for the liquidation estimate
LIQ_GUARD     = 0.8      # stop distance must stay under 0.8 x liq distance
FLAT_FUNDING  = 0.0001   # fallback: +0.01% / 8h, longs pay. NOT zero, on purpose.
INITIAL_CAP   = 1000.0

# Confluence sizing tiers, applied to the INITIAL unit (adds inherit leverage).
TIERS = {4: (10.0, 0.05), 3: (7.0, 0.03), 0: (5.0, 0.02)}   # conf -> (lev, size%)

MONTHS        = 32       # 24-month trade window + ~200 daily bars of warmup
WINDOW_MONTHS = 24


@dataclass
class Params:
    """One backtest cell. The sweep (D8) varies be_at_r, trail_buf, partial_at_r."""
    variant: str                       # A | B | B+P | C | C+P
    be_at_r: float | None = 1.0        # breakeven-plus trigger, None disables (D2)
    trail_buf: float = 0.25            # box floor minus this x ATR(14,1h) (D1)
    partial_at_r: float = 2.0          # C: take 50% off here
    max_adds: int = 2                  # D4
    add_frac: float = 0.5              # D4: add is 0.5 x initial unit

    @property
    def trails(self) -> bool:
        return self.variant != "A"

    @property
    def pyramids(self) -> bool:
        return self.variant.endswith("+P")

    @property
    def partials(self) -> bool:
        return self.variant.startswith("C")


# ── data ──────────────────────────────────────────────────────────────────────

def load_bars(months: int = MONTHS, timeframe: str = "1h") -> pd.DataFrame:
    """OHLCV from BYBIT (D6). Not Kraken: its OHLC endpoint caps at ~720
    candles regardless of `since`, and 24 months of 1h needs ~17,500 bars.
    Reuses the app's cached loader so a sweep doesn't refetch 17k bars per cell."""
    from app.backtest_engine import load_ohlcv
    df = load_ohlcv(symbol="BTC/USDT:USDT", timeframe=timeframe,
                    months=months, exchange_id="bybit")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()      # Wilder, = ta.atr


def build_frame(df: pd.DataFrame, req_weekly: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1h frame with every Pine gate precomputed, plus the daily frame the trail
    uses as its box.

    Higher-timeframe values are taken from the last COMPLETED daily/weekly bar.
    Pine's request.security with lookahead_off is subtler than that on realtime
    bars; the completed-bar reading is the conservative one and cannot look
    ahead, so TradingView's own tester may differ slightly. Honesty over match.
    """
    d = df.copy()

    d["atr"] = _atr(d, ATR_LEN)
    d["vol_sma"] = d["volume"].rolling(20).mean()
    d["vol_spike"] = d["volume"] > d["vol_sma"] * VOL_MULT

    # ── daily box + bias, shifted so a bar only ever sees completed days ──
    day = d.index.floor("D")
    daily = d.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()
    daily["ema200"] = daily["close"].ewm(span=HTF_EMA_LEN, adjust=False).mean()
    prev = pd.DataFrame({
        "prev_high": daily["high"].shift(1),
        "prev_low": daily["low"].shift(1),
        "prev_ema200": daily["ema200"].shift(1),
        "daily_bars": np.arange(len(daily)),
    }, index=daily.index)
    d = d.join(prev, on=day)

    # ── weekly trend, from the last completed week (Monday-anchored, as TV) ──
    wk_start = day - pd.to_timedelta(day.dayofweek, unit="D")
    weekly = d.groupby(wk_start)["close"].last().to_frame("close")
    weekly["sma10"] = weekly["close"].rolling(10).mean()
    pc, ps = weekly["close"].shift(1), weekly["sma10"].shift(1)
    weekly["trend"] = np.where(pc > ps * 1.02, "up",
                               np.where(pc < ps * 0.98, "down", "range"))
    d["wk_trend"] = pd.Series(wk_start, index=d.index).map(weekly["trend"])

    # ── breakout with the [1] first-cross guard ──
    d["range_ok"] = (d["prev_high"] - d["prev_low"]) / d["close"] * 100 >= MIN_RANGE_PCT
    prev_close = d["close"].shift(1)
    d["long_break"] = (d["close"] > d["prev_high"]) & (prev_close <= d["prev_high"]) & d["range_ok"]
    d["short_break"] = (d["close"] < d["prev_low"]) & (prev_close >= d["prev_low"]) & d["range_ok"]

    # ── discipline ──
    hour, dow = d.index.hour, d.index.dayofweek
    d["pass_disc"] = ((dow != 5) if SKIP_SAT else np.ones(len(d), bool)) \
        & (~np.isin(hour, SKIP_BAD_HRS)) \
        & (hour >= SESS_START) & (hour < SESS_END)

    # ── bias gates ──
    d["htf_bull"] = d["close"] > d["prev_ema200"]
    d["htf_bear"] = d["close"] < d["prev_ema200"]
    # reqWeekly is a Pine input, and BASELINE.md asks for both columns. The
    # weekly term still feeds confluence scoring either way — the gate decides
    # whether a signal fires, the score decides how big it is.
    wk_long = (d["wk_trend"] == "up") if req_weekly else True
    wk_short = (d["wk_trend"] == "down") if req_weekly else True
    d["long_ok"] = d["long_break"] & d["vol_spike"] & d["pass_disc"] \
        & d["htf_bull"] & wk_long
    d["short_ok"] = d["short_break"] & d["vol_spike"] & d["pass_disc"] \
        & d["htf_bear"] & wk_short

    # ── confluence (Pine confScore): base 1 + vol + htf + weekly + session ──
    active = ((hour >= 8) & (hour < 21))               # london or ny
    d["conf_long"] = (1 + d["vol_spike"].astype(int) + d["htf_bull"].astype(int)
                      + (d["wk_trend"] == "up").astype(int) + active.astype(int))
    d["conf_short"] = (1 + d["vol_spike"].astype(int) + d["htf_bear"].astype(int)
                       + (d["wk_trend"] == "down").astype(int) + active.astype(int))

    return d, daily


def load_funding(start: datetime, end: datetime) -> dict:
    """Bybit historical funding, ts(ms floor to hour) -> rate. Longs PAY positive.

    Falls back to a flat FLAT_FUNDING if the fetch fails — never to zero. A
    multi-day 10x long that pays no funding is a fantasy, and the whole question
    this backtest answers is whether trail-extended holds survive the carry."""
    try:
        import ccxt
        ex = ccxt.bybit({"enableRateLimit": True})
        since = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        out = {}
        while since < end_ms:
            batch = ex.fetch_funding_rate_history("BTC/USDT:USDT", since=since, limit=200)
            if not batch:
                break
            for f in batch:
                out[f["timestamp"] // 3_600_000 * 3_600_000] = f["fundingRate"]
            nxt = batch[-1]["timestamp"] + 1
            if nxt <= since:
                break
            since = nxt
        if out:
            print(f"[funding] {len(out)} Bybit funding stamps "
                  f"(mean {np.mean(list(out.values()))*100:+.4f}%/8h)")
            return out
    except Exception as e:                              # noqa: BLE001
        print(f"[funding] fetch failed ({e}) — falling back to flat "
              f"{FLAT_FUNDING*100:+.3f}%/8h")
    return {}


# ── the position ─────────────────────────────────────────────────────────────

@dataclass
class Unit:
    entry: float
    notional: float
    fee_paid: float


@dataclass
class Position:
    long: bool
    entry_ts: pd.Timestamp
    units: list = field(default_factory=list)
    stop: float = 0.0
    tp: float | None = None
    r_money: float = 0.0          # R of the ORIGINAL unit, in currency
    r_dist: float = 0.0           # |entry - initial stop|, price units
    orig_entry: float = 0.0
    leverage: float = 5.0
    adds: int = 0
    funding_paid: float = 0.0
    fees_paid: float = 0.0
    realized: float = 0.0         # banked from partials
    mfe_r: float = 0.0
    be_done: bool = False
    partial_done: bool = False

    @property
    def notional(self) -> float:
        return sum(u.notional for u in self.units)

    @property
    def avg_entry(self) -> float:
        n = self.notional
        return sum(u.entry * u.notional for u in self.units) / n if n else 0.0

    def pnl_at(self, price: float) -> float:
        """Gross P&L of all open units at `price`, before exit fees."""
        s = 0.0
        for u in self.units:
            move = (price - u.entry) / u.entry if self.long else (u.entry - price) / u.entry
            s += u.notional * move
        return s

    def net_if_stopped(self) -> float:
        """Total P&L if the stop fills now: open units + banked partials, with
        every entry fee, the exit fee on what's still open, and funding already
        accrued. This is the number the risk-ledger invariant (D4) tests."""
        exit_fee = self.notional * FEE_PER_SIDE
        return (self.realized + self.pnl_at(self.stop)
                - exit_fee - self.fees_paid - self.funding_paid)


def _tier(conf: int) -> tuple[float, float]:
    for need in (4, 3, 0):
        if conf >= need:
            return TIERS[need]
    return TIERS[0]


def _liq_ok(stop_dist_pct: float, leverage: float) -> bool:
    """The exchange must never be the stop. At 10x isolated, liquidation sits
    ~1/lev - maintenance away; the stop has to be comfortably inside it."""
    liq_dist = 1.0 / leverage - MAINT_MARGIN
    return stop_dist_pct < LIQ_GUARD * liq_dist


# ── engine ───────────────────────────────────────────────────────────────────

def run(d: pd.DataFrame, daily: pd.DataFrame, p: Params,
        funding: dict, start_i: int) -> pd.DataFrame:
    equity = INITIAL_CAP
    trades: list[dict] = []
    pos: Position | None = None
    last_sig_ts: pd.Timestamp | None = None
    invariant_blocks = 0
    liq_blocks = 0

    idx = d.index
    day_low = d["low"].groupby(idx.floor("D")).min()
    day_high = d["high"].groupby(idx.floor("D")).max()

    for i in range(start_i, len(d)):
        row = d.iloc[i]
        ts = idx[i]

        # ── manage an open position ──────────────────────────────────────────
        if pos is not None:
            # 1. funding first: it accrues whether or not this bar exits us.
            if ts.hour in (0, 8, 16):
                rate = funding.get(int(ts.timestamp()) // 3600 * 3_600_000, FLAT_FUNDING)
                # long pays a positive rate, short receives it
                pos.funding_paid += pos.notional * (rate if pos.long else -rate)

            hit_stop = row["low"] <= pos.stop if pos.long else row["high"] >= pos.stop
            hit_tp = (pos.tp is not None and
                      (row["high"] >= pos.tp if pos.long else row["low"] <= pos.tp))

            # 2. stop before everything else (D6): when a bar contains both the
            #    stop and a favourable event, we never assume the good one first.
            exit_px = pos.stop if hit_stop else (pos.tp if hit_tp else None)
            if exit_px is not None:
                gross = pos.pnl_at(exit_px)
                exit_fee = pos.notional * FEE_PER_SIDE
                net = pos.realized + gross - exit_fee - pos.fees_paid - pos.funding_paid
                equity += net
                trades.append({
                    "ts": pos.entry_ts, "exit_ts": ts,
                    "direction": "long" if pos.long else "short",
                    "entry": pos.orig_entry, "exit": exit_px,
                    "outcome": "win" if net > 0 else "loss",
                    "net": net, "r": net / pos.r_money if pos.r_money else 0.0,
                    "mfe_r": pos.mfe_r,
                    "fees": pos.fees_paid + exit_fee, "funding": pos.funding_paid,
                    "adds": pos.adds, "equity": equity,
                    "hours": (ts - pos.entry_ts).total_seconds() / 3600,
                })
                pos = None
            else:
                # 3. favourable excursion, then the partial, then the ratchets.
                best = row["high"] if pos.long else row["low"]
                pos.mfe_r = max(pos.mfe_r, pos.pnl_at(best) / pos.r_money) if pos.r_money else 0.0

                if p.partials and not pos.partial_done:
                    trig = (pos.orig_entry + p.partial_at_r * pos.r_dist if pos.long
                            else pos.orig_entry - p.partial_at_r * pos.r_dist)
                    if (row["high"] >= trig) if pos.long else (row["low"] <= trig):
                        half = pos.notional * 0.5
                        move = ((trig - pos.avg_entry) / pos.avg_entry if pos.long
                                else (pos.avg_entry - trig) / pos.avg_entry)
                        pos.realized += half * move
                        pos.fees_paid += half * FEE_PER_SIDE
                        for u in pos.units:
                            u.notional *= 0.5
                        pos.partial_done = True

                if p.trails:
                    # D2 breakeven-plus: at +be_at_r the stop covers entry + fees.
                    if p.be_at_r is not None and not pos.be_done:
                        trig = (pos.orig_entry + p.be_at_r * pos.r_dist if pos.long
                                else pos.orig_entry - p.be_at_r * pos.r_dist)
                        if (row["high"] >= trig) if pos.long else (row["low"] <= trig):
                            fee_cushion = pos.avg_entry * FEE_PER_SIDE * 2
                            be = (pos.avg_entry + fee_cushion if pos.long
                                  else pos.avg_entry - fee_cushion)
                            pos.stop = max(pos.stop, be) if pos.long else min(pos.stop, be)
                            pos.be_done = True

                    # D1 box: on the first bar of a new UTC day, the day that just
                    # closed IS the box. Ratchet only — the stop never widens.
                    if i > 0 and idx[i - 1].floor("D") != ts.floor("D"):
                        box = idx[i - 1].floor("D")
                        buf = p.trail_buf * row["atr"]
                        if pos.long and day_low.get(box, np.nan) - buf > pos.stop:
                            pos.stop = day_low[box] - buf
                        elif not pos.long and day_high.get(box, np.nan) + buf < pos.stop:
                            pos.stop = day_high[box] + buf

                # 4. pyramiding (D4): a NEW signal in the same direction, and only
                #    if the risk ledger says the trade's worst case still hasn't
                #    grown past what was risked at entry.
                fires = row["long_ok"] if pos.long else row["short_ok"]
                if p.pyramids and fires and pos.adds < p.max_adds:
                    add = _try_add(pos, row, p)
                    if add == "invariant":
                        invariant_blocks += 1
                    elif add == "liq":
                        liq_blocks += 1

        # ── open a new position ──────────────────────────────────────────────
        if pos is None and (row["long_ok"] or row["short_ok"]):
            if last_sig_ts is not None and (ts - last_sig_ts) < timedelta(minutes=COOLDOWN_MIN):
                continue
            long_ = bool(row["long_ok"])
            entry, atr = row["close"], row["atr"]
            if not np.isfinite(atr) or atr <= 0:
                continue
            stop = entry - atr * ATR_SL if long_ else entry + atr * ATR_SL
            conf = int(row["conf_long"] if long_ else row["conf_short"])
            lev, size_pct = _tier(conf)

            # Liquidation guard: step DOWN the leverage tiers rather than accept
            # a stop the exchange would reach first. Never let liq be the stop.
            stop_dist_pct = abs(entry - stop) / entry
            while not _liq_ok(stop_dist_pct, lev) and lev > 5.0:
                lev = 7.0 if lev == 10.0 else 5.0
            if not _liq_ok(stop_dist_pct, lev):
                continue                                # unsizeable, skip the trade

            notional = equity * size_pct * lev
            fee = notional * FEE_PER_SIDE
            pos = Position(
                long=long_, entry_ts=ts, stop=stop, orig_entry=entry,
                tp=(entry + atr * ATR_SL * RR_TARGET if long_
                    else entry - atr * ATR_SL * RR_TARGET) if p.variant == "A" else None,
                r_dist=abs(entry - stop), r_money=notional * stop_dist_pct,
                leverage=lev, fees_paid=fee,
                units=[Unit(entry=entry, notional=notional, fee_paid=fee)],
            )
            last_sig_ts = ts

    df = pd.DataFrame(trades)
    df.attrs["invariant_blocks"] = invariant_blocks
    df.attrs["liq_blocks"] = liq_blocks
    return df


def _try_add(pos: Position, row, p: Params) -> str:
    """Attempt one pyramid unit. Returns 'ok' | 'invariant' | 'liq'.

    The invariant is what separates pyramiding from martingale-adjacent size
    creep: an add is permitted only if, at the CURRENT trailed stop, the whole
    position's P&L-if-stopped (every unit, entry fees + exit fee + funding
    accrued) is still >= -1R of the ORIGINAL unit. Adds are financed by locked-in
    trend profit, never by new account risk.
    """
    entry = row["close"]
    dist_pct = abs(entry - pos.stop) / entry

    # Size in risk terms (D4: 0.5 x the initial unit): the add's own worst case
    # at the shared stop is half an original R. Once the stop is at or past the
    # add price the unit cannot lose, so the 0.5x notional cap governs instead —
    # otherwise "size to 0.5R" divides by ~zero and mints an unbounded unit.
    cap = pos.units[0].notional * p.add_frac
    stop_beyond = (pos.stop >= entry) if pos.long else (pos.stop <= entry)
    add_notional = cap if (stop_beyond or dist_pct <= 0) else min(
        cap, pos.r_money * p.add_frac / dist_pct)
    if add_notional <= 0:
        return "invariant"

    # Adds raise the average entry, which drags liquidation closer. Re-check.
    trial_notional = pos.notional + add_notional
    trial_avg = ((pos.avg_entry * pos.notional + entry * add_notional) / trial_notional)
    if not _liq_ok(abs(trial_avg - pos.stop) / trial_avg, pos.leverage):
        return "liq"

    add_fee = add_notional * FEE_PER_SIDE
    pos.units.append(Unit(entry=entry, notional=add_notional, fee_paid=add_fee))
    pos.fees_paid += add_fee

    # The invariant, asserted on the position as it would stand WITH the add.
    if pos.net_if_stopped() < -pos.r_money:
        pos.units.pop()
        pos.fees_paid -= add_fee
        return "invariant"

    pos.adds += 1
    return "ok"


# ── reporting ────────────────────────────────────────────────────────────────

def metrics(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0}
    wins, losses = t[t["net"] > 0], t[t["net"] <= 0]
    gross_p, gross_l = wins["net"].sum(), abs(losses["net"].sum())
    curve = np.concatenate([[INITIAL_CAP], t["equity"].values])
    dd = (curve - np.maximum.accumulate(curve)) / np.maximum.accumulate(curve) * 100
    return {
        "n": len(t),
        "wr": len(wins) / len(t) * 100,
        "pf": gross_p / gross_l if gross_l > 0 else float("inf"),
        "net": t["net"].sum(),
        "max_dd": abs(dd.min()),
        "avg_hold_h": t["hours"].mean(),
        "fees": t["fees"].sum(),
        "funding": t["funding"].sum(),
        # How much of the best unrealized R each trade handed back. This is the
        # number that decides trail-vs-fixed-TP: a trail's whole cost is giveback.
        "giveback_r": (t["mfe_r"] - t["r"]).mean(),
        "avg_r": t["r"].mean(),
        "avg_win_r": wins["r"].mean() if len(wins) else 0.0,
        "avg_loss_r": losses["r"].mean() if len(losses) else 0.0,
        "adds": int(t["adds"].sum()),
    }


def print_table(rows: dict[str, dict]) -> None:
    print("\n" + "=" * 108)
    print("  DAILY_BREAK_v1 — exit mechanics, net of fees + funding")
    print("=" * 108)
    hdr = (f"  {'variant':6} {'n':>4} {'WR%':>6} {'net PF':>7} {'net':>9} "
           f"{'maxDD%':>7} {'avg R':>6} {'hold h':>7} {'fees':>8} {'funding':>9} "
           f"{'givebk R':>9} {'adds':>5}")
    print(hdr)
    print("  " + "-" * 104)
    for name, m in rows.items():
        if m.get("n", 0) == 0:
            print(f"  {name:6} {'—  no trades':>40}")
            continue
        print(f"  {name:6} {m['n']:4d} {m['wr']:6.1f} {m['pf']:7.2f} {m['net']:9.0f} "
              f"{m['max_dd']:7.1f} {m['avg_r']:6.2f} {m['avg_hold_h']:7.1f} "
              f"{m['fees']:8.0f} {m['funding']:9.0f} {m['giveback_r']:9.2f} {m['adds']:5d}")
    print("=" * 108)


def verdict(rows: dict[str, dict]) -> str:
    """D7, written against the criteria and nothing else. 'fixed 3R stands' is a
    fully successful outcome — record it and stop. No parameter-fishing."""
    a = rows.get("A", {})
    if a.get("n", 0) < 30:
        return (f"INSUFFICIENT SAMPLE — variant A closed {a.get('n', 0)} trades in the "
                f"window, under the n>=30 floor. Full stop: no variant is adoptable "
                f"and no comparison below is trustworthy.")

    # D7 compares each variant against 1.2x A's PF. That test only means what it
    # was meant to mean while A is profitable: if A's PF is below 1, "1.2x A" is
    # a bar under breakeven, and a variant could clear it while still losing
    # money every month. Say so instead of reporting the ratio as a result.
    dead = a["pf"] < 1.0
    lines = []
    for name, m in rows.items():
        if name == "A":
            continue
        if m.get("n", 0) < 30:
            lines.append(f"{name}: insufficient sample (n={m.get('n', 0)})")
            continue
        pf_ok = m["pf"] >= 1.2 * a["pf"]
        dd_ok = m["max_dd"] <= 1.25 * a["max_dd"]
        lines.append(
            f"{name}: PF {m['pf']:.2f} vs required {1.2*a['pf']:.2f} "
            f"{'OK' if pf_ok else 'FAIL'} · maxDD {m['max_dd']:.1f}% vs allowed "
            f"{1.25*a['max_dd']:.1f}% {'OK' if dd_ok else 'FAIL'} · "
            f"{'ADOPT' if (pf_ok and dd_ok) else 'reject'}")
    winners = [n for n, m in rows.items()
               if n != "A" and m.get("n", 0) >= 30
               and m["pf"] >= 1.2 * a["pf"] and m["max_dd"] <= 1.25 * a["max_dd"]]
    if dead:
        best = max((n for n in rows if rows[n].get("n", 0) >= 30),
                   key=lambda n: rows[n]["pf"])
        head = (f"PREMISE FAILS — the control is not profitable (variant A net PF "
                f"{a['pf']:.2f}, WR {a['wr']:.1f}%, net {a['net']:+.0f} on "
                f"{a['n']} trades). Exits are not the problem here and no exit "
                f"mechanic is adoptable: the best of them ({best}, PF "
                f"{rows[best]['pf']:.2f}) still loses money. D7's PF test is "
                f"reported below for completeness, but 1.2x a losing PF is a bar "
                f"beneath breakeven and clearing it would mean nothing.")
    elif winners:
        head = f"ADOPT {', '.join(winners)} — clears D7 on PF and drawdown."
    else:
        head = "FIXED 3R STANDS — no variant clears D7."
    return head + "\n  " + "\n  ".join(lines)


def _window(d: pd.DataFrame) -> int:
    """Warmup trim (D6): the 200-EMA gate is meaningless until 200 daily bars
    exist, and the window is the last WINDOW_MONTHS after that."""
    warm = d.index[d["daily_bars"] >= HTF_EMA_LEN]
    cutoff = max(warm[0] if len(warm) else d.index[0],
                 d.index[-1] - pd.Timedelta(days=WINDOW_MONTHS * 31))
    return int(d.index.searchsorted(cutoff))


def baseline_columns() -> dict[str, dict]:
    """The three columns BASELINE.md has been waiting on since 2026-06: variant A
    at 1h with the weekly gate on and off, and at 4h. Same harness, same costs."""
    out = {}
    for label, tf, weekly in (("1h weekly-on", "1h", True),
                              ("1h weekly-off", "1h", False),
                              ("4h weekly-on", "4h", True)):
        d, daily = build_frame(load_bars(timeframe=tf), req_weekly=weekly)
        start_i = _window(d)
        funding = load_funding(d.index[start_i].to_pydatetime(),
                               d.index[-1].to_pydatetime())
        t = run(d, daily, Params(variant="A"), funding, start_i)
        m = metrics(t)
        if m.get("n"):
            m["bars_held"] = (t["hours"] / (1 if tf == "1h" else 4)).mean()
            m["per_week"] = m["n"] / max(
                (t["exit_ts"].iloc[-1] - t["ts"].iloc[0]).days / 7, 1)
            streak = mx = 0
            for o in t["outcome"]:
                streak = streak + 1 if o == "loss" else 0
                mx = max(mx, streak)
            m["max_consec_loss"] = mx
        out[label] = m
    return out


def print_baseline(cols: dict[str, dict]) -> None:
    keys = [("n", "Total trades (n)", "{:.0f}"), ("wr", "Win rate %", "{:.1f}"),
            ("pf", "Profit factor", "{:.2f}"), ("net", "Net profit", "{:+.0f}"),
            ("max_dd", "Max drawdown %", "{:.1f}"),
            ("avg_win_r", "Avg win (R)", "{:+.2f}"),
            ("avg_loss_r", "Avg loss (R)", "{:+.2f}"),
            ("avg_hold_h", "Avg hours in trade", "{:.1f}"),
            ("bars_held", "Avg bars in trade", "{:.1f}"),
            ("per_week", "Trades/week", "{:.2f}"),
            ("max_consec_loss", "Max consecutive losses", "{:.0f}")]
    names = list(cols)
    print("\n" + "=" * 72)
    print("  DAILY_BREAK_v1 — BASELINE (variant A, fixed 3R)")
    print("=" * 72)
    print(f"  {'metric':24}" + "".join(f"{n:>16}" for n in names))
    for k, label, fmt in keys:
        row = "".join(
            (fmt.format(cols[n][k]) if cols[n].get(k) is not None else "—").rjust(16)
            for n in names)
        print(f"  {label:24}" + row)
    print("=" * 72)


def main() -> None:
    if "--baseline" in sys.argv:
        print_baseline(baseline_columns())
        return

    df = load_bars()
    d, daily = build_frame(df)

    start_i = _window(d)
    print(f"[window] {d.index[start_i].date()} -> {d.index[-1].date()} "
          f"({len(d) - start_i} 1h bars, {len(daily)} daily)")

    funding = load_funding(d.index[start_i].to_pydatetime(),
                           d.index[-1].to_pydatetime())

    rows, results = {}, {}
    for v in ("A", "B", "B+P", "C", "C+P"):
        t = run(d, daily, Params(variant=v), funding, start_i)
        results[v] = t
        rows[v] = metrics(t)
        rows[v]["invariant_blocks"] = t.attrs.get("invariant_blocks", 0)
        rows[v]["liq_blocks"] = t.attrs.get("liq_blocks", 0)

    print_table(rows)
    for v in ("B+P", "C+P"):
        r = rows[v]
        print(f"  {v}: {r.get('adds', 0)} adds taken, "
              f"{r.get('invariant_blocks', 0)} blocked by the risk-ledger invariant, "
              f"{r.get('liq_blocks', 0)} by the liquidation guard")
    print("\n  VERDICT (D7)\n  " + verdict(rows))
    return rows, results


if __name__ == "__main__":
    main()
