"""Grouped suite: what reading a `--mask` file returns, held to an oracle, whatever its bytes hold.

`cw_mask.load_mask` is the one reader of a `--mask` file, for `fill` and
`gaps` alike. `test_loader_properties.py` holds it to returning or refusing and
nothing else, and `test_mask_properties.py` holds the picture parser to its
contract over text; this holds the file around the parser: bytes that are not
UTF-8, a byte-order mark, and every line ending an editor uses.

The property: a file reads as a mask or as a `MaskError` naming it, and a file
reads as its own text does -- the same mask `parse_mask` makes of the decoded
bytes, and, when its bytes are UTF-8 with no byte-order mark, a refusal only
where `parse_mask` refuses that text too -- so reading a file adds nothing to
the picture and takes nothing from it. An accepted mask is also the one drawn
by the text's editor lines, re-derived here: each line that is not a comment,
its trailing whitespace trimmed, is one row, and each `MASKED` in it one
masked cell.

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

import cw_mask  # noqa: E402 - import follows the sys.path bootstrap above
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
    "crossword_mask_file_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_mask_file_properties")

#: Text weighted toward a picture -- both marks, the comment prefix, the line
#: ends an editor makes and those it does not -- because arbitrary text is
#: almost never one, and a mask that reads is the interesting case.
_NEAR_PICTURE = st.text(
    alphabet=st.sampled_from(
        (
            cw_mask.FREE,
            cw_mask.MASKED,
            "#",
            " ",
            "\n",
            "\r",
            "\x0c",
            "\x85",
            "\U00002028",
        )
    ),
    max_size=24,
)

#: A file: a picture as saved, or with a mark before it, or any bytes at all.
_FILE = loader_fixtures.input_files(_NEAR_PICTURE)


def _drawn_mask(data: bytes) -> cw_mask.Mask:
    """The mask the editor lines of an accepted file draw, re-derived here.

    A line that is blank once its trailing whitespace is gone is no row: in a
    file that reads, the only such line is the empty one after a final line
    ending, since the parser refuses any other.
    """
    lines = loader_fixtures.editor_lines(data.decode("utf-8"))
    rows = [
        line.rstrip() for line in lines if not line.startswith("#") and line.rstrip()
    ]
    return cw_mask.Mask(
        rows=len(rows),
        cols=len(rows[0]),
        cells=frozenset(
            (row, col)
            for row, marks in enumerate(rows)
            for col, mark in enumerate(marks)
            if mark == cw_mask.MASKED
        ),
    )


class TestReadingAMaskFile(unittest.TestCase):
    """Any file reads as the mask its text draws, or a refusal naming it."""

    @given(_FILE)
    @example(b".X\r\n..\r\n")
    @example(b".X\r..\r")
    @example(b"# a heart\xe2\x80\xa8outline\n.X\n..\n")
    # A last row with no ending after it is still a row.
    @example(b"X.\n.X")
    @example(b"\xef\xbb\xbf.X\n..\n")
    # A blank line at either end of the file is refused, as the parser refuses
    # it: reading a file must not trim what its text holds.
    @example(b"\n.X\n..\n")
    @example(b".X\n..\n \n")
    # A picture saved with a lone surrogate in it, as bytes that are not UTF-8:
    # the alphabet above draws none.
    @example(b".X\n\xed\xb2\x80\n")
    def test_fuzz_load_mask(self, data: bytes) -> None:
        """The mask its decoded text draws, or a refusal naming the file."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shape.txt"
            path.write_bytes(data)
            try:
                mask = cw_mask.load_mask(path)
            except cw_mask.MaskError as exc:
                self.assertIn(str(path), str(exc))
                # A file every reader must read is refused only for what its
                # text draws, which the parser alone refuses as well.
                if loader_fixtures.readable(data):
                    with self.assertRaises(cw_mask.MaskError):
                        cw_mask.parse_mask(data.decode("utf-8"), str(path))
                return
        self.assertTrue(loader_fixtures.readable(data))
        self.assertEqual(mask, cw_mask.parse_mask(data.decode("utf-8"), str(path)))
        self.assertEqual(mask, _drawn_mask(data))


if __name__ == "__main__":
    unittest.main()
