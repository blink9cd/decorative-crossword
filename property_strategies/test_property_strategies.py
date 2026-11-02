"""Tests for property_strategies: the run scan, and the bounds it promises.

Two things here that the suites in `tests/` cannot do for themselves. The
independent run scan is the thing every grid property ultimately rests on, and
exercised only through the subject it exists to check, it would hide its own
defects; so it is tested directly here. And every pinned regression seed must
be a request the strategy could itself have drawn; that is checked here against
the strategy's own declared bounds rather than left as prose.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, given, settings

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_grid  # noqa: E402 - same bootstrap
import property_strategies as ps  # noqa: E402 - same bootstrap

# The same convention the property suites follow, and for the same reason: a
# registered profile loaded before the class bodies, never an `@settings`
# decorator. Its own name so import order cannot decide which profile the
# `@given` test below snapshots. See `tests/test_search_properties.py` for the
# full note.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_strategy_bounds",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_strategy_bounds")


def _assert_within_declared_bounds(
    case: unittest.TestCase, request: ps.Request
) -> None:
    """Fail `case` unless `request` is one `ps.fill_requests` could have drawn.

    One checker for both readers below, so the strategy's declared bounds are
    asserted in one place: the drawn requests and every pinned seed are held to
    exactly the same contract.
    """
    bank, config = request
    answers = [entry.answer for entry in bank.entries]
    case.assertLessEqual(ps.MIN_ANSWERS, len(answers))
    case.assertLessEqual(len(answers), ps.MAX_ANSWERS)
    case.assertEqual(len(set(answers)), len(answers), "answers must be unique")
    for answer in answers:
        case.assertLessEqual(cw_grid.MIN_RUN, len(answer))
        case.assertLessEqual(len(answer), ps.MIN_SIDE)
        case.assertLessEqual(set(answer), set(ps.LETTERS))
    case.assertIsNotNone(
        bank.entries[0].theme,
        "the first entry is always themed, so a floor is reachable",
    )
    for entry in bank.entries:
        case.assertIn(entry.theme, (None, *ps.THEME_KEYS))
        case.assertIsNone(entry.clue)
    declared = {theme for theme in (e.theme for e in bank.entries) if theme is not None}
    case.assertEqual(
        dict(bank.themes),
        {
            key: cw_bank.ThemeInfo(label=key.upper(), summary=f"All about {key}")
            for key in sorted(declared)
        },
    )
    for side in (config.rows, config.cols):
        case.assertLessEqual(ps.MIN_SIDE, side)
        case.assertLessEqual(side, ps.MAX_SIDE)
    case.assertEqual(config.min_blocked, ps.MIN_BLOCKED)
    case.assertIn(config.max_blocked, ps.MAX_BLOCKED_CHOICES)
    # 1, not 0: a floor of zero lets the empty grid conform at the ceiling
    # this strategy draws, which would make every property in the search suite
    # hold vacuously. The mechanism is at the bound itself in
    # `property_strategies`; this is the assertion that pins it.
    case.assertLessEqual(1, config.min_themes)
    case.assertLessEqual(config.min_themes, len(bank.themes))
    case.assertEqual(config.min_entries_per_theme, 1)
    case.assertEqual(config.time_budget, ps.UNREACHABLE_TIME_BUDGET)
    case.assertIn(config.max_steps, ps.STEP_BUDGETS)
    case.assertLessEqual(len(config.features), 1)
    for feature in config.features:
        case.assertIn(feature.answer, answers)
        case.assertIn(feature.anchor, (None, ps.ORIGIN_ACROSS))
        # The invariant ORIGIN_ACROSS's comment rests on, checked rather than
        # trusted: a longer answer here would be refused by validation, and the
        # property suites would be asserting over requests that never search.
        case.assertLessEqual(len(feature.answer), config.cols)
    case.assertIn(config.look_ahead, ps.LOOK_AHEADS)


class TestRunScan(unittest.TestCase):
    """The independent rule reading, checked against hand-built grids."""

    def test_it_finds_across_runs_before_down_runs(self) -> None:
        # ACROSS row-major then DOWN column-major: the same documented order
        # cw_grid.runs_from_rows promises, arrived at independently.
        found = ps.scan_runs(("AB.", "C..", "..."))
        self.assertEqual(
            found,
            (
                ps.ScannedRun("AB", ((0, 0), (0, 1))),
                ps.ScannedRun("AC", ((0, 0), (1, 0))),
            ),
        )

    def test_it_maps_an_offset_run_back_to_its_own_cells(self) -> None:
        # The arithmetic worth testing: a match's offset within the scan line is
        # not its column once the line does not start at the grid's edge.
        self.assertEqual(
            ps.scan_runs((".ABC", "....")),
            (ps.ScannedRun("ABC", ((0, 1), (0, 2), (0, 3))),),
        )

    def test_it_maps_a_down_run_back_to_its_own_cells(self) -> None:
        self.assertEqual(
            ps.scan_runs(("..A", "..B", "..C")),
            (ps.ScannedRun("ABC", ((0, 2), (1, 2), (2, 2))),),
        )

    def test_a_lone_filled_cell_is_not_a_run(self) -> None:
        # The MIN_RUN boundary, and the exact case
        # cw_place.grid_violations is documented as being silent about: the
        # orphan property compares this empty result against filled_cells.
        rows = ("X..", "...", "...")
        self.assertEqual(ps.scan_runs(rows), ())
        self.assertEqual(ps.filled_cells(rows), {(0, 0)})

    def test_an_empty_grid_has_no_runs(self) -> None:
        # The zero-width branch. No search can produce this (--rows and --cols
        # are validated positive), so only a direct call reaches it.
        self.assertEqual(ps.scan_runs(()), ())
        self.assertEqual(ps.filled_cells(()), set())

    def test_filled_cells_excludes_blocks(self) -> None:
        self.assertEqual(ps.filled_cells((".A", "B.")), {(0, 1), (1, 0)})


class TestStrategyBounds(unittest.TestCase):
    """What `fill_requests` promises, and what every pinned seed promises with it."""

    def test_the_clock_never_advances(self) -> None:
        self.assertEqual(ps.frozen_clock(), 0.0)
        self.assertEqual(ps.frozen_clock(), ps.frozen_clock())

    def test_every_pinned_request_is_one_the_strategy_could_have_drawn(self) -> None:
        # Every pinned seed must be one the strategy could have drawn. The fields
        # derived from a named source cannot drift; this is what holds the rest, and
        # it walks `PINNED_REQUESTS` so a seed added later is covered by being
        # added there rather than by anyone remembering to extend this test.
        self.assertTrue(ps.PINNED_REQUESTS, "the pinned seeds must not be empty")
        for index, request in enumerate(ps.PINNED_REQUESTS):
            with self.subTest(seed=index):
                _assert_within_declared_bounds(self, request)

    @given(ps.fill_requests())
    def test_every_drawn_request_stays_inside_the_declared_bounds(
        self, request: ps.Request
    ) -> None:
        _assert_within_declared_bounds(self, request)


if __name__ == "__main__":
    unittest.main()
