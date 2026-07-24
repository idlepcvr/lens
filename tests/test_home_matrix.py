"""The home dot-matrix is drawn from the real ledger — check it can't lie.

The failure that matters: a curve rendered with the wrong sign color (green for a
loss), or a grid that silently drops columns. Both would put a false claim on the
front door.
"""

import re

import _bootstrap  # noqa: F401  — repo root onto sys.path + cwd
from app.home_page import NARROW, WIDE, _matrix, _runs


def _plain(html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", ln) for ln in html.split("\n")]


def test_grid_is_exactly_the_geometry_asked_for():
    for cols, rows in (WIDE, NARROW):
        lines = _plain(_matrix([0, 100, -50, 200, -300], cols, rows))
        assert len(lines) == rows, (cols, rows, len(lines))
        assert {len(ln) for ln in lines} == {cols}, "ragged grid"


def test_sign_drives_the_color_never_decoration():
    # a curve that only ever wins must not contain a single --short cell
    up = _matrix([10, 200, 900, 1500], *WIDE)
    assert 'class="r' not in up, "green ledger rendered with loss color"
    # ...and the mirror image
    down = _matrix([-10, -200, -900, -1500], *WIDE)
    assert 'class="g' not in down, "losing ledger rendered with win color"


def test_curve_edge_is_the_bright_class():
    # 'gc'/'rc' mark the curve itself; without them the plate has no line, just fog
    html = _matrix([0, 400, 1200, 300, -800], *WIDE)
    assert 'class="gc"' in html and 'class="rc"' in html


def test_runs_preserve_every_character():
    cells = [("a", "g"), ("b", "g"), ("c", "r"), ("d", "g")]
    assert _plain(_runs(cells)) == ["abcd"]
    assert _runs(cells).count("<i") == 3, "adjacent same-class cells not merged"


def test_degenerate_ledgers_do_not_raise():
    assert _matrix([], *WIDE) == ""
    assert _matrix([42.0], *WIDE) == ""
    flat = _plain(_matrix([0.0] * 40, *NARROW))       # span == 0
    assert len(flat) == NARROW[1]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
