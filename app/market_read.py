"""What the market looks like right now, in the terms he actually reads.

Built 2026-08-21. The setup gate had become a wall: it said no and gave a hit
rate, which is a verdict without an argument. Going against it should be an
informed decision, so this is the briefing that appears when he does — RSI,
MACD, moving averages, Bollinger position, ATR and trend, each with a stance
and a sentence, computed from the candles already cached locally.

No external chart service. Everything here comes out of `ohlcv_cache`, which
holds 63k hourly bars — and an embedded third-party widget would be blocked by
the page's own rules anyway.

Stances are `bull`, `bear` or `flat`, and `agrees(direction)` counts how many
line up with the trade he is proposing. That count is the honest summary: not
"this is a good trade", but "four of seven readings disagree with you".
"""
from __future__ import annotations

from typing import Optional

from .database import _conn

SYMBOL = "binance:BTC/USDT"      # 63,879 hourly bars, the deepest series cached
TIMEFRAME = "1h"


def _closes(limit: int = 260) -> list[float]:
    c = _conn()
    rows = c.execute(
        "SELECT close, high, low FROM ohlcv_cache WHERE symbol=? AND timeframe=? "
        "ORDER BY ts DESC LIMIT ?", (SYMBOL, TIMEFRAME, limit)).fetchall()
    c.close()
    return [(r["close"], r["high"], r["low"]) for r in reversed(rows)]


def _ema(vals: list[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e


def _rsi(vals: list[float], n: int = 14) -> Optional[float]:
    if len(vals) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = vals[i] - vals[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _stdev(vals: list[float]) -> float:
    m = sum(vals) / len(vals)
    return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5


def read(direction: Optional[str] = None) -> dict:
    """Every reading, with a stance and a sentence. Never raises."""
    try:
        bars = _closes()
        closes = [b[0] for b in bars]
        if len(closes) < 60:
            return {"ok": False, "error": "not enough cached candles"}
        px = closes[-1]
        out: list[dict] = []

        def add(name, value, stance, note):
            out.append({"name": name, "value": value, "stance": stance, "note": note})

        rsi = _rsi(closes)
        add("RSI (14)", f"{rsi:.1f}",
            "bear" if rsi >= 70 else "bull" if rsi <= 30 else
            ("bull" if rsi > 55 else "bear" if rsi < 45 else "flat"),
            "overbought — stretched, not a buy" if rsi >= 70 else
            "oversold — stretched, not a sell" if rsi <= 30 else
            "momentum with the trend" if rsi > 55 else
            "momentum against the trend" if rsi < 45 else "no momentum either way")

        e12, e26 = _ema(closes, 12), _ema(closes, 26)
        macd = (e12 - e26) if (e12 and e26) else None
        sig = _ema([_ema(closes[:i + 1], 12) - _ema(closes[:i + 1], 26)
                    for i in range(26, len(closes))
                    if _ema(closes[:i + 1], 12) and _ema(closes[:i + 1], 26)], 9) \
            if len(closes) > 60 else None
        if macd is not None and sig is not None:
            add("MACD (12/26/9)", f"{macd:+.0f} vs {sig:+.0f}",
                "bull" if macd > sig else "bear",
                "line above signal — momentum building" if macd > sig
                else "line below signal — momentum fading")

        for n in (21, 50, 200):
            e = _ema(closes, n)
            if e:
                add(f"EMA {n}", f"{e:,.0f}", "bull" if px > e else "bear",
                    f"price {'above' if px > e else 'below'} it by "
                    f"{abs(px - e) / e * 100:.2f}%")

        win = closes[-20:]
        mid = sum(win) / len(win)
        sd = _stdev(win)
        if sd:
            z = (px - mid) / sd
            add("Bollinger (20, 2σ)", f"{z:+.2f}σ",
                "bear" if z >= 2 else "bull" if z <= -2 else "flat",
                "riding the upper band — extended" if z >= 2 else
                "riding the lower band — extended" if z <= -2 else
                "inside the bands")

        trs = [max(h - l, abs(h - pc), abs(l - pc))
               for (c_, h, l), (pc, _, _) in zip(bars[-15:], bars[-16:-1])]
        atr = sum(trs) / len(trs) if trs else None
        if atr:
            add("ATR (14, 1h)", f"{atr:,.0f}", "flat",
                f"a typical hour moves ±{atr / px * 100:.2f}%")

        agree = sum(1 for r in out if r["stance"] == ("bull" if direction == "long" else "bear"))
        against = sum(1 for r in out if r["stance"] == ("bear" if direction == "long" else "bull"))
        return {"ok": True, "price": px, "symbol": SYMBOL, "timeframe": TIMEFRAME,
                "readings": out, "agree": agree, "against": against,
                "direction": direction}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
