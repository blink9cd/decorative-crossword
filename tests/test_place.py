"""Tests for cw_place: the no-accidental-run rule and candidate enumeration."""

import unittest
from collections.abc import Iterator

import cw_grid
import cw_place


def _grid(rows: tuple[str, ...]) -> cw_grid.Grid:
    """A Grid pre-filled from row strings, for readable test setup."""
    grid = cw_grid.Grid(len(rows), len(rows[0]))
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            if cell != cw_grid.BLOCK:
                grid.set_letter(row_index, col_index, cell)
    return grid


class TestFits(unittest.TestCase):
    """fits checks bounds, the mask and letter agreement, nothing else."""

    def test_accepts_an_empty_lane(self) -> None:
        grid = cw_grid.Grid(3, 3)
        placement = cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS)
        self.assertTrue(cw_place.fits(grid, placement))

    def test_accepts_agreeing_letters(self) -> None:
        grid = _grid(("C..", "...", "..."))
        self.assertTrue(
            cw_place.fits(grid, cw_place.Placement("COW", 0, 0, cw_grid.DOWN))
        )

    def test_rejects_disagreeing_letters(self) -> None:
        grid = _grid(("C..", "...", "..."))
        self.assertFalse(
            cw_place.fits(grid, cw_place.Placement("DOG", 0, 0, cw_grid.DOWN))
        )

    def test_rejects_running_off_the_edge(self) -> None:
        grid = cw_grid.Grid(3, 3)
        self.assertFalse(
            cw_place.fits(grid, cw_place.Placement("CHEMEX", 0, 0, cw_grid.ACROSS))
        )

    def test_rejects_running_off_the_bottom(self) -> None:
        # The ACROSS case above only ever exercises the column bound; a fits that
        # checked columns alone would pass it while writing off the last row.
        grid = cw_grid.Grid(3, 3)
        self.assertFalse(
            cw_place.fits(grid, cw_place.Placement("CHEMEX", 0, 0, cw_grid.DOWN))
        )

    def test_rejects_a_start_before_the_grid(self) -> None:
        # `cw_reach.placements_over` steps back from a run by the matched
        # letters' offset, so a start before the grid is a shape it really
        # produces. fits has to answer False for it; reading the cell instead
        # would raise out of Grid.letter and take the whole enumeration down
        # with it.
        grid = cw_grid.Grid(3, 3)
        self.assertFalse(
            cw_place.fits(grid, cw_place.Placement("AB", 0, -1, cw_grid.ACROSS))
        )
        self.assertFalse(
            cw_place.fits(grid, cw_place.Placement("AB", -1, 0, cw_grid.DOWN))
        )


class TestGridViolations(unittest.TestCase):
    """Every run of two or more cells must be a distinct allowed answer."""

    def test_clean_grid_has_no_violations(self) -> None:
        self.assertEqual(
            cw_place.grid_violations(("CAT", "O..", "W.."), {"CAT", "COW"}), ()
        )

    def test_reports_a_run_that_is_not_an_allowed_answer(self) -> None:
        # The two T's stack into a vertical "TT" that nobody asked for and that
        # is not in the bank: exactly the accidental letter pair the rule
        # exists to forbid. Asserted as the whole message:
        # a substring check reads as coverage of the position and direction it
        # never actually touches.
        self.assertEqual(
            cw_place.grid_violations(("CAT", "..T"), {"CAT"}),
            ("down run 'TT' at (0, 2) is not a bank answer",),
        )

    def test_reports_a_duplicated_answer(self) -> None:
        # Two entries sharing one answer cannot carry distinct clues downstream.
        # The rows are chosen so duplication is the only possible fault: both
        # columns read "A.A" and "B.B", single cells either side of a block, so
        # there is no perpendicular pair to report. Stacking the rows directly
        # instead ("AB", "AB") spells the non-bank columns "AA" and "BB", and a
        # merely non-empty assertion then passes with the distinctness clause
        # deleted: a test that cannot fail for its own stated reason.
        self.assertEqual(
            cw_place.grid_violations(("AB", "..", "AB"), {"AB"}),
            ("across run 'AB' at (2, 0) repeats an answer already placed",),
        )

    def test_reports_every_copy_after_the_first(self) -> None:
        # Three copies, because a rule that reports only its first repeat still
        # passes the two-copy case above. Rows shaped as there, so duplication
        # stays the only fault.
        rows = ("AB", "..", "AB", "..", "AB")
        self.assertEqual(
            cw_place.breaks_among(cw_grid.runs_from_rows(rows), {"AB"}),
            (
                (cw_grid.Run(2, 0, cw_grid.ACROSS, "AB"), cw_place._ALREADY_PLACED),
                (cw_grid.Run(4, 0, cw_grid.ACROSS, "AB"), cw_place._ALREADY_PLACED),
            ),
        )

    def test_ignores_single_cells(self) -> None:
        self.assertEqual(cw_place.grid_violations(("A.", ".."), {"XY"}), ())

    def test_names_an_across_run_by_its_own_position(self) -> None:
        # The run starts at column 1, not at the scan line's origin: a report that
        # hardcoded the position would still pass every origin-anchored case.
        self.assertEqual(
            cw_place.grid_violations((".AB", "..."), set()),
            ("across run 'AB' at (0, 1) is not a bank answer",),
        )

    def test_names_a_down_run_by_its_own_position(self) -> None:
        self.assertEqual(
            cw_place.grid_violations(("..", ".A", ".B"), set()),
            ("down run 'AB' at (1, 1) is not a bank answer",),
        )

    def test_reports_every_offending_run_in_scan_order(self) -> None:
        # Pins the documented order: every ACROSS run row-major, then every DOWN
        # run column-major: the order cw_grid.runs_from_rows guarantees.
        self.assertEqual(
            cw_place.grid_violations(("AB", "CD"), {"AB"}),
            (
                "across run 'CD' at (1, 0) is not a bank answer",
                "down run 'AC' at (0, 0) is not a bank answer",
                "down run 'BD' at (0, 1) is not a bank answer",
            ),
        )


