"""`--empty-blocks`: a blocked cell paints nothing, so the grid reads as a shape.

The mechanism is one CSS rule and no new geometry. Every cell still emits its
own rect; the open block's rule cancels the fill and the stroke the shared
`.cw-cells rect` rule would otherwise give it. So the outline a reader sees is
drawn entirely by the LETTERED cells around the hole, which is why the tests
below assert on that boundary as well as on the block itself.

Driven at two levels on purpose. The renderer tests pin what the document
says. The CLI tests pin that all four producers can say it: the flag is
registered once for four subparsers, and a wiring slip there would leave some
of them silently unable to reach a renderer that works perfectly.
"""

import re
import tempfile
import unittest
from pathlib import Path

import cw_svg
import cw_svg_style
import decorative_crossword
from tests import cli_fixtures, samples_fixtures, svg_fixtures

#: The grid the three read-side producers run against, and the word `shade`
#: places in it -- the same pair `tests/test_samples_read.py` drives, so this
#: suite exercises the flag on a real committed grid rather than a fixture.
_READ_SOURCE = samples_fixtures.SAMPLES / "large_square"
_HIDDEN_WORD = "LANTERN"


def _declaration(rendered: str, selector: str, prop: str) -> str:
    """The value `selector` gives `prop`, read back out of the stylesheet.

    Read from the rendered document rather than compared against a literal
    color: the palette is private to `cw_svg_style`, and a test that restated
    one of its values would pass after the palette changed underneath it.
    """
    sheet = svg_fixtures.stylesheet(rendered)
    body = re.search(rf"{re.escape(selector)}\{{([^}}]*)\}}", sheet)
    assert body is not None, f"no rule for {selector!r} in {sheet!r}"
    found = re.search(rf"(?:^|;){re.escape(prop)}:([^;]*)", body.group(1))
    assert found is not None, f"{selector!r} declares no {prop!r}"
    return found.group(1)


class TestEmptyBlockRender(unittest.TestCase):
    """What an `--empty-blocks` document says about its blocked cells."""

    def setUp(self) -> None:
        """One render with the flag, and the same request without it."""
        self.empty = cw_svg.render_svg(svg_fixtures.request(empty_blocks=True))
        self.filled = cw_svg.render_svg(svg_fixtures.request())

    def test_no_cell_carries_the_filled_block_class(self) -> None:
        self.assertNotIn(cw_svg.BLOCK_CLASS, svg_fixtures.cell_classes(self.empty))

    def test_a_blocked_cell_carries_the_empty_block_class(self) -> None:
        # SMALL_ROWS blocks exactly two cells, so the count is asserted rather
        # than mere presence: a rule applied to every cell would also satisfy
        # a membership check while erasing the whole grid.
        classes = svg_fixtures.cell_classes(self.empty)
        self.assertEqual(classes.count(cw_svg.EMPTY_BLOCK_CLASS), 2)

    def test_every_cell_still_draws_one_rect(self) -> None:
        # The change is a paint, not a geometry: the same rects are emitted in
        # the same order, and only what they paint differs.
        self.assertEqual(
            len(svg_fixtures.cell_classes(self.empty)),
            len(svg_fixtures.cell_classes(self.filled)),
        )

    def test_the_rule_cancels_both_the_fill_and_the_stroke(self) -> None:
        # Both halves matter. Without `fill:none` the cell paints over the
        # page; without `stroke:none` the shared cell rule still rules its
        # border, and a bordered white square is not an absent one.
        selector = f".{cw_svg.CELL_LAYER} rect.{cw_svg.EMPTY_BLOCK_CLASS}"
        self.assertEqual(_declaration(self.empty, selector, "fill"), "none")
        self.assertEqual(_declaration(self.empty, selector, "stroke"), "none")

    def test_the_rule_outranks_the_shared_cell_stroke(self) -> None:
        """A bare class selector would lose to `.cw-cells rect`, silently."""
        sheet = svg_fixtures.stylesheet(self.empty)
        self.assertIn(f".{cw_svg.CELL_LAYER} rect.{cw_svg.EMPTY_BLOCK_CLASS}{{", sheet)

    def test_no_filled_block_fill_is_declared(self) -> None:
        """The document declares the paint it uses, and not the other one."""
        self.assertNotIn(
            f".{cw_svg.BLOCK_CLASS}{{", svg_fixtures.stylesheet(self.empty)
        )

    def test_a_lettered_cell_keeps_the_stroke_that_draws_the_outline(self) -> None:
        # The silhouette is not drawn by this feature at all: it is the edge
        # the surviving cells already stroke. If that stroke went with the
        # block's, the grid would lose its rules and read as loose letters.
        self.assertEqual(
            _declaration(self.empty, f".{cw_svg.CELL_LAYER} rect", "stroke"),
            _declaration(self.filled, f".{cw_svg.CELL_LAYER} rect", "stroke"),
        )

    def test_the_document_is_still_well_formed(self) -> None:
        svg_fixtures.parse(self.empty)

    def test_the_rule_needs_no_function_the_stylesheet_forbids(self) -> None:
        """SVG IS THE PRODUCT, and `tests/test_svg_containment.py` owns the rest.

        That suite renders this flag too, so the document answers to every
        containment rule there rather than to a weaker copy here. What is
        asserted here is only the part this rule could have got wrong on its
        own: `fill:none` is a keyword, and reaching for `url(...)` instead
        would have been a fetch the other suite forbids outright.
        """
        selector = f".{cw_svg.CELL_LAYER} rect.{cw_svg.EMPTY_BLOCK_CLASS}"
        self.assertNotIn("(", _declaration(self.empty, selector, "fill"))


