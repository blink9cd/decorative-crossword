"""Grouped suite: the renderer shading a hidden word's scattered cells.

`--feature` shades one whole answer, located by its text, and cannot express a
hidden word: those cells are scattered by construction and belong to no single
run. Without this the `shade` subcommand would find cells nothing could draw,
which is half a feature: the useful loop is *find a hidden word, then look at
it*, and it needs the picture.

The extension is deliberately narrow. `RenderRequest.hidden` carries the cells
themselves, already chosen, rather than a second way of naming an answer; the
shading it produces is the same shading `--feature` produces, so the two can be
given together and neither changes what the other draws. Everything here is
about that boundary: the right cells shade, the caption says which word they
spell, and a coordinate the grid does not have is simply not drawn rather than
being an error the renderer has to have an opinion about.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import unittest

import cw_svg
from tests import svg_fixtures as fixtures

#: Two cells of the small fixture that lie in no common run: the top-left C and
#: the E in the bottom row. Shading these is exactly what `--feature` cannot do.
SCATTERED_CELLS = ((0, 0), (2, 1))

#: The word those two cells spell, read in reading order.
SCATTERED_WORD = "CE"


def _shaded(rendered: str, rows: tuple[str, ...]) -> set[tuple[int, int]]:
    """Every (row, col) the render actually shaded.

    Recovered from the emitted cell classes rather than from the request, so a
    test asserting "these cells shade" is reading the picture and not the input
    it was drawn from.
    """
    classes = fixtures.cell_classes(rendered)
    width = len(rows[0])
    return {
        divmod(index, width)
        for index, css_class in enumerate(classes)
        if css_class == cw_svg.FEATURE_TOKEN
    }


class TestHiddenShading(unittest.TestCase):
    """Arbitrary cells shade, and the caption says what they spell."""

    def test_exactly_the_hidden_cells_are_shaded(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.request(
                hidden=cw_svg.HiddenShading(SCATTERED_WORD, SCATTERED_CELLS)
            )
        )
        self.assertEqual(_shaded(rendered, fixtures.SMALL_ROWS), set(SCATTERED_CELLS))

    def test_the_caption_names_the_hidden_word(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.request(
                hidden=cw_svg.HiddenShading(SCATTERED_WORD, SCATTERED_CELLS)
            )
        )
        self.assertIn(
            f"Hidden: {SCATTERED_WORD}", "\n".join(fixtures.caption_lines(rendered))
        )

    def test_no_hidden_word_shades_nothing_and_captions_nothing(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request())
        self.assertEqual(_shaded(rendered, fixtures.SMALL_ROWS), set())
        self.assertNotIn("Hidden:", "\n".join(fixtures.caption_lines(rendered)))

    def test_a_coordinate_outside_the_grid_draws_nothing_and_does_not_raise(
        self,
    ) -> None:
        """The renderer asks the grid which of its cells are shaded.

        So a coordinate the grid does not have simply never matches. Validating
        the source is the CLI's job and this does not repeat
        it: the shape of the check is what makes not repeating it safe.
        """
        rendered = cw_svg.render_svg(
            fixtures.request(hidden=cw_svg.HiddenShading("X", ((99, 99),)))
        )
        self.assertEqual(_shaded(rendered, fixtures.SMALL_ROWS), set())

    def test_a_blocked_cell_stays_blocked(self) -> None:
        """A block has no letter to spell with, so it cannot be shaded.

        The block test already runs first in the cell's own class decision;
        this pins that a hidden word cannot reach past it.
        """
        rendered = cw_svg.render_svg(
            fixtures.request(hidden=cw_svg.HiddenShading("X", ((1, 1),)))
        )
        self.assertEqual(_shaded(rendered, fixtures.SMALL_ROWS), set())
        self.assertEqual(
            fixtures.cell_classes(rendered)[len(fixtures.SMALL_ROWS[0]) + 1],
            cw_svg.BLOCK_CLASS,
        )

    def test_a_feature_and_a_hidden_word_shade_together(self) -> None:
        """Both may be given; neither erases the other.

        The CLI never supplies both, but the renderer is public and a rule
        that silently dropped one would be a surprise waiting for whoever
        first tries it.
        """
        rendered = cw_svg.render_svg(
            fixtures.request(feature="COW", hidden=cw_svg.HiddenShading("T", ((0, 2),)))
        )
        self.assertEqual(
            _shaded(rendered, fixtures.SMALL_ROWS),
            {(0, 0), (1, 0), (2, 0), (0, 2)},
        )

    def test_every_feature_shades_its_own_cells(self) -> None:
        """Several features shade the union of their runs, crossing cell once.

        COW and CAT share the corner, so a shading built by concatenating
        each run's cells rather than taking one set would still pass a
        membership check: the equality below is what pins that the shared
        cell is one cell, and that neither feature's cells were dropped.
        """
        rendered = cw_svg.render_svg(fixtures.request(features=("COW", "CAT")))
        self.assertEqual(
            _shaded(rendered, fixtures.SMALL_ROWS),
            {(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)},
        )

    def test_both_captions_appear_when_both_are_given(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.request(feature="COW", hidden=cw_svg.HiddenShading("T", ((0, 2),)))
        )
        caption = "\n".join(fixtures.caption_lines(rendered))
        self.assertIn("Featured: COW", caption)
        self.assertIn("Hidden: T", caption)

    def test_the_shading_is_byte_stable_for_one_request(self) -> None:
        """The same request renders the same bytes.

        A set of cells is the natural way to ask "is this one shaded", and a
        set is also the classic way an ordering leaks into output, so this
        pins that nothing here iterates one.
        """
        request = fixtures.request(
            hidden=cw_svg.HiddenShading(SCATTERED_WORD, SCATTERED_CELLS)
        )
        self.assertEqual(cw_svg.render_svg(request), cw_svg.render_svg(request))


if __name__ == "__main__":
    unittest.main()
