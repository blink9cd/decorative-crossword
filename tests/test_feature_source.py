"""Tests for cw_feature's pin checks against a --source grid.

Every pin is laid on the source board. It may cross a source entry or lie
exactly on one, but it may not change a source letter, repeat an answer the
source already holds, or leave any entry short of its exact run. A partial run
is no entry: a pin lying along all of it may complete it, and nothing else may
lengthen it.
"""

import unittest

import cw_config
import cw_feature
import cw_grid

from tests.search_fixtures import config as _config
from tests.search_fixtures import pin as _pin

#: CHALK across the top of a 5x5.
_CHALK = ("CHALK", ".....", ".....", ".....", ".....")


def _check(
    start: tuple[str, ...],
    *pins: cw_feature.Feature,
    partial: tuple[cw_grid.Run, ...] = (),
    growable: tuple[cw_grid.Run, ...] = (),
) -> None:
    """Run the feature checks for `pins` on `start`, whose partial runs are `partial`.

    Both halves, in the CLI's order: the checks decided before the bank, then
    the one that needs `cw_source.start_from` to say which runs are partial.
    `growable` is the entries `--absorb-entries` lets grow, empty without it.
    """
    config = _config(rows=len(start), cols=len(start[0]), start=start, features=pins)
    cw_feature.validate_features(config)
    cw_feature.validate_source_runs(config, partial, growable)


def _across(row: int, col: int, text: str) -> cw_grid.Run:
    """An across run, as `cw_source.start_from` reports a partial one."""
    return cw_grid.Run(row=row, col=col, direction=cw_grid.ACROSS, text=text)


