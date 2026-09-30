"""Fixtures shared by the `fill --source` command-line suites.

Not named ``test_*.py`` on purpose: unittest discovery would otherwise collect
it as a suite of its own, and the aggregator's per-file floor map would have to
carry a file holding no tests. It is a plain module the suites import, so each
helper that writes a source or runs `main` is defined exactly once.
"""

import contextlib
import json
from pathlib import Path

import cw_grid
import decorative_crossword
from tests import cli_fixtures

#: One blank row of a 9-wide source.
BLANK = "." * 9


#: What `--source` is saved as, beside the workspace's own `grid_source.json`
#: `--out`, so the two never name one file unless a case means them to.
SOURCE_NAME = "source.json"


def write_source(
    path: Path,
    rows: list[str],
    clues: dict[str, dict[str, str]] | None = None,
    themes: dict[str, dict[str, str]] | None = None,
) -> Path:
    """Write a grid document holding `rows`, `clues` and `themes` at `path`; return it."""
    path.write_text(
        json.dumps({"rows": rows, "themes": themes or {}, "clues": clues or {}}),
        encoding="utf-8",
        newline="\n",
    )
    return path


def without_size(argv: list[str]) -> list[str]:
    """`argv` with its `--rows` and `--cols` pairs removed."""
    trimmed = list(argv)
    for flag in ("--rows", "--cols"):
        at = trimmed.index(flag)
        del trimmed[at : at + 2]
    return trimmed


def source_fill(space: cli_fixtures.Workspace, source: Path, *extra: str) -> list[str]:
    """`space.fill()` without its size, starting from `source`, plus `extra`."""
    return [*without_size(space.fill()), "--source", str(source), *extra]


def filled(rows: list[str]) -> dict[tuple[int, int], str]:
    """Every filled cell of `rows`, keyed by (row, column)."""
    return {
        (row, col): cell
        for row, line in enumerate(rows)
        for col, cell in enumerate(line)
        if cell != cw_grid.BLOCK
    }


class SourceCase(cli_fixtures.QuietCase):
    """A quiet case that runs `main` and hands back its exit code."""

    def run_main(self, argv: list[str]) -> int | None:
        """`main`'s exit code, or None when argparse refused the command line itself.

        argparse leaves through SystemExit. It is suppressed so that a command
        line argparse cannot parse fails a case on its assertions, rather than
        erroring out of the run with nothing said about why.
        """
        code: int | None = None
        with contextlib.suppress(SystemExit):
            code = decorative_crossword.main(argv)
        return code
