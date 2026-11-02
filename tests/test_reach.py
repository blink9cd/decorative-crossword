"""Tests for cw_reach: whether a search step may leave a run the one rule will later accept.

The walk may pass through a grid holding a run that is not yet an answer, as long as
some unused answer could still be laid over it. These tests pin what "could still"
means, one condition at a time, and that a step which breaks nothing never pays for
the answer lookup. Whether the grids a search returns obey the rule is a different
question, answered in `test_search_interlock.py`.
"""

import unittest
from collections.abc import Iterator, Mapping
from unittest import mock

import cw_grid
import cw_reach

from tests.search_fixtures import one_theme_bank as _one_theme_bank


def _across(row: int, col: int, text: str) -> cw_grid.Run:
    """An ACROSS run, spelled the way these tests read it."""
    return cw_grid.Run(row=row, col=col, direction=cw_grid.ACROSS, text=text)


class TestCompletable(unittest.TestCase):
    """A run is completable when an answer containing it could still be laid over it."""

    def test_a_longer_answer_that_fits_and_agrees_completes_the_run(self) -> None:
        # LTS sits at the end of the row; WILTS lays over it, the W already
        # there agrees, and the gap between is empty.
        self.assertTrue(
            cw_reach.completable(("W.LTS",), _across(0, 2, "LTS"), ("WILTS",))
        )

    def test_an_answer_that_would_run_off_the_line_is_no_completion(self) -> None:
        self.assertFalse(
            cw_reach.completable(("LTS..",), _across(0, 0, "LTS"), ("WILTS",))
        )

    def test_a_letter_already_in_the_span_must_agree(self) -> None:
        self.assertFalse(
            cw_reach.completable(("X.LTS",), _across(0, 2, "LTS"), ("WILTS",))
        )

    def test_the_cell_just_past_the_answer_must_be_empty(self) -> None:
        # ABD over AB would end beside the C, joining one longer run that ABD
        # does not spell. The same row with that cell empty is the control.
        self.assertFalse(
            cw_reach.completable((".AB.C",), _across(0, 1, "AB"), ("ABD",))
        )
        self.assertTrue(cw_reach.completable((".AB..",), _across(0, 1, "AB"), ("ABD",)))

    def test_the_cell_just_before_the_answer_must_be_empty(self) -> None:
        self.assertFalse(cw_reach.completable(("C.AB",), _across(0, 2, "AB"), ("DAB",)))

    def test_an_answer_no_longer_than_the_run_is_no_completion(self) -> None:
        # A run that already spells an answer and still breaks the rule is a
        # repeat, and only a longer answer laid over it could change that.
        self.assertFalse(cw_reach.completable(("AB",), _across(0, 0, "AB"), ("AB",)))

    def test_every_offset_of_the_run_inside_the_answer_is_tried(self) -> None:
        # ABAB holds AB twice. Aligning on the first copy runs off the line;
        # only the second copy fits, so a search that stops at the first
        # occurrence reports a completable run as dead.
        self.assertTrue(cw_reach.completable(("..AB",), _across(0, 2, "AB"), ("ABAB",)))

    def test_a_down_run_reads_its_own_column(self) -> None:
        rows = ("W", ".", "L", "T", "S")
        run = cw_grid.Run(row=2, col=0, direction=cw_grid.DOWN, text="LTS")
        self.assertTrue(cw_reach.completable(rows, run, ("WILTS",)))


class TestPinsHold(unittest.TestCase):
    """Every pin must still be an entry of its own, exactly where it was pinned."""

    def test_nothing_pinned_always_holds(self) -> None:
        self.assertTrue(cw_reach.pins_hold(cw_grid.runs_from_rows(("JANET",)), ()))

    def test_a_pin_that_is_still_its_run_holds(self) -> None:
        runs = cw_grid.runs_from_rows(("JANE.",))
        self.assertTrue(cw_reach.pins_hold(runs, (_across(0, 0, "JANE"),)))

    def test_a_pin_extended_into_a_longer_run_does_not_hold(self) -> None:
        runs = cw_grid.runs_from_rows(("JANET",))
        self.assertFalse(cw_reach.pins_hold(runs, (_across(0, 0, "JANE"),)))


