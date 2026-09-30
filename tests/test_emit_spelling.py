"""Tests for what `grid_source.json` carries for a multi-word answer.

The clue key stays the letters read off the grid, so the document format does
not change; the enumeration rides at the end of the answer's own clue, and only
where the bank wrote one.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import unittest

import cw_bank
import cw_emit
import cw_grid
import cw_place
import cw_search
from tests.emit_fixtures import _clues
from tests.search_fixtures import config as _config


def _outcome(answer: str) -> cw_search.SearchOutcome:
    """A one-row grid holding `answer` alone, across from the corner."""
    return cw_search.SearchOutcome(
        rows=(answer,),
        placed=(cw_place.Placement(answer, 0, 0, cw_grid.ACROSS),),
        conforming=True,
        missed=(),
        steps=1,
    )


def _emitted(written: str, clue: str | None) -> dict[str, dict[str, str]]:
    """The clue table emitted for a grid of `written`, parsed from a real bank."""
    record: dict[str, object] = {"answer": written}
    if clue is not None:
        record["clue"] = clue
    bank = cw_bank.parse_bank({"themes": {}, "entries": [record]})
    (entry,) = bank.entries
    document = cw_emit.build_document(_outcome(entry.answer), bank, _config())
    return {key: dict(value) for key, value in _clues(document).items()}


class TestEnumeratedClues(unittest.TestCase):
    """A clued multi-word answer's clue ends with its enumeration."""

    def test_a_space_is_a_comma(self) -> None:
        self.assertEqual(
            _emitted("HELLO THERE", "Greeting"),
            {"HELLOTHERE": {"clue": "Greeting (5,5)"}},
        )

    def test_a_hyphen_is_a_hyphen(self) -> None:
        clues = _emitted("ATTA-BOY", "Well done")
        self.assertEqual(clues["ATTABOY"]["clue"], "Well done (4-3)")

    def test_an_apostrophe_is_neither_counted_nor_a_break(self) -> None:
        clues = _emitted("JACK-O'-LANTERN", "Carved gourd")
        self.assertEqual(clues["JACKOLANTERN"]["clue"], "Carved gourd (4-1-7)")

    def test_an_unclued_answer_stays_unclued(self) -> None:
        self.assertEqual(_emitted("HELLO THERE", None), {"HELLOTHERE": {"clue": ""}})

    def test_an_enumeration_typed_by_hand_is_not_doubled(self) -> None:
        clues = _emitted("HELLO THERE", "Greeting (5,5)")
        self.assertEqual(clues["HELLOTHERE"]["clue"], "Greeting (5,5)")

    def test_one_word_with_an_apostrophe_keeps_its_clue(self) -> None:
        clues = _emitted("O'CLOCK", "On the hour")
        self.assertEqual(clues["OCLOCK"]["clue"], "On the hour")

    def test_a_letters_only_answer_keeps_its_clue(self) -> None:
        self.assertEqual(
            _emitted("HELLOTHERE", "Greeting"), {"HELLOTHERE": {"clue": "Greeting"}}
        )


if __name__ == "__main__":
    unittest.main()
