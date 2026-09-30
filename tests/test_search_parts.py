"""Tests for cw_search's pure parts: pre-flight, scoring, acceptance.

The search itself lives in test_search.py, and the candidate order it walks in
test_order.py. These are the other functions it is assembled from, tested where
each rule can be inverted on its own.
"""

import unittest

import cw_accept
import cw_bank
import cw_search
import cw_select

# Aliased to the private spellings the test bodies use, so a fixture shared
# across the cw_search suites is still defined exactly once (see search_fixtures).
from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import entries_bank as _entries_bank
from tests.search_fixtures import one_theme_bank as _one_theme_bank
from tests.search_fixtures import themed_bank as _themed_bank
from tests.search_fixtures import (
    ONE_HUNDRED_EIGHTY_TWO_OF_625 as _ONE_HUNDRED_EIGHTY_TWO_OF_625,
)
from tests.search_fixtures import TWENTY_EIGHT_OF_100 as _TWENTY_EIGHT_OF_100
from tests.search_fixtures import TWENTY_NINE_OF_100 as _TWENTY_NINE_OF_100

#: Six of nine cells blocked. Written as the division rather than 66.7 so the
#: assertions below compare against the definition, not a rounded copy of it.
_SIX_OF_NINE = 600 / 9

#: A 3x3 board carrying one answer, for the acceptance and density tests.
_ONE_ANSWER_ROWS = ("CAT", "...", "...")

#: A 3x3 board carrying exactly two two-letter entries, AT and TO, and no other run.
_TWO_TWOS_ROWS = ("AT.", "...", "TO.")

#: A board standing exactly on a one-decimal bound that binary floating point
#: misses: 37 blocked cells of 125, exactly 29.6%.
_THIRTY_SEVEN_OF_125 = ("C" * 25,) * 3 + ("C" * 13 + "." * 12,) + ("." * 25,)


