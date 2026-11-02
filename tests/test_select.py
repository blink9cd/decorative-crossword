"""Tests for cw_select: what makes one conforming grid better than another,
and the look-ahead window a search chooses within.

The order of the score is the whole rule (most letters, then answers the operator
preferred, then the grid's worst rating, then its matching cell pairs under
--prefer-symmetry, then themed entries, then the growable --source entries still
standing), so each case below
gives the grid that should win the worse figure on every later level, and a score
that dropped or reordered a term picks the other one.
"""

import dataclasses
import statistics
import unittest

import cw_bank
import cw_grid
import cw_select

from tests.search_fixtures import entries_bank as _entries_bank


def _bank() -> cw_bank.Bank:
    """Two themed answers, three unthemed, one of them a longer CAT."""
    return _entries_bank(
        (("CAT", "a"), ("COW", "a"), ("DOG", None), ("EEL", None), ("CATS", None)),
        {"a": "A"},
    )


def _rated(bank: cw_bank.Bank, **ratings: int) -> cw_bank.Bank:
    """`bank` with the named answers rated and every other answer unrated."""
    return dataclasses.replace(
        bank,
        entries=tuple(
            dataclasses.replace(entry, rating=ratings.get(entry.answer))
            for entry in bank.entries
        ),
    )


def _snap(rows: tuple[str, ...]) -> cw_select.Snapshot:
    """A conforming snapshot of `rows`; only its rows matter to a selection."""
    return cw_select.Snapshot(rows=rows, placed=(), missed=(), rank=(0, 0.0, 0))


class TestGridScore(unittest.TestCase):
    """Letters, preferred answers, worst rating and themed entries, in the module's order."""

    def test_the_score_is_letters_preferred_worst_rating_and_themed(self) -> None:
        bank = _rated(_bank(), COW=2)
        self.assertEqual(
            cw_select.grid_score(("CAT..", ".....", "COW.."), bank, ("COW", "DOG")),
            (6, 1, 2, 0, 2, 0),
        )

    def test_more_letters_outrank_every_later_level(self) -> None:
        # The sparser grid holds both themed answers, the preferred one, and only
        # top-rated words; the denser holds a bottom-rated word and none of the
        # rest, and still wins on letters.
        bank = _rated(_bank(), CAT=5, COW=5, DOG=1)
        dense = ("CATS.", ".....", "DOG..")
        sparse = ("CAT..", ".....", "COW..")
        self.assertGreater(
            cw_select.grid_score(dense, bank, ("CAT",)),
            cw_select.grid_score(sparse, bank, ("CAT",)),
        )

    def test_a_preferred_answer_breaks_a_tie_on_letters(self) -> None:
        # Both hold one themed answer, so only the preference can separate them.
        cat = ("CAT..", ".....", "DOG..")
        cow = ("COW..", ".....", "DOG..")
        self.assertGreater(
            cw_select.grid_score(cow, _bank(), ("COW",)),
            cw_select.grid_score(cat, _bank(), ("COW",)),
        )

    def test_themed_entries_break_a_tie_on_every_earlier_level(self) -> None:
        # Nothing is rated, so both grids tie on the worst rating as well.
        themed = ("CAT..", ".....", "DOG..")
        plain = ("EEL..", ".....", "DOG..")
        self.assertGreater(
            cw_select.grid_score(themed, _bank(), ()),
            cw_select.grid_score(plain, _bank(), ()),
        )


