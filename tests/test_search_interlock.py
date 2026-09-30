"""Tests for cw_search on an interlocked grid: one the walk can only reach by passing
through a run that is not an answer yet.

The fixture (`tests/interlock_fixtures.py`) is a dense, hand-shaped 5x5. From the state
a one-word-at-a-time walk gets stuck in, every remaining answer placed ALONE breaks the
one rule, and the smallest legal step is two answers placed together. So a walk that
insists every grid it passes through already obeys the rule stops short, however large
its budget.

This suite pins both halves of letting the walk pass through such a run: the walk
reaches the grid, and every grid a search RETURNS -- conforming or best-effort, however
the walk ends -- still obeys the rule in full.

It also pins what that latitude must not cost. A step that breaks the rule opens a
detour, and on a bank whose runs nearly all have some answer that could complete them,
a detour that never repairs can take every node the walk has. So a detour is bounded:
past a fixed number of broken boards the walk gives it up and goes back.
"""

import unittest

import cw_grid
import cw_place
import cw_search

from tests import interlock_fixtures as grids
from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import pin as _pin
from tests.search_fixtures import still as _still

#: A node cap far above what reaching the target needs, so a failure to reach it
#: is the walk's shape and not its budget.
_AMPLE_STEPS = 2000


class TestReachesAnInterlockedGrid(unittest.TestCase):
    """The walk passes through partial runs, and so reaches the dense grid."""

    def _search(self, *pins: cw_grid.Run) -> cw_search.SearchOutcome:
        """Search for the target with `pins` fixed, at the target's own density."""
        return cw_search.search(
            _bank(list(grids.ANSWERS)),
            _config(
                rows=5,
                cols=5,
                min_blocked=0.0,
                max_blocked=grids.TARGET_BLOCKED,
                min_themes=0,
                max_steps=_AMPLE_STEPS,
                features=tuple(
                    _pin(run.text, run.row, run.col, run.direction) for run in pins
                ),
            ),
            clock=_still,
        )

    def test_from_an_empty_board(self) -> None:
        # Either orientation, and asserted as exactly those two grids rather than
        # by pinning a seed: which one comes first is the hashed tie-break's
        # call, and a test that bet on it would be pinning the key, not the walk.
        outcome = self._search()
        self.assertTrue(outcome.conforming)
        self.assertIn(outcome.rows, (grids.TARGET, grids.TRANSPOSED))

    def test_from_pins_on_three_of_its_lines(self) -> None:
        # The pins fix the orientation, so here the grid is exactly the target.
        outcome = self._search(*grids.pinned_lines())
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, grids.TARGET)


class TestReturnedGridsObeyTheRule(unittest.TestCase):
    """However the walk ends, the grid it hands back obeys the rule in full."""

    def test_every_returned_grid_obeys_the_rule_under_every_budget(self) -> None:
        # The walk may hold a run that is not an answer yet, so the grid it
        # is standing on when a budget runs out, or when a loose density window
        # is met, can be one no one could print. Swept across ceilings and node
        # caps so the walk is stopped inside such a state as well as outside it.
        allowed = frozenset(grids.ANSWERS)
        for max_blocked in (16.0, 32.0, 48.0, 64.0, 80.0):
            for max_steps in range(1, 12):
                with self.subTest(max_blocked=max_blocked, max_steps=max_steps):
                    outcome = cw_search.search(
                        _bank(list(grids.ANSWERS)),
                        _config(
                            rows=5,
                            cols=5,
                            min_blocked=0.0,
                            max_blocked=max_blocked,
                            min_themes=0,
                            max_steps=max_steps,
                        ),
                        clock=_still,
                    )
                    self.assertEqual(
                        cw_place.grid_violations(outcome.rows, allowed), ()
                    )


class TestADetourIsBounded(unittest.TestCase):
    """A detour that never repairs is given up, and the walk reaches the grid past it."""

    #: A 7x7 board found by a seeded sweep of random letter strings and cut down to
    #: the answers that still show it. The walk lays BBCBFAD across and ECEBCAD
    #: down through the middle, and with no bound on a detour it never gets past
    #: them: at the cap below, the best grid it has seen still holds only those two.
    #: The letters mean nothing, so no run is an answer by accident.
    ANSWERS = (
        "BBCBFAD",
        "DEEDEDC",
        "ECD",
        "ECDACAA",
        "ECDB",
        "ECDC",
        "ECE",
        "ECEBCAD",
        "ECEE",
        "EDB",
        "EDDAB",
        "EDDB",
        "EDEDA",
        "EFDE",
    )

    #: Far past the node the grid is reached on, so a miss is the walk's shape.
    #: A walk with no bound on a detour spent all of it on this board.
    STEPS = 600

    #: The grid, and the node it conformed on, when a detour is given up at the
    #: budget: pinned to the node because arriving late means a detour ran long.
    GRID = (
        "DEEDEDC",
        ".C.....",
        ".E..E.E",
        "BBCBFAD",
        ".C..D.E",
        ".A..ECD",
        "EDDB..A",
    )
    NODE = 105

    def test_the_walk_reaches_the_grid_past_a_detour_that_never_repairs(self) -> None:
        outcome = cw_search.search(
            _bank(list(self.ANSWERS)),
            _config(
                rows=7,
                cols=7,
                seed=12,
                min_blocked=0.0,
                max_blocked=40.0,
                min_themes=0,
                max_steps=self.STEPS,
            ),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, self.GRID)
        self.assertEqual(outcome.steps, self.NODE)


class TestADetourThatRepairsIsKept(unittest.TestCase):
    """The budget is wide enough for a detour a real grid needs.

    Each detour a budget cuts is a grid it may lose, so the bound is a floor as
    much as a ceiling. This 6x6 board's grid lies at the end of one detour of
    thirty-three broken boards: a budget of thirty-two misses it at the cap
    below, and every budget from thirty-three up reaches it on node 41. It is
    the longest detour to a grid any measurement found.
    """

    #: Found by a seeded sweep of random letter strings, where a budget of 32 lost
    #: it, and cut down to the answers that still show it. The letters mean
    #: nothing, so no run is an answer by accident.
    ANSWERS = (
        "AB",
        "ABCD",
        "ACAB",
        "ACB",
        "ACCACB",
        "ACCDDD",
        "ADAB",
        "ADD",
        "BA",
        "BCABAA",
        "CAB",
        "CAC",
        "CACA",
        "CAD",
        "CB",
        "CBAD",
        "CD",
        "CDDDBD",
        "DAAD",
        "DABADC",
        "DABCBB",
        "DACBDB",
        "DD",
    )

    #: A walk that gave the detour up too soon spent all of this on the board.
    STEPS = 2000

    GRID = (
        "DACBDB",
        "ACB...",
        "BCABAA",
        "ADD.CB",
        "DD.CAC",
        "CDDDBD",
    )
    NODE = 41

    def test_the_walk_follows_a_thirty_three_board_detour_to_its_grid(self) -> None:
        outcome = cw_search.search(
            _bank(list(self.ANSWERS)),
            _config(
                rows=6,
                cols=6,
                seed=4,
                min_blocked=0.0,
                max_blocked=16.0,
                min_themes=0,
                max_steps=self.STEPS,
            ),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(outcome.rows, self.GRID)
        self.assertEqual(outcome.steps, self.NODE)
