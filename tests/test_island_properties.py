"""Grouped suite: property tests for the stray-letter reader and the island filler.

`cw_island.stray_letters` reads any grid `preview`, `shade` or `gaps` is handed,
including one this project never wrote, so it carries the `# fuzz-target` marker,
paired with `test_fuzz_stray_letters` below.

Two properties, for two different claims:

- **The reader re-derived independently.** Every filled cell outside the runs
  `property_strategies.scan_runs` finds (a regex reading of the grid, not
  `cw_grid`'s accumulator) is a stray unless its letter is an island letter
  with a covered cell at a corner. Compared as a list, so the row-major order is
  pinned along with the membership. Its oracle restates the rule's two clauses,
  so it checks the implementation and ratifies the rule: what the rule says is
  pinned by the hand-worked cases in `test_island.py`.
- **The filler and the reader stay in step.** `fill_islands` and `stray_letters`
  state the corner rule two ways: the filler asks for any letter of the grid it
  was handed outside `fixed`, the reader for a letter some entry covers. `fill`
  hands the filler a grid whose every letter outside `fixed` is in an entry
  (under `--source`, `fixed` is each lone letter the fill left), so the two must
  agree, and nothing `fill_islands` lays may read back as a stray. The draw
  below is that grid with nothing fixed: every letter is in an entry.

The draw is BLOCK-HEAVY on purpose. A uniform alphabet almost never walls a
letter in, and a property whose every example holds no lone letter asserts
nothing.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location. The two reach it differently, so the bootstrap below names the
project root, `src/` and the strategy folder rather than relying on either.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE.parent / "property_strategies"))

import cw_grid  # noqa: E402 - import follows the sys.path bootstrap above
import cw_island  # noqa: E402 - same bootstrap
import property_strategies  # noqa: E402 - same bootstrap

# A registered profile loaded at import under this module's own name, never an
# `@settings` decorator, which would pin the property's settings where no
# campaign runner could re-stamp them. Derandomized so the in-suite run is
# reproducible; no deadline, because a per-example wall clock measures machine
# load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_island_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_island_properties")

#: Two island letters, one letter off the set, and the block three times over, so
#: most letters are walled in and both kinds of lone letter are common.
_CELL_ALPHABET = ("A", "I", "Q", cw_grid.BLOCK, cw_grid.BLOCK, cw_grid.BLOCK)

#: Grid side bounds, drawn independently so non-square grids are in range.
_MIN_SIDE = 1
_MAX_SIDE = 6

#: The row and column offsets that, paired, reach the four corner cells.
_DIAGONAL = (-1, 1)

#: The phrase every off-set stray's reason carries.
_OFF_SET = "not an island letter"

#: One stray as the property compares it: row, column, letter, and whether its
#: reason says the letter is off the set.
Key = tuple[int, int, str, bool]


@st.composite
def _grids(draw: st.DrawFn) -> tuple[str, ...]:
    """A small block-heavy grid of island letters, one other letter and blocks."""
    rows = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    cols = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    return tuple(
        "".join(draw(st.sampled_from(_CELL_ALPHABET)) for _ in range(cols))
        for _ in range(rows)
    )


def _covered(rows: tuple[str, ...]) -> set[tuple[int, int]]:
    """Every cell some independently scanned run reads through."""
    return {cell for run in property_strategies.scan_runs(rows) for cell in run.cells}


def _expected_strays(rows: tuple[str, ...]) -> list[Key]:
    """Every lone letter the island rule does not accept, row-major."""
    covered = _covered(rows)
    expected: list[Key] = []
    for row, col in sorted(property_strategies.filled_cells(rows) - covered):
        letter = rows[row][col]
        at_entry_corner = any(
            (row + d_row, col + d_col) in covered
            for d_row in _DIAGONAL
            for d_col in _DIAGONAL
        )
        off_set = letter not in cw_island.ISLAND_LETTERS
        if off_set or not at_entry_corner:
            expected.append((row, col, letter, off_set))
    return expected


@st.composite
def _island_requests(
    draw: st.DrawFn,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """An entries-only grid, and the island letters to lay on it, in order."""
    rows = draw(_grids())
    covered = _covered(rows)
    entries_only = tuple(
        "".join(
            cell if (row, col) in covered else cw_grid.BLOCK
            for col, cell in enumerate(line)
        )
        for row, line in enumerate(rows)
    )
    order = draw(st.permutations(cw_island.ISLAND_LETTERS))
    count = draw(st.integers(min_value=1, max_value=len(order)))
    return entries_only, tuple(order[:count])


class TestStrayLettersProperties(unittest.TestCase):
    """`stray_letters` agrees with an independent scan, and with `fill_islands`."""

    @given(rows=_grids())
    @example(rows=("CAT..", "...A.", "....I"))
    @example(rows=("CAT.", "...Q"))
    def test_fuzz_stray_letters(self, rows: tuple[str, ...]) -> None:
        found = [
            (row, col, letter, _OFF_SET in reason)
            for row, col, letter, reason in cw_island.stray_letters(rows)
        ]
        self.assertEqual(found, _expected_strays(rows))

    @given(request=_island_requests())
    @example(request=(("CAT...", "......"), ("A",)))
    def test_nothing_fill_islands_lays_reads_back_as_a_stray(
        self, request: tuple[tuple[str, ...], tuple[str, ...]]
    ) -> None:
        rows, letters = request
        laid, placed = cw_island.fill_islands(rows, letters)
        # Every placed island is a lone letter of the result, and nothing else
        # is: so the empty tuple below is a statement about the islands.
        self.assertEqual(
            {(row, col) for row, col, _ in placed},
            property_strategies.filled_cells(laid) - _covered(laid),
        )
        self.assertEqual(cw_island.stray_letters(laid), ())


if __name__ == "__main__":
    unittest.main()
