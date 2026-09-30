"""Grouped suite: property tests for cw_mask's picture parser.

`cw_mask.parse_mask` reads a file an operator drew by hand, so it carries the
`# fuzz-target` marker, paired with `test_fuzz_parse_mask` below. A picture is
structured input with three independent ways to be malformed -- a width, a
character, an emptiness -- which is exactly the shape 100% branch coverage says
nothing about: a few hand-picked pictures can walk every branch and still leave
the parser faulting on the next one.

**Each property re-derives its answer independently** of the subject. How many
rows a text describes is recounted here from a universal-newline text stream,
`str.startswith` and `str.rstrip` rather than read off the `Mask`, and an
accepted picture is rendered back to text and re-read, so the parse is held to
agreeing with itself rather than merely to not raising.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location. The two reach it differently, so the bootstrap below names the
project root and `src/` rather than relying on either.
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_mask  # noqa: E402 - import follows the sys.path bootstrap above

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
    "crossword_mask_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_mask_properties")

#: What a refusal calls the input. Any string does; the parser only quotes it.
_NAME = "shape.txt"

#: Text weighted toward the characters the parser is about -- both marks, the
#: comment prefix, both line ends, a LINE SEPARATOR that ends no line, and the
#: whitespace that is trimmed at one end of a row and refused at the other --
#: because arbitrary Unicode is almost never a well-formed picture, and the
#: accepted branch is the interesting one.
_NEAR_PICTURE = st.text(
    alphabet=cw_mask.FREE + cw_mask.MASKED + "#\n\r\U00002028 \tXx.", max_size=24
)

_ANY_TEXT = st.one_of(_NEAR_PICTURE, st.text(max_size=24))


@st.composite
def _pictures(draw: st.DrawFn) -> str:
    """A rectangular picture of `FREE` and `MASKED`, with a trailing newline.

    Built to be accepted, so the properties about an accepted picture are
    exercised on more than whatever `_ANY_TEXT` stumbles into. Wholly masked
    pictures are drawn too: the parser refuses them, and a property that
    assumed otherwise would be asserting the generator's taste.
    """
    rows = draw(st.integers(min_value=1, max_value=6))
    cols = draw(st.integers(min_value=1, max_value=6))
    marks = st.sampled_from((cw_mask.FREE, cw_mask.MASKED))
    lines = [
        "".join(draw(st.lists(marks, min_size=cols, max_size=cols)))
        for _ in range(rows)
    ]
    return "".join(f"{line}\n" for line in lines)


def _described_rows(text: str) -> int:
    r"""How many grid rows `text` describes, recounted without the subject.

    The lines are those a universal-newline text stream reads, which end at
    `\n`, `\r\n` or a lone `\r`, where an editor ends one. A line is a row
    unless it opens with the comment prefix; a row that is blank once its
    trailing whitespace is gone is not one either, because the parser refuses
    it rather than counting it.
    """
    return sum(
        1
        for line in io.StringIO(text, newline=None)
        if not line.startswith("#") and line.rstrip() != ""
    )


def _picture_of(mask: cw_mask.Mask) -> str:
    """The picture `mask` describes, rendered back to text.

    Sorted by coordinate rather than by iterating `mask.cells`: a frozenset's
    order is `PYTHONHASHSEED`-dependent, and a property that read it would pass
    or fail by seed.
    """
    return "".join(
        "".join(
            cw_mask.MASKED if (row, col) in mask.cells else cw_mask.FREE
            for col in range(mask.cols)
        )
        + "\n"
        for row in range(mask.rows)
    )


class TestParseMaskProperties(unittest.TestCase):
    """What holds of every text, and of every picture the parser accepts."""

    @given(_ANY_TEXT)
    @example("")
    @example("#\n")
    @example("X\n")
    @example(".X\n..\n")
    @example(".\r\n.\r\n")
    @example("#\U00002028.\n.\n")
    def test_fuzz_parse_mask(self, text: str) -> None:
        """Never raises anything but MaskError; an accepted picture is coherent."""
        try:
            mask = cw_mask.parse_mask(text, _NAME)
        except cw_mask.MaskError as exc:
            # A refusal is only useful if it points at the file: every message
            # names it, so an operator knows which picture was rejected.
            self.assertIn(_NAME, str(exc))
            return
        self.assertEqual(mask.rows, _described_rows(text))
        self.assertGreaterEqual(mask.rows, 1)
        self.assertGreaterEqual(mask.cols, 1)
        for row, col in sorted(mask.cells):
            self.assertTrue(0 <= row < mask.rows, (row, col))
            self.assertTrue(0 <= col < mask.cols, (row, col))
        # Strictly fewer, never equal: the wholly-masked picture is refused.
        self.assertLess(len(mask.cells), mask.rows * mask.cols)

    @given(_ANY_TEXT)
    def test_an_accepted_picture_reads_back_as_itself(self, text: str) -> None:
        """Rendering an accepted mask and re-reading it gives the same mask."""
        try:
            mask = cw_mask.parse_mask(text, _NAME)
        except cw_mask.MaskError:
            return
        self.assertEqual(cw_mask.parse_mask(_picture_of(mask), _NAME), mask)

    @given(_pictures())
    def test_a_rectangular_picture_is_accepted_unless_it_masks_everything(
        self, text: str
    ) -> None:
        """The only refusal a well-formed rectangle can earn is masking every cell."""
        lines = text.splitlines()
        if all(char == cw_mask.MASKED for line in lines for char in line):
            with self.assertRaises(cw_mask.MaskError):
                cw_mask.parse_mask(text, _NAME)
            return
        mask = cw_mask.parse_mask(text, _NAME)
        self.assertEqual((mask.rows, mask.cols), (len(lines), len(lines[0])))
        self.assertEqual(
            mask.cells,
            frozenset(
                (row, col)
                for row, line in enumerate(lines)
                for col, char in enumerate(line)
                if char == cw_mask.MASKED
            ),
        )

    @given(_pictures(), st.text(alphabet="abc ", min_size=1, max_size=4))
    def test_a_comment_line_never_changes_the_picture(
        self, text: str, note: str
    ) -> None:
        """Prefixing an annotation leaves the mask the bare picture gives."""
        try:
            bare = cw_mask.parse_mask(text, _NAME)
        except cw_mask.MaskError:
            return
        self.assertEqual(cw_mask.parse_mask(f"#{note}\n{text}", _NAME), bare)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    unittest.main()
