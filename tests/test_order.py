"""Tests for cw_order: which placements a search node tries, and in what order.

The walk that consumes this order is tested in test_search.py, and the order it
produces is observed through emitted grids there (TestCandidateOrdering). These
are the parts the order is assembled from, each tested where its rule can be
inverted on its own.
"""

import unittest
from unittest import mock

import cw_grid
import cw_order
import cw_place

# Aliased to the private spellings the test bodies use, so a fixture shared with
# the cw_search suites is still defined exactly once (see search_fixtures).
from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import grid as _grid
from tests.search_fixtures import themed_bank as _themed_bank


class TestOrderKey(unittest.TestCase):
    """Ordering is a pure function of seed and token -- never builtin hash()."""

    def test_is_stable_across_calls(self) -> None:
        self.assertEqual(cw_order.order_key(7, "CAT"), cw_order.order_key(7, "CAT"))

    def test_differs_by_seed(self) -> None:
        self.assertNotEqual(cw_order.order_key(7, "CAT"), cw_order.order_key(8, "CAT"))

    def test_differs_by_token(self) -> None:
        self.assertNotEqual(cw_order.order_key(7, "CAT"), cw_order.order_key(7, "COW"))

    def test_a_token_carries_position_and_direction(self) -> None:
        # Two candidates for the same word must not share a key: if they did,
        # the winner would fall to enumeration order rather than to the seed.
        across = cw_place.Placement("ALPHA", 1, 2, cw_grid.ACROSS)
        tokens = {
            cw_order._placement_token(across),
            cw_order._placement_token(cw_place.Placement("ALPHA", 1, 2, cw_grid.DOWN)),
            cw_order._placement_token(
                cw_place.Placement("ALPHA", 2, 1, cw_grid.ACROSS)
            ),
        }
        self.assertEqual(len(tokens), 3)


class TestCenteredStart(unittest.TestCase):
    """The seed sits centered, computed from both dimensions and the answer."""

    def test_centers_an_across_seed(self) -> None:
        # 7x11, length 5: row (7-1)//2 = 3, col (11-5)//2 = 3. A non-square grid
        # and a non-trivial length on purpose, so arithmetic replaced by a
        # constant -- 0, or either dimension's midpoint -- cannot pass.
        self.assertEqual(cw_order._centered_start(7, 11, 5, cw_grid.ACROSS), (3, 3))

    def test_centers_a_down_seed(self) -> None:
        # Same grid and length, other axis: row (7-5)//2 = 1, col (11-1)//2 = 5.
        self.assertEqual(cw_order._centered_start(7, 11, 5, cw_grid.DOWN), (1, 5))

    def test_centers_an_across_seed_on_an_even_grid(self) -> None:
        # Odd dimensions cannot see the `- 1` at all: (7-1)//2 and 7//2 are
        # both 3. On 8 rows they part company -- (8-1)//2 is 3, 8//2 is 4 --
        # so only an even grid pins which of the two the code computes.
        self.assertEqual(cw_order._centered_start(8, 10, 4, cw_grid.ACROSS), (3, 3))

    def test_centers_a_down_seed_on_an_even_grid(self) -> None:
        # The same distinction on the other axis: (10-1)//2 is 4, 10//2 is 5.
        self.assertEqual(cw_order._centered_start(8, 10, 4, cw_grid.DOWN), (2, 4))


class TestNewCellCount(unittest.TestCase):
    """Scoring counts the cells a placement would ADD, not the ones it covers."""

    def test_counts_only_the_cells_a_placement_would_newly_fill(self) -> None:
        placement = cw_place.Placement("COW", 0, 0, cw_grid.DOWN)
        self.assertEqual(
            cw_order._new_cell_count(_grid(("C..", "...", "...")), placement), 2
        )

    def test_counts_a_whole_answer_on_an_empty_grid(self) -> None:
        placement = cw_place.Placement("COW", 0, 0, cw_grid.ACROSS)
        self.assertEqual(cw_order._new_cell_count(cw_grid.Grid(3, 3), placement), 3)


class TestSortKey(unittest.TestCase):
    """Candidate order: a source run's completion, a bare feature, more cells, a short theme."""

    def _by_tiebreak(self) -> tuple[cw_place.Placement, cw_place.Placement]:
        """Two placements, in the order their seeded tie-break key alone puts them.

        Returning them in that order is what makes the assertions decisive: the
        candidate the tie-break would put LAST is the one given the winning
        score, so a sort that dropped a scoring term flips the result rather
        than passing half the time on the hash's say-so.
        """
        pair = (
            cw_place.Placement("ALPHA", 0, 0, cw_grid.ACROSS),
            cw_place.Placement("BRAVO", 0, 0, cw_grid.DOWN),
        )
        first, second = sorted(
            pair, key=lambda p: cw_order.order_key(7, cw_order._placement_token(p))
        )
        return first, second

    def test_prefers_completing_a_partial_run_over_every_other_ranking(self) -> None:
        # Fewer cells, no bare feature, a satisfied theme, and the losing
        # tie-break: completing a source's partial run still sorts first.
        first, second = self._by_tiebreak()
        self.assertLess(
            cw_order._sort_key(second, True, False, 1, False, 7),
            cw_order._sort_key(first, False, True, 4, True, 7),
        )

    def test_prefers_a_bare_feature_over_every_other_ranking(self) -> None:
        # The feature fills fewer cells AND its theme is already satisfied, and
        # it still sorts first: the rank leads both, it is not a later tie-break.
        first, second = self._by_tiebreak()
        self.assertLess(
            cw_order._sort_key(second, False, True, 1, False, 7),
            cw_order._sort_key(first, False, False, 4, True, 7),
        )

    def test_prefers_the_placement_that_fills_more_cells(self) -> None:
        first, second = self._by_tiebreak()
        self.assertLess(
            cw_order._sort_key(second, False, False, 4, False, 7),
            cw_order._sort_key(first, False, False, 3, True, 7),
        )

    def test_prefers_a_short_theme_when_the_fill_counts_tie(self) -> None:
        first, second = self._by_tiebreak()
        self.assertLess(
            cw_order._sort_key(second, False, False, 3, True, 7),
            cw_order._sort_key(first, False, False, 3, False, 7),
        )

    def test_falls_back_to_the_seeded_tiebreak(self) -> None:
        first, second = self._by_tiebreak()
        self.assertLess(
            cw_order._sort_key(first, False, False, 3, True, 7),
            cw_order._sort_key(second, False, False, 3, True, 7),
        )


