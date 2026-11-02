"""Tests for cw_svg: a well-formed, self-contained, stable render.

Every assertion about structure goes through a real XML parse. The failure this
subject exists to prevent (an unescaped `&` producing a document that renders
as a blank page with no error) satisfies "the file was written" and every
substring check, and is caught only by parsing.
"""

import unittest

import cw_grid
import cw_svg
from tests import svg_fixtures as fixtures


def _cell_position(index: int, cols: int) -> tuple[int, int]:
    """The (row, col) of the `index`-th background rect in emitted order."""
    return divmod(index, cols)


class TestDocumentShape(unittest.TestCase):
    """The render parses, roots as SVG, and repeats itself byte for byte.

    It does not ask whether the document reaches outside itself: every fetch
    assertion lives in `test_svg_containment.py`, beside the whitelists that
    make that question answerable.
    """

    def test_output_parses_as_xml(self) -> None:
        fixtures.parse(cw_svg.render_svg(fixtures.request()))

    def test_a_wide_multi_theme_render_parses_too(self) -> None:
        # The square single-theme fixture is the shape that hides bugs; the
        # document has to survive the awkward one as well.
        fixtures.parse(cw_svg.render_svg(fixtures.wide_request(feature="PEAR")))

    def test_is_an_svg_root(self) -> None:
        root = fixtures.parse(cw_svg.render_svg(fixtures.request()))
        self.assertTrue(root.tag.endswith("svg"))

    def test_declares_the_svg_namespace(self) -> None:
        # A document without the SVG namespace parses as XML and renders as
        # nothing at all, the same blank page an escaping bug produces, so it
        # needs its own pin rather than riding on the parse test.
        root = fixtures.parse(cw_svg.render_svg(fixtures.request()))
        self.assertEqual(root.tag, f"{{{cw_svg.SVG_NAMESPACE}}}svg")

    def test_emits_no_width_or_height_attribute(self) -> None:
        # viewBox alone scales to whatever opens it; a fixed width pins the
        # render to one display size.
        root = fixtures.parse(cw_svg.render_svg(fixtures.request()))
        self.assertIsNone(root.get("width"))
        self.assertIsNone(root.get("height"))

    def test_is_byte_identical_across_calls(self) -> None:
        self.assertEqual(
            cw_svg.render_svg(fixtures.request()), cw_svg.render_svg(fixtures.request())
        )

    def test_a_wide_render_is_byte_identical_across_calls(self) -> None:
        first = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        second = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        self.assertEqual(first, second)

    def test_theme_order_does_not_depend_on_mapping_insertion_order(self) -> None:
        # The ordering is fixed. A caller that built the same
        # themes in a different order must still get the same bytes.
        forward = cw_svg.render_svg(fixtures.wide_request())
        reversed_themes = dict(reversed(list(fixtures.WIDE_THEMES.items())))
        backward = cw_svg.render_svg(fixtures.wide_request(themes=reversed_themes))
        self.assertEqual(forward, backward)


