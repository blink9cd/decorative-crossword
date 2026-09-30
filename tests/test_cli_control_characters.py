"""CLI tests: a control character in operator text never reaches the terminal raw.

Two answers to one hazard, chosen by who owns the text's shape. A bank and a
grid file follow a schema this tool defines, so a label carrying a control
character is refused at exit 2 before anything is written or printed. A word
list is free text read line by line, whose unusable lines are skipped and
named in the report, so a skipped line is shown with each such character
escaped -- visibly, so the operator can see the line held something odd --
rather than refused.

A bidi control is escaped wherever the report prints a label or a skipped
line, but never refused: it is legal text in a label, so the grid file keeps
it as written.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import json
import tempfile
from pathlib import Path

import decorative_crossword
from tests import cli_fixtures

#: An OSC sequence that retitles a terminal window: ESC, the payload, BEL.
_RETITLE = "\x1b]0;pwned\x07"

#: The same sequence once a word-list reader has upper-cased it and this tool
#: has escaped it for the report.
_RETITLE_SHOWN = "\\x1b]0;PWNED\\x07"

#: A right-to-left override: on a terminal it reverses the rest of the line it
#: is printed on, so a report line could read as something it does not say.
_OVERRIDE = "\U0000202e"

#: How the report shows it.
_OVERRIDE_SHOWN = r"\u202e"

#: A grid document for the read commands: one themed across entry.
_GRID: dict[str, object] = {
    "rows": ["CAT", "O..", "WET"],
    "themes": {"pets": {"label": "Pets", "summary": "Two cats"}},
    "clues": {"CAT": {"clue": "Sleeps on the keyboard", "theme": "pets"}},
}


def _bank_labeled(label: str) -> dict[str, object]:
    """The shared three-theme bank with theme `a` relabeled `label`."""
    themes = {**cli_fixtures.THEMES, "a": {**cli_fixtures.THEMES["a"], "label": label}}
    return {"themes": themes, "entries": cli_fixtures.ENTRIES}


def _write(path: Path, text: str) -> Path:
    """Write `text` at `path` and return the path."""
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _word_list(space: cli_fixtures.Workspace) -> Path:
    """A word list holding a usable word and four lines the reader skips.

    The skipped lines hold a retitling sequence, a right-to-left override, a
    soft hyphen and an accented letter.
    """
    return _write(
        space.root / "words.txt",
        f"CAT\nDO{_RETITLE}G\nDOG{_OVERRIDE}CAT\nCAT\xadNAP\nCAF\xe9\n",
    )


class TestSchemaText(cli_fixtures.QuietCase):
    """A bank or grid string carrying a control character is exit 2, printed nowhere raw."""

    def test_fill_refuses_a_bank_label_before_printing_it(self) -> None:
        for label in (f"A{_RETITLE}", "A\x9b2J", "A\U0000d800"):
            with (
                self.subTest(label=ascii(label)),
                tempfile.TemporaryDirectory() as folder,
            ):
                space = cli_fixtures.Workspace(folder, _bank_labeled(label))
                printed, errors = len(self.printed), len(self.errors)
                self.assertEqual(decorative_crossword.main(space.fill()), 2)
                self.assertFalse(space.out.exists())
                said = self.printed[printed:] + self.errors[errors:]
                self.assertIn(f"U+{ord(label[1]):04X}", said)
                self.assertNotIn(label[1], said)

    def test_preview_refuses_a_grid_label_no_svg_can_hold(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            themes = {"pets": {"label": "Pets\x01", "summary": "Two cats"}}
            _write(space.out, json.dumps({**_GRID, "themes": themes}))
            argv = ["preview", "--source", str(space.out), "--out", str(space.svg)]
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertFalse(space.svg.exists())
            self.assertIn("U+0001", self.errors)


class TestPrintedLabels(cli_fixtures.QuietCase):
    """A bank label is printed with its bidi controls escaped, and kept as written."""

    def test_fill_escapes_a_bidi_control_in_the_themes_block(self) -> None:
        label = f"Caf\xe9{_OVERRIDE}"
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder, _bank_labeled(label))
            self.assertEqual(decorative_crossword.main(space.fill()), 0)
            said = self.printed + self.errors
            # The accented letter is text to a terminal, so it is left as written.
            self.assertIn(f"Caf\xe9{_OVERRIDE_SHOWN}: ", said)
            self.assertNotIn(_OVERRIDE, said)
            written: dict[str, dict[str, dict[str, str]]] = json.loads(
                space.out.read_text(encoding="utf-8")
            )
            self.assertEqual(written["themes"]["a"]["label"], label)


class TestSkippedLines(cli_fixtures.QuietCase):
    """A skipped word-list line is named with its control characters escaped."""

    def assert_shown_escaped(self) -> None:
        """The report names each odd line escaped, and nothing else changed."""
        self.assertIn(_RETITLE_SHOWN, self.printed)
        self.assertNotIn("\x1b", self.printed)
        self.assertNotIn("\x07", self.printed)
        self.assertIn(f"DOG{_OVERRIDE_SHOWN}CAT", self.printed)
        self.assertNotIn(_OVERRIDE, self.printed)
        # A format character that is not a bidi control, and an accented
        # letter, are text to a terminal: each is left as written.
        self.assertIn("CAT\xadNAP", self.printed)
        self.assertIn("CAF\xc9", self.printed)

    def test_shade_escapes_a_skipped_words_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            _write(space.out, json.dumps(_GRID))
            words = _word_list(space)
            decorative_crossword.main(
                ["shade", "--source", str(space.out), "--words", str(words)]
            )
            self.assert_shown_escaped()

    def test_gaps_escapes_a_skipped_words_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            _write(space.out, json.dumps(_GRID))
            words = _word_list(space)
            decorative_crossword.main(
                ["gaps", "--source", str(space.out), "--words", str(words)]
            )
            self.assert_shown_escaped()

    def test_fill_escapes_a_skipped_phrases_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            phrases = _word_list(space)
            decorative_crossword.main(space.fill("--phrases", str(phrases)))
            self.assert_shown_escaped()
