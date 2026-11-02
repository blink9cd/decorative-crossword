"""Grouped suite: the hidden-word search and the cells it chooses to shade.

Two halves, and the second is the one that matters. Finding *whether* a word
can be spelled by shading cells is a subsequence test and is nearly free: on
a real grid most short words match, so a suite that only checked "it finds a
word" would stay green against a tool that chose the wrong cells every time.
The cell choice is the load-bearing half, and the obvious implementation of it
(take the first occurrence of each letter) is measurably wrong: it clusters
the picks inside one answer, and the shading reads as a corrupted entry rather
than as a hidden word.

So the cases below pin the distinction in both directions. `TestClustering`
holds one word against two grids (one that forces its letters into a single
row and one that spreads them one per row), and asserts the scores are far
apart. `TestGreedyIsNotEnough` holds a grid where the greedy pick and the
chosen pick differ, and asserts the cells, not just the score: a chooser
swapped for greedy fails there even if the scoring function survives intact.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest
from pathlib import Path

import cw_shade


#: A grid whose only row spells HIDDEN, so the word's six letters have exactly
#: one home each and every consecutive pair sits in the same row one column
#: apart. There is no scattered alternative to find, which is what makes the
#: high score below a fact about the grid rather than about the chooser.
ONE_ROW = ("HIDDEN",)

#: The same word's letters, one per row, no two in the same row. Every pair is
#: two or more cells apart, so a chooser that walks them in order pays nothing.
#: Deliberately not a diagonal all the way down: the last letter sits back at
#: column 0, so a chooser that only ever stepped down-and-right would still
#: have to reach it.
SCATTERED = ("H.....", ".I....", "..D...", "...D..", "....E.", "N.....")

#: C has one home; A and T each have two: one in row 0 beside C, one further
#: down and away. Greedy takes the row-0 pair and lands on three consecutive
#: cells of one entry; the shortest path takes the far pair and pays nothing.
#: The two disagree on the cells, not only on the score.
GREEDY_TRAP = ("CAT..", ".A...", "..T..")

#: What greedy would pick on GREEDY_TRAP, and what the chooser must not.
GREEDY_TRAP_GREEDY_CELLS = ((0, 0), (0, 1), (0, 2))

#: What the shortest path picks there instead.
GREEDY_TRAP_CHOSEN_CELLS = ((0, 0), (1, 1), (2, 2))

#: Four lettered cells, one per row, columns alternating 0 and 2 so that no two
#: of them share a row and no two of them touch. Every word spelled off it
#: therefore scores 0, which is the point: on this grid the ranking's clustering
#: term separates nothing, so the two tie-break terms are the only thing
#: deciding the order and a test can hold them alone.
TIE_GRID = ("A..", "..B", "C..", "..D")


class TestLetteredCells(unittest.TestCase):
    """The grid read as letters in reading order, blocks skipped."""

    def test_reads_row_major_and_skips_blocks(self) -> None:
        cells = cw_shade.lettered_cells(("A.B", ".C."))
        self.assertEqual(cells, ((0, 0, "A"), (0, 2, "B"), (1, 1, "C")))

    def test_an_all_blocked_grid_has_no_letters(self) -> None:
        self.assertEqual(cw_shade.lettered_cells(("..", "..")), ())


class TestClusteringPenalty(unittest.TestCase):
    """One step's penalty, by the relationship between the two cells."""

    def test_same_row_adjacent_column_is_the_heaviest_step(self) -> None:
        """Adjacent in a row is what makes shading read as a corrupted entry.

        It is also orthogonally touching, so it pays that term too: the two
        are separate observations about one step, and the heaviest penalty in
        the table is the sum rather than a fourth named number.
        """
        self.assertEqual(
            cw_shade.clustering_penalty((2, 3), (2, 4)),
            cw_shade.SAME_ROW_ADJACENT_PENALTY + cw_shade.TOUCHING_PENALTY,
        )

    def test_same_row_further_apart_pays_only_the_row_term(self) -> None:
        self.assertEqual(
            cw_shade.clustering_penalty((2, 0), (2, 5)),
            cw_shade.SAME_ROW_PENALTY,
        )

    def test_vertically_touching_pays_only_the_touching_term(self) -> None:
        self.assertEqual(
            cw_shade.clustering_penalty((2, 3), (3, 3)),
            cw_shade.TOUCHING_PENALTY,
        )

    def test_cells_that_neither_share_a_row_nor_touch_are_free(self) -> None:
        self.assertEqual(cw_shade.clustering_penalty((0, 0), (3, 4)), 0)

    def test_the_penalty_does_not_depend_on_the_order_of_the_pair(self) -> None:
        """Reading order fixes which cell is 'previous'; the cost is the same."""
        self.assertEqual(
            cw_shade.clustering_penalty((1, 1), (1, 2)),
            cw_shade.clustering_penalty((1, 2), (1, 1)),
        )


