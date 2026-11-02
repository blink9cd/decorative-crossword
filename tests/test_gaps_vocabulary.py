"""Grouped suite: what a vocabulary says about a gap, and how gaps are ranked.

The derivation in `test_gaps.py` says what a fill would demand. This suite is
the other half: given the words the operator actually holds, which gaps are
already payable and which need a word that does not exist yet. That split is
the whole point of the subcommand (a list of coordinates nobody can act on
becomes a short list of specific asks), so the cases here pin the three
outcomes apart from each other.

Two of them are easy to get wrong and are pinned deliberately:

- **The crossing.** A two-demand gap can have words for each pattern
  separately and still be unfillable, because no single letter satisfies both.
  Reporting that as "you have the words" would be false, and reporting it as
  "you need two words" overstates it: one new answer in either pattern clears it.
- **Absorption frees an answer.** A fill that welds two runs retires what it
  swallows, so an answer this candidate absorbs is available again to its own
  other demand. `TestAbsorptionFreesAnswers` holds the case; without the rule
  the resolver refuses a fill that is in fact legal. What it frees is the
  occurrence, not the word: a grid that spells one answer twice keeps spending
  it after a fill absorbs one copy, and the same class holds that case beside
  this one so the two cannot drift apart.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import unittest

import cw_gaps


#: A gap whose only demand is the two-letter run `A?`. Column 0 carries AB
#: down, so the A at (0, 0) already belongs to an entry.
ONE_DEMAND = ("A.", "B.")

#: A gap at (1, 1) demanding `E?` across and `A?` down at once: two runs one
#: letter has to satisfy together.
TWO_DEMANDS = ("HAY.", "E...", "D...", "GIRL")

#: A gap at (1, 1) whose two demands are the same pattern, `A?`. A letter here
#: would need one word to stand as two distinct entries, which no grid allows.
SAME_PATTERN = (".A.", "A..", "...")

#: A grid whose row 0 already answers AB, so AB is spoken for: a gap elsewhere
#: beside an A cannot claim it a second time.
GRID_HOLDING_AB = ("AB.", "...", "A..")

#: A gap at (1, 2) whose ACROSS demand absorbs the answer AB, while its DOWN
#: demand `A?` is a pattern AB itself matches. The absorbed answer is off the
#: grid once the fill lands, so it is available to the other demand.
ABSORBS_AND_REUSES = ("..A", "AB.", "...")

#: `ABSORBS_AND_REUSES` with the answer AB spelled a second time, in row 2. The
#: across demand still absorbs row 1's copy, so a resolver that tracks answers
#: as a set sees AB go free, while row 2 goes on spelling it, untouched by
#: this fill. Kept beside the grid it differs from by one row, because a
#: resolver that tracks answers as a set resolves the two identically.
ABSORBS_ONE_OF_TWO = ("..A", "AB.", "AB.")


def _resolve(
    rows: tuple[str, ...], vocabulary: set[str]
) -> tuple[cw_gaps.Resolution, ...]:
    """Every resolution for `rows` against `vocabulary`, in analysis order."""
    return cw_gaps.resolve_all(rows, cw_gaps.analyze_grid(rows), frozenset(vocabulary))


def _for_cell(
    resolutions: tuple[cw_gaps.Resolution, ...], row: int, col: int
) -> cw_gaps.Resolution:
    """The resolution for one cell, or fail the calling test saying it is absent."""
    for resolution in resolutions:
        if (resolution.candidate.row, resolution.candidate.col) == (row, col):
            return resolution
    raise AssertionError(f"no resolution at ({row}, {col})")


class TestReadyNow(unittest.TestCase):
    """A gap whose demands the operator can already pay names the letter."""

    def test_a_matching_word_yields_a_fill(self) -> None:
        resolution = _for_cell(_resolve(ONE_DEMAND, {"AT"}), 0, 1)
        self.assertEqual(resolution.fills, (cw_gaps.Fill(letter="T", words=("AT",)),))

    def test_a_ready_gap_needs_no_new_word(self) -> None:
        resolution = _for_cell(_resolve(ONE_DEMAND, {"AT"}), 0, 1)
        self.assertEqual(resolution.new_words, 0)

    def test_fills_are_ordered_by_letter(self) -> None:
        # Deterministic output; alphabetical is the order a reader scanning
        # for their own idea expects.
        resolution = _for_cell(_resolve(ONE_DEMAND, {"AT", "AM", "AH"}), 0, 1)
        self.assertEqual(
            tuple(fill.letter for fill in resolution.fills), ("H", "M", "T")
        )

    def test_one_letter_satisfying_both_demands_yields_one_fill(self) -> None:
        resolution = _for_cell(_resolve(TWO_DEMANDS, {"EX", "AX"}), 1, 1)
        self.assertEqual(
            resolution.fills, (cw_gaps.Fill(letter="X", words=("EX", "AX")),)
        )


class TestNeedsANewWord(unittest.TestCase):
    """A demand no word matches is named, so the operator knows what to invent."""

    def test_an_unmatched_pattern_is_named(self) -> None:
        resolution = _for_cell(_resolve(ONE_DEMAND, {"ZZ"}), 0, 1)
        self.assertEqual(resolution.unmatched, ("A?",))

    def test_one_unmatched_demand_is_one_new_word(self) -> None:
        resolution = _for_cell(_resolve(ONE_DEMAND, {"ZZ"}), 0, 1)
        self.assertEqual(resolution.new_words, 1)

    def test_two_unmatched_demands_are_two_new_words(self) -> None:
        resolution = _for_cell(_resolve(TWO_DEMANDS, set()), 1, 1)
        self.assertEqual(
            (resolution.unmatched, resolution.new_words), (("E?", "A?"), 2)
        )

    def test_an_empty_vocabulary_leaves_every_demand_unmet(self) -> None:
        # The no-vocabulary case is the empty-vocabulary case, so there is one
        # code path rather than two that could disagree.
        resolution = _for_cell(_resolve(ONE_DEMAND, set()), 0, 1)
        self.assertEqual((resolution.fills, resolution.unmatched), ((), ("A?",)))


class TestTheCrossing(unittest.TestCase):
    """Words for each pattern separately is not words for the gap."""

    def test_no_shared_letter_yields_no_fill(self) -> None:
        # EX pays the across demand `E?` with X and AM pays the down demand
        # `A?` with M, so each pattern has a word, and no single letter pays
        # both, which is the whole distinction.
        resolution = _for_cell(_resolve(TWO_DEMANDS, {"EX", "AM"}), 1, 1)
        self.assertEqual(resolution.fills, ())

    def test_neither_pattern_is_reported_unmatched(self) -> None:
        resolution = _for_cell(_resolve(TWO_DEMANDS, {"EX", "AM"}), 1, 1)
        self.assertEqual(resolution.unmatched, ())

    def test_the_crossing_is_distinguishable_from_a_plain_miss(self) -> None:
        resolution = _for_cell(_resolve(TWO_DEMANDS, {"EX", "AM"}), 1, 1)
        self.assertTrue(resolution.blocked_by_crossing)

    def test_a_crossing_costs_one_new_word_not_two(self) -> None:
        # Either pattern gaining one word whose letter matches the other's
        # existing word clears it, so overstating the cost at two would send
        # the operator looking for a word they do not need.
        resolution = _for_cell(_resolve(TWO_DEMANDS, {"EX", "AM"}), 1, 1)
        self.assertEqual(resolution.new_words, 1)

    def test_a_plain_miss_is_not_reported_as_a_crossing(self) -> None:
        resolution = _for_cell(_resolve(ONE_DEMAND, {"ZZ"}), 0, 1)
        self.assertFalse(resolution.blocked_by_crossing)


class TestDistinctness(unittest.TestCase):
    """Every run on a grid is a distinct answer, and the resolver honors it."""

    def test_a_word_already_on_the_grid_is_not_available(self) -> None:
        # AB is the across run in row 0, so it cannot also become the run this
        # fill creates, and with nothing else offered, `A?` is unmet rather
        # than merely unfilled.
        resolution = _for_cell(_resolve(GRID_HOLDING_AB, {"AB"}), 2, 1)
        self.assertEqual((resolution.fills, resolution.unmatched), ((), ("A?",)))

    def test_one_letter_may_not_pay_two_demands_with_one_word(self) -> None:
        resolution = _for_cell(_resolve(SAME_PATTERN, {"AB"}), 1, 1)
        self.assertEqual(resolution.fills, ())

    def test_an_identical_pair_is_a_crossing_not_a_miss(self) -> None:
        # The refusal above is about reusing one word, not about the patterns
        # looking alike: each is matched, so neither is reported unmet.
        resolution = _for_cell(_resolve(SAME_PATTERN, {"AB"}), 1, 1)
        self.assertEqual(
            (resolution.unmatched, resolution.blocked_by_crossing), ((), True)
        )


class TestAbsorptionFreesAnswers(unittest.TestCase):
    """An answer this fill retires is available to this fill's other demand."""

    def test_an_absorbed_answer_may_pay_the_other_demand(self) -> None:
        resolution = _for_cell(_resolve(ABSORBS_AND_REUSES, {"ABB", "AB"}), 1, 2)
        self.assertEqual(
            resolution.fills, (cw_gaps.Fill(letter="B", words=("ABB", "AB")),)
        )

    def test_absorbing_one_copy_does_not_free_a_doubled_answer(self) -> None:
        # The grid spells AB twice and this fill absorbs one copy. The other
        # still stands, so AB is not the resolver's to spend and the down demand
        # `A?` goes unmet; offering B here would write a third AB onto a grid
        # already breaking the one rule the subcommand serves.
        resolution = _for_cell(_resolve(ABSORBS_ONE_OF_TWO, {"ABB", "AB"}), 1, 2)
        self.assertEqual((resolution.fills, resolution.unmatched), ((), ("A?",)))

    def test_an_answer_no_candidate_absorbs_stays_unavailable(self) -> None:
        # The same grid and the same demand, but AB is not offered as the
        # welded run's own match, so the across demand has nothing.
        resolution = _for_cell(_resolve(ABSORBS_AND_REUSES, {"AB"}), 1, 2)
        self.assertEqual((resolution.fills, resolution.unmatched), ((), ("AB?",)))


