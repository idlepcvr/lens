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

PROP_STRATEGY = HERO            # default hero / fallback signal discriminator
MM_RATE = 0.005                 # maintenance margin assumption (Kraken BTC perp ~0.5%)

# Fallback tradeable set if the Strategy Board cache is missing — the top-3 prop
# strategies and the R each one is traded at (its board-optimal "best R").
PROP_FALLBACK = [("ASIAN_RSI_DIP_v1", 2.0), ("ASIAN_PULLBACK_v2", 3.0), ("ASIAN_PULLBACK_v1", 3.0)]


def prop_tradeable() -> list[tuple[str, float]]:
    """The live prop tradeable set: the Strategy Board's top-3 prop strategies,
    each paired with its board-optimal target R. Auto-syncs with the weekly board
    refresh; falls back to PROP_FALLBACK if the cache isn't there yet."""
    try:
        from .strategy_eval import load_cache
        d = load_cache()
        if d:
            top = sorted([o for o in d["results"]
                          if o["mode"] == "prop" and o.get("top3") and o.get("best_r")],
                         key=lambda x: x["rank"])
            if top:
                return [(o["name"], float(o["best_r"])) for o in top]
    except Exception:
        pass
    return list(PROP_FALLBACK)


def prop_ticket(entry: float, stop: float, target: float, long_: bool,
                strategy: str = PROP_STRATEGY) -> dict:
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
        "eval": EVAL, "strategy": strategy,
    }


def _prop_alert_message(sig: dict) -> tuple[str, str, str]:
    """Slim prop ticket for the lock screen — full detail lives on /prop-signals."""
    entry, stop, target = sig["entry_price"], sig["stop_price"], sig["target_price"]
    long_ = sig["direction"] == "long"
    t = prop_ticket(entry, stop, target, long_, strategy=sig.get("strategy_name", PROP_STRATEGY))
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
    strat_name = sig.get("strategy_name", PROP_STRATEGY)
    body = (
        f"{head} PROP · {side} · BTC/USD {arrow}\n"
        f"\U0001F9E0 {strat_name} (4H eval · {t['rr']:g}R)\n"             # 🧠
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
    """Cron entry point: evaluate the Strategy Board's top-3 prop strategies on the
    freshest closed 4H Asian bar. The highest-ranked one saying ENTER wins the bar
    (one alert max); it's traded at that strategy's board-optimal target R. Signal
    is deduped per bar+strategy so re-scanning the same bar is a no-op."""
    from .database import init_db, insert_signal
    from .prop_desk import prop_desk_state

    init_db()
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    tradeable = prop_tradeable()

    last_state = None
    emitted = "none"
    fired = None
    for rank, (name, target_r) in enumerate(tradeable, 1):
        state = prop_desk_state(refresh=(rank == 1), strategy=name)
        last_state = state
        if state.get("error"):
            continue
        verdict, direction = state.get("verdict"), state.get("direction")
        if not (emit and verdict == "enter" and direction and state.get("is_asian")):
            continue

        # trade at the strategy's board-optimal R: target = entry ± stop_dist × R
        entry = state["close"]
        stop = state["plan"][direction]["stop"]
        stop_dist = abs(entry - stop)
        target = round(entry + stop_dist * target_r if direction == "long"
                       else entry - stop_dist * target_r, 1)
        bar_ts = state.get("bar_ts")
        sig_id = f"prop-{name}-{bar_ts.replace(':', '').replace('-', '')}"
        payload = {
            "signal_id": sig_id,
            "strategy_name": name,
            "strategy_version": "1.0",
            "symbol": "BTC/USD",
            "venue": "kraken_futures",
            "trigger_type": name,
            "direction": direction,
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "expected_rr": round(target_r, 2),
            "suggested_leverage": state["sizing"]["leverage"],
            "suggested_size_pct": state["sizing"]["actual_risk_pct"],
            "mtf_confluence": [f"board top-{rank} prop", f"4H {state['trend']}-trend", f"{target_r:g}R target"],
            "confluence_count": 2,
        }
        try:
            row = insert_signal(payload)
            row["strategy_name"] = name
            title, body, tag = _prop_alert_message(row)
            _notify(title, body, signal_id=sig_id, tags=tag)
            emitted = f"{sig_id}:pushed"
        except ValueError:
            emitted = f"{sig_id}:already-emitted"
        fired = name
        break   # highest-ranked ENTER wins the bar

    s = last_state or {}
    print(f"[{stamp}] bar={s.get('bar_ts')} close={s.get('close')} "
          f"asian={s.get('is_asian')} set={[n for n, _ in tradeable]} "
          f"fired={fired} signal={emitted}")
    return last_state or {"error": "no strategies evaluated"}


if __name__ == "__main__":
    run_prop_scan_cli()
