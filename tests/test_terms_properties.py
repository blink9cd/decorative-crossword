"""Grouped suite: an excluded-terms file, read and then applied, held to an oracle.

`cw_excluded_terms.load_excluded_terms` reads a list the operator wrote by
hand. `test_loader_properties.py` holds it to returning or refusing and
nothing else; this holds the terms it returns to the lines re-derived here, and
follows them on into `cw_excluded_terms.screen_excluded`, the only thing they
are for. The draw is the whole
file: bytes that are not UTF-8, a byte-order mark, every line ending an editor
uses and the characters that end a line only for `str.splitlines`, comments,
blank lines, and terms that name answers of the bank they screen.

The property, re-derived where it can be: a file reads as terms or as a
`BankError` naming it, and is refused exactly when its bytes are not UTF-8 or
open with a byte-order mark; the terms are exactly its editor lines that are
neither blank nor a comment, each stripped and lower-cased; and screening never
raises, keeps and drops every entry exactly once between them, drops only for
a term it names, and drops every entry whose answer is itself a term.

Run through test_decorative_crossword.py's `load_tests` hook, or imported by
location by a campaign runner, which is why the bootstrap below names the
project root and `src/` itself.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_excluded_terms  # noqa: E402 - same bootstrap
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
    "crossword_terms_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_terms_properties")

#: The bank every drawn list screens: plain, spaced and hyphenated answers,
#: and a clue a term can match on its own.
_BANK = cw_bank.parse_bank(
    {
        "themes": {},
        "entries": [
            {"answer": "CAT", "clue": "Sleeps on the keyboard"},
            {"answer": "HELLO THERE"},
            {"answer": "ATTA-BOY"},
            {"answer": "OWL"},
        ],
    }
)

#: Terms that name something in `_BANK`, so drawn lists often drop an entry.
_NAMING = ("cat", "CAT", "there", "hello-there", "atta boy", "keyboard", "owl")

#: Any character, surrogates included, or one a line of a list is about. A
#: lone surrogate is sampled as well, because a draw of any character almost
#: never makes one, and it is how a list reaches its file as bytes that are
#: not UTF-8 although every other character in it is text.
_CHARACTER = st.one_of(
    st.characters(exclude_categories=()),
    st.sampled_from(
        ("#", " ", "\t", "\x0c", "\x85", "\U00002028", "\U0000feff", "\U0000dc80")
    ),
)

_LINE = st.one_of(
    st.sampled_from(_NAMING), st.lists(_CHARACTER, max_size=8).map("".join)
)

#: A list's text: lines, each closed by an ending an editor makes.
_LIST = loader_fixtures.line_lists(_LINE)

#: A file: the list as saved, or with a mark before it, or any bytes at all.
_FILE = loader_fixtures.input_files(_LIST)


class TestAnExcludedTermsFile(unittest.TestCase):
    """Any file reads as terms or a refusal, and screening with them never fails."""

    @given(_FILE)
    @example(b"cat\n")
    @example(b"  # a note\n\nowl\r\nzzz\xe2\x80\xa8there\n")
    # A last line with no ending after it is still a term.
    @example(b"OWL\r\n\tthere")
    @example(b"\xef\xbb\xbfcat\n")
    # A list saved with a lone surrogate in a line, as bytes that are not UTF-8.
    @example(b"cat\n\xed\xb2\x80\n")
    def test_fuzz_load_excluded_terms(self, data: bytes) -> None:
        """The terms its editor lines list, and a screen that partitions the bank."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "excluded.txt"
            path.write_bytes(data)
            try:
                terms = cw_excluded_terms.load_excluded_terms(path)
            except cw_bank.BankError as exc:
                self.assertIn(str(path), str(exc))
                self.assertFalse(loader_fixtures.readable(data))
                return
        self.assertTrue(loader_fixtures.readable(data))
        listed = loader_fixtures.listed_lines(data)
        self.assertEqual(terms, frozenset(line.lower() for line in listed))
        kept, dropped = cw_excluded_terms.screen_excluded(_BANK, terms)
        answers = [entry.answer for entry in _BANK.entries]
        dropped_answers = [answer for answer, _ in dropped]
        self.assertEqual(
            sorted([entry.answer for entry in kept.entries] + dropped_answers),
            sorted(answers),
        )
        for _, reason in dropped:
            self.assertTrue(any(reason.endswith(f"{term!r}") for term in terms))
        for answer in answers:
            if answer.lower() in terms:
                self.assertIn(answer, dropped_answers)


if __name__ == "__main__":
    unittest.main()
