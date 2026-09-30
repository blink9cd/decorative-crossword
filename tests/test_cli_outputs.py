"""Grouped suite: no subcommand writes over a file it reads, or where no file can go.

Every subcommand that writes hands its output flags and its input flags to
`cw_paths.refuse_unusable_outputs` before it reads a file. These cases drive
`main` end to end, one per handler and one per input flag that handler hands
over, so a handler that dropped the call, dropped a flag from it, or moved it
past a read fails a case of its own. What the check decides -- spellings, hard
links, case -- is `test_paths.py`'s, and the `--source` spellings under `fill`
stay in `test_cli_source.py`.

Each refusal asserts that the protected file is byte-for-byte unchanged and
that no report reached stdout: without the check, the overwriting runs here
would replace their input at exit 0 or 1, and the directory runs would refuse
only at the write, after everything else had run -- an exit 2 either way, so
the exit code alone cannot tell the check from its absence.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: CAT and DOG two rows apart: `shade` can spell CAT in it and `gaps` finds a
#: gap worth reporting in it, so neither run stops short of its write.
_GRID_ROWS = ["CAT.", "....", "DOG."]

#: What a refusal of an output that is a directory says, after its flag.
_DIRECTORY = "names a directory"

#: What a refusal of an output in no directory says, after its path.
_MISSING_DIRECTORY = "is in a directory that does not exist"


def _write_lines(path: Path, *lines: str) -> Path:
    """Write `lines` at `path`, one per line; return the path."""
    path.write_text(
        "".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n"
    )
    return path


def _write_grid(path: Path) -> Path:
    """Write a grid document holding `_GRID_ROWS` at `path`; return the path."""
    path.write_text(
        json.dumps({"rows": _GRID_ROWS, "themes": {}, "clues": {}}),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _directory(root: Path) -> Path:
    """Make a directory inside `root`; return it.

    Inside rather than `root` itself, so a write that a defect lets through
    leaves its temporary file in the case's own folder.
    """
    folder = root / "folder"
    folder.mkdir()
    return folder


class OutputsCase(cli_fixtures.QuietCase):
    """A quiet case that runs `main` and checks what a refusal left alone."""

    def run_main(self, argv: list[str]) -> int | None:
        """`main`'s exit code, or None when argparse refused the command line itself.

        Suppressed so that a command line argparse cannot parse fails a case
        on its assertions, rather than erroring out of the run.
        """
        code: int | None = None
        with contextlib.suppress(SystemExit):
            code = decorative_crossword.main(argv)
        return code

    def assert_refused(self, argv: list[str], protected: Path, words: str) -> None:
        """Run `argv`: exit 2 saying `words`, `protected` unchanged, no report."""
        before = protected.read_bytes()
        code = self.run_main(argv)
        self.assertEqual(code, 2, self.errors)
        self.assertIn(words, self.errors)
        self.assertEqual(protected.read_bytes(), before)
        self.assertEqual(self.printed, "")


class TestFillOutputs(OutputsCase):
    """`fill --out` and `--preview`, against every file `fill` reads and each other."""

    def test_out_naming_the_bank_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--out", str(space.bank))
            self.assert_refused(argv, space.bank, "--out names the --bank file")

    def test_out_naming_the_excluded_terms_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.excluded("zzz")
            argv = space.fill("--excluded-terms", str(terms), "--out", str(terms))
            self.assert_refused(argv, terms, "--out names the --excluded-terms file")

    def test_out_naming_any_phrases_list_is_refused(self) -> None:
        # The SECOND list: a check handed only the first --phrases would pass
        # this command line and write over this one.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            first = _write_lines(space.root / "first.txt", "alpha amber")
            second = _write_lines(space.root / "second.txt", "brook crane")
            argv = space.fill(
                "--phrases", str(first), "--phrases", str(second), "--out", str(second)
            )
            self.assert_refused(argv, second, "--out names the --phrases file")

    def test_preview_naming_an_input_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.bank))
            self.assert_refused(argv, space.bank, "--preview names the --bank file")
            self.assertFalse(space.out.exists())

    def test_preview_naming_the_out_file_is_refused(self) -> None:
        # Unchecked, the picture would be written second and replace the grid.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.out))
            self.assert_refused(argv, space.bank, "--preview names the --out file")
            self.assertFalse(space.out.exists())

    def test_out_naming_a_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--out", str(_directory(space.root)))
            self.assert_refused(argv, space.bank, f"--out {_DIRECTORY}")

    def test_preview_naming_a_directory_leaves_no_grid_behind(self) -> None:
        # Unchecked, the grid would be written and the picture then fail at
        # exit 2, leaving a file behind a refusal.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(_directory(space.root)))
            self.assert_refused(argv, space.bank, f"--preview {_DIRECTORY}")
            self.assertFalse(space.out.exists())

    def test_out_in_a_missing_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--out", str(space.root / "missing" / "grid.json"))
            self.assert_refused(argv, space.bank, _MISSING_DIRECTORY)

    def test_the_outputs_are_checked_before_the_bank_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.bank.unlink()
            code = self.run_main(space.fill("--out", str(_directory(space.root))))
            self.assertEqual(code, 2)
            self.assertIn(f"--out {_DIRECTORY}", self.errors)


class TestReadCommandOutputs(OutputsCase):
    """`preview`, `shade` and `gaps` never write over a file they read."""

    def test_preview_out_naming_the_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = _write_grid(Path(folder) / "grid_source.json")
            argv = ["preview", "--source", str(source), "--out", str(source)]
            self.assert_refused(argv, source, "--out names the --source file")

    def test_shade_out_naming_the_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = _write_grid(Path(folder) / "grid_source.json")
            argv = ["shade", "--source", str(source), "--word", "CAT"]
            argv += ["--out", str(source)]
            self.assert_refused(argv, source, "--out names the --source file")

    def test_gaps_out_naming_the_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = _write_grid(Path(folder) / "grid_source.json")
            argv = ["gaps", "--source", str(source), "--out", str(source)]
            self.assert_refused(argv, source, "--out names the --source file")

    def test_gaps_out_naming_the_bank_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = _write_grid(space.root / "source.json")
            argv = ["gaps", "--source", str(source), "--bank", str(space.bank)]
            argv += ["--out", str(space.bank)]
            self.assert_refused(argv, space.bank, "--out names the --bank file")

    def test_gaps_out_naming_any_words_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _write_grid(root / "grid_source.json")
            first = _write_lines(root / "first.txt", "COD")
            second = _write_lines(root / "second.txt", "CAT")
            argv = ["gaps", "--source", str(source), "--words", str(first)]
            argv += ["--words", str(second), "--out", str(second)]
            self.assert_refused(argv, second, "--out names the --words file")

    def test_gaps_out_naming_any_phrases_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _write_grid(root / "grid_source.json")
            first = _write_lines(root / "first.txt", "cat dog")
            second = _write_lines(root / "second.txt", "dog cat")
            argv = ["gaps", "--source", str(source), "--phrases", str(first)]
            argv += ["--phrases", str(second), "--out", str(second)]
            self.assert_refused(argv, second, "--out names the --phrases file")

    def test_preview_checks_its_output_before_reading_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            missing = root / "grid_source.json"
            argv = ["preview", "--source", str(missing), "--out", str(_directory(root))]
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn(f"--out {_DIRECTORY}", self.errors)

    def test_shade_checks_its_output_before_reading_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            missing = root / "grid_source.json"
            argv = ["shade", "--source", str(missing), "--word", "CAT"]
            argv += ["--out", str(_directory(root))]
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn(f"--out {_DIRECTORY}", self.errors)

    def test_gaps_checks_its_output_before_reading_the_bank(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _write_grid(root / "grid_source.json")
            argv = ["gaps", "--source", str(source), "--bank", str(root / "bank.json")]
            argv += ["--out", str(_directory(root))]
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn(f"--out {_DIRECTORY}", self.errors)


if __name__ == "__main__":
    unittest.main()
