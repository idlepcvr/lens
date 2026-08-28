"""Guards PROP↔HEDGE nav parity and shared-page mode resolution.

Two failure modes this locks down:
  1. A page exists for hedge with no prop counterpart (the drift this fixes).
  2. A prop page reusing a hedge bare path (drift back to the old ?book= toggle).
     Every prop page now has its own /prop-* URL, so page_mode resolves each one
     unambiguously and no prop click can land in the hedge nav.

Offline, no DB. Run: .venv/bin/python test_nav_parity.py
"""

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app.theme import (HEDGE_MAIN, NAV_HEDGE, NAV_NEUTRAL, NAV_PROP, PROP_MAIN,
                       page_mode)

# hedge label → the prop entry that fulfils it
EXPECTED = {
    "Overview": "/prop-overview",
    "Plan": "/prop-plan",
    "Goal": "/prop-goal",
    "Position": "/prop-position",
    "Desk": "/prop-desk",
    "Signals": "/prop-signals",
    "Analytics": "/prop-analytics",
    "Journal": "/prop-journal",
    "Edge": "/prop-edge",
}


def test_nav_parity():
    prop = dict((lbl, href) for href, lbl in NAV_PROP)
    hedge = dict((lbl, href) for href, lbl in NAV_HEDGE)

    # 1) every hedge page has a prop counterpart, under the same label
    missing = [lbl for lbl in hedge if lbl not in prop]
    assert not missing, f"hedge pages with no prop twin: {missing}"

    # 2) and it's the one we intend (catches a twin pointing at the wrong page)
    for lbl, href in EXPECTED.items():
        assert lbl in hedge, f"{lbl} vanished from NAV_HEDGE"
        assert prop[lbl] == href, f"{lbl}: prop nav points at {prop[lbl]}, want {href}"

    # 2b) the mirror is exact — same chips, same count. Cone/Engines/Ledger/Income
    #     used to hang off the end of NAV_PROP and made the two bars different
    #     lengths; they're engine cards on /prop-plan now.
    assert [lbl for _, lbl in NAV_PROP] == [lbl for _, lbl in NAV_HEDGE], \
        "the two nav bars must be the same ten chips in the same order"

    # 3) labels appear in the SAME order in both navs, so the layout is learnable
    shared = [lbl for _, lbl in NAV_HEDGE]
    prop_order = [lbl for _, lbl in NAV_PROP if lbl in set(shared)]
    assert prop_order == shared, f"order drift:\n prop  {prop_order}\n hedge {shared}"

    # 4) full separation: no bare path is claimed by both navs. Every prop page has
    #    its own /prop-* URL, so page_mode resolves each one unambiguously.
    bare_p = {h.split("?")[0] for h, _ in NAV_PROP}
    bare_h = {h.split("?")[0] for h, _ in NAV_HEDGE}
    both = bare_p & bare_h
    assert not both, (f"prop and hedge share bare path(s) {both} — every prop page "
                      f"must have its own /prop-* URL, not a ?book= toggle")

    # 5) page_mode: each prop URL is prop, each hedge URL is hedge
    assert page_mode("/prop-position") == "prop"
    assert page_mode("/hedge-position") == "hedge"
    assert page_mode("/prop-journal") == "prop"
    assert page_mode("/hedge-journal") == "hedge"
    assert page_mode("/prop-analytics") == "prop"
    assert page_mode("/prop-edge") == "prop"
    assert page_mode("/prop-desk") == "prop"
    assert page_mode("/hedge-plan") == "hedge"

    # 6) neutral pages are owned by neither nav
    neutral = {h for h, _ in NAV_NEUTRAL}
    assert not (neutral & bare_p), f"neutral page in NAV_PROP: {neutral & bare_p}"
    assert not (neutral & bare_h), f"neutral page in NAV_HEDGE: {neutral & bare_h}"

    # 7) the top-bar chips actually exist in their nav list
    for main, nav, name in ((PROP_MAIN, NAV_PROP, "PROP"), (HEDGE_MAIN, NAV_HEDGE, "HEDGE")):
        hrefs = {h for h, _ in nav}
        assert main <= hrefs, f"{name}_MAIN has chips not in its nav: {main - hrefs}"

    print(f"ok — {len(hedge)} hedge pages all have prop twins, order matches, "
          f"every prop page has its own /prop-* URL")


if __name__ == "__main__":
    test_nav_parity()
