"""cw_reach: whether a search step may leave a run the one rule will later accept.

The one rule (every maximal run of two or more filled cells is a distinct bank
answer) is a promise about the grids this tool accepts and writes. Holding every
step of the walk to it as well made interlocked grids unreachable: where answers
share cells densely enough, every remaining answer placed alone breaks the rule and
only two placed together obey it, and a walk that lays one answer at a time never
takes that step, however large its budget.

So a step may leave a run that breaks the rule, provided an unused answer could
still be laid over it (`completable`). That is a pruning test and nothing more. It
ignores what completing a run would do to the lines crossing it and whether two
partial runs want the same answer, and for a repeated answer it considers only the
copy `cw_place.rule_breaks` reports. So a step it lets through may lead nowhere,
and one it refuses might occasionally have been rescued another way. Neither can
put a bad grid on disk: `cw_search` accepts and returns only grids for which
`cw_place.rule_breaks` is empty.

Nor can it keep the latitude from swallowing the walk, and two bounds do that,
neither of them here. While a break the walk made stands (`walk_breaks`),
`cw_order` offers only placements laid over it; and `cw_search` gives a detour a
fixed budget of broken boards before it goes back. On a bank rich in short
answers nearly every run passes `completable`, and without them one detour took
every node the walk had.

A `--source` grid may start on such a run: a half-written word no answer spells
yet, which the fill must complete (`partial_runs`). The same test decides whether
one is worth starting from, and it stays a pruning test there too: a source run
it passes may still never be completed.

Pins get no such latitude. A pin extended into a longer run can never become
itself again, so `pins_hold` is checked strictly at every step.

Both questions are asked on every node, so what they read is kept to what they
need. A broken board's candidates are built from the break's own line
(`placements_over`), and a step check asks about a broken run only the answers
holding its letters (`holders_by_fragment`). Each gives exactly what the full read
gave, so the walk is unchanged; the full reads cost a 13x13 fill minutes.

Nothing here takes an ordering from a set: every lookup walks the sequence it is
handed, and every tuple returned keeps that sequence's order.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from types import MappingProxyType

import cw_bank
import cw_grid
import cw_place


def _line(rows: Sequence[str], run: cw_grid.Run) -> tuple[str, int]:
    """The whole row or column `run` lies in, and the run's start along it."""
    if run.direction == cw_grid.ACROSS:
        return rows[run.row], run.col
    return "".join(row[run.col] for row in rows), run.row


def _offsets(answer: str, text: str) -> Iterator[int]:
    """Every index at which `text` occurs inside `answer`, overlaps included.

    Every one, not the first: an answer can hold a run twice, and only a later
    copy may be the alignment that fits the line.
    """
    index = answer.find(text)
    while index != -1:
        yield index
        index = answer.find(text, index + 1)


def _lays_over(line: str, first: int, answer: str) -> bool:
    """Whether `answer` placed from `first` along `line` would stand as its own run.

    It must lie inside the line, agree with every letter already in its span,
    and have a block or the edge just past both ends: a filled neighbor would
    join the two into one longer run that `answer` does not spell.
    """
    end = first + len(answer)
    if first < 0 or end > len(line):
        return False
    if first > 0 and line[first - 1] != cw_grid.BLOCK:
        return False
    if end < len(line) and line[end] != cw_grid.BLOCK:
        return False
    return all(
        cell in (cw_grid.BLOCK, letter)
        for cell, letter in zip(line[first:end], answer, strict=True)
    )


def completable(rows: Sequence[str], run: cw_grid.Run, answers: Sequence[str]) -> bool:
    """Whether some answer in `answers` could still be laid over `run`.

    Only a longer answer counts: a run that already spells an answer and still
    breaks the rule is a repeat, which only extending it could change.
    """
    line, start = _line(rows, run)
    return any(
        _lays_over(line, start - offset, answer)
        for answer in answers
        if len(answer) > len(run.text)
        for offset in _offsets(answer, run.text)
    )


