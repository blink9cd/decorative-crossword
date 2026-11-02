"""cw_gaps_command: the `gaps` handler, from parsed arguments to an exit code.

Its own module rather than a block in `cw_commands` beside `fill`, which
searches for a grid and writes it: `gaps` reads a `--source` grid, changes
nothing in it and reports on it. It reads a bank differently too: for its
answers alone, as a vocabulary merged with any `--words` list, where `fill`
reads its themes and clues as well.

The refusal contract, the `UsageError` type and the single call to the renderer
all come from `cw_command_base`, so this handler and those in `cw_commands` and
`cw_read_commands` refuse exactly the same set of faults in exactly the same words.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import cw_bank_merge
import cw_command_base
import cw_config
import cw_emit
import cw_gaps
import cw_gaps_report
import cw_gaps_summary
import cw_mask
import cw_pairs
import cw_paths
import cw_shade


def _config_from(
    args: argparse.Namespace, mask: cw_mask.Mask | None
) -> cw_config.GapsConfig:
    """Assemble the typed `gaps` configuration from a parsed command line.

    `--bank`, `--words`, `--phrases` and `--out` are absent by design: each is a
    question about presence rather than a value, and `cw_config.GapsConfig` says
    why. `mask` is the read `--mask` picture, or None; its cells are a value, so
    they do belong here.
    """
    return cw_config.GapsConfig(
        top=args.top,
        include_absorbing=bool(args.include_absorbing),
        cell=args.cell,
        masked=frozenset() if mask is None else mask.cells,
    )


def _require_mask_agrees(mask: cw_mask.Mask, rows: Sequence[str]) -> None:
    """Raise UsageError unless the picture describes the `--source` grid it was given.

    Two faults, in this order: a size the grid does not have, then a cell where
    the picture forbids a letter the grid already holds. Size first, because a
    cell of a mis-sized picture names nothing the operator can find in either
    file.

    The letter half is the same operator-authored contradiction
    `cw_config._validate_masked_source_letters` refuses under `fill`, and `gaps`
    owes it for a second reason of its own. `cw_gaps.analyze_grid` classifies
    only blocked cells, so a masked cell holding a letter is never counted as
    masked, leaving the report claiming a cell "may never hold a letter" beside
    a masked count that does not include it, two figures for one thing.

    `UsageError` rather than `cw_config.ConfigError`, and asked here rather than
    in `validate_gaps_config`: this is a flag naming something the given input
    does not contain, which is what that type is for, and it cannot be decided
    until the source file has been read. `fill` asks the same question in its
    config validation instead, because there the grid's size is part of the
    configuration.

    The width is the longest row, as every other measurement of a grid in this
    subcommand is.
    """
    cols = max((len(row) for row in rows), default=0)
    if (mask.rows, mask.cols) != (len(rows), cols):
        raise cw_command_base.UsageError(
            f"--mask draws a {mask.rows}x{mask.cols} picture but the --source grid "
            f"is {len(rows)}x{cols}: a mask describes the grid cell for cell, so "
            "the two must be the same size"
        )
    fault = cw_mask.forbidden_letter(rows, mask.cells)
    if fault is not None:
        raise cw_command_base.UsageError(fault)


def _bank_answers(args: argparse.Namespace) -> frozenset[str]:
    """The answers of every `--bank`, merged, or none when no bank was given.

    For membership only. Merged by `cw_bank_merge`, as `fill` merges them, so a
    set of banks one subcommand refuses the other refuses too, even though only
    the answers are read here.
    """
    if args.bank is None:
        return frozenset()
    merged = cw_bank_merge.load_banks(args.bank).bank
    return frozenset(entry.answer for entry in merged.entries)


def _vocabulary(
    args: argparse.Namespace, bank_answers: frozenset[str]
) -> tuple[frozenset[str], tuple[tuple[str, str], ...]]:
    """Every answer this run may draw on, and the list lines it could not use.

    Two sources that union rather than two modes that exclude each other, which
    is the opposite of `shade`'s `--words` / `--word` and is right for the
    opposite reason: those two ask for different products, while a bank and a
    filler list are two halves of one vocabulary, often kept in separate files.

    A `--words` file holding nothing usable is refused rather than absorbed.
    The alternative is a report whose headline says no vocabulary was supplied,
    to an operator who supplied one: a flag accepted and silently inert, and
    a sentence that is simply false.

    The answers are gathered in a set and handed back frozen for membership
    only; nothing iterates them, so their `PYTHONHASHSEED`-dependent order
    cannot reach the output, which is fixed across runs.
    """
    answers: set[str] = set(bank_answers)
    skipped: list[tuple[str, str]] = []
    for path in args.words or ():
        words, list_skipped = cw_shade.load_word_list(path)
        if not words:
            raise cw_command_base.UsageError(
                f"--words file {path} holds no usable words: every line was "
                "blank, a comment, or not a word a grid could hold"
            )
        answers.update(words)
        skipped.extend(list_skipped)
    return frozenset(answers), tuple(skipped)


def _pair_lines(
    args: argparse.Namespace,
    rows: Sequence[str],
    bank_answers: frozenset[str],
    phrases: cw_pairs.Phrases,
) -> list[str]:
    """The answer-pairs block, or nothing when this run offered nothing to join into.

    A join counts against the bank and `--phrases` only. `--words` is filler for
    a gap rather than a word two entries were meant to spell, so a run offering
    only that has nothing to join into, and "none join" there would describe a
    check that had no vocabulary to run against.
    """
    if args.bank is None and not args.phrases:
        return []
    return cw_pairs.pair_lines(rows, bank_answers, phrases)


def _refuse_unusable_output(args: argparse.Namespace) -> None:
    """Raise ConfigError if `--out` is no place to write, or names a file this run reads.

    Every file `gaps` reads is handed over: each `--bank` file and each
    `--words` and `--phrases` list, not only the first of each.
    """
    cw_paths.refuse_unusable_outputs(
        (("--out", args.out),),
        (
            ("--source", args.source),
            *(("--bank", path) for path in args.bank or ()),
            *(("--words", path) for path in args.words or ()),
            *(("--phrases", path) for path in args.phrases or ()),
            ("--mask", args.mask),
        ),
    )


def _run(args: argparse.Namespace) -> int:
    """Run `gaps` and return its exit code, or raise one of `cw_command_base.REFUSALS`.

    The validate half of `validate -> act -> record`, in the order a refusal is
    cheapest to reach: the `--mask` picture and the configuration's own values
    first, then whether `--out` can be written without touching an input, then
    whether a bank file is given twice, then the vocabulary and the phrase
    lists, then the grid, and last whether the picture agrees with it.

    The report is printed before the render is written, for the same reason
    `fill` writes its grid before its preview: the report
    is the product and the picture is an inspection aid, so a filesystem
    failure between them leaves the recoverable artifact.
    """
    mask = None if args.mask is None else cw_mask.load_mask(args.mask)
    config = _config_from(args, mask)
    cw_config.validate_gaps_config(config)
    _refuse_unusable_output(args)
    cw_paths.refuse_repeated_inputs("--bank", args.bank or ())
    bank_answers = _bank_answers(args)
    vocabulary, skipped = _vocabulary(args, bank_answers)
    phrases = cw_command_base.load_phrases(args.phrases)
    document = cw_command_base.load_source(args.tool, args.source)
    if mask is not None:
        _require_mask_agrees(mask, document.rows)
    search = cw_gaps.search_gaps(document.rows, vocabulary, config.masked)
    pairs = _pair_lines(args, document.rows, bank_answers, phrases)
    print(
        cw_gaps_report.render_report(
            document.rows,
            search,
            config,
            skipped,
            pairs,
            mask_file=None if args.mask is None else str(args.mask),
        ),
        file=sys.stdout,
    )
    if args.out is not None:
        cw_emit.write_atomically(
            args.out,
            cw_command_base.render(
                document,
                (),
                config.cell,
                None,
                None,
                gaps=cw_gaps_report.marked_cells(search, config),
                empty_blocks=bool(args.empty_blocks),
            ),
        )
    return 0 if cw_gaps_summary.listable(search, config) else 1


def run_gaps(args: argparse.Namespace) -> int:
    """Report what a letter in each blocked cell would cost the bank.

    0 this grid has a gap worth reporting, 1 the analysis ran and it has none,
    2 the run could not happen.
    """
    try:
        return _run(args)
    except cw_command_base.REFUSALS as exc:
        return cw_command_base.refuse(args.tool, exc)