class TestTheFlagOffChangesNothing(unittest.TestCase):
    """Every document made without the flag carries no trace of it."""

    def test_the_render_is_byte_identical_to_the_default(self) -> None:
        self.assertEqual(
            cw_svg.render_svg(svg_fixtures.request(empty_blocks=False)),
            cw_svg.render_svg(svg_fixtures.request()),
        )

    def test_the_empty_block_class_appears_nowhere(self) -> None:
        # Its rule replaces the block rule only for a render that uses it, so a
        # render without the flag carries no trace of it.
        self.assertNotIn(
            cw_svg.EMPTY_BLOCK_CLASS, cw_svg.render_svg(svg_fixtures.request())
        )


class TestTheOtherLayersSurvive(unittest.TestCase):
    """The caption, legend and bold source letters are untouched by the flag."""

    def setUp(self) -> None:
        """A render carrying every other layer at once, with and without.

        Spelled out twice rather than splatted from a shared dict: a `**kwargs`
        of mixed value types needs a `type: ignore` to pass mypy, and a
        suppression is a worse price than one repeated line.
        """
        self.empty = cw_svg.render_svg(
            svg_fixtures.request(
                feature="COW",
                settings={"seed": "7"},
                fixed=((0, 0), (0, 1)),
                empty_blocks=True,
            )
        )
        self.filled = cw_svg.render_svg(
            svg_fixtures.request(
                feature="COW", settings={"seed": "7"}, fixed=((0, 0), (0, 1))
            )
        )

    def test_the_caption_says_the_same_thing(self) -> None:
        self.assertEqual(
            svg_fixtures.caption_lines(self.empty),
            svg_fixtures.caption_lines(self.filled),
        )

    def test_the_legend_says_the_same_thing(self) -> None:
        self.assertEqual(
            svg_fixtures.legend_labels(self.empty),
            svg_fixtures.legend_labels(self.filled),
        )

    def test_the_bold_source_letters_are_still_drawn(self) -> None:
        self.assertEqual(
            len(
                svg_fixtures.children(
                    self.empty, cw_svg_style.FIXED_LETTER_LAYER, "text"
                )
            ),
            len(
                svg_fixtures.children(
                    self.filled, cw_svg_style.FIXED_LETTER_LAYER, "text"
                )
            ),
        )

    def test_nothing_is_drawn_on_a_black_square(self) -> None:
        """No layer may sit on a block, because no block is painted."""
        self.assertNotIn(cw_svg.BLOCK_CLASS, svg_fixtures.cell_classes(self.empty))


