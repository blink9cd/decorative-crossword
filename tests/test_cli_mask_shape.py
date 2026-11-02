"""Grouped suite: a real fill under a mask writes no letter the picture forbids.

The claim the whole feature rests on, checked on the written grid rather than on
anything the search reports about itself. A mask consulted in `cw_place.fits` but
missed in `crossing_candidates` (the two are parallel predicates, not one choke
point) still returns a grid with letters where the operator drew none, and only
reading the file catches that.

The pictures here are shapes rather than single cells, deliberately. One masked
cell can be missed by a seam and still leave a grid that looks plausible; a
silhouette cannot, because the search has to route every crossing around it.

A sibling file rather than a section of `test_cli_mask.py`, which owns the
command line: exit codes, sizes, refused files. This one owns the search.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest

import cw_mask
import decorative_crossword
from tests import cli_fixtures

#: A 9x9 picture masking the four corners, matching `Workspace.fill`'s grid.
_CORNERS = (
    "X.......X",
    ".........",
    ".........",
    ".........",
    ".........",
    ".........",
    ".........",
    ".........",
    "X.......X",
)

#: A 9x9 diamond: every cell outside it is forbidden, so the fill has to route
#: its whole shape through the middle. The strongest picture the default bank
#: can still fill, and the one a half-wired seam fails on.
_DIAMOND = (
    "XXXX.XXXX",
    "XXX...XXX",
    "XX.....XX",
    "X.......X",
    ".........",
    "X.......X",
    "XX.....XX",
    "XXX...XXX",
    "XXXX.XXXX",
)


def _masked_cells(picture: tuple[str, ...]) -> frozenset[tuple[int, int]]:
    """The cells `picture` forbids, read the way the parser reads them.

    Through `cw_mask.parse_mask` rather than by re-scanning the strings here: a
    second reader of the picture format in the tests is a second thing that can
    disagree with the tool about what the operator drew.
    """
    text = "".join(f"{row}\n" for row in picture)
    return cw_mask.parse_mask(text, "fixture").cells


class TestShapedFill(cli_fixtures.QuietCase):
    """The written grid honors the picture, and is still a real grid."""

    def _filled(self, picture: tuple[str, ...]) -> tuple[int, list[str]]:
        """Fill under `picture`; return the exit code and the written rows."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            code = decorative_crossword.main(
                space.fill("--mask", str(space.mask(*picture)))
            )
            return code, space.rows()

    def test_no_masked_cell_holds_a_letter_under_a_corner_mask(self) -> None:
        code, rows = self._filled(_CORNERS)
        self.assertEqual(code, 0)
        for row, col in sorted(_masked_cells(_CORNERS)):
            self.assertEqual(rows[row][col], ".", f"cell {row},{col}")

    def test_no_masked_cell_holds_a_letter_under_a_diamond(self) -> None:
        code, rows = self._filled(_DIAMOND)
        self.assertEqual(code, 0)
        for row, col in sorted(_masked_cells(_DIAMOND)):
            self.assertEqual(rows[row][col], ".", f"cell {row},{col}")

    def test_the_diamond_is_still_filled_inside(self) -> None:
        # The other side of every guard above. A seam that refused every
        # placement, or a mask read as forbidding the whole grid, passes both
        # tests above and fails this one.
        _, rows = self._filled(_DIAMOND)
        letters = sum(1 for row in rows for cell in row if cell != ".")
        self.assertGreater(letters, 1)

    def test_an_unmasked_fill_of_the_same_request_is_unchanged(self) -> None:
        # The mask must cost nothing where it forbids nothing: under an all-open
        # picture, the same seed, bank and size write exactly the grid a run
        # without the flag writes. This pins the result; whether a change leaves
        # the walk itself unchanged is a separate walk-comparison harness's to
        # prove; it is not shipped here.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            bare = space.rows()
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            open_picture = space.mask(*(("." * 9,) * 9))
            decorative_crossword.main(space.fill("--mask", str(open_picture)))
            wide_open = space.rows()
        self.assertEqual(bare, wide_open)


if __name__ == "__main__":
    unittest.main()
