"""cw_search: deterministic backtracking over placements, under a budget.

This module turns a bank and a configuration into a grid. It owns the search
and its determinism; the constraints it searches toward live in cw_accept,
in both the forms this module needs them. What a single step may leave
behind -- a run an unused answer could still complete -- is cw_reach's
question; every grid this module accepts or returns obeys the one rule in full.
Which placements a node tries, and in what order, is cw_order's. Which of
several conforming grids it keeps is cw_select's.

DETERMINISM IS THE GUARANTEE THIS MODULE EXISTS TO KEEP, and it is exactly
this:

    Given the same seed, bank and configuration, any run that exits 0 emits a
    byte-identical grid. The budgets can only decide WHETHER the search reaches
    that grid, never WHICH grid it reaches -- with one stated exception.

The exception: a budget that closes the run INSIDE the look-ahead window keeps
the best conforming grid seen so far, which a roomier budget might have bettered.
That is inherent to choosing among grids within a window at all, so it is made
visible rather than hidden: `SearchOutcome.look_ahead_cut` says so and the report
repeats it. A step cap that does it is still a function of the inputs; a clock
that does it is not, which is why every committed sample pins `--time-budget 0`.

`DETOUR_BUDGET` is not one of those budgets. It belongs to the walk, as fixed as
the ranking: a node count no request can change, so the same request always gives
up the same detours and reaches the same grid.

That holds only because node order is a pure function of the inputs -- a slower
machine explores the same nodes in the same order and simply stops sooner. So
nothing here may take an ordering from a `set`, from a dict built out of one,
or from the builtin `hash()`; see `cw_order.order_key` for why, and cw_grid's
module docstring for the same rule stated for runs. Every set in this file is a
membership test that is never iterated, and every returned order comes from a
list or tuple built beside it.

Recursion depth is the placements on one path, `FRAMES_PER_PLACEMENT` frames
each, and a path holds at most one placement per cell, because a candidate
that would fill none is dropped before it is tried (see
`cw_order.ordered_candidates`). `cw_grid.MAX_SIDE` caps that at 625
placements, which could pass the interpreter's default limit of 1,000 frames,
so `search` first raises the limit to what its grid can need
(`_room_to_recurse`). Real paths are far shallower, because a placement fills
several cells rather than one; and a grid of 300 cells or fewer needs no raise
at all.
"""

from __future__ import annotations

import math
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import cw_bank
import cw_board
import cw_config
import cw_grid
import cw_order
import cw_place
import cw_reach
import cw_select
import cw_text
from cw_accept import longest_line, preflight

#: The best-effort rank of a stand-in for "no grid at all". Every rank
#: `cw_select.snapshot` computes is a theme count of zero or more, a negated
#: finite distance, and a run count of zero or more, so this sits below all of
#: them and the first legal state the walk reaches replaces it.
_NO_GRID_RANK = (-1, -math.inf, -1)

#: How many broken boards one detour may stand on before the walk gives it up.
#: A detour opens where a step leaves a board holding a break the walk made
#: (`cw_reach.walk_breaks`) from one that held none. Every broken board inside
#: it spends one, siblings included; a whole board reached inside it spends
#: nothing, and a break below that board opens a detour of its own.
#: Measured rather than guessed. The longest detour found to lead to a grid cost
#: 33 broken boards, on a dense 6x6 that a budget of 32 lost; on a 9x9 of a
#: 1,817-answer bank the longest cost 19. Detours that led nowhere ran to 92, 302
#: and nearly a thousand. 48 clears the longest by half again. 64 was measured
#: too: the same grids on that bank, its slowest first grid about three seconds
#: later.
DETOUR_BUDGET = 48

#: Frames one placement adds: `_expand`, `_judge_and_walk`, `_try_placement`, once each.
FRAMES_PER_PLACEMENT = 3

#: Frames beneath and above the levels -- the caller's stack, a node's own
#: calls -- with room to spare.
FRAMES_OUTSIDE_THE_WALK = 100


