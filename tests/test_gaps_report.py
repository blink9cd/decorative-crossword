"""Grouped suite: what `gaps` prints, and the arithmetic a reader may trust.

The subcommand's human-facing product, on stdout, exactly as
`cw_shade_report.render_search_report` is `shade`'s. Two rules run through it,
both borrowed rather than re-decided:

- **The grid is authoritative.** Every figure is read off the rows and the
  candidates derived from them.
- **A count that is not accounted for is a count that misleads.** The headline
  splits the blocked cells it counts into tiers, and `TestAccounting` pins, with
  a mask and without, that those tiers add up to the blocked count it prints,
  so a reader can act on the headline instead of recounting the grid.

The report's own reason for existing is a third rule, and it is the one worth
testing hardest: a wall of coordinates is not a decision. `TestGrouping` pins
that two gaps wanting the same pattern share one line, because the operator's
unit of work is the word they have to think of, not the square it lands in.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import re
import unittest
from typing import cast

import cw_config
import cw_gaps
import cw_gaps_report
import cw_gaps_summary


#: 16 cells, 7 of them blocked. One gap absorbs HAY, one is an orphan, and the
#: other five are pure additions: one of each tier the report separates.
GRID = ("HAY.", "E...", "D...", "GIRL")

#: Pays the `Y?` demand at (1, 2) with the letter O, and nothing else.
VOCABULARY = frozenset({"YO"})

#: Four letters fit the `Y?` demand at (1, 2), which is more options than one
#: line should print: the report shows some and says how many it held back.
MANY_FILLS = frozenset({"YO", "YE", "YA", "YU"})

#: Pays `Y?` as above, and pays each of (1, 1)'s two demands separately (EX
#: for `E?`, AM for `A?`), with no letter paying both. That gap is a crossing.
CROSSING_VOCABULARY = frozenset({"YO", "EX", "AM"})

#: Two of GRID's seven blocked cells, (0, 3) and (1, 3), drawn out by a mask.
#: The headline then counts the other five, over the fourteen cells left.
TWO_MASKED = frozenset({(0, 3), (1, 3)})

#: Three gaps, at (0, 1) across and at (1, 0) and (1, 3) down, each demanding the
#: pattern `A?` and nothing else. The two directions share one ask, so the
#: report has a genuine chance to print one line or three.
SHARED_PATTERN = ("A..A", "....")


def _config(**overrides: object) -> cw_config.GapsConfig:
    """A `gaps` configuration at its defaults, with named fields overridden."""
    fields: dict[str, object] = {
        "top": cast(int, cw_config.DEFAULTS["top"]),
        "include_absorbing": False,
        "cell": cast(int, cw_config.DEFAULTS["cell"]),
        "masked": frozenset(),
    }
    fields.update(overrides)
    return cw_config.GapsConfig(**fields)  # type: ignore[arg-type]


def _render(
    rows: tuple[str, ...] = GRID,
    vocabulary: frozenset[str] = VOCABULARY,
    skipped: tuple[tuple[str, str], ...] = (),
    mask_file: str | None = None,
    **overrides: object,
) -> str:
    """Render one gaps report over `rows`, at the configuration given."""
    config = _config(**overrides)
    return cw_gaps_report.render_report(
        rows,
        cw_gaps.search_gaps(rows, vocabulary, config.masked),
        config,
        skipped,
        mask_file=mask_file,
    )


def _counts(
    rows: tuple[str, ...] = GRID, vocabulary: frozenset[str] = VOCABULARY
) -> dict[str, int]:
    """The tier split the headline prints."""
    return cw_gaps_summary.tier_counts(cw_gaps.search_gaps(rows, vocabulary))


def _lines_holding(report: str, needle: str) -> list[str]:
    """Every line of `report` containing `needle`."""
    return [line for line in report.splitlines() if needle in line]


class TestHeadline(unittest.TestCase):
    """Size, density and the tier split, before any list."""

    def test_names_the_grid_size(self) -> None:
        self.assertIn("4x4", _render())

    def test_names_the_blocked_count_and_percentage(self) -> None:
        self.assertIn("7 of 16 cells blocked, 43.8%", _render())

    def test_counts_masked_cells_apart_from_the_blocked_ones(self) -> None:
        # Masked, the two cells are still blocked (the grid did not change),
        # but they are no longer cells the operator could ever fill, so the
        # headline takes its count and percentage over what remains, 5 of 14,
        # and one line of their own, outside the indented tier list, says where
        # the other two went.
        headline = _render(masked=TWO_MASKED)
        masked = f"Not counted above: 2 blocked cell(s) {cw_gaps_summary.MASKED_TIER}."
        self.assertIn("5 of 14 cells blocked, 35.7%", headline)
        self.assertIn(masked, headline.splitlines())
        # "Above" is the tier list, so the line follows its last entry directly
        # and closes the headline block: printed any earlier, it would sit above
        # tiers it says it was not counted in.
        block = headline.split("\n\n")[0].splitlines()
        last_tier = max(i for i, line in enumerate(block) if line.startswith(" "))
        self.assertEqual(block[last_tier + 1 :], [masked])

    def test_names_no_masked_tier_without_a_mask(self) -> None:
        # A zero beside every other tier would tell an operator who gave no
        # picture about a feature they are not using.
        self.assertNotIn(cw_gaps_summary.MASKED_TIER, _render())

    def test_names_the_mask_file_when_one_was_given(self) -> None:
        self.assertIn(
            "From --mask shape.txt: 1 of 16 cells may never hold a letter.",
            _render(masked=frozenset({(0, 3)}), mask_file="shape.txt"),
        )

    def test_names_the_vocabulary_size(self) -> None:
        self.assertIn("1 answer", _render())

    def test_says_when_no_vocabulary_was_supplied(self) -> None:
        # A different sentence from "none of your words matched": one is about
        # the run's inputs, the other about the operator's bank.
        self.assertIn("no vocabulary", _render(vocabulary=frozenset()).lower())


class TestAccounting(unittest.TestCase):
    """Every blocked cell lands in exactly one tier, and every tier is printed."""

    def test_the_tiers_add_up_to_the_blocked_cells(self) -> None:
        self.assertEqual(sum(_counts().values()), 7)

    def test_under_a_mask_the_tiers_add_up_to_the_cells_left_blocked(self) -> None:
        # The five the operator could still fill: a masked cell is not a gap.
        search = cw_gaps.search_gaps(GRID, VOCABULARY, TWO_MASKED)
        self.assertEqual(sum(cw_gaps_summary.tier_counts(search).values()), 5)

    def test_the_printed_tiers_add_up_to_the_printed_headline(self) -> None:
        """Read off the report, because a reader checks what they can see.

        With and without a mask: the mask is where the two diverge, since the
        headline leaves masked cells out, and an indented tier list that counted
        them would total more than the count it sits under.
        """
        for masked in (frozenset(), TWO_MASKED):
            with self.subTest(masked=sorted(masked)):
                headline = _render(masked=masked).split("\n\n")[0].splitlines()
                blocked = re.search(r"(\d+) of \d+ cells blocked", headline[0])
                assert blocked is not None
                tiers = [
                    int(line.split()[0]) for line in headline if line.startswith(" ")
                ]
                self.assertEqual(sum(tiers), int(blocked.group(1)))

    def test_every_tier_label_appears_in_the_report(self) -> None:
        report = _render()
        for label in _counts():
            self.assertIn(label, report)

    def test_the_orphan_tier_is_counted(self) -> None:
        self.assertEqual(_counts()[cw_gaps_summary.ORPHAN_TIER], 1)

    def test_the_absorbing_tier_is_counted(self) -> None:
        self.assertEqual(_counts()[cw_gaps_summary.ABSORBING_TIER], 1)

    def test_a_ready_gap_is_counted_as_ready(self) -> None:
        self.assertEqual(_counts()[cw_gaps_summary.READY_TIER], 1)

    def test_a_crossing_counts_as_one_new_word_not_two(self) -> None:
        # (1, 1) is the crossing; (2, 2) and (2, 3) each miss one pattern
        # outright. Only (2, 1) genuinely needs two.
        counts = _counts(vocabulary=CROSSING_VOCABULARY)
        self.assertEqual(
            (
                counts[cw_gaps_summary.ONE_ANSWER_TIER],
                counts[cw_gaps_summary.TWO_ANSWER_TIER],
            ),
            (3, 1),
        )


def _headline_label(report: str, needle: str) -> str:
    """The one tier label in `report`'s headline holding `needle`, its count dropped."""
    headline = report.split("\n\n")[0].splitlines()
    labels = [line.split(maxsplit=1)[1] for line in headline if line.startswith(" ")]
    (label,) = [label for label in labels if needle in label]
    return label


