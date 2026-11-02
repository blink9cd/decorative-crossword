"""Tests for cw_island: lone decorative letters in blocked cells that touch a letter
only at a corner.

An island is the one deliberate exception to "every filled cell belongs to an entry",
so what qualifies is pinned narrowly: no letter above, below, left or right, and a
letter of the original grid at a corner. The letter itself must read as a word on its
own, and is the first of the operator's letters that no touching corner already shows.
"""

import unittest

import cw_config
import cw_island

from tests import interlock_fixtures as grids

#: The letters a normal run asks for.
_AIX = ("A", "I", "X")


class TestParseIslandLetters(unittest.TestCase):
    """`--island-letters` names A, I, X, U or Y, in order of preference."""

    def test_reads_the_letters_in_order(self) -> None:
        self.assertEqual(cw_island.parse_island_letters("AIX"), _AIX)

    def test_folds_lower_case(self) -> None:
        self.assertEqual(cw_island.parse_island_letters("aix"), _AIX)

    def test_accepts_the_sound_alike_words(self) -> None:
        self.assertEqual(cw_island.parse_island_letters("UY"), ("U", "Y"))

    def test_rejects_an_empty_value(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_island.parse_island_letters("")
        self.assertIn("--island-letters", str(caught.exception))

    def test_rejects_a_letter_that_is_no_word_on_its_own(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_island.parse_island_letters("AB")
        message = str(caught.exception)
        self.assertIn("--island-letters", message)
        self.assertIn("'B'", message)


class TestFillIslands(unittest.TestCase):
    """Which blocked cells take a letter, and which letter each takes."""

    def test_fills_a_corner_touching_a_letter_only_diagonally(self) -> None:
        # The target's top-left block: blocks beside it, D at its corner. Its
        # other three blocks each have a letter beside them and stay blocked.
        rows, placed = cw_island.fill_islands(grids.TARGET, _AIX)
        self.assertEqual(rows, ("A.ABC", ".DEFG", "HIJKL", "MNOPQ", "RST.U"))
        self.assertEqual(placed, ((0, 0, "A"),))

    def test_only_letters_of_the_original_grid_make_a_cell_an_island(self) -> None:
        # (1, 3) touches the T at a corner. The cells around the letter placed
        # there touch only that letter, so they stay blocked: islands never chain
        # across empty space.
        rows, placed = cw_island.fill_islands(("CAT...", "......", "......"), _AIX)
        self.assertEqual(rows, ("CAT...", "...A..", "......"))
        self.assertEqual(placed, ((1, 3, "A"),))

    def test_two_neighboring_islands_never_both_take_a_letter(self) -> None:
        # (1, 1) and (1, 2) both qualify on the grid as given. Filling the first
        # puts a letter beside the second, which is then no island: otherwise
        # the two would spell a two-letter run no bank holds.
        rows, placed = cw_island.fill_islands(("C..C", "...."), _AIX)
        self.assertEqual(rows, ("C..C", ".A.."))
        self.assertEqual(placed, ((1, 1, "A"),))

    def test_takes_the_first_letter_no_touching_corner_shows(self) -> None:
        rows, _ = cw_island.fill_islands(("A..", "...", "..."), ("A", "I"))
        self.assertEqual(rows[1], ".I.")

    def test_falls_back_to_the_first_letter_when_every_letter_is_shown(self) -> None:
        rows, _ = cw_island.fill_islands(("A..", "...", "..."), ("A",))
        self.assertEqual(rows[1], ".A.")

    def test_a_placed_island_letter_counts_as_shown_to_a_later_island(self) -> None:
        # (1, 1) touches the corner A and takes I. (2, 2) touches the corner A
        # below and the I just placed, so it takes X.
        rows, placed = cw_island.fill_islands(("A...", "....", "....", "...A"), _AIX)
        self.assertEqual(rows, ("A...", ".I..", "..X.", "...A"))
        self.assertEqual(placed, ((1, 1, "I"), (2, 2, "X")))

    def test_a_grid_without_an_island_comes_back_unchanged(self) -> None:
        self.assertEqual(cw_island.fill_islands(("CAT",), _AIX), (("CAT",), ()))


class TestSpare(unittest.TestCase):
    """`spare` is how many blocked cells the grid may give up; past it, cells stay blocked."""

    def test_lays_only_as_many_islands_as_the_grid_can_spare(self) -> None:
        # (1, 1) and (2, 2) both qualify. Room for one keeps the first found,
        # row-major, and (2, 2) stays blocked though it still qualifies.
        rows, placed = cw_island.fill_islands(
            ("A...", "....", "....", "...A"), _AIX, spare=1
        )
        self.assertEqual(rows, ("A...", ".I..", "....", "...A"))
        self.assertEqual(placed, ((1, 1, "I"),))

    def test_nothing_to_spare_lays_nothing(self) -> None:
        rows = ("A...", "....", "....", "...A")
        self.assertEqual(cw_island.fill_islands(rows, _AIX, spare=0), (rows, ()))


class TestMaskedCells(unittest.TestCase):
    """A masked cell is ineligible for an island, never a reason to refuse.

    The other half of the pin/island asymmetry: an island is a choice the tool
    makes for itself, so a mask simply takes the cell off the table. A
    `--feature` pin in the same cell is refused instead, because that is
    something the operator asked for: `test_feature.py` owns that side.
    """

    def test_a_masked_cell_never_takes_an_island_letter(self) -> None:
        rows = ("A...", "....", "....")
        self.assertEqual(
            cw_island.fill_islands(rows, _AIX, masked=frozenset({(1, 1)})),
            (rows, ()),
        )

    def test_unmasked_the_same_cell_takes_one(self) -> None:
        # The other side of the guard: without this, a `fill_islands` that laid
        # nothing at all would pass the test above.
        rows, placed = cw_island.fill_islands(("A...", "....", "...."), _AIX)
        self.assertEqual(placed, ((1, 1, "I"),))

    def test_a_masked_cell_does_not_stop_an_island_elsewhere(self) -> None:
        # A mask read as "no islands at all" would leave this grid bare.
        _, placed = cw_island.fill_islands(
            ("A...", "....", "...."), _AIX, masked=frozenset({(2, 3)})
        )
        self.assertEqual(placed, ((1, 1, "I"),))


class TestFixedLoneLetters(unittest.TestCase):
    """Letters already lone before islands are laid never qualify a corner."""

    def test_a_fixed_lone_letter_qualifies_no_island(self) -> None:
        rows = ("A...", "....", "....")
        self.assertEqual(
            cw_island.fill_islands(rows, _AIX, fixed=frozenset({(0, 0)})), (rows, ())
        )

    def test_unfixed_the_same_letter_would_qualify_one(self) -> None:
        # The discriminating half: without `fixed`, (1, 1) takes the first letter
        # its corners do not show, which proves the case above tests something.
        _, placed = cw_island.fill_islands(("A...", "....", "...."), _AIX)
        self.assertEqual(placed, ((1, 1, "I"),))

    def test_an_entry_letter_at_another_corner_still_qualifies_the_cell(self) -> None:
        _, placed = cw_island.fill_islands(
            ("A...", "....", "..CA"), _AIX, fixed=frozenset({(0, 0)})
        )
        self.assertEqual(placed, ((1, 1, "I"),))

    def test_a_fixed_letter_still_blocks_an_island_beside_it(self) -> None:
        """`fixed` empties a corner only, never a side: that guards the one rule.

        (1, 2) touches the entry's A at a corner, but the fixed A sits beside it.
        A letter there would spell a two-letter run no bank holds.
        """
        rows = ("CA..", "...A")
        self.assertEqual(
            cw_island.fill_islands(rows, _AIX, fixed=frozenset({(1, 3)})), (rows, ())
        )

    def test_lone_cells_names_strays_and_islands_alike(self) -> None:
        self.assertEqual(cw_island.lone_cells(("CAT..", ".....", "DOG.Q")), ((2, 4),))
        self.assertEqual(cw_island.lone_cells(("CAT.", "...A")), ((1, 3),))
        # Row-major: a column-first order would put (2, 0) ahead of (0, 3).
        self.assertEqual(
            cw_island.lone_cells(("...Q", "....", "Z...")), ((0, 3), (2, 0))
        )


class TestStrayLetters(unittest.TestCase):
    """Which lone letters of a grid this tool did not write are strays, not islands.

    The read side of the rule, so a corner counts only when an entry covers it:
    the grid the letters were laid on is gone, and a letter walled in beside it
    may be a stray itself.
    """

    def test_a_letter_off_the_set_is_a_stray_even_at_an_entry_corner(self) -> None:
        # Q touches CAT's T at a corner, which would make an A an island.
        self.assertEqual(
            cw_island.stray_letters(("CAT.", "...Q")),
            ((1, 3, "Q", "Q is not an island letter (A, I, X, U, Y)"),),
        )

    def test_every_island_letter_at_an_entry_corner_is_no_stray(self) -> None:
        for letter in cw_island.ISLAND_LETTERS:
            with self.subTest(letter=letter):
                self.assertEqual(cw_island.stray_letters(("CAT.", f"...{letter}")), ())

    def test_an_island_letter_touching_only_another_island_is_a_stray(self) -> None:
        # The A at (1, 3) is an island; the I at (2, 4) touches nothing but it.
        ((row, col, letter, reason),) = cw_island.stray_letters(
            ("CAT..", "...A.", "....I")
        )
        self.assertEqual((row, col, letter), (2, 4, "I"))
        self.assertIn("corner", reason)

    def test_an_island_letter_touching_nothing_is_a_stray(self) -> None:
        ((row, col, letter, reason),) = cw_island.stray_letters(("CAT..", "....A"))
        self.assertEqual((row, col, letter), (1, 4, "A"))
        self.assertIn("corner", reason)

    def test_a_letter_in_an_entry_is_never_a_stray(self) -> None:
        # Each letter of the down run stands alone across, and Q sits inside QT.
        self.assertEqual(cw_island.stray_letters(("C..", "A..", "T..")), ())
        self.assertEqual(cw_island.stray_letters(("QT",)), ())

    def test_strays_come_back_row_major(self) -> None:
        found = cw_island.stray_letters(("Q...Z", ".....", "..K.."))
        self.assertEqual(
            [(row, col) for row, col, _, _ in found], [(0, 0), (0, 4), (2, 2)]
        )

    def test_a_grid_with_no_letters_has_no_strays(self) -> None:
        self.assertEqual(cw_island.stray_letters(("..", "..")), ())
