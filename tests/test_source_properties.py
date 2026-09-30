"""Grouped suite: property test for the `--source` start check.

`cw_source.start_from` reads any grid an operator hands `fill --source`,
including one this project never wrote, so it carries the `# fuzz-target`
marker, paired with `test_fuzz_start_from` below.

**A source that passes is a board the search may start from.** Every run of it
that breaks the distinct-run rule under the vocabulary the check hands back --
the bank's answers plus every kept entry -- must be a partial run the check
names, in scan order, and one an answer not on the board could still be laid
over; and a kept entry must be one the bank lacked and the source declared.
The walk's own step test rests on the first half, and the best-effort guard,
which writes an empty board rather than a board holding a partial run, on
both.

**Both outcomes are measured, not assumed.** A property whose draws are all
refused asserts nothing, and one whose draws all pass never meets a refusal.
The draws were counted to reach every outcome: passing with kept entries, with
a partial run, with runs but none kept, and holding no run at all, and refused
for a repeated answer and for a run nothing declares or could complete. The
small alphabet, the half-the-draws declaration and the grown run below are what
bought that spread; each is explained where it is drawn.

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

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_grid  # noqa: E402 - same bootstrap
import cw_grid_document  # noqa: E402 - same bootstrap
import cw_place  # noqa: E402 - same bootstrap
import cw_reach  # noqa: E402 - same bootstrap
import cw_source  # noqa: E402 - same bootstrap

# Hypothesis settings come from a registered profile loaded at import under
# this module's own name, never an `@settings` decorator, which would pin the
# property's settings where no campaign runner could re-stamp them. A `@given`
# test snapshots its settings when it is decorated, so the example count set
# here reaches this module's property alone.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_source_properties",
    derandomize=True,
    deadline=None,
    max_examples=300,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_source_properties")

#: Three letters: few enough that runs repeat and cross often, not so few that a
#: repeat refuses most draws -- over two letters it refused 193 of 302 calls.
_LETTERS = "ABC"

#: The letters plus the block, the cells a grid is drawn from.
_ALPHABET = _LETTERS + cw_grid.BLOCK

#: Grid side bounds, drawn independently so non-square grids are in range.
_MIN_SIDE = 2
_MAX_SIDE = 4

#: How many answers outside the grid a bank may add, and how long each is.
_MAX_EXTRA = 3
_MIN_EXTRA_LENGTH = 2
_MAX_EXTRA_LENGTH = 4

#: One draw in this many grows a run into a banked answer one letter longer.
_GROW_ONE_IN = 2

#: One drawn case: the source, the screened bank, and the answers it declares.
Request = tuple[cw_grid_document.GridDocument, cw_bank.Bank, set[str]]


@st.composite
def _requests(draw: st.DrawFn) -> Request:
    """A small grid, a bank holding some of its runs, and a declared subset."""
    height = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    width = draw(st.integers(min_value=_MIN_SIDE, max_value=_MAX_SIDE))
    rows = tuple(
        "".join(
            draw(st.lists(st.sampled_from(_ALPHABET), min_size=width, max_size=width))
        )
        for _ in range(height)
    )
    texts = sorted({run.text for run in cw_grid.runs_from_rows(rows)})
    pick: st.SearchStrategy[set[str]] = (
        st.sets(st.sampled_from(texts)) if texts else st.just(set[str]())
    )
    held = draw(pick)
    declared = draw(pick)
    # One draw in `_GROW_ONE_IN` grows one run: bank an answer one letter longer than
    # it, and neither hold nor declare the run itself, so it can only pass as a
    # partial run. Every OTHER run the bank lacks is then declared, because a
    # single undeclared run nothing extends refuses the whole source -- with
    # random answers alone, 1 of 303 calls passed holding a partial run, and
    # growing a run without declaring the rest, 1 again. The rate was measured
    # at one in 1, 2 and 3: every draw growing a run passed with kept entries in
    # 1 of 303 calls, one in 3 halved the partial-run passes, and one in 2 kept
    # both near 1 in 18.
    grows = bool(texts) and draw(st.integers(1, _GROW_ONE_IN)) == 1
    grow = draw(st.sampled_from(texts)) if grows else None
    if grow is not None or draw(st.booleans()):
        # Otherwise half the draws declare every run the bank lacks, so a source
        # that repeats nothing passes WITH kept entries. Two independent subsets
        # alone passed with a kept entry in 19 of 302 calls (over two letters),
        # starving the loop that checks what was kept.
        declared = declared | (set(texts) - held)
    extra = draw(
        st.lists(
            st.text(_LETTERS, min_size=_MIN_EXTRA_LENGTH, max_size=_MAX_EXTRA_LENGTH),
            max_size=_MAX_EXTRA,
        )
    )
    if grow is not None:
        held = held - {grow}
        declared = declared - {grow}
        letter = draw(st.sampled_from(_LETTERS))
        extra.append(draw(st.sampled_from((grow + letter, letter + grow))))
    answers = sorted(held | set(extra))
    bank = cw_bank.Bank(
        themes={}, entries=tuple(cw_bank.BankEntry(a, None, None) for a in answers)
    )
    document = cw_grid_document.parse_document(
        {"rows": list(rows), "clues": {text: {} for text in sorted(declared)}}
    )
    return document, bank, declared


class TestStartFromProperties(unittest.TestCase):
    """A source that passes is a board the search may stand on."""

    @given(request=_requests())
    @example(  # passes, with one kept entry
        request=(
            cw_grid_document.parse_document(
                {"rows": ["AB", ".."], "clues": {"AB": {}}}
            ),
            cw_bank.Bank(themes={}, entries=()),
            {"AB"},
        )
    )
    @example(  # passes, with AB a partial run ABC completes
        request=(
            cw_grid_document.parse_document({"rows": ["AB.", "..."]}),
            cw_bank.Bank(themes={}, entries=(cw_bank.BankEntry("ABC", None, None),)),
            set(),
        )
    )
    @example(  # refused: a run nothing declares and no answer could complete
        request=(
            cw_grid_document.parse_document({"rows": ["AB", ".."]}),
            cw_bank.Bank(themes={}, entries=()),
            set(),
        )
    )
    def test_fuzz_start_from(self, request: Request) -> None:
        document, bank, declared = request
        try:
            start = cw_source.start_from(document, bank, (), None)
        except cw_source.SourceError:
            return
        answers = frozenset(entry.answer for entry in start.bank.entries)
        # The document's own rows: what `fill` hands the search as its start board.
        breaks = cw_place.rule_breaks(document.rows, answers)
        self.assertEqual(tuple(run for run, _ in breaks), start.partial)
        present = {run.text for run in cw_grid.runs_from_rows(document.rows)}
        unused = [answer for answer in sorted(answers) if answer not in present]
        for run in start.partial:
            self.assertTrue(cw_reach.completable(document.rows, run, unused))
        held = {entry.answer for entry in bank.entries}
        for answer in start.kept:
            self.assertNotIn(answer, held)
            self.assertIn(answer, declared)


if __name__ == "__main__":
    unittest.main()