def _headings(report: str) -> list[str]:
    """The first line of every block in `report` but the headline's."""
    return [block.splitlines()[0] for block in report.split("\n\n")][1:]


class TestOneWordingPerTier(unittest.TestCase):
    """A tier's headline label and its block's heading ask for the same thing.

    Read off one report that prints every block, so a heading worded apart from
    its label fails here however either is built: over `CROSSING_VOCABULARY`
    there is a ready gap, gaps needing one and two new answers, and (once
    asked for) the absorbing gap.
    """

    def setUp(self) -> None:
        self.report = _render(vocabulary=CROSSING_VOCABULARY, include_absorbing=True)

    def test_a_new_answer_is_called_an_answer_in_both_places(self) -> None:
        for count in ("one new answer", "two new answers"):
            with self.subTest(count):
                label = _headline_label(self.report, count)
                self.assertEqual(label, f"needing {count}")
                asked = label.removeprefix("needing ")
                self.assertIn(f"Needs {asked} - by pattern:", _headings(self.report))

    def test_the_ready_tier_reads_the_same_in_both_places(self) -> None:
        label = _headline_label(self.report, "ready")
        openings = [heading.split(" - ")[0] for heading in _headings(self.report)]
        self.assertIn(label.capitalize(), openings)

    def test_the_absorbing_tier_reads_the_same_in_all_three_places(self) -> None:
        label = _headline_label(self.report, "absorb")
        self.assertEqual(label, "that would absorb an existing answer")
        asked = label.removeprefix("that ")
        openings = [heading.split(" (")[0] for heading in _headings(self.report)]
        self.assertIn(asked.capitalize(), openings)
        hidden = _render(vocabulary=CROSSING_VOCABULARY)
        self.assertIn(f"1 gap {asked} and is not listed", hidden)

    def test_no_label_or_heading_asks_for_a_word(self) -> None:
        headline = self.report.split("\n\n")[0].splitlines()[1:]
        for line in (*headline, *_headings(self.report)):
            with self.subTest(line):
                self.assertNotRegex(line, r"\bwords?\b")


