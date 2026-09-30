#!/usr/bin/env python3
"""decorative_crossword: fill a crossword grid from a word bank, offline.

One subcommand per verb. `fill` searches for a grid
and writes `grid_source.json`; `preview` draws an existing one as a
self-contained SVG; `shade` reads an existing one and reports which words it
can spell in shaded cells, and which cells to shade; `gaps` reads one and
reports what a letter in each of its blocked cells would demand of the bank.
The split follows what each verb does -- "search a grid", "draw a grid" and
"read a grid" -- and it is what makes the last three useful on grids this tool
never produced.

**Everything in this file is argument parsing.** Not one line decides what a
run does: `build_parser` builds the surface and `main` dispatches into the
handler modules under `src/`. Every option of every subcommand is declared
in this file, so the whole command-line surface reads in one place and a
documentation check can find each option without following imports. Helpers
*within* this file are fine, and the `_add_*_arguments` functions below are
where the option tables actually live.

What an option SAYS is a separate question from where it is declared, and the
answer is `cw_help`: help long enough to need a paragraph lives there, beside
the epilogs, so this file stays a table of option declarations. A one-line
help stays here at its own call, where a reader still meets the flag and its
description together. `tests/test_cli_help_prose.py` holds that line and pins
each constant to exactly one option.

No optional's default is written here. Every one reads from
`cw_config.DEFAULTS`, and `--help` renders it from the live `default=` through
the formatter, so the flag, the help text and the tool cannot disagree. The
exception is `None`, argparse's "not given", which the formatter leaves unstated.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import cast

# This project's modules live in src/, which is NOT what a script's sys.path[0]
# points at (that is this file's own directory). Inserted rather than making
# src/ a package, so this entry point and the test suites reach the modules by
# the same bare name.
#
# Unconditional, not guarded on "is it already there": the suites insert the
# same directory before importing this module, so a guard would be a branch
# whose taken side no run of this file can reach -- and a repeated sys.path
# entry costs nothing, since a module is imported once.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# The shared UTF-8 stdio policy library, at ONE fixed place: the stdio_utf8/ folder beside
# this file. Appended, not inserted, so it can shadow neither src/ nor the standard library.
# Not a search of the parent directories: with this folder missing, a search would reach
# past the clone and import whatever folder of that name it found above it; a fixed path
# fails at the import instead.
sys.path.append(str(Path(__file__).resolve().parent / "stdio_utf8"))

import cw_command_base
import cw_commands
import cw_config
import cw_gaps_command
import cw_grid
import cw_read_commands
import cw_help
import cw_symmetry
import cw_text
import stdio_utf8

#: How diagnostics name this tool on stderr. Taken from the file's own name so
#: a rename carries it, rather than from `sys.argv[0]`, which under a test
#: runner or a `python -m` invocation names something that is not this tool.
#: The usage synopsis still takes argparse's own argv[0]-derived `prog`, which
#: is the right answer for a command line.
_TOOL_NAME = Path(__file__).stem


def _finite_float(text: str) -> float:
    """`text` as a float, or an argparse refusal when it is not a finite number.

    `float` alone reads `nan`, `inf` and an overflowing `1e999`. A NaN passes
    every range check downstream while meaning nothing, since no comparison
    with it is true; an infinite density bound is refused there, but a NaN or
    `inf` `--time-budget` is a wall clock that never runs out. Refused here, as a
    type, so every float option shares the rule and argparse names the flag.
    Text that is no number at all gets the same sentence, rather than
    argparse's own, which would name this function.
    """
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(
            f"must be a finite number, got {cw_text.shown(text)}"
        )
    return value


def _add_fill_arguments(parser: argparse.ArgumentParser) -> None:
    """Register `fill`'s options."""
    parser.add_argument(
        "--bank",
        type=Path,
        action="append",
        required=True,
        default=None,
        help="Path to a word bank JSON file; repeat it to merge several, in order.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Path the candidate grid_source.json is written to.",
    )
    parser.add_argument(
        "--seed", type=int, required=True, help="Integer seed; fixes the search order."
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=None,
        help=(
            f"Grid height in cells, at most {cw_grid.MAX_SIDE}; required unless "
            "--source, which it may only grow, or --mask."
        ),
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=None,
        help=(
            f"Grid width in cells, at most {cw_grid.MAX_SIDE}; required unless "
            "--source, which it may only grow, or --mask."
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help=cw_help.FILL_SOURCE_HELP,
    )
    parser.add_argument(
        "--absorb-entries",
        action="store_true",
        help=cw_help.FILL_ABSORB_ENTRIES_HELP,
    )
    # Registered here and again under `gaps`, each with its OWN help, rather
    # than through one shared loop like `--empty-blocks`: that flag means the
    # same thing in every subcommand it reaches, and this one does not.
    parser.add_argument(
        "--mask",
        type=Path,
        default=None,
        help=cw_help.FILL_MASK_HELP,
    )
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help=cw_help.FILL_PREVIEW_HELP,
    )
    parser.add_argument(
        "--feature",
        action="append",
        default=None,
        metavar="ANSWER[@ROW,COL,DIR]",
        help=cw_help.FILL_FEATURE_HELP,
    )
    parser.add_argument(
        "--min-blocked",
        type=_finite_float,
        default=cw_config.DEFAULTS["min_blocked"],
        help="Lower bound of the blocked-cell percentage.",
    )
    parser.add_argument(
        "--max-blocked",
        type=_finite_float,
        default=cw_config.DEFAULTS["max_blocked"],
        help="Upper bound of the blocked-cell percentage.",
    )
    parser.add_argument(
        "--min-themes",
        type=int,
        default=cw_config.DEFAULTS["min_themes"],
        help="Themes that must each meet the per-theme floor; 0 asks for none.",
    )
    parser.add_argument(
        "--min-entries-per-theme",
        type=int,
        default=cw_config.DEFAULTS["min_entries_per_theme"],
        help="Placed entries a theme needs before it counts.",
    )
    parser.add_argument(
        "--time-budget",
        type=_finite_float,
        default=cw_config.DEFAULTS["time_budget"],
        help=cw_help.FILL_TIME_BUDGET_HELP,
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=cw_config.DEFAULTS["max_steps"],
        help="Deterministic node cap; 0 means unlimited.",
    )
    parser.add_argument(
        "--max-two-letter",
        type=int,
        default=None,
        metavar="N",
        help="Most two-letter entries a grid may carry; 0 allows none. No cap unless given.",
    )
    parser.add_argument(
        "--excluded-terms",
        type=Path,
        default=None,
        help=cw_help.FILL_EXCLUDED_TERMS_HELP,
    )
    parser.add_argument(
        "--look-ahead",
        type=int,
        default=cw_config.DEFAULTS["look_ahead"],
        help=cw_help.FILL_LOOK_AHEAD_HELP,
    )
    parser.add_argument(
        "--prefer",
        action="append",
        default=None,
        metavar="ANSWER",
        help="Answer that makes a grid better when present; repeat for several.",
    )
    parser.add_argument(
        "--prefer-symmetry",
        choices=tuple(cw_symmetry.KINDS),
        default=None,
        help=cw_help.FILL_PREFER_SYMMETRY_HELP,
    )
    parser.add_argument(
        "--island-letters",
        default=None,
        metavar="LETTERS",
        help=cw_help.FILL_ISLAND_LETTERS_HELP,
    )
    parser.add_argument(
        "--phrases",
        type=Path,
        action="append",
        default=None,
        help=cw_help.FILL_PHRASES_HELP,
    )


