"""Grouped suite: property tests for every reader of an operator's file, and two text screens.

Each reader of a file the operator hands over carries a `# fuzz-target`
marker, the one a property-test runner looks for, paired with a
`test_fuzz_<name>` below: the bank reader, the grid file reader, the mask reader, the word or phrase list reader
and the barred-term list reader. So do two functions that take operator text
without a file: the barred-term screen and the `--island-letters` parser.

The binding claim is the same for every one of them: whatever the input, the
function returns, or it raises its own refusal type (the one its command
turns into exit 2 and a single line naming the input), and nothing else. Any
other exception escapes the `except` clause and fails the property. A file
reader's refusal must also name the file, or the operator cannot tell which
input was wrong.

Where a reader hands its result on, the property follows it one step further.
A bank payload goes to `cw_bank.parse_bank`, which must take it or refuse it
as `BankError` too: the reader refuses a repeated key, over-deep nesting and
a long integer wherever they sit, but judges no field's value, so without this
a NaN or a surrogate in one would reach no validator at all, and every
refusal quotes it, so `repr` must be able to walk it. A grid file's theme text
is drawn into an SVG, so it must hold only characters XML allows, which is
re-derived here rather than asked of the subject.

The files are drawn by `tests/loader_fixtures.py`, which says what they hold
and why.

Entry point assumptions: run through the parent aggregator's `load_tests`
hook, or by a fuzz runner that imports this file by location. The two reach it
differently, so the bootstrap below names the project root and `src/` rather
than relying on either.
"""

from __future__ import annotations

import contextlib
import json
import string
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_config  # noqa: E402 - same bootstrap
import cw_emit  # noqa: E402 - same bootstrap
import cw_excluded_terms  # noqa: E402 - same bootstrap
import cw_grid  # noqa: E402 - same bootstrap
import cw_grid_document  # noqa: E402 - same bootstrap
import cw_island  # noqa: E402 - same bootstrap
import cw_mask  # noqa: E402 - same bootstrap
import cw_shade  # noqa: E402 - same bootstrap
from tests import loader_fixtures  # noqa: E402 - same bootstrap

# A registered profile loaded at import, never an `@settings` decorator, which
# a campaign runner could not re-stamp. Derandomized so the in-suite run is
# reproducible; no deadline, because most examples write a file, and a
# per-example wall clock would measure the disk rather than the reader.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_loader_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_loader_properties")

#: One declared theme, as a bank and a grid file both write it.
_THEMES = {"a": {"label": "Alpha", "summary": "The first theme"}}

#: A well-formed bank: every field an entry may carry, and a written spelling.
_BANK: dict[str, object] = {
    "themes": _THEMES,
    "entries": [
        {"answer": "CAT", "theme": "a", "clue": "A pet", "rating": 3},
        {"answer": "HELLO THERE"},
    ],
}

#: A well-formed grid file: CAT and WET across, COW down, one of them clued.
_GRID: dict[str, object] = {
    "rows": ["CAT", "O..", "WET"],
    "themes": _THEMES,
    "clues": {"CAT": {"clue": "A pet", "theme": "a"}, "COW": {}},
}

#: Where the grid file above writes its one theme's label.
_LABEL: tuple[loader_fixtures.Step, ...] = ("themes", "a", "label")

#: The file of nothing but the long number, and of nothing but either depth of
#: nesting: each is refused before any field of either format is looked at.
_LONG = loader_fixtures.encoded(loader_fixtures.LONG_NUMBER)
_DEEP = loader_fixtures.encoded(loader_fixtures.nested(loader_fixtures.DEEP))
_DEEPER = loader_fixtures.encoded(loader_fixtures.nested(loader_fixtures.DEEPER))


#: A file that is not UTF-8 at all: one byte no UTF-8 sequence can start with.
_NOT_UTF8 = b"\xff"


def _written_with(
    document: dict[str, object], path: tuple[loader_fixtures.Step, ...], fragment: str
) -> bytes:
    """`document` as a file, with the value at `path` written as the JSON text `fragment`."""
    return loader_fixtures.encoded(loader_fixtures.spliced(document, path, fragment))


