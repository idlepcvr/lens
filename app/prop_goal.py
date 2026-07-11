"""LENS /prop-goal — time-to-target cone for the live prop eval.

The hedge /goal page is a BTC-stack milestone ladder measured in years. A prop
eval is a different animal: one bounded run from `account` to `account × (1+target)`
with a hard floor underneath, expected to resolve in weeks. So the prop goal page
answers the only question that matters here:

    given the basket I actually trade, when do I hit the target — and how often
    do I hit the floor first?

Everything is resampled from the basket's REAL backtested trades (same engine and
the same eval walls as /prop and /survival), so this page can never disagree with
them. Two honest caveats are rendered on the page itself:

  1. The cone is drawn on BACKTEST geometry. The measured edge from the live
     ledger is worse (see eval_mc.py, 2026-07-09). Both numbers are shown.
  2. Widening the basket buys trades/month, not edge. It shortens the median time
     to target AND lowers the pass-rate. The page prices both sides.
"""

import datetime

import numpy as np

from .prop_eval import EVALS, _portfolio_daily_trades, _walk_eval
from .prop_scan import prop_tradeable
from .prop_views import prop_config
from .theme import shell

MONTHS = 30          # backtest window the trades are resampled from
PATHS = 2000
MAX_DAYS = 252
DAYS_PER_MONTH = 30.44


def _basket() -> list:
    return [n for n, _ in prop_tradeable()]


def cone(basket: list = None, paths: int = PATHS, seed: int = 42) -> dict:
    """Monte-Carlo the active basket under the live eval walls and return an
    equity cone indexed by trade number, plus the calendar mapping.

    The cone is over SURVIVING paths at each trade index. A path that busts stops
    contributing — so the p10 band is the 10th percentile of accounts still alive,
    not of all accounts. Failures are reported separately as fail_pct rather than
    smeared into the band, because a busted eval isn't a low equity, it's over.
    """
    cfg = prop_config()
    account, risk, eval_name = cfg["account"], cfg["risk"], cfg["eval_name"]
    rule = EVALS[eval_name]
    basket = basket or _basket()
    if not basket:
        return {"error": "empty basket"}

    daily_trades, n_trades = _portfolio_daily_trades(basket, rule, risk, MONTHS)
    if not daily_trades:
        return {"error": "no trades for basket"}

    tpm = n_trades / MONTHS                       # trades per month, whole basket
    rng = np.random.default_rng(seed)
    n_days = len(daily_trades)

    curves, results, trades_to_pass = [], [], []
    for _ in range(paths):
        idx = rng.integers(0, n_days, size=MAX_DAYS)
        p = []
        res, _final, n, _why = _walk_eval([daily_trades[k] for k in idx],
                                          account, rule, True, path=p)
        curves.append(p)
        results.append(res)
        if res == "PASS":
            trades_to_pass.append(n)

    passes = sum(r == "PASS" for r in results)
    fails = sum(r == "FAIL" for r in results)

    # cone over survivors at each trade index (cap at the median passer's horizon
    # so the tail isn't drawn from the handful of paths that grind for 200 trades)
    horizon = int(np.median(trades_to_pass)) * 2 if trades_to_pass else 40
    horizon = max(10, min(horizon, 120))
    band = []
    for k in range(horizon):
        alive = [c[k] for c in curves if len(c) > k]
        if len(alive) < max(20, paths * 0.02):    # too few survivors to be meaningful
            break
        a = np.array(alive)
        band.append({
            "trade": k + 1,
            "days": round((k + 1) / tpm * DAYS_PER_MONTH, 1) if tpm else None,
            "p10": round(float(np.percentile(a, 10)), 2),
            "p50": round(float(np.percentile(a, 50)), 2),
            "p90": round(float(np.percentile(a, 90)), 2),
            "alive_pct": round(len(alive) / paths * 100, 1),
        })

    med_trades = int(np.median(trades_to_pass)) if trades_to_pass else None
    med_days = round(med_trades / tpm * DAYS_PER_MONTH) if (med_trades and tpm) else None
    fee = cfg.get("fee") or 0.0
    pass_pct = passes / paths * 100

    return {
        "basket": basket, "eval": eval_name,
        "account": account, "risk_pct": risk,
        "target": round(account * (1 + rule["profit_target_pct"] / 100), 2),
        "floor": round(account * (1 - rule["max_dd_pct"] / 100), 2),
        "target_pct": rule["profit_target_pct"], "dd_pct": rule["max_dd_pct"],
        "trades_per_month": round(tpm, 2),
        "signals_per_week": round(tpm / 4.345, 1),
        "pass_pct": round(pass_pct, 1),
        "fail_pct": round(fails / paths * 100, 1),
        "median_trades_to_target": med_trades,
        "median_days_to_target": med_days,
        "eta_date": (datetime.date.today() + datetime.timedelta(days=med_days)).isoformat()
                    if med_days else None,
        # what the attempt is expected to cost you, given the fee actually paid and
        # how often this basket survives. The number the fee ledger was built for.
        "fee": round(fee, 2),
        "expected_cost_per_pass": round(fee / (pass_pct / 100), 2) if pass_pct > 0 and fee else None,
        "band": band,
        "paths": paths,
    }


def _losses_to_floor(dd_frac: float, risk_frac: float) -> int:
    """Consecutive full stops from the start balance to the eval floor.
    log(1-dd) / log(1-risk): at 3% floor and 0.5% risk that's 6, not 700."""
    import math
    if not (0 < risk_frac < 1) or not (0 < dd_frac < 1):
        return 0
    return math.ceil(math.log(1 - dd_frac) / math.log(1 - risk_frac))


