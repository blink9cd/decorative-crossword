"""End-to-end: `--excluded-terms` empties a bank that parsed perfectly well.

`cw_bank.parse_bank` refuses an empty `entries` list at exit 2, so this state
is unreachable from a file, but `screen_excluded` is
documented never to fail a run, which makes an emptied bank reachable from a
term list. It is an input shape the rest of the suite never contains, and every
block of the report that reasons over `bank.entries` reads differently on it:
three separate sentences would be vacuously true, or vacuously false, at once.

The partial case runs beside the empty one deliberately. Every fix here is a
guard on "the bank is empty", and a suite holding only the empty case cannot
tell a guard that fires correctly from one that fires always.
"""

import tempfile
import unittest

import decorative_crossword
from tests import cli_fixtures

#: Two answers, no themes. Two rather than one so "the bank holds no answers"
#: is reached by removing several, which is the shape an operator's term list
#: actually produces, and so the partial case below has something to leave.
_TWO_ANSWERS = ("ALPHA", "AMBER")

_SMALL_BANK: dict[str, object] = {
    "themes": {},
    "entries": [{"answer": answer} for answer in _TWO_ANSWERS],
}

#: The sentence a vacuous `any()` over an empty bank would produce. Asserted
#: absent: it is flatly untrue of zero answers, and it points the operator at
#: the grid size when the cause is their own term list.
_FALSE_LENGTH_CLAIM = "no bank answer is short enough"

#: The heading `render_report` promises to drop rather than leave empty.
_LENGTH_HEADING = "Shortage by word length:"


def _fill(space: cli_fixtures.Workspace, *terms: str) -> list[str]:
    """A `fill` argv over the small bank at a zero theme floor, screening `terms`.

    Zero because the bank declares no themes: at any positive floor the run is
    refused for that reason instead, and the empty-bank sentences this file is
    about would never be reached.
    """
    argv = space.fill("--excluded-terms", str(space.excluded(*terms)))
    argv[argv.index("--min-themes") + 1] = "0"
    return argv


class TestScreenedEmptyBank(cli_fixtures.QuietCase):
    """What the operator is told when their term list removed everything."""

    def _report(self, *terms: str) -> str:
        """Run the screened fill in a fresh workspace; return what was printed."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _SMALL_BANK)
            self.assertEqual(decorative_crossword.main(_fill(space, *terms)), 1)
            return self.printed

    def test_it_does_not_claim_every_answer_is_too_long(self) -> None:
        # The serious one. `_no_answer_fits_reason` is an
        # `any(len(a) <= longest)`, vacuously false over no entries, so without
        # its empty-bank guard the report would also carry a sentence about
        # zero answers all being longer than the grid.
        report = self._report(*_TWO_ANSWERS)
        self.assertNotIn(_FALSE_LENGTH_CLAIM, report)
        self.assertIn("the bank holds no answers", report)

    def test_it_does_not_report_the_empty_bank_as_fully_placed(self) -> None:
        # "every bank entry is in the grid" is true of zero entries and zero
        # runs, and reads as success in a report whose verdict is NOT
        # CONFORMING.
        report = self._report(*_TWO_ANSWERS)
        self.assertIn("Unplaced answers: none - the bank holds no answers.", report)
        self.assertNotIn("every bank entry is in the grid", report)

    def test_it_drops_the_length_block_rather_than_heading_nothing(self) -> None:
        # `render_report`'s own docstring: empty blocks drop out rather than
        # leaving a heading with nothing under it. `_length_lines` must return
        # nothing for an empty bank, or its heading alone keeps the
        # orchestrator's filter from firing.
        self.assertNotIn(_LENGTH_HEADING, self._report(*_TWO_ANSWERS))

    def test_it_still_names_what_the_term_list_removed(self) -> None:
        # The neutral pre-flight sentence is only honest because this block
        # sits above it: between them the operator has the cause and the names.
        report = self._report(*_TWO_ANSWERS)
        self.assertIn("Dropped by --excluded-terms (2):", report)
        for answer in _TWO_ANSWERS:
            self.assertIn(answer, report)

    def test_a_partly_screened_bank_keeps_every_block_it_should(self) -> None:
        # The other side of every guard added for the empty case. One answer
        # survives, so the length block, the ordinary "unplaced" wording and
        # the absence of the empty-bank sentence must all come back: a guard
        # that fired unconditionally would pass the four tests above and fail
        # this one. Exit 0: one five-letter answer on this 9x9 at the
        # workspace's own 0-95% window is a conforming grid.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _SMALL_BANK)
            code = decorative_crossword.main(_fill(space, _TWO_ANSWERS[0]))
            report = self.printed
        self.assertEqual(code, 0)
        self.assertIn(_LENGTH_HEADING, report)
        self.assertIn("every bank entry is in the grid", report)
        self.assertNotIn("the bank holds no answers", report)
        self.assertIn("Dropped by --excluded-terms (1):", report)


if __name__ == "__main__":
    unittest.main()
