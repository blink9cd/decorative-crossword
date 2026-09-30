"""Grouped suite: property test for a fill that may absorb its --source entries.

**Growth only adds letters around the source.** Under `--absorb-entries`, whatever
grid a search returns holds every source letter at its own cell, and every source
entry it no longer holds lies inside a longer bank answer covering all of its
cells: the entry was absorbed, never moved, re-lettered or dropped.

**That growth really happens is measured, not assumed.** A first draw of random
dense grids absorbed an entry in none of 150 examples, and in 5 to 7 of 150 over
more letters and blocks: the cell past a run was nearly always a clashing letter,
or the lines crossing it made the growth illegal. So most draws here are LAID OUT
for growth -- across runs on alternating rows, so no letter added past one can
form a crossing run, some of them banked one letter longer and one sometimes split
into two runs a bank answer welds -- and the rest stay random, for the shapes a
layout never draws. The rates this bought are recorded beside `_requests`.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`; the
bootstrap below names both, as the project's other property suites do.
"""

from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_grid  # noqa: E402 - same bootstrap
import cw_reach  # noqa: E402 - same bootstrap
import cw_search  # noqa: E402 - same bootstrap
from tests.search_fixtures import BASE_CONFIG, still  # noqa: E402 - same bootstrap

# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_absorb_properties",
    derandomize=True,
    deadline=None,
    max_examples=150,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_absorb_properties")

#: Four letters: few enough that answers share letters, enough that two laid runs
#: rarely spell one answer twice, which pre-flight refuses before the walk.
_LETTERS = "ABCD"

#: A random grid's cells: the letters and three blocks, so runs stay short.
_SCATTER = _LETTERS + cw_grid.BLOCK * 3

#: Side bounds of a random grid, drawn independently so non-square is in range.
_MIN_SIDE = 2
_MAX_SIDE = 5

#: Width bounds of a laid-out grid, and how many across runs it lays.
_MIN_WIDTH = 4
_MAX_WIDTH = 7
_MAX_LINES = 3

#: The shortest run a laid-out line may be split into for a weld: two runs of
#: `cw_grid.MIN_RUN` letters with one block between them.
_WELD_WIDTH = 2 * cw_grid.MIN_RUN + 1

#: A small node cap and window: enough to lay a growth, cheap per example.
_MAX_STEPS = 40
_LOOK_AHEAD = 20

#: One drawn case: the source rows and the bank's answers.
Request = tuple[tuple[str, ...], frozenset[str]]


def _word(draw: st.DrawFn, length: int, taken: set[str]) -> str:
    """One word of `length` letters from `_LETTERS` that `taken` does not hold yet.

    A laid run repeating one already laid is a source pre-flight refuses before
    the walk, which asserts nothing about growth.
    """
    return draw(
        st.text(_LETTERS, min_size=length, max_size=length).filter(
            lambda word: word not in taken
        )
    )


@st.composite
def _scattered(draw: st.DrawFn) -> Request:
    """A random grid whose every run the bank holds, one run sometimes banked longer."""
    height = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    width = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    rows = tuple(_word_of(draw, _SCATTER, width) for _ in range(height))
    answers = {run.text for run in cw_grid.runs_from_rows(rows)}
    if answers:
        text = draw(st.sampled_from(sorted(answers)))
        letter = draw(st.sampled_from(_LETTERS))
        answers.add(draw(st.sampled_from((text + letter, letter + text))))
    return rows, frozenset(answers)


def _word_of(draw: st.DrawFn, alphabet: str, length: int) -> str:
    """One string of `length` cells drawn from `alphabet`."""
    return "".join(
        draw(st.lists(st.sampled_from(alphabet), min_size=length, max_size=length))
    )


