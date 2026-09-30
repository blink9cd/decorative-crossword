"""cw_gaps_report: the `gaps` report assembled, and the gaps it lists.

The human-facing product of the subcommand, on stdout, exactly as
`cw_shade_report.render_search_report` is `shade`'s. This module assembles the
whole report and writes everything under its head: the gaps listed tier by
tier, the absorbing ones only when asked for, the answer pairs `cw_pairs`
rendered and the word-list lines that were skipped. It also selects the cells
`--out` marks; the handler in `cw_gaps_command` renders them and writes that
file. The head itself -- the grid, its density, the tier split and the
`--max-blocked` advice, with the arithmetic behind them -- is
`cw_gaps_summary`'s.

One rule runs through both modules, borrowed from `cw_shade_report` rather than
re-decided: **the grid is authoritative.** Every figure here is read off the
rows and the candidates derived from them, never off a record of what a search
believed.

A second rule is this module's own, and it is why the subcommand is worth
having at all: **a wall of coordinates is not a decision.** Every blocked cell
is technically a candidate, so listing them per cell reproduces the problem
`shade` already solved once -- 224 candidates nobody could act on. The output
is therefore grouped by the PATTERN a gap demands, because the operator's unit
of work is the word they have to think of, not the square it lands in: four
cells all wanting a two-letter answer beginning with C are one idea, not four.

Separate from `cw_shade_report` rather than added to it: that module is about a
search for a hidden WORD -- clustering, rows spanned, one shaded cell per
letter -- and none of its blocks or its vocabulary apply here.

Every ordering here comes from an ordered source -- the ranked resolution
tuple, or an explicit slice of it -- because two runs must produce
byte-identical output.
"""

from __future__ import annotations

from collections.abc import Sequence

import cw_config
import cw_gaps
import cw_text
from cw_gaps_summary import (
    _INDENT,
    ABSORBING,
    ABSORBING_TIER,
    ONE_ANSWER,
    ONE_ANSWER_TIER,
    READY_TIER,
    TWO_ANSWER_TIER,
    TWO_ANSWERS,
    _density_lines,
    _headline_lines,
    _mask_line,
    _tier_of,
    listable,
    tier_counts,
)

#: The separator between a listed name and the note explaining it.
_REASON = " - "

#: How many letters one ready gap lists before it says how many more there are.
#: Three because the line is an INVITATION to choose rather than an inventory:
#: the operator needs enough options to recognize one they like, and a gap that
#: ten letters would fit is not ten decisions.
_MAX_FILLS_SHOWN = 3


def _fill_line(resolution: cw_gaps.Resolution, fill: cw_gaps.Fill) -> str:
    """One ready gap and one letter that fills it, with the words it spends."""
    candidate = resolution.candidate
    words = ", ".join(
        f"{demand.direction} {word} at ({demand.row}, {demand.col})"
        for demand, word in zip(candidate.demands, fill.words, strict=True)
    )
    return (
        f"{_INDENT}({candidate.row}, {candidate.col}) take {fill.letter}"
        f"{_REASON}{words}"
    )


def _ready_lines(listed: Sequence[cw_gaps.Resolution]) -> list[str]:
    """The gaps whose answers the operator already holds, letter by letter.

    Capped per gap rather than per report: a gap ten letters would fit is one
    decision with ten options, and printing all of them buries the gap next to
    it. The count of what was left out is printed, so nothing is hidden.
    """
    ready = [resolution for resolution in listed if _tier_of(resolution) == READY_TIER]
    if not ready:
        return []
    lines = [
        f"{READY_TIER.capitalize()}{_REASON}a letter whose answers you already hold:"
    ]
    for resolution in ready:
        shown = resolution.fills[:_MAX_FILLS_SHOWN]
        lines.extend(_fill_line(resolution, fill) for fill in shown)
        remaining = len(resolution.fills) - len(shown)
        if remaining:
            lines.append(
                f"{_INDENT}{_INDENT}... and {remaining} more letter(s) fit here"
            )
    return lines


def _group_key(resolution: cw_gaps.Resolution) -> tuple[str, ...]:
    """What makes two gaps one line: the patterns they demand.

    Direction is deliberately NOT part of the key. `A?` across and `A?` down
    are the same request of the operator -- think of a two-letter answer
    beginning with A -- and splitting them would double a list whose whole
    purpose is to be short.
    """
    return tuple(demand.pattern for demand in resolution.candidate.demands)


def _cells_phrase(members: Sequence[cw_gaps.Resolution]) -> str:
    """How many gaps a group serves, and which cells they are."""
    cells = ", ".join(
        f"({resolution.candidate.row}, {resolution.candidate.col})"
        for resolution in members
    )
    plural = "" if len(members) == 1 else "s"
    return f"{len(members)} gap{plural}: {cells}"


def _grouped(
    listed: Sequence[cw_gaps.Resolution], tier: str
) -> list[tuple[tuple[str, ...], list[cw_gaps.Resolution]]]:
    """One tier's resolutions, gathered by demanded pattern, in rank order.

    A plain dict, which preserves insertion order, so the groups come out in
    the order their cheapest member was ranked -- never in a set's order, which
    must never reach output.
    """
    groups: dict[tuple[str, ...], list[cw_gaps.Resolution]] = {}
    for resolution in listed:
        if _tier_of(resolution) != tier:
            continue
        groups.setdefault(_group_key(resolution), []).append(resolution)
    return list(groups.items())