def _grid_file(path: tuple[loader_fixtures.Step, ...], fragment: str) -> bytes:
    """The grid file above, with the value at `path` written as the JSON text `fragment`."""
    return _written_with(_GRID, path, fragment)


def _bank_file(path: tuple[loader_fixtures.Step, ...], fragment: str) -> bytes:
    """The bank above, with the value at `path` written as the JSON text `fragment`."""
    return _written_with(_BANK, path, fragment)


#: Where the bank above writes its first entry's rating, and its clue.
_RATING: tuple[loader_fixtures.Step, ...] = ("entries", 0, "rating")
_CLUE: tuple[loader_fixtures.Step, ...] = ("entries", 0, "clue")


#: A well-formed mask: a comment, then a picture with a notch in it.
_PICTURE = ("# a notch", ".X.", "...", "X..")

#: A well-formed word or phrase list: a comment, a word, and two phrases.
_WORDS = ("# hidden words", "CAT", "hello there", "atta-boy")

#: A well-formed barred-term list: a comment, then terms in mixed case and padding.
_TERMS = ("# barred", "cat", "Web Site", "  -ish  ")


def _xml_characters(text: str) -> bool:
    """Whether every character of `text` is one an XML 1.0 document may hold.

    The XML `Char` production, restated here rather than asked of the subject:
    tab, line feed, carriage return, and every code point from the space up
    except the surrogates and U+FFFE and U+FFFF.
    """
    return all(
        char in "\t\n\r"
        or " " <= char <= "\U0000d7ff"
        or "\U0000e000" <= char <= "\U0000fffd"
        or char >= "\U00010000"
        for char in text
    )


