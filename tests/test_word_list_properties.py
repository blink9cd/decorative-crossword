"""Grouped suite: what reading a word or phrase list returns, held to an oracle.

`cw_shade.load_word_list` reads every `--words` and `--phrases` list, lists no
one may have curated. `test_loader_properties.py` holds it to returning or
refusing and nothing else; this holds what it returns to the lines re-derived
here, whatever the file holds. The draw is the whole file: bytes that are
not UTF-8, a byte-order mark, every line ending an editor uses and those it
does not, comments, blank lines, spaces, hyphens and apostrophes -- read both
as words and, closed up, as phrases.

The property, with the line split and the closing up re-derived here: a file
reads, or is refused naming it exactly when its bytes are not UTF-8 or open
with a byte-order mark; every usable word is A-Z, at least the shortest run,
and listed once; and every line that is neither blank nor a comment is
accounted for, usable or skipped with the reason it fails, so nothing is
dropped quietly.

Run through test_decorative_crossword.py's `load_tests` hook, or imported by
location by a campaign runner, which is why the bootstrap below names the
project root and `src/` itself.
"""

from __future__ import annotations

import string
import sys
import tempfile
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_grid  # noqa: E402 - import follows the sys.path bootstrap above
import cw_shade  # noqa: E402 - same bootstrap
from tests import loader_fixtures  # noqa: E402 - same bootstrap

# A registered profile loaded at import, never an `@settings` decorator, which
# would pin the property's settings where no campaign runner could re-stamp
# them. Derandomized so the in-suite run is reproducible; no deadline, because
# a per-example wall clock measures machine load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_word_list_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_word_list_properties")

#: Letters, and every other character a line of a list is about. A lone
#: surrogate is sampled as well, because a draw of any character almost never
#: makes one, and it is how a list reaches its file as bytes that are not
#: UTF-8 although every other character in it is text.
_CHARACTER = st.one_of(
    st.sampled_from("CATcat"),
    st.sampled_from(
        ("#", " ", "-", "'", "\t", "\x0c", "\x85", "\U00002028", "\U0000dc80")
    ),
    st.characters(exclude_categories=()),
)

#: A list's text: lines, each closed by a line ending an editor makes.
_LIST = loader_fixtures.line_lists(st.lists(_CHARACTER, max_size=8).map("".join))

#: A file: the list as saved, or with a mark before it, or any bytes at all.
_FILE = loader_fixtures.input_files(_LIST)

#: What a usable word is spelled in.
_LETTERS = frozenset(string.ascii_uppercase)

#: Why a line is skipped: too short, checked first, or not spelled in A-Z.
_TOO_SHORT = f"shorter than the {cw_grid.MIN_RUN}-letter minimum"
_NOT_LETTERS = "holds a character outside A-Z"


#: What closes up in a phrase besides whitespace: a hyphen joins two words,
#: and an apostrophe sits inside one.
_JOINERS = frozenset("-'")


def _closed_up(line: str) -> str:
    """`line` as a phrase is read: its whitespace, hyphens and apostrophes gone."""
    return "".join(char for char in line if not char.isspace() and char not in _JOINERS)


def _skip_reason(line: str) -> str | None:
    """Why a read line is no usable word, or None when it is one."""
    if len(line) < cw_grid.MIN_RUN:
        return _TOO_SHORT
    if not set(line) <= _LETTERS:
        return _NOT_LETTERS
    return None


class TestReadingAWordList(unittest.TestCase):
    """Any file reads as words and skipped lines, or a refusal naming it."""

    @given(_FILE, st.booleans())
    @example(b"CAT\n# note\n\ncat\r\nC\rCAT DOG\n", False)
    @example(b"atta-boy\nhello there\n", True)
    # An apostrophe and a tab close up in a phrase as a hyphen and a space do.
    @example(b"o'clock\ntwo\tstep\n", True)
    @example(b"LAN\xe2\x80\xa8TERN\n", False)
    # A last line with no ending after it is still read.
    @example(b"OWL\nEMU", False)
    @example(b"\xef\xbb\xbfCAT\n", False)
    def test_fuzz_load_word_list(self, data: bytes, close_up: bool) -> None:
        """Every listed line is a usable word or a skip with its reason."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "words.txt"
            path.write_bytes(data)
            try:
                words, skipped = cw_shade.load_word_list(path, close_up=close_up)
            except cw_shade.ShadeError as exc:
                self.assertIn(str(path), str(exc))
                self.assertFalse(loader_fixtures.readable(data))
                return
        self.assertTrue(loader_fixtures.readable(data))
        read = [
            (_closed_up(line) if close_up else line).upper()
            for line in loader_fixtures.listed_lines(data)
        ]
        usable = [line for line in read if _skip_reason(line) is None]
        self.assertEqual(list(words), list(dict.fromkeys(usable)))
        self.assertEqual(
            list(skipped),
            [(line, _skip_reason(line)) for line in read if _skip_reason(line)],
        )


if __name__ == "__main__":
    unittest.main()
