"""Grouped suite: the cheap reads a walk node makes equal the full ones they replace.

**Why an equivalence, and why it is the density guarantee.** A walk node on a
broken board builds only the placements laid over a break, and a step check asks
only the answers holding a run's letters (`test_search_cost.py`). The walk sorts
its candidates on a total key, so it takes the steps the straightforward reads
would take, in the same order, exactly when each node offers the same set of
placements and each step gets the same verdict. That is what these properties
assert (over generated boards rather than examples), so the grids and their
density are the ones the straightforward reads would give.

The oracles are those straightforward reads, written out from public pieces:
`cw_place.crossing_candidates` filtered by `cw_reach.covers`, and
`cw_reach.completable` over `cw_reach.unused_answers`. The look-ahead window's reads
have full oracles of their own: every filled cell asked every answer, each
alignment fit-checked on the board (`_scanned_crossings`); every line scanned afresh
(`_scanned_runs`); and the pins and the breaks read off the rows separately. The
first two are compared exactly, order included, because `crossing_candidates` and
`runs_from_rows` both document their order as a contract.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`; the
bootstrap below names both, as the project's other property suites do.
"""

import re
import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_grid  # noqa: E402 - import follows the sys.path bootstrap above
import cw_place  # noqa: E402 - same bootstrap
import cw_reach  # noqa: E402 - same bootstrap
from tests.search_fixtures import bank as _bank  # noqa: E402 - same bootstrap
from tests.search_fixtures import grid as _grid  # noqa: E402 - same bootstrap

# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_reach_properties",
    derandomize=True,
    deadline=None,
    max_examples=300,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_reach_properties")

#: Three letters: few enough that answers and runs share letters, so completions
#: and crossings are common rather than rare.
_LETTERS = "ABC"

#: A board's cells: the letters and two blocks, so runs stay short and plentiful.
_CELLS = _LETTERS + cw_grid.BLOCK * 2

#: Side bounds of a board, drawn independently so non-square is in range.
_MIN_SIDE = 2
_MAX_SIDE = 6

#: Answer length bounds: a run of two cells up to one longer than the widest board,
#: so an answer can fail to fit as well as fit.
_MIN_ANSWER = cw_grid.MIN_RUN
_MAX_ANSWER = _MAX_SIDE + 1

#: How many answers a drawn bank holds beyond those taken from the board.
_MAX_DRAWN_ANSWERS = 8

#: One drawn case: the board's rows and its bank's answers, in bank order.
Board = tuple[tuple[str, ...], tuple[str, ...]]


def _word_of(draw: st.DrawFn, alphabet: str, length: int) -> str:
    """One string of `length` cells drawn from `alphabet`."""
    return "".join(
        draw(st.lists(st.sampled_from(alphabet), min_size=length, max_size=length))
    )


@st.composite
def _boards(draw: st.DrawFn) -> Board:
    """A random board, and a bank holding some of its runs and some extensions of them.

    Runs taken from the board make some of them answers, so a board can obey the
    rule; a run grown by a letter at either end makes a completion possible; the
    drawn words make the rest of the bank, which mostly completes nothing.
    """
    height = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    width = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    rows = tuple(_word_of(draw, _CELLS, width) for _ in range(height))
    texts = sorted({run.text for run in cw_grid.runs_from_rows(rows)})
    answers: list[str] = []
    for text in texts:
        if draw(st.booleans()):
            answers.append(text)
        if draw(st.booleans()):
            letter = draw(st.sampled_from(_LETTERS))
            answers.append(draw(st.sampled_from((text + letter, letter + text))))
    words = st.text(_LETTERS, min_size=_MIN_ANSWER, max_size=_MAX_ANSWER)
    answers += draw(st.lists(words, max_size=_MAX_DRAWN_ANSWERS))
    return rows, tuple(dict.fromkeys(answers))


#: One drawn case with pins: the board's rows, its bank's answers, and its pins.
PinnedBoard = tuple[tuple[str, ...], tuple[str, ...], tuple[cw_grid.Run, ...]]

#: A pin at the origin, for the examples: held by `JANE.`, swallowed by `JANET`.
_JANE = cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="JANE")

#: How many pins a drawn case carries at most.
_MAX_PINS = 3


@st.composite
def _pinned_boards(draw: st.DrawFn) -> PinnedBoard:
    """A drawn board and bank, pinned with some of its runs and some it has outgrown.

    An outgrown pin is one of the board's runs cut short by its last letter: the
    run that swallowed it is still there, so the pin fails exactly as JANE does
    once JANET is laid.
    """
    rows, answers = draw(_boards())
    runs = cw_grid.runs_from_rows(rows)
    outgrown = [
        cw_grid.Run(
            row=run.row, col=run.col, direction=run.direction, text=run.text[:-1]
        )
        for run in runs
        if len(run.text) > cw_grid.MIN_RUN
    ]
    pins = (*runs, *outgrown)
    if not pins:
        return rows, answers, ()
    return (
        rows,
        answers,
        tuple(draw(st.lists(st.sampled_from(pins), max_size=_MAX_PINS))),
    )


def _cells(placement: cw_place.Placement) -> tuple[tuple[int, int], ...]:
    """Every cell `placement` would occupy."""
    run = cw_grid.Run(
        row=placement.row,
        col=placement.col,
        direction=placement.direction,
        text=placement.answer,
    )
    return run.cells


#: A stretch of two or more filled cells along one line: a run, for `_scanned_runs`.
_STRETCH = re.compile(rf"[^{re.escape(cw_grid.BLOCK)}]{{{cw_grid.MIN_RUN},}}")


