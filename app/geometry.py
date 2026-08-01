"""Exit geometry from first principles — pure math, no I/O.

The question every other geometry answer in this repo skipped: *how long does
this trade take to resolve, and is the toll worth paying over that distance?*

Model. Price is a driftless random walk with daily volatility σ. Put an
absorbing barrier at −a (stop) and +b (target). Two textbook results:

    E[hold]  = a · b / σ²          expected time to hit either barrier
    P(target) = a / (a + b)         probability it's the target you hit

Both are drift-free. That is the honest baseline: it is what a coin gets, and
any win rate above it is edge you have to actually supply. For a fixed R:R
(b = R·a) they collapse to

    a = σ · √(hold / R)            stop width for a target hold
    P(target) = 1 / (1 + R)        the coin-flip win rate — 20% at R:R 4

Friction is what makes this bite. A round trip costs f (fees + slippage, as %
of price, same units as a and b). You capture b − f on a win and pay a + f on
a loss, so

    breakeven win rate = (a + f) / ((b − f) + (a + f))

Note what is absent: leverage. It scales the win and the loss by exactly the
same factor, so it cancels out of the breakeven condition entirely. Leverage
sets the SIZE of the P&L, never its SIGN. It is a drawdown dial, not an edge
dial — `leverage_for()` therefore derives it from a risk budget, downstream of
the geometry, never as an input to it.

The consequence that drives the whole page: f is a fixed toll, but a shrinks
with √hold. Short holds pay the same toll over a shorter distance, so friction
eats a larger fraction of a smaller stop. Below `min_viable_hold()` no win rate
you can realistically supply covers it — the trade is structurally negative
before you have an opinion about direction.

σ comes from volatility.fetch_volatility()["daily_sigma"] so the geometry
tracks the regime instead of freezing a number from one afternoon's fit.
"""

from __future__ import annotations

from math import sqrt

# Round-trip friction, % of price. 0.15%/side Kraken taker — matches
# calculator.compute_projection's fee_roundtrip default. Maker fills roughly
# halve it, which is the single biggest lever on this page.
FRICTION_PCT = 0.30

# Kraken maker/taker, both sides, for the friction ladder.
FRICTION_LADDER = {
    "taker both sides": 0.30,
    "taker in, maker out": 0.20,
    "maker both sides": 0.10,
    "maker + rebate": 0.05,
}


class GeometryError(ValueError):
    pass


def solve(sigma_daily_pct: float, hold_days: float, rr: float,
          friction_pct: float = FRICTION_PCT) -> dict:
    """Stop/target for a trade intended to resolve in ~`hold_days`.

    Inverts E[hold] = a·b/σ² at fixed R:R. Everything else on the page is a
    consequence of the (a, b) this returns.
    """
    if sigma_daily_pct <= 0:
        raise GeometryError("sigma_daily_pct must be positive")
    if hold_days <= 0:
        raise GeometryError("hold_days must be positive")
    if rr <= 0:
        raise GeometryError("rr must be positive")
    if friction_pct < 0:
        raise GeometryError("friction_pct must be non-negative")

    stop = sigma_daily_pct * sqrt(hold_days / rr)
    target = stop * rr

    # Friction can exceed a thin target outright — at which case there is no
    # win rate that saves it and the breakeven is undefined, not merely high.
    net_win = target - friction_pct
    net_loss = stop + friction_pct
    viable = net_win > 0

    coinflip = 1.0 / (1.0 + rr)
    breakeven = net_loss / (net_win + net_loss) if viable else None

    return {
        "sigma_daily_pct": round(sigma_daily_pct, 4),
        "hold_days": round(hold_days, 3),
        "hold_hours": round(hold_days * 24, 1),
        "rr": round(rr, 3),
        "friction_pct": round(friction_pct, 4),
        "stop_pct": round(stop, 4),
        "target_pct": round(target, 4),
        # What the toll actually costs you, as a share of the stop you're
        # risking. This is the number that indicts short holds.
        "friction_share_of_stop": round(friction_pct / stop, 4),
        "net_win_pct": round(net_win, 4),
        "net_loss_pct": round(net_loss, 4),
        "coinflip_wr": round(coinflip, 4),
        "breakeven_wr": round(breakeven, 4) if breakeven is not None else None,
        # The edge you must supply over a coin, in percentage points. The
        # honest difficulty rating of the configuration.
        "edge_needed_pp": round((breakeven - coinflip) * 100, 2) if breakeven is not None else None,
        "viable": viable,
    }