class _Unread(Mapping[str, tuple[str, ...]]):
    """A fragment index that fails the test the moment anything reads it."""

    def __getitem__(self, fragment: str) -> tuple[str, ...]:
        raise AssertionError(
            f"a grid that obeys the rule read the index for {fragment!r}"
        )

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("a grid that obeys the rule walked the index")

    def __len__(self) -> int:
        raise AssertionError("a grid that obeys the rule sized the index")


def _holders(*answers: str) -> Mapping[str, tuple[str, ...]]:
    """The fragment index a search builds over these answers, on a grid holding all."""
    return cw_reach.holders_by_fragment(answers, longest=max(map(len, answers)))


class TestStepAllowed(unittest.TestCase):
    """A step may break the rule only in ways an unused answer could still repair."""

    def test_a_step_that_breaks_nothing_never_reads_the_index(self) -> None:
        # Most steps break nothing, and asking who could complete a run is the
        # expensive part, so a legal grid must never ask.
        self.assertTrue(
            cw_reach.step_allowed(("CAT",), frozenset({"CAT"}), (), _Unread())
        )

    def test_a_break_an_unused_answer_could_complete_is_allowed(self) -> None:
        self.assertTrue(
            cw_reach.step_allowed(
                ("W.LTS",), frozenset({"WILTS"}), (), _holders("WILTS")
            )
        )

    def test_a_break_nothing_could_complete_is_refused(self) -> None:
        self.assertFalse(
            cw_reach.step_allowed(("QZ...",), frozenset({"CAT"}), (), _holders("CAT"))
        )

    def test_an_answer_already_on_the_board_completes_nothing(self) -> None:
        # WILTS holds LTS, but it is already an entry, so it is not unused: only
        # a second copy could lie over the break, and that copy breaks the rule.
        rows = ("W.LTS", ".....", "WILTS")
        self.assertFalse(
            cw_reach.step_allowed(rows, frozenset({"WILTS"}), (), _holders("WILTS"))
        )

    def test_one_dead_break_refuses_the_step_beside_a_live_one(self) -> None:
        # LTS could still become WILTS; QZ could become nothing. The blank middle
        # row keeps the columns to single letters, so these are the only breaks.
        self.assertFalse(
            cw_reach.step_allowed(
                ("W.LTS", ".....", "QZ..."),
                frozenset({"WILTS"}),
                (),
                _holders("WILTS"),
            )
        )

    def test_a_broken_pin_refuses_the_step_even_where_the_rule_holds(self) -> None:
        self.assertFalse(
            cw_reach.step_allowed(
                ("JANET",),
                frozenset({"JANE", "JANET"}),
                (_across(0, 0, "JANE"),),
                _holders("JANE", "JANET"),
            )
        )

    def test_a_break_is_checked_against_only_the_answers_holding_it(self) -> None:
        # Only an answer holding the run's letters can lie over a break, so only
        # those are asked rather than the whole unused bank: here WILTS and
        # SALTS, which the X keeps from laying, among twenty that are longer
        # than LTS and hold none of it.
        answers = ("WILTS", "SALTS") + tuple(
            letter * 4 for letter in "ABCDEFGHIJKLMNOPQRST"
        )
        with mock.patch.object(
            cw_reach, "_offsets", wraps=cw_reach._offsets
        ) as offsets:
            allowed = cw_reach.step_allowed(
                ("X.LTS",), frozenset(answers), (), _holders(*answers)
            )
        self.assertFalse(allowed)
        self.assertLessEqual(offsets.call_count, 2)