def _add_preview_arguments(parser: argparse.ArgumentParser) -> None:
    """Register `preview`'s options."""
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to an existing grid_source.json.",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Path the SVG is written to."
    )
    parser.add_argument(
        "--feature",
        action="append",
        default=None,
        metavar="ANSWER",
        help=cw_help.PREVIEW_FEATURE_HELP,
    )
    parser.add_argument(
        "--cell",
        type=int,
        default=cw_config.DEFAULTS["cell"],
        help=f"Cell edge in SVG user units, at most {cw_config.MAX_CELL}.",
    )


def _add_shade_arguments(parser: argparse.ArgumentParser) -> None:
    """Register `shade`'s options.

    `--words` and `--word` are two plain optionals rather than a mutually
    exclusive group: the "exactly one of them" rule is enforced in
    `cw_read_commands`, where the message can say which two flags disagree and why,
    in the vocabulary the rest of this tool's refusals use. argparse's own
    group message is terser and would be the one thing on stderr not written
    like the others.
    """
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to an existing grid_source.json.",
    )
    parser.add_argument(
        "--words",
        type=Path,
        default=None,
        help="Path to a candidate word list, one word per line; ranks them.",
    )
    parser.add_argument(
        "--word",
        default=None,
        help="A single word to place; emits its cells instead of a ranking.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Path for a render shading --word's cells; --word mode only.",
    )
    parser.add_argument(
        "--exclude-grid-answers",
        action="store_true",
        help="Drop words this grid already answers; they are repeats, not bonuses.",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=cw_config.DEFAULTS["min_length"],
        help="Shortest word the ranked search will consider.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=cw_config.DEFAULTS["top"],
        help="Ranked candidates to print; 0 prints every one.",
    )
    parser.add_argument(
        "--cell",
        type=int,
        default=cw_config.DEFAULTS["cell"],
        help=f"Cell edge in SVG user units, for --out; at most {cw_config.MAX_CELL}.",
    )


