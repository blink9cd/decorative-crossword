"""Tests for reading a bank or a grid file whose JSON parses into something unusable.

`json.loads` fails in more ways than `json.JSONDecodeError` names, and a JSON
file can parse cleanly into a value the rest of the run cannot handle. Each
case here is a file an operator could hand the tool, and each must be refused
the way a malformed file is (exit 2, naming the file) rather than escaping
as a traceback. The difference matters more here than in most tools: an
uncaught exception exits 1, which is also what this tool says for "the run
happened and no conforming grid was found".

A file can also parse cleanly into less than it says. An object that names one
key twice keeps only the last value, so a hand edit that leaves an old line
behind would be overruled without a word; that too is refused, naming the key
and the object holding it (`test_json_repeated_key.py` pins where). A property
holds the other side of that line: an object whose keys are all distinct loads
exactly as it always has, key order included.

Entry point assumptions: run through the parent aggregator's `load_tests` hook,
which puts the project root and `src/` on `sys.path`.
"""

import json
import sys
import tempfile
import tracemalloc
import unittest
from collections.abc import Callable
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

import cw_bank
import cw_emit
import cw_grid_document
import cw_json
import decorative_crossword
from tests import cli_fixtures

# A registered profile loaded at import, never an `@settings` decorator, as the
# project's other property suites do. Derandomized so the in-suite run is
# reproducible; no deadline, because a per-example wall clock measures machine
# load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_json_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_json_properties")

#: Nesting that `json.loads` parses but that `repr` cannot walk, and every
#: refusal quotes the value at fault from its whole `repr`, however little of
#: it the message keeps. Measured on CPython 3.14: ten thousand levels quote
#: cleanly and a hundred thousand overflow the stack.
_DEEP = 100_000

#: Nesting the parser itself cannot finish: measured on CPython 3.14, it raises
#: RecursionError, which is not a ValueError at all.
_DEEPER = 1_000_000

#: A flat array long enough that whatever the depth check keeps per value
#: dwarfs the array itself. Zeros, because CPython shares one object for every
#: small integer, so the parsed array costs a pointer per value and no more.
_FLAT_LENGTH = 100_000

#: An object naming one key twice at the top of the file. Neither format has a
#: key `a`, which does not matter: the repeat is refused before the file's
#: shape is looked at.
_REPEATED_AT_THE_TOP = '{"a": 1, "a": 2}'

#: A grid file holding one theme, whose label `_repeating_a_label` writes twice.
_GRID: dict[str, object] = {
    "rows": ["CAT"],
    "themes": {"a": cli_fixtures.THEMES["a"]},
    "clues": {},
}

#: Any string, lone surrogates included: JSON's `\udXXX` escape can spell one,
#: and `st.text()` on its own never draws it.
_ANY_TEXT = st.text(st.characters())

#: Every scalar a JSON document can hold. NaN is left out only because it is
#: never equal to itself, which would fail the comparison for a reason that
#: has nothing to do with keys.
_SCALAR = st.one_of(
    st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False), _ANY_TEXT
)

#: JSON values of every shape. `max_leaves` keeps them far shallower than
#: `cw_json.MAX_DEPTH`, so no example is refused for its depth instead.
_VALUE = st.recursive(
    _SCALAR,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_ANY_TEXT, children, max_size=4),
    ),
    max_leaves=12,
)


def _nested(depth: int) -> str:
    """A JSON array nested `depth` levels deep, holding nothing else."""
    return "[" * depth + "]" * depth


def _long_number(case: unittest.TestCase) -> str:
    """An integer literal one digit past the interpreter's limit, pinned for `case`.

    The limit is process-wide and can be raised or switched off from the
    environment, so it is set to its floor for the one test and put back after,
    rather than trusting whatever default this run happened to start with.
    """
    case.addCleanup(sys.set_int_max_str_digits, sys.get_int_max_str_digits())
    floor = sys.int_info.str_digits_check_threshold
    sys.set_int_max_str_digits(floor)
    return "1" * (floor + 1)


