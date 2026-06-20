"""LENS prop scanner — the live alert for the PROP hero (ASIAN_RSI_DIP_v1).

Mirrors the HEDGE app.setups loop, but for the prop eval and on a 4H cadence.
Reuses the same read the /prop-desk page shows (prop_desk_state) so the alert
and the page never disagree. On an Asian-session 4H close where the hero says
ENTER, it inserts ONE prop signal (deduped by bar) and pushes a phone alert with
TAKE / SKIP buttons — same decide path as HEDGE (POST /api/signals/{id}/decide).

Run from repo root (cron):  python3 -m app.prop_scan
The scanner self-gates: non-Asian closes and STAND DOWN bars emit nothing, so it
is safe to run at every 4H boundary.
"""
from __future__ import annotations

import datetime

from .prop_eval import EVALS, _legal_leverage
from .prop_views import ACCOUNT, EVAL, HERO, RISK
from .setups import _notify

PROP_STRATEGY = HERO            # "ASIAN_RSI_DIP_v1" — the prop signal discriminator
MM_RATE = 0.005                 # maintenance margin assumption (Kraken BTC perp ~0.5%)


def prop_ticket(entry: float, stop: float, target: float, long_: bool) -> dict:
    """Prop-legal order ticket from a signal's levels — same sizing math as
    prop_desk_state (risk% of the $5k eval account, leverage capped at the firm's
    5x). Deterministic from entry/stop/target, so it recomputes identically for a
    live pending signal or a historical one on the review page."""
    rule = EVALS[EVAL]
    fee_rt = rule.get("commission_per_side", 0.0004) * 2
    stop_pct = abs(entry - stop) / entry * 100 if entry else 0.0
    tp_pct = abs(target - entry) / entry * 100 if entry else 0.0
    lev, actual_risk = _legal_leverage(stop_pct, RISK, rule["max_leverage"])
    risk_usd = ACCOUNT * RISK / 100.0
    notional = risk_usd / (stop_pct / 100.0) if stop_pct else 0.0
    size_btc = notional / entry if entry else 0.0
    margin = notional / lev if lev else 0.0
    fee_usd = notional * fee_rt
    win_usd = notional * (tp_pct / 100.0) - fee_usd
    loss_usd = risk_usd + fee_usd
    breakeven = entry * (1 + fee_rt) if long_ else entry * (1 - fee_rt)
    liq = entry * (1 - 1 / lev + MM_RATE) if long_ else entry * (1 + 1 / lev - MM_RATE)
    liq = liq if liq and liq > 0 else None
    return {
        "account": ACCOUNT, "risk_pct": RISK, "leverage": round(lev, 2),
        "actual_risk_pct": round(actual_risk, 2), "notional": round(notional, 2),
        "size_btc": size_btc, "margin_usd": round(margin, 2),
        "win_usd": round(win_usd, 2), "loss_usd": round(loss_usd, 2),
        "risk_usd": round(risk_usd, 2), "fee_rt_pct": fee_rt * 100,
        "breakeven": round(breakeven, 1), "liq": round(liq, 1) if liq else None,
        "stop_pct": round(stop_pct, 2), "tp_pct": round(tp_pct, 2),
        "rr": round(tp_pct / stop_pct, 2) if stop_pct else 0.0,
        "max_leverage": rule["max_leverage"],
        "eval": EVAL, "strategy": PROP_STRATEGY,
    }


