"""What the `fill --source` samples are for, read back out of their committed files.

`tests/test_samples.py` regenerates every `fill` sample and compares bytes, which
proves each file is what the tool produces today. It does not say the file still
shows what its sample exists to show: a change that moved a source letter, or
stopped growing the grid, would regenerate into new files that match themselves.
These cases read the committed grids back instead.

The command table stays in `tests/test_samples.py`, the one place a machine pins
the README's commands, and is read from there rather than copied: each case reads
the very flags the regeneration runs with, so the source, size and pin a case
checks are the command's own.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import unittest
from pathlib import Path

import cw_feature
import cw_grid
import cw_island
import cw_reach
from tests import samples_fixtures
from tests.test_samples import _CASES, _rows_of


def _flag_value(name: str, flag: str) -> str:
    """The value `flag` takes in sample `name`'s own command."""
    argv = _CASES[name]
    return argv[argv.index(flag) + 1]


def _source_path(name: str) -> Path:
    """The `--source` file sample `name`'s command reads."""
    return Path(_flag_value(name, "--source"))


class TestPartialGridSample(unittest.TestCase):
    """The committed partial grid shows what it is for: a source kept, and finished.

    The byte comparison proves the files are what the tool produces. These say
    the files still show `--source` doing its job, so a change that moved a
    source letter, stopped keeping an entry the bank lacks, or accepted a grid
    whose stray is still lone fails by name instead of regenerating quietly into
    a sample that demonstrates nothing.
    """

    def test_every_source_letter_sits_unchanged_in_the_grid(self) -> None:
        source = json.loads(_source_path("partial_grid").read_text("utf-8"))["rows"]
        grid = _rows_of("partial_grid")
        self.assertEqual((len(grid), len(grid[0])), (len(source), len(source[0])))
        letters = [
            (row, col, letter)
            for row, line in enumerate(source)
            for col, letter in enumerate(line)
            if letter != cw_grid.BLOCK
        ]
        self.assertTrue(letters, "the sample exists to start from letters")
        for row, col, letter in letters:
            with self.subTest(cell=(row, col)):
                self.assertEqual(grid[row][col], letter)

    def test_the_source_stray_is_covered_by_an_entry(self) -> None:
        # Read with the rule `fill` warns by, so the sample must hold a real
        # stray: a lone letter that is already an island would pass untouched.
        source = json.loads(_source_path("partial_grid").read_text("utf-8"))["rows"]
        strays = cw_island.stray_letters(source)
        self.assertTrue(strays, "the sample exists to show a stray being covered")
        runs = cw_grid.runs_from_rows(_rows_of("partial_grid"))
        covered = {cell for run in runs for cell in run.cells}
        for row, col, _, _ in strays:
            with self.subTest(cell=(row, col)):
                self.assertIn((row, col), covered)

    def test_an_entry_the_bank_lacks_is_kept_with_the_source_record(self) -> None:
        folder = samples_fixtures.SAMPLES / "partial_grid"
        source = json.loads(_source_path("partial_grid").read_text("utf-8"))
        bank = json.loads((folder / "bank.json").read_text("utf-8"))
        grid = json.loads((folder / "grid_source.json").read_text("utf-8"))
        answers = {entry["answer"] for entry in bank["entries"]}
        kept = [
            run.text
            for run in cw_grid.runs_from_rows(source["rows"])
            if run.text not in answers and run.text in source["clues"]
        ]
        self.assertTrue(kept, "the sample exists to keep an entry the bank lacks")
        for text in kept:
            with self.subTest(answer=text):
                self.assertEqual(grid["clues"][text], source["clues"][text])

    def test_a_half_written_word_is_finished_by_a_bank_answer(self) -> None:
        folder = samples_fixtures.SAMPLES / "partial_grid"
        source = json.loads(_source_path("partial_grid").read_text("utf-8"))
        bank = json.loads((folder / "bank.json").read_text("utf-8"))
        held = {entry["answer"] for entry in bank["entries"]} | set(source["clues"])
        partial = cw_reach.partial_runs(source["rows"], held)
        self.assertTrue(partial, "the sample exists to finish a half-written word")
        grid = cw_grid.runs_from_rows(_rows_of("partial_grid"))
        for run in partial:
            with self.subTest(run=run.text):
                self.assertTrue(any(cw_reach.covers(run, e.cells) for e in grid))


