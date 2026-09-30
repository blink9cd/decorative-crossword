"""Grouped suite: drawing the letters `fill --source` fixed, in bold.

A fill that starts from a source grows around letters the operator already
had, and the render says which those were. The mark is the letter's WEIGHT and
nothing else, because each other channel a cell has is already spoken for:
its background is the block, the feature shading or the theme tint, and its
bottom-right corner holds the theme marker. Weight also survives a monochrome
print, which a color could not.

Every case reads the render back as a document -- which layer holds a letter,
what the stylesheet declares for it -- rather than matching a template, as the
page test in `test_svg_visibility.py` also does.

`TestNoRegression` guards the other side: a render with nothing fixed carries no
fixed-letter layer or rule, which is what keeps every committed sample drawn
without `--source` unchurned.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import unittest

import cw_grid
import cw_svg
import cw_svg_plan
import cw_svg_style
from tests import svg_fixtures

#: PLUMS across the top of the wide fixture, and the E crossing nothing at
#: (2, 2): a whole entry and a single letter, so the mark is shown to follow
#: cells rather than entries.
FIXED = ((0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (2, 2))

#: A blocked cell and a cell outside the grid: coordinates that name no letter.
NO_LETTER = ((1, 1), (9, 9))

#: What the caption says, for a count of fixed letters drawn.
CAPTION = "Fixed from --source: {} letter(s), in bold"


def _render(
    *,
    fixed: tuple[tuple[int, int], ...] = (),
    feature: str | None = None,
    settings: dict[str, str] | None = None,
    hidden: cw_svg_plan.HiddenShading | None = None,
) -> str:
    """The wide multi-theme fixture rendered with the given overrides."""
    return cw_svg.render_svg(
        svg_fixtures.wide_request(
            fixed=fixed, feature=feature, settings=settings, hidden=hidden
        )
    )


def _every_letter() -> dict[tuple[int, int], str]:
    """Every lettered cell of the wide fixture, read off its rows."""
    return {
        (row, col): char
        for row, line in enumerate(svg_fixtures.WIDE_ROWS)
        for col, char in enumerate(line)
        if char != cw_grid.BLOCK
    }


class TestNoRegression(unittest.TestCase):
    """A render with no fixed letter to draw carries no trace of the mark."""

    def test_the_layer_is_absent_without_fixed_cells(self) -> None:
        self.assertNotIn(cw_svg_style.FIXED_LETTER_LAYER, _render())

    def test_an_empty_fixed_tuple_renders_the_same_bytes(self) -> None:
        self.assertEqual(
            _render(fixed=()), cw_svg.render_svg(svg_fixtures.wide_request())
        )

    def test_coordinates_naming_no_letter_change_nothing(self) -> None:
        # A block cannot be bold and a cell off the grid is not drawn, so the
        # request carries nothing to mark -- and a layer, a stylesheet rule or
        # a caption line that nothing on the picture answers to would be a lie.
        self.assertEqual(_render(fixed=NO_LETTER), _render())


class TestTheMark(unittest.TestCase):
    """Fixed letters are drawn in their own layer; filled-in letters are not."""

    def test_every_fixed_letter_is_drawn_in_the_fixed_layer(self) -> None:
        drawn = svg_fixtures.letter_cells(
            _render(fixed=FIXED), cw_svg_style.FIXED_LETTER_LAYER
        )
        expected = {cell: _every_letter()[cell] for cell in FIXED}
        self.assertEqual(drawn, expected)

    def test_a_filled_in_letter_is_not_marked(self) -> None:
        plain = svg_fixtures.letter_cells(_render(fixed=FIXED), cw_svg.LETTER_LAYER)
        expected = {
            cell: char for cell, char in _every_letter().items() if cell not in FIXED
        }
        self.assertEqual(plain, expected)

    def test_every_letter_is_drawn_exactly_once(self) -> None:
        # The two layers split the letters rather than copying any: a letter
        # drawn twice, bold over regular, would smear at the edges of its glyph.
        rendered = _render(fixed=FIXED)
        counted = len(
            svg_fixtures.children(rendered, cw_svg.LETTER_LAYER, "text")
        ) + len(
            svg_fixtures.children(rendered, cw_svg_style.FIXED_LETTER_LAYER, "text")
        )
        self.assertEqual(counted, len(_every_letter()))

    def test_the_fixed_letters_are_bold(self) -> None:
        values = svg_fixtures.rule_values(
            _render(fixed=FIXED),
            "font-weight",
            f"{cw_svg_style.FIXED_LETTER_LAYER} text",
        )
        self.assertEqual(values, ["bold"])

    def test_a_filled_in_letter_declares_no_weight(self) -> None:
        values = svg_fixtures.rule_values(
            _render(fixed=FIXED), "font-weight", f"{cw_svg.LETTER_LAYER} text"
        )
        self.assertEqual(values, [])


class TestDistinctFromShadingAndThemes(unittest.TestCase):
    """The mark adds a weight, and takes nothing from any other reading."""

    def test_cell_backgrounds_are_unchanged_by_the_mark(self) -> None:
        # PLUMS is both featured (shaded) and themed here, so this covers the
        # shading and the tint in one comparison.
        self.assertEqual(
            svg_fixtures.cell_classes(_render(feature="PLUMS", fixed=FIXED)),
            svg_fixtures.cell_classes(_render(feature="PLUMS")),
        )

    def test_theme_markers_are_unchanged_by_the_mark(self) -> None:
        self.assertEqual(
            svg_fixtures.marker_cells(_render(fixed=FIXED), cw_svg.MARKER_LAYER),
            svg_fixtures.marker_cells(_render(), cw_svg.MARKER_LAYER),
        )

    def test_weight_is_the_only_difference_from_a_filled_in_letter(self) -> None:
        # Same ink and same size as every other letter: a mark that changed
        # the color would fail a monochrome print, and one that changed the
        # size would read as a different kind of cell rather than a given one.
        rendered = _render(fixed=FIXED)
        for prop in ("fill", "font-size", "font-family", "text-anchor"):
            with self.subTest(prop=prop):
                self.assertEqual(
                    svg_fixtures.rule_values(
                        rendered, prop, f"{cw_svg_style.FIXED_LETTER_LAYER} text"
                    ),
                    svg_fixtures.rule_values(
                        rendered, prop, f"{cw_svg.LETTER_LAYER} text"
                    ),
                )


class TestCaption(unittest.TestCase):
    """The caption says what bold means, and counts what it marks."""

    def test_the_caption_counts_the_fixed_letters_drawn(self) -> None:
        # NO_LETTER rides along to show the count is of letters DRAWN, so the
        # caption cannot disagree with the picture it sits under.
        lines = svg_fixtures.caption_lines(_render(fixed=FIXED + NO_LETTER))
        self.assertIn(CAPTION.format(len(FIXED)), lines)

    def test_no_fixed_line_without_a_fixed_letter(self) -> None:
        lines = svg_fixtures.caption_lines(_render(fixed=NO_LETTER))
        self.assertEqual([line for line in lines if line.startswith("Fixed")], [])

    def test_the_fixed_line_sits_after_the_hidden_word_and_before_the_settings(
        self,
    ) -> None:
        lines = svg_fixtures.caption_lines(
            _render(
                fixed=FIXED,
                hidden=cw_svg_plan.HiddenShading("PA", ((0, 0), (2, 0))),
                settings={"seed": "3"},
            )
        )
        self.assertEqual(
            lines[-3:], ["Hidden: PA", CAPTION.format(len(FIXED)), "seed: 3"]
        )


class TestSelfContained(unittest.TestCase):
    """The mark fetches nothing and keeps the document well formed."""

    def test_the_namespace_is_the_only_url_in_the_document(self) -> None:
        rendered = _render(fixed=FIXED)
        svg_fixtures.parse(rendered)
        self.assertEqual(rendered.count("http"), 1)
        for fetch in ("href", "url(", "@import", "@font-face"):
            with self.subTest(fetch=fetch):
                self.assertNotIn(fetch, rendered)

    def test_two_renders_agree(self) -> None:
        self.assertEqual(_render(fixed=FIXED), _render(fixed=FIXED))


if __name__ == "__main__":
    unittest.main()
