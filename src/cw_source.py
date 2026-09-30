"""cw_source: decides which `--source` grids a fill can start from.

`fill --source grid_source.json` starts a fill from an existing grid instead of
an empty one. The source contributes its rows, and every run of them is one of
three things:

- an entry the BANK holds, described by the bank's own record;
- an entry KEPT from the source, for a run the bank lacks but the source's own
  `clues` map declares, carried into the search bank with the clue and theme
  that record gives it;
- a PARTIAL run, one neither holds nor declares, that a bank answer not yet on
  the grid could still be laid over: a half-written word the fill completes.

A run that is none of the three is refused rather than guessed at.

**The bank wins wherever it holds an answer.** A run the bank holds is the
bank's entry, clue and theme included, whatever the source says of it; and
where the bank and the source both declare a theme key, the bank's record is the
one the search sees. A source adds only what the bank lacks.

**A source that passes breaks the one rule only where the fill must finish it.**
Once `start_from` returns, every run of the source's rows that breaks the
distinct-run rule under the vocabulary it hands back -- the bank's answers plus
every kept entry -- is one of its partial runs, and an unused answer could
still be laid over each. The walk's step test and the best-effort guard rest on
that property, and `tests/test_source_properties.py` holds `start_from` to it.
It is a promise about the START only: `cw_reach.completable` ignores the lines
crossing a run, so a partial run that passes may still never be completed.

**Every refusal names every offender of its kind**, never the first. That is
why a kept entry is parsed on its own rather than in one batch, and why the
`--excluded-terms` refusal gathers the bank entries the caller's screen dropped
and the kept entries the terms bar into one message.

`start_from` takes a bank the caller has ALREADY screened with
`--excluded-terms`, plus what that screen dropped. It screens only the kept
entries itself, because they never passed through the caller's screen.

`resolve_size` is the check on the size FLAGS beside a source, decided before
its content matters: they may grow the source's grid, never crop it, and never
past `cw_grid.MAX_SIDE`. It raises `cw_config.ConfigError`, because that is a
contradictory command line rather than a fault in the grid. `place_source` then
writes the source onto the top-left of that canvas, so every source cell keeps
its own coordinates and a position read off the source still names the same
cell. That no output names the source file is
`cw_paths.refuse_unusable_outputs`' check, which covers every file a run reads.

`source_lines` words the fill report's block on the grid a fill started from:
what the source held, which entries were kept from it, and how each partial run
was completed.
"""

from __future__ import annotations

from collections.abc import Sequence, Set as AbstractSet
from dataclasses import dataclass
from types import MappingProxyType

import cw_bank
import cw_config
import cw_excluded_terms
import cw_grid
import cw_grid_document
import cw_island
import cw_reach
import cw_text


class SourceError(ValueError):
    """A `--source` grid no fill can start from: exit 2, naming what is wrong."""


def resolve_size(
    rows: int | None, cols: int | None, start: tuple[str, ...]
) -> tuple[int, int]:
    """The grid size: a source's own, grown by either flag given; else both flags, required."""
    if start:
        return _grown_size(rows, cols, (len(start), len(start[0])))
    # Tested on the two values themselves rather than on the list below, so the
    # return narrows both to int without a cast.
    if rows is None or cols is None:
        flags = (("--rows", rows), ("--cols", cols))
        missing = [flag for flag, value in flags if value is None]
        verb = "is" if len(missing) == 1 else "are"
        raise cw_config.ConfigError(
            f"{' and '.join(missing)} {verb} required unless --source gives the grid"
        )
    return rows, cols


def _grown_size(
    rows: int | None, cols: int | None, own: tuple[int, int]
) -> tuple[int, int]:
    """The canvas beside a source whose own size is `own`: each flag given, else the source's.

    A flag equal to the source's dimension is accepted, since it states the
    size the source already has. One under it is refused, because fill only
    ever adds to a source and a smaller grid would have to drop some of it;
    every such flag is named in the one refusal.

    One past the grid-size cap is refused too, here and not only in
    `cw_config.validate_fill_config`: the source is placed on this canvas
    before that check runs, and a flag far past the cap would make placing it
    gigabytes of blocked cells, or a traceback, rather than a refusal.
    """
    given = (("--rows", rows, own[0], "rows"), ("--cols", cols, own[1], "columns"))
    short = [
        f"{flag} {value} is smaller than the --source grid's {size} {unit}"
        for flag, value, size, unit in given
        if value is not None and value < size
    ]
    if short:
        raise cw_config.ConfigError(
            "; ".join(short) + ": fill grows a source, never crops it"
        )
    grown = (own[0] if rows is None else rows, own[1] if cols is None else cols)
    cw_config.validate_size(*grown)
    return grown


