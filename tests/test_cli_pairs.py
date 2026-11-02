"""Grouped suite: `--phrases` and the answer-pairs block at the process boundary.

What only a real run can settle: that `fill` and `gaps` both take the list, what
reaches stdout, and which faults are exit 2 and leave no grid behind. And the
one promise the block makes that no unit test can: the grid a run writes is the
same with a phrase list as without one, because a pair is reported and never
scored.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: Two answers and nothing else, pinned where they cannot touch, so the grid a
#: run writes is exactly these two and every report line below is known ahead.
PAIR_BANK: dict[str, object] = {
    "themes": {},
    "entries": [{"answer": "JANE"}, {"answer": "DOE"}],
}

#: The same two answers plus the word they join into.
JOINING_BANK: dict[str, object] = {
    "themes": {},
    "entries": [{"answer": answer} for answer in ("JANE", "DOE", "JANEDOE")],
}

PINS = (
    "--min-themes",
    "0",
    "--feature",
    "JANE@0,0,across",
    "--feature",
    "DOE@2,5,across",
)

#: The same two answers as a grid `gaps` reads, at the same cells.
GAPS_ROWS = ["JANE....", "........", ".....DOE"]

HEADING = (
    "Answer pairs that join into a bank answer or a --phrases entry, "
    "never scored (0-based row, column):"
)
NONE = "Answer pairs: none join into a bank answer or a --phrases entry."
JANE_DOE = "  JANE, across from (0, 0) + DOE, across from (2, 5) = JANEDOE"
DOE_JANE = "  DOE, across from (2, 5) + JANE, across from (0, 0) = DOEJANE"


def _write(root: Path, name: str, text: str) -> Path:
    """Write a plain text file into `root` and return its path."""
    path = root / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


class TestFillPhrases(cli_fixtures.QuietCase):
    """`fill --phrases`: named in the report, refused when unusable, never scored."""

    def _fill(
        self, folder: str, *extra: str, bank: dict[str, object] = PAIR_BANK
    ) -> int:
        """Run `fill` on the pinned two-answer board with `extra` appended."""
        space = cli_fixtures.Workspace(folder, bank)
        return decorative_crossword.main(space.fill(*PINS, *extra))

    def test_a_phrase_list_names_the_pair_it_joins(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = _write(Path(folder), "phrases.txt", "Jane Doe\n")
            code = self._fill(folder, "--phrases", str(phrases))
        self.assertEqual(code, 0)
        self.assertIn(JANE_DOE, self.printed.splitlines())

    def test_without_a_join_the_report_says_none(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._fill(folder)
        self.assertIn(NONE, self.printed.splitlines())

    def test_a_bank_answer_is_a_join_without_any_list(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._fill(folder, bank=JOINING_BANK)
        self.assertIn(JANE_DOE, self.printed.splitlines())

    def test_phrases_repeats_and_the_lists_union(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = _write(Path(folder), "one.txt", "jane doe\n")
            second = _write(Path(folder), "two.txt", "doe jane\n")
            self._fill(folder, "--phrases", str(first), "--phrases", str(second))
        printed = self.printed.splitlines()
        self.assertIn(JANE_DOE, printed)
        self.assertIn(DOE_JANE, printed)

    def test_a_skipped_phrase_line_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = _write(Path(folder), "phrases.txt", "Jane Doe\nJane.Doe\n")
            self._fill(folder, "--phrases", str(phrases))
        self.assertIn(
            "  JANE.DOE - holds a character outside A-Z", self.printed.splitlines()
        )

    def test_an_unreadable_phrase_list_is_exit_two_and_writes_no_grid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, PAIR_BANK)
            missing = space.root / "absent.txt"
            code = decorative_crossword.main(
                space.fill(*PINS, "--phrases", str(missing))
            )
            written = space.out.exists()
        self.assertEqual(code, 2)
        self.assertFalse(written)
        self.assertIn("absent.txt", self.errors)

    def test_a_phrase_list_holding_nothing_usable_is_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = _write(Path(folder), "phrases.txt", "# only a note\n")
            code = self._fill(folder, "--phrases", str(phrases))
        self.assertEqual(code, 2)
        self.assertIn("holds no usable phrases", self.errors)

    def test_a_mis_encoded_phrase_list_is_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = cli_fixtures.write_mis_encoded(Path(folder) / "phrases.txt")
            code = self._fill(folder, "--phrases", str(phrases))
        self.assertEqual(code, 2)

    def test_the_grid_written_is_the_same_with_phrases_as_without(self) -> None:
        # Every ordered join of every bank answer is offered, so whatever grid
        # the search keeps holds pairs: a list that matched nothing would
        # leave the two runs identical for no reason worth pinning.
        answers = [entry["answer"] for entry in cli_fixtures.ENTRIES]
        joins = "".join(f"{a}{b}\n" for a in answers for b in answers if a != b)
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            phrases = _write(space.root, "phrases.txt", joins)
            self.assertEqual(decorative_crossword.main(space.fill()), 0)
            without = space.out.read_bytes()
            code = decorative_crossword.main(space.fill("--phrases", str(phrases)))
            self.assertEqual(code, 0)
            with_phrases = space.out.read_bytes()
        self.assertEqual(with_phrases, without)
        self.assertIn(HEADING, self.printed.splitlines())


class TestGapsPhrases(cli_fixtures.QuietCase):
    """`gaps` joins against its bank and `--phrases`, and never against `--words`."""

    def _gaps(self, folder: str, *extra: str) -> int:
        """Run `gaps` on the two-answer grid with `extra` appended."""
        source = _write(
            Path(folder),
            "grid_source.json",
            json.dumps({"rows": GAPS_ROWS, "themes": {}, "clues": {}}),
        )
        return decorative_crossword.main(["gaps", "--source", str(source), *extra])

    def test_a_phrase_list_names_the_pair_it_joins(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = _write(Path(folder), "phrases.txt", "Jane Doe\n")
            self._gaps(folder, "--phrases", str(phrases))
        self.assertIn(JANE_DOE, self.printed.splitlines())

    def test_a_bank_answer_is_a_join(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            bank = _write(Path(folder), "bank.json", json.dumps(JOINING_BANK))
            self._gaps(folder, "--bank", str(bank))
        self.assertIn(JANE_DOE, self.printed.splitlines())

    def test_a_word_list_is_filler_and_offers_nothing_to_join_into(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            words = _write(Path(folder), "words.txt", "JANEDOE\n")
            self._gaps(folder, "--words", str(words))
        self.assertNotIn("Answer pairs", self.printed)

    def test_with_nothing_to_join_into_there_is_no_pairs_block(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._gaps(folder)
        self.assertNotIn("Answer pairs", self.printed)

    def test_a_phrase_list_holding_nothing_usable_is_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = _write(Path(folder), "phrases.txt", "\n")
            code = self._gaps(folder, "--phrases", str(phrases))
        self.assertEqual(code, 2)
        self.assertIn("holds no usable phrases", self.errors)


if __name__ == "__main__":
    unittest.main()
