"""Tests that the render is VISIBLE and in the RIGHT PLACE, not merely present.

Kept apart from `test_svg.py` because the two ask different questions: that file
asks whether the document has the right parts, this one asks whether those parts
landed on the right cell and can actually be seen, and the two questions fail for
different reasons.

The distinction is not academic. A marker counted, shaped correctly and drawn
on the wrong cell reports the wrong grouping -- worse than no marker, because
the picture still looks finished. Any of the render's inks set to the paper
color -- the shading, the marker, or the shared TEXT fill that paints the
letters, the legend labels and the whole caption at once -- leaves the
contract satisfied in the markup and erased on screen. None of it
is visible to a test that counts elements or compares tags.

What the placement tests here do NOT cover, stated so the coverage is not
over-read: they locate one anchor point per marker, not the marker's outline.
A marker whose anchor stays in its own cell while its shape bleeds into the
neighbor passes. That bound is deliberate -- pinning the outline is the golden
sample's job -- and it is why the tests are named for the anchor.
"""

import re
import unittest

import cw_svg
from tests import svg_fixtures as fixtures

#: What a fill has to look like to be a color rather than a keyword the viewer
#: resolves for itself. `fill:none` and `fill:transparent` are both legal CSS
#: and both leave the page unpainted, so "the rule exists" is not the assertion
#: that matters -- "the rule paints something" is.
_COLOR_PATTERN = re.compile(r"^#[0-9a-f]{6}$")


def _expected_marker_shapes() -> dict[tuple[int, int], str]:
    """The marker element each themed cell of the wide grid should carry."""
    order = sorted(fixtures.WIDE_THEMES)
    return {
        cell: cw_svg.marker_element_name(order.index(theme_id))
        for theme_id, cells in fixtures.WIDE_THEME_CELLS.items()
        for cell in cells
    }


