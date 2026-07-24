"""The reach verdict on the alert ticket.

Contract, and every line of it is a scar:

  · The badge rides the BODY. It NEVER touches the title. The verdict reads the
    geometry (a fixed TP/SL), not the moment, so for a given setup it returns the
    same word on every signal forever. In the title that is an alarm firing 100%
    of the time — an alarm you learn to ignore, which is worse than no alarm.
    This has been wired to the title twice and removed twice. Don't be the third.

  · A badge that cannot be computed NEVER blocks the push. A missing badge costs
    a line of text. A missing alert costs the trade.

Run: .venv/bin/python3 test_alert_regime.py
"""
import os

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
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
_real_badge = setups._regime_badge      # capture BEFORE the stubs replace it

# 1. Every verdict reports in the body and NONE of them shout in the title.
#    STARVED is the one that would tempt you. It still doesn't get the title.
for word in ("STARVED", "TIGHT", "OFFERED"):
    setups._regime_badge = lambda *_a, _w=word: {"badge": _w, "text": "needs 4/wk · offers ~1/wk"}
    title, body, tag = setups._alert_message(SIG)
    assert word in body, f"{word} must reach the body"
    assert not title.startswith("["), f"{word} must NOT shout in the title: {title}"
    assert "S1 SHORT BTC" in title, title
    assert "warning" not in tag, f"{word} must not tag the push as a warning"
    assert title.encode("latin-1"), "ntfy titles must be latin-1 encodable"

# 2. No badge → a clean ticket, exactly as it was before the feature existed.
setups._regime_badge = lambda *_a: None
title, body, tag = setups._alert_message(SIG)
assert not title.startswith("["), title
assert "Reach" not in body, body

# ── the badge itself: authority order, and it must never take the alert down ──
import app.excursion as _excursion
import app.realism as _realism


def _raise(*_a, **_k):
    raise RuntimeError("ohlcv cache is empty")


_saved_reach, _saved_badge = _excursion.reachability, _realism.badge

# 3. His own fills outrank the day-range proxy. Given a real answer from
#    reachability, realism is never consulted — it would raise if it were.
_excursion.reachability = lambda *_a, **_k: {"badge": "STARVED", "text": "ceiling 34%"}
_realism.badge = _raise
assert _real_badge(0.95, 0.63)["text"] == "ceiling 34%", "excursion must win when it answers"

# 4. Under min_n reachability returns None → fall back to the proxy, don't crash.
_excursion.reachability = lambda *_a, **_k: None
_realism.badge = lambda *_a, **_k: {"badge": "OFFERED", "text": "proxy"}
assert _real_badge(0.95, 0.63)["text"] == "proxy", "None reachability falls back to realism"

# 5. THE IMPORTANT ONE: both sources dead must not take the alert with them.
_excursion.reachability = _raise
_realism.badge = _raise
assert _real_badge(0.95, 0.63) is None, "a raising badge must yield None, not propagate"

setups._regime_badge = _real_badge
title, body, tag = setups._alert_message(SIG)
assert "S1 SHORT BTC" in title and "Reach" not in body, "the push survives a dead badge"
_excursion.reachability, _realism.badge = _saved_reach, _saved_badge

# 6. A zero/None required move can't be judged → no badge, no crash.
assert _real_badge(0, 0.63) is None
assert _real_badge(None, 0.63) is None

print("ok — verdict reports in the body, never the title, and never eats an alert")