class TestReadyNow(unittest.TestCase):
    """A gap the operator can already pay for names the letter and the words."""

    def test_names_the_cell(self) -> None:
        self.assertIn("(1, 2)", _render())

    def test_names_the_letter_to_use(self) -> None:
        self.assertIn("take O", _render())

    def test_names_the_word_and_its_direction(self) -> None:
        self.assertIn("down YO", _render())

    def test_a_gap_with_many_letters_says_how_many_it_held_back(self) -> None:
        # An inventory is not a decision: the line invites a choice, so it
        # shows a few and counts the rest rather than printing all four.
        self.assertIn("more letter(s) fit here", _render(vocabulary=MANY_FILLS))

    def test_it_prints_fewer_lines_than_there_are_letters(self) -> None:
        report = _render(vocabulary=MANY_FILLS)
        self.assertLess(len(_lines_holding(report, "take ")), len(MANY_FILLS))

    def test_is_absent_when_nothing_is_ready(self) -> None:
        # An empty heading is noise, and the headline's tier count still says
        # zero, so nothing goes unreported by leaving the block out.
        self.assertNotIn("take ", _render(vocabulary=frozenset()))


class TestTheCrossing(unittest.TestCase):
    """A gap whose patterns are each matched but never together says so."""

    def test_the_line_says_no_letter_pays_both(self) -> None:
        report = _render(vocabulary=CROSSING_VOCABULARY)
        self.assertIn("no single letter", report)

    def test_it_is_not_reported_as_two_missing_words(self) -> None:
        # Overstating the cost would send the operator looking for a word they
        # do not need: one new answer in either pattern clears a crossing.
        report = _render(vocabulary=CROSSING_VOCABULARY)
        self.assertEqual(len(_lines_holding(report, "no single letter")), 1)


