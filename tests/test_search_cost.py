"""Tests for what one walk node reads: the work it does, not the grid it reaches.

A cost regression is invisible to a correctness suite: a walk doing needless work
reaches exactly the same grids on the same nodes, only slower. Measured on this
walk: when every node on a detour built every crossing the board offered, and every
step check scanned the whole bank for an answer that could complete a run, a first
11x11 or 13x13 grid took minutes rather than seconds; when each look-ahead board
aligned every answer on every letter, read the board cell by cell for each
alignment and derived its runs twice per tried step, an 11x11 window took about 76
seconds rather than 20. No grid, sample or node count differs between the two.

So this suite pins the WORK, deterministically -- never a clock. Each test runs the
bounded-detour fixture of `test_search_interlock.py` and asserts two things: the
walk reached the same grid on the same node, and no node read more than its
question needs. The equivalence that lets the cheaper reads stand in for the
exhaustive ones is `test_reach_properties.py`.
"""

import unittest
from collections import Counter
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from unittest import mock

import cw_bank
import cw_config
import cw_grid
import cw_order
import cw_place
import cw_reach
import cw_search

# The module, not the class: a TestCase bound in this namespace would run again
# here. Its fixture is the one whose walk opens detours on nearly every step.
from tests import test_search_interlock as _interlock
from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import still as _still

_FIXTURE = _interlock.TestADetourIsBounded


def _search() -> cw_search.SearchOutcome:
    """The bounded-detour fixture's search, exactly as its own test runs it."""
    return cw_search.search(
        _bank(list(_FIXTURE.ANSWERS)),
        _config(
            rows=7,
            cols=7,
            seed=12,
            min_blocked=0.0,
            max_blocked=40.0,
            min_themes=0,
            max_steps=_FIXTURE.STEPS,
        ),
        clock=_still,
    )


def _broken(rows: Sequence[str]) -> bool:
    """Whether `rows` holds a break the walk made (no --source here)."""
    allowed = frozenset(_FIXTURE.ANSWERS)
    return bool(cw_reach.walk_breaks(rows, allowed, ()))


class TestADetourNodeBuildsOnlyItsRepairs(unittest.TestCase):
    """A board holding a walk break offers only placements over it, so it builds only those."""

    def test_no_board_holding_a_walk_break_enumerates_every_crossing(self) -> None:
        # Every crossing on the board is the whole-board question; a detour node
        # keeps only the placements laid over its break, so building the rest
        # was the cost -- on a 13x13 of a 1,758-answer bank, 62,600 fit checks a
        # node to keep about 150. The broken-board count proves the walk really
        # stood on such boards, so the empty list below is not vacuous.
        enumerated_on_broken: list[tuple[str, ...]] = []
        broken_nodes: list[tuple[str, ...]] = []
        crossings = cw_place.crossing_candidates
        ordered = cw_order.ordered_candidates

        def spy_crossings(
            grid: cw_grid.Grid,
            answers: Sequence[str],
            masked: AbstractSet[tuple[int, int]] = frozenset(),
        ) -> list[cw_place.Placement]:
            if _broken(grid.to_rows()):
                enumerated_on_broken.append(grid.to_rows())
            return crossings(grid, answers, masked)

        def spy_ordered(
            grid: cw_grid.Grid, bank: cw_bank.Bank, config: cw_config.FillConfig
        ) -> list[cw_place.Placement]:
            if _broken(grid.to_rows()):
                broken_nodes.append(grid.to_rows())
            return ordered(grid, bank, config)

        with (
            mock.patch.object(cw_place, "crossing_candidates", spy_crossings),
            mock.patch.object(cw_order, "ordered_candidates", spy_ordered),
        ):
            outcome = _search()
        self.assertEqual((outcome.rows, outcome.steps), (_FIXTURE.GRID, _FIXTURE.NODE))
        self.assertTrue(broken_nodes, "the fixture's walk stood on no broken board")
        self.assertEqual(enumerated_on_broken, [])


