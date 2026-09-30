"""Property suite: the gap analysis, checked against what actually happens.

`analyze_grid` reads a grid and PREDICTS what a letter in each blocked cell
would do to it. That is exactly the shape a property test can hold to account,
because the prediction is checkable: write the letter in and ask `cw_grid`,
which is the authority on what a run is, what really happened.

So the headline properties here never restate the analysis's own method. They
fill the cell, re-derive the grid's runs from scratch, and assert the
prediction matched -- the demanded pattern IS a run at the coordinates it
named, the number of demands IS the number of runs that now contain the cell,
and the absorbed answers ARE the old runs the new one swallowed. A neighbors-
only reader, a transposed axis, or a demand that forgot to weld all fail
against a grid nobody had to think of first.

`test_fuzz_analyze_grid` and `test_fuzz_resolve_all` are the property tests
paired with the `# fuzz-target` markers on `cw_gaps.analyze_grid` and
`cw_gaps.resolve_all`.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
its own path.
"""

from __future__ import annotations

import sys
import unittest
from collections.abc import Sequence
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_gaps  # noqa: E402 - import follows the sys.path bootstrap above
import cw_grid  # noqa: E402 - same bootstrap

# A REGISTERED profile, loaded at import and before any class body, never an
# `@settings` decorator -- a `@given` test snapshots its settings when it is
# DECORATED, and a decorator would pin the property's settings where no
# campaign runner could re-stamp them: Hypothesis refuses a second settings
# object on a function that already carries one.
# Its own profile NAME, distinct from every other property module's here, so no
# import order can decide what this module's tests had already snapshotted.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_gaps_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_gaps_properties")

#: A two-letter alphabet plus the block. Deliberately tiny: short runs and
#: repeated texts are what make WELDS and shared patterns common in the drawn
#: grids, and those are the cases the analysis is easiest to get wrong on.
#: Over twenty-six letters most drawn grids would be sparse noise.
_CELL_ALPHABET = "AB" + cw_grid.BLOCK

#: The letter written into a gap when a property checks what really happens.
#: Outside `_CELL_ALPHABET` so a filled cell is identifiable in the result,
#: which is what lets a failure be read rather than merely reported.
_PROBE = "Z"

_MIN_SIDE = 1
_MAX_SIDE = 5

#: Two-letter words over the same alphabet the grids use, plus the probe, so a
#: drawn vocabulary has a real chance of matching a drawn grid's demands.
_VOCABULARY = st.frozensets(
    st.text(
        alphabet=_CELL_ALPHABET.replace(cw_grid.BLOCK, "") + _PROBE,
        min_size=2,
        max_size=3,
    ),
    max_size=6,
)


@st.composite
def _grids(draw: st.DrawFn) -> tuple[str, ...]:
    """A small rectangular grid of letters and blocks.

    The two sides are drawn independently so NON-SQUARE grids are in range: a
    transposed arm walk passes every square grid and fails here.
    """
    height = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    width = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    return tuple(
        "".join(draw(st.sampled_from(_CELL_ALPHABET)) for _ in range(width))
        for _ in range(height)
    )


def _with_letter(
    rows: Sequence[str], row: int, col: int, letter: str
) -> tuple[str, ...]:
    """`rows` with one cell replaced -- the fill the analysis is predicting."""
    return tuple(
        line if index != row else line[:col] + letter + line[col + 1 :]
        for index, line in enumerate(rows)
    )


def _runs_covering(rows: Sequence[str], cell: tuple[int, int]) -> list[cw_grid.Run]:
    """Every run of `rows` that occupies `cell`, straight from the authority."""
    return [run for run in cw_grid.runs_from_rows(rows) if cell in run.cells]


class TestPartition(unittest.TestCase):
    """Candidates and orphans account for every blocked cell, exactly once."""

    @given(_grids())
    def test_fuzz_analyze_grid(self, rows: tuple[str, ...]) -> None:
        """Every blocked cell becomes exactly one of the two, and nothing else does.

        The report's headline arithmetic rests on this, so it is asserted over
        drawn grids rather than trusted: the two counts add up to the blocked
        cells, and no cell appears in both halves.
        """
        analysis = cw_gaps.analyze_grid(rows)
        blocked = sum(line.count(cw_grid.BLOCK) for line in rows)
        candidate_cells = {(c.row, c.col) for c in analysis.candidates}
        orphan_cells = set(analysis.orphans)
        self.assertEqual(len(candidate_cells) + len(orphan_cells), blocked)
        self.assertEqual(candidate_cells & orphan_cells, set())

    @given(_grids())
    def test_every_candidate_names_a_blocked_cell(self, rows: tuple[str, ...]) -> None:
        analysis = cw_gaps.analyze_grid(rows)
        for candidate in analysis.candidates:
            self.assertEqual(rows[candidate.row][candidate.col], cw_grid.BLOCK)


