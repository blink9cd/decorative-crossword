"""Tests for cw_search with pinned features: the board a search starts from.

A pinned `--feature` is written onto the grid before the first node, and every
case here is about what that means for the walk: the pins sit at exactly their
cells, hold them under every seed, and are what the fill grows outward from.
The search's other behavior is in `test_search.py`.
"""

import unittest

import cw_config
import cw_feature
import cw_grid
import cw_place
import cw_search

from tests.search_fixtures import config as _config
from tests.search_fixtures import one_theme_bank as _one_theme_bank
from tests.search_fixtures import pin as _pin
from tests.search_fixtures import still as _still
from tests.search_fixtures import themed_bank as _themed_bank

#: A window a pin alone cannot meet on 9x9: 80% blocked needs at least 17
#: filled cells and a five-letter pin holds 5, so the walk has to cross it.
_DENSE_WINDOW = 80.0

#: A wall clock no search here can reach, so only the node cap can stop one.
_LONG_BUDGET = 3600.0

#: A node cap generous enough to reach the dense window.
_LONG_STEPS = 20000

#: Answers that cross JANE and DOE and one another, every one longer than DOE.
#: Letter patterns rather than words, on purpose: what decides the contest below
#: is only how many cells each crossing fills, and a pattern alphabet guarantees
#: each of these fills more than a three-letter answer ever can.
_CROSSING_PATTERNS = (
    "DADAD",
    "DERAD",
    "JADAD",
    "JERAD",
    "NADAD",
    "NERAD",
    "RADAD",
    "RERAD",
    "SADAD",
    "SERAD",
    "TADAD",
    "TERAD",
)

#: The node cap for that contest. Measured with bare features ranked by cells
#: alone, the walk spent all 40 nodes without placing DOE on 5 of the 10 seeds
#: below beside a pin, and on 4 of them as the bare feature the seed did not
#: take. Ranked first, every run conforms by node 3.
_CONTEST_STEPS = 40

#: Every seed in a range, not a chosen miss: a seed that reached the feature
#: anyway passes with the rank removed, so only the whole range is decisive.
_CONTEST_SEEDS = range(1, 11)


