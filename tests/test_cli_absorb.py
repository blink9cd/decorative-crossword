"""Grouped suite: `fill --source --absorb-entries`, on the command line.

With the flag, a source entry the bank holds may grow into a longer bank answer
covering it, and the report names each one absorbed. A pin lying on an entry
still holds it; a pin lying along all of one chooses its growth; an entry kept
only because the source declares it never grows. These cases drive `main` end to
end, because what each proves is a process boundary: an exit code, the grid and
clues written, and the words the report prints.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest

import cw_grid
from tests import cli_fixtures
from tests.source_fixtures import SOURCE_NAME as _SOURCE_NAME
from tests.source_fixtures import SourceCase, filled, source_fill, write_source

#: Three themes, so the theme floor is met by more than one shape. JANE and
#: JANET share a theme; BOX and CUP share no letter with either, so nothing
#: else can cross the source.
_BANK: dict[str, object] = {
    "themes": cli_fixtures.THEMES,
    "entries": [
        {"answer": "JANE", "theme": "a", "clue": "A placeholder first name"},
        {"answer": "JANET", "theme": "a", "clue": "A longer placeholder name"},
        {"answer": "BOX", "theme": "b"},
        {"answer": "CUP", "theme": "c"},
    ],
}

#: JANE across the top of a 3x5: 73.3% blocked, over the 70% ceiling below.
#: JANET over it leaves 66.7%, inside it.
_JANE = ["JANE.", ".....", "....."]

#: The ceiling only a grown JANE clears.
_CEILING = ("--max-blocked", "70")

#: The flag this suite is about.
_ABSORB = "--absorb-entries"


class TestGrowingASourceEntry(SourceCase):
    """With the flag an entry the bank holds grows; without it, it is held."""

    def _run(
        self, rows: list[str], *extra: str
    ) -> tuple[int | None, list[str], cli_fixtures.Workspace]:
        """Run `fill` from `rows`; the exit code, the grid written, and the workspace."""
        folder = self.enterContext(tempfile.TemporaryDirectory())
        space = cli_fixtures.Workspace(folder, _BANK)
        path = write_source(space.root / _SOURCE_NAME, rows)
        code = self.run_main(source_fill(space, path, *_CEILING, *extra))
        return code, space.rows() if space.out.exists() else [], space

    def test_an_entry_grows_and_the_report_names_it(self) -> None:
        code, written, space = self._run(_JANE, _ABSORB)
        self.assertEqual(code, 0, self.errors)
        self.assertEqual(written[0], "JANET")
        self.assertLessEqual(filled(_JANE).items(), filled(written).items())
        self.assertIn(
            "Absorbed from --source (1): JANE into JANET across at (0, 0).",
            self.printed.splitlines(),
        )
        # The grown answer is written with the bank's clue; JANE left with its run.
        self.assertEqual(space.clues()["JANET"]["clue"], "A longer placeholder name")
        self.assertNotIn("JANE", space.clues())

    def test_the_chosen_grid_line_names_the_level(self) -> None:
        self._run(_JANE, _ABSORB)
        self.assertIn(
            "then themed entries, then fewest absorbed --source entries.", self.printed
        )

    def test_without_the_flag_the_entry_is_held(self) -> None:
        code, written, _ = self._run(_JANE)
        self.assertEqual(code, 1, self.errors)
        self.assertEqual(written, _JANE)
        self.assertNotIn("Absorbed from --source", self.printed)
        self.assertNotIn("absorbed --source entries", self.printed)

    def test_the_flag_without_a_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _BANK)
            code = self.run_main(space.fill(_ABSORB))
            self.assertEqual(code, 2)
            self.assertIn("--absorb-entries needs --source", self.errors)
            self.assertFalse(space.out.exists())


class TestPinsBesideTheFlag(SourceCase):
    """A pin on an entry holds it; a pin along all of one chooses its growth."""

    def _pinned(self, *extra: str) -> tuple[int | None, list[str]]:
        """Run `fill` from `_JANE` with `extra` flags; the exit code and the grid."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _BANK)
            source = write_source(space.root / _SOURCE_NAME, _JANE)
            code = self.run_main(source_fill(space, source, *_CEILING, *extra))
            return code, space.rows() if space.out.exists() else []

    def test_a_pin_lying_on_the_entry_holds_it(self) -> None:
        code, written = self._pinned(_ABSORB, "--feature", "JANE@0,0,across")
        self.assertEqual(code, 1, self.errors)
        self.assertEqual(written, _JANE)

    def test_a_pin_lying_along_the_entry_chooses_its_growth(self) -> None:
        code, written = self._pinned(_ABSORB, "--feature", "JANET@0,0,across")
        self.assertEqual(code, 0, self.errors)
        self.assertIn(
            cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="JANET"),
            cw_grid.runs_from_rows(written),
        )
        self.assertIn(
            "Absorbed from --source (1): JANE into JANET across at (0, 0).",
            self.printed.splitlines(),
        )

    def test_without_the_flag_a_pin_along_the_entry_is_refused(self) -> None:
        code, written = self._pinned("--feature", "JANET@0,0,across")
        self.assertEqual(code, 2)
        self.assertIn("extend the --source entry 'JANE'", self.errors)
        self.assertEqual(written, [])


#: OX across the top of a 3x5: 86.7% blocked. OXEN over it would leave 73.3%.
_OX = ["OX...", ".....", "....."]

#: A bank holding OXEN but not OX, whose other answers share no letter with it.
_OXEN_BANK: dict[str, object] = {
    "themes": cli_fixtures.THEMES,
    "entries": [
        {"answer": "OXEN", "theme": "a"},
        {"answer": "CUP", "theme": "b"},
        {"answer": "DIG", "theme": "c"},
    ],
}


class TestAKeptEntryUnderTheFlag(SourceCase):
    """An entry kept only because the source declares it never grows."""

    def _kept(self, *extra: str) -> tuple[int | None, list[str]]:
        """Run `fill --absorb-entries` from `_OX`, declaring OX; exit code and grid."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _OXEN_BANK)
            source = write_source(
                space.root / _SOURCE_NAME,
                _OX,
                clues={"OX": {"clue": "A placeholder beast"}},
            )
            code = self.run_main(
                source_fill(space, source, "--max-blocked", "80", _ABSORB, *extra)
            )
            return code, space.rows() if space.out.exists() else []

    def test_a_kept_entry_is_held_as_its_exact_run(self) -> None:
        code, written = self._kept()
        self.assertEqual(code, 1, self.errors)
        self.assertEqual(written, _OX)
        self.assertNotIn("Absorbed from --source", self.printed)

    def test_a_pin_along_a_kept_entry_is_still_refused(self) -> None:
        code, written = self._kept("--feature", "OXEN@0,0,across")
        self.assertEqual(code, 2)
        self.assertIn("extend the --source entry 'OX'", self.errors)
        self.assertEqual(written, [])


if __name__ == "__main__":
    unittest.main()
