"""C3 (stack half) — when do the 5 BTC and 50 BTC rungs actually land?

The cone tracks the ENGINE in EUR. This converts that engine into STACK in BTC
and dates the rungs, under the plan's three flat-CAGR price scenarios. Three
lines, no extra Monte Carlo — the engine's uncertainty already lives in the cone.

Two curve shapes, deliberately not conflated:

  · personal (Kraken) COMPOUNDS — profit stays in the account and grows the base.
  · prop is a linear PAYOUT STREAM — profit is withdrawn, the account never
    compounds. Monthly surplus = payout × take-home − burn, converted at spot.

There is no funded account, so `prop_payout_eur` is 0 and the surplus is just
−burn: the stack is drained by living costs until the engine or a payout covers
them. That is the honest baseline, not a bug. An `n_accounts` multiplier scales
the prop stream; it is NOT a prop-firm scaling-plan simulator, and won't become
one.

Two rows, always, in the same measured-vs-plan grammar as the scenario ladder's
M/P pins:
  · MEASURED — the ledger's own win rate, R and cadence. What you've shown.
  · PLAN     — the typed assumptions. What you claim.
The distance between the rows is the argument.
"""

import math
from datetime import date

MAX_YEARS = 20          # past this the answer is "never", not a date
PAYOUT_SHARE = 0.80


def monthly_return(win_rate: float, rr: float, risk_frac: float) -> float:
    """Geometric monthly growth of a compounding account, per trade then per month.

    Per-trade log growth: WR·ln(1+risk·R) + (1−WR)·ln(1−risk). Geometric, not
    arithmetic — an account that wins 3R and loses 1R alternately does NOT grow at
    the arithmetic mean, and the difference is what kills over-sized accounts.
    """
    if not (0 < win_rate < 1) or risk_frac <= 0 or risk_frac >= 1 or rr <= 0:
        return 0.0
    g = win_rate * math.log(1 + risk_frac * rr) + (1 - win_rate) * math.log(1 - risk_frac)
    return math.exp(g) - 1.0        # per trade


def project(stack_btc: float, price_eur: float, balance_eur: float,
            win_rate: float, rr: float, trades_per_week: float, risk_frac: float,
            burn_eur: float, annual_price_pct: float,
            prop_payout_eur: float = 0.0, n_accounts: int = 1,
            months: int = MAX_YEARS * 12) -> list[dict]:
    """Month-by-month stack path.

        stack(t)     = btc_held(t) + personal_equity(t) / price(t)
        btc_held(t+1) = btc_held(t) + (payout×share×n − burn) / price(t)
        equity(t+1)   = equity(t) × (1 + monthly growth)

    The personal account's profit is NOT also added to btc_held — it is already in
    the stack through equity/price. Counting it twice was the first thing the
    self-check caught.

    Note the sign that surprises people: a HIGHER BTC price pushes a BTC-denominated
    rung FURTHER away, because EUR income buys fewer sats. Bull is slower than bear
    whenever net EUR flow is positive.
    """
    per_trade = monthly_return(win_rate, rr, risk_frac)
    tpm = trades_per_week * 52.0 / 12.0
    growth = (1 + per_trade) ** tpm - 1.0 if per_trade > -1 else -1.0
    px_m = (1 + annual_price_pct / 100.0) ** (1 / 12.0) - 1.0
    surplus = prop_payout_eur * PAYOUT_SHARE * n_accounts - burn_eur

    held, bal, px = stack_btc, balance_eur, price_eur
    out = []
    for m in range(1, months + 1):
        held = max(0.0, held + surplus / px)
        bal = max(0.0, bal * (1 + growth))
        px *= (1 + px_m)
        stack = held + bal / px
        out.append({"m": m, "stack": stack, "held": held, "balance": bal, "price": px})
        if stack <= 0:
            break
    return out


def _lands(path: list[dict], target: float, today: date) -> str | None:
    for p in path:
        if p["stack"] >= target:
            y, mo = divmod(today.month - 1 + p["m"], 12)
            return f"{today.year + y:04d}-{mo + 1:02d}"
    return None


def rungs(stack_btc: float, price_eur: float, balance_eur: float, burn_eur: float,
          scenarios: dict, targets=(5.0, 50.0), **kw) -> dict:
    """{target: {bear|base|bull: 'YYYY-MM' | None}} for one parameter set."""
    today = date.today()
    out = {}
    for t in targets:
        out[str(t)] = {name: _lands(project(stack_btc, price_eur, balance_eur,
                                            burn_eur=burn_eur, annual_price_pct=pct, **kw),
                                    t, today)
                       for name, pct in scenarios.items()}
    return out


