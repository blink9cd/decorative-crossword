"""Tests for the fill report under --source: its source block, and what it counts.

The vocabulary blocks describe the --bank file, so an entry kept from the source
is never counted there; the theme block and the verdict judge the grid, so it is.
"""

import dataclasses
import unittest

import cw_accept
import cw_bank
import cw_board
import cw_report
import cw_search

from tests.report_fixtures import DEFAULT_ROWS, make_bank, make_config, make_outcome

#: CAT across and COW down from the corner: five letters, two entries.
_START = ("CAT", "O..", "W..")

#: CA across and COW down from the corner. CA is a partial run: CAT completes it.
_HALF_CAT = ("CA.", "O..", "W..")

#: `_HALF_CAT` with CA completed as CAT.
_CAT_FINISHED = ("CAT", "O..", "W..")

#: The heading of the report's closing block, the knob for each missed constraint.
_KNOBS = "What would clear each:"


def _stray_knob(row: int, col: int) -> str:
    """The knob line, as the report indents it, for a stray at (row, col)."""
    return f"  add a bank answer that crosses ({row}, {col}), or remove that letter from --source"


def _knob_block(text: str) -> list[str]:
    """Every line under the knob heading: the remedy block closes the report."""
    body = text.splitlines()
    return body[body.index(_KNOBS) + 1 :]


def _report(
    kept: tuple[str, ...] = (),
    start: tuple[str, ...] = _START,
    rows: tuple[str, ...] = DEFAULT_ROWS,
) -> str:
    """The report for `rows` under a source of `start`, keeping `kept`."""
    config = make_config(start=start)
    outcome = make_outcome(rows, config=config)
    return cw_report.render_report(outcome, make_bank(), config, (), kept=kept)


class TestSourceBlock(unittest.TestCase):
    """What the report says about the grid it started from."""

    def test_counts_the_fixed_letters_entries_and_lone_letters(self) -> None:
        self.assertIn(
            "From --source: 5 fixed letter(s) in 2 entry(s), 0 lone letter(s).",
            _report().splitlines(),
        )

    def test_names_the_entries_kept_from_the_source(self) -> None:
        self.assertIn(
            "Kept from --source, not in the bank (1): COW.",
            _report(kept=("COW",)).splitlines(),
        )

    def test_says_nothing_without_a_source(self) -> None:
        self.assertNotIn("--source", _report(start=()))

    def test_counts_a_partial_run_apart_from_the_entries(self) -> None:
        # CA is no bank answer, so it is no entry of the source: counted as an
        # entry, the line would claim two where the source held one.
        self.assertIn(
            "From --source: 4 fixed letter(s) in 1 entry(s), 1 partial run(s), "
            "0 lone letter(s).",
            _report(start=_HALF_CAT, rows=_CAT_FINISHED).splitlines(),
        )

    def test_names_each_completed_run_with_the_answer_now_covering_it(self) -> None:
        self.assertIn(
            "Completed from --source (1): CA as CAT across at (0, 0).",
            _report(start=_HALF_CAT, rows=_CAT_FINISHED).splitlines(),
        )

    def test_names_no_completion_on_a_grid_that_does_not_hold_one(self) -> None:
        # The empty board an unfinished walk writes: the source block still
        # counts what was handed in, and claims no completion.
        report = _report(start=_HALF_CAT, rows=("...", "...", "..."))
        self.assertIn("1 partial run(s)", report)
        self.assertNotIn("Completed from --source", report)


def _with_answers(bank: cw_bank.Bank, *answers: str) -> cw_bank.Bank:
    """`bank` with each of `answers` added, unthemed."""
    added = tuple(cw_bank.BankEntry(answer, None, None) for answer in answers)
    return dataclasses.replace(bank, entries=bank.entries + added)


