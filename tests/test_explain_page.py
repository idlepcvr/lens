"""The front door is the one page shown to people who can't audit it themselves.

These aren't render-smoke tests. Each one guards a rule from the page's
docstring that a well-meaning edit would otherwise quietly break — the banned
vocabulary, the no-money-figures rule, and the honesty of the decision grid.
"""

import _bootstrap  # noqa: F401  — must precede the app import

import re

from app import explain_page


def _html() -> str:
    return explain_page.render()


def test_renders():
    assert _html().lstrip().startswith("<!"), "shell() should emit a document"


def test_decision_grid_matches_the_ledger():
    """The dots are a record, not an illustration — one per real signal."""
    seen = explain_page._decisions()
    grid = re.search(r'<div class="grid".*?>(.*?)</div>', _html(), re.S).group(1)
    assert grid.count("<i") == len(seen)
    assert grid.count('class="ok"') == sum(s == "approved" for s in seen)


def test_no_money_figures():
    """A figure invites 'are you any good?' and 'how much have you got?'."""
    assert not re.search(r"[€$]\s?\d", _html())


def test_no_jargon_and_no_hold_time_claim():
    """`swing`/`day trader` are banned because the ledger contradicts them:
    median hold is ~2h and no position has ever been held past 3 days."""
    html = _html().lower()
    for term in ("swing", "day trader", "days or weeks",
                 "drawdown", "backtest", "veto", "edge"):
        assert term not in html, f"banned term on the front door: {term!r}"


def test_no_solicitation():
    """Left off deliberately while AKA is in wind-down. Lawyer first.

    Guarded from both ends, because the words themselves are ambiguous — the
    page says "no signup" as a *disclaimer*. So: the disclaimer must survive,
    and the terms that could only ever appear in an actual offer must not.
    """
    html = _html().lower()
    flat = re.sub(r"\s+", " ", html)     # the copy wraps; the sentence must not
    assert "i'm not managing anyone's money and i'm not asking for any" in flat
    assert "no product, no signup, no advice, and no offer" in flat
    for term in ("invest", "subscribe", "deposit", "get started",
                 "on your behalf", "minimum", "returns"):
        assert term not in html, f"this page must not solicit: {term!r}"


def test_diagrams_survive_without_css_or_js():
    """Every fold's message is markup, so it renders in print and headless."""
    html = _html()
    assert "<script" not in html
    assert html.count("<svg") == 3          # two trades + the no-keys plate
    for label in ("aria-label", "role=\"img\""):
        assert label in html


def test_one_way_out():
    """/system was deleted 2026-07-31 for being a craft showcase aimed at
    nobody. The front door has exactly one exit and it goes to the desk."""
    html = _html()
    assert "/system" not in html, "the deleted instrument plate is linked again"
    out = re.search(r'<div class="out">(.*?)</div>', html, re.S).group(1)
    assert out.count("<a ") == 1, "the front door should offer one way out"
    assert "/dashboard" in out


def test_both_outcomes_are_shown():
    """Showing only the winning trade would be the most dishonest thing here."""
    html = _html()
    assert "this one worked" in html and "this one didn't" in html


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
