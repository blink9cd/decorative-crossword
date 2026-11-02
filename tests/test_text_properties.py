"""Grouped suite: property test for how a refusal quotes a value, `cw_text.shown`.

Whatever the value (text holding any character, surrogates included, a
whole number, a float that is NaN or infinite, or lists and objects of them
nested a few deep), its quote is never longer than the cap plus a short
suffix naming the full length. And a value whose repr fits the cap is quoted
exactly as `repr` writes it, which is what keeps every refusal about a short
value word for word what it was before quotes were capped.

The text is drawn up to half again longer than the cap, so the draw lands on
both sides of it, and the examples pin the two lengths either side of the edge.

Run through test_decorative_crossword.py's `load_tests` hook, or on its own,
which is why the bootstrap below names `src/` rather than relying on the
aggregator having done so.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_text  # noqa: E402 - import follows the sys.path bootstrap above

# A registered profile loaded at import, never an `@settings` decorator, which
# would pin the property's settings where no campaign runner could re-stamp
# them. Derandomized so the in-suite run is reproducible; no deadline, because
# a per-example wall clock measures machine load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_text_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_text_properties")

#: The most a cut quote may run past the cap: `... (`, the full length's
#: digits and ` characters)`. The words take seventeen characters, which
#: leaves room for a length of fifteen digits, far past any value drawn here.
_SUFFIX_ALLOWANCE = 32

#: The longest text drawn: half again the cap, so draws fall either side of it.
_LONGEST_TEXT = 300

#: Any character at all, the surrogates included, which a plain text strategy
#: never draws.
_TEXT = st.text(alphabet=st.characters(exclude_categories=()), max_size=_LONGEST_TEXT)

#: A JSON-shaped scalar, plus NaN and the infinities `st.floats` draws.
_SCALAR = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), _TEXT)

#: A scalar, or lists and objects of them nested a few deep.
_VALUE = st.recursive(
    _SCALAR,
    lambda inner: st.one_of(
        st.lists(inner, max_size=20), st.dictionaries(_TEXT, inner, max_size=8)
    ),
    max_leaves=40,
)


class TestQuotedValueProperties(unittest.TestCase):
    """`shown` is capped, and a value whose repr fits is quoted as `repr` writes it."""

    @given(_VALUE)
    @example("x" * 198)
    @example("x" * 199)
    def test_a_quote_is_capped_and_a_short_one_is_the_repr(self, value: object) -> None:
        quoted = cw_text.shown(value)
        whole = repr(value)
        self.assertLessEqual(len(quoted), cw_text.SHOWN_MAX_CHARS + _SUFFIX_ALLOWANCE)
        if len(whole) <= cw_text.SHOWN_MAX_CHARS:
            self.assertEqual(quoted, whole)
        else:
            self.assertTrue(quoted.startswith(whole[: cw_text.SHOWN_MAX_CHARS]))


if __name__ == "__main__":
    unittest.main()