class TestRanking(unittest.TestCase):
    """Cheapest ask first, and a fill that retires an answer is never cheap."""

    def _ranked(
        self, rows: tuple[str, ...], vocabulary: set[str]
    ) -> list[tuple[int, int]]:
        ranked = cw_gaps.rank(_resolve(rows, vocabulary))
        return [(r.candidate.row, r.candidate.col) for r in ranked]

    def test_a_ready_gap_outranks_one_needing_a_word(self) -> None:
        # (0, 3) closes HAY and needs a four-letter word; (1, 1) is payable.
        order = self._ranked(TWO_DEMANDS, {"EX", "AX"})
        self.assertLess(order.index((1, 1)), order.index((0, 3)))

    def test_an_absorbing_gap_ranks_below_every_pure_addition(self) -> None:
        ranked = cw_gaps.rank(_resolve(TWO_DEMANDS, set()))
        absorbing = [bool(r.candidate.absorbed) for r in ranked]
        self.assertEqual(absorbing, sorted(absorbing))

    def test_a_shorter_ask_outranks_a_longer_one(self) -> None:
        order = self._ranked(("A..", "B.C", "..."), set())
        # (0, 1) demands the two-letter `A?`; (1, 1) sits between B and C and
        # demands the three-letter `B?C`.
        self.assertLess(order.index((0, 1)), order.index((1, 1)))

    def test_the_order_is_stable_between_two_runs(self) -> None:
        first = self._ranked(TWO_DEMANDS, {"EX", "AX"})
        second = self._ranked(TWO_DEMANDS, {"EX", "AX"})
        self.assertEqual(first, second)


class TestSearchGaps(unittest.TestCase):
    """One call composing the derivation, the resolution and the ranking."""

    def test_the_resolutions_come_back_ranked(self) -> None:
        search = cw_gaps.search_gaps(TWO_DEMANDS, frozenset({"EX", "AX"}))
        self.assertEqual(search.resolutions, cw_gaps.rank(search.resolutions))

    def test_the_analysis_is_carried_alongside(self) -> None:
        search = cw_gaps.search_gaps(TWO_DEMANDS, frozenset())
        self.assertEqual(search.analysis, cw_gaps.analyze_grid(TWO_DEMANDS))

    def test_the_vocabulary_size_is_recorded(self) -> None:
        # The report leads with it, and zero is how it tells a reader that no
        # vocabulary was supplied rather than that none of it matched.
        search = cw_gaps.search_gaps(TWO_DEMANDS, frozenset({"EX", "AX"}))
        self.assertEqual(search.vocabulary_size, 2)

    def test_every_candidate_is_resolved(self) -> None:
        search = cw_gaps.search_gaps(TWO_DEMANDS, frozenset())
        self.assertEqual(len(search.resolutions), len(search.analysis.candidates))


if __name__ == "__main__":
    unittest.main()