def place_source(start: tuple[str, ...], rows: int, cols: int) -> tuple[str, ...]:
    """`start` written onto the top-left of a `rows` x `cols` grid, every other cell blocked.

    Empty without a source. Requires a size `resolve_size` accepted, so at
    least the source's own and at most the cap. The top-left is deliberate: a
    source cell keeps its (row, column), so a pin, a stray's position or a
    `gaps` report read off the source names the same cell of the grown grid,
    and a source that should grow upward or leftward is given blocked rows or
    columns there instead.
    """
    if not start:
        return ()
    added = (cw_grid.BLOCK * cols,) * (rows - len(start))
    return tuple(line.ljust(cols, cw_grid.BLOCK) for line in start) + added


@dataclass(frozen=True)
class StartSource:
    """A source that passed: the entries kept from it, its partial runs, and the search bank.

    `kept` and `partial` are in run scan order. `bank` holds the screened bank's
    entries first, then each kept entry in that same order. `partial` is empty
    unless the source holds a half-written word, and always without a source.
    """

    kept: tuple[str, ...]
    bank: cw_bank.Bank
    partial: tuple[cw_grid.Run, ...] = ()


def _refuse_repeats(runs: Sequence[cw_grid.Run]) -> None:
    """Raise SourceError naming every answer the source holds twice."""
    seen: set[str] = set()
    # A list, not a set: it is joined into the message, whose order must not
    # depend on hash seeding.
    repeated: list[str] = []
    for run in runs:
        if run.text in seen and run.text not in repeated:
            repeated.append(run.text)
        seen.add(run.text)
    if repeated:
        raise SourceError(
            "--source holds "
            + ", ".join(cw_text.shown(text) for text in repeated)
            + " twice; a grid holds each answer once"
        )


def _describe_run(run: cw_grid.Run) -> str:
    """One run as a refusal names it: its letters, its direction, its first cell."""
    return f"{cw_text.shown(run.text)} {run.direction} at ({run.row}, {run.col})"


def _partial_runs(
    document: cw_grid_document.GridDocument,
    runs: Sequence[cw_grid.Run],
    accounted: AbstractSet[str],
    bank: cw_bank.Bank,
) -> tuple[cw_grid.Run, ...]:
    """The runs neither accounted for nor declared; SourceError naming each nothing could complete.

    `accounted` is the bank's answers plus the entries the caller's screen
    dropped: a dropped run is the `--excluded-terms` refusal's to name, and
    calling it undeclared would send the operator after the wrong fix.

    Such a run is partial when an answer of the screened bank not already on
    the source could be laid over it (`cw_reach.completable`), ends or gaps
    alike. One no answer could ever complete is refused here, in milliseconds,
    rather than proven hopeless by a whole budget: nothing vouches for it, and
    the tool does not guess.
    """
    undeclared = [
        run
        for run in runs
        if run.text not in accounted and run.text not in document.clues
    ]
    unused = cw_reach.unused_answers(document.rows, bank)
    stranded = [
        run
        for run in undeclared
        if not cw_reach.completable(document.rows, run, unused)
    ]
    if stranded:
        raise SourceError(
            "--source holds runs that are neither bank answers, declared in its "
            "clues, nor completable by a bank answer: "
            + "; ".join(_describe_run(run) for run in stranded)
        )
    return tuple(undeclared)


def _theme_record(
    key: str, document: cw_grid_document.GridDocument, bank: cw_bank.Bank
) -> cw_bank.ThemeInfo | None:
    """Theme `key`'s record: the bank's where it declares the key, else the source's, else None."""
    if key in bank.themes:
        return bank.themes[key]
    return document.themes.get(key)


def _kept_record(
    answer: str, document: cw_grid_document.GridDocument
) -> dict[str, str]:
    """One kept entry as a bank.json record: its answer, and its theme and clue if any."""
    record = {"answer": answer}
    if answer in document.entry_themes:
        record["theme"] = document.entry_themes[answer]
    if document.clues.get(answer):
        record["clue"] = document.clues[answer]
    return record


def _kept_payload(
    answer: str, document: cw_grid_document.GridDocument, bank: cw_bank.Bank
) -> dict[str, object]:
    """One kept entry as a one-entry bank.json payload, with its theme record if declared.

    A theme key neither the bank nor the source declares is left out of
    `themes`, so `parse_bank` names it as undeclared instead of this module
    restating that rule.
    """
    themes: dict[str, dict[str, str]] = {}
    key = document.entry_themes.get(answer)
    if key is not None:
        info = _theme_record(key, document, bank)
        if info is not None:
            themes[key] = {"label": info.label, "summary": info.summary}
    return {"themes": themes, "entries": [_kept_record(answer, document)]}


