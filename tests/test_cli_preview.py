"""Tests for the CLI's screen, its `preview` subcommand, and the single renderer.

Organized along the seam the CLI draws: `fill` searches, `preview` draws, and
the claim that binds them is that there is only ONE drawing implementation
behind both.
"""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from unittest import mock

import decorative_crossword
import cw_grid
import cw_svg
from tests import cli_fixtures, svg_fixtures

#: Layers whose content is a function of the grid alone. `fill --preview` and
#: `preview` must produce these identically for one grid filled without
#: `--source`: then the caption's configuration tier is the ONLY thing the two
#: modes are allowed to differ by.
_GRID_LAYERS = (
    cw_svg.CELL_LAYER,
    cw_svg.MARKER_LAYER,
    cw_svg.LETTER_LAYER,
    cw_svg.LEGEND_LAYER,
)


def _layer_bytes(rendered: str, layer: str) -> bytes:
    """One layer of a rendered document, serialized for comparison."""
    return ElementTree.tostring(svg_fixtures.layers(rendered)[layer])


class TestExcludedTerms(cli_fixtures.QuietCase):
    """The screen drops and reports; it never removes an entry quietly."""

    def test_drops_a_barred_answer(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.excluded("alpha")
            decorative_crossword.main(space.fill("--excluded-terms", str(terms)))
            self.assertNotIn("ALPHA", space.clues())

    def test_the_screen_changes_which_answers_get_placed(self) -> None:
        # The test above passes for an answer the search never reached anyway.
        # This one bars the answer THIS seed actually places, so a screen that
        # dropped nothing would leave the grid unchanged and fail here.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(decorative_crossword.main(space.fill()), 0)
            # AMBER is a DOWN entry here, so "is it in the grid" is a run
            # lookup rather than a substring search on the joined rows -- the
            # search this suite would otherwise silently always pass.
            self.assertIsNotNone(cw_grid.find_answer(space.rows(), "AMBER"))
            terms = space.excluded("amber")
            self.assertEqual(
                decorative_crossword.main(space.fill("--excluded-terms", str(terms))), 0
            )
            self.assertIsNone(cw_grid.find_answer(space.rows(), "AMBER"))

    def test_every_drop_is_named_in_the_report(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.excluded("amber", "brook")
            decorative_crossword.main(space.fill("--excluded-terms", str(terms)))
            self.assertIn("AMBER", self.printed)
            self.assertIn("BROOK", self.printed)

    def test_a_term_matching_only_a_clue_drops_that_entry(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(
                folder, cli_fixtures.bank_with_clue("The first one")
            )
            terms = space.excluded("first")
            decorative_crossword.main(space.fill("--excluded-terms", str(terms)))
            self.assertIsNone(
                cw_grid.find_answer(space.rows(), cli_fixtures.CLUED_ANSWER)
            )

    def test_a_partial_word_does_not_drop_an_entry(self) -> None:
        # Whole-word matching: "amb" is a prefix of AMBER
        # and must not screen it, or the operator's list silently over-reaches.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.excluded("amb")
            self.assertEqual(
                decorative_crossword.main(space.fill("--excluded-terms", str(terms))), 0
            )
            self.assertIsNotNone(cw_grid.find_answer(space.rows(), "AMBER"))

    def test_blank_lines_and_comments_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.root / "excluded.txt"
            terms.write_text("\n# amber\n  \nalpha\n", encoding="utf-8", newline="\n")
            self.assertEqual(
                decorative_crossword.main(space.fill("--excluded-terms", str(terms))), 0
            )
            # The commented-out term did not take effect...
            self.assertIsNotNone(cw_grid.find_answer(space.rows(), "AMBER"))
            # ...and the real one did, which the report says by name.
            self.assertIn("ALPHA", self.printed)

    def test_a_mis_encoded_terms_file_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = cli_fixtures.write_mis_encoded(space.root / "excluded.txt")
            argv = space.fill("--excluded-terms", str(terms))
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertFalse(space.out.exists())
            self.assertIn("decorative_crossword:", self.errors)

    def test_an_unreadable_terms_file_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--excluded-terms", str(space.root / "absent.txt"))
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertFalse(space.out.exists())

    def test_screening_away_the_featured_answer_exits_two(self) -> None:
        # The two flags contradict each other outright; resolving it silently
        # either way would be wrong.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.excluded("alpha")
            argv = space.fill("--excluded-terms", str(terms), "--feature", "ALPHA")
            self.assertEqual(decorative_crossword.main(argv), 2)

    def test_the_contradiction_names_both_flags(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            terms = space.excluded("alpha")
            argv = space.fill("--excluded-terms", str(terms), "--feature", "ALPHA")
            decorative_crossword.main(argv)
            self.assertIn("--excluded-terms", self.errors)
            self.assertIn("--feature", self.errors)


class TestPreviewSubcommand(cli_fixtures.QuietCase):
    """preview renders an existing grid and never runs a search."""

    def _generated(self, space: cli_fixtures.Workspace, *extra: str) -> None:
        """Fill `space` so there is a real document for preview to read."""
        self.assertEqual(decorative_crossword.main(space.fill(*extra)), 0)

    def test_renders_a_generated_grid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 0)
            self.assertTrue(space.svg.exists())

    def test_unreadable_source_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            code = decorative_crossword.main(
                [
                    "preview",
                    "--source",
                    str(space.root / "absent.json"),
                    "--out",
                    str(space.svg),
                ]
            )
            self.assertEqual(code, 2)

    def test_feature_absent_from_the_grid_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            code = decorative_crossword.main(
                [
                    "preview",
                    "--source",
                    str(space.out),
                    "--out",
                    str(space.svg),
                    "--feature",
                    "NOTHERE",
                ]
            )
            self.assertEqual(code, 2)

    def test_a_feature_present_in_the_grid_is_shaded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self._generated(space, "--feature", "CHALK")
            code = decorative_crossword.main(
                [
                    "preview",
                    "--source",
                    str(space.out),
                    "--out",
                    str(space.svg),
                    "--feature",
                    "CHALK",
                ]
            )
            self.assertEqual(code, 0)
            rendered = space.svg.read_text(encoding="utf-8")
            self.assertEqual(rendered.count(cw_svg.FEATURE_CLASS), len("CHALK"))

    def test_a_non_square_grid_previews_at_its_own_shape(self) -> None:
        # The recurring blind spot in this project's suites: a square grid
        # renders identically under a rows/cols transposition.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--rows") + 1] = "7"
            argv[argv.index("--cols") + 1] = "11"
            self.assertEqual(decorative_crossword.main(argv), 0)
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 0)
            caption = space.svg.read_text(encoding="utf-8")
            self.assertIn("7x11 grid", caption)

    def test_the_cell_size_scales_the_document(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self._generated(space)
            for cell in ("48", "96"):
                code = decorative_crossword.main(
                    [
                        "preview",
                        "--source",
                        str(space.out),
                        "--out",
                        str(space.root / f"{cell}.svg"),
                        "--cell",
                        cell,
                    ]
                )
                self.assertEqual(code, 0)
            small = (space.root / "48.svg").read_text(encoding="utf-8")
            large = (space.root / "96.svg").read_text(encoding="utf-8")
            self.assertNotEqual(small, large)

    def test_a_questionable_grid_still_renders(self) -> None:
        # An entry with no clue, and a theme used but not declared, are for
        # whatever consumes the grid to judge, not this tool.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.out.write_text(
                json.dumps(
                    {
                        "rows": ["CAT", "O..", "WET"],
                        "themes": {},
                        "clues": {"CAT": {"theme": "undeclared"}},
                    }
                ),
                encoding="utf-8",
                newline="\n",
            )
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 0)

    def test_an_incoherent_grid_exits_two_and_writes_nothing(self) -> None:
        broken = {
            "ragged": ["CAT", "WETS"],
            "empty": [],
            "no columns": ["", ""],
            "bad cell": ["CA?", "O..", "WET"],
            "not strings": [["C", "A", "T"]],
        }
        for label, rows in broken.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                space.out.write_text(
                    json.dumps({"rows": rows, "themes": {}, "clues": {}}),
                    encoding="utf-8",
                    newline="\n",
                )
                code = decorative_crossword.main(
                    ["preview", "--source", str(space.out), "--out", str(space.svg)]
                )
                self.assertEqual(code, 2, label)
                self.assertFalse(space.svg.exists(), label)

    def test_a_mis_encoded_source_exits_two(self) -> None:
        # `preview` has no exit 1 at all, as its --help says; an
        # `except OSError` read seam would let a mis-encoded source through
        # as a traceback and exit 1.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            cli_fixtures.write_mis_encoded(space.out)
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 2)
            self.assertFalse(space.svg.exists())
            self.assertIn("decorative_crossword:", self.errors)

    def test_a_non_positive_cell_exits_two(self) -> None:
        # Every length in the document is a multiple of the cell edge, so a
        # zero or negative one writes a negative viewBox and a negative
        # stroke-width: a file nothing can render.
        for cell in ("0", "-5"):
            with self.subTest(cell), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                self._generated(space)
                # QuietCase.setUp runs once per test METHOD, so self.errors
                # holds every earlier iteration's message too: without this
                # mark, the second iteration's flag assertion is satisfied by
                # the first one's output and proves nothing about "-5".
                already_said = len(self.errors)
                code = decorative_crossword.main(
                    [
                        "preview",
                        "--source",
                        str(space.out),
                        "--out",
                        str(space.svg),
                        "--cell",
                        cell,
                    ]
                )
                self.assertEqual(code, 2, cell)
                self.assertFalse(space.svg.exists(), cell)
                self.assertIn("--cell", self.errors[already_said:], cell)

    def _drawn_at(self, space: cli_fixtures.Workspace, cell: str) -> int:
        """Run `preview` on `space`'s grid with `--cell cell`; return the exit code."""
        return decorative_crossword.main(
            ["preview", "--source", str(space.out), "--out", str(space.svg)]
            + ["--cell", cell]
        )

    def test_a_cell_past_the_ceiling_exits_two(self) -> None:
        # A whole number parses at any size, and a few hundred digits overflow
        # the float arithmetic that lays the drawing out: a traceback rather
        # than a refusal. The ceiling refuses that edge and every one past it.
        # The figure is written out here because it is the one an operator is
        # told; the unit tests derive theirs from the constant.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self._generated(space)
            for cell in ("9" * 400, "1001"):
                with self.subTest(digits=len(cell)):
                    already_said = len(self.errors)
                    self.assertEqual(self._drawn_at(space, cell), 2)
                    self.assertFalse(space.svg.exists())
                    self.assertIn(
                        f"--cell must be at most 1000, got {cell}",
                        self.errors[already_said:],
                    )

    def test_the_ceiling_itself_still_draws(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self._generated(space)
            self.assertEqual(self._drawn_at(space, "1000"), 0)
            self.assertTrue(space.svg.exists())

    def test_an_unparseable_source_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.out.write_text("{not json", encoding="utf-8", newline="\n")
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 2)

    def test_a_source_that_is_not_an_object_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.out.write_text("[1, 2, 3]", encoding="utf-8", newline="\n")
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 2)

    def test_an_unwritable_out_path_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self._generated(space)
            space.svg.mkdir()
            code = decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(code, 2)