class TestPinnedFeatures(unittest.TestCase):
    """Anchored features are the board the search starts from, and never move."""

    def _dense(self, *pins: cw_feature.Feature, seed: int = 7) -> cw_config.FillConfig:
        """A window the pins alone cannot meet, so the walk has to cross them."""
        return _config(
            seed=seed,
            max_blocked=_DENSE_WINDOW,
            time_budget=_LONG_BUDGET,
            max_steps=_LONG_STEPS,
            features=pins,
        )

    def test_an_anchored_feature_occupies_exactly_its_cells(self) -> None:
        # The top-left corner, deliberately off-center: a bare CHALK seeds at
        # the centered start, so an implementation that dropped the anchor and
        # fell back to seeding would put CHALK somewhere else and fail here.
        outcome = cw_search.search(
            _themed_bank(),
            _config(features=(_pin("CHALK", 0, 0, cw_grid.ACROSS),)),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(
            cw_grid.find_answer(outcome.rows, "CHALK"),
            cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="CHALK"),
        )

    def test_several_anchors_are_the_starting_board_in_the_order_given(self) -> None:
        # A name-grid shape: one answer across the top, two hanging down from
        # its first and last letters. Every pin sits exactly where it was asked
        # for, and the placement history opens with the pins in flag order --
        # they were applied, and `placed` is the record of what was applied.
        pins = (
            _pin("ALPHA", 0, 0, cw_grid.ACROSS),
            _pin("AMBER", 0, 0, cw_grid.DOWN),
            _pin("ANVIL", 0, 4, cw_grid.DOWN),
        )
        outcome = cw_search.search(_themed_bank(), _config(features=pins), clock=_still)
        self.assertTrue(outcome.conforming)
        for run in (
            cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="ALPHA"),
            cw_grid.Run(row=0, col=0, direction=cw_grid.DOWN, text="AMBER"),
            cw_grid.Run(row=0, col=4, direction=cw_grid.DOWN, text="ANVIL"),
        ):
            with self.subTest(answer=run.text):
                self.assertEqual(cw_grid.find_answer(outcome.rows, run.text), run)
        self.assertEqual(
            outcome.placed[:3],
            (
                cw_place.Placement("ALPHA", 0, 0, cw_grid.ACROSS),
                cw_place.Placement("AMBER", 0, 0, cw_grid.DOWN),
                cw_place.Placement("ANVIL", 0, 4, cw_grid.DOWN),
            ),
        )

    def test_the_search_grows_outward_from_a_pin(self) -> None:
        # 80% blocked needs at least 17 filled cells on 9x9 and CHALK holds 5,
        # so this conforms only if the walk crosses the pin: the pinned board is
        # where `crossing_candidates` starts, with no separate seed beside it.
        outcome = cw_search.search(
            _themed_bank(),
            self._dense(_pin("CHALK", 0, 0, cw_grid.ACROSS)),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        self.assertEqual(
            cw_grid.find_answer(outcome.rows, "CHALK"),
            cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="CHALK"),
        )
        self.assertGreater(len(cw_grid.runs_from_rows(outcome.rows)), 1)

    def test_a_pin_holds_its_cells_under_every_seed(self) -> None:
        # Read unconditionally, not only on a conforming run: exit 1 still
        # writes the best grid seen, and a pin that drifted there would be a
        # wrong file sitting beside an honest exit code.
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                outcome = cw_search.search(
                    _themed_bank(),
                    self._dense(_pin("CHALK", 3, 1, cw_grid.DOWN), seed=seed),
                    clock=_still,
                )
                self.assertEqual(
                    cw_grid.find_answer(outcome.rows, "CHALK"),
                    cw_grid.Run(row=3, col=1, direction=cw_grid.DOWN, text="CHALK"),
                )

    def test_every_bare_feature_is_placed_and_one_takes_the_seed(self) -> None:
        # With no pin the board starts empty, so the one unanchored placement
        # the search makes must go to a feature -- any other opening word leaves
        # the whole budget free to be spent on grids that cannot conform.
        outcome = cw_search.search(
            _themed_bank(),
            _config(
                features=(
                    cw_feature.Feature("CHALK", None),
                    cw_feature.Feature("BRAVO", None),
                )
            ),
            clock=_still,
        )
        self.assertTrue(outcome.conforming)
        for answer in ("CHALK", "BRAVO"):
            with self.subTest(answer=answer):
                self.assertIsNotNone(cw_grid.find_answer(outcome.rows, answer))
        self.assertIn(outcome.placed[0].answer, ("CHALK", "BRAVO"))

    def test_refused_pins_leave_an_empty_board_rather_than_a_broken_one(self) -> None:
        # The pinned board breaks the one rule. Returning it as the best-effort
        # grid would write a file the tool exists never to write.
        outcome = cw_search.search(
            _one_theme_bank(["ALPHA", "BRAVO"]),
            _config(
                features=(
                    _pin("ALPHA", 0, 0, cw_grid.ACROSS),
                    _pin("BRAVO", 1, 0, cw_grid.ACROSS),
                )
            ),
            clock=_still,
        )
        self.assertEqual(outcome.steps, 0)
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.rows, (cw_grid.BLOCK * 9,) * 9)
        self.assertEqual(outcome.placed, ())

    def test_a_pinned_search_emits_the_same_grid_twice(self) -> None:
        config = self._dense(
            _pin("CHALK", 0, 0, cw_grid.ACROSS), _pin("CEDAR", 0, 0, cw_grid.DOWN)
        )
        first = cw_search.search(_themed_bank(), config, clock=_still)
        second = cw_search.search(_themed_bank(), config, clock=_still)
        self.assertEqual(first.rows, second.rows)
        self.assertEqual(first.steps, second.steps)

    def test_a_pin_is_never_extended_into_a_longer_answer(self) -> None:
        # One row, so nothing can cross and the only move on offer is JANET laid
        # over the pinned JANE. That leaves every pinned cell in place and still
        # removes JANE from the grid, because an entry is a whole run. The pinned
        # board must be what comes back -- even though JANET would land inside a
        # window the pinned board misses, which is exactly what would make it the
        # "best" grid if a pin were held as cells rather than as an entry.
        outcome = cw_search.search(
            _one_theme_bank(["JANE", "JANET"]),
            _config(
                rows=1,
                cols=9,
                max_blocked=50.0,
                features=(_pin("JANE", 0, 0, cw_grid.ACROSS),),
            ),
            clock=_still,
        )
        self.assertEqual(outcome.rows, ("JANE.....",))