class TestGridDrawing(unittest.TestCase):
    """One rect per cell, one letter per filled cell, in row-major order."""

    def test_draws_every_letter(self) -> None:
        text = cw_svg.render_svg(fixtures.request())
        for letter in "CATOWET":
            self.assertIn(f">{letter}<", text)

    def test_draws_one_background_rect_per_cell(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        expected = len(fixtures.WIDE_ROWS) * len(fixtures.WIDE_ROWS[0])
        self.assertEqual(len(fixtures.cell_classes(rendered)), expected)

    def test_blocked_cells_carry_the_block_class_in_row_major_order(self) -> None:
        # Pins both the block class and the emission order every other
        # index-to-cell assertion in this suite relies on.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        cols = len(fixtures.WIDE_ROWS[0])
        drawn = {
            _cell_position(index, cols)
            for index, name in enumerate(fixtures.cell_classes(rendered))
            if name == cw_svg.BLOCK_CLASS
        }
        expected = {
            (row_index, col_index)
            for row_index, row in enumerate(fixtures.WIDE_ROWS)
            for col_index, char in enumerate(row)
            if char == cw_grid.BLOCK
        }
        self.assertEqual(drawn, expected)

    def test_an_unthemed_filled_cell_is_plain(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request(themes={}, entry_themes={}))
        classes = set(fixtures.cell_classes(rendered))
        self.assertEqual(classes, {cw_svg.PLAIN_CLASS, cw_svg.BLOCK_CLASS})

    def test_draws_a_letter_for_every_filled_cell_and_no_others(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        blocked = sum(row.count(cw_grid.BLOCK) for row in fixtures.WIDE_ROWS)
        total = len(fixtures.WIDE_ROWS) * len(fixtures.WIDE_ROWS[0])
        drawn = fixtures.children(rendered, cw_svg.LETTER_LAYER, "text")
        self.assertEqual(len(drawn), total - blocked)

    def test_letters_land_at_their_own_cells(self) -> None:
        # Reading the drawn letters back in geometric order reconstructs the
        # grid. On a non-square grid this fails loudly if rows and columns are
        # transposed anywhere in the geometry: on a square one it would not.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        drawn = fixtures.children(rendered, cw_svg.LETTER_LAYER, "text")
        in_reading_order = sorted(
            drawn,
            key=lambda node: (float(str(node.get("y"))), float(str(node.get("x")))),
        )
        self.assertEqual(
            "".join(str(node.text) for node in in_reading_order),
            "".join(fixtures.WIDE_ROWS).replace(cw_grid.BLOCK, ""),
        )

    def test_a_letter_that_is_xml_special_is_escaped(self) -> None:
        # Cell content is validated upstream, not here; escaping it anyway costs
        # nothing and keeps one unvalidated caller from producing a blank page.
        rendered = cw_svg.render_svg(fixtures.request(rows=("&<", "..")))
        fixtures.parse(rendered)
        self.assertIn("&amp;", rendered)
        self.assertNotIn(">&<", rendered)


class TestThemeStyling(unittest.TestCase):
    """Tint plus a non-color marker, cycled deterministically, and a legend."""

    def test_themed_cells_carry_their_own_theme_class(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        cols = len(fixtures.WIDE_ROWS[0])
        by_class: dict[str, set[tuple[int, int]]] = {}
        for index, name in enumerate(fixtures.cell_classes(rendered)):
            by_class.setdefault(name, set()).add(_cell_position(index, cols))
        for order, theme_id in enumerate(sorted(fixtures.WIDE_THEMES)):
            expected = set(fixtures.WIDE_THEME_CELLS.get(theme_id, ()))
            self.assertEqual(
                by_class.get(cw_svg.theme_class(order), set()),
                expected,
                f"theme {theme_id} tinted the wrong cells",
            )

    def test_across_owns_a_crossing_cell_shared_by_two_themes(self) -> None:
        # (0, 0) is in PLUMS (fruit, ACROSS) and PEAR (trees, DOWN). The
        # documented tie-break is run order, which puts ACROSS first.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        fruit_index = sorted(fixtures.WIDE_THEMES).index("fruit")
        self.assertEqual(
            fixtures.cell_classes(rendered)[0], cw_svg.theme_class(fruit_index)
        )

    def test_an_undeclared_theme_renders_plain(self) -> None:
        # A grid whose content is questionable still renders.
        rendered = cw_svg.render_svg(
            fixtures.wide_request(themes={}, entry_themes={"PLUMS": "fruit"})
        )
        self.assertEqual(
            set(fixtures.cell_classes(rendered)),
            {cw_svg.PLAIN_CLASS, cw_svg.BLOCK_CLASS},
        )

    def test_a_marker_is_drawn_on_every_themed_cell(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        expected = sum(len(cells) for cells in fixtures.WIDE_THEME_CELLS.values())
        self.assertEqual(
            len(fixtures.marker_tags(rendered, cw_svg.MARKER_LAYER)), expected
        )

    def test_grid_markers_follow_the_theme_each_cell_carries(self) -> None:
        # Shape counts, not a total: a render that drew one shape everywhere
        # would pass a count of markers and fail this.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        order = sorted(fixtures.WIDE_THEMES)
        expected: dict[str, int] = {}
        for theme_id, cells in fixtures.WIDE_THEME_CELLS.items():
            tag = cw_svg.marker_element_name(order.index(theme_id))
            expected[tag] = expected.get(tag, 0) + len(cells)
        drawn: dict[str, int] = {}
        for tag in fixtures.marker_tags(rendered, cw_svg.MARKER_LAYER):
            drawn[tag] = drawn.get(tag, 0) + 1
        self.assertEqual(drawn, expected)

    def test_the_legend_shows_one_marker_per_declared_theme_in_cycle_order(
        self,
    ) -> None:
        # Five declared themes against four marker shapes, so this also pins the
        # wrap: the fifth theme reuses the first shape.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        self.assertEqual(
            fixtures.marker_tags(rendered, cw_svg.LEGEND_MARKER_LAYER),
            [
                cw_svg.marker_element_name(order)
                for order in range(len(fixtures.WIDE_THEMES))
            ],
        )

    def test_the_marker_cycle_wraps_rather_than_running_out(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        tags = fixtures.marker_tags(rendered, cw_svg.LEGEND_MARKER_LAYER)
        self.assertGreater(len(tags), len(set(tags)))
        self.assertEqual(tags[0], tags[-1])

    def test_the_two_rectangular_markers_are_distinguishable(self) -> None:
        # Two of the marker shapes are both rects; if they rendered identically
        # the cycle would have one fewer usable shape than it claims.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        aspects = {
            float(str(rect.get("width"))) == float(str(rect.get("height")))
            for rect in fixtures.children(rendered, cw_svg.LEGEND_MARKER_LAYER, "rect")
        }
        self.assertEqual(aspects, {True, False})

    def test_the_legend_marker_matches_the_grid_marker_for_one_theme(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.wide_request(
                themes={"places": "Places"}, entry_themes={"ARENA": "places"}
            )
        )
        legend = fixtures.marker_tags(rendered, cw_svg.LEGEND_MARKER_LAYER)
        grid = fixtures.marker_tags(rendered, cw_svg.MARKER_LAYER)
        self.assertEqual(set(legend), set(grid))

    def test_the_legend_names_every_declared_theme_in_one_order(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        self.assertEqual(
            fixtures.legend_labels(rendered),
            [fixtures.WIDE_THEMES[key] for key in sorted(fixtures.WIDE_THEMES)],
        )

    def test_each_legend_swatch_carries_its_own_tint_class(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        swatches = fixtures.children(rendered, cw_svg.SWATCH_LAYER, "rect")
        self.assertEqual(
            [str(rect.get("class")) for rect in swatches],
            [cw_svg.theme_class(order) for order in range(len(fixtures.WIDE_THEMES))],
        )

    def test_more_themes_than_the_palette_holds_still_render(self) -> None:
        # The palette is finite and a grid may declare more themes than it has
        # colors; the cycle has to wrap rather than run off the end.
        many = {f"t{index:02d}": f"Theme {index}" for index in range(12)}
        rendered = cw_svg.render_svg(
            fixtures.wide_request(themes=many, entry_themes={})
        )
        fixtures.parse(rendered)
        self.assertEqual(len(fixtures.legend_labels(rendered)), len(many))

    def test_every_declared_theme_gets_a_stylesheet_rule(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        for order in range(len(fixtures.WIDE_THEMES)):
            self.assertIn(f".{cw_svg.theme_class(order)}", rendered)

    def test_escapes_xml_special_characters_in_a_theme_label(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request(themes={"pets": "Cats & <dogs>"}))
        fixtures.parse(rendered)
        self.assertIn("&amp;", rendered)
        self.assertNotIn("<dogs>", rendered)
        self.assertEqual(fixtures.legend_labels(rendered), ["Cats & <dogs>"])

    def test_a_grid_with_no_declared_themes_still_renders(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request(themes={}, entry_themes={}))
        fixtures.parse(rendered)
        self.assertEqual(fixtures.legend_labels(rendered), [])


class TestFeatureShading(unittest.TestCase):
    """The featured answer's cells are shaded, and only those."""

    def test_shades_the_featured_cells(self) -> None:
        plain = cw_svg.render_svg(fixtures.request())
        featured = cw_svg.render_svg(fixtures.request(feature="COW"))
        self.assertNotEqual(plain, featured)

    def test_names_the_featured_answer_in_the_caption(self) -> None:
        self.assertIn("COW", cw_svg.render_svg(fixtures.request(feature="COW")))

    def test_shaded_cell_count_matches_the_answer_length(self) -> None:
        # Counting the shading class is what catches a render that shades a whole
        # row instead of one entry: a picture that still looks plausible.
        rendered = cw_svg.render_svg(fixtures.request(feature="COW"))
        self.assertEqual(rendered.count(cw_svg.FEATURE_CLASS), 3)

    def test_shades_exactly_the_cells_the_answer_occupies(self) -> None:
        # PEAR runs DOWN the first column of the wide grid. Reading the shaded
        # positions back out is what separates a coordinate bug from a render
        # that merely shades the right number of cells.
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        cols = len(fixtures.WIDE_ROWS[0])
        shaded = {
            _cell_position(index, cols)
            for index, name in enumerate(fixtures.cell_classes(rendered))
            if name == cw_svg.FEATURE_TOKEN
        }
        self.assertEqual(shaded, {(0, 0), (1, 0), (2, 0), (3, 0)})

    def test_a_featured_themed_cell_keeps_both_readings(self) -> None:
        # The shading is the cell fill and the theme's marker
        # still draws over it, so neither reading is lost. Every PEAR cell is
        # also themed, so shading them must not cost a single marker.
        plain = cw_svg.render_svg(fixtures.wide_request())
        featured = cw_svg.render_svg(fixtures.wide_request(feature="PEAR"))
        self.assertEqual(
            fixtures.marker_tags(featured, cw_svg.MARKER_LAYER),
            fixtures.marker_tags(plain, cw_svg.MARKER_LAYER),
        )

    def test_a_feature_absent_from_the_grid_shades_nothing(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request(feature="ZEBRA"))
        self.assertNotIn(cw_svg.FEATURE_TOKEN, fixtures.cell_classes(rendered))

    def test_an_empty_feature_string_is_treated_as_absent(self) -> None:
        self.assertEqual(
            cw_svg.render_svg(fixtures.request(feature="")),
            cw_svg.render_svg(fixtures.request(feature=None)),
        )


if __name__ == "__main__":
    unittest.main()
