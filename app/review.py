"""Trade review page — enriched trades with edge conditions, integrated into LENS."""

import bisect
import datetime
import json
import sqlite3
from typing import Any

from .database import DB_PATH

APR25_MS      = int(datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
STEP_4H_MS    = 14_400_000
EMA_WARMUP_4H = 100


# ── math ──────────────────────────────────────────────────────────────────────

def _ema(closes: list, period: int) -> list:
    k = 2 / (period + 1)
    result, avg = [], None
    for i, v in enumerate(closes):
        if i < period - 1:
            result.append(None)
        elif i == period - 1:
            avg = sum(closes[:period]) / period
            result.append(avg)
        else:
            avg = v * k + avg * (1 - k)
            result.append(avg)
    return result


def _rsi(closes: list, period: int = 14) -> list:
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains  = [max(0.0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
    losses = [max(0.0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
    avg_g  = sum(gains[:period])  / period
    avg_l  = sum(losses[:period]) / period
    result[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + gains[i-1])  / period
        avg_l = (avg_l * (period - 1) + losses[i-1]) / period
        result[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    return result


def _sma(closes: list, period: int) -> list:
    result, window_sum = [None] * len(closes), 0.0
    for i, v in enumerate(closes):
        window_sum += v
        if i >= period:
            window_sum -= closes[i - period]
        if i >= period - 1:
            result[i] = window_sum / period
    return result


def _bollinger(closes: list, period: int = 20, mult: float = 2.0) -> dict:
    mid = _sma(closes, period)
    upper, lower = [None] * len(closes), [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is None:
            continue
        window = closes[i - period + 1:i + 1]
        var = sum((c - mid[i]) ** 2 for c in window) / period
        sd = var ** 0.5
        upper[i], lower[i] = mid[i] + mult * sd, mid[i] - mult * sd
    return {"mid": mid, "upper": upper, "lower": lower}


def _macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    ema_f, ema_s = _ema(closes, fast), _ema(closes, slow)
    line = [None if (a is None or b is None) else a - b for a, b in zip(ema_f, ema_s)]
    # signal is an EMA of the line itself — _ema needs a value at every index it
    # touches, so feed it 0.0 where the line isn't warmed up yet and mask after
    filler = [v if v is not None else 0.0 for v in line]
    sig_raw = _ema(filler, signal)
    first_valid = next((i for i, v in enumerate(line) if v is not None), len(line))
    sig = [None if i < first_valid + signal - 1 else v for i, v in enumerate(sig_raw)]
    hist = [None if (a is None or b is None) else a - b for a, b in zip(line, sig)]
    return {"line": line, "signal": sig, "hist": hist}


def _bar_idx(ts_arr: list, target_ms: int):
    i = bisect.bisect_right(ts_arr, target_ms) - 1
    return i if i >= 0 else None


def _parse_ms(iso_str: str) -> int:
    s  = iso_str.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


# ── data ──────────────────────────────────────────────────────────────────────

def _load_ohlcv():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts, open, high, low, close, volume FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    c1h = cur.fetchall()
    warmup = APR25_MS - EMA_WARMUP_4H * STEP_4H_MS
    cur.execute("""
        SELECT ts, open, high, low, close FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='4h' AND ts >= ?
        ORDER BY ts
    """, (warmup,))
    c4h = cur.fetchall()
    conn.close()
    return c1h, c4h


# Fresh scoreboard (his call, 2026-07-12): analytics stats default to trades
# opened on/after this date — start of Q3; the old trades stay in the DB as the
# baseline (they built the filters + fee math) and are reachable with era='all'.
ERA_START = "2026-07-01"


def era_filter(era: str) -> str:
    """SQL fragment scoping a trades query to the current era ('all' = lifetime)."""
    return "" if era == "all" else f" AND opened_at >= '{ERA_START}'"


def book_filter(book: str) -> tuple:
    """(sql_fragment, params) for scoping a trades query to one book.

    `book='prop'` means EVERY prop attempt — the live eval plus its dated archives
    (`prop_arch_*`) — because prop performance only makes sense across attempts;
    a single eval is often 7 trades long. The CURRENT eval alone is /prop-ledger.
    `book='hedge'` is exact. None = every book, which is what analytics did
    unconditionally before, quietly folding prop trades into hedge stats.
    """
    if not book:
        return "", []
    if book == "prop":
        return " AND book LIKE 'prop%'", []
    return " AND book = ?", [book]


def _load_trades(book: str = None):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    bsql, bparams = book_filter(book)
    cur.execute(f"""
        SELECT id, direction, entry, exit, pnl, fees, size, leverage,
               opened_at, closed_at, notes, balance_after, balance_before, merged_manual, setup_tag,
               tp, sl, funding_cost, followed_plan, followed_strategy,
               market_type, order_type, fill_count,
               grade, conviction, emotion, mistakes, went_right, went_wrong, lesson,
               book, venue, symbol, manually_edited
        FROM trades WHERE (closed_at IS NOT NULL OR exit IS NULL) {bsql} ORDER BY opened_at
    """, list(bparams))
    rows = cur.fetchall()
    conn.close()
    return rows


# ── enrichment ────────────────────────────────────────────────────────────────

def get_enriched_trades(book: str = None) -> list:
    c1h, c4h   = _load_ohlcv()
    trades_raw = _load_trades(book)

    ts1h   = [r[0] for r in c1h]
    open1h = [r[1] for r in c1h]
    clos1h = [r[4] for r in c1h]
    rsi14  = _rsi(clos1h, 14)

    ts4h   = [r[0] for r in c4h]
    clos4h = [r[4] for r in c4h]
    ema21  = _ema(clos4h, 21)
    ema50  = _ema(clos4h, 50)

    out = []
    for row in trades_raw:
        (tid, direction, entry, exit_, pnl, fees, size, leverage,
         opened_at, closed_at, notes, bal_after, bal_before, merged_manual, setup_tag,
         tp, sl, funding_cost, followed_plan, followed_strategy,
         market_type, order_type, fill_count,
         grade, conviction, emotion, mistakes, went_right, went_wrong, lesson,
         book, venue, symbol, manually_edited) = row

        ts_e = _parse_ms(opened_at)
        ts_x = _parse_ms(closed_at) if closed_at else None
        i1   = _bar_idx(ts1h, ts_e)
        i4   = _bar_idx(ts4h, ts_e)

        bar_dir = bar_aligned = rsi_val = rsi_zone = None
        trend_4h = trend_aligned = None

        if i1 is not None and i1 < len(c1h):
            o, c   = open1h[i1], clos1h[i1]
            bar_dir    = "bull" if c >= o else "bear"
            bar_aligned = (bar_dir == "bull") == (direction == "long")
            rsi_val    = rsi14[i1]
            if rsi_val is not None:
                rsi_zone = "dip" if rsi_val < 40 else ("momentum" if rsi_val > 55 else "neutral")

        if i4 is not None and i4 < len(c4h):
            e21, e50 = ema21[i4], ema50[i4]
            if e21 and e50:
                trend_4h    = "bull" if e21 > e50 else "bear"
                trend_aligned = (trend_4h == "bull") == (direction == "long")

        move_pct = None
        if entry and exit_:
            raw = (exit_ - entry) / entry * 100
            move_pct = round(raw * (1 if direction == "long" else -1), 3)

        out.append({
            "id":             tid,
            "direction":      direction,
            "entry":          entry,
            "exit":           exit_,
            "pnl":            pnl,
            "fees":           fees,
            "size":           size,
            "leverage":       leverage,
            "opened_at":      opened_at[:19].replace("T", " "),
            # open positions have no close — they belong in the log so the plan
            # can be recorded BEFORE the outcome exists
            "closed_at":      closed_at[:19].replace("T", " ") if closed_at else "",
            "is_open":        closed_at is None,
            "notes":          notes or "",
            "balance_after":  bal_after,
            "balance_before": bal_before,
            "merged_manual":  merged_manual,
            "manually_edited": manually_edited,
            "book":           book or "hedge",
            "venue":          venue or "",
            "symbol":         symbol or "BTC/USD",
            "setup_tag":      setup_tag or "",
            "ts_entry":       ts_e // 1000,
            "ts_exit":        (ts_x // 1000) if ts_x else None,
            "bar_dir":        bar_dir,
            "bar_aligned":    bar_aligned,
            "rsi":            round(rsi_val, 1) if rsi_val else None,
            "rsi_zone":       rsi_zone,
            "trend_4h":       trend_4h,
            "trend_aligned":  trend_aligned,
            "move_pct":       move_pct,
            # breakdown extras (for the editable modal, step B)
            "tp":             tp,
            "sl":             sl,
            "funding_cost":   funding_cost,
            "market_type":    market_type,
            "order_type":     order_type,
            "fill_count":     fill_count,
            "followed_plan":     None if followed_plan     is None else bool(followed_plan),
            "followed_strategy": None if followed_strategy is None else bool(followed_strategy),
            # review layer
            "grade":          grade,
            "conviction":     conviction,
            "emotion":        emotion,
            "mistakes":       mistakes or "",
            "went_right":     went_right or "",
            "went_wrong":     went_wrong or "",
            "lesson":         lesson or "",
        })
    return out


def review_analytics(book: str = None, era: str = "current") -> dict:
    """Trade-log analytics for the /review dashboard: performance, risk-adjusted
    ratios, duration breakdown (the key edge insight — long holds carry), and
    actual-vs-model. Capital-independent where possible; cum/annual return need a
    capital base (lens_config.start_balance, only used if it looks like a real
    hedge balance, i.e. >= 100). Pass book='hedge'|'prop' to scope to one book.
    era='current' (default) = trades since ERA_START; era='all' = lifetime."""
    import math, datetime as _dt
    conn = sqlite3.connect(DB_PATH)
    bsql, bparams = book_filter(book)
    where = "closed_at IS NOT NULL AND pnl IS NOT NULL" + bsql + era_filter(era)
    rows = conn.execute(
        f"SELECT pnl, fees, direction, opened_at, closed_at FROM trades "
        f"WHERE {where} ORDER BY closed_at", list(bparams)
    ).fetchall()
    cfg = conn.execute("SELECT start_balance, win_rate, rr_ratio FROM lens_config WHERE id=1").fetchone()
    n_open = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE closed_at IS NULL" + bsql, list(bparams)
    ).fetchone()[0]
    conn.close()

    n = len(rows)
    if not n:
        return {"n": 0, "open": n_open,
                "era_start": None if era == "all" else ERA_START}

    pnls = [r[0] for r in rows]
    fees = [r[1] or 0.0 for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    nw, nl = len(wins), len(losses)
    gw, gl = sum(wins), -sum(losses)
    avg_win = gw / nw if nw else 0.0
    avg_loss = gl / nl if nl else 0.0
    total_pnl, total_fees = sum(pnls), sum(fees)

    def _mins(o, c):
        try:
            a = _dt.datetime.fromisoformat(o.replace("Z", "+00:00"))
            b = _dt.datetime.fromisoformat(c.replace("Z", "+00:00"))
            return (b - a).total_seconds() / 60.0
        except Exception:
            return None
    durs = [_mins(r[2 + 1], r[2 + 2]) for r in rows]  # opened_at idx3, closed_at idx4
    vd = [d for d in durs if d is not None and d >= 0]
    avg_dur_h = (sum(vd) / len(vd) / 60.0) if vd else None

    longs = [r[0] for r in rows if r[2] == "long"]
    shorts = [r[0] for r in rows if r[2] == "short"]
    lwr = (sum(1 for p in longs if p > 0) / len(longs) * 100) if longs else None
    swr = (sum(1 for p in shorts if p > 0) / len(shorts) * 100) if shorts else None

    # equity curve on cumulative PnL → max drawdown (€) + streaks
    eq = peak = 0.0
    maxdd_eur = 0.0
    cur_ws = cur_ls = max_ws = max_ls = 0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        maxdd_eur = max(maxdd_eur, peak - eq)
        if p > 0:
            cur_ws += 1; cur_ls = 0; max_ws = max(max_ws, cur_ws)
        else:
            cur_ls += 1; cur_ws = 0; max_ls = max(max_ls, cur_ls)

    # per-trade Sharpe/Sortino (€ cancels: mean/stdev), annualised by trades/yr
    mean_p = total_pnl / n
    var = sum((p - mean_p) ** 2 for p in pnls) / n
    sd = math.sqrt(var)
    downs = [p for p in pnls if p < mean_p]
    dvar = sum((p - mean_p) ** 2 for p in downs) / n if downs else 0.0
    dsd = math.sqrt(dvar)
    try:
        t0 = _dt.datetime.fromisoformat(rows[0][4].replace("Z", "+00:00"))
        t1 = _dt.datetime.fromisoformat(rows[-1][4].replace("Z", "+00:00"))
        span_days = max(1, (t1 - t0).days)
    except Exception:
        span_days = 365
    tpy = n / (span_days / 365.0)
    sharpe = (mean_p / sd * math.sqrt(tpy)) if sd else 0.0
    sortino = (mean_p / dsd * math.sqrt(tpy)) if dsd else 0.0

    # Capital-dependent. `lens_config.start_balance` doubles as the Goal model's
    # seed (it is literally 100.0), so a bare `>= 100` test lets a fake base through
    # and prints things like "max drawdown −9512%". A capital base is only credible
    # if the account could actually have absorbed the drawdown it took: otherwise
    # equity would have gone through zero and the trades could not have happened.
    raw_capital = cfg[0] if (cfg and cfg[0]) else None
    capital = raw_capital if (raw_capital and raw_capital > maxdd_eur) else None
    cum_return = (total_pnl / capital * 100) if capital else None
    ann_return = (cum_return / (span_days / 365.0)) if cum_return is not None else None
    # drawdown as a fraction of peak EQUITY (capital + cumulative pnl), not of the
    # starting balance — a €500 drawdown off a €10k peak is 5%, not 5% of the seed.
    maxdd_pct = None
    if capital:
        eq2 = peak_eq = capital
        dd = 0.0
        for p in pnls:
            eq2 += p
            peak_eq = max(peak_eq, eq2)
            if peak_eq > 0:
                dd = max(dd, (peak_eq - eq2) / peak_eq * 100)
        maxdd_pct = dd
    calmar = (ann_return / maxdd_pct) if (ann_return is not None and maxdd_pct) else None

    buckets = [("< 5m", 0, 5), ("5–15m", 5, 15), ("15–60m", 15, 60),
               ("1–4h", 60, 240), ("4–24h", 240, 1440), ("> 24h", 1440, float("inf"))]
    bd = []
    for lbl, lo, hi in buckets:
        idx = [i for i, d in enumerate(durs) if d is not None and lo <= d < hi]
        cnt = len(idx)
        w = sum(1 for i in idx if pnls[i] > 0)
        tot = sum(pnls[i] for i in idx)
        bd.append({"label": lbl, "n": cnt, "w": w, "l": cnt - w,
                   "total": round(tot, 2), "avg": round(tot / cnt, 2) if cnt else 0.0})

    return {
        "n": n, "open": n_open, "book": book or "all",
        "era_start": None if era == "all" else ERA_START,
        # capital_base is null when start_balance isn't credible — the UI must then
        # show "—", not a percentage derived from the Goal model's seed.
        "capital_note": None if capital else
            (f"no capital base: start_balance €{raw_capital:,.0f} is smaller than the "
             f"€{maxdd_eur:,.0f} drawdown, so % figures would be fiction"
             if raw_capital else "no start_balance set"),
        "wr": round(nw / n * 100, 1),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "rr": round(avg_win / avg_loss, 2) if avg_loss else None,
        "expectancy": round(total_pnl / n, 2),
        "total_pnl": round(total_pnl, 2), "total_fees": round(total_fees, 2),
        "avg_dur_h": round(avg_dur_h, 1) if avg_dur_h else None,
        "long_wr": round(lwr, 1) if lwr is not None else None,
        "short_wr": round(swr, 1) if swr is not None else None,
        "profit_factor": round(gw / gl, 3) if gl else None,
        "max_dd_eur": round(maxdd_eur, 2), "max_dd_pct": round(maxdd_pct, 1) if maxdd_pct is not None else None,
        "sharpe": round(sharpe, 3), "sortino": round(sortino, 3),
        "win_streak": max_ws, "loss_streak": max_ls,
        "cum_return": round(cum_return, 2) if cum_return is not None else None,
        "ann_return": round(ann_return, 1) if ann_return is not None else None,
        "calmar": round(calmar, 3) if calmar is not None else None,
        "capital_base": capital,
        "model_wr": round(cfg[1] * 100, 1) if (cfg and cfg[1]) else None,
        "model_rr": cfg[2] if cfg else None,
        "span_days": span_days,
        "duration": bd,
    }


def equity_timing(book: str = None, era: str = "current") -> dict:  # book=None → all books, to match review_analytics on the same page
    """Equity curve + time-of-play breakdowns for the /analytics page.

    Returns:
      equity  — per closed trade: {t: closed date, cum: cumulative realised P&L,
                bal: balance_after}. The sobering line from the beginning.
      daily   — end-of-day balance from daily_snapshots (the smoothed curve).
      dow     — P&L grouped by weekday of ENTRY (what days pay).
      hod     — P&L grouped by hour of ENTRY, Bangkok time (what hours pay).
      periods — avg/best P&L per day, week, month.
    Hours use a fixed UTC+7 (Bangkok has no DST, so the offset is exact).
    era='current' (default) scopes trade stats to ERA_START+; transfers and
    daily snapshots stay lifetime — cash history is not era-dependent."""
    import datetime as _dt
    conn = sqlite3.connect(DB_PATH)
    where = "closed_at IS NOT NULL AND pnl IS NOT NULL"
    bsql, params = book_filter(book)
    where += bsql + era_filter(era)
    rows = conn.execute(
        f"SELECT pnl, opened_at, closed_at, balance_after FROM trades "
        f"WHERE {where} ORDER BY closed_at", list(params)
    ).fetchall()
    is_prop = bool(book) and book.startswith("prop")
    if is_prop:
        # Prop cash reality: eval FEES are the only real money — eval P&L is paper
        # and there are no payouts yet. Hedge Kraken transfers/daily balances are
        # foreign data on this book, so they're replaced wholesale.
        snaps, dep_in, dep_out, xfers = [], 0.0, 0.0, []
        cur = conn.execute(
            "SELECT eval_name, account, fee FROM prop_eval_state WHERE id=1").fetchone()
        arch = conn.execute(
            "SELECT eval_name, account, fee, created_at FROM prop_eval_archive "
            "ORDER BY created_at").fetchall()
        attempts = ([{"ts": (a[3] or "")[:10], "eval": a[0], "account": a[1],
                      "fee": a[2] or 0.0, "status": "archived"} for a in arch]
                    + ([{"ts": None, "eval": cur[0], "account": cur[1],
                         "fee": cur[2] or 0.0, "status": "live"}] if cur else []))
        prop_cash = {"attempts": attempts,
                     "fees_total": round(sum(a["fee"] for a in attempts), 2),
                     "payouts": 0.0}
    else:
        prop_cash = None
        snaps = conn.execute(
            "SELECT snapshot_date, eur_balance FROM daily_snapshots "
            "WHERE eur_balance IS NOT NULL ORDER BY snapshot_date"
        ).fetchall()
        # EUR cash actually moved — gross deposits, gross withdrawals, and the raw
        # list for the cash-flow table. xbt/eth/fee legs are in-kind noise, EUR is the cash.
        # biz-account transfers (venue kraken_futures_biz, synced by /money) are the
        # business book — keep them out of the personal cash-flow numbers here
        dep_in, dep_out = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0),"
            "       COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0)"
            " FROM transfers WHERE asset IN ('eur','ZEUR','EUR')"
            " AND COALESCE(venue,'') <> 'kraken_futures_biz'"
        ).fetchone()
        xfers = conn.execute(
            "SELECT ts, transfer_type, amount FROM transfers "
            "WHERE asset IN ('eur','ZEUR','EUR')"
            " AND COALESCE(venue,'') <> 'kraken_futures_biz' ORDER BY ts DESC"
        ).fetchall()
    conn.close()
    if not rows:
        return {"n": 0, "era_start": None if era == "all" else ERA_START}

    BKK = _dt.timezone(_dt.timedelta(hours=7))
    def _parse(s):
        try:
            return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    # equity curve — cumulative realised P&L per trade. lightweight-charts wants a
    # strictly-ascending time axis; many trades share a second (partial closes), so
    # nudge each duplicate +1s to keep it monotonic without shifting the shape.
    eq, equity, last_ts = 0.0, [], 0
    for pnl, _o, closed, bal in rows:
        eq += pnl
        dt = _parse(closed)
        ts = int(dt.timestamp()) if dt else last_ts + 1
        if ts <= last_ts:
            ts = last_ts + 1
        last_ts = ts
        equity.append({"t": ts, "cum": round(eq, 2),
                       "bal": round(bal, 2) if bal is not None else None})

    # daily balance — midnight-UTC seconds so it shares the equity axis
    daily = []
    for d, b in snaps:
        dt = _parse(d + "T00:00:00+00:00")
        if dt:
            daily.append({"t": int(dt.timestamp()), "bal": round(b, 2)})

    # weekday & hour of entry, and per-period sums — one pass over trades
    dow_pnl = [[0.0, 0] for _ in range(7)]          # [total, count] Mon..Sun
    hod_pnl = [[0.0, 0] for _ in range(24)]
    by_day, by_week, by_month = {}, {}, {}
    for pnl, opened, _c, _b in rows:
        dt = _parse(opened)
        if dt:
            local = dt.astimezone(BKK)
            dow_pnl[local.weekday()][0] += pnl; dow_pnl[local.weekday()][1] += 1
            hod_pnl[local.hour][0] += pnl; hod_pnl[local.hour][1] += 1
            by_day[local.strftime("%Y-%m-%d")] = by_day.get(local.strftime("%Y-%m-%d"), 0.0) + pnl
            iso = local.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            by_week[wk] = by_week.get(wk, 0.0) + pnl
            mo = local.strftime("%Y-%m")
            by_month[mo] = by_month.get(mo, 0.0) + pnl

    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow = [{"label": DOW[i], "n": c, "total": round(t, 2),
            "avg": round(t / c, 2) if c else 0.0} for i, (t, c) in enumerate(dow_pnl)]
    hod = [{"hour": h, "n": c, "total": round(t, 2),
            "avg": round(t / c, 2) if c else 0.0} for h, (t, c) in enumerate(hod_pnl)]

    def _period(d):
        vals = list(d.values())
        best_k = max(d, key=d.get) if d else None
        worst_k = min(d, key=d.get) if d else None
        return {"n": len(vals), "avg": round(sum(vals) / len(vals), 2) if vals else 0.0,
                "best": {"k": best_k, "v": round(d[best_k], 2)} if best_k else None,
                "worst": {"k": worst_k, "v": round(d[worst_k], 2)} if worst_k else None}
    periods = {"day": _period(by_day), "week": _period(by_week), "month": _period(by_month)}

    cur_bal = daily[-1]["bal"] if daily else (equity[-1]["bal"] if equity else None)
    if is_prop:
        try:
            from .prop_ledger import prop_ledger_data
            cur_bal = prop_ledger_data().get("equity")   # live eval equity, USD
        except Exception:
            cur_bal = None
    return {"n": len(rows), "equity": equity, "daily": daily,
            "era_start": None if era == "all" else ERA_START,
            "dow": dow, "hod": hod, "periods": periods,
            "deposits": round(dep_in, 2), "withdrawals": round(dep_out, 2),
            "net_deposit": round(dep_in - dep_out, 2), "cur_bal": cur_bal,
            "prop_cash": prop_cash,
            "transfers": [{"ts": t[:10], "type": ty, "amount": round(a, 2)}
                          for t, ty, a in xfers],
            "cum_pnl": equity[-1]["cum"] if equity else 0.0}


SUPPORTED_TFS = ("1m", "5m", "15m", "1h", "4h", "1d")
_TF_SYMBOL = "BTC/USDT:USDT"
_TF_EXCHANGE = "bybit"


def auto_timeframe(entry_ts: int, exit_ts: int | None) -> str:
    """Duration-based default, his own suggested rule: the timeframe that
    would have actually been on screen while the trade was open, not a
    fixed 1h for a 10-minute scalp and a fixed 1h for a 3-day swing."""
    dur = (exit_ts or entry_ts) - entry_ts
    if dur <= 1800:
        return "1m"
    if dur <= 6 * 3600:
        return "5m"
    if dur <= 24 * 3600:
        return "15m"
    if dur <= 7 * 86400:
        return "1h"
    if dur <= 30 * 86400:
        return "4h"
    return "1d"


def _tf_window(timeframe: str, entry_ts: int, exit_ts: int | None,
              bars_before: int = 100, bars_after: int = 30) -> tuple:
    """5m/15m/1h/4h/1d: top up the rolling cache (cheap — it already reaches
    back to Dec 2023, so this only ever fetches the stale tail) then pull
    just the window around the trade. 1m is never cached as a rolling
    series (would mean caching years of 1-minute bars for a page most
    trades don't need it on) — instead it's fetched as a single bounded
    request for exactly this trade's window via backtest_engine.fetch_window,
    then written into the same table so revisiting the same trade is instant.

    5m/15m/1m only exist under bybit:BTC/USDT:USDT (checked live — binance
    only has 1h cached). 1h/4h/1d exist under both; bybit is used
    throughout for consistency across every timeframe.

    Returns (time[], open[], high[], low[], close[]).
    """
    from .backtest_engine import load_ohlcv, fetch_window, _tf_ms
    if timeframe not in SUPPORTED_TFS:
        raise ValueError(f"timeframe must be one of {SUPPORTED_TFS}")
    tf_sec = _tf_ms(timeframe) // 1000
    start_ms = (entry_ts - bars_before * tf_sec) * 1000
    end_ms = ((exit_ts or entry_ts) + bars_after * tf_sec) * 1000
    cache_symbol = f"{_TF_EXCHANGE}:{_TF_SYMBOL}"

    if timeframe == "1m":
        conn = sqlite3.connect(DB_PATH)
        have = conn.execute(
            "SELECT COUNT(*) FROM ohlcv_cache WHERE symbol=? AND timeframe=? AND ts>=? AND ts<=?",
            (cache_symbol, timeframe, start_ms, end_ms)).fetchone()[0]
        expected = (end_ms - start_ms) // (tf_sec * 1000)
        if have < expected * 0.9:   # under 90% covered — fetch, don't trust a partial cache
            bars = fetch_window(_TF_SYMBOL, timeframe, start_ms, end_ms, _TF_EXCHANGE)
            if bars:
                conn.executemany(
                    "INSERT OR REPLACE INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)",
                    [(cache_symbol, timeframe, b[0], b[1], b[2], b[3], b[4], b[5]) for b in bars])
                conn.commit()
        conn.close()
    else:
        load_ohlcv(symbol=_TF_SYMBOL, timeframe=timeframe, exchange_id=_TF_EXCHANGE, months=30)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT ts, open, high, low, close FROM ohlcv_cache
        WHERE symbol=? AND timeframe=? AND ts >= ? AND ts <= ?
        ORDER BY ts
    """, (f"{_TF_EXCHANGE}:{_TF_SYMBOL}", timeframe, start_ms, end_ms))
    rows = cur.fetchall()
    conn.close()
    time   = [r[0] // 1000 for r in rows]
    opens  = [r[1] for r in rows]
    highs  = [r[2] for r in rows]
    lows   = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    return time, opens, highs, lows, closes


def get_ohlcv_window(timeframe: str, entry_ts: int, exit_ts: int | None) -> list:
    time, opens, highs, lows, closes = _tf_window(timeframe, entry_ts, exit_ts)
    return [{"time": t, "open": o, "high": h, "low": l, "close": c}
            for t, o, h, l, c in zip(time, opens, highs, lows, closes)]


def get_indicators_window(timeframe: str, entry_ts: int, exit_ts: int | None) -> dict:
    time, opens, highs, lows, closes = _tf_window(timeframe, entry_ts, exit_ts)
    bb = _bollinger(closes, 20, 2.0)
    macd = _macd(closes, 12, 26, 9)
    return {
        "time": time,
        "sma50": _sma(closes, 50), "sma100": _sma(closes, 100), "sma200": _sma(closes, 200),
        "bb_upper": bb["upper"], "bb_mid": bb["mid"], "bb_lower": bb["lower"],
        "rsi14": _rsi(closes, 14),
        "macd_line": macd["line"], "macd_signal": macd["signal"], "macd_hist": macd["hist"],
    }


def get_levels_window(timeframe: str, entry_ts: int, exit_ts: int | None) -> list:
    from .levels import level_flips
    time, opens, highs, lows, closes = _tf_window(timeframe, entry_ts, exit_ts,
                                                    bars_before=300, bars_after=30)
    flips = level_flips(highs, lows, closes)
    return [{"level": f["level"], "kind": f["kind"],
             "pivot_time": time[f["pivot_i"]], "confirm_time": time[f["confirm_i"]]}
            for f in flips]


def get_ohlcv_1h() -> list:
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts, open, high, low, close FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    rows = cur.fetchall()
    conn.close()
    return [{"time": r[0]//1000, "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in rows]


def get_levels_1h() -> list:
    """Resistance-becomes-support / support-becomes-resistance, over the same
    1h candles everything else on this page reads. Detection only — see
    app/levels.py's docstring; not yet tested for edge, just drawn.
    """
    from .levels import level_flips
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts, high, low, close FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    rows = cur.fetchall()
    conn.close()
    time   = [r[0] // 1000 for r in rows]
    highs  = [r[1] for r in rows]
    lows   = [r[2] for r in rows]
    closes = [r[3] for r in rows]
    flips = level_flips(highs, lows, closes)
    return [{"level": f["level"], "kind": f["kind"],
             "pivot_time": time[f["pivot_i"]], "confirm_time": time[f["confirm_i"]]}
            for f in flips]


def get_indicators_1h() -> dict:
    """SMA 50/100/200, Bollinger(20,2) and MACD(12,26,9), aligned to
    get_ohlcv_1h()'s exact row set — same query, so `time[i]` in one response
    is `time[i]` in the other with no re-matching needed on the client.

    From docs/trading-philosophy-2026-08.md: SMA 50/100/200 is the trend-
    confidence stack (above 50 = confident, breaks to 100 = normal pullback,
    breaks to 200 = real fear) — that's why these three periods, not a
    generic EMA. RSI already exists client-side nowhere on this page; it's
    added here anyway since /prop-desk's market_read.py computes the same
    RSI(14) and this keeps the two readings from ever being able to diverge.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ts, close FROM ohlcv_cache
        WHERE symbol='binance:BTC/USDT' AND timeframe='1h' AND ts >= ?
        ORDER BY ts
    """, (APR25_MS,))
    rows = cur.fetchall()
    conn.close()
    time   = [r[0] // 1000 for r in rows]
    closes = [r[1] for r in rows]
    bb = _bollinger(closes, 20, 2.0)
    macd = _macd(closes, 12, 26, 9)
    return {
        "time": time,
        "sma50": _sma(closes, 50), "sma100": _sma(closes, 100), "sma200": _sma(closes, 200),
        "bb_upper": bb["upper"], "bb_mid": bb["mid"], "bb_lower": bb["lower"],
        "rsi14": _rsi(closes, 14),
        "macd_line": macd["line"], "macd_signal": macd["signal"], "macd_hist": macd["hist"],
    }

