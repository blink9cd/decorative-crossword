"""Grouped suite: a property test for `--feature`'s value grammar.

`cw_feature.parse_feature` turns one command-line string (`ANSWER`, or
`ANSWER@ROW,COL,DIR`) into the typed pin the search starts from, and it is
the only place that string is read. The example tests in `test_feature.py` pin
each malformed shape somebody thought to write down; they say nothing about the
strings nobody did. This property does: whatever text arrives, the parser
returns a well-formed `Feature` or raises `ConfigError` and nothing else, and
what it returns survives being written back out in canonical form and read
again.

A file of its own because each `# fuzz-target` parser's `test_fuzz_<name>`
property lives in a sibling `*_properties.py` module, and `test_properties.py`
is scoped to `cw_bank`'s boundary.

Entry point assumptions: the same callers `test_properties.py` documents
(the aggregator's loader, and a fuzzing campaign importing by location), so
the same bootstrap, for the same reason.
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

import cw_answer  # noqa: E402 - import follows the sys.path bootstrap above
import cw_config  # noqa: E402 - same bootstrap
import cw_feature  # noqa: E402 - same bootstrap
import cw_grid  # noqa: E402 - same bootstrap

# The registered-profile convention `test_properties.py` explains: a decorator
# would stop a campaign runner re-stamping the property's settings, and
# `derandomize=True` keeps the in-suite run reproducible.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_feature_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_feature_properties")

#: Characters the grammar is built from, plus the near misses a hand-typed pin
#: carries: case, a sign, a space, and a non-ASCII digit `int()` would accept.
_ALPHABET = "ACHKLacdnorsw@,0123456789-+ ٣"

#: Free text over that alphabet. Mostly malformed, which is the point.
_FREE_TEXT = st.text(alphabet=_ALPHABET, max_size=24)

#: A coordinate that is sometimes a plain index and sometimes one of the
#: spellings the grammar refuses.
_COORDINATE = st.one_of(
    st.integers(min_value=0, max_value=30).map(str),
    st.sampled_from(("", "-1", "+1", " 2", "01", "٣", "x")),
)

#: A pin-shaped string, so the draw reaches the per-part branches that free
#: text lands on only by accident.
_PIN_SHAPED = st.builds(
    lambda answer, row, col, direction: f"{answer}@{row},{col},{direction}",
    st.sampled_from(("CHALK", "AB", "", "chalk")),
    _COORDINATE,
    _COORDINATE,
    st.sampled_from((cw_grid.ACROSS, cw_grid.DOWN, "ACROSS", "diagonal", "")),
)


class TestParseFeatureProperties(unittest.TestCase):
    """`parse_feature` returns a well-formed pin or refuses, for any text."""

    @given(st.one_of(_FREE_TEXT, _PIN_SHAPED))
    @example("CHALK")
    @example("CHALK@2,3,down")
    @example("CHALK@0,0")
    @example("CHALK@0,0,diagonal")
    @example("CHALK@x,0,across")
    @example("@0,0,across")
    @example("CHALK@1,1,down@2,2,down")
    @example("CHALK@" + "1" * 5000 + ",0,down")
    @example("ATTA-BOY@0,0,across")
    @example(" - ")
    def test_fuzz_parse_feature(self, text: str) -> None:
        """Every string yields a Feature or a ConfigError, and a Feature round-trips.

        The try/except is the crash-freedom half: any exception other than
        ConfigError escapes it and fails the test. The assertions after it are
        the half that catches a parser which accepts what it should not (a
        negative index, a direction the search cannot step along), which
        "returns or raises" alone would wave through.
        """
        try:
            feature = cw_feature.parse_feature(text)
        except cw_config.ConfigError:
            return

        self.assertTrue(feature.answer)
        self.assertNotIn("@", feature.answer)
        if feature.anchor is None:
            # Verbatim but closed up: `ATTA-BOY` names the grid's `ATTABOY`.
            self.assertEqual(feature.answer, cw_answer.grid_form(text))
            return
        anchor = feature.anchor
        self.assertGreaterEqual(anchor.row, 0)
        self.assertGreaterEqual(anchor.col, 0)
        self.assertIn(anchor.direction, (cw_grid.ACROSS, cw_grid.DOWN))
        canonical = f"{feature.answer}@{anchor.row},{anchor.col},{anchor.direction}"
        self.assertEqual(cw_feature.parse_feature(canonical), feature)


if __name__ == "__main__":
    unittest.main()
