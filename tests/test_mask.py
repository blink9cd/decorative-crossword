"""Tests for cw_mask: reading a shape picture, and every refusal it can make."""

import tempfile
import unittest
from pathlib import Path

import cw_grid
import cw_mask


def _written(folder: str, text: str) -> Path:
    """Write `text` as a mask file in `folder` and return its path.

    `newline="\\n"` because the picture's line endings are what the reader
    splits on, so a host that translated them would make the fixture a
    different file per machine.
    """
    path = Path(folder) / "shape.txt"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


class TestMaskCharacters(unittest.TestCase):
    """The picture's alphabet, and the one character the line view borrows."""

    def test_free_and_blocked_are_distinct_single_characters(self) -> None:
        self.assertEqual(len(cw_mask.FREE), 1)
        self.assertEqual(len(cw_mask.MASKED), 1)
        self.assertNotEqual(cw_mask.FREE, cw_mask.MASKED)

    def test_the_stamp_is_neither_a_block_nor_a_letter(self) -> None:
        # `cw_place._fits_line` accepts a cell only when it is BLOCK or the
        # wanted letter, so the stamp rejects a placement for free -- but only
        # while it is neither. MASKED itself is "X", a letter a bank can want.
        self.assertNotEqual(cw_mask.STAMP, cw_grid.BLOCK)
        self.assertFalse("A" <= cw_mask.STAMP <= "Z")
        self.assertEqual(len(cw_mask.STAMP), 1)


class TestLoadMask(unittest.TestCase):
    """A picture read into its size and the cells it forbids."""

    def test_reads_the_masked_cells_and_the_picture_size(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "X..\n..X\n")
            mask = cw_mask.load_mask(path)
            self.assertEqual((mask.rows, mask.cols), (2, 3))
            self.assertEqual(mask.cells, frozenset({(0, 0), (1, 2)}))

    def test_a_picture_with_nothing_masked_reads_as_no_cells(self) -> None:
        # Legal, and not the same as no mask at all: it still fixes the size.
        with tempfile.TemporaryDirectory() as folder:
            mask = cw_mask.load_mask(_written(folder, "..\n..\n"))
            self.assertEqual((mask.rows, mask.cols), (2, 2))
            self.assertEqual(mask.cells, frozenset())

    def test_comment_lines_are_skipped_and_are_not_rows(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            mask = cw_mask.load_mask(_written(folder, "# a heart\nX.\n# mid\n.X\n"))
            self.assertEqual((mask.rows, mask.cols), (2, 2))
            self.assertEqual(mask.cells, frozenset({(0, 0), (1, 1)}))

    def test_trailing_whitespace_on_a_row_is_not_part_of_the_picture(self) -> None:
        # A trailing space is invisible in an editor and a "\r" is invisible
        # everywhere, so neither may change the picture's width.
        with tempfile.TemporaryDirectory() as folder:
            mask = cw_mask.load_mask(_written(folder, "X.  \n.X\t\n"))
            self.assertEqual((mask.rows, mask.cols), (2, 2))
            self.assertEqual(mask.cells, frozenset({(0, 0), (1, 1)}))

    def test_a_file_with_no_trailing_newline_reads_the_same(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            mask = cw_mask.load_mask(_written(folder, "X.\n.X"))
            self.assertEqual(mask.cells, frozenset({(0, 0), (1, 1)}))

    def test_one_row_of_one_cell_is_a_picture(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            mask = cw_mask.load_mask(_written(folder, ".\n"))
            self.assertEqual((mask.rows, mask.cols), (1, 1))
            self.assertEqual(mask.cells, frozenset())


class TestLoadMaskRefusals(unittest.TestCase):
    """Every way a picture is refused, each naming the line at fault."""

    def _refusal(self, text: str) -> str:
        """The message `load_mask` refuses `text` with."""
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, text)
            with self.assertRaises(cw_mask.MaskError) as caught:
                cw_mask.load_mask(path)
        return str(caught.exception)

    def test_a_ragged_row_names_the_line_and_both_widths(self) -> None:
        message = self._refusal("...\n..\n")
        self.assertIn("line 2", message)
        self.assertIn("2", message)
        self.assertIn("3", message)

    def test_the_ragged_line_number_counts_comments(self) -> None:
        # The operator fixes the file by line number, so the count is the
        # FILE's, not the picture's -- a comment still occupies a line.
        self.assertIn("line 3", self._refusal("# note\n...\n..\n"))

    def test_a_blank_line_is_refused_naming_the_line(self) -> None:
        message = self._refusal("..\n\n..\n")
        self.assertIn("line 2", message)
        self.assertIn("blank", message)

    def test_a_blank_line_of_whitespace_is_refused_too(self) -> None:
        self.assertIn("line 2", self._refusal("..\n   \n..\n"))

    def test_an_unknown_character_names_the_line_the_column_and_it(self) -> None:
        message = self._refusal("..\n.q\n")
        self.assertIn("line 2", message)
        self.assertIn("column 2", message)
        self.assertIn("'q'", message)

    def test_a_lowercase_x_is_an_unknown_character(self) -> None:
        # Not folded: a picture means exactly what it draws, and a fold would
        # make "x" and "X" two spellings of one cell in a file whose whole
        # content is single characters.
        self.assertIn("'x'", self._refusal("..\n.x\n"))

    def test_a_leading_space_is_an_unknown_character(self) -> None:
        # Leading whitespace would shift the row, so it is never trimmed.
        message = self._refusal(" .\n..\n")
        self.assertIn("line 1", message)
        self.assertIn("column 1", message)

    def test_an_empty_file_is_refused(self) -> None:
        self.assertIn("no rows", self._refusal(""))

    def test_a_file_of_only_comments_is_refused(self) -> None:
        self.assertIn("no rows", self._refusal("# just a note\n"))

    def test_a_picture_masking_every_cell_is_refused(self) -> None:
        # It forbids every letter, so no grid could be filled -- and it is the
        # one picture that leaves the density denominator at zero.
        message = self._refusal("XX\nXX\n")
        self.assertIn("every cell", message)

    def test_a_missing_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_mask.MaskError):
                cw_mask.load_mask(Path(folder) / "absent.txt")

    def test_a_directory_where_a_file_is_expected_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_mask.MaskError):
                cw_mask.load_mask(Path(folder))

    def test_a_file_that_is_not_valid_utf_8_is_refused(self) -> None:
        # A UnicodeDecodeError is a ValueError rather than an OSError, so it
        # needs naming separately or it escapes the CLI's refusal set as a
        # traceback -- the reason `cw_bank` names it too.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shape.txt"
            path.write_bytes(b"..\n.\xff\n")
            with self.assertRaises(cw_mask.MaskError):
                cw_mask.load_mask(path)

    def test_the_refusal_names_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, "")
            with self.assertRaises(cw_mask.MaskError) as caught:
                cw_mask.load_mask(path)
            self.assertIn(str(path), str(caught.exception))