def _basket_geometry(basket: list = None) -> dict:
    """Measured win-rate and R for the active basket, from its real backtested
    trades under the eval's fee model. This is the 'plan' pin."""
    cfg = prop_config()
    rule = EVALS[cfg["eval_name"]]
    basket = basket or _basket()
    daily, n = _portfolio_daily_trades(basket, rule, cfg["risk"], MONTHS)
    pnls = [p for day in daily for p, _dip in day]
    if not pnls:
        return {}
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p <= 0]
    wr = len(wins) / len(pnls)
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    return {"win_rate": wr, "rr": (aw / al) if al else 0.0,
            "n": len(pnls), "trades_per_month": n / MONTHS,
            "avg_win_pct": aw, "avg_loss_pct": al}


def _measured_geometry() -> dict:
    """Win-rate and R actually REALISED on prop trades (all attempts). The pin
    that matters — a backtest is a claim, this is the evidence."""
    from .review import review_analytics
    a = review_analytics(book="prop")
    if not a.get("n"):
        return {}
    return {"win_rate": a["wr"] / 100.0, "rr": a.get("rr") or 0.0, "n": a["n"]}


def _goal(account, target, days, tpw, wr, rr, risk_frac, dd_frac, stop_pct, leverage):
    """compute_goal, fed prop's constraints. Two inversions vs the hedge goal:

      risk_per_trade is FIXED (the firm sets it via your plan), not derived from
      the target — so `optimal_risk_pct` becomes a CHECK on the risk you're
      already taking rather than a number to adopt.

      max_drawdown_allowed is the eval FLOOR (3%), not a 50% wipeout. Since
      risk_of_ruin integrates against `B = -log(1 - max_drawdown_allowed)`, this
      makes it the probability of touching the floor — which is the number that
      actually ends the eval. (The 2026-06-17 dashboard spec asked for exactly
      this and the June note flagged that 50%-DD 'risk of ruin' was the wrong bar.)
    """
    import datetime as _dt
    from .calculator import CalcError, compute_goal
    losses_allowed = max(1, int(dd_frac / risk_frac))   # consecutive stops to the floor
    try:
        return compute_goal(
            account, target, _dt.date.today() + _dt.timedelta(days=max(1, int(days))),
            # LEGAL leverage, not the firm's 5x cap: compute_goal derives the
            # underlying stop as risk/fill/leverage - friction, so passing the cap
            # implies a 0.1% price stop that fees swallow whole.
            max(0.1, tpw), wr, rr, leverage,
            max_drawdown_allowed=dd_frac,
            losses_allowed=losses_allowed,
            fractional_kelly=0.25,
            execution_fill_factor=1.0,      # limit fills on the eval, no market slip
            slippage_pct=0.0,
            risk_per_trade=risk_frac,       # FIXED by the plan
            min_underlying_stop_pct=stop_pct,
        )
    except CalcError as e:
        # surfaced, not swallowed — a silent {} here reads as "model didn't
        # converge" when the real cause is a bad input (e.g. passing the 5x cap
        # as leverage, which implies a 0.1% stop that fees eat whole).
        return {"_error": str(e)}