@dataclass(frozen=True)
class SearchOutcome:
    """What one search produced: a grid, how it got there, and how it ended.

    `rows` is always a grid of the requested size, even when the search was
    refused before it started -- a caller writing best-effort output on exit 1
    must never have to special-case an absent grid.

    `placed` is the placement history, in the order applied. The grid's own
    runs (`cw_grid.runs_from_rows`) are the authoritative entry set: one
    placement can create more than one entry, and an entry can arrive for free.

    `compared` counts the distinct conforming grids the look-ahead chose among,
    and `look_ahead_cut` says a budget stopped it before its window closed.
    """

    rows: tuple[str, ...]
    placed: tuple[cw_place.Placement, ...]
    conforming: bool
    missed: tuple[str, ...]
    steps: int
    compared: int = 0
    look_ahead_cut: bool = False


@dataclass
class _SearchState:
    """Everything one running search mutates.

    Not frozen, deliberately: the grid, the placement stack, the step count and
    the best state seen all advance as the walk proceeds. `allowed` is a
    membership set that is never iterated; `holders` is
    `cw_reach.holders_by_fragment` over the bank, built once because every
    tried step that breaks the rule reads it; `pinned` is the exact run each
    source entry and pin must stay after every placement, and `growable` the
    source entries `--absorb-entries` lets grow instead; `selection` holds the
    conforming grids compared so far. `detours` holds, innermost last, how many
    broken boards each detour open along the current path has spent
    (`DETOUR_BUDGET`).
    """

    bank: cw_bank.Bank
    config: cw_config.FillConfig
    clock: Callable[[], float]
    started: float
    grid: cw_grid.Grid
    allowed: frozenset[str]
    holders: Mapping[str, tuple[str, ...]]
    pinned: tuple[cw_grid.Run, ...]
    growable: tuple[cw_grid.Run, ...]
    placed: list[cw_place.Placement]
    steps: int
    best: cw_select.Snapshot
    selection: cw_select.Selection
    stopped: bool
    detours: list[int]


def _budget_spent(state: _SearchState) -> bool:
    """Whether either budget has run out, latching `state.stopped` when it has.

    Called exactly once per node, before anything else, so a run under an
    injected clock reads it a predictable number of times. The step budget is
    checked first and short-circuits the clock reading: `--max-steps` exists
    precisely so a test can pin a deterministic node budget instead of a wall
    clock.

    **Zero means "no limit" on BOTH budgets**, and the symmetry is load-bearing
    rather than tidy. A step cap alone cannot make a run reproducible: this is
    an `elif`, so whenever the cap has not yet fired the clock is still read,
    and a search that merely runs SLOWLY then returns a different -- worse --
    grid rather than a later one. Dropping the clock is what lets a caller ask
    for a result that is a function of the bank and the seed alone, which is
    what every committed sample needs. `cw_config` refuses the one combination
    this opens up, both budgets zero, so nothing here can run unbounded.

    The boundary: the count is incremented BEFORE this test, so the node that
    reaches `--max-steps N` is cut before it does any work, leaving **N-1**
    productive nodes. `1` is therefore the smallest budget that terminates and
    does nothing at all, not the one that tries a single placement.

    The look-ahead window (`cw_select.Selection`) is the third stop. It is a
    node count too, so it is checked before the clock and costs no clock read.
    """
    config = state.config
    if config.max_steps and state.steps >= config.max_steps:
        state.stopped = True
    elif state.selection.closed(state.steps):
        state.stopped = True
    elif config.time_budget and state.clock() - state.started >= config.time_budget:
        state.stopped = True
    return state.stopped


def _try_placement(
    state: _SearchState, placement: cw_place.Placement, on_detour: bool
) -> None:
    """Apply, check the step, recurse, and undo exactly what was filled.

    The check is whole-grid after every tentative placement, not incremental
    bookkeeping -- but it is `cw_reach.step_allowed`, not the rule in full. The
    grid may hold a run an unused answer could still complete, which is what
    lets the walk reach interlocked grids; `_judge_and_walk` is where the rule
    applies in full. The undo runs on the way out of a SUCCESSFUL
    branch too: every snapshot kept holds its own copy of the rows, so
    leaving the grid as it was found keeps every frame's state honest.

    `on_detour` says whether the board this step leaves holds a break the walk
    made, which is how the node below knows whether it opens a detour or spends
    from one already open.
    """
    filled = cw_place.apply_placement(state.grid, placement)
    state.placed.append(placement)
    rows = state.grid.to_rows()
    if cw_reach.step_allowed(rows, state.allowed, state.pinned, state.holders):
        _expand(state, on_detour)
    state.placed.pop()
    cw_place.undo_placement(state.grid, filled)


