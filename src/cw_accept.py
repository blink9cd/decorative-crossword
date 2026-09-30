"""cw_accept: the constraints a conforming grid must meet.

They are: blocked percentage inside the requested window, at least
`--min-themes` themes each carrying at least `--min-entries-per-theme`
entries, and every featured answer present. The search
needs each of them in two forms:

- `preflight` judges them against the BANK, before a single node is searched.
  A request no amount of searching could satisfy is refused immediately
  rather than after thirty seconds of proving it.
- `missed_constraints` judges them against a GRID, at every node, and names
  each one the grid currently fails.

Under `--source` the grid form alone gains one more: a stray lone letter, which
only a source can bring, so no bank-side form of it exists.

Given `--max-two-letter`, the grid form gains another: no more two-letter entries
than the cap. It has no bank-side form either -- whether a bank can make a grid
under a COUNT of short entries is a question only the search itself answers.

Both forms live here rather than beside the walk so that the constraints
are stated once. Splitting them across modules by *when* they run would put the
theme floor in two places, free to drift the first time either changes.

Nothing here may take an ordering from a `set` or a dict built out of one
(the search's node order must be a pure function of its inputs). Every set
below is a membership test, never iterated, and every returned tuple's
order comes from a list built beside it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import cw_bank
import cw_board
import cw_config
import cw_density
import cw_grid
import cw_island
import cw_place
import cw_reach
import cw_text


def longest_line(config: cw_config.FillConfig) -> int:
    """The longest answer the grid could hold in either direction.

    PUBLIC because the report (`cw_report`) has to annotate an unplaced answer
    as "too long for a RxC grid" using the SAME rule this module refuses a
    featured answer by. Two copies of "how long a grid can hold" would let the
    pre-flight refusal and the report's annotation disagree about the same
    answer -- the operator would be told two different things about one word.
    """
    return max(config.rows, config.cols)


def _theme_reach_reason(bank: cw_bank.Bank, config: cw_config.FillConfig) -> str | None:
    """Why the bank cannot reach the theme floor, or None if it can.

    Depth as well as count: three themes carrying three answers each cannot
    meet a floor of four entries per theme, however many themes are declared.
    """
    counts: dict[str, int] = {}
    for entry in bank.entries:
        if entry.theme is not None:
            counts[entry.theme] = counts.get(entry.theme, 0) + 1
    deep_enough = sum(
        1 for count in counts.values() if count >= config.min_entries_per_theme
    )
    if deep_enough >= config.min_themes:
        return None
    return (
        f"the bank has {deep_enough} theme(s) carrying at least "
        f"{config.min_entries_per_theme} answer(s), short of the "
        f"{config.min_themes} that --min-themes asks for"
    )


def feature_missing_from_bank(
    bank: cw_bank.Bank, config: cw_config.FillConfig
) -> str | None:
    """Why a `--feature` names something the bank does not contain, or None.

    PUBLIC, and deliberately so, because this one failure belongs on the
    **exit-2** line -- with the other configuration errors -- while every other
    reason `preflight` returns is exit 1. The CLI calls this directly to make
    that decision, so there is one implementation of the
    check and no string-matching on reason text. `preflight` calls it too, so
    a caller reaching the search without the CLI still gets a refusal.

    Every absent answer, in the order given, in one reason: told only the
    first, an operator fixes it and is refused again for the second.

    Membership only -- the set below is never iterated, so its hash-seeded
    order cannot reach the returned reason.
    """
    held = {entry.answer for entry in bank.entries}
    return (
        "; ".join(
            f"the featured answer {cw_text.shown(feature.answer)} is not in the bank"
            for feature in config.features
            if feature.answer not in held
        )
        or None
    )


def _feature_length_reason(
    _bank: cw_bank.Bank, config: cw_config.FillConfig
) -> str | None:
    """Why a bare featured answer is too long for the grid, or None.

    Bare features only. A pinned one's fit is a question about its CELLS, which
    `cw_feature.validate_features` has already answered at exit 2, naming the
    pin as `ANSWER@ROW,COL,DIR` -- a second, vaguer sentence here would only
    restate it.
    """
    longest = longest_line(config)
    return (
        "; ".join(
            f"the featured answer {cw_text.shown(feature.answer)} is "
            f"{len(feature.answer)} letters, longer than any line of a "
            f"{config.rows}x{config.cols} grid"
            for feature in config.features
            if feature.anchor is None and len(feature.answer) > longest
        )
        or None
    )


def _pinned_board_reason(
    bank: cw_bank.Bank, config: cw_config.FillConfig
) -> str | None:
    """Why the pinned board already breaks the one rule, or None.

    Two pins in adjacent parallel lines create a pair at every cell between
    them, and each pair must itself be a distinct bank answer. When one is not,
    no search could repair the board it would start from, so this is refused
    before a single node rather than returned as a search that found nothing.
    It needs the bank, which is why it is here at exit 1 rather than beside the
    flag-only pin checks in `cw_config`.

    One break is excused: a `--source` partial run (`cw_reach.partial_runs`)
    still standing on the pinned board, that an answer not yet on it could
    still be laid over. The fill exists to finish that run. A pin that uses up
    every answer that could is what leaves one unexcused, and it is named here.

    The rule is judged by `cw_place.rule_breaks`, the one place it lives, and
    each break is worded by `cw_place.describe_break`, so each sentence names
    the offending run the same way a search would.

    It stands aside when a featured answer is missing from the bank: that is
    `feature_missing_from_bank`'s reason to give, and a pinned answer no bank
    could hold may not even be letters a board can be built from.
    """
    if feature_missing_from_bank(bank, config) is not None:
        return None
    rows = cw_board.pinned_board(config).to_rows()
    allowed = frozenset(entry.answer for entry in bank.entries)
    partial = cw_reach.partial_runs(config.start, allowed)
    unused = cw_reach.unused_answers(rows, bank)
    unexcused = [
        cw_place.describe_break(run, problem)
        for run, problem in cw_place.rule_breaks(rows, allowed)
        if run not in partial or not cw_reach.completable(rows, run, unused)
    ]
    if not unexcused:
        return None
    return "the pinned features already break the one rule: " + "; ".join(unexcused)


def _start_density_reason(
    bank: cw_bank.Bank, config: cw_config.FillConfig
) -> str | None:
    """Why a --source board is already too dense for the window, or None.

    Letters are only ever added, so blocked cells only fall. A start board
    under --min-blocked can never rise back into the window. Only under
    --source; a pins-only run is not refused here. Its two figures come from
    `cw_density.window_figures`, so a board that one decimal would print as
    standing on the floor reads as under it.
    """
    if not config.start or feature_missing_from_bank(bank, config) is not None:
        return None
    rows = cw_board.pinned_board(config).to_rows()
    if cw_density.window_miss(rows, config) >= 0:
        return None
    figures = cw_density.window_figures(rows, config)
    return (
        f"{_measured_board_name(config)} is already {figures.share}% blocked, under "
        f"the requested {figures.floor}% floor, and fill only adds letters"
    )


def _measured_board_name(config: cw_config.FillConfig) -> str:
    """The board a start's blocked percent is taken over, named for its refusal.

    `config.start` is the source as placed on the grid, so on a grown grid the
    percent counts the grown cells, which start blocked. Calling that figure the
    source's own would misstate the operator's grid, so a grown grid is named
    with the source's own size beside it, as the report's grown line names both.
    """
    source_rows, source_cols = config.source_size
    if (source_rows, source_cols) == (config.rows, config.cols):
        return "the --source grid"
    return (
        f"this {config.rows}x{config.cols} grid, with its {source_rows}x{source_cols} "
        "--source grid placed at the top-left,"
    )


def _empty_bank_reason(bank: cw_bank.Bank, _config: cw_config.FillConfig) -> str | None:
    """Why there is nothing left to place, or None.

    `cw_bank.parse_bank` refuses an empty `entries` list at exit 2, so this is
    unreachable from a file -- but `screen_excluded` can empty a bank that
    parsed fine, and it is documented never to fail the run. Without this
    check that state reaches the operator as `_no_answer_fits_reason`'s
    sentence, which is vacuously true over no answers and points them at the
    grid size when the cause is their term list.

    The sentence stays NEUTRAL about the cause: the pre-flight checks see the
    screened bank and not the screen, and the report's own "Dropped by
    --excluded-terms" block is where the count and the names honestly live.
    """
    if bank.entries:
        return None
    return "the bank holds no answers"


def _no_answer_fits_reason(
    bank: cw_bank.Bank, config: cw_config.FillConfig
) -> str | None:
    """Why no answer in the bank could be placed at all, or None.

    An EMPTY bank is not this reason and must not be reported as one: `any`
    over no entries is vacuously false, so the sentence below would assert that
    every one of zero answers is longer than the grid. `_empty_bank_reason`
    above states that case, and this one declines it.
    """
    if not bank.entries:
        return None
    longest = longest_line(config)
    if any(len(entry.answer) <= longest for entry in bank.entries):
        return None
    return (
        f"no bank answer is short enough for a {config.rows}x{config.cols} grid: "
        f"every one is longer than {longest} letters"
    )


#: The pre-flight checks, in report order. A tuple rather than a set so the
#: reasons come back in the same order every run.
_PREFLIGHT_CHECKS: tuple[
    Callable[[cw_bank.Bank, cw_config.FillConfig], str | None], ...
] = (
    _theme_reach_reason,
    feature_missing_from_bank,
    _feature_length_reason,
    _pinned_board_reason,
    _start_density_reason,
    _empty_bank_reason,
    _no_answer_fits_reason,
)


def preflight(bank: cw_bank.Bank, config: cw_config.FillConfig) -> tuple[str, ...]:
    """Every reason this request cannot be met, before a single node is searched.

    Empty means proceed. A refusal here is still exit 1, not 2: the request is
    well-formed, it just cannot be met by this bank at this size.

    EVERY reason, not the first: an operator told one of two faults would fix
    it, re-run, and be told the second. The checks are therefore independent
    predicates rather than a chain.

    Every check but two assumes nothing about the config's validity. The
    pinned-board and start-density checks both build `cw_board.pinned_board`,
    so they require `cw_config.validate_fill_config` and
    `cw_feature.validate_features` to have passed, for the reason
    `cw_board.pinned_board` gives.

    One caveat for the CLI: a featured answer that is not in the bank belongs
    on the exit-2 line, with the other configuration errors, because it is a
    flag naming something that does not exist rather than a hard search. Do NOT
    map every reason here to exit 1 -- call `feature_missing_from_bank` for
    that decision, which is the same function this one calls, so the two cannot
    disagree.
    """
    return tuple(
        reason
        for check in _PREFLIGHT_CHECKS
        if (reason := check(bank, config)) is not None
    )


def density_distance(rows: Sequence[str], config: cw_config.FillConfig) -> float:
    """How far outside the requested blocked-percentage window `rows` sits.

    Zero inside the window, so it serves as both the acceptance test for
    density and the axis along which the search ranks a near miss. Judged
    exactly by `cw_density.window_miss`, then read as a float by both of them:
    the rank, and `missed_constraints`'s test for a miss. Neither loses the
    verdict, because a nonzero miss stays nonzero as a float.
    """
    return float(abs(cw_density.window_miss(rows, config)))


def theme_counts(rows: Sequence[str], bank: cw_bank.Bank) -> dict[str, int]:
    """Entries per theme, counted from the grid's own runs.

    From the runs rather than from what the search placed, because a placement
    can create more than one entry at once: an answer the grid gained for free
    counts toward its theme exactly like a deliberate one.
    """
    index = bank.by_answer()
    counts: dict[str, int] = {}
    for run in cw_grid.runs_from_rows(rows):
        entry = index.get(run.text)
        if entry is not None and entry.theme is not None:
            counts[entry.theme] = counts.get(entry.theme, 0) + 1
    return counts


def themes_meeting_floor(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> int:
    """How many themes currently carry at least `min_entries_per_theme` entries."""
    return sum(
        1
        for count in theme_counts(rows, bank).values()
        if count >= config.min_entries_per_theme
    )


def theme_floor_status(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> tuple[int, bool]:
    """How many themes reach the per-theme floor, and whether that meets the floor.

    The two halves come back together because they come from ONE walk of
    `theme_counts`: the verdict is derived from the very count its callers go
    on to print, so asking for both at once costs exactly what asking for the
    verdict alone did. Every caller that needs both -- `missed_constraints`
    below, `cw_report`'s theme block and `cw_report_remedy`'s knob lines --
    reads them here.

    PUBLIC for the same reason `longest_line` is, and with a sharper failure
    mode: the report prints a "floor met" / "floor NOT met" verdict directly
    above the missed-constraint list this module produces. A second copy of the
    comparison would let the two disagree IN THE SAME OUTPUT -- "floor met"
    standing over an echoed "0 of 1 themes reach the 1-entry floor" -- which is
    worse than either sentence being wrong alone. So the comparison exists
    here, once, and nowhere else in the project.
    """
    met = themes_meeting_floor(rows, bank, config)
    return met, met >= config.min_themes


def theme_floor_met(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> bool:
    """Whether enough themes reach the per-theme entry floor.

    The verdict-only spelling of `theme_floor_status`'s single walk, so a
    caller wanting the boolean alone reaches for this instead of writing the
    `>= config.min_themes` comparison itself -- which would be the second
    statement of the rule `theme_floor_status` exists to prevent.
    """
    return theme_floor_status(rows, bank, config)[1]


def missed_constraints(
    rows: Sequence[str], bank: cw_bank.Bank, config: cw_config.FillConfig
) -> tuple[str, ...]:
    """Every acceptance rule `rows` currently fails; empty means conforming.

    Acceptance and its diagnosis are one function on purpose, because a
    failure must NAME the missed constraint: a separate predicate
    would be a second statement of the same rules, free to drift from the
    sentences the operator is shown.

    Features are looked for in the grid rather than in the search's placement
    history, because the grid is what the operator gets -- an answer that
    arrived as a free crossing is just as present as one deliberately placed.
    A pinned feature counts only as its own exact run (`cw_board.pinned_runs`). The same
    answer somewhere else is not the pin, and a pin extended into a longer
    answer is no entry at all, though every one of its cells is still there.

    A stray lone letter is judged only under --source. During a walk nothing
    else can leave one: every placed answer is at least two cells, so a lone
    letter on the board is always one the source brought.
    """
    missed: list[str] = []
    if density_distance(rows, config) > 0:
        # `window_figures`, not three `.1f`s: one decimal can round a miss onto
        # the bound it misses, and this sentence exists to say it missed.
        figures = cw_density.window_figures(rows, config)
        missed.append(
            f"blocked {figures.share}% is outside the requested "
            f"{figures.floor}-{figures.ceiling}% window"
        )
    # One call, not two: the verdict and the count come out of the same walk of
    # `theme_counts` (which rebuilds `bank.by_answer()` each time), and this
    # function runs at every search node -- see the module docstring.
    #
    # Computing the count separately, only on a miss, would add a second walk
    # at most checks, because most checks miss: on samples/large_square's
    # committed command, 2,261 of the 2,378 floor checks miss the floor, and one
    # walk per check took that run's `theme_counts` walks from 7,018 to 4,756.
    # Re-measure before splitting it.
    met, floor_met = theme_floor_status(rows, bank, config)
    if not floor_met:
        missed.append(
            f"{met} of {config.min_themes} themes reach the "
            f"{config.min_entries_per_theme}-entry floor"
        )
    over = two_letter_overrun(rows, config)
    if over:
        missed.append(
            f"{over} two-letter entries, over the requested cap of "
            f"{config.max_two_letter}"
        )
    if config.features:
        missed.extend(_missed_features(rows, config))
    if config.start:
        missed.extend(_missed_strays(rows))
    return tuple(missed)


#: The entry length `--max-two-letter` counts, named so the comparison reads as
#: "two-letter" rather than as a bare 2.
_TWO_LETTERS = 2


def two_letter_overrun(rows: Sequence[str], config: cw_config.FillConfig) -> int:
    """How many two-letter entries `rows` carries when that is over the cap; 0 otherwise.

    The count is returned only on a miss, so one value answers both questions a
    caller asks -- is the cap missed, and by how much -- and the comparison lives
    here once: `missed_constraints` and `cw_report_remedy` both read it rather
    than each spelling `count > cap`. A miss is never 0, since a cap is at least 0.

    No cap walks nothing: acceptance runs at every search node.
    """
    cap = config.max_two_letter
    if cap is None:
        return 0
    count = sum(
        1 for run in cw_grid.runs_from_rows(rows) if len(run.text) == _TWO_LETTERS
    )
    return count if count > cap else 0


def _missed_strays(rows: Sequence[str]) -> list[str]:
    """One sentence per lone letter of `rows` that is no island, row-major."""
    return [
        f"the fixed letter {letter} at ({row}, {col}) belongs to no entry"
        for row, col, letter, _ in cw_island.stray_letters(rows)
    ]


def _missed_features(rows: Sequence[str], config: cw_config.FillConfig) -> list[str]:
    """Each feature `rows` fails to hold, as a sentence, in flag order.

    One walk of the runs for every feature; the caller skips it entirely for a
    run with no feature, because acceptance runs at every search node. A bare
    feature is present as a run anywhere; a pinned one only as its exact run.
    """
    runs = cw_grid.runs_from_rows(rows)
    texts = [run.text for run in runs]
    pinned = iter(cw_board.pinned_runs(config))
    missed: list[str] = []
    for feature in config.features:
        if feature.anchor is None:
            if feature.answer not in texts:
                missed.append(
                    f"the featured answer {cw_text.shown(feature.answer)} "
                    "is not in the grid"
                )
        elif (run := next(pinned)) not in runs:
            missed.append(
                f"the pinned answer {cw_text.shown(feature.answer)} is not an entry at "
                f"({run.row}, {run.col}) {run.direction}"
            )
    return missed
