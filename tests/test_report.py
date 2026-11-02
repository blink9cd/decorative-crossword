"""Tests for cw_report's content blocks: what the report says was placed.

The remedy block (the missed constraints and the knob for each) is the
other half of the report and lives in test_report_remedy.py; both suites
share tests/report_fixtures.py.

Assertions here are deliberately line-scoped (`_line`) or exact-fragment
rather than `assertIn(..., whole_report)`. A report is one long string, so a
membership test can be satisfied by an echoed answer, a theme label, or a
neighboring section: an assertion that passes for a reason it was not
written to check. `_line` pins the one line under test and fails loudly when
the prefix matches none or several; `_block_after` is what pins an order,
since a test that gathers its expected lines by prefix reconstructs the very
order it means to assert.
"""

import dataclasses
import unittest

import cw_bank
import cw_feature
import cw_grid
import cw_place
import cw_report

from tests.report_fixtures import block_after as _block_after
from tests.report_fixtures import cells as _cells
from tests.report_fixtures import line as _line
from tests.report_fixtures import lines as _lines
from tests.report_fixtures import make_bank as _bank
from tests.report_fixtures import make_config as _config
from tests.report_fixtures import make_outcome as _outcome


class TestPlacedCount(unittest.TestCase):
    """The headline: placed N of M bank entries."""

    def test_states_placed_of_total(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(_line(text, "Placed "), "Placed 3 of 5 bank entries.")

    def test_counts_the_grid_rather_than_the_placement_record(self) -> None:
        # The grid's own runs are the authoritative entry set (cw_search's own
        # docstring): one placement can create more than one entry, and an
        # entry can arrive for free. The record below holds one placement while
        # the grid holds three answers (COW and WET arrived as crossings),
        # so an implementation counting `outcome.placed` prints "1 of 5".
        outcome = _outcome(placed=(cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS),))
        text = cw_report.render_report(outcome, _bank(), _config(), [])
        self.assertEqual(len(outcome.placed), 1)
        self.assertEqual(_line(text, "Placed "), "Placed 3 of 5 bank entries.")