class TestPartialRunsRankFirst(unittest.TestCase):
    """A placement laid along a source's partial run is tried before any other."""

    def test_the_completion_leads_although_it_fills_one_cell(self) -> None:
        # AMBER and ANVIL down from the A each fill four cells; ALPHA fills one.
        # Ranked by cells alone, the walk would wander before finishing ALPH.
        start = ("ALPH.....", ".........", ".........", ".........", ".........")
        config = _config(rows=5, cols=9, start=start)
        candidates = cw_order.ordered_candidates(_grid(start), _themed_bank(), config)
        self.assertEqual(
            candidates[0], cw_place.Placement("ALPHA", 0, 0, cw_grid.ACROSS)
        )

    def test_a_finished_completion_ranks_nothing_first(self) -> None:
        # ALPH is already ALPHA, an answer: nothing is left to finish, so the
        # one-cell ALPHAS laid along it must not jump the four-cell crossings.
        start = ("ALPH.....", ".........", ".........", ".........", ".........")
        grid = _grid(("ALPHA....",) + start[1:])
        candidates = cw_order.ordered_candidates(
            grid,
            _bank(["ALPHA", "ALPHAS", "AMBER"]),
            _config(rows=5, cols=9, start=start, min_themes=0),
        )
        self.assertIn(cw_place.Placement("ALPHAS", 0, 0, cw_grid.ACROSS), candidates)
        self.assertNotEqual(
            candidates[0], cw_place.Placement("ALPHAS", 0, 0, cw_grid.ACROSS)
        )

    def test_the_completion_is_never_offered_alone(self) -> None:
        # Ranked first, not filtered: the walk stays free to lay other letters
        # around a source's half-written word.
        start = ("ALPH.....", ".........", ".........", ".........", ".........")
        config = _config(rows=5, cols=9, start=start)
        candidates = cw_order.ordered_candidates(_grid(start), _themed_bank(), config)
        self.assertIn(cw_place.Placement("AMBER", 0, 0, cw_grid.DOWN), candidates)


class TestAWalkBreakOffersOnlyItsRepairs(unittest.TestCase):
    """A board holding a break the walk made offers only placements laid over it.

    The walk stood on that board only because an unused answer could still be laid
    over the break, so a repair is always there to try, and every other placement
    opens a subtree that must repair the break anyway -- on a bank rich in short
    answers, one the walk never climbed back out of.
    """

    def test_without_a_source_only_the_repair_is_offered(self) -> None:
        # The same board as a source's partial run, but nothing here is the
        # source's: ALPH is the walk's own break, and ALPHA is its one repair.
        board = ("ALPH.....", ".........", ".........", ".........", ".........")
        candidates = cw_order.ordered_candidates(
            _grid(board), _themed_bank(), _config(rows=5, cols=9)
        )
        self.assertEqual(
            candidates, [cw_place.Placement("ALPHA", 0, 0, cw_grid.ACROSS)]
        )

    def test_a_board_that_obeys_the_rule_offers_every_crossing(self) -> None:
        board = ("ALPHA....", ".........", ".........", ".........", ".........")
        candidates = cw_order.ordered_candidates(
            _grid(board), _themed_bank(), _config(rows=5, cols=9)
        )
        self.assertIn(cw_place.Placement("AMBER", 0, 0, cw_grid.DOWN), candidates)
        self.assertIn(cw_place.Placement("ANVIL", 0, 0, cw_grid.DOWN), candidates)

    def test_a_break_is_repaired_without_building_the_rest_of_the_board(self) -> None:
        # What a broken board may build is bounded by its break alone: one fit
        # check per place an answer holds the break's letters, however many
        # letters stand elsewhere, never the board's every crossing filtered
        # down. CAT, CAR and RAT give TACT, TRACT, CARAT and ATTACK dozens of
        # crossings; LT is the one break, and only WILTS, SALT and BOLT hold it.
        board = ("CAT......", "A........", "RAT......", ".........", "...LT....")
        answers = ["CAT", "CAR", "RAT", "WILTS", "SALT", "BOLT", "TACT", "TRACT"]
        answers += ["CARAT", "ATTACK"]
        alignments = sum(
            answer.startswith("LT", index)
            for answer in answers
            for index in range(len(answer))
        )
        with mock.patch.object(cw_place, "fits", wraps=cw_place.fits) as fits:
            candidates = cw_order.ordered_candidates(
                _grid(board), _bank(answers), _config(rows=5, cols=9)
            )
        self.assertEqual(
            {placement.answer for placement in candidates}, {"WILTS", "SALT", "BOLT"}
        )
        self.assertLessEqual(fits.call_count, alignments)


if __name__ == "__main__":
    unittest.main()
