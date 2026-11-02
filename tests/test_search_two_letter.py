"""Tests that the walk acts on `--max-two-letter`: an over-cap grid is walked past, not kept.

`test_search_parts.py` proves `cw_accept.missed_constraints` names the cap. That cannot
show the search consults the verdict: that with a look-ahead of zero an over-cap grid
is not taken as the first conforming one and returned. The board below was found by
searching small banks for one where the cap changes the grid the walk returns.
"""

import unittest
from collections.abc import Sequence

import cw_config
import cw_grid
import cw_search

from tests.search_fixtures import config as _config
from tests.search_fixtures import one_theme_bank as _one_theme_bank
from tests.search_fixtures import still as _still

#: Two two-letter answers among longer ones: the walk's first grid stands AT down.
_ANSWERS = ["AT", "IS", "OAT", "RAT", "TEN", "TONE"]


def _request(max_two_letter: int | None = None) -> cw_config.FillConfig:
    """A 3x3 dense enough (56% blocked at most) that its first grid is two crossing runs."""
    return _config(
        rows=3, cols=3, seed=32, max_blocked=56.0, max_two_letter=max_two_letter
    )


def _two_letter_entries(rows: Sequence[str]) -> int:
    """How many of `rows`' runs are two letters long."""
    return sum(1 for run in cw_grid.runs_from_rows(rows) if len(run.text) == 2)


class TestTheWalkHoldsToTheCap(unittest.TestCase):
    """The same request with and without a cap: only the cap differs, so it moved the grid."""

    def test_without_a_cap_the_first_grid_carries_a_two_letter_entry(self) -> None:
        outcome = cw_search.search(_one_theme_bank(_ANSWERS), _request(), clock=_still)
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, ("A..", "TEN", "..."))
        self.assertEqual(_two_letter_entries(outcome.rows), 1)

    def test_a_cap_of_zero_walks_on_to_a_grid_without_one(self) -> None:
        outcome = cw_search.search(
            _one_theme_bank(_ANSWERS), _request(max_two_letter=0), clock=_still
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, (".R.", "OAT", ".T."))
        self.assertEqual(_two_letter_entries(outcome.rows), 0)
