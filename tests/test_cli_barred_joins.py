"""Grouped suite: `fill --excluded-terms` warns about a join, at the process boundary.

What only a real run can settle: that the warning reaches stdout, that the exit
code is the one the grid earned without it, that a barred `--phrases` line is
named and never listed as wordplay, and (the promise no unit test can make)
that the grid a run writes is the same with the terms as without them, because
a barred join is reported and never steers the search.

Every barred term is a made-up letter string, never a real word.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: Two made-up answers and nothing else, pinned where they cannot touch, so the
#: grid a run writes is exactly these two and every report line is known ahead.
PAIR_BANK: dict[str, object] = {
    "themes": {},
    "entries": [{"answer": "QZXV"}, {"answer": "JVK"}],
}

PINS = (
    "--min-themes",
    "0",
    "--feature",
    "QZXV@0,0,across",
    "--feature",
    "JVK@2,5,across",
)

WARNING = (
    "WARNING - entries that join into an --excluded-terms term (0-based row, column):"
)
QZXV_JVK = "  QZXV, across from (0, 0) + JVK, across from (2, 5) = QZXVJVK"
JVK_QZXV = "  JVK, across from (2, 5) + QZXV, across from (0, 0) = JVKQZXV"
NONE = "Answer pairs: none join into a bank answer or a --phrases entry."


class TestFillWarnsAboutBarredJoins(cli_fixtures.QuietCase):
    """`fill --excluded-terms`: a barred join is named, and nothing else changes."""

    def _fill(self, folder: str, terms: tuple[str, ...], *extra: str) -> int:
        """Run `fill` on the pinned two-answer board against `terms`."""
        space = cli_fixtures.Workspace(folder, PAIR_BANK)
        excluded = str(space.excluded(*terms))
        return decorative_crossword.main(
            space.fill(*PINS, "--excluded-terms", excluded, *extra)
        )

    def test_a_join_that_is_a_term_warns_and_the_exit_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            code = self._fill(folder, ("qzxvjvk",))
        self.assertEqual(code, 0)
        self.assertEqual(_block_opening(self.printed, WARNING), [WARNING, QZXV_JVK])

    def test_a_join_against_reading_order_warns_through_a_spaced_term(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._fill(folder, ("jvk qzxv",))
        self.assertEqual(_block_opening(self.printed, WARNING), [WARNING, JVK_QZXV])

    def test_a_clean_join_is_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._fill(folder, ("zzqq",))
        self.assertNotIn("WARNING", self.printed)

    def test_a_barred_phrase_line_is_named_and_never_listed_as_wordplay(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phrases = Path(folder) / "phrases.txt"
            phrases.write_text("qzxv jvk\n", encoding="utf-8", newline="\n")
            self._fill(folder, ("qzxvjvk",), "--phrases", str(phrases))
        printed = self.printed.splitlines()
        self.assertIn(NONE, printed)
        self.assertIn("  QZXVJVK - is an --excluded-terms term", printed)
        self.assertIn(QZXV_JVK, printed)

    def test_the_grid_written_is_the_same_with_the_terms_as_without(self) -> None:
        # Every ordered join of every bank answer is barred, so whatever grid
        # the search keeps warns: terms that matched nothing would leave the
        # two runs identical for no reason worth pinning.
        answers = [entry["answer"] for entry in cli_fixtures.ENTRIES]
        joins = [f"{a}{b}".lower() for a in answers for b in answers if a != b]
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            excluded = str(space.excluded(*joins))
            self.assertEqual(decorative_crossword.main(space.fill()), 0)
            without = space.out.read_bytes()
            code = decorative_crossword.main(space.fill("--excluded-terms", excluded))
            self.assertEqual(code, 0)
            with_terms = space.out.read_bytes()
        self.assertEqual(with_terms, without)
        self.assertIn(WARNING, self.printed.splitlines())


def _block_opening(printed: str, heading: str) -> list[str]:
    """The report block in `printed` that opens with `heading`, heading included.

    Empty when no block opens with it, so a missing warning fails the equality
    it is compared in rather than raising on the way there.
    """
    blocks = [block.splitlines() for block in printed.split("\n\n")]
    return next((lines for lines in blocks if lines[:1] == [heading]), [])


if __name__ == "__main__":
    unittest.main()
