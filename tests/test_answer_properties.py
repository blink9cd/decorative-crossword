"""Grouped suite: property tests for cw_answer's normalization and spelling rule.

`cw_answer.grid_form` is applied to every answer an operator types -- bank
answers, `--feature`, `--prefer`, `--phrases` lines and `--excluded-terms` --
and `cw_answer.is_spelling` reads the bank's untrusted answers, so both carry
the `# fuzz-target` marker, paired with `test_fuzz_grid_form` and
`test_fuzz_is_spelling` below.

**Each property re-derives its answer independently** of the subject: what
`grid_form` keeps is recomputed character by character with `str.isspace`, and
what an accepted spelling must look like is checked as plain invariants rather
than with a second regex. A spelling built word by word must be accepted, and
one with a character no answer may hold must not, so the rule is held from both
sides rather than only against what it happens to accept.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location. The two reach it differently, so the bootstrap below names the
project root and `src/` rather than relying on either.
"""

from __future__ import annotations

import re
import string
import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_answer  # noqa: E402 - import follows the sys.path bootstrap above

# A registered profile loaded at import under this module's own name, never an
# `@settings` decorator, which would pin the property's settings where no
# campaign runner could re-stamp them. Derandomized so the in-suite run is
# reproducible; no deadline, because a per-example wall clock measures machine
# load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_answer_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_answer_properties")

#: The characters `grid_form` removes besides whitespace.
_JOINERS = "-'"

#: The two characters that separate words, and so split an enumeration.
_WORD_BREAKS = " -"

#: Text weighted toward the characters the rule is about -- letters of both
#: cases, both word breaks, the apostrophe, a tab, and a few it refuses --
#: because arbitrary Unicode almost never holds a well-formed spelling.
_NEAR_SPELLING = st.text(
    alphabet="ABCXYZ"
    + "ab"
    + _WORD_BREAKS
    + "'"
    + "\t.&\N{RIGHT SINGLE QUOTATION MARK}",
    max_size=12,
)

_ANY_TEXT = st.one_of(_NEAR_SPELLING, st.text(max_size=12))

#: One run of capital letters: the piece `_words` joins with apostrophes.
_LETTERS = st.text(alphabet=string.ascii_uppercase, min_size=1, max_size=5)


@st.composite
def _words(draw: st.DrawFn) -> str:
    """One written word: letter runs joined by apostrophes, with optional ends."""
    runs = draw(st.lists(_LETTERS, min_size=1, max_size=3))
    opening = draw(st.sampled_from(("", "'")))
    closing = draw(st.sampled_from(("", "'")))
    return opening + "'".join(runs) + closing


@st.composite
def _spellings(draw: st.DrawFn) -> str:
    """A whole written answer: words joined by one space or one hyphen each."""
    words = draw(st.lists(_words(), min_size=1, max_size=4))
    breaks = draw(
        st.lists(
            st.sampled_from(_WORD_BREAKS),
            min_size=len(words) - 1,
            max_size=len(words) - 1,
        )
    )
    spelled = words[0]
    for word_break, word in zip(breaks, words[1:], strict=True):
        spelled += word_break + word
    return spelled


#: A character no written answer may hold anywhere.
_FORBIDDEN = st.sampled_from(
    ("a", "7", ".", "&", "\t", "\N{RIGHT SINGLE QUOTATION MARK}")
)


def _enumeration_lengths(enumeration: str) -> list[int]:
    """The word lengths an enumeration like `(4-1,7)` lists, in order."""
    return [int(part) for part in re.findall(r"\d+", enumeration)]


class TestGridFormProperties(unittest.TestCase):
    """`grid_form` removes exactly whitespace, hyphens and apostrophes."""

    @given(_ANY_TEXT)
    @example("JACK-O'-LANTERN")
    @example("web\tsite")
    def test_fuzz_grid_form(self, text: str) -> None:
        """Every other character survives in order, and a second pass changes nothing."""
        closed = cw_answer.grid_form(text)
        kept = "".join(
            char for char in text if not char.isspace() and char not in _JOINERS
        )
        self.assertEqual(closed, kept)
        self.assertEqual(cw_answer.grid_form(closed), closed)


class TestIsSpellingProperties(unittest.TestCase):
    """`is_spelling` accepts what may be written, and nothing else."""

    @given(_ANY_TEXT)
    @example("ROCK 'N' ROLL")
    @example("O''CLOCK")
    def test_fuzz_is_spelling(self, text: str) -> None:
        """Never raises; an accepted text closes up to A-Z and enumerates its letters."""
        if not cw_answer.is_spelling(text):
            return
        letters = cw_answer.grid_form(text)
        self.assertTrue(letters)
        self.assertTrue(all("A" <= char <= "Z" for char in letters), repr(text))
        self.assertNotIn(text[0], _WORD_BREAKS)
        self.assertNotIn(text[-1], _WORD_BREAKS)
        self.assertNotIn("''", text)
        for first, second in zip(text, text[1:], strict=False):
            self.assertFalse(first in _WORD_BREAKS and second in _WORD_BREAKS, text)
        self._assert_enumeration_counts(text, letters)

    def _assert_enumeration_counts(self, text: str, letters: str) -> None:
        """An enumeration lists one length per word, summing to the letters."""
        enumeration = cw_answer.enumeration(text)
        breaks = sum(text.count(char) for char in _WORD_BREAKS)
        if breaks == 0:
            self.assertIsNone(enumeration)
            return
        assert enumeration is not None  # narrowed for mypy; a None fails below
        lengths = _enumeration_lengths(enumeration)
        self.assertEqual(len(lengths), breaks + 1)
        self.assertEqual(sum(lengths), len(letters))

    @given(_spellings())
    def test_a_spelling_built_word_by_word_is_accepted(self, spelled: str) -> None:
        self.assertTrue(cw_answer.is_spelling(spelled), repr(spelled))
        self._assert_enumeration_counts(spelled, cw_answer.grid_form(spelled))

    @given(_spellings(), _FORBIDDEN, st.integers(min_value=0))
    def test_a_forbidden_character_anywhere_is_refused(
        self, spelled: str, forbidden: str, position: int
    ) -> None:
        at = position % (len(spelled) + 1)
        self.assertFalse(cw_answer.is_spelling(spelled[:at] + forbidden + spelled[at:]))

    @given(_spellings(), st.sampled_from(_WORD_BREAKS))
    def test_a_word_break_at_either_end_is_refused(
        self, spelled: str, word_break: str
    ) -> None:
        self.assertFalse(cw_answer.is_spelling(word_break + spelled))
        self.assertFalse(cw_answer.is_spelling(spelled + word_break))


if __name__ == "__main__":
    unittest.main()