def _expand(state: _SearchState, parent_on_detour: bool) -> None:
    """One node: the step budget, then the detour budget, then the node's work.

    The step budget is checked before acceptance, so a run cut short reports
    the state it actually reached rather than one it was about to.

    A node standing on a break the walk made (`cw_reach.walk_breaks`) is inside
    a detour. The first such board below a whole one opens it, and every such
    board spends one of `DETOUR_BUDGET`; one past the budget does no work at
    all, so the walk goes back toward the whole board the detour left and tries
    that board's next step. The budget is counted in nodes, never seconds, so
    where a detour ends is a function of the request like everything else here.
    """
    state.steps += 1
    if _budget_spent(state):
        return
    rows = state.grid.to_rows()
    on_detour = bool(cw_reach.walk_breaks(rows, state.allowed, state.config.start))
    opens = on_detour and not parent_on_detour
    if opens:
        state.detours.append(0)
    if on_detour:
        state.detours[-1] += 1
    if not on_detour or state.detours[-1] <= DETOUR_BUDGET:
        _judge_and_walk(state, rows, on_detour)
    if opens:
        state.detours.pop()


def _judge_and_walk(
    state: _SearchState, rows: tuple[str, ...], on_detour: bool
) -> None:
    """A node within budget: acceptance, then each candidate in ranked order.

    A conforming state is offered to `state.selection`, and the walk goes on
    below it -- a denser grid may lie deeper -- until the look-ahead window
    closes; a look-ahead of zero closes it at once, keeping the first grid.
    The loop stops as soon as the budget latches: without that, every frame
    still open would start one more child and the step count would overrun its
    own cap.

    A node may stand on a run that is not an answer yet (`_try_placement`), so
    it is judged -- for acceptance and as a best-effort grid alike -- only when
    the rule holds in full. The written grid, its preview and the report all
    come from one of those two, so no partial grid can reach any of them.
    """
    if not cw_place.rule_breaks(rows, state.allowed):
        here = cw_select.snapshot(rows, tuple(state.placed), state.bank, state.config)
        if not here.missed:
            score = cw_select.grid_score(
                rows,
                state.bank,
                state.config.prefer,
                state.growable,
                state.config.prefer_symmetry,
            )
            state.selection.offer(here, score, state.steps)
            if state.selection.closed(state.steps):
                state.stopped = True
                return
        elif here.rank > state.best.rank:
            state.best = here
    for placement in cw_order.ordered_candidates(state.grid, state.bank, state.config):
        _try_placement(state, placement, on_detour)
        if state.stopped:
            break


def _empty_board(config: cw_config.FillConfig) -> tuple[str, ...]:
    """Every cell of the requested size blocked: a grid holding no run at all."""
    return cw_grid.Grid(config.rows, config.cols).to_rows()


def _unfinished_line(run: cw_grid.Run) -> str:
    """The missed-constraint sentence for a `--source` partial run no grid completed."""
    return (
        f"the partial run {cw_text.shown(run.text)} {run.direction} at "
        f"({run.row}, {run.col}) was never completed by a bank answer"
    )


def _first_best(
    rows: tuple[str, ...],
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
    partial: tuple[cw_grid.Run, ...],
) -> cw_select.Snapshot:
    """The best-effort state before the walk takes a step.

    The pinned board, which every state the walk reaches holds -- unless the
    source left a partial run on it. That board breaks the one rule, and so does
    every board holding its letters until the run is finished, so none of them
    may be returned. The stand-in is an empty board naming each run as missed,
    ranked below anything the walk can reach: the first legal state, which has
    finished every run, replaces it.
    """
    if not partial:
        return cw_select.snapshot(
            rows, cw_board.pinned_placements(config), bank, config
        )
    return cw_select.Snapshot(
        rows=_empty_board(config),
        placed=(),
        missed=tuple(_unfinished_line(run) for run in partial),
        rank=_NO_GRID_RANK,
    )