class TestGridLine(unittest.TestCase):
    """The grid block: size, filled cells, blocked percent, requested range."""

    def test_states_size_fill_and_density_against_the_request(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(
            _line(text, "Grid "),
            "Grid 3x3: 7 filled cells, 22.2% blocked (requested 10.0-45.0%).",
        )

    def test_states_a_non_square_grid_rows_before_cols(self) -> None:
        # --rows and --cols are independent options, so a non-square grid is
        # ordinary input, and a square fixture cannot tell "RxC" from "CxR".
        # Every other grid in these suites is square, which is exactly why this
        # one exists.
        config = _config(rows=2, cols=4, max_blocked=60.0, min_themes=0)
        text = cw_report.render_report(
            _outcome(("CAT.", "O..."), config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "Grid "),
            "Grid 2x4: 4 filled cells, 50.0% blocked (requested 10.0-60.0%).",
        )

    def test_echoes_requested_against_achieved_density(self) -> None:
        config = _config(min_blocked=12.5, max_blocked=37.5)
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertIn("(requested 12.5-37.5%)", _line(text, "Grid "))

    def test_names_the_basis_it_measured_under_a_mask(self) -> None:
        # Masked cells leave both numerator and denominator, so the percentage
        # is over a smaller grid than the size beside it, and a figure whose
        # basis a reader cannot see is a figure they will misread.
        # One of the 3x3's two blocked cells outside the entries is masked, so
        # the basis is 8 cells and one of them is blocked.
        config = _config(masked=frozenset({(1, 1)}), mask_size=(3, 3))
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(
            _line(text, "Grid "),
            "Grid 3x3: 7 filled cells, 12.5% blocked of 8 unmasked cells "
            "(requested 10.0-45.0%).",
        )

    def test_the_grid_line_names_no_basis_without_a_mask(self) -> None:
        # The clause appears only under `--mask`, so a run without one prints no
        # basis, which is what keeps every unmasked sample byte-identical.
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertNotIn("unmasked", _line(text, "Grid "))


class TestFeature(unittest.TestCase):
    """The feature line: orientation, span, and 0-based (row, column) cells."""

    def test_reports_a_down_featured_answer_span_and_cells(self) -> None:
        config = _config(feature="COW")
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(
            _line(text, "Featured answer"),
            "Featured answer COW: down, (0, 0) to (2, 0).",
        )
        self.assertEqual(
            _line(text, "  Shaded cells"),
            "  Shaded cells, 0-based (row, column): (0, 0), (1, 0), (2, 0)",
        )

    def test_reports_an_across_featured_answer_span_and_cells(self) -> None:
        # CAT runs ACROSS from the same corner COW runs DOWN from. Without this
        # case every feature fixture is a DOWN one, and an orientation hardcoded
        # to "down" renders correctly in all of them, while orientation is
        # one of the three elements the line is required to carry.
        config = _config(feature="CAT")
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(
            _line(text, "Featured answer"),
            "Featured answer CAT: across, (0, 0) to (0, 2).",
        )
        self.assertEqual(
            _line(text, "  Shaded cells"),
            "  Shaded cells, 0-based (row, column): (0, 0), (0, 1), (0, 2)",
        )

    def test_reads_the_cells_back_out_of_the_grid_not_the_placement_record(
        self,
    ) -> None:
        # The reported coordinates are the cells the answer actually occupies,
        # checked by reading them back out of `rows`. The
        # placement record below deliberately disagrees with the grid, so an
        # implementation that trusted it would report (2, 2)/(2, 3)/(2, 4):
        # positions that do not spell COW, two of them off a 3x3 grid entirely.
        config = _config(feature="COW")
        outcome = _outcome(
            placed=(cw_place.Placement("COW", 2, 2, cw_grid.ACROSS),), config=config
        )
        text = cw_report.render_report(outcome, _bank(), config, [])
        cells = _cells(_line(text, "  Shaded cells"))
        self.assertEqual(
            "".join(outcome.rows[row][col] for row, col in cells),
            "COW",
            "the reported cells must spell the featured answer in the grid",
        )
        self.assertEqual(cells, ((0, 0), (1, 0), (2, 0)))

    def test_says_so_when_the_featured_answer_is_not_in_the_grid(self) -> None:
        config = _config(feature="COW")
        text = cw_report.render_report(
            _outcome(("CAT", "...", "..."), config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "Featured answer"),
            "Featured answer COW: not present in the grid.",
        )
        self.assertEqual(_lines(text, "  Shaded cells"), [])

    def test_reports_every_featured_answer_in_the_order_given(self) -> None:
        # Two pins crossing at the corner, given DOWN first. Each gets its own
        # line pair, in flag order rather than grid scan order, which would
        # put the ACROSS entry first and hide an implementation that sorted.
        config = _config(
            features=(
                cw_feature.Feature("COW", cw_feature.Anchor(0, 0, cw_grid.DOWN)),
                cw_feature.Feature("CAT", cw_feature.Anchor(0, 0, cw_grid.ACROSS)),
            )
        )
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(
            _lines(text, "Featured answer"),
            [
                "Featured answer COW: down, (0, 0) to (2, 0).",
                "Featured answer CAT: across, (0, 0) to (0, 2).",
            ],
        )
        self.assertEqual(
            _lines(text, "  Shaded cells"),
            [
                "  Shaded cells, 0-based (row, column): (0, 0), (1, 0), (2, 0)",
                "  Shaded cells, 0-based (row, column): (0, 0), (0, 1), (0, 2)",
            ],
        )

    def test_omits_the_block_when_no_answer_was_nominated(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(_lines(text, "Featured answer"), [])


class TestThemes(unittest.TestCase):
    """The theme block: per-theme placed counts against the floor, plus a verdict."""

    def test_reports_a_theme_count_against_the_floor(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(_line(text, "Themes ("), "Themes (floor 1 per theme):")
        self.assertEqual(_line(text, "  Pets:"), "  Pets: 2 placed, floor 1 - met")
        self.assertEqual(_line(text, "  Food:"), "  Food: 0 placed, floor 1 - short")

    def test_lists_every_declared_theme_in_bank_order(self) -> None:
        # An ordered slice, not two prefix lookups concatenated: the latter
        # rebuilds the order it claims to check. This also pins the mixed
        # met/short rendering as one block rather than as two isolated lines.
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(
            _block_after(text, "Themes (floor 1 per theme):", 2),
            ["  Pets: 2 placed, floor 1 - met", "  Food: 0 placed, floor 1 - short"],
        )

    def test_marks_a_theme_short_of_the_floor(self) -> None:
        config = _config(min_entries_per_theme=3)
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(_line(text, "  Pets:"), "  Pets: 2 placed, floor 3 - short")

    def test_counts_declared_themes_not_the_theme_floor(self) -> None:
        # The denominator is how many themes the bank declares (2), which is a
        # different number from --min-themes (1). A fixture where they coincide
        # cannot tell the two apart, and the report would then claim a bank
        # declaring two themes had declared one.
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(len(_bank().themes), 2)
        self.assertEqual(_config().min_themes, 1)
        self.assertEqual(
            _line(text, "1 of 2"), "1 of 2 declared themes reach the floor - floor met."
        )

    def test_states_the_floor_verdict_when_it_is_missed(self) -> None:
        config = _config(min_entries_per_theme=3)
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [])
        self.assertEqual(
            _line(text, "0 of 2"),
            "0 of 2 declared themes reach the floor - floor NOT met.",
        )

    def test_says_so_when_the_bank_declares_no_themes(self) -> None:
        bank = cw_bank.Bank(themes={}, entries=(cw_bank.BankEntry("CAT", None, None),))
        config = _config(min_themes=0)
        text = cw_report.render_report(
            _outcome(bank=bank, config=config), bank, config, []
        )
        self.assertEqual(_line(text, "Themes"), "Themes: none declared in the bank.")


class TestUnplaced(unittest.TestCase):
    """The unplaced answers, annotated where the reason is knowable."""

    def test_annotates_an_answer_too_long_for_the_grid(self) -> None:
        # ELEPHANTINE cannot fit a 3x3 in any orientation; saying so beats
        # leaving the operator to compare lengths by eye.
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(_line(text, "Unplaced answers"), "Unplaced answers (2):")
        self.assertEqual(
            _line(text, "  ELEPHANTINE"),
            "  ELEPHANTINE - 11 letters, too long for a 3x3 grid",
        )

    def test_states_a_non_square_grid_rows_before_cols(self) -> None:
        # The annotation names the grid on a second axis-ordered rendering, and
        # a square fixture cannot tell "2x4" from "4x2" any more than the grid
        # line can.
        config = _config(rows=2, cols=4, max_blocked=60.0, min_themes=0)
        text = cw_report.render_report(
            _outcome(("CAT.", "O..."), config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "  ELEPHANTINE"),
            "  ELEPHANTINE - 11 letters, too long for a 2x4 grid",
        )

    def test_does_not_claim_a_fitting_answer_was_too_long(self) -> None:
        # COW fits a 3x3 perfectly well, so "too long" would be a false reason.
        # The honest annotation is the weaker one: merely "did not fit".
        text = cw_report.render_report(
            _outcome(("CAT", "...", "...")), _bank(), _config(), []
        )
        self.assertEqual(_line(text, "  COW"), "  COW - 3 letters, did not fit")

    def test_says_none_when_every_entry_is_in_the_grid(self) -> None:
        bank = cw_bank.Bank(themes={}, entries=(cw_bank.BankEntry("CAT", None, None),))
        config = _config(min_themes=0)
        text = cw_report.render_report(
            _outcome(bank=bank, config=config), bank, config, []
        )
        self.assertEqual(
            _line(text, "Unplaced answers"),
            "Unplaced answers: none - every bank entry is in the grid.",
        )


class TestDropped(unittest.TestCase):
    """Entries the excluded-terms screen removed, listed and counted."""

    def test_lists_entries_dropped_by_the_screen_in_order(self) -> None:
        # A silent drop would make "placed 3 of 5" a lie about a number the
        # operator supplied. Asserted as an ordered slice: gathering the two
        # lines by prefix and concatenating them would rebuild the order.
        text = cw_report.render_report(
            _outcome(),
            _bank(),
            _config(),
            [("BADWORD", "matched --excluded-terms"), ("WORSE", "matched a prefix")],
        )
        self.assertEqual(_line(text, "Dropped by"), "Dropped by --excluded-terms (2):")
        self.assertEqual(
            _block_after(text, "Dropped by --excluded-terms (2):", 2),
            [
                "  BADWORD - matched --excluded-terms",
                "  WORSE - matched a prefix",
            ],
        )

    def test_omits_the_block_when_nothing_was_dropped(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(_lines(text, "Dropped by"), [])


class TestLengthShortage(unittest.TestCase):
    """For each length, how many the bank holds and how many were placed."""

    def test_reports_bank_and_placed_counts_per_length(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(_line(text, "Shortage by"), "Shortage by word length:")
        self.assertEqual(_line(text, "  3 letters"), "  3 letters: 4 in bank, 3 placed")
        self.assertEqual(
            _line(text, "  11 letters"), "  11 letters: 1 in bank, 0 placed"
        )

    def test_orders_lengths_shortest_first(self) -> None:
        # Length 11 sorted as a string would come first; the order below is what
        # proves the sort is numeric, and it is deterministic.
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(
            _block_after(text, "Shortage by word length:", 2),
            ["  3 letters: 4 in bank, 3 placed", "  11 letters: 1 in bank, 0 placed"],
        )


class TestShortfall(unittest.TestCase):
    """The closing shortfall line, in cells and in answers."""

    def test_states_the_cells_and_answers_the_density_still_needs(self) -> None:
        # 5x5 = 25 cells; a 45.0% ceiling allows 11 blocked, so 14 must be
        # filled and only 3 are. 11 more cells, at up to 5 letters an answer,
        # is 3 more answers: arithmetic with a non-trivial value in every
        # term, so a wrong divisor or a dropped term cannot pass unnoticed.
        config = _config(rows=5, cols=5, min_themes=0)
        rows = ("CAT..", ".....", ".....", ".....", ".....")
        text = cw_report.render_report(
            _outcome(rows, config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "Density shortfall"),
            "Density shortfall: 11 more filled cells to reach the requested 45.0% "
            "blocked ceiling - roughly 3 more answers of up to 5 letters.",
        )

    def test_measures_against_the_longest_line_not_the_width(self) -> None:
        # Arithmetic on a non-square grid, not a label: an 8x3 grid holds
        # 8-letter downs, so quoting the width would advise the operator to add
        # 3-letter answers, and would say 4 of them rather than 2. 24 cells,
        # a 45.0% ceiling allowing 10 blocked, 3 filled: 11 more cells, at up to
        # 8 letters an answer, is 2 answers.
        config = _config(rows=8, cols=3, min_themes=0)
        rows = ("CAT", "...", "...", "...", "...", "...", "...", "...")
        text = cw_report.render_report(
            _outcome(rows, config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "Density shortfall"),
            "Density shortfall: 11 more filled cells to reach the requested 45.0% "
            "blocked ceiling - roughly 2 more answers of up to 8 letters.",
        )

    def test_says_none_when_the_ceiling_is_already_met(self) -> None:
        text = cw_report.render_report(_outcome(), _bank(), _config(), [])
        self.assertEqual(
            _line(text, "Density shortfall"),
            "Density shortfall: none - the grid is already within the requested "
            "45.0% blocked ceiling.",
        )

    def test_counts_the_ceilings_allowance_exactly(self) -> None:
        # 18.4% of 375 cells is exactly 69 blocked, but 375 * 18.4 / 100 is
        # 68.99999999999999 in floating point, whose floor of 68 asked for one
        # filled cell more than the ceiling needs. 70 are blocked here.
        config = _config(rows=15, cols=25, max_blocked=18.4, min_themes=0)
        rows = ("C" * 25,) * 12 + ("C" * 5 + "." * 20,) + ("." * 25,) * 2
        text = cw_report.render_report(
            _outcome(rows, config=config), _bank(), config, []
        )
        self.assertEqual(
            _line(text, "Density shortfall"),
            "Density shortfall: 1 more filled cells to reach the requested 18.4% "
            "blocked ceiling - roughly 1 more answers of up to 25 letters.",
        )


class TestIslands(unittest.TestCase):
    """The island block: named when laid, said plainly when none qualified."""

    def test_names_each_island_letter_and_its_cell(self) -> None:
        config = dataclasses.replace(_config(), island_letters=("A",))
        text = cw_report.render_report(
            _outcome(config=config), _bank(), config, [], ((0, 0, "A"), (2, 4, "I"))
        )
        self.assertEqual(
            _line(text, "Islands"),
            "Islands (lone letters in no entry, laid after the grid was chosen): "
            "A at (0, 0), I at (2, 4).",
        )

    def test_says_so_when_island_letters_found_no_island(self) -> None:
        # Asked for and not found is a different fact from not asked for, and a
        # silent report would leave the operator guessing which happened.
        config = dataclasses.replace(_config(), island_letters=("A",))
        text = cw_report.render_report(_outcome(config=config), _bank(), config, [], ())
        self.assertEqual(
            _line(text, "Islands"),
            "Islands: none, since no blocked cell touches a letter only at a corner.",
        )

    def test_names_an_island_the_floor_declined_under_those_laid(self) -> None:
        config = dataclasses.replace(_config(), island_letters=("A",))
        text = cw_report.render_report(
            _outcome(config=config),
            _bank(),
            config,
            [],
            ((0, 0, "A"),),
            declined=((2, 4, "I"),),
        )
        laid = (
            "Islands (lone letters in no entry, laid after the grid was chosen): "
            "A at (0, 0)."
        )
        self.assertEqual(
            _block_after(text, laid, 1),
            [
                "  Not laid, as each would take the grid under the requested 10.0% "
                "floor: (2, 4)."
            ],
        )

    def test_says_none_was_laid_when_the_floor_declined_every_island(self) -> None:
        # "No blocked cell touches a letter only at a corner" would be false:
        # one does, and --min-blocked is why it holds no letter.
        config = dataclasses.replace(_config(), island_letters=("A",))
        text = cw_report.render_report(
            _outcome(config=config), _bank(), config, [], (), declined=((0, 0, "A"),)
        )
        self.assertEqual(
            _line(text, "Islands"),
            "Islands: none laid, since each would take the grid under the requested "
            "10.0% floor: (0, 0).",
        )


if __name__ == "__main__":
    unittest.main()