class _ReaderCase(unittest.TestCase):
    """A case that hands a reader a real file and checks how it refuses one."""

    def _read[T](
        self, read: Callable[[Path], T], refusal: type[ValueError], content: bytes
    ) -> T | None:
        """What `read` returns for a file holding `content`, or None if it refuses it.

        Only `refusal` is caught, so any other exception fails the property;
        and a refusal must name the file it refused.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = loader_fixtures.written(folder, content)
            try:
                return read(path)
            except refusal as exc:
                self.assertIn(str(path), str(exc))
                return None


class TestJsonReaderProperties(_ReaderCase):
    """The bank and grid file readers, over any bytes and any JSON."""

    # Regression seeds, each a file the reader once failed on: the long number
    # escaped the parser as a plain ValueError and the deeper nesting as a
    # RecursionError, while the deep nesting came back as a payload `repr`
    # could not walk.
    @given(loader_fixtures.json_files(_BANK))
    @example(_LONG)
    @example(_DEEP)
    @example(_DEEPER)
    # Values the reader passes on without looking, pinned so each reaches the
    # validator on every run: NaN and an infinity where a rating goes, a lone
    # surrogate in a clue, a file that is not UTF-8, and a file holding only
    # `null`, which parses to the None `_read` also returns for a refusal.
    @example(_bank_file(_RATING, "NaN"))
    @example(_bank_file(_RATING, "-Infinity"))
    @example(_bank_file(_CLUE, json.dumps("\U0000d800")))
    @example(_NOT_UTF8)
    @example(b"null")
    def test_fuzz_read_bank_payload(self, content: bytes) -> None:
        """A payload `repr` can walk and the validator takes or refuses, or BankError."""
        # Boxed, so a payload of None is told apart from a refusal.
        read = self._read(
            lambda path: (cw_bank.read_bank_payload(path),), cw_bank.BankError, content
        )
        if read is None:
            return
        (payload,) = read
        # Every refusal downstream quotes the value at fault from its `repr`,
        # so a payload the reader hands on must be one `repr` can walk.
        self.assertIsInstance(repr(payload), str)
        # What an accepted bank must hold is `test_fuzz_parse_bank`'s to check.
        # Here only the refusal type is, on what a file can carry and that
        # property's payloads are not built from: NaN, the infinities and a
        # lone surrogate, in any field. The long number and the deep nesting
        # never get this far, because the reader refuses both.
        with contextlib.suppress(cw_bank.BankError):
            cw_bank.parse_bank(payload)

    # Regression seeds, each a file the reader once failed on. A label no SVG
    # can hold (a lone surrogate, a control character) was accepted. The
    # long number and the deeper nesting escaped the parser, and the deep
    # nesting, wherever it sat, overflowed the refusal that quoted it.
    @given(loader_fixtures.json_files(_GRID))
    @example(_grid_file(_LABEL, json.dumps("\U0000d800")))
    @example(_grid_file(_LABEL, json.dumps("\x1f")))
    @example(_grid_file(_LABEL, loader_fixtures.nested(loader_fixtures.DEEP)))
    @example(_grid_file(("themes", "a"), loader_fixtures.nested(loader_fixtures.DEEP)))
    @example(_grid_file(("themes",), loader_fixtures.nested(loader_fixtures.DEEP)))
    @example(_grid_file(("rows", 1), loader_fixtures.nested(loader_fixtures.DEEP)))
    @example(_grid_file(("rows",), loader_fixtures.nested(loader_fixtures.DEEP)))
    @example(_grid_file(("rows",), loader_fixtures.nested(loader_fixtures.DEEPER)))
    @example(_DEEP)
    @example(_LONG)
    @example(_NOT_UTF8)
    def test_fuzz_load_document(self, content: bytes) -> None:
        """A document whose theme text XML can hold, or EmitError naming the file."""
        document = self._read(
            cw_grid_document.load_document, cw_emit.EmitError, content
        )
        if document is None:
            return
        for info in document.themes.values():
            self._assert_drawable(info.label)
            self._assert_drawable(info.summary)

    def _assert_drawable(self, text: str) -> None:
        """Fail unless `text` can be written into the SVG: as UTF-8, and as XML."""
        # UTF-8 has no encoding for a lone surrogate, so this raises for one,
        # and fails the property as its own finding rather than as the
        # assertion below, which would otherwise report the two as one.
        text.encode("utf-8")
        self.assertTrue(_xml_characters(text), ascii(text))


class TestLineReaderProperties(_ReaderCase):
    """The mask, word list and barred-term readers, over any bytes and any text."""

    @given(loader_fixtures.line_files(_PICTURE))
    @example(_NOT_UTF8)
    def test_fuzz_load_mask(self, content: bytes) -> None:
        """A mask, or MaskError naming the file."""
        mask = self._read(cw_mask.load_mask, cw_mask.MaskError, content)
        if mask is not None:
            self.assertIsInstance(mask, cw_mask.Mask)

    @given(loader_fixtures.line_files(_WORDS), st.booleans())
    @example(_NOT_UTF8, False)
    def test_fuzz_load_word_list(self, content: bytes, close_up: bool) -> None:
        """Usable words of A-Z alone, each once, or ShadeError naming the file."""
        loaded = self._read(
            lambda path: cw_shade.load_word_list(path, close_up=close_up),
            cw_shade.ShadeError,
            content,
        )
        if loaded is None:
            return
        words, skipped = loaded
        self.assertEqual(len(set(words)), len(words))
        for word in words:
            self.assertGreaterEqual(len(word), cw_grid.MIN_RUN)
            self.assertTrue(set(word) <= set(string.ascii_uppercase), ascii(word))
        for _, reason in skipped:
            self.assertTrue(reason)

    @given(loader_fixtures.line_files(_TERMS))
    @example(_NOT_UTF8)
    def test_fuzz_load_excluded_terms(self, content: bytes) -> None:
        """Terms that are each one trimmed, folded, uncommented line, or BankError."""
        terms = self._read(
            cw_excluded_terms.load_excluded_terms, cw_bank.BankError, content
        )
        for term in terms or ():
            self.assertTrue(term)
            self.assertEqual(term, term.strip().lower())
            self.assertFalse(term.startswith("#"), ascii(term))
            self.assertFalse({"\n", "\r"} & set(term), ascii(term))


#: One word of a written answer.
_WORD = st.text(alphabet=string.ascii_uppercase, min_size=1, max_size=4)


@st.composite
def _entries(draw: st.DrawFn) -> cw_bank.BankEntry:
    """A bank entry as `parse_bank` could return one, but with a clue of any text.

    A clue is free text, and `screen_excluded` is public: a bank built in code
    never passed the parse boundary's screen.
    """
    words = [
        draw(st.text(string.ascii_uppercase, min_size=cw_grid.MIN_RUN, max_size=4)),
        *draw(st.lists(_WORD, max_size=2)),
    ]
    joiner = draw(st.sampled_from(" -"))
    return cw_bank.BankEntry(
        answer="".join(words),
        theme=draw(st.sampled_from((None, "a"))),
        clue=draw(st.one_of(st.none(), loader_fixtures.ANY_TEXT)),
        spelling=joiner.join(words) if len(words) > 1 else None,
    )


def _pieces(entry: cw_bank.BankEntry) -> list[str]:
    """Terms that would match `entry`: its written form, its words, its clue."""
    written = entry.written.lower()
    return [written, *written.replace("-", " ").split(), *filter(None, [entry.clue])]


@st.composite
def _screen_requests(draw: st.DrawFn) -> tuple[cw_bank.Bank, frozenset[str]]:
    """A bank, and barred terms drawn from its own text as often as from any text."""
    entries = draw(
        st.lists(_entries(), min_size=1, max_size=4, unique_by=lambda e: e.answer)
    )
    pieces = [piece for entry in entries for piece in _pieces(entry)]
    terms = draw(
        st.frozensets(
            st.one_of(loader_fixtures.ANY_TEXT, st.sampled_from(pieces)), max_size=4
        )
    )
    themes = MappingProxyType({"a": cw_bank.ThemeInfo("Alpha", "The first theme")})
    return cw_bank.Bank(themes=themes, entries=tuple(entries)), terms


#: A bank whose one clue holds a lone surrogate, and a term that is one: the
#: screen must match it as text like any other rather than fail on it.
_SURROGATE_SCREEN = (
    cw_bank.Bank(
        themes=MappingProxyType({}),
        entries=(cw_bank.BankEntry(answer="CAT", theme=None, clue="a \U0000d800 pet"),),
    ),
    frozenset({"\U0000d800"}),
)

#: Island-letter values near the accepted ones: the letters in both cases, a
#: letter that is none of them, and two that change length or letter when
#: upper-cased (a dotless i, and a sharp s).
_NEAR_LETTERS = st.text(st.sampled_from("AIXUYaixuyQ\U00000131\U000000df"), max_size=4)


class TestTextProperties(unittest.TestCase):
    """The barred-term screen and the island-letter parser, over any text."""

    @given(_screen_requests())
    @example(_SURROGATE_SCREEN)
    def test_fuzz_screen_excluded(
        self, request: tuple[cw_bank.Bank, frozenset[str]]
    ) -> None:
        """Never raises, and parts the bank into what it keeps and what it drops."""
        bank, terms = request
        screened, dropped = cw_excluded_terms.screen_excluded(bank, terms)
        gone = {answer for answer, _ in dropped}
        self.assertEqual(len(gone), len(dropped))
        self.assertLessEqual(gone, {entry.answer for entry in bank.entries})
        self.assertEqual(
            screened.entries,
            tuple(entry for entry in bank.entries if entry.answer not in gone),
        )
        self.assertEqual(dict(screened.themes), dict(bank.themes))
        for entry in bank.entries:
            # A term that is an entry's written form, in any case, bars it.
            if entry.written.lower() in terms:
                self.assertIn(entry.answer, gone)
        for _, reason in dropped:
            self.assertTrue(reason)

    @given(st.one_of(loader_fixtures.ANY_TEXT, _NEAR_LETTERS))
    @example("")
    @example("aix")
    @example("\U0000d800")
    def test_fuzz_parse_island_letters(self, text: str) -> None:
        """The letters in order, each one an island may hold, or ConfigError naming the flag."""
        try:
            letters = cw_island.parse_island_letters(text)
        except cw_config.ConfigError as exc:
            self.assertIn("--island-letters", str(exc))
            return
        self.assertEqual("".join(letters), text.upper())
        for letter in letters:
            self.assertIn(letter, cw_island.ISLAND_LETTERS)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    unittest.main()
