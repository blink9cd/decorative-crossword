"""Grouped suite: property tests for the answer-pairs finder.

`cw_pairs.find_pairs` reads the entries of any grid `gaps` is handed, including
one this project never wrote, so it carries the `# fuzz-target` marker, paired
with `test_fuzz_find_pairs` below.

**The property re-derives the answer independently.** Every ordered pair of
runs found by `property_strategies.scan_runs` (a regex reading of the grid,
not `cw_grid`'s accumulator) whose join is in the vocabulary must be reported,
and nothing else may be. Pairs are compared as the two cell sets plus the joined
text, which makes a join that reads the same either way one expectation rather
than two without copying the subject's tie-break; a line reported twice is a
failure of its own.

The vocabulary is drawn mostly from the grid's own joins, because a random word
almost never equals a join, and a property whose every example finds nothing
asserts nothing.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location. The two reach it differently, so the bootstrap below names the
project root, `src/` and the strategy folder rather than relying on either.
"""

from __future__ import annotations

import itertools
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
import cw_pairs  # noqa: E402 - same bootstrap
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
    "crossword_pairs_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_pairs_properties")

#: Two letters plus the block. Few letters make repeated entries, and a repeated
#: entry is where a join reading the same either way comes from.
_CELL_ALPHABET = "AB" + cw_grid.BLOCK

#: Grid side bounds, drawn independently so non-square grids are in range.
_MIN_SIDE = 1
_MAX_SIDE = 5

#: How many of the grid's own joins, and how many unrelated words, one
#: vocabulary takes.
_MAX_CHOSEN_JOINS = 4
_MAX_NOISE_WORDS = 3

#: Noise word lengths. The shortest join is two runs of the shortest length.
_MIN_NOISE = 2 * cw_grid.MIN_RUN
_MAX_NOISE = 8

#: Offered to `sampled_from` beside the grid's joins so a grid holding fewer
#: than two runs still has something to sample. No join is empty, so it can
#: never match one.
_NO_JOIN = ""

#: One drawn case: a grid, and the vocabulary its pairs are sought in.
Case = tuple[tuple[str, ...], frozenset[str]]

#: A pair as the property compares it: its two cell tuples, unordered, and the
#: text they joined into.
Key = tuple[frozenset[tuple[tuple[int, int], ...]], str]


@st.composite
def _cases(draw: st.DrawFn) -> Case:
    """A grid, and a vocabulary holding some of its joins and some unrelated words."""
    rows = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    cols = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    grid = tuple(
        "".join(draw(st.sampled_from(_CELL_ALPHABET)) for _ in range(cols))
        for _ in range(rows)
    )
    joins = [
        first.text + second.text
        for first, second in itertools.permutations(
            property_strategies.scan_runs(grid), 2
        )
    ]
    chosen = draw(
        st.lists(st.sampled_from([*joins, _NO_JOIN]), max_size=_MAX_CHOSEN_JOINS)
    )
    noise = draw(
        st.lists(
            st.text(alphabet="AB", min_size=_MIN_NOISE, max_size=_MAX_NOISE),
            max_size=_MAX_NOISE_WORDS,
        )
    )
    return grid, frozenset(chosen) | frozenset(noise)


def _expected(case: Case) -> set[Key]:
    """Every pair the grid's independently scanned runs join into, either way round."""
    grid, vocabulary = case
    return {
        (frozenset({first.cells, second.cells}), first.text + second.text)
        for first, second in itertools.permutations(
            property_strategies.scan_runs(grid), 2
        )
        if first.text + second.text in vocabulary
    }


class TestFindPairsProperties(unittest.TestCase):
    """`find_pairs` reports exactly the joins an independent scan finds."""

    @given(case=_cases())
    @example(case=((".SITE", "W....", "E....", "B...."), frozenset({"WEBSITE"})))
    @example(case=(("AB.AB",), frozenset({"ABAB"})))
    def test_fuzz_find_pairs(self, case: Case) -> None:
        grid, vocabulary = case
        found = [
            (frozenset({pair.first.cells, pair.second.cells}), pair.joined)
            for pair in cw_pairs.find_pairs(grid, vocabulary)
        ]
        self.assertEqual(len(found), len(set(found)), "a pair was reported twice")
        self.assertEqual(set(found), _expected(case))


if __name__ == "__main__":
    unittest.main()