def implied_hold_days(stop_pct: float, target_pct: float,
                      sigma_daily_pct: float) -> float:
    """The reverse read: how long an EXISTING geometry takes to resolve.

    Point this at a stop/target pair someone chose by eye and it tells you the
    holding period they implicitly signed up for — usually a surprise.
    """
    if sigma_daily_pct <= 0:
        raise GeometryError("sigma_daily_pct must be positive")
    if stop_pct <= 0 or target_pct <= 0:
        raise GeometryError("stop_pct and target_pct must be positive")
    return stop_pct * target_pct / (sigma_daily_pct ** 2)


def net_edge_pct(stop_pct: float, target_pct: float, win_rate: float,
                 friction_pct: float = FRICTION_PCT) -> float:
    """Expected % of notional per trade. Positive = the system makes money.

    Leverage is deliberately not a parameter: it multiplies this number without
    changing its sign. Convert to % of account with `× leverage`.
    """
    if not 0.0 <= win_rate <= 1.0:
        raise GeometryError("win_rate must be between 0 and 1")
    return (win_rate * (target_pct - friction_pct)
            - (1.0 - win_rate) * (stop_pct + friction_pct))


def min_viable_stop(rr: float, win_rate: float,
                    friction_pct: float = FRICTION_PCT) -> float | None:
    """Narrowest stop that still breaks even at `win_rate`, or None if no stop
    does.

    Setting net_edge to zero with target = rr·stop and solving:

        stop = friction / (win_rate·(rr + 1) − 1)

    The denominator going non-positive is the meaningful failure: it means the
    win rate is at or below the coin-flip baseline 1/(1+rr), and then no stop
    width rescues the configuration — widening it scales edge and risk
    together and never crosses zero.
    """
    denom = win_rate * (rr + 1.0) - 1.0
    return None if denom <= 0 else friction_pct / denom


def min_viable_hold(rr: float, win_rate: float, sigma_daily_pct: float,
                    friction_pct: float = FRICTION_PCT) -> float | None:
    """Shortest hold with non-negative EV at `win_rate`. None if unreachable.

    The headline of the page: hold shorter than this and the toll wins,
    regardless of how good the entry was.
    """
    stop = min_viable_stop(rr, win_rate, friction_pct)
    if stop is None:
        return None
    return implied_hold_days(stop, stop * rr, sigma_daily_pct)


# ─── sizing: downstream of geometry, never an input to it ────────────────────

def risk_for_drawdown(max_drawdown: float, streak: int) -> float:
    """Risk-per-trade (fraction of account) that caps `streak` consecutive
    losses at `max_drawdown`. Compounding, so 1 − (1−dd)^(1/streak)."""
    if not 0.0 < max_drawdown < 1.0:
        raise GeometryError("max_drawdown must be between 0 and 1")
    if streak < 1:
        raise GeometryError("streak must be at least 1")
    return 1.0 - (1.0 - max_drawdown) ** (1.0 / streak)


def leverage_for(risk_pct: float, stop_pct: float,
                 friction_pct: float = FRICTION_PCT) -> float:
    """Leverage that makes one stop-out cost exactly `risk_pct` of the account.

    A loss costs (stop + friction) of NOTIONAL; notional/equity is leverage.
    """
    denom = stop_pct + friction_pct
    if denom <= 0:
        raise GeometryError("stop + friction must be positive")
    return risk_pct / denom


def loss_streak_odds(win_rate: float, streak: int) -> float:
    """P(at least one run of `streak` losses in ~100 trades) — the sanity check
    on whether the drawdown cap you sized for is a real scenario or a ghost.

    ponytail: (1−w)^streak × trades, the standard first-passage approximation.
    Overstates slightly by ignoring overlap; fine for a page that only needs to
    say "this is a 1-in-80 event, not a 1-in-3". Exact Markov chain if it ever
    has to drive a decision.
    """
    return min(1.0, (1.0 - win_rate) ** streak * 100)


