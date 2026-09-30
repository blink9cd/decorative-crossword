"""CLI tests for `fill --prefer-symmetry`: a ranking preference, never a filter.

Driven end to end through `decorative_crossword.main`, because the contract is at
the process boundary: which grid lands on disk, what the report says about it, and
that the flag reaches the choice without touching the walk.

The fixture is `small_square`'s committed bank on a 5x6 grid. Its search reaches
116 conforming grids, and the densest of them tie on everything else, so the
first found is kept today; one of the others matches 9 of its 15 rotated pairs
against the kept grid's 7, and every kind prefers it.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import cast

import cw_bank
import cw_config
import cw_search
import cw_symmetry
import decorative_crossword
from tests import cli_fixtures, samples_fixtures

#: The bank the fixture fills from, read and never written.
_BANK = samples_fixtures.SAMPLES / "small_square" / "bank.json"

#: The grid kept without the flag: the first of the densest found.
_FIRST = ["..P..W", ".HEDGE", "..T..T", "..A...", "WOLF.."]

#: The grid every kind prefers, tying the first on letters, ratings and themes.
_BALANCED = ["..P..W", ".HEDGE", "..T..T", ".RAIN.", "..L..."]

#: Each kind's line for `_BALANCED`, as the report states it.
_FIGURES = {
    "rotational": "Rotational symmetry: 9 of 15 cell pairs match.",
    "left-right": "Left-right symmetry: 9 of 15 cell pairs match.",
    "top-bottom": "Top-bottom symmetry: 10 of 12 cell pairs match.",
}

#: The report's count of grids compared: the walk's, which the flag never moves.
_COMPARED = re.compile(r"Chosen as the best of (\d+) conforming grid")


def _argv(out: Path, bank: Path = _BANK, *extra: str) -> list[str]:
    """The fixture's fill, written to `out`, plus `extra`."""
    return [
        "fill",
        "--bank",
        str(bank),
        "--out",
        str(out),
        "--seed",
        "1",
        "--rows",
        "5",
        "--cols",
        "6",
        "--min-blocked",
        "0",
        "--max-blocked",
        "70",
        "--min-themes",
        "0",
        "--time-budget",
        "0",
        "--max-steps",
        "4000",
        *extra,
    ]


def _rows(out: Path) -> list[str]:
    """The grid rows a run wrote to `out`."""
    rows: list[str] = json.loads(out.read_text("utf-8"))["rows"]
    return rows


