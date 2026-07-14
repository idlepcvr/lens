"""The trade-log memo must be invisible: same trades in, same trades out.

_cached_trade_log stands between every prop page and _trade_log. If it ever
returns something the raw walk wouldn't, every downstream number (pass%, cone,
expectancy, sizing) silently lies. So: prove it equals the raw walk, and prove
the key actually separates the inputs that change the answer.

    .venv/bin/python3 test_trade_log_cache.py
"""
from app.backtest_engine import STRATEGIES
from app.prop_eval import EVALS, _cached_df, _cached_trade_log, _trade_log
from app.prop_goal import MONTHS, _basket
from app.prop_views import prop_config

cfg = prop_config()
rule = EVALS[cfg["eval_name"]]
risk = cfg["risk"]
names = [n for n in dict.fromkeys([*_basket(), "ASIAN_RSI_DIP_v1"]) if n in STRATEGIES]
assert names, "no backtestable strategies in the basket — nothing to check"

# 1. identical to the uncached walk, strategy by strategy
for name in names:
    strat = STRATEGIES[name]
    raw = _trade_log(_cached_df(MONTHS, strat.get("timeframe", "4h")),
                     strat["signal_fn"], strat["params"], rule, risk)
    assert _cached_trade_log(name, rule, risk, MONTHS) == raw, f"{name}: memo != raw walk"
    print(f"  {name:<28} {len(raw):>4} trades — memo matches raw walk")

# 2. a second call is a hit, not a re-walk (the whole point)
a = _cached_trade_log(names[0], rule, risk, MONTHS)
b = _cached_trade_log(names[0], rule, risk, MONTHS)
assert a is b, "second call re-walked instead of hitting the cache"

# 3. the key separates what changes the answer — risk scales pnl, so a different
#    risk must not hand back the cached log for the old one.
other = _cached_trade_log(names[0], rule, risk * 2, MONTHS)
assert other is not a, "risk is not part of the cache key — stale log served"
if a:
    assert other[0]["pnl_pct"] != a[0]["pnl_pct"], "doubling risk changed nothing?"

# 4. same for the eval rule (different walls -> different fills/stops)
alt = next((k for k in EVALS if k != cfg["eval_name"]), None)
if alt:
    assert _cached_trade_log(names[0], EVALS[alt], risk, MONTHS) is not a, \
        "eval rule is not part of the cache key — stale log served"

# 5. /regime buckets the hero's trades by the regime on their entry day. It used
#    to walk its own uncached log with its own hardcoded args; it now shares the
#    memo. Same trades in, or the win-rate-per-regime table moves.
REG = ("ASIAN_RSI_DIP_v1", "BREAKOUT_1STEP_TURBO", 0.5, 30)
if REG[0] in STRATEGIES:
    s = STRATEGIES[REG[0]]
    raw = _trade_log(_cached_df(REG[3], s.get("timeframe", "4h")), s["signal_fn"],
                     s["params"], EVALS[REG[1]], REG[2])
    assert _cached_trade_log(REG[0], EVALS[REG[1]], REG[2], REG[3]) == raw, \
        "regime's hero log changed — win-rate-per-regime would move"
    print(f"  regime hero log              {len(raw):>4} trades — memo matches raw walk")

print("\nOK — memo is transparent, and the key covers strategy/risk/rule/months.")