def _prop_alert_message(sig: dict) -> tuple[str, str, str]:
    """Slim prop ticket for the lock screen — full detail lives on /prop-signals."""
    entry, stop, target = sig["entry_price"], sig["stop_price"], sig["target_price"]
    long_ = sig["direction"] == "long"
    t = prop_ticket(entry, stop, target, long_)
    side = "LONG" if long_ else "SHORT"
    arrow = "▲" if long_ else "▼"
    head = "\U0001F7E2" if long_ else "\U0001F534"     # 🟢 / 🔴
    win_bal, lose_bal = t["account"] + t["win_usd"], t["account"] - t["loss_usd"]

    def m(x):
        return f"{x:,.0f}" if x is not None else "—"

    W = 13

    def L(em, lab, val):
        return f"{em} {lab:<{W}}{val}\n"

    title = f"PROP {side} BTC {m(entry)}"
    body = (
        f"{head} PROP · {side} · BTC/USD {arrow}\n"
        f"\U0001F9E0 Asian-session RSI reclaim (4H eval)\n"               # 🧠
        "\n"
        + L("\U0001F4E5", "Entry (in)", m(entry))                         # 📥
        + L("\U0001F3AF", "TP  (out)", f"{m(target)} · +{t['tp_pct']:.2f}%")   # 🎯
        + L("\U0001F6D1", "SL  (out)", f"{m(stop)} · −{t['stop_pct']:.2f}%")   # 🛑
        + "\n"
        + L("\U0001F4C8", "Win bal", f"${m(win_bal)}  (+${m(t['win_usd'])})")  # 📈
        + L("\U0001F4C9", "Lose bal", f"${m(lose_bal)}  (−${m(t['loss_usd'])})")  # 📉
        + "\n"
        + L("\U0001F4E6", "Notional", f"${m(t['notional'])}")             # 📦
        + L("\U0001FA99", "Size", f"{t['size_btc']:.4f} ₿")          # 🪙
        + L("⚡", "Leverage", f"{t['leverage']:g}× (cap {t['max_leverage']:g}×)")  # ⚡
        + L("\U0001F6A6", "Risk", f"${m(t['risk_usd'])} · {t['actual_risk_pct']:.1f}% (prop)")  # 🚦
        + "\n"
        + "\U0001F4DD /prop-signals to review → log to ledger"            # 📝
    )
    tag = "green_circle" if long_ else "red_circle"
    return title, body, tag


def run_prop_scan_cli(emit: bool = True) -> dict:
    """Cron entry point: read the hero on the freshest closed 4H bar; on an ENTER
    at an Asian close, insert one deduped prop signal and push the alert."""
    from .database import init_db, insert_signal
    from .prop_desk import prop_desk_state

    init_db()
    state = prop_desk_state(refresh=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    if state.get("error"):
        print(f"[{stamp}] prop-scan error: {state['error']}")
        return state

    verdict = state.get("verdict")
    direction = state.get("direction")
    bar_ts = state.get("bar_ts")
    emitted = "none"

    if emit and verdict == "enter" and direction and state.get("is_asian"):
        plan = state["plan"][direction]
        # deterministic id per bar → a second scan of the same bar is a no-op
        sig_id = f"prop-{bar_ts.replace(':', '').replace('-', '')}"
        payload = {
            "signal_id": sig_id,
            "strategy_name": PROP_STRATEGY,
            "strategy_version": "1.0",
            "symbol": "BTC/USD",
            "venue": "kraken_futures",
            "trigger_type": "ASIAN_RSI_DIP",
            "direction": direction,
            "entry_price": state["close"],
            "stop_price": plan["stop"],
            "target_price": plan["target"],
            "expected_rr": plan["rr"],
            "suggested_leverage": state["sizing"]["leverage"],
            "suggested_size_pct": state["sizing"]["actual_risk_pct"],
            "mtf_confluence": ["Asian-session RSI reclaim", f"4H {state['trend']}-trend"],
            "confluence_count": 2,
        }
        try:
            row = insert_signal(payload)
            title, body, tag = _prop_alert_message(row)
            _notify(title, body, signal_id=sig_id, tags=tag)
            emitted = f"{sig_id}:pushed"
        except ValueError:
            emitted = f"{sig_id}:already-emitted"

    print(f"[{stamp}] bar={bar_ts} close={state.get('close')} "
          f"asian={state.get('is_asian')} verdict={verdict} dir={direction} "
          f"signal={emitted}")
    return state


if __name__ == "__main__":
    run_prop_scan_cli()
