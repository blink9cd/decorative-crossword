"""Tests for cw_report's remedy block: the missed constraint and the knob for it.

The content blocks are tested in test_report.py. Both suites share
tests/report_fixtures.py, so the bank the arithmetic depends on is defined
exactly once.

The reason this block exists at all: the operator's bottleneck is the word
list rather than the tool, so a failure that
says only "no grid found" sends the reader back to `--help` while one naming
the number to change does not.
"""

import unittest

import cw_accept
import cw_feature
import cw_report
import cw_search

from tests.report_fixtures import block_after as _block_after
from tests.report_fixtures import line as _line
from tests.report_fixtures import lines as _lines
from tests.report_fixtures import make_bank as _bank
from tests.report_fixtures import make_config as _config
from tests.report_fixtures import make_outcome as _outcome
from tests.search_fixtures import TWENTY_EIGHT_OF_100 as _TWENTY_EIGHT_OF_100
from tests.search_fixtures import TWENTY_NINE_OF_100 as _TWENTY_NINE_OF_100

#: A 3x3 board holding two two-letter runs, CA and WE, and nothing longer.
_TWO_TWOS = ("CA.", "...", "WE.")

#: The largest grid side, written out rather than read from the code under
#: test, so a changed cap fails here instead of moving the test along with it.
_CAP = 25


def _cat_on(height: int, width: int) -> tuple[str, ...]:
    """A `height` x `width` board: CAT across its top-left corner, nothing else."""
    return ("CAT" + "." * (width - 3),) + ("." * width,) * (height - 1)


