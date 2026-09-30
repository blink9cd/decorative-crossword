"""CLI tests: a refusal is printed with each character a terminal would obey escaped.

A refusal names a file by its path as written, and argparse's own error line
quotes an argument as it was typed. A file name or an argument can hold a
control character or a bidi control, which printed raw would command the
terminal or make the rest of the line display as other text than it holds. So
the message is printed escaped, as a skipped word-list line is, whichever of
the tool or its parser made the refusal, from the top-level parser and from
each subcommand's alike. An argument holding a byte that is not UTF-8 reaches
the tool as a lone surrogate, and what a real stderr then carries -- its escape,
and exit 2 -- is pinned in bytes from a child process.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: RIGHT-TO-LEFT OVERRIDE, which a file name can hold: the text after it is
#: displayed right to left, so a file named `grid`, the override, `nosj.txt`
#: shows on a terminal as `gridtxt.json`.
_OVERRIDE = "\U0000202e"

#: The override as a refusal shows it. Spelled out rather than derived, so the
#: test does not restate how an escape is built.
_OVERRIDE_SHOWN = "\\u202e"

#: How long the child process in the one test that starts one may run. It
#: parses its command line and stops, well inside this on any machine.
_CHILD_SECONDS = 120


class TestARefusalNamingAFile(cli_fixtures.QuietCase):
    """The tool's own refusal is printed with a path's bidi control escaped."""

    def test_a_path_holding_an_override_is_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = space.root / f"grid{_OVERRIDE}nosj.txt"
            source.write_text(json.dumps(["CAT"]), encoding="utf-8", newline="\n")
            argv = ["preview", "--source", str(source), "--out", str(space.svg)]
            self.assertEqual(decorative_crossword.main(argv), 2)
            shown = str(source).replace(_OVERRIDE, _OVERRIDE_SHOWN)
        self.assertNotIn(_OVERRIDE, self.errors)
        self.assertIn(f"decorative_crossword: grid file {shown}: ", self.errors)


class TestAMalformedCommandLine(cli_fixtures.QuietCase):
    """argparse's own error line is escaped as any other refusal is."""

    def refused_with(self, argv: list[str]) -> str:
        """Run `argv`, which the parser refuses at exit 2; return its error line's end.

        That is everything after the last `: error: `: the message itself,
        ahead of which argparse prints the usage and the parser's name.
        """
        with self.assertRaises(SystemExit) as caught:
            decorative_crossword.main(argv)
        self.assertEqual(caught.exception.code, 2)
        return self.errors.rpartition(": error: ")[2]

    def test_an_unrecognized_argument_is_escaped(self) -> None:
        stray = f"stray{_OVERRIDE}name"
        said = self.refused_with(
            ["preview", "--source", "x.json", "--out", "y.svg", stray]
        )
        self.assertNotIn(_OVERRIDE, self.errors)
        self.assertEqual(said, f"unrecognized arguments: stray{_OVERRIDE_SHOWN}name\n")

    def test_a_subcommand_parser_escapes_its_own_refusal(self) -> None:
        # An abbreviation that matches several options is refused by the
        # subcommand's parser, whose name ends in the subcommand's, and the
        # refusal quotes the argument as it was typed.
        said = self.refused_with(["fill", f"--min={_OVERRIDE}"])
        self.assertIn(" fill: error: ", self.errors)
        self.assertNotIn(_OVERRIDE, self.errors)
        self.assertTrue(
            said.startswith(f"ambiguous option: --min={_OVERRIDE_SHOWN} could match "),
            ascii(said),
        )

    def test_an_argument_that_is_not_utf8_is_escaped_rather_than_a_traceback(
        self,
    ) -> None:
        # A child process, because only a real stream encodes what it is given:
        # the captured stream the other tests read stores any character. This
        # pins the bytes a real stderr carries and the exit code. U+DCFF is
        # what Python makes of the byte 0xFF in an argument.
        stray = "stray\U0000dcffname"
        argv = ["preview", "--source", "x.json", "--out", "y.svg", stray]
        entry = decorative_crossword.__file__
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "child.log"
            with log.open("wb") as sink:
                # reliability: ignore[RL005] a file, not a pipe: nothing is left to read
                done = subprocess.run(
                    [sys.executable, entry, *argv],
                    stdout=sink,
                    stderr=sink,
                    timeout=_CHILD_SECONDS,
                    check=False,
                )
            said = log.read_text(encoding="utf-8")
        self.assertNotIn("Traceback", said)
        self.assertEqual(done.returncode, 2)
        self.assertTrue(
            said.endswith(": error: unrecognized arguments: stray\\udcffname\n"),
            said,
        )
