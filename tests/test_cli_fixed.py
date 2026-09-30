"""Grouped suite: `fill --source --preview` draws the source's letters in bold.

Only `fill` knows which letters it was handed: a finished `grid_source.json`
records none of it, so a later `preview` of that file cannot mark them and
does not guess. These cases drive `main` end to end, because the claim is about
the file a real run writes, and they read that SVG back as a document.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cw_grid
import cw_svg
import cw_svg_style
import decorative_crossword
from tests import cli_fixtures, svg_fixtures

#: One blank row of a 9-wide source.
_BLANK = "." * 9

#: ALPHA across row 4 of a 9x9, and nothing else: room on every side to grow.
_ALPHA_ROW = [_BLANK] * 4 + ["..ALPHA.."] + [_BLANK] * 4

#: What `--source` is saved as, beside the workspace's own `--out`.
_SOURCE_NAME = "source.json"


def _letters(rows: list[str]) -> dict[tuple[int, int], str]:
    """Every lettered cell of `rows`, keyed by (row, column)."""
    return {
        (row, col): char
        for row, line in enumerate(rows)
        for col, char in enumerate(line)
        if char != cw_grid.BLOCK
    }


def _source_fill(space: cli_fixtures.Workspace) -> list[str]:
    """A `fill` from `_ALPHA_ROW` with a preview: the workspace's argv, sized by the source."""
    source = space.root / _SOURCE_NAME
    source.write_text(
        json.dumps({"rows": _ALPHA_ROW, "themes": {}, "clues": {}}),
        encoding="utf-8",
        newline="\n",
    )
    argv = space.fill("--source", str(source), "--preview", str(space.svg))
    for flag in ("--rows", "--cols"):
        at = argv.index(flag)
        del argv[at : at + 2]
    return argv


class TestFillMarksItsSource(cli_fixtures.QuietCase):
    """The preview a source fill writes marks exactly the source's letters."""

    def test_the_source_letters_are_bold_and_the_filled_in_letters_are_not(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(decorative_crossword.main(_source_fill(space)), 0)
            rendered = space.svg.read_text(encoding="utf-8")
            written = _letters(space.rows())
            fixed = svg_fixtures.letter_cells(rendered, cw_svg_style.FIXED_LETTER_LAYER)
            plain = svg_fixtures.letter_cells(rendered, cw_svg.LETTER_LAYER)
        self.assertEqual(fixed, _letters(_ALPHA_ROW))
        # The fill must actually have grown, or "not marked" is vacuous.
        self.assertTrue(plain)
        self.assertEqual({**plain, **fixed}, written)
        self.assertIn(
            "Fixed from --source: 5 letter(s), in bold",
            svg_fixtures.caption_lines(rendered),
        )

    def test_a_fill_without_a_source_marks_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.svg))
            self.assertEqual(decorative_crossword.main(argv), 0)
            rendered = space.svg.read_text(encoding="utf-8")
        self.assertNotIn(cw_svg_style.FIXED_LETTER_LAYER, rendered)

    def test_a_later_preview_of_the_written_grid_marks_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(decorative_crossword.main(_source_fill(space)), 0)
            redrawn = Path(folder) / "redrawn.svg"
            argv = ["preview", "--source", str(space.out), "--out", str(redrawn)]
            self.assertEqual(decorative_crossword.main(argv), 0)
            rendered = redrawn.read_text(encoding="utf-8")
        self.assertNotIn(cw_svg_style.FIXED_LETTER_LAYER, rendered)


if __name__ == "__main__":
    unittest.main()
