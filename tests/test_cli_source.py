"""Grouped suite: `fill --source` on the command line.

`fill --source grid_source.json` starts the search from a grid the operator
already has: every letter and entry of it stays where it is, and the fill grows
into its blocked cells. These cases drive `main` end to end, because what each
proves is a process boundary -- an exit code, the files that did or did not
appear, and the words on stdout or stderr -- and each source check is decided
at its own call site in `cw_commands._prepare_fill`.

Every refusal case asserts the diagnostic's own words, not the exit code alone.
argparse exits 2 for an unknown flag too, so a case that checked only the code
would pass on a tool with no `--source` at all.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import cw_grid
import cw_island
import decorative_crossword
from tests import cli_fixtures
from tests.source_fixtures import BLANK as _BLANK
from tests.source_fixtures import SOURCE_NAME as _SOURCE_NAME
from tests.source_fixtures import SourceCase, filled, source_fill, write_source
from tests.source_fixtures import without_size


#: ALPHA across row 4 of a 9x9, and nothing else: room on every side to grow.
_ALPHA_ROW = [_BLANK] * 4 + ["..ALPHA.."] + [_BLANK] * 4

#: `_ALPHA_ROW` plus OX, which no bank holds. OX shares no letter with ALPHA,
#: so it cannot cross it; it stands apart in the same grid instead.
_WITH_OX = [_BLANK] * 4 + ["..ALPHA.."] + [_BLANK] * 2 + [".......OX", _BLANK]


#: The clue record that declares OX, so the source may keep it.
_OX_CLUE = {"clue": "Hay eater"}

#: ALPHA twice: a grid holds each answer once.
_TWICE = ["ALPHA...."] + [_BLANK] * 3 + ["ALPHA...."] + [_BLANK] * 4

#: A lone letter at (4, 6) beside ALPHA across the top. B is crossed by several
#: bank answers; Q by none.
_STRAY_B = ["ALPHA...."] + [_BLANK] * 3 + ["......B.."] + [_BLANK] * 4
_STRAY_Q = ["ALPHA...."] + [_BLANK] * 3 + ["......Q.."] + [_BLANK] * 4

#: ALPHA across and AMBER down from one A: 9 letters of 25, so 64% blocked, and
#: already conforming under the workspace's floors.
_CORNER = ["ALPHA", "M....", "B....", "E....", "R...."]

#: A source wider than it is tall, and one taller than it is wide.
_WIDE = ["ALPHA...."] + [_BLANK] * 4
_TALL = ["ALPHA"] + ["....."] * 8

#: A source island A at (1, 5), qualified by ALPHA's last letter at (0, 4). No
#: bank answer can cross it on three rows, and it sits at a corner of the empty
#: (2, 4): were the island allowed to qualify a corner, (2, 4) would take a
#: letter touching nothing but another lone letter, and read back as a stray.
_SHUT_IN_ISLAND = ["ALPHA.", ".....A", "......"]

#: The same island on a 9x9, where the fill crosses it. Once crossed it is an
#: entry letter, so it qualifies (0, 6) like any other.
_CROSSED_ISLAND = ["ALPHA....", ".....A..."] + [_BLANK] * 7


#: How the tool names itself on stderr, derived as the entry point derives it.
TOOL = Path(decorative_crossword.__file__).stem


def covered(rows: list[str]) -> set[tuple[int, int]]:
    """Every cell some entry of `rows` reads through."""
    return {cell for run in cw_grid.runs_from_rows(rows) for cell in run.cells}


def written_themes(space: cli_fixtures.Workspace) -> dict[str, dict[str, str]]:
    """The written grid's `themes` map, annotated at the binding as `rows` is."""
    parsed: dict[str, dict[str, dict[str, str]]] = json.loads(
        space.out.read_text(encoding="utf-8")
    )
    return parsed["themes"]