class TestPlaceWord(unittest.TestCase):
    """Choosing which cells to shade for one named word."""

    def test_a_word_the_grid_cannot_spell_is_not_placed(self) -> None:
        self.assertIsNone(cw_shade.place_word(ONE_ROW, "ZEBRA"))

    def test_an_empty_word_is_not_placed(self) -> None:
        """It spells nothing, so a placement of no cells would be a lie.

        Nothing in the CLI can reach this (the word list skips a blank line
        and `--word` is length-checked), but `place_word` is public, and
        without the guard the empty case is an IndexError rather than an
        answer.
        """
        self.assertIsNone(cw_shade.place_word(ONE_ROW, ""))

    def test_letters_out_of_order_cannot_be_placed(self) -> None:
        """Reading order is the whole constraint: NEDDIH is HIDDEN backwards."""
        self.assertIsNone(cw_shade.place_word(ONE_ROW, "NEDDIH"))

    def test_the_chosen_cells_spell_the_word_in_reading_order(self) -> None:
        placement = cw_shade.place_word(SCATTERED, "HIDDEN")
        assert placement is not None
        spelled = "".join(SCATTERED[row][col] for row, col in placement.cells)
        self.assertEqual(spelled, "HIDDEN")
        self.assertEqual(list(placement.cells), sorted(placement.cells))

    def test_one_cell_per_letter(self) -> None:
        placement = cw_shade.place_word(SCATTERED, "HIDDEN")
        assert placement is not None
        self.assertEqual(len(placement.cells), len("HIDDEN"))

    def test_rows_spanned_counts_distinct_rows(self) -> None:
        placement = cw_shade.place_word(SCATTERED, "HIDDEN")
        assert placement is not None
        self.assertEqual(placement.rows_spanned, len(SCATTERED))

    def test_a_single_letter_word_pays_nothing(self) -> None:
        """No step, so no penalty: the sum over an empty set of steps."""
        placement = cw_shade.place_word(ONE_ROW, "H")
        assert placement is not None
        self.assertEqual(placement.clustering, 0)
        self.assertEqual(placement.rows_spanned, 1)


class TestClustering(unittest.TestCase):
    """The tool's opinion: the same word, on two grids that shade it differently.

    This is the finding the tool exists to report, so it is pinned as a fact
    about two numbers rather than as "a score was returned".
    """

    def test_a_forced_single_row_word_scores_high(self) -> None:
        placement = cw_shade.place_word(ONE_ROW, "HIDDEN")
        assert placement is not None
        self.assertEqual(placement.rows_spanned, 1)
        # Five steps, every one of them same-row and one column apart.
        self.assertEqual(
            placement.clustering,
            (len("HIDDEN") - 1)
            * (cw_shade.SAME_ROW_ADJACENT_PENALTY + cw_shade.TOUCHING_PENALTY),
        )

    def test_a_scattered_word_scores_zero(self) -> None:
        placement = cw_shade.place_word(SCATTERED, "HIDDEN")
        assert placement is not None
        self.assertEqual(placement.clustering, 0)

    def test_the_clustered_reading_scores_far_above_the_scattered_one(self) -> None:
        """The comparison itself, stated so neither number can drift alone."""
        clustered = cw_shade.place_word(ONE_ROW, "HIDDEN")
        scattered = cw_shade.place_word(SCATTERED, "HIDDEN")
        assert clustered is not None
        assert scattered is not None
        self.assertGreater(clustered.clustering, scattered.clustering)