def _peak_bytes(read: Callable[[str], object], text: str) -> int:
    """The most memory Python held at once while `read` parsed `text`.

    Counted by tracemalloc, which sees each allocation Python makes, so the
    figure is the same from run to run however busy the machine is.
    """
    tracemalloc.start()
    try:
        read(text)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _written(folder: str, name: str, text: str) -> Path:
    """Write `text` to `name` in `folder` and return the path."""
    path = Path(folder) / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _repeating_a_label(case: unittest.TestCase, document: dict[str, object]) -> str:
    """`document` as JSON, but with theme `a` naming its label twice.

    Two objects below the top, the shape a hand edit leaves when a label is
    rewritten and the old line is not deleted. Nothing else about the file is
    wrong, so without the refusal the second label would win unremarked.
    `case` fails if the label is not there to repeat, rather than the text
    coming back unchanged and a refusal being asserted of a file that had
    nothing to refuse.
    """
    text = json.dumps(document)
    repeated = text.replace('"label": "A"', '"label": "A", "label": "Shadow"', 1)
    case.assertNotEqual(repeated, text, "theme a has no label A to repeat")
    return repeated


class TestBankFile(unittest.TestCase):
    """`cw_bank.load_bank` refuses every such file as a BankError naming it."""

    def test_a_number_past_the_digit_limit(self) -> None:
        text = '{"themes": {}, "entries": [{"answer": "CAT", "rating": %s}]}'
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", text % _long_number(self))
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
            self.assertIn(path.name, str(caught.exception))

    def test_nesting_too_deep_to_quote(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", _nested(_DEEP))
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
            self.assertIn(path.name, str(caught.exception))

    def test_nesting_too_deep_to_parse(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "bank.json", _nested(_DEEPER))
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_bank.load_bank(path)
            self.assertIn(path.name, str(caught.exception))


class TestGridFile(unittest.TestCase):
    """`cw_grid_document.load_document` refuses every such file as an EmitError naming it."""

    def test_a_number_past_the_digit_limit(self) -> None:
        text = '{"rows": ["CAT"], "note": %s}'
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "grid.json", text % _long_number(self))
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_grid_document.load_document(path)
            self.assertIn(path.name, str(caught.exception))

    def test_nesting_too_deep_to_quote(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "grid.json", _nested(_DEEP))
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_grid_document.load_document(path)
            self.assertIn(path.name, str(caught.exception))

    def test_nesting_too_deep_to_parse(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "grid.json", _nested(_DEEPER))
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_grid_document.load_document(path)
            self.assertIn(path.name, str(caught.exception))


class TestCeiling(unittest.TestCase):
    """Where `cw_json.loads` draws the depth line, counted in objects and arrays."""

    def test_nesting_at_the_ceiling_is_read(self) -> None:
        self.assertIsInstance(cw_json.loads(_nested(cw_json.MAX_DEPTH)), list)

    def test_nesting_one_past_the_ceiling_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            cw_json.loads(_nested(cw_json.MAX_DEPTH + 1))
        self.assertIn(f"more than {cw_json.MAX_DEPTH}", str(caught.exception))

    def test_the_ceiling_is_sixty_four(self) -> None:
        # The companion document states this number, so a change to it is a
        # change to that sentence too.
        self.assertEqual(cw_json.MAX_DEPTH, 64)

    def test_an_object_counts_toward_the_depth_as_an_array_does(self) -> None:
        depth = cw_json.MAX_DEPTH + 1
        with self.assertRaises(ValueError):
            cw_json.loads('{"a": ' * depth + "0" + "}" * depth)


class TestDepthCost(unittest.TestCase):
    """Measuring the depth costs memory for the nesting, not for every value."""

    def test_a_flat_array_costs_what_parsing_it_does(self) -> None:
        text = "[" + ",".join(["0"] * _FLAT_LENGTH) + "]"
        parsed = _peak_bytes(json.loads, text)
        # Twice is a generous bound, not a measured one. A walk that kept an
        # entry for every value in the array measured about nine times what
        # parsing alone did, on CPython 3.14.
        self.assertLess(_peak_bytes(cw_json.loads, text), 2 * parsed)