class TestThePredictionHolds(unittest.TestCase):
    """Fill the cell, ask cw_grid what happened, and compare."""

    @given(_grids())
    def test_each_demand_is_a_real_run_at_its_own_coordinates(
        self, rows: tuple[str, ...]
    ) -> None:
        for candidate in cw_gaps.analyze_grid(rows).candidates:
            filled = _with_letter(rows, candidate.row, candidate.col, _PROBE)
            actual = {
                (run.direction, run.row, run.col): run.text
                for run in cw_grid.runs_from_rows(filled)
            }
            for demand in candidate.demands:
                key = (demand.direction, demand.row, demand.col)
                self.assertIn(key, actual)
                self.assertEqual(
                    actual[key], demand.pattern.replace(cw_gaps.UNKNOWN, _PROBE)
                )

    @given(_grids())
    def test_no_axis_is_missed_and_none_is_invented(
        self, rows: tuple[str, ...]
    ) -> None:
        # The count of runs the filled cell ends up inside is the count of
        # demands it should have had. A transposed or forgotten axis fails
        # here even when every demand it DID report is correct.
        for candidate in cw_gaps.analyze_grid(rows).candidates:
            cell = (candidate.row, candidate.col)
            filled = _with_letter(rows, *cell, _PROBE)
            self.assertEqual(len(_runs_covering(filled, cell)), len(candidate.demands))

    @given(_grids())
    def test_an_orphan_would_really_join_nothing(self, rows: tuple[str, ...]) -> None:
        for cell in cw_gaps.analyze_grid(rows).orphans:
            filled = _with_letter(rows, *cell, _PROBE)
            self.assertEqual(_runs_covering(filled, cell), [])

    @given(_grids())
    def test_the_absorbed_answers_are_the_runs_the_new_one_swallows(
        self, rows: tuple[str, ...]
    ) -> None:
        # Re-derived from cw_grid rather than from the analysis: the old runs
        # whose cells the new run entirely covers ARE what the fill retires,
        # and a demand that under-reported them would leave the operator
        # unaware of what the fill costs.
        before = cw_grid.runs_from_rows(rows)
        for candidate in cw_gaps.analyze_grid(rows).candidates:
            cell = (candidate.row, candidate.col)
            filled = _with_letter(rows, *cell, _PROBE)
            for demand in candidate.demands:
                new_run = next(
                    run
                    for run in _runs_covering(filled, cell)
                    if run.direction == demand.direction
                )
                covered = tuple(
                    run.text
                    for run in before
                    if run.direction == demand.direction
                    and set(run.cells) <= set(new_run.cells)
                )
                self.assertEqual(covered, demand.absorbed)


class TestResolutionIsSound(unittest.TestCase):
    """Any letter the resolver offers really does leave a legal grid."""

    @given(_grids(), _VOCABULARY)
    # A regression seed, carried as an `@example` rather than left in a corpus
    # database: the suite runs DERANDOMIZED, which Hypothesis forbids alongside
    # a database, so a corpus seed would guard only exploratory runs. Row 4 is
    # load-bearing: it is the second AB, and without it the grid is legal and
    # the property holds.
    @example(("AAAA", "AA.A", "AAAA", "AB..", "AB.A"), frozenset({"AB", "ABB"}))
    def test_fuzz_resolve_all(
        self, rows: tuple[str, ...], vocabulary: frozenset[str]
    ) -> None:
        """Every offered fill spells vocabulary answers, all of them distinct.

        The tool's one rule, checked on the grid the fill would actually
        produce: each run through the filled cell is an answer the operator
        holds, no two of them are the same answer, and none of them repeats an
        answer standing elsewhere on the grid. A resolver that ignored
        distinctness passes every count-shaped test and fails here.
        """
        search = cw_gaps.search_gaps(rows, vocabulary)
        for resolution in search.resolutions:
            candidate = resolution.candidate
            cell = (candidate.row, candidate.col)
            for fill in resolution.fills:
                filled = _with_letter(rows, *cell, fill.letter)
                through = _runs_covering(filled, cell)
                texts = [run.text for run in through]
                self.assertEqual(sorted(texts), sorted(fill.words))
                self.assertEqual(len(set(texts)), len(texts))
                elsewhere = {
                    run.text
                    for run in cw_grid.runs_from_rows(filled)
                    if run not in through
                }
                self.assertEqual(set(texts) & elsewhere, set())
                for text in texts:
                    self.assertIn(text, vocabulary)

    @given(_grids(), _VOCABULARY)
    def test_an_unmatched_pattern_really_has_no_answer(
        self, rows: tuple[str, ...], vocabulary: frozenset[str]
    ) -> None:
        # The other direction: a pattern reported unmet must genuinely have no
        # word the operator could use, or the report is sending them to invent
        # something they already own.
        #
        # What "could use" means is re-derived from the FILLED grid, never
        # from the resolver's own availability rule. Recomputing that rule
        # here made this test agree with the subject even while the subject
        # was wrong: it read the grid's answers as a SET, so a fill that
        # absorbed one copy of a doubled answer looked free to re-spell it,
        # and the mirror said so too. `cw_grid` is the authority on what is
        # still standing, so it is the one asked.
        search = cw_gaps.search_gaps(rows, vocabulary)
        for resolution in search.resolutions:
            candidate = resolution.candidate
            cell = (candidate.row, candidate.col)
            # Which runs survive a fill is decided by WHERE the letter lands,
            # not by which letter it is, so this is derived once per candidate.
            filled = _with_letter(rows, *cell, _PROBE)
            through = _runs_covering(filled, cell)
            standing = {
                run.text for run in cw_grid.runs_from_rows(filled) if run not in through
            }
            for pattern in resolution.unmatched:
                for letter in "ABZ":
                    self.assertNotIn(
                        pattern.replace(cw_gaps.UNKNOWN, letter),
                        vocabulary - standing,
                    )


if __name__ == "__main__":
    unittest.main()