class TestStampedRows(unittest.TestCase):
    """The derived line view `cw_place._fits_line` reads a masked cell through."""

    def test_stamps_each_masked_cell(self) -> None:
        self.assertEqual(
            cw_mask.stamped_rows(("CAT", "..."), frozenset({(0, 1), (1, 2)})),
            (f"C{cw_mask.STAMP}T", f"..{cw_mask.STAMP}"),
        )

    def test_without_a_mask_the_rows_come_back_unchanged(self) -> None:
        # The fast path every unmasked search takes: `crossing_candidates` asks
        # this of nearly every node, so an unmasked run must pay nothing for it.
        rows = ("CAT", "...")
        self.assertEqual(cw_mask.stamped_rows(rows, frozenset()), rows)

    def test_a_masked_cell_outside_the_rows_is_ignored(self) -> None:
        # The size-agreement check makes this unreachable from a command line,
        # but the function is public and must not index past a row.
        self.assertEqual(cw_mask.stamped_rows(("CAT",), frozenset({(5, 5)})), ("CAT",))

    def test_a_masked_letter_is_stamped_over(self) -> None:
        # Not reachable from a validated run either -- a letter in a masked cell
        # is refused before the search -- but the view must not silently keep a
        # letter the mask forbids, since that letter would then satisfy a match.
        self.assertEqual(
            cw_mask.stamped_rows(("CAT",), frozenset({(0, 0)})),
            (f"{cw_mask.STAMP}AT",),
        )


