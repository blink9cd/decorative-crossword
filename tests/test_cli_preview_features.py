"""CLI tests for a repeated `preview --feature`, and the shapes it refuses.

`preview --feature` repeats as `fill --feature` does, but takes a bare ANSWER
only. `preview` locates an answer in a grid it did not build, and the shading
follows the answer's text, so a position could change nothing drawn:
`ANSWER@ROW,COL,DIR` is REFUSED at exit 2 rather than read as an assertion, and
an answer named twice is refused, as `fill` refuses it.

Several cases give the flags in an order chosen so that a last-wins
`--feature` -- argparse's default for a repeated flag -- would pass the wrong
one: the value that has to be checked comes first, where a last-wins flag
drops it.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
from pathlib import Path

import cw_command_base
import cw_grid_document
import cw_svg
import decorative_crossword
from tests import cli_fixtures, test_cli_strays

#: Two entries, CAT across the top and DOG across the bottom, and nothing else.
ROWS = ["CAT..", ".....", "DOG.."]

#: A cell edge given explicitly, so the expected render is built from the same
#: int the command line carried rather than from the untyped defaults table.
CELL = 40


def preview_argv(source: Path, svg: Path, *features: str) -> list[str]:
    """A `preview` argv for `source` into `svg`, one `--feature` per value."""
    argv = ["preview", "--source", str(source), "--out", str(svg)]
    for feature in features:
        argv += ["--feature", feature]
    return argv


def shaded_cells(svg: Path) -> int:
    """How many cells the render at `svg` shades as featured."""
    return svg.read_text(encoding="utf-8").count(cw_svg.FEATURE_CLASS)


class TestRepeatedPreviewFeature(cli_fixtures.QuietCase):
    """Every `--feature` given is shaded, and every one is checked."""

    def test_every_repeated_feature_is_shaded_and_captioned(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            code = decorative_crossword.main(preview_argv(source, svg, "CAT", "DOG"))
            self.assertEqual(code, 0)
            self.assertEqual(shaded_cells(svg), len("CAT") + len("DOG"))
            rendered = svg.read_text(encoding="utf-8")
            for answer in ("CAT", "DOG"):
                with self.subTest(answer=answer):
                    self.assertIn(f"Featured: {answer}<", rendered)

    def test_a_first_feature_absent_from_the_grid_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            code = decorative_crossword.main(preview_argv(source, svg, "NOPE", "CAT"))
            self.assertEqual(code, 2)
            self.assertIn("'NOPE'", self.errors)
            self.assertFalse(svg.exists())

    def test_every_absent_feature_is_named_in_one_refusal(self) -> None:
        # Told only the first, an operator fixes it and is refused again.
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            argv = preview_argv(source, svg, "NOPE", "CAT", "NIX")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertEqual(len(self.errors.splitlines()), 1, self.errors)
            self.assertIn("'NOPE'", self.errors)
            self.assertIn("'NIX'", self.errors)
            self.assertLess(self.errors.index("'NOPE'"), self.errors.index("'NIX'"))

    def test_a_single_absent_feature_keeps_its_message(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            self.assertEqual(
                decorative_crossword.main(preview_argv(source, svg, "NOPE")), 2
            )
            self.assertEqual(
                self.errors,
                f"{test_cli_strays.TOOL}: the featured answer 'NOPE' is not in "
                "this grid\n",
            )

    def test_a_single_feature_draws_exactly_the_one_answer_render(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            argv = [*preview_argv(source, svg, "DOG"), "--cell", str(CELL)]
            self.assertEqual(decorative_crossword.main(argv), 0)
            document = cw_grid_document.load_document(source)
            expected = cw_command_base.render(document, ("DOG",), CELL, None, None)
            self.assertEqual(svg.read_text(encoding="utf-8"), expected)

    def test_a_stray_still_warns_beside_two_features(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, test_cli_strays.STRAY_ROWS)
            svg = Path(folder) / "p.svg"
            code = decorative_crossword.main(preview_argv(source, svg, "CAT", "DOG"))
            self.assertEqual(code, 0)
            self.assertEqual(shaded_cells(svg), len("CAT") + len("DOG"))
            warning = f"{test_cli_strays.TOOL}: {test_cli_strays.STRAY_WARNING}\n"
            self.assertEqual(self.errors.count(warning), 1, self.errors)

    def test_fill_preview_and_preview_shade_the_same_repeated_features(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            features = ("--feature", "CHALK", "--feature", "BRAVO")
            argv = space.fill(*features, "--preview", str(space.svg))
            self.assertEqual(decorative_crossword.main(argv), 0)
            from_fill = shaded_cells(space.svg)
            self.assertEqual(from_fill, len("CHALK") + len("BRAVO"))
            again = Path(folder) / "again.svg"
            argv = preview_argv(space.out, again, "CHALK", "BRAVO")
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(shaded_cells(again), from_fill)


class TestPreviewTakesNoPosition(cli_fixtures.QuietCase):
    """`ANSWER@ROW,COL,DIR` is refused: a position would change nothing drawn."""

    def test_a_positioned_feature_exits_two_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            argv = preview_argv(source, svg, "CAT@0,0,across", "DOG")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("'CAT@0,0,across'", self.errors)
            self.assertIn("takes no position", self.errors)
            self.assertFalse(svg.exists())

    def test_a_malformed_position_gets_the_same_refusal(self) -> None:
        # Not fill's "a pin is ANSWER@ROW,COL,DIR", which would read as though
        # a well-formed pin were welcome here.
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            argv = preview_argv(source, svg, "CAT@junk", "DOG")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("takes no position", self.errors)
            self.assertNotIn("a pin is", self.errors)

    def test_the_position_is_refused_before_the_source_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            absent = Path(folder) / "absent.json"
            svg = Path(folder) / "p.svg"
            argv = preview_argv(absent, svg, "CAT@0,0,across", "DOG")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("takes no position", self.errors)
            self.assertNotIn("absent.json", self.errors)


class TestPreviewRefusesADuplicate(cli_fixtures.QuietCase):
    """An answer named twice is refused, as `fill` refuses it."""

    def test_an_answer_named_twice_exits_two_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = test_cli_strays.write_source(folder, ROWS)
            svg = Path(folder) / "p.svg"
            argv = preview_argv(source, svg, "CAT", "DOG", "CAT")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("--feature names 'CAT' twice", self.errors)
            self.assertFalse(svg.exists())

    def test_the_duplicate_is_refused_before_the_source_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            absent = Path(folder) / "absent.json"
            argv = preview_argv(absent, Path(folder) / "p.svg", "CAT", "CAT")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("twice", self.errors)
            self.assertNotIn("absent.json", self.errors)
