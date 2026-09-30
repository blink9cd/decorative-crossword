"""CLI tests for a repeated and anchored `fill --feature`.

`--feature` repeats, and each value is `ANSWER` or `ANSWER@ROW,COL,DIR`. These
drive `decorative_crossword.main` end to end, because what is under test is the
flag's contract at the process boundary: which exit code a malformed or
contradictory pin produces, whether a refused run leaves a file behind, and
whether the grid on disk holds every pin where it was asked for.

Several cases give the flags in an order chosen so that a last-wins
`--feature` -- argparse's default for a repeated flag -- would pass the wrong
one: the answer that has to be checked comes first, where a last-wins flag
drops it.

The last classes pin the parser end of the same flags: an omitted one parses
to None, and `--help` does not stamp that as `(default: None)` -- nor any
default on a required option, on the oldest interpreter this project supports
as on the newest.
"""

import argparse
import tempfile
import unittest

import cw_grid
import cw_help
import decorative_crossword
from tests import cli_fixtures


class TestRepeatedFeature(cli_fixtures.QuietCase):
    """Every `--feature` given is a hard constraint, not only the last one."""

    def test_every_repeated_feature_is_placed_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--feature", "CHALK", "--feature", "BRAVO")
            self.assertEqual(decorative_crossword.main(argv), 0)
            for answer in ("CHALK", "BRAVO"):
                with self.subTest(answer=answer):
                    self.assertIsNotNone(cw_grid.find_answer(space.rows(), answer))
                    self.assertIn(f"Featured answer {answer}:", self.printed)

    def test_a_first_feature_absent_from_the_bank_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--feature", "NOPE", "--feature", "CHALK")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("'NOPE'", self.errors)
            self.assertFalse(space.out.exists())

    def test_the_screen_dropping_a_first_feature_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill(
                "--feature",
                "AMBER",
                "--feature",
                "CHALK",
                "--excluded-terms",
                str(space.excluded("amber")),
            )
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("'AMBER'", self.errors)
            self.assertFalse(space.out.exists())


class TestAnchoredFeature(cli_fixtures.QuietCase):
    """`ANSWER@ROW,COL,DIR` pins an answer to its cells, or is refused."""

    def test_anchored_features_land_on_their_cells_and_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill(
                "--feature", "ALPHA@0,0,across", "--feature", "AMBER@0,0,down"
            )
            self.assertEqual(decorative_crossword.main(argv), 0)
            rows = space.rows()
            self.assertEqual(
                cw_grid.find_answer(rows, "ALPHA"),
                cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="ALPHA"),
            )
            self.assertEqual(
                cw_grid.find_answer(rows, "AMBER"),
                cw_grid.Run(row=0, col=0, direction=cw_grid.DOWN, text="AMBER"),
            )
            self.assertIn(
                "Featured answer ALPHA: across, (0, 0) to (0, 4).", self.printed
            )
            self.assertIn(
                "Featured answer AMBER: down, (0, 0) to (4, 0).", self.printed
            )

    def test_a_malformed_anchor_exits_two_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--feature", "ALPHA@0,0")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("--feature", self.errors)
            self.assertFalse(space.out.exists())

    def test_an_anchor_running_off_the_grid_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--feature", "ALPHA@0,5,across")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("9x9", self.errors)
            self.assertFalse(space.out.exists())

    def test_anchors_that_disagree_on_a_cell_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill(
                "--feature", "ALPHA@0,0,across", "--feature", "BRAVO@0,0,down"
            )
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("(0, 0)", self.errors)
            self.assertFalse(space.out.exists())

    def test_pins_that_run_into_each_other_exit_two(self) -> None:
        # CHALK ends at (0, 4) and CRANE starts at (0, 5), so the top row reads
        # CHALKC: neither pin would be an entry, whatever the bank holds. The
        # flags decide that alone, which puts it on the exit-2 line -- not on
        # pre-flight's exit 1, where a bank lacking CHALKC would otherwise send
        # it with a sentence about the bank rather than about the pins.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill(
                "--feature", "CHALK@0,0,across", "--feature", "CRANE@0,5,down"
            )
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn("CHALK@0,0,across", self.errors)
            self.assertIn("CRANE@0,5,down", self.errors)
            self.assertFalse(space.out.exists())

    def test_pins_that_break_the_one_rule_exit_one_naming_the_run(self) -> None:
        # Exit 1, not 2: both flags are well formed and agree cell for cell, and
        # the fault is that THIS bank holds no AB. The report names the run, and
        # the file written is the empty board rather than the illegal one.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill(
                "--feature", "ALPHA@0,0,across", "--feature", "BRAVO@1,0,across"
            )
            self.assertEqual(decorative_crossword.main(argv), 1)
            self.assertIn("'AB'", self.printed)
            self.assertEqual(space.rows(), [cw_grid.BLOCK * 9] * 9)


