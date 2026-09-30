"""cw_read_commands: what `preview` and `shade` do with a parsed command line.

Kept apart from `cw_commands` along the seam the subcommands already draw:
`fill` searches for a grid and writes one, while these two READ a `--source`
grid this tool may never have produced and change nothing in it -- the kinship
they share with `gaps`, the third reader, rather than with `fill`.

Every `add_argument` call stays in `decorative_crossword.py`, for the reason
`cw_commands` gives, and the refusal contract is `cw_command_base.REFUSALS`,
shared with every other handler module.
"""

from __future__ import annotations

import argparse
import sys

import cw_answer
import cw_command_base
import cw_config
import cw_emit
import cw_feature
import cw_grid
import cw_grid_document
import cw_paths
import cw_shade
import cw_shade_report
import cw_svg
import cw_text


def _require_no_position(features: tuple[str, ...]) -> None:
    """Raise UsageError if any `--feature` value carries a position.

    `preview` locates an answer in a grid it did not build, and the render
    shades an answer by its text, so `@ROW,COL,DIR` could change nothing drawn.
    Refused rather than read as an assertion that the answer sits there: a
    refusal can be loosened later without breaking a command line, and an
    accepted position cannot be withdrawn.

    A value carrying the mark is refused whole, before its position is parsed,
    so a malformed one is never told what a well-formed pin looks like -- as
    though pins were welcome here.
    """
    for feature in features:
        if cw_feature.ANCHOR_MARK in feature:
            raise cw_command_base.UsageError(
                f"--feature {cw_text.shown(feature)}: preview finds an answer in "
                "the grid it is given and takes no position; give the answer alone"
            )


def _features_in_grid(
    rows: tuple[str, ...], features: tuple[str, ...]
) -> tuple[str, ...]:
    """The features to shade, once the grid holds every one of them.

    Raises UsageError naming every absent answer, in the order given, in one
    refusal: told only the first, an operator fixes it and is refused again.

    `preview --feature` locates answers in the grid it was handed rather than
    constraining a search, so an answer that is not there is the same kind of
    mistake as one that is not in the bank: a flag naming something that does
    not exist, exit 2.
    """
    absent = [
        feature for feature in features if cw_grid.find_answer(rows, feature) is None
    ]
    if absent:
        raise cw_command_base.UsageError(
            "; ".join(
                f"the featured answer {cw_text.shown(feature)} is not in this grid"
                for feature in absent
            )
        )
    return features


def _preview(args: argparse.Namespace) -> int:
    """Run `preview` and return its exit code, or raise one of `cw_command_base.REFUSALS`.

    There is no exit 1 here: `preview` has no constraint to miss. It renders a
    grid whose CONTENT is questionable -- an entry with no
    clue, a theme used but not declared -- without complaint, because those are
    for whatever consumes the grid to judge, not this tool. A stray lone letter
    draws a warning from `cw_command_base.load_source` and is drawn all the same.

    `--cell` and the SHAPE of each `--feature` -- a position, a repeat -- are
    checked BEFORE the source is read, because they are the faults here that
    need no file to diagnose, and reading first would spend the read to reach
    the same refusal. So is `--out`, which may be neither a directory nor the
    source itself. Whether the grid holds each answer needs the grid.
    """
    cw_config.validate_cell(args.cell)
    _require_no_position(tuple(args.feature or ()))
    features = tuple(cw_answer.grid_form(feature) for feature in args.feature or ())
    cw_feature.validate_distinct(features)
    cw_paths.refuse_unusable_outputs(
        (("--out", args.out),), (("--source", args.source),)
    )
    document = cw_command_base.load_source(args.tool, args.source)
    shaded = _features_in_grid(document.rows, features)
    cw_emit.write_atomically(
        args.out,
        cw_command_base.render(
            document,
            shaded,
            args.cell,
            None,
            None,
            empty_blocks=args.empty_blocks,
        ),
    )
    return 0


def _shade_config_from(args: argparse.Namespace) -> cw_config.ShadeConfig:
    """Assemble the typed `shade` configuration from a parsed command line.

    The one transformation it makes is UPPERCASING `--word`. The word list is
    case-folded on the way in, so a word copied out of a lower-case list into
    `--word` has to reach the same answer as the same word in that list --
    without the fold it would be refused as "not letters A-Z", which is a true
    sentence about the wrong thing.
    """
    return cw_config.ShadeConfig(
        min_length=args.min_length,
        top=args.top,
        exclude_grid_answers=args.exclude_grid_answers,
        word=None if args.word is None else args.word.upper(),
        cell=args.cell,
    )


def _require_one_shade_mode(args: argparse.Namespace) -> None:
    """Raise UsageError unless exactly one mode flag, and a usable `--out`, is set.

    `--words` and `--word` are two MODES rather than two settings, so neither
    a default nor a precedence rule between them would be honest: only the
    operator knows which they meant. `--out` asks for a picture of one word,
    so it is refused in the ranked mode rather than accepted and ignored --
    silently-inert flags are how a command line comes to mean something other
    than what it says.
    """
    if (args.words is None) == (args.word is None):
        raise cw_command_base.UsageError(
            "give exactly one of --words (rank a list) or --word (place one "
            "word); they select the two modes and neither can stand in for "
            "the other"
        )
    if args.out is not None and args.word is None:
        raise cw_command_base.UsageError(
            "--out draws one word's shaded cells and needs --word; the ranked "
            "search has no single word to draw"
        )


