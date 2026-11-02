"""Grouped suite: `fill --source` completing a partial run, on the command line.

A run the bank does not hold and the source does not declare is a partial run
when a bank answer could still be laid over it, and `fill` must finish it. These
cases drive `main` end to end, because what each proves is a process boundary:
an exit code, the grid written, and the words the report prints.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import tempfile
import unittest

import cw_grid
from tests import cli_fixtures
from tests.source_fixtures import BLANK as _BLANK
from tests.source_fixtures import SOURCE_NAME as _SOURCE_NAME
from tests.source_fixtures import SourceCase, filled, source_fill, write_source

#: ALPH across the top of a 5x9: only ALPHA, a bank answer, can complete it.
#: Wider than tall, so a transposed read of the rows cannot pass.
_HALF_ALPHA = ["ALPH....."] + [_BLANK] * 4


#: ALPH over a Z on a 2x9. ALPHA would stand its A on the Z, and AZ is no
#: answer, so the one completion there is can never be laid.
_UNFINISHABLE = ["ALPH.....", "....Z...."]


class TestCompletingAPartialRun(SourceCase):
    """A half-written source word the bank can finish is finished, never kept half-written."""

    def test_a_half_written_word_the_bank_completes_is_filled_in(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _HALF_ALPHA)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 0, self.errors)
            written = space.rows()
            self.assertLessEqual(filled(_HALF_ALPHA).items(), filled(written).items())
            self.assertIn(
                cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="ALPHA"),
                cw_grid.runs_from_rows(written),
            )
            self.assertIn(
                "From --source: 4 fixed letter(s) in 0 entry(s), 1 partial run(s), "
                "0 lone letter(s).",
                self.printed,
            )
            self.assertIn(
                "Completed from --source (1): ALPH as ALPHA across at (0, 0).",
                self.printed,
            )

    def test_a_run_the_walk_never_completes_writes_an_empty_board(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, _UNFINISHABLE)
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 1, self.errors)
            self.assertEqual(space.rows(), [_BLANK, _BLANK])
            self.assertIn(
                "the partial run 'ALPH' across at (0, 0) was never completed by a "
                "bank answer",
                self.printed,
            )

    def test_a_declared_run_is_held_exactly_and_never_completed(self) -> None:
        # Declared, ALPH is an entry the source keeps: held as its exact run, so
        # ALPHA never grows out of it, and a kept entry never grows even under
        # --absorb-entries (test_cli_absorb).
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(
                space.root / _SOURCE_NAME,
                _HALF_ALPHA,
                clues={"ALPH": {"clue": "Most of a letter"}},
            )
            code = self.run_main(source_fill(space, source))
            self.assertEqual(code, 0, self.errors)
            self.assertIn(
                cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="ALPH"),
                cw_grid.runs_from_rows(space.rows()),
            )
            self.assertIn(
                "Kept from --source, not in the bank (1): ALPH.", self.printed
            )
            self.assertNotIn("Completed from --source", self.printed)


class TestAPinCompletingAPartialRun(SourceCase):
    """A pin lying along all of a partial run names the completion; any other lengthening is refused."""

    def _pinned(self, rows: list[str], *extra: str) -> tuple[int | None, list[str]]:
        """Run `fill` from `rows` with `extra` flags; the exit code and the grid written."""
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(space.root / _SOURCE_NAME, rows)
            code = self.run_main(source_fill(space, source, *extra))
            return code, space.rows() if space.out.exists() else []

    def test_a_pin_lying_along_a_partial_run_completes_it(self) -> None:
        # A partial run is no entry, so a pin may name the answer that
        # finishes it.
        code, written = self._pinned(_HALF_ALPHA, "--feature", "ALPHA@0,0,across")
        self.assertEqual(code, 0, self.errors)
        self.assertLessEqual(filled(_HALF_ALPHA).items(), filled(written).items())
        self.assertIn(
            cw_grid.Run(row=0, col=0, direction=cw_grid.ACROSS, text="ALPHA"),
            cw_grid.runs_from_rows(written),
        )
        self.assertIn(
            "Completed from --source (1): ALPH as ALPHA across at (0, 0).",
            self.printed,
        )

    def test_a_down_pin_growing_a_partial_run_at_its_start_completes_it(self) -> None:
        # MBER down from (1, 0): AMBER's first letter lands before the run, so
        # the completion's first cell is not the run's.
        rows = [_BLANK, "M........", "B........", "E........", "R........"]
        code, written = self._pinned(rows, "--feature", "AMBER@0,0,down")
        self.assertEqual(code, 0, self.errors)
        self.assertIn(
            cw_grid.Run(row=0, col=0, direction=cw_grid.DOWN, text="AMBER"),
            cw_grid.runs_from_rows(written),
        )
        self.assertIn(
            "Completed from --source (1): MBER as AMBER down at (0, 0).",
            self.printed,
        )

    def test_a_crossing_pin_lengthening_a_partial_run_is_refused(self) -> None:
        # A down pin starting just past ALPH's last letter lengthens it without
        # lying along it, whether the longer run is no answer (ALPHB) or one
        # the bank holds (ALPHA): a pin completes a run only by covering it.
        for pin in ("BRAVO@0,4,down", "AMBER@0,4,down"):
            with self.subTest(pin=pin):
                code, written = self._pinned(_HALF_ALPHA, "--feature", pin)
                self.assertEqual(code, 2)
                self.assertIn(
                    "lengthen the --source partial run 'ALPH' at (0, 0) across",
                    self.errors,
                )
                self.assertEqual(written, [])

    def test_a_pin_contradicting_a_letter_of_a_partial_run_is_refused(self) -> None:
        code, written = self._pinned(_HALF_ALPHA, "--feature", "ANVIL@0,0,across")
        self.assertEqual(code, 2)
        self.assertIn("disagrees with --source at (0, 1): 'L' against 'N'", self.errors)
        self.assertEqual(written, [])

    def test_a_pin_extending_a_declared_run_is_still_refused(self) -> None:
        # Declared, ALPH is a kept entry, which no pin may grow, even under
        # --absorb-entries: that flag grows only the entries the bank holds.
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = write_source(
                space.root / _SOURCE_NAME,
                _HALF_ALPHA,
                clues={"ALPH": {"clue": "Most of a letter"}},
            )
            code = self.run_main(
                source_fill(space, source, "--feature", "ALPHA@0,0,across")
            )
            self.assertEqual(code, 2)
            self.assertIn("extend the --source entry 'ALPH'", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_pinned_answer_the_bank_lacks_is_named_as_not_in_the_bank(self) -> None:
        # ALPHA could still finish ALPH, so the source passes and the pin
        # reaches the feature check, which names the missing answer.
        code, _ = self._pinned(_HALF_ALPHA, "--feature", "ALPHAS@0,0,across")
        self.assertEqual(code, 2)
        self.assertIn("the featured answer 'ALPHAS' is not in the bank", self.errors)

    def test_a_run_nothing_in_the_bank_could_finish_is_refused_before_the_pin(
        self,
    ) -> None:
        # No bank answer completes QUIL, so the source check refuses it first,
        # in the words it uses without a pin: the refusal order is unchanged.
        rows = ["QUIL....."] + [_BLANK] * 4
        code, _ = self._pinned(rows, "--feature", "QUILT@0,0,across")
        self.assertEqual(code, 2)
        self.assertIn("nor completable by a bank answer: 'QUIL' across", self.errors)


if __name__ == "__main__":
    unittest.main()