class TestApplyAndUndo(unittest.TestCase):
    """A placement is exactly reversible, which is what makes backtracking safe."""

    def test_undo_restores_the_original_grid(self) -> None:
        grid = _grid(("C..", "...", "..."))
        before = grid.to_rows()
        filled = cw_place.apply_placement(
            grid, cw_place.Placement("COW", 0, 0, cw_grid.DOWN)
        )
        self.assertNotEqual(grid.to_rows(), before)
        cw_place.undo_placement(grid, filled)
        self.assertEqual(grid.to_rows(), before)

    def test_undo_leaves_cells_the_placement_did_not_fill(self) -> None:
        # The C was already there; undoing COW must not erase it. A naive undo
        # that clears every cell of the placement silently destroys crossings.
        grid = _grid(("C..", "...", "..."))
        filled = cw_place.apply_placement(
            grid, cw_place.Placement("COW", 0, 0, cw_grid.DOWN)
        )
        cw_place.undo_placement(grid, filled)
        self.assertEqual(grid.letter(0, 0), "C")

    def test_apply_writes_every_letter_away_from_the_origin(self) -> None:
        # A span walk anchored at (0, 0) would pass every origin-started case.
        grid = cw_grid.Grid(3, 3)
        cw_place.apply_placement(grid, cw_place.Placement("AB", 1, 1, cw_grid.DOWN))
        self.assertEqual(grid.to_rows(), ("...", ".A.", ".B."))

    def test_apply_reports_only_the_cells_it_newly_filled(self) -> None:
        grid = _grid(("C..", "...", "..."))
        filled = cw_place.apply_placement(
            grid, cw_place.Placement("COW", 0, 0, cw_grid.DOWN)
        )
        self.assertEqual(filled, ((1, 0), (2, 0)))

    def test_undo_restores_a_grid_that_already_holds_a_crossing_word(self) -> None:
        # The classic backtracking bug: COW crosses CAT at the shared C, so an
        # undo driven by the placement's span rather than by what it actually
        # filled would delete a letter belonging to an entry it never touched.
        grid = _grid(("CAT", "...", "..."))
        before = grid.to_rows()
        filled = cw_place.apply_placement(
            grid, cw_place.Placement("COW", 0, 0, cw_grid.DOWN)
        )
        self.assertEqual(grid.to_rows(), ("CAT", "O..", "W.."))
        cw_place.undo_placement(grid, filled)
        self.assertEqual(grid.to_rows(), before)

    def test_apply_rejects_a_placement_that_runs_off_the_grid(self) -> None:
        # Writing letter by letter until Grid.set_letter raises would leave the
        # prefix on the board with no undo list returned: unrecoverable state.
        grid = cw_grid.Grid(3, 3)
        with self.assertRaises(ValueError):
            cw_place.apply_placement(
                grid, cw_place.Placement("CHEMEX", 0, 0, cw_grid.ACROSS)
            )
        self.assertEqual(grid.to_rows(), ("...", "...", "..."))

    def test_apply_rejects_a_placement_whose_letters_disagree(self) -> None:
        grid = _grid(("C..", "...", "..."))
        with self.assertRaises(ValueError):
            cw_place.apply_placement(
                grid, cw_place.Placement("DOG", 0, 0, cw_grid.DOWN)
            )
        self.assertEqual(grid.to_rows(), ("C..", "...", "..."))


