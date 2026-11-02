"""Grouped suite: property tests for the hidden-word chooser.

`cw_shade.place_word` takes a grid and a word from outside the tool (the grid
from a file `preview` is documented to accept even when this project did not
write it, the word from a list nobody hand-curated), so it is this
subcommand's untrusted-input boundary and carries the `# fuzz-target` marker,
paired with the `test_fuzz_place_word` below.

**The optimality property is the one that matters.** 100% branch coverage
proves every line of the chooser ran; it says nothing about whether the cells
it chose were the cheapest ones, and a greedy chooser passes every
coverage-shaped test while being measurably wrong. So the headline property
here re-derives the answer independently: it enumerates every subsequence of
the grid's letters that spells the word and asserts the chooser's score is the
minimum over all of them. That enumeration is deliberately not a second
dynamic-programming table (a property asserting the subject's own method
could not fail when the method is what is wrong), and it is affordable only
because the drawn grids are tiny, which is why they are.

The invariants beside it are the structural ones: every chosen cell holds a
letter, the letters spell the word in reading order, the cells strictly
increase, and a placement is never longer than the grid has letters to give.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location. The two reach it differently, so the bootstrap below names both the
project root and `src/` rather than relying on either caller.
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

import cw_grid  # noqa: E402 - import follows the sys.path bootstrap above
import cw_shade  # noqa: E402 - same bootstrap

# Hypothesis settings come from a registered profile, loaded at import and
# before any class body, never an `@settings` decorator: a `@given` test
# snapshots its settings when it is decorated, and a decorator would pin the
# property's settings where no campaign runner could re-stamp them: Hypothesis
# refuses a second settings object on a function that already carries one. Its
# own profile name, distinct from every other property module's, so no import
# order can decide what this module's tests had already snapshotted.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_shade_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_shade_properties")

#: A two-letter alphabet plus the block. Deliberately tiny: repeated letters
#: are what give the chooser a genuine choice between cells, and a choice is
#: the only thing an optimality property can be about. Over twenty-six letters
#: most drawn words would have one placement or none.
_CELL_ALPHABET = "AB" + cw_grid.BLOCK

#: Grid side bounds, drawn independently so non-square grids are in range:
#: the shape a row/column mix-up hides in.
_MIN_SIDE = 1
_MAX_SIDE = 4

#: Word length bounds. The upper one is what keeps the brute-force enumeration
#: below affordable: a 4x4 grid holds at most 16 letters, and choosing 4 of
#: them in order is under two thousand combinations.
_MIN_WORD = 1
_MAX_WORD = 4


@st.composite
def _grids(draw: st.DrawFn) -> tuple[str, ...]:
    """A rectangular grid of letters and blocks, possibly entirely blocked.

    An all-blocked grid is drawn on purpose: it is the degenerate input every
    property here must still hold on, and it is the one a real `preview` source
    can genuinely be.
    """
    rows = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    cols = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    return tuple(
        "".join(draw(st.sampled_from(_CELL_ALPHABET)) for _ in range(cols))
        for _ in range(rows)
    )


#: A word over the same tiny alphabet, so it collides with the grid often
#: enough that most draws actually place something. The block character is
#: excluded: a word is A-Z by definition everywhere else in this project.
_WORDS = st.text(alphabet="AB", min_size=_MIN_WORD, max_size=_MAX_WORD)

#: A grid with two readings of one word, one clustered and one scattered: the
#: shape the whole chooser exists for, pinned so it is reached on every run
#: rather than on most of them.
#:
#: It is not pinned because the draw rarely reaches it. Over 2,000 draws from
#: this module's own space, 954 produced a placeable (grid, word) and a greedy
#: chooser disagreed with the brute-force optimum on 254 of those (26.6%), so
#: the optimality property below kills greedy within a handful of examples
#: unpinned. What the pin buys is that the kill is not a property of one
#: revision of this test: `@given` draws are derandomized from the test's own
#: source text, so an inert statement added to a body reshuffles every input it
#: sees, and a seed is the only thing that survives that.
_CHOICE_EXAMPLE = (("AB.", ".B.", "..A"), "ABA")


def _brute_force_best(rows: tuple[str, ...], word: str) -> int | None:
    """The cheapest cost of any cell subsequence spelling `word`, or None.

    An independent reading of what `place_word` is supposed to return: every
    combination of cells in reading order is enumerated and scored, and the
    minimum is taken. It shares only `lettered_cells` and `clustering_penalty`
    (the two definitions the property is not about), and none of the
    subject's search machinery, so a defect in that machinery cannot hide
    inside this check as well.
    """
    cells = cw_shade.lettered_cells(rows)
    best: int | None = None
    for choice in itertools.combinations(range(len(cells)), len(word)):
        if "".join(cells[index][2] for index in choice) != word:
            continue
        cost = sum(
            cw_shade.clustering_penalty(
                cells[choice[step - 1]][:2], cells[choice[step]][:2]
            )
            for step in range(1, len(choice))
        )
        if best is None or cost < best:
            best = cost
    return best


class TestPlaceWordProperties(unittest.TestCase):
    """What `place_word` guarantees for any grid and any word."""

    @given(_grids(), _WORDS)
    @example(*_CHOICE_EXAMPLE)
    def test_fuzz_place_word(self, rows: tuple[str, ...], word: str) -> None:
        """Every grid and word yields a coherent Placement or None, never a crash.

        The structural half of the contract, asserted together because they are
        one claim about one returned value: the cells hold letters, those
        letters spell the word, they are in strictly increasing reading order,
        and there are no more of them than the grid has letters. A chooser that
        returned cells in the wrong order, or reused one, satisfies "returns a
        Placement" and fails here.
        """
        placement = cw_shade.place_word(rows, word)
        if placement is None:
            return
        cells = placement.cells
        self.assertEqual(len(cells), len(word))
        self.assertLessEqual(len(cells), len(cw_shade.lettered_cells(rows)))
        for row, col in cells:
            self.assertNotEqual(
                rows[row][col], cw_grid.BLOCK, f"cell ({row}, {col}) is a block"
            )
        self.assertEqual("".join(rows[row][col] for row, col in cells), word)
        self.assertEqual(list(cells), sorted(cells), "cells must read in order")
        self.assertGreaterEqual(placement.clustering, 0)

    @given(_grids(), _WORDS)
    @example(*_CHOICE_EXAMPLE)
    def test_the_chosen_cells_are_the_cheapest_that_spell_the_word(
        self, rows: tuple[str, ...], word: str
    ) -> None:
        """The property greedy fails, and coverage cannot see.

        Both directions: the chooser places a word exactly when some cell
        subsequence spells it, and when it does, its score is the minimum over
        every such subsequence. The one-sided version ("if it placed one, the
        score is minimal") would be satisfied by a chooser that placed
        nothing at all.
        """
        placement = cw_shade.place_word(rows, word)
        expected = _brute_force_best(rows, word)
        if expected is None:
            self.assertIsNone(placement)
            return
        assert placement is not None
        self.assertEqual(placement.clustering, expected)

    @given(_grids(), _WORDS)
    def test_the_score_is_the_cost_of_the_path_it_reports(
        self, rows: tuple[str, ...], word: str
    ) -> None:
        """The number and the cells must describe each other.

        Without this a chooser could report an honest minimum beside a
        different set of cells, and every other property here would still
        hold: the caller pastes the cells, so a score that describes some
        other choice is worse than no score.
        """
        placement = cw_shade.place_word(rows, word)
        if placement is None:
            return
        walked = sum(
            cw_shade.clustering_penalty(
                placement.cells[step - 1], placement.cells[step]
            )
            for step in range(1, len(placement.cells))
        )
        self.assertEqual(placement.clustering, walked)

    @given(_grids(), _WORDS)
    def test_placing_the_same_word_twice_gives_the_same_cells(
        self, rows: tuple[str, ...], word: str
    ) -> None:
        """Two runs of one request produce the same bytes.

        The chooser walks mappings and breaks ties between equal-cost cells,
        which is exactly where a hash-seeded order leaks into output.
        """
        self.assertEqual(
            cw_shade.place_word(rows, word), cw_shade.place_word(rows, word)
        )


class TestSearchProperties(unittest.TestCase):
    """What the ranked search guarantees over a whole word list."""

    @given(_grids(), st.lists(_WORDS, max_size=5, unique=True))
    def test_every_word_is_accounted_for_exactly_once(
        self, rows: tuple[str, ...], words: list[str]
    ) -> None:
        """The report's accounting can only be honest if the search's is.

        Candidates plus the three exclusion counts must equal the words handed
        in, whatever the grid: a word counted twice, or dropped from every
        count, produces a report whose headline no reader can check.
        """
        result = cw_shade.search_hidden_words(
            rows, words, min_length=cw_grid.MIN_RUN, exclude_grid_answers=True
        )
        self.assertEqual(
            len(result.candidates)
            + result.too_short
            + result.unspellable
            + len(result.excluded_answers),
            len(words),
        )

    @given(_grids(), st.lists(_WORDS, max_size=5, unique=True))
    def test_the_ranking_never_puts_a_worse_score_first(
        self, rows: tuple[str, ...], words: list[str]
    ) -> None:
        scores = [
            candidate.clustering
            for candidate in cw_shade.search_hidden_words(
                rows, words, min_length=cw_grid.MIN_RUN, exclude_grid_answers=False
            ).candidates
        ]
        self.assertEqual(scores, sorted(scores))


if __name__ == "__main__":
    unittest.main()
