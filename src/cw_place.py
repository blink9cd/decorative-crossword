"""cw_place: placement legality, exact undo, and candidate enumeration.

This module owns the one rule the rest of the project rests on:

    Every maximal run of two or more filled cells must be a distinct bank answer.

`rule_breaks` is that rule, whole, in one pure function, and `grid_violations`
renders what it finds as sentences. There is no incremental variant here and
there must not be one: judging the whole grid every time it is asked is
*deliberate*, because an incremental version of that rule is easy to get subtly
wrong in a way no test notices. It is O(cells) per question against a search
that is bounded by an explicit budget anyway -- correct-by-inspection over
fast-and-clever.

Because that check is whole-grid, the rest of this module deliberately does
NOT judge legality. `fits` answers only "does this answer physically go here
without contradicting a letter already on the board", and `crossing_candidates`
enumerates without filtering beyond that. Everything else is decided after the
tentative apply, by the one function that owns the rule -- in full when the
search accepts a grid, and through `cw_reach` at each step of the walk, where a
break that an unused answer could still repair is let through.

Determinism: `crossing_candidates` feeds the search's node
order, and any run that exits 0 must emit a byte-identical grid. Nothing here
may take an ordering from a `set`, a `dict` built from one, or the builtin
`hash()` -- see cw_grid's module docstring for why. Both sets in this file
(`breaks_among`' distinctness tracker and `crossing_candidates`'s duplicate
filter) are membership tests that are never iterated; each result's order comes
from the list or tuple built beside them, and the letter index's lists keep the
order of the answers they were built from.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from types import MappingProxyType

import cw_grid
import cw_mask
import cw_text

#: (row, col) delta per step for each direction, DERIVED from cw_grid rather
#: than restated. `Run.cells` is this project's single definition of which way
#: ACROSS and DOWN advance, so the second cell of a two-cell run laid at the
#: origin IS that direction's step. Writing the table out literally here would
#: be a second copy of that definition, free to drift from cw_grid's the day
#: either changes. MappingProxyType so the "single source" claim is real: a
#: plain module-level dict is mutable through any importer's reference.
_STEPS: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        direction: cw_grid.Run(row=0, col=0, direction=direction, text="AA").cells[1]
        for direction in (cw_grid.ACROSS, cw_grid.DOWN)
    }
)

#: The two halves of a violation message. Named so the check that detects a
#: problem and the sentence describing it cannot drift apart.
_NOT_A_BANK_ANSWER = "is not a bank answer"
_ALREADY_PLACED = "repeats an answer already placed"


@dataclass(frozen=True)
class Placement:
    """One proposed entry: an answer, where it starts, and which way it runs.

    A proposal, not a fact about the grid -- `fits` and `grid_violations` decide
    whether it may exist. `direction` is `cw_grid.ACROSS` or `cw_grid.DOWN`; any
    other value raises KeyError at the first geometry lookup rather than being
    silently treated as one of them, matching cw_grid's own choice.
    """

    answer: str
    row: int
    col: int
    direction: str


def _span(placement: Placement) -> tuple[tuple[int, int], ...]:
    """Every (row, col) the placement would occupy, from its start outwards."""
    d_row, d_col = _STEPS[placement.direction]
    return tuple(
        (placement.row + d_row * offset, placement.col + d_col * offset)
        for offset in range(len(placement.answer))
    )


def _start_for_crossing(
    row: int, col: int, direction: str, offset: int
) -> tuple[int, int]:
    """Where an answer must start so its letter `offset` lands on (row, col).

    The inverse of `_span`: step *back* along the direction. The result may be
    negative or past an edge -- that is `fits`' call to make, not this one's.
    """
    d_row, d_col = _STEPS[direction]
    return (row - d_row * offset, col - d_col * offset)


def fits(
    grid: cw_grid.Grid,
    placement: Placement,
    masked: AbstractSet[tuple[int, int]] = frozenset(),
) -> bool:
    """Whether `placement` is inside `grid`, clear of `masked`, and contradicts no letter.

    Bounds, the mask, and letter agreement only. It is NOT the legality check: whether the
    resulting grid obeys the distinct-run rule is `grid_violations`' job, after the
    tentative apply. The bounds half is load-bearing rather than defensive:
    `cw_reach.placements_over` steps back from a run by the matched letters'
    offset, so it really does propose starts before row 0 or column 0.
    Checking the range here is what turns those into a plain False -- without
    it `Grid.letter` raises, and building would crash rather than filter.
    `crossing_candidates` makes the same judgment on the board's own lines
    (`_fits_line`), and `tests/test_reach_properties.py` holds the two to one
    answer.

    `masked` is `FillConfig.masked`, the cells a `--mask` picture forbids a
    letter, and defaults to none, so a caller with no mask passes nothing. It
    is consulted here rather than written into the grid because
    `cw_grid.Grid` is strictly two-valued and the search mutates one of them:
    a masked cell is a fact about the REQUEST, not about the board. Membership
    only, so no order of it can reach the search's node order.
    """
    for (row, col), letter in zip(_span(placement), placement.answer, strict=True):
        if not (0 <= row < grid.height) or not (0 <= col < grid.width):
            return False
        if (row, col) in masked:
            return False
        existing = grid.letter(row, col)
        if existing is not None and existing != letter:
            return False
    return True


def apply_placement(
    grid: cw_grid.Grid, placement: Placement
) -> tuple[tuple[int, int], ...]:
    """Write `placement` into `grid`; return only the cells it NEWLY filled.

    That return value is what makes `undo_placement` exact. A placement that
    crosses an existing entry reuses cells it must not later erase, so the
    cells it found already filled are deliberately absent from the result.

    Raises ValueError unless the placement fits. The guard is not redundant
    with the caller's own `fits` call: without it, a placement running off an
    edge strands its prefix. The loop below READS each cell before writing it,
    so the failure comes out of `Grid.letter`'s index check, not out of
    `set_letter` -- measured, with the guard disabled: `CHEMEX` laid across a
    3x3 raises `cell (0, 3) is outside a 3x3 grid` and leaves
    ('CHE', '...', '...') behind with no undo list ever returned, which is
    state the caller cannot recover because it cannot know how far it got. A
    placement contradicting a letter already on the board is the subtler
    fault: the loop skips a cell it finds occupied, so it would quietly write
    around the clash and spell something that is not the answer.

    The guard covers those two faults and no others. It does not screen the
    MASK: `fits` is asked here without one, deliberately, because the cells a
    `--mask` forbids are a fact about the request and this function is given
    only a grid. Every placement that reaches here has already been screened --
    the search's come from `cw_order.ordered_candidates`, whose every generator
    consults `config.masked`, and a pin's is refused by
    `cw_feature.validate_features` before any board is built.

    Beyond those two faults it inspects position, not charset. An answer
    carrying a character outside A-Z still strands a prefix, raising out of
    `Grid.set_letter`'s own letter check. Answer validity belongs to
    `cw_bank._parse_answer`, at the input boundary, so such an answer cannot
    reach here from a loaded bank.
    """
    if not fits(grid, placement):
        raise ValueError(
            f"placement {cw_text.shown(placement.answer)} does not fit at "
            f"({placement.row}, {placement.col}) {placement.direction}"
        )
    filled: list[tuple[int, int]] = []
    for (row, col), letter in zip(_span(placement), placement.answer, strict=True):
        if grid.letter(row, col) is None:
            grid.set_letter(row, col, letter)
            filled.append((row, col))
    return tuple(filled)


def undo_placement(grid: cw_grid.Grid, filled: Sequence[tuple[int, int]]) -> None:
    """Clear exactly the cells `apply_placement` reported filling.

    `filled` must be that return value and nothing else. Clearing a placement's
    whole span instead would erase the crossing letters it shares with entries
    placed earlier, and the corruption surfaces many search steps later as an
    unrelated failure.
    """
    for row, col in filled:
        grid.clear(row, col)


def describe_break(run: cw_grid.Run, problem: str) -> str:
    """One violation sentence, naming the run's own position and direction."""
    return (
        f"{run.direction} run {cw_text.shown(run.text)} at ({run.row}, {run.col}) "
        f"{problem}"
    )


