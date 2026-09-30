"""Grouped suite: pairs of placed entries that join into another word.

Two shapes are pinned first because NEITHER is a crossing or a same-line
neighbor: `WEB` meets `SITE` only at a corner and joins AGAINST reading order,
and `ATTA` meets `BOY` only at a corner. A finder that looked at crossings or
at runs sharing a line would pass every other test here and miss both -- which
is why the pairs are looked for anywhere in the grid.

Assertions on the report are whole-line and exact: the block is read by a
person deciding whether a pun is worth keeping, so its wording is the product.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest
from pathlib import Path

import cw_bank
import cw_command_base
import cw_config
import cw_gaps
import cw_gaps_report
import cw_grid
import cw_pairs
import cw_report
import cw_shade

from tests.report_fixtures import block_after as _block_after
from tests.report_fixtures import make_bank as _bank
from tests.report_fixtures import make_config as _config
from tests.report_fixtures import make_outcome as _outcome

#: `SITE` a row above `WEB`, touching it only at the corner between (0, 1) and
#: (1, 0). Reading order meets SITE first, and SITEWEB is no word.
CORNER_AGAINST_READING = (".SITE", "W....", "E....", "B....")

#: `ATTA` down the right-hand column and `BOY` across the bottom row, touching
#: only at the corner between (3, 3) and (4, 2).
CORNER_IN_READING = ("...A", "...T", "...T", "...A", "BOY.")

#: Two entries with the whole grid between them.
FAR_APART = ("JANE....", "........", "........", ".....DOE")

HEADING = (
    "Answer pairs that join into a bank answer or a --phrases entry, "
    "never scored (0-based row, column):"
)
NONE = "Answer pairs: none join into a bank answer or a --phrases entry."

#: One skipped phrase line, as `cw_shade.load_word_list` reports it.
SKIPPED = (("WEB.SITE", "holds a character outside A-Z"),)


def _run(row: int, col: int, direction: str, text: str) -> cw_grid.Run:
    """A run literal, so an expected pair reads as the grid it came from."""
    return cw_grid.Run(row=row, col=col, direction=direction, text=text)


class TestFindPairs(unittest.TestCase):
    """Which pairs are found: anywhere, either way round, vocabulary only."""

    def test_a_corner_touch_joining_against_reading_order_is_found(self) -> None:
        self.assertEqual(
            cw_pairs.find_pairs(CORNER_AGAINST_READING, frozenset({"WEBSITE"})),
            (
                cw_pairs.Pair(
                    _run(1, 0, cw_grid.DOWN, "WEB"), _run(0, 1, cw_grid.ACROSS, "SITE")
                ),
            ),
        )

    def test_a_corner_touch_joining_in_reading_order_is_found(self) -> None:
        self.assertEqual(
            cw_pairs.find_pairs(CORNER_IN_READING, frozenset({"ATTABOY"})),
            (
                cw_pairs.Pair(
                    _run(0, 3, cw_grid.DOWN, "ATTA"), _run(4, 0, cw_grid.ACROSS, "BOY")
                ),
            ),
        )

    def test_entries_far_apart_still_pair(self) -> None:
        self.assertEqual(
            cw_pairs.find_pairs(FAR_APART, frozenset({"JANEDOE"})),
            (
                cw_pairs.Pair(
                    _run(0, 0, cw_grid.ACROSS, "JANE"),
                    _run(3, 5, cw_grid.ACROSS, "DOE"),
                ),
            ),
        )

    def test_both_orders_are_reported_when_each_spells_a_word(self) -> None:
        on = _run(0, 0, cw_grid.ACROSS, "ON")
        to = _run(0, 3, cw_grid.ACROSS, "TO")
        self.assertEqual(
            cw_pairs.find_pairs(("ON.TO",), frozenset({"ONTO", "TOON"})),
            (cw_pairs.Pair(on, to), cw_pairs.Pair(to, on)),
        )

    def test_a_join_that_reads_the_same_either_way_is_reported_once(self) -> None:
        self.assertEqual(
            cw_pairs.find_pairs(("AB.AB",), frozenset({"ABAB"})),
            (
                cw_pairs.Pair(
                    _run(0, 0, cw_grid.ACROSS, "AB"), _run(0, 3, cw_grid.ACROSS, "AB")
                ),
            ),
        )

    def test_the_entries_themselves_are_not_a_join(self) -> None:
        self.assertEqual(
            cw_pairs.find_pairs(CORNER_AGAINST_READING, frozenset({"WEB", "SITE"})), ()
        )

    def test_an_entry_never_pairs_with_itself(self) -> None:
        self.assertEqual(cw_pairs.find_pairs(("AB",), frozenset({"ABAB"})), ())

    def test_a_lone_letter_is_in_no_entry_and_never_pairs(self) -> None:
        self.assertEqual(
            cw_pairs.find_pairs(("A...", "....", "BOY."), frozenset({"ABOY"})), ()
        )

    def test_the_joined_text_is_first_then_second(self) -> None:
        pair = cw_pairs.Pair(
            _run(1, 0, cw_grid.DOWN, "WEB"), _run(0, 1, cw_grid.ACROSS, "SITE")
        )
        self.assertEqual(pair.joined, "WEBSITE")


class TestPairLines(unittest.TestCase):
    """The report block both `fill` and `gaps` print."""

    def test_names_each_pair_by_where_its_two_entries_start(self) -> None:
        self.assertEqual(
            cw_pairs.pair_lines(
                CORNER_AGAINST_READING, ("WEBSITE",), cw_pairs.NO_PHRASES
            ),
            [HEADING, "  WEB, down from (1, 0) + SITE, across from (0, 1) = WEBSITE"],
        )

    def test_says_none_when_nothing_joins(self) -> None:
        self.assertEqual(
            cw_pairs.pair_lines(CORNER_AGAINST_READING, ("CAT",), cw_pairs.NO_PHRASES),
            [NONE],
        )

    def test_a_phrase_joins_exactly_like_a_bank_answer(self) -> None:
        phrases = cw_pairs.Phrases(frozenset({"JANEDOE"}), ())
        self.assertEqual(
            cw_pairs.pair_lines(FAR_APART, (), phrases),
            [HEADING, "  JANE, across from (0, 0) + DOE, across from (3, 5) = JANEDOE"],
        )

    def test_every_skipped_phrase_line_is_named_with_its_reason(self) -> None:
        phrases = cw_pairs.Phrases(frozenset(), SKIPPED)
        self.assertEqual(
            cw_pairs.pair_lines(CORNER_AGAINST_READING, (), phrases),
            [
                NONE,
                "--phrases lines skipped (1):",
                "  WEB.SITE - holds a character outside A-Z",
            ],
        )

    def test_a_grid_holding_no_entries_makes_no_claim_about_pairs(self) -> None:
        self.assertEqual(
            cw_pairs.pair_lines(("A.", ".."), ("AA",), cw_pairs.NO_PHRASES), []
        )

    def test_a_grid_holding_no_entries_still_names_skipped_lines(self) -> None:
        phrases = cw_pairs.Phrases(frozenset(), SKIPPED)
        self.assertEqual(
            cw_pairs.pair_lines(("A.", ".."), (), phrases),
            [
                "--phrases lines skipped (1):",
                "  WEB.SITE - holds a character outside A-Z",
            ],
        )


class TestLoadPhrases(unittest.TestCase):
    """Reading `--phrases`: a word list whose lines may be written with spaces."""

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

    def test_a_phrase_is_folded_and_closed_up(self) -> None:
        loaded = cw_command_base.load_phrases(
            [self._write("phrases.txt", "atta boy\nWEB  SITE\n")]
        )
        self.assertEqual(
            loaded, cw_pairs.Phrases(frozenset({"ATTABOY", "WEBSITE"}), ())
        )

    def test_the_lists_union(self) -> None:
        loaded = cw_command_base.load_phrases(
            [self._write("one.txt", "atta boy\n"), self._write("two.txt", "web site\n")]
        )
        self.assertEqual(loaded.words, frozenset({"ATTABOY", "WEBSITE"}))

    def test_a_line_outside_a_to_z_is_skipped_and_named(self) -> None:
        loaded = cw_command_base.load_phrases(
            [self._write("phrases.txt", "WEB.SITE\nATTA BOY\n")]
        )
        self.assertEqual(loaded, cw_pairs.Phrases(frozenset({"ATTABOY"}), SKIPPED))

    def test_a_list_holding_nothing_usable_is_refused(self) -> None:
        path = self._write("phrases.txt", "# only a note\nWEB.SITE\n")
        with self.assertRaisesRegex(
            cw_command_base.UsageError, "holds no usable phrases"
        ):
            cw_command_base.load_phrases([path])

    def test_no_lists_is_no_phrases(self) -> None:
        self.assertEqual(cw_command_base.load_phrases(None), cw_pairs.NO_PHRASES)

    def test_the_word_list_reader_still_skips_a_spaced_line_by_default(self) -> None:
        words, skipped = cw_shade.load_word_list(
            self._write("words.txt", "ATTA BOY\nCAT\n")
        )
        self.assertEqual(words, ("CAT",))
        self.assertEqual(skipped[0][0], "ATTA BOY")


class TestReportsCarryThePairs(unittest.TestCase):
    """Both reports print the block, and neither invents one it was not given."""

    def test_the_fill_report_names_a_phrase_pair_under_its_heading(self) -> None:
        text = cw_report.render_report(
            _outcome(),
            _bank(),
            _config(),
            [],
            phrases=cw_pairs.Phrases(frozenset({"WETCAT"}), ()),
        )
        self.assertEqual(
            _block_after(text, HEADING, 1),
            ["  WET, across from (2, 0) + CAT, across from (0, 0) = WETCAT"],
        )

    def test_the_fill_report_joins_against_the_bank_as_well(self) -> None:
        base = _bank()
        bank = cw_bank.Bank(
            themes=dict(base.themes),
            entries=(*base.entries, cw_bank.BankEntry("CATCOW", None, None)),
        )
        text = cw_report.render_report(_outcome(bank=bank), bank, _config(), [])
        self.assertEqual(
            _block_after(text, HEADING, 1),
            ["  CAT, across from (0, 0) + COW, down from (0, 0) = CATCOW"],
        )

    def test_the_fill_report_says_none_without_a_join(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertIn(NONE, text.splitlines())

    def test_the_fill_report_is_silent_about_pairs_on_an_empty_grid(self) -> None:
        text = cw_report.render_report(
            _outcome(("...", "...", "...")), _bank(), _config(), []
        )
        self.assertNotIn("Answer pairs", text)

    def test_the_gaps_report_prints_the_pairs_block_it_is_given(self) -> None:
        config = cw_config.GapsConfig(top=0, include_absorbing=False, cell=10)
        search = cw_gaps.search_gaps(CORNER_AGAINST_READING, frozenset())
        text = cw_gaps_report.render_report(
            CORNER_AGAINST_READING, search, config, (), pairs=[NONE]
        )
        self.assertIn(NONE, text.splitlines())

    def test_the_gaps_report_has_no_pairs_block_unless_given_one(self) -> None:
        config = cw_config.GapsConfig(top=0, include_absorbing=False, cell=10)
        search = cw_gaps.search_gaps(CORNER_AGAINST_READING, frozenset())
        text = cw_gaps_report.render_report(CORNER_AGAINST_READING, search, config, ())
        self.assertNotIn("Answer pairs", text)


if __name__ == "__main__":
    unittest.main()