class TestGrownGridSample(unittest.TestCase):
    """The committed grown grid shows what it is for: a source placed on a larger grid.

    These say the files still show `--rows` and `--cols` growing a source, so a
    change that centered the source, stopped growing the grid, or read a pin in
    the source's coordinates rather than the grid's fails by name instead of
    regenerating quietly into a sample that demonstrates nothing.
    """

    def test_the_source_sits_unmoved_at_the_top_left_of_a_larger_grid(self) -> None:
        source = json.loads(_source_path("grown_grid").read_text("utf-8"))["rows"]
        grid = _rows_of("grown_grid")
        size = (
            int(_flag_value("grown_grid", "--rows")),
            int(_flag_value("grown_grid", "--cols")),
        )
        self.assertEqual((len(grid), len(grid[0])), size)
        self.assertGreater(size[0], len(source), "the sample exists to grow the rows")
        self.assertGreater(size[1], len(source[0]), "and to grow the columns")
        letters = [
            (row, col, letter)
            for row, line in enumerate(source)
            for col, letter in enumerate(line)
            if letter != cw_grid.BLOCK
        ]
        self.assertTrue(letters, "the sample exists to start from letters")
        for row, col, letter in letters:
            with self.subTest(cell=(row, col)):
                self.assertEqual(grid[row][col], letter)

    def test_the_pin_lies_in_cells_only_the_grown_grid_has(self) -> None:
        source = json.loads(_source_path("grown_grid").read_text("utf-8"))["rows"]
        feature = cw_feature.parse_feature(_flag_value("grown_grid", "--feature"))
        if feature.anchor is None:
            self.fail("the sample exists to pin an answer where the source has no cell")
        pinned = cw_grid.Run(
            row=feature.anchor.row,
            col=feature.anchor.col,
            direction=feature.anchor.direction,
            text=feature.answer,
        )
        self.assertEqual(
            cw_grid.find_answer(_rows_of("grown_grid"), feature.answer), pinned
        )
        beyond = [
            (row, col)
            for row, col in pinned.cells
            if row >= len(source) or col >= len(source[0])
        ]
        self.assertEqual(beyond, list(pinned.cells))


class TestAbsorbedGridSample(unittest.TestCase):
    """The committed absorbed grid shows what it is for: a source entry grown in place.

    These say the files still show `--absorb-entries` growing an entry, so a
    change that stopped growing it, moved a source letter while growing it, or
    ran the command without the flag fails by name instead of regenerating
    quietly into a sample that demonstrates nothing.
    """

    def test_every_source_letter_sits_unchanged_in_the_grid(self) -> None:
        source = json.loads(_source_path("absorbed_grid").read_text("utf-8"))["rows"]
        grid = _rows_of("absorbed_grid")
        letters = [
            (row, col, letter)
            for row, line in enumerate(source)
            for col, letter in enumerate(line)
            if letter != cw_grid.BLOCK
        ]
        self.assertTrue(letters, "the sample exists to start from letters")
        for row, col, letter in letters:
            with self.subTest(cell=(row, col)):
                self.assertEqual(grid[row][col], letter)

    def test_a_source_entry_is_absorbed_into_a_longer_bank_answer(self) -> None:
        self.assertIn("--absorb-entries", _CASES["absorbed_grid"])
        folder = samples_fixtures.SAMPLES / "absorbed_grid"
        source = json.loads(_source_path("absorbed_grid").read_text("utf-8"))["rows"]
        bank = json.loads((folder / "bank.json").read_text("utf-8"))
        answers = {entry["answer"] for entry in bank["entries"]}
        grid = cw_grid.runs_from_rows(_rows_of("absorbed_grid"))
        gone = [
            run
            for run in cw_grid.runs_from_rows(source)
            if run.text in answers and run not in grid
        ]
        self.assertTrue(gone, "the sample exists to grow a source entry")
        for entry in gone:
            with self.subTest(entry=entry.text):
                self.assertTrue(
                    any(
                        run.text in answers
                        and len(run.text) > len(entry.text)
                        and cw_reach.covers(entry, run.cells)
                        for run in grid
                    )
                )


if __name__ == "__main__":
    unittest.main()
