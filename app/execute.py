"""LENS execution — a full order ticket, not a buy button.

Built 2026-08-20. The first cut sent a market order and a size, which is the
one thing the exchange's own form makes hardest to get wrong. What it dropped
was the part LENS is actually better at: this app already computes the take
profit and the stop loss for every ticket, and the website makes you retype
them. So the bracket is the point — entry, TP and SL leave together.

Gates, all mandatory, evaluated server-side and re-evaluated on send so a stale
page can never talk the server into an order:

  1. confirm=True          — no scan or page load can send
  2. discipline.evaluate() — his own bleed-hour / revenge-cooldown / venue rules
  3. size ceiling          — LENS_MAX_ORDER_BTC, the caller cannot raise it
  4. bracket sanity        — a long's TP above and SL below the entry, and the
                             reverse for a short. Sending a stop on the wrong
                             side fills instantly at market; the exchange will
                             happily do it, so this is checked here.

# ponytail: fills are NOT written to the DB here. kraken_sync imports them and
# _link_signal claims the signal; a second write recreates the manual-twin merge
# problem that logic exists to solve.
"""
from __future__ import annotations

import os
from typing import Optional

from . import discipline
from .kraken_sync import get_api_keys

SYMBOL = "PF_XBTUSD"                      # 523 of 523 fills in the book
_SIDE = {"long": "buy", "short": "sell"}
_OPPOSITE = {"long": "short", "short": "long"}
ORDER_TYPES = ("mkt", "lmt", "post", "ioc")   # ioc = immediate-or-cancel
TRIGGERS = ("mark", "index", "last")


class NoDemoKeys(RuntimeError):
    """Demo is a separate Kraken account with its own credentials — a live key
    against demo-futures.kraken.com gets an HTML login page, not a JSON error."""


def sandbox() -> bool:
    """Demo unless explicitly switched off, so a missing env var can never mean
    'send this to the real account'."""
    return os.getenv("KRAKEN_FUTURES_SANDBOX", "1").strip() != "0"


_BAL_CACHE: dict = {"t": 0.0, "eur": None, "fx": None}
_BAL_TTL = 60.0


def _account() -> tuple[Optional[float], float]:
    """(balance EUR, EUR/USD). Cached — check() runs on every keystroke and the
    exchange does not need to hear about each one."""
    import time
    now = time.time()
    if _BAL_CACHE["eur"] is not None and now - _BAL_CACHE["t"] < _BAL_TTL:
        return _BAL_CACHE["eur"], _BAL_CACHE["fx"] or 1.0
    try:
        from .kraken_sync import fetch_live_balance
        key, secret = get_api_keys("personal")
        b = fetch_live_balance(key, secret)
        _BAL_CACHE.update({"t": now, "eur": b.get("eur_balance"),
                           "fx": b.get("eur_usd") or 1.0})
    except Exception:
        pass
    return _BAL_CACHE["eur"], _BAL_CACHE["fx"] or 1.0


def max_order_btc(leverage: float = 10.0, mark_usd: Optional[float] = None) -> float:
    """The ceiling, derived rather than typed.

    It used to be a fixed BTC number I picked (0.005), which is meaningless
    until converted: against a EUR 305 balance that was 1.0x, while 0.5 BTC —
    the fat-finger case it existed to stop — was 101x. Expressed as leverage the
    limit explains itself, and it moves with the account instead of going stale.

        ceiling = balance x max leverage, in BTC

    LENS_MAX_ORDER_BTC still wins if set, as a deliberate manual brake.
    """
    hard = os.getenv("LENS_MAX_ORDER_BTC", "").strip()
    if hard:
        return float(hard)
    bal_eur, fx = _account()
    if not bal_eur or not mark_usd or not leverage:
        return 0.01                      # no balance yet — stay conservative
    btc_eur = mark_usd / (fx or 1.0)
    return (bal_eur * leverage) / btc_eur