class TestPreflight(unittest.TestCase):
    """Unsatisfiable requests are refused before the search, not after the budget."""

    def test_passes_a_satisfiable_request(self) -> None:
        self.assertEqual(cw_search.preflight(_themed_bank(), _config()), ())

    def test_refuses_an_unreachable_theme_floor(self) -> None:
        reasons = cw_search.preflight(_bank(["ALPHA", "BRAVO"]), _config(min_themes=3))
        self.assertTrue(reasons)
        self.assertIn("theme", " ".join(reasons).lower())

    def test_refuses_a_feature_longer_than_the_grid(self) -> None:
        reasons = cw_search.preflight(
            _bank(["EXTRAORDINARY"]), _config(rows=5, cols=5, feature="EXTRAORDINARY")
        )
        self.assertTrue(reasons)

    def test_refuses_a_floor_no_single_theme_is_deep_enough_for(self) -> None:
        # Three themes exist and the theme COUNT is met; the per-theme depth is
        # not. A pre-flight counting only declared themes waves this through.
        reasons = cw_search.preflight(
            _themed_bank(), _config(min_themes=3, min_entries_per_theme=4)
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("theme", reasons[0].lower())

    def test_refuses_a_feature_missing_from_the_bank(self) -> None:
        reasons = cw_search.preflight(
            _one_theme_bank(["ALPHA", "BRAVO"]), _config(feature="OMEGA")
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("OMEGA", reasons[0])

    def test_refuses_a_bank_whose_answers_all_exceed_the_grid(self) -> None:
        reasons = cw_search.preflight(
            _one_theme_bank(["ALPHA", "BRAVO"]), _config(rows=4, cols=3)
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("4x3", reasons[0])

    def test_reports_every_reason_a_request_fails(self) -> None:
        # An unthemed bank whose one answer is also too long trips two checks.
        # `preflight` promises every reason: told only the first, an operator
        # fixes it, re-runs, and is told the second -- discoverability one
        # round-trip at a time.
        reasons = cw_search.preflight(_bank(["EXTRAORDINARY"]), _config(rows=5, cols=5))
        self.assertEqual(len(reasons), 2)
        self.assertIn("theme", reasons[0].lower())
        self.assertIn("5x5", reasons[1])

    def test_names_the_absent_feature_through_its_own_callable(self) -> None:
        # This one reason belongs on the exit-2 line while the rest are exit 1,
        # so the CLI needs it as a callable rather than as a string to match
        # against. One implementation, reached two ways.
        bank = _one_theme_bank(["ALPHA"])
        config = _config(feature="OMEGA")
        reason = cw_accept.feature_missing_from_bank(bank, config)
        self.assertIsNotNone(reason)
        self.assertEqual(cw_search.preflight(bank, config), (reason,))
        self.assertIsNone(
            cw_accept.feature_missing_from_bank(bank, _config(feature="ALPHA"))
        )

    def test_accepts_a_feature_exactly_as_long_as_the_longer_side(self) -> None:
        # The bound is inclusive: a 5-letter feature fits a grid with a 5-long
        # side. A strict ">" here refuses a plainly satisfiable request.
        self.assertEqual(
            cw_search.preflight(
                _one_theme_bank(["ALPHA"]), _config(rows=5, cols=3, feature="ALPHA")
            ),
            (),
        )


class TestDensityDistance(unittest.TestCase):
    """How far outside the window a grid sits -- the best-effort ranking's axis."""

    def test_is_zero_inside_the_window(self) -> None:
        self.assertEqual(
            cw_accept.density_distance(
                _ONE_ANSWER_ROWS, _config(min_blocked=0.0, max_blocked=95.0)
            ),
            0.0,
        )

    def test_measures_the_gap_below_the_window(self) -> None:
        self.assertAlmostEqual(
            cw_accept.density_distance(
                _ONE_ANSWER_ROWS, _config(min_blocked=90.0, max_blocked=95.0)
            ),
            90.0 - _SIX_OF_NINE,
        )

    def test_measures_the_gap_above_the_window(self) -> None:
        self.assertAlmostEqual(
            cw_accept.density_distance(
                _ONE_ANSWER_ROWS, _config(min_blocked=0.0, max_blocked=50.0)
            ),
            _SIX_OF_NINE - 50.0,
        )

    def test_a_grid_exactly_on_the_ceiling_is_inside(self) -> None:
        # 28 of 100 is exactly 28%, but 28 / 100 * 100 is 28.000000000000004 in
        # binary floating point: over a 28.0 ceiling by a float comparison.
        config = _config(rows=10, cols=10, max_blocked=28.0)
        self.assertEqual(cw_accept.density_distance(_TWENTY_EIGHT_OF_100, config), 0.0)

    def test_a_grid_exactly_on_the_floor_is_inside(self) -> None:
        # 29 / 100 * 100 is 28.999999999999996: under a 29.0 floor by float.
        config = _config(rows=10, cols=10, min_blocked=29.0)
        self.assertEqual(cw_accept.density_distance(_TWENTY_NINE_OF_100, config), 0.0)

    def test_a_floor_is_the_decimal_the_operator_typed(self) -> None:
        # 37 of 125 is exactly 29.6%. The float 29.6 is 29.60000000000000142...,
        # so a floor taken from the float's binary value refuses this grid as
        # surely as the float quotient 29.599999999999998 does.
        config = _config(rows=5, cols=25, min_blocked=29.6)
        self.assertEqual(cw_accept.density_distance(_THIRTY_SEVEN_OF_125, config), 0.0)


class TestThemeFloorStatus(unittest.TestCase):
    """The count and the verdict, from one walk and one comparison.

    Every caller but the verdict-only `theme_floor_met` needs BOTH halves --
    the verdict to decide whether to speak, the count to say "lower
    --min-themes to N". Pinned as a whole tuple so a transposed return, which
    would still type-check, fails here.
    """

    def test_reports_the_count_beside_a_met_verdict(self) -> None:
        self.assertEqual(
            cw_accept.theme_floor_status(
                _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config()
            ),
            (1, True),
        )

    def test_reports_the_count_beside_an_unmet_verdict(self) -> None:
        # The count is what the report turns into a remedy, so it has to be
        # right on the branch that MISSES -- a status computing it only when
        # the floor is met would leave that line quoting nothing.
        self.assertEqual(
            cw_accept.theme_floor_status(
                _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config(min_themes=2)
            ),
            (1, False),
        )

    def test_its_two_halves_agree_with_the_functions_they_serve(self) -> None:
        # One walk answers both questions. If the halves could disagree with
        # their single-purpose siblings, the report's verdict line and its
        # remedy line could contradict each other in one report. Three floors,
        # straddling the boundary on both sides.
        for min_themes in (0, 1, 2):
            with self.subTest(min_themes=min_themes):
                bank = _one_theme_bank(["CAT"])
                config = _config(min_themes=min_themes)
                met, floor_met = cw_accept.theme_floor_status(
                    _ONE_ANSWER_ROWS, bank, config
                )
                self.assertEqual(
                    met,
                    cw_accept.themes_meeting_floor(_ONE_ANSWER_ROWS, bank, config),
                )
                self.assertEqual(
                    floor_met,
                    cw_accept.theme_floor_met(_ONE_ANSWER_ROWS, bank, config),
                )


class TestThemeFloorMet(unittest.TestCase):
    """The verdict-only spelling of `theme_floor_status`.

    `cw_report` prints a "floor met" / "floor NOT met" verdict directly above
    the missed-constraint list `missed_constraints` produces, and both read
    `theme_floor_status`. This predicate is kept so a caller wanting the boolean
    alone does not restate the comparison, and pinned here on its own so that
    caller gets the same verdict.
    """

    def test_is_true_when_enough_themes_reach_the_floor(self) -> None:
        self.assertTrue(
            cw_accept.theme_floor_met(
                _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config()
            )
        )

    def test_is_false_when_too_few_themes_reach_it(self) -> None:
        self.assertFalse(
            cw_accept.theme_floor_met(
                _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config(min_themes=2)
            )
        )

    def test_agrees_with_the_missed_constraint_it_gates(self) -> None:
        # The verdict and the sentence must never disagree. A boundary case on
        # each side of the floor, checked against the SAME inputs
        # missed_constraints sees.
        for min_themes, expected in ((1, True), (2, False)):
            with self.subTest(min_themes=min_themes):
                bank = _one_theme_bank(["CAT"])
                config = _config(min_themes=min_themes)
                met = cw_accept.theme_floor_met(_ONE_ANSWER_ROWS, bank, config)
                sentences = cw_accept.missed_constraints(_ONE_ANSWER_ROWS, bank, config)
                self.assertEqual(met, expected)
                self.assertEqual(met, not any("themes reach" in s for s in sentences))


class TestMissedConstraints(unittest.TestCase):
    """Acceptance, stated as the list of rules a grid currently fails."""

    def test_is_empty_for_a_conforming_grid(self) -> None:
        self.assertEqual(
            cw_accept.missed_constraints(
                _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config()
            ),
            (),
        )

    def test_names_a_grid_that_is_too_blocked(self) -> None:
        missed = cw_accept.missed_constraints(
            _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config(max_blocked=50.0)
        )
        self.assertEqual(len(missed), 1)
        self.assertIn("0.0-50.0", missed[0])

    def test_names_a_grid_that_is_not_blocked_enough(self) -> None:
        missed = cw_accept.missed_constraints(
            _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config(min_blocked=90.0)
        )
        self.assertEqual(len(missed), 1)
        self.assertIn("90.0-95.0", missed[0])

    def test_a_miss_one_decimal_would_hide_is_printed_to_show_it(self) -> None:
        # 29.12% over a 29.1 ceiling: at one decimal the sentence read
        # "blocked 29.1% is outside the requested 0.0-29.1% window".
        missed = cw_accept.missed_constraints(
            _ONE_HUNDRED_EIGHTY_TWO_OF_625,
            _one_theme_bank(["CAT"]),
            _config(rows=25, cols=25, max_blocked=29.1, min_themes=0),
        )
        self.assertEqual(
            missed, ("blocked 29.12% is outside the requested 0.00-29.10% window",)
        )

    def test_an_ordinary_miss_is_printed_to_one_decimal(self) -> None:
        missed = cw_accept.missed_constraints(
            _ONE_HUNDRED_EIGHTY_TWO_OF_625,
            _one_theme_bank(["CAT"]),
            _config(rows=25, cols=25, max_blocked=25.0, min_themes=0),
        )
        self.assertEqual(
            missed, ("blocked 29.1% is outside the requested 0.0-25.0% window",)
        )

    def test_names_an_unmet_theme_floor(self) -> None:
        missed = cw_accept.missed_constraints(
            _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config(min_themes=2)
        )
        self.assertEqual(len(missed), 1)
        self.assertIn("1 of 2", missed[0])

    def test_names_an_absent_feature(self) -> None:
        missed = cw_accept.missed_constraints(
            _ONE_ANSWER_ROWS, _one_theme_bank(["CAT", "COW"]), _config(feature="COW")
        )
        self.assertEqual(len(missed), 1)
        self.assertIn("COW", missed[0])

    def test_rejects_a_feature_that_is_only_a_substring(self) -> None:
        # CATS is on the board; CAT is not an entry. The feature is a hard
        # constraint on the grid's ENTRIES, so scanning the row
        # strings for its letters would report it present, mark the grid
        # conforming, and have the render shade cells for an entry that is not
        # there -- the worst available outcome, because it looks finished.
        missed = cw_accept.missed_constraints(
            ("CATS.", ".....", ".....", ".....", "....."),
            _one_theme_bank(["CATS", "CAT"]),
            _config(rows=5, cols=5, feature="CAT"),
        )
        self.assertEqual(len(missed), 1)
        self.assertIn("CAT", missed[0])

    def test_counts_only_themed_entries_towards_the_floor(self) -> None:
        # The unthemed answer on the board is a perfectly legal entry; it just
        # cannot carry a theme floor. A count taken over runs rather than over
        # THEMED runs reports the floor met.
        mixed = _entries_bank((("CAT", None), ("COW", "a")), {"a": "A"})
        missed = cw_accept.missed_constraints(_ONE_ANSWER_ROWS, mixed, _config())
        self.assertEqual(len(missed), 1)
        self.assertIn("0 of 1", missed[0])


class TestTwoLetterCap(unittest.TestCase):
    """`--max-two-letter`: at most that many two-letter entries, or no cap when unset."""

    def test_names_a_grid_over_the_cap(self) -> None:
        missed = cw_accept.missed_constraints(
            _TWO_TWOS_ROWS, _one_theme_bank(["AT", "TO"]), _config(max_two_letter=1)
        )
        self.assertEqual(missed, ("2 two-letter entries, over the requested cap of 1",))

    def test_accepts_a_grid_exactly_at_the_cap(self) -> None:
        # The cap is a ceiling the grid may REACH: `<` in place of `<=` would
        # refuse a grid carrying exactly the capped count.
        self.assertEqual(
            cw_accept.missed_constraints(
                _TWO_TWOS_ROWS, _one_theme_bank(["AT", "TO"]), _config(max_two_letter=2)
            ),
            (),
        )

    def test_a_cap_of_zero_is_a_cap_not_the_absence_of_one(self) -> None:
        # Zero is a real value: it forbids two-letter entries outright. A
        # truthiness test would read it as "no cap" and accept this grid.
        missed = cw_accept.missed_constraints(
            _TWO_TWOS_ROWS, _one_theme_bank(["AT", "TO"]), _config(max_two_letter=0)
        )
        self.assertEqual(missed, ("2 two-letter entries, over the requested cap of 0",))

    def test_counts_only_two_letter_entries(self) -> None:
        # CAT is an entry of three: a count over every run would refuse it at zero.
        self.assertEqual(
            cw_accept.missed_constraints(
                _ONE_ANSWER_ROWS, _one_theme_bank(["CAT"]), _config(max_two_letter=0)
            ),
            (),
        )

    def test_no_cap_when_unset(self) -> None:
        self.assertEqual(
            cw_accept.missed_constraints(
                _TWO_TWOS_ROWS, _one_theme_bank(["AT", "TO"]), _config()
            ),
            (),
        )


class TestSnapshotRank(unittest.TestCase):
    """The best-effort ranking: theme floor, then density, then entries placed.

    That ORDER is fixed, and it is the whole content of the
    rule -- each case below gives the state that should win the worse figure on
    every later level, so a rank that dropped or reordered a term picks the
    other one.
    """

    #: 7x5 with answers on alternate rows, so no accidental DOWN run forms.
    _TWO_THEMED = ("CAT..", ".....", "COW..", ".....", ".....", ".....", ".....")
    _THREE_MIXED = ("CAT..", ".....", "DOG..", ".....", "EEL..", ".....", ".....")
    _FOUR_MIXED = ("CAT..", ".....", "DOG..", ".....", "EEL..", ".....", "FIG..")

    def _bank(self) -> cw_bank.Bank:
        """Two themes of two, plus two unthemed answers to pad a grid with."""
        return _entries_bank(
            (("CAT", "a"), ("COW", "a"), ("DOG", "b"), ("EEL", None), ("FIG", None)),
            {"a": "A", "b": "B"},
        )

    def _rank(
        self, rows: tuple[str, ...], *, min_blocked: float = 70.0
    ) -> tuple[int, float, int]:
        """This state's rank. The floor moves so a case can put both inside."""
        config = _config(
            rows=7,
            cols=5,
            min_blocked=min_blocked,
            max_blocked=80.0,
            min_entries_per_theme=2,
        )
        return cw_select.snapshot(rows, (), self._bank(), config).rank

    def test_ranks_a_met_theme_floor_above_everything_else(self) -> None:
        # Two entries in one theme reach the floor at 82.9% blocked -- outside
        # the window -- against three entries in no theme sitting inside it.
        # The theme term is the only one that favors the winner.
        self.assertGreater(self._rank(self._TWO_THEMED), self._rank(self._THREE_MIXED))

    def test_ranks_the_density_window_above_the_entry_count(self) -> None:
        # Neither reaches a theme floor, so the tie falls to density: three
        # entries inside the window beat four that undershoot it.
        self.assertGreater(self._rank(self._THREE_MIXED), self._rank(self._FOUR_MIXED))

    def test_ranks_the_entry_count_last(self) -> None:
        # A window wide enough to hold both, and a theme floor neither reaches,
        # so the entry count is the only term left with anything to say.
        self.assertGreater(
            self._rank(self._FOUR_MIXED, min_blocked=60.0),
            self._rank(self._THREE_MIXED, min_blocked=60.0),
        )