def model(basket: list = None) -> dict:
    """The /prop-goal metrics panel: the same engine as the hedge /goal, fed the
    eval's fixed risk and 3% floor. Includes the WR-sensitivity table, R-target
    scenarios and the WR×R scenario ladder, plus both pins (backtest vs realised)."""
    cfg = prop_config()
    rule = EVALS[cfg["eval_name"]]
    account = cfg["account"]
    target = account * (1 + rule["profit_target_pct"] / 100)
    dd_frac = rule["max_dd_pct"] / 100
    risk_frac = cfg["risk"] / 100
    geo = _basket_geometry(basket)
    if not geo:
        return {"error": "no trades for basket"}

    c = cone(basket) if basket else cone()
    days = c.get("median_days_to_target") or 90
    tpw = geo["trades_per_month"] / 4.345

    # The basket's underlying price stop, and the leverage that turns it into a
    # risk_pct loss. Legal leverage is risk/stop capped at the firm's max — at
    # 0.5% risk on a 1% stop that is 0.5x, nowhere near the 5x cap.
    from .backtest_engine import STRATEGIES
    from .prop_eval import _legal_leverage
    names = basket or _basket()
    stops = [STRATEGIES[n]["params"].get("stop_pct", 1.0) for n in names if n in STRATEGIES]
    stop_price_pct = sum(stops) / len(stops) if stops else 1.0     # % price move
    leverage, _ = _legal_leverage(stop_price_pct, cfg["risk"], rule["max_leverage"])
    stop_pct = stop_price_pct / 100.0                              # as a fraction

    g = _goal(account, target, days, tpw, geo["win_rate"], geo["rr"],
              risk_frac, dd_frac, stop_pct, leverage)
    if not g or "_error" in g:
        return {"error": g.get("_error", "goal model did not converge") if g else "no model"}

    # compute_goal returns PERCENTAGES already (verified against /goal: per_trade_ev
    # 7.542 is the page's "7.542%"). Multiplying by 100 here produced a 3717% ruin.
    def _row(wr, rr):
        r = _goal(account, target, days, tpw, wr, rr, risk_frac, dd_frac, stop_pct, leverage)
        if not r or "_error" in r:
            return None
        return {"wr": round(wr * 100, 1), "rr": round(rr, 2),
                "ev": round(float(r["per_trade_ev"]), 3),
                "drift": round(float(r["geometric_drift"]), 3),
                "ruin": round(float(r["risk_of_ruin"]), 1)}

    base_wr, base_rr = geo["win_rate"], geo["rr"]
    wr_sens = [x for x in (_row(w, base_rr)
               for w in (base_wr - .10, base_wr - .05, base_wr, base_wr + .05, base_wr + .10))
               if x and 0 < x["wr"] < 100]
    r_scen = [x for x in (_row(base_wr, r) for r in (2.0, 3.0, 4.0, base_rr, 5.0, 6.0)) if x]
    r_scen.sort(key=lambda x: x["rr"])

    # WR × R ladder — the same shape as the hedge page's, in prop terms
    wr_axis = [.20, .25, .30, .35, .40, .45, .50]
    r_axis = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
    ladder = []
    for w in wr_axis:
        cells = []
        for r in r_axis:
            row = _row(w, r)
            cells.append({"ev": row["ev"], "ruin": row["ruin"]} if row else None)
        ladder.append({"wr": round(w * 100), "cells": cells})

    meas = _measured_geometry()
    return {
        "eval": cfg["eval_name"],
        "account": account, "target": round(target, 2),
        "floor": round(account * (1 - dd_frac), 2),
        "risk_pct": cfg["risk"], "risk_usd": round(account * risk_frac, 2),
        "target_pct": rule["profit_target_pct"], "dd_pct": rule["max_dd_pct"],
        "daily_pct": rule["daily_loss_pct"], "max_leverage": rule["max_leverage"],
        "leverage": round(leverage, 2), "stop_price_pct": round(stop_price_pct, 2),
        "basket": basket or _basket(),
        "trades_per_month": round(geo["trades_per_month"], 2),
        "trades_per_week": round(tpw, 2),
        "days_to_target": days,
        # ── fixed-risk framing. compute_goal already returns percentages. ──
        "used_risk_pct": round(risk_frac * 100, 3),
        "optimal_risk_pct": round(float(g["optimal_risk_pct"]), 3),
        "kelly_pct": round(float(g["kelly_risk"]), 2) if g.get("kelly_risk") else None,
        "full_kelly_pct": round(float(g["full_kelly"]), 2) if g.get("full_kelly") else None,
        "dd_constraint_pct": round(float(g["dd_risk_constraint"]), 3) if g.get("dd_risk_constraint") else None,
        # calculator's losses_to_ruin means "equity falls TO max_drawdown_allowed"
        # (a 97% loss at dd=0.03), not "hits the 3% floor". Derived here instead.
        "losses_to_floor": _losses_to_floor(dd_frac, risk_frac),
        "wins_to_breakeven": g.get("wins_to_breakeven"),
        # edge
        "ev_per_trade_pct": round(float(g["per_trade_ev"]), 3),
        "ev_required_pct": round(float(g["per_trade_ev_required"]), 3),
        "geom_drift_pct": round(float(g["geometric_drift"]), 3),
        "expectancy_r": round(float(g["expectancy_pct_of_risk"]) / 100, 3),
        "profit_factor": round(float(g["profit_factor"]), 2),
        "sharpe_per_trade": round(float(g["sharpe_ratio"]), 3),
        "trade_volatility_pct": round(float(g["trade_volatility"]), 2),
        # Two arrival dates that mean different things:
        #   days_to_target  — the MEDIAN PASSER's, from the cone. Conditional on
        #                     surviving, so it is survivorship-biased and fast.
        #   days_needed_ev  — the AVERAGE path's, from expectancy. Slower, and the
        #                     honest answer to "when will I get there".
        "trades_needed": g.get("trades_needed"),
        "days_needed_ev": round(g["trades_needed"] / tpw * 7) if (g.get("trades_needed") and tpw) else None,
        "edge_sufficient": float(g["per_trade_ev"]) >= float(g["per_trade_ev_required"]),
        # the number that actually ends the eval: P(touching the 3% floor).
        # Closed-form (calculator) — the cone's fail_pct is the MC estimate of the
        # same event. Both are shown; when they disagree, trust neither blindly.
        "floor_touch_pct": round(float(g["risk_of_ruin"]), 1),
        "floor_touch_mc_pct": c.get("fail_pct"),
        "ruin_label": g.get("ror_label"),
        "typical_win_pct": round(float(g["typical_win"]), 2),
        "typical_loss_pct": round(float(g["typical_loss"]), 2),
        "friction_pct": round(float(g["friction_pct"]), 3),
        # pins
        "plan": {"wr": round(base_wr * 100, 1), "rr": round(base_rr, 2), "n": geo["n"]},
        "measured": ({"wr": round(meas["win_rate"] * 100, 1), "rr": round(meas["rr"], 2),
                      "n": meas["n"]} if meas else None),
        "wr_sensitivity": wr_sens,
        "r_scenarios": r_scen,
        "ladder": {"wr_axis": [round(w * 100) for w in wr_axis], "r_axis": r_axis, "rows": ladder},
    }


def basket_options() -> list:
    """Score a handful of candidate baskets so the speed/survival trade is visible
    BEFORE you commit to one. Ordered widest-first is deliberate: the fastest
    basket is also the one most likely to lose the fee."""
    from .prop_eval import monte_carlo_portfolio
    cfg = prop_config()
    account, risk, eval_name = cfg["account"], cfg["risk"], cfg["eval_name"]
    CANDIDATES = {
        "Hero only": ["ASIAN_RSI_DIP_v1"],
        "Asian ×3 (board top-3)": ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v2", "ASIAN_PULLBACK_v1"],
        "Asian ×3 + PULLBACK_4R": ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v2", "ASIAN_PULLBACK_v1",
                                   "PULLBACK_4R_v1"],
        "Asian ×3 + RSI_DIP + P4R": ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v2", "ASIAN_PULLBACK_v1",
                                     "RSI_DIP_v1", "PULLBACK_4R_v1"],
        "Wide (7 strategies)": ["ASIAN_RSI_DIP_v1", "ASIAN_PULLBACK_v2", "ASIAN_PULLBACK_v1",
                                "PULLBACK_4R_v1", "TREND_4R_v1", "ENGULF_v1", "RSI_DIP_v1"],
    }
    fee = cfg.get("fee") or 0.0
    active = _basket()
    out = []
    for label, b in CANDIDATES.items():
        m = monte_carlo_portfolio(b, eval_name, account, risk, MONTHS, paths=1200)
        if "error" in m:
            continue
        tpm = m["trades_per_month"]
        mo = m.get("est_months_to_pass")
        pp = m["pass_rate_pct"]
        out.append({
            "label": label, "basket": b, "n": len(b),
            "trades_per_month": tpm,
            "signals_per_week": round(tpm / 4.345, 1),
            "pass_pct": pp,
            "fail_dd_pct": m["fail_max_dd_pct"],
            "days_to_target": round(mo * DAYS_PER_MONTH) if mo else None,
            "expected_cost_per_pass": round(fee / (pp / 100), 2) if pp > 0 and fee else None,
            "active": sorted(b) == sorted(active),
        })
    return out