def _client(account: str = "personal"):
    from kraken.futures import Trade
    if sandbox():
        key = os.getenv("KRAKEN_FUTURES_DEMO_API_KEY", "")
        secret = os.getenv("KRAKEN_FUTURES_DEMO_API_SECRET", "")
        if not key or not secret:
            raise NoDemoKeys(
                "KRAKEN_FUTURES_DEMO_API_KEY/_SECRET are not set. Register at "
                "demo-futures.kraken.com for demo credentials, or set "
                "KRAKEN_FUTURES_SANDBOX=0 to trade the live account.")
        return Trade(key=key, secret=secret, sandbox=True)
    key, secret = get_api_keys(account)
    return Trade(key=key, secret=secret, sandbox=False)


# ─── the ticket ──────────────────────────────────────────────────────────────

def build_orders(direction: str, size_btc: float, *, order_type: str = "mkt",
                 limit_price: Optional[float] = None,
                 take_profit: Optional[float] = None,
                 stop_loss: Optional[float] = None,
                 reduce_only: bool = False, post_only: bool = False,
                 trigger_signal: str = "mark",
                 signal_id: Optional[str] = None) -> list[dict]:
    """The exact batch that would be sent. Pure — no network, no side effects,
    so the confirm dialog and the sender can render the same thing."""
    side = _SIDE[direction]
    exit_side = _SIDE[_OPPOSITE[direction]]
    otype = "post" if post_only else order_type

    entry: dict = {"order": "send", "order_tag": "entry", "orderType": otype,
                   "symbol": SYMBOL, "side": side, "size": size_btc}
    if otype in ("lmt", "post", "ioc") and limit_price is not None:
        entry["limitPrice"] = limit_price
    if reduce_only:
        entry["reduceOnly"] = True
    if signal_id:
        entry["cliOrdId"] = str(signal_id)[:36]

    batch = [entry]

    # TP and SL close the position, so they are the opposite side and reduce-only.
    if take_profit:
        batch.append({"order": "send", "order_tag": "tp", "orderType": "take_profit",
                      "symbol": SYMBOL, "side": exit_side, "size": size_btc,
                      "stopPrice": take_profit, "triggerSignal": trigger_signal,
                      "reduceOnly": True})
    if stop_loss:
        batch.append({"order": "send", "order_tag": "sl", "orderType": "stp",
                      "symbol": SYMBOL, "side": exit_side, "size": size_btc,
                      "stopPrice": stop_loss, "triggerSignal": trigger_signal,
                      "reduceOnly": True})
    return batch


def setup_gate(direction: str) -> Optional[str]:
    """Refuse an entry the setup scanner has already judged.

    Measured over the whole hedge book on 2026-08-21, by setup_tag:

        S1                   12 trades   83.3% WR   +EUR 933
        S3                   42 trades   45.2% WR   +EUR 178
        NONE                 97 trades   35.1% WR   -EUR 2432
        VETO:* (all)        ~258 trades  20-48% WR  -EUR 6000+

    The three clean setups are +EUR 1239 between them. Everything else is the
    loss. discipline.evaluate() never looked at this — it checks the clock, the
    cooldown and the venue, so a NONE entry at a good hour sailed through.

    Returns a reason string to block, or None to allow. Never raises: a scanner
    that cannot read a bar must not also stop him closing a position.
    """
    if os.getenv("LENS_ALLOW_UNTAGGED", "0").strip() == "1":
        return None
    try:
        from . import setups
        state = setups.desk_state(refresh=False)
        v = (state.get("verdicts") or {}).get(direction) or {}
        vetoes = v.get("vetoes") or []
        hits = v.get("setups") or []
        board = state.get("scoreboard") or {}

        def stat(tag):
            row = board.get(tag) or {}
            if not row.get("n"):
                return ""
            return f" [{tag}: {row['n']} trades, {row['wr']}% WR, EUR {row['pnl']:.0f}]"

        if hits and not vetoes:
            return None
        if vetoes:
            return "setup_veto:" + ",".join(vetoes)[:120] + stat("VETO:" + ",".join(vetoes))
        return "no_setup" + stat("NONE")
    except Exception:
        return None


