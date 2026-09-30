"""Grouped suite: what `--island-letters` reads its text as, held to an oracle.

`cw_island.parse_island_letters` reads a flag's value as the operator typed it,
case-folded. `test_loader_properties.py` holds it to returning or refusing and
nothing else; this holds it to accepting exactly the valid text, and to the
letters re-derived here. The draw is any text at all --
surrogates included, which is how a command line's undecodable bytes arrive --
weighted toward the five island letters in both cases.

The property, re-derived here: text reads as letters or as a `ConfigError`
naming the flag; letters come back exactly when every character of the text,
upper-cased, is an island letter, and they are those characters in the order
typed.

Run through test_decorative_crossword.py's `load_tests` hook, or imported by
location by a campaign runner, which is why the bootstrap below names the
project root and `src/` itself.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_config  # noqa: E402 - import follows the sys.path bootstrap above
import cw_island  # noqa: E402 - same bootstrap

# A registered profile loaded at import, never an `@settings` decorator, which
# would pin the property's settings where no campaign runner could re-stamp
# them. Derandomized so the in-suite run is reproducible; no deadline, because
# a per-example wall clock measures machine load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_island_letters_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_island_letters_properties")

#: The island letters in both cases, or any character at all.
_CHARACTER = st.one_of(
    st.sampled_from("AIXUYaixuy"), st.characters(exclude_categories=())
)

#: The letters an island may hold, spelled out rather than read from the subject.
_ISLAND = frozenset("AIXUY")


class TestIslandLetters(unittest.TestCase):
    """Any text reads as island letters in the order typed, or a refusal."""

    @given(st.lists(_CHARACTER, max_size=6).map("".join))
    @example("")
    @example("aix")
    @example("AIB")
    @example("\U00000131")
    @example("\U0000dc80")
    def test_fuzz_parse_island_letters(self, text: str) -> None:
        """Letters exactly when every upper-cased character is an island letter."""
        try:
            letters = cw_island.parse_island_letters(text)
        except cw_config.ConfigError as exc:
            self.assertIn("--island-letters", str(exc))
            self.assertFalse(text.upper() and set(text.upper()) <= _ISLAND)
            return
        self.assertTrue(letters)
        self.assertLessEqual(set(letters), _ISLAND)
        self.assertEqual(letters, tuple(text.upper()))


if __name__ == "__main__":
    unittest.main()
