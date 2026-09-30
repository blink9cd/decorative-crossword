"""Tests for cw_paths: which output paths a run may write to.

Every subcommand that writes checks its output flags before it reads a file: no
output may be a directory, sit in a directory that does not exist, name a file
the same run reads, or name the file another of its outputs writes. These cases
prove what that check decides; `test_cli_outputs.py` proves each handler hands
it the right flags.

`same_file` is the identity test behind the last two, and each of its spellings
has a case: through `..`, through a hard link, in another case where the
filesystem folds case, and by resolved spelling where a path does not exist.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import os
import tempfile
import unittest
from pathlib import Path

import cw_config
import cw_paths
from tests import cli_fixtures


def _touch(path: Path) -> Path:
    """Write an empty JSON object at `path`; return the path."""
    path.write_text("{}", encoding="utf-8", newline="\n")
    return path


class TestSameFile(unittest.TestCase):
    """One file, however either path is spelled."""

    def test_a_spelling_through_a_directory_and_back_is_the_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sub").mkdir()
            source = _touch(root / "source.json")
            other = root / "sub" / ".." / "source.json"
            self.assertTrue(cw_paths.same_file(other, source))

    def test_a_hard_link_is_the_same_file(self) -> None:
        # One file under two names, which resolve to two different strings on
        # every filesystem: only the file's identity says they are one.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _touch(root / "source.json")
            link = root / "linked.json"
            try:
                os.link(source, link)
            except OSError as exc:
                self.skipTest(f"this filesystem cannot hard-link a file: {exc}")
            self.assertTrue(cw_paths.same_file(link, source))

    @unittest.skipUnless(
        cli_fixtures.FOLDS_CASE,
        "this filesystem tells names apart by case, so the upper-cased name is "
        "another file rather than the same one",
    )
    def test_another_case_is_the_same_file_where_names_fold_case(self) -> None:
        # Resolving canonicalizes links and `..` but never case, so only the
        # file's identity can see that these two strings open one file.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _touch(root / "source.json")
            self.assertTrue(cw_paths.same_file(root / "SOURCE.JSON", source))

    def test_a_missing_path_is_compared_by_its_resolved_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sub").mkdir()
            source = root / "source.json"
            other = root / "sub" / ".." / "source.json"
            self.assertTrue(cw_paths.same_file(other, source))
            self.assertFalse(cw_paths.same_file(root / "other.json", source))

    def test_two_existing_files_are_not_the_same(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = _touch(root / "source.json")
            other = _touch(root / "other.json")
            self.assertFalse(cw_paths.same_file(other, source))


class TestRefuseUnusableOutputs(unittest.TestCase):
    """An output may not be a directory, lack one, or name a file the run touches."""

    def refusal(
        self,
        outputs: tuple[tuple[str, Path | None], ...],
        inputs: tuple[tuple[str, Path | None], ...],
    ) -> str:
        """The ConfigError message `refuse_unusable_outputs` raises for these flags."""
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_paths.refuse_unusable_outputs(outputs, inputs)
        return str(caught.exception)

    def test_an_output_naming_an_input_is_refused_by_both_flags(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            bank = _touch(Path(folder) / "bank.json")
            message = self.refusal((("--out", bank),), (("--bank", bank),))
            self.assertIn(f"--out names the --bank file {bank}", message)
            self.assertIn("a run never writes over a file it reads", message)

    def test_distinct_files_and_absent_flags_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bank = _touch(root / "bank.json")
            cw_paths.refuse_unusable_outputs(
                (("--out", root / "grid.json"), ("--preview", None)),
                (("--bank", bank), ("--excluded-terms", None)),
            )

    def test_an_output_that_is_a_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            message = self.refusal((("--out", root),), ())
            self.assertIn(f"--out names a directory, {root}", message)
            self.assertIn("give the path of a file to write", message)

    def test_a_directory_output_is_never_called_an_input_file(self) -> None:
        # A directory is refused as one. Calling it "the --bank file" as well
        # would be a false sentence about the operator's path.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            message = self.refusal((("--out", root),), (("--bank", root),))
            self.assertIn("--out names a directory", message)
            self.assertNotIn("--bank", message)

    def test_an_output_in_a_missing_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing"
            out = missing / "grid.json"
            message = self.refusal((("--out", out),), ())
            self.assertIn(
                f"--out {out} is in a directory that does not exist: {missing}",
                message,
            )

    def test_an_output_under_a_file_is_refused_as_lacking_a_directory(self) -> None:
        # The parent exists but is a file, so no DIRECTORY of that name exists:
        # the refusal's sentence stays true, and nothing reaches the write.
        with tempfile.TemporaryDirectory() as folder:
            parent = _touch(Path(folder) / "parent.json")
            message = self.refusal((("--out", parent / "grid.json"),), ())
            self.assertIn("is in a directory that does not exist", message)

    def test_two_outputs_naming_one_file_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "grid.json"
            message = self.refusal((("--out", out), ("--preview", out)), ())
            self.assertIn(f"--preview names the --out file {out}", message)
            self.assertIn("the grid and its picture need two files", message)

    def test_a_directory_named_by_both_outputs_is_refused_only_as_a_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            message = self.refusal((("--out", root), ("--preview", root)), ())
            self.assertIn("--out names a directory", message)
            self.assertIn("--preview names a directory", message)
            self.assertNotIn("names the --out file", message)

    def test_every_offender_is_named_in_one_refusal(self) -> None:
        # Told only the first, an operator fixes it and is refused again.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bank = _touch(root / "bank.json")
            terms = _touch(root / "terms.txt")
            message = self.refusal(
                (("--out", bank), ("--preview", root)),
                (("--bank", bank), ("--excluded-terms", terms)),
            )
            self.assertIn("--out names the --bank file", message)
            self.assertIn("--preview names a directory", message)


class TestRefuseRepeatedInputs(unittest.TestCase):
    """A repeatable input flag may not name one file twice, however it is spelled."""

    def refusal(self, paths: tuple[Path, ...]) -> str:
        """The ConfigError message `refuse_repeated_inputs` raises for these paths."""
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_paths.refuse_repeated_inputs("--bank", paths)
        return str(caught.exception)

    def test_distinct_files_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cw_paths.refuse_repeated_inputs(
                "--bank", (_touch(root / "main.json"), _touch(root / "names.json"))
            )

    def test_one_file_given_twice_is_refused_under_both_spellings(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sub").mkdir()
            bank = _touch(root / "bank.json")
            again = root / "sub" / ".." / "bank.json"
            message = self.refusal((bank, again))
            self.assertIn(
                f"--bank names the same file twice, {bank} and {again}", message
            )

    def test_every_repeat_is_named_in_one_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            main = _touch(root / "main.json")
            names = _touch(root / "names.json")
            message = self.refusal((main, names, main, names))
            self.assertIn(f"twice, {main} and {main}", message)
            self.assertIn(f"twice, {names} and {names}", message)


if __name__ == "__main__":
    unittest.main()