# ── page ──────────────────────────────────────────────────────────────────────
_CSS = r"""<style>
.pg h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pg .sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.pg .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin-bottom:16px}
.pg .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;position:relative;overflow:hidden}
.pg .card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--line2)}
.pg .card.g::after{background:var(--long)}.pg .card.r::after{background:var(--short)}
.pg .card.a::after{background:var(--amber)}.pg .card.b::after{background:var(--accent)}
.pg .card .lbl{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:6px}
.pg .card .val{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1.05;color:var(--ink)}
.pg .card .note{font-size:10.5px;color:var(--dim);margin-top:4px}
.pg canvas{width:100%;height:300px;background:var(--panel);border:1px solid var(--line);border-radius:11px}
.pg table{width:100%;border-collapse:collapse;font-size:12px}
.pg th,.pg td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--line);font-family:var(--mono)}
.pg th{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:500}
.pg th:first-child,.pg td:first-child{text-align:left}
.pg td.g{color:var(--long)}.pg td.r{color:var(--short)}.pg td.dim{color:var(--dim)}
.pg tbody tr.on td{background:var(--accent-d)}
.pg .sb-wrap{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:4px 10px;overflow-x:auto}
.pg .pick{background:var(--accent-d);color:var(--accent);border:1px solid var(--line2);border-radius:5px;padding:4px 10px;font-family:var(--mono);font-size:10px;cursor:pointer}
.pg .pick:hover{filter:brightness(1.3)}
.pg .warn{background:rgba(255,176,32,.09);border:1px solid var(--amber);border-radius:10px;padding:11px 14px;margin:14px 0;font-size:11.5px;color:var(--ink);line-height:1.55}
.pg .warn b{color:var(--amber)}
.pg .skeleton{padding:28px;text-align:center;color:var(--dim)}
/* two-column layout — mirrors hedge /goal: sticky param+plan sidebar, main column */
.pg .pg-main{display:grid;grid-template-columns:264px 1fr;gap:18px;align-items:start}
@media(max-width:900px){.pg .pg-main{grid-template-columns:1fr}}
.pg .pg-side{position:sticky;top:74px;display:flex;flex-direction:column;gap:12px}
@media(max-width:900px){.pg .pg-side{position:static}}
.pg .side-card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 14px}
.pg .side-h{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:10px}
.pg .side-card .kv{display:flex;justify-content:space-between;gap:8px;padding:4px 0;font-size:11.5px}
.pg .side-card .kv .k{color:var(--dim)}.pg .side-card .kv .v{font-family:var(--mono);color:var(--ink);text-align:right}
.pg .side-card .kv .v.g{color:var(--long)}.pg .side-card .kv .v.r{color:var(--short)}.pg .side-card .kv .v.a{color:var(--amber)}.pg .side-card .kv .v.dim{color:var(--dim)}
/* four-pillar hero */
.pg .pillars{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
@media(max-width:680px){.pg .pillars{grid-template-columns:repeat(2,1fr)}}
.pg .pil{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 16px;position:relative;overflow:hidden}
.pg .pil::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--line2)}
.pg .pil.g::after{background:var(--long)}.pg .pil.r::after{background:var(--short)}.pg .pil.a::after{background:var(--amber)}.pg .pil.b::after{background:var(--accent)}
.pg .pil-l{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:8px}
.pg .pil-v{font-family:var(--mono);font-size:25px;font-weight:800;line-height:1;color:var(--ink)}
.pg .pil-n{font-size:10.5px;color:var(--dim);margin-top:7px;line-height:1.35}
.pg .sect2-h{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin:22px 0 10px}
/* milestone ladder — floor → target rungs with the live equity marker */
.pg .mrung{display:grid;grid-template-columns:112px 1fr 78px;align-items:center;gap:11px;padding:8px 8px;border-radius:7px}
.pg .mrung+.mrung{margin-top:2px}
.pg .mrung .mlab{font-size:11px;color:var(--dim)}
.pg .mrung .mbar{height:8px;border-radius:4px;background:var(--line2);position:relative;overflow:hidden}
.pg .mrung .mbar>span{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.pg .mrung .mval{font-family:var(--mono);font-size:12px;color:var(--ink);text-align:right}
.pg .mrung.here{background:var(--accent-d);outline:1px solid var(--line2)}
.pg .mrung.here .mlab{color:var(--accent);font-weight:600}
</style>"""