def grid_violations(rows: Sequence[str], allowed: AbstractSet[str]) -> tuple[str, ...]:
    """Every way `rows` breaks the distinct-run rule, as reader-facing sentences.

    The rule: every maximal run of two or more filled cells must be a distinct
    answer drawn from `allowed`. Two clauses, and both matter -- "in the bank"
    forbids the accidental letter pair that two words laid in adjacent parallel
    lines would create, and "distinct" forbids two entries sharing one answer,
    which downstream cannot give distinct clues.

    `allowed` is normally every answer in the bank, not the unused remainder:
    an answer already on the board must stay legal where it lies, and it is the
    distinctness clause, not this set, that stops it being placed twice.

    Takes rows rather than a Grid so the same rule can check a loaded
    `grid_source.json` and be driven by generated data in the property tests.

    Runs of one cell are not entries and are not reported,
    because `cw_grid.runs_from_rows` never yields them. The consequence is
    worth stating plainly: this function is SILENT about an orphaned filled
    cell. A lone letter touching nothing forms no run, so `(('X.', '..'),
    set())` comes back clean. It assumes every filled cell it is shown came
    from an answer of length >= `cw_grid.MIN_RUN` -- free for the search,
    where the rule holds because every placed answer is at least two cells
    long, but NOT free for rows that arrived another way. A
    caller checking a hand-edited `grid_source.json` or generated data must
    establish that itself; this function will not catch it.

    Violations come back in `runs_from_rows`'s documented scan order -- every
    ACROSS run row-major, then every DOWN run column-major -- so the report is
    stable across processes.
    """
    return tuple(
        describe_break(run, problem) for run, problem in rule_breaks(rows, allowed)
    )


