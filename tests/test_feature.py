"""Tests for cw_feature: the `--feature` grammar, and the pin checks the flags alone decide.

Every refusal here is a `cw_config.ConfigError` -- the exit-2 line -- and names
`--feature`. Whether pins that pass these checks also suit a BANK is
`cw_accept`'s question, and its tests are in `test_accept_features.py`.
"""

import unittest

import cw_config
import cw_feature
import cw_grid

from tests.search_fixtures import config as _config
from tests.search_fixtures import pin as _pin


class TestParseFeature(unittest.TestCase):
    """`--feature` is ANSWER, or ANSWER@ROW,COL,DIR pinning it to one cell."""

    def test_a_bare_answer_has_no_anchor(self) -> None:
        self.assertEqual(
            cw_feature.parse_feature("CHALK"), cw_feature.Feature("CHALK", None)
        )

    def test_a_bare_answer_is_taken_verbatim(self) -> None:
        # Not uppercased: whether it names a bank answer is the bank check's
        # question, which already answers it at exit 2. (Spaces, hyphens and
        # apostrophes do close up, through `cw_answer.grid_form`.) A parser
        # that folded case here would make `--feature chalk` succeed where the
        # bank check refuses it, which is a behavior change hiding inside a
        # grammar.
        self.assertEqual(cw_feature.parse_feature("chalk").answer, "chalk")

    def test_an_anchor_carries_its_cell_and_direction(self) -> None:
        self.assertEqual(
            cw_feature.parse_feature("CHALK@2,3,down"),
            _pin("CHALK", 2, 3, cw_grid.DOWN),
        )

    def test_an_anchor_may_run_across(self) -> None:
        # The DOWN case alone would pass a parser that ignored the token and
        # always answered DOWN.
        self.assertEqual(
            cw_feature.parse_feature("CHALK@0,11,across"),
            _pin("CHALK", 0, 11, cw_grid.ACROSS),
        )

    def test_rejects_an_empty_answer(self) -> None:
        for text in ("", "@0,0,across"):
            with self.subTest(text=text):
                with self.assertRaises(cw_config.ConfigError) as caught:
                    cw_feature.parse_feature(text)
                self.assertIn("--feature", str(caught.exception))

    def test_rejects_more_than_one_anchor(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.parse_feature("CHALK@1,1,down@2,2,down")
        self.assertIn("--feature", str(caught.exception))

    def test_rejects_an_anchor_without_exactly_three_parts(self) -> None:
        for text in ("CHALK@", "CHALK@0,0", "CHALK@0,0,across,1"):
            with self.subTest(text=text):
                with self.assertRaises(cw_config.ConfigError) as caught:
                    cw_feature.parse_feature(text)
                self.assertIn("ROW,COL,DIR", str(caught.exception))

    def test_rejects_a_coordinate_that_is_not_a_plain_integer(self) -> None:
        # `int()` would accept every one of the last four: a sign, padding, and
        # a non-ASCII digit. A pin is a cell index typed by hand, so the grammar
        # is the digits 0-9 and nothing else -- a negative row is refused here
        # rather than reaching the bounds check as a cell before the grid.
        for text in (
            "CHALK@a,0,down",
            "CHALK@0,,down",
            "CHALK@-1,0,down",
            "CHALK@0,+1,down",
            "CHALK@0, 1,down",
            "CHALK@\u0663,0,down",
        ):
            with self.subTest(text=text):
                with self.assertRaises(cw_config.ConfigError) as caught:
                    cw_feature.parse_feature(text)
                self.assertIn("non-negative integer", str(caught.exception))

    def test_rejects_a_direction_that_is_not_across_or_down(self) -> None:
        # Case-sensitive on purpose: the report prints `across` and `down`, so
        # the spelling a pin is written in is the one the tool writes back.
        for text in ("CHALK@0,0,diagonal", "CHALK@0,0,ACROSS", "CHALK@0,0,"):
            with self.subTest(text=text):
                with self.assertRaises(cw_config.ConfigError) as caught:
                    cw_feature.parse_feature(text)
                message = str(caught.exception)
                self.assertIn(cw_grid.ACROSS, message)
                self.assertIn(cw_grid.DOWN, message)

    def test_rejects_a_coordinate_past_the_integer_string_limit(self) -> None:
        # Five thousand digits pass the ASCII-digit screen and then make `int()`
        # raise a plain ValueError past the interpreter's integer-string limit.
        # That is not a ConfigError: unwrapped, it escapes the exit-2 line as a
        # traceback. The refusal must also not echo the whole value back.
        text = "CHALK@" + "1" * 5000 + ",0,down"
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.parse_feature(text)
        message = str(caught.exception)
        self.assertIn("--feature", message)
        self.assertLess(len(message), 200)


class TestValidateFeatures(unittest.TestCase):
    """Pins that contradict the grid or each other are refused before any search."""

    def test_accepts_anchors_that_agree_where_they_cross(self) -> None:
        cw_feature.validate_features(
            _config(
                features=(
                    _pin("ALPHA", 0, 0, cw_grid.ACROSS),
                    _pin("AMBER", 0, 0, cw_grid.DOWN),
                )
            )
        )

    def test_accepts_an_anchor_that_exactly_fills_to_the_edge(self) -> None:
        # Columns 4-8 of a 9-wide grid. Paired with the off-edge refusals below
        # so the bound is pinned from both sides: an off-by-one `>=` refuses
        # this plainly satisfiable pin.
        cw_feature.validate_features(
            _config(features=(_pin("ALPHA", 0, 4, cw_grid.ACROSS),))
        )

    def test_rejects_an_answer_featured_twice(self) -> None:
        # Once bare and once pinned is still twice: the distinct-run rule allows
        # one entry per answer, so no grid could honor both.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    features=(
                        cw_feature.Feature("ALPHA", None),
                        _pin("ALPHA", 0, 0, cw_grid.ACROSS),
                    )
                )
            )
        message = str(caught.exception)
        self.assertIn("--feature", message)
        self.assertIn("'ALPHA'", message)
        self.assertIn("twice", message)

    def test_rejects_an_anchor_running_off_the_right_edge(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(features=(_pin("ALPHA", 0, 5, cw_grid.ACROSS),))
            )
        message = str(caught.exception)
        self.assertIn("--feature", message)
        self.assertIn("ALPHA@0,5,across", message)
        self.assertIn("9x9", message)

    def test_rejects_an_anchor_running_off_the_bottom_edge(self) -> None:
        # Its own case: a bounds check that tested only columns would pass the
        # across refusal above and let this one through.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(rows=4, features=(_pin("ALPHA", 0, 0, cw_grid.DOWN),))
            )
        self.assertIn("4x9", str(caught.exception))

    def test_rejects_an_anchor_starting_past_the_last_row(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(features=(_pin("AB", 9, 0, cw_grid.ACROSS),))
            )
        self.assertIn("AB@9,0,across", str(caught.exception))

    def test_rejects_anchors_that_disagree_on_a_shared_cell(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    features=(
                        _pin("ALPHA", 0, 0, cw_grid.ACROSS),
                        _pin("BRAVO", 0, 0, cw_grid.DOWN),
                    )
                )
            )
        message = str(caught.exception)
        self.assertIn("ALPHA@0,0,across", message)
        self.assertIn("BRAVO@0,0,down", message)
        self.assertIn("(0, 0)", message)

    def test_rejects_a_pin_that_ends_where_another_begins(self) -> None:
        # Along one line AB is the start of ABC, so AB is no entry at all: the
        # pinned cells agree letter for letter, and still one pin swallows the
        # other. Decided by the flags alone, so it is refused here at exit 2.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    features=(
                        _pin("AB", 0, 0, cw_grid.ACROSS),
                        _pin("ABC", 0, 0, cw_grid.ACROSS),
                    )
                )
            )
        message = str(caught.exception)
        self.assertIn("AB@0,0,across", message)
        self.assertIn("ABC@0,0,across", message)

    def test_rejects_a_perpendicular_pin_starting_just_past_another(self) -> None:
        # CRANE's first cell is the one after CHALK's last, so the top row reads
        # CHALKC. The cell AFTER a pin is checked, whatever direction the other
        # pin runs.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    features=(
                        _pin("CHALK", 0, 0, cw_grid.ACROSS),
                        _pin("CRANE", 0, 5, cw_grid.DOWN),
                    )
                )
            )
        self.assertIn("CRANE@0,5,down", str(caught.exception))

    def test_rejects_a_pin_starting_just_after_another_pinned_cell(self) -> None:
        # DOG starts at (0, 3) and CAT runs DOWN through (0, 2), so the top row
        # reads CDOG. Nothing sits past DOG's END: only the cell BEFORE its start
        # catches this one, so the two directions are pinned separately.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    features=(
                        _pin("DOG", 0, 3, cw_grid.ACROSS),
                        _pin("CAT", 0, 2, cw_grid.DOWN),
                    )
                )
            )
        self.assertIn("DOG@0,3,across", str(caught.exception))

    def test_accepts_pins_that_touch_only_diagonally(self) -> None:
        # The name-grid sample's own layout: DOE begins diagonally below JANE's
        # last letter. Diagonal contact forms no run, so it is no collision.
        cw_feature.validate_features(
            _config(
                features=(
                    _pin("JANE", 0, 0, cw_grid.ACROSS),
                    _pin("DOE", 1, 4, cw_grid.DOWN),
                )
            )
        )


