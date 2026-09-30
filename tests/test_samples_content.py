"""What the pinned and banked `fill` samples are FOR, read back out of their committed files.

`tests/test_samples.py` regenerates every `fill` sample and compares bytes, which
proves each file is what the tool produces today. It does not say a file still
shows what its sample exists to show: a pin moved by one cell, a preference or a
rating that stopped deciding, or a second `--bank` no longer read would each
regenerate into new files that match themselves. These cases read the committed
grids of `name_grid`, `best_grid`, `rated_grid`, `symmetric_grid`, `two_banks` and
`phrase_grid` back instead;
`tests/test_samples_source.py` does the same for the `--source` samples.

The command table stays in `tests/test_samples.py`, the one place a machine pins
the README's commands, and is read from there together with the names its
commands share, so each case reads the very flags the regeneration runs with.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
import cw_answer
import cw_feature
import cw_grid
import cw_symmetry
from tests import cli_fixtures, samples_fixtures
from tests.test_samples import (
    _BEST_GRID_ISLAND_LETTERS,
    _BEST_GRID_PREFER,
    _CASES,
    _NAME_GRID_PINS,
    _PHRASE_GRID_FEATURES,
    _SYMMETRIC_GRID_KIND,
    _TWO_BANKS_NAMES,
    _TWO_BANKS_SECOND,
    _rows_of,
)

#: The one answer `rated_grid`'s bank rates, at the bottom of the scale. That
#: rating is the only thing separating its bank from `name_grid`'s, so it is
#: what the grid choice below is pinned to.
_RATED_GRID_LOW = "NED"


class TestNameGridSample(unittest.TestCase):
    """The committed name grid holds each pin exactly where its command puts it.

    The byte comparison in `tests/test_samples.py` proves the file is what the
    tool produces; it does not say the file shows what the sample is FOR. A
    regression that moved every pin by one cell would regenerate a new
    committed grid that still matched itself -- this reads the pins back out of
    it.
    """

    def test_each_pin_sits_at_its_anchor(self) -> None:
        rows = _rows_of("name_grid")
        for text in _NAME_GRID_PINS:
            with self.subTest(pin=text):
                feature = cw_feature.parse_feature(text)
                if feature.anchor is None:
                    self.fail(f"{text!r} names no cell, so it demonstrates no pin")
                self.assertEqual(
                    cw_grid.find_answer(rows, feature.answer),
                    cw_grid.Run(
                        row=feature.anchor.row,
                        col=feature.anchor.col,
                        direction=feature.anchor.direction,
                        text=feature.answer,
                    ),
                )


class TestBestGridSample(cli_fixtures.QuietCase):
    """The committed best grid shows what it is FOR: a preference that decided, and islands.

    The byte comparison in `tests/test_samples.py` proves the files are what
    the tool produces. These say the files still show the two flags doing their
    jobs, so a change that stopped the preference deciding, or stopped laying
    islands, fails by name instead of regenerating quietly into a sample that
    demonstrates nothing.
    """

    def test_the_preferred_answer_is_an_entry(self) -> None:
        self.assertIsNotNone(
            cw_grid.find_answer(_rows_of("best_grid"), _BEST_GRID_PREFER)
        )

    def test_every_letter_outside_an_entry_is_an_island_letter(self) -> None:
        rows = _rows_of("best_grid")
        covered = {cell for run in cw_grid.runs_from_rows(rows) for cell in run.cells}
        lone = [
            rows[row][col]
            for row in range(len(rows))
            for col in range(len(rows[row]))
            if rows[row][col] != cw_grid.BLOCK and (row, col) not in covered
        ]
        self.assertTrue(lone, "the sample exists to show an island")
        self.assertLessEqual(set(lone), set(_BEST_GRID_ISLAND_LETTERS))

    def test_without_the_preference_the_search_keeps_another_grid(self) -> None:
        # The same command with --prefer removed. Islands are a function of the
        # grid, so the rows can only differ if the SEARCH kept another grid --
        # which is the preference deciding, not decoration.
        argv = list(_CASES["best_grid"])
        at = argv.index("--prefer")
        del argv[at : at + 2]
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "grid_source.json"
            bank = samples_fixtures.SAMPLES / "best_grid" / "bank.json"
            command = ["fill", "--bank", str(bank), "--out", str(out), *argv]
            self.assertEqual(decorative_crossword.main(command), 0)
            rows = json.loads(out.read_text("utf-8"))["rows"]
        self.assertNotEqual(rows, _rows_of("best_grid"))


class TestRatedGridSample(cli_fixtures.QuietCase):
    """The committed rated grid shows what it is FOR: one rating that decided.

    The byte comparison in `tests/test_samples.py` proves the files are what
    the tool produces. This says they still show a rating choosing between two
    tied grids, so a change that stopped the rating deciding fails by name
    instead of regenerating quietly into a sample that demonstrates nothing.
    """

    def test_without_the_rating_the_search_keeps_another_grid(self) -> None:
        # The same command against the same bank with its one rating removed.
        # The two grids hold the same number of letters, so what moves the choice
        # is the rating alone: unrated, the grid found first keeps NED; rated at
        # the bottom of the scale, NED loses to the tied grid that does without it.
        bank = json.loads(
            (samples_fixtures.SAMPLES / "rated_grid" / "bank.json").read_text("utf-8")
        )
        for entry in bank["entries"]:
            entry.pop("rating", None)
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, bank)
            command = [
                "fill",
                "--bank",
                str(space.bank),
                "--out",
                str(space.out),
                *_CASES["rated_grid"],
            ]
            self.assertEqual(decorative_crossword.main(command), 0)
            unrated = space.rows()
        rated = _rows_of("rated_grid")
        answers = [
            {run.text for run in cw_grid.runs_from_rows(rows)}
            for rows in (unrated, rated)
        ]
        letters = [
            sum(cell != cw_grid.BLOCK for row in rows for cell in row)
            for rows in (unrated, rated)
        ]
        self.assertNotEqual(unrated, rated)
        self.assertIn(_RATED_GRID_LOW, answers[0])
        self.assertNotIn(_RATED_GRID_LOW, answers[1])
        self.assertEqual(letters[0], letters[1])


class TestSymmetricGridSample(cli_fixtures.QuietCase):
    """The committed symmetric grid shows what it is FOR: the preference deciding.

    Without this, a change that stopped the level deciding would regenerate the
    sample into the grid the search found first, which matches itself as well.
    """

    def test_without_the_flag_the_search_keeps_a_less_balanced_grid(self) -> None:
        # The same command with --prefer-symmetry removed. Both grids hold the
        # same number of letters, so only the balance level can have chosen.
        argv = list(_CASES["symmetric_grid"])
        at = argv.index("--prefer-symmetry")
        del argv[at : at + 2]
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "grid_source.json"
            bank = samples_fixtures.SAMPLES / "symmetric_grid" / "bank.json"
            command = ["fill", "--bank", str(bank), "--out", str(out), *argv]
            self.assertEqual(decorative_crossword.main(command), 0)
            first: list[str] = json.loads(out.read_text("utf-8"))["rows"]
        chosen = _rows_of("symmetric_grid")
        letters = [
            sum(cell != cw_grid.BLOCK for row in rows for cell in row)
            for rows in (first, chosen)
        ]
        self.assertNotEqual(first, chosen)
        self.assertEqual(letters[0], letters[1])
        self.assertGreater(
            cw_symmetry.matching_pairs(chosen, _SYMMETRIC_GRID_KIND),
            cw_symmetry.matching_pairs(first, _SYMMETRIC_GRID_KIND),
        )


class TestTwoBanksSample(cli_fixtures.QuietCase):
    """The committed two-bank grid shows what it is FOR: a grid neither bank makes alone.

    The byte comparison in `tests/test_samples.py` proves the files are what
    the tool produces. These say the grid still holds the second bank's
    answers, and that the command still needs both banks, so a change that
    quietly read only one --bank fails by name instead of regenerating into a
    sample that demonstrates nothing.
    """

    def test_every_answer_of_the_second_bank_is_an_entry(self) -> None:
        second = json.loads(_TWO_BANKS_SECOND.read_text("utf-8"))
        answers = [entry["answer"] for entry in second["entries"]]
        self.assertEqual(sorted(answers), sorted(_TWO_BANKS_NAMES))
        rows = _rows_of("two_banks")
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertIsNotNone(cw_grid.find_answer(rows, answer))

    def test_neither_bank_runs_the_command_alone(self) -> None:
        # The main bank lacks both featured names, and the names bank uses a
        # theme only the main bank declares, so either one alone is exit 2.
        argv = list(_CASES["two_banks"])
        at = argv.index("--bank")
        del argv[at : at + 2]
        main = samples_fixtures.SAMPLES / "two_banks" / "bank.json"
        for bank in (main, _TWO_BANKS_SECOND):
            with self.subTest(bank=bank.name), tempfile.TemporaryDirectory() as folder:
                out = Path(folder) / "grid_source.json"
                command = ["fill", "--bank", str(bank), "--out", str(out), *argv]
                self.assertEqual(decorative_crossword.main(command), 2)
                self.assertFalse(out.exists())


class TestPhraseGridSample(unittest.TestCase):
    """The committed phrase grid lays each written answer by its letters, and clues it.

    Its bank's `sayings` theme holds an answer for each shape the bank accepts
    beyond plain letters -- a space, a hyphen, an apostrophe, a space beside
    apostrophes -- plus one left unclued, and the command features two of them
    as written.
    """

    def test_every_saying_is_an_entry_by_its_letters(self) -> None:
        bank = json.loads(
            (samples_fixtures.SAMPLES / "phrase_grid" / "bank.json").read_text(
                encoding="utf-8"
            )
        )
        sayings = [
            entry["answer"]
            for entry in bank["entries"]
            if entry.get("theme") == "sayings"
        ]
        self.assertTrue(set(_PHRASE_GRID_FEATURES) <= set(sayings))
        rows = _rows_of("phrase_grid")
        for written in sayings:
            with self.subTest(answer=written):
                letters = cw_answer.grid_form(written)
                self.assertIsNotNone(cw_grid.find_answer(rows, letters))

    def test_each_clued_saying_ends_with_its_enumeration(self) -> None:
        document = json.loads(
            (samples_fixtures.SAMPLES / "phrase_grid" / "grid_source.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {
            "HELLOTHERE": "Friendly greeting (5,5)",
            "ATTABOY": "Well done (4-3)",
            "ROCKNROLL": "Music of the fifties (4,1,4)",
            "OCLOCK": "On the hour",
            "NOONE": "",
        }
        clues = document["clues"]
        self.assertEqual({key: clues[key]["clue"] for key in expected}, expected)


if __name__ == "__main__":
    unittest.main()
