"""Where an option's help prose lives, that it stays wired, and what the epilogs name.

`cw_help` holds every help string that runs to more than one line, for the
reason that module's docstring already gives about the epilogs: the entry point
stays a table of option declarations. Its `add_argument` calls stay together
there, so the whole command-line surface reads in one place; prose is what can
leave.

What that costs is DISTANCE. A flag and its description do not sit on
adjacent lines, so no reader can see at a glance that the right constant
reached the right option, and an orphaned or doubled-up constant looks exactly
like a correct one. These tests buy that distance back.

They also keep the entry point under the 500 lines this project holds every
Python file to. Prose written straight into an `add_argument` call would grow
it one option at a time, each step too small to notice, until it passed that
size with no single change to blame.

Read as SOURCE rather than by importing the modules: the question is where a
string is written, and an imported module cannot answer that -- by then the
constant and a literal are the same object.

`TestEachEpilogNamesWhatItClaims` asks a different question, what an epilog
TELLS its reader, so it reads `--help` as printed instead. An epilog's exit-2
list is where a reader learns what a subcommand refuses without running it, and
it is written in `cw_help`, far from the code that refuses, so a rewrite that
drops a refusal reads as fine to anyone who does not know that code. Each phrase
pinned there names a refusal the code makes or, for `fill`, the inputs that
state a grid's size or why the size has no default; a refusal or a size input
the code gains belongs in the epilog and in those pins together, since nothing
here can find it on its own.
"""

import ast
import unittest
from pathlib import Path

import cw_grid
import decorative_crossword
from tests import cli_fixtures

_PROJECT = Path(__file__).resolve().parent.parent
_ENTRY_POINT = _PROJECT / "decorative_crossword.py"
_HELP_MODULE = _PROJECT / "src" / "cw_help.py"

#: What marks a `cw_help` constant as one option's help text, telling it from
#: the epilogs and the formatter that module also holds. A naming convention
#: rather than a listing here, so a constant added later is covered by being
#: named like its neighbors instead of by remembering this file.
_HELP_SUFFIX = "_HELP"

#: A floor on the SCAN's denominator, not on the number of options. Every
#: assertion below is a statement about a set, and each one passes trivially
#: over an empty set -- the shape that reports a clean result while measuring
#: nothing at all. This is what makes the others mean something.
_MIN_HELP_CONSTANTS = 10

#: The two refusals `preview`, `shade` and `gaps` make of the grid file they
#: read, pinned in the one phrasing their three epilogs share: a grid past the
#: size cap, and a theme label or summary the bank screen would refuse.
_GRID_FILE_REFUSALS = (
    f"wider or taller than {cw_grid.MAX_SIDE} cells",
    "whose theme label or summary holds a character a bank refuses",
)


def _parse(path: Path) -> ast.Module:
    """Parse one source file this project owns."""
    return ast.parse(path.read_text(encoding="utf-8"))


