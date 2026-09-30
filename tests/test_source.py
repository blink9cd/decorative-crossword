"""Tests for cw_source.start_from: which --source grids a fill can start from.

Every source entry must be a bank answer or a key of the source's own `clues`
map; the second kind is KEPT, carried with its source clue and theme. A run that
is neither, but that some unused bank answer could still be laid over, is a
PARTIAL run the fill must complete. A source that repeats an answer, holds a
barred entry, or holds a run nothing declares and nothing could complete is
refused.
"""

import unittest
from collections.abc import Mapping, Sequence

import cw_bank
import cw_excluded_terms
import cw_grid
import cw_grid_document
import cw_source

from tests.search_fixtures import theme_records


def _document(
    rows: Sequence[str],
    clues: Mapping[str, object] | None = None,
    themes: Mapping[str, object] | None = None,
) -> cw_grid_document.GridDocument:
    """A parsed source document holding `rows`, its clue records and themes."""
    return cw_grid_document.parse_document(
        {"rows": list(rows), "themes": themes or {}, "clues": clues or {}}
    )


def _bank(*pairs: tuple[str, str | None]) -> cw_bank.Bank:
    """A bank of (answer, theme) pairs over themes a, b and c."""
    return cw_bank.Bank(
        themes=theme_records({"a": "A", "b": "B", "c": "C"}),
        entries=tuple(
            cw_bank.BankEntry(answer, theme, None) for answer, theme in pairs
        ),
    )


#: CAT across and COW down share the C; WET sits alone on the bottom row.
_ROWS = ("CAT", "O..", "WET")


class TestStartFrom(unittest.TestCase):
    """What a source must hold, and what comes back when it does."""

    def test_a_source_of_bank_answers_keeps_nothing_and_leaves_the_bank(self) -> None:
        bank = _bank(("CAT", "a"), ("COW", "b"), ("WET", None))
        start = cw_source.start_from(_document(_ROWS), bank, (), None)
        self.assertEqual(start.kept, ())
        self.assertEqual(start.bank.entries, bank.entries)

    def test_a_declared_run_the_bank_lacks_is_kept_with_its_own_clue_and_theme(
        self,
    ) -> None:
        bank = _bank(("CAT", "a"), ("WET", None))
        document = _document(
            _ROWS,
            clues={"COW": {"clue": "Barn resident", "theme": "farm"}},
            themes={"farm": {"label": "Farm", "summary": "Mostly cows"}},
        )
        start = cw_source.start_from(document, bank, (), None)
        self.assertEqual(start.kept, ("COW",))
        self.assertEqual(start.bank.entries[: len(bank.entries)], bank.entries)
        self.assertEqual(
            start.bank.entries[-1], cw_bank.BankEntry("COW", "farm", "Barn resident")
        )
        self.assertEqual(start.bank.themes["farm"].summary, "Mostly cows")

    def test_the_banks_theme_record_wins_over_the_sources(self) -> None:
        bank = _bank(("CAT", "a"), ("WET", None))
        document = _document(
            _ROWS,
            clues={"COW": {"theme": "b"}},
            themes={"b": {"label": "Other", "summary": "The source's words"}},
        )
        start = cw_source.start_from(document, bank, (), None)
        self.assertEqual(start.bank.themes["b"], bank.themes["b"])

    def test_every_run_nothing_declares_is_named(self) -> None:
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(_document(_ROWS), _bank(("CAT", "a")), (), None)
        message = str(caught.exception)
        self.assertIn("'COW'", message)
        self.assertIn("'WET'", message)
        self.assertIn("--source", message)
        self.assertIn("nor completable by a bank answer", message)

    def test_an_answer_the_source_holds_twice_is_refused(self) -> None:
        rows = ("CAT", "...", "CAT")
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(_document(rows), _bank(("CAT", "a")), (), None)
        self.assertIn("'CAT'", str(caught.exception))
        self.assertIn("twice", str(caught.exception))

    def test_a_bank_entry_the_screen_dropped_is_refused_not_kept(self) -> None:
        # Declared in the source AND dropped from the bank: keeping it would let
        # the source smuggle past the very screen that removed it.
        document = _document(_ROWS, clues={"WET": {}})
        bank = _bank(("CAT", "a"), ("COW", "b"))
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(document, bank, (("WET", "matched"),), None)
        self.assertIn("--excluded-terms", str(caught.exception))
        self.assertIn("'WET'", str(caught.exception))

    def test_a_kept_entry_a_term_bars_is_refused(self) -> None:
        document = _document(_ROWS, clues={"WET": {}})
        bank = _bank(("CAT", "a"), ("COW", "b"))
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(document, bank, (), frozenset({"wet"}))
        self.assertIn("--excluded-terms", str(caught.exception))
        self.assertIn("'WET'", str(caught.exception))

    def test_kept_entries_come_back_in_run_scan_order(self) -> None:
        # TOE across the top, ARM across the bottom, neither in the bank. Scan
        # order puts TOE first; sorting, or the clues map's own order, puts ARM
        # first. The search bank and the report's kept line both read this order.
        document = _document(("TOE", "...", "ARM"), clues={"ARM": {}, "TOE": {}})
        start = cw_source.start_from(document, _bank(), (), None)
        self.assertEqual(start.kept, ("TOE", "ARM"))

    def test_a_term_that_bars_no_kept_entry_leaves_it_kept(self) -> None:
        document = _document(_ROWS, clues={"WET": {"clue": "Just rained on"}})
        bank = _bank(("CAT", "a"), ("COW", "b"))
        start = cw_source.start_from(document, bank, (), frozenset({"dry"}))
        self.assertEqual(start.kept, ("WET",))
        self.assertEqual(
            start.bank.entries[-1], cw_bank.BankEntry("WET", None, "Just rained on")
        )

    def test_a_kept_entry_is_held_to_the_banks_own_parse_rules(self) -> None:
        # A theme neither the bank nor the source declares: bank.json refuses it.
        document = _document(_ROWS, clues={"WET": {"theme": "nowhere"}})
        bank = _bank(("CAT", "a"), ("COW", "b"))
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(document, bank, (), None)
        self.assertIn("nowhere", str(caught.exception))
        self.assertIn("--source", str(caught.exception))

    def test_every_kept_entry_the_banks_parser_refuses_is_named(self) -> None:
        document = _document(
            _ROWS,
            clues={"WET": {"theme": "elsewhere"}, "COW": {"theme": "nowhere"}},
        )
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(document, _bank(("CAT", "a")), (), None)
        message = str(caught.exception)
        for named in ("'WET'", "elsewhere", "'COW'", "nowhere"):
            self.assertIn(named, message)

    def test_a_dropped_bank_entry_and_a_barred_kept_entry_are_named_together(
        self,
    ) -> None:
        # One check covers a barred entry whether it came from the bank or the
        # source: a source holding one of each must name both, not stop at the
        # first kind.
        terms = frozenset({"wet", "cow"})
        screened, dropped = cw_excluded_terms.screen_excluded(
            _bank(("CAT", "a"), ("WET", None)), terms
        )
        document = _document(_ROWS, clues={"COW": {}})
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(document, screened, dropped, terms)
        message = str(caught.exception)
        for named in ("--excluded-terms", "'WET'", "'COW'"):
            self.assertIn(named, message)

    def test_a_dropped_entry_the_source_declares_is_never_parsed_as_kept(self) -> None:
        # Its theme is declared nowhere, so parsing it as a kept entry would
        # refuse it for THAT; the screen is the reason it must be refused for.
        document = _document(_ROWS, clues={"WET": {"theme": "nowhere"}})
        bank = _bank(("CAT", "a"), ("COW", "b"))
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(document, bank, (("WET", "matched"),), None)
        self.assertIn("--excluded-terms", str(caught.exception))
        self.assertNotIn("nowhere", str(caught.exception))


