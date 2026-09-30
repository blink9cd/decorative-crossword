"""Grouped suite: multi-word bank answers at the process boundary.

What only a real run can settle: that a bank answer written `HELLO THERE` is
laid in the grid as `HELLOTHERE`, that its clue reaches `grid_source.json` with
its enumeration, that the report names the written form, and that every flag
naming an answer -- `--feature`, `--prefer`, `--excluded-terms`, `--phrases`
and `preview --feature` -- reaches it through its punctuation. Each refusal is
exit 2 and leaves no grid behind.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cw_grid
import decorative_crossword
from tests import cli_fixtures

#: Two clued multi-word answers and nothing else, so the grid a pinned run
#: writes is exactly these two.
SPELLED_BANK: dict[str, object] = {
    "themes": {},
    "entries": [
        {"answer": "HELLO THERE", "clue": "Greeting"},
        {"answer": "ATTA-BOY", "clue": "Well done"},
    ],
}

#: Both answers pinned where they cannot touch, on a grid wide enough for the
#: longer, which is ten letters.
PINS = (
    "--min-themes",
    "0",
    "--cols",
    "10",
    "--feature",
    "HELLO THERE@0,0,across",
    "--feature",
    "ATTA-BOY@2,0,across",
)

#: The report block naming each placed answer the bank spells otherwise.
WRITTEN_HEADING = (
    "Written forms, as the bank spells them "
    "(the enumeration ends a clued answer's clue):"
)
HELLO_LINE = "  HELLOTHERE - HELLO THERE (5,5)"
ATTA_LINE = "  ATTABOY - ATTA-BOY (4-3)"

#: Two answers that join into a hyphenated phrase, pinned apart.
JOIN_BANK: dict[str, object] = {
    "themes": {},
    "entries": [{"answer": "ATTA"}, {"answer": "BOY"}],
}
JOIN_PINS = (
    "--min-themes",
    "0",
    "--feature",
    "ATTA@0,0,across",
    "--feature",
    "BOY@2,5,across",
)
ATTA_BOY = "  ATTA, across from (0, 0) + BOY, across from (2, 5) = ATTABOY"


def _write(root: Path, name: str, text: str) -> Path:
    """Write a plain text file into `root` and return its path."""
    path = root / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


class TestSpelledFill(cli_fixtures.QuietCase):
    """`fill` lays a written answer by its letters and keeps its written form."""

    def _fill(self, folder: str, *extra: str) -> cli_fixtures.Workspace:
        """Run the pinned two-answer `fill`, asserting exit 0; return the space."""
        space = cli_fixtures.Workspace(folder, SPELLED_BANK)
        code = decorative_crossword.main(space.fill(*PINS, *extra))
        self.assertEqual(code, 0, self.errors)
        return space

    def test_a_spaced_answer_is_laid_by_its_letters(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            rows = self._fill(folder).rows()
        self.assertEqual(rows[0], "HELLOTHERE")
        self.assertTrue(rows[2].startswith("ATTABOY"))

    def test_each_clue_ends_with_its_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            clues = self._fill(folder).clues()
        self.assertEqual(clues["HELLOTHERE"]["clue"], "Greeting (5,5)")
        self.assertEqual(clues["ATTABOY"]["clue"], "Well done (4-3)")

    def test_the_report_names_each_written_form(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._fill(folder)
        lines = self.printed.splitlines()
        start = lines.index(WRITTEN_HEADING)
        self.assertEqual(lines[start + 1 : start + 3], [HELLO_LINE, ATTA_LINE])

    def test_a_letters_only_run_prints_no_written_block(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, JOIN_BANK)
            code = decorative_crossword.main(space.fill(*JOIN_PINS))
        self.assertEqual(code, 0, self.errors)
        self.assertNotIn(WRITTEN_HEADING, self.printed)

    def test_a_bare_feature_reaches_the_answer_through_its_hyphen(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, SPELLED_BANK)
            code = decorative_crossword.main(
                space.fill("--min-themes", "0", "--cols", "10", "--feature", "ATTA-BOY")
            )
            self.assertEqual(code, 0, self.errors)
            rows = space.rows()
        # Either direction: the search, not a pin, chooses where it goes.
        self.assertIsNotNone(cw_grid.find_answer(rows, "ATTABOY"), rows)

    def test_prefer_reaches_the_answer_through_its_space(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._fill(folder, "--prefer", "HELLO THERE")
        self.assertIn("Preferred answers placed: HELLOTHERE (1 of 1).", self.printed)

    def test_prefer_in_two_spellings_is_one_answer_named_twice(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, SPELLED_BANK)
            code = decorative_crossword.main(
                space.fill(*PINS, "--prefer", "HELLO THERE", "--prefer", "HELLOTHERE")
            )
        self.assertEqual(code, 2)
        self.assertIn("--prefer names 'HELLOTHERE' twice", self.errors)

    def test_an_excluded_term_reaches_the_answer_through_its_hyphen(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, SPELLED_BANK)
            terms = space.excluded("hello-there")
            code = decorative_crossword.main(
                space.fill(*PINS, "--excluded-terms", str(terms))
            )
            written = space.out.exists()
        self.assertEqual(code, 2)
        self.assertIn(
            "--excluded-terms drops the featured answer 'HELLOTHERE'", self.errors
        )
        self.assertFalse(written)


class TestSpelledRefusals(cli_fixtures.QuietCase):
    """A bank answer no rule accepts is exit 2, and writes nothing."""

    def _refused(self, folder: str, bank: dict[str, object]) -> str:
        """Run `fill` on `bank`, assert exit 2 and no grid; return stderr."""
        space = cli_fixtures.Workspace(folder, bank)
        code = decorative_crossword.main(space.fill("--min-themes", "0"))
        self.assertEqual(code, 2)
        self.assertFalse(space.out.exists())
        return self.errors

    def test_a_period_is_refused_naming_the_rule(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            errors = self._refused(
                folder, {"themes": {}, "entries": [{"answer": "ST. ELMO"}]}
            )
        self.assertIn("'ST. ELMO'", errors)
        self.assertIn("spaces or hyphens", errors)

    def test_two_spellings_in_one_bank_are_refused_naming_both(self) -> None:
        # Annotated: inferred, the literal is narrower than `_refused` takes,
        # and `dict` is invariant in its value type.
        bank: dict[str, object] = {
            "themes": {},
            "entries": [{"answer": "ATTA-BOY"}, {"answer": "ATTA BOY"}],
        }
        with tempfile.TemporaryDirectory() as folder:
            errors = self._refused(folder, bank)
        self.assertIn("'ATTA-BOY'", errors)
        self.assertIn("'ATTA BOY'", errors)

    def test_two_spellings_across_banks_are_refused_in_its_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, SPELLED_BANK)
            second = _write(
                space.root,
                "second.json",
                # The same clue, so the spelling is the one field that differs.
                json.dumps(
                    {
                        "themes": {},
                        "entries": [{"answer": "ATTA BOY", "clue": "Well done"}],
                    }
                ),
            )
            code = decorative_crossword.main(
                space.fill("--min-themes", "0", "--bank", str(second))
            )
        self.assertEqual(code, 2)
        self.assertIn("'ATTABOY' differs between the bank files", self.errors)
        self.assertIn("in its spelling", self.errors)


class TestSpelledPhrases(cli_fixtures.QuietCase):
    """`--phrases` and the barred-join warning close up hyphens and apostrophes."""

    def test_a_hyphenated_phrase_line_names_its_pair(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, JOIN_BANK)
            phrases = _write(space.root, "phrases.txt", "atta-boy\n")
            code = decorative_crossword.main(
                space.fill(*JOIN_PINS, "--phrases", str(phrases))
            )
        self.assertEqual(code, 0, self.errors)
        self.assertIn(ATTA_BOY, self.printed.splitlines())

    def test_a_hyphenated_term_warns_of_the_join(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, JOIN_BANK)
            terms = space.excluded("atta-boy")
            code = decorative_crossword.main(
                space.fill(*JOIN_PINS, "--excluded-terms", str(terms))
            )
        self.assertEqual(code, 0, self.errors)
        lines = self.printed.splitlines()
        warnings = [index for index, line in enumerate(lines) if "WARNING" in line]
        self.assertTrue(warnings, self.printed)
        self.assertEqual(lines[warnings[0] + 1], ATTA_BOY)


class TestSpelledPreview(cli_fixtures.QuietCase):
    """`preview --feature` finds a written answer by its letters."""

    def test_a_spaced_feature_is_found_in_the_grid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = _write(
                Path(folder),
                "grid_source.json",
                json.dumps({"rows": ["HELLOTHERE"], "themes": {}, "clues": {}}),
            )
            svg = Path(folder) / "preview.svg"
            code = decorative_crossword.main(
                [
                    "preview",
                    "--source",
                    str(source),
                    "--out",
                    str(svg),
                    "--feature",
                    "HELLO THERE",
                ]
            )
        self.assertEqual(code, 0, self.errors)


if __name__ == "__main__":
    unittest.main()