class TestAbsorbedEntries(unittest.TestCase):
    """Each source entry the grid grew is named with the answer now covering it."""

    def test_names_an_entry_grown_into_a_longer_answer(self) -> None:
        bank = _with_answers(make_bank(), "CATS")
        config = make_config(rows=3, cols=4, start=("CAT.", "O...", "W..."))
        outcome = make_outcome(("CATS", "O...", "W..."), bank=bank, config=config)
        report = cw_report.render_report(outcome, bank, config, ())
        self.assertIn(
            "Absorbed from --source (1): CAT into CATS across at (0, 0).",
            report.splitlines(),
        )

    def test_names_both_entries_a_weld_joined(self) -> None:
        bank = cw_bank.Bank(
            themes={},
            entries=tuple(
                cw_bank.BankEntry(answer, None, None)
                for answer in ("SUN", "LOWER", "SUNFLOWER")
            ),
        )
        config = make_config(rows=1, cols=9, start=("SUN.LOWER",), min_themes=0)
        outcome = make_outcome(("SUNFLOWER",), bank=bank, config=config)
        report = cw_report.render_report(outcome, bank, config, ())
        self.assertIn(
            "Absorbed from --source (2): SUN and LOWER into SUNFLOWER across at (0, 0).",
            report.splitlines(),
        )

    def test_names_nothing_while_every_entry_stands_or_on_an_empty_board(self) -> None:
        # A completed partial run is no absorbed entry: CA was never an entry.
        for report in (
            _report(),
            _report(start=_HALF_CAT, rows=_CAT_FINISHED),
            _report(rows=("...", "...", "...")),
        ):
            with self.subTest(report=report):
                self.assertNotIn("Absorbed from --source", report)

    def test_the_chosen_line_names_the_level_only_under_the_flag(self) -> None:
        base = dataclasses.replace(make_config(start=_START), look_ahead=10)
        for absorb, expected in ((True, True), (False, False)):
            with self.subTest(absorb=absorb):
                config = dataclasses.replace(base, absorb_entries=absorb)
                outcome = make_outcome(config=config)
                report = cw_report.render_report(outcome, make_bank(), config, ())
                self.assertEqual(
                    "then themed entries, then fewest absorbed --source entries."
                    in report,
                    expected,
                )


class TestKeptEntriesInTheCounts(unittest.TestCase):
    """The headline describes the bank file; the theme block describes the grid."""

    def test_the_headline_counts_only_the_bank_files_entries(self) -> None:
        lines = _report(kept=("COW",)).splitlines()
        self.assertIn("Placed 2 of 4 bank entries.", lines)
        self.assertIn("  3 letters: 3 in bank, 2 placed", lines)

    def test_the_theme_block_still_counts_a_kept_entry(self) -> None:
        self.assertIn(
            "  Pets: 2 placed, floor 1 - met", _report(kept=("COW",)).splitlines()
        )

    def test_a_stray_names_the_knob_that_clears_it(self) -> None:
        report = _report(start=("Q..", "...", "..."), rows=("Q..", "...", "CAT"))
        self.assertIn(
            "  the fixed letter Q at (0, 0) belongs to no entry", report.splitlines()
        )
        self.assertIn(
            "  add a bank answer that crosses (0, 0), or remove that letter from --source",
            report.splitlines(),
        )


class TestKeptEntriesUnderRatings(unittest.TestCase):
    """The worst-rating line describes the bank the grid was scored on."""

    def test_a_kept_entry_is_counted_among_the_unrated_answers(self) -> None:
        """COW, kept from the source, is the one unrated answer at the worst.

        A source document cannot carry a rating, so an entry kept from it is
        always unrated and counts as the neutral 3. Traced by hand: the grid's
        entries are CAT (rated 4), WET (rated 5) and COW (kept, unrated, so 3).
        The worst is therefore 3; no rated entry holds it, so nothing is named,
        and the one unrated answer, COW, is counted.
        """
        bank = make_bank()
        rated = {"CAT": 4, "WET": 5}
        bank = dataclasses.replace(
            bank,
            entries=tuple(
                dataclasses.replace(entry, rating=rated.get(entry.answer))
                for entry in bank.entries
            ),
        )
        config = make_config(start=_START)
        outcome = make_outcome(bank=bank, config=config)
        report = cw_report.render_report(outcome, bank, config, (), kept=("COW",))
        self.assertIn(
            "Worst rating in the grid: 3 (1 unrated answer(s), which count as 3).",
            report.splitlines(),
        )


