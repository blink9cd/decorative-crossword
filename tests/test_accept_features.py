"""Tests for cw_accept's feature checks: pre-flight on pins, and acceptance per feature.

Pins add two questions `cw_accept` answers: whether the board they form
already breaks the one rule for this bank, before a search, and whether each
featured answer is in a grid, at every node of one. The acceptance rules'
other cases are in `test_search_parts.py`.
"""

import unittest

import cw_accept
import cw_feature
import cw_grid
import cw_search

from tests.search_fixtures import config as _config
from tests.search_fixtures import one_theme_bank as _one_theme_bank
from tests.search_fixtures import pin as _pin
from tests.search_fixtures import themed_bank as _themed_bank

#: A 3x3 board holding CAT alone, across the top.
_CAT_ONLY = ("CAT", "...", "...")


class TestPinnedPreflight(unittest.TestCase):
    """Pins this bank cannot hold together are refused before the search."""

    def test_refuses_pins_that_form_a_run_the_bank_does_not_hold(self) -> None:
        # ALPHA directly over BRAVO: every column between them reads as a
        # two-letter run, and none of AB, LR, PA, HV or AO is an answer. The
        # board the search would start from already breaks the one rule, so no
        # amount of searching could repair it: refused here, naming the run,
        # rather than returned as a search that silently found nothing.
        reasons = cw_search.preflight(
            _one_theme_bank(["ALPHA", "BRAVO"]),
            _config(
                features=(
                    _pin("ALPHA", 0, 0, cw_grid.ACROSS),
                    _pin("BRAVO", 1, 0, cw_grid.ACROSS),
                )
            ),
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("pinned", reasons[0])
        self.assertIn("'AB'", reasons[0])
        self.assertIn("is not a bank answer", reasons[0])

    def test_passes_pins_whose_every_run_is_an_answer(self) -> None:
        # The accepting half of the refusal above: two pins crossing at a shared
        # letter form exactly two runs, both of them answers.
        self.assertEqual(
            cw_search.preflight(
                _themed_bank(),
                _config(
                    features=(
                        _pin("ALPHA", 0, 0, cw_grid.ACROSS),
                        _pin("AMBER", 0, 0, cw_grid.DOWN),
                    )
                ),
            ),
            (),
        )

    def test_names_every_featured_answer_missing_from_the_bank(self) -> None:
        # Every one, in the order given, and never the one the bank does hold:
        # told only OMEGA, an operator fixes it and is refused again for ZULU.
        bank = _one_theme_bank(["ALPHA"])
        config = _config(
            features=(
                cw_feature.Feature("OMEGA", None),
                cw_feature.Feature("ALPHA", None),
                cw_feature.Feature("ZULU", None),
            )
        )
        reason = str(cw_accept.feature_missing_from_bank(bank, config))
        self.assertIn("'OMEGA'", reason)
        self.assertIn("'ZULU'", reason)
        self.assertNotIn("'ALPHA'", reason)
        self.assertLess(reason.index("'OMEGA'"), reason.index("'ZULU'"))

    def test_measures_only_the_feature_that_is_too_long(self) -> None:
        reasons = cw_search.preflight(
            _one_theme_bank(["EXTRAORDINARY", "ALPHA"]),
            _config(
                rows=5,
                cols=5,
                features=(
                    cw_feature.Feature("EXTRAORDINARY", None),
                    cw_feature.Feature("ALPHA", None),
                ),
            ),
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("'EXTRAORDINARY'", reasons[0])
        self.assertNotIn("'ALPHA'", reasons[0])

    def test_names_a_pinned_answer_the_bank_lacks_instead_of_raising(self) -> None:
        # A caller reaching pre-flight without the CLI (which would refuse
        # this at exit 2 first) must still get a reason, not a traceback from
        # building a board out of an answer no bank could hold.
        reasons = cw_search.preflight(
            _one_theme_bank(["ALPHA"]),
            _config(features=(_pin("cat", 0, 0, cw_grid.ACROSS),)),
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("'cat'", reasons[0])


class TestFeatureAcceptance(unittest.TestCase):
    """Every featured answer is an acceptance constraint of its own."""

    def test_names_each_absent_feature_in_the_order_given(self) -> None:
        # CAT is on the board and must not be named; the two that are not are
        # each a missed constraint of their own, so the report's remedy block
        # can offer a knob for each.
        missed = cw_accept.missed_constraints(
            _CAT_ONLY,
            _one_theme_bank(["CAT", "COW", "PIG"]),
            _config(
                features=(
                    cw_feature.Feature("CAT", None),
                    cw_feature.Feature("COW", None),
                    cw_feature.Feature("PIG", None),
                )
            ),
        )
        self.assertEqual(len(missed), 2)
        self.assertIn("'COW'", missed[0])
        self.assertIn("'PIG'", missed[1])

    def test_a_pinned_answer_counts_only_at_its_own_cell(self) -> None:
        # JANE is an entry in this grid, on row 0, and pinned to row 1. A pin
        # is a position, so JANE elsewhere does not satisfy it: reading only
        # "is JANE a run anywhere" would accept a grid that dropped the pin.
        missed = cw_accept.missed_constraints(
            ("JANE.", "....."),
            _one_theme_bank(["JANE"]),
            _config(rows=2, cols=5, features=(_pin("JANE", 1, 0, cw_grid.ACROSS),)),
        )
        self.assertEqual(len(missed), 1)
        self.assertIn("'JANE'", missed[0])
        self.assertIn("(1, 0)", missed[0])
