"""Tests for cw_search and cw_accept under a --source grid.

A source is the board the walk starts from: every letter stays, every entry is
held as its exact run, and a refusal writes the source rather than an empty
board. A lone letter the source brings must end in an entry or as an island.
A partial run (one the bank answers only by a longer word) must be
completed, and a source holding one is never itself written: it breaks the
one rule, so a refusal or an unfinished walk writes an empty board instead.
"""

import unittest
from unittest import mock

import cw_accept
import cw_grid
import cw_search

from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import pin as _pin
from tests.search_fixtures import still as _still
from tests.search_fixtures import themed_bank as _themed_bank
from tests.search_fixtures import (
    ONE_HUNDRED_EIGHTY_TWO_OF_625 as _ONE_HUNDRED_EIGHTY_TWO_OF_625,
)

#: ALPHA across the top of a 3x5: 66.7% blocked.
_ALPHA_ONLY = ("ALPHA", ".....", ".....")

#: ALPHA across and AMBER down from the same A: every run a themed answer.
_CORNER = ("ALPHA", "M....", "B....", "E....", "R....")


def _letters(rows: tuple[str, ...]) -> int:
    """Filled cells in `rows`."""
    return sum(1 for row in rows for cell in row if cell != cw_grid.BLOCK)


class TestTheWalkHoldsTheSource(unittest.TestCase):
    """Source letters and entries never move, change or grow."""

    def test_a_source_entry_is_never_extended_into_a_longer_answer(self) -> None:
        # JANET over JANE is the only move that adds a letter here, and it would
        # conform. Held as its exact run, JANE blocks it: the same fault a pinned
        # --feature is held against, arriving through --source instead.
        start = ("JANE.", ".....", ".....")
        outcome = cw_search.search(
            _bank(["JANE", "JANET"]),
            _config(rows=3, cols=5, start=start, min_themes=0, max_blocked=70.0),
            clock=_still,
        )
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.rows, start)

    def test_a_source_that_already_conforms_comes_back_unchanged(self) -> None:
        outcome = cw_search.search(
            _themed_bank(), _config(rows=5, cols=5, start=_CORNER), clock=_still
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, _CORNER)
        self.assertEqual(outcome.steps, 1)

    def test_a_look_ahead_only_adds_letters_around_the_source(self) -> None:
        outcome = cw_search.search(
            _themed_bank(),
            _config(rows=5, cols=5, start=_CORNER, look_ahead=300, max_steps=3000),
            clock=_still,
        )
        runs = cw_grid.runs_from_rows(outcome.rows)
        for run in cw_grid.runs_from_rows(_CORNER):
            self.assertIn(run, runs)
        self.assertGreaterEqual(_letters(outcome.rows), _letters(_CORNER))

    def test_a_non_square_source_grows_in_both_orientations(self) -> None:
        across = (".........", ".........", "..ALPHA..", ".........", ".........")
        down = tuple("".join(row[col] for row in across) for col in range(9))
        for start in (across, down):
            with self.subTest(height=len(start)):
                outcome = cw_search.search(
                    _themed_bank(),
                    _config(
                        rows=len(start),
                        cols=len(start[0]),
                        start=start,
                        max_blocked=80.0,
                        max_steps=4000,
                    ),
                    clock=_still,
                )
                self.assertTrue(outcome.conforming)
                self.assertIn(
                    cw_grid.runs_from_rows(start)[0],
                    cw_grid.runs_from_rows(outcome.rows),
                )
                self.assertGreater(_letters(outcome.rows), _letters(start))

    def test_the_same_seed_reaches_the_same_grid(self) -> None:
        request = _config(rows=5, cols=5, start=_CORNER, look_ahead=50, max_steps=2000)
        first = cw_search.search(_themed_bank(), request, clock=_still)
        second = cw_search.search(_themed_bank(), request, clock=_still)
        self.assertEqual(first.rows, second.rows)