class TestPinsAgainstAMask(unittest.TestCase):
    """A pin is an operator's claim, so a masked cell refuses it rather than losing.

    The asymmetry with an island is deliberate: a pin is something the operator
    ASKED for, and silently dropping it would give them a grid that is not what
    they wrote. An island is a choice the tool makes for itself, so a mask
    merely makes the cell ineligible.
    """

    def test_a_pin_into_a_masked_cell_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    features=(_pin("CAT", 0, 0, cw_grid.ACROSS),),
                    masked=frozenset({(0, 2)}),
                    mask_size=(9, 9),
                )
            )
        message = str(caught.exception)
        self.assertIn("--feature", message)
        self.assertIn("--mask", message)
        self.assertIn("0,2", message)

    def test_a_pin_clear_of_the_mask_is_accepted(self) -> None:
        # The other side of the guard: a check reading the mask as "anywhere on
        # the pin's line" would refuse this too.
        cw_feature.validate_features(
            _config(
                features=(_pin("CAT", 0, 0, cw_grid.ACROSS),),
                masked=frozenset({(0, 3)}),
                mask_size=(9, 9),
            )
        )

    def test_an_off_grid_pin_is_still_named_for_the_grid(self) -> None:
        # Ordering: the bounds check runs first, so a pin that is BOTH off the
        # grid and over a masked cell is named for the fault the operator must
        # fix first. Named for the mask instead, the message would point at a
        # picture that cannot describe cells the grid does not have.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_feature.validate_features(
                _config(
                    rows=2,
                    cols=2,
                    features=(_pin("CAT", 0, 0, cw_grid.ACROSS),),
                    masked=frozenset({(0, 1)}),
                    mask_size=(2, 2),
                )
            )
        self.assertIn("runs off a 2x2 grid", str(caught.exception))
