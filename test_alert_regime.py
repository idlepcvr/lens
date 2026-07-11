"""The regime badge on the alert ticket (pre-trade, not post-mortem).

The contract: STARVED reaches the ASCII title so it lands on the lock screen, and
a badge that cannot be computed NEVER blocks the push. A missing alert is a worse
failure than a missing badge.

Run: python test_alert_regime.py
"""
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import app.setups as setups

SIG = {
    "trigger_type": "S1", "direction": "short", "signal_id": "t-1",
    "entry_price": 60000.0, "target_price": 59430.0, "stop_price": 60378.0,
}


def _shape(_sig):
    return {
        "long": False, "entry": 60000.0, "target": 59430.0, "stop": 60378.0,
        "win_move_pct": 0.95, "loss_move_pct": 0.63, "account": 5000.0,
        "reward_usd": 47.5, "risk_usd": 31.5, "notional": 5000.0,
        "leverage": 5.0, "loss_pct": 0.63,
    }


setups._trade_shape = _shape
_real_badge = setups._regime_badge   # capture BEFORE the stubs below replace it

# 1. STARVED rides the title AND the body, and adds the warning tag.
setups._regime_badge = lambda *_a: {
    "badge": "STARVED", "text": "needs 4/wk · SIDEWAYS regime offers ~1/wk of >=0.95% moves"}
title, body, tag = setups._alert_message(SIG)
assert title.startswith("[STARVED] "), title
assert "S1 SHORT BTC" in title, title
assert "STARVED" in body, body
assert "warning" in tag, tag
assert title.encode("latin-1"), "ntfy titles must be latin-1 encodable"

# 2. OFFERED is informational: body only, no title shout, no warning tag.
setups._regime_badge = lambda *_a: {"badge": "OFFERED", "text": "needs 4/wk · offers ~9/wk"}
title, body, tag = setups._alert_message(SIG)
assert not title.startswith("["), title
assert "OFFERED" in body, body
assert "warning" not in tag, tag

# 3. TIGHT likewise reports without shouting.
setups._regime_badge = lambda *_a: {"badge": "TIGHT", "text": "needs 4/wk · offers ~4/wk"}
title, body, tag = setups._alert_message(SIG)
assert not title.startswith("["), title
assert "TIGHT" in body, body

import app.excursion as _excursion
import app.realism as _realism


def _raise(*_a, **_k):
    raise RuntimeError("ohlcv cache is empty")


_saved_reach, _saved_badge = _excursion.reachability, _realism.badge

# 4. His own fills outrank the day-range proxy. Given a loss move, reachability
#    answers and realism is never consulted (it would raise if it were).
_excursion.reachability = lambda *_a, **_k: {"badge": "STARVED", "text": "ceiling 34%"}
_realism.badge = _raise
assert _real_badge(0.95, 0.63)["text"] == "ceiling 34%", "excursion must win when it answers"

# 5. Under min_n reachability returns None -> fall back to the proxy, don't crash.
_excursion.reachability = lambda *_a, **_k: None
_realism.badge = lambda *_a, **_k: {"badge": "OFFERED", "text": "proxy"}
assert _real_badge(0.95, 0.63)["text"] == "proxy", "None reachability falls back to realism"

# 6. THE IMPORTANT ONE: both sources dead must not take the alert with them.
_excursion.reachability = _raise
_realism.badge = _raise
assert _real_badge(0.95, 0.63) is None, "a raising badge must yield None, not propagate"

# ...and the ticket still builds, unbadged.
setups._regime_badge = _real_badge
title, body, tag = setups._alert_message(SIG)
assert "S1 SHORT BTC" in title and "Regime" not in body, "push survives a dead badge"
_excursion.reachability, _realism.badge = _saved_reach, _saved_badge

# 7. No badge at all -> a clean ticket, unchanged from before this feature.
setups._regime_badge = lambda *_a: None
title, body, tag = setups._alert_message(SIG)
assert not title.startswith("["), title
assert "Regime" not in body, body
assert "warning" not in tag, tag

# 8. A zero/None required move can't be checked -> no badge, no crash.
assert _real_badge(0, 0.63) is None
assert _real_badge(None, 0.63) is None

print("ok — 18 checks passed")