class TestMarkerPlacement(unittest.TestCase):
    """A theme's marker sits on the cells that carry that theme, and only those."""

    def test_marker_anchors_land_on_the_cells_that_carry_their_theme(self) -> None:
        # Counting markers, and counting them per shape, both survive a marker
        # drawn on the wrong cell. Locating each one's anchor in the cell boxes
        # the document itself reports is what does not.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        self.assertEqual(
            fixtures.marker_cells(rendered, cw_svg.MARKER_LAYER),
            _expected_marker_shapes(),
        )

    def test_marker_anchors_stay_in_their_cells_at_every_size(self) -> None:
        # The marker inset and size are both fractions of the cell, so the
        # mapping must be identical at any cell size; an inset that behaved
        # differently at one size would move an anchor into another cell.
        #
        # ANCHOR, not outline. A marker can bleed well into its neighbor, or
        # sit on top of the letter, without moving its anchor: the admissible
        # inset band this leaves open is roughly (-0.073, 0.89) against a
        # shipped 0.08. The golden sample is what pins the exact value.
        for cell in (10, 40):
            with self.subTest(cell=cell):
                rendered = cw_svg.render_svg(fixtures.wide_request(cell=cell))
                self.assertEqual(
                    fixtures.marker_cells(rendered, cw_svg.MARKER_LAYER),
                    _expected_marker_shapes(),
                )

    def test_shading_a_cell_does_not_move_its_marker(self) -> None:
        # Every PEAR cell is themed, so shading them exercises the composition
        # the contract requires: the shading is the fill, and the marker
        # still draws over it -- in the same place it drew before.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        self.assertEqual(
            fixtures.marker_cells(rendered, cw_svg.MARKER_LAYER),
            _expected_marker_shapes(),
        )

    def test_no_marker_anchor_lands_on_an_unthemed_cell(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        themed = {
            cell for cells in fixtures.WIDE_THEME_CELLS.values() for cell in cells
        }
        self.assertEqual(
            set(fixtures.marker_cells(rendered, cw_svg.MARKER_LAYER)) - themed, set()
        )


class TestColorVisibility(unittest.TestCase):
    """Every ink the render depends on is distinguishable from what it sits on.

    "Every ink" is a claim, so it is enumerated: the cell fills (plain, block,
    shading, each tint), the marker ink in both layers, the SHARED TEXT FILL
    that paints the letters, the legend labels and the caption together, and
    the stroke that rules the grid. Each is read back out of the stylesheet and
    compared with the surface it is actually drawn on.
    """

    def _values(self, rendered: str, prop: str, *selectors: str) -> list[str]:
        """What `selectors` declare for `prop`, asserting every one declares it.

        Checked here rather than at each call site: a selector that stopped
        declaring the property would otherwise quietly shorten the list, and a
        shorter list passes a distinctness check for free.
        """
        values = fixtures.rule_values(rendered, prop, *selectors)
        self.assertEqual(len(values), len(selectors))
        return values

    def _tint_classes(self) -> tuple[str, ...]:
        """One tint class per theme the wide fixture declares."""
        return tuple(
            cw_svg.theme_class(order) for order in range(len(fixtures.WIDE_THEMES))
        )

    def _cell_surfaces(self, rendered: str) -> list[str]:
        """Every fill a cell that carries a letter, marker or rule can have.

        BLOCK_CLASS is deliberately absent, and shares the ink of the marks
        drawn elsewhere on purpose. For two of the three consumers the reason
        is that the collision cannot occur: a blocked cell is in no run, so it
        carries no theme, no marker and no letter. For the THIRD -- the grid
        rule -- the collision is real and intended. `.cw-block` fill and the
        cell stroke are both `_INK`, so a blocked cell's border merges into
        the cell. That is the crossword look, not a defect, and including
        BLOCK_CLASS here would fail the rule test for drawing it.

        PAGE_CLASS is absent for a different reason: it is not a cell fill at
        all. Every cell in the grid draws its own opaque rect over the page, so
        nothing drawn INSIDE the grid is ever read against it. What IS read
        against it -- the legend and the caption -- has its own test below.
        """
        return self._values(
            rendered,
            "fill",
            cw_svg.PLAIN_CLASS,
            cw_svg.FEATURE_TOKEN,
            *self._tint_classes(),
        )

    def test_every_cell_background_is_a_distinct_color(self) -> None:
        # Plain, blocked, shaded and each tint have to be told apart at a
        # glance; two of them resolving to the same value makes the picture
        # unreadable while every element count stays right.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        fills = self._values(
            rendered,
            "fill",
            cw_svg.PLAIN_CLASS,
            cw_svg.BLOCK_CLASS,
            cw_svg.FEATURE_TOKEN,
            *self._tint_classes(),
        )
        self.assertEqual(len(set(fills)), len(fills))

    def test_the_feature_shading_differs_from_a_plain_cell(self) -> None:
        # Shading set to the paper color deletes the gray square from the
        # picture while it stays in the markup.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        plain, shaded = self._values(
            rendered, "fill", cw_svg.PLAIN_CLASS, cw_svg.FEATURE_TOKEN
        )
        self.assertNotEqual(shaded, plain)

    def test_each_declared_theme_gets_a_tint_of_its_own(self) -> None:
        # A palette index that never advanced would give every theme the same
        # color: distinct classes, a full legend, and a picture in which the
        # themes are nonetheless indistinguishable.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        tints = self._values(rendered, "fill", *self._tint_classes())
        self.assertEqual(len(set(tints)), len(tints))

    def test_marker_ink_differs_from_every_fill_it_can_be_drawn_on(self) -> None:
        # The marker is the channel that has to survive a monochrome print and
        # a color-vision difference. Ink matching a fill it
        # is drawn over erases that channel on some cells and not others --
        # the grouping silently half-reported.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        (ink,) = self._values(rendered, "fill", cw_svg.MARKER_LAYER)
        self.assertNotIn(ink, self._cell_surfaces(rendered))

    def test_legend_marker_ink_matches_the_grid_marker_ink(self) -> None:
        # The legend explains the grid; the two drawn in different inks would
        # read as two different marks.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        grid, legend = self._values(
            rendered, "fill", cw_svg.MARKER_LAYER, cw_svg.LEGEND_MARKER_LAYER
        )
        self.assertEqual(grid, legend)

    def test_legend_marker_ink_differs_from_the_swatch_it_sits_on(self) -> None:
        # A legend row's marker is drawn INSIDE its tint swatch, so the tints
        # are the surfaces that one has to stay legible against.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        (ink,) = self._values(rendered, "fill", cw_svg.LEGEND_MARKER_LAYER)
        self.assertNotIn(ink, self._values(rendered, "fill", *self._tint_classes()))

    def test_letter_ink_differs_from_every_cell_it_can_sit_on(self) -> None:
        # ONE fill paints the letters, and it is shared with the legend labels
        # and the whole caption -- so setting it to the paper color erases
        # more of the picture than the shading and the marker together, with
        # every element count, every tag list and every parsed text node
        # completely intact.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        (ink,) = self._values(rendered, "fill", f"{cw_svg.LETTER_LAYER} text")
        self.assertNotIn(ink, self._cell_surfaces(rendered))

    def test_the_document_paints_its_own_page(self) -> None:
        # The legend and the caption are drawn outside the grid, so the only
        # surface behind them is whatever the document itself paints across the
        # whole canvas. If it paints nothing, that surface is the viewer's --
        # white in a light-mode browser, near-black in a dark one -- and the
        # ink comparison below has nothing to compare against.
        for description, request in (
            ("wide, featured, with settings", fixtures.wide_request(feature="PEAR")),
            ("small, single theme", fixtures.request()),
            ("empty grid", fixtures.request(rows=(), themes={}, entry_themes={})),
        ):
            with self.subTest(document=description):
                rendered = cw_svg.render_svg(request)
                self.assertEqual(
                    fixtures.page_rect(rendered).get("class"), cw_svg.PAGE_CLASS
                )
                self.assertRegex(fixtures.page_fill(rendered), _COLOR_PATTERN)

    def test_legend_and_caption_ink_differ_from_the_page(self) -> None:
        # These two sit outside the grid, on the page the document paints. That
        # color is read back OUT OF THE RENDER -- the rect covering the whole
        # viewBox, and the fill its class declares -- rather than borrowed from
        # the plain cell fill, which is a color the page is under no
        # obligation to share and which the document paints nowhere near them.
        rendered = cw_svg.render_svg(
            fixtures.wide_request(feature="PEAR", settings={"seed": "7"})
        )
        page = fixtures.page_fill(rendered)
        labels, caption = self._values(
            rendered,
            "fill",
            f"{cw_svg.LEGEND_LAYER} text",
            f"{cw_svg.CAPTION_LAYER} text",
        )
        self.assertNotEqual(labels, page)
        self.assertNotEqual(caption, page)

    def test_the_grid_rules_differ_from_the_cells_they_separate(self) -> None:
        # A stroke is an ink too. Ruled in the color of the cells it divides,
        # the grid stops reading as a grid while every rect stays in place.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        (stroke,) = self._values(rendered, "stroke", f"{cw_svg.CELL_LAYER} rect")
        self.assertNotIn(stroke, self._cell_surfaces(rendered))


if __name__ == "__main__":
    unittest.main()