class TestPreferSymmetry(cli_fixtures.QuietCase):
    """The flag chooses among tied grids, and the report says so."""

    def _fill(self, *extra: str) -> list[str]:
        """Run the fixture's fill with `extra`, assert exit 0, return the rows."""
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "grid_source.json"
            self.assertEqual(decorative_crossword.main(_argv(out, _BANK, *extra)), 0)
            return _rows(out)

    def test_without_the_flag_the_first_tied_grid_stays(self) -> None:
        self.assertEqual(self._fill(), _FIRST)
        self.assertNotIn("symmetry", self.printed.lower())

    def test_the_flag_chooses_the_more_balanced_of_tied_grids(self) -> None:
        self.assertEqual(self._fill("--prefer-symmetry", "rotational"), _BALANCED)

    def test_the_flag_changes_the_choice_and_never_the_walk(self) -> None:
        # The same number of grids compared, with and without: the walk that
        # found them is the same one, and only the grid kept differs.
        self._fill()
        self._fill("--prefer-symmetry", "rotational")
        counts = _COMPARED.findall(self.printed)
        self.assertEqual(counts, ["116", "116"])

    def test_the_report_names_the_level_and_the_chosen_grid_s_pairs(self) -> None:
        self._fill("--prefer-symmetry", "rotational")
        self.assertIn(
            "most letters, then --prefer answers, then rotational symmetry, then "
            "themed entries.",
            self.printed,
        )
        self.assertIn(_FIGURES["rotational"], self.printed.splitlines())

    def test_each_kind_names_its_own_figure(self) -> None:
        for kind in cw_symmetry.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self._fill("--prefer-symmetry", kind), _BALANCED)
                self.assertIn(_FIGURES[kind], self.printed.splitlines())

    def test_the_level_follows_the_worst_rating_in_a_rated_bank(self) -> None:
        document = json.loads(_BANK.read_text("utf-8"))
        document["entries"][0]["rating"] = 4
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, document)
            argv = _argv(space.out, space.bank, "--prefer-symmetry", "rotational")
            self.assertEqual(decorative_crossword.main(argv), 0)
        self.assertIn(
            "then worst rating, then rotational symmetry, then themed entries.",
            self.printed,
        )

    def test_the_figure_is_the_ranked_grid_s_before_islands(self) -> None:
        # Island letters are laid after the choice and change the pattern, so
        # the written grid reads differently; the report names what was ranked.
        written = self._fill("--prefer-symmetry", "rotational", "--island-letters", "A")
        self.assertNotEqual(written, _BALANCED)
        self.assertNotEqual(cw_symmetry.matching_pairs(written, "rotational"), (9, 15))
        self.assertIn(_FIGURES["rotational"], self.printed.splitlines())

    def test_without_a_look_ahead_the_figure_still_describes_the_grid(self) -> None:
        # Nothing is compared, so the Chosen sentence is absent; the figure
        # describes the one grid kept, as the preferred-answers line does.
        self._fill("--prefer-symmetry", "rotational", "--look-ahead", "0")
        self.assertNotIn("Chosen as", self.printed)
        self.assertIn(
            "Rotational symmetry: 8 of 15 cell pairs match.", self.printed.splitlines()
        )


def _search(kind: str | None) -> cw_search.SearchOutcome:
    """The fixture's search, straight through `cw_search`, under `kind` or none."""
    config = cw_config.FillConfig(
        rows=5,
        cols=6,
        seed=1,
        min_blocked=0.0,
        max_blocked=70.0,
        min_themes=0,
        min_entries_per_theme=cast(int, cw_config.DEFAULTS["min_entries_per_theme"]),
        time_budget=0.0,
        max_steps=4000,
        features=(),
        look_ahead=cast(int, cw_config.DEFAULTS["look_ahead"]),
        prefer=(),
        island_letters=(),
        prefer_symmetry=kind,
    )
    return cw_search.search(cw_bank.load_bank(_BANK), config)


class TestTheWalkUnderTheFlag(unittest.TestCase):
    """The flag moves which grid is kept, never how many nodes found them."""

    def test_every_kind_walks_the_same_nodes_and_keeps_another_grid(self) -> None:
        # A reordered walk that happened to reach the same set of grids would
        # keep the compared count and move the node count; both are pinned.
        plain = _search(None)
        self.assertEqual(plain.rows, tuple(_FIRST))
        for kind in cw_symmetry.KINDS:
            with self.subTest(kind=kind):
                balanced = _search(kind)
                self.assertEqual(balanced.steps, plain.steps)
                self.assertEqual(balanced.compared, plain.compared)
                self.assertEqual(balanced.look_ahead_cut, plain.look_ahead_cut)
                self.assertEqual(balanced.rows, tuple(_BALANCED))


class TestPreferSymmetryRefusals(cli_fixtures.QuietCase):
    """A kind the table does not hold never reaches a search."""

    def test_an_unknown_kind_is_refused_by_the_parser(self) -> None:
        # argparse's `choices=` refuses it: SystemExit 2, naming the kinds.
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "grid_source.json"
            with self.assertRaises(SystemExit) as caught:
                decorative_crossword.main(
                    _argv(out, _BANK, "--prefer-symmetry", "diagonal")
                )
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse(out.exists())
        self.assertIn("invalid choice: 'diagonal'", self.errors)
        self.assertIn("rotational", self.errors)