def config(sigma_daily_pct: float, hold_days: float, rr: float, win_rate: float,
           friction_pct: float = FRICTION_PCT, max_drawdown: float = 0.25,
           streak: int = 15) -> dict:
    """The whole recommendation in one call: geometry + sizing + expectancy.

    This is what the page and setups.py both read, so the number on screen and
    the number the scanner uses can never drift apart.
    """
    g = solve(sigma_daily_pct, hold_days, rr, friction_pct)
    risk = risk_for_drawdown(max_drawdown, streak)
    lev = leverage_for(risk * 100, g["stop_pct"], friction_pct)
    edge = net_edge_pct(g["stop_pct"], g["target_pct"], win_rate, friction_pct)

    # Per-trade % of ACCOUNT, then compounded out at the implied trade rate.
    per_trade_acct = edge * lev
    trades_per_week = 7.0 / hold_days
    weekly = (1 + per_trade_acct / 100) ** trades_per_week - 1
    monthly = (1 + weekly) ** (365.25 / 12 / 7) - 1

    return {
        **g,
        "win_rate": round(win_rate, 4),
        "max_drawdown": round(max_drawdown, 4),
        "loss_streak": streak,
        "streak_odds_per_100": round(loss_streak_odds(win_rate, streak), 4),
        "risk_pct": round(risk * 100, 3),
        "leverage": round(lev, 3),
        "net_edge_pct": round(edge, 4),
        "per_trade_acct_pct": round(per_trade_acct, 4),
        "trades_per_week": round(trades_per_week, 2),
        "weekly_pct": round(weekly * 100, 4),
        "monthly_pct": round(monthly * 100, 4),
        "positive": edge > 0,
    }


# ─── target-first: what does a given weekly return actually demand? ──────────
#
# The rest of this module answers "what does this geometry earn?". These two
# invert it: name the weekly return you want, and get back the win rate it
# requires — stated as an edge over the MEASURED random-entry baseline rather
# than over zero, because zero is not the competition. A cell needing +5pp over
# random is a research problem; one needing +40pp is a fantasy, and the only
# honest way to tell them apart is to price both against the same floor.

def win_rate_for(weekly_target: float, rr: float, risk_pct: float,
                 trades_per_week: float, stop_pct: float,
                 friction_pct: float = FRICTION_PCT) -> float | None:
    """Win rate needed to compound `weekly_target` (0.10 = 10%/week).

    Per trade the account must gain (1+target)^(1/N) − 1. A win pays
    risk × net_R, a loss costs risk, so solving for w:

        w = (need/risk + 1) / (net_R + 1)

    Returns None when the answer is ≥100% — the cell cannot deliver the target
    at that risk budget no matter how good the entries are.
    """
    if risk_pct <= 0 or trades_per_week <= 0:
        raise GeometryError("risk_pct and trades_per_week must be positive")
    target = stop_pct * rr
    net_r = (target - friction_pct) / (stop_pct + friction_pct)
    if net_r <= 0:
        return None
    need = (1.0 + weekly_target) ** (1.0 / trades_per_week) - 1.0
    w = (need / (risk_pct / 100.0) + 1.0) / (net_r + 1.0)
    return None if w >= 1.0 else w


def target_cell(weekly_target: float, rr: float, risk_pct: float,
                trades_per_week: float, sigma_daily_pct: float,
                random_wr: float, hold_days: float = 2.5,
                friction_pct: float = FRICTION_PCT) -> dict | None:
    """One cell of the feasibility map, priced against a measured baseline."""
    g = solve(sigma_daily_pct, hold_days, rr, friction_pct)
    w = win_rate_for(weekly_target, rr, risk_pct, trades_per_week,
                     g["stop_pct"], friction_pct)
    if w is None:
        return None
    # Drawdown from a losing run, and how often such a run shows up. Both are
    # needed: a 60% drawdown that never happens is noise, one that happens
    # monthly is the end of the account.
    dd = lambda k: 1.0 - (1.0 - risk_pct / 100.0) ** k
    return {
        "rr": rr, "risk_pct": risk_pct, "trades_per_week": trades_per_week,
        "stop_pct": g["stop_pct"], "target_pct": g["target_pct"],
        "need_wr": w, "random_wr": random_wr,
        "edge_pp": (w - random_wr) * 100,
        "breakeven_wr": g["breakeven_wr"],
        "dd_5": dd(5), "dd_10": dd(10), "dd_20": dd(20),
        # P(a k-loss run appears in a week) — the drawdown you actually meet
        "streak_5_wk": min(1.0, (1 - w) ** 5 * trades_per_week),
        "leverage": leverage_for(risk_pct, g["stop_pct"], friction_pct),
    }


def max_risk_for_drawdown_cap(max_drawdown: float, losses_tolerated: int) -> float:
    """Inverse of risk_for_drawdown — the biggest risk/trade that survives
    `losses_tolerated` in a row inside a hard drawdown cap. This is the binding
    constraint on a prop account, where breaching ends the account outright
    rather than merely hurting."""
    return risk_for_drawdown(max_drawdown, losses_tolerated) * 100


