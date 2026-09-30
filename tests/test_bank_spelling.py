"""Tests for a bank answer written with spaces, hyphens or apostrophes.

The bank keys such an entry by its GRID form, letters only, and keeps what the
operator wrote as `spelling`. Everything that compares answers -- the repeat
check, the merge of several banks, the `--excluded-terms` screen -- therefore
compares letters, and two spellings of one answer are one answer.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cw_answer
import cw_bank
import cw_bank_merge
import cw_excluded_terms


def _parsed(*answers: str) -> cw_bank.Bank:
    """A themeless bank of `answers`, through the parse boundary."""
    return cw_bank.parse_bank(
        {"themes": {}, "entries": [{"answer": answer} for answer in answers]}
    )


def _refusal(*answers: str) -> str:
    """The message `parse_bank` refuses a themeless bank of `answers` with."""
    try:
        _parsed(*answers)
    except cw_bank.BankError as exc:
        return str(exc)
    raise AssertionError(f"{answers!r} was accepted")


class TestSpelledAnswers(unittest.TestCase):
    """A written form is keyed by its letters and kept beside them."""

    def test_a_spaced_answer_is_keyed_by_its_letters(self) -> None:
        (entry,) = _parsed("HELLO THERE").entries
        self.assertEqual(entry.answer, "HELLOTHERE")
        self.assertEqual(entry.spelling, "HELLO THERE")

    def test_a_hyphen_and_an_apostrophe_close_up_too(self) -> None:
        (entry,) = _parsed("JACK-O'-LANTERN").entries
        self.assertEqual(entry.answer, "JACKOLANTERN")
        self.assertEqual(entry.spelling, "JACK-O'-LANTERN")

    def test_a_letters_only_answer_builds_the_entry_it_always_did(self) -> None:
        # Equal to a BankEntry built without the field: a letters-only answer
        # carries no spelling.
        (entry,) = cw_bank.parse_bank(
            {"themes": {}, "entries": [{"answer": "CHEMEX", "clue": "Hourglass"}]}
        ).entries
        self.assertEqual(entry, cw_bank.BankEntry("CHEMEX", None, "Hourglass"))
        self.assertIsNone(entry.spelling)

    def test_every_still_refused_shape_names_the_answer_and_the_rule(self) -> None:
        for answer in ("ST. ELMO", "R&B", "V60", "chemex", "HELLO  THERE", "-ISH"):
            with self.subTest(answer=answer):
                message = _refusal(answer)
                self.assertIn(repr(answer), message)
                self.assertIn(cw_answer.SPELLING_RULE, message)

    def test_a_later_refusal_names_the_answer_as_written(self) -> None:
        # The operator searches the file for what they wrote, not the letters.
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank(
                {"themes": {}, "entries": [{"answer": "HELLO THERE", "rating": 9}]}
            )
        self.assertIn("entry 'HELLO THERE' rating", str(caught.exception))

    def test_too_few_letters_once_closed_up_is_refused_for_length(self) -> None:
        message = _refusal("A'")
        self.assertIn("at least 2 letters", message)

    def test_two_spellings_of_one_answer_are_refused_naming_both(self) -> None:
        message = _refusal("ATTA-BOY", "ATTA BOY")
        self.assertIn("'ATTABOY' appears more than once in the bank", message)
        self.assertIn("'ATTA-BOY'", message)
        self.assertIn("'ATTA BOY'", message)

    def test_a_spelled_answer_repeating_its_grid_form_is_refused(self) -> None:
        self.assertIn("more than once", _refusal("HELLO THERE", "HELLOTHERE"))

    def test_an_identical_repeat_keeps_its_old_message(self) -> None:
        self.assertEqual(
            _refusal("BLOOM", "BLOOM"),
            "answer 'BLOOM' appears more than once in the bank",
        )


class TestMergedSpellings(unittest.TestCase):
    """Across `--bank` files, a different spelling is a different record."""

    def _merge(self, folder: str, *answers: str) -> cw_bank_merge.BankSet:
        """Merge one single-entry bank file per answer, in order."""
        paths = []
        for index, answer in enumerate(answers):
            path = Path(folder) / f"bank{index}.json"
            payload = {"themes": {}, "entries": [{"answer": answer}]}
            path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
            paths.append(path)
        return cw_bank_merge.load_banks(paths)

    def test_two_spellings_across_banks_are_refused_in_its_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_bank.BankError) as caught:
                self._merge(folder, "HELLO THERE", "HELLOTHERE")
        message = str(caught.exception)
        self.assertIn("'HELLOTHERE' differs between the bank files", message)
        self.assertIn("bank0.json", message)
        self.assertIn("bank1.json", message)
        self.assertIn("in its spelling", message)

    def test_one_spelling_in_two_banks_is_kept_once(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            merged = self._merge(folder, "HELLO THERE", "HELLO THERE")
        (entry,) = merged.bank.entries
        self.assertEqual((entry.answer, entry.spelling), ("HELLOTHERE", "HELLO THERE"))


class TestScreenThroughPunctuation(unittest.TestCase):
    """`--excluded-terms` reads a written answer both as written and closed up."""

    def _dropped(self, term: str, *answers: str) -> tuple[str, ...]:
        """The answers `term` screens out of a bank of `answers`."""
        _, dropped = cw_excluded_terms.screen_excluded(
            _parsed(*answers), frozenset({term})
        )
        return tuple(answer for answer, _ in dropped)

    def test_a_term_matching_as_written_or_closed_up_drops_the_answer(self) -> None:
        for term in ("hello there", "hello-there", "hellothere", "there"):
            with self.subTest(term=term):
                self.assertEqual(self._dropped(term, "HELLO THERE"), ("HELLOTHERE",))

    def test_a_term_inside_one_word_does_not(self) -> None:
        # Whole-word: THE is not a word of HELLO THERE.
        for term in ("the", "ello", "lothe"):
            with self.subTest(term=term):
                self.assertEqual(self._dropped(term, "HELLO THERE"), ())

    def test_a_spaced_term_drops_a_letters_only_answer(self) -> None:
        self.assertEqual(self._dropped("web site", "WEBSITE"), ("WEBSITE",))

    def test_the_reason_names_the_term_as_written(self) -> None:
        _, dropped = cw_excluded_terms.screen_excluded(
            _parsed("HELLO THERE"), frozenset({"hello-there"})
        )
        self.assertEqual(
            dropped,
            (("HELLOTHERE", "its answer matches the excluded term 'hello-there'"),),
        )


if __name__ == "__main__":
    unittest.main()