def _add_gaps_arguments(parser: argparse.ArgumentParser) -> None:
    """Register `gaps`' options.

    `--bank` and `--words` are two plain optionals that UNION rather than a
    mutually exclusive group, which is the opposite of `shade`'s mode flags and
    right for the opposite reason: those select which PRODUCT the run makes,
    while these are two halves of one vocabulary that are naturally kept in
    separate files -- a curated bank, and filler lists.
    """
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to an existing grid_source.json.",
    )
    parser.add_argument(
        "--bank",
        type=Path,
        action="append",
        default=None,
        help="A word bank JSON whose answers this run may draw on; repeatable.",
    )
    parser.add_argument(
        "--words",
        type=Path,
        action="append",
        default=None,
        help="A plain word list this run may draw on; repeatable.",
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=None,
        help=cw_help.GAPS_MASK_HELP,
    )
    parser.add_argument(
        "--phrases",
        type=Path,
        action="append",
        default=None,
        help=cw_help.GAPS_PHRASES_HELP,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Path for a render marking the gaps this run lists.",
    )
    parser.add_argument(
        "--include-absorbing",
        action="store_true",
        help="List the gaps whose fill would retire an existing answer.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=cw_config.DEFAULTS["top"],
        help="Ranked gaps to list; 0 lists every one.",
    )
    parser.add_argument(
        "--cell",
        type=int,
        default=cw_config.DEFAULTS["cell"],
        help=f"Cell edge in SVG user units, for --out; at most {cw_config.MAX_CELL}.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the root parser and every subcommand.

    Returned rather than parsed here so a test can inspect the surface without
    driving a run, and so `main` stays a dispatch.
    """
    # Its error line is escaped as a refusal is; every subcommand's parser is
    # built of the same class.
    parser = cw_command_base.ArgumentParser(
        description=(
            "Fill a crossword grid from a word bank, draw one that already "
            "exists, read one back for the words it can spell in shaded "
            "cells, or ask what a letter in each of its blocked cells would "
            "demand of the bank. Offline, and deterministic with --time-budget 0 "
            "and a --max-steps cap: the same bank and seed then produce the same "
            "bytes."
        ),
        formatter_class=cw_help.HelpFormatter,
    )
    parser.set_defaults(command=None, tool=_TOOL_NAME)
    subparsers = parser.add_subparsers(dest="command", metavar="SUBCOMMAND")

    fill_parser = subparsers.add_parser(
        "fill",
        help="Search for a grid and write it, and its SVG with --preview",
        formatter_class=cw_help.HelpFormatter,
        epilog=cw_help.FILL_EPILOG,
    )
    _add_fill_arguments(fill_parser)
    fill_parser.set_defaults(func=cw_commands.run_fill, tool=_TOOL_NAME)

    preview_parser = subparsers.add_parser(
        "preview",
        help="Draw an existing grid_source.json as a self-contained SVG",
        formatter_class=cw_help.HelpFormatter,
        epilog=cw_help.PREVIEW_EPILOG,
    )
    _add_preview_arguments(preview_parser)
    preview_parser.set_defaults(func=cw_read_commands.run_preview, tool=_TOOL_NAME)

    shade_parser = subparsers.add_parser(
        "shade",
        help="Find the words a grid can spell in shaded cells, and where to shade",
        formatter_class=cw_help.HelpFormatter,
        epilog=cw_help.SHADE_EPILOG,
    )
    _add_shade_arguments(shade_parser)
    shade_parser.set_defaults(func=cw_read_commands.run_shade, tool=_TOOL_NAME)

    gaps_parser = subparsers.add_parser(
        "gaps",
        help="Report what a letter in each blocked cell would demand of the bank",
        formatter_class=cw_help.HelpFormatter,
        epilog=cw_help.GAPS_EPILOG,
    )
    _add_gaps_arguments(gaps_parser)
    gaps_parser.set_defaults(func=cw_gaps_command.run_gaps, tool=_TOOL_NAME)

    # One loop, not four blocks: every subcommand that can write an SVG takes
    # this one and it means the same thing in each. The name stays a LITERAL at
    # the call, so a reader, or a check scanning this file's `add_argument`
    # calls, finds it; a helper taking the name as a parameter would hide it.
    for renderer in (fill_parser, preview_parser, shade_parser, gaps_parser):
        renderer.add_argument(
            "--empty-blocks",
            action="store_true",
            help=cw_help.EMPTY_BLOCKS_HELP,
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns the process exit code."""
    # First statement, before anything is printed (stdio_utf8.md): theme labels
    # and clues carry accented text, and a Windows console defaulting to a
    # legacy code page would fail on exactly the content this tool emits.
    stdio_utf8.force_utf8_streams(sys.stdout, sys.stderr)
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    return cast(int, args.func(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
