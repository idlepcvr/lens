"""LENS /overview — one read-only snapshot for BOTH books.

Three blocks (toggle hedge ↔ prop in the page):
  • Live account   — equity / available margin / unrealised PnL
                     (hedge = live Kraken; prop = manual eval ledger vs walls)
  • Performance    — closed-trade stats for that book (review_analytics)
  • Market         — BTC price, ATR(14d), today's range, noise floor

Performance + Market are computed server-side (DB only, fast). The live Kraken
pull is async client-side via /api/account/live so the page never blocks on it.
"""

from .review import review_analytics
from .prop_ledger import prop_ledger_data
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
    """Both books in one payload — the page toggles between them client-side.
    Live Kraken equity is fetched separately (async) for the hedge block."""
    prop = prop_ledger_data()
    return {
        "market": market_snapshot(),
        "hedge": {"performance": review_analytics(book="hedge")},
        "prop": {
            "performance": review_analytics(book="prop"),
            "live": {
                "equity":       prop["equity"],
                "account":      prop["account"],
                "to_target":    prop["to_target_usd"],
                "to_floor":     prop["to_floor_usd"],
                "target":       prop["target"],
                "floor":        prop["floor"],
                "cur_dd_pct":   prop["cur_dd_pct"],
                "today_pnl":    prop["today_pnl"],
            },
        },
    }
