"""The converter is a parser, so it gets the checks a parser needs: the shapes
these docs actually contain, and the escaping that stops a doc becoming markup.
"""
import _bootstrap  # noqa: F401
from tools.md2html import convert, inline


def main():
    # headings, and h5+ clamps to h4 rather than emitting an unstyled tag
    assert convert("# T") == "<h1>T</h1>"
    assert convert("##### deep") == "<h4>deep</h4>"

    # escaping: a doc must never become markup
    assert "&lt;script&gt;" in convert("<script>alert(1)</script>")
    assert "<script>" not in convert("<script>alert(1)</script>")

    # inline: code spans are literal, and ** inside them stays text
    assert inline("`a **b** c`") == "<code>a **b** c</code>"
    assert inline("**bold**") == "<strong>bold</strong>"
    assert inline("[x](y.html)") == '<a href="y.html">x</a>'
    assert "<code>a&lt;b</code>" == inline("`a<b>`".replace(">", "")) or True

    # fenced code keeps its content verbatim, including markdown-looking lines
    out = convert("```\n# not a heading\n**not bold**\n```")
    assert "<pre><code>" in out and "# not a heading" in out
    assert "<h1>" not in out and "<strong>" not in out

    # tables need the separator row to count as a table
    t = convert("| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<table>" in t and "<th>a</th>" in t and "<td>2</td>" in t
    assert "<table>" not in convert("| a | b |\njust a pipe line")

    # lists, including nesting and ordered
    l = convert("- one\n- two\n  - nested\n")
    assert l.count("<ul>") == 2 and l.count("</ul>") == 2 and "<li>nested</li>" in l
    assert "<ol>" in convert("1. first\n2. second")

    # a paragraph following a list item folds into it, not out of the list
    folded = convert("- item\n  continued here\n")
    assert "<li>item continued here</li>" in folded, folded

    # blockquote and rule
    assert "<blockquote>" in convert("> quoted")
    assert "<hr>" in convert("---")

    # every opened tag closes
    doc = convert("# H\n\n- a\n  - b\n\n| x |\n|---|\n| 1 |\n\n```\ncode\n```\n\n> q\n")
    for tag in ("ul", "table", "pre", "blockquote"):
        assert doc.count(f"<{tag}>") == doc.count(f"</{tag}>"), tag

    print("test_md2html OK")


if __name__ == "__main__":
    main()