def rule_breaks(
    rows: Sequence[str], allowed: AbstractSet[str]
) -> tuple[tuple[cw_grid.Run, str], ...]:
    """Every run in `rows` that breaks the distinct-run rule, with the clause it breaks.

    The rule, stated once, in `breaks_among`: this is that rule over the whole
    grid's runs. `grid_violations` renders these as sentences for a reader, and
    `cw_reach` asks of each whether an unused answer could still complete it. One
    statement for every caller, so the check a search step passes and the check an
    accepted grid passes cannot come to disagree about what breaks the rule.

    Scan order, the meaning of `allowed`, and the silence about an orphaned
    cell are exactly as `grid_violations` documents them. For a repeated
    answer it is the LATER copy in scan order that is reported.
    """
    return breaks_among(cw_grid.runs_from_rows(rows), allowed)


def breaks_among(
    runs: Sequence[cw_grid.Run], allowed: AbstractSet[str]
) -> tuple[tuple[cw_grid.Run, str], ...]:
    """The runs of `runs` that break the distinct-run rule, with the clause each breaks.

    The rule's own statement, for a caller that already holds a grid's runs: a
    step check needs them for more than the rule, and deriving them twice was
    most of its cost. `runs` must be every run of one grid, in scan order
    (`cw_grid.runs_from_rows`), or "distinct" is judged against the wrong entries.
    """
    breaks: list[tuple[cw_grid.Run, str]] = []
    seen: set[str] = set()
    for run in runs:
        if run.text not in allowed:
            breaks.append((run, _NOT_A_BANK_ANSWER))
        elif run.text in seen:
            breaks.append((run, _ALREADY_PLACED))
        # Membership only: `seen` is never iterated, so its PYTHONHASHSEED-
        # dependent order cannot reach the returned tuple.
        seen.add(run.text)
    return tuple(breaks)


def _filled_cells(grid: cw_grid.Grid) -> tuple[tuple[int, int, str], ...]:
    """Every filled cell as (row, col, letter), row-major."""
    return tuple(
        (row, col, letter)
        for row in range(grid.height)
        for col in range(grid.width)
        if (letter := grid.letter(row, col)) is not None
    )


def _answers_by_letter(answers: Iterable[str]) -> dict[str, list[str]]:
    """Each letter, mapped to the answers holding it, in the order given.

    An answer is listed once under each letter it holds, however often it holds
    it: `_alignments` finds every offset. Membership and order both come from
    the lists, which keep `answers`' order.
    """
    table: dict[str, list[str]] = {}
    for answer in answers:
        for letter in dict.fromkeys(answer):
            table.setdefault(letter, []).append(answer)
    return table


def _alignments(
    row: int, col: int, letter: str, answer: str
) -> list[tuple[int, int, str]]:
    """Every start that puts one of `answer`'s `letter`s on (row, col), with its direction.

    Both directions, one alignment per matching letter offset -- so an answer
    carrying the crossed letter twice offers two starting positions in each
    direction, not one. Starts rather than placements: nearly every alignment
    on a full board fails to fit, and it is cheaper never to build those.
    """
    found: list[tuple[int, int, str]] = []
    for offset, answer_letter in enumerate(answer):
        if answer_letter != letter:
            continue
        for direction in (cw_grid.ACROSS, cw_grid.DOWN):
            start_row, start_col = _start_for_crossing(row, col, direction, offset)
            found.append((start_row, start_col, direction))
    return found


