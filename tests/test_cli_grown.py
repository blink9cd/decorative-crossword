"""Grouped suite: `fill --source` growing the grid past the source's own size.

`--rows` and `--cols` beside `--source` give the canvas the source is placed on,
at the top-left, so every source cell keeps its coordinates: each flag at least
the source's own dimension, a flag left off taking the source's. These cases
drive `main` end to end, because each claim is about what a real run writes,
prints or refuses.

Every fixture's expected outcome is the one its source gives when padded by
hand with blocked cells to the canvas: top-left placement makes that padded
source exactly the board a grown run starts from.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest

import cw_grid
import cw_svg
import cw_svg_style
from tests import cli_fixtures, svg_fixtures
from tests.source_fixtures import SOURCE_NAME, SourceCase, filled, source_fill
from tests.source_fixtures import write_source

#: CRA down column 0 of a 3x3: a half-written CRANE. No bank answer fits over it
#: at its own size, since CRANE needs five rows, so this source is refused there
#: and becomes a partial run only on a canvas at least five rows tall.
_CRA = ["C..", "R..", "A.."]

#: A 2x3 source holding CRA across, and its 3x2 transpose holding CRA down.
_CRA_WIDE = ["CRA", "..."]
_CRA_TALL = ["C.", "R.", "A."]

#: ALPHA across row 4 of a 9x9, and nothing else.
_ALPHA_ROW = ["." * 9] * 4 + ["..ALPHA.."] + ["." * 9] * 4

#: ALPHA across and AMBER down from one corner of a 5x5: 64.0% blocked at its
#: own size, and 70.0% once a sixth column of blocked cells is added.
_CORNER = ["ALPHA", "M....", "B....", "E....", "R...."]

#: The words every size refusal closes with.
_TAIL = ": fill grows a source, never crops it"


def _cells_of(rows: list[str], answer: str) -> list[tuple[int, int]]:
    """The cells `answer` reads through in `rows`, first to last; empty when absent."""
    run = cw_grid.find_answer(rows, answer)
    return [] if run is None else list(run.cells)


def _down(col: int, length: int) -> list[tuple[int, int]]:
    """`length` cells down column `col` from the top row."""
    return [(row, col) for row in range(length)]


def _across(row: int, length: int) -> list[tuple[int, int]]:
    """`length` cells across row `row` from the first column."""
    return [(row, col) for col in range(length)]


class TestGrowingTheCanvas(SourceCase):
    """A source sits at the top-left of a larger grid, and nothing of it moves."""

    def test_a_3x3_source_in_a_5x7_canvas_conforms_with_every_source_letter_in_place(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _CRA)
            extra = ("--rows", "5", "--cols", "7", "--min-themes", "2")
            code = self.run_main(source_fill(space, source, *extra))
            self.assertEqual(code, 0, self.errors)
            written = space.rows()
        self.assertEqual((len(written), len(written[0])), (5, 7))
        self.assertLessEqual(filled(_CRA).items(), filled(written).items())
        self.assertEqual(_cells_of(written, "CRANE"), _down(0, 5))
        lines = self.printed.splitlines()
        self.assertIn(
            "Grown from --source: its 3x3 grid sits at (0, 0) of this 5x7 grid.", lines
        )
        self.assertTrue(any(line.startswith("Grid 5x7: ") for line in lines))

    def test_the_same_source_is_refused_at_its_own_size(self) -> None:
        # The other half of the case above: the grown canvas is what opened the
        # source's edge, so CRA is completable there and nowhere smaller.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _CRA)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 2)
            self.assertIn("nor completable by a bank answer: 'CRA' down", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_non_square_source_grows_into_a_non_square_canvas(self) -> None:
        cases = (
            (_CRA_WIDE, (6, 8), _across(0, 5)),
            (_CRA_TALL, (8, 6), _down(0, 5)),
        )
        for rows, (height, width), crane in cases:
            with (
                self.subTest(canvas=f"{height}x{width}"),
                tempfile.TemporaryDirectory() as folder,
            ):
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / SOURCE_NAME, rows)
                size = ("--rows", str(height), "--cols", str(width))
                code = self.run_main(source_fill(space, source, *size))
                self.assertEqual(code, 0, self.errors)
                written = space.rows()
                self.assertEqual((len(written), len(written[0])), (height, width))
                self.assertLessEqual(filled(rows).items(), filled(written).items())
                self.assertEqual(_cells_of(written, "CRANE"), crane)

    def test_one_flag_grows_one_dimension_and_the_other_stays_the_sources(
        self,
    ) -> None:
        cases = ((_CRA, "--rows", "5", (5, 3)), (_CRA_WIDE, "--cols", "8", (2, 8)))
        for rows, flag, value, size in cases:
            with self.subTest(flag), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / SOURCE_NAME, rows)
                code = self.run_main(source_fill(space, source, flag, value))
                self.assertEqual(code, 0, self.errors)
                written = space.rows()
                self.assertEqual((len(written), len(written[0])), size)

    def test_a_size_equal_to_the_sources_writes_what_no_size_flag_writes(
        self,
    ) -> None:
        outputs: list[bytes] = []
        for size in ((), ("--rows", "9", "--cols", "9")):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / SOURCE_NAME, _ALPHA_ROW)
                self.assertEqual(self.run_main(source_fill(space, source, *size)), 0)
                outputs.append(space.out.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        self.assertNotIn("Grown from --source", self.printed)


class TestSizesASourceRefuses(SourceCase):
    """A size under the source's own is exit 2, naming every flag at fault."""

    def test_a_size_under_the_sources_is_refused_naming_each_flag(self) -> None:
        rows_short = "--rows 2 is smaller than the --source grid's 3 rows"
        cols_short = "--cols 1 is smaller than the --source grid's 3 columns"
        cases = (
            (("--rows", "2"), rows_short + _TAIL),
            (("--cols", "1"), cols_short + _TAIL),
            (("--rows", "2", "--cols", "1"), f"{rows_short}; {cols_short}{_TAIL}"),
        )
        for size, message in cases:
            with self.subTest(size=size), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / SOURCE_NAME, _CRA)
                code = self.run_main(source_fill(space, source, *size))
                self.assertEqual(code, 2)
                self.assertIn(message, self.errors)
                self.assertFalse(space.out.exists())