class TestGrouping(unittest.TestCase):
    """The unit of work is the word to think of, not the square it lands in."""

    def test_two_gaps_wanting_one_pattern_share_a_line(self) -> None:
        report = _render(rows=SHARED_PATTERN, vocabulary=frozenset())
        shared = [
            line
            for line in report.splitlines()
            if all(cell in line for cell in ("(0, 1)", "(1, 0)", "(1, 3)"))
        ]
        self.assertEqual(len(shared), 1)

    def test_the_shared_line_names_the_pattern_once(self) -> None:
        report = _render(rows=SHARED_PATTERN, vocabulary=frozenset())
        self.assertEqual(len(_lines_holding(report, "A?")), 1)

    def test_the_shared_line_says_how_many_gaps_it_serves(self) -> None:
        report = _render(rows=SHARED_PATTERN, vocabulary=frozenset())
        self.assertIn("3 gaps", report)


class TestAbsorbing(unittest.TestCase):
    """A fill that retires a curated answer is counted, and hidden until asked for."""

    def test_the_absorbing_pattern_is_not_listed_by_default(self) -> None:
        self.assertNotIn("HAY?", _render())

    def test_the_report_says_how_to_see_them(self) -> None:
        self.assertIn("--include-absorbing", _render())

    def test_the_flag_lists_them(self) -> None:
        self.assertIn("HAY?", _render(include_absorbing=True))

    def test_the_flag_names_what_each_would_retire(self) -> None:
        self.assertIn("retires HAY", _render(include_absorbing=True))

    def test_the_hint_is_absent_once_they_are_shown(self) -> None:
        # The heading still names the flag, which is how a reader knows why the
        # block is there; what goes away is the sentence offering to show them.
        self.assertNotIn("not listed", _render(include_absorbing=True))