class TestNoneDefaultsInHelp(cli_fixtures.QuietCase):
    """`--help` stamps no `(default: None)`: None means "not given", not a value.

    That real defaults still render in the formatter's own form is
    `test_cli.py`'s `TestParser`, which reads them off the live DEFAULTS.
    """

    def _help_for(self, subcommand: str) -> str:
        """Return only this subcommand's --help, whitespace-normalized.

        Sliced off the captured stdout, which accumulates across calls in one
        test. Normalized because argparse wraps "(default:" and its value onto
        two lines wherever the width runs out.
        """
        already = len(self.printed)
        with self.assertRaises(SystemExit):
            decorative_crossword.main([subcommand, "--help"])
        return " ".join(self.printed[already:].split())

    def test_no_subcommand_s_help_renders_a_none_default(self) -> None:
        for subcommand in ("fill", "preview", "shade", "gaps"):
            with self.subTest(subcommand=subcommand):
                self.assertNotIn("(default: None)", self._help_for(subcommand))

    def test_a_none_default_option_keeps_its_help_text(self) -> None:
        # Dropping the suffix must not drop the sentence it was appended to.
        self.assertIn("corner. Off unless given.", self._help_for("fill"))


class _PreFixDefaultsFormatter(argparse.ArgumentDefaultsHelpFormatter):
    """Stands in for argparse before 3.13: a default on every action, required or not.

    Only a suppressed default is skipped, as it was then too -- `--help`'s own is
    one, and argparse cannot interpolate a default it has suppressed.
    """

    def _get_help_string(self, action: argparse.Action) -> str | None:
        if action.default is argparse.SUPPRESS:
            return action.help
        return f"{action.help} (default: %(default)s)"


class _OverPreFix(cw_help.HelpFormatter, _PreFixDefaultsFormatter):
    """This project's formatter over that base, so its `super()` reaches the old one."""


class TestRequiredOptionsAtTheFloor(unittest.TestCase):
    """A required option states no default, even under argparse's pre-3.13 stamp.

    This project's floor is below argparse's own fix. A host newer than the fix
    already leaves the stamp off, so a test against the stock formatter there
    would pass with the guard deleted. The old behavior is therefore stood in
    for rather than hoped for, and the test means the same on every host.
    """

    def _help(self, *, required: bool) -> str:
        parser = argparse.ArgumentParser(prog="demo", formatter_class=_OverPreFix)
        parser.add_argument("--flag", required=required, default=7, help="Help text.")
        return " ".join(parser.format_help().split())

    def test_a_required_option_states_no_default(self) -> None:
        # A required option can never fall back to its default, so naming one
        # would describe a value no run of the tool can ever take.
        self.assertNotIn("(default: 7)", self._help(required=True))

    def test_an_optional_one_still_states_its_default(self) -> None:
        self.assertIn("(default: 7)", self._help(required=False))


class TestRepeatableOptionsParse(cli_fixtures.QuietCase):
    """`--feature`, `--prefer` and `--island-letters` keep their None default.

    `cw_commands._config_from` reads `args.feature or ()`, `args.prefer or ()`
    and `args.island_letters is None`, so an omitted option must parse to None
    and a repeated one to a fresh list per parse.
    """

    def test_omitted_options_parse_to_none(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            argv = cli_fixtures.Workspace(folder).fill()
            args = decorative_crossword.build_parser().parse_args(argv)
            for dest in ("feature", "prefer", "island_letters"):
                with self.subTest(dest=dest):
                    self.assertIsNone(getattr(args, dest))

    def test_repeated_options_accumulate_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            flags = ("--feature", "CHALK", "--prefer", "BOY")
            argv = cli_fixtures.Workspace(folder).fill(
                *flags, "--feature", "BRAVO", "--prefer", "ALPHA"
            )
            args = decorative_crossword.build_parser().parse_args(argv)
            self.assertEqual(args.feature, ["CHALK", "BRAVO"])
            self.assertEqual(args.prefer, ["BOY", "ALPHA"])

    def test_nothing_carries_from_one_parse_to_the_next(self) -> None:
        # One parser, two parses: an `append` default shared between them would
        # show the first run's answers in the second.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            parser = decorative_crossword.build_parser()
            parser.parse_args(
                space.fill(
                    "--feature", "CHALK", "--prefer", "BOY", "--island-letters", "AI"
                )
            )
            second = parser.parse_args(space.fill("--feature", "BRAVO"))
            self.assertEqual(second.feature, ["BRAVO"])
            self.assertIsNone(second.prefer)
            self.assertIsNone(second.island_letters)
