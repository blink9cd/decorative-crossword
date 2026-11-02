"""cw_gaps: what a letter in a blocked cell would demand of the bank.

The instrument behind the tool's one rule rather than an exception to it. Every
maximal run of two or more filled cells must be a distinct bank answer, so a
denser grid is a demand on the bank; this module turns "this grid is sparser
than I want" into the specific letter patterns that would answer that demand,
and it writes nothing into any grid. Constructing filler stays impossible: the
output is a question for the operator, and the fill still happens the one way it
can, by an answer entering the bank and `fill` running again.

The load-bearing subtlety is welding. A blocked cell between two existing runs
does not create a short run out of its immediate neighbors: it joins them,
and the whole joined line is what must then be a bank answer. Reading only the
neighbors of `AB.CD` reports a three-letter demand where the truth is a
five-letter one, and it stays silent about `AB` and `CD` ceasing to be entries.
So each demand carries the full run it would create plus the answers that run
would absorb, and `tests/test_gaps.py`'s `TestWelding` fails any reader that
loses either half.

A cell whose fill would create no run at all is an orphan and is excluded, not
ranked: a lone letter forms no entry, so it answers no demand on the bank, and
`cw_place.grid_violations` is documented as silent about one. They are counted
rather than dropped, because a count that is not accounted for is a count that
misleads.

Order is row-major and is part of the contract: two runs must produce
byte-identical output, and every ordering here comes from the scan rather than
from a set.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

import cw_grid

#: The unfilled cell inside a demanded pattern. Exactly one appears in each,
#: and it is deliberately not `cw_grid.BLOCK`: a pattern is a request for a
#: letter, and spelling the request with the character that means "no letter
#: here" would read as the opposite of what it asks.
UNKNOWN = "?"

#: Per direction, the step that walks backward along it and the step that walks
#: forward. Backward comes first because a pattern reads in the run's own
#: direction, so the backward arm is reversed into place ahead of the gap.
#: A lookup rather than an if/else, so an unrecognized direction raises
#: KeyError loudly instead of being silently treated as one of the two:
#: the same choice, for the same reason, as `cw_grid._STEPS`.
_ARMS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    cw_grid.ACROSS: ((0, -1), (0, 1)),
    cw_grid.DOWN: ((-1, 0), (1, 0)),
}


@dataclass(frozen=True)
class Demand:
    """One maximal run a fill would create, with the new cell written as UNKNOWN.

    `row` and `col` are where the run starts, not where the gap is: a reader
    sent to the gap's own coordinates would be looking at the wrong square of
    a welded run. `absorbed` names the existing answers this run would swallow,
    which is the cost of the fill and is empty for a pure addition.
    """

    direction: str
    row: int
    col: int
    pattern: str
    absorbed: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    """One blocked cell a letter could occupy, and every run that letter creates.

    `demands` holds one or two entries, ACROSS before DOWN, and never zero: a
    cell that would create no run is an orphan and never becomes a Candidate.
    Both demands must be satisfied by the same letter, which is what makes a
    two-demand cell a materially bigger ask than a one-demand cell.
    """

    row: int
    col: int
    demands: tuple[Demand, ...]

    @property
    def absorbed(self) -> tuple[str, ...]:
        """Every existing answer this fill would retire, across both demands."""
        return tuple(answer for demand in self.demands for answer in demand.absorbed)

    @property
    def pattern_length(self) -> int:
        """Total length of the patterns this fill demands.

        The ranking's measure of how big the ask is once the number of demands
        is equal: two two-letter runs are a smaller request than one six-letter
        run, and both are smaller than the pair of them.
        """
        return sum(len(demand.pattern) for demand in self.demands)


@dataclass(frozen=True)
class GapAnalysis:
    """Every blocked cell of one grid, split by what it can be.

    `candidates`, `orphans` and `masked` partition the grid's blocked cells:
    their three lengths add up to the blocked count, which `tests/test_gaps.py`
    pins so a reader can trust the report's arithmetic rather than re-deriving it.

    `masked` is the cells a `--mask` picture forbids a letter. A third tier
    rather than more orphans: an orphan is a cell a letter could take and should
    not, which is a different sentence from one that may never hold one, and a
    reader given the wrong one would go looking for the crossing that caused it.
    """

    candidates: tuple[Candidate, ...]
    orphans: tuple[tuple[int, int], ...]
    masked: tuple[tuple[int, int], ...] = ()


def _arm(rows: Sequence[str], row: int, col: int, d_row: int, d_col: int) -> str:
    """The contiguous letters walking outward from (row, col), nearest first.

    Stops at a block or at the edge. The width is re-read per row rather than
    taken from the first, so the walk never indexes past a short row.
    """
    letters: list[str] = []
    walk_row, walk_col = row + d_row, col + d_col
    while 0 <= walk_row < len(rows) and 0 <= walk_col < len(rows[walk_row]):
        char = rows[walk_row][walk_col]
        if char == cw_grid.BLOCK:
            break
        letters.append(char)
        walk_row += d_row
        walk_col += d_col
    return "".join(letters)


def _demand_for(
    rows: Sequence[str], row: int, col: int, direction: str
) -> Demand | None:
    """The run a letter at (row, col) would create along `direction`, or None.

    None when the letter would stand alone on this axis: both arms empty, so
    the "run" is the one cell and `cw_grid.MIN_RUN` is not reached. That is not
    a failure: it is how a cell with a neighbor on only one axis comes back
    with a single demand.
    """
    back_step, forward_step = _ARMS[direction]
    # Reversed because `_arm` walks outward, nearest letter first, while a
    # pattern reads in the run's own direction.
    before = _arm(rows, row, col, *back_step)[::-1]
    after = _arm(rows, row, col, *forward_step)
    pattern = before + UNKNOWN + after
    if len(pattern) < cw_grid.MIN_RUN:
        return None
    return Demand(
        direction=direction,
        row=row + back_step[0] * len(before),
        col=col + back_step[1] * len(before),
        pattern=pattern,
        # An arm of one letter is no entry, so welding it costs nothing;
        # reporting it as absorbed would invent a loss the operator does
        # not take.
        absorbed=tuple(arm for arm in (before, after) if len(arm) >= cw_grid.MIN_RUN),
    )


def _candidate_for(rows: Sequence[str], row: int, col: int) -> Candidate | None:
    """The candidate for one blocked cell, or None when it would be an orphan."""
    demands = []
    for direction in (cw_grid.ACROSS, cw_grid.DOWN):
        demand = _demand_for(rows, row, col, direction)
        if demand is not None:
            demands.append(demand)
    if not demands:
        return None
    return Candidate(row=row, col=col, demands=tuple(demands))


# fuzz-target
def analyze_grid(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]] = frozenset()
) -> GapAnalysis:
    """Split every blocked cell of `rows` into a candidate, an orphan or a masked cell.

    Row-major, so the order is the one a reader scanning the grid expects and
    is stable across processes. That matters for `masked` in particular: it is
    read off the grid and never by iterating the set, whose order is hash-seeded
    and whose contents reach a report.

    A masked cell is set aside before it is examined at all. `gaps` exists to
    say which letter to buy for a blocked cell, and a cell the operator drew out
    of the grid is one they will never fill, so any advice about it is advice
    they would have to throw away.
    """
    candidates: list[Candidate] = []
    orphans: list[tuple[int, int]] = []
    forbidden: list[tuple[int, int]] = []
    for row_index, row in enumerate(rows):
        for col_index, char in enumerate(row):
            if char != cw_grid.BLOCK:
                continue
            if (row_index, col_index) in masked:
                forbidden.append((row_index, col_index))
                continue
            candidate = _candidate_for(rows, row_index, col_index)
            if candidate is None:
                orphans.append((row_index, col_index))
            else:
                candidates.append(candidate)
    return GapAnalysis(
        candidates=tuple(candidates),
        orphans=tuple(orphans),
        masked=tuple(forbidden),
    )


#: Every letter a gap could take. Spelled out rather than derived from a range,
#: because `cw_grid` defines a cell's contents as A-Z and this is that same
#: alphabet rather than a coincidence of character codes.
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class Fill:
    """One letter that satisfies every demand of a candidate at once.

    `words` holds one answer per demand, in the candidate's own demand order,
    so a reader can see which word lands across and which lands down.
    """

    letter: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class Resolution:
    """What one vocabulary says about one candidate.

    Three outcomes, and keeping them apart is the point of the subcommand:
    `fills` non-empty means the operator can already pay for this gap;
    `unmatched` non-empty names the patterns nothing matches; and both empty is
    the crossing: every pattern has a word, no single letter has them all.
    """

    candidate: Candidate
    fills: tuple[Fill, ...]
    unmatched: tuple[str, ...]

    @property
    def blocked_by_crossing(self) -> bool:
        """True when each pattern is matched but no one letter matches them all."""
        return not self.fills and not self.unmatched

    @property
    def new_words(self) -> int:
        """How many answers the operator must invent before this gap can be filled.

        A crossing costs one, not one per demand: either pattern gaining a
        single word whose letter the other pattern already answers clears it.
        Charging two there would send the operator looking for a word they do
        not need.
        """
        if self.fills:
            return 0
        if self.unmatched:
            return len(self.unmatched)
        return 1


def _available(
    vocabulary: frozenset[str], used: Counter[str], candidate: Candidate
) -> frozenset[str]:
    """The answers `candidate` may draw on, honoring the distinctness rule.

    The vocabulary less what this grid already spends, and plus what this
    fill would retire, because an answer a weld absorbs is off the grid by the
    time the new run needs a name, and is therefore free for this candidate's
    other demand.

    Counted rather than set-subtracted, because absorption frees an
    occurrence and not a word. A grid handed to `gaps` may already spell one
    answer twice (it is hand-authored input, and telling the operator so is
    half the point of the subcommand), and against a set the surviving copy
    would vanish along with the absorbed one, so the resolver would offer a
    letter whose run spelled an answer still standing elsewhere on the grid,
    breaking the one rule this module exists to serve.
    """
    absorbed = Counter(candidate.absorbed)
    # Every absorbed answer is a run of this grid, so `absorbed` can never
    # out-count `used`: the test reads "this fill retires the last copy".
    return frozenset(
        answer for answer in vocabulary if used[answer] <= absorbed[answer]
    )


def _fill_for(
    candidate: Candidate, letter: str, available: frozenset[str]
) -> Fill | None:
    """The fill `letter` would make of `candidate`, or None if it would not.

    Two ways to fail, and the first is not the obvious one: a letter that makes
    both demands spell the same word is refused however available that word is,
    because one answer cannot stand as two distinct entries.
    """
    words = tuple(
        demand.pattern.replace(UNKNOWN, letter) for demand in candidate.demands
    )
    if len(set(words)) != len(words):
        return None
    if not all(word in available for word in words):
        return None
    return Fill(letter=letter, words=words)


def _is_matched(pattern: str, available: frozenset[str]) -> bool:
    """Whether any available answer fits `pattern` with some letter in the gap."""
    return any(pattern.replace(UNKNOWN, letter) in available for letter in _ALPHABET)


def resolve(
    candidate: Candidate, vocabulary: frozenset[str], used: Counter[str]
) -> Resolution:
    """Ask `vocabulary` what it can do for one candidate.

    An absent vocabulary is the empty vocabulary rather than a second code
    path: every pattern comes back unmatched, which is the honest reading of
    "nothing was offered", and there is one implementation to keep correct.
    """
    available = _available(vocabulary, used, candidate)
    fills = []
    for letter in _ALPHABET:
        fill = _fill_for(candidate, letter, available)
        if fill is not None:
            fills.append(fill)
    unmatched = tuple(
        demand.pattern
        for demand in candidate.demands
        if not _is_matched(demand.pattern, available)
    )
    return Resolution(candidate=candidate, fills=tuple(fills), unmatched=unmatched)


# fuzz-target
def resolve_all(
    rows: Sequence[str], analysis: GapAnalysis, vocabulary: frozenset[str]
) -> tuple[Resolution, ...]:
    """Resolve every candidate of `analysis` against `vocabulary`.

    The grid's own answers are read once, here, as a multiset: a grid may
    already spell one answer twice, and counting it once would let a fill
    absorb one copy and then re-spend the word the other copy still holds.
    They are looked up by key and never iterated, so no ordering of theirs
    can reach the output, which must be stable across runs.
    """
    used = Counter(run.text for run in cw_grid.runs_from_rows(rows))
    return tuple(
        resolve(candidate, vocabulary, used) for candidate in analysis.candidates
    )


def _rank_key(resolution: Resolution) -> tuple[bool, int, int, int, int]:
    """Cheapest ask first; the trailing cell makes the order total and stable.

    Absorption leads because it is a different kind of cost from the others:
    every other tier adds an answer, while an absorbing fill retires ones the
    operator curated, and no number of short patterns makes that the cheaper
    move.
    """
    candidate = resolution.candidate
    return (
        bool(candidate.absorbed),
        resolution.new_words,
        candidate.pattern_length,
        candidate.row,
        candidate.col,
    )


def rank(resolutions: Sequence[Resolution]) -> tuple[Resolution, ...]:
    """Order resolutions by how cheap their demand on the bank is."""
    return tuple(sorted(resolutions, key=_rank_key))


@dataclass(frozen=True)
class GapSearch:
    """Everything one `gaps` run derived, in the order the report wants it.

    `vocabulary_size` is carried rather than recomputed downstream so the
    report's headline cannot disagree with what the resolver was actually
    handed; zero is how a reader is told no vocabulary was supplied, which is
    a different sentence from "none of it matched".
    """

    analysis: GapAnalysis
    resolutions: tuple[Resolution, ...]
    vocabulary_size: int


def search_gaps(
    rows: Sequence[str],
    vocabulary: frozenset[str],
    masked: AbstractSet[tuple[int, int]] = frozenset(),
) -> GapSearch:
    """Derive, resolve and rank every gap in `rows` against `vocabulary`.

    `masked` is `GapsConfig.masked` and defaults to none; a masked cell never
    becomes a candidate, so nothing downstream resolves or ranks one.
    """
    analysis = analyze_grid(rows, masked)
    return GapSearch(
        analysis=analysis,
        resolutions=rank(resolve_all(rows, analysis, vocabulary)),
        vocabulary_size=len(vocabulary),
    )