class TestUnplacedUnderASource(unittest.TestCase):
    """The unplaced block describes the --bank file, not the entries kept."""

    def test_an_empty_bank_file_says_so_when_every_run_is_kept(self) -> None:
        # Counted over the full bank, the line would read "every bank entry is
        # in the grid": a success claim about a --bank file that held nothing.
        bank = cw_bank.Bank(
            themes={},
            entries=(
                cw_bank.BankEntry("CAT", None, None),
                cw_bank.BankEntry("COW", None, None),
            ),
        )
        config = make_config(start=_START, min_themes=0)
        outcome = make_outcome(_START, bank=bank, config=config)
        report = cw_report.render_report(outcome, bank, config, (), kept=("CAT", "COW"))
        self.assertIn(
            "Unplaced answers: none - the bank holds no answers.", report.splitlines()
        )


class TestStrayKnobs(unittest.TestCase):
    """Each stray the returned grid still holds gets its own knob."""

    def test_two_strays_get_their_knobs_in_row_major_order(self) -> None:
        # Z at (0, 2) and Q at (2, 0): column-major order would put Q first.
        start = ("..Z.", "....", "Q...", "....")
        rows = ("..Z.", "...C", "Q..A", "...T")
        config = make_config(rows=4, cols=4, start=start)
        report = cw_report.render_report(
            make_outcome(rows, config=config), make_bank(), config, ()
        )
        strays = [knob for knob in _knob_block(report) if "crosses" in knob]
        self.assertEqual(strays, [_stray_knob(0, 2), _stray_knob(2, 0)])

    def test_a_source_letter_the_grid_covers_gets_no_knob(self) -> None:
        # The source's C is a stray of the source, but CAT and COW now cross
        # it; only Q, still alone in the returned grid, needs clearing.
        config = make_config(start=("C..", "...", "..Q"))
        report = cw_report.render_report(
            make_outcome(("CAT", "O..", "W.Q"), config=config),
            make_bank(),
            config,
            (),
        )
        self.assertEqual(_knob_block(report), [_stray_knob(2, 2)])


class TestKnobsWhenTheGridHoldsNoEntry(unittest.TestCase):
    """A refusal suppresses every knob; a source grid without entries does not."""

    def test_a_pre_flight_refusal_under_a_source_offers_no_knob(self) -> None:
        # The refusal writes the source, which holds CAT and a stray Q. The
        # missed list is the refusal's reason alone, so a knob for Q (or for
        # the source's density) would clear a constraint nobody named.
        bank = make_bank()
        config = make_config(start=("CAT", "...", "..Q"), min_themes=3)
        refusals = cw_accept.preflight(bank, config)
        # Built the way `cw_search.search` builds a refusal, from the same calls.
        refusal = cw_search.SearchOutcome(
            rows=cw_board.start_rows(config),
            placed=(),
            conforming=False,
            missed=refusals,
            steps=0,
        )
        report = cw_report.render_report(refusal, bank, config, ())
        self.assertEqual(len(refusals), 1)
        self.assertNotIn(_KNOBS, report)
        self.assertNotIn("crosses", report)

    def test_a_source_holding_only_a_stray_still_names_its_knob(self) -> None:
        # No answer crosses Q, so the grid holds no entry at all; the missed
        # list names the stray, and the knob block says how to clear it. The
        # density and theme knobs stay out: arithmetic on a grid holding no
        # entry describes nothing an operator can act on.
        start = ("Q..", "...", "...")
        config = make_config(start=start)
        report = cw_report.render_report(
            make_outcome(start, config=config), make_bank(), config, ()
        )
        self.assertIn(
            "  the fixed letter Q at (0, 0) belongs to no entry", report.splitlines()
        )
        self.assertIn(_KNOBS, report.splitlines())
        self.assertEqual(_knob_block(report), [_stray_knob(0, 0)])

    def test_a_source_grid_holding_no_entry_keeps_its_feature_knobs(self) -> None:
        # The missed list names CAT as absent, so the block must say how to
        # place it; only the density and theme figures of an empty grid go.
        start = ("Q..", "...", "...")
        config = make_config(feature="CAT", start=start)
        report = cw_report.render_report(
            make_outcome(start, config=config), make_bank(), config, ()
        )
        self.assertIn(
            "  the featured answer 'CAT' is not in the grid", report.splitlines()
        )
        self.assertIn(_KNOBS, report.splitlines())
        # Growing is legal beside --source, so the size half of the knob stays.
        self.assertEqual(
            _knob_block(report),
            [
                "  place CAT by raising --time-budget or --max-steps, or grow "
                "--rows / --cols",
                _stray_knob(0, 0),
            ],
        )


