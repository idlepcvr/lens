"""MAE/MFE sign conventions and the long/short mirror.

An inverted sign here would be invisible on the page and wrong in the verdict.
Run: python test_excursion.py
"""
import os, sqlite3, tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "t.db"

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
import app.excursion as ex
ex._DB_PATH = _tmp

O, C = "2026-01-01T00:00:00+00:00", "2026-01-01T02:30:00+00:00"
T0 = 1767225600000  # ms epoch of O; bars must sit on the same clock as the trades

# One 1h series. Entry lands on bar 0; price runs UP to 110 then DOWN to 90.
BARS = [  # ts(ms), high, low
    (T0,             102.0, 98.0),
    (T0 + 3600_000,  110.0, 100.0),
    (T0 + 7200_000,  105.0, 90.0),
]
c = sqlite3.connect(_tmp)
c.execute("CREATE TABLE ohlcv_cache (symbol TEXT, timeframe TEXT, ts INTEGER,"
          " open REAL, high REAL, low REAL, close REAL, volume REAL,"
          " PRIMARY KEY (symbol,timeframe,ts))")
c.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, direction TEXT, entry REAL,"
          " exit REAL, opened_at TEXT, closed_at TEXT, pnl REAL, setup_tag TEXT)")
c.executemany("INSERT INTO ohlcv_cache VALUES ('bybit:BTC/USDT:USDT','1h',?,0,?,?,0,0)", BARS)

# entry 100: high 110 (+10%), low 90 (-10%)
c.execute("INSERT INTO trades VALUES (1,'long',100,104,?,?,4,'S1')", (O, C))
c.execute("INSERT INTO trades VALUES (2,'short',100,96,?,?,4,'S2')", (O, C))
c.commit(); c.close()

# force the 1h series (no 5m data in this fixture)
ex._SOURCES = [("bybit:BTC/USDT:USDT", "1h", 3_600_000)]
rows = {r["id"]: r for r in ex.excursions()}
assert len(rows) == 2, rows

# LONG: price up 10% = MFE; price down 10% = MAE. Realized +4%. Capture 4/10.
lo = rows[1]
assert abs(lo["mfe_pct"] - 10.0) < 1e-6, lo
assert abs(lo["mae_pct"] - 10.0) < 1e-6, lo
assert abs(lo["realized_pct"] - 4.0) < 1e-6, lo
assert abs(lo["capture"] - 0.4) < 1e-6, lo

# SHORT: mirrored. Price DOWN to 90 is favourable (MFE), UP to 110 is adverse (MAE).
sh = rows[2]
assert abs(sh["mfe_pct"] - 10.0) < 1e-6, sh
assert abs(sh["mae_pct"] - 10.0) < 1e-6, sh
assert abs(sh["realized_pct"] - 4.0) < 1e-6, sh

# An excursion is a distance: never negative, even when price only moves one way.
c = sqlite3.connect(_tmp)
c.execute("DELETE FROM ohlcv_cache")
c.executemany("INSERT INTO ohlcv_cache VALUES ('bybit:BTC/USDT:USDT','1h',?,0,?,?,0,0)",
              [(T0, 101.0, 100.0), (T0 + 3600_000, 108.0, 100.0), (T0 + 7200_000, 108.0, 100.0)])
c.commit(); c.close()
only_up = {r["id"]: r for r in ex.excursions()}
assert only_up[1]["mae_pct"] == 0.0, "long that never went under entry has zero MAE"
assert only_up[2]["mfe_pct"] == 0.0, "short that never went under entry has zero MFE"

# Verdict logic: the whole point of the module. cap = capture on WINNERS.
assert "EXITS" in ex._verdict(0.3, 1.2), "move was there on losers + you banked little = exits"
assert "SELECTION" in ex._verdict(0.85, 0.31), "you bank the move; losers never ran = selection"
assert "MIXED" in ex._verdict(0.85, 1.2), "bank the move AND losers ran = neither dominates"
assert ex._verdict(None, None) == "insufficient data"

# Capture on a loser is a sign artefact, so summary() must not median it in.
fake = [
    {"pnl": +1, "capture": 0.9, "mfe_pct": 1.2, "mae_pct": 0.3, "realized_pct": 1.0, "resolution": "5m"},
    {"pnl": -1, "capture": -5.0, "mfe_pct": 0.1, "mae_pct": 0.9, "realized_pct": -0.5, "resolution": "5m"},
]
s = ex.summary(fake)
assert s["median_capture_on_winners"] == 0.9, "losers must not drag capture negative"

# The panel grades against the LIVE geometry, never a stale literal.
from app.setups import SL_PCT, TP_PCT
assert (s["tp_pct"], s["sl_pct"]) == (TP_PCT, SL_PCT), "summary must track setups' geometry"


# reachability: a win-rate CEILING held against the fee-adjusted breakeven WR.
# rr = 1.5/0.63 = 2.381 -> breakeven = 1.112/3.381 = 32.9%.
def _rows(hits, n=100, move=2.0):
    """n rows, `hits` of which ran >= 2.0% in favour (so >= any tp we test)."""
    return [{"mfe_pct": move if i < hits else 0.1, "mae_pct": 0.5,
             "realized_pct": 0.0, "capture": None, "pnl": 0, "resolution": "5m"}
            for i in range(n)]


starved = ex.reachability(1.5, 0.63, rows=_rows(10))    # ceiling 10% vs 32.9%
assert starved["badge"] == "STARVED", starved
assert starved["hit"] == 10 and starved["n"] == 100, starved
assert abs(starved["breakeven_wr"] - 0.3289) < 1e-3, starved

tight = ex.reachability(1.5, 0.63, rows=_rows(40))      # 40% -> ratio 1.22
assert tight["badge"] == "TIGHT", tight

offered = ex.reachability(1.5, 0.63, rows=_rows(60))    # 60% -> ratio 1.82
assert offered["badge"] == "OFFERED", offered

# A wider TP lowers the breakeven bar but drops the ceiling faster — that trade-off
# is the whole finding, so pin it: same book, same stop, strictly worse ratio.
assert (ex.reachability(3.0, 0.63, rows=_rows(40, move=2.0))["ratio"]
        < tight["ratio"]), "a target past every MFE cannot improve the ratio"

# Guards: too few trades to measure, and degenerate geometry.
assert ex.reachability(1.5, 0.63, rows=_rows(3, n=5)) is None, "min_n guard"
assert ex.reachability(0, 0.63, rows=_rows(40)) is None
assert ex.reachability(1.5, 0, rows=_rows(40)) is None

print("ok — 25 checks passed")
