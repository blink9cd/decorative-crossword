"""cw_report_choice: the `fill` report blocks about how the written grid was chosen.

Kept apart from `cw_report` on the one seam these blocks share: each describes
what happened once the search had conforming grids in hand (which one was kept
and by what order, which preferred answers it holds, how its worst entry is
rated, how balanced it is under `--prefer-symmetry`, and which lone letters were
laid on it afterward) rather than how the grid measures against the bank and
the request. That is also why each is empty for a best-effort miss, which was
not chosen among anything and had nothing laid on it.

The rating lines appear only when the bank rates at least one answer. A bank
that rates nothing ties every grid on the rating level, so naming that level
would describe a comparison that decided nothing. The symmetry lines appear
only under `--prefer-symmetry`, for the same reason.

`cw_report.render_report` stays the one orchestrator. This module only builds
blocks for it, under the sourcing and ordering rules that module's docstring
states: what the grid holds is read back out of it, and every ordering comes
from an ordered source.
"""

from __future__ import annotations

from collections.abc import Sequence

import cw_bank
import cw_config
import cw_grid
import cw_search
import cw_select
import cw_symmetry

#: Detail lines sit one indent under their heading, as in every report block.
_INDENT = "  "

#: The rating level's words in the chosen sentence, spliced in only when the bank
#: rates an answer. The order the sentence describes is `cw_select.grid_score`'s.
_RATING_LEVEL = "then worst rating, "

#: The symmetry level's words, spliced in only under `--prefer-symmetry`, where
#: `cw_select.grid_score` ranks it: after the worst rating, before themes.
_SYMMETRY_LEVEL = "then {kind} symmetry, "

#: The kept-entry level's words, closing the chosen sentence only under
#: `--absorb-entries`: without it the level ties every grid and decides nothing.
_ABSORB_LEVEL = ", then fewest absorbed --source entries"


def _rates_any(bank: cw_bank.Bank) -> bool:
    """Whether the bank rates at least one answer: what turns the rating lines on."""
    return any(entry.rating is not None for entry in bank.entries)


def _worst_rating_line(rows: Sequence[str], bank: cw_bank.Bank) -> str:
    """The grid's worst rating, and which of its entries hold it.

    The figure is `cw_select.worst_rating`'s, the one the choice was made on.
    Rated entries at the worst are named in bank order, the order every other
    list in the report follows. Unrated entries are counted rather than named,
    and only when the worst is the neutral rating they count as: below it they
    are not the worst, and above it none can be in the grid.
    """
    worst = cw_select.worst_rating(rows, bank)
    runs = cw_grid.runs_from_rows(rows)
    present = {run.text for run in runs}  # membership only, never iterated
    named = [
        entry.answer
        for entry in bank.entries
        if entry.answer in present and entry.rating == worst
    ]
    parts = [", ".join(named)] if named else []
    if worst == cw_bank.NEUTRAL_RATING:
        rating_of = {entry.answer: entry.rating for entry in bank.entries}
        unrated = sum(1 for run in runs if rating_of.get(run.text) is None)
        if unrated:
            parts.append(
                f"{unrated} unrated answer(s), which count as {cw_bank.NEUTRAL_RATING}"
            )
    return f"Worst rating in the grid: {worst} ({', and '.join(parts)})."


def _symmetry_line(rows: Sequence[str], kind: str) -> str:
    """How many of the grid's partner-cell pairs match under `kind`.

    Read off the rows the search chose, which is the figure the choice was made
    on: island letters are laid afterward, on another copy, and would change the
    pattern they fill.
    """
    matched, total = cw_symmetry.matching_pairs(rows, kind)
    return f"{kind.capitalize()} symmetry: {matched} of {total} cell pairs match."


def selection_lines(
    outcome: cw_search.SearchOutcome,
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
) -> list[str]:
    """How the grid was chosen, and its preferred answers, worst rating and balance.

    Only for a conforming grid: a best-effort miss was not chosen among
    anything. The comparison line appears only when a look-ahead ran, and says
    when a budget cut it short, because a grid chosen from a window that closed
    early may not be the one a full window would have kept. The worst-rating
    line does not wait for a look-ahead: like the preferred answers, it
    describes the grid rather than a comparison. It is left out for a grid
    holding no entries, where a worst rating would describe nothing. The
    symmetry line does not wait for one either, and is left out without
    `--prefer-symmetry`.
    """
    if not outcome.conforming:
        return []
    rated = _rates_any(bank)
    lines: list[str] = []
    if config.look_ahead:
        cut = (
            ", cut short by --max-steps or --time-budget"
            if outcome.look_ahead_cut
            else ""
        )
        level = _RATING_LEVEL if rated else ""
        kind = config.prefer_symmetry
        balance = "" if kind is None else _SYMMETRY_LEVEL.format(kind=kind)
        absorb = _ABSORB_LEVEL if config.absorb_entries else ""
        lines.append(
            f"Chosen as the best of {outcome.compared} conforming grid(s) found "
            f"within {config.look_ahead} node(s) of the first{cut}: most letters, "
            f"then --prefer answers, {level}{balance}then themed entries{absorb}."
        )
    if config.prefer:
        placed = [
            answer
            for answer in config.prefer
            if cw_grid.find_answer(outcome.rows, answer) is not None
        ]
        lines.append(
            f"Preferred answers placed: {', '.join(placed) or 'none'} "
            f"({len(placed)} of {len(config.prefer)})."
        )
    if rated and cw_grid.runs_from_rows(outcome.rows):
        lines.append(_worst_rating_line(outcome.rows, bank))
    if config.prefer_symmetry is not None:
        lines.append(_symmetry_line(outcome.rows, config.prefer_symmetry))
    return lines


def island_lines(
    outcome: cw_search.SearchOutcome,
    config: cw_config.FillConfig,
    islands: Sequence[tuple[int, int, str]],
    declined: Sequence[tuple[int, int, str]] = (),
) -> list[str]:
    """The lone letters laid in islands, those `--min-blocked` declined, or a plain none.

    Absent when islands were not asked for, or when the grid missed and so none
    were laid: saying "none" there would claim a search for islands that never
    ran. A declined island is named by its cell, because "no blocked cell
    touches a letter only at a corner" would be false of a grid where one does.
    """
    if not config.island_letters or not outcome.conforming:
        return []
    cells = ", ".join(f"({row}, {col})" for row, col, _ in declined)
    why = (
        f"each would take the grid under the requested {config.min_blocked:.1f}% "
        f"floor: {cells}."
    )
    if not islands:
        if declined:
            return [f"Islands: none laid, since {why}"]
        return [
            "Islands: none, since no blocked cell touches a letter only at a corner."
        ]
    laid = ", ".join(f"{letter} at ({row}, {col})" for row, col, letter in islands)
    lines = [
        f"Islands (lone letters in no entry, laid after the grid was chosen): {laid}."
    ]
    if declined:
        lines.append(f"{_INDENT}Not laid, as {why}")
    return lines