class TestDensityAdvice(unittest.TestCase):
    """The report closes the loop: what to run so the search reaches for a gap."""

    def test_names_the_percentage_one_more_cell_would_reach(self) -> None:
        self.assertIn("37.5", _render())

    def test_names_the_flag_to_lower(self) -> None:
        self.assertIn("--max-blocked", _render())

    def test_the_suggested_ceiling_accepts_the_denser_grid(self) -> None:
        # Derived, not guessed: `fill` accepts at `blocked <= max_blocked`, so
        # a ceiling at the denser grid's own figure accepts that grid and
        # rejects today's. Rounded up to one decimal, because a ceiling rounded
        # down would refuse the very grid it was printed to ask for.
        ceiling = cw_gaps_summary.ceiling_for(blocked=7, total=16)
        self.assertGreaterEqual(ceiling, 6 / 16 * 100)
        self.assertLess(ceiling, 7 / 16 * 100)

    def test_a_grid_with_no_gap_gives_no_ceiling_advice(self) -> None:
        self.assertNotIn("--max-blocked", _render(rows=("AB", "CD")))

    def test_one_gap_short_of_29_of_100_reads_28_percent(self) -> None:
        # 28 of 100 is exactly 28.0%. The float 28.000000000000004 rounded up
        # to a tenth printed 28.1: as the grid's own figure, and as a ceiling
        # a tenth looser than the one that admits it. (8, 0) and (9, 1) are the
        # gaps: each joins the lone A in a new word and swallows no answer.
        rows = ("ABCDEFGHIJ",) * 7 + ("." * 10,) * 2 + ("A" + "." * 9,)
        text = _render(rows=rows)
        self.assertIn(
            "Filling any one gap takes this grid to 28.0% blocked.",
            text.splitlines(),
        )
        self.assertIn("--max-blocked 28.0 as well.", text.splitlines())

    def test_the_figure_is_shown_as_fill_shows_it_and_the_ceiling_admits_it(
        self,
    ) -> None:
        # 23 of 80 is 28.75%. `fill` would report that grid as 28.7 (the
        # float is 28.749999999999996), and a ceiling must be 28.8 to admit
        # it. One number cannot be both, so the sentence and the flag differ.
        rows = ("ABCDEFGHIJ",) * 5 + ("ABCDE.....", "." * 10, "A" + "." * 9)
        text = _render(rows=rows)
        self.assertIn(
            "Filling any one gap takes this grid to 28.7% blocked.",
            text.splitlines(),
        )
        self.assertIn("--max-blocked 28.8 as well.", text.splitlines())


class TestCapping(unittest.TestCase):
    """`--top` bites loudly or not at all."""

    def test_a_cap_that_bites_says_so(self) -> None:
        self.assertIn("showing", _render(top=1).lower())

    def test_a_cap_that_does_not_bite_is_not_mentioned(self) -> None:
        # "showing 25 of 25" invites a reader to wonder what was hidden when
        # nothing was: the reading `shade` already settled.
        self.assertNotIn("showing", _render().lower())

    def test_zero_shows_every_gap(self) -> None:
        self.assertNotIn("showing", _render(top=0).lower())


class TestListable(unittest.TestCase):
    """One function decides what is listed, so the exit code cannot disagree."""

    def test_absorbing_gaps_are_left_out_by_default(self) -> None:
        search = cw_gaps.search_gaps(GRID, VOCABULARY)
        listed = cw_gaps_summary.listable(search, _config())
        self.assertTrue(all(not r.candidate.absorbed for r in listed))

    def test_the_flag_puts_them_back(self) -> None:
        search = cw_gaps.search_gaps(GRID, VOCABULARY)
        listed = cw_gaps_summary.listable(search, _config(include_absorbing=True))
        self.assertEqual(len(listed), len(search.resolutions))

    def test_a_grid_of_only_absorbing_gaps_lists_nothing(self) -> None:
        # The exit-1 case: the analysis ran, and every gap it found costs an
        # answer the operator already has.
        search = cw_gaps.search_gaps(("AB.CD",), frozenset())
        self.assertEqual(cw_gaps_summary.listable(search, _config()), ())


class TestSkippedLines(unittest.TestCase):
    """A word list's unusable lines are named with their reason, never dropped."""

    def test_names_the_line_and_the_reason(self) -> None:
        report = _render(skipped=(("cat-nap", "not letters A-Z"),))
        self.assertIn("cat-nap", report)
        self.assertIn("not letters A-Z", report)

    def test_no_skipped_block_when_nothing_was_skipped(self) -> None:
        self.assertNotIn("skipped", _render().lower())


class TestEmptyAndStable(unittest.TestCase):
    """A grid with nothing to say, and output that does not drift."""

    def test_a_grid_with_no_gaps_still_reports_its_size(self) -> None:
        self.assertIn("2x2", _render(rows=("AB", "CD")))

    def test_two_renders_agree_byte_for_byte(self) -> None:
        self.assertEqual(_render(), _render())

    def test_the_report_has_no_trailing_blank_line(self) -> None:
        self.assertEqual(_render(), _render().rstrip("\n"))


if __name__ == "__main__":
    unittest.main()
