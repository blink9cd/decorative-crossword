"""Grouped suite: drawing the gaps `gaps --out` listed, on top of the blocks.

`shade --out` could reuse the existing shading because it marks lettered cells.
This cannot: `cw_svg._cell_class` returns `BLOCK_CLASS` before it ever consults
`shaded_cells`, deliberately: shading is the cell fill,
and a block's fill is the block. So a blocked cell handed to the shading path
draws as an ordinary block and the operator sees nothing at all.

The mark therefore lives in a layer of its own, drawn over the block's ink in
the paper color, and `TestVisible` is the case that matters: it asserts the
stylesheet actually paints the layer in something that shows against ink,
because a mark present in the markup and invisible on the page is the exact
failure this suite exists to prevent.

`TestNoRegression` guards the other side. Every other render (`fill`,
`preview`, `shade`) carries no gaps, so it must carry no gap layer or rule,
which is what keeps `tests/test_samples.py` and `tests/test_samples_read.py`
passing without the committed SVGs being churned for no reader's benefit.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import re
import unittest

import cw_svg
import cw_svg_style
from tests import svg_fixtures

#: A grid with blocked cells in known places, so a mark's position can be
#: checked against the cell it is supposed to sit in.
ROWS = ("AB.", "..C", "DE.")

#: Two gaps in one row, one column apart: the pair whose x difference must be
#: exactly one cell edge.
SAME_ROW_GAPS = ((1, 0), (1, 1))


def _render(**overrides: object) -> str:
    """Render the fixture request over ROWS, with fields overridden."""
    return cw_svg.render_svg(
        svg_fixtures.request(rows=ROWS, themes={}, entry_themes={}, **overrides)  # type: ignore[arg-type]
    )


def _layer(drawn: str) -> str:
    """The gap layer's own markup, or "" when the document carries none."""
    opening = f'<g class="{cw_svg_style.GAP_LAYER}">'
    if opening not in drawn:
        return ""
    return drawn.split(opening, 1)[1].split("</g>", 1)[0]


def _declarations(drawn: str, css_class: str) -> str:
    """The declaration block the stylesheet gives one class."""
    return drawn.split(f".{css_class}{{", 1)[1].split("}", 1)[0]


def _centers(drawn: str) -> list[tuple[float, float]]:
    """Every gap mark's center, in the order the layer draws them."""
    return [
        (float(x), float(y))
        for x, y in re.findall(r'cx="([\d.]+)" cy="([\d.]+)"', _layer(drawn))
    ]


class TestNoRegression(unittest.TestCase):
    """A render with no gaps carries no gap layer or rule."""

    def test_the_layer_is_absent_when_there_are_no_gaps(self) -> None:
        # Absent rather than emitted empty, a departure from
        # `cw_svg_style.group`'s usual rule: only `gaps --out` ever has a gap
        # to draw, and an empty group in every other render would churn their
        # committed samples for nothing.
        self.assertNotIn(cw_svg_style.GAP_LAYER, _render())

    def test_an_empty_gap_tuple_renders_the_same_bytes(self) -> None:
        self.assertEqual(_render(), _render(gaps=()))


class TestTheMarks(unittest.TestCase):
    """One mark per gap, on the cell it names."""

    def test_one_mark_per_gap_cell(self) -> None:
        self.assertEqual(len(_centers(_render(gaps=SAME_ROW_GAPS))), 2)

    def test_a_column_step_moves_the_mark_one_cell_right(self) -> None:
        # Asserted as a difference so the test does not restate the geometry
        # arithmetic it is checking: a second copy of that sum would pass
        # against a renderer that had drifted with it.
        first, second = _centers(_render(gaps=SAME_ROW_GAPS))
        self.assertAlmostEqual(second[0] - first[0], svg_fixtures.DEFAULT_CELL)

    def test_a_column_step_does_not_move_the_mark_vertically(self) -> None:
        first, second = _centers(_render(gaps=SAME_ROW_GAPS))
        self.assertAlmostEqual(second[1], first[1])

    def test_a_row_step_moves_the_mark_one_cell_down(self) -> None:
        first, second = _centers(_render(gaps=((0, 2), (1, 0))))
        self.assertAlmostEqual(second[1] - first[1], svg_fixtures.DEFAULT_CELL)

    def test_the_marks_keep_the_order_they_were_given(self) -> None:
        # Deterministic output: the caller hands over a
        # ranked tuple, and the layer must not sort or set-ify it.
        forward = _centers(_render(gaps=((1, 0), (1, 1))))
        backward = _centers(_render(gaps=((1, 1), (1, 0))))
        self.assertEqual(forward, list(reversed(backward)))


class TestVisible(unittest.TestCase):
    """A mark that is present in the markup but invisible on the page is a bug."""

    def test_the_layer_is_painted_in_the_page_color(self) -> None:
        # The block underneath is ink, so a mark inheriting the marker layer's
        # own ink would be a black ring on a black square. The page's own rule
        # supplies the expected color, so this asserts a relation between two
        # rules of the one document rather than restating a hex literal that
        # would then be free to drift from the stylesheet.
        drawn = _render(gaps=SAME_ROW_GAPS)
        page = _declarations(drawn, cw_svg_style.PAGE_CLASS).removeprefix("fill:")
        self.assertIn(page, _declarations(drawn, cw_svg_style.GAP_LAYER))

    def test_the_mark_is_a_shape_and_not_a_color_alone(self) -> None:
        # The non-color rule: the grouping has to survive a
        # monochrome print, so the mark is an outline rather than a tint.
        declarations = _declarations(
            _render(gaps=SAME_ROW_GAPS), cw_svg_style.GAP_LAYER
        )
        self.assertIn("fill:none", declarations)
        self.assertIn("stroke", declarations)

    def test_the_block_is_still_drawn_under_the_mark(self) -> None:
        # Additive, not a replacement: the cell keeps reading as a block, which
        # is what makes the mark read as "this block could take a letter".
        plain = _render().count(cw_svg_style.BLOCK_CLASS)
        marked = _render(gaps=SAME_ROW_GAPS).count(cw_svg_style.BLOCK_CLASS)
        self.assertEqual(marked, plain)


class TestStable(unittest.TestCase):
    """Two renders of one request agree byte for byte."""

    def test_two_renders_agree(self) -> None:
        self.assertEqual(_render(gaps=SAME_ROW_GAPS), _render(gaps=SAME_ROW_GAPS))

    def test_the_document_stays_self_contained(self) -> None:
        self.assertNotIn("http://www.w3.org/1999/xlink", _render(gaps=SAME_ROW_GAPS))


if __name__ == "__main__":
    unittest.main()
