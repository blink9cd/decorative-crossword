"""End-to-end: a bank that declares no themes, run at a theme floor of zero.

A bank's `themes` map is required but may be empty, and each entry's `theme`
is optional -- so a wholly unthemed bank is legal input, and it fills at
`--min-themes 0`. No positive floor is reachable without a themed answer, so
pre-flight refuses such a run at a floor of one before a node is searched. The
tests here pin both halves: the refusal at a floor of one, and the grid at a
floor of zero.

A sibling of `test_cli.py` rather than a section of it: this project keeps each
Python file under 500 lines, and splits a grown suite into a named sibling
rather than letting one file run past that.
"""

import tempfile
import unittest

import decorative_crossword
from tests import cli_fixtures

#: Both sides of the grid, as the CLI takes it. Small on purpose: what these
#: tests prove is that a themeless bank reaches a grid at all, and a bigger
#: rectangle would buy nothing for that while costing search time on every run
#: of the suite.
_SIDE = "5"

#: The density ceiling these runs ask for. Chosen so the SEED placement alone
#: does not conform -- one five-letter answer leaves a 5x5 grid 80% blocked --
#: so a grid that comes back inside this window is one the search had to cross
#: a second answer into. Loose enough to be reached from two of them, so the
#: run still finishes in milliseconds.
_MAX_BLOCKED = "70"

#: The fewest answers a grid inside that window can hold: two crossing
#: five-letter answers fill nine of the twenty-five cells, for 64% blocked.
_MIN_PLACED = 2


def _themeless_fill(
    space: cli_fixtures.Workspace, floor: str, *extra: str
) -> list[str]:
    """A small-grid `fill` argv over the themeless bank at `--min-themes floor`."""
    argv = space.fill(*extra)
    argv[argv.index("--rows") + 1] = _SIDE
    argv[argv.index("--cols") + 1] = _SIDE
    argv[argv.index("--max-blocked") + 1] = _MAX_BLOCKED
    argv[argv.index("--min-themes") + 1] = floor
    return argv


class TestThemelessBank(cli_fixtures.QuietCase):
    """A themeless bank at a floor of zero, and the same bank at a floor of one."""

    def _workspace(self, folder: str) -> cli_fixtures.Workspace:
        """A workspace whose written bank is the themeless one."""
        return cli_fixtures.Workspace(folder, cli_fixtures.THEMELESS_BANK)

    def test_a_zero_floor_fills_a_grid_from_a_themeless_bank(self) -> None:
        # The load-bearing case: exit 0 on a bank with no themes. The grid is
        # read back rather than inferred from the exit code, which an empty
        # rectangle -- what the refusal path writes -- would not distinguish.
        with tempfile.TemporaryDirectory() as folder:
            space = self._workspace(folder)
            self.assertEqual(decorative_crossword.main(_themeless_fill(space, "0")), 0)
            placed = set(space.clues())
            self.assertGreaterEqual(len(placed), _MIN_PLACED)
            self.assertLessEqual(placed, set(cli_fixtures.THEMELESS_ANSWERS))
            self.assertEqual(len(space.rows()), int(_SIDE))

    def test_a_floor_of_one_still_refuses_the_same_bank(self) -> None:
        # The other half of the pair, and the reason the zero above is not
        # cosmetic: this bank cannot reach a floor of one. A relaxation that
        # stopped applying the floor at all would pass the test above and fail
        # this one.
        with tempfile.TemporaryDirectory() as folder:
            space = self._workspace(folder)
            self.assertEqual(decorative_crossword.main(_themeless_fill(space, "1")), 1)
            self.assertEqual(space.clues(), {})

    def test_the_caption_echoes_a_zero_floor_as_the_number_it_was_given(self) -> None:
        # The caption is a verbatim echo of the settings a reader cannot
        # recover from grid_source.json, and a floor of zero is a setting like
        # any other. Pinned so that substituting a word for the number becomes
        # a visible decision rather than a quiet one.
        with tempfile.TemporaryDirectory() as folder:
            space = self._workspace(folder)
            argv = _themeless_fill(space, "0", "--preview", str(space.svg))
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertIn(
                "theme floor: 0 theme(s) x 1 entry(s)",
                space.svg.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