class TestGreedyIsNotEnough(unittest.TestCase):
    """The chooser is a shortest path, and taking the first fit is not it.

    Greedy is what a later reader reaches for (it is shorter and it looks
    obviously correct), so the cases here fail against it rather than merely
    scoring it worse. They assert the cells, which is what a caller pastes.
    """

    def test_the_chosen_cells_are_not_the_greedy_ones(self) -> None:
        placement = cw_shade.place_word(GREEDY_TRAP, "CAT")
        assert placement is not None
        self.assertEqual(placement.cells, GREEDY_TRAP_CHOSEN_CELLS)
        self.assertNotEqual(placement.cells, GREEDY_TRAP_GREEDY_CELLS)

    def test_the_greedy_pick_really_is_available_and_really_is_worse(self) -> None:
        """Without this the case above could pass on a grid greedy never sees.

        It establishes that the greedy cells spell the word too (so the
        chooser had a genuine choice), and that they cost strictly more.
        """
        spelled = "".join(
            GREEDY_TRAP[row][col] for row, col in GREEDY_TRAP_GREEDY_CELLS
        )
        self.assertEqual(spelled, "CAT")
        greedy_cost = sum(
            cw_shade.clustering_penalty(
                GREEDY_TRAP_GREEDY_CELLS[index - 1], GREEDY_TRAP_GREEDY_CELLS[index]
            )
            for index in range(1, len(GREEDY_TRAP_GREEDY_CELLS))
        )
        placement = cw_shade.place_word(GREEDY_TRAP, "CAT")
        assert placement is not None
        self.assertGreater(greedy_cost, placement.clustering)

    def test_ties_are_broken_by_reading_order(self) -> None:
        """Two equally-cheap readings must not depend on dict iteration order.

        Both A cells are two rows away from nothing and cost the same; the
        earlier one in reading order wins, so the output is byte-stable
        across runs.
        """
        rows = ("A...A", ".....", "....Z")
        placement = cw_shade.place_word(rows, "AZ")
        assert placement is not None
        self.assertEqual(placement.cells, ((0, 0), (2, 4)))


class TestGridAnswers(unittest.TestCase):
    """The answers already standing in the grid, which are repeats not bonuses."""

    def test_reads_both_directions(self) -> None:
        self.assertEqual(
            cw_shade.grid_answers(("CAT", "O..", "WET")),
            frozenset({"CAT", "WET", "COW"}),
        )


class TestSearchHiddenWords(unittest.TestCase):
    """The ranked search over a word list, and what it excludes and why."""

    def test_ranks_the_least_clustered_word_first(self) -> None:
        """The primary ranking term, on a grid where it decides every pair.

        Measured on these rows, the three words score 3, 19 and 54: three
        distinct values, so this case exercises the clustering term and nothing
        else. The two tie-break terms are unreachable here and are held by the
        two cases below, on a grid built to tie.
        """
        rows = ("HIDDEN", "E.....", "N.....")
        result = cw_shade.search_hidden_words(
            rows, ("HIDDEN", "HEN", "HID"), min_length=2, exclude_grid_answers=False
        )
        self.assertEqual(
            [candidate.clustering for candidate in result.candidates],
            [3, 19, 54],
        )
        self.assertEqual(
            [candidate.word for candidate in result.candidates],
            ["HEN", "HID", "HIDDEN"],
        )

    def test_the_longer_of_two_equally_clustered_words_ranks_first(self) -> None:
        """The length tie-break, against an input order that contradicts it.

        Both words score 0, so clustering cannot order them, and `sorted` is
        stable, so a ranking that had lost its length term would hand back the
        order they were supplied in. They are supplied shortest first for
        exactly that reason: the assertion below can only pass if the term ran.
        """
        result = cw_shade.search_hidden_words(
            TIE_GRID, ("ABC", "ABCD"), min_length=2, exclude_grid_answers=False
        )
        self.assertEqual([c.clustering for c in result.candidates], [0, 0])
        self.assertEqual([c.word for c in result.candidates], ["ABCD", "ABC"])

    def test_two_equally_clustered_words_of_a_length_rank_alphabetically(self) -> None:
        """The last-resort tie-break, supplied in reverse-alphabetical order.

        Same clustering and same length, so neither earlier term can separate
        this pair: only the alphabetical term can, and it has to reverse the
        input order to do it. That is what makes the ranking total, and
        therefore reproducible across runs.
        """
        result = cw_shade.search_hidden_words(
            TIE_GRID, ("ABD", "ABC"), min_length=2, exclude_grid_answers=False
        )
        self.assertEqual([c.clustering for c in result.candidates], [0, 0])
        self.assertEqual([len(c.word) for c in result.candidates], [3, 3])
        self.assertEqual([c.word for c in result.candidates], ["ABC", "ABD"])

    def test_a_word_shorter_than_the_floor_is_counted_not_ranked(self) -> None:
        result = cw_shade.search_hidden_words(
            ONE_ROW, ("HIDDEN", "HI"), min_length=3, exclude_grid_answers=False
        )
        self.assertEqual([c.word for c in result.candidates], ["HIDDEN"])
        self.assertEqual(result.too_short, 1)

    def test_a_word_the_grid_cannot_spell_is_counted_not_ranked(self) -> None:
        result = cw_shade.search_hidden_words(
            ONE_ROW, ("HIDDEN", "ZEBRA"), min_length=2, exclude_grid_answers=False
        )
        self.assertEqual(result.unspellable, 1)

    def test_grid_answers_are_kept_by_default(self) -> None:
        rows = ("CAT", "O..", "WET")
        result = cw_shade.search_hidden_words(
            rows, ("CAT",), min_length=2, exclude_grid_answers=False
        )
        self.assertEqual([c.word for c in result.candidates], ["CAT"])
        self.assertEqual(result.excluded_answers, ())

    def test_grid_answers_are_named_when_excluded(self) -> None:
        """Named, not merely counted: a silent drop is what the flag must avoid."""
        rows = ("CAT", "O..", "WET")
        result = cw_shade.search_hidden_words(
            rows, ("CAT", "COW"), min_length=2, exclude_grid_answers=True
        )
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.excluded_answers, ("CAT", "COW"))

    def test_an_empty_word_list_yields_no_candidates(self) -> None:
        result = cw_shade.search_hidden_words(
            ONE_ROW, (), min_length=2, exclude_grid_answers=False
        )
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.unspellable, 0)


