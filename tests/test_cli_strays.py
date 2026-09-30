"""Grouped suite: the read subcommands warn about a stray lone letter.

`preview`, `shade` and `gaps` take a `--source` grid this tool may never have
produced, so a hand edit can leave a letter in no entry. An ISLAND -- a letter
from `cw_island.ISLAND_LETTERS` with a letter of an entry at a corner -- is such
a letter on purpose and draws nothing; any other lone letter is a stray. A
stray gets a WARNING on stderr and nothing else changes: each subcommand still
draws, places or reports, and exits as it would have.

One case per subcommand, because each handler reads its grid at its own call
site: a handler that went back to reading without the warning would pass every
other test here.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: CAT and DOG are entries; the Q at (2, 4) touches no letter at all, and is off
#: the island set besides.
STRAY_ROWS = ["CAT..", ".....", "DOG.Q"]

#: The whole diagnostic for that Q, after the tool's name.
STRAY_WARNING = (
    "warning: cell 2,4 (Q) belongs to no entry: "
    "Q is not an island letter (A, I, X, U, Y)"
)

#: The A at (1, 3) touches CAT's T at a corner: an island, so no warning.
ISLAND_ROWS = ["CAT.", "...A"]

#: A committed grid `fill --island-letters` laid two islands in.
BEST_GRID = (
    Path(__file__).resolve().parents[1] / "samples" / "best_grid" / "grid_source.json"
)

#: How the tool names itself on stderr, derived as the entry point derives it.
TOOL = Path(decorative_crossword.__file__).stem


def write_source(folder: str, rows: list[str]) -> Path:
    """Write a grid document holding `rows` into `folder`; return its path."""
    path = Path(folder) / "grid_source.json"
    path.write_text(
        json.dumps({"rows": rows, "themes": {}, "clues": {}}),
        encoding="utf-8",
        newline="\n",
    )
    return path


class TestEachReaderWarns(cli_fixtures.QuietCase):
    """Each read subcommand names the stray on stderr and still does its job."""

    def assert_warned_once(self) -> None:
        """The stray's warning reached stderr exactly once, and stdout not at all."""
        self.assertEqual(
            self.errors.count(f"{TOOL}: {STRAY_WARNING}\n"), 1, self.errors
        )
        self.assertNotIn("belongs to no entry", self.printed)

    def test_preview_warns_and_still_draws(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = write_source(folder, STRAY_ROWS)
            svg = Path(folder) / "preview.svg"
            code = decorative_crossword.main(
                ["preview", "--source", str(source), "--out", str(svg)]
            )
            self.assertEqual(code, 0)
            self.assertTrue(svg.exists())
            self.assert_warned_once()

    def test_shade_warns_and_still_places_the_word(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = write_source(folder, STRAY_ROWS)
            code = decorative_crossword.main(
                ["shade", "--source", str(source), "--word", "CAT"]
            )
            self.assertEqual(code, 0)
            self.assertIn("CAT", self.printed)
            self.assert_warned_once()

    def test_gaps_warns_and_still_reports(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = write_source(folder, STRAY_ROWS)
            code = decorative_crossword.main(["gaps", "--source", str(source)])
            self.assertNotEqual(code, 2)
            self.assertTrue(self.printed)
            self.assert_warned_once()


class TestWhatDrawsNoWarning(cli_fixtures.QuietCase):
    """An island is a lone letter on purpose, and says nothing."""

    def test_an_island_draws_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = write_source(folder, ISLAND_ROWS)
            code = decorative_crossword.main(
                [
                    "preview",
                    "--source",
                    str(source),
                    "--out",
                    str(Path(folder) / "p.svg"),
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(self.errors, "")

    def test_the_islands_fill_laid_in_a_sample_draw_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            code = decorative_crossword.main(
                [
                    "preview",
                    "--source",
                    str(BEST_GRID),
                    "--out",
                    str(Path(folder) / "p.svg"),
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(self.errors, "")


class TestEveryStrayIsNamed(cli_fixtures.QuietCase):
    """Two strays are two lines, row-major, each with its own reason."""

    def test_each_stray_gets_its_own_line(self) -> None:
        # Q at (0, 0) is off the set; the I at (2, 0) is on it and touches nothing.
        with tempfile.TemporaryDirectory() as folder:
            source = write_source(folder, ["Q.CAT", ".....", "I...."])
            decorative_crossword.main(["gaps", "--source", str(source)])
            lines = self.errors.splitlines()
            self.assertEqual(len(lines), 2, self.errors)
            self.assertIn("cell 0,0 (Q)", lines[0])
            self.assertIn("cell 2,0 (I)", lines[1])
            self.assertIn("corner", lines[1])
