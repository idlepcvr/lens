"""-3% barrier-touch Monte Carlo for the Kraken eval ladder.

Answers: at a given edge, what fraction of eval attempts hit +10% (pass)
before touching -3% (fail)?  This is the rule that actually kills the eval,
not the 50%-drawdown "risk of ruin" the spreadsheet reports.
"""
import random

TRIALS = 20_000
MAX_TRADES = 400  # eval attempt gives up after this many


def attempt(wr, R, risk, fee_R, trailing, rng, target_pct=10.0, dd_pct=3.0):
    """One eval attempt. Returns 'pass' | 'fail' | 'stall'.

    target_pct/dd_pct default to the original 10%/3% this script shipped
    with — pass them explicitly to match a real eval rule (they differ per
    tier: TURBO is 9%/3%, CLASSIC 10%/6%, PRO 12%/5%)."""
    eq = 1.0
    peak = 1.0
    target = 1.0 + target_pct / 100
    for _ in range(MAX_TRADES):
        won = rng.random() < wr
        eq += risk * ((R if won else -1.0) - fee_R)
        peak = max(peak, eq)
        floor = peak - dd_pct / 100 if trailing else 1.0 - dd_pct / 100
        if eq <= floor:
            return "fail"
        if eq >= target:
            return "pass"
    return "stall"


def run(wr, R, risk, fee_R=0.1, trailing=True, seed=1, target_pct=10.0, dd_pct=3.0):
    rng = random.Random(seed)
    out = {"pass": 0, "fail": 0, "stall": 0}
    for _ in range(TRIALS):
        out[attempt(wr, R, risk, fee_R, trailing, rng, target_pct, dd_pct)] += 1
    return {k: v / TRIALS for k, v in out.items()}


def expectancy(wr, R, fee_R=0.1):
    return wr * R - (1 - wr) - fee_R


# fee_R: measured WR/R come from the trade ledger where `pnl` is ALREADY net of
# fees (verified: balance_after - balance_before == pnl). Charging fees again
# would double-count. The hypothetical geometries are stated gross, so they pay.
SCENARIOS = [
    ("measured (90d): 32.5% WR, 1.76R", 0.325, 1.76, 0.0),
    ("thesis survival bar: 30% WR, 3R", 0.30, 3.0, 0.1),
    ("his claim (n=0):    50% WR, 3R", 0.50, 3.0, 0.1),
]

if __name__ == "__main__":
    for trailing in (True, False):
        kind = "trailing-peak" if trailing else "static-from-start"
        print(f"\n=== -3% drawdown, {kind} · target +10% ===")
        print(f"{'edge':<36} {'risk':>5} {'E[R]':>7} {'pass':>7} {'fail':>7} {'stall':>7}")
        for label, wr, R, fee_R in SCENARIOS:
            for risk in (0.005, 0.01, 0.02):
                r = run(wr, R, risk, fee_R=fee_R, trailing=trailing)
                print(f"{label:<36} {risk:>5.1%} {expectancy(wr,R,fee_R):>+7.3f} "
                      f"{r['pass']:>7.1%} {r['fail']:>7.1%} {r['stall']:>7.1%}")

    # self-check: a large positive edge with tiny risk should mostly pass;
    # a negative edge should almost never pass.
    good = run(0.60, 3.0, 0.005, fee_R=0.1)
    bad = run(0.325, 1.76, 0.02, fee_R=0.0)
    assert good["pass"] > 0.5, good
    assert bad["pass"] < 0.10, bad

    # target_pct/dd_pct are now real parameters, not baked into 10%/3% — a
    # tighter target must never pass MORE often than a looser one at the
    # same edge, and a tighter floor must never pass more often either.
    same_edge = dict(wr=0.55, R=2.0, risk=0.01, fee_R=0.1, seed=7)
    loose = run(target_pct=9.0, dd_pct=3.0, **same_edge)
    tight = run(target_pct=15.0, dd_pct=3.0, **same_edge)
    assert loose["pass"] > tight["pass"], (loose, tight)
    wide_floor = run(target_pct=9.0, dd_pct=6.0, **same_edge)
    assert wide_floor["pass"] >= loose["pass"], (wide_floor, loose)

    print("\nself-check ok")