def _scanned_crossings(
    grid: cw_grid.Grid, answers: tuple[str, ...]
) -> list[cw_place.Placement]:
    """Every crossing, as the old enumeration built it: each cell asked every answer.

    Cells row-major, answers in bank order, offsets ascending, ACROSS before DOWN,
    each placement kept at its first appearance and judged by `cw_place.fits`.
    """
    found: list[cw_place.Placement] = []
    for row in range(grid.height):
        for col in range(grid.width):
            letter = grid.letter(row, col)
            for answer in answers:
                for offset, answer_letter in enumerate(answer):
                    if letter is None or answer_letter != letter:
                        continue
                    for placement in (
                        cw_place.Placement(answer, row, col - offset, cw_grid.ACROSS),
                        cw_place.Placement(answer, row - offset, col, cw_grid.DOWN),
                    ):
                        if placement not in found and cw_place.fits(grid, placement):
                            found.append(placement)
    return found


def _scanned_runs(rows: tuple[str, ...]) -> tuple[cw_grid.Run, ...]:
    """Every run, as a fresh scan finds it: ACROSS row-major, then DOWN column-major."""
    columns = ["".join(column) for column in zip(*rows, strict=True)]
    return tuple(
        cw_grid.Run(
            row=index if direction == cw_grid.ACROSS else match.start(),
            col=match.start() if direction == cw_grid.ACROSS else index,
            direction=direction,
            text=match.group(),
        )
        for direction, lines in ((cw_grid.ACROSS, rows), (cw_grid.DOWN, columns))
        for index, line in enumerate(lines)
        for match in _STRETCH.finditer(line)
    )


class TestPlacementsOverAreTheCrossingsLaidOverARun(unittest.TestCase):
    """Building the placements over some runs gives exactly the crossings that cover one."""

    @given(_boards())
    @example(((".ALT.",), ("SALT", "BOLT", "LT")))
    def test_the_set_matches_the_filtered_crossings_and_repeats_nothing(
        self, board: Board
    ) -> None:
        rows, answers = board
        grid = _grid(rows)
        runs = cw_grid.runs_from_rows(rows)
        built = cw_reach.placements_over(grid, runs, answers)
        filtered = {
            placement
            for placement in cw_place.crossing_candidates(grid, answers)
            if any(cw_reach.covers(run, _cells(placement)) for run in runs)
        }
        self.assertEqual(len(built), len(set(built)))
        self.assertEqual(set(built), filtered)


class TestStepAllowedMatchesTheUnusedScan(unittest.TestCase):
    """The indexed step check gives the verdict the scan over unused answers gave."""

    @given(_boards())
    # One break WILTS completes, one it cannot (the X), and one only an answer
    # already on the board holds: each verdict the index must reproduce.
    @example((("W.LTS",), ("WILTS",)))
    @example((("X.LTS",), ("WILTS",)))
    @example((("W.LTS", ".....", "WILTS"), ("WILTS",)))
    def test_the_verdict_matches(self, board: Board) -> None:
        rows, answers = board
        allowed = frozenset(answers)
        unused = cw_reach.unused_answers(rows, _bank(list(answers)))
        scanned = all(
            cw_reach.completable(rows, run, unused)
            for run, _ in cw_place.rule_breaks(rows, allowed)
        )
        # Indexed as a search on this board indexes: only the answers its
        # longest line can hold, which leaves every verdict as it was.
        longest = max(len(rows), len(rows[0]))
        indexed = cw_reach.step_allowed(
            rows, allowed, (), cw_reach.holders_by_fragment(answers, longest=longest)
        )
        self.assertEqual(indexed, scanned)


class TestStepAllowedWithPinsMatchesTheSeparateReads(unittest.TestCase):
    """A step check reading the runs once gives the verdict its separate reads gave."""

    @given(_pinned_boards())
    # A pin the board still holds, and one a longer run has swallowed.
    @example((("JANE.",), ("JANE",), (_JANE,)))
    @example((("JANET",), ("JANE", "JANET"), (_JANE,)))
    def test_the_verdict_matches(self, board: PinnedBoard) -> None:
        rows, answers, pinned = board
        runs = cw_grid.runs_from_rows(rows)
        allowed = frozenset(answers)
        unused = cw_reach.unused_answers(rows, _bank(list(answers)))
        separate = all(run in runs for run in pinned) and all(
            cw_reach.completable(rows, run, unused)
            for run, _ in cw_place.rule_breaks(rows, allowed)
        )
        longest = max(len(rows), len(rows[0]))
        once = cw_reach.step_allowed(
            rows,
            allowed,
            pinned,
            cw_reach.holders_by_fragment(answers, longest=longest),
        )
        self.assertEqual(once, separate)


class TestCrossingCandidatesMatchTheCellScan(unittest.TestCase):
    """Built from the letters each answer holds, the crossings are the cell scan's, in order."""

    @given(_boards())
    # CARAT holds A twice: two alignments on each A, and one reachable from both.
    @example((("CAT..", ".....", "..A.."), ("CARAT", "AT", "TACT")))
    def test_the_list_matches_exactly(self, board: Board) -> None:
        rows, answers = board
        grid = _grid(rows)
        self.assertEqual(
            cw_place.crossing_candidates(grid, answers),
            _scanned_crossings(grid, answers),
        )


class TestRunsMatchAFreshScan(unittest.TestCase):
    """Runs read through remembered lines are the runs a fresh scan finds, every time."""

    @given(_boards())
    def test_the_runs_match_on_every_read(self, board: Board) -> None:
        rows, _ = board
        scanned = _scanned_runs(rows)
        self.assertEqual(cw_grid.runs_from_rows(rows), scanned)
        self.assertEqual(cw_grid.runs_from_rows(rows), scanned)
