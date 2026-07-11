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
from .prop_views import HERO, prop_config
from .setups import _notify

PROP_STRATEGY = HERO            # default hero / fallback signal discriminator
MM_RATE = 0.005                 # maintenance margin assumption (Kraken BTC perp ~0.5%)

# Fallback tradeable set if the Strategy Board cache is missing — the top-3 prop
# strategies and the R each one is traded at (its board-optimal "best R").
PROP_FALLBACK = [("ASIAN_RSI_DIP_v1", 2.0), ("ASIAN_PULLBACK_v2", 3.0), ("ASIAN_PULLBACK_v1", 3.0)]


def prop_tradeable() -> list[tuple[str, float]]:
    """The live prop tradeable set, each strategy paired with its board-optimal
    target R. Precedence:
      1. the basket saved on the eval config (explicit user choice), else
      2. the Strategy Board's top-3 prop strategies (auto-syncs weekly), else
      3. PROP_FALLBACK.
    Widening the basket raises trades/month and LOWERS the eval pass-rate — the
    two move against each other. /prop-goal prices that trade before you take it."""
    from .backtest_engine import STRATEGIES
    best_r = {}
    try:
        from .strategy_eval import load_cache
        d = load_cache() or {}
        for o in d.get("results", []):
            if o["mode"] == "prop" and o.get("best_r"):
                best_r[o["name"]] = float(o["best_r"])
    except Exception:
        pass

    chosen = prop_config().get("basket")
    if chosen:
        # ignore anything that isn't a real backtest strategy — a basket entry with
        # no signal_fn would silently never fire.
        return [(n, best_r.get(n, 4.0)) for n in chosen if n in STRATEGIES]

    try:
        from .strategy_eval import load_cache
        d = load_cache()
        if d:
            # Default = every prop SURVIVOR, not just the board top-3: any strategy
            # that isn't `thin` (≥40 occurrences) and has a net-positive config
            # (score > 0, i.e. at least one R level pays after fees). Ordered best
            # score first, hero pinned rank-1 so it still wins ties on the bar.
            # ⚠️ Wider basket = more signals but a LOWER eval pass-rate (speed↔
            # survival). This is his explicit call — /prop-goal prices it.
            surv = sorted([o for o in d["results"]
                           if o["mode"] == "prop" and not o.get("thin")
                           and o.get("best_r") and o.get("score", 0) > 0],
                          key=lambda x: (x["name"] != HERO, -x.get("score", 0)))
            if surv:
                return [(o["name"], float(o["best_r"])) for o in surv]
    except Exception:
        pass
    return list(PROP_FALLBACK)


def prop_ticket(entry: float, stop: float, target: float, long_: bool,
                strategy: str = PROP_STRATEGY, account: float = None,
                risk: float = None, max_lev: float = None) -> dict:
    """Prop-legal order ticket from a signal's levels — same sizing math as
    prop_desk_state (risk% of the eval account, leverage capped at the firm's
    5x). Deterministic from entry/stop/target, so it recomputes identically for a
    live pending signal or a historical one on the review page. `account`/risk/plan
    default to the active eval config; pass the live eval equity to size off it.
    `risk` (%) / `max_lev` override the plan for what-if sizing on /prop-position."""
    cfg = prop_config()
    EVAL = cfg["eval_name"]
    RISK = risk if risk is not None else cfg["risk"]
    if account is None:
        account = cfg["account"]
    rule = EVALS[EVAL]
    cap = max_lev if max_lev is not None else rule["max_leverage"]
    fee_rt = rule.get("commission_per_side", 0.0004) * 2
    stop_pct = abs(entry - stop) / entry * 100 if entry else 0.0
    tp_pct = abs(target - entry) / entry * 100 if entry else 0.0
    lev, actual_risk = _legal_leverage(stop_pct, RISK, cap)
    risk_usd = account * RISK / 100.0
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
        "account": account, "risk_pct": RISK, "leverage": round(lev, 2),
        "actual_risk_pct": round(actual_risk, 2), "notional": round(notional, 2),
        "size_btc": size_btc, "margin_usd": round(margin, 2),
        "win_usd": round(win_usd, 2), "loss_usd": round(loss_usd, 2),
        "risk_usd": round(risk_usd, 2), "fee_rt_pct": fee_rt * 100,
        "breakeven": round(breakeven, 1), "liq": round(liq, 1) if liq else None,
        "stop_pct": round(stop_pct, 2), "tp_pct": round(tp_pct, 2),
        "rr": round(tp_pct / stop_pct, 2) if stop_pct else 0.0,
        "max_leverage": cap,
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
    from .backtest_engine import STRATEGIES
    tf = (STRATEGIES.get(strat_name, {}).get("timeframe") or "4h").upper()
    body = (
        f"{head} PROP · {side} · BTC/USD {arrow}\n"
        f"\U0001F9E0 {strat_name} ({tf} eval · {t['rr']:g}R)\n"           # 🧠
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


DIGEST_HOUR_UTC = 8     # just after the 04:00 UTC Asian bar closes


def _push_stand_down(states: list) -> bool:
    """One low-priority push naming the first unmet gate per strategy. Answers
    'why did nothing fire today?' without you opening the desk."""
    if not states:
        return False
    lines = []
    for name, st in states:
        why = st.get("stand_down_reason") or "conditions not met"
        lines.append(f"• {name}\n   {why}")
    close = states[0][1].get("close")
    body = (f"\U0001F634 No prop entry today\n"           # 😴
            f"BTC ${close:,.0f}\n\n" + "\n".join(lines) +
            "\n\n\U0001F4CA /prop-desk for the full read")
    return _notify("PROP · stand down", body, tags="sleeping")


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
    states = []
    for rank, (name, target_r) in enumerate(tradeable, 1):
        state = prop_desk_state(refresh=(rank == 1), strategy=name)
        last_state = state
        if state.get("error"):
            continue
        states.append((name, state))
        verdict, direction = state.get("verdict"), state.get("direction")
        # NO session gate here. Every signal_fn enforces its own session/hour rule
        # (ASIAN_* check `df.index[i].hour in (0, 4)` internally, backtest_engine.py).
        # The old `state["is_asian"]` gate was redundant for those and silently made
        # it impossible for any non-Asian strategy in the basket to ever emit.
        if not (emit and verdict == "enter" and direction):
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

    # Nothing fired → once a day, say WHY, so silence is legible instead of
    # ambiguous. Gated to a single UTC hour: the scanner runs every hour, and a
    # "nothing happened" push on each of those would train you to ignore it.
    if emit and fired is None and datetime.datetime.now(datetime.timezone.utc).hour == DIGEST_HOUR_UTC:
        _push_stand_down(states)

    s = last_state or {}
    print(f"[{stamp}] bar={s.get('bar_ts')} close={s.get('close')} "
          f"asian={s.get('is_asian')} set={[n for n, _ in tradeable]} "
          f"fired={fired} signal={emitted}")
    return last_state or {"error": "no strategies evaluated"}


if __name__ == "__main__":
    run_prop_scan_cli()