class TestTheGapRingStaysVisible(unittest.TestCase):
    """`gaps --out` rings are painted against whatever the block now is."""

    def setUp(self) -> None:
        """The same two marked gaps, drawn over a block and over a hole."""
        self.marks = ((1, 1), (1, 2))
        self.empty = cw_svg.render_svg(
            svg_fixtures.request(gaps=self.marks, empty_blocks=True)
        )
        self.filled = cw_svg.render_svg(svg_fixtures.request(gaps=self.marks))

    def test_the_ring_is_inked_when_the_block_is_a_hole(self) -> None:
        # Left in the page color it would be white on white and vanish, which
        # is the one way this feature could silently break another one.
        self.assertEqual(
            _declaration(self.empty, f".{cw_svg_style.GAP_LAYER}", "stroke"),
            _declaration(self.empty, f".{cw_svg.CELL_LAYER} rect", "stroke"),
        )

    def test_the_ring_stays_the_page_color_over_a_filled_block(self) -> None:
        self.assertEqual(
            _declaration(self.filled, f".{cw_svg_style.GAP_LAYER}", "stroke"),
            _declaration(self.filled, f".{cw_svg.PAGE_CLASS}", "fill"),
        )

    def test_the_two_rings_are_told_apart_from_each_other(self) -> None:
        """The recolor is a real difference, not the same value twice."""
        self.assertNotEqual(
            _declaration(self.empty, f".{cw_svg_style.GAP_LAYER}", "stroke"),
            _declaration(self.filled, f".{cw_svg_style.GAP_LAYER}", "stroke"),
        )


class TestEveryProducerTakesTheFlag(cli_fixtures.QuietCase):
    """All four renderers reach the flag, and none of them does without it."""

    def _blocks_in(self, argv: list[str], out: Path) -> bool:
        """Run `argv`, assert exit 0, and say whether `out` paints a block."""
        self.assertEqual(decorative_crossword.main(argv), 0)
        return cw_svg.BLOCK_CLASS in svg_fixtures.cell_classes(
            out.read_text(encoding="utf-8")
        )

    def _read_argv(self, command: str, out: Path, *extra: str) -> list[str]:
        """One read-side command against the committed `large_square` grid."""
        return [
            command,
            "--source",
            str(_READ_SOURCE / "grid_source.json"),
            *extra,
            "--out",
            str(out),
        ]

    def test_fill_preview_draws_no_block_under_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            workspace = cli_fixtures.Workspace(folder)
            argv = workspace.fill("--preview", str(workspace.svg), "--empty-blocks")
            self.assertFalse(self._blocks_in(argv, workspace.svg))

    def test_preview_draws_no_block_under_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "preview.svg"
            argv = self._read_argv("preview", out, "--empty-blocks")
            self.assertFalse(self._blocks_in(argv, out))

    def test_shade_draws_no_block_under_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "hidden.svg"
            argv = self._read_argv(
                "shade", out, "--word", _HIDDEN_WORD, "--empty-blocks"
            )
            self.assertFalse(self._blocks_in(argv, out))

    def test_gaps_draws_no_block_under_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "gaps.svg"
            argv = self._read_argv(
                "gaps",
                out,
                "--bank",
                str(_READ_SOURCE / "bank.json"),
                "--empty-blocks",
            )
            self.assertFalse(self._blocks_in(argv, out))

    def test_preview_still_draws_a_block_without_the_flag(self) -> None:
        """The control: the flag is what changes the picture, not the fixture."""
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "preview.svg"
            self.assertTrue(self._blocks_in(self._read_argv("preview", out), out))


if __name__ == "__main__":  # pragma: no cover - the suite runs under the aggregator
    unittest.main()
