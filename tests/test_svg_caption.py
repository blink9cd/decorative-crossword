"""Tests for cw_svg's caption tiers, legend geometry and number formatting.

Kept apart from `test_svg.py` at a class boundary: each file holds one coherent
concern -- the document's structure there, what it says about itself here.

The caption's two tiers are a correctness requirement, not a layout preference.
The derivable tier is read out of the grid and is always
present; the configuration tier is stamped only when the caller actually knows
those values, and is ABSENT -- not blank, not defaulted -- when it does not.
"""

import re
import unittest

import cw_svg
from tests import svg_fixtures as fixtures

#: Every viewBox number must render in one-decimal fixed form. A bare float
#: repr varies in digit count between values, which would break the
#: byte-identical guarantee the golden sample depends on.
_ONE_DECIMAL = re.compile(r"^\d+\.\d$")

#: How far a quadrupled dimension may miss its rounded quadruple by. The
#: emitted numbers are rounded to one decimal, so exact linearity cannot
#: survive the round-trip; an absolute unit smuggled into the geometry would
#: show up as a constant offset far larger than one rounding step.
_ROUNDING_SLACK = 0.5


def _viewbox(rendered: str) -> tuple[float, ...]:
    """The four viewBox numbers of a rendered document."""
    return tuple(
        float(part) for part in str(fixtures.parse(rendered).get("viewBox")).split()
    )


class TestDerivableCaption(unittest.TestCase):
    """Size, blocked percentage and theme counts come off the grid every time."""

    def test_caption_carries_the_derivable_tier_always(self) -> None:
        # Asserted as the whole line. A bare `assertIn("3", ...)` is satisfied
        # by any coordinate in the document and reads as coverage it does not
        # provide.
        rendered = cw_svg.render_svg(fixtures.request())
        self.assertEqual(
            fixtures.caption_lines(rendered)[0], "3x3 grid | 22.2% blocked | Pets: 2"
        )

    def test_reports_size_blocked_and_theme_counts_on_one_line(self) -> None:
        rendered = cw_svg.render_svg(fixtures.wide_request())
        self.assertEqual(
            fixtures.caption_lines(rendered)[0],
            "4x5 grid | 30.0% blocked | Flight: 1 | Fruit: 1 | Places: 1 "
            "| Trees: 1 | Water: 0",
        )

    def test_size_names_rows_before_columns(self) -> None:
        # A square fixture cannot tell these apart, which is why the check runs
        # on a grid that is taller than it is wide.
        rendered = cw_svg.render_svg(
            fixtures.request(rows=("AB", "CD", "EF"), themes={}, entry_themes={})
        )
        self.assertIn("3x2 grid", fixtures.caption_lines(rendered)[0])

    def test_blocked_percentage_is_measured_not_echoed(self) -> None:
        # Settings claiming a different range must not move the achieved
        # figure: one is a request, the other is what the grid actually is.
        rendered = cw_svg.render_svg(
            fixtures.wide_request(settings={"density": "60.0-70.0"})
        )
        self.assertIn("30.0% blocked", fixtures.caption_lines(rendered)[0])

    def test_a_declared_theme_with_no_entries_counts_zero(self) -> None:
        # "Water" is declared and never placed. Dropping it would make the
        # caption silently disagree with the legend beside it.
        rendered = cw_svg.render_svg(fixtures.wide_request())
        self.assertIn("Water: 0", fixtures.caption_lines(rendered)[0])

    def test_theme_counts_track_the_entries_actually_in_the_grid(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.wide_request(
                entry_themes={"PLUMS": "fruit", "PEAR": "fruit", "SOAR": "fruit"}
            )
        )
        self.assertIn("Fruit: 3", fixtures.caption_lines(rendered)[0])
        self.assertIn("Places: 0", fixtures.caption_lines(rendered)[0])

    def test_an_entry_theme_that_is_not_declared_is_counted_nowhere(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.wide_request(entry_themes={"PLUMS": "undeclared"})
        )
        line = fixtures.caption_lines(rendered)[0]
        self.assertNotIn("undeclared", line)
        self.assertIn("Fruit: 0", line)


