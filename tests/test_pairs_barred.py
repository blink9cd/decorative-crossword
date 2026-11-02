"""Grouped suite: two entries that join into an `--excluded-terms` term.

`--excluded-terms` screens each bank entry, so every entry `fill` places is
clean, and two clean entries can still spell a barred term together. These
pin the calls that shape the check: a join is barred only when the whole join
is a term, either way round, once the term's spaces close up; a `--phrases`
line that is a term is dropped and named rather than listed as wordplay; and
the check is a warning in the report, never a refusal.

Every barred term here is a made-up letter string, never a real word: what is
under test is the matching, and a real term would plant in the suite the very
thing the flag exists to keep out.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest
from pathlib import Path

import cw_command_base
import cw_pairs
import cw_report

from tests.report_fixtures import block_after as _block_after
from tests.report_fixtures import make_bank as _bank
from tests.report_fixtures import make_config as _config
from tests.report_fixtures import make_outcome as _outcome

#: Two made-up entries with the whole grid between them.
APART = ("QZXV....", "........", "........", ".....JVK")

WARNING = (
    "WARNING - entries that join into an --excluded-terms term (0-based row, column):"
)
QZXV_JVK = "  QZXV, across from (0, 0) + JVK, across from (3, 5) = QZXVJVK"
JVK_QZXV = "  JVK, across from (3, 5) + QZXV, across from (0, 0) = JVKQZXV"

#: The reason a barred `--phrases` line is skipped under.
BARRED = "is an --excluded-terms term"


def _barring(*terms: str) -> cw_pairs.Phrases:
    """No phrases, and `terms` as the closed-up barred set."""
    return cw_pairs.Phrases(frozenset(), (), frozenset(terms))


class TestClosedUpTerms(unittest.TestCase):
    """A term is read the way a phrase is: folded, with its spaces closed up."""

    def test_a_term_is_uppercased_and_its_spaces_close_up(self) -> None:
        self.assertEqual(
            cw_pairs.closed_up_terms(frozenset({"qzxv jvk", "zzq"})),
            frozenset({"QZXVJVK", "ZZQ"}),
        )


class TestBarredLines(unittest.TestCase):
    """The warning block: the whole join, either way round, or nothing."""

    def test_a_join_in_reading_order_that_is_a_term_warns(self) -> None:
        self.assertEqual(
            cw_pairs.barred_lines(APART, _barring("QZXVJVK")), [WARNING, QZXV_JVK]
        )

    def test_a_join_against_reading_order_that_is_a_term_warns(self) -> None:
        self.assertEqual(
            cw_pairs.barred_lines(APART, _barring("JVKQZXV")), [WARNING, JVK_QZXV]
        )

    def test_a_clean_join_warns_nothing(self) -> None:
        self.assertEqual(cw_pairs.barred_lines(APART, _barring("QQQQQQQ")), [])

    def test_a_term_that_is_only_part_of_a_join_warns_nothing(self) -> None:
        self.assertEqual(cw_pairs.barred_lines(APART, _barring("ZXVJV")), [])

    def test_an_entry_that_is_itself_a_term_is_not_a_join(self) -> None:
        # The bank screen's job, not this block's: in `fill` it cannot happen.
        self.assertEqual(cw_pairs.barred_lines(APART, _barring("JVK")), [])

    def test_no_terms_warns_nothing(self) -> None:
        self.assertEqual(cw_pairs.barred_lines(APART, cw_pairs.NO_PHRASES), [])


class TestLoadPhrasesScreen(unittest.TestCase):
    """`load_phrases` given the barred-term list: a line that is a term is dropped."""

    def setUp(self) -> None:
        """Give each test its own folder to write lists into."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def _write(self, name: str, text: str) -> Path:
        """Write one list into this test's folder and return its path."""
        path = self.root / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def _load(self, phrases: str, terms: str) -> cw_pairs.Phrases:
        """Load one phrase list against one barred-term list."""
        return cw_command_base.load_phrases(
            [self._write("phrases.txt", phrases)], self._write("terms.txt", terms)
        )

    def test_a_phrase_line_that_is_a_term_is_skipped_and_named(self) -> None:
        self.assertEqual(
            self._load("qzxv jvk\nzzq xxv\n", "qzxvjvk\n"),
            cw_pairs.Phrases(
                frozenset({"ZZQXXV"}),
                (("QZXVJVK", BARRED),),
                frozenset({"QZXVJVK"}),
            ),
        )

    def test_a_term_written_with_spaces_bars_the_closed_up_line(self) -> None:
        loaded = self._load("qzxvjvk\nzzq xxv\n", "qzxv jvk\n")
        self.assertEqual(loaded.skipped, (("QZXVJVK", BARRED),))

    def test_a_line_merely_holding_a_term_is_kept(self) -> None:
        loaded = self._load("qzxv jvk\n", "jvk\n")
        self.assertEqual((loaded.words, loaded.skipped), (frozenset({"QZXVJVK"}), ()))

    def test_a_list_whose_every_line_is_barred_is_not_refused(self) -> None:
        loaded = self._load("qzxv jvk\n", "qzxvjvk\n")
        self.assertEqual(
            (loaded.words, loaded.skipped), (frozenset(), (("QZXVJVK", BARRED),))
        )

    def test_a_barred_line_follows_its_lists_own_skips(self) -> None:
        loaded = self._load("qzxv jvk\nQZXV.JVK\n", "qzxvjvk\n")
        self.assertEqual(
            loaded.skipped,
            (("QZXV.JVK", "holds a character outside A-Z"), ("QZXVJVK", BARRED)),
        )

    def test_terms_without_phrases_still_carry_the_terms(self) -> None:
        self.assertEqual(
            cw_command_base.load_phrases(None, self._write("terms.txt", "qzxv jvk\n")),
            _barring("QZXVJVK"),
        )


class TestFillReportWarns(unittest.TestCase):
    """The `fill` report carries the block, straight after its headline."""

    def test_the_fill_report_warns_under_its_heading(self) -> None:
        text = cw_report.render_report(
            _outcome(), _bank(), _config(), [], phrases=_barring("COWWET")
        )
        self.assertEqual(
            _block_after(text, WARNING, 1),
            ["  COW, down from (0, 0) + WET, across from (2, 0) = COWWET"],
        )

    def test_the_warning_is_the_block_after_the_headline(self) -> None:
        text = cw_report.render_report(
            _outcome(), _bank(), _config(), [], phrases=_barring("COWWET")
        )
        self.assertEqual(text.split("\n\n")[1].splitlines()[0], WARNING)

    def test_the_fill_report_has_no_warning_without_a_barred_join(self) -> None:
        text = cw_report.render_report(
            _outcome(), _bank(), _config(), [], phrases=_barring("CATCAT")
        )
        self.assertNotIn(WARNING, text.splitlines())


if __name__ == "__main__":
    unittest.main()
