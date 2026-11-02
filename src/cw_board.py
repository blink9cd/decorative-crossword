"""cw_board: the board a `fill` run starts from, and the runs it must keep.

Every search starts from one board (the `--source` rows, or an empty grid,
with each pin applied over it) and must keep some runs of that board exactly
as they are. Both are stated here once, because more than one module needs
them and must not build them two ways: `cw_accept`'s pre-flight judges the
board against the one rule, `cw_search` walks outward from it, and a refusal
writes the rows it began from.

Kept apart from `cw_accept`, whose question is which constraints a grid meets:
this module holds no constraint, only the board those constraints are judged
on.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet

import cw_config
import cw_grid
import cw_place


def pinned_placements(config: cw_config.FillConfig) -> tuple[cw_place.Placement, ...]:
    """Each pinned feature as the placement that puts it on the board, in flag order."""
    return tuple(
        cw_place.Placement(
            feature.answer,
            feature.anchor.row,
            feature.anchor.col,
            feature.anchor.direction,
        )
        for feature in config.features
        if feature.anchor is not None
    )


def start_rows(config: cw_config.FillConfig) -> tuple[str, ...]:
    """The grid a run begins from before any pin: the --source rows, or an empty board.

    Public because a refusal writes it: under --source the operator's own grid,
    which the source checks made legal, never the pinned board that may not be.
    A source still holding a partial run is the one exception, and `cw_search`
    writes an empty board for it instead: that run breaks the one rule.
    """
    if config.start:
        return config.start
    return cw_grid.Grid(config.rows, config.cols).to_rows()


def pinned_board(config: cw_config.FillConfig) -> cw_grid.Grid:
    """The grid every search under `config` starts from: each pin, applied.

    Empty when nothing is pinned and no source was given. Under --source the
    board starts from the source, and each pin is applied over it. Public
    because two modules need this board and must not build it two ways:
    `cw_accept.preflight` judges it against the one rule, and `cw_search`
    walks outward from it.

    Requires a config that passed `cw_config.validate_fill_config` and
    `cw_feature.validate_features`. A pin that runs off the grid or contradicts
    another raises ValueError out of `cw_place.apply_placement`'s own guard,
    which that validation makes unreachable, so reaching it means a caller
    skipped the check.
    """
    board = cw_grid.Grid(config.rows, config.cols)
    for row, line in enumerate(start_rows(config)):
        for col, cell in enumerate(line):
            if cell != cw_grid.BLOCK:
                board.set_letter(row, col, cell)
    for placement in pinned_placements(config):
        cw_place.apply_placement(board, placement)
    return board


def pinned_runs(config: cw_config.FillConfig) -> tuple[cw_grid.Run, ...]:
    """The run each pin must stay, exactly: its answer at its anchor, in flag order.

    Public because a pin is kept by holding this run, not merely its cells: a
    placement can leave every pinned cell alone and still end the pin, by
    filling the cell just past it and turning JANE into JANET. So
    `cw_accept.missed_constraints` accepts a pinned feature only as this exact
    run, and `cw_search` refuses any placement after which one is no longer
    present.
    """
    return tuple(
        cw_grid.Run(
            row=placement.row,
            col=placement.col,
            direction=placement.direction,
            text=placement.answer,
        )
        for placement in pinned_placements(config)
    )


def growable_runs(
    config: cw_config.FillConfig, allowed: AbstractSet[str], kept: AbstractSet[str]
) -> tuple[cw_grid.Run, ...]:
    """Every --source entry `--absorb-entries` lets grow, in scan order; none without it.

    An entry the bank holds: a run `allowed`, the search bank, spells that is
    not in `kept`, the entries carried in only because the source's clues
    declare them. A kept entry never grows, because absorbing it would retire
    the one thing vouching for it and leave it as vocabulary from outside the
    curated bank.

    Growing means a longer answer comes to cover every cell of the entry, so
    the entry is no longer a run of its own. Letters never move, so that answer
    holds the entry's letters at the entry's own cells.
    """
    if not config.absorb_entries:
        return ()
    return tuple(
        run
        for run in cw_grid.runs_from_rows(config.start)
        if run.text in allowed and run.text not in kept
    )


def held_runs(
    config: cw_config.FillConfig,
    allowed: AbstractSet[str],
    kept: AbstractSet[str] = frozenset(),
) -> tuple[cw_grid.Run, ...]:
    """Every run the walk must keep exactly: each --source entry not growable, then each pin.

    A source entry is a run `allowed` (the search bank) spells: a bank
    answer, or one kept from the source. A partial run spells none, and the fill
    must complete it, which holding it exactly would forbid; so it is left out
    (`cw_reach.partial_runs`), and only the rule and its letters bind it. So is
    an entry `growable_runs` lets grow, which the rule alone binds as well.

    Every pin is held, whatever the flags say: a pin is where the operator put
    an answer, and JANET over a pinned JANE is the fault this hold exists for.

    Separate from `pinned_runs`, which `cw_accept`'s feature check walks in step
    with the pinned features and must hold pins alone.
    """
    growable = growable_runs(config, allowed, kept)
    entries = tuple(
        run
        for run in cw_grid.runs_from_rows(config.start)
        if run.text in allowed and run not in growable
    )
    return (*entries, *pinned_runs(config))
