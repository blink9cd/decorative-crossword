"""Tests for the CLI: exit codes, file effects, and option wiring.

Everything here drives `decorative_crossword.main(argv)`, never a handler
directly. An exit code produced by calling `run_fill(args)` with a
hand-assembled namespace proves nothing about what a malformed command line
does, and a parser test proves nothing about which exception the handler
catches; the exit-code contract is a property of the two together.
"""

import contextlib
import io
import tempfile
import unittest
from unittest import mock

import decorative_crossword
import cw_config
import cw_emit
import cw_grid
import cw_search
import cw_svg
from tests import cli_fixtures


class TestFillExitCodes(cli_fixtures.QuietCase):
    """Exit 0 conforming, 1 not found, 2 the run could not happen."""

    def test_conforming_run_exits_zero_and_writes_the_grid(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(decorative_crossword.main(space.fill()), 0)
            self.assertTrue(space.out.exists())

    def test_missing_bank_exits_two_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.bank.unlink()
            self.assertEqual(decorative_crossword.main(space.fill()), 2)
            self.assertFalse(space.out.exists())

    def test_contradictory_density_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--min-blocked") + 1] = "90"
            argv[argv.index("--max-blocked") + 1] = "10"
            self.assertEqual(decorative_crossword.main(argv), 2)

    def test_unreachable_theme_floor_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--min-themes") + 1] = "9"
            self.assertEqual(decorative_crossword.main(argv), 1)

    def test_exit_one_still_writes_the_best_effort_grid(self) -> None:
        # "Best-effort return" means nothing if the near miss is withheld.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill(*["--preview", str(space.svg)])
            argv[argv.index("--max-blocked") + 1] = "0"
            self.assertEqual(decorative_crossword.main(argv), 1)
            self.assertTrue(space.out.exists())
            self.assertTrue(space.svg.exists())

    def test_feature_absent_from_the_bank_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(
                decorative_crossword.main(space.fill("--feature", "NOPE")), 2
            )

    def test_a_pre_flight_refusal_writes_no_preview_only_because_none_was_asked(
        self,
    ) -> None:
        # The exit-1 pair, stated as its own case: the grid IS written on a
        # pre-flight refusal (steps == 0, nothing searched), and the SVG is
        # absent for the ordinary reason that --preview was omitted -- not
        # because exit 1 suppresses it. Without this,
        # `test_exit_one_still_writes_the_best_effort_grid`'s two assertions
        # could both be satisfied by a rule that keyed on "conforming" rather
        # than on the flag.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--min-themes") + 1] = "9"
            self.assertEqual(decorative_crossword.main(argv), 1)
            self.assertTrue(space.out.exists())
            self.assertFalse(space.svg.exists())

    def test_exit_two_writes_neither_the_grid_nor_the_preview(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.svg), "--feature", "NOPE")
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertFalse(space.out.exists())
            self.assertFalse(space.svg.exists())

    def test_an_unwritable_out_path_exits_two(self) -> None:
        # A directory where the file belongs exits 2. That it is refused
        # before the search starts, not at the write, `test_cli_outputs.py`
        # pins by the refusal's words: the exit code is 2 either way.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.out.mkdir()
            self.assertEqual(decorative_crossword.main(space.fill()), 2)

    def test_an_unwritable_preview_path_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            space.svg.mkdir()
            argv = space.fill("--preview", str(space.svg))
            self.assertEqual(decorative_crossword.main(argv), 2)

    def test_a_refusal_after_the_search_leaves_no_grid_behind(self) -> None:
        # The no-undo ordering rule: the preview is RENDERED before anything is
        # written, so a refusal that could have been found first does not leave
        # a grid on disk, since exit 2 writes no file.
        # Reached through the renderer because nothing a real bank can hold
        # makes a render of a searched grid fail -- which is exactly why the
        # ordering would otherwise be an untested claim.
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(
                cw_svg, "render_svg", side_effect=cw_emit.EmitError("refused")
            ),
        ):
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.svg))
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertFalse(space.out.exists())
            self.assertFalse(space.svg.exists())

    def test_a_mis_encoded_bank_exits_two(self) -> None:
        # `UnicodeDecodeError` is a ValueError, NOT an OSError, so an
        # `except OSError` read seam lets it past the CLI's refusal set
        # entirely: traceback, exit 1, no diagnostic. A bank saved from an
        # editor in a legacy code page is the ordinary way here.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            cli_fixtures.write_mis_encoded(space.bank)
            self.assertEqual(decorative_crossword.main(space.fill()), 2)
            self.assertFalse(space.out.exists())
            self.assertIn("decorative_crossword:", self.errors)

    def test_a_failed_grid_write_leaves_no_preview_behind(self) -> None:
        # Pins the no-undo ORDER, not just that both files appear: with the
        # preview written first, this passes only if the grid write is what
        # comes first. Nothing else in the suite can tell the two orders apart.
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(
                cw_emit, "write_document", side_effect=cw_emit.EmitError("refused")
            ),
        ):
            space = cli_fixtures.Workspace(folder)
            argv = space.fill("--preview", str(space.svg))
            self.assertEqual(decorative_crossword.main(argv), 2)
            self.assertFalse(space.svg.exists())

    def test_a_bug_in_the_search_is_not_reported_as_the_operator_s_mistake(
        self,
    ) -> None:
        # The refusal set names each type rather than their common base.
        # Collapsing it to `ValueError` would turn a genuine bug in the search
        # or the renderer into "decorative_crossword: <internal message>" and
        # exit 2 -- an operator told to fix their bank for a fault in the tool.
        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(cw_search, "search", side_effect=ValueError("a bug")),
        ):
            space = cli_fixtures.Workspace(folder)
            with self.assertRaises(ValueError):
                decorative_crossword.main(space.fill())

    def test_the_placeholder_clue_option_is_gone(self) -> None:
        """`--placeholder-clue` is not an option.

        argparse rejects the unknown option during parsing, so this is a
        SystemExit rather than one of the tool's own exit codes -- the flag is
        absent, not merely inert.
        """
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            with self.assertRaises(SystemExit):
                decorative_crossword.main(
                    space.fill("--placeholder-clue", "Clue for {answer}")
                )

    def test_a_bank_clue_that_would_break_the_page_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(
                folder, cli_fixtures.bank_with_clue("bad </script> clue")
            )
            self.assertEqual(decorative_crossword.main(space.fill()), 2)
            self.assertFalse(space.out.exists())

    def test_a_theme_key_that_would_break_the_page_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(
                folder, cli_fixtures.bank_with_theme_key("a</script>b")
            )
            self.assertEqual(decorative_crossword.main(space.fill()), 2)
            self.assertFalse(space.out.exists())