if __name__ == "__main__":   # ponytail: one runnable check
    SIGMA = 1.79   # live daily_sigma when this was written, % per day

    # ── the barrier identities round-trip ────────────────────────────────────
    g = solve(SIGMA, 2.5, 4.0)
    # tolerances are loose because solve() rounds its outputs to 4dp for display
    assert abs(implied_hold_days(g["stop_pct"], g["target_pct"], SIGMA) - 2.5) < 1e-3
    assert abs(g["target_pct"] / g["stop_pct"] - 4.0) < 1e-3
    # coin-flip win rate is 1/(1+R), independent of vol and hold
    assert abs(g["coinflip_wr"] - 0.20) < 1e-9
    assert abs(solve(3.3, 0.5, 4.0)["coinflip_wr"] - 0.20) < 1e-9

    # ── LEVERAGE CANCELS: the claim the page is built on ─────────────────────
    # Same geometry, wildly different leverage — the SIGN of the edge is
    # identical because leverage never enters net_edge_pct at all.
    e = net_edge_pct(g["stop_pct"], g["target_pct"], 0.25)
    for lev in (1.0, 5.0, 25.0):
        assert (e * lev > 0) == (e > 0), "leverage must not flip the sign"

    # ── friction is what kills short holds ───────────────────────────────────
    short, long_ = solve(SIGMA, 4 / 24, 4.0), solve(SIGMA, 5.0, 4.0)
    assert short["friction_share_of_stop"] > long_["friction_share_of_stop"]
    assert short["breakeven_wr"] > long_["breakeven_wr"]
    # a 4h hold at R:R 4 demands far more edge over a coin than a 5-day one
    assert short["edge_needed_pp"] > 10 > long_["edge_needed_pp"]
    # with zero friction the breakeven collapses to the coin flip
    free = solve(SIGMA, 4 / 24, 4.0, friction_pct=0.0)
    assert abs(free["breakeven_wr"] - free["coinflip_wr"]) < 1e-9

    # ── a target thinner than the toll is not merely hard, it's undefined ────
    doomed = solve(SIGMA, 0.001, 4.0)
    assert not doomed["viable"] and doomed["breakeven_wr"] is None

    # ── min viable: at or below the coin flip, no stop width rescues it ──────
    assert min_viable_stop(4.0, 0.20) is None      # exactly coin-flip
    assert min_viable_stop(4.0, 0.15) is None      # worse than a coin
    ms = min_viable_stop(4.0, 0.25)
    assert ms is not None and abs(net_edge_pct(ms, ms * 4, 0.25)) < 1e-9, "min stop must be exactly breakeven"
    # and the hold it implies is the floor: shorter is negative, longer positive
    mh = min_viable_hold(4.0, 0.25, SIGMA)
    below, above = solve(SIGMA, mh * 0.5, 4.0), solve(SIGMA, mh * 2, 4.0)
    assert net_edge_pct(below["stop_pct"], below["target_pct"], 0.25) < 0 < \
           net_edge_pct(above["stop_pct"], above["target_pct"], 0.25)

    # ── sizing ───────────────────────────────────────────────────────────────
    assert abs(risk_for_drawdown(0.25, 15) - 0.0190) < 1e-3
    # one stop-out costs exactly the risk budget, by construction
    lv = leverage_for(1.9, g["stop_pct"])
    assert abs((g["stop_pct"] + FRICTION_PCT) * lv - 1.9) < 1e-9

    # ── the recommendation, and the friction lever ───────────────────────────
    c = config(SIGMA, 2.5, 4.0, 0.25)
    assert c["positive"] and c["monthly_pct"] > 0
    cheap = config(SIGMA, 2.5, 4.0, 0.25, friction_pct=0.10)
    assert cheap["monthly_pct"] > c["monthly_pct"], "cheaper fills must pay more"
    # and the fragility: a couple of points of win rate flips it
    assert not config(SIGMA, 2.5, 4.0, 0.22)["positive"]

    print(f"σ {SIGMA}%/d · hold 2.5d · R:R 4")
    print(f"  stop {c['stop_pct']:.2f}%  target {c['target_pct']:.2f}%  "
          f"BE {c['breakeven_wr']:.1%} vs coin {c['coinflip_wr']:.0%}")
    print(f"  risk {c['risk_pct']:.2f}%  lev {c['leverage']:.2f}x  "
          f"→ {c['monthly_pct']:+.2f}%/mo")
    print(f"  4h hold would need {short['breakeven_wr']:.1%} "
          f"({short['edge_needed_pp']:+.1f}pp over a coin)")
    print(f"  min viable hold at 25% WR: {mh * 24:.0f}h")
    print("all checks passed")
