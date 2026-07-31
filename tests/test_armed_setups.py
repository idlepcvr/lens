"""ARMED_SETUPS gates the LIVE surfaces and nothing else.

The failure this guards is subtle and expensive in both directions:

  · Gate too little — a disarmed setup reaches the desk as ENTER, or lands in
    the signals pipeline, and he trades a setup whose out-of-sample expectancy
    is negative. That is the hedge book: 496 fills, 39.5% WR, −€4,347.

  · Gate too much — classify()/backfill_setup_tags() get filtered too, and
    every historical trade tagged S2–S5 silently becomes NONE. The realized-vs-
    mined scoreboard is what would eventually justify re-arming a setup, so
    breaking the tagger destroys the only evidence that could reverse this.

Offline, no DB, no network. Run: python3 test_armed_setups.py
"""

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd

import inspect

from app import setups


def test_only_s1_is_armed():
    """Per results/strategy_scores.json (2026-07-26): S1 is the only setup with
    non-negative net R over 63,270 candles."""
    assert setups.ARMED_SETUPS == frozenset({"S1"})


def test_every_setup_is_accounted_for():
    """A setup that exists but appears in no arming decision is a silent hole.
    SETUP_NAMES also carries 'TEST', a manual signal-injection tag that never
    comes out of matched_setups(), so it is not part of the arming decision."""
    mined = {"S1", "S2", "S3", "S4", "S5"}
    assert mined <= set(setups.SETUP_NAMES)
    assert setups.ARMED_SETUPS <= mined


def test_live_scan_is_gated():
    """scan_latest() feeds emit_signals() — it must filter."""
    src = inspect.getsource(setups.scan_latest)
    assert "ARMED_SETUPS" in src, "the signals pipeline is not gated"


def test_desk_verdict_is_gated():
    """desk_state() drives the ENTER / STAND DOWN verdict he acts on."""
    src = inspect.getsource(setups.desk_state)
    assert "ARMED_SETUPS" in src, "the desk verdict is not gated"


def test_history_tagger_is_NOT_gated():
    """classify() tags trades that already happened. Gating it would rewrite
    the past and destroy the scoreboard that could justify re-arming."""
    src = inspect.getsource(setups.classify)
    assert "ARMED_SETUPS" not in src, (
        "classify() must stay ungated — it tags history, and history happened")


def test_matched_setups_is_NOT_gated():
    """The shared matcher stays honest; callers decide what to do with it."""
    src = inspect.getsource(setups.matched_setups)
    assert "ARMED_SETUPS" not in src, (
        "filter at the caller, not in the shared matcher — classify() uses it too")


def test_desk_labels_do_not_advertise_in_sample_winrates():
    """The desk used to show '90.9% realized (n=11)' beside a setup scoring
    +0.04R over n=431. Those small-sample numbers are why they got traded."""
    src = inspect.getsource(setups._setup_checklists)
    for stale in ("90.9%", "65% mined", "56.7%", "62% mined", "60% realized"):
        assert stale not in src, f"in-sample win rate still on the desk: {stale}"
    assert src.count("out-of-sample") == 5


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
