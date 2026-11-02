"""Fixtures shared by the CLI suites: banks, a workspace, a quiet base case, and a case probe.

`FOLDS_CASE` says whether this machine's temporary directory ignores case in a
file name, for the cases that prove an output is refused under another case.

Named `*_fixtures.py` rather than `test_*.py` so the aggregator's discovery
skips it and it carries no floor of its own, like every `*_fixtures.py` module
here.

The workspace writes a real bank into a real temporary directory and hands back
real paths, because what these suites test is a process boundary: an exit code,
and the files that did or did not appear beside it. A faked filesystem would
prove neither.

`QuietCase` exists so a suite that drives `main` does not spray a twenty-line
report per test across the run's own output. It captures both streams rather
than discarding them, so a test that wants to assert on what was printed reads
`self.printed` / `self.errors` instead of arranging its own redirect.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

#: Three themes carrying three answers each. Multi-theme deliberately: a
#: single-themed bank cannot exercise the theme floor as anything but a
#: pass/fail flag, and it hides the per-theme report block entirely.
#: Each theme is a {label, summary} record. Both fields are required and
#: non-empty at the parse boundary, because the summary is what the consumer's
#: readout leads with.
THEMES: dict[str, dict[str, str]] = {
    "a": {"label": "A", "summary": "The first theme"},
    "b": {"label": "B", "summary": "The second theme"},
    "c": {"label": "C", "summary": "The third theme"},
}

ENTRIES: list[dict[str, str]] = [
    {"answer": answer, "theme": theme}
    for theme, group in (
        ("a", ["ALPHA", "AMBER", "ANVIL"]),
        ("b", ["BRAVO", "BLADE", "BROOK"]),
        ("c", ["CEDAR", "CRANE", "CHALK"]),
    )
    for answer in group
]

BANK: dict[str, object] = {"themes": THEMES, "entries": ENTRIES}

#: A bank that declares no themes and attaches none: the `themes` map "may be
#: empty", with each entry's optional `theme` key simply absent rather
#: than null. Its own constant rather than BANK with the theme fields stripped,
#: because what these answers have to be is short and mutually crossable on a
#: small grid: the opposite of what BANK's three-theme shape is arranged for.
THEMELESS_ANSWERS: tuple[str, ...] = ("DELTA", "EAGLE", "TIGER", "LEMON")

THEMELESS_BANK: dict[str, object] = {
    "themes": {},
    "entries": [{"answer": answer} for answer in THEMELESS_ANSWERS],
}

#: The answer the clue-bearing variants below attach their clue to. Named once
#: so a test asserting on the emitted clue and the fixture that planted it
#: cannot drift onto two different answers.
CLUED_ANSWER = "AMBER"


def bank_with_clue(clue: str) -> dict[str, object]:
    """BANK with `clue` attached to CLUED_ANSWER's entry.

    Rebuilds the records rather than mutating ENTRIES, which every other
    fixture in this module shares.
    """
    return {
        "themes": THEMES,
        "entries": [
            {**entry, "clue": clue} if entry["answer"] == CLUED_ANSWER else entry
            for entry in ENTRIES
        ],
    }


def bank_with_theme_key(key: str) -> dict[str, object]:
    """A one-entry bank whose declared theme key is `key`.

    Separate from `bank_with_clue` because the key is a different untrusted
    field reaching the emitted document by a different path, and nothing but
    the clue-safety screen constrains its characters.
    """
    return {
        "themes": {key: {"label": "Label", "summary": "A summary"}},
        "entries": [{"answer": "AMBER", "theme": key}],
    }


def write_mis_encoded(path: Path) -> Path:
    """Write bytes at `path` that no UTF-8 decoder can read; return the path.

    `0xFF` never appears in a valid UTF-8 sequence in any position, so this is
    genuinely mis-encoded rather than merely unusual. It is the shape an editor
    saving an accented clue in a legacy code page produces, which is the
    ordinary way an operator reaches these seams.
    """
    path.write_bytes(b'{"themes": {}, "entries": [{"answer": "CAF\xff"}]}')
    return path


def folds_case() -> bool:
    """Whether a temporary file is found again under its name upper-cased.

    Probed rather than read off the platform: macOS and Windows volumes can be
    formatted either way, and so can a Linux mount.
    """
    with tempfile.TemporaryDirectory() as folder:
        probe = Path(folder) / "probe.json"
        probe.write_text("", encoding="utf-8", newline="\n")
        return (probe.parent / probe.name.upper()).exists()


#: Whether this machine's temporary directory ignores case in a file name.
FOLDS_CASE = folds_case()


class Workspace:
    """A temporary folder holding a written bank and paths for the outputs."""

    def __init__(self, folder: str, bank: dict[str, object] | None = None) -> None:
        """Write `bank` (or the shared default) into `folder` and name the outputs."""
        self.root = Path(folder)
        self.bank = self.root / "bank.json"
        self.bank.write_text(json.dumps(bank or BANK), encoding="utf-8", newline="\n")
        self.out = self.root / "grid_source.json"
        self.svg = self.root / "preview.svg"

    def fill(self, *extra: str) -> list[str]:
        """A minimal valid `fill` argv, plus whatever the test adds."""
        return [
            "fill",
            "--bank",
            str(self.bank),
            "--out",
            str(self.out),
            "--seed",
            "7",
            "--rows",
            "9",
            "--cols",
            "9",
            "--min-blocked",
            "0",
            "--max-blocked",
            "95",
            "--min-themes",
            "1",
            "--min-entries-per-theme",
            "1",
            "--max-steps",
            "4000",
            *extra,
        ]

    def excluded(self, *terms: str) -> Path:
        """Write an excluded-terms file holding `terms`, and return its path."""
        path = self.root / "excluded.txt"
        path.write_text(
            "".join(f"{term}\n" for term in terms), encoding="utf-8", newline="\n"
        )
        return path

    def mask(self, *rows: str) -> Path:
        """Write a `--mask` picture holding `rows`, and return its path.

        Beside `excluded` rather than in the one suite that needs it: a mask is
        an input file more than one suite gives the tool, and a second writer
        of the same format is a second thing to get the line endings wrong in.
        """
        path = self.root / "shape.txt"
        path.write_text(
            "".join(f"{row}\n" for row in rows), encoding="utf-8", newline="\n"
        )
        return path

    def document(self) -> dict[str, object]:
        """The written grid document, parsed."""
        parsed: dict[str, object] = json.loads(self.out.read_text(encoding="utf-8"))
        return parsed

    def clues(self) -> dict[str, dict[str, str]]:
        """The written grid's clue records, keyed by answer.

        Annotated at the binding for the same reason `rows` is: the document
        format fixes the shape, and `json.loads` is typed wherever it lands.
        """
        parsed: dict[str, dict[str, dict[str, str]]] = json.loads(
            self.out.read_text(encoding="utf-8")
        )
        return parsed["clues"]

    def rows(self) -> list[str]:
        """The written grid's rows.

        Re-reads the file under its own narrower annotation rather than
        narrowing `document`'s `object` values with a cast: the shape of
        `rows` is fixed by the document format, and a `json.loads` result is
        typed at the binding either way.
        """
        parsed: dict[str, list[str]] = json.loads(self.out.read_text(encoding="utf-8"))
        return parsed["rows"]


class QuietCase(unittest.TestCase):
    """A TestCase whose subject's stdout and stderr are captured, not printed.

    Captured rather than suppressed: a diagnostic this base class threw away
    would be a diagnostic no test could assert on, and half of the exit-code
    contract is *what the tool said*, not just the number it returned.
    """

    def setUp(self) -> None:
        """Redirect both streams for the duration of one test."""
        self._out = io.StringIO()
        self._err = io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(self._out))
        stack.enter_context(contextlib.redirect_stderr(self._err))

    @property
    def printed(self) -> str:
        """Everything the subject has written to stdout so far."""
        return self._out.getvalue()

    @property
    def errors(self) -> str:
        """Everything the subject has written to stderr so far."""
        return self._err.getvalue()