def _kept_bank(
    kept: Sequence[str], document: cw_grid_document.GridDocument, bank: cw_bank.Bank
) -> cw_bank.Bank:
    """The kept entries parsed by the bank's own rules, or SourceError naming each refusal.

    Going through `parse_bank` rather than building entries directly holds a
    kept entry to every rule a bank.json entry meets: A-Z answers, declared
    themes, non-empty theme fields and the clue-safety screen. Each entry is
    parsed ON ITS OWN, because `parse_bank` stops at the first bad entry and the
    refusal must name them all. No two kept entries share an answer -- repeats
    are refused before this runs -- so the per-entry parses cannot disagree
    about a duplicate.
    """
    themes: dict[str, cw_bank.ThemeInfo] = {}
    entries: list[cw_bank.BankEntry] = []
    refusals: list[str] = []
    for answer in kept:
        try:
            parsed = cw_bank.parse_bank(_kept_payload(answer, document, bank))
        except cw_bank.BankError as exc:
            refusals.append(f"{cw_text.shown(answer)}: {exc}")
            continue
        themes.update(parsed.themes)
        entries.extend(parsed.entries)
    if refusals:
        raise SourceError(
            "--source entries kept outside the bank are unusable: "
            + "; ".join(refusals)
        )
    return cw_bank.Bank(themes=MappingProxyType(themes), entries=tuple(entries))


def _refuse_screened(
    runs: Sequence[cw_grid.Run],
    dropped: Sequence[tuple[str, str]],
    extra: cw_bank.Bank,
    terms: frozenset[str] | None,
) -> None:
    """Raise SourceError naming every source entry --excluded-terms bars, bank or kept.

    One refusal, whichever side an entry came from: a source run the caller's
    screen dropped from the bank, and a kept entry the terms bar. Named in run
    scan order with each one's reason. A dropped run is refused even when the
    source declares it -- keeping it would carry an answer past the very
    screen that removed it -- which is why `start_from` never keeps one.
    """
    reasons = dict(dropped)
    if terms is not None:
        reasons.update(cw_excluded_terms.screen_excluded(extra, terms)[1])
    barred = [
        f"{cw_text.shown(run.text)} ({reasons[run.text]})"
        for run in runs
        if run.text in reasons
    ]
    if barred:
        raise SourceError(
            "--excluded-terms bars these --source entries: " + ", ".join(barred)
        )


# fuzz-target
def start_from(
    document: cw_grid_document.GridDocument,
    bank: cw_bank.Bank,
    dropped: tuple[tuple[str, str], ...],
    terms: frozenset[str] | None,
) -> StartSource:
    """Validate a loaded `--source` against the screened bank; return what the fill starts from.

    `bank` is the bank after `--excluded-terms`, `dropped` the pairs that screen
    removed, and `terms` the barred terms themselves (None when none were
    given). Raises SourceError, naming every offender, for a repeated answer,
    a run nothing declares that no unused bank answer could complete, a kept
    entry the bank's parser refuses, or an entry `--excluded-terms` bars --
    checked in that order, so repeats are refused before anything is parsed.
    """
    runs = cw_grid.runs_from_rows(document.rows)
    held = {entry.answer for entry in bank.entries}
    removed = {answer for answer, _ in dropped}
    accounted = held | removed
    # A repeat is an ANSWER held twice. A partial run spells no answer, so two
    # copies of one are no repeat: different answers may finish them.
    _refuse_repeats(
        [run for run in runs if run.text in accounted or run.text in document.clues]
    )
    partial = _partial_runs(document, runs, accounted, bank)
    # A dropped run is never kept, declared or not: `_refuse_screened` names it.
    kept = tuple(
        run.text
        for run in runs
        if run.text not in accounted and run.text in document.clues
    )
    extra = _kept_bank(kept, document, bank)
    _refuse_screened(runs, dropped, extra, terms)
    themes = dict(bank.themes)
    themes.update((k, v) for k, v in extra.themes.items() if k not in bank.themes)
    return StartSource(
        kept=kept,
        bank=cw_bank.Bank(
            themes=MappingProxyType(themes), entries=bank.entries + extra.entries
        ),
        partial=partial,
    )


