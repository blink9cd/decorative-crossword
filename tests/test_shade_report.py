"""Grouped suite: what `shade` prints, in both of its modes.

The report is this subcommand's product on stdout, exactly as the fill report
is `fill`'s: a ranked opinion plus the accounting behind it. Two things are
pinned here beyond the wording. First, the counts have to add up: a headline
saying 57 candidates out of 1332 words is only meaningful beside the reasons
the other 1275 did not qualify, and a block that quietly stopped counting one
of them would leave a plausible-looking report that is wrong. Second, the
placement report has to name the cells in both the project's own
`(row, column)` convention and a paste-ready form, because a caller who cannot
paste them has not been given the answer.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import unittest
from typing import cast

import cw_config
import cw_grid
import cw_shade
import cw_shade_report

#: A grid that spells CAT cleanly, one letter per row, and DOG badly, three
#: adjacent cells of one row, so a single fixture reaches both ends of the ranking.
ROWS = ("CAT..", ".A...", "..T..", "DOG..")


#: The `--cell` default, taken from the one place that owns it rather than
#: written out again: `cw_config` says a default lives in `DEFAULTS` exactly
#: once. `cast` is how every other reader of that `Mapping[str, object]`
#: narrows a value.
_DEFAULT_CELL = cast(int, cw_config.DEFAULTS["cell"])


def _config(
    *,
    min_length: int = 2,
    top: int = 0,
    exclude_grid_answers: bool = False,
    word: str | None = None,
    cell: int = _DEFAULT_CELL,
) -> cw_config.ShadeConfig:
    """A `shade` configuration, with any field overridden by keyword.

    Typed keyword parameters rather than a `**overrides` mapping, for the
    reason `svg_fixtures.request` gives: an untyped splat would need a mypy
    suppression, and a suppression with no cause is exactly what this project
    does not ship.
    """
    return cw_config.ShadeConfig(
        min_length=min_length,
        top=top,
        exclude_grid_answers=exclude_grid_answers,
        word=word,
        cell=cell,
    )


class TestSearchReport(unittest.TestCase):
    """The ranked candidate report and the accounting under it."""

    def _report(
        self,
        words: tuple[str, ...],
        *,
        min_length: int = 2,
        top: int = 0,
        exclude_grid_answers: bool = False,
    ) -> str:
        """Search `words` against ROWS under one configuration, and render it."""
        config = _config(
            min_length=min_length,
            top=top,
            exclude_grid_answers=exclude_grid_answers,
        )
        result = cw_shade.search_hidden_words(
            ROWS,
            words,
            min_length=config.min_length,
            exclude_grid_answers=config.exclude_grid_answers,
        )
        return cw_shade_report.render_search_report(ROWS, result, config, ())

    def test_the_headline_names_the_grid_and_its_lettered_cells(self) -> None:
        report = self._report(("CAT",))
        self.assertIn("Grid 4x5", report)
        self.assertIn("8 lettered cells", report)

    def test_each_candidate_line_carries_length_rows_and_clustering(self) -> None:
        report = self._report(("CAT",))
        self.assertIn("CAT - 3 letters, 3 row(s) spanned, clustering 0", report)

    def test_candidates_are_listed_best_first(self) -> None:
        report = self._report(("CAT", "DOG"))
        # DOG's three letters have one home each, all in row 3 and adjacent,
        # so it is the clustered one and must come second.
        self.assertLess(report.index("CAT -"), report.index("DOG -"))

    def test_top_limits_the_list_and_says_so(self) -> None:
        report = self._report(("CAT", "DOG"), top=1)
        self.assertIn("showing 1 of 2", report)
        self.assertNotIn("DOG -", report)

    def test_a_top_of_zero_shows_every_candidate(self) -> None:
        report = self._report(("CAT", "DOG"), top=0)
        self.assertIn("DOG -", report)
        self.assertNotIn("showing", report)

    def test_the_counts_account_for_every_word_searched(self) -> None:
        """Candidates plus every named exclusion must equal the words handed in.

        A block that stopped counting one reason would leave a report that
        looks right and is wrong, which is the one failure a reader cannot
        catch by eye.
        """
        words = ("CAT", "DOG", "AT", "ZEBRA")
        config = _config(min_length=3)
        result = cw_shade.search_hidden_words(
            ROWS,
            words,
            min_length=config.min_length,
            exclude_grid_answers=config.exclude_grid_answers,
        )
        accounted = (
            len(result.candidates)
            + result.too_short
            + result.unspellable
            + len(result.excluded_answers)
        )
        self.assertEqual(accounted, len(words))
        report = cw_shade_report.render_search_report(ROWS, result, config, ())
        self.assertIn(f"{len(words)} distinct words", report)
        self.assertIn("1 shorter than 3 letters", report)
        self.assertIn("1 not spellable", report)

    def test_excluded_grid_answers_are_named_not_only_counted(self) -> None:
        report = self._report(("CAT", "DOG"), exclude_grid_answers=True)
        self.assertIn("Already answers in this grid (2)", report)
        self.assertIn("CAT", report)
        self.assertIn("DOG", report)

    def test_the_excluded_block_is_absent_when_the_flag_is_off(self) -> None:
        self.assertNotIn("Already answers in this grid", self._report(("CAT",)))

    def test_skipped_word_list_lines_are_named_with_their_reason(self) -> None:
        config = _config()
        result = cw_shade.search_hidden_words(
            ROWS, ("CAT",), min_length=2, exclude_grid_answers=False
        )
        report = cw_shade_report.render_search_report(
            ROWS, result, config, (("WELL-KNOWN", "holds a character outside A-Z"),)
        )
        self.assertIn("Skipped word-list lines (1)", report)
        self.assertIn("WELL-KNOWN - holds a character outside A-Z", report)

    def test_a_miss_the_floor_did_not_cause_leaves_the_floor_alone(self) -> None:
        """A lower `--min-length` only readmits words the floor turned away.

        ZEBRA clears this floor and is simply unspellable here, so the floor
        removed nothing and advising a lower one is advice that cannot help:
        the same false remedy the exclusion case below is guarded against.
        """
        report = self._report(("ZEBRA",), min_length=cw_grid.MIN_RUN + 1)
        self.assertIn("NO HIDDEN WORD FOUND", report)
        self.assertNotIn("--min-length", report)
        self.assertIn("supply a longer word list", report)

    def test_a_miss_the_floor_caused_offers_a_lower_one(self) -> None:
        """Each word is spellable in ROWS and was refused for its length alone.

        `validate_shade_config` accepts no floor under MIN_RUN, so MIN_RUN + 1
        is the lowest floor this advice can be followed from, and the MIN_RUN
        guard must let it through there. A second floor above it is checked as
        well, each naming its own number: at a single floor, a guard or a
        message fixed to that one number would pass unnoticed.
        """
        cases = ((cw_grid.MIN_RUN + 1, "AT"), (cw_grid.MIN_RUN + 2, "CAT"))
        for floor, word in cases:
            with self.subTest(floor=floor, word=word):
                report = self._report((word, "ZEBRA"), min_length=floor)
                self.assertIn("NO HIDDEN WORD FOUND", report)
                self.assertIn(f"lower --min-length below {floor}", report)

    def test_the_floor_is_offered_only_when_there_is_room_below_it(self) -> None:
        """`validate_shade_config` refuses a floor under MIN_RUN.

        So a run already at the floor cannot take this advice (following it
        would exit 2) even when a word fell under it. Such a word cannot come
        out of `load_word_list`, which screens anything under MIN_RUN, so it is
        handed to the search directly: the guard is on the floor, not on how
        the word arrived.
        """
        report = self._report(("A", "ZEBRA"), min_length=cw_grid.MIN_RUN)
        # The word did fall short, so only the floor guard can withhold the advice.
        self.assertIn(f"1 shorter than {cw_grid.MIN_RUN} letters", report)
        self.assertIn("NO HIDDEN WORD FOUND", report)
        self.assertNotIn("lower --min-length", report)
        self.assertIn("supply a longer word list", report)

    def test_the_no_candidate_knobs_offer_the_exclusion_only_when_it_bit(self) -> None:
        """Offering a flag that removed nothing would be advice that cannot help."""
        without = self._report(("ZEBRA",))
        self.assertNotIn("--exclude-grid-answers", without)
        with_exclusion = self._report(("CAT", "DOG"), exclude_grid_answers=True)
        self.assertIn("--exclude-grid-answers", with_exclusion)

    def test_a_report_with_candidates_carries_no_miss_verdict(self) -> None:
        self.assertNotIn("NO HIDDEN WORD FOUND", self._report(("CAT",)))


class TestPlacementReport(unittest.TestCase):
    """The single-word report: where to shade, and whether it is worth shading."""

    def _placement(self, rows: tuple[str, ...], word: str) -> cw_shade.Placement:
        placement = cw_shade.place_word(rows, word)
        assert placement is not None
        return placement

    def test_names_the_word_its_cells_and_its_score(self) -> None:
        report = cw_shade_report.render_placement_report(self._placement(ROWS, "CAT"))
        self.assertIn("Hidden word CAT: 3 cells across 3 row(s), clustering 0.", report)

    def test_lists_the_cells_in_the_projects_own_coordinate_convention(self) -> None:
        report = cw_shade_report.render_placement_report(self._placement(ROWS, "CAT"))
        self.assertIn(
            "Shaded cells, 0-based (row, column): (0, 0), (1, 1), (2, 2)", report
        )

    def test_offers_a_paste_form_that_is_valid_json(self) -> None:
        """Parsed rather than string-matched: the point is that it pastes."""
        report = cw_shade_report.render_placement_report(self._placement(ROWS, "CAT"))
        line = next(line for line in report.splitlines() if "Paste form" in line)
        payload = json.loads(line.split(":", 1)[1].strip())
        self.assertEqual(payload, [[0, 0], [1, 1], [2, 2]])

    def test_a_scattered_placement_reads_as_a_hidden_word(self) -> None:
        report = cw_shade_report.render_placement_report(self._placement(ROWS, "CAT"))
        self.assertIn("reads as a hidden word", report)

    def test_a_bunched_placement_is_called_out_as_one(self) -> None:
        """The finding a person cannot eyeball, stated in words as well.

        DOG's letters have one home each, consecutive in the last row, so the
        shading would read as a corrupted answer, and the report has to say
        so rather than leaving a bare number the reader has no scale for.
        """
        report = cw_shade_report.render_placement_report(self._placement(ROWS, "DOG"))
        self.assertIn("corrupted answer", report)

    def test_the_verdict_turns_on_one_neighboring_step(self) -> None:
        """The threshold is derived from the penalty table, not a loose number.

        A placement whose clustering reaches the cost of a single same-row
        neighboring step has bunched, whichever steps paid for it; one below
        it has not.
        """
        self.assertEqual(
            cw_shade.NEIGHBORING_STEP_PENALTY,
            cw_shade.SAME_ROW_ADJACENT_PENALTY + cw_shade.TOUCHING_PENALTY,
        )


if __name__ == "__main__":
    unittest.main()
