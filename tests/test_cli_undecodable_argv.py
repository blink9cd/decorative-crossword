"""CLI test: a mistyped path holding a byte that is not UTF-8 is refused at exit 2.

Python decodes argv with `surrogateescape`, so the byte 0xFF in an argument
arrives as a lone surrogate, and every refusal of an input names its path. The
refusal must reach stderr with that byte escaped. It does because the tool
escapes every refusal line before printing it, its own and the argument
parser's alike, and a lone surrogate is among the characters escaped; stderr's
own escaping of a character it cannot encode is only the backstop behind that.
With neither, the write would raise instead, a traceback and exit 1, which
this tool also means as "no conforming grid", so a typo would read as a verdict.

The child is the real entry point, run as a script and writing to a real
stderr: a redirect to `io.StringIO` stores the surrogate without encoding it,
so no in-process test can see this at all. That stderr is a file rather than a
pipe, so the timeout binds (test_cli_input.py says why). The argv byte works on
macOS too: APFS restricts file names, not arguments.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

#: The entry point, run as a script. Derived from this file's own location so
#: the suite survives a move.
_ENTRY_POINT = Path(__file__).resolve().parent.parent / "decorative_crossword.py"

#: Seconds the child gets. It imports the tool and refuses one path, which
#: takes about a second, so anything near this is a hang.
_CHILD_TIMEOUT = 60.0

#: A grid file that does not exist, named with the byte 0xFF: what
#: `surrogateescape` hands the tool for that byte.
_MISTYPED = "\udcffmissing.json"


class TestUndecodableArgument(unittest.TestCase):
    """A refusal naming an argv path that is not UTF-8 prints it escaped."""

    def test_a_mistyped_source_is_refused_escaped_at_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            errors = scratch / "stderr.bin"
            with errors.open("wb") as stderr:
                # A file and DEVNULL, not pipes: nothing for a grandchild to hold
                # open, so the timeout binds.
                done = subprocess.run(  # reliability: ignore[RL005] file sinks, no pipe
                    [
                        sys.executable,
                        str(_ENTRY_POINT),
                        "preview",
                        "--source",
                        _MISTYPED,
                        "--out",
                        "grid.svg",
                    ],
                    cwd=scratch,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr,
                    timeout=_CHILD_TIMEOUT,
                    check=False,
                )
            written = errors.read_bytes()
            self.assertEqual(done.returncode, 2, written)
            self.assertIn(b"could not read grid file \\udcffmissing.json", written)
            self.assertNotIn(b"Traceback", written)
            self.assertFalse((scratch / "grid.svg").exists())
