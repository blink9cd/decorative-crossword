"""Tests for an input path that names something other than a file, at the process boundary.

Every input a subcommand reads (a bank, an excluded-terms list, a mask, a
word list and a grid file) is refused at exit 2 when its path names a FIFO,
naming the path, rather than waiting for a writer that may never come. Each
input is its own case because each reaches its own reader: a reader left
calling a plain read would pass every other case here.

`/dev/stdin` is held to the same rule by what it is, never by its name: fed
from a pipe it is refused, and redirected from a file it is that file and is
read like one.

The FIFO case covers one flag for each reader. The routes the other flags take
to those readers (`fill`'s `--phrases` and `--source`, and each input of
`shade` and `gaps`) are held to the rule too, with a device standing for the
file: `os.devnull` reads as empty rather than blocking, so those run through
`main` in this process and a route that stopped checking fails its own case.

Every FIFO case and every `/dev/stdin` case runs the tool in a child
interpreter under a timeout, rather than through `main` in this process, so a
reader that regressed to waiting fails its own case instead of hanging the
whole suite.

Entry point assumptions: run through the parent aggregator's `load_tests` hook,
which puts the project root and `src/` on `sys.path`.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import IO

import decorative_crossword
from tests import cli_fixtures, source_fixtures

#: The project root, which holds the entry point the child imports. Derived
#: from this file's own location so the suite survives a move.
_ROOT = Path(__file__).resolve().parent.parent

#: Seconds each child gets. It imports the tool and refuses one file, which
#: takes about a second, so anything near this is a read that is waiting.
_CHILD_TIMEOUT = 60.0

#: Runs the tool on the arguments after the first two (the project root and a
#: result file), and writes the exit code, then everything the tool wrote to
#: stderr, into that file. The parent captures nothing, deliberately: a
#: timeout on a capturing call kills only the direct child and then blocks
#: re-reading pipes a grandchild still holds, so handing the child a file to
#: write is what keeps the bound binding.
_CHILD_PROGRAM = r"""
import contextlib
import io
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
import decorative_crossword

errors = io.StringIO()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
    code = decorative_crossword.main(sys.argv[3:])
