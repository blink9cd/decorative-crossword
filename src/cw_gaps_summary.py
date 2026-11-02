"""cw_gaps_summary: the head of the `gaps` report, and the tiers it counts in.

The summary states the grid (its size, its density, and the cells `--mask`
took out of it), then the vocabulary the search was handed, how the blocked
cells split into tiers, and the `--max-blocked` that would let `fill` reach for
one of them. `cw_gaps_report` renders the rest of the report, which lists the
gaps tier by tier. Which gaps a run lists at all (`listable`) is decided here,
because the headline and that advice both depend on it.

**A count that is not accounted for is a count that misleads**, a rule borrowed
from `cw_shade_report` rather than re-decided. The headline splits every
blocked cell it counts into exactly one tier, and those tiers add up to the
blocked count it prints (`tests/test_gaps_report.py` pins that they do, with
a mask and without), so a reader can act on the headline instead of
recounting the grid. A masked cell is in neither, and is counted on a line of
its own after the tiers.

The tier vocabulary lives here because both halves use it: the summary counts
in it and the listing sorts by it. Kept here, it lets the imports run one way:
the listing takes it from this module, and this module takes nothing from the
listing.
"""

from __future__ import annotations

from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from fractions import Fraction

import cw_config
import cw_density
import cw_gaps
import cw_grid
import cw_text

#: Detail lines sit one indent under the heading that introduces them, the same
#: width `cw_report` and `cw_shade_report` use, so all three read as one tool.
_INDENT = "  "

#: What three of the tiers cost the operator, each worded once. The tier's
#: headline label below, the heading of its block in the listing and, for the
#: absorbing tier, the line counting those the listing left out are all built
#: from it, so they cannot come to name different things.
ONE_ANSWER = "one new answer"
TWO_ANSWERS = "two new answers"
ABSORBING = "would absorb an existing answer"

#: The tiers every unmasked blocked cell falls into, exactly one each;
#: `MASKED_TIER` below takes the rest. Public because the headline prints them
#: and the tests assert the split adds up: naming them once here gives the
#: headline and the tests one spelling to read. The listing sorts by them too,
#: and builds each block's heading from the same wording: `READY_TIER` itself,
#: or the phrase above that the label is built from.
READY_TIER = "ready now"
ONE_ANSWER_TIER = f"needing {ONE_ANSWER}"
TWO_ANSWER_TIER = f"needing {TWO_ANSWERS}"
ABSORBING_TIER = f"that {ABSORBING}"
ORPHAN_TIER = "whose letter would join no entry"

#: Not an ask and not a cost: a cell the operator drew out of the grid. The
#: headline's count leaves it out, so it is printed apart from the five tiers.
MASKED_TIER = "that --mask forbids a letter"

#: Percentages are printed to one decimal throughout this project (see
#: `cw_report`'s "24.7% blocked"), and the ceiling advice is rounded up to the
#: place `cw_density` rounds it to, which is where this precision is read from.
#: Rounding it down would print a ceiling that refuses the very grid it was
#: printed to ask for.
_PERCENT_DECIMALS = cw_density.DECIMALS


def _tier_of(resolution: cw_gaps.Resolution) -> str:
    """Which tier one resolved candidate belongs to.

    Absorption is tested first and therefore outranks readiness: a fill that
    retires an answer the operator curated is a different kind of cost from one
    that adds a word, and no amount of "you already have the words" makes
    losing two entries the cheap move.
    """
    if resolution.candidate.absorbed:
        return ABSORBING_TIER
    if resolution.new_words == 0:
        return READY_TIER
    if resolution.new_words == 1:
        return ONE_ANSWER_TIER
    return TWO_ANSWER_TIER


def tier_counts(search: cw_gaps.GapSearch) -> dict[str, int]:
    """Every blocked cell the headline counts, split into its tier.

    Insertion-ordered, and the order is the headline's: cheapest ask first,
    then the two tiers that are costs rather than asks. The orphan count comes
    straight from the analysis, which is what makes the figures partition the
    headline's count rather than merely resemble it; a masked cell is in none
    of them.
    """
    counts = {
        READY_TIER: 0,
        ONE_ANSWER_TIER: 0,
        TWO_ANSWER_TIER: 0,
        ABSORBING_TIER: 0,
        ORPHAN_TIER: len(search.analysis.orphans),
    }
    for resolution in search.resolutions:
        counts[_tier_of(resolution)] += 1
    return counts


def listable(
    search: cw_gaps.GapSearch, config: cw_config.GapsConfig
) -> tuple[cw_gaps.Resolution, ...]:
    """The ranked resolutions this run will list, before `--top` caps them.

    One function rather than a rule the report and the CLI each apply: the exit
    code says whether this run found anything, and a report that listed
    something while the exit code said nothing was found (or the reverse)
    would be worse than either being wrong alone.
    """
    if config.include_absorbing:
        return search.resolutions
    return tuple(
        resolution
        for resolution in search.resolutions
        if not resolution.candidate.absorbed
    )


def ceiling_for(*, blocked: int, total: int) -> Fraction:
    """The `--max-blocked` at which `fill` would reach for one more filled cell.

    `fill` accepts a grid at or under its ceiling, so a ceiling set to the
    denser grid's own share accepts that grid and rejects today's, which is
    the whole of the advice, derived rather than guessed. The share is exact
    and rounded up to a tenth by `cw_density`, the module that judges the
    ceiling, so the number a reader copies is one that rule accepts.
    """
    return cw_density.ceil_tenth(cw_density.percent(blocked - 1, total))


