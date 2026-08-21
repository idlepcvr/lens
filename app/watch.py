"""Tell him when a working order fires, and where the month stands.

Until now a take profit could fill while he slept and nothing would say so —
the position page only reports a fill if he happens to be looking at it. This
runs on cron and pushes to the phone he already has ntfy on.

Two pushes, both deliberately quiet:

  * a fill — a resting order disappeared and the position moved with it. Says
    which one fired, at what price, and what the balance did.
  * a daily rung check — where the stack sits against this month's target.
    One a day, not one an hour: a target you are reminded of hourly stops
    being a target and starts being noise.

State lives in a JSON file beside the database, so a restart never re-announces
a fill that already happened.

    python3 -m app.watch          # cron entry point
    python3 -m app.watch --dry    # print, push nothing
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .kraken_sync import fetch_live_balance, fetch_open_orders, get_api_keys, \
    fetch_open_positions_enriched

STATE = Path(__file__).resolve().parent.parent / "data" / "watch_state.json"
RUNG_HOUR = 8          # local hour for the daily rung check


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=1))


def _fmt(v, dp=0) -> str:
    return "—" if v is None else f"{v:,.{dp}f}"


def rung_line() -> str:
    """Where the stack sits against the month's target, in one line."""
    try:
        from . import plan
        l = plan.ladder()
        cur = (l["stack"] or {}).get("btc_total")
        nxt = next((m for m in l["milestones"] if not m.get("done")), None)
        if not cur or not nxt:
            return ""
        gap = nxt["btc"] - cur
        pct = cur / nxt["btc"] * 100 if nxt["btc"] else 0
        return (f"{cur:.5f} / {nxt['btc']:.5f} BTC ({pct:.0f}%) — "
                f"{gap:.5f} to {nxt['label']} by {nxt.get('by') or nxt.get('date')}")
    except Exception:
        return ""


def check(dry: bool = False) -> dict:
    from .setups import _notify

    key, secret = get_api_keys("personal")
    orders = fetch_open_orders(key, secret, "personal")
    pos = fetch_open_positions_enriched(key, secret, "personal")
    bal = fetch_live_balance(key, secret)

    size = float(pos[0]["size"]) if pos else 0.0
    eur = bal.get("eur_balance")
    now = datetime.now(timezone.utc)

    prev = _load()
    prev_orders = {o["order_id"]: o for o in prev.get("orders", [])}
    prev_size = prev.get("size")
    prev_eur = prev.get("eur")

    fired = []
    live_ids = {o["order_id"] for o in orders}
    for oid, o in prev_orders.items():
        if oid in live_ids:
            continue
        # Gone from the book. If the position shrank too, it filled rather than
        # being cancelled — a cancel leaves the position exactly where it was.
        if prev_size is not None and size < prev_size - 1e-9:
            fired.append(o)

    out = {"fired": [], "rung": None}

    for o in fired:
        win = o["role"] == "take_profit"
        moved = (eur - prev_eur) if (eur is not None and prev_eur is not None) else None
        title = ("Take profit hit" if win else
                 "Stop hit" if o["role"] == "stop_loss" else "Order filled")
        body = (f"{_fmt(o.get('trigger'))} · "
                + (f"{'+' if moved >= 0 else '−'}€{abs(moved):,.2f} · "
                   if moved is not None else "")
                + (f"position now {size:.4f} BTC" if size else "position now flat"))
        r = rung_line()
        if r:
            body += f"\n{r}"
        out["fired"].append({"title": title, "body": body})
        if not dry:
            _notify(title, body, tags="white_check_mark" if win else "x")

    # once a day, and only after the chosen hour
    today = date.today().isoformat()
    if prev.get("rung_date") != today and datetime.now().hour >= RUNG_HOUR:
        r = rung_line()
        if r:
            out["rung"] = r
            if not dry:
                _notify("This month's rung", r, tags="dart")
            prev["rung_date"] = today

    if not dry:
        _save({"orders": orders, "size": size, "eur": eur,
               "ts": now.isoformat(), "rung_date": prev.get("rung_date")})
    return out


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    res = check(dry=dry)
    for f in res["fired"]:
        print(f"{f['title']}: {f['body']}")
    if res["rung"]:
        print(f"rung: {res['rung']}")
    if not res["fired"] and not res["rung"]:
        print("nothing to report")