def _laid_from(run: cw_grid.Run, answer: str, offset: int) -> cw_place.Placement:
    """The placement of `answer` along `run`'s line whose letter `offset` is the run's first."""
    if run.direction == cw_grid.ACROSS:
        return cw_place.Placement(answer, run.row, run.col - offset, run.direction)
    return cw_place.Placement(answer, run.row - offset, run.col, run.direction)


def placements_over(
    grid: cw_grid.Grid,
    runs: Sequence[cw_grid.Run],
    answers: Sequence[str],
    masked: AbstractSet[tuple[int, int]] = frozenset(),
) -> list[cw_place.Placement]:
    """Every fitting placement of `answers` that lies over all of one of `runs`.

    Exactly the placements `cw_place.crossing_candidates` offers that `covers` one
    of `runs`, but built from each run's own line rather than filtered out of every
    crossing on the board. A placement covering a run lies along its line (see
    `covers`), and one agreeing with its letters holds the run's text at the offset
    it starts from, so `_offsets` names every one; `cw_place.fits` then judges it
    exactly as the enumeration would. The filter was the cost: on a 13x13 of a
    1,758-answer bank, building every crossing to keep these took 94.6% of a fill,
    about 62,600 fit checks a node to keep about 150.

    `masked` is `FillConfig.masked` and defaults to none; it reaches the
    judgment through `cw_place.fits`, which is the whole of this function's
    screen, so a masked cell is refused here exactly as
    `cw_place.crossing_candidates` refuses it through its stamped line view.

    Order: `runs` as given, then `answers` as given, then ascending offset; a
    placement lying over two runs is kept at its first. `seen` is a membership test
    and is never iterated.
    """
    found: list[cw_place.Placement] = []
    seen: set[cw_place.Placement] = set()
    for run in runs:
        for answer in answers:
            for offset in _offsets(answer, run.text):
                placement = _laid_from(run, answer, offset)
                if placement in seen or not cw_place.fits(grid, placement, masked):
                    continue
                seen.add(placement)
                found.append(placement)
    return found


def holders_by_fragment(
    answers: Sequence[str], *, longest: int
) -> Mapping[str, tuple[str, ...]]:
    """Every fragment of two or more letters, mapped to the longer answers holding it.

    Built once per search, so a step check asks about a broken run only the answers
    that could ever lie over it. `completable` counts an answer only when it is
    longer than the run and holds the run's letters, and those are exactly the
    answers listed under the run's text, so asking them alone gives its verdict,
    without scanning every unused answer on every tried step (on a 1,817-answer
    bank, 85% of an 11x11 fill once candidate building was cheap). An answer is
    never listed under itself, and once under a fragment it holds twice.

    Only answers of at most `longest` letters (the grid's longest line) are
    indexed. A longer one can never be laid, so `completable` would never count
    it, and indexing it costs every substring it has: about L**3 / 6 characters,
    built before the first node, where no budget is read.

    Keys and holders keep the order given; nothing reads an order from them anyway,
    since `step_allowed` only asks whether any holder lies over the run.
    """
    table: dict[str, list[str]] = {}
    placeable = (answer for answer in answers if len(answer) <= longest)
    for answer in dict.fromkeys(placeable):
        fragments = dict.fromkeys(
            answer[start:end]
            for start in range(len(answer))
            for end in range(start + cw_grid.MIN_RUN, len(answer) + 1)
            if end - start < len(answer)
        )
        for fragment in fragments:
            table.setdefault(fragment, []).append(answer)
    return MappingProxyType({key: tuple(found) for key, found in table.items()})


def unused_answers(rows: Sequence[str], bank: cw_bank.Bank) -> tuple[str, ...]:
    """Bank answers not already on the board as an entry, in bank order.

    The vocabulary a node's candidates are drawn from, and the one `completable`
    is asked about by the `--source` check and by pre-flight, which is why it
    lives beside it. The walk's step check asks the same question of fewer
    answers (`holders_by_fragment`). Read off the grid's runs rather than from a list
    of what the search placed, so an answer the grid gained for free is
    excluded too.

    It does not rule out `cw_place.crossing_candidates`' documented
    zero-progress candidate, and must not be read as though it did: an answer
    whose letters all sit inside a longer run (CAT inside CATS) is not
    itself a run, so it survives this filter, and re-laying it over those cells
    would fill nothing. `cw_order.ordered_candidates` is what drops that one.
    """
    present = {run.text for run in cw_grid.runs_from_rows(rows)}
    return tuple(entry.answer for entry in bank.entries if entry.answer not in present)