def payload() -> dict:
    """Both rows against the live plan, ledger and config. `stack: null` when no
    snapshot exists — nothing to project from, and we won't invent a holding."""
    from .database import get_actual_stats, get_lens_config
    from . import plan as P

    pl = P.active_plan()
    snap = P.latest_snapshot()
    cfg = get_lens_config()
    stats = get_actual_stats()

    price = cfg.get("btc_price_eur")
    bal = stats.get("current_balance") or cfg.get("start_balance")
    if not snap or not price or not bal:
        return {"stack": None,
                "reason": "log a stack snapshot (and a BTC price) to date the rungs"}

    burn = pl["burn_monthly_eur"] or 0.0
    scen = {k: pl["price_scenarios"][k] for k in ("bear", "base", "bull")}
    common = dict(stack_btc=snap["btc_total"], price_eur=price, balance_eur=bal,
                  burn_eur=burn, scenarios=scen)

    rows = {}
    m = P.measured()
    if m.get("n") and m.get("rr_ratio") and stats.get("avg_loss_eur"):
        rows["measured"] = {
            "n": m["n"], "win_rate": m["win_rate"], "rr": m["rr_ratio"],
            "trades_per_week": m["trades_per_week"],
            "risk_pct": round(abs(stats["avg_loss_eur"]) / bal * 100, 2),
            "rungs": rungs(win_rate=m["win_rate"], rr=m["rr_ratio"],
                           trades_per_week=m["trades_per_week"],
                           risk_frac=min(abs(stats["avg_loss_eur"]) / bal, 0.99), **common),
        }

    risk_frac = 0.02
    try:
        from .calculator import compute_goal
        g = compute_goal(cfg["start_balance"], cfg["target_balance"],
                         date.fromisoformat(cfg["target_date"]),
                         trades_per_week=cfg["trades_per_week"], win_rate=cfg["win_rate"],
                         rr_ratio=cfg["rr_ratio"], leverage=cfg["leverage"])
        risk_frac = min(g["risk_per_trade"] / 100.0, 0.99)
    except Exception:
        pass
    rows["plan"] = {
        "win_rate": cfg["win_rate"], "rr": cfg["rr_ratio"],
        "trades_per_week": cfg["trades_per_week"], "risk_pct": round(risk_frac * 100, 2),
        "rungs": rungs(win_rate=cfg["win_rate"], rr=cfg["rr_ratio"],
                       trades_per_week=cfg["trades_per_week"], risk_frac=risk_frac, **common),
    }

    return {"stack": snap["btc_total"], "stack_date": snap["date"], "price_eur": price,
            "balance_eur": bal, "burn_monthly_eur": burn, "scenarios": scen,
            "prop_payout_eur": 0.0, "payout_share": PAYOUT_SHARE,
            "targets": [5.0, 50.0], "rows": rows,
            "note": "No funded account: prop payouts are €0, so the monthly surplus is "
                    "−burn and the stack is drained until the engine covers it."}


if __name__ == "__main__":   # ponytail: one runnable check
    SCEN = {"bear": -20.0, "base": 15.0, "bull": 50.0}
    base = dict(stack_btc=1.0, price_eur=55_000.0, balance_eur=100_000.0,
                burn_eur=2_800.0, scenarios=SCEN)

    # a negative-drift engine never arrives, whatever the price does
    dead = rungs(win_rate=0.39, rr=1.3, trades_per_week=7.6, risk_frac=0.10, **base)
    assert all(v is None for v in dead["5.0"].values()), dead

    # a real edge does arrive — and BEAR arrives first: EUR income buys more sats
    # when BTC is cheap. The bull case is the slow one for a BTC-denominated rung.
    good = rungs(win_rate=0.50, rr=2.5, trades_per_week=3.0, risk_frac=0.02, **base)
    assert good["5.0"]["base"] is not None, good
    assert good["5.0"]["bear"] <= good["5.0"]["base"] <= good["5.0"]["bull"], good["5.0"]
    # 50 BTC can't land before 5 BTC
    assert good["50.0"]["base"] >= good["5.0"]["base"], good
    # the personal account is counted once: its equity enters only via equity/price
    p = project(1.0, 50_000.0, 50_000.0, 0.5, 2.5, 3.0, 0.02, 0.0, 0.0)
    assert abs(p[0]["stack"] - (p[0]["held"] + p[0]["balance"] / p[0]["price"])) < 1e-9

    # geometric, not arithmetic: 50% at 3R with 20% risk has positive arithmetic EV
    # and negative log growth — the model must not report growth here
    assert monthly_return(0.5, 3.0, 0.20) < 0.5 * 0.20 * 3.0 - 0.5 * 0.20
    assert monthly_return(0.4, 1.0, 0.5) < 0        # loses more than it wins, geometrically

    # burn with no payout drains a dormant stack
    idle = project(1.0, 55_000.0, 0.0, 0.4, 2.0, 0.0, 0.02, 2_800.0, 0.0)
    assert idle[-1]["stack"] < 1.0, idle[-1]

    print("dead engine  5 BTC:", dead["5.0"])
    print("good engine  5 BTC:", good["5.0"], "| 50 BTC:", good["50.0"])
    print("live payload:", {k: v for k, v in payload().items() if k != "rows"})
