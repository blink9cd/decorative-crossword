"""Tests for cw_density: the blocked-cell window, judged exactly.

The verdict on a grid (`window_miss`) and the counts a ceiling or a floor allows
(`most_blocked`, `fewest_blocked`) are statements of one rule, and the report
and the island laying read the counts about grids acceptance judges -- so
`TestTheCountAgreesWithTheVerdict` holds them to one answer over every
one-decimal bound, on the grid sizes where binary floating point splits them.
The advice figures are rounded in the direction that clears a miss.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import dataclasses
import unittest
from fractions import Fraction

import cw_density

from tests.search_fixtures import config as _config

#: Grid sizes, in usable cells, where float arithmetic misjudges a one-decimal
#: bound: 11 of 20 at 55%, 7 of 25 at 28%, 23 of 80, 28 and 29 of 100, 37 of
#: 125, and 69 of 375 at 18.4% -- plus 625, a 25 x 25 grid's.
_TOTALS = (20, 25, 80, 100, 125, 375, 625)


def _line_of(total: int, blocked: int) -> tuple[str]:
    """A one-row grid of `total` cells, `blocked` of them blocked."""
    return ("." * blocked + "C" * (total - blocked),)


class TestPercent(unittest.TestCase):
    """A share of usable cells, exactly."""

    def test_is_exact(self) -> None:
        self.assertEqual(cw_density.percent(29, 100), 29)
        self.assertEqual(cw_density.percent(1, 3), Fraction(100, 3))

    def test_a_grid_with_no_usable_cells_is_zero_not_a_division_error(self) -> None:
        self.assertEqual(cw_density.percent(0, 0), 0)


class TestWindowMiss(unittest.TestCase):
    """Signed: below zero under the floor, above it over the ceiling, zero inside."""

    def test_under_the_floor_is_negative(self) -> None:
        config = _config(rows=1, cols=10, min_blocked=50.0, max_blocked=60.0)
        self.assertEqual(cw_density.window_miss(_line_of(10, 4), config), -10)

    def test_over_the_ceiling_is_positive(self) -> None:
        config = _config(rows=1, cols=10, min_blocked=50.0, max_blocked=60.0)
        self.assertEqual(cw_density.window_miss(_line_of(10, 7), config), 10)

    def test_both_bounds_are_inside(self) -> None:
        config = _config(rows=1, cols=10, min_blocked=50.0, max_blocked=60.0)
        for blocked in (5, 6):
            with self.subTest(blocked=blocked):
                self.assertEqual(
                    cw_density.window_miss(_line_of(10, blocked), config), 0
                )


class TestTheCountAgreesWithTheVerdict(unittest.TestCase):
    """The count forms are the last counts `window_miss` admits at the same bound."""

    def test_over_every_one_decimal_ceiling(self) -> None:
        for total in _TOTALS:
            base = _config(rows=1, cols=total, min_blocked=0.0)
            for tenths in range(1001):
                ceiling = tenths / 10
                config = dataclasses.replace(base, max_blocked=ceiling)
                most = cw_density.most_blocked(total, ceiling)
                self.assertEqual(
                    cw_density.window_miss(_line_of(total, most), config),
                    0,
                    f"{most} of {total} under {ceiling}",
                )
                if most < total:
                    self.assertGreater(
                        cw_density.window_miss(_line_of(total, most + 1), config),
                        0,
                        f"{most + 1} of {total} under {ceiling}",
                    )

    def test_over_every_one_decimal_floor(self) -> None:
        # `fewest_blocked` is what island laying reads, and it must stop exactly
        # where acceptance would start refusing.
        for total in _TOTALS:
            base = _config(rows=1, cols=total, max_blocked=100.0)
            for tenths in range(1001):
                floor = tenths / 10
                config = dataclasses.replace(base, min_blocked=floor)
                fewest = cw_density.fewest_blocked(total, floor)
                self.assertEqual(
                    cw_density.window_miss(_line_of(total, fewest), config),
                    0,
                    f"{fewest} of {total} over {floor}",
                )
                if fewest > 0:
                    self.assertLess(
                        cw_density.window_miss(_line_of(total, fewest - 1), config),
                        0,
                        f"{fewest - 1} of {total} over {floor}",
                    )


class TestWindowFigures(unittest.TestCase):
    """A grid's percentage and the window, printed so a miss reads as one."""

    def test_an_ordinary_miss_prints_to_one_decimal(self) -> None:
        config = _config(rows=1, cols=10, min_blocked=50.0, max_blocked=60.0)
        self.assertEqual(
            cw_density.window_figures(_line_of(10, 8), config),
            ("80.0", "50.0", "60.0"),
        )

    def test_a_grid_inside_the_window_prints_to_one_decimal(self) -> None:
        config = _config(rows=1, cols=10, min_blocked=50.0, max_blocked=60.0)
        self.assertEqual(
            cw_density.window_figures(_line_of(10, 5), config),
            ("50.0", "50.0", "60.0"),
        )

    def test_a_miss_one_decimal_hides_over_a_ceiling_prints_to_two(self) -> None:
        # 182 of 625 is exactly 29.12%: one decimal prints it as the 29.1
        # ceiling it is over.
        config = _config(rows=1, cols=625, max_blocked=29.1)
        self.assertEqual(
            cw_density.window_figures(_line_of(625, 182), config),
            ("29.12", "0.00", "29.10"),
        )

    def test_a_miss_one_decimal_hides_under_a_floor_prints_to_two(self) -> None:
        config = _config(rows=1, cols=625, min_blocked=29.13, max_blocked=100.0)
        self.assertEqual(
            cw_density.window_figures(_line_of(625, 182), config),
            ("29.12", "29.13", "100.00"),
        )

    def test_a_miss_can_need_more_than_one_more_decimal(self) -> None:
        # 3 of 9 is 33.333...%, over a 33.33 ceiling: both print as 33.3 at
        # one decimal and as 33.33 at two.
        config = _config(rows=1, cols=9, max_blocked=33.33)
        self.assertEqual(
            cw_density.window_figures(_line_of(9, 3), config),
            ("33.333", "0.000", "33.330"),
        )

    def test_a_bound_is_widened_with_the_share(self) -> None:
        # 7 of 24 is 29.1666...%, over a 29.16 ceiling, and at one decimal the
        # CEILING rounds up to 29.2 with it: widening the share alone would
        # print 29.17 against 29.2, which reads as inside.
        config = _config(rows=1, cols=24, max_blocked=29.16)
        self.assertEqual(
            cw_density.window_figures(_line_of(24, 7), config),
            ("29.17", "0.00", "29.16"),
        )

    def test_the_widened_figures_are_the_exact_values(self) -> None:
        # A ceiling typed to fifteen places, 3e-15 under 29.12%. The float
        # 182 / 625 * 100 prints as 29.120000000000001 at that many places.
        config = _config(rows=1, cols=625, max_blocked=29.119999999999997)
        self.assertEqual(
            cw_density.window_figures(_line_of(625, 182), config),
            ("29.120000000000000", "0.000000000000000", "29.119999999999997"),
        )


class TestTenths(unittest.TestCase):
    """The advice figures, rounded the way that clears the miss."""

    def test_a_ceiling_rounds_up(self) -> None:
        self.assertEqual(cw_density.ceil_tenth(Fraction(400, 9)), Fraction(445, 10))

    def test_a_floor_rounds_down(self) -> None:
        self.assertEqual(cw_density.floor_tenth(Fraction(75, 4)), Fraction(187, 10))

    def test_a_whole_tenth_is_kept_either_way(self) -> None:
        self.assertEqual(cw_density.ceil_tenth(Fraction(28)), 28)
        self.assertEqual(cw_density.floor_tenth(Fraction(29)), 29)


if __name__ == "__main__":
    unittest.main()
