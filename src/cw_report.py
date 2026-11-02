"""cw_report: the placement report and its shortage diagnosis.

This is the tool's human-facing product, not an error channel: the same report
goes to stdout on exit 0 and on exit 1, because what an operator needs after a
miss is the number to change, not a restatement that the run failed. Density
is the reason the closing lines exist at all: it is a demand on the bank
rather than on search effort, so a report ending in "no grid found"
would send the reader back to `--help` for a knob that cannot help them.

One sourcing rule runs through every block here, and it is deliberate:

- **The grid is authoritative, never the placement record.** Which answers are
  in the puzzle, which themes they carry, and where each featured answer sits
  are all read back out of `outcome.rows`. One placement can create more than
  one entry and an entry can arrive for free, so the record under-reports; and
  reading the cells back is what stops a coordinate bug and a rendering bug
  from agreeing with each other and producing a picture
  that looks right beside a report that matches it.

The closing block, which turns a miss into the knob to change, is built in
`cw_report_remedy`, and the rule its verdict is sourced by is stated there.

Every ordering here comes from an ordered source (`bank.entries`,
`bank.themes`, or an explicit `sorted`) because two runs must produce
byte-identical output, and a set's iteration order is
`PYTHONHASHSEED`-dependent. No set here can reach output: each serves only
`in` and `len`, or goes straight into `sorted`, which replaces the hash order
with a defined one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

import cw_accept
import cw_answer
import cw_bank
import cw_config
import cw_density
import cw_grid
import cw_pairs
import cw_report_choice
import cw_report_remedy
import cw_search
import cw_source
import cw_text

#: Detail lines sit one indent under the heading that introduces them, so a
#: block can be found by its heading and read without re-parsing the whole
#: report. Named because both the writer and every test that scopes an
#: assertion to one line depend on the same width.
_INDENT = "  "

#: Heads the block naming each placed answer the bank writes otherwise.
_WRITTEN_HEADING = (
    "Written forms, as the bank spells them "
    "(the enumeration ends a clued answer's clue):"
)


def _cell_counts(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]] = frozenset()
) -> tuple[int, int]:
    """`(cells the grid may use, filled cells)`, both on one basis.

    Through `cw_grid.usable_cells` rather than re-summing the same two counts
    here: a second spelling of the density arithmetic is a second thing a
    `--mask` would have to be taught, and the two would disagree the first time
    only one of them was.
    """
    total, blocked = cw_grid.usable_cells(rows, masked)
    return total, total - blocked


def _placed_answers(rows: Sequence[str], bank: cw_bank.Bank) -> frozenset[str]:
    """Every bank answer standing in the grid, as a membership set.

    From the grid's runs rather than from the search's placement history, for
    the reason `cw_search.SearchOutcome` states: an entry can arrive as a free
    crossing, and it counts exactly like a deliberate one.

    A set rather than an ordered sequence because `in` and `len` are all any
    caller wants: an ordering documented here but read by nobody is a promise
    that goes stale silently, and an unread order is also a hash-seeded one
    waiting to leak into output the first time somebody does iterate it.
    Neither this set nor the `present` set below is ever iterated.
    """
    present = {run.text for run in cw_grid.runs_from_rows(rows)}  # membership only
    return frozenset(entry.answer for entry in bank.entries if entry.answer in present)


def _placed_line(rows: Sequence[str], bank: cw_bank.Bank) -> str:
    """The headline count: placed N of M bank entries.

    `len` of the set is the entry count because `cw_bank.parse_bank` rejects a
    repeated answer before a Bank exists, the same guarantee `Bank.by_answer`
    already builds on.
    """
    return (
        f"Placed {len(_placed_answers(rows, bank))} of "
        f"{len(bank.entries)} bank entries."
    )


def _mask_lines(mask_file: str | None, config: cw_config.FillConfig) -> list[str]:
    """The `--mask` line: the picture's own path, and what it forbids; none without one.

    Beside `_files_lines` and just above the grid line, because those three are
    one thought: which files this run read, and what the grid measured against.
    The count is derived from the config, so it cannot disagree with the basis
    the grid line names; only the PATH has to be carried here, since a config
    holds values rather than the files they came from.

    The denominator is the whole grid rather than the usable part: this line
    is how a reader learns how many cells left the grid, so measuring it over
    what remains would state the subtraction in terms of its own result.

    The path is escaped here, where the line is built, as a refusal escapes
    one (`cw_text.visible`): a file name can hold a control or bidi character,
    or a surrogate no strict UTF-8 stream can write, and the caller keeps the
    name as written, so a report and a refusal show one file alike.
    """
    if mask_file is None:
        return []
    cells = config.rows * config.cols
    return [
        f"From --mask {cw_text.visible(mask_file)}: {len(config.masked)} of "
        f"{cells} cells may never hold a letter."
    ]


def _files_lines(files: Sequence[tuple[str, int]]) -> list[str]:
    """Each `--bank` file, in the order merged, with its entry count; nothing for one.

    Under the headline because the headline counts the merged bank, each answer
    once, and this line is how a reader squares that count with their own files.
    One bank prints nothing: there is no merge to square. Each name is escaped
    as `_mask_lines` escapes its path, and for the same reason.
    """
    if len(files) <= 1:
        return []
    listed = ", ".join(
        f"{cw_text.visible(name)} ({count} {'entry' if count == 1 else 'entries'})"
        for name, count in files
    )
    return [f"Merged {len(files)} bank files, in the order given: {listed}."]


def _grid_line(rows: Sequence[str], config: cw_config.FillConfig) -> str:
    """Size, fill, achieved density, and the range that was requested.

    The size is the requested one (`config`) while the cell counts and the
    percentage are the produced ones (`rows`). Deliberately both: the size is
    what the operator asked for and what every "too long for a RxC grid"
    annotation below names, while the density verdict has to describe the grid
    that actually came back.
    """
    total, filled = _cell_counts(rows, config.masked)
    # Named only under a mask, where the percentage is over fewer cells than the
    # size beside it: a figure whose basis a reader cannot see is one they will
    # read against the wrong grid. Without a mask the size beside the figure is
    # its basis, so the line names none.
    basis = "" if not config.masked else f"of {total} unmasked cells "
    return (
        f"Grid {config.rows}x{config.cols}: {filled} filled cells, "
        f"{cw_grid.blocked_percent(rows, config.masked):.1f}% blocked {basis}"
        f"(requested {config.min_blocked:.1f}-{config.max_blocked:.1f}%)."
    )


def _one_feature_lines(rows: Sequence[str], answer: str) -> list[str]:
    """One featured answer's orientation, span, and shaded cells.

    `cw_grid.find_answer` is the required read-back: the coordinates printed
    are the ones the answer actually occupies in `rows`,
    so a report cannot agree with a wrong placement record. Coordinates are
    0-based `(row, column)` indexing `rows[r][c]`, and the line says so:
    an unstated convention here is the classic off-by-one.
    """
    run = cw_grid.find_answer(rows, answer)
    if run is None:
        return [f"Featured answer {answer}: not present in the grid."]
    cells = run.cells
    first, last = cells[0], cells[-1]
    rendered = ", ".join(f"({row}, {col})" for row, col in cells)
    return [
        f"Featured answer {answer}: {run.direction}, "
        f"({first[0]}, {first[1]}) to ({last[0]}, {last[1]}).",
        f"{_INDENT}Shaded cells, 0-based (row, column): {rendered}",
    ]


def _feature_lines(rows: Sequence[str], config: cw_config.FillConfig) -> list[str]:
    """Every featured answer's lines, in the order the flags were given.

    Flag order rather than grid scan order, so a reader finds each feature
    where they wrote it. A pinned feature is reported exactly like a bare one,
    read back out of the grid: printing its anchor instead would be trusting
    the request over the result.
    """
    return [
        line
        for feature in config.features
        for line in _one_feature_lines(rows, feature.answer)
    ]


def _theme_lines(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> list[str]:
    """Per-theme placed counts against the floor, then the floor's verdict.

    Each label is shown through `cw_text.visible`, which escapes the refusal
    set plus the bidi controls. The bank has already refused the first in a
    label, but a bidi control is legal there, and printed raw it would reorder
    the rest of its line.
    """
    if not bank.themes:
        return ["Themes: none declared in the bank."]
    counts = cw_accept.theme_counts(rows, bank)
    floor = config.min_entries_per_theme
    lines = [f"Themes (floor {floor} per theme):"]
    for key, info in bank.themes.items():
        count = counts.get(key, 0)
        verdict = "met" if count >= floor else "short"
        label = cw_text.visible(info.label)
        lines.append(f"{_INDENT}{label}: {count} placed, floor {floor} - {verdict}")
    # The overall verdict comes from cw_accept, not from a second
    # `met >= min_themes` here: this line prints directly above the echoed
    # missed-constraint list, so two copies of the comparison could contradict
    # each other inside one report. Named `floor_met` rather than reusing
    # `verdict` above, which is the per-theme string.
    met, floor_met = cw_accept.theme_floor_status(rows, bank, config)
    overall = "floor met" if floor_met else "floor NOT met"
    lines.append(
        f"{met} of {len(bank.themes)} declared themes reach the floor - {overall}."
    )
    return lines


def _unplaced_annotation(answer: str, config: cw_config.FillConfig) -> str:
    """Why `answer` is not in the grid, as far as that is knowable.

    "Too long" is the one reason a report can assert: an answer longer than
    every line of the grid could never have been placed, whatever the search
    did. Anything else genuinely is "did not fit", and claiming a specific
    cause there would be a sentence the code cannot support.
    """
    if len(answer) > cw_accept.longest_line(config):
        return f"{len(answer)} letters, too long for a {config.rows}x{config.cols} grid"
    return f"{len(answer)} letters, did not fit"


def _unplaced_lines(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> list[str]:
    """The answers the grid does not hold, annotated where the reason is knowable."""
    if not bank.entries:
        # "every bank entry is in the grid" is vacuously true of no entries and
        # reads as success. A bank can arrive here empty (`screen_excluded`
        # never fails a run), so the sentence has to say which of the two it is.
        return ["Unplaced answers: none - the bank holds no answers."]
    placed = _placed_answers(rows, bank)
    missing = [entry.answer for entry in bank.entries if entry.answer not in placed]
    if not missing:
        return ["Unplaced answers: none - every bank entry is in the grid."]
    return [f"Unplaced answers ({len(missing)}):"] + [
        f"{_INDENT}{answer} - {_unplaced_annotation(answer, config)}"
        for answer in missing
    ]


def _dropped_lines(dropped: Sequence[tuple[str, str]]) -> list[str]:
    """The entries `--excluded-terms` removed, listed and counted.

    Omitted entirely when the screen removed nothing, which is the same state
    as the flag not having been used. The block exists because a silent drop
    would make the headline "placed N of M" a lie about a number the operator
    supplied.
    """
    if not dropped:
        return []
    return [f"Dropped by --excluded-terms ({len(dropped)}):"] + [
        f"{_INDENT}{answer} - {reason}" for answer, reason in dropped
    ]


def _length_lines(rows: Sequence[str], bank: cw_bank.Bank) -> list[str]:
    """For each answer length, how many the bank holds and how many are placed.

    Shortest first, sorted on the integer length: `sorted` rather than the
    set's own order because a hash-seeded ordering must never reach emitted
    output, and on the integer rather than on the rendered
    label because sorting those as text would put 11 before 3.
    """
    if not bank.entries:
        # `render_report`'s own contract: an empty block drops out rather than
        # leaving a heading with nothing under it. The loop below emits no row
        # for an empty bank, so without this the heading is the whole block and
        # the orchestrator's `if block` filter never fires for it.
        return []
    placed = _placed_answers(rows, bank)
    lines = ["Shortage by word length:"]
    for length in sorted({len(entry.answer) for entry in bank.entries}):
        held = [entry.answer for entry in bank.entries if len(entry.answer) == length]
        in_grid = sum(1 for answer in held if answer in placed)
        lines.append(
            f"{_INDENT}{length} letters: {len(held)} in bank, {in_grid} placed"
        )
    return lines


def _shortfall_cells(rows: Sequence[str], config: cw_config.FillConfig) -> int:
    """How many more filled cells the requested density ceiling needs.

    Zero when the ceiling is already met. The allowance is
    `cw_density.most_blocked`, the count form of the very ceiling acceptance
    judges by, so this line and the missed list above it cannot disagree about
    whether the grid is within it.
    """
    total, filled = _cell_counts(rows, config.masked)
    allowed_blocked = cw_density.most_blocked(total, config.max_blocked)
    return max(0, total - allowed_blocked - filled)


def _shortfall_line(rows: Sequence[str], config: cw_config.FillConfig) -> str:
    """The closing shortfall line: cells needed, and answers that would supply them.

    The gap is closed by longer answers, not by more search time, so the figure
    quoted is against the longest answer the grid can hold.
    The division is safe without a guard: `validate_fill_config` rejects a
    non-positive dimension, so `longest_line` is at least 1 wherever this
    branch runs: a zero-divisor guard here would be a branch no test could
    reach.
    """
    needed = _shortfall_cells(rows, config)
    if needed == 0:
        return (
            "Density shortfall: none - the grid is already within the requested "
            f"{config.max_blocked:.1f}% blocked ceiling."
        )
    longest = cw_accept.longest_line(config)
    answers = math.ceil(needed / longest)
    return (
        f"Density shortfall: {needed} more filled cells to reach the requested "
        f"{config.max_blocked:.1f}% blocked ceiling - roughly {answers} more "
        f"answers of up to {longest} letters."
    )


def _written_lines(rows: Sequence[str], bank: cw_bank.Bank) -> list[str]:
    """Each placed answer the bank spells otherwise, in grid order, with its enumeration.

    Empty, heading and all, when none is placed, so a letters-only run's report
    carries no such block. The enumeration shown is the one a clued answer's
    clue ends with in the written grid (`cw_answer.with_enumeration`).
    """
    by_answer = bank.by_answer()
    lines: list[str] = []
    for text in dict.fromkeys(run.text for run in cw_grid.runs_from_rows(rows)):
        entry = by_answer.get(text)
        if entry is None or entry.spelling is None:
            continue
        lengths = cw_answer.enumeration(entry.spelling)
        shown = entry.spelling if lengths is None else f"{entry.spelling} {lengths}"
        lines.append(f"{_INDENT}{text} - {shown}")
    return [_WRITTEN_HEADING, *lines] if lines else []


def _vocabulary(bank: cw_bank.Bank, kept: Sequence[str]) -> cw_bank.Bank:
    """The --bank file's own entries: `bank` without the entries kept from --source."""
    if not kept:
        return bank
    left = frozenset(kept)  # membership only
    return cw_bank.Bank(
        themes=bank.themes,
        entries=tuple(entry for entry in bank.entries if entry.answer not in left),
    )


