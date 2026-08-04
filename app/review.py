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
        FROM trades WHERE closed_at IS NOT NULL {bsql} ORDER BY opened_at
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
        ts_x = _parse_ms(closed_at)
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
            "closed_at":      closed_at[:19].replace("T", " "),
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
            "ts_exit":        ts_x // 1000,
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


# ── HTML ──────────────────────────────────────────────────────────────────────

REVIEW_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LENS // Journal</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
<link rel="apple-touch-icon" href="/assets/favicon.svg">
<link rel="stylesheet" href="/assets/lens.css">
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  /* Palette aliased onto the shared LENS tokens (app/theme.py LENS_CSS, served
     via /assets/lens.css) — single source of truth, no hardcoded hex so the
     review page can never drift from the design system. --bg/--mono inherit
     straight from the LENS :root; --b3/--t4 have no LENS equivalent. */
  --s1:var(--panel); --s2:var(--panel2);
  --b1:var(--line);  --b2:var(--line2); --b3:#313d52;
  --t1:var(--ink);   --t2:var(--dim);   --t3:var(--faint); --t4:#1c2636;
  --ac:var(--accent);--adim:var(--accent-d);
  --gr:var(--long);  --re:var(--short); --am:var(--amber);
  --ui:var(--hud);
}
/* kill the LENS cockpit grid overlay — review is a full-bleed chart IDE */
body::before{content:none}
html,body{height:100%;overflow:hidden}
body{font-family:var(--ui);font-size:13px;background:var(--bg);color:var(--t1);-webkit-font-smoothing:antialiased;display:flex;flex-direction:column}