class TestTwoLetterRemedy(unittest.TestCase):
    """A grid over `--max-two-letter` names the figure that would clear it."""

    def test_names_the_cap_that_would_admit_this_grid(self) -> None:
        # Density and themes are opened wide so the cap is the only miss, and so
        # the one knob asserted below cannot be some other constraint's.
        config = _config(min_themes=0, max_blocked=95.0, max_two_letter=1)
        outcome = _outcome(_TWO_TWOS, config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(len(outcome.missed), 1)
        self.assertEqual(
            _block_after(text, "What would clear each:", 1),
            [
                "  loosen --max-two-letter to 2 or higher, "
                "or raise --time-budget or --max-steps"
            ],
        )

    def test_offers_no_cap_knob_for_a_grid_at_the_cap(self) -> None:
        # Two runs at a cap of two meet it: a knob here would advise loosening a
        # constraint the missed list above never names.
        config = _config(max_two_letter=2)
        text = cw_report.render_report(
            _outcome(_TWO_TWOS, config=config), _bank(), config, []
        )
        self.assertEqual(_lines(text, "  loosen --max-two-letter"), [])


class TestRemedy(unittest.TestCase):
    """On a miss: the missed constraint, and the knob to turn."""

    def test_echoes_every_missed_constraint_verbatim(self) -> None:
        config = _config(min_entries_per_theme=3)
        outcome = _outcome(("CAT", "...", "..."), config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(_line(text, "NOT CONFORMING"), "NOT CONFORMING - missed:")
        # Two reasons, not one: a report that echoed only the first would still
        # satisfy a single-reason fixture, and each one has to be named.
        self.assertEqual(len(outcome.missed), 2)
        self.assertEqual(
            _block_after(text, "NOT CONFORMING - missed:", len(outcome.missed)),
            [f"  {reason}" for reason in outcome.missed],
        )

    def test_names_max_blocked_rounded_UP_to_a_figure_that_clears(self) -> None:
        # 4 of 9 cells blocked is 44.44...%, which renders as "44.4", a figure
        # still below the achieved density, so an operator who set it there
        # would be refused again. The stated figure is rounded up instead.
        config = _config(max_blocked=20.0, min_themes=0)
        text = cw_report.render_report(
            _outcome(("CAT", "O..", "W.."), config=config), _bank(), config, []
        )
        self.assertEqual(_line(text, "What would clear"), "What would clear each:")
        self.assertEqual(
            _line(text, "  loosen"),
            "  loosen --max-blocked to 44.5 or higher, or shrink --rows / --cols",
        )
        # Only the constraint actually missed earns a knob: a block that listed
        # every option would be a menu. The density here is too high, not too
        # low, and --min-themes is 0, so neither of those lines belongs.
        self.assertEqual(_lines(text, "  lower --min-blocked"), [])
        self.assertEqual(_lines(text, "  lower --min-themes"), [])

    def test_offers_no_density_knob_at_exactly_the_ceiling(self) -> None:
        # 2 blocked of 8 cells is exactly 25.0%, which meets a 25.0% ceiling.
        # A `>=` comparison here would hand this run a "loosen --max-blocked"
        # line contradicting its own echoed missed list, in the one module whose
        # whole job is telling the operator the truth about the run.
        config = _config(rows=2, cols=4, max_blocked=25.0, min_themes=1)
        outcome = _outcome(("CATS", "OW.."), config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(outcome.conforming, False)
        self.assertIn("25.0% blocked", _line(text, "Grid "))
        # Nothing about density: no knob, and no density sentence echoed. The
        # missed constraint is the theme floor, and it is the only knob offered.
        self.assertEqual(_lines(text, "  loosen"), [])
        self.assertEqual(_lines(text, "  blocked "), [])
        self.assertEqual(len(_lines(text, "  lower --min-themes")), 1)

    def test_offers_no_theme_knob_at_exactly_the_floor(self) -> None:
        # The twin of the density boundary above, on the other axis. Pets
        # carries 2 entries and reaches the floor; Food carries none. So
        # exactly one theme reaches it, against a --min-themes of 1: the floor
        # is met, and `met < min_themes` re-spelled as `<=` would offer "lower
        # --min-themes" beside a missed list naming only density.
        config = _config(max_blocked=20.0, min_themes=1)
        rows = ("CAT", "O..", "WET")
        outcome = _outcome(rows, config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        # Pin the fixture on the boundary, so it cannot drift off it unnoticed.
        self.assertEqual(
            cw_accept.themes_meeting_floor(rows, _bank(), config), config.min_themes
        )
        self.assertEqual(outcome.conforming, False)
        self.assertEqual(len(outcome.missed), 1)
        self.assertEqual(_lines(text, "  lower --min-themes"), [])
        self.assertEqual(len(_lines(text, "  loosen")), 1)

    def test_names_min_blocked_rounded_DOWN_to_a_figure_that_clears(self) -> None:
        # 3 of 16 cells blocked is 18.75%, which rounds to "18.8", a figure
        # above the achieved density, so it would not clear either. Rounded down.
        config = _config(rows=4, cols=4, min_blocked=30.0, min_themes=0)
        rows = ("CATS", "O...", "WEST", "SEED")
        text = cw_report.render_report(
            _outcome(rows, config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "  lower --min-blocked"),
            "  lower --min-blocked to 18.7 or lower",
        )

    def test_names_the_theme_floor_knobs(self) -> None:
        config = _config(min_entries_per_theme=3)
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(
            _line(text, "  lower --min-themes"),
            "  lower --min-themes to 0, or lower --min-entries-per-theme, or add "
            "themed answers to the bank",
        )
        # The density sits inside the window here, so neither bound is at fault.
        self.assertEqual(_lines(text, "  loosen"), [])
        self.assertEqual(_lines(text, "  lower --min-blocked"), [])

    def test_names_the_feature_knobs_when_the_answer_is_missing(self) -> None:
        config = _config(feature="COW", min_themes=0, max_blocked=100.0)
        text = cw_report.render_report(
            _outcome(("CAT", "...", "..."), config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "  place COW"),
            "  place COW by raising --time-budget or --max-steps, or grow "
            "--rows / --cols",
        )
        # A 100% ceiling and a floor of 0 themes leave the feature as the one
        # constraint missed, so it must be the one knob offered.
        self.assertEqual(_lines(text, "  loosen"), [])
        self.assertEqual(_lines(text, "  lower --min-themes"), [])

    def test_names_a_knob_for_each_absent_feature_in_the_order_given(self) -> None:
        # Two features, both missing: each is its own missed constraint, so
        # each gets its own knob. A block that named only the first would
        # leave the operator to discover the second on the next run.
        config = _config(
            features=(cw_feature.Feature("WET", None), cw_feature.Feature("COW", None)),
            min_themes=0,
            max_blocked=100.0,
        )
        text = cw_report.render_report(
            _outcome(("CAT", "...", "..."), config=config), _bank(), config, []
        )
        self.assertEqual(
            _lines(text, "  place "),
            [
                "  place WET by raising --time-budget or --max-steps, or grow "
                "--rows / --cols",
                "  place COW by raising --time-budget or --max-steps, or grow "
                "--rows / --cols",
            ],
        )

    def test_offers_no_grow_clause_on_a_grid_at_the_size_cap(self) -> None:
        # Both dimensions already at the cap: growing either is refused at exit
        # 2, so the knob names only the budgets.
        config = _config(
            rows=_CAP, cols=_CAP, feature="COW", min_themes=0, max_blocked=100.0
        )
        text = cw_report.render_report(
            _outcome(_cat_on(_CAP, _CAP), config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "  place COW"),
            "  place COW by raising --time-budget or --max-steps",
        )

    def test_names_only_the_dimension_under_the_cap_to_grow(self) -> None:
        # `--rows` is the height and `--cols` the width, so the grid tall at the
        # cap may still grow wider and the one wide at the cap taller. Both
        # shapes, so a knob that swapped the flags fails one of them.
        for height, width, flag in ((_CAP, 10, "--cols"), (10, _CAP, "--rows")):
            with self.subTest(height=height, width=width):
                config = _config(
                    rows=height,
                    cols=width,
                    feature="COW",
                    min_themes=0,
                    max_blocked=100.0,
                )
                text = cw_report.render_report(
                    _outcome(_cat_on(height, width), config=config),
                    _bank(),
                    config,
                    [],
                )
                self.assertEqual(
                    _line(text, "  place COW"),
                    "  place COW by raising --time-budget or --max-steps, or grow "
                    + flag,
                )

    def test_offers_no_feature_knob_when_the_answer_is_in_the_grid(self) -> None:
        # COW stands in column 0 of this grid, so the run misses on density
        # alone. A knob block that named the feature whenever one was nominated
        # would send the operator after a constraint that is already met.
        config = _config(feature="COW", max_blocked=20.0, min_themes=0)
        outcome = _outcome(("CAT", "O..", "W.."), config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(outcome.conforming, False)
        self.assertEqual(_lines(text, "  place COW"), [])
        self.assertEqual(len(_lines(text, "  loosen")), 1)

    def test_names_the_feature_knob_on_a_grid_holding_no_entry(self) -> None:
        # A walk cut at its root comes back holding no entry, and its missed
        # list names the absent feature, so the block must say how to place it,
        # with or without --source. Only the density and theme figures of an
        # empty grid go: this one misses both, and neither earns a knob.
        config = _config(feature="COW")
        outcome = _outcome(("...", "...", "..."), config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(len(outcome.missed), 3)
        self.assertIn("the featured answer 'COW' is not in the grid", outcome.missed)
        # Two lines asked for, one expected: the knob block closes the report,
        # so a density or theme knob beside the feature's would be the second.
        self.assertEqual(
            _block_after(text, "What would clear each:", 2),
            [
                "  place COW by raising --time-budget or --max-steps, or grow "
                "--rows / --cols"
            ],
        )
        # Without a source every flag named is one this run accepts: --rows and
        # --cols are required here, and no knob may point at a source never read.
        self.assertNotIn("--source", text)

    def test_offers_no_knob_on_a_grid_holding_no_entry_and_no_feature(self) -> None:
        # The same empty grid with nothing featured misses density and themes
        # alone, and arithmetic on a grid holding no entry points at nothing an
        # operator can act on, so the knob block is absent, not empty.
        config = _config()
        outcome = _outcome(("...", "...", "..."), config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(len(outcome.missed), 2)
        self.assertEqual(_lines(text, "What would clear"), [])

    def test_says_nothing_about_a_knob_when_conforming(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertNotIn("--max-blocked", text)
        self.assertEqual(_lines(text, "NOT CONFORMING"), [])

    def test_offers_no_knob_on_a_pre_flight_refusal(self) -> None:
        # A pre-flight refusal comes back with zero steps, the bank's own
        # reasons, and the grid the run began from: here an empty board. A knob
        # read off that unsearched grid would advise loosening --max-blocked to
        # 100: true of the rectangle and useless to the operator.
        config = _config(min_themes=3, min_entries_per_theme=3)
        refusals = cw_accept.preflight(_bank(), config)
        refusal = cw_search.SearchOutcome(
            rows=("...", "...", "..."),
            placed=(),
            conforming=False,
            missed=refusals,
            steps=0,
        )
        text = cw_report.render_report(refusal, _bank(), config, [])
        # The reason is the producer's own sentence, not a paraphrase of it: a
        # hand-written stand-in would keep passing after `preflight` reworded.
        self.assertEqual(len(refusals), 1)
        self.assertEqual(_line(text, "  the bank has"), f"  {refusals[0]}")
        self.assertEqual(_lines(text, "What would clear"), [])
        self.assertNotIn("--max-blocked", text)


class TestGrowAdviceStopsAtTheCap(unittest.TestCase):
    """A feature's knob advises growing only a dimension under the cap, to the cell."""

    #: The knob's opening, which every case below shares.
    PLACE = "  place COW by raising --time-budget or --max-steps"

    def _feature_knob(self, rows: int, cols: int) -> str:
        """The knob for a missing COW on a `rows` x `cols` grid holding CAT alone."""
        config = _config(
            rows=rows, cols=cols, feature="COW", min_themes=0, max_blocked=100.0
        )
        text = cw_report.render_report(
            _outcome(_cat_on(rows, cols), config=config), _bank(), config, []
        )
        return _line(text, "  place COW")

    def test_a_flag_at_the_cap_is_not_advised_to_grow(self) -> None:
        # A --rows or --cols past the cap is refused at exit 2, so advice to
        # grow a dimension already there sends the operator to a run that
        # cannot start. One cell under it on the other side, so the boundary
        # is held from both directions.
        under = _CAP - 1
        for rows, cols, clause in (
            (_CAP, under, ", or grow --cols"),
            (under, _CAP, ", or grow --rows"),
            (_CAP, _CAP, ""),
        ):
            with self.subTest(rows=rows, cols=cols):
                self.assertEqual(self._feature_knob(rows, cols), self.PLACE + clause)

    def test_a_flag_one_under_the_cap_is_still_advised_to_grow(self) -> None:
        under = _CAP - 1
        self.assertEqual(
            self._feature_knob(under, under), self.PLACE + ", or grow --rows / --cols"
        )


class TestNoResizeUnderAMask(unittest.TestCase):
    """Under --mask no knob advises a resize: the picture fixes the grid's size."""

    #: A run missing density and a feature at once, so one knob block carries
    #: both size clauses. 4 of the 9 cells are blocked, 44.4...%, over a 20%
    #: ceiling and rounded up to 44.5 to clear it; PIE is nowhere in the grid.
    ROWS = ("CAT", "O..", "W..")

    def _knob_block(
        self, masked: frozenset[tuple[int, int]], mask_size: tuple[int, int]
    ) -> list[str]:
        """The knob block for `ROWS` under the picture `masked` and `mask_size`."""
        config = _config(
            feature="PIE",
            max_blocked=20.0,
            min_themes=0,
            masked=masked,
            mask_size=mask_size,
        )
        text = cw_report.render_report(
            _outcome(self.ROWS, config=config), _bank(), config, []
        )
        # Three lines asked for, two expected: the knob block closes the
        # report, so a third knob would show here.
        return _block_after(text, "What would clear each:", 3)

    def test_neither_knob_names_a_resize_under_a_mask(self) -> None:
        # A --rows or --cols that disagrees with the picture, 3x3 like the
        # grid, is refused at exit 2, so either clause would send the operator
        # to a run that cannot start. Both pictures, because one forbidding no
        # cell is still a mask: it fixes the size all the same. The corner the
        # second forbids leaves both density counts, so its figure is 3 of 8,
        # exactly 37.5%.
        for masked, figure in ((frozenset(), "44.5"), (frozenset({(2, 2)}), "37.5")):
            with self.subTest(masked=sorted(masked)):
                self.assertEqual(
                    self._knob_block(masked, (3, 3)),
                    [
                        f"  loosen --max-blocked to {figure} or higher",
                        "  place PIE by raising --time-budget or --max-steps",
                    ],
                )

    def test_both_knobs_name_a_resize_without_a_mask(self) -> None:
        # The same run without the picture, whose size a config then carries
        # as (0, 0): what drops the clauses above is the mask and nothing else.
        self.assertEqual(
            self._knob_block(frozenset(), (0, 0)),
            [
                "  loosen --max-blocked to 44.5 or higher, or shrink --rows / --cols",
                "  place PIE by raising --time-budget or --max-steps, or grow "
                "--rows / --cols",
            ],
        )


class TestExactDensity(unittest.TestCase):
    """The verdict, the shortfall and the knobs all judge density one exact way."""

    def test_a_grid_exactly_on_the_ceiling_is_no_miss(self) -> None:
        # A float verdict called this grid over its 28.0 ceiling while the
        # shortfall line, counting cells, called it within, in one report.
        config = _config(rows=10, cols=10, max_blocked=28.0, min_themes=0)
        outcome = _outcome(_TWENTY_EIGHT_OF_100, config=config)
        text = cw_report.render_report(outcome, _bank(), config, [])
        self.assertEqual(outcome.missed, ())
        self.assertEqual(_lines(text, "NOT CONFORMING"), [])
        self.assertEqual(
            _line(text, "Density shortfall"),
            "Density shortfall: none - the grid is already within the requested "
            "28.0% blocked ceiling.",
        )

    def test_the_ceiling_knob_rounds_the_exact_share_up(self) -> None:
        # Exactly 28%: rounding the float 28.000000000000004 up to a tenth gave
        # 28.1, a ceiling a tenth looser than the one that admits this grid.
        config = _config(rows=10, cols=10, max_blocked=27.9, min_themes=0)
        text = cw_report.render_report(
            _outcome(_TWENTY_EIGHT_OF_100, config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "  loosen"),
            "  loosen --max-blocked to 28.0 or higher, or shrink --rows / --cols",
        )

    def test_the_floor_knob_rounds_the_exact_share_down(self) -> None:
        # Exactly 29%: rounding the float 28.999999999999996 down gave 28.9.
        config = _config(rows=10, cols=10, min_blocked=29.1, min_themes=0)
        text = cw_report.render_report(
            _outcome(_TWENTY_NINE_OF_100, config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "  lower --min-blocked"),
            "  lower --min-blocked to 29.0 or lower",
        )


if __name__ == "__main__":
    unittest.main()