class TestWorstRating(unittest.TestCase):
    """The grid's worst entry, never an average; unrated counts as the middle."""

    _CAT = ("CAT..", ".....", "DOG..")
    _COW = ("COW..", ".....", "DOG..")

    def test_a_higher_worst_rating_breaks_a_tie_on_letters_and_preferences(
        self,
    ) -> None:
        # Each holds one themed answer beside the unrated DOG, so only the rating
        # of CAT against COW can separate them.
        bank = _rated(_bank(), CAT=1, COW=4)
        self.assertGreater(
            cw_select.grid_score(self._COW, bank, ()),
            cw_select.grid_score(self._CAT, bank, ()),
        )

    def test_a_better_average_cannot_hide_one_bad_entry(self) -> None:
        # The anti-averaging rule, pinned. One clunker behind two favorites
        # averages higher than three ordinary words, and loses to them: a reader
        # notices the one bad entry, not the mean. The first assertion keeps the
        # premise true, so a fixture edit cannot quietly make this test vacuous.
        clunker, steady = ("ASH", "BAY", "COD"), ("DEW", "ELM", "FIG")
        ratings = {"ASH": 5, "BAY": 5, "COD": 1, "DEW": 3, "ELM": 3, "FIG": 3}
        bank = _rated(
            _entries_bank(tuple((answer, None) for answer in ratings), {}), **ratings
        )
        self.assertGreater(
            statistics.mean(ratings[answer] for answer in clunker),
            statistics.mean(ratings[answer] for answer in steady),
        )
        self.assertGreater(
            cw_select.grid_score((".".join(steady),), bank, ()),
            cw_select.grid_score((".".join(clunker),), bank, ()),
        )

    def test_an_unrated_answer_counts_as_the_middle_of_the_scale(self) -> None:
        # DOG stays unrated throughout; only the ratings named below move.
        def score(**ratings: int) -> tuple[int, ...]:
            return cw_select.grid_score(self._CAT, _rated(_bank(), **ratings), ())

        unrated = score()
        self.assertEqual(score(CAT=cw_bank.NEUTRAL_RATING), unrated)
        self.assertLess(score(CAT=cw_bank.NEUTRAL_RATING - 1), unrated)
        # Rating CAT at the top does not lift a grid whose DOG is unrated: its
        # worst entry is still DOG, at the middle. Rating both above it does.
        self.assertEqual(score(CAT=cw_bank.MAX_RATING), unrated)
        self.assertGreater(score(CAT=4, DOG=4), unrated)

    def test_a_preferred_answer_outranks_a_better_worst_rating(self) -> None:
        # CAT is preferred and rated at the bottom, COW rated at the top: the
        # preference typed for this run wins over the standing rating.
        bank = _rated(_bank(), CAT=1, COW=5)
        self.assertGreater(
            cw_select.grid_score(self._CAT, bank, ("CAT",)),
            cw_select.grid_score(self._COW, bank, ("CAT",)),
        )

    def test_a_better_worst_rating_outranks_more_themed_entries(self) -> None:
        bank = _rated(_bank(), CAT=1)
        plain = ("EEL..", ".....", "DOG..")
        self.assertGreater(
            cw_select.grid_score(plain, bank, ()),
            cw_select.grid_score(self._CAT, bank, ()),
        )


#: Six letters each, one themed (CAT) and one not (EEL); only EEL's grid is
#: balanced under rotation: 3 of 7 rotated pairs match against 7 of 7.
_UNBALANCED = ("CAT..", ".....", "DOG..")
_BALANCED = ("EEL..", ".....", "..DOG")


class TestSymmetryLevel(unittest.TestCase):
    """Matching cell pairs: after the worst rating, ahead of themed entries."""

    def test_without_a_kind_the_level_is_zero_for_every_grid(self) -> None:
        # What keeps a run without --prefer-symmetry choosing on the other levels.
        for rows in (_BALANCED, _UNBALANCED):
            with self.subTest(rows=rows):
                self.assertEqual(cw_select.grid_score(rows, _bank(), ())[3], 0)

    def test_a_kind_counts_the_grid_s_matching_pairs(self) -> None:
        self.assertEqual(
            cw_select.grid_score(_UNBALANCED, _bank(), ("COW",), (), "rotational"),
            (6, 0, 3, 3, 1, 0),
        )

    def test_symmetry_outranks_more_themed_entries(self) -> None:
        # The premise first: without a kind, the themed CAT decides.
        bank = _bank()
        self.assertGreater(
            cw_select.grid_score(_UNBALANCED, bank, ()),
            cw_select.grid_score(_BALANCED, bank, ()),
        )
        self.assertGreater(
            cw_select.grid_score(_BALANCED, bank, (), (), "rotational"),
            cw_select.grid_score(_UNBALANCED, bank, (), (), "rotational"),
        )

    def test_a_better_worst_rating_outranks_symmetry(self) -> None:
        # A word rated a clunker still loses, however balanced its grid.
        bank = _rated(_bank(), EEL=1)
        self.assertGreater(
            cw_select.grid_score(_UNBALANCED, bank, (), (), "rotational"),
            cw_select.grid_score(_BALANCED, bank, (), (), "rotational"),
        )

    def test_a_preferred_answer_outranks_symmetry(self) -> None:
        self.assertGreater(
            cw_select.grid_score(_UNBALANCED, _bank(), ("CAT",), (), "rotational"),
            cw_select.grid_score(_BALANCED, _bank(), ("CAT",), (), "rotational"),
        )

    def test_more_letters_outrank_symmetry(self) -> None:
        denser = ("CATS.", ".....", "DOG..")
        self.assertGreater(
            cw_select.grid_score(denser, _bank(), (), (), "rotational"),
            cw_select.grid_score(_BALANCED, _bank(), (), (), "rotational"),
        )