pathlib.Path(sys.argv[2]).write_text(
    f"{code}\n{errors.getvalue()}", encoding="utf-8", newline="\n"
)
"""

#: A grid document the `shade` case reads before its word list, so the word
#: list is the only input that case can refuse.
_GRID = {"rows": ["CAT..", ".A...", "..T..", "DOG.."], "themes": {}, "clues": {}}

#: A character device on every host, which reads as empty rather than blocking.
_DEVICE = Path(os.devnull)

#: The path the stdin cases name as the bank.
_STDIN = "/dev/stdin"

#: Why a test that needs one of these is skipped where it is absent.
_NO_FIFO = "this platform has no FIFOs"
_NO_DEV_STDIN = "this platform has no /dev/stdin"


def _run_tool(
    argv: list[str], stdin: int | IO[bytes] = subprocess.DEVNULL
) -> tuple[int, str]:
    """The exit code and the stderr of the tool run on `argv` in a child.

    `stdin` is what the child reads as its standard input, which is nothing
    unless a case gives it something: the child must never read the terminal
    the suite happens to run in.
    """
    with tempfile.TemporaryDirectory() as scratch:
        result = Path(scratch) / "result.txt"
        subprocess.run(
            [sys.executable, "-c", _CHILD_PROGRAM, str(_ROOT), str(result), *argv],
            stdin=stdin,
            timeout=_CHILD_TIMEOUT,
            check=True,
        )
        code, _, errors = result.read_text(encoding="utf-8").partition("\n")
    return int(code), errors


def _naming_the_bank(argv: list[str], bank: str, instead: str) -> list[str]:
    """`argv` with its `--bank` value `bank` replaced by `instead`."""
    return [instead if value == bank else value for value in argv]


class TestFifo(unittest.TestCase):
    """A FIFO given for any input is refused at exit 2, naming it, at once."""

    def test_every_input_refuses_a_fifo(self) -> None:
        # Skipped by platform rather than by probing for `os.mkfifo`, so the
        # type check of this body for Windows, which has none, is narrowed too.
        if sys.platform == "win32":
            self.skipTest(_NO_FIFO)  # pragma: only-on win32
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            fifo = Path(folder) / "input.fifo"
            os.mkfifo(fifo)
            grid = Path(folder) / "grid.json"
            grid.write_text(json.dumps(_GRID), encoding="utf-8", newline="\n")
            for label, argv in (
                ("--bank", _naming_the_bank(space.fill(), str(space.bank), str(fifo))),
                ("--excluded-terms", space.fill("--excluded-terms", str(fifo))),
                ("--mask", space.fill("--mask", str(fifo))),
                ("--words", ["shade", "--source", str(grid), "--words", str(fifo)]),
                (
                    "--source",
                    ["preview", "--source", str(fifo), "--out", str(space.svg)],
                ),
            ):
                with self.subTest(label):
                    code, errors = _run_tool(argv)
                    self.assertEqual(code, 2)
                    self.assertIn(f"{fifo} is not a regular file", errors)
                    self.assertFalse(space.out.exists() or space.svg.exists())


class TestEveryOtherInputFlag(cli_fixtures.QuietCase):
    """Every other flag naming an input refuses a device at exit 2, naming it."""

    def test_each_flag_refuses_a_device(self) -> None:
        device = str(_DEVICE)
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            grid = space.root / source_fixtures.SOURCE_NAME
            grid.write_text(json.dumps(_GRID), encoding="utf-8", newline="\n")
            source = str(grid)
            # A usable list, so `shade --source` can fail only on the grid.
            words = space.root / "words.txt"
            words.write_text("CAT\n", encoding="utf-8", newline="\n")
            routes = {
                "fill --phrases": space.fill("--phrases", device),
                "fill --source": source_fixtures.source_fill(space, _DEVICE),
                "shade --source": ["shade", "--source", device, "--words", str(words)],
                "gaps --source": ["gaps", "--source", device],
                "gaps --bank": ["gaps", "--source", source, "--bank", device],
                "gaps --words": ["gaps", "--source", source, "--words", device],
                "gaps --mask": ["gaps", "--source", source, "--mask", device],
                "gaps --phrases": ["gaps", "--source", source, "--phrases", device],
            }
            for route, argv in routes.items():
                # Cleared first, so a route that wrote fails only its own case.
                space.out.unlink(missing_ok=True)
                space.svg.unlink(missing_ok=True)
                with self.subTest(route=route):
                    already = len(self.errors)
                    self.assertEqual(decorative_crossword.main(argv), 2)
                    self.assertIn(
                        f"{device} is not a regular file", self.errors[already:]
                    )
                    self.assertFalse(space.out.exists())
                    self.assertFalse(space.svg.exists())


@unittest.skipUnless(os.path.lexists(_STDIN), _NO_DEV_STDIN)
class TestStandardInput(unittest.TestCase):
    """`/dev/stdin` is judged by what it is: a pipe is refused, a file is read."""

    def test_stdin_fed_from_a_pipe_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            reading, writing = os.pipe()
            self.addCleanup(os.close, reading)
            # A bank this small fits the pipe's buffer, so writing it all
            # before the child starts cannot block.
            with os.fdopen(writing, "wb") as sink:
                sink.write(space.bank.read_bytes())
            argv = _naming_the_bank(space.fill(), str(space.bank), _STDIN)
            code, errors = _run_tool(argv, stdin=reading)
            self.assertEqual(code, 2)
            self.assertIn(f"{_STDIN} is not a regular file", errors)
            self.assertFalse(space.out.exists())

    def test_stdin_redirected_from_a_file_is_read_as_that_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = _naming_the_bank(space.fill(), str(space.bank), _STDIN)
            with space.bank.open("rb") as bank:
                code, errors = _run_tool(argv, stdin=bank)
            self.assertEqual(code, 0, errors)
            self.assertTrue(space.out.exists())


if __name__ == "__main__":
    unittest.main()
