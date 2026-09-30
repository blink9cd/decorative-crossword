"""Tests for how a key written twice in one object is refused: named, and located.

`json.loads` keeps the last of two same-named members of an object and says
nothing, so such a file was read as whichever came last: a bank entry written
with two answers was read as the second, and a bank whose entries were written
twice was refused as having none. Such a file is grammatical JSON, so the
refusal must not call it invalid; and in a bank of hundreds of entries, naming
the key alone leaves a person searching every entry for the one holding it
twice. So the refusal names the object too, as a path from the top of the file.

`test_json.py` holds the rest of what `cw_json` refuses, and the property that
an object of distinct keys loads unchanged.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import contextlib
import json
import tempfile
import tracemalloc
import unittest
from collections.abc import Callable
from pathlib import Path

import cw_bank
import cw_emit
import cw_grid_document
import cw_json

#: A bank whose one entry is written with two answers.
_TWO_ANSWERS = '{"themes": {}, "entries": [{"answer": "CAT", "answer": "DOG"}]}'

#: A bank whose entries are written twice, the second time empty.
_TWO_ENTRY_LISTS = '{"themes": {}, "entries": [{"answer": "CAT"}], "entries": []}'

#: A grid file whose rows are written twice.
_TWO_GRIDS = '{"rows": ["CAT"], "rows": ["DOG"]}'

#: A flat array long enough that whatever a walk keeps per value dwarfs the array
#: itself. Zeros, because CPython shares one object for every small integer, so
#: the parsed array costs a pointer per value and no more.
_FLAT_LENGTH = 100_000

#: RIGHT-TO-LEFT OVERRIDE. Printed raw inside a key the refusal quotes, it
#: would reverse the rest of the error line on a terminal.
_OVERRIDE = "\U0000202e"


def _nested(depth: int) -> str:
    """A JSON array nested `depth` levels deep, holding nothing else."""
    return "[" * depth + "]" * depth


def _peak_bytes(read: Callable[[str], object], text: str) -> int:
    """The most memory Python held at once while `read` took `text`, refusal included.

    Counted by tracemalloc, which sees each allocation Python makes, so the
    figure is the same from run to run however busy the machine is. A refused
    repeat is part of what is measured, so it is let through here.
    """
    tracemalloc.start()
    try:
        with contextlib.suppress(cw_json.RepeatedKeyError):
            read(text)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _written(folder: str, name: str, text: str) -> Path:
    """Write `text` to `name` in `folder` and return the path."""
    path = Path(folder) / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


class TestDuplicateKeys(unittest.TestCase):
    """A key written twice in one object is refused, naming the key and the object."""

    def test_a_bank_entry_with_two_answers(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", _TWO_ANSWERS)
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
        self.assertEqual(
            str(caught.exception),
            f"bank file {path} writes the key 'answer' more than once in the "
            "object at ['entries'][0], and which one counts would be a guess",
        )

    def test_a_bank_with_two_entry_lists(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", _TWO_ENTRY_LISTS)
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
        self.assertIn(
            "the key 'entries' more than once in the top-level object",
            str(caught.exception),
        )

    def test_a_grid_file_with_two_grids(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "grid.json", _TWO_GRIDS)
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_grid_document.load_document(path)
        self.assertEqual(
            str(caught.exception),
            f"grid file {path} writes the key 'rows' more than once in the "
            "top-level object, and which one counts would be a guess",
        )

    def test_a_file_that_is_not_json_is_still_called_so(self) -> None:
        # The other refusals keep their wording: only a repeat is grammatical.
        for load, name in (
            (cw_bank.load_bank, "bank.json"),
            (cw_grid_document.load_document, "grid.json"),
        ):
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                path = _written(folder, name, '{"rows": [')
                with self.assertRaises(ValueError) as caught:
                    load(path)
                self.assertIn(f"{path} is not valid JSON", str(caught.exception))

    def test_a_repeated_key_is_quoted_with_its_controls_escaped(self) -> None:
        key = f"x{_OVERRIDE}y"
        text = '{"themes": {}, "entries": [{"answer": "CAT", "%s": 1, "%s": 2}]}'
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", text % (key, key))
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
        self.assertIn("the key 'x\\u202ey' more than once", str(caught.exception))
        self.assertNotIn(_OVERRIDE, str(caught.exception))

    def test_a_key_on_the_path_is_quoted_with_its_controls_escaped(self) -> None:
        key = f"x{_OVERRIDE}y"
        text = '{"themes": {"%s": {"label": "A", "label": "B"}}, "entries": []}'
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", text % key)
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
        self.assertIn("the object at ['themes']['x\\u202ey']", str(caught.exception))
        self.assertNotIn(_OVERRIDE, str(caught.exception))


class TestWhatCountsAsARepeat(unittest.TestCase):
    """Only a key twice in ONE object is a repeat."""

    def test_one_key_in_each_of_two_objects_is_no_repeat(self) -> None:
        self.assertEqual(
            cw_json.loads('[{"answer": "CAT"}, {"answer": "DOG"}]'),
            [{"answer": "CAT"}, {"answer": "DOG"}],
        )

    def test_keys_differing_only_in_case_are_two_keys(self) -> None:
        self.assertEqual(cw_json.loads('{"a": 1, "A": 2}'), {"a": 1, "A": 2})


class TestWhereTheRepeatIs(unittest.TestCase):
    """The refusal names the object holding the repeat, as a path from the top.

    Keys are quoted, indexes count from 0, and the top of the file is named in
    words, so a person can walk to the object without counting braces.
    """

    def _refusal(self, text: str) -> str:
        """What `cw_json.loads` says about `text`, which repeats a key."""
        with self.assertRaises(cw_json.RepeatedKeyError) as caught:
            cw_json.loads(text)
        return str(caught.exception)

    def test_a_repeat_in_the_top_level_object_is_named_so(self) -> None:
        self.assertEqual(
            self._refusal('{"a": 1, "a": 2}'),
            "writes the key 'a' more than once in the top-level object, and which "
            "one counts would be a guess",
        )

    def test_an_index_counts_the_objects_before_it(self) -> None:
        refusal = self._refusal('{"a": [{"b": 1}, {"b": 1, "c": 2, "b": 3}]}')
        self.assertIn("the key 'b' more than once in the object at ['a'][1],", refusal)

    def test_the_first_repeat_in_the_file_is_the_one_named(self) -> None:
        refusal = self._refusal('[{"x": 1}, {"y": 1, "y": 2}, {"z": 1, "z": 2}]')
        self.assertIn("the key 'y' more than once in the object at [1],", refusal)

    def test_the_first_key_one_object_repeats_is_the_one_named(self) -> None:
        refusal = self._refusal('{"a": 1, "b": 1, "b": 2, "a": 2}')
        self.assertIn("the key 'b' more than once", refusal)

    def test_an_object_its_repeat_threw_away_is_not_the_one_named(self) -> None:
        # The first "a" holds an object repeating "b", and the second "a"
        # replaces it: no path reaches that object any more. The repeat that
        # threw it away is the one a person can find.
        refusal = self._refusal('{"a": {"b": 1, "b": 2}, "a": 3}')
        self.assertIn("the key 'a' more than once in the top-level object", refusal)

    def test_finding_the_repeat_costs_what_parsing_the_file_does(self) -> None:
        # The walk that names the object runs only on a refusal, but it runs
        # over the whole parsed value, and a file past the depth check can
        # still be one long array. Held to the bound the depth check's own
        # walk is held to, wherever in the array the repeat sits.
        repeat, zeros = '{"a": 1, "a": 1}', ["0"] * _FLAT_LENGTH
        for where, members in (
            ("first", [repeat, *zeros]),
            ("last", [*zeros, repeat]),
        ):
            with self.subTest(where):
                text = "[" + ",".join(members) + "]"
                with self.assertRaises(cw_json.RepeatedKeyError):
                    cw_json.loads(text)
                parsed = _peak_bytes(json.loads, text)
                self.assertLess(_peak_bytes(cw_json.loads, text), 2 * parsed)

    def test_nesting_is_judged_before_a_repeat(self) -> None:
        # A file both too deep and repeating a key is refused for its depth,
        # the refusal that holds whatever else is wrong with it.
        text = '{"a": 1, "a": ' + _nested(cw_json.MAX_DEPTH + 1) + "}"
        with self.assertRaises(ValueError) as caught:
            cw_json.loads(text)
        self.assertNotIsInstance(caught.exception, cw_json.RepeatedKeyError)
        self.assertIn(f"more than {cw_json.MAX_DEPTH}", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
