"""Grouped suite: `--mask` at the process boundary -- exit codes, sizes, files.

What only a real run can settle about a shape file: that a picture the parser
refuses reaches the operator as exit 2 rather than a traceback, that a picture
stands in for `--rows` / `--cols` the way a `--source` grid does, and that a
picture conflicting with either is refused before any searching.

That the grid comes back with no letter where the picture forbids one is the
point of the feature, and `test_cli_mask_shape.py` owns it: it is a claim about
the search's seams rather than about the command line, and it needs a grid big
enough for the crossing generator to be exercised.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest

import decorative_crossword
from tests import cli_fixtures


def _without_size(argv: list[str]) -> list[str]:
    """`argv` with `--rows` and `--cols` and their values removed.

    So the mask is the only thing left that can say how big the grid is, which
    is the case the sizing rule is about.
    """
    stripped = list(argv)
    for flag in ("--rows", "--cols"):
        at = stripped.index(flag)
        del stripped[at : at + 2]
    return stripped


class TestMaskSizing(cli_fixtures.QuietCase):
    """What the picture says about how big the grid is."""

    def test_a_picture_supplies_an_absent_rows_and_cols(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            picture = space.mask("X....", ".....", "....X")
            code = decorative_crossword.main(
                _without_size(space.fill("--mask", str(picture)))
            )
            rows = space.rows()
        self.assertEqual(code, 0)
        self.assertEqual((len(rows), len(rows[0])), (3, 5))

    def test_a_picture_disagreeing_with_rows_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            picture = space.mask("X....", ".....", "....X")
            code = decorative_crossword.main(space.fill("--mask", str(picture)))
            written = space.out.exists()
        self.assertEqual(code, 2)
        self.assertIn("--mask", self.errors)
        self.assertIn("3x5", self.errors)
        self.assertIn("9x9", self.errors)
        self.assertFalse(written)


class TestMaskReportLine(cli_fixtures.QuietCase):
    """One line under `--mask`, naming the file and how much it forbids."""

    def test_names_the_file_and_the_masked_count(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            picture = space.mask("X.......X", *(("." * 9,) * 7), "X.......X")
            code = decorative_crossword.main(space.fill("--mask", str(picture)))
            report = self.printed
        self.assertEqual(code, 0)
        self.assertIn(
            f"From --mask {picture}: 4 of 81 cells may never hold a letter.",
            report.splitlines(),
        )

    def test_the_density_is_measured_over_the_unmasked_cells(self) -> None:
        # The line above and the basis clause on the grid line are one thought
        # split in two: the count says how many cells left the grid, and the
        # clause says the percentage was taken over what remains.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            picture = space.mask("X.......X", *(("." * 9,) * 7), "X.......X")
            decorative_crossword.main(space.fill("--mask", str(picture)))
            report = self.printed
        self.assertIn("blocked of 77 unmasked cells", report)

    def test_a_run_without_a_mask_prints_no_such_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            report = self.printed
        self.assertNotIn("--mask", report)
        self.assertNotIn("unmasked", report)


class TestMaskRefusals(cli_fixtures.QuietCase):
    """A picture the parser rejects is exit 2, on stderr, with no grid written."""

    def _refused(self, *rows: str) -> int:
        """Run a fill over the picture `rows`; return its exit code."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            code = decorative_crossword.main(
                space.fill("--mask", str(space.mask(*rows)))
            )
            self.assertFalse(space.out.exists())
        return code

    def test_a_ragged_picture_is_exit_two_and_not_a_traceback(self) -> None:
        # The claim under test is that `cw_mask.MaskError` is in the CLI's
        # refusal set: uncaught it would be a traceback at a non-2 exit.
        self.assertEqual(self._refused("...", ".."), 2)
        self.assertIn("ragged", self.errors)

    def test_an_unknown_character_is_exit_two(self) -> None:
        self.assertEqual(self._refused(".q.", "..."), 2)
        self.assertIn("column 2", self.errors)

    def test_a_wholly_masked_picture_is_exit_two(self) -> None:
        self.assertEqual(self._refused("XX", "XX"), 2)
        self.assertIn("every cell", self.errors)

    def test_a_pin_into_a_masked_cell_is_exit_two(self) -> None:
        # An operator-authored claim beats nothing: the pin and the picture
        # contradict each other, so the run is refused rather than one of them
        # quietly winning. Without the check the pin would win, because
        # `apply_placement` builds the pinned board with no mask in hand.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            picture = space.mask("X" + "." * 8, *(("." * 9,) * 8))
            code = decorative_crossword.main(
                space.fill("--mask", str(picture), "--feature", "ALPHA@0,0,across")
            )
            written = space.out.exists()
        self.assertEqual(code, 2)
        self.assertIn("--feature", self.errors)
        self.assertIn("--mask", self.errors)
        self.assertFalse(written)

    def test_a_missing_picture_is_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            code = decorative_crossword.main(
                space.fill("--mask", str(space.root / "absent.txt"))
            )
            written = space.out.exists()
        self.assertEqual(code, 2)
        self.assertIn("could not read mask file", self.errors)
        self.assertFalse(written)


if __name__ == "__main__":
    unittest.main()
