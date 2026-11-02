"""cw_island: lone decorative letters in blocked cells that touch a letter only at a corner.

Every other filled cell this tool writes belongs to an entry. An island is the one
deliberate exception, and it exists for looks: a blocked notch at the edge of a grid's
lettered shape makes the silhouette ragged, and a single letter there fills it. So what
qualifies is kept narrow, and what goes in it must still read as something:

- The cell has no letter above, below, left or right, so its letter joins no run and
  the one rule is untouched; and a letter of the grid as chosen sits at one of its
  corners. Letters placed as islands never qualify a further cell, and nor does a
  lone letter the grid already held (`fixed`), so islands cannot chain out across
  empty space.
- The letter reads as a word on its own (`ISLAND_LETTERS`). It is the first of the
  operator's letters that no touching corner already shows, falling back to the first
  when every one is shown, so an island doubles the letter beside it only when no other
  is left.

Cells are visited row-major and re-checked against the grid as it fills, so of two
neighboring islands only the first takes a letter: two would spell a two-letter run no
bank holds.

A grid carrying an island holds a cell in no entry, the one exception to the rule that
every letter belongs to one; islands stay opt-in because whether a grid wants one is a
judgment about its look, and `fill` lays them only on a grid its search already chose.

`stray_letters` reads the same shape back from a grid alone, for the subcommands that
take a `--source` this tool may never have written. The grid the letters were laid on
is gone by then, so a corner counts only when an entry covers it. The two statements
share `ISLAND_LETTERS` and `_CORNERS` and differ only in what a corner letter must be.
They agree on every grid `fill` lays islands on: there every letter outside `fixed` is
in an entry, and a letter at a `fixed` cell never qualifies a corner, so a corner the
filler counts is one the reader counts too. The property suite holds them to that on
grids whose every letter is in an entry, where nothing is fixed.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from collections.abc import Set as AbstractSet

import cw_config
import cw_grid
import cw_text

#: The letters an island may hold: the two one-letter English words, the letter
#: that marks a spot, and the two that sound like words ("you", "why").
ISLAND_LETTERS = ("A", "I", "X", "U", "Y")

#: Row and column steps to the four cells sharing an edge, and the four sharing
#: only a corner.
_BESIDE = ((-1, 0), (1, 0), (0, -1), (0, 1))
_CORNERS = ((-1, -1), (-1, 1), (1, -1), (1, 1))

#: One placed island: row, column, and the letter laid there.
Island = tuple[int, int, str]

#: One lone letter that is no island: row, column, the letter, and why.
Stray = tuple[int, int, str, str]


# fuzz-target
def parse_island_letters(text: str) -> tuple[str, ...]:
    """Parse `--island-letters`: letters from `ISLAND_LETTERS`, in preference order.

    Case-folded, so `aix` names the same letters as `AIX`. Raises ConfigError,
    naming the flag, on an empty value or on any letter that does not read as a
    word on its own.
    """
    letters = tuple(text.upper())
    if not letters:
        raise cw_config.ConfigError("--island-letters names no letters")
    for letter in letters:
        if letter not in ISLAND_LETTERS:
            raise cw_config.ConfigError(
                f"--island-letters: {cw_text.shown(letter)} is not one of "
                f"{', '.join(ISLAND_LETTERS)}: an island letter must read as a "
                "word on its own"
            )
    return letters


def _around_cells(
    grid: Sequence[Sequence[str]], row: int, col: int, steps: Sequence[tuple[int, int]]
) -> list[tuple[int, int]]:
    """The in-bounds coordinates at `steps` from (row, col), in step order."""
    return [
        (row + d_row, col + d_col)
        for d_row, d_col in steps
        if 0 <= row + d_row < len(grid) and 0 <= col + d_col < len(grid[0])
    ]


def _around(
    grid: Sequence[Sequence[str]], row: int, col: int, steps: Sequence[tuple[int, int]]
) -> list[str]:
    """The cells at `steps` from (row, col) that lie inside `grid`."""
    return [grid[r][c] for r, c in _around_cells(grid, row, col, steps)]


def _island_letter(
    original: Sequence[str],
    current: Sequence[Sequence[str]],
    at: tuple[int, int],
    letters: Sequence[str],
    fixed: AbstractSet[tuple[int, int]],
    masked: AbstractSet[tuple[int, int]] = frozenset(),
) -> str | None:
    """The letter the cell at `at` takes as an island, or None when it is no island.

    Emptiness beside the cell is read from the grid as it is being filled, so a
    neighbor filled a moment ago counts; the corner letter that qualifies it is
    read from the original grid, so an island never qualifies another. A corner
    in `fixed` counts as empty: it was lone before any island was laid, and an
    island beside it would chain off it just as it would off another island.

    A cell in `masked` is no island: a `--mask` picture forbids a letter there,
    and an island is a letter. Ineligible rather than refused: an island is a
    choice this module makes for itself, so a mask takes the cell off the table
    the way blocks beside it already do. A `--feature` pin into the same cell is
    refused instead, because that one the operator wrote themselves.
    """
    row, col = at
    if (row, col) in masked:
        return None
    if current[row][col] != cw_grid.BLOCK:
        return None
    if any(cell != cw_grid.BLOCK for cell in _around(current, row, col, _BESIDE)):
        return None
    # Coordinates rather than `_around`'s letters, because `fixed` names cells.
    corners = _around_cells(original, row, col, _CORNERS)
    if all(original[r][c] == cw_grid.BLOCK or (r, c) in fixed for r, c in corners):
        return None
    shown = _around(current, row, col, _CORNERS)
    return next((letter for letter in letters if letter not in shown), letters[0])


def fill_islands(
    rows: Sequence[str],
    letters: Sequence[str],
    fixed: AbstractSet[tuple[int, int]] = frozenset(),
    masked: AbstractSet[tuple[int, int]] = frozenset(),
    spare: int | None = None,
) -> tuple[tuple[str, ...], tuple[Island, ...]]:
    """Lay a letter in every island of `rows`; return the new rows and each island.

    `letters` must be non-empty, as `parse_island_letters` guarantees. Islands
    come back in the row-major order they were laid. A letter at a `fixed` cell
    never qualifies a corner: pass `lone_cells` of the grid being decorated,
    so a lone letter it already holds is no seed. `fixed` is read for membership
    only, and so is `masked`, the cells a `--mask` picture forbids a letter.

    `spare` is how many blocked cells the grid may give up, or None for no limit.
    Each island takes one, so once `spare` are laid every later island is
    skipped (its cell stays blocked), and the walk goes on, laying nothing.
    """
    original = tuple(rows)
    current = [list(row) for row in original]
    placed: list[Island] = []
    for row in range(len(original)):
        for col in range(len(original[row])):
            letter = _island_letter(
                original, current, (row, col), letters, fixed, masked
            )
            if letter is not None and (spare is None or len(placed) < spare):
                current[row][col] = letter
                placed.append((row, col, letter))
    return tuple("".join(cells) for cells in current), tuple(placed)


def _covered(rows: Sequence[str]) -> frozenset[tuple[int, int]]:
    """Every cell some entry of `rows` reads through. For membership only."""
    return frozenset(cell for run in cw_grid.runs_from_rows(rows) for cell in run.cells)


def _stray_reason(
    letter: str, at: tuple[int, int], covered: AbstractSet[tuple[int, int]]
) -> str | None:
    """Why the lone `letter` at `at` is no island, or None when it is one.

    The letter is checked before the corner, so a letter off the set is named as
    that wherever it lies: moving it would not make it an island.
    """
    if letter not in ISLAND_LETTERS:
        return f"{letter} is not an island letter ({', '.join(ISLAND_LETTERS)})"
    row, col = at
    if not any((row + d_row, col + d_col) in covered for d_row, d_col in _CORNERS):
        return "no letter of an entry touches it at a corner, so it is no island"
    return None


def _lone(
    rows: Sequence[str], covered: AbstractSet[tuple[int, int]]
) -> Iterator[tuple[int, int, str]]:
    """Each filled cell of `rows` outside `covered`, row-major, with its letter."""
    for row, line in enumerate(rows):
        for col, letter in enumerate(line):
            if letter != cw_grid.BLOCK and (row, col) not in covered:
                yield row, col, letter


# fuzz-target
def stray_letters(rows: Sequence[str]) -> tuple[Stray, ...]:
    """Every lone letter of `rows` that is no island, row-major, with the reason.

    A lone letter is a filled cell no entry reads through; nothing beside it
    needs checking, because two orthogonally adjacent letters are already an
    entry. `rows` must be a coherent grid, as `cw_grid.validate_rows` holds a
    loaded one to. Islands are not returned: a grid that holds only those, or
    no lone letter at all, comes back as the empty tuple.
    """
    covered = _covered(rows)
    strays: list[Stray] = []
    for row, col, letter in _lone(rows, covered):
        reason = _stray_reason(letter, (row, col), covered)
        if reason is not None:
            strays.append((row, col, letter, reason))
    return tuple(strays)


def lone_cells(rows: Sequence[str]) -> tuple[tuple[int, int], ...]:
    """Every filled cell of `rows` that no entry reads through, row-major.

    Islands and strays alike: the question is only whether a letter stands
    alone, not whether it may. `fill_islands` takes the cells as `fixed`, so a
    lone letter a source grid already held never seeds a further island.
    """
    return tuple((row, col) for row, col, _ in _lone(rows, _covered(rows)))