class TestAStepCheckReadsOnlyTheAnswersHoldingTheBreak(unittest.TestCase):
    """A step check asks about a broken run only answers that could be laid over it."""

    def test_completable_is_handed_only_longer_answers_holding_the_run(self) -> None:
        # An answer that does not hold the run's letters, or is no longer than
        # it, can never be laid over it, so handing it over is pure cost: the
        # whole bank, on every tried step that breaks the rule.
        wasted: list[tuple[str, str]] = []
        calls: list[str] = []
        completable = cw_reach.completable

        def spy(rows: Sequence[str], run: cw_grid.Run, answers: Sequence[str]) -> bool:
            calls.append(run.text)
            wasted.extend(
                (run.text, answer)
                for answer in answers
                if run.text not in answer or len(answer) <= len(run.text)
            )
            return completable(rows, run, answers)

        with mock.patch.object(cw_reach, "completable", spy):
            outcome = _search()
        self.assertEqual((outcome.rows, outcome.steps), (_FIXTURE.GRID, _FIXTURE.NODE))
        self.assertTrue(calls, "no step in the fixture's walk broke the rule")
        self.assertEqual(wasted, [])


class TestAStepCheckDerivesTheBoardsRunsOnce(unittest.TestCase):
    """A step check reads the board's runs once, for its pins, its breaks and its entries."""

    def test_no_step_check_derives_the_runs_twice(self) -> None:
        # A step that broke the rule derived the runs a second time, for the
        # answers already on the board, and a pinned board a third, for its
        # pins. The step check is the walk's most frequent question -- about
        # 455,000 tried steps in an 11x11 window, nearly all of them refused --
        # so the runs are derived once and every half of the check reads them.
        per_check: list[int] = []
        derived = [0]
        runs_from_rows = cw_grid.runs_from_rows
        step_allowed = cw_reach.step_allowed

        def spy_runs(rows: Sequence[str]) -> tuple[cw_grid.Run, ...]:
            derived[0] += 1
            return runs_from_rows(rows)

        def spy_step(
            rows: Sequence[str],
            allowed: AbstractSet[str],
            pinned: tuple[cw_grid.Run, ...],
            holders: Mapping[str, Sequence[str]],
        ) -> bool:
            before = derived[0]
            verdict = step_allowed(rows, allowed, pinned, holders)
            per_check.append(derived[0] - before)
            return verdict

        with (
            mock.patch.object(cw_grid, "runs_from_rows", spy_runs),
            mock.patch.object(cw_reach, "step_allowed", spy_step),
        ):
            outcome = _search()
        self.assertEqual((outcome.rows, outcome.steps), (_FIXTURE.GRID, _FIXTURE.NODE))
        self.assertTrue(per_check, "the fixture's walk tried no step")
        self.assertEqual(max(per_check), 1)


class TestAWholeBoardEnumerationReadsOnlyWhatCanFit(unittest.TestCase):
    """Every crossing on a whole board is built from its letters, not from every answer."""

    def test_no_answer_is_aligned_on_a_letter_it_does_not_hold(self) -> None:
        # Every filled cell asked every unused answer where it could cross, so a
        # nearly full 11x11 board aligned about 150,000 answer-and-cell pairs to
        # find the few that hold the cell's letter at all. Only an answer holding
        # the letter has an alignment there.
        aligned: list[tuple[str, str]] = []
        alignments = cw_place._alignments

        def spy(row: int, col: int, letter: str, answer: str) -> object:
            aligned.append((letter, answer))
            return alignments(row, col, letter, answer)

        with mock.patch.object(cw_place, "_alignments", spy):
            outcome = _search()
        self.assertEqual((outcome.rows, outcome.steps), (_FIXTURE.GRID, _FIXTURE.NODE))
        self.assertTrue(aligned, "the fixture's walk aligned no answer")
        self.assertEqual([pair for pair in aligned if pair[0] not in pair[1]], [])

    def test_no_enumeration_reads_a_cell_more_than_once(self) -> None:
        # Each alignment was fit-checked by reading its cells off the board one
        # at a time, so a cell was read once for every alignment crossing it:
        # about 14 million fit checks in one 11x11 window. The board's letters
        # are the same for the whole enumeration, so it reads each cell once.
        overreads: list[tuple[int, int]] = []
        enumerations = [0]
        reads = [0]
        letter = cw_grid.Grid.letter
        crossings = cw_place.crossing_candidates

        def spy_letter(grid: cw_grid.Grid, row: int, col: int) -> str | None:
            reads[0] += 1
            return letter(grid, row, col)

        def spy_crossings(
            grid: cw_grid.Grid,
            answers: Sequence[str],
            masked: AbstractSet[tuple[int, int]] = frozenset(),
        ) -> list[cw_place.Placement]:
            enumerations[0] += 1
            before = reads[0]
            found = crossings(grid, answers, masked)
            if reads[0] - before > grid.height * grid.width:
                overreads.append((reads[0] - before, grid.height * grid.width))
            return found

        with (
            mock.patch.object(cw_grid.Grid, "letter", spy_letter),
            mock.patch.object(cw_place, "crossing_candidates", spy_crossings),
        ):
            outcome = _search()
        self.assertEqual((outcome.rows, outcome.steps), (_FIXTURE.GRID, _FIXTURE.NODE))
        self.assertTrue(enumerations[0], "the fixture's walk enumerated no whole board")
        self.assertEqual(overreads, [])