#: `_START` at the top-left of a 3x5 canvas, as `fill --source --cols 5` places it.
_START_WIDE = ("CAT..", "O....", "W....")

#: `_START` at the top-left of a 4x4 canvas, grown in both dimensions.
_START_GROWN = ("CAT.", "O...", "W...", "....")


def _grown_report(
    start: tuple[str, ...], *, max_blocked: float = 45.0, min_themes: int = 1
) -> str:
    """The report for `start` as its own grid, placed there from a 3x3 source."""
    config = dataclasses.replace(
        make_config(
            rows=len(start),
            cols=len(start[0]),
            start=start,
            max_blocked=max_blocked,
            min_themes=min_themes,
        ),
        source_size=(3, 3),
    )
    outcome = make_outcome(start, config=config)
    return cw_report.render_report(outcome, make_bank(), config, ())


class TestAGrownCanvas(unittest.TestCase):
    """A source placed on a larger canvas says so, straight under what it held."""

    def test_names_the_sources_size_and_where_it_sits(self) -> None:
        lines = _grown_report(_START_WIDE).splitlines()
        held = "From --source: 5 fixed letter(s) in 2 entry(s), 0 lone letter(s)."
        self.assertEqual(
            lines[lines.index(held) + 1],
            "Grown from --source: its 3x3 grid sits at (0, 0) of this 3x5 grid.",
        )

    def test_a_source_at_its_own_size_names_no_growth(self) -> None:
        self.assertNotIn("Grown from --source", _report())


class TestSizeKnobsUnderASource(unittest.TestCase):
    """No knob advises a size `fill` would refuse: never under the source's own."""

    def test_the_density_knob_under_a_source_stops_at_its_ceiling(self) -> None:
        # 4 of 9 cells blocked is 44.4%, over a 20.0% ceiling. `fill` refuses a
        # --rows or --cols under the source's own size, and this grid is the
        # source's size, so "or shrink" would advise a value turned away at exit 2.
        config = make_config(start=_START, max_blocked=20.0, min_themes=0)
        report = cw_report.render_report(
            make_outcome(_START, config=config), make_bank(), config, ()
        )
        self.assertEqual(
            _knob_block(report), ["  loosen --max-blocked to 44.5 or higher"]
        )

    def test_the_density_knob_names_only_a_dimension_grown_past_the_source(
        self,
    ) -> None:
        # 10 of 15 cells blocked is 66.7%. Only the columns grew, so only
        # --cols has room to shrink; --rows is already the source's.
        report = _grown_report(_START_WIDE, max_blocked=20.0, min_themes=0)
        self.assertEqual(
            _knob_block(report),
            ["  loosen --max-blocked to 66.7 or higher, or shrink --cols"],
        )

    def test_the_density_knob_names_both_dimensions_when_both_grew(self) -> None:
        # 11 of 16 cells blocked is 68.75%, rounded up to a figure that clears.
        report = _grown_report(_START_GROWN, max_blocked=20.0, min_themes=0)
        self.assertEqual(
            _knob_block(report),
            ["  loosen --max-blocked to 68.8 or higher, or shrink --rows / --cols"],
        )


if __name__ == "__main__":
    unittest.main()
