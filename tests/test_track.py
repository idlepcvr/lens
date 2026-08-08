"""Scoring rules for /hedge-track. Pure functions only — no DB, no fixtures."""

from app.track import (MAX_POINTS, WEIGHTS, band_at, band_position, _streaks,
                       score_day)

BAND = {"p10": -100.0, "p25": -50.0, "p50": 0.0, "p75": 50.0, "p90": 100.0}


def _day(kept, **kw):
    return {"kept": kept, **kw}


def test_band_position_ladders_up():
    assert band_position(60.0, BAND) == (75, 1.0)
    assert band_position(10.0, BAND) == (50, 0.75)
    assert band_position(-40.0, BAND) == (25, 0.5)
    assert band_position(-90.0, BAND) == (10, 0.25)
    assert band_position(-500.0, BAND) == (0, 0.0)


def test_no_band_is_not_a_zero():
    # a day the cone can't see must read n/a, never as a miss
    assert band_position(0.0, None) == (None, 0.0)
    assert score_day(None, 0, 0.0, None)["band_pct"] is None


def test_band_at_interpolates_and_bounds():
    pts = [{"t": 0, "p50": 0.0}, {"t": 100, "p50": 100.0}]
    assert band_at(pts, 50)["p50"] == 50.0
    assert band_at(pts, -1) is None      # before the anchor
    assert band_at(pts, 101) is None     # past the horizon


def test_quiet_day_keeps_discipline_but_breaks_the_streak():
    d = score_day(None, 0, 0.0, None)
    assert d["disciplined"] is True      # nothing broken
    assert d["engaged"] is False         # but nothing done
    assert d["kept"] is False            # so it is NOT a streak day


def test_breach_costs_the_largest_component():
    clean = {"n": 1, "breached": 0, "on_plan": 1, "unreviewed": 0}
    dirty = {"n": 1, "breached": 1, "on_plan": 0, "unreviewed": 0}
    assert score_day(clean, 1, 60.0, BAND)["parts"]["discipline"] == WEIGHTS["discipline"]
    assert score_day(dirty, 1, 60.0, BAND)["parts"]["discipline"] == 0
    assert score_day(dirty, 1, 60.0, BAND)["kept"] is False


def test_a_breach_zeroes_the_whole_day():
    # discipline is a gate: a perfect day that broke a rule must not outscore
    # a clean day that did nothing at all
    dirty_but_great = {"n": 3, "breached": 1, "on_plan": 2, "unreviewed": 0}
    busy = score_day(dirty_but_great, 5, 999.0, BAND)
    quiet_clean = score_day(None, 0, 0.0, None)
    assert busy["points"] == 0
    assert set(busy["parts"].values()) == {0}
    assert quiet_clean["points"] > busy["points"]


def test_unreviewed_trade_earns_no_plan_points_and_no_breach():
    t = {"n": 2, "breached": 0, "on_plan": 0, "unreviewed": 2}
    d = score_day(t, 0, 0.0, None)
    assert d["parts"]["plan"] == 0       # silence is not compliance
    assert d["disciplined"] is True      # but it is not a breach either
    assert d["unreviewed"] == 2
    assert d["kept"] is True             # a trade counts as engagement


def test_perfect_day_hits_the_ceiling():
    t = {"n": 1, "breached": 0, "on_plan": 1, "unreviewed": 0}
    assert score_day(t, 1, 60.0, BAND)["points"] == MAX_POINTS


def test_streaks_count_current_from_the_end_and_best_anywhere():
    days = [_day(True), _day(True), _day(True), _day(False), _day(True), _day(True)]
    s = _streaks(days)
    assert s["current"] == 2    # counting back from today
    assert s["best"] == 3


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("track scoring: all checks pass")
