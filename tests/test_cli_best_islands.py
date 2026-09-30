"""CLI tests for choosing the best grid and for island letters.

`--look-ahead`, `--prefer`, a bank's answer ratings and `--island-letters` driven
end to end through `decorative_crossword.main`, because what is under test is each
one's contract at the process boundary: which exit code a bad value produces, and
what lands in the grid on disk and in the report beside it.
"""

import tempfile
from collections.abc import Mapping

import cw_bank
import decorative_crossword
from tests import cli_fixtures
from tests import interlock_fixtures as grids


def _bank(
    extra: tuple[str, ...] = (), ratings: Mapping[str, int] | None = None
) -> dict[str, object]:
    """The interlock fixture's answers, plus `extra`, as a bank file's contents.

    `ratings` rates the answers it names and leaves every other one unrated.
    """
    rated = ratings or {}
    return {
        "themes": {},
        "entries": [
            {"answer": answer, **({"rating": rated[answer]} if answer in rated else {})}
            for answer in (*grids.ANSWERS, *extra)
        ],
    }


def _argv(space: cli_fixtures.Workspace, *extra: str) -> list[str]:
    """A fill of the pinned interlock grid at its own density, plus `extra`."""
    pins = [
        arg
        for run in grids.pinned_lines()
        for arg in ("--feature", f"{run.text}@{run.row},{run.col},{run.direction}")
    ]
    argv = space.fill(*pins, *extra)
    for flag, value in (
        ("--rows", "5"),
        ("--cols", "5"),
        ("--max-blocked", str(grids.TARGET_BLOCKED)),
        ("--min-themes", "0"),
    ):
        argv[argv.index(flag) + 1] = value
    return argv


class TestBestGrid(cli_fixtures.QuietCase):
    """`--prefer` decides between tied fills, and the report says what was compared."""

    def test_a_preferred_answer_chooses_between_tied_fills(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank(grids.ALTERNATE_ANSWERS))
            argv = _argv(space, "--prefer", "VST")
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(space.rows(), list(grids.ALTERNATE))
            self.assertIn("Preferred answers placed: VST", self.printed)

    def test_the_report_says_how_many_grids_it_compared(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank(grids.ALTERNATE_ANSWERS))
            self.assertEqual(decorative_crossword.main(_argv(space)), 0)
            self.assertIn("best of", self.printed)

    def test_the_report_says_when_a_budget_cut_the_look_ahead_short(self) -> None:
        # At 60% the pinned board conforms at the first node, so the look-ahead
        # opens at once -- and a three-node cap closes the run inside it.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space)
            argv[argv.index("--max-blocked") + 1] = "60"
            argv[argv.index("--max-steps") + 1] = "3"
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertIn("cut short", self.printed)

    def test_a_negative_look_ahead_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            self.assertEqual(
                decorative_crossword.main(_argv(space, "--look-ahead", "-1")), 2
            )
            # The explanation, not just the flag's name: argparse names an
            # unknown flag too, and exits 2 for it, so asserting only those two
            # would pass on a tool that has no such option at all.
            self.assertIn("--look-ahead must not be negative", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_preferred_answer_absent_from_the_bank_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            self.assertEqual(
                decorative_crossword.main(_argv(space, "--prefer", "NOPE")), 2
            )
            self.assertIn("'NOPE'", self.errors)

    def test_an_answer_preferred_twice_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank(grids.ALTERNATE_ANSWERS))
            argv = _argv(space, "--prefer", "VST", "--prefer", "VST")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("twice", self.errors)

    def test_the_screen_dropping_a_preferred_answer_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank(grids.ALTERNATE_ANSWERS))
            argv = _argv(
                space, "--prefer", "VST", "--excluded-terms", str(space.excluded("vst"))
            )
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("'VST'", self.errors)


class TestRatings(cli_fixtures.QuietCase):
    """A bank's ratings choose between tied fills; a malformed one refuses the run."""

    def test_a_low_rating_on_one_fill_chooses_the_other(self) -> None:
        # The two fills differ only in RST and HMR against VST and HMV. Rating
        # either side low chooses the other, whichever fill the walk reaches first.
        for low, chosen in (("RST", grids.ALTERNATE), ("VST", grids.TARGET)):
            with self.subTest(low=low), tempfile.TemporaryDirectory() as folder:
                bank = _bank(grids.ALTERNATE_ANSWERS, {low: cw_bank.MIN_RATING})
                space = cli_fixtures.Workspace(folder, bank)
                self.assertEqual(decorative_crossword.main(_argv(space)), 0)
                self.assertEqual(space.rows(), list(chosen))

    def test_the_report_names_the_chosen_grids_worst_rated_answer(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            bank = _bank(grids.ALTERNATE_ANSWERS, {"RST": 1, "VST": 2})
            space = cli_fixtures.Workspace(folder, bank)
            self.assertEqual(decorative_crossword.main(_argv(space)), 0)
            self.assertIn("then worst rating, then themed entries.", self.printed)
            self.assertIn("Worst rating in the grid: 2 -- VST.", self.printed)

    def test_rating_every_answer_alike_writes_the_unrated_grid(self) -> None:
        # A uniform rating ties every grid on the rating level, so the grid on disk
        # is the unrated bank's byte for byte -- and no rating reaches the document.
        answers = (*grids.ANSWERS, *grids.ALTERNATE_ANSWERS)
        uniform: dict[str, int] = dict.fromkeys(answers, cw_bank.MAX_RATING)
        written: list[bytes] = []
        for ratings in ({}, uniform):
            with tempfile.TemporaryDirectory() as folder:
                bank = _bank(grids.ALTERNATE_ANSWERS, ratings)
                space = cli_fixtures.Workspace(folder, bank)
                self.assertEqual(decorative_crossword.main(_argv(space)), 0)
                written.append(space.out.read_bytes())
        self.assertEqual(written[0], written[1])
        self.assertNotIn(b"rating", written[1])

    def test_a_rating_off_the_scale_exits_two_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank(ratings={"RST": 6}))
            self.assertEqual(decorative_crossword.main(_argv(space)), 2)
            self.assertIn("'RST'", self.errors)
            self.assertIn("1 to 5", self.errors)
            self.assertFalse(space.out.exists())


