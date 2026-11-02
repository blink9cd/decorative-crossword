"""cw_shade_report: what `shade` prints, in each of its two modes.

The human-facing product of the subcommand, on stdout, exactly as
`cw_report.render_report` is `fill`'s. Two rules run through it, and both are
borrowed from that module rather than re-decided:

- **The grid is authoritative.** Every figure here is read off the rows and
  the placements derived from them, never off a record of what the search
  thought it did.
- **A count that is not accounted for is a count that misleads.** A headline
  saying 57 of 1332 words became candidates is only usable beside the reasons
  the other 1275 did not, so the two blocks below name every one of them and
  the four numbers add up to the words the search was handed.
  `tests/test_shade_report.py` pins that they do.

Separate from `cw_report` rather than added to it: that module is about a
search for a grid (density, theme floors, shortage by word length), and
none of its blocks or its vocabulary apply here.

Every ordering here comes from an ordered source (the ranked candidate
tuple, the word list's own order, or an explicit slice) because two runs
must produce byte-identical output.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import cw_config
import cw_grid
import cw_shade
import cw_text

#: Detail lines sit one indent under the heading that introduces them, the
#: same width `cw_report` uses, so the two reports read as one tool's output.
_INDENT = "  "

#: The separator between a listed name and the note explaining it.
_REASON = " - "


def _headline_lines(
    rows: Sequence[str],
    result: cw_shade.HiddenWordSearch,
    distinct_words: int,
    skipped: Sequence[tuple[str, str]],
) -> list[str]:
    """Grid size, how many words the search was handed, and the candidate count.

    The word count is distinct words, not lines of the file: `load_word_list`
    collapses duplicates and folds case before the search sees them, so a list
    holding a word twice has fewer words than it has lines. Saying "read" would
    invite the reader to check the number against their file's line count and
    find it short, with nothing in the report to explain the gap.

    The grid's width is the longest row, as `cw_svg_caption.derivable_line`
    measures it.
    """
    cols = max((len(row) for row in rows), default=0)
    lettered = len(cw_shade.lettered_cells(rows))
    return [
        f"Grid {len(rows)}x{cols}: {lettered} lettered cells.",
        f"Word list: {distinct_words} distinct words, "
        f"{len(skipped)} skipped as unusable.",
        f"Candidates: {len(result.candidates)} of {distinct_words} words spell a "
        "hidden word in this grid.",
    ]


def _shortfall_lines(
    result: cw_shade.HiddenWordSearch, config: cw_config.ShadeConfig
) -> list[str]:
    """Why the words that did not become candidates did not.

    Each line names the flag that governs it where one does, so the reader can
    act on the number rather than only read it. A reason that removed nothing
    is omitted: a line saying "0 shorter than 5 letters" is noise, and the
    block drops out entirely when every word qualified.
    """
    lines: list[str] = []
    if result.too_short:
        lines.append(
            f"{_INDENT}{result.too_short} shorter than {config.min_length} "
            "letters (--min-length)"
        )
    if result.unspellable:
        lines.append(
            f"{_INDENT}{result.unspellable} not spellable by this grid in reading order"
        )
    return ["Did not qualify:", *lines] if lines else []


def _excluded_lines(result: cw_shade.HiddenWordSearch) -> list[str]:
    """The words `--exclude-grid-answers` removed, by name.

    Named rather than only counted, and for a specific reason: an answer
    already in the grid is usually the word the operator was about to choose,
    so seeing it removed is the useful half. Absent entirely when the flag was
    off or removed nothing, which are the same state as far as a reader is
    concerned.
    """
    if not result.excluded_answers:
        return []
    return [
        f"Already answers in this grid ({len(result.excluded_answers)}) - "
        "excluded by --exclude-grid-answers:",
        *(f"{_INDENT}{answer}" for answer in result.excluded_answers),
    ]


def _candidate_line(placement: cw_shade.Placement) -> str:
    """One ranked candidate: what it is, how far it spreads, what it costs."""
    return (
        f"{_INDENT}{placement.word}{_REASON}{len(placement.word)} letters, "
        f"{placement.rows_spanned} row(s) spanned, clustering "
        f"{placement.clustering}"
    )


def _candidate_lines(
    result: cw_shade.HiddenWordSearch, config: cw_config.ShadeConfig
) -> list[str]:
    """The ranked list, capped by `--top`, saying so only when it capped.

    A cap that did not bite is not mentioned: "showing 25 of 25" invites the
    reader to wonder what was hidden when nothing was. `--top 0` shows the
    whole list, the same reading of zero `--max-steps` already has.
    """
    if not result.candidates:
        return []
    shown = result.candidates if config.top == 0 else result.candidates[: config.top]
    counts = (
        ""
        if len(shown) == len(result.candidates)
        else f" (showing {len(shown)} of {len(result.candidates)})"
    )
    return [
        f"Hidden-word candidates{counts}, best first - one shaded cell per letter:",
        *(_candidate_line(placement) for placement in shown),
    ]


def _skipped_lines(skipped: Sequence[tuple[str, str]]) -> list[str]:
    """The word-list lines that were not usable words, named with their reason.

    The half of `load_word_list`'s contract that keeps a skip from being a
    quiet one: the reader can see exactly which lines their list lost and fix
    them, rather than wondering why a word they expected never appeared. Each
    is shown through `cw_text.visible`, since a skipped line is exactly the
    one that may hold a character a terminal would act on rather than show.
    """
    if not skipped:
        return []
    return [
        f"Skipped word-list lines ({len(skipped)}):",
        *(
            f"{_INDENT}{cw_text.visible(word)}{_REASON}{reason}"
            for word, reason in skipped
        ),
    ]


def _miss_lines(
    result: cw_shade.HiddenWordSearch, config: cw_config.ShadeConfig
) -> list[str]:
    """On an empty candidate list, the knobs that could produce one.

    Modeled on `cw_report_remedy`'s "What would clear each": a verdict with no
    route out of it sends the reader back to `--help` for a knob that may not
    help. Each remedy is offered only when it could actually apply: dropping
    `--exclude-grid-answers` cannot help a run where it removed nothing, and
    lowering `--min-length` cannot help a run where no word fell short of it;
    advertising either there would be advice that is simply false.

    The floor is guarded a second way, for a sharper version of the same
    reason: `cw_config.validate_shade_config` refuses a `--min-length` under
    `cw_grid.MIN_RUN`, so a run already at the floor has nowhere to lower it to
    and following the advice would exit 2.
    """
    if result.candidates:
        return []
    remedies: list[str] = []
    if result.too_short and config.min_length > cw_grid.MIN_RUN:
        remedies.append(f"lower --min-length below {config.min_length}")
    if result.excluded_answers:
        remedies.append(
            "drop --exclude-grid-answers, which removed "
            f"{len(result.excluded_answers)} word(s)"
        )
    remedies.append("supply a longer word list")
    return [
        "NO HIDDEN WORD FOUND.",
        "What would find one:",
        *(f"{_INDENT}{remedy}" for remedy in remedies),
    ]


def render_search_report(
    rows: Sequence[str],
    result: cw_shade.HiddenWordSearch,
    config: cw_config.ShadeConfig,
    skipped: Sequence[tuple[str, str]],
) -> str:
    """Render the ranked hidden-word report for one `shade --words` run.

    An orchestrator only: each block is built by its own helper above, blocks
    are separated by a blank line so one can be found by its heading, and an
    empty block drops out rather than leaving a heading with nothing under it,
    the same shape `cw_report.render_report` has.

    `distinct_words` is recovered from the result's own four counts rather
    than taken as a parameter: they partition the list by construction, so
    deriving it here is what makes the headline incapable of disagreeing with
    the accounting beneath it.
    """
    distinct_words = (
        len(result.candidates)
        + result.too_short
        + result.unspellable
        + len(result.excluded_answers)
    )
    blocks: list[list[str]] = [
        _headline_lines(rows, result, distinct_words, skipped),
        _shortfall_lines(result, config),
        _excluded_lines(result),
        _candidate_lines(result, config),
        _skipped_lines(skipped),
        _miss_lines(result, config),
    ]
    return "\n\n".join("\n".join(block) for block in blocks if block)


def _verdict_line(placement: cw_shade.Placement) -> str:
    """The score in words, so a reader needs no scale to act on it.

    The threshold is `cw_shade.NEIGHBORING_STEP_PENALTY`, which is derived
    from the penalty table rather than chosen: the cost of one same-row
    neighboring step, the shape that makes shading read as a damaged entry. It
    is judged on the whole clustering, so touching steps alone can reach it
    too, with no same-row pair anywhere, and the verdict calls that bunched as
    well.
    """
    if placement.clustering >= cw_shade.NEIGHBORING_STEP_PENALTY:
        return (
            f"{_INDENT}Clustering {placement.clustering}: the shaded cells "
            "bunch - this will read as a corrupted answer, not a hidden word."
        )
    return (
        f"{_INDENT}Clustering {placement.clustering}: the shaded cells scatter "
        "- this reads as a hidden word."
    )


def render_placement_report(placement: cw_shade.Placement) -> str:
    """Render the single-word report for one `shade --word` run.

    Coordinates appear twice, in two forms, and that is deliberate rather than
    duplication: the `(row, column)` line is the convention the rest of this
    project reports shaded cells in (see `cw_report`'s featured-answer block),
    and the paste form is the one a caller can put straight into a data file.
    Both are rendered from the one `placement.cells` tuple, so they cannot
    disagree about which cells were chosen.
    """
    rendered = ", ".join(f"({row}, {col})" for row, col in placement.cells)
    # `json.dumps` rather than hand-built brackets: the paste form is only
    # worth offering if it is genuinely valid JSON, and the encoder is what
    # guarantees that rather than a format string that looks like it.
    paste = json.dumps([[row, col] for row, col in placement.cells])
    return "\n".join(
        [
            f"Hidden word {placement.word}: {len(placement.cells)} cells across "
            f"{placement.rows_spanned} row(s), clustering {placement.clustering}.",
            f"{_INDENT}Shaded cells, 0-based (row, column): {rendered}",
            f"{_INDENT}Paste form: {paste}",
            _verdict_line(placement),
        ]
    )