def _require_placeable_word(
    rows: tuple[str, ...], config: cw_config.ShadeConfig
) -> cw_shade.Placement:
    """The placement for `--word`, or the UsageError saying why there is none.

    The exclusion is checked FIRST and gets its own message, mirroring
    `cw_commands`' `_require_reachable_features`: "these two flags ask for
    opposite things" is a different thing to tell the operator than "this grid
    cannot spell that", and only they can say which they meant.
    """
    # mypy: this handler is only reached with a word, because
    # `_require_one_shade_mode` has already refused the other mode.
    assert config.word is not None
    if config.exclude_grid_answers and config.word in cw_shade.grid_answers(rows):
        raise cw_command_base.UsageError(
            f"--exclude-grid-answers removes {cw_text.shown(config.word)}, which "
            "this grid already answers: it and --word ask for opposite things, "
            "and only you can say which was meant"
        )
    placement = cw_shade.place_word(rows, config.word)
    if placement is None:
        raise cw_command_base.UsageError(
            f"this grid cannot spell {cw_text.shown(config.word)} in reading order: its "
            "letters do not all appear, or do not appear in that order"
        )
    return placement


def _shade_one_word(
    args: argparse.Namespace,
    document: cw_grid_document.GridDocument,
    config: cw_config.ShadeConfig,
) -> int:
    """Place `--word`, draw it where asked, and report it. Always exit 0 or raise.

    There is no exit 1 here: a word that cannot be placed is a flag naming
    something the given grid does not contain, which belongs on the exit-2
    line -- the same reading `preview --feature` already gets.

    The render is built before anything is written, so a refusal from it leaves
    no file behind: exit 2 writes none.
    """
    placement = _require_placeable_word(document.rows, config)
    if args.out is not None:
        cw_emit.write_atomically(
            args.out,
            cw_command_base.render(
                document,
                (),
                config.cell,
                None,
                cw_svg.HiddenShading(placement.word, placement.cells),
                empty_blocks=args.empty_blocks,
            ),
        )
    print(cw_shade_report.render_placement_report(placement), file=sys.stdout)
    return 0


def _shade_search(
    args: argparse.Namespace,
    document: cw_grid_document.GridDocument,
    config: cw_config.ShadeConfig,
) -> int:
    """Rank `--words` against the grid and report: 0 with candidates, 1 without.

    A list that yields no usable word at all is exit 2 rather than exit 1, and
    the difference is the whole point of having both: exit 1 says the search
    ran and this grid spells none of these words, while a list holding nothing
    to search with means no search happened. Reporting the second as the first
    would tell the operator something false about their grid.
    """
    words, skipped = cw_shade.load_word_list(args.words)
    if not words:
        raise cw_command_base.UsageError(
            f"--words file {args.words} holds no usable words: every line was "
            "blank, a comment, or not a word this grid could hold"
        )
    result = cw_shade.search_hidden_words(
        document.rows,
        words,
        min_length=config.min_length,
        exclude_grid_answers=config.exclude_grid_answers,
    )
    print(
        cw_shade_report.render_search_report(document.rows, result, config, skipped),
        file=sys.stdout,
    )
    return 0 if result.candidates else 1


def _shade(args: argparse.Namespace) -> int:
    """Run `shade` and return its exit code, or raise one of `cw_command_base.REFUSALS`.

    The validate half of `validate -> act -> record`, in the order a refusal is
    cheapest to reach: the mode flags first (no file is needed to decide them),
    then the configuration's values, then whether `--out` can be written
    without touching the grid, then the grid, then whichever mode's own input.
    `--words` is not handed to the output check: `--out` is refused in the
    mode that reads it, so the two never meet.
    """
    _require_one_shade_mode(args)
    config = _shade_config_from(args)
    cw_config.validate_shade_config(config)
    cw_paths.refuse_unusable_outputs(
        (("--out", args.out),), (("--source", args.source),)
    )
    document = cw_command_base.load_source(args.tool, args.source)
    if config.word is not None:
        return _shade_one_word(args, document, config)
    return _shade_search(args, document, config)


def run_preview(args: argparse.Namespace) -> int:
    """Render an existing grid: 0 on a render, 2 on any refusal."""
    try:
        return _preview(args)
    except cw_command_base.REFUSALS as exc:
        return cw_command_base.refuse(args.tool, exc)


def run_shade(args: argparse.Namespace) -> int:
    """Find or place a hidden word: 0 found, 1 searched and found none, 2 refused."""
    try:
        return _shade(args)
    except cw_command_base.REFUSALS as exc:
        return cw_command_base.refuse(args.tool, exc)