def _fits_line(line: str, first: int, answer: str) -> bool:
    """Whether `answer` laid from `first` along `line` stays on it and contradicts no letter.

    `fits`, judged on the line's own letters rather than cell by cell through the
    grid: bounds along the line and letter agreement, nothing more. The other
    bound is the caller's, which picks the line.
    """
    end = first + len(answer)
    if first < 0 or end > len(line):
        return False
    return all(
        cell in (cw_grid.BLOCK, letter)
        for cell, letter in zip(line[first:end], answer, strict=True)
    )


def crossing_candidates(
    grid: cw_grid.Grid,
    answers: Iterable[str],
    masked: AbstractSet[tuple[int, int]] = frozenset(),
) -> list[Placement]:
    """Every fitting placement of `answers` that crosses a letter already on `grid`.

    Crossing is by construction, not by a filter: each candidate is built from a
    filled cell it must cover, which is what keeps the grid one connected shape
    and what bounds the search. An empty grid therefore yields nothing -- the
    seed placement is the search's job.

    Enumerates without judging. Beyond bounds, the mask and letter agreement
    (`fits`, here judged on the board's rows and columns by `_fits_line`),
    whether a candidate is legal is decided by `rule_breaks` after the tentative
    apply, so that the rule lives in exactly one place.

    `masked` is `FillConfig.masked` and defaults to none. It is applied by
    stamping the derived line view (`cw_mask.stamped_rows`) rather than by a
    check of its own, which is why `_fits_line` is untouched.

    A candidate is not a promise of progress. An answer whose every letter is
    already on the board fits, so it is offered, and `apply_placement` then
    returns an empty tuple -- it filled nothing. Callers must not assume a
    candidate fills at least one cell. Harmless for the search, which draws
    only from answers not yet used, but it is not an invariant this
    function provides.

    ORDER IS PART OF THE CONTRACT (the search's node order must be a pure
    function of its inputs): filled cells row-major, that is row
    0 left-to-right, then row 1, and so on; within one cell, `answers` in the
    order given; within one answer, ascending letter offset; within one offset,
    ACROSS before DOWN. A placement reachable from two different crossed cells
    is offered once, at the position of its first appearance.

    The look-ahead window asks this of nearly full boards, so it reads only
    what can fit: a cell is asked only about the answers holding its letter
    (`_answers_by_letter`), the board is read once as rows and columns, and each
    start is judged once. On an 11x11 window that was most of its 76 seconds:
    about 150,000 answer-and-cell pairs a board, and 14 million fit checks
    reading the board cell by cell.
    """
    holders = _answers_by_letter(answers)
    # The mask reaches this enumeration as a CHARACTER in the derived line view,
    # not as a second predicate: `_fits_line` already refuses any cell that is
    # neither a block nor the wanted letter, so a stamped cell is refused by the
    # check that is there. An unmasked call gets the rows back untouched.
    rows = cw_mask.stamped_rows(grid.to_rows(), masked)
    lines = {
        cw_grid.ACROSS: rows,
        cw_grid.DOWN: tuple("".join(column) for column in zip(*rows, strict=True)),
    }
    found: list[Placement] = []
    # Membership only -- the returned order comes from `found`, so this set's
    # hash-seeded iteration order never reaches output. A start that failed to
    # fit is remembered too: its verdict cannot change within one enumeration.
    judged: set[tuple[str, int, int, str]] = set()
    for row, col, letter in _filled_cells(grid):
        for answer in holders.get(letter, ()):
            for start_row, start_col, direction in _alignments(
                row, col, letter, answer
            ):
                key = (answer, start_row, start_col, direction)
                if key in judged:
                    continue
                judged.add(key)
                # The crossed cell fixes the line: its row across, its column down.
                line, first = (
                    (lines[direction][row], start_col)
                    if direction == cw_grid.ACROSS
                    else (lines[direction][col], start_row)
                )
                if _fits_line(line, first, answer):
                    found.append(Placement(answer, start_row, start_col, direction))
    return found
