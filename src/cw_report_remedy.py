"""cw_report_remedy: the `fill` report's closing block, which turns a miss into a knob.

The report's other blocks describe the bank and the grid that came back; this
one names each constraint that grid missed and then the concrete option to
change for it, and it is empty for a conforming grid. It is a module of its own
because a remedy is a judgment about a miss, tested apart from the blocks that
only describe.

`cw_report.render_report` stays the one orchestrator. This module builds its
closing block under the sourcing and ordering rules that module's docstring
states -- what the grid holds is read back out of it, and every ordering comes
from an ordered source -- and adds one rule of its own:

- **`outcome.missed` is authoritative for the VERDICT.** It is the only record
  of a pre-flight refusal, which comes back with zero steps and the grid the run
  began from, and whose reasons are about the bank rather than about that grid,
  so they are echoed verbatim rather than recomputed.
"""

from __future__ import annotations

from collections.abc import Sequence

import cw_accept
import cw_bank
import cw_config
import cw_density
import cw_grid
import cw_island
import cw_mask
import cw_search

#: Detail lines sit one indent under their heading, as in every report block.
_INDENT = "  "


def _size_clause(verb: str, flags: Sequence[str]) -> str:
    """`, or VERB` and the size `flags`, closing a knob; empty when there are none."""
    return f", or {verb} {' / '.join(flags)}" if flags else ""


def _sized_by_mask(config: cw_config.FillConfig) -> bool:
    """Whether a `--mask` picture fixes the grid's size, so no knob may resize it.

    A --rows or --cols that disagrees with the picture is refused at exit 2
    (`cw_mask.size_disagreement`), in either direction. Read from `mask_size`,
    never `masked`: a picture forbidding no cell is a legal one, and it fixes
    the size all the same.
    """
    return config.mask_size != cw_mask.NO_MASK_SIZE


def _shrinkable(config: cw_config.FillConfig) -> tuple[str, ...]:
    """The size flags a knob may advise SHRINKING: each dimension above the source's own.

    `cw_source.resolve_size` refuses a --rows or --cols under the source's own
    size at exit 2, so a knob may shrink only a dimension grown past it; a grid
    of the source's own size has neither, and a masked grid has neither
    (`_sized_by_mask`). Without a source or a mask, `source_size` is `(0, 0)`
    and both flags qualify. Growing is checked against the grid-size cap
    instead, never the source (`_growable`).
    """
    if _sized_by_mask(config):
        return ()
    sizes = (
        ("--rows", config.rows, config.source_size[0]),
        ("--cols", config.cols, config.source_size[1]),
    )
    return tuple(flag for flag, size, floor in sizes if size > floor)


def _growable(config: cw_config.FillConfig) -> tuple[str, ...]:
    """The size flags a knob may advise GROWING: each dimension under the cap.

    A --rows or --cols past `cw_grid.MAX_SIDE` is refused at exit 2, with or
    without a source, so a knob may grow only a dimension still short of it; a
    grid at the cap both ways has neither, and a masked grid has neither
    (`_sized_by_mask`).
    """
    if _sized_by_mask(config):
        return ()
    sizes = (("--rows", config.rows), ("--cols", config.cols))
    return tuple(flag for flag, size in sizes if size < cw_grid.MAX_SIDE)