class TestPinsOnASource(unittest.TestCase):
    """What a pin may and may not do to the grid it is laid on."""

    def test_a_pin_lying_exactly_on_its_own_source_entry_is_allowed(self) -> None:
        _check(_CHALK, _pin("CHALK", 0, 0, cw_grid.ACROSS))

    def test_a_pin_crossing_a_source_letter_it_agrees_with_is_allowed(self) -> None:
        _check(_CHALK, _pin("CEDAR", 0, 0, cw_grid.DOWN))

    def test_a_pin_disagreeing_with_a_source_letter_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(_CHALK, _pin("CRANE", 0, 0, cw_grid.ACROSS))
        message = str(caught.exception)
        self.assertIn("--source", message)
        self.assertIn("(0, 1)", message)

    def test_a_pin_disagreeing_with_a_stray_at_its_first_cell_is_refused(self) -> None:
        # The K is a lone letter in no entry, so no later check falls back on
        # it: only the agreement check stands between the pin and overwriting it.
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(("K....", "....."), _pin("CHALK", 0, 0, cw_grid.ACROSS))
        self.assertIn(
            "disagrees with --source at (0, 0): 'K' against 'C'", str(caught.exception)
        )

    def test_a_pin_disagreeing_with_a_stray_at_its_last_cell_is_refused(self) -> None:
        # The first-cell case's mirror: an agreement check that stopped one
        # cell short would let CHALK's K overwrite this lone Q.
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(("....Q", "....."), _pin("CHALK", 0, 0, cw_grid.ACROSS))
        self.assertIn(
            "disagrees with --source at (0, 4): 'Q' against 'K'", str(caught.exception)
        )

    def test_a_pin_naming_an_answer_the_source_holds_elsewhere_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(_CHALK, _pin("CHALK", 2, 0, cw_grid.ACROSS))
        self.assertIn("(0, 0) across", str(caught.exception))

    def test_a_pin_running_into_a_source_letter_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(("....K", "....."), _pin("CHAL", 0, 0, cw_grid.ACROSS))
        self.assertIn("'CHAL'", str(caught.exception))

    def test_a_pin_extending_a_source_entry_along_its_line_is_refused(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(("CHAL.", "....."), _pin("CHALK", 0, 0, cw_grid.ACROSS))
        self.assertIn("'CHAL'", str(caught.exception))

    def test_a_pin_extending_a_source_entry_before_its_first_letter_is_refused(
        self,
    ) -> None:
        # The pin's C lands just before HALK's H, so the entry grows at its
        # start rather than its end.
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check((".HALK", "....."), _pin("CHALK", 0, 0, cw_grid.ACROSS))
        self.assertIn("'HALK' at (0, 1) across", str(caught.exception))

    def test_a_pin_extending_a_source_entry_across_its_line_is_refused(self) -> None:
        # EAT across row 3 puts an E under COW, which then reads COWE.
        start = ("CAT..", "O....", "W....", ".....")
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(start, _pin("EAT", 3, 0, cw_grid.ACROSS))
        self.assertIn("'COW'", str(caught.exception))


class TestPinsGrowingAnEntry(unittest.TestCase):
    """Under --absorb-entries a pin lying along all of a growable entry chooses its growth."""

    def test_a_pin_lying_along_a_growable_entry_grows_it(self) -> None:
        _check(
            ("CHAL..", "......"),
            _pin("CHALK", 0, 0, cw_grid.ACROSS),
            growable=(_across(0, 0, "CHAL"),),
        )

    def test_one_pin_welds_two_growable_entries(self) -> None:
        _check(
            ("CH.LK.", "......"),
            _pin("CHALK", 0, 0, cw_grid.ACROSS),
            growable=(_across(0, 0, "CH"), _across(0, 3, "LK")),
        )

    def test_an_entry_not_growable_is_still_refused_beside_one_that_is(self) -> None:
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(
                ("CHAL..", "......", "AL...."),
                _pin("CHALK", 0, 0, cw_grid.ACROSS),
                growable=(_across(2, 0, "AL"),),
            )
        self.assertIn("extend the --source entry 'CHAL'", str(caught.exception))


class TestPinsOnAPartialRun(unittest.TestCase):
    """A partial run is no entry: a pin may complete it only by lying along all of it."""

    def test_a_pin_lying_along_a_partial_run_past_its_end_completes_it(self) -> None:
        _check(
            ("ALPH..", "......"),
            _pin("ALPHA", 0, 0, cw_grid.ACROSS),
            partial=(_across(0, 0, "ALPH"),),
        )

    def test_a_down_pin_lying_along_a_partial_run_before_its_start_completes_it(
        self,
    ) -> None:
        # 5x2, not square: a transposed read of the rows cannot pass.
        mber = cw_grid.Run(row=1, col=0, direction=cw_grid.DOWN, text="MBER")
        _check(
            ("..", "M.", "B.", "E.", "R."),
            _pin("AMBER", 0, 0, cw_grid.DOWN),
            partial=(mber,),
        )

    def test_one_pin_across_a_gap_completes_both_partial_runs(self) -> None:
        _check(
            ("AL.HA.", "......"),
            _pin("ALPHA", 0, 0, cw_grid.ACROSS),
            partial=(_across(0, 0, "AL"), _across(0, 3, "HA")),
        )

    def test_a_crossing_pin_lengthening_a_partial_run_is_refused(self) -> None:
        # BRAVO down from (0, 4) lands just past ALPH's H: the run reads ALPHB,
        # and no pin lies along it.
        start = ("ALPH..", "......", "......", "......", "......")
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(
                start,
                _pin("BRAVO", 0, 4, cw_grid.DOWN),
                partial=(_across(0, 0, "ALPH"),),
            )
        self.assertIn(
            "lengthen the --source partial run 'ALPH' at (0, 0) across",
            str(caught.exception),
        )

    def test_an_entry_a_pin_lies_along_is_still_refused_beside_a_partial_run(
        self,
    ) -> None:
        # CHAL is an entry, not partial, so lying along it is extending it;
        # the partial run elsewhere in the grid excuses nothing for it.
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(
                ("CHAL..", "......", "AL...."),
                _pin("CHALK", 0, 0, cw_grid.ACROSS),
                partial=(_across(2, 0, "AL"),),
            )
        self.assertIn("extend the --source entry 'CHAL'", str(caught.exception))

    def test_a_crossing_pin_lengthening_a_growable_entry_is_refused(self) -> None:
        # Under --absorb-entries COW may grow, but only by a pin lying along it:
        # EAT across row 3 lands just under it, and COWE is a run no pin holds.
        start = ("CAT..", "O....", "W....", ".....")
        cow = cw_grid.Run(row=0, col=0, direction=cw_grid.DOWN, text="COW")
        with self.assertRaises(cw_config.ConfigError) as caught:
            _check(start, _pin("EAT", 3, 0, cw_grid.ACROSS), growable=(cow,))
        self.assertIn(
            "lengthen the --source entry 'COW' at (0, 0) down, but no pin lies along "
            "all of it",
            str(caught.exception),
        )

    def test_without_a_source_nothing_is_checked(self) -> None:
        cw_feature.validate_source_runs(
            _config(features=(_pin("ALPHA", 0, 0, cw_grid.ACROSS),)), ()
        )
