"""Tests for cw_grid: run derivation, density, and the mutable grid."""

import unittest

import cw_grid


class TestRunsFromRows(unittest.TestCase):
    """A run is a maximal line of two or more filled cells, in either direction."""

    def test_finds_across_and_down_runs(self) -> None:
        runs = cw_grid.runs_from_rows(("CAT", "O..", "WET"))
        found = {(run.text, run.direction, run.row, run.col) for run in runs}
        self.assertIn(("CAT", cw_grid.ACROSS, 0, 0), found)
        self.assertIn(("WET", cw_grid.ACROSS, 2, 0), found)
        self.assertIn(("COW", cw_grid.DOWN, 0, 0), found)

    def test_ignores_single_cells(self) -> None:
        # The lone T at (1, 2) has no neighbor in either direction, so it is in no
        # run. Length-1 runs are never entries.
        runs = cw_grid.runs_from_rows(("AB.", "..T"))
        self.assertEqual([run.text for run in runs], ["AB"])

    def test_run_cells_walk_the_direction(self) -> None:
        (run,) = cw_grid.runs_from_rows(("AB",))
        self.assertEqual(run.cells, ((0, 0), (0, 1)))

    def test_across_run_start_is_not_always_the_line_origin(self) -> None:
        # Every other case in this class starts its run at offset 0 of its scan
        # line, which never exercises the "start partway through the line"
        # arithmetic -- a stretch_start hardcoded to 0 would still pass them
        # all. This run starts at column 1.
        (run,) = cw_grid.runs_from_rows((".AB",))
        self.assertEqual((run.row, run.col), (0, 1))
        self.assertEqual(run.cells, ((0, 1), (0, 2)))

    def test_down_run_start_is_not_always_the_column_origin(self) -> None:
        # Same gap, DOWN direction: the column's run starts at row 1, not 0.
        (run,) = cw_grid.runs_from_rows((".", "A", "B"))
        self.assertEqual((run.row, run.col), (1, 0))
        self.assertEqual(run.cells, ((1, 0), (2, 0)))


class TestFindAnswer(unittest.TestCase):
    """find_answer locates one answer's run, for `preview --feature`."""

    def test_returns_the_matching_run(self) -> None:
        run = cw_grid.find_answer(("CAT", "O..", "WET"), "COW")
        self.assertIsNotNone(run)
        assert run is not None  # narrows for mypy
        self.assertEqual(run.direction, cw_grid.DOWN)
        self.assertEqual(run.cells, ((0, 0), (1, 0), (2, 0)))

    def test_returns_none_when_absent(self) -> None:
        self.assertIsNone(cw_grid.find_answer(("CAT",), "DOG"))


class TestBlockedPercent(unittest.TestCase):
    """Density is percent BLOCKED cells."""

    def test_counts_blocks_over_area(self) -> None:
        # 3x3 = 9 cells, 3 of them blocked: "O.." and "W.T" contribute 2 + 1.
        # The arithmetic is derived from the row tuple beside it rather than
        # copied, so each figure in it can be checked against the rows.
        self.assertAlmostEqual(cw_grid.blocked_percent(("CAT", "O..", "W.T")), 300 / 9)

    def test_all_blocked_is_one_hundred(self) -> None:
        self.assertEqual(cw_grid.blocked_percent(("..", "..")), 100.0)

    def test_empty_grid_is_zero_not_a_division_error(self) -> None:
        # No cells at all -- the divide-by-zero guard, not the general formula.
        self.assertEqual(cw_grid.blocked_percent(()), 0.0)

    def test_a_masked_cell_leaves_both_the_numerator_and_the_denominator(self) -> None:
        # The same grid as above, with one of its three blocked cells masked. If
        # the mask left only the numerator, the answer would be 200/9; if only
        # the denominator, 300/8. Density means "of the cells this grid may use,
        # how many are blocked", so it is 200/8.
        self.assertAlmostEqual(
            cw_grid.blocked_percent(("CAT", "O..", "W.T"), frozenset({(1, 1)})),
            200 / 8,
        )

    def test_masking_every_blocked_cell_leaves_no_blocks(self) -> None:
        self.assertEqual(
            cw_grid.blocked_percent(
                ("CAT", "O..", "W.T"), frozenset({(1, 1), (1, 2), (2, 1)})
            ),
            0.0,
        )

    def test_a_masked_grid_with_no_usable_cell_is_zero(self) -> None:
        # `cw_mask` refuses a wholly-masked picture, so no command line reaches
        # this -- but the guard is the same honest answer the empty grid gets,
        # and without it the arithmetic divides by zero.
        self.assertEqual(
            cw_grid.blocked_percent(("..",), frozenset({(0, 0), (0, 1)})), 0.0
        )

    def test_an_empty_mask_measures_exactly_as_before(self) -> None:
        rows = ("CAT", "O..", "W.T")
        self.assertEqual(
            cw_grid.blocked_percent(rows, frozenset()), cw_grid.blocked_percent(rows)
        )


