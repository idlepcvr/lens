"""LENS volatility feed — live BTC ATR for the stop-loss noise floor.

The idea (Prism's): a stop must sit BEYOND the market's normal daily wiggle or
ordinary variance stops you out before your thesis plays. ATR(14d) is the
typical full daily range; the noise floor is a fraction of it (noise_mult). Feed
noise_floor_pct into the calculator's existing min_underlying_stop_pct and its
auto-widen logic (calculator.py) does the rest.

Source is the same OHLCV cache the rest of LENS uses (binance:BTC/USDT 1h,
resampled to daily) — one data path, no new dependency, no live HTTP on render.
"""

import sqlite3
from datetime import datetime, timezone

from .database import DB_PATH

_OHLCV_SYMBOL = "binance:BTC/USDT"


def _daily_candles() -> list[dict]:
    """1h cache → UTC daily OHLC, oldest → newest."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT ts, open, high, low, close FROM ohlcv_cache "
        "WHERE symbol=? AND timeframe='1h' ORDER BY ts DESC LIMIT 480",
        (_OHLCV_SYMBOL,),
    ).fetchall()
    conn.close()
    days: dict = {}
    order: list = []
    for ts, o, h, l, c in rows[::-1]:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d not in days:
            days[d] = {"o": o, "h": h, "l": l, "c": c}; order.append(d)
        else:
            days[d]["h"] = max(days[d]["h"], h)
            days[d]["l"] = min(days[d]["l"], l)
            days[d]["c"] = c
    return [days[d] for d in order]


def fetch_volatility(noise_mult: float = 0.5) -> dict:
    """ATR14 (% of price) + the noise floor a stop must clear.
    noise_mult: fraction of avg daily range (0.5 = half a day's range, Prism's
    conservative minimum; 1.0–1.5 = the standard 'outside the noise' placement)."""
    daily = _daily_candles()
    if not daily:
        return {"btc_usd": None, "atr_14d_pct": None,
                "noise_floor_pct": None, "today_range_pct": None,
                "noise_mult": noise_mult}
    price = daily[-1]["c"]

    atr_pct = None
    if len(daily) >= 15:
        trs = [max(daily[i]["h"] - daily[i]["l"],
                   abs(daily[i]["h"] - daily[i - 1]["c"]),
                   abs(daily[i]["l"] - daily[i - 1]["c"]))
               for i in range(1, len(daily))]
        atr_pct = sum(trs[-14:]) / 14 / price * 100 if price else None

    today = daily[-1]
    today_pct = (today["h"] - today["l"]) / today["o"] * 100 if today["o"] else None
    atr_14d = round(atr_pct, 4) if atr_pct is not None else None
    return {
        "btc_usd":         round(price, 2),
        "atr_14d_pct":     atr_14d,
        "noise_floor_pct": round(atr_14d * noise_mult, 4) if atr_14d is not None else None,
        "today_range_pct": round(today_pct, 4) if today_pct is not None else None,
        "noise_mult":      noise_mult,
    }


if __name__ == "__main__":   # ponytail: one runnable check
    v = fetch_volatility(0.5)
    assert v["atr_14d_pct"] and v["atr_14d_pct"] > 0
    assert v["noise_floor_pct"] == round(v["atr_14d_pct"] * 0.5, 4)
    print(v)