class TestRepeatedKey(unittest.TestCase):
    """`cw_json.loads` refuses an object that names one key twice, at any depth."""

    def test_the_repeat_is_refused_naming_the_key(self) -> None:
        for label, text in (
            ("at the top level", _REPEATED_AT_THE_TOP),
            ("two objects deep", '{"outer": {"inner": {"a": 1, "a": 2}}}'),
            ("in an object inside an array", '[{"a": 1, "a": 2}]'),
            ("with both values alike", '{"a": 1, "a": 1}'),
            ("spelled the second time as an escape", '{"a": 1, "\\u0061": 2}'),
        ):
            with self.subTest(label):
                with self.assertRaises(ValueError) as caught:
                    cw_json.loads(text)
                self.assertIn(
                    "writes the key 'a' more than once", str(caught.exception)
                )


class TestDistinctKeys(unittest.TestCase):
    """An object whose keys are all distinct loads exactly as `json.dumps` wrote it."""

    @given(st.dictionaries(_ANY_TEXT, _VALUE))
    @example({"b": {"d": 1, "c": 2}, "a": []})
    def test_it_loads_back_unchanged(self, value: dict[str, object]) -> None:
        text = json.dumps(value)
        loaded = cw_json.loads(text)
        self.assertEqual(loaded, value)
        # `==` between two dicts ignores the order of their keys. The text
        # written back from what was loaded does not, at any depth.
        self.assertEqual(json.dumps(loaded), text)


class TestCommandLine(cli_fixtures.QuietCase):
    """Every subcommand reading such a file exits 2 and names it."""

    def test_fill_refuses_such_a_bank(self) -> None:
        text = '{"themes": {}, "entries": [{"answer": "CAT", "rating": %s}]}'
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            for label, content in (
                ("digits", text % _long_number(self)),
                ("depth", _nested(_DEEP)),
            ):
                with self.subTest(label):
                    already = len(self.errors)
                    space.bank.write_text(content, encoding="utf-8", newline="\n")
                    self.assertEqual(decorative_crossword.main(space.fill()), 2)
                    self.assertFalse(space.out.exists())
                    self.assertIn(space.bank.name, self.errors[already:])

    def test_every_grid_reader_refuses_such_a_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            # Named so that no other path in the run contains it: `fill`'s
            # output is `grid_source.json`, and a refusal naming that file
            # would pass for one naming this.
            source = _written(folder, "deep.json", _nested(_DEEP))
            for argv in (
                ["preview", "--source", str(source), "--out", str(space.svg)],
                ["shade", "--source", str(source), "--word", "CAT"],
                ["gaps", "--source", str(source)],
                space.fill("--source", str(source)),
            ):
                with self.subTest(argv[0]):
                    already = len(self.errors)
                    self.assertEqual(decorative_crossword.main(argv), 2)
                    self.assertIn(source.name, self.errors[already:])

    def test_fill_refuses_a_bank_that_repeats_a_key(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            for label, content, key in (
                ("at the top level", _REPEATED_AT_THE_TOP, "a"),
                (
                    "two objects deep",
                    _repeating_a_label(self, cli_fixtures.BANK),
                    "label",
                ),
            ):
                with self.subTest(label):
                    already = len(self.errors)
                    space.bank.write_text(content, encoding="utf-8", newline="\n")
                    self.assertEqual(decorative_crossword.main(space.fill()), 2)
                    self.assertFalse(space.out.exists())
                    said = self.errors[already:]
                    self.assertIn(space.bank.name, said)
                    self.assertIn(f"writes the key {key!r} more than once in", said)

    def test_preview_refuses_a_grid_file_that_repeats_a_key(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            for label, content, key in (
                ("at the top level", _REPEATED_AT_THE_TOP, "a"),
                ("two objects deep", _repeating_a_label(self, _GRID), "label"),
            ):
                with self.subTest(label):
                    already = len(self.errors)
                    source = _written(folder, "repeated.json", content)
                    argv = ["preview", "--source", str(source), "--out", str(space.svg)]
                    self.assertEqual(decorative_crossword.main(argv), 2)
                    self.assertFalse(space.svg.exists())
                    said = self.errors[already:]
                    self.assertIn(source.name, said)
                    self.assertIn(f"writes the key {key!r} more than once in", said)


if __name__ == "__main__":
    unittest.main()