def check(direction: str, size_btc: float, *, order_type: str = "mkt",
          limit_price: Optional[float] = None, take_profit: Optional[float] = None,
          stop_loss: Optional[float] = None, mark: Optional[float] = None,
          reduce_only: bool = False, post_only: bool = False,
          trigger_signal: str = "mark", leverage: float = 10.0,
          signal_id: Optional[str] = None, override_reason: Optional[str] = None,
          last_signal: Optional[dict] = None, venue: str = "kraken_futures") -> dict:
    """Every gate, evaluated, nothing sent."""
    reasons: list[str] = []

    if direction not in _SIDE:
        reasons.append(f"bad_direction:{direction}")
    if order_type not in ORDER_TYPES:
        reasons.append(f"bad_order_type:{order_type}")
    if trigger_signal not in TRIGGERS:
        reasons.append(f"bad_trigger:{trigger_signal}")
    if not size_btc or size_btc <= 0:
        reasons.append("size_not_positive")

    cap = max_order_btc(leverage, limit_price or mark)
    if size_btc and size_btc > cap:
        reasons.append(f"over_size_cap:{size_btc:.5f}>{cap:.5f} "
                       f"(= balance x {leverage:g} leverage)")

    if (order_type in ("lmt", "post", "ioc") or post_only) and not limit_price:
        reasons.append("limit_price_required")

    # bracket sanity, against the limit price if there is one, else the mark
    ref = limit_price or mark
    if ref and direction in _SIDE:
        long_ = direction == "long"
        if take_profit:
            if long_ and take_profit <= ref:
                reasons.append(f"tp_below_entry:{take_profit}<={ref}")
            if not long_ and take_profit >= ref:
                reasons.append(f"tp_above_entry:{take_profit}>={ref}")
        if stop_loss:
            if long_ and stop_loss >= ref:
                reasons.append(f"sl_above_entry:{stop_loss}>={ref}")
            if not long_ and stop_loss <= ref:
                reasons.append(f"sl_below_entry:{stop_loss}<={ref}")

    veto = discipline.evaluate({"venue": venue}, last_signal)
    if veto:
        reasons.append(veto)

    # An exit is never blocked by the setup: closing a losing position is the
    # one trade that must always be available.
    overriding = False
    setup_note = None
    if not reduce_only:
        setup_note = setup_gate(direction)
        if setup_note:
            from .veto_log import valid_reason
            if valid_reason(override_reason):
                # He has stated what he sees. That is more useful recorded and
                # taken than refused and repeated on his phone where nothing
                # can measure it.
                overriding = True
            else:
                reasons.append(setup_note)

    notional = (size_btc or 0) * (ref or 0)
    return {
        "ok": not reasons,
        "reasons": reasons,
        "sandbox": sandbox(),
        "symbol": SYMBOL,
        "side": _SIDE.get(direction),
        "size_btc": size_btc,
        "size_cap_btc": cap,
        "size_cap_usd": round(cap * (limit_price or mark or 0), 2) or None,
        "order_type": "post" if post_only else order_type,
        "notional_usd": round(notional, 2),
        "required_margin_usd": round(notional / leverage, 2) if leverage else None,
        "reduce_only": reduce_only,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "trigger_signal": trigger_signal,
        "discipline": discipline.settings(),
        "setup_note": setup_note,
        "overriding": overriding,
        "orders": build_orders(direction, size_btc or 0, order_type=order_type,
                               limit_price=limit_price, take_profit=take_profit,
                               stop_loss=stop_loss, reduce_only=reduce_only,
                               post_only=post_only, trigger_signal=trigger_signal,
                               signal_id=signal_id)
        if direction in _SIDE else [],
    }


# Kraken answers `result: success` for the API CALL, and puts the fate of the
# order in a status field alongside it. An order rejected for insufficient funds
# comes back inside a "successful" response, which is how a rejection was
# reported to him as "sent" on 2026-08-21 — the position stayed flat and nothing
# in LENS said otherwise.
_ACCEPTED = {"placed", "partiallyfilled", "filled", "edited", "untouched"}