def _room_to_recurse(config: cw_config.FillConfig) -> None:
    """Raise the interpreter's recursion limit to what this grid's walk can need.

    A path holds at most one placement per cell, so the need is
    `FRAMES_PER_PLACEMENT` a cell plus `FRAMES_OUTSIDE_THE_WALK`: 1,975 frames at
    `cw_grid.MAX_SIDE`, past the default limit of 1,000. The frames outside were
    measured at 16 to 21 beneath `search` under a test runner, and 8 above the
    deepest node's `_expand`. Raising the limit costs no C stack, because since
    Python 3.11 a call from Python to Python keeps its frame in heap memory. It
    is never lowered: a higher limit is the caller's own.
    """
    needed = FRAMES_PER_PLACEMENT * config.rows * config.cols + FRAMES_OUTSIDE_THE_WALK
    if sys.getrecursionlimit() < needed:
        sys.setrecursionlimit(needed)


def search(
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
    clock: Callable[[], float] = time.monotonic,
    *,
    kept: tuple[str, ...] = (),
) -> SearchOutcome:
    """Fill a grid from `bank` under `config`, deterministically.

    `clock` is injected so a test can pin the deadline instead of waiting on
    one: a suite that depends on real elapsed time fails on a loaded machine.
    It is read once before the walk starts, and at most once per node
    thereafter -- never per node under `--time-budget 0`.

    `kept` names the entries `bank` carries only because a --source declared
    them (`cw_source.StartSource.kept`). Under `--absorb-entries` every other
    source entry may grow, and a kept one is still held as its exact run.

    Returns the best conforming grid found within `config.look_ahead` nodes of
    the first (`cw_select`), or the best non-conforming one seen, with `missed`
    naming each constraint that state fails. An
    unsatisfiable request comes back with `steps == 0` and pre-flight's reasons
    -- pre-flight refuses it before the search, not after the budget -- and
    with the start rows: an empty board, or the --source grid, never the pinned
    board. That board may be the very thing pre-flight refused, and a
    best-effort write must not put a grid that breaks the one rule on disk.

    A --source grid still holding a partial run (`cw_reach.partial_runs` over
    this bank) breaks that rule too. Its refusal writes an empty board, and so
    does a walk that never finishes the run, naming each one as missed.

    Otherwise the walk starts from `cw_board.pinned_board`, and `placed` opens
    with the pins in flag order, since they were applied first. The pinned
    board is also the first best state: every state the walk reaches holds it.

    Requires a config that passed `cw_config.validate_fill_config` and
    `cw_feature.validate_features`, as the CLI's always has; see
    `cw_board.pinned_board` for what an unvalidated pin does.
    """
    _room_to_recurse(config)
    allowed = frozenset(entry.answer for entry in bank.entries)
    partial = cw_reach.partial_runs(config.start, allowed)
    refusals = preflight(bank, config)
    if refusals:
        return SearchOutcome(
            rows=_empty_board(config) if partial else cw_board.start_rows(config),
            placed=(),
            conforming=False,
            missed=refusals,
            steps=0,
        )
    board = cw_board.pinned_board(config)
    state = _SearchState(
        bank=bank,
        config=config,
        clock=clock,
        started=clock(),
        grid=board,
        allowed=allowed,
        holders=cw_reach.holders_by_fragment(
            tuple(entry.answer for entry in bank.entries),
            longest=longest_line(config),
        ),
        pinned=cw_board.held_runs(config, allowed, frozenset(kept)),
        growable=cw_board.growable_runs(config, allowed, frozenset(kept)),
        placed=list(cw_board.pinned_placements(config)),
        steps=0,
        best=_first_best(board.to_rows(), bank, config, partial),
        selection=cw_select.Selection(config.look_ahead),
        stopped=False,
        detours=[],
    )
    _expand(state, False)
    chosen = state.selection.chosen
    best = chosen if chosen is not None else state.best
    return SearchOutcome(
        rows=best.rows,
        placed=best.placed,
        conforming=not best.missed,
        missed=best.missed,
        steps=state.steps,
        compared=state.selection.compared,
        look_ahead_cut=(
            chosen is not None
            and state.stopped
            and not state.selection.closed(state.steps)
        ),
    )