def _grid_knobs(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> list[str]:
    """The density and theme knobs, each one arithmetic on `rows`.

    The density knob is offered on the verdict acceptance reached, and its
    figure is the grid's exact share rounded the way that clears the miss:
    rounding to nearest would state a ceiling under the grid or a floor over it.
    """
    knobs: list[str] = []
    miss = cw_density.window_miss(rows, config)
    share = cw_density.blocked_share(rows, config.masked)
    if miss > 0:
        knobs.append(
            "loosen --max-blocked to "
            f"{cw_density.ceil_tenth(share):.{cw_density.DECIMALS}f} or higher"
            + _size_clause("shrink", _shrinkable(config))
        )
    elif miss < 0:
        knobs.append(
            "lower --min-blocked to "
            f"{cw_density.floor_tenth(share):.{cw_density.DECIMALS}f} or lower"
        )
    # The same verdict the theme block reads, not a third spelling of the
    # comparison -- and the count with it, out of one walk. A local
    # `met < config.min_themes` would be CORRECT: it is exactly the negation
    # cw_accept computes. What is wrong with it is that it would be a third
    # unpinned copy of the rule, free to be "tidied" to `<=`, which IS off by
    # one in the direction that hurts: at met == min_themes the floor is met,
    # so `<=` would offer "lower --min-themes" beside a missed list that says
    # nothing about themes -- the density-axis contradiction the boundary check
    # above exists to prevent, arriving on the theme axis.
    met, floor_met = cw_accept.theme_floor_status(rows, bank, config)
    if not floor_met:
        knobs.append(
            f"lower --min-themes to {met}, or lower --min-entries-per-theme, "
            "or add themed answers to the bank"
        )
    # The overrun, not a count compared here: the same single comparison the
    # missed list above was built from, for the reason the theme knob gives.
    over = cw_accept.two_letter_overrun(rows, config)
    if over:
        knobs.append(
            f"loosen --max-two-letter to {over} or higher, "
            "or raise --time-budget or --max-steps"
        )
    return knobs


def _feature_knobs(rows: Sequence[str], config: cw_config.FillConfig) -> list[str]:
    """One knob per featured answer `rows` does not hold, in flag order."""
    return [
        f"place {feature.answer} by raising --time-budget or --max-steps"
        + _size_clause("grow", _growable(config))
        for feature in config.features
        if cw_grid.find_answer(rows, feature.answer) is None
    ]


def _stray_knobs(rows: Sequence[str], config: cw_config.FillConfig) -> list[str]:
    """One knob per stray `rows` still holds, row-major; none without --source.

    Read from `rows`, the grid that came back, never from `config.start`: a
    source letter the fill has since crossed is no stray any more. Only under
    --source, as `cw_accept.missed_constraints` judges strays: during a walk
    nothing else can leave a lone letter on the board.
    """
    if not config.start:
        return []
    return [
        f"add a bank answer that crosses ({row}, {col}), "
        "or remove that letter from --source"
        for row, col, _, _ in cw_island.stray_letters(rows)
    ]


def _knob_lines(
    outcome: cw_search.SearchOutcome,
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
) -> list[str]:
    """The concrete option to change for each constraint this grid misses.

    None at all on a pre-flight refusal. Its reasons are about the BANK, and the
    grid that came back with them was never searched: an empty board, or under
    --source the source itself. A knob read off that grid would clear a
    constraint the echoed reasons above never named -- loosening
    `--max-blocked` to 100 for an empty rectangle, or crossing a stray the
    refusal never judged. What those reasons give instead is the fact about the
    bank that made the request impossible, the half an operator can act on.

    The refusal is recognized by the outcome's own record: `cw_search.search`
    returns `steps == 0` for a refusal alone, since every walk counts its root.
    Not by the grid's shape, because under --source a refusal's grid can hold
    entries and a searched one can hold none. Not by calling
    `cw_accept.preflight` again either: the rule this module's docstring states
    makes the outcome, never a recomputation, the record of a refusal.

    A searched grid holding no entry loses its density and theme knobs, whose
    figures, read off a grid with nothing in it, point at nothing an operator
    can act on. It keeps its feature knobs in either mode, and under --source
    its stray knobs, each the remedy for a constraint the missed list names.
    Neither needs a source-mode or mask check here: each knob already names
    only flags its own mode accepts (`_shrinkable`, `_growable`, and
    `_stray_knobs`' own guard), and a masked run accepts no resize at all.
    """
    if outcome.steps == 0:
        return []
    rows = outcome.rows
    named = _feature_knobs(rows, config) + _stray_knobs(rows, config)
    if cw_grid.runs_from_rows(rows):
        return _grid_knobs(rows, bank, config) + named
    return named


def remedy_lines(
    outcome: cw_search.SearchOutcome,
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
) -> list[str]:
    """On a miss, every missed constraint and then the knob that would clear it.

    The reasons are echoed from `outcome.missed` rather than recomputed: for a
    grid the search actually walked the two agree (both are
    `cw_accept.missed_constraints` of the same inputs), but for a pre-flight
    refusal only `outcome.missed` knows that the fault is in the bank.
    """
    if outcome.conforming:
        return []
    lines = ["NOT CONFORMING - missed:"]
    lines.extend(f"{_INDENT}{reason}" for reason in outcome.missed)
    knobs = _knob_lines(outcome, bank, config)
    if knobs:
        lines.append("What would clear each:")
        lines.extend(f"{_INDENT}{knob}" for knob in knobs)
    return lines
