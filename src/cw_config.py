"""cw_config: the typed subcommand configurations and their pure-value validation.

`DEFAULTS` is the single source of every non-None default a value-taking
option has, whichever subcommand takes it. The argument parser passes
`default=DEFAULTS["min_blocked"]` rather than repeating a literal, and `--help`
renders the live `default=`, so a default lives here exactly once.

`validate_fill_config` is a list of independent guard clauses, not a single
merged predicate: each rejection must name the CLI option at fault, because a
generic "bad configuration" would undo the discoverability the rest of the CLI
builds. Every clause here is load-bearing (a test fails if any one of them
is deleted) so a clause that would only ever be redundant with another one
already present is deliberately left out; `_validate_blocked_bounds` works
through the case and says what the omission costs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

import cw_grid
import cw_mask
import cw_symmetry
import cw_text

if TYPE_CHECKING:
    # For the `FillConfig.features` annotation only. `cw_feature` imports this
    # module at runtime, for ConfigError, so a runtime import back would be a
    # cycle.
    import cw_feature

#: Every optional's default, in one place. The parser reads these rather than
#: repeating literals, so --help cannot disagree with what the tool actually
#: does. Wrapped in MappingProxyType so the "single source"
#: claim is real: a plain dict is still mutable through any reference an
#: importer holds, which would let one module's accidental write corrupt every
#: other reader's defaults (the same class of bug guarded against for
#: `Bank.themes` in cw_bank.py).
DEFAULTS: Mapping[str, object] = MappingProxyType(
    {
        "min_blocked": 30.0,
        "max_blocked": 45.0,
        "min_themes": 3,
        "min_entries_per_theme": 3,
        "time_budget": 30.0,
        "max_steps": 0,
        # How many nodes `fill` keeps searching past its first conforming grid
        # for a better one, as `cw_select.grid_score` ranks grids. The order
        # is stated there, once. A node count rather than a clock, so the grid chosen
        # depends on the request alone. Sized by measurement: the case that
        # motivated it found its better grid 13 nodes after the first, and at
        # the tens of milliseconds a node a 1,300-answer bank costs this is about
        # twenty seconds, on the samples a fraction of one. 0 keeps the first.
        "look_ahead": 500,
        "cell": 48,
        # `shade`'s two list knobs. The length floor is 5 because a hidden
        # word is a bonus answer and a three-letter one is not much of a
        # bonus, and because candidacy is a weak filter, so without a floor
        # the list is dominated by short words: on a real 9x9 the candidate
        # count falls from 224 to 63 at five letters, and the long words worth
        # choosing become visible. The list cap keeps a default run readable;
        # 0 means show every candidate, matching `--max-steps`'s own reading
        # of zero as "no limit".
        "min_length": 5,
        "top": 25,
    }
)

#: Forbidden in any operator text this tool emits: it would break the
#: consumer's inline data block. Looked for in the case-folded text, because an
#: HTML parser matches an end tag's name without regard to ASCII case, so
#: `</SCRIPT>` ends the block too. Folding also catches a long s and a t with
#: dieresis, which lowering would leave alone; a parser would not end the
#: block on either, and refusing them is the safe side.
_SCRIPT_CLOSE_TAG = "</script"

#: The blocked-cell percentage scale's ceiling. Named so the comparison and
#: the message it produces cannot drift apart: changing the bound in one
#: spot changes what the operator is told in the other.
_MAX_BLOCKED_PERCENT = 100

#: The largest `--cell` edge, in SVG user units. Far above any drawing's need
#: (the largest grid `cw_grid.MAX_SIDE` allows is an ordinary document at
#: this edge), and it keeps the edge inside the float arithmetic that lays a
#: drawing out.
MAX_CELL = 1000


class ConfigError(ValueError):
    """Raised when a run's settings are internally contradictory or out of range.

    Shared by `FillConfig` and `ShadeConfig`, and by the standalone `--cell`
    check `preview` and `shade` both make: one exception type, because every
    such refusal lands on the same exit-2 line and a second type would only
    give the CLI a second thing to catch.
    """


def forbidden_clue_fragment(text: str) -> str | None:
    """Name the first fragment of `text` that no output of this tool may carry.

    Returns None when `text` is safe to emit. The screen lives here once and is
    applied by every writer of operator text: `cw_bank` at the parse boundary,
    `cw_emit` on every clue, theme key, theme label and theme summary it
    actually writes, and `cw_grid_document` on each theme field it reads from a
    grid file. Two copies of a screen whose whole job is to keep markup,
    terminal controls and characters XML cannot hold out of every output is a
    hole rather than a duplication (widening one copy leaves the other passing
    the very text it was widened for) so the rule is public here instead. The
    characters a terminal or an SVG cannot take are `cw_text`'s to name; a
    newline is one of them, and keeps its own words.
    """
    if "\n" in text:
        return "a newline"
    character = cw_text.unsafe_character(text)
    if character is not None:
        return character
    if _SCRIPT_CLOSE_TAG in text.casefold():
        return f"the literal {cw_text.shown(_SCRIPT_CLOSE_TAG)}"
    return None


@dataclass(frozen=True)
class FillConfig:
    """A resolved `fill` run's settings: one field per CLI option.

    `seed` fixes the search's iteration order; it has no
    validation rule of its own because every integer is a legal seed.

    `features` holds every `--feature` in the order given. The order is not
    cosmetic: pins are applied in it, and the report and the caption list
    features in it, so a reader finds each where they wrote it. What makes a
    feature valid, alone and beside the others, is `cw_feature`'s question.

    `look_ahead`, `prefer` and `prefer_symmetry` choose among the conforming
    grids a search finds (`cw_select`); `prefer_symmetry` is a `cw_symmetry`
    kind, or None when no symmetry was asked for. `island_letters` is empty
    unless islands were asked for (`cw_island`), and is already parsed when it
    gets here.

    `start` holds the `--source` rows placed on the grid, or is empty when no
    source was given. It is trusted to match `rows` and `cols` rather than
    checked against them, because the CLI places the source onto exactly that
    grid (`cw_source.place_source`). `source_size` is the source's own
    `(rows, cols)`, which the placed rows can no longer tell (a blocked row the
    source ended on and one the grid added look alike) and `(0, 0)` without a
    source.

    `absorb_entries` is `--absorb-entries`: a source entry the bank holds may
    grow into a longer answer covering it (`cw_board.growable_runs`). It means
    nothing without `start`, which is why `validate_fill_config` refuses it there.

    `max_two_letter` is `--max-two-letter`: the most two-letter entries an
    accepted grid may carry. `None` is no cap, and zero is a real one (a caller
    whose consumer allows no two-letter entry at all must be able to say so), so
    nothing downstream may test it for truthiness.

    `masked` is the cells a `--mask` picture forbids a letter, for membership
    only; `cw_mask` says why a mask rides on the config rather than in the grid.
    `mask_size` is the picture's own size, `cw_mask.NO_MASK_SIZE` without one.
    The two are separate for the reason `start` and `source_size` are: a mask
    forbidding nothing is a legal picture, so the cells alone cannot say whether
    a mask was given, let alone how big it was.
    """

    rows: int
    cols: int
    seed: int
    min_blocked: float
    max_blocked: float
    min_themes: int
    min_entries_per_theme: int
    time_budget: float
    max_steps: int
    features: tuple[cw_feature.Feature, ...]
    look_ahead: int
    prefer: tuple[str, ...]
    island_letters: tuple[str, ...]
    start: tuple[str, ...] = ()
    source_size: tuple[int, int] = (0, 0)
    absorb_entries: bool = False
    max_two_letter: int | None = None
    prefer_symmetry: str | None = None
    masked: frozenset[tuple[int, int]] = frozenset()
    mask_size: tuple[int, int] = (0, 0)


def validate_size(rows: int, cols: int) -> None:
    """Raise ConfigError unless both grid dimensions are positive and at most the cap.

    The cap is `cw_grid.MAX_SIDE`, and a refusal names the flag: a `--source`
    grid or a `--mask` picture past it is refused where it is read, earlier, so
    a size past it that reaches here is one a flag asked for. Public so a size
    can be checked before anything is built at it.
    """
    for flag, size in (("--rows", rows), ("--cols", cols)):
        if size <= 0:
            raise ConfigError(f"{flag} must be positive, got {size}")
        if size > cw_grid.MAX_SIDE:
            raise ConfigError(f"{flag} must be at most {cw_grid.MAX_SIDE}, got {size}")


def _validate_blocked_bounds(config: FillConfig) -> None:
    """Raise ConfigError unless the blocked-cell range is sane.

    Only the lower bound of `--min-blocked`, the upper bound of
    `--max-blocked`, and their relative order are checked directly. A
    dedicated check for the other two combinations (`--min-blocked` over
    the ceiling, `--max-blocked` under 0) is not dead code (each is
    genuinely reachable: it would fire on plenty of inputs if it ran first),
    it is simply always redundant with one of the three above. Whenever
    `--min-blocked` exceeds the ceiling, either `--max-blocked` is below it
    too (order check fires) or `--max-blocked` is at or above `--min-blocked`
    and therefore also over the ceiling (upper-bound check fires); the
    symmetric argument holds for `--max-blocked` under 0. So omitting the two
    extra checks loses no coverage: the input is still rejected with a
    message naming a real flag. It just means a value that is wrong on both
    fields costs one extra fix-and-rerun cycle instead of being named in a
    single pass.
    """
    if config.min_blocked < 0:
        raise ConfigError(f"--min-blocked must be at least 0, got {config.min_blocked}")
    if config.max_blocked > _MAX_BLOCKED_PERCENT:
        raise ConfigError(
            f"--max-blocked must be at most {_MAX_BLOCKED_PERCENT}, got "
            f"{config.max_blocked}"
        )
    if config.min_blocked > config.max_blocked:
        raise ConfigError(
            f"--min-blocked ({config.min_blocked}) must not exceed "
            f"--max-blocked ({config.max_blocked})"
        )


def _validate_theme_floors(config: FillConfig) -> None:
    """Raise ConfigError unless the theme-coverage floors are in range.

    `--min-themes` admits zero, which turns the theme floor off. A bank may
    declare no themes at all, so every positive floor is one such a bank cannot
    reach: a positive-only rule here would make legal input guarantee a
    refusal. No downstream special
    case goes with it: a floor of zero is met by any count of themes, so every
    comparison against it already answers "met" and the constraint stops being
    a question rather than becoming one asked differently.

    `--min-entries-per-theme` keeps its positive rule: it is a depth per theme
    rather than a count of themes.
    """
    if config.min_themes < 0:
        raise ConfigError(f"--min-themes must not be negative, got {config.min_themes}")
    if config.min_entries_per_theme <= 0:
        raise ConfigError(
            "--min-entries-per-theme must be positive, got "
            f"{config.min_entries_per_theme}"
        )


def _validate_budgets(config: FillConfig) -> None:
    """Raise ConfigError unless the budgets are non-negative and one of them binds.

    Zero reads as "no limit" on both, which makes their combination the single
    request nothing can stop. It is refused here, before any searching, where
    the message can name both flags, rather than left to look like a hang.
    """
    if config.time_budget < 0:
        raise ConfigError(
            f"--time-budget must not be negative, got {config.time_budget}"
        )
    if config.max_steps < 0:
        raise ConfigError(f"--max-steps must not be negative, got {config.max_steps}")
    if not config.time_budget and not config.max_steps:
        raise ConfigError(
            "--time-budget 0 drops the wall clock, so --max-steps must supply a "
            "bound; both zero would search forever"
        )


def validate_cell(cell: int) -> None:
    """Raise ConfigError unless `cell` is a usable SVG cell edge.

    `preview`'s only numeric knob, and the only flag it has that can produce a
    file nothing can render: every length in the document is a multiple of the
    cell edge, so a zero or negative one would emit a negative `viewBox` and a
    negative `stroke-width`: a structurally invalid SVG. An edge past
    `MAX_CELL` is refused too: the parser reads a whole number of any size, and
    one a few hundred digits long overflows that float arithmetic, a traceback
    rather than a refusal.

    It is configuration validation: specific, at exit 2, each rejection naming
    the option at fault. It lives beside the `fill` validators rather than in
    the CLI for the same reason they do: `DEFAULTS["cell"]` is here, and a
    check that named a flag would drift from the default it guards if the two
    lived apart.
    """
    if cell <= 0:
        raise ConfigError(f"--cell must be positive, got {cell}")
    if cell > MAX_CELL:
        raise ConfigError(f"--cell must be at most {MAX_CELL}, got {cell}")


@dataclass(frozen=True)
class ShadeConfig:
    """A resolved `shade` run's settings: one field per CLI option.

    `word` is the answer `--word` names, already uppercased by the caller, or
    None in the ranked-search mode. Which of the two modes a run is in is
    decided by the flags the operator supplied rather than by a field here,
    because "exactly one of `--words` and `--word`" is a question about
    presence and this struct holds values.
    """

    min_length: int
    top: int
    exclude_grid_answers: bool
    word: str | None
    cell: int


def _validate_word(word: str | None) -> None:
    """Raise ConfigError unless `--word` names something a grid could hold.

    The same two rules a bank answer must satisfy (at least `cw_grid.MIN_RUN`
    letters, A-Z only) because a hidden word is read off a grid, and a grid
    holds nothing else. Checked here rather than left to come back as "this
    grid cannot spell it", which would be a true sentence pointing at the
    wrong thing: a `--word` of "cat-nap" is a mistake in the flag, not a fact
    about the grid.
    """
    if word is None:
        return
    if len(word) < cw_grid.MIN_RUN:
        raise ConfigError(
            f"--word must be at least {cw_grid.MIN_RUN} letters, got {cw_text.shown(word)}"
        )
    if not all("A" <= letter <= "Z" for letter in word):
        raise ConfigError(f"--word must be letters A-Z only, got {cw_text.shown(word)}")


def validate_shade_config(config: ShadeConfig) -> None:
    """Raise ConfigError on the first rule `config` violates; return None otherwise.

    Guard clauses naming the specific `--flag` at fault, for the reason
    `validate_fill_config` below gives.

    `--cell` is validated whatever mode the run is in, even though only a run
    that also gives `--out` draws anything. One rule rather than a
    mode-dependent one: a cell edge out of range is never what anyone meant,
    `preview` already refuses it unconditionally, and a check that fired in
    one mode and not the other would be a difference between two subcommands
    with no reason a reader could reconstruct.
    """
    if config.min_length < cw_grid.MIN_RUN:
        raise ConfigError(
            f"--min-length must be at least {cw_grid.MIN_RUN}, got {config.min_length}"
        )
    if config.top < 0:
        raise ConfigError(f"--top must not be negative, got {config.top}")
    _validate_word(config.word)
    validate_cell(config.cell)


@dataclass(frozen=True)
class GapsConfig:
    """A resolved `gaps` run's settings: one field per numeric or toggle option.

    `--bank`, `--words`, `--phrases` and `--out` are absent for the same reason
    `shade`'s mode flags are: they are questions about presence (was a
    vocabulary offered, was a render asked for) and this struct holds values. The
    handler reads the flags; the resolver and the report are told the result.

    `masked` is here for the opposite reason: a `--mask` picture's cells are a
    value, and every reader of them (the analysis, the headline, the density
    and the ceiling advice) already takes this struct. Membership only. Unlike
    `FillConfig` there is no `mask_size` beside it, because `gaps` is given its
    grid rather than asked to make one: the size agreement is a question about
    the `--source` file, so `cw_gaps_command` asks it where that file is read.
    """

    top: int
    include_absorbing: bool
    cell: int
    masked: frozenset[tuple[int, int]] = frozenset()


def validate_gaps_config(config: GapsConfig) -> None:
    """Raise ConfigError on the first rule `config` violates; return None otherwise.

    The same two rules `shade` applies to the same two knobs, deliberately
    rather than by coincidence: a reader who has learned what `--top 0` and an
    out-of-range `--cell` mean in one subcommand must not find them meaning
    something else in the other.
    """
    if config.top < 0:
        raise ConfigError(f"--top must not be negative, got {config.top}")
    validate_cell(config.cell)


def _validate_selection(config: FillConfig) -> None:
    """Raise ConfigError unless the look-ahead and the preferences can be honored.

    A repeated `--prefer` would count one answer twice when grids are compared,
    which is a preference nobody stated. Membership only: `seen` is never
    iterated, so the answer named is the first repeat in flag order.

    An unknown symmetry kind is refused at the command line by argparse's
    `choices=`; it is checked again here because a config built directly would
    otherwise reach the search and fail on a lookup there.
    """
    if config.look_ahead < 0:
        raise ConfigError(f"--look-ahead must not be negative, got {config.look_ahead}")
    seen: set[str] = set()
    for answer in config.prefer:
        if answer in seen:
            raise ConfigError(
                f"--prefer names {cw_text.shown(answer)} twice; each answer counts once"
            )
        seen.add(answer)
    kind = config.prefer_symmetry
    if kind is not None and kind not in cw_symmetry.KINDS:
        raise ConfigError(
            f"--prefer-symmetry names {cw_text.shown(kind)}; the kinds are "
            + ", ".join(cw_symmetry.KINDS)
        )


def _validate_two_letter_cap(config: FillConfig) -> None:
    """Raise ConfigError on a negative `--max-two-letter`; zero and no cap both pass.

    Zero is refused by nothing: it is the cap a consumer allowing no two-letter
    entry states, so the rule is non-negative, never positive.
    """
    cap = config.max_two_letter
    if cap is not None and cap < 0:
        raise ConfigError(f"--max-two-letter must not be negative, got {cap}")


def validate_fill_config(config: FillConfig) -> None:
    """Raise ConfigError on the first rule `config` violates; return None otherwise.

    Called before any search starts: a contradictory configuration is exit 2,
    not a search that predictably fails. Each helper below owns one related
    group of fields and names the specific `--flag` at fault, as every
    configuration rejection must.

    It says nothing about `--feature`: that flag's grammar, model and checks
    are one concern with a module of its own, and the CLI runs
    `cw_feature.validate_features` straight after this.
    """
    validate_size(config.rows, config.cols)
    _validate_blocked_bounds(config)
    _validate_theme_floors(config)
    _validate_budgets(config)
    _validate_selection(config)
    _validate_two_letter_cap(config)
    _validate_absorb(config)
    _validate_mask_size(config)
    _validate_masked_source_letters(config)


def _validate_absorb(config: FillConfig) -> None:
    """Raise ConfigError if `--absorb-entries` is given with no `--source` to grow.

    Refused rather than ignored: a flag that silently does nothing is how a
    command line comes to mean something other than what it says.
    """
    if config.absorb_entries and not config.start:
        raise ConfigError(
            "--absorb-entries needs --source: without a grid to start from there "
            "is no entry to grow"
        )


def _validate_mask_size(config: FillConfig) -> None:
    """Raise ConfigError unless a `--mask` picture is exactly the size of the grid.

    The rule and its sentence are `cw_mask.size_disagreement`'s. `gaps` asks the
    same question of its `--source` grid in `cw_gaps_command._require_mask_agrees`,
    and words its refusal there.
    """
    fault = cw_mask.size_disagreement(config.mask_size, (config.rows, config.cols))
    if fault is not None:
        raise ConfigError(fault)


def _validate_masked_source_letters(config: FillConfig) -> None:
    """Raise ConfigError if a `--source` letter sits where `--mask` forbids one.

    Runs after `_validate_mask_size`, so a mis-sized picture is named as that
    first: a cell of one names nothing the operator can find in either file.
    """
    fault = cw_mask.forbidden_letter(config.start, config.masked)
    if fault is not None:
        raise ConfigError(fault)