class TestLoadWordList(unittest.TestCase):
    """Reading the candidate word list: one word per line, folded and screened."""

    def _write(self, text: str) -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "words.txt"
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def test_reads_one_word_per_line_uppercased(self) -> None:
        words, skipped = cw_shade.load_word_list(self._write("notebook\nBREACH\n"))
        self.assertEqual(words, ("NOTEBOOK", "BREACH"))
        self.assertEqual(skipped, ())

    def test_blank_lines_and_comments_are_ignored_silently(self) -> None:
        words, skipped = cw_shade.load_word_list(self._write("# a note\n\n  \nCAT\n"))
        self.assertEqual(words, ("CAT",))
        self.assertEqual(skipped, ())

    def test_duplicates_collapse_in_first_seen_order(self) -> None:
        words, _ = cw_shade.load_word_list(self._write("CAT\nDOG\ncat\n"))
        self.assertEqual(words, ("CAT", "DOG"))

    def test_a_word_outside_a_to_z_is_skipped_and_named(self) -> None:
        """Skipped and reported, never dropped quietly, and never fatal.

        A run that refused outright on one hyphen would be hostile to a list
        nobody hand-curated.
        """
        words, skipped = cw_shade.load_word_list(self._write("WELL-KNOWN\nCAT\n"))
        self.assertEqual(words, ("CAT",))
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0][0], "WELL-KNOWN")
        self.assertIn("A-Z", skipped[0][1])

    def test_a_one_letter_word_is_skipped_and_named(self) -> None:
        words, skipped = cw_shade.load_word_list(self._write("A\nCAT\n"))
        self.assertEqual(words, ("CAT",))
        self.assertEqual(skipped[0][0], "A")

    def test_an_unreadable_file_raises_shade_error(self) -> None:
        missing = self._write("CAT\n").parent / "absent.txt"
        with self.assertRaises(cw_shade.ShadeError):
            cw_shade.load_word_list(missing)

    def test_a_mis_encoded_file_raises_shade_error(self) -> None:
        """A UnicodeDecodeError is a ValueError, not an OSError.

        A reader that caught only the latter would let an editor's legacy code
        page past as a traceback rather than as the tool's own refusal.
        """
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "words.txt"
        path.write_bytes(b"CAF\xff\n")
        with self.assertRaises(cw_shade.ShadeError):
            cw_shade.load_word_list(path)


if __name__ == "__main__":
    unittest.main()
