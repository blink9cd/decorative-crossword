"""Tests for the canvas a `fill --source` grid is placed on, and where it sits.

`--rows` and `--cols` beside a source grow its grid: each flag given must be at
least the source's own dimension, a flag left off takes the source's, and the
source sits at the top-left, so every source cell keeps its coordinates in the
grown grid. These are the pure halves; `tests/test_cli_grown.py` drives them
end to end.
"""

import unittest

import cw_config
import cw_source

#: A 2x3 source: CAT across the top row, nothing under it.
_SOURCE = ("CAT", "...")

#: The words every size refusal closes with.
_TAIL = ": fill grows a source, never crops it"


class TestResolveSize(unittest.TestCase):
    """The canvas: the source's own size, or larger in either dimension, never smaller."""

    def test_no_size_flag_keeps_the_sources_size(self) -> None:
        self.assertEqual(cw_source.resolve_size(None, None, _SOURCE), (2, 3))

    def test_both_flags_grow_the_canvas(self) -> None:
        self.assertEqual(cw_source.resolve_size(5, 7, _SOURCE), (5, 7))

    def test_a_flag_left_off_takes_the_sources_dimension(self) -> None:
        self.assertEqual(cw_source.resolve_size(4, None, _SOURCE), (4, 3))
        self.assertEqual(cw_source.resolve_size(None, 6, _SOURCE), (2, 6))

    def test_a_flag_equal_to_the_sources_dimension_is_accepted(self) -> None:
        # It states the size the source already has, so it contradicts nothing.
        self.assertEqual(cw_source.resolve_size(2, 3, _SOURCE), (2, 3))

    def test_rows_under_the_sources_rows_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_source.resolve_size(1, None, _SOURCE)
        self.assertEqual(
            str(caught.exception),
            "--rows 1 is smaller than the --source grid's 2 rows" + _TAIL,
        )

    def test_cols_under_the_sources_columns_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_source.resolve_size(None, 2, _SOURCE)
        self.assertEqual(
            str(caught.exception),
            "--cols 2 is smaller than the --source grid's 3 columns" + _TAIL,
        )

    def test_both_flags_under_the_source_are_named_in_one_refusal(self) -> None:
        # Every refusal names every offender of its kind, never the first.
        with self.assertRaises(cw_config.ConfigError) as caught:
            cw_source.resolve_size(1, 2, _SOURCE)
        self.assertEqual(
            str(caught.exception),
            "--rows 1 is smaller than the --source grid's 2 rows; --cols 2 is "
            "smaller than the --source grid's 3 columns" + _TAIL,
        )

    def test_without_a_source_both_flags_are_the_size(self) -> None:
        self.assertEqual(cw_source.resolve_size(3, 4, ()), (3, 4))


class TestPlaceSource(unittest.TestCase):
    """The source written onto the top-left of its canvas, every other cell blocked."""

    def test_the_source_sits_at_the_top_left_of_a_larger_canvas(self) -> None:
        self.assertEqual(
            cw_source.place_source(_SOURCE, 4, 5),
            ("CAT..", ".....", ".....", "....."),
        )

    def test_a_canvas_of_the_sources_own_size_is_the_source(self) -> None:
        self.assertEqual(cw_source.place_source(_SOURCE, 2, 3), _SOURCE)

    def test_no_source_places_nothing(self) -> None:
        # A fill without --source keeps its empty start whatever size it asks for.
        self.assertEqual(cw_source.place_source((), 4, 5), ())


if __name__ == "__main__":
    unittest.main()