def _grid_shape(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]] = frozenset()
) -> tuple[int, int, int, int]:
    """The grid's rows, columns, blocked-cell count and the cells it may use.

    The width is the longest row rather than the first, matching how `cw_svg`
    captions a grid and how `cw_shade_report` measures one.

    The last two come from `cw_grid.usable_cells`, the one place this project
    spells out its density arithmetic, so a `--mask` is applied to it once
    rather than at each call site.
    """
    cols = max((len(row) for row in rows), default=0)
    total, blocked = cw_grid.usable_cells(rows, masked)
    return len(rows), cols, blocked, total


def _vocabulary_line(search: cw_gaps.GapSearch) -> str:
    """How many answers the resolver was handed, or that it was handed none.

    "No vocabulary was supplied" and "none of your words matched" are different
    sentences about different things (the run's inputs, and the operator's
    bank), and a reader who was told the second when the first was true would
    go looking for a shortage that does not exist.
    """
    if search.vocabulary_size == 0:
        return (
            "Vocabulary: no vocabulary supplied, so every demand below is "
            "reported as unmet. Pass --bank or --words to sort them."
        )
    plural = "" if search.vocabulary_size == 1 else "s"
    return f"Vocabulary: {search.vocabulary_size} answer{plural} offered."


def _mask_line(
    rows: Sequence[str], mask_file: str | None, config: cw_config.GapsConfig
) -> list[str]:
    """The `--mask` line: the picture's path and what it forbids; none without one.

    The denominator is the whole grid rather than the usable part, as it is in
    `cw_report`: this line is how a reader learns how many cells left the grid,
    so measuring it over what remains would state the subtraction in terms of
    its own result.

    The numerator is the picture's own count, `config.masked`, not the analysis's
    `masked` count. The two agree only because `cw_gaps_command` refuses a source
    letter in a masked cell: without that check the analysis counts fewer, since
    it classifies blocked cells alone, and this line would claim a cell may never
    hold a letter beside a masked count that did not include it.

    The path is escaped as `cw_report` escapes one (`cw_text.visible`), and for
    the same reason: a file name can hold a character no terminal can take.
    """
    if mask_file is None:
        return []
    cells = sum(len(row) for row in rows)
    return [
        f"From --mask {cw_text.visible(mask_file)}: {len(config.masked)} of "
        f"{cells} cells may never hold a letter."
    ]


def _headline_lines(
    rows: Sequence[str], search: cw_gaps.GapSearch, config: cw_config.GapsConfig
) -> list[str]:
    """Grid size, density, the vocabulary, the tier split, and any masked cells.

    The masked count follows the tiers, unindented: the headline leaves those
    cells out of its blocked count, so a line among the tiers would make them
    add up to more than it. Absent without a mask, where a zero would describe
    a feature the operator is not using.
    """
    height, width, blocked, total = _grid_shape(rows, config.masked)
    percent = cw_grid.blocked_percent(rows, config.masked)
    listed = listable(search, config)
    lines = [
        f"Gaps in a {height}x{width} grid: {blocked} of {total} cells blocked, "
        f"{percent:.{_PERCENT_DECIMALS}f}%.",
        _vocabulary_line(search),
    ]
    if config.top and len(listed) > config.top:
        lines.append(
            f"Showing the {config.top} cheapest of {len(listed)} listed gaps (--top)."
        )
    lines.extend(
        f"{_INDENT}{count} {label}" for label, count in tier_counts(search).items()
    )
    if search.analysis.masked:
        lines.append(
            f"Not counted above: {len(search.analysis.masked)} blocked cell(s) "
            f"{MASKED_TIER}."
        )
    return lines


def _density_lines(
    rows: Sequence[str], search: cw_gaps.GapSearch, config: cw_config.GapsConfig
) -> list[str]:
    """What to re-run so the search actually reaches for one of these gaps.

    The half of the loop a bare list would leave open, and it is not obvious:
    adding the word to the bank may change nothing on its own. `fill` keeps the
    grid with the most letters it finds within `--look-ahead` nodes of the first
    one inside its window; this grid is already in one, and a denser grid that
    needs the new word can lie farther off than that. The ceiling is what makes
    the search reach for it.
    Absent when nothing is listed: advice about gaps the reader cannot see is
    noise.
    """
    if not listable(search, config):
        return []
    _, _, blocked, total = _grid_shape(rows, config.masked)
    # Two figures, because one number cannot be both. The first is the denser
    # grid's own percentage, shown as `fill` would show that grid; the second
    # is the lowest ceiling that admits it, which can be a tenth above.
    denser = cw_grid.percent_of(blocked - 1, total)
    ceiling = ceiling_for(blocked=blocked, total=total)
    return [
        f"Filling any one gap takes this grid to {denser:.{_PERCENT_DECIMALS}f}% "
        "blocked.",
        "`fill` looks only a little past the first grid inside its window, so a new",
        "answer in the bank may change nothing on its own: re-run with",
        f"--max-blocked {ceiling:.{_PERCENT_DECIMALS}f} as well.",
    ]