class TestPreflightUnderASource(unittest.TestCase):
    """What pre-flight refuses, and what a refused run writes."""

    def test_a_refused_request_writes_the_source_not_an_empty_board(self) -> None:
        outcome = cw_search.search(
            _themed_bank(),
            _config(rows=3, cols=5, start=_ALPHA_ONLY, min_themes=4),
            clock=_still,
        )
        self.assertEqual(outcome.steps, 0)
        self.assertEqual(outcome.rows, _ALPHA_ONLY)

    def test_refuses_a_source_already_under_the_blocked_floor(self) -> None:
        reasons = cw_search.preflight(
            _themed_bank(),
            _config(rows=3, cols=5, start=_ALPHA_ONLY, min_blocked=70.0),
        )
        self.assertEqual(
            reasons,
            (
                "the --source grid is already 66.7% blocked, under the requested "
                "70.0% floor, and fill only adds letters",
            ),
        )

    def test_a_source_a_decimal_under_the_floor_is_printed_to_show_it(self) -> None:
        # 10 of 15 is 66.666...%, under a 66.7 floor: at one decimal the
        # refusal read "already 66.7% blocked, under the requested 66.7% floor".
        reasons = cw_search.preflight(
            _themed_bank(),
            _config(rows=3, cols=5, start=_ALPHA_ONLY, min_blocked=66.7),
        )
        self.assertEqual(
            reasons,
            (
                "the --source grid is already 66.67% blocked, under the requested "
                "66.70% floor, and fill only adds letters",
            ),
        )

    def test_a_source_of_182_of_625_under_a_29_13_floor_says_so(self) -> None:
        # 29.12% under 29.13: both print as 29.1 at one decimal. The source's
        # runs are no bank answers, which pre-flight names too; only the
        # density sentence is under test.
        reasons = cw_search.preflight(
            _themed_bank(),
            _config(
                rows=25,
                cols=25,
                start=_ONE_HUNDRED_EIGHTY_TWO_OF_625,
                min_blocked=29.13,
                min_themes=0,
            ),
        )
        self.assertIn(
            "the --source grid is already 29.12% blocked, under the requested "
            "29.13% floor, and fill only adds letters",
            reasons,
        )

    def test_a_source_exactly_at_the_blocked_floor_is_not_refused(self) -> None:
        # ALPHA across a 4x5 blocks 15 of 20 cells: exactly 75.0%. Only a board
        # already under --min-blocked is refused; one at the floor is inside the
        # window, and any floor above it refuses: 75.1 is just the probe.
        start = ("ALPHA", ".....", ".....", ".....")
        self.assertEqual(cw_grid.blocked_percent(start), 75.0)
        at_floor = _config(rows=4, cols=5, start=start, min_blocked=75.0)
        self.assertEqual(cw_search.preflight(_themed_bank(), at_floor), ())
        above = _config(rows=4, cols=5, start=start, min_blocked=75.1)
        self.assertEqual(len(cw_search.preflight(_themed_bank(), above)), 1)

    def test_a_source_on_a_floor_floats_miss_is_not_refused(self) -> None:
        # 29 of 50 cells is exactly 58%, but 29 / 50 * 100 is 57.99999999999999,
        # which a float comparison put under a 58.0 floor, and refused with
        # "already 58.0% blocked, under the requested 58.0% floor".
        start = ("ABCDEFGHIJ", "." * 10, "KLMNOPQRS.", "." * 10, "UV" + "." * 8)
        bank = _bank(["ABCDEFGHIJ", "KLMNOPQRS", "UV"])
        at_floor = _config(rows=5, cols=10, start=start, min_blocked=58.0, min_themes=0)
        self.assertEqual(cw_search.preflight(bank, at_floor), ())

    def test_a_pinned_board_without_a_source_is_not_refused_for_density(self) -> None:
        # No run without --source may change: pins-only boards keep walking.
        reasons = cw_search.preflight(
            _themed_bank(),
            _config(
                rows=3,
                cols=5,
                min_blocked=70.0,
                features=(_pin("ALPHA", 0, 0, cw_grid.ACROSS),),
            ),
        )
        self.assertEqual(reasons, ())


