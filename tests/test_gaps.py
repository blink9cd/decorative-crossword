"""Grouped suite: what a letter in a blocked cell would demand of the bank.

Two halves, and the second is the one that matters. Deciding *whether* a
blocked cell could take a letter is nearly free -- almost every one could, so a
suite that only checked "it found some candidates" would stay green against a
tool that described every one of them wrongly. The DEMAND is the load-bearing
half, and the obvious implementation of it -- read the cell's immediate
neighbors -- is wrong in a way that matters: filling a cell between two
existing runs WELDS them, so the run that has to be a bank answer afterward is
the whole thing, not the two letters either side of the gap.

`TestWelding` is where that is pinned. On `AB.CD` a neighbors-only reader
reports `B?C` and asks the operator for a three-letter word; the truth is
`AB?CD`, a five-letter word, and accepting the wrong one would retire `AB` and
`CD` from the puzzle without saying so. The absorbed answers are asserted
alongside the pattern, so an implementation that got the pattern right by
accident and stayed silent about the cost still fails.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import unittest

import cw_gaps
import cw_grid


#: A grid in which blocked cell (0, 1) has one letter neighbor, the A, so the
#: fill is pure addition: one new two-letter run, nothing existing disturbed.
#: Column 0 carries AB as a down run, which is what makes the A at (0, 0) a
#: letter that already belongs to an entry rather than an orphan.
PURE_ADDITION = ("A.", "B.")

#: One row, two runs, one gap. The fill welds them into a single five-letter
#: run and retires both -- the case a neighbors-only reader gets wrong.
WELD = ("AB.CD",)

#: A blocked cell with a letter to its left AND a letter above it, so the fill
#: creates two runs at once and both must be satisfied by the same letter.
BOTH_AXES = ("HAY.", "E...", "D...", "GIRL")

#: Every cell blocked: no cell has a letter neighbor, so nothing here could
#: take a letter that belonged to an entry.
ALL_BLOCKED = ("..", "..")


def _patterns(candidate: cw_gaps.Candidate) -> tuple[str, ...]:
    """The demanded patterns of one candidate, in the order it holds them."""
    return tuple(demand.pattern for demand in candidate.demands)


def _at(analysis: cw_gaps.GapAnalysis, row: int, col: int) -> cw_gaps.Candidate:
    """The candidate for one cell, or fail the calling test saying it is absent."""
    for candidate in analysis.candidates:
        if (candidate.row, candidate.col) == (row, col):
            return candidate
    raise AssertionError(f"no candidate at ({row}, {col})")


class TestPureAddition(unittest.TestCase):
    """A gap beside a single letter demands one short run and disturbs nothing."""

    def test_one_demand_on_the_axis_with_a_neighbor(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(PURE_ADDITION), 0, 1)
        self.assertEqual(_patterns(candidate), ("A?",))

    def test_the_demand_names_the_across_direction(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(PURE_ADDITION), 0, 1)
        self.assertEqual(candidate.demands[0].direction, cw_grid.ACROSS)

    def test_nothing_is_absorbed(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(PURE_ADDITION), 0, 1)
        self.assertEqual(candidate.absorbed, ())

    def test_a_gap_below_a_letter_demands_a_down_run(self) -> None:
        # (1, 0) sits under A at (0, 0) and beside C at (1, 1), so it demands
        # an ACROSS run and a DOWN one. Asserting the DOWN demand `A?` is what
        # stops a transposed implementation passing the row cases while getting
        # every column case backwards.
        candidate = _at(cw_gaps.analyze_grid(("AB", ".C")), 1, 0)
        self.assertEqual(_patterns(candidate), ("?C", "A?"))

    def test_the_down_demand_starts_at_the_run_not_the_cell(self) -> None:
        # The DOWN run created at (1, 0) begins at (0, 0), where A already is.
        # A demand that reported its own cell as the start would send a reader
        # to the wrong square.
        candidate = _at(cw_gaps.analyze_grid(("AB", ".C")), 1, 0)
        down = candidate.demands[1]
        self.assertEqual((down.direction, down.row, down.col), (cw_grid.DOWN, 0, 0))


class TestWelding(unittest.TestCase):
    """Filling a gap between two runs demands the WHOLE welded run, and says so.

    The distinction a neighbors-only reader loses. Both assertions matter: the
    pattern is what the operator has to match, and the absorbed list is what it
    would cost them.
    """

    def test_the_pattern_spans_both_runs(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(WELD), 0, 2)
        self.assertEqual(_patterns(candidate), ("AB?CD",))

    def test_the_pattern_is_not_the_immediate_neighbors(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(WELD), 0, 2)
        self.assertNotEqual(_patterns(candidate), ("B?C",))

    def test_both_existing_answers_are_named_as_absorbed(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(WELD), 0, 2)
        self.assertEqual(candidate.absorbed, ("AB", "CD"))

    def test_a_single_letter_arm_is_not_absorbed(self) -> None:
        # A lone letter is no entry (cw_grid.MIN_RUN), so welding one costs
        # nothing -- reporting it as absorbed would invent a loss.
        candidate = _at(cw_gaps.analyze_grid(("A.CD",)), 0, 1)
        self.assertEqual(
            (_patterns(candidate), candidate.absorbed), (("A?CD",), ("CD",))
        )

    def test_a_welded_down_run_names_its_absorbed_answer(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(("A", "B", ".", "C", "D")), 2, 0)
        self.assertEqual(
            (_patterns(candidate), candidate.absorbed), (("AB?CD",), ("AB", "CD"))
        )


class TestBothAxes(unittest.TestCase):
    """A gap with neighbors on both axes demands two runs of one letter."""

    def test_two_demands_across_then_down(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(BOTH_AXES), 1, 1)
        self.assertEqual(_patterns(candidate), ("E?", "A?"))

    def test_the_two_demands_name_their_own_directions(self) -> None:
        candidate = _at(cw_gaps.analyze_grid(BOTH_AXES), 1, 1)
        self.assertEqual(
            tuple(demand.direction for demand in candidate.demands),
            (cw_grid.ACROSS, cw_grid.DOWN),
        )

    def test_a_gap_with_one_neighbor_has_one_demand(self) -> None:
        # (0, 3) closes HAY across and has nothing below it, so the DOWN axis
        # produces no run at all and must not appear as a one-letter demand.
        candidate = _at(cw_gaps.analyze_grid(BOTH_AXES), 0, 3)
        self.assertEqual(_patterns(candidate), ("HAY?",))


class TestOrphans(unittest.TestCase):
    """A gap that would create no run at all is excluded, and is counted."""

    def test_a_cell_with_no_letter_neighbor_is_not_a_candidate(self) -> None:
        self.assertEqual(cw_gaps.analyze_grid(ALL_BLOCKED).candidates, ())

    def test_every_such_cell_is_reported_as_an_orphan(self) -> None:
        self.assertEqual(
            cw_gaps.analyze_grid(ALL_BLOCKED).orphans,
            ((0, 0), (0, 1), (1, 0), (1, 1)),
        )

    def test_an_orphan_letter_would_belong_to_no_entry(self) -> None:
        # The reason the exclusion exists: a letter here would form no run, so
        # it answers no demand on the bank and would be a stray, which
        # `cw_place.grid_violations` is documented as silent about.
        self.assertEqual(cw_gaps.analyze_grid(("..", ".A")).orphans, ((0, 0),))


class TestMaskedCells(unittest.TestCase):
    """A masked cell is a third thing a blocked cell can be, and is counted as one.

    `gaps` exists to advise which letter to buy for a blocked cell. A cell the
    operator drew out of the grid is one they will never fill, so advising about
    it would be advice they must throw away -- and silently dropping it would
    leave the report's own arithmetic short.
    """

    def test_a_masked_cell_is_no_candidate(self) -> None:
        analysis = cw_gaps.analyze_grid(("AB", ".C"), frozenset({(1, 0)}))
        self.assertEqual(analysis.candidates, ())

    def test_a_masked_cell_is_no_orphan_either(self) -> None:
        # Not quietly reclassified: an orphan is a cell a letter COULD take and
        # should not, which is a different sentence from one that may never.
        analysis = cw_gaps.analyze_grid(("..", ".A"), frozenset({(0, 0)}))
        self.assertNotIn((0, 0), analysis.orphans)

    def test_masked_cells_come_back_row_major(self) -> None:
        # Read off the grid, never off the set: a frozenset's order is
        # hash-seeded, and this tuple reaches a report.
        analysis = cw_gaps.analyze_grid(
            ("...", "..."), frozenset({(1, 2), (0, 0), (0, 2)})
        )
        self.assertEqual(analysis.masked, ((0, 0), (0, 2), (1, 2)))

    def test_an_unmasked_grid_reports_no_masked_cells(self) -> None:
        self.assertEqual(cw_gaps.analyze_grid(("AB", ".C")).masked, ())


class TestAccounting(unittest.TestCase):
    """Every blocked cell is either a candidate or an orphan, and none is both."""

    def test_the_two_counts_add_up_to_the_blocked_cells(self) -> None:
        analysis = cw_gaps.analyze_grid(BOTH_AXES)
        blocked = sum(row.count(cw_grid.BLOCK) for row in BOTH_AXES)
        self.assertEqual(len(analysis.candidates) + len(analysis.orphans), blocked)

    def test_the_three_counts_add_up_under_a_mask(self) -> None:
        # The partition stays total: a reader who trusts the report's arithmetic
        # must still be able to add the tiers up to the blocked count.
        # (0, 3) is a genuinely BLOCKED cell of this grid, so it really does
        # move from one tier to another rather than never having been in one.
        masked = frozenset({(0, 3)})
        analysis = cw_gaps.analyze_grid(BOTH_AXES, masked)
        self.assertEqual(analysis.masked, ((0, 3),))
        blocked = sum(row.count(cw_grid.BLOCK) for row in BOTH_AXES)
        self.assertEqual(
            len(analysis.candidates) + len(analysis.orphans) + len(analysis.masked),
            blocked,
        )

    def test_a_grid_with_no_blocked_cell_yields_nothing(self) -> None:
        analysis = cw_gaps.analyze_grid(("AB", "CD"))
        self.assertEqual((analysis.candidates, analysis.orphans), ((), ()))

    def test_candidates_come_back_row_major(self) -> None:
        # Deterministic order is part of the contract, and row-major is the
        # order a reader scanning the grid expects.
        analysis = cw_gaps.analyze_grid(BOTH_AXES)
        cells = tuple((c.row, c.col) for c in analysis.candidates)
        self.assertEqual(cells, tuple(sorted(cells)))


if __name__ == "__main__":
    unittest.main()
