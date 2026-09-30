r"""Tests for what the input readers make of a file's text: its first character and its lines.

Two rules hold for every input file:

- one that begins with a byte-order mark is refused. Read as text, the mark
  would become part of the first line, so a barred term written there would
  match nothing, and nothing would say so;
- a line ends only where an editor ends one: at `\n`, `\r\n` or a lone `\r`.
  `str.splitlines` also ends one at eight other characters, so a line number
  counted that way can name a line the operator's editor shows as another,
  and a word list line holding one of them would be read as two words.

The line rule is carried by one shared split, which the three readers that
take a file line by line -- the excluded-terms list, the mask and the word or
phrase list -- all call. For a text holding none of the eight, each reader
must return exactly what it did when it split with `str.splitlines`, and a
property per reader holds it to that.

The mark is refused through the command line as well as by each reader: a
marked file ends the run at exit 2, in one line naming it, and writes nothing.
That is pinned end to end on one input flag per reader. Every other input flag
reaches one of those same readers, so the reader's own case in this file holds
it to the mark, rather than a command-line case of its own.

Entry point assumptions: run through the parent aggregator's `load_tests` hook,
which puts the project root and `src/` on `sys.path`.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

import cw_bank
import cw_excluded_terms
import cw_grid_document
import cw_input
import cw_mask
import cw_shade
import decorative_crossword
from tests import cli_fixtures, source_fixtures

# A registered profile loaded at import, never an `@settings` decorator, as the
# project's other property suites do. Derandomized so the in-suite run is
# reproducible; no deadline, because most examples write a file and a
# per-example wall clock would measure the disk rather than the reader.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_input_text_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_input_text_properties")

#: The character a byte-order mark decodes to.
_BOM = "\U0000feff"

#: What every reader's refusal of a leading byte-order mark says after the path.
_BOM_REFUSAL = "begins with a byte-order mark (U+FEFF); save it as UTF-8 without one"

#: LINE SEPARATOR and NEXT LINE, the two of the eight most likely to arrive in
#: text pasted from elsewhere.
_LINE_SEPARATOR = "\U00002028"
_NEXT_LINE = "\x85"

#: The eight characters `str.splitlines` ends a line at and an editor does not:
#: line tabulation, form feed, the three information separators, NEXT LINE,
#: LINE SEPARATOR and PARAGRAPH SEPARATOR.
_SPLITLINES_ONLY = (
    "\x0b",
    "\x0c",
    "\x1c",
    "\x1d",
    "\x1e",
    _NEXT_LINE,
    _LINE_SEPARATOR,
    "\U00002029",
)

#: What a mask refusal calls the input when no file is involved.
_NAME = "shape.txt"

#: The pieces the readers' rules turn on, drawn far more often than arbitrary
#: text would reach them: each line end, a blank and a tab, the comment
#: prefix, both of a mask's marks and a letter.
_EDGES = ("\n", "\r", "\r\n", " ", "\t", "#", ".", "X", "A")

#: Text holding none of the eight, assembled from arbitrary characters and the
#: edges above. It never begins with U+FEFF, which a file reader refuses before
#: any line is split, and holds no surrogate, which no UTF-8 file can.
_ORDINARY_TEXT = (
    st.lists(
        st.one_of(
            st.text(
                st.characters(codec="utf-8", exclude_characters=_SPLITLINES_ONLY),
                max_size=4,
            ),
            st.sampled_from(_EDGES),
        ),
        max_size=24,
    )
    .map("".join)
    .filter(lambda text: not text.startswith(_BOM))
)

#: Any text at all, with the eight drawn as often as the other edges.
_ANY_TEXT = st.lists(
    st.one_of(st.text(max_size=4), st.sampled_from(_EDGES + _SPLITLINES_ONLY)),
    max_size=24,
).map("".join)


def _written(folder: str, text: str) -> Path:
    """Write `text` into `folder` as UTF-8, line ends untouched, and return its path."""
    path = Path(folder) / "input.txt"
    path.write_bytes(text.encode("utf-8"))
    return path


def _lines_read_in_universal_newline_mode(text: str) -> tuple[str, ...]:
    r"""The lines of `text` as a Python text stream in universal-newline mode reads them.

    Such a stream ends a line at `\n`, `\r\n` or a lone `\r` and at nothing
    else, which is the editor's rule, so this re-derives the answer without
    the subject's own split.
    """
    return tuple(line.removesuffix("\n") for line in io.StringIO(text, newline=None))


def _split_as_before(text: str) -> tuple[str, ...]:
    """`text` split by `str.splitlines`, the split every line reader used to make."""
    return tuple(text.splitlines())


def _outcome(read: Callable[[], object]) -> object:
    """What `read` returns, or the type and message of the refusal it raises instead.

    Every reader's refusal is a `ValueError`, so a reader that raised anything
    else fails the property outright rather than being compared.
    """
    try:
        return read()
    except ValueError as exc:
        return type(exc), str(exc)


class TestEditorLines(unittest.TestCase):
    """The shared split ends a line where an editor does and nowhere else."""

    def test_a_line_ends_at_each_of_the_three_line_ends(self) -> None:
        self.assertEqual(cw_input.editor_lines("a\nb\r\nc\rd"), ("a", "b", "c", "d"))

    def test_a_final_line_end_closes_a_line_rather_than_opening_one(self) -> None:
        # As `str.splitlines` has it, so a reader loses nothing and gains no
        # blank last line -- which a mask would refuse.
        for text, lines in (
            ("", ()),
            ("a", ("a",)),
            ("a\n", ("a",)),
            ("a\r\n", ("a",)),
            ("a\r", ("a",)),
            ("\n", ("",)),
            ("a\n\n", ("a", "")),
        ):
            with self.subTest(text=text):
                self.assertEqual(cw_input.editor_lines(text), lines)

    def test_none_of_the_eight_ends_a_line(self) -> None:
        for separator in _SPLITLINES_ONLY:
            with self.subTest(f"U+{ord(separator):04X}"):
                self.assertEqual(
                    cw_input.editor_lines(f"a{separator}b\n"), (f"a{separator}b",)
                )

    def test_the_eight_are_all_that_splitlines_adds(self) -> None:
        # Measured on the running interpreter, so the properties that exclude
        # the eight cannot silently miss one a later Python adds.
        breaking = {
            chr(point)
            for point in range(sys.maxunicode + 1)
            if len(f"a{chr(point)}b".splitlines()) == 2
        }
        self.assertEqual(breaking - {"\n", "\r"}, set(_SPLITLINES_ONLY))

    @given(_ANY_TEXT)
    @example(f"a{_LINE_SEPARATOR}b\r\nc{_NEXT_LINE}\r")
    def test_the_lines_are_those_universal_newline_reading_gives(
        self, text: str
    ) -> None:
        self.assertEqual(
            cw_input.editor_lines(text), _lines_read_in_universal_newline_mode(text)
        )

    @given(_ORDINARY_TEXT)
    @example("")
    @example("\n\n")
    @example("a\r\r\nb\r")
    def test_without_the_eight_the_lines_are_those_splitlines_gives(
        self, text: str
    ) -> None:
        self.assertEqual(cw_input.editor_lines(text), _split_as_before(text))


class TestReadersKeepTheirResults(unittest.TestCase):
    """For text holding none of the eight, each reader returns what it did before.

    "Before" is the reader run with `str.splitlines` in place of the shared
    split, which is the reader exactly as it was: the split is all that
    changed. The stand-in must be called, and once, or the comparison would
    be of the reader with itself.
    """

    def _assert_unchanged(self, read: Callable[[], object]) -> None:
        """`read` gives the same result, or the same refusal, split either way."""
        now = _outcome(read)
        with mock.patch.object(
            cw_input, "editor_lines", side_effect=_split_as_before
        ) as split:
            before = _outcome(read)
        split.assert_called_once()
        self.assertEqual(now, before)

    @given(_ORDINARY_TEXT)
    def test_the_excluded_terms_list(self, text: str) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, text)
            self._assert_unchanged(lambda: cw_excluded_terms.load_excluded_terms(path))

    @given(_ORDINARY_TEXT, st.booleans())
    def test_the_word_list(self, text: str, close_up: bool) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, text)
            self._assert_unchanged(
                lambda: cw_shade.load_word_list(path, close_up=close_up)
            )

    @given(_ORDINARY_TEXT)
    @example("")
    @example("\n")
    @example("X.\n..")
    @example(".X\r\n..\r\n")
    @example(".\n\n.\n")
    def test_the_mask(self, text: str) -> None:
        # The parser itself, fed the text raw: it is also handed text that
        # never passed through the file reader's line-end translation.
        self._assert_unchanged(lambda: cw_mask.parse_mask(text, _NAME))


class TestLineEnds(unittest.TestCase):
    """A character only `str.splitlines` breaks at stays inside its line."""

    def test_a_mask_refusal_names_the_line_an_editor_shows(self) -> None:
        # Split at the LINE SEPARATOR, line 2 became two rows two cells wide,
        # and the refusal named line 4 of a three-line file.
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, f"# a shape\n..{_LINE_SEPARATOR}..\n.....\n")
            with self.assertRaises(cw_mask.MaskError) as caught:
                cw_mask.load_mask(path)
        self.assertIn(
            f"mask file {path} line 2 column 3 holds {_LINE_SEPARATOR!r}",
            str(caught.exception),
        )

    def test_a_word_list_line_holding_next_line_is_one_skipped_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, f"CAT{_NEXT_LINE}DOG\nBIRD\n")
            words, skipped = cw_shade.load_word_list(path)
        self.assertEqual(words, ("BIRD",))
        self.assertEqual([word for word, _ in skipped], [f"CAT{_NEXT_LINE}DOG"])
        self.assertIn("A-Z", skipped[0][1])

    def test_a_phrase_list_closes_up_next_line_as_it_does_a_space(self) -> None:
        # A phrase list removes the whitespace inside a line, and NEXT LINE
        # is whitespace, so the line's two words join as a space's would.
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, f"atta{_NEXT_LINE}boy\n")
            words, skipped = cw_shade.load_word_list(path, close_up=True)
        self.assertEqual(words, ("ATTABOY",))
        self.assertEqual(skipped, ())

    def test_a_term_list_line_holding_a_line_separator_is_one_term(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, f"hello{_LINE_SEPARATOR}there\n")
            terms = cw_excluded_terms.load_excluded_terms(path)
        self.assertEqual(terms, frozenset({f"hello{_LINE_SEPARATOR}there"}))


class TestByteOrderMark(unittest.TestCase):
    """A file that begins with a byte-order mark is refused, whichever input it is."""

    def test_a_term_list_that_begins_with_one_is_refused(self) -> None:
        # Read as text, the mark joined the first term, which then matched
        # no entry: the one barred term the list opened with went unscreened.
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, f"{_BOM}barred\nother\n")
            with self.assertRaises(cw_bank.BankError) as caught:
                cw_excluded_terms.load_excluded_terms(path)
        self.assertEqual(
            str(caught.exception),
            f"could not read excluded-terms file {path}: {path} {_BOM_REFUSAL}",
        )

    def test_every_input_refuses_one_before_reading_it_as_its_format(self) -> None:
        # One file serves every reader: the refusal comes before any of them
        # judges the rest, so a JSON reader never gets to call it bad JSON.
        readers: tuple[tuple[str, Callable[[Path], object]], ...] = (
            ("--bank", cw_bank.load_bank),
            ("--source", cw_grid_document.load_document),
            ("--excluded-terms", cw_excluded_terms.load_excluded_terms),
            ("--mask", cw_mask.load_mask),
            ("--words", cw_shade.load_word_list),
        )
        for label, read in readers:
            with self.subTest(label), tempfile.TemporaryDirectory() as folder:
                path = _written(folder, f"{_BOM}{{}}\n")
                with self.assertRaises(ValueError) as caught:
                    read(path)
                self.assertIn(f"{path} {_BOM_REFUSAL}", str(caught.exception))


class TestByteOrderMarkOnTheCommandLine(cli_fixtures.QuietCase):
    """A marked file given to one input flag per reader ends the run at exit 2, in one line."""

    def test_fill_refuses_a_marked_term_list_rather_than_placing_the_term(self) -> None:
        # The case that was silent: the list's first term matched nothing.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = _written(folder, f"{_BOM}alpha\n")
            argv = space.fill("--excluded-terms", str(terms))
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertIn(f"{terms} {_BOM_REFUSAL}", self.errors)
            # One line, and so one refusal alone: neither printed after a
            # report, nor spread over a second line.
            self.assertEqual(self.errors.count("\n"), 1, self.errors)
            self.assertEqual(self.printed, "")
            self.assertFalse(space.out.exists())

    def test_one_input_flag_per_reader_refuses_a_marked_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            marked = str(_written(folder, f"{_BOM}{{}}\n"))
            grid = space.root / source_fixtures.SOURCE_NAME
            grid.write_text(
                json.dumps({"rows": ["CAT", "O..", "WET"]}),
                encoding="utf-8",
                newline="\n",
            )
            bank = space.fill()
            bank[bank.index("--bank") + 1] = marked
            routes = {
                "fill --bank": bank,
                "fill --excluded-terms": space.fill("--excluded-terms", marked),
                "fill --mask": source_fixtures.without_size(
                    space.fill("--mask", marked)
                ),
                "shade --words": ["shade", "--source", str(grid), "--words", marked],
                "preview --source": [
                    "preview",
                    "--source",
                    marked,
                    "--out",
                    str(space.svg),
                ],
            }
            for route, argv in routes.items():
                with self.subTest(route=route):
                    already = len(self.errors)
                    self.assertEqual(decorative_crossword.main(argv), 2)
                    said = self.errors[already:]
                    self.assertIn(f"{marked} {_BOM_REFUSAL}", said)
                    self.assertEqual(said.count("\n"), 1, said)
                    self.assertFalse(space.out.exists())
                    self.assertFalse(space.svg.exists())


if __name__ == "__main__":
    unittest.main()
