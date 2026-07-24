"""Self-check for Stage B — scoring /edge search rows against the Fit envelope.

Asserts scored distance (not a hard box): inside → FITS, outside → ranked by how
far outside and on which axis. Pure math, offline (no candles, no DB, no HTTP).
Run: python3 test_search_envelope.py
"""

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app.search_custom import annotate, score_row

ENV = {"wr":   {"min": 0.40, "max": 0.60},
       "rr":   {"min": 2.0,  "max": 4.0},
       "freq": {"min": 1.0,  "max": 5.0},
       "lev":  {"min": 1.0,  "max": 8.0}}


def row(wr, rr, freq, **kw):
    return dict(wr=wr, rr=rr, freq=freq, robust=True, net_pct=1.0, **kw)


def test_inside_fits():
    f = score_row(row(50, 3.0, 3.0), ENV)
    assert f["fits"] and f["dist"] == 0.0 and f["fails"] == [], f


def test_edges_are_inside():
    for r in (row(40, 2.0, 1.0), row(60, 4.0, 5.0)):
        assert score_row(r, ENV)["fits"], r


def test_outside_names_the_axis_and_the_gap():
    f = score_row(row(30, 3.0, 3.0), ENV)          # WR 0.30 vs [0.40, 0.60], span 0.20
    assert not f["fits"]
    assert len(f["fails"]) == 1
    assert f["fails"][0]["axis"] == "win rate"
    assert f["fails"][0]["needs"] == "≥ 40%" and f["fails"][0]["has"] == "30%"
    assert abs(f["dist"] - 0.5) < 1e-9, f          # 0.10 outside ÷ 0.20 span


def test_distance_accumulates_across_axes():
    near = score_row(row(38, 3.0, 3.0), ENV)       # misses WR only
    far = score_row(row(30, 1.0, 9.0), ENV)        # misses WR, R:R and cadence
    assert far["dist"] > near["dist"] > 0
    assert len(far["fails"]) == 3


def test_degenerate_envelope_does_not_divide_by_zero():
    env = {"wr": {"min": 0.5, "max": 0.5}}
    f = score_row(row(40, 3.0, 3.0), env)
    assert not f["fits"] and f["dist"] > 0 and f["dist"] < float("inf")


def test_missing_axis_on_row_is_skipped_not_failed():
    r = {"wr": 50, "rr": 3.0, "robust": True, "net_pct": 1.0}   # no freq
    f = score_row(r, ENV)
    assert f["fits"], f


def test_stale_or_empty_envelope_annotates_nothing():
    rows = [row(50, 3.0, 3.0)]
    for env_row in (None,
                    {"stale": True, "envelope": ENV},
                    {"stale": False, "envelope": {}}):
        annotate(rows, env_row)
        assert "fit" not in rows[0], env_row
    annotate(rows, {"stale": False, "envelope": ENV})
    assert rows[0]["fit"]["fits"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("✓", name)
    print("all green")