class TestConfigurationCaption(unittest.TestCase):
    """The configuration tier is stamped only when the caller knows it."""

    def test_caption_omits_configuration_when_it_is_unknown(self) -> None:
        # Bare `preview` knows no seed. Inventing one would put a number on the
        # picture that nothing checked.
        self.assertNotIn("seed", cw_svg.render_svg(fixtures.request()).lower())

    def test_caption_carries_configuration_when_supplied(self) -> None:
        text = cw_svg.render_svg(
            fixtures.request(settings={"seed": "7", "density": "30.0-45.0"})
        )
        self.assertIn("seed", text.lower())
        self.assertIn("7", text)

    def test_configuration_is_absent_rather_than_blank(self) -> None:
        # An empty line would still be a line: the tier has to disappear.
        without = cw_svg.render_svg(fixtures.wide_request())
        with_settings = cw_svg.render_svg(fixtures.wide_request(settings={"seed": "7"}))
        self.assertEqual(
            len(fixtures.caption_lines(with_settings)),
            len(fixtures.caption_lines(without)) + 1,
        )
        self.assertNotIn("", fixtures.caption_lines(without))

    def test_configuration_renders_every_pair_in_a_fixed_order(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.request(
                settings={"seed": "7", "density": "30.0-45.0", "themes": "3"}
            )
        )
        self.assertEqual(
            fixtures.caption_lines(rendered)[-1],
            "density: 30.0-45.0 | seed: 7 | themes: 3",
        )

    def test_configuration_order_does_not_depend_on_insertion_order(self) -> None:
        forward = cw_svg.render_svg(
            fixtures.request(settings={"seed": "7", "density": "30.0-45.0"})
        )
        backward = cw_svg.render_svg(
            fixtures.request(settings={"density": "30.0-45.0", "seed": "7"})
        )
        self.assertEqual(forward, backward)

    def test_empty_settings_is_treated_as_absent(self) -> None:
        # A caller assembling settings conditionally must not be able to emit a
        # configuration line that says nothing.
        self.assertEqual(
            cw_svg.render_svg(fixtures.request(settings={})),
            cw_svg.render_svg(fixtures.request(settings=None)),
        )

    def test_configuration_text_is_escaped(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request(settings={"bank": "a & b"}))
        fixtures.parse(rendered)
        self.assertIn("&amp;", rendered)
        self.assertEqual(fixtures.caption_lines(rendered)[-1], "bank: a & b")


class TestFeatureCaption(unittest.TestCase):
    """The featured answer is named in both modes, and never invented."""

    def test_the_feature_is_named_without_settings(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request(feature="COW"))
        self.assertIn("Featured: COW", fixtures.caption_lines(rendered))

    def test_the_feature_is_named_with_settings(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.request(feature="COW", settings={"seed": "7"})
        )
        self.assertIn("Featured: COW", fixtures.caption_lines(rendered))

    def test_no_feature_line_without_a_feature(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request())
        self.assertEqual(len(fixtures.caption_lines(rendered)), 1)

    def test_a_feature_absent_from_the_grid_says_so(self) -> None:
        # Naming it with nothing shaded would be a caption that disagrees with
        # the picture; the honest render says which of the two is missing.
        rendered = cw_svg.render_svg(fixtures.request(feature="ZEBRA"))
        self.assertEqual(
            fixtures.caption_lines(rendered)[1], "Featured: ZEBRA (not in this grid)"
        )

    def test_a_feature_name_is_escaped(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request(feature="A & B"))
        fixtures.parse(rendered)
        self.assertIn("&amp;", rendered)

    def test_every_feature_is_named_in_the_order_given(self) -> None:
        # COW before CAT, the reverse of the grid's own ACROSS-first scan, so
        # a caption built by walking runs instead of the request is caught.
        rendered = cw_svg.render_svg(fixtures.request(features=("COW", "CAT")))
        self.assertEqual(
            fixtures.caption_lines(rendered)[1:3], ["Featured: COW", "Featured: CAT"]
        )

    def test_an_absent_feature_is_named_beside_a_present_one(self) -> None:
        rendered = cw_svg.render_svg(fixtures.request(features=("COW", "ZEBRA")))
        self.assertEqual(
            fixtures.caption_lines(rendered)[1:3],
            ["Featured: COW", "Featured: ZEBRA (not in this grid)"],
        )


