"""Tests for the report's rating lines, which a bank with no ratings never sees.

An operator who has rated nothing must get a report with no rating in it, so
both lines here depend on at least one rated answer in the bank -- and each
absence is pinned beside its presence. The worst-rating line names the chosen
grid's WORST entries because that is the entry a reader notices: nobody
averages a crossword.

Every case but the empty-grid one reports on `report_fixtures.DEFAULT_ROWS`,
whose entries are CAT and WET across and COW down. The bank lists them CAT,
COW, WET, which is not the grid's across-then-down order, so a line naming them
in bank order can be told apart from one naming them in grid order.
"""

import dataclasses
import unittest

import cw_bank
import cw_report

from tests import report_fixtures as fx

#: How the chosen sentence ends when the bank rates at least one answer.
_RATED_ORDER = (
    "most letters, then --prefer answers, then worst rating, then themed entries."
)

#: How it ends for an unrated bank.
_UNRATED_ORDER = "most letters, then --prefer answers, then themed entries."

_WORST = "Worst rating in the grid:"


def _rated(**ratings: int) -> cw_bank.Bank:
    """The report fixtures' bank with the named answers rated."""
    bank = fx.make_bank()
    return dataclasses.replace(
        bank,
        entries=tuple(
            dataclasses.replace(entry, rating=ratings.get(entry.answer))
            for entry in bank.entries
        ),
    )


def _report(
    bank: cw_bank.Bank, *, look_ahead: int = 10, max_blocked: float = 45.0
) -> str:
    """The report on the default grid, chosen within `look_ahead` nodes."""
    config = dataclasses.replace(
        fx.make_config(min_blocked=0.0, max_blocked=max_blocked),
        look_ahead=look_ahead,
    )
    outcome = fx.make_outcome(bank=bank, config=config)
    return cw_report.render_report(outcome, bank, config, ())


class TestChosenSentence(unittest.TestCase):
    """The sentence names the rating level only when the bank rates something."""

    def test_a_rated_bank_names_the_worst_rating_in_the_order(self) -> None:
        self.assertIn(_RATED_ORDER, _report(_rated(PIE=4)))

    def test_an_unrated_bank_keeps_the_sentence_it_always_had(self) -> None:
        report = _report(fx.make_bank())
        self.assertIn(_UNRATED_ORDER, report)
        self.assertNotIn(_WORST, report)


class TestWorstRatingLine(unittest.TestCase):
    """The chosen grid's worst rating, and the entries holding it."""

    def test_the_worst_rated_entries_are_named_in_bank_order(self) -> None:
        self.assertEqual(
            fx.line(_report(_rated(COW=1, WET=1)), _WORST),
            f"{_WORST} 1 -- COW, WET.",
        )

    def test_a_rated_answer_the_grid_does_not_hold_is_not_counted(self) -> None:
        self.assertEqual(
            fx.line(_report(_rated(PIE=1, CAT=2)), _WORST), f"{_WORST} 2 -- CAT."
        )

    def test_unrated_entries_at_the_worst_are_counted_rather_than_named(self) -> None:
        # CAT is rated above the middle, so the worst belongs to COW and WET.
        self.assertEqual(
            fx.line(_report(_rated(CAT=4)), _WORST),
            f"{_WORST} 3 -- 2 unrated answer(s), which count as 3.",
        )

    def test_a_rated_entry_at_the_middle_is_named_beside_the_unrated(self) -> None:
        self.assertEqual(
            fx.line(_report(_rated(CAT=3)), _WORST),
            f"{_WORST} 3 -- CAT, and 2 unrated answer(s), which count as 3.",
        )

    def test_a_grid_holding_no_rated_answer_counts_every_entry(self) -> None:
        self.assertEqual(
            fx.line(_report(_rated(PIE=4)), _WORST),
            f"{_WORST} 3 -- 3 unrated answer(s), which count as 3.",
        )

    def test_a_grid_rated_above_the_middle_names_its_lowest(self) -> None:
        self.assertEqual(
            fx.line(_report(_rated(CAT=5, COW=4, WET=5)), _WORST),
            f"{_WORST} 4 -- COW.",
        )

    def test_the_line_is_printed_without_a_look_ahead(self) -> None:
        # Like the preferred-answers line, it describes the grid rather than a
        # comparison, so it does not wait for a window to have been searched.
        report = _report(_rated(CAT=2), look_ahead=0)
        self.assertEqual(fx.line(report, _WORST), f"{_WORST} 2 -- CAT.")
        self.assertNotIn("Chosen as", report)

    def test_a_middle_worst_with_every_entry_rated_names_only_the_rated(
        self,
    ) -> None:
        # The worst is the neutral rating, but nothing is unrated to be counted.
        self.assertEqual(
            fx.line(_report(_rated(CAT=3, COW=4, WET=5)), _WORST),
            f"{_WORST} 3 -- CAT.",
        )

    def test_a_grid_holding_no_entries_gets_no_rating_line(self) -> None:
        # A worst rating of a grid with nothing in it would be a sentence about
        # entries that are not there -- the vacuous line the answer-pairs block
        # also declines to print for an empty grid.
        bank = _rated(CAT=2)
        config = fx.make_config(min_blocked=0.0, max_blocked=100.0, min_themes=0)
        outcome = fx.make_outcome(("...", "...", "..."), bank=bank, config=config)
        self.assertTrue(outcome.conforming)
        self.assertNotIn(_WORST, cw_report.render_report(outcome, bank, config, ()))

    def test_a_missed_grid_carries_no_rating_line(self) -> None:
        # A best-effort miss was not chosen among anything.
        self.assertNotIn(_WORST, _report(_rated(CAT=2), max_blocked=5.0))


if __name__ == "__main__":
    unittest.main()
