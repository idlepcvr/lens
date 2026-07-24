"""
Permutation robustness check for the discipline filters — CLI twin of /robustness.

Engine lives in app/robustness_page.py (the page and this script share it).
Run from the repo root:  python3 research/perm_test.py [--selftest]
"""

import sys

import _bootstrap  # noqa: F401  — repo root onto sys.path; must precede `app`

from app.robustness_page import load_trades, perm_test


def report(trades, label, n_shuffles=10_000):
    o = perm_test(trades, n_shuffles=n_shuffles)
    print(f"\n=== {label} — {o['n']} trades, {n_shuffles} shuffles ===")
    print(f"09:00 BKK bucket:   {o['h9_n']} trades, €{o['h9_pnl']:+,.0f}")
    print(f"  p (hour 9 this bad, fixed bucket)      = {o['p_h9']:.4f}")
    print(f"  p (ANY hour this bad — honest number)  = {o['p_worst']:.4f}"
          f"   [real worst hour: {o['worst_hr']:02d}:00 BKK €{o['worst_hr_pnl']:+,.0f}]")
    print(f"Saturday bucket:    {o['sat_n']} trades, €{o['sat_pnl']:+,.0f}")
    print(f"  p (ANY weekday this good)              = {o['p_sat']:.4f}")
    return o


def selftest():
    # equal pnls: every shuffle identical, all p-values must be 1.0
    fake = [(h % 24, h % 7, -10.0) for h in range(200)]
    o = report(fake, "selftest: uniform pnl", n_shuffles=1000)
    assert (o["p_h9"], o["p_worst"], o["p_sat"]) == (1.0, 1.0, 1.0)
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        report(load_trades("2026-01-01"), "2026 only (basis of the current rules)")
        report(load_trades(), "lifetime")
        print("\nReading: p < 0.05 → rule beats luck. p > 0.3 → likely noise-mined;"
              "\nkeep collecting (rejected signals are stored) before trusting it."
              "\nSame verdict rendered at http://localhost:8765/robustness")