class TestLoneSourceLetters(unittest.TestCase):
    """A stray the source brings must end in an entry, or as an island."""

    def test_a_stray_the_fill_covers_is_accepted(self) -> None:
        start = (".....", ".....", "..B..", ".....", ".....")
        outcome = cw_search.search(
            _themed_bank(),
            _config(rows=5, cols=5, start=start, max_steps=2000),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        covered = {
            cell for run in cw_grid.runs_from_rows(outcome.rows) for cell in run.cells
        }
        self.assertIn((2, 2), covered)

    def test_a_stray_nothing_can_cover_keeps_the_grid_from_conforming(self) -> None:
        outcome = cw_search.search(
            _themed_bank(),
            _config(rows=3, cols=5, start=("Q....", ".....", "....."), min_themes=0),
            clock=_still,
        )
        self.assertFalse(outcome.conforming)
        self.assertIn(
            "the fixed letter Q at (0, 0) belongs to no entry", outcome.missed
        )

    def test_an_island_letter_at_an_entrys_corner_is_no_missed_constraint(self) -> None:
        rows = ("A.....", ".CHALK", "......")
        request = _config(
            rows=3, cols=6, start=("A.....", "......", "......"), min_themes=0
        )
        self.assertEqual(
            cw_accept.missed_constraints(rows, _themed_bank(), request), ()
        )

    def test_without_a_source_a_lone_letter_is_not_judged(self) -> None:
        rows = ("Q.....", ".CHALK", "......")
        request = _config(rows=3, cols=6, min_themes=0)
        self.assertEqual(
            cw_accept.missed_constraints(rows, _themed_bank(), request), ()
        )


#: ALPH across the top of a 3x5: ALPHA is the only answer that completes it.
_HALF_ALPHA = ("ALPH.", ".....", ".....")

#: The empty 3x5 board a source holding a partial run falls back to.
_EMPTY_3X5 = (".....", ".....", ".....")


class TestPartialSourceRuns(unittest.TestCase):
    """A half-written source word is completed, never written half-written."""

    def test_the_walk_completes_a_partial_run(self) -> None:
        outcome = cw_search.search(
            _themed_bank(), _config(rows=3, cols=5, start=_HALF_ALPHA), clock=_still
        )
        self.assertTrue(outcome.conforming, outcome.missed)
        self.assertIn(_run(0, 0, "ALPHA"), cw_grid.runs_from_rows(outcome.rows))

    def test_a_partial_run_is_no_detour_and_spends_no_detour_budget(self) -> None:
        # A detour is a break the walk made; a source's half-written word is not
        # one, and the walk stays free around it. With no detour budget at all,
        # a board standing on ALPH must still be expanded: counted as a detour,
        # the very first board would be cut and nothing would ever finish it.
        with mock.patch.object(cw_search, "DETOUR_BUDGET", 0):
            outcome = cw_search.search(
                _themed_bank(), _config(rows=3, cols=5, start=_HALF_ALPHA), clock=_still
            )
        self.assertTrue(outcome.conforming, outcome.missed)
        self.assertIn(_run(0, 0, "ALPHA"), cw_grid.runs_from_rows(outcome.rows))

    def test_a_completion_fills_the_gap_between_two_partial_runs(self) -> None:
        start = ("AL.HA", ".....", ".....")
        outcome = cw_search.search(
            _themed_bank(), _config(rows=3, cols=5, start=start), clock=_still
        )
        self.assertTrue(outcome.conforming, outcome.missed)
        self.assertEqual(outcome.rows[0], "ALPHA")

    def test_a_held_entry_beside_a_partial_run_is_still_never_extended(self) -> None:
        # JANET would conform over JANE; only ALPHA may grow out of the source.
        start = ("JANE.", ".....", "ALPH.")
        outcome = cw_search.search(
            _bank(["JANE", "JANET", "ALPHA"]),
            _config(rows=3, cols=5, start=start, min_themes=0),
            clock=_still,
        )
        self.assertTrue(outcome.conforming, outcome.missed)
        runs = cw_grid.runs_from_rows(outcome.rows)
        self.assertIn(_run(0, 0, "JANE"), runs)
        self.assertIn(_run(2, 0, "ALPHA"), runs)

    def test_an_unfinished_walk_writes_an_empty_board_naming_the_run(self) -> None:
        # ALPHA would put A above the Z, and AZ is no answer, so the one move
        # that completes ALPH is never allowed. The source breaks the one rule,
        # so the best-effort grid cannot be the source either.
        start = ("ALPH.", "....Z", ".....")
        outcome = cw_search.search(
            _themed_bank(), _config(rows=3, cols=5, start=start), clock=_still
        )
        self.assertFalse(outcome.conforming)
        self.assertGreater(outcome.steps, 0)
        self.assertEqual(outcome.rows, _EMPTY_3X5)
        self.assertEqual(
            outcome.missed,
            (
                "the partial run 'ALPH' across at (0, 0) was never completed by a "
                "bank answer",
            ),
        )

    def test_a_completed_grid_that_misses_density_is_the_best_effort(self) -> None:
        # ALPHA leaves 66.7% blocked, under a 70% floor the source (73.3%)
        # still met: a legal grid holding every source letter beats the
        # empty fallback.
        outcome = cw_search.search(
            _themed_bank(),
            _config(rows=3, cols=5, start=_HALF_ALPHA, min_blocked=70.0),
            clock=_still,
        )
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.rows[0], "ALPHA")

    def test_a_refusal_under_a_partial_source_writes_an_empty_board(self) -> None:
        outcome = cw_search.search(
            _themed_bank(),
            _config(rows=3, cols=5, start=_HALF_ALPHA, min_themes=4),
            clock=_still,
        )
        self.assertEqual(outcome.steps, 0)
        self.assertEqual(outcome.rows, _EMPTY_3X5)

    def test_preflight_excuses_a_partial_run_that_can_still_be_completed(
        self,
    ) -> None:
        self.assertEqual(
            cw_search.preflight(
                _themed_bank(), _config(rows=3, cols=5, start=_HALF_ALPHA)
            ),
            (),
        )

    def test_preflight_refuses_a_partial_run_nothing_left_can_complete(
        self,
    ) -> None:
        # Pinned elsewhere, ALPHA is used, and no other answer finishes ALPH.
        config = _config(
            rows=3,
            cols=5,
            start=_HALF_ALPHA,
            features=(_pin("ALPHA", 2, 0, cw_grid.ACROSS),),
        )
        reasons = cw_search.preflight(_themed_bank(), config)
        self.assertEqual(len(reasons), 1)
        self.assertIn("'ALPH'", reasons[0])


def _run(row: int, col: int, text: str) -> cw_grid.Run:
    """The ACROSS run `text` starting at (row, col)."""
    return cw_grid.Run(row=row, col=col, direction=cw_grid.ACROSS, text=text)