class TestHoldersByFragment(unittest.TestCase):
    """Every fragment a run could be, mapped to the answers that could lie over it."""

    def test_maps_a_fragment_to_the_longer_answers_holding_it_in_order(self) -> None:
        self.assertEqual(_holders("WILTS", "SALT", "LT")["LT"], ("WILTS", "SALT"))

    def test_an_answer_is_never_listed_under_itself(self) -> None:
        # A run that already spells an answer and still breaks the rule is a
        # repeat, which only a longer answer could change.
        self.assertNotIn("SALT", _holders("WILTS", "SALT"))

    def test_an_answer_holding_a_fragment_twice_is_listed_once(self) -> None:
        self.assertEqual(_holders("ABAB")["AB"], ("ABAB",))

    def test_a_single_letter_is_no_fragment(self) -> None:
        # A run is at least two cells, so no run is ever looked up by one letter.
        self.assertNotIn("L", _holders("WILTS"))

    def test_an_answer_no_line_of_the_grid_can_hold_is_not_indexed(self) -> None:
        # Indexing an answer costs every substring of it (about L**3 / 6
        # characters, ten gigabytes for one 4,000-letter answer), and a
        # 30-letter answer can never lie on a grid whose longest line is 7.
        index = cw_reach.holders_by_fragment(("CAT", "AB" * 15), longest=7)
        self.assertEqual(dict(index), {"CA": ("CAT",), "AT": ("CAT",)})

    def test_an_answer_exactly_as_long_as_the_longest_line_is_indexed(self) -> None:
        index = cw_reach.holders_by_fragment(("CATS",), longest=4)
        self.assertEqual(index["CAT"], ("CATS",))


class TestWalkBreaks(unittest.TestCase):
    """The breaks the walk made itself: every break but one along a `--source` partial run.

    The walk treats its own breaks differently from a source's half-written words
    (it may lay only a repair over the first, and is left free around the second), so
    which is which is pinned here, one shape at a time.
    """

    def test_a_board_that_obeys_the_rule_has_none(self) -> None:
        self.assertEqual(cw_reach.walk_breaks(("CAT",), frozenset({"CAT"}), ()), ())

    def test_a_run_no_answer_spells_is_one_without_a_source(self) -> None:
        self.assertEqual(
            cw_reach.walk_breaks(("W.LTS",), frozenset({"WILTS"}), ()),
            (_across(0, 2, "LTS"),),
        )

    def test_a_repeated_answer_is_one(self) -> None:
        # The rule reports the later copy of a repeat, and so does this.
        self.assertEqual(
            cw_reach.walk_breaks(("AB.AB",), frozenset({"AB"}), ()),
            (_across(0, 3, "AB"),),
        )

    def test_a_source_partial_run_is_not_one(self) -> None:
        start = ("W.LTS",)
        self.assertEqual(cw_reach.walk_breaks(start, frozenset({"WILTS"}), start), ())

    def test_a_source_partial_run_the_walk_has_grown_is_still_not_one(self) -> None:
        # TS was the source's; the walk laid the L beside it, and LTS lies along all
        # of TS, so it is still that half-written word rather than a new break.
        self.assertEqual(
            cw_reach.walk_breaks(("W.LTS",), frozenset({"WILTS"}), ("W..TS",)), ()
        )

    def test_a_break_beside_a_source_partial_run_is_still_one(self) -> None:
        start = ("W.LTS", ".....", ".....")
        rows = ("W.LTS", ".....", "QZ...")
        self.assertEqual(
            cw_reach.walk_breaks(rows, frozenset({"WILTS"}), start),
            (_across(2, 0, "QZ"),),
        )


class TestUnusedAnswers(unittest.TestCase):
    """What the search may still draw on, read off the board itself."""

    def test_drops_an_answer_already_on_the_grid(self) -> None:
        self.assertEqual(
            cw_reach.unused_answers(
                ("CAT", "...", "..."), _one_theme_bank(["CAT", "COW", "DOG"])
            ),
            ("COW", "DOG"),
        )

    def test_keeps_bank_order(self) -> None:
        self.assertEqual(
            cw_reach.unused_answers(
                ("...", "...", "..."), _one_theme_bank(["DOG", "COW", "CAT"])
            ),
            ("DOG", "COW", "CAT"),
        )


class TestPartialRuns(unittest.TestCase):
    """The runs of a grid no answer spells: a source's half-written words."""

    def test_names_each_run_the_vocabulary_lacks_in_scan_order(self) -> None:
        # JAN across, then OX across, then JO down: scan order is every ACROSS
        # run first, so a set or a sort would put them in a different order.
        rows = ("JAN.", "O...", "..OX")
        self.assertEqual(
            cw_reach.partial_runs(rows, frozenset({"OX"})),
            (
                _across(0, 0, "JAN"),
                cw_grid.Run(row=0, col=0, direction=cw_grid.DOWN, text="JO"),
            ),
        )