class TestPartialRuns(unittest.TestCase):
    """A run no one declares is completed when an unused bank answer fits over it."""

    def test_a_run_a_bank_answer_could_complete_is_partial_not_refused(self) -> None:
        start = cw_source.start_from(
            _document(("JAN.", "....")), _bank(("JANE", "a")), (), None
        )
        self.assertEqual(start.partial, (_across(0, 0, "JAN"),))
        self.assertEqual(start.kept, ())

    def test_a_completion_may_fill_a_gap_inside_the_line(self) -> None:
        # JA and a lone E, with a block between: JANE lays over all three cells.
        start = cw_source.start_from(
            _document(("JA.E", "....")), _bank(("JANE", "a")), (), None
        )
        self.assertEqual(start.partial, (_across(0, 0, "JA"),))

    def test_a_declared_run_is_kept_even_where_a_bank_answer_extends_it(self) -> None:
        # The declaration wins: a kept entry is held as its exact run, so JAN
        # never becomes JANE. Growing an entry is a separate question.
        document = _document(("JAN.", "...."), clues={"JAN": {}})
        start = cw_source.start_from(document, _bank(("JANE", "a")), (), None)
        self.assertEqual(start.kept, ("JAN",))
        self.assertEqual(start.partial, ())

    def test_an_answer_already_on_the_source_cannot_complete_a_run(self) -> None:
        # JANE stands on row 0, so it is used: nothing else could finish JAN.
        with self.assertRaises(cw_source.SourceError) as caught:
            cw_source.start_from(
                _document(("JANE", "....", "JAN.")), _bank(("JANE", "a")), (), None
            )
        self.assertIn("'JAN' across at (2, 0)", str(caught.exception))
        self.assertIn("nor completable by a bank answer", str(caught.exception))

    def test_two_partial_runs_spelling_the_same_letters_are_no_repeat(self) -> None:
        # A repeat is an ANSWER held twice; AN is no answer, and ANT and AND
        # could finish the two copies differently.
        start = cw_source.start_from(
            _document(("AN..", "....", "AN..")),
            _bank(("ANT", "a"), ("AND", "b")),
            (),
            None,
        )
        self.assertEqual(start.partial, (_across(0, 0, "AN"), _across(2, 0, "AN")))


def _across(row: int, col: int, text: str) -> cw_grid.Run:
    """The ACROSS run `text` starting at (row, col)."""
    return cw_grid.Run(row=row, col=col, direction=cw_grid.ACROSS, text=text)


if __name__ == "__main__":
    unittest.main()
