"""Tests for cw_search choosing among conforming grids within --look-ahead nodes.

Every case here is built so that it holds WHICHEVER grid the walk happens to reach
first. The preference and theme cases run in both directions, so one direction has to
override the grid found first; the letters case uses a ceiling loose enough that the
pinned board itself conforms at the very first node.
"""

import unittest

import cw_bank
import cw_board
import cw_config
import cw_search

from tests import interlock_fixtures as grids
from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import entries_bank as _entries_bank
from tests.search_fixtures import pin as _pin
from tests.search_fixtures import still as _still

#: A look-ahead and node cap far above what these small fixtures need.
_AMPLE = 5000

#: A ceiling the pinned board alone meets: its 12 letters leave 52% blocked.
_LOOSE = 60.0


def _request(
    *,
    look_ahead: int,
    max_blocked: float = grids.TARGET_BLOCKED,
    prefer: tuple[str, ...] = (),
    max_steps: int = _AMPLE,
) -> cw_config.FillConfig:
    """The pinned interlock request, varied by the knobs these tests turn."""
    return _config(
        rows=5,
        cols=5,
        min_blocked=0.0,
        max_blocked=max_blocked,
        min_themes=0,
        max_steps=max_steps,
        look_ahead=look_ahead,
        prefer=prefer,
        features=tuple(
            _pin(run.text, run.row, run.col, run.direction)
            for run in grids.pinned_lines()
        ),
    )


def _two_fills(themed: tuple[str, ...] = ()) -> cw_bank.Bank:
    """The target's answers plus the alternate pair; `themed` answers carry a theme."""
    answers = (*grids.ANSWERS, *grids.ALTERNATE_ANSWERS)
    return _entries_bank(
        tuple((answer, "a" if answer in themed else None) for answer in answers),
        {"a": "A"},
    )


class TestLookAhead(unittest.TestCase):
    """How far past the first grid the walk keeps looking, and what it keeps."""

    def test_a_look_ahead_of_zero_keeps_the_first_conforming_grid(self) -> None:
        config = _request(look_ahead=0, max_blocked=_LOOSE)
        outcome = cw_search.search(_bank(list(grids.ANSWERS)), config, clock=_still)
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, cw_board.pinned_board(config).to_rows())

    def test_a_look_ahead_trades_the_first_grid_for_one_with_more_letters(self) -> None:
        outcome = cw_search.search(
            _bank(list(grids.ANSWERS)),
            _request(look_ahead=_AMPLE, max_blocked=_LOOSE),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, grids.TARGET)

    def test_a_full_tie_keeps_the_grid_found_first(self) -> None:
        # At the target's density only full fills conform, and with nothing
        # themed or preferred the two fills tie on every level of the score.
        first = cw_search.search(_two_fills(), _request(look_ahead=0), clock=_still)
        ahead = cw_search.search(
            _two_fills(), _request(look_ahead=_AMPLE), clock=_still
        )
        self.assertEqual(ahead.rows, first.rows)
        self.assertEqual(first.compared, 1)
        self.assertGreaterEqual(ahead.compared, 2)

    def test_a_budget_that_cuts_the_look_ahead_still_returns_a_conforming_grid(
        self,
    ) -> None:
        outcome = cw_search.search(
            _bank(list(grids.ANSWERS)),
            _request(look_ahead=_AMPLE, max_blocked=_LOOSE, max_steps=3),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertTrue(outcome.look_ahead_cut)

    def test_the_same_request_chooses_the_same_grid_twice(self) -> None:
        config = _request(look_ahead=_AMPLE, prefer=("VST",))
        first = cw_search.search(_two_fills(), config, clock=_still)
        second = cw_search.search(_two_fills(), config, clock=_still)
        self.assertEqual(first.rows, second.rows)
        self.assertEqual(first.steps, second.steps)


class TestPreference(unittest.TestCase):
    """A preferred answer decides between fills that tie on letters."""

    def test_preferring_the_alternate_fill_chooses_it(self) -> None:
        outcome = cw_search.search(
            _two_fills(), _request(look_ahead=_AMPLE, prefer=("VST",)), clock=_still
        )
        self.assertEqual(outcome.rows, grids.ALTERNATE)

    def test_preferring_the_target_fill_chooses_it(self) -> None:
        outcome = cw_search.search(
            _two_fills(), _request(look_ahead=_AMPLE, prefer=("RST",)), clock=_still
        )
        self.assertEqual(outcome.rows, grids.TARGET)


class TestThemes(unittest.TestCase):
    """Themed entries decide between fills that tie on letters and preferences."""

    def test_the_themed_alternate_fill_is_chosen(self) -> None:
        outcome = cw_search.search(
            _two_fills(themed=("VST", "HMV")), _request(look_ahead=_AMPLE), clock=_still
        )
        self.assertEqual(outcome.rows, grids.ALTERNATE)

    def test_the_themed_target_fill_is_chosen(self) -> None:
        outcome = cw_search.search(
            _two_fills(themed=("RST", "HMR")), _request(look_ahead=_AMPLE), clock=_still
        )
        self.assertEqual(outcome.rows, grids.TARGET)

    def test_a_preference_outranks_themes(self) -> None:
        outcome = cw_search.search(
            _two_fills(themed=("RST", "HMR")),
            _request(look_ahead=_AMPLE, prefer=("VST",)),
            clock=_still,
        )
        self.assertEqual(outcome.rows, grids.ALTERNATE)