class TestTheGrownDensityRefusal(SourceCase):
    """A grown board under --min-blocked is refused naming what was measured."""

    def test_the_refusal_names_the_grown_grid_its_percentage_is_taken_over(
        self,
    ) -> None:
        # 70.0% is the 5x6 board's figure, grown cells included; the source's
        # own 5x5 is 64.0%. The sentence must not call the 70.0% the source's.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _CORNER)
            extra = ("--cols", "6", "--min-blocked", "75")
            code = self.run_main(source_fill(space, source, *extra))
            self.assertEqual(code, 1, self.errors)
        self.assertIn(
            "  this 5x6 grid, with its 5x5 --source grid placed at the top-left, is "
            "already 70.0% blocked, under the requested 75.0% floor, and fill only "
            "adds letters",
            self.printed.splitlines(),
        )
        self.assertNotIn("the --source grid is already", self.printed)


class TestPinsOnAGrownCanvas(SourceCase):
    """A pin names a canvas cell, which for every source cell is the source's own."""

    def test_a_pin_is_placed_in_canvas_cells_past_the_sources_edge(self) -> None:
        # Column 6 exists only on the canvas: at the source's 3x3 it runs off.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _CRA)
            extra = ("--rows", "5", "--cols", "7", "--feature", "BLADE@0,6,down")
            code = self.run_main(source_fill(space, source, *extra))
            self.assertEqual(code, 0, self.errors)
            written = space.rows()
        self.assertEqual(_cells_of(written, "BLADE"), _down(6, 5))
        self.assertLessEqual(filled(_CRA).items(), filled(written).items())

    def test_a_pin_off_the_canvas_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _CRA)
            extra = ("--rows", "5", "--cols", "7", "--feature", "BLADE@0,7,down")
            code = self.run_main(source_fill(space, source, *extra))
            self.assertEqual(code, 2)
            self.assertIn("--feature BLADE@0,7,down runs off a 5x7 grid", self.errors)
            self.assertFalse(space.out.exists())


class TestTheGrownPictureAndRemedies(SourceCase):
    """The picture marks the source's cells, and no knob names a refused size."""

    def test_the_bold_letters_land_on_the_sources_cells_in_the_grown_grid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _CRA)
            extra = ("--rows", "5", "--cols", "7", "--preview", str(space.svg))
            self.assertEqual(self.run_main(source_fill(space, source, *extra)), 0)
            rendered = space.svg.read_text(encoding="utf-8")
            written = filled(space.rows())
        fixed = svg_fixtures.letter_cells(rendered, cw_svg_style.FIXED_LETTER_LAYER)
        plain = svg_fixtures.letter_cells(rendered, cw_svg.LETTER_LAYER)
        self.assertEqual(fixed, filled(_CRA))
        # The fill must actually have grown, or "not marked" is vacuous.
        self.assertTrue(plain)
        self.assertEqual({**plain, **fixed}, written)
        self.assertIn(
            "Fixed from --source: 3 letter(s), in bold",
            svg_fixtures.caption_lines(rendered),
        )

    def test_no_knob_advises_a_size_the_source_refuses(self) -> None:
        cases = (
            (
                ("--rows", "5", "--max-blocked", "10"),
                "  loosen --max-blocked to 66.7 or higher, or shrink --rows",
            ),
            (
                ("--rows", "5", "--cols", "7", "--max-blocked", "10"),
                "  loosen --max-blocked to 40.0 or higher, or shrink --rows / --cols",
            ),
            (
                (
                    "--rows",
                    "5",
                    "--cols",
                    "7",
                    "--feature",
                    "BROOK",
                    "--max-steps",
                    "2",
                ),
                "  place BROOK by raising --time-budget or --max-steps, or grow "
                "--rows / --cols",
            ),
        )
        for extra, knob in cases:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / SOURCE_NAME, _CRA)
                code = self.run_main(source_fill(space, source, *extra))
                self.assertEqual(code, 1, self.errors)
                self.assertIn(knob, self.printed.splitlines())

    def test_a_source_at_its_own_size_is_never_advised_to_shrink(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / SOURCE_NAME, _ALPHA_ROW)
            code = self.run_main(source_fill(space, source, "--max-blocked", "10"))
            self.assertEqual(code, 1, self.errors)
        knobs = [line for line in self.printed.splitlines() if "--max-blocked" in line]
        self.assertTrue(any(line.startswith("  loosen") for line in knobs))
        self.assertNotIn("shrink", self.printed)


if __name__ == "__main__":
    unittest.main()
