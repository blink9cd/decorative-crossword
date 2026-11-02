"""Tests for the `shade` subcommand at the process boundary: exit codes and files.

What this suite establishes is the exit-code contract every subcommand keeps,
applied to `shade`: exit 0 when the run succeeded, exit 1 when it happened and
found nothing, exit 2 when it could not happen, and the files that did or did
not appear beside each. The algorithm itself is `tests/test_shade.py`'s and is
not re-tested here.

The two refusals worth naming are the ones a reader will not predict.
`--words` and `--word` are the two modes, so supplying neither or both is a
contradictory configuration rather than a defaulting question, and `--out`
asks for a picture of one word, so it is refused in the ranked-search mode
rather than accepted and ignored.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import json
import tempfile
import unittest
from pathlib import Path

import decorative_crossword
import cw_svg
from tests import cli_fixtures, svg_fixtures

#: A grid that spells CAT one letter per row and DOG along its last row, so one
#: fixture reaches both ends of the tool's opinion. Its own answers (CAT and
#: DOG across, AA and TG down) make the `--exclude-grid-answers` cases real.
GRID_ROWS = ["CAT..", ".A...", "..T..", "DOG.."]

#: The cells CAT must be shaded in: one per row, no two touching.
CAT_CELLS = [[0, 0], [1, 1], [2, 2]]


class ShadeSpace:
    """A temporary folder holding a grid, a word list, and paths for outputs."""

    def __init__(self, folder: str, rows: list[str] | None = None) -> None:
        """Write a grid document into `folder` and name the other paths."""
        self.root = Path(folder)
        self.source = self.root / "grid_source.json"
        self.source.write_text(
            json.dumps({"rows": rows or GRID_ROWS, "themes": {}, "clues": {}}),
            encoding="utf-8",
            newline="\n",
        )
        self.svg = self.root / "shaded.svg"

    def words(self, *lines: str) -> Path:
        """Write a word list holding `lines`, and return its path."""
        path = self.root / "words.txt"
        path.write_text(
            "".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n"
        )
        return path

    def argv(self, *extra: str) -> list[str]:
        """A `shade` argv naming this grid, plus whatever the test adds."""
        return ["shade", "--source", str(self.source), *extra]


class TestShadeSearch(cli_fixtures.QuietCase):
    """`--words`: the ranked search over a candidate list."""

    def test_a_grid_with_candidates_exits_zero_and_ranks_them(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT", "DOG")
            code = decorative_crossword.main(
                space.argv("--words", str(words), "--min-length", "2")
            )
            self.assertEqual(code, 0)
            self.assertIn("CAT - 3 letters", self.printed)
            self.assertLess(self.printed.index("CAT -"), self.printed.index("DOG -"))

    def test_a_search_that_finds_nothing_exits_one_and_says_so(self) -> None:
        """Exit 1 is 'the run happened and did not succeed'.

        Not exit 2: the request was well formed and the grid was read; this
        word list simply holds nothing this grid can spell.
        """
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("ZEBRA")
            code = decorative_crossword.main(space.argv("--words", str(words)))
            self.assertEqual(code, 1)
            self.assertIn("NO HIDDEN WORD FOUND", self.printed)

    def test_top_caps_the_printed_list(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT", "DOG")
            decorative_crossword.main(
                space.argv("--words", str(words), "--min-length", "2", "--top", "1")
            )
            self.assertIn("showing 1 of 2", self.printed)

    def test_excluding_grid_answers_names_what_it_removed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT")
            code = decorative_crossword.main(
                space.argv(
                    "--words",
                    str(words),
                    "--min-length",
                    "2",
                    "--exclude-grid-answers",
                )
            )
            self.assertEqual(code, 1)
            self.assertIn("Already answers in this grid", self.printed)

    def test_an_unusable_word_list_line_is_skipped_and_reported(self) -> None:
        """One bad line must not fail a list nobody hand-curated."""
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("WELL-KNOWN", "CAT")
            code = decorative_crossword.main(
                space.argv("--words", str(words), "--min-length", "2")
            )
            self.assertEqual(code, 0)
            self.assertIn("WELL-KNOWN", self.printed)

    def test_a_word_list_holding_no_usable_word_is_refused(self) -> None:
        """Exit 2: there was nothing to search with, so no run could happen.

        Distinct from the exit-1 case above, and the distinction is the point:
        one is a search that found nothing, the other is an input that offered
        nothing to search.
        """
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("# only a comment", "")
            self.assertEqual(
                decorative_crossword.main(space.argv("--words", str(words))), 2
            )
            self.assertIn("no usable words", self.errors)

    def test_a_missing_word_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            missing = space.root / "absent.txt"
            self.assertEqual(
                decorative_crossword.main(space.argv("--words", str(missing))), 2
            )

    def test_a_mis_encoded_word_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            path = space.root / "words.txt"
            path.write_bytes(b"CAF\xff\n")
            self.assertEqual(
                decorative_crossword.main(space.argv("--words", str(path))), 2
            )


class TestShadePlace(cli_fixtures.QuietCase):
    """`--word`: one named word, its cells, and optionally its picture."""

    def test_places_a_word_and_prints_its_cells(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            code = decorative_crossword.main(space.argv("--word", "CAT"))
            self.assertEqual(code, 0)
            self.assertIn("(0, 0), (1, 1), (2, 2)", self.printed)

    def test_the_paste_form_round_trips_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            decorative_crossword.main(space.argv("--word", "CAT"))
            line = next(
                line for line in self.printed.splitlines() if "Paste form" in line
            )
            self.assertEqual(json.loads(line.split(":", 1)[1].strip()), CAT_CELLS)

    def test_a_lower_case_word_is_folded(self) -> None:
        """A word copied out of a lower-case list must not behave differently."""
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(decorative_crossword.main(space.argv("--word", "cat")), 0)
            self.assertIn("Hidden word CAT", self.printed)

    def test_a_word_this_grid_cannot_spell_is_refused(self) -> None:
        """A flag naming something that does not exist: exit 2.

        The same reading `preview --feature` already gets for an answer the
        given grid does not hold.
        """
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(
                decorative_crossword.main(space.argv("--word", "ZEBRA")), 2
            )
            self.assertIn("ZEBRA", self.errors)

    def test_a_word_outside_a_to_z_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(
                decorative_crossword.main(space.argv("--word", "CAT-NAP")), 2
            )
            self.assertIn("--word", self.errors)

    def test_excluding_grid_answers_refuses_a_word_that_is_one(self) -> None:
        """The two flags ask for opposite things, and only the operator knows.

        The same refusal `fill` makes when `--excluded-terms` would drop the
        answer `--feature` names.
        """
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(
                decorative_crossword.main(
                    space.argv("--word", "CAT", "--exclude-grid-answers")
                ),
                2,
            )
            self.assertIn("--exclude-grid-answers", self.errors)

    def test_out_writes_a_render_shading_the_chosen_cells(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            code = decorative_crossword.main(
                space.argv("--word", "CAT", "--out", str(space.svg))
            )
            self.assertEqual(code, 0)
            rendered = space.svg.read_text(encoding="utf-8")
            classes = svg_fixtures.cell_classes(rendered)
            width = len(GRID_ROWS[0])
            shaded = {
                divmod(index, width)
                for index, css in enumerate(classes)
                if css == cw_svg.FEATURE_TOKEN
            }
            self.assertEqual(shaded, {(0, 0), (1, 1), (2, 2)})

    def test_the_render_caption_names_the_hidden_word(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            decorative_crossword.main(
                space.argv("--word", "CAT", "--out", str(space.svg))
            )
            caption = "\n".join(
                svg_fixtures.caption_lines(space.svg.read_text(encoding="utf-8"))
            )
            self.assertIn("Hidden: CAT", caption)

    def test_no_out_writes_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            decorative_crossword.main(space.argv("--word", "CAT"))
            self.assertFalse(space.svg.exists())

    def test_a_refused_word_writes_no_render(self) -> None:
        """Exit 2 writes no file, the same rule every other subcommand keeps."""
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            decorative_crossword.main(
                space.argv("--word", "ZEBRA", "--out", str(space.svg))
            )
            self.assertFalse(space.svg.exists())

    def test_an_unwritable_render_path_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(
                decorative_crossword.main(
                    space.argv(
                        "--word", "CAT", "--out", str(space.root / "gone" / "x.svg")
                    )
                ),
                2,
            )


class TestShadeRefusals(cli_fixtures.QuietCase):
    """Configurations `shade` will not run, each naming the flag at fault."""

    def test_neither_mode_flag_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(decorative_crossword.main(space.argv()), 2)
            self.assertIn("--words", self.errors)
            self.assertIn("--word", self.errors)

    def test_both_mode_flags_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT")
            self.assertEqual(
                decorative_crossword.main(
                    space.argv("--words", str(words), "--word", "CAT")
                ),
                2,
            )

    def test_out_is_refused_in_the_search_mode(self) -> None:
        """Refused rather than accepted and ignored: there is no one word to draw."""
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT")
            self.assertEqual(
                decorative_crossword.main(
                    space.argv("--words", str(words), "--out", str(space.svg))
                ),
                2,
            )
            self.assertIn("--out", self.errors)

    def test_a_non_positive_cell_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            self.assertEqual(
                decorative_crossword.main(space.argv("--word", "CAT", "--cell", "0")),
                2,
            )
            self.assertIn("--cell", self.errors)

    def test_a_min_length_below_the_two_letter_floor_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT")
            self.assertEqual(
                decorative_crossword.main(
                    space.argv("--words", str(words), "--min-length", "1")
                ),
                2,
            )
            self.assertIn("--min-length", self.errors)

    def test_a_negative_top_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            words = space.words("CAT")
            self.assertEqual(
                decorative_crossword.main(
                    space.argv("--words", str(words), "--top", "-1")
                ),
                2,
            )
            self.assertIn("--top", self.errors)

    def test_a_missing_grid_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            space.source.unlink()
            self.assertEqual(decorative_crossword.main(space.argv("--word", "CAT")), 2)

    def test_an_incoherent_grid_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            space.source.write_text(
                json.dumps({"rows": ["AB", "C"]}), encoding="utf-8", newline="\n"
            )
            self.assertEqual(decorative_crossword.main(space.argv("--word", "AB")), 2)


if __name__ == "__main__":
    unittest.main()