class TestBareFeaturesAreCrossedFirst(unittest.TestCase):
    """A bare feature still off the board is tried ahead of every other answer.

    Once anything is on the board there is no seed slot, so a bare feature has
    to be reached by crossing. Ranked by cells alone, a short one fills fewer
    than any longer answer at every node and is tried last everywhere, which in
    a depth-first walk under a node cap means never.
    """

    def _contest(
        self, features: tuple[cw_feature.Feature, ...], seed: int
    ) -> cw_search.SearchOutcome:
        """One run of the contest a short bare feature loses when ranked by cells alone."""
        return cw_search.search(
            _one_theme_bank(["JANE", "DOE", *_CROSSING_PATTERNS]),
            _config(
                seed=seed,
                time_budget=0.0,
                max_steps=_CONTEST_STEPS,
                features=features,
            ),
            clock=_still,
        )

    def test_a_bare_feature_beside_a_pin_is_placed_under_every_seed(self) -> None:
        features = (
            _pin("JANE", 4, 0, cw_grid.ACROSS),
            cw_feature.Feature("DOE", None),
        )
        for seed in _CONTEST_SEEDS:
            with self.subTest(seed=seed):
                outcome = self._contest(features, seed)
                self.assertTrue(outcome.conforming)
                self.assertEqual(
                    cw_grid.find_answer(outcome.rows, "JANE"),
                    cw_grid.Run(row=4, col=0, direction=cw_grid.ACROSS, text="JANE"),
                )
                self.assertIsNotNone(cw_grid.find_answer(outcome.rows, "DOE"))

    def test_the_bare_feature_the_seed_did_not_take_is_placed_too(self) -> None:
        # No pin: JANE fills more cells than DOE, so it takes the one opening
        # move, and DOE is left to the same contest as a feature beside a pin.
        features = (
            cw_feature.Feature("JANE", None),
            cw_feature.Feature("DOE", None),
        )
        for seed in _CONTEST_SEEDS:
            with self.subTest(seed=seed):
                outcome = self._contest(features, seed)
                self.assertTrue(outcome.conforming)
                for answer in ("JANE", "DOE"):
                    self.assertIsNotNone(cw_grid.find_answer(outcome.rows, answer))

    def test_a_bare_feature_ranked_first_still_never_extends_a_pin(self) -> None:
        # One row, so JANET laid over the pinned JANE is the only move there is,
        # and it is ranked first. It must still be refused: the rank orders what
        # reaches the step check and never goes around it.
        outcome = cw_search.search(
            _one_theme_bank(["JANE", "JANET"]),
            _config(
                rows=1,
                cols=9,
                max_blocked=50.0,
                features=(
                    _pin("JANE", 0, 0, cw_grid.ACROSS),
                    cw_feature.Feature("JANET", None),
                ),
            ),
            clock=_still,
        )
        self.assertEqual(outcome.rows, ("JANE.....",))
        self.assertFalse(outcome.conforming)


class TestTheRankIsInertWithoutABareFeatureToPlace(unittest.TestCase):
    """A run with no bare feature left to place walks the same nodes it would without the rank.

    The rank is one more leading level in the sort key, and it takes the same
    value for every candidate unless a bare feature is still off the board. So
    each run below is pinned by the node it conformed on and the grid it
    reached, both measured with the rank removed: a reordered walk reaches its
    first conforming grid at a different node, and the count is what moves.
    """

    def test_the_walk_is_unchanged_node_for_node(self) -> None:
        cases = (
            (
                "no feature",
                _config(seed=3, max_blocked=62.0, time_budget=0.0, max_steps=3000),
                37,
                (
                    "...A.....",
                    "CRANE....",
                    "H..V.....",
                    "A..I..C..",
                    "L.BLADE..",
                    "K.R...D..",
                    "..ALPHA..",
                    "..V...R..",
                    "BROOK....",
                ),
            ),
            (
                "pins only",
                _config(
                    seed=7,
                    max_blocked=62.0,
                    time_budget=0.0,
                    max_steps=3000,
                    features=(_pin("CHALK", 0, 0, cw_grid.ACROSS),),
                ),
                293,
                (
                    "CHALK....",
                    "..N......",
                    "..V..B...",
                    "..I..L...",
                    ".ALPHA.C.",
                    ".M...D.R.",
                    ".B..CEDAR",
                    ".E.....N.",
                    "BROOK..E.",
                ),
            ),
            (
                "one bare feature, which the seed takes",
                _config(
                    seed=7,
                    max_blocked=66.0,
                    time_budget=0.0,
                    max_steps=3000,
                    feature="CHALK",
                ),
                193,
                (
                    ".........",
                    ".........",
                    "..B.CRANE",
                    "..R.H....",
                    "..A.ALPHA",
                    "..V.L...M",
                    "BROOK...B",
                    "........E",
                    "....CEDAR",
                ),
            ),
        )
        for name, config, steps, rows in cases:
            with self.subTest(case=name):
                outcome = cw_search.search(_themed_bank(), config, clock=_still)
                self.assertTrue(outcome.conforming)
                self.assertEqual(outcome.steps, steps)
                self.assertEqual(outcome.rows, rows)