class TestALineIsScannedOncePerSearch(unittest.TestCase):
    """A line's runs are scanned once for each position and contents it is met with."""

    def test_no_line_is_scanned_twice(self) -> None:
        # Every step check scanned every line of the board afresh, though a
        # placement changes only the lines it lies in and crosses. An 11x11
        # window met 19,339 distinct lines in about 10 million line reads, so a
        # line's runs are remembered by the line itself, where it lies included.
        scanned: list[tuple[int, int, str, str]] = []
        runs_in_line = cw_grid._runs_in_line

        def spy(
            start_row: int, start_col: int, direction: str, line: str
        ) -> list[cw_grid.Run]:
            scanned.append((start_row, start_col, direction, line))
            return runs_in_line(start_row, start_col, direction, line)

        with mock.patch.object(cw_grid, "_runs_in_line", spy):
            outcome = _search()
        self.assertEqual((outcome.rows, outcome.steps), (_FIXTURE.GRID, _FIXTURE.NODE))
        repeated = [line for line, seen in Counter(scanned).items() if seen > 1]
        self.assertEqual(repeated, [])


def _indexes_built(
    answers: list[str], rows: int, cols: int
) -> list[Mapping[str, tuple[str, ...]]]:
    """Every fragment index a one-node search over `answers` builds on a `rows` x `cols`."""
    indexes: list[Mapping[str, tuple[str, ...]]] = []
    build = cw_reach.holders_by_fragment

    def spy(given: Sequence[str], **bound: int) -> Mapping[str, tuple[str, ...]]:
        index = build(given, **bound)
        indexes.append(index)
        return index

    with mock.patch.object(cw_reach, "holders_by_fragment", spy):
        cw_search.search(
            _bank(answers),
            _config(rows=rows, cols=cols, min_themes=0, max_steps=1),
            clock=_still,
        )
    return indexes


class TestTheFragmentIndexHoldsOnlyAnswersThatFit(unittest.TestCase):
    """The index a search builds before its first node leaves out what no line holds."""

    def test_an_answer_longer_than_every_line_is_not_indexed(self) -> None:
        # The index is built before the first node and the budgets are read per
        # node, so nothing bounded what one answer cost there: every substring
        # of it, about L**3 / 6 characters. A 30-letter answer can never lie on
        # a 7x7, so leaving it out changes no grid.
        long = "AB" * 15
        indexes: list[Mapping[str, tuple[str, ...]]] = []
        build = cw_reach.holders_by_fragment

        def spy(answers: Sequence[str], **bound: int) -> Mapping[str, tuple[str, ...]]:
            index = build(answers, **bound)
            indexes.append(index)
            return index

        with mock.patch.object(cw_reach, "holders_by_fragment", spy):
            cw_search.search(
                _bank(["CAT", "ACT", long]),
                _config(rows=7, cols=7, min_themes=0, max_steps=1),
                clock=_still,
            )
        self.assertEqual(len(indexes), 1)
        self.assertFalse(
            any(long in held for held in indexes[0].values()),
            "the 30-letter answer was indexed",
        )

    def test_the_index_holds_answers_up_to_the_longer_side_and_no_longer(
        self,
    ) -> None:
        # One that fits only the LONGER side of a non-square grid can be laid,
        # and leaving it out would prune legal paths -- so the bound is that
        # side, either way round, which a square grid cannot tell apart.
        fits, too_long = "ABCDEFG", "ABCDEFGH"
        for rows, cols in ((5, 7), (7, 5)):
            with self.subTest(rows=rows, cols=cols):
                indexes = _indexes_built(["CAT", "ACT", fits, too_long], rows, cols)
                self.assertEqual(len(indexes), 1)
                held = {answer for found in indexes[0].values() for answer in found}
                self.assertIn(fits, held, "an answer the longer side holds is left out")
                self.assertNotIn(too_long, held, "an answer no line holds is indexed")
