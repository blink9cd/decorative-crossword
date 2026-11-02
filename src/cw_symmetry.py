"""cw_symmetry: how balanced a grid's pattern of letters and blocks is.

`fill --prefer-symmetry KIND` ranks the conforming grids a search finds by this
measure (`cw_select.grid_score`), and the report names the chosen grid's figure.
It is a ranking level and never a filter: Crossword Compiler and Ingrid enforce
symmetry as a hard constraint over block templates, and on a bank of tens of
words that would starve the search.

The measure is the pattern, never the letters. Two partner cells match when both
hold a letter or both are blocked; two partner letters almost never agree, so
comparing them would count little but matched blocks, which is not a look anyone
sees. Each pair of partner cells counts once, and a cell that is its own partner
(the center under rotation, a middle column or row under a mirror) is no
pair at all, so "N of M" holds no match that came free. Counting cells instead
would rank grids exactly as counting pairs does, and only inflate the figure.

Each kind is one partner rule, `(row, col, rows, cols) -> (row, col)`, and every
rule is its own inverse, which is what makes counting each pair once sound.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType

import cw_grid

#: Where a cell's partner sits: `(row, col, rows, cols) -> (row, col)`.
Partner = Callable[[int, int, int, int], tuple[int, int]]


def _rotated(row: int, col: int, rows: int, cols: int) -> tuple[int, int]:
    """The cell a half turn about the grid's center carries `(row, col)` to."""
    return rows - 1 - row, cols - 1 - col


def _left_right(row: int, col: int, _rows: int, cols: int) -> tuple[int, int]:
    """The cell across the grid's vertical center line from `(row, col)`."""
    return row, cols - 1 - col


def _top_bottom(row: int, col: int, rows: int, _cols: int) -> tuple[int, int]:
    """The cell across the grid's horizontal center line from `(row, col)`."""
    return rows - 1 - row, col


#: Every kind `--prefer-symmetry` accepts, in the order its `--help` lists them.
#: The parser's `choices=` and the config check both read this table, so a kind
#: added here is offered and accepted in one edit.
KINDS: Mapping[str, Partner] = MappingProxyType(
    {
        "rotational": _rotated,
        "left-right": _left_right,
        "top-bottom": _top_bottom,
    }
)


def matching_pairs(rows: Sequence[str], kind: str) -> tuple[int, int]:
    """Return how many partner-cell pairs match under `kind`, and how many there are.

    A pair matches when both cells hold a letter or both are blocked. Linear in
    the grid's cells, so scoring every conforming grid a look-ahead window finds
    costs nothing next to the walk that found them.
    """
    partner = KINDS[kind]
    height, width = len(rows), len(rows[0])
    matched = total = 0
    for row in range(height):
        for col in range(width):
            there = partner(row, col, height, width)
            # Each pair is met twice, once from each end: count it from the
            # earlier cell only. A cell that is its own partner never counts.
            if there <= (row, col):
                continue
            total += 1
            here_blocked = rows[row][col] == cw_grid.BLOCK
            matched += here_blocked == (rows[there[0]][there[1]] == cw_grid.BLOCK)
    return matched, total