#: CAT across the top of a 3x5, as a source entry `--absorb-entries` may grow.
_CAT_ENTRY = cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="CAT")


class TestKeptSourceEntries(unittest.TestCase):
    """The last level: of grids tying on every other one, keeping a source entry wins."""

    def test_the_level_counts_the_growable_entries_still_standing(self) -> None:
        self.assertEqual(
            cw_select.grid_score(
                ("CAT..", ".....", "DOG.."), _bank(), (), (_CAT_ENTRY,)
            ),
            (6, 0, 3, 0, 1, 1),
        )
        self.assertEqual(
            cw_select.grid_score(
                ("CATS.", ".....", "EEL.."), _bank(), (), (_CAT_ENTRY,)
            ),
            (7, 0, 3, 0, 0, 0),
        )

    def test_keeping_an_entry_breaks_a_tie_on_every_other_level(self) -> None:
        # Seven letters and one themed answer each; one grid grew CAT into CATS.
        kept = ("CAT..", ".....", "COWS.")
        grown = ("CATS.", ".....", "COW..")
        bank = _entries_bank(
            (("CAT", "a"), ("CATS", "a"), ("COW", None), ("COWS", None)), {"a": "A"}
        )
        self.assertGreater(
            cw_select.grid_score(kept, bank, (), (_CAT_ENTRY,)),
            cw_select.grid_score(grown, bank, (), (_CAT_ENTRY,)),
        )

    def test_a_themed_entry_outranks_keeping_a_source_entry(self) -> None:
        # The grown grid holds one more themed answer, and ties on the rest:
        # growth pays there, so it wins.
        kept = ("CAT..", ".....", "EELS.")
        grown = ("CATS.", ".....", "EEL..")
        bank = _entries_bank(
            (("CAT", None), ("CATS", "a"), ("EEL", None), ("EELS", None)), {"a": "A"}
        )
        self.assertGreater(
            cw_select.grid_score(grown, bank, (), (_CAT_ENTRY,)),
            cw_select.grid_score(kept, bank, (), (_CAT_ENTRY,)),
        )


class TestSelection(unittest.TestCase):
    """The first grid opens the window; a better one replaces it; ties keep the first."""

    _A = ("CAT..", ".....", "DOG..")
    _B = ("COW..", ".....", "DOG..")

    def test_the_first_offer_is_chosen(self) -> None:
        selection = cw_select.Selection(10)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        self.assertIsNotNone(selection.chosen)
        self.assertEqual(getattr(selection.chosen, "rows", None), self._A)
        self.assertEqual(selection.compared, 1)

    def test_a_tie_keeps_the_grid_found_first(self) -> None:
        selection = cw_select.Selection(10)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        selection.offer(_snap(self._B), (6, 0, 3, 0, 1, 0), 6)
        self.assertEqual(getattr(selection.chosen, "rows", None), self._A)
        self.assertEqual(selection.compared, 2)

    def test_a_higher_score_replaces_the_choice(self) -> None:
        selection = cw_select.Selection(10)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        selection.offer(_snap(self._B), (6, 0, 4, 0, 1, 0), 6)
        self.assertEqual(getattr(selection.chosen, "rows", None), self._B)

    def test_the_same_grid_reached_twice_is_compared_once(self) -> None:
        # Two placement orders can reach one grid; counting it twice would
        # overstate how many grids the report says were compared.
        selection = cw_select.Selection(10)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 7)
        self.assertEqual(selection.compared, 1)

    def test_the_window_closes_look_ahead_nodes_after_the_first_offer(self) -> None:
        selection = cw_select.Selection(3)
        self.assertFalse(selection.closed(100), "no window before any offer")
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        self.assertFalse(selection.closed(7))
        self.assertTrue(selection.closed(8))

    def test_a_look_ahead_of_zero_closes_at_the_first_offer(self) -> None:
        selection = cw_select.Selection(0)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        self.assertTrue(selection.closed(5))

    def test_a_later_offer_does_not_move_the_window(self) -> None:
        # The window is measured from the first grid. Reopening it on every better
        # grid would let a long run of small improvements search without end.
        selection = cw_select.Selection(3)
        selection.offer(_snap(self._A), (6, 0, 3, 0, 1, 0), 5)
        selection.offer(_snap(self._B), (6, 1, 3, 0, 1, 0), 7)
        self.assertTrue(selection.closed(8))
