"""scope_css is what lets two merged pages keep their own .conf without one
restyling the other — so it gets the one test the merge relies on."""

import pytest

from app.theme import merged, scope_css


def test_merged_rejects_a_section_id_already_used_inside_a_body():
    """The cone shipped broken for one build: section id="cone" won
    getElementById over the cone's own <canvas id="cone">, so drawCone() got a
    <section> and threw on .getContext. Loud failure beats a blank panel."""
    with pytest.raises(ValueError, match="cone"):
        merged("/x", "X", [{"id": "cone", "label": "Cone",
                            "body": '<canvas id="cone"></canvas>'}])


def test_merged_allows_distinct_ids():
    out = merged("/x", "X", [{"id": "projection", "label": "Cone",
                              "body": '<canvas id="cone"></canvas>'}])
    assert 'id="projection"' in out and 'href="#projection"' in out


def test_plain_rules_and_selector_lists():
    out = scope_css(".conf{color:red}.a,.b{margin:0}", "#s")
    assert out == "#s .conf{color:red}#s .a,#s .b{margin:0}"


def test_media_block_scopes_inner_rules_not_the_query():
    out = scope_css("@media(max-width:720px){.conf{grid-template-columns:1fr}}", "#s")
    assert out == "@media(max-width:720px){#s .conf{grid-template-columns:1fr}}"


def test_root_and_body_map_to_the_scope_itself():
    # A section must not be able to restyle the document it was merged into.
    assert scope_css(":root{--x:1}", "#s") == "#s{--x:1}"
    assert scope_css("body{padding:32px}", "#s") == "#s{padding:32px}"


def test_keyframes_are_left_alone():
    css = "@keyframes spin{from{transform:rotate(0)}to{transform:rotate(1turn)}}"
    assert scope_css(css, "#s") == css


def test_style_tags_and_comments_are_stripped():
    assert scope_css("<style>/* hi */.a{color:red}</style>", "#s") == "#s .a{color:red}"


def test_two_pages_that_collide_stay_separate():
    a = scope_css(".conf{grid-template-columns:repeat(3,1fr)}", "#geometry")
    b = scope_css(".conf{grid-template-columns:1fr}", "#target")
    assert "#geometry .conf" in a and "#target .conf" in b
    assert "#target" not in a
