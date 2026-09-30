"""Grouped suite: merging several bank files into the one bank a run searches.

`fill` and `gaps` take `--bank` more than once, so one run can draw on a
site-wide bank and a small per-grid bank of names without a hand-built copy of
both. These cases prove what the merge decides: the order the banks are given
is the order of their themes and entries, an identical record in two banks is
kept once, and every disagreement between two banks is refused by naming both
files. Which subcommand hands over which files is `test_cli_banks.py`'s.

A lone bank has to read exactly as `cw_bank.parse_bank` reads it, down to the
words of its refusals, which is why several cases compare against that function
itself rather than against a restated message.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cw_bank
import cw_bank_merge

#: A theme record, and the same key declared with a different summary.
_THEME_A = {"label": "A", "summary": "The first theme"}
_THEME_A_ELSEWHERE = {"label": "A", "summary": "Another summary"}

#: The first bank of most cases: one theme, two answers.
_MAIN: dict[str, object] = {
    "themes": {"a": _THEME_A},
    "entries": [{"answer": "ALPHA", "theme": "a"}, {"answer": "AMBER"}],
}

#: A names bank declaring no theme of its own.
_NAMES: dict[str, object] = {"themes": {}, "entries": [{"answer": "JANE"}]}


def _answers(bank: cw_bank.Bank) -> list[str]:
    """The bank's answers, in its entry order."""
    return [entry.answer for entry in bank.entries]


def _keys(count: int) -> list[str]:
    """`count` distinct four-letter answers, `QXAA` onward, in order."""
    return [
        f"QX{chr(65 + index // 26)}{chr(65 + index % 26)}" for index in range(count)
    ]


def _rated_banks(count: int) -> tuple[cw_bank_merge.BankFile, ...]:
    """Two banks holding the same `count` answers, every one rated differently."""
    return tuple(
        (
            name,
            {
                "themes": {},
                "entries": [{"answer": a, "rating": r} for a in _keys(count)],
            },
        )
        for name, r in (("main", 1), ("names", 2))
    )


def _summarized_banks(count: int) -> tuple[cw_bank_merge.BankFile, ...]:
    """Two banks declaring the same `count` themes, every one summarized differently."""
    return tuple(
        (
            name,
            {
                "themes": {k: {"label": k, "summary": summary} for k in _keys(count)},
                "entries": [{"answer": name.upper()}],
            },
        )
        for name, summary in (("main", "One"), ("names", "Two"))
    )


class TestMergeOrder(unittest.TestCase):
    """The banks' records, in the order the banks were given."""

    def test_a_lone_bank_reads_as_parse_bank_reads_it(self) -> None:
        merged = cw_bank_merge.parse_banks((("main.json", _MAIN),))
        self.assertEqual(merged.bank, cw_bank.parse_bank(_MAIN))
        self.assertEqual(merged.files, (("main.json", 2),))

    def test_entries_follow_the_order_the_banks_are_given(self) -> None:
        forward = cw_bank_merge.parse_banks((("main", _MAIN), ("names", _NAMES)))
        backward = cw_bank_merge.parse_banks((("names", _NAMES), ("main", _MAIN)))
        self.assertEqual(_answers(forward.bank), ["ALPHA", "AMBER", "JANE"])
        self.assertEqual(_answers(backward.bank), ["JANE", "ALPHA", "AMBER"])

    def test_themes_follow_the_order_the_banks_are_given(self) -> None:
        other = {
            "themes": {"b": {"label": "B", "summary": "The second theme"}},
            "entries": [{"answer": "BRAVO", "theme": "b"}],
        }
        forward = cw_bank_merge.parse_banks((("main", _MAIN), ("other", other)))
        backward = cw_bank_merge.parse_banks((("other", other), ("main", _MAIN)))
        self.assertEqual(list(forward.bank.themes), ["a", "b"])
        self.assertEqual(list(backward.bank.themes), ["b", "a"])

    def test_each_file_counts_its_own_entries(self) -> None:
        names = {"themes": {}, "entries": [{"answer": "AMBER"}, {"answer": "JANE"}]}
        merged = cw_bank_merge.parse_banks((("main", _MAIN), ("names", names)))
        self.assertEqual(merged.files, (("main", 2), ("names", 2)))
        self.assertEqual(_answers(merged.bank), ["ALPHA", "AMBER", "JANE"])