class TestOneRenderer(cli_fixtures.QuietCase):
    """One renderer behind `fill --preview` and `preview`, not a second renderer."""

    def _both(self, folder: str) -> tuple[str, str]:
        """Render one grid twice -- once inside `fill`, once through `preview`."""
        space = cli_fixtures.Workspace(folder)
        self.assertEqual(
            decorative_crossword.main(space.fill("--preview", str(space.svg))), 0
        )
        second = space.root / "again.svg"
        self.assertEqual(
            decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(second)]
            ),
            0,
        )
        return (
            space.svg.read_text(encoding="utf-8"),
            second.read_text(encoding="utf-8"),
        )

    def test_both_modes_draw_the_grid_identically(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inside, standalone = self._both(folder)
            for layer in _GRID_LAYERS:
                self.assertEqual(
                    _layer_bytes(inside, layer),
                    _layer_bytes(standalone, layer),
                    f"the {layer} layer differs between the two callers",
                )

    def test_only_the_configuration_tier_differs(self) -> None:
        # `preview` has no honest way to know the seed, so it omits the tier
        # rather than inventing it.
        with tempfile.TemporaryDirectory() as folder:
            inside, standalone = self._both(folder)
            self.assertIn("seed: 7", inside)
            self.assertNotIn("seed", standalone)

    def test_the_configuration_tier_stamps_the_values_it_was_given(self) -> None:
        # This tier is the one thing that must not carry a number nothing
        # checked. Asserting only the seed would leave the density range DRAWN
        # BUT UNREAD: swapping min and max would stamp "requested blocked:
        # 95.0-0.0%" and still pass.
        #
        # Every value below is distinct and asymmetric on purpose -- 35 vs 80,
        # 2 vs 1 -- so neither pair can be transposed without the assertion
        # seeing it.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.svg))
            argv[argv.index("--seed") + 1] = "11"
            argv[argv.index("--min-blocked") + 1] = "35"
            argv[argv.index("--max-blocked") + 1] = "80"
            argv[argv.index("--min-themes") + 1] = "2"
            argv[argv.index("--min-entries-per-theme") + 1] = "1"
            decorative_crossword.main(argv)
            rendered = space.svg.read_text(encoding="utf-8")
            self.assertIn("seed: 11", rendered)
            self.assertIn("requested blocked: 35.0-80.0%", rendered)
            self.assertIn("theme floor: 2 theme(s) x 1 entry(s)", rendered)

    def test_neither_handler_draws_anything_of_its_own(self) -> None:
        # The provenance claim behind the two tests above: with the single
        # renderer replaced, BOTH outputs become the replacement entirely --
        # so neither handler can be contributing markup beside it.
        sentinel = "<svg-stand-in/>\n"
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(cw_svg, "render_svg", return_value=sentinel),
        ):
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill("--preview", str(space.svg)))
            self.assertEqual(space.svg.read_text(encoding="utf-8"), sentinel)
            second = space.root / "again.svg"
            decorative_crossword.main(
                ["preview", "--source", str(space.out), "--out", str(second)]
            )
            self.assertEqual(second.read_text(encoding="utf-8"), sentinel)


if __name__ == "__main__":
    unittest.main()