BODY = r"""
<div class="pg">
  <h1>Prop Goal</h1>
  <div class="sub">Time-to-target for the live eval, resampled from the basket's real backtested trades against the same walls as <a href="/survival" class="ac">Survival</a>. <span class="dim">Hedge twin: <a href="/goal" class="ac">/goal</a>.</span></div>
  <div class="pg-main">
    <aside class="pg-side">
      <div class="side-card"><div class="side-h">The plan · locked eval rules</div><div id="plan"><div class="skeleton">…</div></div></div>
      <div class="side-card"><div class="side-h">Parameters · basket &amp; edge</div><div id="params"><div class="skeleton">…</div></div></div>
    </aside>
    <div class="pg-content">
      <div id="pillars" class="pillars"></div>
      <canvas id="cone" width="900" height="300"></canvas>
      <div id="caveat"></div>

      <div class="sect2-h">Milestone ladder — floor → target</div>
      <div id="milestones"><div class="skeleton">placing the marker…</div></div>

      <div class="sect" id="h-verd" onclick="tog('verd')"><span class="caret">▾</span><span class="ttl">the four checks</span><span class="line"></span></div>
      <div class="sec-body" id="s-verd"><div id="verdicts"><div class="skeleton">solving goal model…</div></div></div>

      <div class="sect" id="h-risk" onclick="tog('risk')"><span class="caret">▾</span><span class="ttl">risk &amp; Kelly · per-trade model</span><span class="line"></span></div>
      <div class="sec-body" id="s-risk"><div id="riskbox"></div></div>

      <div class="sect" id="h-sens" onclick="tog('sens')"><span class="caret">▾</span><span class="ttl">win-rate sensitivity · R-target scenarios</span><span class="line"></span></div>
      <div class="sec-body" id="s-sens"><div id="sens"></div></div>

      <div class="sect" id="h-lad" onclick="tog('lad')"><span class="caret">▾</span><span class="ttl">scenario ladder — win rate × R</span><span class="line"></span></div>
      <div class="sec-body" id="s-lad"><div id="ladder"></div></div>

      <div class="sect" id="h-bask" onclick="tog('bask')"><span class="caret">▾</span><span class="ttl">basket — speed vs survival</span><span class="line"></span></div>
      <div class="sec-body" id="s-bask"><div id="baskets"><div class="skeleton">scoring baskets…</div></div></div>

      <div class="sect2-h">next</div>
      <div style="display:flex;flex-wrap:wrap;gap:10px 16px;font-size:12px;margin-bottom:6px">
        <a class="ac" href="/prop-desk">Desk · can I enter now? →</a>
        <a class="ac" href="/prop-signals">Signals · pending alerts →</a>
        <a class="ac" href="/prop-position">Position · size a trade →</a>
        <a class="ac" href="/prop-ledger">Ledger · track equity vs the walls →</a>
        <a class="ac" href="/prop-analytics">Analytics · how am I doing? →</a>
      </div>
    </div>
  </div>
</div>
"""

