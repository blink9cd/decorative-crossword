"""cw_order: which placements one search node tries, and in what order.

The walk itself -- its state, its budgets, acceptance and backtracking -- is
cw_search's. This module answers the question each node asks before it
recurses: what may be laid next, best first. Kept apart from cw_search along
that seam because the two change for different reasons: a new ranking level
touches only the order, and a new budget or stop touches only the walk.

The order is half of cw_search's determinism guarantee, so the same rule binds
here: nothing may take an ordering from a `set`, from a dict built out of one,
or from the builtin `hash()`; see `order_key` for why. Every set in this file is
a membership test that is never iterated, and every returned order comes from a
list or tuple built beside it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

import cw_bank
import cw_config
import cw_grid
import cw_place
import cw_reach
from cw_accept import theme_counts

#: Digest width for an ordering key. Sixteen bytes is far more than a tie-break
#: over one bank's candidates needs, and it costs nothing: blake2b's work is in
#: compressing one short block either way.
_KEY_BYTES = 16

#: Rank of a candidate laid along a `--source` partial run the board still
#: holds, and of any other. It leads the key: no grid the walk reaches is legal
#: until every partial run is finished, and ranked by cells alone a completion
#: adding one letter is tried last at every node. Measured on `partial_grid`'s
#: source with TEAPOT cut back to TEAPO: 1,859 nodes to a conforming grid
#: unranked, 8 ranked. Without a partial run it is one value for every
#: candidate, so no other walk moves.
_COMPLETES_PARTIAL = 0
_LEAVES_PARTIAL = 1

#: Rank of a candidate whose answer is a bare feature not yet on the board, and
#: of any other. Past the seed slot a bare feature can only be crossed in, and
#: ranked by cells alone a short one is tried last at every node.
_BARE_FEATURE = 0
_OTHER_ANSWER = 1

#: Rank of a candidate whose theme has yet to reach its floor, and of one whose
#: has. Lower sorts first, so the short theme wins: push the search toward the
#: hard constraints rather than stumbling onto them.
_THEME_SHORT = 0
_THEME_SATISFIED = 1

#: One candidate's ascending order key, level by level (see `_sort_key`).
SortKey = tuple[int, int, int, int, bytes]


def order_key(seed: int, token: str) -> bytes:
    """A stable pseudo-random sort key for one candidate under one seed.

    blake2b rather than builtin hash(): hash() is salted by PYTHONHASHSEED and
    varies between processes, which would break the byte-identical guarantee
    between two runs of the same binary on the same machine. Not random.shuffle
    either -- its stability across CPython releases is an implementation detail,
    and this project targets the oldest supported behavior.
    """
    return hashlib.blake2b(
        f"{seed}:{token}".encode("utf-8"), digest_size=_KEY_BYTES
    ).digest()


def _placement_token(placement: cw_place.Placement) -> str:
    """The string identifying one placement uniquely, for `order_key`.

    All four fields, not just the answer: two candidates for the same word must
    not share a key, or the choice between them would fall to the enumeration
    order rather than to the seed -- and the seed is what the operator turns.
    """
    return f"{placement.answer}:{placement.row}:{placement.col}:{placement.direction}"


def _placement_cells(placement: cw_place.Placement) -> tuple[tuple[int, int], ...]:
    """Every cell a placement would occupy, via cw_grid's own geometry.

    Built from a `Run` rather than from a step table of its own: cw_grid is
    this project's single definition of which way ACROSS and DOWN advance, and
    a second copy here would be free to drift from it.
    """
    return cw_grid.Run(
        row=placement.row,
        col=placement.col,
        direction=placement.direction,
        text=placement.answer,
    ).cells


def _new_cell_count(grid: cw_grid.Grid, placement: cw_place.Placement) -> int:
    """How many cells `placement` would NEWLY fill.

    The caller must have established that the placement fits: an out-of-bounds
    cell raises out of `Grid.letter` rather than being counted as empty.
    """
    return sum(
        1 for row, col in _placement_cells(placement) if grid.letter(row, col) is None
    )


def _sort_key(
    placement: cw_place.Placement,
    completes_partial: bool,
    is_bare_feature: bool,
    new_cells: int,
    theme_is_short: bool,
    seed: int,
) -> SortKey:
    """One candidate's ascending order key: ranking first, then the seeded tie-break.

    Five levels: a placement laid along a source's partial run first, then a
    bare feature, then fill more cells, then prefer an answer whose theme has
    yet to meet its floor, then the seeded tie-break. The count is negated
    rather than sorted with `reverse=True`, so every level ascends together --
    reversing would also reverse the tie-break, making the seed's effect depend
    on which level happened to decide.
    """
    return (
        _COMPLETES_PARTIAL if completes_partial else _LEAVES_PARTIAL,
        _BARE_FEATURE if is_bare_feature else _OTHER_ANSWER,
        -new_cells,
        _THEME_SHORT if theme_is_short else _THEME_SATISFIED,
        order_key(seed, _placement_token(placement)),
    )


def _centered_start(
    height: int, width: int, length: int, direction: str
) -> tuple[int, int]:
    """Where an answer of `length` starts so it sits centered in the grid.

    May be negative when the answer is longer than the line it would occupy;
    `cw_place.fits` is what rejects that, so this stays pure arithmetic.
    """
    if direction == cw_grid.ACROSS:
        return ((height - 1) // 2, (width - length) // 2)
    return ((height - length) // 2, (width - 1) // 2)


def _has_letters(rows: Sequence[str]) -> bool:
    """Whether any cell is filled -- the seed slot is 'nothing on the board yet'."""
    return any(cell != cw_grid.BLOCK for row in rows for cell in row)


def _bare_features(config: cw_config.FillConfig) -> tuple[str, ...]:
    """Every featured answer with no anchor, in the order given."""
    return tuple(
        feature.answer for feature in config.features if feature.anchor is None
    )


def _seed_placements(
    grid: cw_grid.Grid, config: cw_config.FillConfig, unused: tuple[str, ...]
) -> list[cw_place.Placement]:
    """The alternatives for the one placement with no crossing to anchor it.

    The bare featured answers take this slot alone when any are nominated:
    each is a hard constraint, so seeding with anything else would
    leave the search free to spend its whole budget on grids that can never
    conform. Otherwise every unused answer is a candidate, and the ranking in
    `ordered_candidates` decides which is tried first.

    Only a BARE feature is ever offered here. A pinned one is already on the
    board before the walk starts, and a board with anything on it has no seed
    slot at all -- `_has_letters` sends every node to `crossing_candidates`
    instead. So a bare feature given beside a pin must be reached by crossing,
    as must every bare feature but the one seeded; `ordered_candidates` is
    what tries those crossings ahead of every other answer's.

    Both orientations are offered at the centered start for the answer's length.
    One of them may start outside the grid -- a seven-letter answer centered
    ACROSS in a five-wide grid begins at column -1 -- and `fits` is what drops
    it, which is why the arithmetic above it need not special-case the shape.

    A `--mask` is the same kind of fact, and is dropped the same way: the center
    of a grid is exactly where a silhouette is most likely to be open, but a
    picture that forbids it leaves this slot empty and the run comes back having
    placed nothing, which is a report rather than a refusal. A mask the operator
    drew is not a promise that some answer can be centered inside it.
    """
    answers = _bare_features(config) or unused
    found: list[cw_place.Placement] = []
    for answer in answers:
        for direction in (cw_grid.ACROSS, cw_grid.DOWN):
            row, col = _centered_start(grid.height, grid.width, len(answer), direction)
            placement = cw_place.Placement(answer, row, col, direction)
            if cw_place.fits(grid, placement, config.masked):
                found.append(placement)
    return found


def _short_themes(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> frozenset[str]:
    """The declared themes still short of their per-theme floor.

    Membership only: `ordered_candidates` asks whether one theme is in here
    and never walks it, so this set cannot leak an order into the search.
    """
    counts = theme_counts(rows, bank)
    return frozenset(
        key for key in bank.themes if counts.get(key, 0) < config.min_entries_per_theme
    )


def _open_partials(
    rows: Sequence[str], config: cw_config.FillConfig, answers: AbstractSet[str]
) -> tuple[cw_grid.Run, ...]:
    """The runs of this board that still leave a `--source` partial run unfinished.

    A run counts when it spells no answer and lies along one of the source's
    partial runs, covering all of it: the partial run itself, or the longer
    unfinished run a step has since grown it into. Empty without a source, and
    for a source holding no partial run, so the level ranks every other walk's
    candidates alike.
    """
    partial = cw_reach.partial_runs(config.start, answers)
    if not partial:
        return ()
    return tuple(
        run
        for run in cw_grid.runs_from_rows(rows)
        if run.text not in answers
        and any(cw_reach.covers(inner, run.cells) for inner in partial)
    )


def ordered_candidates(
    grid: cw_grid.Grid, bank: cw_bank.Bank, config: cw_config.FillConfig
) -> list[cw_place.Placement]:
    """Every placement worth trying from this node, best first.

    Zero-progress candidates are dropped rather than ranked last. Such a
    placement leaves the grid byte-identical, so its child node re-derives its
    own parent's state and the walk never terminates -- a budget would bound
    that, but only by spending the whole budget on one repeated state.

    A placement laid along an unfinished `--source` partial run, and a bare
    feature's crossings, are RANKED first, never offered alone: a ranking only
    orders the walk, and the walk must stay free to lay any other letter. With
    no partial run standing, and every bare feature placed (a feature on the
    board is no candidate, `cw_reach.unused_answers`), each rank is one value
    for all and changes nothing.

    A break the walk made (`cw_reach.walk_breaks`) is the one thing FILTERED
    rather than ranked: while the board holds one, only a placement laid over
    it is offered. The reason a ranking must never become a filter does not
    apply here. The walk stood on this board only because an unused answer could
    still be laid over the break (`cw_reach.step_allowed`), so a repair is there
    to try; and every other placement opens a subtree that must repair the break
    anyway. Measured on a 1,817-answer bank, where nearly every run is one some
    answer could complete, that subtree was one the walk never climbed out of.

    Those placements are BUILT from the break's own line
    (`cw_reach.placements_over`), never filtered out of every crossing on the
    board: the set is the same, and the key below is total, so the order is too.
    Building every crossing to keep the few over a break was nearly all of a
    detour node's cost, and a large fill stands on hundreds of such nodes.
    """
    rows = grid.to_rows()
    unused = cw_reach.unused_answers(rows, bank)
    index = bank.by_answer()
    breaks = cw_reach.walk_breaks(rows, index.keys(), config.start)
    if breaks:
        raw = cw_reach.placements_over(grid, breaks, unused, config.masked)
    elif _has_letters(rows):
        raw = cw_place.crossing_candidates(grid, unused, config.masked)
    else:
        raw = _seed_placements(grid, config, unused)
    short = _short_themes(rows, bank, config)
    open_partials = _open_partials(rows, config, index.keys())
    bare = frozenset(_bare_features(config))

    def keyed(placement: cw_place.Placement) -> SortKey:
        """This node's ordering key for one candidate."""
        entry = index.get(placement.answer)
        cells = _placement_cells(placement)
        return _sort_key(
            placement,
            any(cw_reach.covers(run, cells) for run in open_partials),
            placement.answer in bare,
            _new_cell_count(grid, placement),
            entry is not None and entry.theme in short,
            config.seed,
        )

    progressing = [
        placement for placement in raw if _new_cell_count(grid, placement) > 0
    ]
    return sorted(progressing, key=keyed)