def _laid_line(draw: st.DrawFn, width: int, answers: set[str]) -> str:
    """One across line of a laid-out grid: a run or a weldable pair, banked, maybe longer.

    Every run is banked. A single run is sometimes banked one letter longer at
    whichever end has room; a line split in two by one block is sometimes banked
    as the one answer filling that block.
    """
    if width >= _WELD_WIDTH and draw(st.booleans()):
        left = _word(draw, draw(st.integers(cw_grid.MIN_RUN, width - 3)), answers)
        right_most = width - len(left) - 1
        right = _word(
            draw, draw(st.integers(cw_grid.MIN_RUN, right_most)), answers | {left}
        )
        answers.update((left, right))
        if draw(st.booleans()):
            answers.add(left + draw(st.sampled_from(_LETTERS)) + right)
        return (left + cw_grid.BLOCK + right).ljust(width, cw_grid.BLOCK)
    length = draw(st.integers(cw_grid.MIN_RUN, width - 1))
    col = draw(st.integers(0, width - length))
    text = _word(draw, length, answers)
    answers.add(text)
    letter = draw(st.sampled_from(_LETTERS))
    room = [text + letter] if col + length < width else []
    room += [letter + text] if col > 0 else []
    if draw(st.booleans()):
        answers.add(draw(st.sampled_from(room)))
    return (cw_grid.BLOCK * col + text).ljust(width, cw_grid.BLOCK)


@st.composite
def _laid_out(draw: st.DrawFn) -> Request:
    """Across runs on alternating rows, so a letter added past one crosses nothing."""
    width = draw(st.integers(min_value=_MIN_WIDTH, max_value=_MAX_WIDTH))
    lines = draw(st.integers(min_value=1, max_value=_MAX_LINES))
    answers: set[str] = set()
    blank = cw_grid.BLOCK * width
    rows: list[str] = []
    for index in range(lines):
        if index:
            rows.append(blank)
        rows.append(_laid_line(draw, width, answers))
    if draw(st.booleans()):
        rows.append(blank)
    grid = tuple(rows)
    if draw(st.booleans()):
        # Transposed: the same layout as down runs, on a taller-than-wide grid.
        grid = tuple("".join(row[col] for row in grid) for col in range(width))
    return grid, frozenset(answers)


#: Measured with a counting wrapper around the search, over this module's 150
#: examples: 45 absorbed at least one entry, 59 kept every entry, 43 were refused
#: before the walk -- mostly a scattered grid spelling one run twice -- and 3 held
#: no entry. With `_word` accepting an answer already drawn, 23 absorbed and 57
#: were refused. Re-measure after any edit to a draw: `derandomize=True` fixes
#: the seed, not the examples, so even an equivalent rewrite of a draw call
#: draws different ones.
_requests = st.one_of(_laid_out(), _scattered())


class TestAbsorbingProperties(unittest.TestCase):
    """Growing a source entry never changes or moves a source letter."""

    @given(request=_requests)
    def test_growth_keeps_every_source_letter_and_covers_every_absorbed_entry(
        self, request: Request
    ) -> None:
        rows, answers = request
        bank = cw_bank.Bank(
            themes={},
            entries=tuple(cw_bank.BankEntry(a, None, None) for a in sorted(answers)),
        )
        config = dataclasses.replace(
            BASE_CONFIG,
            rows=len(rows),
            cols=len(rows[0]),
            start=rows,
            min_themes=0,
            max_blocked=100.0,
            time_budget=0.0,
            max_steps=_MAX_STEPS,
            look_ahead=_LOOK_AHEAD,
            absorb_entries=True,
        )
        outcome = cw_search.search(bank, config, clock=still)
        for r, line in enumerate(rows):
            for c, cell in enumerate(line):
                if cell != cw_grid.BLOCK:
                    self.assertEqual(outcome.rows[r][c], cell, (rows, outcome.rows))
        after = cw_grid.runs_from_rows(outcome.rows)
        for entry in cw_grid.runs_from_rows(rows):
            if entry in after:
                continue
            self.assertTrue(
                any(
                    run.text in answers
                    and len(run.text) > len(entry.text)
                    and cw_reach.covers(entry, run.cells)
                    for run in after
                ),
                (rows, outcome.rows, entry),
            )


if __name__ == "__main__":
    unittest.main()
