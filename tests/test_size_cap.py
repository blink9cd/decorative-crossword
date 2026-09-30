"""Tests for the largest grid this tool makes or reads: 25 x 25.

Every route a size arrives by is refused past the cap at exit 2, naming the
input that asked for more: `fill`'s `--rows` and `--cols`, a `--mask` picture,
and every grid file read -- `fill --source`, `preview`, `shade` and `gaps`
alike. A `--source` that would GROW past the cap is refused by the flag that
grows it, before a grid of that size is built. Exactly 25 is accepted on each
route, so a cap that crept one cell lower fails here as surely as one that went
missing. `fill --help` states the cap on both size flags, and what else
supplies a size. And the search makes room on the interpreter's stack for the
deepest walk its grid allows.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import inspect
import sys
import tempfile
import unittest
from pathlib import Path

import cw_command_base
import cw_config
import cw_emit
import cw_mask
import cw_search
import decorative_crossword

from tests import cli_fixtures, source_fixtures
from tests.search_fixtures import config as _config
from tests.search_fixtures import still as _still
from tests.search_fixtures import themed_bank as _themed_bank

#: The cap, written out rather than read from the code under test, so a
#: changed constant fails here instead of moving the test along with it.
_CAP = 25

#: What every refusal of an oversize grid file or picture closes with.
_TOO_BIG = f"larger than the {_CAP}x{_CAP} most a grid may be"


def _square(side: int) -> list[str]:
    """A `side` x `side` grid: AB at its top-left corner, every other cell blocked."""
    return ["AB" + "." * (side - 2)] + ["." * side] * (side - 1)


def _picture(rows: int, cols: int) -> str:
    """A `--mask` picture of `rows` x `cols` free cells."""
    return "".join("." * cols + "\n" for _ in range(rows))


class TestTheFillSize(unittest.TestCase):
    """`--rows` and `--cols`, whatever supplied them, are at most the cap."""

    def test_each_flag_past_the_cap_is_refused_by_name(self) -> None:
        for flag, config in (
            ("--rows", _config(rows=_CAP + 1)),
            ("--cols", _config(cols=_CAP + 1)),
        ):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(
                    cw_config.ConfigError, f"^{flag} must be at most 25, got 26$"
                ):
                    cw_config.validate_fill_config(config)

    def test_exactly_the_cap_is_accepted(self) -> None:
        cw_config.validate_fill_config(_config(rows=_CAP, cols=_CAP))


class TestTheMaskSize(unittest.TestCase):
    """A `--mask` picture past the cap is refused, naming the file."""

    def test_a_picture_wider_or_taller_than_the_cap_is_refused(self) -> None:
        for rows, cols in ((1, _CAP + 1), (_CAP + 1, 1)):
            with self.subTest(rows=rows, cols=cols):
                with self.assertRaises(cw_mask.MaskError) as caught:
                    cw_mask.parse_mask(_picture(rows, cols), "shape.txt")
                self.assertEqual(
                    str(caught.exception),
                    f"mask file shape.txt draws a {rows}x{cols} grid, {_TOO_BIG}",
                )

    def test_a_picture_exactly_the_cap_is_read(self) -> None:
        mask = cw_mask.parse_mask(_picture(_CAP, _CAP), "shape.txt")
        self.assertEqual((mask.rows, mask.cols), (_CAP, _CAP))


class TestTheGridFileSize(cli_fixtures.QuietCase):
    """A grid file past the cap is refused by the one reader every command shares."""

    def test_a_grid_wider_or_taller_than_the_cap_is_refused(self) -> None:
        for rows in (_square(_CAP + 1)[:1], [row[:1] for row in _square(_CAP + 1)]):
            height, width = len(rows), len(rows[0])
            with self.subTest(height=height, width=width):
                with tempfile.TemporaryDirectory() as folder:
                    path = source_fixtures.write_source(
                        Path(folder) / "grid.json", rows
                    )
                    with self.assertRaises(cw_emit.EmitError) as caught:
                        cw_command_base.load_source("tool", path)
                self.assertEqual(
                    str(caught.exception),
                    f"grid file {path}: the grid is {height}x{width}, {_TOO_BIG}",
                )

    def test_a_grid_exactly_the_cap_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = source_fixtures.write_source(
                Path(folder) / "grid.json", _square(_CAP)
            )
            document = cw_command_base.load_source("tool", path)
        self.assertEqual(len(document.rows), _CAP)


class TestEveryCommandRefusesPastTheCap(source_fixtures.SourceCase):
    """End to end: exit 2, the input named, and nothing written."""

    def test_every_command_refuses_an_oversize_grid_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = source_fixtures.write_source(
                space.root / source_fixtures.SOURCE_NAME, _square(_CAP + 1)
            )
            path = str(source)
            commands = {
                "preview": ["preview", "--source", path, "--out", str(space.svg)],
                "shade": ["shade", "--source", path, "--word", "CAT"],
                "gaps": ["gaps", "--source", path],
                "fill": source_fixtures.source_fill(space, source),
            }
            for name, argv in commands.items():
                with self.subTest(command=name):
                    # Only this command's own stderr: the refusal is worded the
                    # same for all four, so an earlier one must not answer here.
                    before = len(self.errors)
                    self.assertEqual(self.run_main(argv), 2)
                    self.assertIn(
                        f"grid file {source}: the grid is 26x26, {_TOO_BIG}",
                        self.errors[before:],
                    )
                    self.assertFalse(space.svg.exists())
                    self.assertFalse(space.out.exists())

    def test_a_source_grown_past_the_cap_is_refused_by_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = source_fixtures.write_source(
                space.root / source_fixtures.SOURCE_NAME, _square(_CAP)
            )
            argv = source_fixtures.source_fill(space, source, "--rows", "26")
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn("--rows must be at most 25, got 26", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_flag_far_past_the_cap_is_refused_before_the_source_grows(self) -> None:
        # A source is placed on the grid its flags ask for before the whole
        # configuration is checked, so a flag this far past the cap asked for
        # more cells than the interpreter can count: a traceback, where one a
        # little smaller would have been gigabytes of blocked cells.
        far = str(10**20)
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            source = source_fixtures.write_source(
                space.root / source_fixtures.SOURCE_NAME, _square(2)
            )
            argv = source_fixtures.source_fill(space, source, "--rows", far)
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn(f"--rows must be at most 25, got {far}", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_mask_past_the_cap_is_refused_by_its_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            shape = space.mask(*("." * (_CAP + 1) for _ in range(_CAP + 1)))
            argv = source_fixtures.without_size(space.fill("--mask", str(shape)))
            argv[argv.index("--max-steps") + 1] = "1"
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn(f"mask file {shape} draws a 26x26 grid", self.errors)
            self.assertFalse(space.out.exists())

    def test_a_flag_past_the_cap_is_refused_before_a_search(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            argv = space.fill()
            argv[argv.index("--cols") + 1] = "26"
            argv[argv.index("--max-steps") + 1] = "1"
            self.assertEqual(self.run_main(argv), 2)
            self.assertIn("--cols must be at most 25, got 26", self.errors)
            self.assertFalse(space.out.exists())


class TestTheHelpStatesTheCap(cli_fixtures.QuietCase):
    """`fill --help` states the cap on both size flags, and what else supplies a size."""

    def test_each_size_flag_states_the_cap(self) -> None:
        with self.assertRaises(SystemExit):
            decorative_crossword.main(["fill", "--help"])
        # Joined back into one line: argparse wraps help to the terminal's
        # width, which may break a phrase anywhere.
        helped = " ".join(self.printed.split())
        for phrase in (
            f"Grid height in cells, at most {_CAP};",
            f"Grid width in cells, at most {_CAP};",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, helped)
        # A --mask picture supplies the size too, as its own help says.
        self.assertEqual(
            helped.count("required unless --source, which it may only grow, or --mask"),
            2,
        )


class TestTheWalkHasRoomToRecurse(unittest.TestCase):
    """`search` raises the recursion limit to what its grid can need, never lowering."""

    def setUp(self) -> None:
        self.original = sys.getrecursionlimit()

    def _search_under(
        self, limit: int, config: cw_config.FillConfig
    ) -> tuple[cw_search.SearchOutcome, int]:
        """A search run under `limit`, and the limit it left behind.

        The original limit is back before anything else runs, error or not:
        under the low one, even reporting a failure would overflow.
        """
        sys.setrecursionlimit(limit)
        try:
            return (
                cw_search.search(_themed_bank(), config, clock=_still),
                sys.getrecursionlimit(),
            )
        finally:
            sys.setrecursionlimit(self.original)

    def test_a_limit_too_low_for_the_walk_is_raised_before_it(self) -> None:
        # Ten frames above this one: far fewer than a search stands on. A 25x25
        # can need 1,975 against the default 1,000, so the search makes room
        # for its own grid -- here a 9x9, 3 x 81 + 100 -- before it walks.
        outcome, left = self._search_under(len(inspect.stack(0)) + 10, _config())
        self.assertTrue(outcome.conforming)
        self.assertEqual(
            left,
            cw_search.FRAMES_PER_PLACEMENT * 9 * 9 + cw_search.FRAMES_OUTSIDE_THE_WALK,
        )

    def test_a_higher_limit_is_left_alone(self) -> None:
        _, left = self._search_under(50_000, _config(max_steps=1))
        self.assertEqual(left, 50_000)


if __name__ == "__main__":
    unittest.main()
