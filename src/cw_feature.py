"""cw_feature: the `--feature` flag: its grammar, its typed model, and its pin checks.

`fill --feature` repeats, and each value is `ANSWER` or `ANSWER@ROW,COL,DIR`: an
answer the grid must hold, optionally pinned with its first letter at a 0-based
cell. Everything about that one flag that can be decided without a bank lives
here (reading a value, and refusing pins that contradict the grid, each
other, or the `--source` grid they are laid on, including a pin another pin or
a source letter would swallow), and every refusal is a `cw_config.ConfigError`,
on the exit-2 line with the other contradictory configurations. One source
check is handed the source's partial runs rather than a bank:
`validate_source_runs`, which lets a pin lying along a partial run complete it.

What needs the bank does not live here. Whether two pins in adjacent lines form
pairs the bank holds is `cw_accept.preflight`'s question, at exit 1, and the
board the pins form is built once, by `cw_board.pinned_board`.

`preview --feature` repeats too but takes a bare answer only, and borrows two
pieces from here rather than restating them: `ANCHOR_MARK`, to refuse a
position, and `validate_distinct`, to refuse a repeat in `fill`'s own words.

`cw_config.FillConfig` carries a tuple of these `Feature`s, but names the type
only for the type checker: this module imports `cw_config` at runtime, for
`ConfigError` and `FillConfig`, and a runtime import back would be a cycle.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass

import cw_answer
import cw_config
import cw_grid
import cw_reach
import cw_text

#: The character separating an answer from its anchor in a `--feature` value.
#: Public because `preview --feature` refuses any value that carries it.
ANCHOR_MARK = "@"

#: What separates an anchor's parts, and how many parts there are: ROW, COL, DIR.
_ANCHOR_SEPARATOR = ","
_ANCHOR_PARTS = 3

#: The directions an anchor may name, spelled exactly as the report prints them,
#: so a pin can be copied out of one run's report into the next command line.
_DIRECTIONS = (cw_grid.ACROSS, cw_grid.DOWN)

#: A pin as the checks below read it: its answer, and an anchor that is never None.
_Pin = tuple[str, "Anchor"]


@dataclass(frozen=True)
class Anchor:
    """Where a pinned feature's first letter sits, and which way it runs.

    0-based `(row, col)` from the top-left cell, the convention the report
    prints and `grid_source.json`'s `rows` array indexes.
    """

    row: int
    col: int
    direction: str


@dataclass(frozen=True)
class Feature:
    """One `--feature`: an answer the grid must hold, and optionally where.

    `anchor` is None when the search chooses the position, as for a bare
    `--feature ANSWER`. The three coordinates travel together in one `Anchor`
    rather than as three optional fields, so a pin with a row and no direction
    cannot be built at all, and nothing downstream checks for one.
    """

    answer: str
    anchor: Anchor | None


def _parse_index(name: str, part: str, text: str) -> int:
    """One anchor coordinate: the ASCII digits 0-9 and nothing else.

    Not bare `int()`, which also takes a sign, surrounding whitespace, an
    underscore and non-ASCII digits. A pin is a cell index typed by hand, and a
    grammar that quietly accepted ` 1` or `+1` is one whose refusals nobody
    could predict, so a negative row is refused here, as a malformed value,
    rather than reaching the bounds check as a cell above the grid.
    """
    if not (part.isascii() and part.isdigit()):
        raise cw_config.ConfigError(
            f"--feature {cw_text.shown(text)}: {name} must be a non-negative "
            f"integer, got {cw_text.shown(part)}"
        )
    try:
        return int(part)
    except ValueError as exc:
        # The screen above leaves int() one way to refuse: more digits than the
        # interpreter's integer-string limit. No grid has that many rows, so
        # it is a malformed value like any other, named by its length, since
        # echoing thousands of digits back would bury the message.
        raise cw_config.ConfigError(
            f"--feature: {name} has {len(part)} digits, far past any grid's size"
        ) from exc


# fuzz-target
def parse_feature(text: str) -> Feature:
    """Parse one `--feature` value: `ANSWER`, or `ANSWER@ROW,COL,DIR`.

    Raises ConfigError, naming `--feature`, on any other shape. The answer is
    taken verbatim but for its spaces, hyphens and apostrophes, which close up
    (`cw_answer.grid_form`) so `ATTA-BOY` names the grid's `ATTABOY`; case is
    left alone, for the reason `grid_form` gives. Whether it names a bank
    answer is the bank check's question, asked later at exit 2. Whether an
    anchor fits the grid, or agrees with another, is `validate_features`'
    question: this sees one value and no grid.
    """
    written, mark, spec = text.partition(ANCHOR_MARK)
    answer = cw_answer.grid_form(written)
    if not answer:
        raise cw_config.ConfigError(f"--feature {cw_text.shown(text)} names no answer")
    if not mark:
        return Feature(answer, None)
    parts = spec.split(_ANCHOR_SEPARATOR)
    if ANCHOR_MARK in spec or len(parts) != _ANCHOR_PARTS:
        raise cw_config.ConfigError(
            f"--feature {cw_text.shown(text)}: a pin is ANSWER@ROW,COL,DIR, "
            "one to a --feature"
        )
    row_text, col_text, direction = parts
    row = _parse_index("ROW", row_text, text)
    col = _parse_index("COL", col_text, text)
    if direction not in _DIRECTIONS:
        raise cw_config.ConfigError(
            f"--feature {cw_text.shown(text)}: DIR must be "
            f"{cw_text.shown(cw_grid.ACROSS)} or {cw_text.shown(cw_grid.DOWN)}, "
            f"got {cw_text.shown(direction)}"
        )
    return Feature(answer, Anchor(row, col, direction))


def _pins(features: tuple[Feature, ...]) -> tuple[_Pin, ...]:
    """Every pinned feature as its answer and anchor, in flag order.

    Bare features are dropped here, once, so the checks below take an anchor
    that cannot be None and carry no branch for a case they are never handed.
    """
    return tuple(
        (feature.answer, feature.anchor)
        for feature in features
        if feature.anchor is not None
    )


def _pin_text(pin: _Pin) -> str:
    """One pin spelled as its `--feature` value, for quoting it in a refusal."""
    answer, anchor = pin
    return (
        f"{answer}{ANCHOR_MARK}{anchor.row}{_ANCHOR_SEPARATOR}"
        f"{anchor.col}{_ANCHOR_SEPARATOR}{anchor.direction}"
    )


def _pinned_letters(pin: _Pin) -> tuple[tuple[tuple[int, int], str], ...]:
    """Each cell a pin occupies, with its letter.

    Through `cw_grid.Run`, this project's one definition of which way ACROSS
    and DOWN advance, rather than a step table of its own.
    """
    answer, anchor = pin
    run = cw_grid.Run(
        row=anchor.row, col=anchor.col, direction=anchor.direction, text=answer
    )
    return tuple(zip(run.cells, answer, strict=True))


def _caps(pin: _Pin) -> tuple[tuple[int, int], tuple[int, int]]:
    """The cell just before a pin's first letter, and just after its last.

    The step is the second cell of a two-cell run laid at the origin, the
    idiom `cw_place` derives its own step table by, so `cw_grid.Run` stays the
    one definition of which way ACROSS and DOWN advance.
    """
    answer, anchor = pin
    d_row, d_col = cw_grid.Run(
        row=0, col=0, direction=anchor.direction, text="AA"
    ).cells[1]
    last_row, last_col = _pinned_letters(pin)[-1][0]
    return (
        (anchor.row - d_row, anchor.col - d_col),
        (last_row + d_row, last_col + d_col),
    )


def validate_distinct(answers: tuple[str, ...]) -> None:
    """Raise ConfigError if one answer is featured twice, bare or pinned.

    The distinct-run rule allows each answer one entry, so no grid could honor
    both. Takes answers rather than `Feature`s so `preview`, whose values are
    never parsed into one, refuses a repeat in the same words. Membership
    only: `seen` is never iterated.
    """
    seen: set[str] = set()
    for answer in answers:
        if answer in seen:
            raise cw_config.ConfigError(
                f"--feature names {cw_text.shown(answer)} twice; a grid holds "
                "each answer once"
            )
        seen.add(answer)


def _validate_in_bounds(pins: tuple[_Pin, ...], rows: int, cols: int) -> None:
    """Raise ConfigError if any pinned cell lies outside a `rows` x `cols` grid."""
    for pin in pins:
        for (row, col), _ in _pinned_letters(pin):
            if not (0 <= row < rows and 0 <= col < cols):
                raise cw_config.ConfigError(
                    f"--feature {_pin_text(pin)} runs off a {rows}x{cols} grid"
                )


def _validate_clear_of_mask(
    pins: tuple[_Pin, ...], masked: AbstractSet[tuple[int, int]]
) -> None:
    """Raise ConfigError if any pinned cell is one a `--mask` forbids a letter.

    A pin and a picture that contradict each other are two operator claims, and
    neither may quietly win: without this check the pin does, because
    `cw_board.pinned_board` writes it through `cw_place.apply_placement`, which
    is given a grid and no mask. Refused here, before any board is built.

    An island in a masked cell is not refused, only ineligible
    (`cw_island.fill_islands`). The difference is authorship: a pin is what the
    operator wrote, and a grid missing it is not the grid they asked for, while
    an island is a choice the tool makes for itself and can simply decline.

    Runs after the bounds check, so a pin both off the grid and over a masked
    cell is named for the grid: a picture cannot describe a cell the grid does
    not have, so reporting the mask there would point at the wrong file.
    """
    for pin in pins:
        for cell, _ in _pinned_letters(pin):
            if cell in masked:
                raise cw_config.ConfigError(
                    f"--feature {_pin_text(pin)} pins a letter into cell "
                    f"{cell[0]},{cell[1]}, which --mask forbids a letter"
                )


def _validate_agreement(pins: tuple[_Pin, ...]) -> None:
    """Raise ConfigError if two pins put different letters in one cell.

    `claimed` is looked up by cell and never iterated, so the pin named first
    in the message is always the one given first on the command line.
    """
    claimed: dict[tuple[int, int], tuple[str, _Pin]] = {}
    for pin in pins:
        for cell, letter in _pinned_letters(pin):
            held_letter, held_pin = claimed.setdefault(cell, (letter, pin))
            if held_letter != letter:
                raise cw_config.ConfigError(
                    f"--feature {_pin_text(held_pin)} and --feature "
                    f"{_pin_text(pin)} disagree at ({cell[0]}, {cell[1]}): "
                    f"{cw_text.shown(held_letter)} against {cw_text.shown(letter)}"
                )


def _validate_apart(pins: tuple[_Pin, ...]) -> None:
    """Raise ConfigError if a pin runs into another pinned cell along its line.

    A pin is an entry only while its run is maximal. A pinned cell just before
    its first letter or just after its last joins the line into one longer
    run, and the pin spells part of something else: `AB` inside `ABC`, or
    `CHALK` running into a `CRANE` pinned down from the next cell. With only
    pins on the board that is the whole condition, so no board is built to
    decide it. The map below is looked up by cell and never iterated, and names
    the first pin given to hold each cell.
    """
    pin_at: dict[tuple[int, int], _Pin] = {}
    for pin in pins:
        for cell, _ in _pinned_letters(pin):
            pin_at.setdefault(cell, pin)
    for pin in pins:
        for cap in _caps(pin):
            if cap in pin_at:
                raise cw_config.ConfigError(
                    f"--feature {_pin_text(pin)} runs into --feature "
                    f"{_pin_text(pin_at[cap])} at ({cap[0]}, {cap[1]}): along one "
                    "line they read as one longer run, so "
                    f"{cw_text.shown(pin[0])} would not be an entry"
                )


def _validate_start_agreement(pins: tuple[_Pin, ...], start: tuple[str, ...]) -> None:
    """Raise ConfigError if a pinned letter differs from the source letter under it.

    A source letter is fixed: `fill` only adds letters, so a pin that would
    overwrite one describes a grid the run can never reach. Indexing `start`
    by a pinned cell is safe because the bounds check has already run, against
    the canvas the CLI places the source on, which `start` always fills.
    """
    for pin in pins:
        for (row, col), letter in _pinned_letters(pin):
            held = start[row][col]
            if held not in (cw_grid.BLOCK, letter):
                raise cw_config.ConfigError(
                    f"--feature {_pin_text(pin)} disagrees with --source at "
                    f"({row}, {col}): {cw_text.shown(held)} against {cw_text.shown(letter)}"
                )


def _validate_not_held_elsewhere(
    pins: tuple[_Pin, ...], source_runs: tuple[cw_grid.Run, ...]
) -> None:
    """Raise ConfigError if a pin names an answer the source holds at another position.

    The distinct-run rule allows each answer one entry, and a source entry
    cannot be moved, so the pin could only ever be a second copy. A pin lying
    exactly on the source's own entry is the same run, not a copy, and passes.
    """
    for pin in pins:
        answer, anchor = pin
        mine = cw_grid.Run(
            row=anchor.row, col=anchor.col, direction=anchor.direction, text=answer
        )
        for run in source_runs:
            if run.text == answer and run != mine:
                raise cw_config.ConfigError(
                    f"--feature {_pin_text(pin)} names an answer --source already "
                    f"holds at ({run.row}, {run.col}) {run.direction}; a grid holds "
                    "each answer once"
                )


def _pin_run(pin: _Pin) -> cw_grid.Run:
    """One pin as the run it must stay: its answer, from its anchor."""
    answer, anchor = pin
    return cw_grid.Run(
        row=anchor.row, col=anchor.col, direction=anchor.direction, text=answer
    )


def _combined_runs(
    pins: tuple[_Pin, ...], start: tuple[str, ...]
) -> tuple[cw_grid.Run, ...]:
    """Every maximal run of the `--source` board with each pin written over it.

    Unlike `_validate_apart`, this builds the board: a source letter can extend
    a pin, and a pin can extend a source run along its own line or, by landing
    next to its end, across it. Reading the runs back off the board catches all
    three at once, and both source-run checks read this one board.
    """
    cells = [list(row) for row in start]
    for pin in pins:
        for (row, col), letter in _pinned_letters(pin):
            cells[row][col] = letter
    return cw_grid.runs_from_rows(["".join(line) for line in cells])


def _validate_pins_exact_on_start(
    pins: tuple[_Pin, ...], start: tuple[str, ...]
) -> None:
    """Raise ConfigError unless every pin is an exact run of the combined board.

    The pins' half only, which needs no bank: a pin is an entry whatever the
    source's runs turn out to be. Walks pins in flag order, so the pin named
    is always the first one given.
    """
    runs = _combined_runs(pins, start)
    for pin in pins:
        if _pin_run(pin) not in runs:
            raise cw_config.ConfigError(
                f"--feature {_pin_text(pin)} runs into a --source letter, so "
                f"{cw_text.shown(pin[0])} would not be an entry"
            )


def validate_source_runs(
    config: cw_config.FillConfig,
    partial: tuple[cw_grid.Run, ...],
    growable: tuple[cw_grid.Run, ...] = (),
) -> None:
    """Raise ConfigError if the pins lengthen a `--source` run they may not.

    `partial` is the source's partial runs as `cw_source.start_from` returns
    them, which is why this runs after it rather than in `validate_features`:
    whether a run is an entry or a partial run is the screened bank's and the
    source's clues' to say. An entry must stay its exact run, so a pin that
    lengthens one is refused, naming the entry rather than the pin. A partial
    run is no entry, and a pin lying along all of it (`cw_reach.covers`, the
    test the walk's rank and the report share) names the answer completing it.
    Any other lengthening (a pin landing just past its end, across its line)
    is refused: the longer run is one no pin holds. Source runs are walked
    in scan order, so the fault named is the first.

    `growable` is the entries `--absorb-entries` lets grow
    (`cw_board.growable_runs`), empty without the flag. Each is treated as a
    partial run is: a pin lying along all of it chooses its growth, and any
    other lengthening is refused.

    Run it after `validate_features`, which settled that every pin is in
    bounds, agrees with the source letters and is its own exact run.
    """
    if not config.start:
        return
    pins = _pins(config.features)
    runs = _combined_runs(pins, config.start)
    for run in cw_grid.runs_from_rows(config.start):
        if run in runs:
            continue
        where = f"{cw_text.shown(run.text)} at ({run.row}, {run.col}) {run.direction}"
        if run not in partial and run not in growable:
            raise cw_config.ConfigError(
                f"the --feature pins extend the --source entry {where}, so it "
                "would not be an entry"
            )
        if not any(cw_reach.covers(run, _pin_run(pin).cells) for pin in pins):
            kind, verb = (
                ("partial run", "completes a partial run")
                if run in partial
                else ("entry", "grows an entry")
            )
            raise cw_config.ConfigError(
                f"the --feature pins lengthen the --source {kind} {where}, but no "
                f"pin lies along all of it; a pin {verb} only by covering it"
            )


def validate_features(config: cw_config.FillConfig) -> None:
    """Raise ConfigError unless every `--feature` can hold at once on this grid.

    Every fault here is decided before the bank is screened, which is what
    puts it on the exit-2 line first. Some need only the flags and the grid
    size: an answer featured twice, a pin off the grid, a pin into a cell a
    `--mask` forbids a letter, two pins disagreeing
    on a cell, and a pin running into another. The rest need the `--source`
    grid, and run only when one was given: a pin disagreeing with a source
    letter, a pin naming an answer the source holds at another position, and
    a pin that is no longer its exact run once laid on the source. Two
    questions need more. Whether a pin may lengthen a source run turns on
    which runs are partial, so that is `validate_source_runs`, still at exit
    2. Whether the pinned board obeys the one rule needs the bank (two pins
    in adjacent lines are legal exactly when every pair they create is an
    answer), so that is `cw_accept.preflight`'s question, at exit 1.

    The source checks run last, in that order, so each can lean on what the
    earlier ones settled: pins in bounds, distinct, agreeing with each other
    and apart. Agreement comes before the exact-run check so a pin that
    changes a letter is named for the letter, not for the longer run the
    changed letter happens to make.

    Run it after `cw_config.validate_fill_config`, as the CLI does: the bounds
    check trusts that the grid's dimensions are already known to be positive,
    and on a zero-row grid it would report every pin as running off the edge
    rather than naming `--rows`.
    """
    validate_distinct(tuple(feature.answer for feature in config.features))
    pins = _pins(config.features)
    _validate_in_bounds(pins, config.rows, config.cols)
    _validate_clear_of_mask(pins, config.masked)
    _validate_agreement(pins)
    _validate_apart(pins)
    if config.start:
        source_runs = cw_grid.runs_from_rows(config.start)
        _validate_start_agreement(pins, config.start)
        _validate_not_held_elsewhere(pins, source_runs)
        _validate_pins_exact_on_start(pins, config.start)
