"""cw_density: the blocked-cell window, judged in exact arithmetic.

A grid's density is a ratio of two cell counts, and the window it is judged
against is two percentages the operator typed. Binary floating point holds
neither exactly: 28 blocked cells of 100 computes as 28.000000000000004%, so a
float comparison refuses a grid standing exactly on a `--max-blocked 28`
ceiling, while a cell count done the other way calls it within -- two
sentences about one grid, in one report, disagreeing.

So every question about the window is answered here, once, over `Fraction`s:
whether a grid is inside it and by how far it misses (`window_miss`), how many
blocked cells a ceiling allows and a floor requires (`most_blocked`,
`fewest_blocked`), and the one-decimal figure an operator can adopt to clear a
miss (`ceil_tenth`, `floor_tenth`).

A grid's percentage is SHOWN from `cw_grid.percent_of`, to one decimal,
wherever a report describes the grid, so it reads the same in every line. Two
kinds of figure are printed from here instead, because each answers a question
about the window: the advice figures above, rounded the way that clears a
miss, and the figures of a missed-window sentence (`window_figures`), printed
at more places only where one decimal would round a miss onto its bound.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from fractions import Fraction
from typing import NamedTuple

import cw_config
import cw_grid

#: Percent scale: a share of the usable cells times this is what the flags state.
_PERCENT = 100

#: The decimal places an advice figure is rounded to here and printed at by
#: `cw_report_remedy` and `cw_gaps_summary`, stated once so the two cannot
#: part: a ceiling rounded up to hundredths but printed to tenths would print
#: under the very grid it was rounded to admit. `window_figures` starts from it
#: too, the one decimal every report shows a percentage to.
DECIMALS = 1

#: One step in the last printed place, the scale the advice figures are
#: rounded on, in the direction that clears the miss.
_TENTHS = 10**DECIMALS


class WindowFigures(NamedTuple):
    """A grid's blocked percentage and the requested window, as one line prints them."""

    share: str
    floor: str
    ceiling: str


@functools.cache
def _bound(percent: float) -> Fraction:
    """A `--min-blocked` or `--max-blocked` value as the decimal the operator typed.

    Through `str` rather than straight from the float: `str` is the shortest
    decimal that reads back as the same float, which for a value typed with up
    to 15 significant digits is the value typed. `Fraction(12.4)` is instead the
    float's binary value, 12.4000000000000003..., a hair above what was asked,
    and a grid standing exactly on a 12.4% floor would fall short of it.

    Remembered, because the search asks about the same two bounds at every
    node. The value is finite, as `Fraction` requires: the command line refuses
    a non-finite float option before a config is built.
    """
    return Fraction(str(percent))


def percent(blocked: int, total: int) -> Fraction:
    """`blocked` of `total` usable cells as an exact percentage; 0 with no cells.

    Zero for a grid with no usable cells, the answer `cw_grid.percent_of` gives:
    a grid with no cells has none to be blocked.
    """
    if total == 0:
        return Fraction(0)
    return Fraction(blocked * _PERCENT, total)


def blocked_share(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]] = frozenset()
) -> Fraction:
    """The exact percentage of the cells `rows` may use that are blocked."""
    total, blocked = cw_grid.usable_cells(rows, masked)
    return percent(blocked, total)


def window_miss(rows: Sequence[str], config: cw_config.FillConfig) -> Fraction:
    """How far `rows` sits outside the requested window: under 0 below it, over 0 above.

    Zero exactly when the grid is inside, both bounds included -- the one
    statement of acceptance by density. Signed, so a caller that must know WHICH
    bound was missed reads it here rather than comparing a second time.
    """
    share = blocked_share(rows, config.masked)
    floor = _bound(config.min_blocked)
    if share < floor:
        return share - floor
    ceiling = _bound(config.max_blocked)
    if share > ceiling:
        return share - ceiling
    return Fraction(0)


def window_figures(rows: Sequence[str], config: cw_config.FillConfig) -> WindowFigures:
    """`rows`' blocked percentage and the window's two bounds, printed to show a miss.

    To `DECIMALS` places, as every report prints them -- unless the grid misses
    the window and, at that precision, would read as standing on or inside the
    bound it misses: 182 of 625 cells is 29.12%, which one decimal prints as
    the 29.1 ceiling it is over. Then all three are printed at the fewest more
    places that show the miss, from their exact values, so the line compares
    like with like: a bound rounds too, and a 29.16 ceiling prints as 29.2 at
    one decimal. The widening ends, because the share and the bound it misses
    are two different exact numbers, and a bound's own decimal is finite.
    """
    shown = WindowFigures(
        *(
            f"{value:.{DECIMALS}f}"
            for value in (
                cw_grid.blocked_percent(rows, config.masked),
                config.min_blocked,
                config.max_blocked,
            )
        )
    )
    miss = window_miss(rows, config)
    exact = (
        blocked_share(rows, config.masked),
        _bound(config.min_blocked),
        _bound(config.max_blocked),
    )
    places = DECIMALS
    while not _reads_as(shown, miss):
        places += 1
        shown = WindowFigures(*(f"{value:.{places}f}" for value in exact))
    return shown


def _reads_as(shown: WindowFigures, miss: Fraction) -> bool:
    """Whether a reader of `shown` would see the verdict `miss` states.

    Compared as the decimals printed, since that is what a reader compares: a
    share over the ceiling must read as over it, one under the floor as under
    it, and a grid inside the window has no miss to show.
    """
    share = Fraction(shown.share)
    if miss > 0:
        return share > Fraction(shown.ceiling)
    if miss < 0:
        return share < Fraction(shown.floor)
    return True


def most_blocked(total: int, max_blocked: float) -> int:
    """The most blocked cells `total` usable cells may hold under `max_blocked`.

    The count form of `window_miss`'s ceiling: `blocked * 100 / total` is over
    the ceiling exactly when the whole number `blocked` is over
    `total * ceiling / 100`, that is, over its floor.
    """
    return math.floor(total * _bound(max_blocked) / _PERCENT)


def fewest_blocked(total: int, min_blocked: float) -> int:
    """The fewest blocked cells `total` usable cells may hold at `min_blocked` or over.

    The count form of `window_miss`'s floor, as `most_blocked` is of its
    ceiling: `blocked * 100 / total` is under the floor exactly when the whole
    number `blocked` is under `total * floor / 100`, that is, under its ceiling.
    """
    return math.ceil(total * _bound(min_blocked) / _PERCENT)


def ceil_tenth(share: Fraction) -> Fraction:
    """`share` rounded UP to a whole tenth: the lowest `--max-blocked` that admits it.

    Rounding to nearest would turn an achieved 44.44% into 44.4, a ceiling still
    under the grid, which would refuse the very next run.
    """
    return Fraction(math.ceil(share * _TENTHS), _TENTHS)


def floor_tenth(share: Fraction) -> Fraction:
    """`share` rounded DOWN to a whole tenth: the highest `--min-blocked` that admits it."""
    return Fraction(math.floor(share * _TENTHS), _TENTHS)
