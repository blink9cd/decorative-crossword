"""Tests for `fill --max-two-letter`: the flag reaches acceptance, end to end.

Driven through `main` because what these cases prove is the WIRING -- parser, to
`FillConfig`, to `cw_accept.missed_constraints` -- and each link of that chain is
tested on its own elsewhere (`test_search_parts.py`, `test_config.py`). A flag that
parsed but never reached the config would pass every one of those, and a search
would go on accepting grids the caller had capped.
"""

import tempfile

import decorative_crossword

from tests import cli_fixtures

#: Two-letter answers only, so every grid this bank can make holds a two-letter
#: entry and a cap of zero leaves it nothing that conforms.
_TWO_LETTER_BANK: dict[str, object] = {
    "themes": {"a": {"label": "A", "summary": "The only theme"}},
    "entries": [{"answer": answer, "theme": "a"} for answer in ("AT", "TO")],
}


def _small(argv: list[str]) -> list[str]:
    """`argv` at 3x3: the bank is two words, and a 9x9 walk would only cost time."""
    for flag in ("--rows", "--cols"):
        argv[argv.index(flag) + 1] = "3"
    return argv


class TestMaxTwoLetter(cli_fixtures.QuietCase):
    """The cap is a constraint the run is held to, named when it is missed."""

    def test_a_cap_the_bank_cannot_meet_is_a_miss_that_names_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _TWO_LETTER_BANK)
            code = decorative_crossword.main(
                _small(space.fill("--max-two-letter", "0"))
            )
        self.assertEqual(code, 1)
        self.assertIn("two-letter entries, over the requested cap of 0", self.printed)

    def test_the_same_request_without_the_flag_conforms(self) -> None:
        # The control for the case above: the miss there is the cap's, not the bank's.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _TWO_LETTER_BANK)
            code = decorative_crossword.main(_small(space.fill()))
        self.assertEqual(code, 0)
        self.assertNotIn("over the requested cap", self.printed)

    def test_a_negative_cap_is_refused_naming_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _TWO_LETTER_BANK)
            code = decorative_crossword.main(
                _small(space.fill("--max-two-letter", "-1"))
            )
        self.assertEqual(code, 2)
        self.assertIn("--max-two-letter", self.errors)

    def test_help_names_the_flag(self) -> None:
        with self.assertRaises(SystemExit):
            decorative_crossword.main(["fill", "--help"])
        self.assertIn("--max-two-letter", self.printed)
