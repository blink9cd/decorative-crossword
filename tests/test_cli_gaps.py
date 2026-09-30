"""Grouped suite: `gaps` at the process boundary -- exit codes and files.

What these cases test is not the analysis, which `test_gaps.py` owns, but the
three things only a real run can settle: which exit code the operator's script
sees, what reached stdout versus stderr, and whether a file appeared. So the
fixtures write real banks, real word lists and a real grid into a real
temporary folder.

The exit codes follow `shade`'s, deliberately rather than by coincidence:
`0` this grid has a gap worth reporting, `1` the analysis ran and it has none,
`2` the run could not happen. `TestExitOne` is the one worth reading -- a grid
whose every gap would absorb a curated answer has been ANALYZED successfully
and still has nothing to offer, and reporting that as `2` would say something
false about the operator's file.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cw_gaps_summary
import cw_grid
import decorative_crossword
from tests import cli_fixtures

#: CAT and DOG lie two rows apart, so three of the four cells between them each
#: demand a three-letter run crossing both -- `C?D`, `A?O`, `T?G` -- the fourth
#: would join no entry, and the two cells at the line ends would weld an answer
#: instead. One grid, every tier but "needing two new answers".
GRID_ROWS = ["CAT.", "....", "DOG."]

#: COD pays `C?D` with the letter O; nothing here pays `A?O` or `T?G`, so one
#: gap is ready and the rest name what the operator would have to invent.
BANK: dict[str, object] = {
    "themes": {"a": {"label": "A", "summary": "The only theme"}},
    "entries": [{"answer": answer, "theme": "a"} for answer in ("CAT", "DOG", "COD")],
}

#: Every gap on this grid welds an existing answer, so the run succeeds and has
#: nothing to list -- the exit-1 case.
ONLY_ABSORBING_ROWS = ["AB.CD"]


class GapsSpace:
    """A temporary folder holding a grid, a bank, and paths for outputs."""

    def __init__(self, folder: str, rows: list[str] | None = None) -> None:
        """Write a grid and a bank into `folder` and name the other paths."""
        self.root = Path(folder)
        self.source = self.root / "grid_source.json"
        self.source.write_text(
            json.dumps({"rows": rows or GRID_ROWS, "themes": {}, "clues": {}}),
            encoding="utf-8",
            newline="\n",
        )
        self.bank = self.root / "bank.json"
        self.bank.write_text(json.dumps(BANK), encoding="utf-8", newline="\n")
        self.svg = self.root / "gaps.svg"

    def words(self, *lines: str, name: str = "words.txt") -> Path:
        """Write a word list holding `lines`, and return its path."""
        path = self.root / name
        path.write_text(
            "".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n"
        )
        return path

    def mask(self, *rows: str) -> Path:
        """Write a `--mask` picture holding `rows`, and return its path."""
        path = self.root / "shape.txt"
        path.write_text(
            "".join(f"{row}\n" for row in rows), encoding="utf-8", newline="\n"
        )
        return path

    def argv(self, *extra: str) -> list[str]:
        """A `gaps` argv naming this grid, plus whatever the test adds."""
        return ["gaps", "--source", str(self.source), *extra]


class TestExitZero(cli_fixtures.QuietCase):
    """A grid with a gap worth reporting exits 0 and prints its report."""

    def test_a_bare_run_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            code = decorative_crossword.main(space.argv())
            self.assertEqual(code, 0)
            self.assertIn("Gaps in a 3x4 grid", self.printed)

    def test_the_report_goes_to_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            decorative_crossword.main(space.argv())
            self.assertNotEqual(self.printed, "")
            self.assertEqual(self.errors, "")

    def test_without_a_vocabulary_it_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            decorative_crossword.main(space.argv())
            self.assertIn("no vocabulary supplied", self.printed)


class TestVocabularySources(cli_fixtures.QuietCase):
    """`--bank` and `--words` are two ways to offer answers, and they union."""

    def test_a_bank_makes_a_ready_gap_visible(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            code = decorative_crossword.main(space.argv("--bank", str(space.bank)))
            self.assertEqual(code, 0)
            self.assertIn("take O", self.printed)

    def test_a_word_list_makes_a_ready_gap_visible(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            words = space.words("ato")
            decorative_crossword.main(space.argv("--words", str(words)))
            self.assertIn("take T", self.printed)

    def test_a_lower_case_list_is_folded_like_shade_folds_one(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            words = space.words("ato")
            decorative_crossword.main(space.argv("--words", str(words)))
            self.assertIn("ATO", self.printed)

    def test_words_is_repeatable_and_the_lists_union(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            first = space.words("ato", name="first.txt")
            second = space.words("tug", name="second.txt")
            decorative_crossword.main(
                space.argv("--words", str(first), "--words", str(second))
            )
            printed = self.printed
            self.assertIn("ATO", printed)
            self.assertIn("TUG", printed)

    def test_a_bank_and_a_list_union(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            words = space.words("ato")
            decorative_crossword.main(
                space.argv("--bank", str(space.bank), "--words", str(words))
            )
            printed = self.printed
            self.assertIn("take O", printed)
            self.assertIn("take T", printed)

    def test_an_unusable_line_is_named_with_its_reason(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            words = space.words("ato", "cat-nap")
            decorative_crossword.main(space.argv("--words", str(words)))
            # Reported UPPERCASED, because `load_word_list` folds case before
            # it judges a line -- the same form `shade` reports a skip in.
            self.assertIn("CAT-NAP", self.printed)


class TestExitOne(cli_fixtures.QuietCase):
    """The analysis ran and this grid has nothing to offer."""

    def test_a_grid_of_only_absorbing_gaps_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder, rows=ONLY_ABSORBING_ROWS)
            code = decorative_crossword.main(space.argv())
            self.assertEqual(code, 1)

    def test_it_still_prints_the_report(self) -> None:
        # Exit 1 is a fact about the grid, not a refusal: the headline still
        # accounts for every blocked cell, which is what makes it actionable.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder, rows=ONLY_ABSORBING_ROWS)
            decorative_crossword.main(space.argv())
            self.assertIn("Gaps in a 1x5 grid", self.printed)

    def test_including_the_absorbing_tier_turns_it_back_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder, rows=ONLY_ABSORBING_ROWS)
            code = decorative_crossword.main(space.argv("--include-absorbing"))
            self.assertEqual(code, 0)


class TestExitTwo(cli_fixtures.QuietCase):
    """The run could not happen: a diagnostic on stderr, and no file written."""

    def _refused(self, *extra: str, rows: list[str] | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder, rows=rows)
            code = decorative_crossword.main(space.argv(*extra))
            return code, self.errors

    def test_a_missing_source_is_refused(self) -> None:
        code = decorative_crossword.main(["gaps", "--source", "no-such-grid.json"])
        self.assertEqual(code, 2)
        self.assertNotEqual(self.errors, "")

    def test_a_ragged_grid_is_refused(self) -> None:
        code, err = self._refused(rows=["ABC", "AB"])
        self.assertEqual(code, 2)
        self.assertIn("ragged", err)

    def test_a_negative_top_is_refused_naming_the_flag(self) -> None:
        code, err = self._refused("--top", "-1")
        self.assertEqual((code, "--top" in err), (2, True))

    def test_a_zero_cell_is_refused_naming_the_flag(self) -> None:
        code, err = self._refused("--cell", "0")
        self.assertEqual((code, "--cell" in err), (2, True))

    def test_a_word_list_with_nothing_usable_is_refused(self) -> None:
        # The flag was given and supplied nothing, so the report's "no
        # vocabulary supplied" line would be false. A silently inert flag is
        # how a command line comes to mean something other than what it says.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            words = space.words("#  only a comment", "")
            code = decorative_crossword.main(space.argv("--words", str(words)))
            self.assertEqual(code, 2)
            self.assertIn(str(words), self.errors)

    def test_an_unreadable_bank_is_refused(self) -> None:
        code, err = self._refused("--bank", "no-such-bank.json")
        self.assertEqual(code, 2)
        self.assertNotEqual(err, "")


class TestRender(cli_fixtures.QuietCase):
    """`--out` draws the gaps this run listed, and only when the run succeeds."""

    def test_out_writes_an_svg(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            code = decorative_crossword.main(space.argv("--out", str(space.svg)))
            self.assertEqual(code, 0)
            self.assertTrue(space.svg.exists())

    def test_a_refused_run_writes_no_svg(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            code = decorative_crossword.main(
                space.argv("--out", str(space.svg), "--cell", "0")
            )
            self.assertEqual(code, 2)
            self.assertFalse(space.svg.exists())

    def test_the_svg_is_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            decorative_crossword.main(space.argv("--out", str(space.svg)))
            drawn = space.svg.read_text(encoding="utf-8")
            # No fetched resource of any kind. The SVG namespace is a URI in
            # the document either way, so "no http" would fail on the one
            # string that has to be there; what matters is that nothing is
            # REFERENCED.
            self.assertNotIn("href", drawn)
            self.assertNotIn("<image", drawn)


class TestMask(cli_fixtures.QuietCase):
    """`gaps --mask` advises nothing about a cell the operator drew out."""

    def test_a_masked_cell_is_reported_as_masked_and_not_as_a_gap(self) -> None:
        # (1, 3) is one of this grid's gaps. Masked, the operator will never
        # fill it, so advice about it is advice they would have to discard.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            picture = space.mask("....", "...X", "....")
            code = decorative_crossword.main(
                space.argv("--bank", str(space.bank), "--mask", str(picture))
            )
            report = self.printed
        self.assertEqual(code, 0)
        self.assertIn(
            f"Not counted above: 1 blocked cell(s) {cw_gaps_summary.MASKED_TIER}.",
            report.splitlines(),
        )
        self.assertIn(
            f"From --mask {picture}: 1 of 12 cells may never hold a letter.",
            report.splitlines(),
        )

    def test_a_picture_the_grid_does_not_match_is_exit_two(self) -> None:
        # The size is the SOURCE grid's here, not a flag's: `gaps` is given a
        # grid rather than asked to make one, so the refusal names both shapes.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            picture = space.mask("..", "..")
            code = decorative_crossword.main(
                space.argv("--bank", str(space.bank), "--mask", str(picture))
            )
        self.assertEqual(code, 2)
        self.assertIn("--mask", self.errors)
        self.assertIn("2x2", self.errors)
        self.assertIn("3x4", self.errors)

    def test_a_source_letter_in_a_masked_cell_is_exit_two(self) -> None:
        # The same operator-authored contradiction `fill` refuses, and `gaps`
        # has to refuse it for a second reason of its own: accepted, the letter
        # would make the report say "1 of 12 cells may never hold a letter"
        # about a cell holding C, and the masked count -- counted off the
        # analysis, which only ever classifies BLOCKED cells -- would not
        # include it.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            picture = space.mask("X...", "....", "....")
            code = decorative_crossword.main(
                space.argv("--bank", str(space.bank), "--mask", str(picture))
            )
        self.assertEqual(code, 2)
        self.assertIn("--source", self.errors)
        self.assertIn("--mask", self.errors)
        self.assertIn("0,0", self.errors)

    def test_a_ragged_picture_is_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            picture = space.mask("....", "...")
            code = decorative_crossword.main(
                space.argv("--bank", str(space.bank), "--mask", str(picture))
            )
        self.assertEqual(code, 2)
        self.assertIn("ragged", self.errors)

    def test_each_other_picture_the_parser_refuses_is_exit_two(self) -> None:
        side = cw_grid.MAX_SIDE + 1
        pictures = {
            "a blank line": (("....", "", "...."), "line 2 is blank"),
            "no rows": (("# a title and nothing else",), "holds no rows"),
            "a stray character": (("..q.", "....", "...."), "column 3 holds 'q'"),
            "past the size cap": (("." * side,) * side, f"draws a {side}x{side}"),
            "every cell masked": (("XXXX",) * 3, "masks every cell"),
        }
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            for fault, (rows, said) in pictures.items():
                with self.subTest(fault=fault):
                    already = len(self.errors)
                    argv = space.argv("--mask", str(space.mask(*rows)))
                    self.assertEqual(decorative_crossword.main(argv), 2)
                    self.assertIn(said, self.errors[already:])

    def test_out_naming_the_mask_is_refused(self) -> None:
        # The output-collision check has to know about every input, or a run
        # pointed at its own picture writes an SVG over it.
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            picture = space.mask("....", "....", "....")
            before = picture.read_bytes()
            code = decorative_crossword.main(
                space.argv("--mask", str(picture), "--out", str(picture))
            )
            after = picture.read_bytes()
        self.assertEqual(code, 2)
        self.assertIn("--out names the --mask file", self.errors)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