class TestGrid(unittest.TestCase):
    """The mutable grid the search writes into."""

    def test_starts_empty(self) -> None:
        grid = cw_grid.Grid(2, 3)
        self.assertEqual(grid.to_rows(), ("...", "..."))
        self.assertIsNone(grid.letter(0, 0))

    def test_reports_its_own_dimensions(self) -> None:
        grid = cw_grid.Grid(2, 3)
        self.assertEqual(grid.height, 2)
        self.assertEqual(grid.width, 3)

    def test_set_and_clear_round_trip(self) -> None:
        grid = cw_grid.Grid(2, 2)
        grid.set_letter(0, 1, "Q")
        self.assertEqual(grid.letter(0, 1), "Q")
        self.assertEqual(grid.to_rows(), (".Q", ".."))
        grid.clear(0, 1)
        self.assertEqual(grid.to_rows(), ("..", ".."))

    def test_runs_reads_through_to_the_pure_helper(self) -> None:
        grid = cw_grid.Grid(1, 2)
        grid.set_letter(0, 0, "A")
        grid.set_letter(0, 1, "B")
        self.assertEqual([run.text for run in grid.runs()], ["AB"])

    def test_letter_rejects_an_out_of_range_index(self) -> None:
        # A negative index would otherwise wrap silently to the far edge
        # instead of signaling the caller's bug.
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.letter(-1, 0)

    def test_set_letter_rejects_an_out_of_range_index(self) -> None:
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.set_letter(2, 0, "A")

    def test_letter_rejects_a_negative_column(self) -> None:
        # The COLUMN half of the same wrap the negative-row case above covers.
        # `_validate_index` is `0 <= row < rows` and `0 <= col < cols`, and the
        # two halves are independent: with only the row case tested, deleting
        # `0 <= col` leaves every negative column wrapping silently to the far
        # edge -- the exact failure the guard's docstring says it exists to
        # catch -- with the whole suite green.
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.letter(0, -1)

    def test_clear_rejects_an_out_of_range_index(self) -> None:
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.clear(0, 2)

    def test_set_letter_rejects_a_multi_character_value(self) -> None:
        # A multi-character value would silently corrupt the one-character-
        # per-cell row-string representation to_rows() produces.
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.set_letter(0, 0, "AB")

    def test_set_letter_rejects_a_letter_outside_a_to_z(self) -> None:
        # A single character that fails the length check trivially (it is
        # exactly one character) still must not pass the range check -- this
        # is a distinct assertion from the multi-character case above, since
        # `len(letter) != 1 or not ("A" <= letter <= "Z")` short-circuits on
        # the first clause and would never reach the second for "AB".
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.set_letter(0, 0, "a")

    def test_set_letter_rejects_the_block_character(self) -> None:
        # The LOWER half of the same range check. "a" is above "Z" and so is
        # rejected by `letter <= "Z"` alone; BLOCK is below "A" and is the only
        # case that needs `"A" <= letter`. Deleting that clause leaves the
        # suite green while `set_letter` happily writes a BLOCK -- which the
        # guard's own docstring names as a case it rejects, and which corrupts
        # the one-character-per-cell row string every consumer parses. `clear`
        # is how a caller blocks a cell.
        grid = cw_grid.Grid(2, 2)
        with self.assertRaises(ValueError):
            grid.set_letter(0, 0, cw_grid.BLOCK)


class TestValidateRows(unittest.TestCase):
    """The grid-coherence check `preview` applies.

    It lives here rather than in the CLI because "what a row of cells may
    contain" is this module's own definition; a copy in the loader would be a
    second statement of it, free to drift from `Grid`'s.
    """

    def test_accepts_a_rectangular_grid_and_returns_it_as_a_tuple(self) -> None:
        # Returns the narrowed value rather than only raising: the loader that
        # calls it has an `object` straight out of `json.loads`, and handing
        # back `tuple[str, ...]` is what saves that caller a cast.
        self.assertEqual(
            cw_grid.validate_rows(["CAT", "O..", "WET"]), ("CAT", "O..", "WET")
        )

    def test_accepts_a_non_square_grid(self) -> None:
        self.assertEqual(len(cw_grid.validate_rows(["PLUMS", "E...O"])), 2)

    def test_rejects_a_grid_that_is_not_a_list(self) -> None:
        with self.assertRaises(ValueError):
            cw_grid.validate_rows("CAT")

    def test_rejects_an_empty_grid(self) -> None:
        with self.assertRaises(ValueError):
            cw_grid.validate_rows([])

    def test_rejects_a_grid_with_no_columns(self) -> None:
        with self.assertRaises(ValueError):
            cw_grid.validate_rows(["", ""])

    def test_rejects_ragged_rows(self) -> None:
        with self.assertRaises(ValueError):
            cw_grid.validate_rows(["CAT", "WETS"])

    def test_rejects_a_row_that_is_not_a_string(self) -> None:
        with self.assertRaises(ValueError):
            cw_grid.validate_rows([["C", "A", "T"]])

    def test_rejects_a_later_row_that_is_not_a_string(self) -> None:
        # Distinct from the case above: a non-string FIRST row is refused by
        # the width-establishing check, so the per-row type check is reachable
        # only from row 1 onward.
        with self.assertRaises(ValueError) as caught:
            cw_grid.validate_rows(["CAT", ["W", "E", "T"]])
        self.assertIn("row 1", str(caught.exception))

    def test_rejects_a_cell_that_is_neither_a_letter_nor_a_block(self) -> None:
        with self.assertRaises(ValueError):
            cw_grid.validate_rows(["CA?", "O..", "WET"])

    def test_rejects_a_lowercase_cell(self) -> None:
        # Distinct from the punctuation case: the emitted contract is A-Z, and
        # a lowercase letter passes any "is it alphabetic" test.
        with self.assertRaises(ValueError):
            cw_grid.validate_rows(["cat", "O..", "WET"])

    def test_the_message_names_the_offending_cell(self) -> None:
        with self.assertRaises(ValueError) as caught:
            cw_grid.validate_rows(["CA?", "O..", "WET"])
        self.assertIn("(0, 2)", str(caught.exception))