class TestIslands(cli_fixtures.QuietCase):
    """`--island-letters` puts a lone letter in the corner, and only when asked."""

    def test_island_letters_fill_the_corner_and_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space, "--island-letters", "aix")
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(space.rows()[0], "A.ABC")
            self.assertIn("A at (0, 0)", self.printed)

    def test_the_report_describes_the_grid_as_written(self) -> None:
        # The island at (0, 0) is a letter on disk and in the preview, so the
        # report counts it too: 3 of 25 cells blocked, not the search's 4.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space, "--island-letters", "aix")
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertIn(
                "Grid 5x5: 22 filled cells, 12.0% blocked (requested 0.0-16.0%).",
                self.printed.splitlines(),
            )

    def test_an_island_that_would_break_the_floor_is_not_laid(self) -> None:
        # At --min-blocked 16 the grid's 4 blocked cells are all the floor
        # allows: the island would leave 3, 12%, and exit 0 must still mean
        # the written grid conforms. The report names the cell it left.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space, "--island-letters", "aix")
            argv[argv.index("--min-blocked") + 1] = "16"
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(space.rows()[0], "..ABC")
            self.assertIn(
                "Islands: none laid -- each would take the grid under the requested "
                "16.0% floor: (0, 0).",
                self.printed.splitlines(),
            )

    def test_an_island_that_lands_exactly_on_the_floor_is_laid(self) -> None:
        # The other side of the floor: at --min-blocked 12 the island leaves 3
        # of 25 cells blocked, exactly 12%, which conforms. So it is laid, and
        # nothing is named as declined.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space, "--island-letters", "aix")
            argv[argv.index("--min-blocked") + 1] = "12"
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(space.rows()[0], "A.ABC")
            self.assertIn(
                "Islands (lone letters in no entry, laid after the grid was chosen): "
                "A at (0, 0).",
                self.printed.splitlines(),
            )
            self.assertNotIn("Not laid", self.printed)

    def test_the_floor_is_counted_over_the_unmasked_cells(self) -> None:
        # (4, 3) is drawn out of the grid, so 3 of the 24 cells left are blocked:
        # 12.5%, and the island would leave 2, 8.3%, under a 12% floor. Counted
        # over all 25 cells, the masked one a block among them, 4 blocked would
        # seem to spare one -- 3 of 25 is exactly 12% -- and the island would be
        # laid through the floor the grid is judged by.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            picture = space.mask(".....", ".....", ".....", ".....", "...X.")
            argv = _argv(space, "--island-letters", "aix", "--mask", str(picture))
            argv[argv.index("--min-blocked") + 1] = "12"
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(space.rows()[0], "..ABC")
            self.assertIn(
                "Islands: none laid -- each would take the grid under the requested "
                "12.0% floor: (0, 0).",
                self.printed.splitlines(),
            )

    def test_without_island_letters_the_corner_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            self.assertEqual(decorative_crossword.main(_argv(space)), 0)
            self.assertEqual(space.rows()[0], "..ABC")
            self.assertNotIn("Island", self.printed)

    def test_island_letters_leave_a_best_effort_grid_alone(self) -> None:
        # No grid is 0% blocked, so the run misses. Islands decorate a grid the
        # search CHOSE; laid on a miss they would move the density figures the
        # report's remedies are computed from.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space, "--island-letters", "AIX")
            argv[argv.index("--max-blocked") + 1] = "0"
            self.assertEqual(decorative_crossword.main(argv), 1)
            self.assertEqual(space.rows()[0][0], ".")
            self.assertNotIn("Island", self.printed)

    def test_an_island_letter_that_is_no_word_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank())
            argv = _argv(space, "--island-letters", "AB")
            self.assertEqual(decorative_crossword.main(argv), 2)
            # The offending letter, for the reason the look-ahead case gives.
            self.assertIn("'B'", self.errors)
            self.assertFalse(space.out.exists())