class TestGeometry(unittest.TestCase):
    """Fixed number formatting, and a viewBox that follows what is drawn."""

    def test_viewbox_numbers_use_one_decimal_form(self) -> None:
        for number in str(
            fixtures.parse(cw_svg.render_svg(fixtures.wide_request())).get("viewBox")
        ).split():
            self.assertRegex(number, _ONE_DECIMAL)

    def test_cell_size_scales_the_viewbox(self) -> None:
        small = fixtures.parse(cw_svg.render_svg(fixtures.request(cell=10)))
        large = fixtures.parse(cw_svg.render_svg(fixtures.request(cell=40)))
        self.assertNotEqual(small.get("viewBox"), large.get("viewBox"))

    def test_every_dimension_scales_with_the_cell(self) -> None:
        # Nothing in the render may carry a size in absolute units: a fixed
        # margin or font size would distort the picture at another cell size.
        small = _viewbox(cw_svg.render_svg(fixtures.wide_request(cell=10)))
        large = _viewbox(cw_svg.render_svg(fixtures.wide_request(cell=40)))
        for narrow, wide in zip(small, large, strict=True):
            self.assertAlmostEqual(wide, narrow * 4, delta=_ROUNDING_SLACK)

    def test_the_first_cell_sits_one_half_cell_from_the_corner(self) -> None:
        rendered = cw_svg.render_svg(
            fixtures.request(rows=("AB", "CD"), themes={}, entry_themes={}, cell=10)
        )
        corner = fixtures.children(rendered, cw_svg.CELL_LAYER, "rect")[0]
        self.assertEqual(
            [corner.get(name) for name in ("x", "y", "width", "height")],
            ["5.0", "5.0", "10.0", "10.0"],
        )

    def test_a_taller_grid_makes_a_taller_document(self) -> None:
        short = _viewbox(cw_svg.render_svg(fixtures.request(rows=("AB", "CD"))))
        tall = _viewbox(cw_svg.render_svg(fixtures.request(rows=("AB", "CD", "EF"))))
        self.assertGreater(tall[3], short[3])
        self.assertEqual(tall[2], short[2])

    def test_a_wider_grid_makes_a_wider_document(self) -> None:
        narrow = _viewbox(
            cw_svg.render_svg(fixtures.request(rows=("ABCDEFGH", "IJKLMNOP")))
        )
        wide = _viewbox(
            cw_svg.render_svg(fixtures.request(rows=("ABCDEFGHI", "JKLMNOPQR")))
        )
        self.assertGreater(wide[2], narrow[2])

    def test_more_themes_make_a_taller_document(self) -> None:
        one = _viewbox(cw_svg.render_svg(fixtures.request()))
        many = _viewbox(
            cw_svg.render_svg(fixtures.wide_request(rows=("CAT", "O..", "WET")))
        )
        self.assertGreater(many[3], one[3])

    def test_a_long_label_widens_the_document(self) -> None:
        # The caption and legend sit under a narrow grid; if the viewBox tracked
        # the grid alone the text they carry would be clipped away.
        plain = _viewbox(cw_svg.render_svg(fixtures.request()))
        wordy = _viewbox(
            cw_svg.render_svg(fixtures.request(themes={"pets": "Pets " * 20}))
        )
        self.assertGreater(wordy[2], plain[2])

    def test_an_empty_grid_still_renders(self) -> None:
        # `preview` rejects an empty grid upstream; the renderer must not be the
        # thing that crashes if one ever reaches it.
        rendered = cw_svg.render_svg(
            fixtures.request(rows=(), themes={}, entry_themes={})
        )
        fixtures.parse(rendered)
        self.assertIn("0x0 grid", fixtures.caption_lines(rendered)[0])


if __name__ == "__main__":
    unittest.main()