class TestCrossingCandidates(unittest.TestCase):
    """Candidates must cross an existing letter, so the grid stays connected."""

    def test_offers_placements_that_cross_a_filled_cell(self) -> None:
        grid = _grid(("CAT", "...", "..."))
        found = cw_place.crossing_candidates(grid, ["COW"])
        self.assertIn(cw_place.Placement("COW", 0, 0, cw_grid.DOWN), found)

    def test_offers_nothing_on_an_empty_grid(self) -> None:
        # The seed placement is the search's job, not the candidate list's:
        # there is no letter to cross yet.
        self.assertEqual(cw_place.crossing_candidates(cw_grid.Grid(3, 3), ["CAT"]), [])

    def test_offers_both_directions_for_one_crossed_letter(self) -> None:
        # Exact list, so the documented ACROSS-before-DOWN order is pinned too.
        grid = _grid(("...", ".A.", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["AB"]),
            [
                cw_place.Placement("AB", 1, 1, cw_grid.ACROSS),
                cw_place.Placement("AB", 1, 1, cw_grid.DOWN),
            ],
        )

    def test_offers_an_alignment_that_starts_before_the_crossed_cell(self) -> None:
        # The crossed B is the answer's second letter, so each start sits one step
        # back along its own direction. An enumerator that only ever aligned offset
        # 0 would return nothing here and still pass every other case in this class.
        grid = _grid(("...", ".B.", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["AB"]),
            [
                cw_place.Placement("AB", 1, 0, cw_grid.ACROSS),
                cw_place.Placement("AB", 0, 1, cw_grid.DOWN),
            ],
        )

    def test_offers_every_matching_offset_in_ascending_order(self) -> None:
        # An answer that carries the crossed letter once cannot tell
        # all-offsets-ascending apart from first-offset-only, last-offset-only,
        # or descending, and branch coverage cannot either: a single-offset
        # answer still reaches both arms of the offset loop.
        # "ATA" crosses the A at (2, 2) at offsets 0 and 2, and the exact list
        # kills all three mutants: first-offset-only drops the last two
        # entries, last-offset-only drops the first two, descending reorders.
        grid = _grid((".....", ".....", "..A..", ".....", "....."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["ATA"]),
            [
                cw_place.Placement("ATA", 2, 2, cw_grid.ACROSS),
                cw_place.Placement("ATA", 2, 2, cw_grid.DOWN),
                cw_place.Placement("ATA", 2, 0, cw_grid.ACROSS),
                cw_place.Placement("ATA", 0, 2, cw_grid.DOWN),
            ],
        )

    def test_rejects_an_alignment_that_would_start_outside_the_grid(self) -> None:
        # Crossing the A at (0, 0) as BA's second letter puts the start at column
        # -1 (ACROSS) or row -1 (DOWN); both are off the board.
        grid = _grid(("A..", "...", "..."))
        self.assertEqual(cw_place.crossing_candidates(grid, ["BA"]), [])

    def test_offers_nothing_for_an_answer_that_shares_no_letter(self) -> None:
        grid = _grid(("A..", "...", "..."))
        self.assertEqual(cw_place.crossing_candidates(grid, ["DOG"]), [])

    def test_does_not_repeat_a_placement_reachable_from_two_cells(self) -> None:
        # CAT across at (0, 0) is reachable from the C and again from the A. The
        # search would otherwise explore the identical node twice.
        grid = _grid(("CA.", "...", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["CAT"]),
            [
                cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS),
                cw_place.Placement("CAT", 0, 0, cw_grid.DOWN),
            ],
        )

    def test_visits_filled_cells_in_row_major_order(self) -> None:
        # The documented order is part of the contract, because it decides the
        # search's node order and therefore which grid a seed produces.
        # Column-major would return these same three placements in a
        # different order, so an exact list is what pins it.
        grid = _grid(("..B", "A..", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["AB"]),
            [
                cw_place.Placement("AB", 0, 1, cw_grid.ACROSS),
                cw_place.Placement("AB", 1, 0, cw_grid.ACROSS),
                cw_place.Placement("AB", 1, 0, cw_grid.DOWN),
            ],
        )

    def test_keeps_the_answers_in_the_order_given(self) -> None:
        # Same contract, inner loop: the caller's ranking survives, so sorting
        # or otherwise reordering the bank here would change the search's path.
        grid = _grid(("...", ".A.", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["AC", "AB"]),
            [
                cw_place.Placement("AC", 1, 1, cw_grid.ACROSS),
                cw_place.Placement("AC", 1, 1, cw_grid.DOWN),
                cw_place.Placement("AB", 1, 1, cw_grid.ACROSS),
                cw_place.Placement("AB", 1, 1, cw_grid.DOWN),
            ],
        )

    def test_reads_the_answers_once_so_a_generator_is_not_exhausted(self) -> None:
        # `answers` is an Iterable, and the walk visits it once per filled cell.
        # A one-shot iterator consumed at the first cell would silently offer
        # nothing for every later one: here the only match is at the third.
        grid = _grid(("CAT", "...", "..."))
        answers: Iterator[str] = iter(["TOP"])
        self.assertEqual(
            cw_place.crossing_candidates(grid, answers),
            [cw_place.Placement("TOP", 0, 2, cw_grid.DOWN)],
        )