def _crossing_note(members: Sequence[cw_gaps.Resolution]) -> str:
    """The note a crossing needs, and nothing for a plain miss.

    A crossing is the case that reads wrong without a sentence: the operator
    has a word for each pattern and would reasonably expect the gap to be
    payable. Naming it is what stops them hunting for a shortage that is not
    there.
    """
    if not all(resolution.blocked_by_crossing for resolution in members):
        return ""
    return (
        "you hold a word for each, but no single letter pays both; "
        f"{ONE_ANSWER} in either clears it" + _REASON
    )


def _need_lines(
    listed: Sequence[cw_gaps.Resolution], tier: str, heading: str
) -> list[str]:
    """One tier of gaps, grouped by the pattern each asks the operator to find."""
    groups = _grouped(listed, tier)
    if not groups:
        return []
    lines = [heading]
    for patterns, members in groups:
        lines.append(
            f"{_INDENT}{' + '.join(patterns)}{_REASON}"
            f"{_crossing_note(members)}{_cells_phrase(members)}"
        )
    return lines


def _absorbing_lines(
    listed: Sequence[cw_gaps.Resolution], config: cw_config.GapsConfig
) -> list[str]:
    """The gaps that would retire an existing answer, named only when asked for.

    Off by default and loud when on, mirroring `--exclude-grid-answers`: these
    are the majority of any real grid's blocked cells, and a fill that swallows
    two curated answers to gain one cell is a decision of a different kind from
    everything above it.
    """
    groups = _grouped(listed, ABSORBING_TIER)
    if not config.include_absorbing or not groups:
        return []
    lines = [f"{ABSORBING.capitalize()} (--include-absorbing):"]
    for patterns, members in groups:
        retired = ", ".join(members[0].candidate.absorbed)
        lines.append(
            f"{_INDENT}{' + '.join(patterns)}{_REASON}retires {retired}"
            f"{_REASON}{_cells_phrase(members)}"
        )
    return lines


def _absorbing_hint(
    search: cw_gaps.GapSearch, config: cw_config.GapsConfig
) -> list[str]:
    """One line saying how to see the tier this run left out."""
    hidden = tier_counts(search)[ABSORBING_TIER]
    if config.include_absorbing or not hidden:
        return []
    subject = "gap" if hidden == 1 else "gaps"
    verb = "is" if hidden == 1 else "are"
    return [
        f"{hidden} {subject} {ABSORBING} and {verb} not listed; "
        "--include-absorbing lists them."
    ]


def _skipped_lines(skipped: Sequence[tuple[str, str]]) -> list[str]:
    """Every word-list line that was not usable, named with its reason.

    Never silently drop an ineligible unit: exclude it, report the specific
    reason, and count it.
    """
    if not skipped:
        return []
    return [
        f"Word-list lines skipped ({len(skipped)}):",
        *(
            f"{_INDENT}{cw_text.visible(line)}{_REASON}{reason}"
            for line, reason in skipped
        ),
    ]


def _capped(
    listed: Sequence[cw_gaps.Resolution], config: cw_config.GapsConfig
) -> Sequence[cw_gaps.Resolution]:
    """`--top` applied to the ranked list; zero means every one of them.

    The same reading of zero `--max-steps` and `shade --top` already have, so a
    reader who has learned it once does not have to learn it again.
    """
    if config.top == 0:
        return listed
    return listed[: config.top]


def marked_cells(
    search: cw_gaps.GapSearch, config: cw_config.GapsConfig
) -> tuple[tuple[int, int], ...]:
    """The cells `--out` marks: exactly the gaps this report lists, in rank order.

    Derived from the same `_shown` the report renders from, so the picture and
    the text cannot disagree about which gaps this run is talking about -- a
    render marking a gap the report capped away would be worse than either
    being wrong alone.
    """
    return tuple(
        (resolution.candidate.row, resolution.candidate.col)
        for resolution in _shown(search, config)
    )


def _shown(
    search: cw_gaps.GapSearch, config: cw_config.GapsConfig
) -> Sequence[cw_gaps.Resolution]:
    """The listed gaps this run will actually print: filtered, then capped."""
    return _capped(listable(search, config), config)


def render_report(
    rows: Sequence[str],
    search: cw_gaps.GapSearch,
    config: cw_config.GapsConfig,
    skipped: Sequence[tuple[str, str]],
    pairs: Sequence[str] = (),
    mask_file: str | None = None,
) -> str:
    """Render the whole `gaps` report for one run.

    An orchestrator only: each block is built by its own helper above, blocks
    are separated by a blank line so one can be found by its heading, and an
    empty block drops out rather than leaving a heading with nothing under it
    -- the same shape `cw_report.render_report` and `cw_shade_report` have.
    `pairs` is the answer-pairs block `cw_pairs` rendered for this grid, and is
    empty when the run offered nothing to join into. `mask_file` is the `--mask`
    picture's path as the operator wrote it, or None without the flag; the cells
    it forbids travel on `config`, and only this path has to be carried.
    """
    shown = _shown(search, config)
    blocks: list[list[str]] = [
        # The mask line heads the headline block: it says how many cells the
        # headline's density leaves out.
        [*_mask_line(rows, mask_file, config), *_headline_lines(rows, search, config)],
        _density_lines(rows, search, config),
        _ready_lines(shown),
        _need_lines(shown, ONE_ANSWER_TIER, f"Needs {ONE_ANSWER}{_REASON}by pattern:"),
        _need_lines(shown, TWO_ANSWER_TIER, f"Needs {TWO_ANSWERS}{_REASON}by pattern:"),
        _absorbing_lines(shown, config),
        _absorbing_hint(search, config),
        list(pairs),
        _skipped_lines(skipped),
    ]
    return "\n\n".join("\n".join(block) for block in blocks if block)
