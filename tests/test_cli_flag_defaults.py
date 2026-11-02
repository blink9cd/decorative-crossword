"""On/off flags print no default in `--help`, and reach the code as booleans.

An on/off flag's `--help` line printed `(default: False)`, which tells a reader
nothing: a flag that is off unless given is what `store_true` means. Each such
flag is therefore declared with `default=None`, which the help formatter leaves
out, and that moves the work to every place the parsed value is read. An absent
flag now arrives as None, so each reader wraps it in `bool()` before it reaches
a typed field.

None and False draw the same picture and choose the same grid, so no test of the
output can notice a wrap that was removed: a field annotated `bool` would hold
None and every result would still pass. These tests watch the values instead, at
the two seams every reader goes through: the typed configuration each subcommand
builds, and the `empty_blocks` keyword of `cw_command_base.render`.
"""

import contextlib
import io
import tempfile
import unittest
from collections.abc import Callable
from typing import TypeVar
from unittest import mock

import cw_command_base
import cw_commands
import cw_gaps_command
import cw_read_commands
import decorative_crossword
from tests import cli_fixtures
from tests.test_cli_gaps import GapsSpace
from tests.test_cli_shade import ShadeSpace

#: Every subcommand, each of which takes at least one on/off flag.
_SUBCOMMANDS = ("fill", "preview", "shade", "gaps")

#: What an on/off flag's help line printed before it was declared with None.
_FALSE_DEFAULT = "(default: False)"

_Value = TypeVar("_Value")


def _recorder(
    target: Callable[..., _Value],
) -> tuple[list[_Value], Callable[..., _Value]]:
    """Wrap `target` so each value it returns is also kept, in call order.

    `mock.Mock(wraps=...)` records the arguments of a call but not what it
    returned, and the configuration a builder returns is what these tests read.
    """
    seen: list[_Value] = []

    def record(*args: object, **kwargs: object) -> _Value:
        value = target(*args, **kwargs)
        seen.append(value)
        return value

    return seen, record


class TestOnOffFlagsPrintNoDefault(unittest.TestCase):
    """No subcommand's `--help` prints a False default for an on/off flag."""

    def _help_for(self, subcommand: str) -> str:
        """`subcommand --help` as printed, with its wrapping undone."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            decorative_crossword.main([subcommand, "--help"])
        return " ".join(out.getvalue().split())

    def test_no_subcommand_help_prints_a_false_default(self) -> None:
        for subcommand in _SUBCOMMANDS:
            with self.subTest(subcommand=subcommand):
                self.assertNotIn(_FALSE_DEFAULT, self._help_for(subcommand))

    def test_the_flags_still_read_as_off_unless_given(self) -> None:
        parsed = decorative_crossword.build_parser().parse_args(
            ["gaps", "--source", "grid_source.json"]
        )
        self.assertFalse(parsed.include_absorbing)
        self.assertFalse(parsed.empty_blocks)


class TestOnOffFlagsReachTheCodeAsBooleans(cli_fixtures.QuietCase):
    """An absent flag reaches each typed field and `render` as False, not None."""

    def _rendered_empty_blocks(self, argv: list[str]) -> list[object]:
        """Run `argv` and return the `empty_blocks` value of each render it drew."""
        spy = mock.Mock(wraps=cw_command_base.render)
        with mock.patch.object(cw_command_base, "render", spy):
            self.assertEqual(decorative_crossword.main(argv), 0)
        self.assertTrue(spy.call_args_list, "the run drew no render to inspect")
        return [call.kwargs["empty_blocks"] for call in spy.call_args_list]

    def test_fill_builds_absorb_entries_as_false(self) -> None:
        seen, record = _recorder(cw_commands._config_from)
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            with mock.patch.object(cw_commands, "_config_from", record):
                self.assertEqual(decorative_crossword.main(space.fill()), 0)
        self.assertIs(seen[0].absorb_entries, False)

    def test_gaps_builds_include_absorbing_as_false(self) -> None:
        seen, record = _recorder(cw_gaps_command._config_from)
        with tempfile.TemporaryDirectory() as folder:
            space = GapsSpace(folder)
            with mock.patch.object(cw_gaps_command, "_config_from", record):
                self.assertEqual(decorative_crossword.main(space.argv()), 0)
        self.assertIs(seen[0].include_absorbing, False)

    def test_shade_builds_exclude_grid_answers_as_false(self) -> None:
        seen, record = _recorder(cw_read_commands._shade_config_from)
        with tempfile.TemporaryDirectory() as folder:
            space = ShadeSpace(folder)
            with mock.patch.object(cw_read_commands, "_shade_config_from", record):
                self.assertEqual(
                    decorative_crossword.main(space.argv("--word", "CAT")), 0
                )
        self.assertIs(seen[0].exclude_grid_answers, False)

    def test_every_render_receives_empty_blocks_as_false(self) -> None:
        # A folder each: every space writes its own `grid_source.json`.
        with contextlib.ExitStack() as stack:
            fill = cli_fixtures.Workspace(
                stack.enter_context(tempfile.TemporaryDirectory())
            )
            shade = ShadeSpace(stack.enter_context(tempfile.TemporaryDirectory()))
            gaps = GapsSpace(stack.enter_context(tempfile.TemporaryDirectory()))
            runs = {
                "fill": fill.fill("--preview", str(fill.svg)),
                "preview": [
                    "preview",
                    "--source",
                    str(shade.source),
                    "--out",
                    str(shade.svg),
                ],
                "shade": shade.argv("--word", "CAT", "--out", str(shade.svg)),
                "gaps": gaps.argv("--out", str(gaps.svg)),
            }
            for subcommand, argv in runs.items():
                with self.subTest(subcommand=subcommand):
                    for value in self._rendered_empty_blocks(argv):
                        self.assertIs(value, False)


if __name__ == "__main__":
    unittest.main()