def _completions(
    partial: Sequence[cw_grid.Run], rows: Sequence[str], allowed: AbstractSet[str]
) -> list[str]:
    """Each partial run `rows` completes, as `TEXT as ANSWER DIRECTION at (ROW, COL)`.

    Completed means an answer in `allowed` now lies along the run and covers
    all of it (`cw_reach.covers`). The position is that answer's own first
    cell, which a completion that grew the run backward, or filled a gap before
    it, has moved. In the order `partial` gives; a run nothing covers is left
    out.
    """
    runs = cw_grid.runs_from_rows(rows)
    found: list[str] = []
    for inner in partial:
        cover = next(
            (
                run
                for run in runs
                if run.text in allowed and cw_reach.covers(inner, run.cells)
            ),
            None,
        )
        if cover is not None:
            found.append(
                f"{inner.text} as {cover.text} {cover.direction} at "
                f"({cover.row}, {cover.col})"
            )
    return found


def source_lines(
    start: tuple[str, ...],
    kept: Sequence[str],
    rows: Sequence[str],
    allowed: AbstractSet[str],
    source_size: tuple[int, int],
) -> list[str]:
    """The fill report's block on the grid a fill started from; empty without one.

    The count is taken from `start`, the source's rows as placed on the grid,
    rather than from the grid that came back: it says what the operator handed
    in, and every other block already describes the result. A partial run -- one
    `allowed`, the search bank, does not spell -- is no entry, so it is counted
    apart, and its clause is left out when the source holds none. A lone letter
    is counted whether or not it may stand as an island, because the question
    here is only what the source held. `kept` is named in the order given, and
    its line is left out when the bank already held every run.

    The grown line follows the count when the grid is larger than
    `source_size`, the source's own size, which the placed `start` cannot tell.
    It names the top-left cell because `place_source` always puts a source
    there, which is why every source position the report names is still the
    source's own.

    The completed line is the one read off `rows`, the grid that came back:
    each partial run with the answer now covering it. It is left out when none
    was completed -- on the empty board a refusal or an unfinished walk writes.
    The absorbed line follows it, read off `rows` the same way: each answer
    that grew source entries under `--absorb-entries`, and which (`_absorptions`).
    """
    if not start:
        return []
    letters = sum(len(row) - row.count(cw_grid.BLOCK) for row in start)
    partial = cw_reach.partial_runs(start, allowed)
    entries = len(cw_grid.runs_from_rows(start)) - len(partial)
    partial_clause = f"{len(partial)} partial run(s), " if partial else ""
    lines = [
        f"From --source: {letters} fixed letter(s) in {entries} entry(s), "
        f"{partial_clause}{len(cw_island.lone_cells(start))} lone letter(s)."
    ]
    grid = (len(start), len(start[0]))
    if source_size != grid:
        lines.append(
            f"Grown from --source: its {source_size[0]}x{source_size[1]} grid sits "
            f"at (0, 0) of this {grid[0]}x{grid[1]} grid."
        )
    if kept:
        lines.append(
            f"Kept from --source, not in the bank ({len(kept)}): {', '.join(kept)}."
        )
    completed = _completions(partial, rows, allowed)
    if completed:
        lines.append(
            f"Completed from --source ({len(completed)}): {', '.join(completed)}."
        )
    absorbed, grown = _absorptions(start, rows, allowed)
    if grown:
        lines.append(f"Absorbed from --source ({absorbed}): {', '.join(grown)}.")
    return lines


def _absorptions(
    start: Sequence[str], rows: Sequence[str], allowed: AbstractSet[str]
) -> tuple[int, list[str]]:
    """How many source entries `rows` absorbed, and each absorbing answer as a phrase.

    An entry is a run of `start` that `allowed` spells. It was absorbed when
    `rows` no longer holds it and another run covers all of its cells
    (`cw_reach.covers`). No such run needs checking against `allowed`: source
    letters never move, so a run covering an entry that is gone is longer than
    it, and only `--absorb-entries` lets a fill write one. A weld covers two or
    more, named in `start`'s scan order: `SUN and LOWER into SUNFLOWER across at
    (0, 0)`. Phrases follow `rows`' scan order; an entry nothing covers, as on
    an empty board, is named nowhere.
    """
    after = cw_grid.runs_from_rows(rows)
    gone = [
        run
        for run in cw_grid.runs_from_rows(start)
        if run.text in allowed and run not in after
    ]
    count = 0
    phrases: list[str] = []
    for cover in after:
        inner = [entry.text for entry in gone if cw_reach.covers(entry, cover.cells)]
        if inner:
            count += len(inner)
            phrases.append(
                f"{' and '.join(inner)} into {cover.text} {cover.direction} at "
                f"({cover.row}, {cover.col})"
            )
    return count, phrases
