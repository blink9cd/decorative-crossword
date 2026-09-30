"""CLI tests: a number option given something that is not a finite number is refused.

`float` reads `nan`, `inf`, `-inf` and an overflowing `1e999` as numbers, and
each passes every range check downstream while meaning nothing: no comparison
with NaN is true, so a NaN bound is no bound at all, and a NaN or infinite
time budget is a wall clock that never runs out. So every float-typed option
refuses them while the command line is parsed -- exit 2, naming the option,
before any file is read -- exactly as it refuses text that is no number.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import tempfile

import decorative_crossword
from tests import cli_fixtures

#: Every float-typed option this tool takes. All three are `fill`'s: every
#: number the other subcommands take is a whole one.
_FLOAT_OPTIONS = ("--min-blocked", "--max-blocked", "--time-budget")

#: Spellings `float` accepts that are not finite numbers. Each is given as
#: `--option=value`, because argparse reads a separate `-inf` as an option name
#: and refuses it as a missing value before any type sees it.
_NOT_FINITE = ("nan", "inf", "-inf", "1e999")


class TestNotFinite(cli_fixtures.QuietCase):
    """Each float option refuses each non-finite value, and still reads a finite one."""

    def test_every_float_option_refuses_each_non_finite_value(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            for option in _FLOAT_OPTIONS:
                for value in _NOT_FINITE:
                    with self.subTest(option=option, value=value):
                        already = len(self.errors)
                        with self.assertRaises(SystemExit) as caught:
                            decorative_crossword.main(space.fill(f"{option}={value}"))
                        self.assertEqual(caught.exception.code, 2)
                        self.assertIn(
                            f"{option}: must be a finite number, got {value!r}",
                            self.errors[already:],
                        )
                        self.assertFalse(space.out.exists())

    def test_text_that_is_no_number_is_refused_in_the_same_words(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            with self.assertRaises(SystemExit) as caught:
                decorative_crossword.main(space.fill("--time-budget", "soon"))
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("--time-budget: must be a finite number", self.errors)

    def test_a_finite_value_still_parses(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            argv = cli_fixtures.Workspace(folder).fill(
                "--time-budget", "2.5", "--min-blocked", "1e1"
            )
            args = decorative_crossword.build_parser().parse_args(argv)
            self.assertEqual((args.time_budget, args.min_blocked), (2.5, 10.0))
