"""The grid model: cells, maximal-run derivation, and density.

An entry is derived from the letters, never declared: a maximal line of two or
more filled cells in either direction. Every other
module in this project reads runs through here, so the definition lives in one
place and cannot drift between the search and the emitter.

`Run` is frozen and therefore hashable (`@dataclass(frozen=True)` synthesizes
`__hash__` over all of its fields, the two ints included), which makes
`set(runs)` type-check, but a set's iteration order is
`PYTHONHASHSEED`-dependent, and output must be byte-identical across runs. Keep
runs in the tuple `runs_from_rows` returns (or another order-preserving
container); never route them through a `set` on any path that reaches emitted
output.

`runs_from_rows` is asked about nearly every board the search tries, and a
placement changes only the lines it lies in and crosses, so each line's runs are
remembered by the line itself (`_line_runs`). A remembered answer is the scan's own
answer, so nothing a caller sees changes; the cache is keyed by value, so it holds
no order a caller could read.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

import cw_text

#: A blocked cell. "." rather than "#" because it reads as negative space in a
#: row string, which is what makes an emitted grid legible in a diff.
BLOCK = "."

ACROSS = "across"
DOWN = "down"

#: The (row, col) step each direction advances by. A lookup rather than an
#: if/else fallback, so an unrecognized direction raises KeyError loudly instead
#: of being silently treated as DOWN.
_STEPS: dict[str, tuple[int, int]] = {ACROSS: (0, 1), DOWN: (1, 0)}

#: A run must be at least this long to be an entry.
MIN_RUN = 2

#: The most cells a grid this tool makes or reads may have in either direction.
#: 25 x 25 is the largest crossword size in common publication, so no grid
#: anyone lays out needs more. It also bounds the work: a search path is at most
#: one placement per cell, three Python frames each, so the cap bounds the depth
#: `cw_search` makes room for; and the passes `preview`, `shade` and `gaps` make
#: over a grid grow faster than its cell count. Held where each size enters
#: (`--rows` and `--cols`, a `--mask` picture, every grid file read), so a
#: refusal names that input.
MAX_SIDE = 25

#: How many distinct lines `_line_runs` remembers. Measured: an 11x11 fill's full
#: look-ahead window met 19,339 distinct lines in about 10 million line reads, and
#: remembering 4,096 of them ran as fast as remembering all of them.
_LINE_CACHE_SIZE = 4096


@dataclass(frozen=True)
class Run:
    """One maximal line of filled cells, with where it starts and what it spells."""

    row: int
    col: int
    direction: str
    text: str

    @property
    def cells(self) -> tuple[tuple[int, int], ...]:
        """Every (row, col) this run occupies, walking its own direction."""
        d_row, d_col = _STEPS[self.direction]
        return tuple(
            (self.row + d_row * offset, self.col + d_col * offset)
            for offset in range(len(self.text))
        )


def _lines_for_direction(
    rows: Sequence[str], direction: str
) -> list[tuple[int, int, str]]:
    """The scan lines for one direction, each as (start_row, start_col, text).

    ACROSS scans each row left-to-right; DOWN scans each column top-to-bottom.
    Expressing both as "the characters along one line, plus that line's starting
    cell" lets `_runs_in_line` do the actual run accumulation once, so the two
    directions can never drift into two subtly different implementations.
    """
    if direction == ACROSS:
        return [(row_index, 0, row) for row_index, row in enumerate(rows)]
    # DOWN: transpose. strict=True makes a ragged grid fail loudly right here
    # (a mismatched row length raises ValueError at the transpose) instead of
    # zip's default silently truncating every column to the shortest row, which
    # would silently drop cells rather than signal the caller's bug.
    columns = zip(*rows, strict=True)
    return [(0, col_index, "".join(column)) for col_index, column in enumerate(columns)]


def _runs_in_line(
    start_row: int, start_col: int, direction: str, line: str
) -> list[Run]:
    """Accumulate maximal non-BLOCK stretches of `line` into Runs of length >= MIN_RUN.

    A single pass with one pending-stretch buffer, flushed whenever a BLOCK cell
    is reached: the shared logic both ACROSS and DOWN scans reduce to via
    `_lines_for_direction`. Scanning `line + BLOCK` rather than `line` appends a
    virtual terminator so a stretch that runs to the end of the line flushes
    through this same branch as every interior one, rather than a second,
    near-identical flush block after the loop: one implementation of "turn a
    stretch into a Run" instead of two that could quietly drift apart.
    """
    d_row, d_col = _STEPS[direction]
    runs: list[Run] = []
    stretch = ""
    for offset, char in enumerate(line + BLOCK):
        if char == BLOCK:
            if len(stretch) >= MIN_RUN:
                stretch_start = offset - len(stretch)
                runs.append(
                    Run(
                        row=start_row + d_row * stretch_start,
                        col=start_col + d_col * stretch_start,
                        direction=direction,
                        text=stretch,
                    )
                )
            stretch = ""
        else:
            stretch += char
    return runs


@functools.lru_cache(maxsize=_LINE_CACHE_SIZE)
def _line_runs(
    start_row: int, start_col: int, direction: str, line: str
) -> tuple[Run, ...]:
    """`_runs_in_line`, remembered for each line's position and contents.

    Keyed on where the line lies as well as what it holds, since a run carries its
    own position. `Run` is frozen, so sharing one between callers is safe.
    """
    return tuple(_runs_in_line(start_row, start_col, direction, line))


def runs_from_rows(rows: Sequence[str]) -> tuple[Run, ...]:
    """Every maximal ACROSS and DOWN run of two-plus filled cells in `rows`.

    Order is deterministic and part of the contract, not an accident of the
    scan: every ACROSS run first, row-major (row 0's runs left-to-right, then
    row 1's, and so on), then every DOWN run, column-major (column 0's runs
    top-to-bottom, then column 1's, and so on). Output must be byte-identical
    across runs of this project, so callers may rely on this order. See the
    module docstring for why a `set` of these must not be used on any path that
    reaches it.
    """
    found: list[Run] = []
    for direction in (ACROSS, DOWN):
        for start_row, start_col, line in _lines_for_direction(rows, direction):
            found.extend(_line_runs(start_row, start_col, direction, line))
    return tuple(found)


def find_answer(rows: Sequence[str], answer: str) -> Run | None:
    """The first run in `rows` whose text equals `answer`, or None."""
    for run in runs_from_rows(rows):
        if run.text == answer:
            return run
    return None


def usable_cells(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]] = frozenset()
) -> tuple[int, int]:
    """`(cells this grid may use, how many of them are BLOCK)`.

    The one place this project's density arithmetic is spelled out. `masked` is
    the cells a `--mask` picture forbids a letter, and they leave both counts:
    density means "of the cells this grid may use, how many are blocked", so a
    cell the operator drew out of the grid is no more a block than it is a
    letter. Counting it as blocked would make every shape "too dense" by
    construction against the default window.

    An unmasked call counts through `str.count`, at C speed, because
    `cw_density.window_miss` asks this of every board the search judges:
    hundreds of thousands of them inside one look-ahead window. The per-cell
    walk is paid only by a run that actually has a mask.

    `masked` is read by membership only. It is iterated nowhere: the walk below
    goes over `rows`, whose order is the grid's, so no hash-seeded order can
    reach an answer.
    """
    if not masked:
        total = sum(len(row) for row in rows)
        return total, sum(row.count(BLOCK) for row in rows)
    total = 0
    blocked = 0
    for row, line in enumerate(rows):
        for col, cell in enumerate(line):
            if (row, col) in masked:
                continue
            total += 1
            blocked += cell == BLOCK
    return total, blocked


def percent_of(blocked: int, total: int) -> float:
    """`blocked` of `total` usable cells as the percentage every report shows.

    For display only: whether a grid is inside the requested window is
    `cw_density`'s question, asked in exact arithmetic, because this float can
    land a hair either side of a bound the grid sits exactly on. A grid's own
    percentage is printed from this figure wherever a report describes the
    grid, so it reads the same in every line; the figures that advise a bound,
    or that must show a miss one decimal would hide, are `cw_density`'s.

    Returns 0.0 when there are no usable cells rather than dividing by zero:
    a grid with no cells has none to be blocked, so "no blocks" is the honest
    answer, not an error. That covers the empty grid and the wholly-masked one
    alike; `cw_mask` refuses the second at the input boundary, so no command
    line reaches it, but the guard costs one comparison and the alternative is
    a crash.
    """
    if total == 0:
        return 0.0
    return blocked / total * 100


def oversize(height: int, width: int) -> str | None:
    """Why a `height` x `width` grid is past `MAX_SIDE`, or None when it is not.

    One clause for every file that can carry a size, so a `--mask` picture and a
    grid file are refused in the same words; each caller names its file.
    """
    if height <= MAX_SIDE and width <= MAX_SIDE:
        return None
    return f"larger than the {MAX_SIDE}x{MAX_SIDE} most a grid may be"


def blocked_percent(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]] = frozenset()
) -> float:
    """Percent of the cells this grid may use that are BLOCK, as `percent_of` shows it.

    `masked` defaults to none, which measures every cell.
    """
    total, blocked = usable_cells(rows, masked)
    return percent_of(blocked, total)


def _validate_row(index: int, row: object, width: int) -> str:
    """Return `row` as a string of `width` cells, or raise ValueError saying why.

    One row's whole rule in one place: it is a string, it is as wide as the
    first row, and every character is BLOCK or a letter A-Z.
    """
    if not isinstance(row, str):
        raise ValueError(f"grid row {index} must be a string, got {cw_text.shown(row)}")
    if len(row) != width:
        raise ValueError(
            f"grid row {index} holds {len(row)} cells, expected {width}: "
            "a grid may not be ragged"
        )
    for col, char in enumerate(row):
        if char != BLOCK and not ("A" <= char <= "Z"):
            raise ValueError(
                f"cell ({index}, {col}) is {cw_text.shown(char)}, expected a "
                f"letter A-Z or {cw_text.shown(BLOCK)}"
            )
    return row


def validate_rows(rows: object) -> tuple[str, ...]:
    """Narrow an untrusted grid payload into rows of cells, or raise ValueError.

    `preview` refuses a source that is not a coherent grid: ragged rows, an
    empty grid, a cell that is neither a letter nor a block. The rule lives
    here, beside `BLOCK` and `Grid`, because what a row
    of cells may contain is this module's own definition; a copy in the reader
    that needs it would be a second statement of it, free to drift from the
    one `Grid` enforces on the writing side.

    Takes `object` and hands back the narrowed tuple rather than taking
    `Sequence[str]`: the caller holds a `json.loads` result, so "a row that is
    not a string" has to stay a case this function can reject instead of one
    the annotation pretends away, and returning the tuple saves that caller
    a cast.

    A list or a tuple is accepted: `json.loads` yields the first, code
    yields the second. A bare `str` is not, even though it satisfies
    `Sequence[str]`: it would read as a one-column grid of its own letters,
    which is the silent wrong answer rather than the loud one.
    """
    if not isinstance(rows, (list, tuple)):
        raise ValueError(
            f"grid rows must be a list or tuple, got {cw_text.shown(rows)}"
        )
    if not rows:
        raise ValueError("grid rows must not be empty: a grid has no cells")
    first = rows[0]
    if not isinstance(first, str) or not first:
        raise ValueError(
            f"grid row 0 must be a non-empty string, got {cw_text.shown(first)}"
        )
    return tuple(
        _validate_row(index, row, len(first)) for index, row in enumerate(rows)
    )


def _validate_letter(letter: str) -> None:
    """Raise ValueError unless `letter` is exactly one character, A-Z.

    A caller that mistakenly passes BLOCK, a lowercase letter, or a multi-
    character string would otherwise corrupt `Grid.to_rows`'s one-character-
    per-cell row-string representation, which every downstream consumer
    (`runs_from_rows`, the emitter) parses on that exact assumption.
    """
    if len(letter) != 1 or not ("A" <= letter <= "Z"):
        raise ValueError(
            f"letter must be exactly one character A-Z, got {cw_text.shown(letter)}"
        )


class Grid:
    """A mutable rows x cols grid of cells, each BLOCK or one letter."""

    def __init__(self, rows: int, cols: int) -> None:
        """Create an all-BLOCK grid of the given size."""
        # Dimensions are stored directly rather than derived from len(self._cells)
        # / len(self._cells[0]): deriving width from the first row would need an
        # extra empty-grid branch (a zero-row grid has no "first row" to measure),
        # for no benefit over just remembering what the caller asked for.
        self._rows = rows
        self._cols = cols
        self._cells: list[list[str]] = [[BLOCK] * cols for _ in range(rows)]

    @property
    def height(self) -> int:
        """The number of rows."""
        return self._rows

    @property
    def width(self) -> int:
        """The number of columns."""
        return self._cols

    def _validate_index(self, row: int, col: int) -> None:
        """Raise ValueError if (row, col) is outside this grid.

        A negative Python list index silently wraps to the far edge instead of
        raising, so an off-by-one in a caller's arithmetic (`cw_search`'s
        backtracking) would write to the wrong row with no signal at all. Checking the range
        explicitly, rather than trusting an IndexError, is what catches that
        wrap: IndexError only fires on the positive-overflow side.
        """
        if not (0 <= row < self._rows) or not (0 <= col < self._cols):
            raise ValueError(
                f"cell ({row}, {col}) is outside a {self._rows}x{self._cols} grid"
            )

    def letter(self, row: int, col: int) -> str | None:
        """The letter at (row, col), or None if that cell is BLOCK."""
        self._validate_index(row, col)
        cell = self._cells[row][col]
        return None if cell == BLOCK else cell

    def set_letter(self, row: int, col: int, letter: str) -> None:
        """Write `letter` into (row, col)."""
        self._validate_index(row, col)
        _validate_letter(letter)
        self._cells[row][col] = letter

    def clear(self, row: int, col: int) -> None:
        """Reset (row, col) back to BLOCK."""
        self._validate_index(row, col)
        self._cells[row][col] = BLOCK

    def to_rows(self) -> tuple[str, ...]:
        """The grid as row strings, the same shape `runs_from_rows` consumes."""
        return tuple("".join(row) for row in self._cells)

    def runs(self) -> tuple[Run, ...]:
        """The runs this grid currently contains, via the pure row-based helper."""
        return runs_from_rows(self.to_rows())