def render_report(
    outcome: cw_search.SearchOutcome,
    bank: cw_bank.Bank,
    config: cw_config.FillConfig,
    dropped: Sequence[tuple[str, str]],
    islands: Sequence[tuple[int, int, str]] = (),
    phrases: cw_pairs.Phrases = cw_pairs.NO_PHRASES,
    kept: Sequence[str] = (),
    files: Sequence[tuple[str, int]] = (),
    mask_file: str | None = None,
    declined: Sequence[tuple[int, int, str]] = (),
    ranked: cw_search.SearchOutcome | None = None,
) -> str:
    """Render the report for one `fill` run.

    `dropped` is the `(answer, reason)` pairs `--excluded-terms` removed before
    the bank reached the search; empty when the flag was not used. It is taken
    as a parameter rather than recomputed here because `bank` is already the
    screened bank, which is exactly why its removals have to be reported
    separately, or the headline count silently contradicts the operator's own
    input file. `islands` are the lone letters `fill` laid on the written grid,
    and `declined` those `--min-blocked` left unlaid. `outcome` is the grid as
    written, islands included, so every figure here (the density line and the
    shortfall with it) describes the file on disk and its preview. `ranked` is
    the search's own outcome, for the choice block alone: that block states what
    the grid was ranked on, and islands are laid after the ranking. None means
    the two are one grid. `phrases` are the `--phrases` lists the answer-pairs
    block joins against beside the bank, carrying the barred terms the warning
    block reads; `cw_pairs` says why neither scores. The warning comes straight
    after the headline because it is the one block a reader must not miss.

    `kept` is the entries `--source` kept outside the bank, which `bank` already
    holds at its end (`cw_source.StartSource`); empty without a source. The
    headline, unplaced and word-length blocks describe the --bank file, so they
    count without them. Every block that judges the grid (the choice, pairs,
    theme and remedy blocks) counts the full `bank`, the one the grid was
    searched and scored on. The source block comes straight after the warning,
    so what the fill started from is read before anything the fill added.

    `files` is each `--bank` file with the entries it holds, in the order they
    were merged (`cw_bank_merge.BankSet`); a merge of several is listed under
    the headline, and one bank, or none handed over, lists nothing.

    `mask_file` is the `--mask` picture's path as the operator wrote it, or None
    without the flag. A path rather than a count: the count is already in
    `config.masked`, and a report line naming a file has to name the file.

    An orchestrator only: each block is built by its own helper above, and the
    blocks are separated by a blank line so a reader can find one by its
    heading. Empty blocks drop out rather than leaving a heading with nothing
    under it.
    """
    vocabulary = _vocabulary(bank, kept)
    blocks: list[list[str]] = [
        [
            _placed_line(outcome.rows, vocabulary),
            *_files_lines(files),
            *_mask_lines(mask_file, config),
            _grid_line(outcome.rows, config),
        ],
        cw_pairs.barred_lines(outcome.rows, phrases),
        cw_source.source_lines(
            config.start,
            kept,
            outcome.rows,
            frozenset(entry.answer for entry in bank.entries),
            config.source_size,
        ),
        _feature_lines(outcome.rows, config),
        cw_report_choice.selection_lines(
            outcome if ranked is None else ranked, bank, config
        ),
        cw_report_choice.island_lines(outcome, config, islands, declined),
        cw_pairs.pair_lines(
            outcome.rows, (entry.answer for entry in bank.entries), phrases
        ),
        _written_lines(outcome.rows, bank),
        _theme_lines(outcome.rows, bank, config),
        _unplaced_lines(outcome.rows, vocabulary, config),
        _dropped_lines(dropped),
        _length_lines(outcome.rows, vocabulary),
        [_shortfall_line(outcome.rows, config)],
        cw_report_remedy.remedy_lines(outcome, bank, config),
    ]
    return "\n\n".join("\n".join(block) for block in blocks if block)