class TestGrowingFromASource(SourceCase):
    """A source is where the fill starts, and nothing of it moves."""

    def test_a_source_grows_and_every_source_cell_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
            code = self.run_main(source_fill(space, source))
            self.assertNotIn("unrecognized arguments", self.errors)
            self.assertEqual(code, 0, self.errors)
            written = filled(space.rows())
            self.assertLessEqual(filled(_ALPHA_ROW).items(), written.items())
            self.assertGreater(len(written), len(filled(_ALPHA_ROW)))
            self.assertIn("From --source:", self.printed)

    def test_a_complete_conforming_source_is_written_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _CORNER)
            code = self.run_main(source_fill(space, source, "--look-ahead", "0"))
            self.assertEqual(code, 0, self.errors)
            self.assertEqual(space.rows(), _CORNER)

    def test_a_non_square_source_holds_every_run_either_way_round(self) -> None:
        for rows in (_WIDE, _TALL):
            with (
                self.subTest(size=f"{len(rows)}x{len(rows[0])}"),
                tempfile.TemporaryDirectory() as folder,
            ):
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / _SOURCE_NAME, rows)
                code = self.run_main(source_fill(space, source))
                self.assertEqual(code, 0, self.errors)
                written = space.rows()
                self.assertEqual(
                    (len(written), len(written[0])), (len(rows), len(rows[0]))
                )
                held = cw_grid.runs_from_rows(written)
                for run in cw_grid.runs_from_rows(rows):
                    self.assertIn(run, held)

    def test_the_same_command_writes_the_same_bytes(self) -> None:
        outputs: list[bytes] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
                self.assertEqual(self.run_main(source_fill(space, source)), 0)
                outputs.append(space.out.read_bytes())
        self.assertEqual(outputs[0], outputs[1])


class TestTheSizeComesFromTheSource(SourceCase):
    """`--rows` and `--cols` may grow a source's grid, never crop it; without one, both are required."""

    def test_rows_or_cols_under_the_sources_size_is_refused(self) -> None:
        for flag, unit in (("--rows", "rows"), ("--cols", "columns")):
            with self.subTest(flag), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
                code = self.run_main(source_fill(space, source, flag, "8"))
                self.assertEqual(code, 2)
                self.assertIn(
                    f"{flag} 8 is smaller than the --source grid's 9 {unit}",
                    self.errors,
                )
                self.assertFalse(space.out.exists())

    def test_the_size_is_required_without_a_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            code = self.run_main(without_size(space.fill()))
            self.assertEqual(code, 2)
            self.assertIn(
                "--rows and --cols are required unless --source gives the grid",
                self.errors,
            )
            self.assertFalse(space.out.exists())


class TestNeverWritesOverTheSource(SourceCase):
    """No output flag may name the file the run starts from."""

    def test_out_naming_the_source_is_refused(self) -> None:
        # The source by its own spelling, and through a directory and back out:
        # compared as strings, the second is another file and would be written.
        for parts in ((_SOURCE_NAME,), ("sub", "..", _SOURCE_NAME)):
            with (
                self.subTest(out="/".join(parts)),
                tempfile.TemporaryDirectory() as folder,
            ):
                space = cli_fixtures.Workspace(folder)
                (space.root / "sub").mkdir()
                source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
                before = source.read_bytes()
                out = space.root.joinpath(*parts)
                code = self.run_main(source_fill(space, source, "--out", str(out)))
                self.assertEqual(code, 2)
                self.assertIn("--out names the --source file", self.errors)
                self.assertEqual(source.read_bytes(), before)

    def test_preview_naming_the_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
            before = source.read_bytes()
            code = self.run_main(source_fill(space, source, "--preview", str(source)))
            self.assertEqual(code, 2)
            self.assertIn("--preview names the --source file", self.errors)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(space.out.exists())

    @unittest.skipUnless(
        cli_fixtures.FOLDS_CASE,
        "this filesystem tells names apart by case, so the upper-cased name is "
        "another file rather than the source",
    )
    def test_an_output_naming_the_source_in_another_case_is_refused(self) -> None:
        # Resolving a path canonicalizes links and `..` but never case, so on a
        # case-insensitive filesystem the upper-cased name is a different string
        # that opens the source itself.
        for flag in ("--out", "--preview"):
            with self.subTest(flag), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
                before = source.read_bytes()
                upper = space.root / _SOURCE_NAME.upper()
                code = self.run_main(source_fill(space, source, flag, str(upper)))
                self.assertEqual(code, 2, self.errors)
                self.assertIn(f"{flag} names the --source file", self.errors)
                self.assertEqual(source.read_bytes(), before)

    def test_out_naming_a_hard_link_to_the_source_is_refused(self) -> None:
        # One file under two names, which resolve to two different strings on
        # every filesystem: only the file's identity says it is the source. The
        # case-variant case above proves that only where names fold case.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
            before = source.read_bytes()
            link = space.root / "linked.json"
            try:
                os.link(source, link)
            except OSError as exc:
                self.skipTest(f"this filesystem cannot hard-link a file: {exc}")
            code = self.run_main(source_fill(space, source, "--out", str(link)))
            self.assertEqual(code, 2, self.errors)
            self.assertIn("--out names the --source file", self.errors)
            self.assertEqual(source.read_bytes(), before)