def partial_runs(
    rows: Sequence[str], allowed: AbstractSet[str]
) -> tuple[cw_grid.Run, ...]:
    """Every run of `rows` that no answer in `allowed` spells, in scan order.

    On a `--source` grid these are the half-written words. `cw_source` has
    already refused any such run no unused answer could complete, so every one
    left is a run the fill must finish. `allowed` is the search bank (the
    bank's answers and every entry kept from the source), so a kept entry is
    never partial, however a longer answer could extend it.
    """
    return tuple(run for run in cw_grid.runs_from_rows(rows) if run.text not in allowed)


def covers(run: cw_grid.Run, cells: Sequence[tuple[int, int]]) -> bool:
    """Whether a line of `cells` covers every cell of `run`.

    The one test of "laid over a partial run": the walk ranks a placement that
    passes it first, and the report reads a completed run off the answer that
    passes it. The cells alone decide it, with no separate direction check: a
    run is at least two cells of one line, and a crossing line shares at most
    one of them, so only a line running the same way can hold them all. A
    mutation sweep confirmed the direction clause could never change a result.
    """
    return set(run.cells) <= set(cells)


def walk_breaks(
    rows: Sequence[str], allowed: AbstractSet[str], start: Sequence[str]
) -> tuple[cw_grid.Run, ...]:
    """The runs of `rows` that break the rule and that the walk made itself, in scan order.

    Every run `cw_place.rule_breaks` reports except one lying along a `--source`
    partial run (`covers`): the half-written word itself, or the longer
    unfinished run a step has since grown it into. The two are treated
    differently. Around a source's partial run the walk stays free, and
    `cw_order` only ranks the completion first; over a break it made, it may lay
    nothing but a repair. Without a source every break is the walk's own.
    """
    partial = partial_runs(start, allowed)
    return tuple(
        run
        for run, _ in cw_place.rule_breaks(rows, allowed)
        if not any(covers(inner, run.cells) for inner in partial)
    )


def pins_hold(runs: Sequence[cw_grid.Run], pinned: tuple[cw_grid.Run, ...]) -> bool:
    """Whether every pin is still an entry of its own, exactly where it was pinned.

    `runs` is every run of the board (`cw_grid.runs_from_rows`), so the check is
    whole-grid, like the rule: a placement can leave every pinned cell untouched
    and still end a pin, by filling the cell just past it: JANE becomes JANET.
    Holding the cells is not holding the entry.
    """
    return all(run in runs for run in pinned)


def step_allowed(
    rows: Sequence[str],
    allowed: AbstractSet[str],
    pinned: tuple[cw_grid.Run, ...],
    holders: Mapping[str, Sequence[str]],
) -> bool:
    """Whether the search may stand on `rows` after a tentative placement.

    Every pin must hold, and every run that breaks the rule must be one an
    unused answer could still complete. `holders` is `holders_by_fragment` over
    the search bank: each break is asked of the answers listed under its text
    that are not already an entry on this board: the unused ones that could
    ever lie over it, and so the same verdict as asking every unused answer.
    Neither the index nor the board's entries are read when the step breaks
    nothing, which is most steps.

    The board's runs are derived once and read by all three questions (pins,
    breaks, entries), since this is the walk's most frequent question: an 11x11
    look-ahead window asks it about 455,000 times, and deriving the runs again
    for each question was nearly half its cost.
    """
    runs = cw_grid.runs_from_rows(rows)
    if not pins_hold(runs, pinned):
        return False
    breaks = cw_place.breaks_among(runs, allowed)
    if not breaks:
        return True
    # Membership only, like every set in this module: never iterated.
    present = frozenset(run.text for run in runs)
    return all(
        completable(
            rows,
            run,
            [answer for answer in holders.get(run.text, ()) if answer not in present],
        )
        for run, _ in breaks
    )