SCRIPT = r"""
const $=id=>document.getElementById(id);
function tog(id){ $('h-'+id).classList.toggle('closed'); $('s-'+id).classList.toggle('closed'); }
function money(n){ return (n==null)?'—':Number(n).toLocaleString(undefined,{maximumFractionDigits:0}); }
function card(l,v,n,c){ return `<div class="card ${c||''}"><div class="lbl">${l}</div><div class="val">${v}</div><div class="note">${n||''}</div></div>`; }
function pil(l,v,n,c){ return `<div class="pil ${c||''}"><div class="pil-l">${l}</div><div class="pil-v">${v}</div><div class="pil-n">${n||''}</div></div>`; }
let CONE=null, EQUITY=null;

function drawCone(d){
  const cv=$('cone'), ctx=cv.getContext('2d');
  const W=cv.width=cv.clientWidth*2, H=cv.height=600; ctx.scale(1,1);
  ctx.clearRect(0,0,W,H);
  const b=d.band; if(!b||!b.length) return;
  const PAD={l:70,r:16,t:18,b:34};
  const lo=Math.min(d.floor, ...b.map(x=>x.p10)), hi=Math.max(d.target, ...b.map(x=>x.p90));
  const X=i=>PAD.l+(i/(b.length-1))*(W-PAD.l-PAD.r);
  const Y=v=>PAD.t+(1-(v-lo)/(hi-lo))*(H-PAD.t-PAD.b);
  const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
  const ink=css('--ink')||'#ddd', dim=css('--dim')||'#888', long=css('--long')||'#1fd989',
        short=css('--short')||'#ff5468', acc=css('--accent')||'#6cf', line=css('--line')||'#333';

  // p10–p90 band
  ctx.beginPath();
  b.forEach((x,i)=>{ i?ctx.lineTo(X(i),Y(x.p90)):ctx.moveTo(X(i),Y(x.p90)); });
  for(let i=b.length-1;i>=0;i--) ctx.lineTo(X(i),Y(b[i].p10));
  ctx.closePath(); ctx.fillStyle=acc+'22'; ctx.fill();

  // median
  ctx.beginPath(); ctx.lineWidth=3; ctx.strokeStyle=acc;
  b.forEach((x,i)=>{ i?ctx.lineTo(X(i),Y(x.p50)):ctx.moveTo(X(i),Y(x.p50)); }); ctx.stroke();

  // target + floor
  ctx.setLineDash([7,6]); ctx.lineWidth=2;
  ctx.strokeStyle=long; ctx.beginPath(); ctx.moveTo(PAD.l,Y(d.target)); ctx.lineTo(W-PAD.r,Y(d.target)); ctx.stroke();
  ctx.strokeStyle=short; ctx.beginPath(); ctx.moveTo(PAD.l,Y(d.floor)); ctx.lineTo(W-PAD.r,Y(d.floor)); ctx.stroke();
  ctx.setLineDash([]);

  ctx.font='20px ui-monospace,monospace'; ctx.textAlign='left';
  ctx.fillStyle=long;  ctx.fillText('TARGET $'+money(d.target), PAD.l+6, Y(d.target)-8);
  ctx.fillStyle=short; ctx.fillText('FLOOR $'+money(d.floor),  PAD.l+6, Y(d.floor)+24);

  // axes
  ctx.strokeStyle=line; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(PAD.l,PAD.t); ctx.lineTo(PAD.l,H-PAD.b); ctx.lineTo(W-PAD.r,H-PAD.b); ctx.stroke();
  ctx.fillStyle=dim; ctx.font='18px ui-monospace,monospace';
  ctx.textAlign='right';
  [lo,(lo+hi)/2,hi].forEach(v=>ctx.fillText('$'+money(v), PAD.l-8, Y(v)+6));
  ctx.textAlign='center';
  const ticks=Math.min(6,b.length);
  for(let t=0;t<ticks;t++){
    const i=Math.round(t*(b.length-1)/(ticks-1));
    ctx.fillText((b[i].days!=null?b[i].days+'d':b[i].trade+'t'), X(i), H-PAD.b+24);
  }
  ctx.textAlign='left'; ctx.fillStyle=ink;
  ctx.fillText('median of surviving paths · band = p10–p90', PAD.l+6, PAD.t+20);
}

function render(d){
  if(d.error){ $('pillars').innerHTML=`<div class="skeleton" style="color:var(--amber)">${d.error}</div>`; return; }
  CONE=d;
  const eta = d.median_days_to_target!=null ? d.median_days_to_target+'d' : '—';
  $('pillars').innerHTML =
      pil('Pass rate', d.pass_pct+'%', d.fail_pct+'% hit the −'+d.dd_pct+'% floor first', d.pass_pct>=60?'g':d.pass_pct>=35?'a':'r')
    + pil('Median ETA', eta, d.eta_date?('~'+d.eta_date+' · '+d.median_trades_to_target+' trades'):'never reaches it','b')
    + pil('Target', '$'+money(d.target), '+'+d.target_pct+'% · from $'+money(d.account),'g')
    + pil('Signals / wk', d.signals_per_week, d.trades_per_month+'/mo · '+d.basket.length+' strategies · '+(d.expected_cost_per_pass?('$'+money(d.expected_cost_per_pass)+'/pass'):'—'),'b');
  drawCone(d);
  renderMilestones(d);
  $('caveat').innerHTML = `<div class="warn">
    <b>Read this before trusting the cone.</b> It is drawn on <b>backtest</b> geometry.
    The measured edge from your live ledger (2026-07-09 Monte Carlo) put the pass-rate at
    <b>1.5%</b>, not ${d.pass_pct}% — the strategies have not yet reproduced their backtest
    on real fills. Second: widening the basket buys <b>trades per month, not edge</b>. It pulls
    the median date closer and pushes the pass-rate down. Faster is not cheaper.
  </div>`;
}

// Milestone ladder — the eval's rungs (floor → start → target) with the live
// equity marker. The eval's answer to /goal's milestone ladder, but bounded: it's
// a sprint between two walls, not an open-ended climb.
function renderMilestones(d){
  const lo=d.floor, hi=d.target, span=(hi-lo)||1, eq=EQUITY;
  const rungs=[
    ['Target',  d.target,               'long',  '+'+d.target_pct+'% — eval passed'],
    ['Halfway', (d.account+d.target)/2, 'accent','+'+(d.target_pct/2)+'%'],
    ['Start',   d.account,              'dim',   'breakeven'],
    ['Floor',   d.floor,                'short', '−'+d.dd_pct+'% — eval failed'],
  ];
  const bar=v=>(Math.max(0,Math.min(1,(v-lo)/span))*100).toFixed(0);
  const html=rungs.map(([lab,v,cv,note])=>{
    const here = eq!=null && Math.abs(v-eq) <= span*0.055;
    return `<div class="mrung ${here?'here':''}">
      <span class="mlab"><b style="color:var(--${cv})">${lab}</b> · ${note}</span>
      <span class="mbar"><span style="width:${bar(v)}%;background:var(--${cv})"></span></span>
      <span class="mval">$${money(v)}</span></div>`;
  }).join('');
  const note = eq!=null
    ? `Live equity <b style="color:var(--ink)">$${money(eq)}</b> — <b>${(Math.max(0,Math.min(1,(eq-lo)/span))*100).toFixed(0)}%</b> of the way from floor to target. `
      + `Cushion to the floor: <b style="color:var(--short)">$${money(eq-lo)}</b>.`
    : `No live eval equity yet — <a href="/prop-ledger" class="ac">log a fill</a> to place your marker on the ladder.`;
  $('milestones').innerHTML = html + `<div class="sub" style="font-size:11px;margin-top:11px">${note}</div>`;
}

function chk(ok,word,val,lbl,note){
  return `<div class="card ${ok?'g':'r'}"><div class="lbl">${ok?'✓':'✕'} ${word}</div>
    <div class="val">${val}</div><div class="note">${lbl}<br><span style="color:var(--faint)">${note}</span></div></div>`;
}
function kv(k,v,c){ return `<div class="kv"><span class="k">${k}</span><span class="v ${c||''}">${v}</span></div>`; }

function renderModel(m){
  if(m.error){ $('verdicts').innerHTML=`<div class="skeleton" style="color:var(--amber)">${m.error}</div>`; return; }

  // ── the four checks, mirroring /goal but in eval terms ──────────────────────
  const evOK = m.edge_sufficient;
  const floorOK = m.floor_touch_pct < 20;
  const riskOK = Math.abs(m.used_risk_pct - m.optimal_risk_pct) / m.optimal_risk_pct < 0.25;
  const timeOK = m.days_needed_ev != null && m.days_needed_ev <= m.days_to_target * 1.5;
  $('verdicts').className='grid';
  $('verdicts').innerHTML =
      chk(evOK,'Edge', (m.ev_per_trade_pct>=0?'+':'')+m.ev_per_trade_pct+'%', 'EV / trade',
          'need +'+m.ev_required_pct+'% for the target date')
    + chk(floorOK,'Floor', m.floor_touch_pct+'%', 'P(touch −'+m.dd_pct+'% floor)',
          'MC says '+m.floor_touch_mc_pct+'% · '+m.ruin_label)
    + chk(riskOK,'Risk', m.used_risk_pct+'%', 'used vs '+m.optimal_risk_pct+'% optimal',
          m.losses_to_floor+' straight losses reach the floor')
    + chk(timeOK,'Time', (m.days_needed_ev??'—')+'d', 'EV-implied arrival',
          'median passer '+m.days_to_target+'d (survivorship)');

  // ── sidebar: the locked plan (firm rules) + the basket/edge params ──────────
  $('plan').innerHTML =
      kv('Eval', m.eval||'—')
    + kv('Account','$'+money(m.account))
    + kv('Target','$'+money(m.target)+' · +'+m.target_pct+'%','g')
    + kv('Floor','$'+money(m.floor)+' · −'+m.dd_pct+'%','r')
    + kv('Daily wall','−'+m.daily_pct+'%/day','r')
    + kv('Risk / trade',m.used_risk_pct+'% · $'+money(m.risk_usd))
    + kv('Stop · lev',m.stop_price_pct+'% · '+m.leverage+'×')
    + kv('Leverage cap',m.max_leverage+'×','dim')
    + `<div class="sub" style="font-size:10px;margin-top:9px;color:var(--faint)">Fixed by the firm — read-only. Your only levers are <b>R</b> (exit discipline) and the <b>basket</b>.</div>`;
  $('params').innerHTML =
      kv('WR · R <span class="dim">backtest</span>',m.plan.wr+'% · '+m.plan.rr+'R')
    + (m.measured?kv('WR · R <span class="dim">realised</span>',m.measured.wr+'% · '+m.measured.rr+'R','a'):'')
    + kv('EV / trade',(m.ev_per_trade_pct>=0?'+':'')+m.ev_per_trade_pct+'%',m.ev_per_trade_pct>=0?'g':'r')
    + kv('Trades','<b>'+m.trades_per_month+'</b>/mo · '+m.trades_per_week+'/wk')
    + kv('Basket',m.basket.length+' strateg'+(m.basket.length===1?'y':'ies'))
    + kv('Trades needed',m.trades_needed+' <span class="dim">@ EV</span>');

  // ── risk & Kelly ───────────────────────────────────────────────────────────
  $('riskbox').innerHTML = `<div class="panel">
    ${kv('Optimal risk','<b>'+m.optimal_risk_pct+'%</b> <span class="dim">smaller of ¼-Kelly ('+m.kelly_pct+'%) and the floor cap ('+m.dd_constraint_pct+'%)</span>')}
    ${kv('Used risk','<b>'+m.used_risk_pct+'%</b> <span class="dim">'+(m.used_risk_pct<=m.optimal_risk_pct?'inside':'over')+' optimal</span>',m.used_risk_pct<=m.optimal_risk_pct?'g':'r')}
    ${kv('Full Kelly',m.full_kelly_pct+'% <span class="dim">growth-optimal, ignores the floor</span>','dim')}
    ${kv('Losses to floor','<b>'+m.losses_to_floor+'</b> straight stops','r')}
    ${kv('Wins to recover',m.wins_to_breakeven+' from a full drawdown')}
    ${kv('Expectancy','<b>'+m.expectancy_r+'R</b> / trade · PF '+m.profit_factor)}
    ${kv('Geometric drift',(m.geom_drift_pct>=0?'+':'')+m.geom_drift_pct+'% / trade',m.geom_drift_pct>=0?'g':'r')}
    ${kv('Sharpe / trade',m.sharpe_per_trade+' · vol '+m.trade_volatility_pct+'%')}
    ${kv('Typical win / loss','+'+m.typical_win_pct+'% / '+m.typical_loss_pct+'% <span class="dim">log</span>')}
    ${kv('Friction',m.friction_pct+'% / trade <span class="dim">fees, no slippage on limit fills</span>')}
  </div>
  <div class="warn" style="margin-top:10px">The floor cap binds, not Kelly. ¼-Kelly would let you risk <b>${m.kelly_pct}%</b>;
  the <b>${m.dd_pct}% floor</b> only permits <b>${m.dd_constraint_pct}%</b>. You are risking ${m.used_risk_pct}% — essentially exactly at the cap.
  <b>Raising risk cannot help</b>: it buys variance, not edge, and the floor is what ends the eval.</div>`;

  // ── sensitivity + R scenarios ──────────────────────────────────────────────
  const srow=r=>`<tr class="${Math.abs(r.wr-m.plan.wr)<0.05?'on':''}"><td>${r.wr}%</td><td class="${r.ev>=0?'g':'r'}">${r.ev>=0?'+':''}${r.ev}%</td><td class="${r.drift>=0?'g':'r'}">${r.drift>=0?'+':''}${r.drift}%</td><td class="${r.ruin>=20?'r':''}">${r.ruin}%</td></tr>`;
  const rrow=r=>`<tr class="${Math.abs(r.rr-m.plan.rr)<0.01?'on':''}"><td>${r.rr}R</td><td class="${r.ev>=0?'g':'r'}">${r.ev>=0?'+':''}${r.ev}%</td><td class="${r.drift>=0?'g':'r'}">${r.drift>=0?'+':''}${r.drift}%</td><td class="${r.ruin>=20?'r':''}">${r.ruin}%</td></tr>`;
  $('sens').innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px">
    <div><div class="sub" style="font-size:11px">Win-rate sensitivity <span class="dim">(R held at ${m.plan.rr})</span></div>
      <div class="sb-wrap"><table><tr><th>WR</th><th>EV/tr</th><th>drift</th><th>floor risk</th></tr>${m.wr_sensitivity.map(srow).join('')}</table></div></div>
    <div><div class="sub" style="font-size:11px">R-target scenarios <span class="dim">(WR held at ${m.plan.wr}%)</span></div>
      <div class="sb-wrap"><table><tr><th>R:R</th><th>EV/tr</th><th>drift</th><th>floor risk</th></tr>${m.r_scenarios.map(rrow).join('')}</table></div></div>
  </div>
  <div class="sub" style="font-size:11px;margin-top:8px">R is the lever you control — exit discipline. Win rate is the one you don't.
  <b>Note the shape:</b> pushing R from 3 to 6 nearly triples EV but barely moves floor risk (${m.r_scenarios[0]?.ruin}% → ${m.r_scenarios[m.r_scenarios.length-1]?.ruin}%), because bigger targets take longer and the floor gets more chances to hit.</div>`;

  // ── WR × R ladder ──────────────────────────────────────────────────────────
  const L=m.ladder;
  const head='<tr><th>WR ╲ R</th>'+L.r_axis.map(r=>`<th>${r}R</th>`).join('')+'</tr>';
  const body=L.rows.map(row=>{
    const cells=row.cells.map((c,i)=>{
      if(!c) return '<td class="dim">—</td>';
      const pin = (Math.abs(row.wr-m.plan.wr)<3 && Math.abs(L.r_axis[i]-m.plan.rr)<0.5) ? ' style="outline:2px solid var(--accent)"' : '';
      const pinM = (m.measured && Math.abs(row.wr-m.measured.wr)<3 && Math.abs(L.r_axis[i]-m.measured.rr)<0.5) ? ' style="outline:2px solid var(--amber)"' : '';
      return `<td class="${c.ev>=0?'g':'r'}"${pin||pinM}>${c.ev>=0?'+':''}${c.ev}%<br><span class="dim" style="font-size:10px">${c.ruin}% floor</span></td>`;
    }).join('');
    return `<tr><td>${row.wr}%</td>${cells}</tr>`;
  }).join('');
  $('ladder').innerHTML = `<div class="sb-wrap"><table>${head}${body}</table></div>
    <div class="sub" style="font-size:11px;margin-top:8px">Each cell: <b>EV per trade</b> / probability of touching the ${m.dd_pct}% floor.
    <span style="outline:2px solid var(--accent);padding:0 4px">blue</span> = the basket's backtest (WR ${m.plan.wr}% · ${m.plan.rr}R).
    ${m.measured?`<span style="outline:2px solid var(--amber);padding:0 4px">amber</span> = what you've actually realised (WR ${m.measured.wr}% · ${m.measured.rr}R, n=${m.measured.n}). The gap between the two pins is the distance between what the backtest claims and what you've shown.`:''}</div>`;
}

async function loadModel(){
  try{ renderModel(await fetch('/api/prop/goal/model').then(r=>r.json())); }
  catch(e){ $('verdicts').innerHTML='<div class="skeleton" style="color:var(--amber)">model failed</div>'; }
}

async function loadBaskets(){
  try{
    const d=await fetch('/api/prop/baskets').then(r=>r.json());
    const rows=(d.options||[]).map(o=>`<tr class="${o.active?'on':''}">
      <td>${o.label}${o.active?' <span class="dim">· active</span>':''}</td>
      <td>${o.n}</td>
      <td>${o.signals_per_week}</td>
      <td class="${o.pass_pct>=60?'g':o.pass_pct>=35?'':'r'}">${o.pass_pct}%</td>
      <td class="dim">${o.days_to_target!=null?o.days_to_target+'d':'—'}</td>
      <td class="r">${o.expected_cost_per_pass?('$'+money(o.expected_cost_per_pass)):'—'}</td>
      <td>${o.active?'':`<button class="pick" onclick='pick(${JSON.stringify(o.basket)})'>use</button>`}</td>
    </tr>`).join('');
    $('baskets').innerHTML=`<div class="sb-wrap"><table>
      <tr><th>basket</th><th>n</th><th>sig/wk</th><th>pass%</th><th>median</th><th>cost / pass</th><th></th></tr>
      ${rows}</table></div>
      <div class="sub" style="font-size:11px;margin:8px 0 0">“cost / pass” = your $${money(d.fee)} fee ÷ pass-rate: what one funded account is expected to cost in eval fees. Speed is bought with fees, not skill.</div>`;
  }catch(e){ $('baskets').innerHTML='<div class="skeleton" style="color:var(--amber)">failed to score baskets</div>'; }
}
async function pick(b){
  if(!confirm('Trade this basket ('+b.length+' strategies)? The scanner will alert on all of them.')) return;
  const r=await fetch('/api/prop/basket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({basket:b})});
  if(!r.ok){ alert('failed'); return; }
  load(); loadModel(); loadBaskets();   // basket change moves every number on this page
}
async function load(){
  try{
    const [d, led] = await Promise.all([
      fetch('/api/prop/goal').then(r=>r.json()),
      fetch('/api/prop/ledger').then(r=>r.json()).catch(()=>null)
    ]);
    EQUITY = (led && led.equity!=null) ? led.equity : null;
    render(d);
  }catch(e){ $('pillars').innerHTML='<div class="skeleton" style="color:var(--amber)">failed to load</div>'; }
}
addEventListener('resize',()=>CONE&&drawCone(CONE));
load(); loadModel(); loadBaskets();
"""


def goal_page() -> str:
    return shell("/prop-goal", "Goal", BODY, script=SCRIPT, head_extra=_CSS,
                 meta="when do I hit target?")