class TestSizeDisagreement(unittest.TestCase):
    """The sentence `fill` refuses a mis-sized picture with."""

    def test_a_matching_picture_has_no_fault(self) -> None:
        self.assertIsNone(cw_mask.size_disagreement((4, 5), (4, 5)))

    def test_no_mask_has_no_fault(self) -> None:
        self.assertIsNone(cw_mask.size_disagreement(cw_mask.NO_MASK_SIZE, (4, 5)))

    def test_a_disagreement_names_both_sizes(self) -> None:
        fault = cw_mask.size_disagreement((3, 5), (4, 5))
        self.assertIsNotNone(fault)
        assert fault is not None  # narrows for the type checker
        self.assertIn("3x5", fault)
        self.assertIn("4x5", fault)
        self.assertIn("--mask", fault)

    def test_a_picture_larger_than_the_grid_is_a_fault_too(self) -> None:
        # Not "at least big enough": a larger picture draws cells the grid does
        # not have, so the operator's shape is not the shape they would get.
        self.assertIsNotNone(cw_mask.size_disagreement((9, 9), (4, 5)))


class TestForbiddenLetter(unittest.TestCase):
    """A `--source` letter in a masked cell, named for the operator."""

    def test_a_letter_in_a_masked_cell_is_a_fault(self) -> None:
        fault = cw_mask.forbidden_letter(("A.", ".."), frozenset({(0, 0)}))
        self.assertIsNotNone(fault)
        assert fault is not None  # narrows for the type checker
        self.assertIn("--source", fault)
        self.assertIn("--mask", fault)
        self.assertIn("0,0", fault)

    def test_a_letter_clear_of_the_mask_is_no_fault(self) -> None:
        self.assertIsNone(cw_mask.forbidden_letter(("A.", ".."), frozenset({(1, 1)})))

    def test_a_masked_blocked_cell_is_no_fault(self) -> None:
        # A masked cell IS blocked in every grid that reaches here; the rule is
        # about a letter, so the ordinary case must not be reported as one.
        self.assertIsNone(cw_mask.forbidden_letter(("..", ".."), frozenset({(0, 0)})))

    def test_no_rows_is_no_fault(self) -> None:
        self.assertIsNone(cw_mask.forbidden_letter((), frozenset({(0, 0)})))


class TestRequestedSize(unittest.TestCase):
    """What the mask supplies when `--rows` / `--cols` are absent."""

    def _mask(self, rows: int, cols: int) -> cw_mask.Mask:
        """A mask of `rows` x `cols` forbidding nothing."""
        return cw_mask.Mask(rows=rows, cols=cols, cells=frozenset())

    def test_without_a_mask_both_flags_pass_through(self) -> None:
        self.assertEqual(cw_mask.requested_size(5, 7, (0, 0), None), (5, 7))

    def test_without_a_mask_absent_flags_stay_absent(self) -> None:
        self.assertEqual(cw_mask.requested_size(None, None, (0, 0), None), (None, None))

    def test_a_mask_supplies_both_absent_flags(self) -> None:
        mask = self._mask(9, 11)
        self.assertEqual(cw_mask.requested_size(None, None, (0, 0), mask), (9, 11))

    def test_a_mask_supplies_only_the_absent_flag(self) -> None:
        mask = self._mask(9, 11)
        self.assertEqual(cw_mask.requested_size(4, None, (0, 0), mask), (4, 11))
        self.assertEqual(cw_mask.requested_size(None, 4, (0, 0), mask), (9, 4))

    def test_a_mask_larger_than_the_source_supplies_the_grown_size(self) -> None:
        mask = self._mask(9, 11)
        self.assertEqual(cw_mask.requested_size(None, None, (7, 7), mask), (9, 11))

    def test_a_mask_never_supplies_a_dimension_that_would_crop_the_source(self) -> None:
        # Left absent rather than supplied: `cw_source.resolve_size` would
        # refuse it naming `--rows`, a flag the operator did not write. Absent,
        # the source's own size stands and the size-agreement check refuses
        # instead, naming both sizes.
        mask = self._mask(5, 11)
        self.assertEqual(cw_mask.requested_size(None, None, (7, 7), mask), (None, 11))

    def test_a_mask_equal_to_the_source_still_supplies_the_size(self) -> None:
        mask = self._mask(7, 7)
        self.assertEqual(cw_mask.requested_size(None, None, (7, 7), mask), (7, 7))

    def test_a_given_flag_is_never_replaced_even_where_the_mask_would_crop(
        self,
    ) -> None:
        mask = self._mask(5, 5)
        self.assertEqual(cw_mask.requested_size(9, 9, (7, 7), mask), (9, 9))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    unittest.main()