class TestFillDiagnostics(cli_fixtures.QuietCase):
    """Where each stream's content goes, and what it says."""

    def test_the_report_goes_to_stdout_on_a_conforming_run(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            self.assertIn("Placed", self.printed)
            self.assertEqual(self.errors, "")

    def test_the_report_goes_to_stdout_on_exit_one_too(self) -> None:
        # The report is the tool's human-facing product on both 0 and 1, and
        # it NAMES the missed constraint.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--min-themes") + 1] = "9"
            self.assertEqual(decorative_crossword.main(argv), 1)
            self.assertIn("--min-themes", self.printed)

    def test_a_refusal_names_the_tool_and_the_cause_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(
                decorative_crossword.main(space.fill("--feature", "NOPE")), 2
            )
            self.assertEqual(self.printed, "")
            self.assertIn("decorative_crossword:", self.errors)
            self.assertIn("NOPE", self.errors)

    def test_a_contradictory_density_names_the_flag_at_fault(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--min-blocked") + 1] = "90"
            argv[argv.index("--max-blocked") + 1] = "10"
            decorative_crossword.main(argv)
            self.assertIn("--min-blocked", self.errors)


class TestFillOptions(cli_fixtures.QuietCase):
    """Size, density and determinism are wired through to the search."""

    def test_rows_and_cols_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = [
                "fill",
                "--bank",
                str(space.bank),
                "--out",
                str(space.out),
                "--seed",
                "7",
            ]
            self.assertEqual(decorative_crossword.main(argv), 2)

    def test_each_of_rows_and_cols_is_required_on_its_own(self) -> None:
        # Omitting BOTH proves only that one of them is required: a default on
        # --rows alone would still pass the test above, because --cols alone
        # still fails the check. Each is dropped separately here, and the
        # message has to name the one that is missing. Refused by the tool
        # rather than by argparse, since --source can supply both.
        for missing, present in (("--rows", "--cols"), ("--cols", "--rows")):
            with self.subTest(missing), tempfile.TemporaryDirectory() as folder:
                space = cli_fixtures.Workspace(folder)
                argv = [
                    "fill",
                    "--bank",
                    str(space.bank),
                    "--out",
                    str(space.out),
                    "--seed",
                    "7",
                    present,
                    "9",
                ]
                self.assertEqual(decorative_crossword.main(argv), 2)
                self.assertIn(
                    f"{missing} is required unless --source gives the grid",
                    self.errors,
                )

    def test_the_grid_has_the_requested_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--rows") + 1] = "7"
            argv[argv.index("--cols") + 1] = "11"
            decorative_crossword.main(argv)
            rows = space.rows()
            self.assertEqual(len(rows), 7)
            self.assertTrue(all(len(row) == 11 for row in rows))

    def test_the_same_seed_produces_a_byte_identical_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            first = space.out.read_bytes()
            space.out.unlink()
            decorative_crossword.main(space.fill())
            self.assertEqual(space.out.read_bytes(), first)

    def test_a_different_seed_reaches_a_different_grid(self) -> None:
        # The other half of determinism: a seed that changed nothing would
        # satisfy the byte-identical test above forever.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--max-blocked") + 1] = "70"
            decorative_crossword.main(argv)
            first = space.rows()
            argv[argv.index("--seed") + 1] = "8"
            decorative_crossword.main(argv)
            self.assertNotEqual(space.rows(), first)

    def test_preview_is_written_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill("--preview", str(space.svg)))
            self.assertTrue(
                space.svg.read_text(encoding="utf-8").lstrip().startswith("<")
            )

    def test_no_preview_file_when_the_flag_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            decorative_crossword.main(space.fill())
            self.assertFalse(space.svg.exists())

    def test_a_tightened_density_range_actually_binds(self) -> None:
        # The end-to-end claim that density is not merely accepted but obeyed.
        # The lower bound is the interesting half -- it forces the search to
        # STOP placing, which a window checked only from above would never
        # exercise.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--min-blocked") + 1] = "60"
            argv[argv.index("--max-blocked") + 1] = "95"
            self.assertEqual(decorative_crossword.main(argv), 0)
            blocked = cw_grid.blocked_percent(tuple(space.rows()))
            self.assertGreaterEqual(blocked, 60.0)
            self.assertLessEqual(blocked, 95.0)

    def test_the_featured_answer_is_placed_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(
                decorative_crossword.main(space.fill("--feature", "CHALK")), 0
            )
            self.assertIsNotNone(cw_grid.find_answer(space.rows(), "CHALK"))
            self.assertIn("CHALK", self.printed)

    def test_a_bank_clue_reaches_the_document_and_a_missing_one_is_filled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(
                folder, cli_fixtures.bank_with_clue("The first one")
            )
            argv = space.fill("--feature", cli_fixtures.CLUED_ANSWER)
            argv[argv.index("--min-blocked") + 1] = "70"
            self.assertEqual(decorative_crossword.main(argv), 0)
            self.assertEqual(
                space.clues()[cli_fixtures.CLUED_ANSWER]["clue"], "The first one"
            )

    def test_an_unclued_bank_answer_reaches_the_page_with_an_empty_clue(self) -> None:
        # The end-to-end counterpart of test_emit's unit case: the default bank
        # writes no clues at all, so every emitted record must carry the key
        # with an empty value -- not a generated sentence, and not no key.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            self.assertEqual(decorative_crossword.main(space.fill()), 0)
            clues = space.clues()
            self.assertTrue(clues, "the run emitted no clues at all")
            self.assertTrue(
                all(record["clue"] == "" for record in clues.values()),
                f"an unclued answer did not emit an empty clue: {clues}",
            )


class TestParser(cli_fixtures.QuietCase):
    """--help is self-documenting: every optional shows its live default."""

    def test_no_subcommand_exits_two(self) -> None:
        self.assertEqual(decorative_crossword.main([]), 2)

    def _help_for(self, subcommand: str) -> str:
        """Capture a subcommand's --help without exiting the test run.

        Through the public entry point rather than argparse internals: reaching
        into `parser._subparsers` would pin a private structure that changes
        between CPython releases.
        """
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit):
            decorative_crossword.main([subcommand, "--help"])
        return buffer.getvalue()

    def test_fill_help_shows_every_optional_default(self) -> None:
        # Reads the live DEFAULTS rather than repeating literals: the assertion
        # is "--help agrees with the tool", which a hardcoded expectation
        # would not be.
        rendered = self._help_for("fill")
        for key in ("min_blocked", "max_blocked", "time_budget", "min_themes"):
            self.assertIn(
                str(cw_config.DEFAULTS[key]),
                rendered,
                f"--help does not render the live default for {key}",
            )

    def test_fill_help_renders_defaults_in_the_formatter_s_own_form(self) -> None:
        # The stronger claim: the value appears as the formatter's
        # "(default: X)", which is derived from the live `default=`. A value
        # merely mentioned in prose would satisfy the test above.
        # Whitespace-normalized first: argparse wraps a help line wherever it
        # runs out of width, so "(default:" and its value routinely land on
        # two lines. Asserting on the raw text would make this test a function
        # of the terminal width rather than of the default.
        rendered = " ".join(self._help_for("fill").split())
        for key in ("min_blocked", "max_blocked", "time_budget", "max_steps"):
            self.assertIn(f"(default: {cw_config.DEFAULTS[key]})", rendered)

    def test_the_parser_s_own_defaults_are_the_live_defaults(self) -> None:
        # And the other end of the same claim: what --help renders is what the
        # tool would actually use. Together these two make a hardcoded literal
        # in a help string unable to pass while the real default differs.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            args = decorative_crossword.build_parser().parse_args(
                [
                    "fill",
                    "--bank",
                    str(space.bank),
                    "--out",
                    str(space.out),
                    "--seed",
                    "1",
                    "--rows",
                    "5",
                    "--cols",
                    "5",
                ]
            )
            for key in (
                "min_blocked",
                "max_blocked",
                "min_themes",
                "min_entries_per_theme",
                "time_budget",
                "max_steps",
            ):
                self.assertEqual(getattr(args, key), cw_config.DEFAULTS[key])

    def test_fill_help_carries_a_worked_invocation(self) -> None:
        # The epilog, not just the flag list.
        rendered = self._help_for("fill")
        self.assertIn("--rows", rendered)
        self.assertIn("--seed", rendered)
        self.assertIn("--bank", rendered)

    def test_the_worked_invocation_carries_a_size_and_a_density(self) -> None:
        # The epilog must carry a COMPLETE command line, with a size and a
        # density on it. An epilog listing flag names would pass the test
        # above; this one needs values beside them.
        rendered = self._help_for("fill")
        # A VALUE beside each flag: the options list can only ever render
        # "--rows ROWS", so a token carrying a number can have come from
        # nowhere but the worked invocation.
        for token in ("--rows 13", "--cols 13", "--min-blocked 30", "--seed 1"):
            self.assertIn(token, rendered, f"the epilog does not show {token}")

    def test_preview_help_shows_the_cell_default(self) -> None:
        self.assertIn(str(cw_config.DEFAULTS["cell"]), self._help_for("preview"))

    def test_the_preview_parser_s_cell_default_is_the_live_default(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            args = decorative_crossword.build_parser().parse_args(
                ["preview", "--source", str(space.out), "--out", str(space.svg)]
            )
            self.assertEqual(args.cell, cw_config.DEFAULTS["cell"])


if __name__ == "__main__":
    unittest.main()