class TestRecordsInTwoBanks(unittest.TestCase):
    """The same answer, or theme, in more than one bank."""

    def test_an_identical_record_is_kept_once_where_it_first_appears(self) -> None:
        names = {"themes": {}, "entries": [{"answer": "JANE"}, {"answer": "AMBER"}]}
        merged = cw_bank_merge.parse_banks((("main", _MAIN), ("names", names)))
        self.assertEqual(_answers(merged.bank), ["ALPHA", "AMBER", "JANE"])

    def test_a_record_that_differs_is_refused_naming_both_files(self) -> None:
        names = {"themes": {}, "entries": [{"answer": "AMBER", "clue": "Resin"}]}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main.json", _MAIN), ("names.json", names)))
        message = str(caught.exception)
        for part in ("'AMBER'", "main.json", "names.json", "clue"):
            self.assertIn(part, message)

    def test_every_field_that_differs_is_named(self) -> None:
        names = {
            "themes": {},
            "entries": [{"answer": "ALPHA", "clue": "First", "rating": 5}],
        }
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main", _MAIN), ("names", names)))
        for field in ("theme", "clue", "rating"):
            self.assertIn(field, str(caught.exception))

    def test_every_differing_answer_is_named_in_one_refusal(self) -> None:
        names = {
            "themes": {},
            "entries": [{"answer": "ALPHA"}, {"answer": "AMBER", "rating": 1}],
        }
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main", _MAIN), ("names", names)))
        self.assertIn("'ALPHA'", str(caught.exception))
        self.assertIn("'AMBER'", str(caught.exception))

    def test_a_theme_declared_differently_is_refused_naming_both_files(self) -> None:
        other = {"themes": {"a": _THEME_A_ELSEWHERE}, "entries": [{"answer": "JANE"}]}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main.json", _MAIN), ("other.json", other)))
        message = str(caught.exception)
        for part in ("theme 'a'", "main.json", "other.json", "summary"):
            self.assertIn(part, message)

    def test_a_theme_declared_identically_in_two_banks_merges(self) -> None:
        other = {"themes": {"a": dict(_THEME_A)}, "entries": [{"answer": "JANE"}]}
        merged = cw_bank_merge.parse_banks((("main", _MAIN), ("other", other)))
        self.assertEqual(list(merged.bank.themes), ["a"])

    def test_an_entry_may_name_a_theme_another_bank_declares(self) -> None:
        names = {"themes": {}, "entries": [{"answer": "JANE", "theme": "a"}]}
        merged = cw_bank_merge.parse_banks((("names", names), ("main", _MAIN)))
        self.assertEqual(merged.bank.by_answer()["JANE"].theme, "a")

    def test_a_theme_no_bank_declares_is_still_refused(self) -> None:
        names = {"themes": {}, "entries": [{"answer": "JANE", "theme": "z"}]}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main", _MAIN), ("names", names)))
        self.assertIn("undeclared theme 'z'", str(caught.exception))

    def test_a_repeat_inside_one_bank_is_still_refused(self) -> None:
        names = {"themes": {}, "entries": [{"answer": "JANE"}, {"answer": "JANE"}]}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main", _MAIN), ("names", names)))
        self.assertIn("more than once", str(caught.exception))


class TestManyDifferingRecords(unittest.TestCase):
    """A refusal names the first ten differing records and counts the rest.

    Two banks can share every answer, so a refusal naming each would grow with
    the files: two banks of a hundred thousand answers rated differently would
    be a refusal of megabytes. Ten show the pattern, and are few enough to fix
    by hand before the next run names the next ten.
    """

    def refusal_for(self, files: tuple[cw_bank_merge.BankFile, ...]) -> str:
        """The refusal `parse_banks` gives for `files`."""
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks(files)
        return str(caught.exception)

    def test_ten_differing_answers_are_all_named(self) -> None:
        message = self.refusal_for(_rated_banks(10))
        self.assertEqual(message.count("answer 'QX"), 10)
        self.assertNotIn("more", message)

    def test_past_ten_the_rest_are_counted_not_named(self) -> None:
        message = self.refusal_for(_rated_banks(25))
        self.assertEqual(message.count("answer 'QX"), 10)
        self.assertIn("answer 'QXAJ'", message)
        self.assertNotIn("QXAK", message)
        self.assertTrue(message.endswith("; and 15 more"), message[-80:])

    def test_one_past_ten_is_counted_too(self) -> None:
        message = self.refusal_for(_rated_banks(11))
        self.assertEqual(message.count("answer 'QX"), 10)
        self.assertTrue(message.endswith("; and 1 more"), message[-80:])

    def test_differing_themes_are_counted_past_ten_as_well(self) -> None:
        message = self.refusal_for(_summarized_banks(12))
        self.assertEqual(message.count("theme 'QX"), 10)
        self.assertTrue(message.endswith("; and 2 more"), message[-80:])


class TestRefusalWording(unittest.TestCase):
    """A fault in one file says which file, unless it is the only one."""

    def test_a_fault_in_one_of_several_banks_names_its_file(self) -> None:
        broken = {"themes": {}, "entries": [{"answer": "jane"}]}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("main", _MAIN), ("names.json", broken)))
        self.assertTrue(str(caught.exception).startswith("bank file names.json: "))

    def test_a_fault_in_a_lone_bank_reads_exactly_as_parse_bank_says_it(self) -> None:
        broken = {"themes": {"a": "A"}, "entries": []}
        with self.assertRaises(cw_bank.BankError) as expected:
            cw_bank.parse_bank(broken)
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank_merge.parse_banks((("names.json", broken),))
        self.assertEqual(str(caught.exception), str(expected.exception))


class TestLoadBanks(unittest.TestCase):
    """Reading the files, in the order given."""

    def test_reads_each_file_and_names_it_as_given(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            main = Path(folder) / "main.json"
            names = Path(folder) / "names.json"
            main.write_text(json.dumps(_MAIN), encoding="utf-8", newline="\n")
            names.write_text(json.dumps(_NAMES), encoding="utf-8", newline="\n")
            merged = cw_bank_merge.load_banks((names, main))
        self.assertEqual(_answers(merged.bank), ["JANE", "ALPHA", "AMBER"])
        self.assertEqual(merged.files, ((str(names), 1), (str(main), 2)))

    def test_an_unreadable_file_is_refused_by_its_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.json"
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank_merge.load_banks((missing,))
        self.assertIn(f"could not read bank file {missing}", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
