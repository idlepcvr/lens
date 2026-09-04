"""LENS /overview — one read-only snapshot of the hedge book.

Three blocks:
  • Live account   — equity / available margin / unrealised PnL (live Kraken)
  • Performance    — closed-trade stats (review_analytics)
  • Market         — BTC price, ATR(14d), today's range, noise floor

Performance + Market are computed server-side (DB only, fast). The live Kraken
pull is async client-side via /api/account/live so the page never blocks on it.

Was a hedge↔prop toggle in one payload until the 2026-09-05 hedge/prop split;
the prop block (fed by prop_ledger_data) is gone with the prop book.
"""

from .review import review_analytics
from .volatility import fetch_volatility


def market_snapshot() -> dict:
    """BTC price, ATR(14d)% and today's range% — the overview Market block.
    ATR itself is the ~24h min viable stop, so noise floor here uses mult 1.0."""
    v = fetch_volatility(noise_mult=1.0)
    atr_pct = round(v["atr_14d_pct"], 2) if v["atr_14d_pct"] is not None else None
    rng_pct = round(v["today_range_pct"], 2) if v["today_range_pct"] is not None else None
    if rng_pct is None or atr_pct is None:
        regime = "—"
    elif rng_pct < atr_pct * 0.5:
        regime = "quiet"
    elif rng_pct <= atr_pct:
        regime = "normal"
    else:
        regime = "wide"
    return {
        "btc_price":   round(v["btc_usd"], 0) if v["btc_usd"] is not None else None,
        "atr_pct":     atr_pct,
        "noise_floor": atr_pct,          # ATR = ~24h min viable stop
        "range_pct":   rng_pct,
        "regime":      regime,
    }


def overview_data() -> dict:
    """The hedge book's snapshot. Live Kraken equity is fetched separately
    (async, client-side) for the hero block."""
    return {
        "market": market_snapshot(),
        "hedge": {"performance": review_analytics(book="hedge")},
    }