/* ── topbar ── */
.topbar{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;border-bottom:1px solid var(--b1);background:var(--bg);flex-shrink:0;gap:12px;flex-wrap:wrap}
.topnav{display:flex;gap:6px;flex-wrap:wrap}
.topnav a{font-family:var(--mono);font-size:11px;color:var(--t2);text-decoration:none;padding:6px 12px;border:1px solid var(--b1);border-radius:999px;background:var(--s1);letter-spacing:.04em;transition:all .15s}
.topnav a:hover{color:var(--t1);border-color:var(--b2);text-decoration:none}
.topnav a.cur{color:var(--bg);background:var(--ac);border-color:var(--ac);font-weight:700}
.topbar-right{display:flex;gap:8px;align-items:center;margin-left:auto}
.tb-btn{background:var(--s1);border:1px solid var(--b2);color:var(--t2);padding:5px 12px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:11px;font-weight:600;transition:all .12s;white-space:nowrap}
.tb-btn:hover{border-color:var(--ac);color:var(--ac)}
.tb-btn.primary{background:var(--adim);color:var(--ac);border-color:#1e2e54}
.tb-btn.primary:hover{background:#172448}
.tb-btn:disabled{opacity:.4;cursor:default}
.sync-status{font-family:var(--mono);font-size:10px;color:var(--t3)}

/* ── stat chips ── */
.chips{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.chip{background:var(--s1);border:1px solid var(--b1);border-radius:5px;padding:3px 9px;font-family:var(--mono);font-size:11px;color:var(--t2);white-space:nowrap}
.chip b{color:var(--t1)}
.chip.pos b{color:var(--gr)}
.chip.neg b{color:var(--re)}

/* ── layout ── */
#content{display:flex;flex:1;overflow:hidden;min-height:0}

/* ── sidebar ── */
#sidebar{width:300px;display:flex;flex-direction:column;border-right:1px solid var(--b1);flex-shrink:0;background:var(--bg)}

/* ── filters ── */
#filters{padding:9px;border-bottom:1px solid var(--b1);display:flex;flex-direction:column;gap:7px;background:var(--s1)}
#filters select{width:100%;background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 6px;border-radius:4px;font-size:11px;font-family:var(--ui);cursor:pointer;min-width:0}
.fseg{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.fseg b{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;width:42px;flex:0 0 auto;font-weight:600}
.fseg button{padding:2px 9px;border:1px solid var(--b2);background:transparent;color:var(--t2);font-size:10px;border-radius:4px;cursor:pointer;font-family:var(--mono)}
.fseg button.on{border-color:var(--ac);background:var(--ac);color:var(--bg);font-weight:700}
.sec-hd{margin:0;font-size:10px;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.06em;padding:6px 10px;cursor:pointer;background:var(--s2);border-bottom:1px solid var(--b1);display:flex;justify-content:space-between;align-items:center;user-select:none;flex-shrink:0}
.sec-hd:hover{color:var(--t1)}
.sec-hd .cv{color:var(--t3);font-size:11px}
#analytics{flex:1;min-height:0;overflow-y:auto;padding:14px}
#chart-container{flex:none;height:34vh}
.an-sec{margin-bottom:18px}
.an-h{font-size:11px;font-weight:700;color:var(--t2);text-transform:uppercase;letter-spacing:.06em;margin:0 0 8px}
.an-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px}
.an-card{background:var(--s2);border:1px solid var(--b1);border-radius:7px;padding:8px 10px}
.an-card .k{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.an-card .v{font-size:16px;font-weight:700;font-family:var(--mono)}
.an-card .s{font-size:9px;color:var(--t3);margin-top:1px}
.an-tbl{width:100%;border-collapse:collapse;font-size:11px}
.an-tbl th{text-align:right;color:var(--t3);font-weight:600;padding:4px 8px;border-bottom:1px solid var(--b1);text-transform:uppercase;font-size:9px}
.an-tbl th:first-child,.an-tbl td:first-child{text-align:left}
.an-tbl td{text-align:right;padding:4px 8px;border-bottom:1px solid var(--b1);font-family:var(--mono)}
.an-tbl tr.hot td{background:rgba(31,217,137,.10)}

/* ── trade list ── */
#trade-list{flex:1;overflow-y:auto}
.trade-row{display:grid;grid-template-columns:74px 24px 54px 1fr 18px;gap:3px;align-items:center;padding:4px 8px;border-bottom:1px solid var(--b1);cursor:pointer;transition:background 0.08s}
.trade-row:hover{background:var(--s1)}
.trade-row.selected{background:var(--adim);border-left:2px solid var(--ac);padding-left:6px}
.tr-date{color:var(--t3);font-family:var(--mono);font-size:10px}
.tr-dir{font-size:10px;font-weight:700;font-family:var(--mono)}
.tr-dir.long{color:var(--gr)}
.tr-dir.short{color:var(--re)}
.tr-pnl{font-size:11px;font-weight:600;text-align:right;font-family:var(--mono)}
.tr-pnl.pos{color:var(--gr)}
.tr-pnl.neg{color:var(--re)}
.badges{display:flex;gap:2px;flex-wrap:wrap;min-width:0;overflow:hidden}
.badge{font-size:8px;padding:1px 3px;border-radius:3px;font-weight:700;letter-spacing:0.3px;white-space:nowrap;font-family:var(--mono)}
.b-bar-ok{background:#0d2014;color:var(--gr);border:1px solid #1a3a20}
.b-bar-no{background:#200d12;color:var(--re);border:1px solid #3a1a1e}
.b-4h-ok{background:#0d1428;color:var(--ac);border:1px solid #1a2848}
.b-4h-no{background:#1e0d28;color:#b060e0;border:1px solid #3a1a48}
.b-dip{background:#281e0d;color:var(--am);border:1px solid #483a1a}
.b-mom{background:#0d2814;color:#60e080;border:1px solid #1a4828}
.b-neu{background:var(--s2);color:var(--t3);border:1px solid var(--b2)}
.b-setup{background:#1e0d3a;color:#c084fc;border:1px solid #3a1a5a}
.tag-dot{width:7px;height:7px;border-radius:50%;background:var(--b2);border:1px solid var(--b3);cursor:pointer;flex-shrink:0;transition:all .12s}
.tag-dot:hover{border-color:var(--ac)}
.tag-dot.tagged{background:#c084fc;border-color:#9d4dfc}

/* ── edge panel ── */
#edge-panel{border-top:1px solid var(--b1);background:var(--s1);padding:8px;flex-shrink:0;max-height:200px;overflow-y:auto}
#edge-panel h3{font-size:9px;color:var(--t3);letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px}
.edge-tbl{width:100%;border-collapse:collapse;font-size:10px;font-family:var(--mono)}
.edge-tbl th{color:var(--t3);text-align:left;padding:2px 5px;font-weight:400;border-bottom:1px solid var(--b1);font-size:9px;text-transform:uppercase;letter-spacing:.1em}
.edge-tbl td{padding:3px 5px;border-bottom:1px solid var(--b1)}
.edge-tbl tr:hover td{background:var(--s2)}

/* ── main ── */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;background:var(--bg)}
#chart-container{flex:1;min-height:0}

/* ── detail panel ── */
#detail{min-height:130px;max-height:340px;border-top:1px solid var(--b1);background:var(--s1);padding:10px 16px;display:flex;flex-wrap:wrap;gap:16px;flex-shrink:0;overflow-y:auto}
#det-review{flex-basis:100%;border-top:1px solid var(--b1);padding-top:8px;display:flex;flex-direction:column;gap:6px}
.rv-row{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.rv-l{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em;width:78px;flex:0 0 auto}
.rv-opt{padding:2px 8px;border-radius:4px;border:1px solid var(--b2);background:transparent;color:var(--t2);font-size:11px;font-family:var(--mono);cursor:pointer}
.rv-opt.on{border-color:var(--ac);background:var(--ac);color:var(--bg);font-weight:700}
.rv-opt.miss.on{border-color:var(--re);background:rgba(255,84,104,.15);color:var(--re)}
.rv-opt.grade.on{border-color:var(--am);background:transparent;color:var(--am)}
.rv-refl{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}
.rv-refl textarea{background:var(--s2);border:1px solid var(--b2);border-radius:5px;color:var(--t1);font-size:11px;font-family:var(--mono);padding:5px 7px;min-height:42px;resize:vertical;outline:none}
.rv-save{align-self:flex-start;margin-top:2px;padding:6px 16px;border:none;border-radius:5px;background:var(--ac);color:var(--bg);font-size:11px;font-weight:700;cursor:pointer}
/* big trade modal */
.bm-bg{position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.66);backdrop-filter:blur(3px);display:none;align-items:center;justify-content:center;padding:20px}
.bm-bg.open{display:flex}
.bm{width:min(1100px,96vw);max-height:92vh;overflow-y:auto;background:var(--s1);border:1px solid var(--b2);border-radius:12px;padding:16px 18px;box-shadow:0 24px 70px rgba(0,0,0,.6)}
.bm-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.bm-title{font-size:16px;font-weight:700;font-family:var(--mono)}
.bm-x{font-size:18px;color:var(--t3);background:none;border:none;cursor:pointer}
#bm-chart{height:46vh;min-height:260px;border:1px solid var(--b1);border-radius:8px;margin-bottom:12px}
.bm-cols{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:12px}
#bm-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px 14px;align-content:start}
#bm-review{display:flex;flex-direction:column;gap:7px;border-top:1px solid var(--b1);padding-top:10px}
#det-left{flex:1;min-width:0}
#det-right{width:220px;flex-shrink:0}
.det-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
.df label{font-size:9px;color:var(--t3);display:block;letter-spacing:.1em;text-transform:uppercase;margin-bottom:2px}
.df value{font-size:12px;font-weight:600;font-family:var(--mono)}
#setup-row{margin-top:8px;display:flex;align-items:center;gap:8px}
#setup-row label{font-size:9px;color:var(--t3);letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
#setup-select{flex:1;background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:4px 7px;border-radius:4px;font-size:11px;font-family:var(--ui);cursor:pointer;transition:border-color .12s}
#setup-select:focus{outline:none;border-color:var(--ac)}
.cond-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.cond-item{background:var(--s2);border:1px solid var(--b1);border-radius:6px;padding:6px 8px}
.cond-item label{font-size:9px;color:var(--t3);display:block;text-transform:uppercase;letter-spacing:.08em;margin-bottom:2px}
.cond-item value{font-size:12px;font-weight:700;font-family:var(--mono)}
#no-sel{color:var(--t3);font-size:12px;padding:10px 0}

/* ── modal ── */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;align-items:center;justify-content:center}
.modal-bg.open{display:flex}
.modal{background:var(--s1);border:1px solid var(--b2);border-radius:10px;padding:20px 24px;width:420px;max-width:95vw}
.modal h2{font-size:14px;font-weight:700;margin-bottom:16px;color:var(--t1)}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
.fld{display:flex;flex-direction:column;gap:4px}
.fld label{font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--t3);font-weight:700}
.fld input,.fld select{background:var(--s2);border:1px solid var(--b2);color:var(--t1);padding:6px 9px;border-radius:5px;font-family:var(--mono);font-size:12px;transition:border-color .12s;width:100%}
.fld input:focus,.fld select:focus{outline:none;border-color:var(--ac)}
.modal-btns{display:flex;gap:8px;justify-content:flex-end}
.btn-cancel{background:transparent;border:1px solid var(--b2);color:var(--t2);padding:7px 16px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:12px}
.btn-save{background:var(--adim);color:var(--ac);border:1px solid #1e2e54;padding:7px 16px;border-radius:5px;cursor:pointer;font-family:var(--ui);font-size:12px;font-weight:600}
.btn-save:hover{background:#172448}

::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}

/* ── phone (<=700px): restack the 3-pane IDE vertically + detail as a slide-up sheet ── */
#det-close{display:none}
@media(max-width:700px){
  html,body{height:auto;overflow:auto}
  body{display:block}
  .topbar{position:sticky;top:0;z-index:20}
  #content{flex-direction:column;overflow:visible;min-height:0}
  #main{order:-1;display:block;flex:none;min-width:0}
  #chart-container{height:42vh;min-height:240px}
  #sidebar{width:100%;border-right:none;border-top:1px solid var(--b1)}
  #filters{position:sticky;top:52px;z-index:5}
  #trade-list{flex:none;max-height:none}
  #edge-panel{max-height:none}
  /* detail panel → bottom sheet, revealed when a trade is picked */
  #detail{position:fixed;left:0;right:0;bottom:0;height:auto;max-height:72vh;
    flex-direction:column;gap:10px;overflow-y:auto;z-index:60;
    transform:translateY(105%);transition:transform .25s ease;
    box-shadow:0 -10px 30px rgba(0,0,0,.55);border-top:1px solid var(--b2)}
  #detail.open{transform:translateY(0)}
  #det-left,#det-right{width:100%}
  .det-grid{grid-template-columns:repeat(2,1fr)}
  #det-close{display:block;width:100%;background:var(--s2);border:none;
    border-bottom:1px solid var(--b1);color:var(--t2);font-family:var(--ui);
    font-size:12px;padding:10px;cursor:pointer;position:sticky;top:0}
}
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">LEN<span class="s">S</span> <span class="pg">Journal</span></div>
  <div class="modesw">
    <a href="/prop">◎ PROP</a>
    <a href="/hedge-plan" class="on">▤ HEDGE</a>
    <a href="/" class="home">⌂</a>
  </div>
  <nav class="topnav">
    <a href="/hedge-plan">Dashboard</a>
    <a href="/hedge-desk">Desk</a>
    <a href="/hedge-signals">Signals</a>
    <a href="/hedge-calendar">Calendar</a>
    <a href="/hedge-analytics">Analytics</a>
    <a href="/hedge-journal" class="cur">Journal</a>
    <a href="/hedge-edge">Edge</a>
    <a href="/hedge-goal">Goal</a>
  </nav>
  <div class="topbar-right">
    <button class="tb-btn" onclick="openLogModal()">+ Log Trade</button>
    <button class="tb-btn primary" id="sync-btn" onclick="syncKraken()">Sync Kraken</button>
    <span class="sync-status" id="sync-status"></span>
    <button class="tb-btn" onclick="exportCSV()">Export CSV</button>
  </div>
</div>

<div id="content">
  <div id="sidebar">
    <div class="sec-hd" onclick="secToggle('filters','filters')">Filters <span class="cv" id="filters-car">▾</span></div>
    <div id="filters">
      <select id="f-tag" onchange="filter()"><option value="">All setups</option><option value="__none__">Untagged</option></select>
      <div class="fseg" data-k="dir"><b>Dir</b><button data-v="" class="on">All</button><button data-v="long">Long</button><button data-v="short">Short</button></div>
      <div class="fseg" data-k="result"><b>Result</b><button data-v="" class="on">All</button><button data-v="win">Win</button><button data-v="loss">Loss</button></div>
      <div class="fseg" data-k="bar"><b>Bar</b><button data-v="" class="on">All</button><button data-v="true">✓</button><button data-v="false">✗</button></div>
      <div class="fseg" data-k="h4"><b>4H</b><button data-v="" class="on">All</button><button data-v="true">✓</button><button data-v="false">✗</button></div>
      <div class="fseg" data-k="rsi"><b>RSI</b><button data-v="" class="on">All</button><button data-v="dip">Dip</button><button data-v="momentum">Mom</button><button data-v="neutral">Neut</button></div>
    </div>
    <div class="sec-hd" onclick="secToggle('list','trade-list')">Trades <span class="cv" id="list-car">▾</span></div>
    <div id="trade-list"><div style="padding:16px;color:var(--t3)">Loading…</div></div>
  </div>

  <div id="main">
    <div class="sec-hd chart-hd" onclick="secToggle('chart','chart-container')">Chart (also in trade modal) <span class="cv" id="chart-car">▾</span></div>
    <div id="chart-container"></div>
    <div id="detail">
      <button id="det-close" onclick="document.getElementById('detail').classList.remove('open')">▾ close</button>
      <div id="det-left">
        <div class="det-grid" id="det-grid"><div id="no-sel">← select a trade to review</div></div>
        <div id="setup-row" style="display:none">
          <label>Setup Tag</label>
          <select id="setup-select" onchange="saveTag(this.value)">
            <option value="">— untagged —</option>
            <option value="DIP">DIP (RSI&lt;40 pullback)</option>
            <option value="MOMENTUM">MOMENTUM (RSI&gt;55)</option>
            <option value="FOMO">FOMO (chased entry)</option>
            <option value="COUNTER">COUNTER-TREND</option>
            <option value="SCALP">SCALP</option>
            <option value="RANGE">RANGE play</option>
            <option value="REVERSAL">REVERSAL</option>
            <option value="QUALITY">QUALITY (all 3 rules)</option>
            <option value="GARBAGE">GARBAGE (no rules met)</option>
          </select>
        </div>
      </div>
      <div id="det-right"><div class="cond-grid" id="cond-grid"></div></div>
      <div id="det-review" style="display:none">
        <div class="rv-row"><span class="rv-l">Grade</span><span class="rv-opts" id="rv-grade"></span></div>
        <div class="rv-row"><span class="rv-l">Conviction</span><span class="rv-opts" id="rv-conv"></span></div>
        <div class="rv-row"><span class="rv-l">Emotion</span><span class="rv-opts" id="rv-emo"></span></div>
        <div class="rv-row"><span class="rv-l">Mistakes</span><span class="rv-opts" id="rv-miss"></span></div>
        <div class="rv-refl">
          <textarea id="rv-right" placeholder="what went right…"></textarea>
          <textarea id="rv-wrong" placeholder="what went wrong…"></textarea>
          <textarea id="rv-lesson" placeholder="lesson / takeaway…"></textarea>
        </div>
        <button id="rv-save" class="rv-save" onclick="saveReview('rv')">💾 Save review</button>
      </div>
    </div>
  </div>
</div>

<!-- Big trade review modal (chart + breakdown + context + review) -->
<div class="bm-bg" id="big-modal" onclick="if(event.target===this)closeBig()">
  <div class="bm">
    <div class="bm-head"><div class="bm-title" id="bm-title">—</div><button class="bm-x" onclick="closeBig()">✕</button></div>
    <div id="bm-chart"></div>
    <div class="bm-cols">
      <div class="det-grid" id="bm-grid"></div>
      <div class="cond-grid" id="bm-cond"></div>
    </div>
    <div id="bm-review">
      <div class="rv-row"><span class="rv-l">Grade</span><span class="rv-opts" id="bm-grade"></span></div>
      <div class="rv-row"><span class="rv-l">Conviction</span><span class="rv-opts" id="bm-conv"></span></div>
      <div class="rv-row"><span class="rv-l">Emotion</span><span class="rv-opts" id="bm-emo"></span></div>
      <div class="rv-row"><span class="rv-l">Mistakes</span><span class="rv-opts" id="bm-miss"></span></div>
      <div class="rv-refl">
        <textarea id="bm-right" placeholder="what went right…"></textarea>
        <textarea id="bm-wrong" placeholder="what went wrong…"></textarea>
        <textarea id="bm-lesson" placeholder="lesson / takeaway…"></textarea>
      </div>
      <button id="bm-save" class="rv-save" onclick="saveReview('bm')">💾 Save review</button>
    </div>
  </div>
</div>

<!-- Log Trade Modal -->
<div class="modal-bg" id="log-modal" onclick="if(event.target===this)closeLogModal()">
  <div class="modal">
    <h2>Log Trade Manually</h2>
    <div class="form-grid">
      <div class="fld">
        <label>Direction</label>
        <select id="m-dir"><option value="long">Long</option><option value="short">Short</option></select>
      </div>
      <div class="fld">
        <label>Symbol</label>
        <select id="m-symbol">
          <option value="BTC/USD:USD">BTC/USD:USD (Kraken)</option>
          <option value="BTC/USDT:USDT">BTC/USDT:USDT (Bybit)</option>
        </select>
      </div>
      <div class="fld"><label>Entry Price ($)</label><input id="m-entry" type="number" step="any" placeholder="84000"></div>
      <div class="fld"><label>Exit Price ($)</label><input id="m-exit" type="number" step="any" placeholder="86000"></div>
      <div class="fld"><label>Size (BTC)</label><input id="m-size" type="number" step="any" placeholder="0.01"></div>
      <div class="fld"><label>Leverage</label><input id="m-lev" type="number" step="any" placeholder="5" value="1"></div>
      <div class="fld"><label>PnL (€)</label><input id="m-pnl" type="number" step="any" placeholder="42.50"></div>
      <div class="fld"><label>Fees (€)</label><input id="m-fees" type="number" step="any" placeholder="0.80" value="0"></div>
      <div class="fld"><label>Opened At</label><input id="m-open" type="datetime-local"></div>
      <div class="fld"><label>Closed At</label><input id="m-close" type="datetime-local"></div>
    </div>
    <div class="fld" style="margin-bottom:16px"><label>Notes</label><input id="m-notes" type="text" placeholder="optional notes"></div>
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeLogModal()">Cancel</button>
      <button class="btn-save" onclick="submitLog()">Save Trade</button>
    </div>
  </div>
</div>

<script>
let ALL_TRADES = [], CANDLES = [], visible = [], selected = null;

// ── chart ──────────────────────────────────────────────────────────────────────
const chartEl = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(chartEl, {
  layout: { background:{color:'#06080c'}, textColor:'#465064' },
  grid:   { vertLines:{color:'#192232'}, horzLines:{color:'#192232'} },
  crosshair: { mode:LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor:'#192232' },
  timeScale: { borderColor:'#192232', timeVisible:true, secondsVisible:false },
});
const series = chart.addCandlestickSeries({
  upColor:'#1fd989', downColor:'#ff5468',
  borderUpColor:'#1fd989', borderDownColor:'#ff5468',
  wickUpColor:'#1fd989', wickDownColor:'#ff5468',
});
new ResizeObserver(() => chart.applyOptions({width:chartEl.clientWidth, height:chartEl.clientHeight})).observe(chartEl);

const activeLines = [];
function clearOverlays() {
  activeLines.forEach(l => { try { series.removePriceLine(l); } catch(e){} });
  activeLines.length = 0;
  series.setMarkers([]);
}
function showTrade(t) {
  clearOverlays();
  const isL = t.direction === 'long';
  const ec  = isL ? '#1fd989' : '#ff5468';
  if (t.entry) activeLines.push(series.createPriceLine({price:t.entry, color:ec, lineWidth:1, lineStyle:LightweightCharts.LineStyle.Solid, axisLabelVisible:true, title:'ENTRY'}));
  if (t.exit)  activeLines.push(series.createPriceLine({price:t.exit, color:'#828ea6', lineWidth:1, lineStyle:LightweightCharts.LineStyle.Dashed, axisLabelVisible:true, title:'EXIT'}));
  const ms = [];
  if (t.ts_entry) ms.push({time:t.ts_entry, position:isL?'belowBar':'aboveBar', color:ec, shape:isL?'arrowUp':'arrowDown', text:'E', size:1.5});
  if (t.ts_exit)  ms.push({time:t.ts_exit, position:isL?'aboveBar':'belowBar', color:isL?'#ff5468':'#1fd989', shape:isL?'arrowDown':'arrowUp', text:'X', size:1.5});
  series.setMarkers(ms);
  chart.timeScale().setVisibleRange({from:t.ts_entry-48*3600, to:(t.ts_exit||t.ts_entry)+24*3600});
}

// ── save tag ───────────────────────────────────────────────────────────────────
async function saveTag(val) {
  if (!selected) return;
  selected.setup_tag = val;
  renderList(); renderEdge(); updateStats();
  try {
    await fetch(`/api/trades/${selected.id}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({setup_tag: val || null})
    });
    buildTagFilter();
  } catch(e) { console.error('Tag save failed', e); }
}

// ── filters ────────────────────────────────────────────────────────────────────
// Segmented filter state (chips), tag stays a select (dynamic values).
const F = {dir:'', result:'', bar:'', h4:'', rsi:''};
(function wireFilters(){
  const box = document.getElementById('filters');
  if (!box) return;
  box.addEventListener('click', e => {
    const b = e.target.closest('.fseg button'); if (!b) return;
    const seg = b.closest('.fseg');
    F[seg.dataset.k] = b.dataset.v;
    seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    filter();
  });
})();
function filter() {
  const dir = F.dir;
  const tag = document.getElementById('f-tag').value;
  const bar = F.bar;
  const th  = F.h4;
  const rsi = F.rsi;
  const res = F.result;
  visible = ALL_TRADES.filter(t => {
    if (dir && t.direction !== dir) return false;
    const tg = t.setup_tag || '';
    if (tag === '__none__' && tg) return false;
    if (tag && tag !== '__none__' && tg !== tag) return false;
    if (bar && String(t.bar_aligned) !== bar) return false;
    if (th  && String(t.trend_aligned) !== th) return false;
    if (rsi && t.rsi_zone !== rsi) return false;
    if (res === 'win'  && (t.pnl||0) <= 0) return false;
    if (res === 'loss' && (t.pnl||0) >= 0) return false;
    return true;
  });
  renderList(); renderEdge(); updateStats();
}

// ── render list ────────────────────────────────────────────────────────────────
function renderList() {
  const el = document.getElementById('trade-list');
  if (!visible.length) { el.innerHTML='<div style="padding:16px;color:var(--t3)">No trades match</div>'; return; }
  el.innerHTML = visible.slice().reverse().map(t => {
    const pnl = t.pnl||0, ps = pnl>=0?'+':'';
    const sel = selected && selected.id===t.id;
    const bs = [];
    if (t.bar_aligned===true)  bs.push('<span class="badge b-bar-ok">BAR✓</span>');
    if (t.bar_aligned===false) bs.push('<span class="badge b-bar-no">BAR✗</span>');
    if (t.trend_aligned===true)  bs.push('<span class="badge b-4h-ok">4H✓</span>');
    if (t.trend_aligned===false) bs.push('<span class="badge b-4h-no">4H✗</span>');
    if (t.rsi_zone==='dip')      bs.push('<span class="badge b-dip">DIP</span>');
    if (t.rsi_zone==='momentum') bs.push('<span class="badge b-mom">MOM</span>');
    if (t.rsi_zone==='neutral')  bs.push('<span class="badge b-neu">NEU</span>');
    if (t.setup_tag) bs.push(`<span class="badge b-setup">${t.setup_tag}</span>`);
    return `<div class="trade-row${sel?' selected':''}" onclick="openTrade(${t.id})">
      <span class="tr-date">${t.opened_at.slice(0,16)}</span>
      <span class="tr-dir ${t.direction}">${t.direction==='long'?'L':'S'}</span>
      <span class="tr-pnl ${pnl>=0?'pos':'neg'}">${ps}${pnl.toFixed(0)}€</span>
      <div class="badges">${bs.join('')}</div>
      <div class="tag-dot${t.setup_tag?' tagged':''}" title="Click to tag" onclick="event.stopPropagation();pick(${t.id});document.getElementById('setup-select').focus()"></div>
    </div>`;
  }).join('');
  // scroll selected into view
  if (selected) {
    const rows = el.querySelectorAll('.trade-row');
    rows.forEach(r => { if (r.classList.contains('selected')) r.scrollIntoView({block:'nearest'}); });
  }
}

// ── pick trade ─────────────────────────────────────────────────────────────────
function pick(id) {
  selected = ALL_TRADES.find(t => t.id===id);
  if (!selected) return;
  renderList();
  showTrade(selected);
  renderDetail(selected);
  document.getElementById('detail').classList.add('open');  // reveal sheet on phone (no-op on desktop)
}

function renderDetail(t) {
  const pnl = t.pnl||0;
  const dur = t.ts_exit ? Math.round((t.ts_exit-t.ts_entry)/60) : null;
  const durS = dur ? (dur<60?dur+'m':Math.round(dur/60)+'h') : '—';
  document.getElementById('det-grid').innerHTML = `
    <div class="df"><label>Direction</label><value style="color:${t.direction==='long'?'var(--gr)':'var(--re)'}">${t.direction.toUpperCase()}</value></div>
    <div class="df"><label>PnL</label><value style="color:${pnl>=0?'var(--gr)':'var(--re)'}">${pnl>=0?'+':''}${pnl.toFixed(2)}€</value></div>
    <div class="df"><label>Move</label><value>${t.move_pct!=null?(t.move_pct>0?'+':'')+t.move_pct+'%':'—'}</value></div>
    <div class="df"><label>Hold</label><value>${durS}</value></div>
    <div class="df"><label>Entry</label><value>$${t.entry?.toFixed(0)||'—'}</value></div>
    <div class="df"><label>Exit</label><value>$${t.exit?.toFixed(0)||'—'}</value></div>
    <div class="df"><label>Size</label><value>${t.size?.toFixed(4)||'—'}</value></div>
    <div class="df"><label>Lev</label><value>${t.leverage||'—'}×</value></div>
  `;
  document.getElementById('setup-row').style.display = 'flex';
  document.getElementById('setup-select').value = t.setup_tag || '';
  document.getElementById('cond-grid').innerHTML = `
    <div class="cond-item"><label>Entry Bar</label>
      <value style="color:${t.bar_aligned===true?'var(--gr)':t.bar_aligned===false?'var(--re)':'var(--t3)'}">
        ${t.bar_dir?(t.bar_dir.toUpperCase()+(t.bar_aligned?' ✓':' ✗')):'—'}</value></div>
    <div class="cond-item"><label>4H Trend</label>
      <value style="color:${t.trend_aligned===true?'var(--gr)':t.trend_aligned===false?'var(--re)':'var(--t3)'}">
        ${t.trend_4h?(t.trend_4h.toUpperCase()+(t.trend_aligned?' ✓':' ✗')):'—'}</value></div>
    <div class="cond-item"><label>RSI @ Entry</label>
      <value style="color:${t.rsi_zone==='dip'?'var(--am)':t.rsi_zone==='momentum'?'var(--gr)':'var(--t3)'}">
        ${t.rsi!=null?t.rsi:'—'} <small style="font-size:9px;opacity:.7">${t.rsi_zone||''}</small></value></div>
    <div class="cond-item"><label>Bal After</label>
      <value>${t.balance_after!=null?t.balance_after.toFixed(2)+'€':'—'}</value></div>
  `;
  renderReview(t);
}

// ── review layer (parity with the calendar modal) ───────────────────────────────
const RV_MISTAKES=["chased","early","late","oversized","moved stop","no stop","revenge","FOMO","overheld","cut early","no setup"];
const RV_EMOTIONS=["calm","FOMO","tilt","fear","greed","bored"];
const RV_GRADES=["A","B","C","D","F"];
let rev={};
// Render the review controls into a container prefixed `p` (rv = sidebar strip,
// bm = big modal). Shares the `rev` state + `selected` trade (one open at a time).
function renderReview(t, p='rv'){
  const host=document.getElementById(p+'-review'); if(host) host.style.display='flex';
  rev={grade:t.grade||null,conviction:t.conviction||null,emotion:t.emotion||null,
       mistakes:new Set((t.mistakes||'').split(',').map(s=>s.trim()).filter(Boolean))};
  const opt=(v,on,cls)=>`<button class="rv-opt ${cls||''} ${on?'on':''}" data-v="${v}">${v}</button>`;
  document.getElementById(p+'-grade').innerHTML=RV_GRADES.map(g=>opt(g,rev.grade===g,'grade')).join('');
  document.getElementById(p+'-conv').innerHTML=[1,2,3,4,5].map(c=>opt(c,String(rev.conviction)===String(c),'')).join('');
  document.getElementById(p+'-emo').innerHTML=RV_EMOTIONS.map(e=>opt(e,rev.emotion===e,'')).join('');
  document.getElementById(p+'-miss').innerHTML=RV_MISTAKES.map(m=>`<button class="rv-opt miss ${rev.mistakes.has(m)?'on':''}" data-m="${m}">${m}</button>`).join('');
  document.getElementById(p+'-right').value=t.went_right||'';
  document.getElementById(p+'-wrong').value=t.went_wrong||'';
  document.getElementById(p+'-lesson').value=t.lesson||'';
  const single=(rowId,key)=>document.querySelectorAll('#'+rowId+' .rv-opt').forEach(b=>b.onclick=()=>{
    let v=b.dataset.v; if(key==='conviction')v=parseInt(v);
    rev[key]=(String(rev[key])===String(v))?null:v;
    document.querySelectorAll('#'+rowId+' .rv-opt').forEach(x=>x.classList.toggle('on',rev[key]!=null&&String(rev[key])===String(x.dataset.v)));
  });
  single(p+'-grade','grade'); single(p+'-conv','conviction'); single(p+'-emo','emotion');
  document.querySelectorAll('#'+p+'-miss .rv-opt').forEach(b=>b.onclick=()=>{
    const m=b.dataset.m;
    if(rev.mistakes.has(m)){rev.mistakes.delete(m);b.classList.remove('on');}
    else{rev.mistakes.add(m);b.classList.add('on');}
  });
}
async function saveReview(p='rv'){
  if(!selected) return;
  const btn=document.getElementById(p+'-save'); btn.textContent='Saving…'; btn.disabled=true;
  const payload={manually_edited:true,
    went_right:document.getElementById(p+'-right').value||undefined,
    went_wrong:document.getElementById(p+'-wrong').value||undefined,
    lesson:document.getElementById(p+'-lesson').value||undefined,
    mistakes:[...rev.mistakes].join(',')||undefined};
  if(rev.grade!=null) payload.grade=rev.grade;
  if(rev.conviction!=null) payload.conviction=rev.conviction;
  if(rev.emotion!=null) payload.emotion=rev.emotion;
  Object.keys(payload).forEach(k=>payload[k]===undefined&&delete payload[k]);
  try{
    const r=await fetch('/api/trades/'+selected.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    await r.json();
    Object.assign(selected,{grade:rev.grade,conviction:rev.conviction,emotion:rev.emotion,
      mistakes:[...rev.mistakes].join(','),went_right:payload.went_right||'',went_wrong:payload.went_wrong||'',lesson:payload.lesson||''});
    const idx=ALL_TRADES.findIndex(x=>x.id===selected.id); if(idx>=0) Object.assign(ALL_TRADES[idx],selected);
    btn.textContent='✓ Saved'; setTimeout(()=>{btn.textContent='💾 Save review';btn.disabled=false;},1200);
    renderEdge();
  }catch(e){console.error(e);btn.textContent='Error — retry';btn.disabled=false;}
}

// ── big trade modal (chart + breakdown + context + review) ──────────────────────
let bmChart=null, bmSeries=null;
function openTrade(id){ pick(id); if(selected) openBig(selected); }
function openBig(t){
  const dc=t.direction==='long'?'var(--gr)':'var(--re)', pc=(t.pnl||0)>=0?'var(--gr)':'var(--re)';
  document.getElementById('bm-title').innerHTML=
    `<span style="color:${dc}">${t.direction==='long'?'▲ LONG':'▼ SHORT'}</span> ${t.symbol||'BTC/USD'} · #${t.id} `+
    `· <span style="color:${pc}">${(t.pnl||0)>=0?'+':''}${(t.pnl||0).toFixed(2)}€</span>${t.setup_tag?` · <span style="color:var(--ac)">${t.setup_tag}</span>`:''}`;
  // reuse the already-rendered strip grids (pick → renderDetail ran first)
  document.getElementById('bm-grid').innerHTML=document.getElementById('det-grid').innerHTML;
  document.getElementById('bm-cond').innerHTML=document.getElementById('cond-grid').innerHTML;
  renderReview(t,'bm');
  document.getElementById('big-modal').classList.add('open');
  // chart: fresh instance from the loaded candles, disposed on close
  const el=document.getElementById('bm-chart'); el.innerHTML='';
  bmChart=LightweightCharts.createChart(el,{layout:{background:{color:'#06080c'},textColor:'#465064'},
    grid:{vertLines:{color:'#192232'},horzLines:{color:'#192232'}},
    rightPriceScale:{borderColor:'#192232'},timeScale:{borderColor:'#192232',timeVisible:true,secondsVisible:false}});
  bmSeries=bmChart.addCandlestickSeries({upColor:'#1fd989',downColor:'#ff5468',borderUpColor:'#1fd989',borderDownColor:'#ff5468',wickUpColor:'#1fd989',wickDownColor:'#ff5468'});
  bmSeries.setData(CANDLES);
  const isL=t.direction==='long', ec=isL?'#1fd989':'#ff5468', L=LightweightCharts.LineStyle;
  if(t.entry) bmSeries.createPriceLine({price:t.entry,color:ec,lineWidth:1,lineStyle:L.Solid,axisLabelVisible:true,title:'ENTRY'});
  if(t.exit)  bmSeries.createPriceLine({price:t.exit,color:'#828ea6',lineWidth:1,lineStyle:L.Dashed,axisLabelVisible:true,title:'EXIT'});
  if(t.tp)    bmSeries.createPriceLine({price:t.tp,color:'#1fd989',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'TP'});
  if(t.sl)    bmSeries.createPriceLine({price:t.sl,color:'#ff5468',lineWidth:1,lineStyle:L.Dotted,axisLabelVisible:true,title:'SL'});
  const ms=[];
  if(t.ts_entry) ms.push({time:t.ts_entry,position:isL?'belowBar':'aboveBar',color:ec,shape:isL?'arrowUp':'arrowDown',text:'E',size:1.5});
  if(t.ts_exit)  ms.push({time:t.ts_exit,position:isL?'aboveBar':'belowBar',color:isL?'#ff5468':'#1fd989',shape:isL?'arrowDown':'arrowUp',text:'X',size:1.5});
  bmSeries.setMarkers(ms);
  setTimeout(()=>{ if(!bmChart)return; bmChart.applyOptions({width:el.clientWidth,height:el.clientHeight});
    if(t.ts_entry) bmChart.timeScale().setVisibleRange({from:t.ts_entry-48*3600,to:(t.ts_exit||t.ts_entry)+24*3600}); },30);
}
function closeBig(){
  document.getElementById('big-modal').classList.remove('open');
  if(bmChart){ try{bmChart.remove();}catch(e){} bmChart=null; bmSeries=null; }
  if(location.search.includes('trade=')) history.replaceState(null,'','/review');
}
document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&document.getElementById('big-modal').classList.contains('open')) closeBig(); });

// ── collapsible sections, persisted in localStorage ─────────────────────────────
function secToggle(key, bdId){
  const bd=document.getElementById(bdId);
  const collapsing = bd.style.display!=='none';
  bd.style.display = collapsing?'none':'';
  const car=document.getElementById(key+'-car'); if(car) car.textContent=collapsing?'▸':'▾';
  const s=JSON.parse(localStorage.getItem('rv-secs')||'{}'); s[key]=collapsing; localStorage.setItem('rv-secs',JSON.stringify(s));
  if(key==='chart' && !collapsing) setTimeout(()=>chart.applyOptions({width:chartEl.clientWidth,height:chartEl.clientHeight}),20);
}
// ── analytics dashboard ─────────────────────────────────────────────────────────
function renderAnalytics(a){
  const host=document.getElementById('analytics'); if(!host) return;
  if(!a || !a.n){ host.innerHTML='<div style="padding:16px;color:var(--t3)">No closed trades</div>'; return; }
  const eur=v=>v==null?'—':(v>=0?'+':'')+'€'+Math.abs(v).toFixed(2);
  const pc=v=>v>=0?'var(--gr)':'var(--re)';
  const card=(k,v,s,col)=>`<div class="an-card"><div class="k">${k}</div><div class="v" style="color:${col||'var(--t1)'}">${v}</div>${s?`<div class="s">${s}</div>`:''}</div>`;
  const perf=`<div class="an-sec"><div class="an-h">Performance · live from trade log</div><div class="an-grid">`+
    card('Trades',a.n,a.open?a.open+' open':'')+
    card('Win Rate',a.wr+'%',a.long_wr!=null?`L ${a.long_wr}% · S ${a.short_wr}%`:'')+
    card('Net P&L',eur(a.total_pnl),'',pc(a.total_pnl))+
    card('Expectancy',eur(a.expectancy),'per trade',pc(a.expectancy))+
    card('Avg Win',eur(a.avg_win),'','var(--gr)')+
    card('Avg Loss',eur(-a.avg_loss),'','var(--re)')+
    card('Actual R:R',a.rr!=null?a.rr+'×':'—','')+
    card('Profit Factor',a.profit_factor!=null?a.profit_factor:'—','',a.profit_factor>=1?'var(--gr)':'var(--re)')+
    card('Total Fees',eur(-a.total_fees),'','var(--re)')+
    card('Avg Duration',a.avg_dur_h!=null?a.avg_dur_h+'h':'—','')+
    `</div></div>`;
  const risk=`<div class="an-sec"><div class="an-h">Risk-adjusted</div><div class="an-grid">`+
    card('Sharpe',a.sharpe,'per-trade · ann.',a.sharpe>=0?'var(--gr)':'var(--re)')+
    card('Sortino',a.sortino,'',a.sortino>=0?'var(--gr)':'var(--re)')+
    card('Max DD',eur(-a.max_dd_eur)+(a.max_dd_pct!=null?` · ${a.max_dd_pct}%`:''),'peak→trough','var(--re)')+
    card('Win Streak',a.win_streak,'','var(--gr)')+
    card('Loss Streak',a.loss_streak,'','var(--re)')+
    (a.cum_return!=null?card('Cum Return',a.cum_return+'%','',pc(a.cum_return)):card('Cum Return','—','set capital base'))+
    (a.ann_return!=null?card('Ann Return',a.ann_return+'%','',pc(a.ann_return)):'')+
    (a.calmar!=null?card('Calmar',a.calmar,''):'')+
    `</div></div>`;
  const dWR=a.wr-(a.model_wr||0), dRR=(a.rr||0)-(a.model_rr||0);
  const avm=`<div class="an-sec"><div class="an-h">Actual vs Model</div><table class="an-tbl">
    <tr><th>Metric</th><th>Model</th><th>Actual</th><th>Δ</th></tr>
    <tr><td>Win Rate</td><td>${a.model_wr!=null?a.model_wr+'%':'—'}</td><td>${a.wr}%</td><td style="color:${pc(dWR)}">${dWR>=0?'+':''}${dWR.toFixed(1)}</td></tr>
    <tr><td>R:R</td><td>${a.model_rr!=null?a.model_rr+'×':'—'}</td><td>${a.rr!=null?a.rr+'×':'—'}</td><td style="color:${pc(dRR)}">${dRR>=0?'+':''}${dRR.toFixed(2)}</td></tr>
    </table></div>`;
  const dur=`<div class="an-sec"><div class="an-h">Trade Duration Breakdown <span style="color:var(--t3);text-transform:none;font-weight:400">— where the edge lives</span></div><table class="an-tbl">
    <tr><th>Duration</th><th>Count</th><th>W</th><th>L</th><th>Total P&L</th><th>Avg P&L</th></tr>`+
    a.duration.map(d=>`<tr class="${d.total>0&&d.n>=8?'hot':''}"><td>${d.label}</td><td>${d.n}</td><td>${d.w}</td><td>${d.l}</td>
      <td style="color:${pc(d.total)}">${eur(d.total)}</td><td style="color:${pc(d.avg)}">${eur(d.avg)}</td></tr>`).join('')+
    `</table></div>`;
  host.innerHTML=perf+risk+avm+dur;
}

function restoreSecs(){
  const map={filters:'filters', list:'trade-list', chart:'chart-container'};
  const s=JSON.parse(localStorage.getItem('rv-secs')||'{}');
  if(s.chart===undefined) s.chart=true;   // charts live in the modal → collapse page chart by default
  Object.keys(map).forEach(key=>{
    if(s[key]){ const bd=document.getElementById(map[key]); if(bd) bd.style.display='none';
      const car=document.getElementById(key+'-car'); if(car) car.textContent='▸'; }
  });
}

// ── edge table ─────────────────────────────────────────────────────────────────
// Collapse a raw setup_tag into a readable family: S1..S5 stand alone, a
// matched-but-vetoed setup → "Sx (vetoed)", a pure veto → "VETO", else as-is.
function edgeFamily(tag){
  if(!tag) return '(untagged)';
  if(tag.startsWith('VETO:')) return 'VETO';
  if(tag.includes('|VETO:')) return tag.split('|')[0]+' (vetoed)';
  return tag;
}
// KEEP/CUT/SIZE-UP from realised expectancy + sample. Thin samples say so.
function edgeVerdict(n,wr,exp){
  if(n<8)              return ['THIN','var(--t3)'];
  if(exp<=0)           return ['CUT','var(--re)'];
  if(exp>=10&&n>=12&&wr>=45) return ['SIZE-UP','var(--gr)'];
  return ['KEEP','var(--am)'];
}
function renderEdge() {
  if (!document.getElementById('edge-body')) return;  // edge moved to its own /edge page
  const g = {};
  visible.forEach(t => {
    const k = edgeFamily(t.setup_tag);
    if (!g[k]) g[k]={n:0,wins:0,total:0,byGrade:{}};
    g[k].n++; if ((t.pnl||0)>0) g[k].wins++; g[k].total+=t.pnl||0;
    const gr=t.grade||'—';
    if(!g[k].byGrade[gr]) g[k].byGrade[gr]={n:0,wins:0,total:0};
    g[k].byGrade[gr].n++; if((t.pnl||0)>0) g[k].byGrade[gr].wins++; g[k].byGrade[gr].total+=t.pnl||0;
  });
  const rows = Object.entries(g).sort((a,b)=>b[1].total-a[1].total);
  document.getElementById('edge-body').innerHTML = rows.map(([k,d])=>{
    const exp=d.total/d.n, wr=d.wins/d.n*100;
    const [vlabel,vcol]=edgeVerdict(d.n,wr,exp);
    const grades=Object.entries(d.byGrade).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
    const sub = grades.length>1 ? grades.map(([gr,gd])=>
      `<span style="display:inline-block;font-size:9px;padding:1px 5px;margin:3px 4px 0 0;border:1px solid var(--b3);border-radius:3px;color:var(--t2)">`+
      `${gr}: ${gd.n}·${(gd.wins/gd.n*100).toFixed(0)}%·<span style="color:${gd.total>=0?'var(--gr)':'var(--re)'}">${gd.total>=0?'+':''}${gd.total.toFixed(0)}€</span></span>`
    ).join('') : '';
    return `<tr>
      <td>${k}</td><td>${d.n}</td>
      <td>${wr.toFixed(0)}%</td>
      <td style="color:${exp>=0?'var(--gr)':'var(--re)'}">${(exp>=0?'+':'')+exp.toFixed(0)}€</td>
      <td style="color:${d.total>=0?'var(--gr)':'var(--re)'}">${(d.total>=0?'+':'')+d.total.toFixed(0)}€</td>
      <td><b style="color:${vcol}">${vlabel}</b></td>
    </tr>${sub?`<tr><td colspan="6" style="padding:0 0 4px 8px">${sub}</td></tr>`:''}`;
  }).join('');
}

// ── header stats ───────────────────────────────────────────────────────────────
function updateStats() {
  // top chips removed — the Analytics section owns these now. Kept as a no-op
  // (still called from filter()); guarded so absent elements don't throw.
  const el = document.getElementById('s-wr');
  if (!el) return;
  const n = visible.length;
  const wins  = visible.filter(t=>(t.pnl||0)>0).length;
  const total = visible.reduce((s,t)=>s+(t.pnl||0),0);
  const avg   = n ? total/n : 0;
  el.textContent = n ? (wins/n*100).toFixed(1)+'%' : '—';
  document.getElementById('s-avg').textContent   = n ? (avg>=0?'+':'')+avg.toFixed(0)+'€' : '—';
  document.getElementById('s-n').textContent     = n;
  document.getElementById('s-total').textContent = n ? (total>=0?'+':'')+total.toFixed(0)+'€' : '—';
}

// ── tag filter ─────────────────────────────────────────────────────────────────
function buildTagFilter() {
  const used = [...new Set(ALL_TRADES.map(t=>t.setup_tag).filter(Boolean))].sort();
  const sel  = document.getElementById('f-tag');
  const cur  = sel.value;
  sel.innerHTML = '<option value="">All setups</option><option value="__none__">Untagged</option>';
  used.forEach(tg => { const o=document.createElement('option'); o.value=o.textContent=tg; sel.appendChild(o); });
  sel.value = cur;
}

// ── sync kraken ────────────────────────────────────────────────────────────────
let syncPoll = null;
async function syncKraken() {
  const btn = document.getElementById('sync-btn');
  const st  = document.getElementById('sync-status');
  btn.disabled = true; btn.textContent = 'Syncing…'; st.textContent = '';
  try {
    await fetch('/api/sync/kraken', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    syncPoll = setInterval(async () => {
      const r = await fetch('/api/sync/kraken/result?account=personal');
      const d = await r.json();
      st.textContent = d.detail || '';
      if (!d.running) {
        clearInterval(syncPoll); syncPoll = null;
        btn.disabled = false; btn.textContent = 'Sync Kraken';
        // reload trades
        const res = await fetch('/api/review/trades');
        ALL_TRADES = await res.json();
        buildTagFilter(); filter();
      }
    }, 2000);
  } catch(e) {
    btn.disabled = false; btn.textContent = 'Sync Kraken';
    st.textContent = 'Error: ' + e.message;
  }
}

// ── log trade modal ────────────────────────────────────────────────────────────
function openLogModal() {
  // prefill datetime with now
  const now = new Date();
  const fmt = d => d.toISOString().slice(0,16);
  document.getElementById('m-open').value  = fmt(now);
  document.getElementById('m-close').value = fmt(now);
  document.getElementById('log-modal').classList.add('open');
}
function closeLogModal() {
  document.getElementById('log-modal').classList.remove('open');
}
async function submitLog() {
  const toISO = s => s ? new Date(s).toISOString() : null;
  const payload = {
    direction:  document.getElementById('m-dir').value,
    symbol:     document.getElementById('m-symbol').value,
    entry:      parseFloat(document.getElementById('m-entry').value),
    exit:       parseFloat(document.getElementById('m-exit').value)||null,
    size:       parseFloat(document.getElementById('m-size').value)||0.001,
    leverage:   parseFloat(document.getElementById('m-lev').value)||1,
    pnl:        parseFloat(document.getElementById('m-pnl').value)||null,
    fees:       parseFloat(document.getElementById('m-fees').value)||0,
    notes:      document.getElementById('m-notes').value||null,
    opened_at:  toISO(document.getElementById('m-open').value),
    closed_at:  toISO(document.getElementById('m-close').value),
    venue:      'manual',
  };
  if (!payload.entry) return alert('Entry price required');
  try {
    const r = await fetch('/api/trades', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) { const e=await r.json(); throw new Error(JSON.stringify(e)); }
    closeLogModal();
    // reload
    const res = await fetch('/api/review/trades');
    ALL_TRADES = await res.json();
    buildTagFilter(); filter();
    // select new trade
    pick(ALL_TRADES[ALL_TRADES.length-1].id);
  } catch(e) { alert('Save failed: ' + e.message); }
}

// ── export ─────────────────────────────────────────────────────────────────────
function exportCSV() {
  const hdr = 'id,opened_at,direction,pnl,setup_tag,bar_aligned,trend_4h_aligned,rsi_zone,rsi,move_pct';
  const rows = ALL_TRADES.map(t=>[t.id,t.opened_at,t.direction,t.pnl||0,t.setup_tag||'',
    t.bar_aligned??'',t.trend_aligned??'',t.rsi_zone||'',t.rsi??'',t.move_pct??''].join(','));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([[hdr,...rows].join('\n')],{type:'text/csv'}));
  a.download = 'lens_trades_tagged.csv'; a.click();
}

// ── init ───────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const [tr, ca] = await Promise.all([fetch('/api/review/trades'), fetch('/api/review/ohlcv')]);
    ALL_TRADES = await tr.json();
    CANDLES    = await ca.json();
    series.setData(CANDLES);
    buildTagFilter();
    filter();
    restoreSecs();
    const qid = new URLSearchParams(location.search).get('trade');
    if (qid && ALL_TRADES.some(t => String(t.id)===String(qid))) openTrade(parseInt(qid));
    else if (ALL_TRADES.length) pick(ALL_TRADES[ALL_TRADES.length-1].id);
  } catch(e) {
    document.getElementById('trade-list').innerHTML = `<div style="padding:16px;color:var(--re)">Load error: ${e.message}</div>`;
  }
}
init();
</script>
</body>
</html>
"""
