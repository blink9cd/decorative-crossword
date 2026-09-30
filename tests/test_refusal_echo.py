"""Tests: a refusal quotes at most 200 characters of the value it names.

A refusal names the value at fault so the operator can find it in the file,
and quotes it as Python writes it, so a control character arrives as an escape
rather than as a command to the terminal. Quoted whole, though, a value is as
long as the file made it: a label a megabyte long, or a million numbers where
the `themes` object belongs, would put megabytes on stderr for one line of
diagnosis. So every quote goes through `cw_text.shown`, which keeps the first
200 characters and states how long the whole was.

Two halves. The CLI cases feed refused inputs holding huge values and measure
what reaches stderr. The guard reads every module the tool runs, with `ast`,
and fails on any `!r` or `!a` conversion and any `repr` or `ascii` call -- each
quotes a value whole -- outside `shown` itself and the one-character escape in
`cw_text.visible`. It sees only those four shapes: a `%r` in a format string or
a `{!r}` field handed to `str.format` quotes a value whole just as well and
passes it unseen.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import ast
import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: How many characters, or list items, each huge value below holds: far past
#: any quote's cap, and quick to build.
_HUGE = 1_000_000

#: The most stderr one refusal of a file may take: the quote, the file's path
#: and the sentence around them, with room to spare -- three orders of
#: magnitude under what quoting the whole value takes.
_MAX_STDERR_BYTES = 1_000

#: The most the refusal line of a malformed option may take. argparse prints
#: the subcommand's usage above it, which is long but fixed, so the line
#: itself is what is measured.
_MAX_OPTION_LINE = 400

#: The project root: the entry point and `src/` sit directly beneath it.
_ROOT = Path(__file__).resolve().parent.parent

#: The module that defines the quote, and the functions in it whose own calls
#: are let through: `shown`'s `repr`, which every other quote goes through, and
#: `visible`'s `ascii`, which escapes one character at a time.
_QUOTE_MODULE = "cw_text.py"
_QUOTE_FUNCTIONS = frozenset({"shown", "visible"})

#: The conversions and the builtins that write a value whole.
_WHOLE_CONVERSIONS = frozenset({ord("r"), ord("a")})
_WHOLE_BUILTINS = frozenset({"repr", "ascii"})


def _bank_labeled(label: str) -> dict[str, object]:
    """The shared three-theme bank with theme `a` relabeled `label`."""
    themes = {**cli_fixtures.THEMES, "a": {**cli_fixtures.THEMES["a"], "label": label}}
    return {"themes": themes, "entries": cli_fixtures.ENTRIES}


def _modules() -> list[Path]:
    """Every module the tool runs: its entry point and each module under `src/`."""
    return [_ROOT / "decorative_crossword.py", *sorted((_ROOT / "src").glob("*.py"))]


def _quotes_whole(node: ast.expr) -> bool:
    """Whether `node` writes a value whole: `!r`, `!a`, `repr(...)` or `ascii(...)`."""
    if isinstance(node, ast.FormattedValue):
        return node.conversion in _WHOLE_CONVERSIONS
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _WHOLE_BUILTINS
    )


def _whole_quotes(source: str, spared: frozenset[str] = frozenset()) -> list[int]:
    """The line of every whole-value quote in `source`.

    A quote inside a module-level function named in `spared` is not counted:
    that is how `shown` and `visible`, and only they, are let through.
    """
    tree = ast.parse(source)
    inside: set[int] = set()
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef) and statement.name in spared:
            inside.update(id(node) for node in ast.walk(statement))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.expr) and _quotes_whole(node) and id(node) not in inside
    )


def _whole_quotes_in(path: Path) -> list[int]:
    """The line of every whole-value quote in the module at `path`."""
    spared = _QUOTE_FUNCTIONS if path.name == _QUOTE_MODULE else frozenset()
    return _whole_quotes(path.read_text(encoding="utf-8"), spared)


class TestRefusalSize(cli_fixtures.QuietCase):
    """A refused file holding a huge value takes a short line of stderr.

    Size is checked before content in each case, so a regression fails on two
    numbers rather than printing the megabytes it measured.
    """

    def assert_short_refusal(self, argv: list[str]) -> None:
        """`argv` exits 2 with under `_MAX_STDERR_BYTES` of stderr."""
        self.assertEqual(decorative_crossword.main(argv), 2)
        self.assertLess(len(self.errors.encode("utf-8")), _MAX_STDERR_BYTES)

    def test_fill_refuses_a_huge_label_holding_a_newline(self) -> None:
        label = "A\n" + "x" * _HUGE
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank_labeled(label))
            self.assert_short_refusal(space.fill())
        self.assertIn("the label for theme 'a' must not contain a newline", self.errors)
        self.assertIn("got 'A\\nxxx", self.errors)
        self.assertIn(f"... ({len(repr(label))} characters)", self.errors)

    def test_fill_refuses_a_huge_list_where_an_entry_belongs(self) -> None:
        entries = [[0] * _HUGE, *cli_fixtures.ENTRIES]
        with tempfile.TemporaryDirectory() as folder:
            bank: dict[str, object] = {
                "themes": cli_fixtures.THEMES,
                "entries": entries,
            }
            space = cli_fixtures.Workspace(folder, bank)
            self.assert_short_refusal(space.fill())
        self.assertIn("bank entry must be a JSON object, got [0, 0, ", self.errors)
        self.assertIn(f"... ({len(repr(entries[0]))} characters)", self.errors)

    def test_preview_refuses_a_huge_list_where_themes_belong(self) -> None:
        self.assert_short_preview_refusal([0] * _HUGE)
        self.assertIn("document 'themes' must be a JSON object, got [0, ", self.errors)

    def test_preview_refuses_a_huge_string_where_themes_belong(self) -> None:
        self.assert_short_preview_refusal("x" * _HUGE)
        self.assertIn("document 'themes' must be a JSON object, got 'xxx", self.errors)

    def assert_short_preview_refusal(self, themes: object) -> None:
        """`preview` of a grid file whose `themes` is `themes` is a short refusal."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            document = {"rows": ["CAT"], "themes": themes}
            space.out.write_text(json.dumps(document), encoding="utf-8", newline="\n")
            argv = ["preview", "--source", str(space.out), "--out", str(space.svg)]
            self.assert_short_refusal(argv)
            self.assertFalse(space.svg.exists())
        self.assertIn(f"... ({len(repr(themes))} characters)", self.errors)

    def test_a_huge_number_option_is_refused_in_one_short_line(self) -> None:
        value = "x" * _HUGE
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            with self.assertRaises(SystemExit) as caught:
                decorative_crossword.main(space.fill("--time-budget", value))
        self.assertEqual(caught.exception.code, 2)
        line = self.errors.splitlines()[-1]
        self.assertLess(len(line), _MAX_OPTION_LINE)
        self.assertIn("--time-budget: must be a finite number, got 'xxx", line)
        self.assertIn(f"... ({len(repr(value))} characters)", line)


