"""Tests for cw_search under `--absorb-entries`: a --source entry the bank holds may grow.

Without the flag every source entry is held as its exact run (`test_search_source`
pins that). With it, an entry the bank holds may be absorbed into a longer bank
answer lying along all of its cells -- grown at either end, or welded to another
entry through a filled block -- and every source letter stays where it was. A
`--feature` pin, and an entry kept only because the source declares it, are still
held exactly. Every grid here is wider than tall, so a transposed read cannot pass.
"""

import unittest

import cw_grid
import cw_search

from tests.search_fixtures import bank as _bank
from tests.search_fixtures import config as _config
from tests.search_fixtures import pin as _pin
from tests.search_fixtures import still as _still

#: JANE across the top of a 3x5: 73.3% blocked, JANET over it 66.7%.
_JANE = ("JANE.", ".....", ".....")


def _across(row: int, col: int, text: str) -> cw_grid.Run:
    """The ACROSS run `text` starting at (row, col)."""
    return cw_grid.Run(row=row, col=col, direction=cw_grid.ACROSS, text=text)


def _keeps_every_letter(start: tuple[str, ...], rows: tuple[str, ...]) -> bool:
    """Whether every letter of `start` is still in `rows`, at its own cell."""
    return all(
        cell in (cw_grid.BLOCK, rows[r][c])
        for r, line in enumerate(start)
        for c, cell in enumerate(line)
    )


class TestAnEntryGrows(unittest.TestCase):
    """A bank-held source entry is absorbed into a longer answer covering it."""

    def test_an_entry_grows_at_its_end(self) -> None:
        outcome = cw_search.search(
            _bank(["JANE", "JANET"]),
            _config(
                rows=3,
                cols=5,
                start=_JANE,
                min_themes=0,
                max_blocked=70.0,
                absorb_entries=True,
            ),
            clock=_still,
        )
        self.assertTrue(outcome.conforming, outcome.missed)
        self.assertEqual(outcome.rows[0], "JANET")
        self.assertTrue(_keeps_every_letter(_JANE, outcome.rows))

    def test_an_entry_grows_before_its_first_letter(self) -> None:
        start = (".ARM", "....")
        outcome = cw_search.search(
            _bank(["ARM", "FARM"]),
            _config(
                rows=2,
                cols=4,
                start=start,
                min_themes=0,
                max_blocked=60.0,
                absorb_entries=True,
            ),
            clock=_still,
        )
        self.assertTrue(outcome.conforming, outcome.missed)
        self.assertIn(_across(0, 0, "FARM"), cw_grid.runs_from_rows(outcome.rows))
        self.assertTrue(_keeps_every_letter(start, outcome.rows))

    def test_two_entries_weld_through_a_filled_block(self) -> None:
        start = ("SUN.LOWER", ".........", ".........")
        outcome = cw_search.search(
            _bank(["SUN", "LOWER", "SUNFLOWER"]),
            _config(
                rows=3,
                cols=9,
                start=start,
                min_themes=0,
                max_blocked=68.0,
                absorb_entries=True,
            ),
            clock=_still,
        )
        self.assertTrue(outcome.conforming, outcome.missed)
        self.assertEqual(outcome.rows[0], "SUNFLOWER")
        self.assertTrue(_keeps_every_letter(start, outcome.rows))


class TestWhatStaysHeld(unittest.TestCase):
    """A pin and a kept entry are held as their exact runs even under the flag."""

    def test_a_pin_lying_on_the_source_entry_is_never_extended(self) -> None:
        # The pin asks for JANE exactly where the source holds it. JANET would
        # conform, so a walk that let the pin grow would return it.
        outcome = cw_search.search(
            _bank(["JANE", "JANET"]),
            _config(
                rows=3,
                cols=5,
                start=_JANE,
                min_themes=0,
                max_blocked=70.0,
                features=(_pin("JANE", 0, 0, cw_grid.ACROSS),),
                absorb_entries=True,
            ),
            clock=_still,
        )
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.rows, _JANE)

    def test_a_pin_off_the_source_is_never_extended(self) -> None:
        # CAT is the source's only entry and may grow into nothing here; JANE is
        # pinned on a blank row. 7 letters leave 53.3% blocked and JANET's 8
        # would leave 46.7%, inside the 50% ceiling: only a pin let go conforms.
        outcome = cw_search.search(
            _bank(["CAT", "JANE", "JANET"]),
            _config(
                rows=3,
                cols=5,
                start=("CAT..", ".....", "....."),
                min_themes=0,
                max_blocked=50.0,
                features=(_pin("JANE", 2, 0, cw_grid.ACROSS),),
                absorb_entries=True,
            ),
            clock=_still,
        )
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.rows, ("CAT..", ".....", "JANE."))

    def test_an_entry_kept_outside_the_bank_is_never_extended(self) -> None:
        # OX is in the search bank only because the source declared it. OXEN
        # would conform, and would retire the one thing vouching for OX.
        start = ("OX...", ".....", ".....")
        outcome = cw_search.search(
            _bank(["OX", "OXEN"]),
            _config(
                rows=3,
                cols=5,
                start=start,
                min_themes=0,
                max_blocked=80.0,
                absorb_entries=True,
            ),
            clock=_still,
            kept=("OX",),
        )
        self.assertFalse(outcome.conforming)
        self.assertEqual(outcome.rows, start)


class TestKeepingAnEntryBreaksATie(unittest.TestCase):
    """Of two grids tying on every other level, the one keeping the entry is chosen."""

    def test_the_grid_keeping_the_entry_wins_under_every_seed(self) -> None:
        # JANE with JO down, and JANET, both hold five letters and nothing else
        # separates them; JANET and JO together fall under the 62% floor.
        # Measured with the level removed: seeds 6, 11 and 12 choose JANET, and
        # seed 1 chooses JO -- so each seed here decides nothing but the level.
        for seed in (1, 6, 11, 12):
            with self.subTest(seed=seed):
                outcome = cw_search.search(
                    _bank(["JANE", "JANET", "JO"]),
                    _config(
                        rows=3,
                        cols=5,
                        start=_JANE,
                        min_themes=0,
                        min_blocked=62.0,
                        max_blocked=70.0,
                        look_ahead=50,
                        seed=seed,
                        absorb_entries=True,
                    ),
                    clock=_still,
                )
                self.assertTrue(outcome.conforming, outcome.missed)
                self.assertEqual(outcome.rows, ("JANE.", "O....", "....."))


if __name__ == "__main__":
    unittest.main()
