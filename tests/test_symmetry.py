"""Tests for cw_symmetry: how many of a grid's cell pairs match under one symmetry.

The measure is the letter-or-block pattern, never the letters: two partner cells
match when both hold a letter or both are blocked. Each pair is counted once, and
a cell that is its own partner (the center under rotation, a middle column under
a left-right mirror) is no pair at all, so a figure of "N of M" holds no match
that came free.
"""

import unittest

import cw_symmetry

#: A 3x5 grid balanced under rotation alone, which tells the three kinds apart.
_ROTATED = ("EEL..", ".....", "..DOG")


class TestKinds(unittest.TestCase):
    """The kinds `--prefer-symmetry` offers, in the order `--help` lists them."""

    def test_the_kinds_are_rotational_and_the_two_mirrors(self) -> None:
        self.assertEqual(
            tuple(cw_symmetry.KINDS), ("rotational", "left-right", "top-bottom")
        )

    def test_every_partner_rule_is_its_own_inverse(self) -> None:
        # What makes counting each pair once sound: the cell a partner points
        # back to is always the one it came from, on odd and even sides alike.
        for kind, partner in cw_symmetry.KINDS.items():
            for height, width in ((3, 4), (4, 5), (5, 5), (2, 2)):
                for row in range(height):
                    for col in range(width):
                        with self.subTest(
                            kind=kind, size=(height, width), cell=(row, col)
                        ):
                            there = partner(row, col, height, width)
                            self.assertEqual(partner(*there, height, width), (row, col))


class TestMatchingPairs(unittest.TestCase):
    """Matching pairs of partner cells, and how many pairs there are."""

    def test_rotation_leaves_the_center_of_an_odd_grid_out(self) -> None:
        self.assertEqual(cw_symmetry.matching_pairs(("...",) * 3, "rotational"), (4, 4))
        self.assertEqual(
            cw_symmetry.matching_pairs(("....",) * 2, "rotational"), (4, 4)
        )

    def test_a_left_right_mirror_leaves_the_middle_column_out(self) -> None:
        self.assertEqual(cw_symmetry.matching_pairs(("...",) * 3, "left-right"), (3, 3))
        self.assertEqual(
            cw_symmetry.matching_pairs(("....",) * 2, "left-right"), (4, 4)
        )

    def test_a_top_bottom_mirror_leaves_the_middle_row_out(self) -> None:
        self.assertEqual(cw_symmetry.matching_pairs(("..",) * 3, "top-bottom"), (2, 2))
        self.assertEqual(cw_symmetry.matching_pairs(("...",) * 4, "top-bottom"), (6, 6))

    def test_a_single_cell_is_no_pair_under_any_kind(self) -> None:
        for kind in cw_symmetry.KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(cw_symmetry.matching_pairs(("A",), kind), (0, 0))

    def test_two_different_letters_still_match(self) -> None:
        # The pattern, never the letters: CAT over DOG mirrors top to bottom
        # although no letter meets its own.
        self.assertEqual(
            cw_symmetry.matching_pairs(("CAT", "...", "DOG"), "top-bottom"), (3, 3)
        )

    def test_a_letter_against_a_block_is_a_mismatch(self) -> None:
        # Of seven rotated pairs, only T-with-G and the middle row's two match.
        self.assertEqual(
            cw_symmetry.matching_pairs(("CAT..", ".....", "DOG.."), "rotational"),
            (3, 7),
        )

    def test_each_kind_reads_the_same_grid_differently(self) -> None:
        self.assertEqual(cw_symmetry.matching_pairs(_ROTATED, "rotational"), (7, 7))
        self.assertEqual(cw_symmetry.matching_pairs(_ROTATED, "left-right"), (2, 6))
        self.assertEqual(cw_symmetry.matching_pairs(_ROTATED, "top-bottom"), (1, 5))
