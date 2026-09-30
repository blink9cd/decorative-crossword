"""CLI test: every `--cell` option states its ceiling, `cw_config.MAX_CELL`, in `--help`.

Every length the SVG writer emits is a multiple of the cell edge, and each is
written through a float, so an edge a few hundred digits long overflows that
conversion. `preview`, `shade` and `gaps` refuse an edge past the ceiling at
exit 2 (`test_config.py` and `test_cli_preview.py` pin the refusal); this pins
that the operator is told the ceiling before running into it.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import cw_config
import decorative_crossword
from tests import cli_fixtures


class TestCellCeilingInTheHelp(cli_fixtures.QuietCase):
    """The ceiling reaches the operator in `--help`, not only in a refusal."""

    def test_every_cell_option_states_the_ceiling_in_its_help(self) -> None:
        for command in ("preview", "shade", "gaps"):
            with self.subTest(command):
                already = len(self.printed)
                with self.assertRaises(SystemExit):
                    decorative_crossword.main([command, "--help"])
                # Joined back into one line: argparse wraps help to the
                # terminal's width, which may break the phrase anywhere.
                helped = " ".join(self.printed[already:].split())
                self.assertIn(f"at most {cw_config.MAX_CELL}", helped)