class TestNoWholeQuote(unittest.TestCase):
    """No `!r`/`!a` or `repr`/`ascii` quote is left outside `cw_text`, and the guard sees each."""

    def test_no_module_quotes_a_whole_value(self) -> None:
        found = [
            f"{path.name}:{line}"
            for path in _modules()
            for line in _whole_quotes_in(path)
        ]
        self.assertEqual(found, [], "quote each value through cw_text.shown")

    def test_each_exempt_function_lets_through_one_call(self) -> None:
        # Without the exemptions the defining module holds exactly two quotes,
        # and sparing either function leaves the other's: so each exemption
        # covers that function's own call and nothing else.
        source = (_ROOT / "src" / _QUOTE_MODULE).read_text(encoding="utf-8")
        self.assertEqual(len(_whole_quotes(source)), 2)
        for name in _QUOTE_FUNCTIONS:
            with self.subTest(spared=name):
                self.assertEqual(len(_whole_quotes(source, frozenset({name}))), 1)

    def test_the_guard_finds_a_conversion_inside_a_raise(self) -> None:
        source = 'if bad:\n    raise ValueError(\n        f"got {value!r}"\n    )\n'
        self.assertEqual(_whole_quotes(source), [3])

    def test_the_guard_finds_a_conversion_built_before_the_raise(self) -> None:
        source = 'message = f"answer {answer!r} is not in the bank"\n'
        self.assertEqual(_whole_quotes(source), [1])

    def test_the_guard_finds_a_repr_call(self) -> None:
        source = 'names = ", ".join(repr(text) for text in repeated)\n'
        self.assertEqual(_whole_quotes(source), [1])

    def test_the_guard_finds_an_ascii_conversion(self) -> None:
        source = 'if bad:\n    raise ValueError(f"got {value!a}")\n'
        self.assertEqual(_whole_quotes(source), [2])

    def test_the_guard_finds_an_ascii_call(self) -> None:
        source = 'names = ", ".join(ascii(text) for text in repeated)\n'
        self.assertEqual(_whole_quotes(source), [1])

    def test_the_guard_spares_only_the_named_function(self) -> None:
        source = (
            "def shown(value):\n"
            "    return repr(value)\n"
            "\n"
            "def other(value):\n"
            "    return repr(value)\n"
        )
        self.assertEqual(_whole_quotes(source, frozenset({"shown"})), [5])
        self.assertEqual(_whole_quotes(source), [2, 5])

    def test_the_guard_ignores_other_conversions(self) -> None:
        source = 'text = f"{value} {value!s} {value:>4}"\n'
        self.assertEqual(_whole_quotes(source), [])


if __name__ == "__main__":
    unittest.main()