def _add_argument_calls(tree: ast.Module) -> list[ast.Call]:
    """Every `add_argument(...)` call in a parsed module, receiver-blind.

    Matched on the attribute name alone, so a call on a subparser, on a loop
    variable or on a group counts here as it does to anyone scanning the entry
    point for its option declarations.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
    ]


def _help_argument(call: ast.Call) -> ast.expr | None:
    """The `help=` value of one `add_argument` call, or None if it has none."""
    for keyword in call.keywords:
        if keyword.arg == "help":
            return keyword.value
    return None


def _option_name(call: ast.Call) -> str:
    """How a failure names the option, falling back for a non-literal first arg."""
    if call.args and isinstance(call.args[0], ast.Constant):
        return str(call.args[0].value)
    return f"<line {call.lineno}>"


def _declared_help_constants() -> set[str]:
    """Every module-level `*_HELP` string constant `cw_help` defines."""
    return {
        target.id
        for node in _parse(_HELP_MODULE).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.endswith(_HELP_SUFFIX)
    }


def _referenced_help_constants() -> list[str]:
    """Every `cw_help.*_HELP` an entry-point `add_argument` passes as its help.

    A list rather than a set: two options sharing one constant is a defect this
    file reports, and a set would swallow the evidence for it.
    """
    referenced = []
    for call in _add_argument_calls(_parse(_ENTRY_POINT)):
        value = _help_argument(call)
        if (
            isinstance(value, ast.Attribute)
            and value.attr.endswith(_HELP_SUFFIX)
            and isinstance(value.value, ast.Name)
            and value.value.id == "cw_help"
        ):
            referenced.append(value.attr)
    return referenced


class TestProseLivesInTheHelpModule(unittest.TestCase):
    """No `add_argument` call in the entry point carries prose of its own."""

    def test_no_option_writes_multi_line_help_into_the_entry_point(self) -> None:
        # The span, not the character count, is the thing that costs headroom,
        # and the two agree anyway: ruff wraps any help too long for one line
        # into the parenthesized form, so "more than one line" IS "long here".
        offenders = []
        for call in _add_argument_calls(_parse(_ENTRY_POINT)):
            value = _help_argument(call)
            if isinstance(value, ast.Constant) and value.end_lineno != value.lineno:
                offenders.append(f"{_option_name(call)} (line {value.lineno})")
        self.assertEqual(
            offenders,
            [],
            "help prose belongs in cw_help, not in the entry point at the "
            f"file-length cap: {offenders}",
        )

    def test_every_option_still_declares_a_help(self) -> None:
        """A missing `help=` leaves an option silently bare."""
        bare = [
            _option_name(call)
            for call in _add_argument_calls(_parse(_ENTRY_POINT))
            if _help_argument(call) is None
        ]
        self.assertEqual(bare, [], f"options with no help at all: {bare}")


class TestEveryConstantIsWiredToOneOption(unittest.TestCase):
    """The wiring an eye can no longer check, checked mechanically."""

    def test_the_scan_found_constants_to_check(self) -> None:
        # Guards the three assertions around this one, each of which is true of
        # the empty set. A rename that put every constant outside the scan's
        # reach would otherwise turn this whole file green and silent.
        declared = _declared_help_constants()
        self.assertGreaterEqual(
            len(declared),
            _MIN_HELP_CONSTANTS,
            f"cw_help declares only {len(declared)} option-help constants; the "
            "scan below would be checking almost nothing",
        )

    def test_every_declared_constant_reaches_an_option(self) -> None:
        """An orphan is prose nobody reads, left behind by a retired option."""
        orphans = sorted(_declared_help_constants() - set(_referenced_help_constants()))
        self.assertEqual(
            orphans, [], f"cw_help constants no option passes as its help: {orphans}"
        )

    def test_every_referenced_constant_is_actually_declared(self) -> None:
        """The other direction: a typo'd name is an AttributeError at startup."""
        missing = sorted(set(_referenced_help_constants()) - _declared_help_constants())
        self.assertEqual(
            missing,
            [],
            f"help constants the entry point names but cw_help lacks: {missing}",
        )

    def test_no_constant_serves_two_options(self) -> None:
        """Two options sharing one string is how a mis-wired constant looks."""
        referenced = _referenced_help_constants()
        shared = sorted({name for name in referenced if referenced.count(name) > 1})
        self.assertEqual(
            shared,
            [],
            "one help constant reached more than one option, which is either a "
            f"copy-paste or two flags that should not share a description: {shared}",
        )


class TestEachEpilogNamesWhatItClaims(cli_fixtures.QuietCase):
    """The phrases each epilog must carry, read from `--help` as it prints."""

    def _assert_help_names(self, subcommand: str, phrases: tuple[str, ...]) -> None:
        """Assert `subcommand --help`, as printed, carries every one of `phrases`.

        Joined back into one line first: an epilog breaks its lines wherever
        its source text wraps, so a phrase may be split anywhere.
        """
        with self.assertRaises(SystemExit):
            decorative_crossword.main([subcommand, "--help"])
        helped = " ".join(self.printed.split())
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, helped)

    def test_fill_names_every_input_that_states_the_size(self) -> None:
        # The second phrase is why no size defaults: a rewrite of the sentence
        # naming the routes must keep it.
        self._assert_help_names(
            "fill",
            (
                "with --rows and --cols or with a --source grid or --mask "
                "picture that already has one",
                "because any default would be a guess at what the consumer of "
                "the grid wants",
            ),
        )

    def test_preview_names_each_feature_refusal(self) -> None:
        self._assert_help_names(
            "preview",
            (
                "2 on a --feature that carries a position",
                "names one answer twice",
                "names an answer the grid does not hold",
            ),
        )

    def test_gaps_names_each_mask_refusal(self) -> None:
        self._assert_help_names(
            "gaps",
            (
                "an unreadable bank, word list, phrase list or --mask picture",
                "a --mask picture with a blank line, no rows, a ragged row or a "
                "character other than '.' and 'X'",
                "one that masks every cell",
                "is not the grid's size",
                "forbids a letter the grid already holds",
            ),
        )

    # One method per subcommand rather than a loop: `printed` accumulates
    # over a test, so a later subcommand's check would also read an earlier
    # one's help and could pass on text its own epilog never printed.
    def test_preview_names_both_grid_file_refusals(self) -> None:
        self._assert_help_names("preview", _GRID_FILE_REFUSALS)

    def test_shade_names_both_grid_file_refusals(self) -> None:
        self._assert_help_names("shade", _GRID_FILE_REFUSALS)

    def test_gaps_names_both_grid_file_refusals(self) -> None:
        self._assert_help_names("gaps", _GRID_FILE_REFUSALS)


if __name__ == "__main__":  # pragma: no cover - the suite runs under the aggregator
    unittest.main()