class TestMaskedCells(unittest.TestCase):
    """A masked cell is one no placement may cover, in either generator.

    Both are tested with the same grid and the same masked cell, because the two
    make the judgment by different means (`fits` reads the grid cell by cell,
    `crossing_candidates` reads a derived line view), and the whole point of
    the design is that they cannot disagree.
    """

    def test_fits_rejects_a_placement_over_a_masked_cell(self) -> None:
        grid = cw_grid.Grid(3, 3)
        placement = cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS)
        self.assertFalse(cw_place.fits(grid, placement, frozenset({(0, 2)})))

    def test_fits_accepts_a_placement_that_stops_short_of_one(self) -> None:
        # The other side of the guard: a mask that rejected everything, or one
        # read as "anywhere on the line", would also pass the test above.
        grid = cw_grid.Grid(3, 3)
        placement = cw_place.Placement("AB", 0, 0, cw_grid.ACROSS)
        self.assertTrue(cw_place.fits(grid, placement, frozenset({(0, 2)})))

    def test_fits_ignores_a_masked_cell_on_another_line(self) -> None:
        grid = cw_grid.Grid(3, 3)
        placement = cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS)
        self.assertTrue(cw_place.fits(grid, placement, frozenset({(2, 2)})))

    def test_fits_without_a_mask_is_unchanged(self) -> None:
        grid = cw_grid.Grid(3, 3)
        placement = cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS)
        self.assertTrue(cw_place.fits(grid, placement))

    def test_crossing_candidates_offers_nothing_over_a_masked_cell(self) -> None:
        grid = _grid(("CAT", "...", "..."))
        found = cw_place.crossing_candidates(grid, ["COW"], frozenset({(2, 0)}))
        self.assertNotIn(cw_place.Placement("COW", 0, 0, cw_grid.DOWN), found)

    def test_crossing_candidates_still_offers_what_the_mask_leaves(self) -> None:
        # COW down column 0 is blocked by the mask at (2, 0); TOP down column 2
        # is not, so a stamp read as "this whole line is forbidden" fails here.
        grid = _grid(("CAT", "...", "..."))
        found = cw_place.crossing_candidates(grid, ["COW", "TOP"], frozenset({(2, 0)}))
        self.assertEqual(found, [cw_place.Placement("TOP", 0, 2, cw_grid.DOWN)])

    def test_a_masked_cell_does_not_stop_a_placement_crossing_it_sideways(
        self,
    ) -> None:
        # The stamp goes into the derived line view, and both an across line and
        # a down line pass through the same cell. A stamp written into only one
        # of the two orientations would let a placement through in the other.
        grid = _grid(("...", ".A.", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["AB"], frozenset({(1, 2), (2, 1)})),
            [],
        )

    def test_crossing_candidates_without_a_mask_is_unchanged(self) -> None:
        grid = _grid(("CAT", "...", "..."))
        self.assertEqual(
            cw_place.crossing_candidates(grid, ["COW"]),
            [cw_place.Placement("COW", 0, 0, cw_grid.DOWN)],
        )


if __name__ == "__main__":
    unittest.main()