def interpret(resp: dict) -> dict:
    """What the exchange actually did, out of its envelope.

    Returns {ok, states, detail} where ok is True only if every leg landed.
    """
    if not isinstance(resp, dict):
        return {"ok": False, "states": [], "detail": "no response"}

    legs: list[tuple[str, str]] = []
    for item in (resp.get("batchStatus") or []):
        legs.append((item.get("order_tag") or "order",
                     (item.get("status") or "unknown")))
    send = resp.get("sendStatus")
    if send:
        legs.append(("order", (send.get("status") or "unknown")))

    if not legs:
        # nothing to read: treat a bare success as unconfirmed, not as done
        return {"ok": resp.get("result") == "success", "states": [],
                "detail": "no per-order status returned — treat as unconfirmed"}

    bad = [f"{tag}: {st}" for tag, st in legs if st.lower() not in _ACCEPTED]
    return {"ok": not bad,
            "states": [{"leg": t, "status": st} for t, st in legs],
            "detail": "; ".join(bad) if bad else
                      "; ".join(f"{t}: {st}" for t, st in legs)}


def execute(direction: str, size_btc: float, *, confirm: bool = False,
            account: str = "personal", last_signal: Optional[dict] = None,
            **ticket) -> dict:
    """Send the ticket. Refuses unless confirm=True and every gate passes."""
    pre = check(direction, size_btc, last_signal=last_signal, **ticket)

    if not confirm:
        return {**pre, "sent": False, "blocked": "not_confirmed"}
    if not pre["ok"]:
        return {**pre, "sent": False, "blocked": pre["reasons"][0]}

    batch = pre["orders"]
    try:
        client = _client(account)
        if len(batch) == 1:
            o = {k: v for k, v in batch[0].items() if k not in ("order", "order_tag")}
            resp = client.create_order(**o)
        else:
            resp = client.create_batch_order(batchorder_list=batch)
    except NoDemoKeys as exc:
        return {**pre, "sent": False, "blocked": "no_demo_keys", "error": str(exc)}
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        if "<!DOCTYPE html>" in msg or "<html" in msg:
            msg = ("the exchange returned an HTML page instead of JSON — almost "
                   "always wrong-environment credentials (a live key sent to demo, "
                   "or the reverse)")
        return {**pre, "sent": False, "blocked": "exchange_error", "error": msg[:300]}

    verdict = interpret(resp)
    if not verdict["ok"]:
        # The call succeeded and the order did not. Saying "sent" here is how a
        # rejection became invisible.
        return {**pre, "sent": False, "blocked": "exchange_rejected",
                "error": verdict["detail"], "states": verdict["states"],
                "response": resp}

    if pre.get("overriding"):
        try:
            from .veto_log import record
            from . import setups
            state = setups.desk_state(refresh=False)
            record(direction, size_btc,
                   entry=ticket.get("limit_price") or ticket.get("mark"),
                   leverage=ticket.get("leverage"),
                   take_profit=ticket.get("take_profit"),
                   stop_loss=ticket.get("stop_loss"),
                   setup_tag=pre.get("setup_note"),
                   veto_reasons=((state.get("verdicts") or {}).get(direction) or {}).get("vetoes"),
                   user_reason=ticket.get("override_reason") or "",
                   context=state.get("context"))
        except Exception:
            pass          # a failed note must never unsend a placed order

    return {**pre, "sent": True, "accepted": verdict["detail"],
            "states": verdict["states"], "response": resp}


def close(direction_of_position: str, size_btc: float, **kw) -> dict:
    """Close or trim an open position: opposite side, reduce-only, market."""
    kw.pop("take_profit", None)
    kw.pop("stop_loss", None)
    return execute(_OPPOSITE[direction_of_position], size_btc,
                   reduce_only=True, order_type="mkt", **kw)


def cancel_all(account: str = "personal") -> dict:
    """Pull every resting order — the panic button for orphaned TP/SL legs."""
    try:
        return {"ok": True, "response": _client(account).cancel_all_orders(symbol=SYMBOL)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
