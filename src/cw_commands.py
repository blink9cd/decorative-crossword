"""cw_commands: what a parsed `fill` command line actually does.

The subcommands that read a grid rather than search for one live beside it:
`preview` and `shade` in `cw_read_commands`, `gaps` in `cw_gaps_command`.

Separate from the entry point from the first line of it, and not for size:
every `add_argument` call stays in `decorative_crossword.py`, so the whole
command-line surface reads in one place and a documentation check can find
each option without following imports. Parsing lives there; everything a
parsed namespace then causes lives here.

**The exit-code policy is stated once, as `cw_command_base.REFUSALS`, rather
than decided per call site**. Exit 2 is *the run could not happen*: a schema
violation, an unreadable or unwritable path, a contradictory configuration.
Exit 1 is *the run happened and did not succeed*, including the case where it
could never have succeeded: an unsatisfiable request comes back from
`cw_search.search` as a non-conforming outcome with `steps == 0`, and is
reported like any other near miss.

The one refusal that has to be picked out of the pre-flight reasons by hand is
a featured answer the bank does not hold, which belongs on the exit-2 line
because it is a flag naming something that does not exist. It is decided
by calling `cw_accept.feature_missing_from_bank` (the same function
`preflight` calls) rather than by matching on reason text, so the two cannot
decide differently about the same bank.

`fill --source` reads its grid through `cw_command_base.load_source`, the
reader `preview`, `shade` and `gaps` use, so a stray letter is warned about in
the same words; whether the grid can be started from is `cw_source`'s question.

`fill --preview` reaches the renderer through `cw_command_base.render` and one
`cw_grid_document.GridDocument`, exactly as `preview` does, so it and a standalone
`preview` of the file it just wrote differ only by what a bare `preview` has
no honest way to know: the caption tier, and the `--source` letters drawn
bold. Neither holds drawing logic.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from typing import cast

import cw_accept
import cw_answer
import cw_bank
import cw_bank_merge
import cw_board
import cw_command_base
import cw_config
import cw_density
import cw_emit
import cw_excluded_terms
import cw_feature
import cw_grid
import cw_grid_document
import cw_island
import cw_mask
import cw_pairs
import cw_paths
import cw_report
import cw_search
import cw_source
import cw_text


#: `fill` renders its preview at the default cell size: `--cell` is an
#: option of the other subcommands, never `fill`'s, because the render
#: inside a fill has no separate size to choose.
_FILL_CELL = cast(int, cw_config.DEFAULTS["cell"])


@dataclass(frozen=True)
class _FillInputs:
    """Everything a `fill` run needs, once it is known the run can happen.

    `dropped` travels with the bank because the bank is the screened one: the
    report has to name the removals separately or its headline count silently
    contradicts the operator's own input file.

    `kept` is the entries `--source` kept outside the bank, empty without a
    source. `bank` already holds them at its end, so the search can place
    around them; they travel apart for the reason `dropped` does, since the
    report's `--bank` blocks must count the operator's file without them.

    `files` is each `--bank` file, in the order merged, with the entries it
    holds; only the report reads it.

    `mask_file` is the `--mask` picture's path as the operator wrote it, None
    without the flag; only the report reads it too. The picture's cells travel
    on the config, where every decider reads them. This carries the file's
    name, which a config has no field for and no decider needs.
    """

    bank: cw_bank.Bank
    config: cw_config.FillConfig
    dropped: tuple[tuple[str, str], ...]
    phrases: cw_pairs.Phrases
    kept: tuple[str, ...]
    files: tuple[tuple[str, int], ...]
    mask_file: str | None = None


def _config_from(
    args: argparse.Namespace, start: tuple[str, ...], mask: cw_mask.Mask | None
) -> cw_config.FillConfig:
    """Assemble the typed run configuration from a parsed `fill` command line.

    A straight field-for-flag transcription with no defaulting of its own:
    every default was applied by the parser, from `cw_config.DEFAULTS`, so a
    second opinion here is the one way `--help` could come to disagree with
    what the tool does. An on/off flag is read through `bool()`: the parser
    leaves it None when absent, so that `--help` prints no default for it.

    Two fields are parsed rather than copied, each raising ConfigError (exit
    2) on a malformed value: every `--feature`, which `cw_feature.parse_feature`
    turns into the typed pin, and `--island-letters`, which
    `cw_island.parse_island_letters` holds to the letters an island may carry.
    Parsing, not defaulting: an absent flag is still no features and no islands.

    `start` is the `--source` rows, empty without a source. The size is the one
    thing not copied from its flags: `cw_source.resolve_size` grows the source
    by them when there is one, and otherwise requires both, raising ConfigError
    whichever way they are misused. The config's `start` is the source already
    placed on that canvas (`cw_source.place_source`), and `source_size` keeps
    the source's own size, which the placed rows can no longer tell.

    `mask` is the read `--mask` picture, or None. It reaches the size only
    through `cw_mask.requested_size`, which stands it in for a flag that was not
    given and then leaves `resolve_size` to settle the size, so a mask never
    changes what a `--rows` the operator did write means.
    Whether the picture matches the size that came out is
    `cw_config.validate_fill_config`'s question, asked next.
    """
    own = (len(start), len(start[0])) if start else cw_mask.NO_MASK_SIZE
    wanted_rows, wanted_cols = cw_mask.requested_size(args.rows, args.cols, own, mask)
    rows, cols = cw_source.resolve_size(wanted_rows, wanted_cols, start)
    return cw_config.FillConfig(
        rows=rows,
        cols=cols,
        seed=args.seed,
        min_blocked=args.min_blocked,
        max_blocked=args.max_blocked,
        min_themes=args.min_themes,
        min_entries_per_theme=args.min_entries_per_theme,
        time_budget=args.time_budget,
        max_steps=args.max_steps,
        features=tuple(cw_feature.parse_feature(text) for text in args.feature or ()),
        look_ahead=args.look_ahead,
        prefer=tuple(cw_answer.grid_form(answer) for answer in args.prefer or ()),
        island_letters=(
            ()
            if args.island_letters is None
            else cw_island.parse_island_letters(args.island_letters)
        ),
        start=cw_source.place_source(start, rows, cols),
        source_size=own,
        absorb_entries=bool(args.absorb_entries),
        max_two_letter=args.max_two_letter,
        prefer_symmetry=args.prefer_symmetry,
        masked=frozenset() if mask is None else mask.cells,
        mask_size=cw_mask.NO_MASK_SIZE if mask is None else (mask.rows, mask.cols),
    )


def _screen_bank(
    args: argparse.Namespace, bank: cw_bank.Bank
) -> tuple[cw_bank.Bank, tuple[tuple[str, str], ...], frozenset[str] | None]:
    """Apply `--excluded-terms` if it was given; otherwise pass the bank through.

    The terms come back as well, None without the flag: a `--source` screens
    the entries it keeps against the same list, which is read here once.
    """
    if args.excluded_terms is None:
        return bank, (), None
    terms = cw_excluded_terms.load_excluded_terms(args.excluded_terms)
    screened, dropped = cw_excluded_terms.screen_excluded(bank, terms)
    return screened, dropped, terms


def _refuse_unusable_outputs(args: argparse.Namespace) -> None:
    """Raise ConfigError if `--out` or `--preview` is no place to write, or names a file this run reads.

    Every file `fill` reads is handed over (each `--bank` file and each
    `--phrases` list, not only the first of each) and the check runs before
    the first of them is read, so a run pointed back at its own input is
    refused as that, whatever the file holds.
    """
    cw_paths.refuse_unusable_outputs(
        (("--out", args.out), ("--preview", args.preview)),
        (
            *(("--bank", path) for path in args.bank),
            ("--source", args.source),
            ("--excluded-terms", args.excluded_terms),
            *(("--phrases", path) for path in args.phrases or ()),
            ("--mask", args.mask),
        ),
    )


def _read_source(args: argparse.Namespace) -> cw_grid_document.GridDocument | None:
    """The `--source` grid, warning about each stray letter; None without one."""
    if args.source is None:
        return None
    return cw_command_base.load_source(args.tool, args.source)


def _start_source(
    document: cw_grid_document.GridDocument | None,
    bank: cw_bank.Bank,
    dropped: tuple[tuple[str, str], ...],
    terms: frozenset[str] | None,
) -> cw_source.StartSource:
    """What the search starts from: the checked source, or no source over `bank`.

    Without a source this is an empty start that keeps nothing and searches
    the screened bank as it stands, so the caller reads one shape either way.
    With one, `cw_source.start_from` raises SourceError for a grid no fill can
    start from.
    """
    if document is None:
        return cw_source.StartSource(kept=(), bank=bank)
    return cw_source.start_from(document, bank, dropped, terms)


def _require_reachable_features(
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
    dropped: tuple[tuple[str, str], ...],
) -> None:
    """Raise UsageError if any `--feature` names an answer the search cannot use.

    The screen is checked first, and gets its own message, because "the two
    flags contradict each other" is a different thing to tell the operator
    than "that answer is not in your bank", and only they can say which of
    the two they meant. Features are checked in the order given, so the one
    named is the first the operator wrote.

    Membership only: the dropped answers are collected into a set that is
    never iterated, so no hash-seeded order can reach the message.
    """
    removed = {answer for answer, _ in dropped}
    for feature in config.features:
        if feature.answer in removed:
            raise cw_command_base.UsageError(
                "--excluded-terms drops the featured answer "
                f"{cw_text.shown(feature.answer)}: --feature and the screen ask "
                "for opposite things, and only you can say which was meant"
            )
    reason = cw_accept.feature_missing_from_bank(bank, config)
    if reason is not None:
        raise cw_command_base.UsageError(reason)


def _require_reachable_preferences(
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
    dropped: tuple[tuple[str, str], ...],
) -> None:
    """Raise UsageError if any `--prefer` names an answer no grid could hold.

    The two refusals `--feature` gets, in the same order and for the same
    reason. A preference the bank lacks can never be placed, so a run that
    ignored it silently would be answering a question the operator did not ask.

    Membership only: both sets are never iterated.
    """
    removed = {answer for answer, _ in dropped}
    held = {entry.answer for entry in bank.entries}
    for answer in config.prefer:
        if answer in removed:
            raise cw_command_base.UsageError(
                "--excluded-terms drops the preferred answer "
                f"{cw_text.shown(answer)}: --prefer and the screen ask for "
                "opposite things, and only you can say which was meant"
            )
        if answer not in held:
            raise cw_command_base.UsageError(
                f"the preferred answer {cw_text.shown(answer)} is not in the bank"
            )


def _prepare_fill(args: argparse.Namespace) -> _FillInputs:
    """Everything that must hold before a single search node is expanded.

    The validate half of `validate -> act -> record`, in refusal order: an
    output flag that is no place to write or names a file the run reads, then
    a bank file given twice, then an unreadable bank or two banks that
    disagree (`cw_bank_merge`), then an unreadable source, then a `--mask` file
    that is not a picture, then a contradictory
    configuration (the size among it, the picture's agreement with it included),
    then the screen, then a source the
    screened bank cannot start from, then a pin lengthening a source run it
    may not (which needs that source's partial runs), then a feature or
    preferred answer neither the bank nor the source can supply, then a phrase
    list. Each step raises, so a caller sees one refusal rather than a partial
    result.
    """
    _refuse_unusable_outputs(args)
    cw_paths.refuse_repeated_inputs("--bank", args.bank)
    banks = cw_bank_merge.load_banks(args.bank)
    bank = banks.bank
    document = _read_source(args)
    mask = None if args.mask is None else cw_mask.load_mask(args.mask)
    config = _config_from(args, () if document is None else document.rows, mask)
    cw_config.validate_fill_config(config)
    cw_feature.validate_features(config)
    screened, dropped, terms = _screen_bank(args, bank)
    # Judged as placed on the grid, not at its own size: a partial run at the
    # source's edge may be completable into cells only a grown grid has.
    placed = None if document is None else replace(document, rows=config.start)
    start = _start_source(placed, screened, dropped, terms)
    allowed = frozenset(entry.answer for entry in start.bank.entries)
    growable = cw_board.growable_runs(config, allowed, frozenset(start.kept))
    cw_feature.validate_source_runs(config, start.partial, growable)
    _require_reachable_features(start.bank, config, dropped)
    _require_reachable_preferences(start.bank, config, dropped)
    phrases = cw_command_base.load_phrases(args.phrases, args.excluded_terms)
    return _FillInputs(
        bank=start.bank,
        config=config,
        dropped=dropped,
        phrases=phrases,
        kept=start.kept,
        files=banks.files,
        # Named as the operator wrote it, the way `cw_bank_merge` names a bank
        # file, so the report and any refusal call the same file the same thing.
        mask_file=None if args.mask is None else str(args.mask),
    )


def _caption_settings(config: cw_config.FillConfig) -> dict[str, str]:
    """The caption tier only a `fill` knows.

    The seed, the requested density range and the theme floor live nowhere in
    `grid_source.json`, so a bare `preview` cannot know them and stamps none of
    them. Rendered as strings here rather than inside `cw_svg`, which is not
    given a `FillConfig` and therefore cannot invent one.
    """
    # Every value here is a verbatim echo of what was asked for, including a
    # `--min-themes` of zero, which reads "0 theme(s) x N entry(s)". Rendering
    # a word like "none" there instead would make one line of the caption an
    # interpretation while the two above it stay literal, and would drop the
    # per-theme number from the picture entirely, and the caption exists so a
    # reader can recover the settings, not so it can summarize them.
    return {
        "seed": str(config.seed),
        "requested blocked": (f"{config.min_blocked:.1f}-{config.max_blocked:.1f}%"),
        "theme floor": (
            f"{config.min_themes} theme(s) x {config.min_entries_per_theme} entry(s)"
        ),
    }


def _source_letters(start: tuple[str, ...]) -> tuple[tuple[int, int], ...]:
    """Every cell `--source` gave a letter: the letters `fill --preview` draws bold.

    Read off the source's own rows rather than the grid that came back, for the
    reason `cw_source.source_lines` counts from them: the mark says what the
    operator handed in. A fill keeps every source letter where it was, so each
    is still in the grid being drawn. Empty without a source, so a fill from an
    empty board draws nothing bold.
    """
    return tuple(
        (row_index, col_index)
        for row_index, row in enumerate(start)
        for col_index, char in enumerate(row)
        if char != cw_grid.BLOCK
    )


def _with_islands(
    outcome: cw_search.SearchOutcome, config: cw_config.FillConfig
) -> tuple[
    cw_search.SearchOutcome, tuple[cw_island.Island, ...], tuple[cw_island.Island, ...]
]:
    """The outcome to write, the islands laid on it, and the islands the floor declined.

    Only on a conforming grid: islands decorate a grid the search chose, and on
    a best-effort miss they would move the very density figures the report's
    remedies are computed from.

    Each island takes a blocked cell, so the grid can give up only the blocks it
    holds past `--min-blocked` (`cw_density.fewest_blocked`, the floor acceptance
    judges by). Islands past that are declined and the rest laid, so the grid
    written still conforms and exit 0 still means it does. The declined ones are
    what laying without the limit adds after the laid ones, since the two walks
    agree up to the limit; the report names them.

    Every lone letter of the chosen grid is fixed, so it never qualifies a
    corner and islands cannot chain off it. The search places only whole runs,
    so each such letter is a `--source` letter the fill did not cross. The
    cells are read off the chosen grid, never off the source: a source letter
    the fill did cross is covered by an entry now, and qualifies a corner like
    any other letter. Without a source nothing in the grid is lone, so nothing
    is fixed.
    """
    if not config.island_letters or not outcome.conforming:
        return outcome, (), ()
    fixed = frozenset(cw_island.lone_cells(outcome.rows))
    total, blocked = cw_grid.usable_cells(outcome.rows, config.masked)
    spare = blocked - cw_density.fewest_blocked(total, config.min_blocked)
    rows, islands = cw_island.fill_islands(
        outcome.rows,
        config.island_letters,
        fixed=fixed,
        masked=config.masked,
        spare=spare,
    )
    _, every = cw_island.fill_islands(
        outcome.rows, config.island_letters, fixed=fixed, masked=config.masked
    )
    return replace(outcome, rows=rows), islands, every[len(islands) :]


def _fill(args: argparse.Namespace) -> int:
    """Run `fill` and return its exit code, or raise one of `cw_command_base.REFUSALS`."""
    prepared = _prepare_fill(args)
    outcome = cw_search.search(prepared.bank, prepared.config, kept=prepared.kept)
    written, islands, declined = _with_islands(outcome, prepared.config)
    document = cw_emit.build_document(written, prepared.bank, prepared.config)
    # Rendered before anything is written, so that a refusal from the build or
    # the render leaves no grid on disk, since exit 2 writes no file. Neither
    # is expected to refuse on this path: the parse
    # boundary already screened the clues and the grid comes from a `Grid`, so
    # nothing a real bank holds reaches either failure, which is exactly why
    # the ordering needs stating: it is insurance whose absence would show up
    # only once something else changed.
    preview = (
        None
        if args.preview is None
        else cw_command_base.render(
            cw_grid_document.parse_document(document),
            tuple(feature.answer for feature in prepared.config.features),
            _FILL_CELL,
            _caption_settings(prepared.config),
            None,
            fixed=_source_letters(prepared.config.start),
            empty_blocks=bool(args.empty_blocks),
        )
    )
    # The grid is written before the preview: if the second write fails, what is
    # left behind is the grid, which `preview` can draw again, rather than a
    # picture nothing can turn back into a grid.
    #
    # Neither write is read back. Both go through `os.replace`, which either
    # renames or raises, so the outcome is already observed at the call:
    # a re-read would report what the next reader sees, not whether this write
    # landed, and the two can only differ if something else is writing the
    # same path.
    cw_emit.write_document(args.out, document)
    if preview is not None:
        cw_emit.write_atomically(args.preview, preview)
    # On exit 1 as much as on exit 0, and the preview above with it: a run that
    # withheld the picture precisely when the result was surprising would have
    # the behavior backwards. The report reads the grid as written, like the
    # file and the preview; only its choice block reads the grid as ranked.
    print(
        cw_report.render_report(
            written,
            prepared.bank,
            prepared.config,
            prepared.dropped,
            islands,
            prepared.phrases,
            kept=prepared.kept,
            files=prepared.files,
            mask_file=prepared.mask_file,
            declined=declined,
            ranked=outcome,
        ),
        file=sys.stdout,
    )
    return 0 if outcome.conforming else 1


def run_fill(args: argparse.Namespace) -> int:
    """Search for a grid, write it, and report: 0 conforming, 1 near miss, 2 refused."""
    try:
        return _fill(args)
    except cw_command_base.REFUSALS as exc:
        return cw_command_base.refuse(args.tool, exc)
