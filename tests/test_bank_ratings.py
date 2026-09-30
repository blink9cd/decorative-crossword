"""Tests for cw_bank's optional answer rating: a whole number from 1 to 5, or none.

A rating is the operator's own judgment of how good an answer is, and it is the
only quality signal `fill` reads: a dictionary or a frequency floor is the filter
this project rejects, and commonness is not quality anyway. A rating ranks grids
and never removes an answer, so the parser's whole job is to refuse any value that
is not plainly a whole number on the scale.
"""

import unittest

import cw_bank


def _parse_rated(rating: object) -> cw_bank.Bank:
    """A one-answer bank whose answer carries `rating`, parsed."""
    return cw_bank.parse_bank(
        {"themes": {}, "entries": [{"answer": "TOLT", "rating": rating}]}
    )


class TestRatingAccepted(unittest.TestCase):
    """Absent, null, or a whole number on the scale."""

    def test_the_scale_runs_from_one_to_five_with_three_in_the_middle(self) -> None:
        # An unrated answer counts as the middle of the scale, which is why the
        # middle is a named value rather than a literal wherever it is used.
        self.assertEqual((cw_bank.MIN_RATING, cw_bank.MAX_RATING), (1, 5))
        self.assertEqual(cw_bank.NEUTRAL_RATING, 3)

    def test_every_rating_on_the_scale_is_kept_as_given(self) -> None:
        for rating in range(cw_bank.MIN_RATING, cw_bank.MAX_RATING + 1):
            with self.subTest(rating=rating):
                self.assertEqual(_parse_rated(rating).entries[0].rating, rating)

    def test_an_absent_rating_leaves_the_answer_unrated(self) -> None:
        bank = cw_bank.parse_bank({"themes": {}, "entries": [{"answer": "TOLT"}]})
        self.assertIsNone(bank.entries[0].rating)

    def test_a_null_rating_leaves_the_answer_unrated(self) -> None:
        # Null reads as absent, exactly as it does for a theme and a clue.
        self.assertIsNone(_parse_rated(None).entries[0].rating)

    def test_the_lowest_rating_keeps_the_answer_in_the_bank(self) -> None:
        # A rating ranks grids and is never a floor: a floor is a filter, and a
        # filter is what removed the winning words the one time one was tried.
        bank = cw_bank.parse_bank(
            {
                "themes": {},
                "entries": [
                    {"answer": "TOLT", "rating": cw_bank.MIN_RATING},
                    {"answer": "WILTS"},
                ],
            }
        )
        self.assertEqual([entry.answer for entry in bank.entries], ["TOLT", "WILTS"])


class TestRatingRefused(unittest.TestCase):
    """Anything but a whole number on the scale is refused, naming what was wrong."""

    def _assert_refused(self, rating: object) -> None:
        """`rating` is refused, and the message names the answer, value and scale."""
        with self.assertRaises(cw_bank.BankError) as caught:
            _parse_rated(rating)
        message = str(caught.exception)
        for fragment in ("'TOLT'", "rating", "1 to 5", repr(rating)):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, message)

    def test_a_rating_below_the_scale_is_refused(self) -> None:
        self._assert_refused(0)

    def test_a_rating_above_the_scale_is_refused(self) -> None:
        self._assert_refused(6)

    def test_a_negative_rating_is_refused(self) -> None:
        self._assert_refused(-3)

    def test_a_fractional_rating_is_refused(self) -> None:
        self._assert_refused(2.5)

    def test_a_whole_number_written_as_a_float_is_refused(self) -> None:
        # JSON keeps 3 and 3.0 apart, and a 3.0 suggests a finer scale than the
        # one this field has.
        self._assert_refused(3.0)

    def test_a_rating_written_as_a_string_is_refused(self) -> None:
        self._assert_refused("3")

    def test_a_boolean_rating_is_refused(self) -> None:
        # `bool` is a subclass of `int`, so `isinstance(True, int)` alone would
        # read a JSON `true` as a rating of 1.
        self._assert_refused(True)


if __name__ == "__main__":
    unittest.main()