class TestWhichRunsASourceMayHold(SourceCase):
    """A run is the bank's, or declared by the source, and held once."""

    def test_a_run_no_one_declares_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _WITH_OX)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 2)
            self.assertIn(
                "neither bank answers, declared in its clues, nor completable by a "
                "bank answer",
                self.errors,
            )
            self.assertIn("'OX'", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_declared_run_the_bank_lacks_is_kept_with_its_clue(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(
                space.root / _SOURCE_NAME, _WITH_OX, clues={"OX": _OX_CLUE}
            )
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 0, self.errors)
            self.assertEqual(space.clues()["OX"]["clue"], _OX_CLUE["clue"])
            self.assertIn("Kept from --source, not in the bank (1): OX.", self.printed)

    def test_a_theme_only_the_source_declares_is_written(self) -> None:
        own = {"label": "Z", "summary": "The last theme"}
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(
                space.root / _SOURCE_NAME,
                _WITH_OX,
                clues={"OX": {**_OX_CLUE, "theme": "z"}},
                themes={"z": own},
            )
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 0, self.errors)
            themes = written_themes(space)
            self.assertEqual(themes.pop("z"), own)
            self.assertEqual(themes, cli_fixtures.THEMES)

    def test_an_answer_the_source_holds_twice_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _TWICE)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 2)
            self.assertIn("--source holds 'ALPHA' twice", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_source_entry_the_excluded_terms_bar_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
            barred = space.excluded("alpha")
            code = self.run_main(
                source_fill(space, source, "--excluded-terms", str(barred))
            )
            self.assertEqual(code, 2)
            self.assertIn(
                "--excluded-terms bars these --source entries: 'ALPHA'", self.errors
            )
            self.assertFalse(space.out.exists())

    def test_a_pin_disagreeing_with_a_source_letter_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _ALPHA_ROW)
            code = self.run_main(
                source_fill(space, source, "--feature", "CEDAR@4,2,down")
            )
            self.assertEqual(code, 2)
            self.assertIn("disagrees with --source at (4, 2)", self.errors)
            self.assertFalse(space.out.exists())


class TestLoneLettersAndDensity(SourceCase):
    """A lone letter must end in an entry or as an island; density is the whole grid's."""

    def test_a_stray_the_fill_can_cover_is_warned_about_and_covered(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _STRAY_B)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 0, self.errors)
            self.assertIn(
                f"{TOOL}: warning: cell 4,6 (B) belongs to no entry", self.errors
            )
            self.assertIn((4, 6), covered(space.rows()))

    def test_a_stray_nothing_covers_is_a_near_miss_naming_its_remedy(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _STRAY_Q)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 1, self.errors)
            self.assertIn(
                "the fixed letter Q at (4, 6) belongs to no entry", self.printed
            )
            self.assertIn(
                "add a bank answer that crosses (4, 6), or remove that letter from "
                "--source",
                self.printed,
            )
            self.assertEqual(space.rows()[4][6], "Q")

    def test_a_source_already_under_the_floor_writes_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _CORNER)
            code = self.run_main(source_fill(space, source, "--min-blocked", "70"))
            self.assertEqual(code, 1, self.errors)
            self.assertIn(
                "  the --source grid is already 64.0% blocked, under the requested "
                "70.0% floor, and fill only adds letters",
                self.printed.splitlines(),
            )
            self.assertEqual(space.rows(), _CORNER)

    def test_a_source_island_never_qualifies_a_new_island(self) -> None:
        # Each grid with the one cell that tells the two readings apart. Left
        # lone, the island must not seed (2, 4). Crossed by the fill, it is an
        # entry letter like any other and qualifies (0, 6): the fixed cells are
        # read off the chosen grid, never the source's.
        for rows, cell, letter in (
            (_SHUT_IN_ISLAND, (2, 4), cw_grid.BLOCK),
            (_CROSSED_ISLAND, (0, 6), "I"),
        ):
            with (
                self.subTest(size=f"{len(rows)}x{len(rows[0])}"),
                tempfile.TemporaryDirectory() as folder,
            ):
                space = cli_fixtures.Workspace(folder)
                source = write_source(space.root / _SOURCE_NAME, rows)
                code = self.run_main(
                    source_fill(space, source, "--island-letters", "AIX")
                )
                self.assertEqual(code, 0, self.errors)
                written = space.rows()
                self.assertEqual(cw_island.stray_letters(written), ())
                self.assertEqual(written[cell[0]][cell[1]], letter)
