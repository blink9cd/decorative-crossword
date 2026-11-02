"""Fixtures shared across suites, built around one baseline fill configuration.

Not named ``test_*.py`` on purpose: unittest discovery would otherwise collect
it as a suite of its own and the aggregator's per-file floor map would have to
carry a file holding no tests. It is a plain module the suites import.

It exists so the baseline configuration is written once. A second copy in a
second suite drifts, and a fixture that restates the values it is meant to test
passes while the subject is wrong about them.
"""

import dataclasses
from typing import TypedDict, Unpack

from collections.abc import Mapping

import cw_bank
import cw_config
import cw_feature
import cw_grid


class ConfigOverrides(TypedDict, total=False):
    """The fields `config()` accepts as overrides, each with its real type.

    Spelling them out is what lets mypy check an override against the field it
    replaces. A bare `**overrides: object` splatted into `dataclasses.replace`
    is rejected (rightly, since it would let `rows="9"` through), and the
    `# type: ignore` that silences it would take every other override's check
    down with it, so the cause is fixed instead.
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
    max_two_letter: int | None
    features: tuple[cw_feature.Feature, ...]
    look_ahead: int
    prefer: tuple[str, ...]
    island_letters: tuple[str, ...]
    start: tuple[str, ...]
    absorb_entries: bool
    masked: frozenset[tuple[int, int]]
    mask_size: tuple[int, int]


#: The baseline every `config()` call starts from.
BASE_CONFIG = cw_config.FillConfig(
    rows=9,
    cols=9,
    seed=7,
    min_blocked=0.0,
    max_blocked=95.0,
    min_themes=1,
    min_entries_per_theme=1,
    time_budget=30.0,
    max_steps=5000,
    features=(),
    # Zero: every suite built on this baseline pins the first conforming grid,
    # which is what they were written against. A suite about choosing among
    # grids asks for a look-ahead explicitly.
    look_ahead=0,
    prefer=(),
    island_letters=(),
)


def theme_records(labels: Mapping[str, str]) -> dict[str, cw_bank.ThemeInfo]:
    """Lift a plain `{key: label}` map into the `{key: ThemeInfo}` a Bank takes.

    A helper rather than a rewrite of every call site: what these fixtures are
    about is how many themes exist and which answers carry them, never what a
    theme's prose says. A theme needs a summary, so one is synthesized per key
    here and the callers name a theme by its label alone.
    """
    return {
        key: cw_bank.ThemeInfo(label=label, summary=f"Everything about {label}")
        for key, label in labels.items()
    }


def config(
    *, feature: str | None = None, **overrides: Unpack[ConfigOverrides]
) -> cw_config.FillConfig:
    """The baseline fill configuration, with any named field replaced.

    `feature` is the one-answer spelling nearly every case needs, and it is
    exactly what a single bare `--feature ANSWER` becomes: one position-less
    `Feature`. It stays a convenience rather than every call site building the
    tuple, so those cases read as what they are: the single-feature behavior,
    which a repeated `--feature` must leave unchanged.
    """
    built = dataclasses.replace(BASE_CONFIG, **overrides)
    if built.start:
        # `FillConfig` pairs a start with its source's own size, as the CLI
        # always does. Left at (0, 0) a start reads as a grid grown from nothing,
        # and these suites place no source, so the start is the source.
        source_size = (len(built.start), len(built.start[0]))
        built = dataclasses.replace(built, source_size=source_size)
    if feature is None:
        return built
    return dataclasses.replace(built, features=(cw_feature.Feature(feature, None),))


def wire_config(config: cw_config.FillConfig) -> dict[str, object]:
    """`config` as fields `json.dumps` accepts, with `masked` written as pairs.

    For a suite that hands a config to a child interpreter. `dataclasses.asdict`
    alone is not enough: `masked` is a frozenset, and JSON has no set. Sorted
    rather than in the set's own order, because such a harness exists to prove
    the search is reproducible across hash seeds: handing the child an order a
    frozenset chose would put the very thing under test into the input.

    Here beside `config` rather than in a suite that calls it: the two are one
    contract, and a second copy of this conversion would be a second chance to
    write the set out in its own order.
    """
    fields = dataclasses.asdict(config)
    fields["masked"] = sorted(config.masked)
    return fields


def pin(answer: str, row: int, col: int, direction: str) -> cw_feature.Feature:
    """A feature anchored at one cell: what `--feature ANSWER@ROW,COL,DIR` parses to.

    Shared by every suite that pins, so the one shape is built one way.
    """
    return cw_feature.Feature(answer, cw_feature.Anchor(row, col, direction))


def bank(answers: list[str], themes: dict[str, str] | None = None) -> cw_bank.Bank:
    """A bank of unthemed answers unless a theme map is supplied."""
    declared = themes or {}
    entries = tuple(
        cw_bank.BankEntry(answer=answer, theme=None, clue=None) for answer in answers
    )
    return cw_bank.Bank(themes=theme_records(declared), entries=entries)


def themed_bank() -> cw_bank.Bank:
    """Three themes carrying three answers each: the floor exactly met."""
    groups = {
        "a": ["ALPHA", "AMBER", "ANVIL"],
        "b": ["BRAVO", "BLADE", "BROOK"],
        "c": ["CEDAR", "CRANE", "CHALK"],
    }
    entries = tuple(
        cw_bank.BankEntry(answer=answer, theme=key, clue=None)
        for key, answers in groups.items()
        for answer in answers
    )
    return cw_bank.Bank(
        themes=theme_records({"a": "A", "b": "B", "c": "C"}), entries=entries
    )


def entries_bank(
    pairs: tuple[tuple[str, str | None], ...], themes: dict[str, str]
) -> cw_bank.Bank:
    """A bank from explicit (answer, theme) pairs and an explicit theme map.

    The shape the other helpers cannot express: several themes of differing
    depth, or themed and unthemed answers side by side in one bank.
    """
    return cw_bank.Bank(
        themes=theme_records(themes),
        entries=tuple(
            cw_bank.BankEntry(answer=answer, theme=theme, clue=None)
            for answer, theme in pairs
        ),
    )


def one_theme_bank(answers: list[str]) -> cw_bank.Bank:
    """Every answer under one declared theme: the smallest satisfiable request."""
    entries = tuple(
        cw_bank.BankEntry(answer=answer, theme="a", clue=None) for answer in answers
    )
    return cw_bank.Bank(themes=theme_records({"a": "A"}), entries=entries)


def still() -> float:
    """A clock frozen at zero: no test here may depend on real elapsed time."""
    return 0.0


def grid(rows: tuple[str, ...]) -> cw_grid.Grid:
    """A Grid pre-filled from row strings, for readable test setup."""
    built = cw_grid.Grid(len(rows), len(rows[0]))
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            if cell != cw_grid.BLOCK:
                built.set_letter(row_index, col_index, cell)
    return built


#: 10x10 boards standing exactly on a one-decimal bound that binary floating
#: point misses: 28 and 29 blocked cells of 100 are exactly 28% and 29%, which
#: `blocked / total * 100` computes as 28.000000000000004 and 28.999999999999996.
TWENTY_EIGHT_OF_100 = ("CATCATCATC",) * 7 + ("CA........",) + ("." * 10,) * 2
TWENTY_NINE_OF_100 = ("CATCATCATC",) * 7 + ("C.........",) + ("." * 10,) * 2

#: A 25x25 board with 182 of its 625 cells blocked: exactly 29.12%, which one
#: decimal prints as 29.1: the figure of a 29.1 ceiling it is over, or of a
#: 29.13 floor it is under.
ONE_HUNDRED_EIGHTY_TWO_OF_625 = (
    ("." * 25,) * 7 + ("." * 7 + "C" * 18,) + ("CATCATCATCATCATCATCATCATC",) * 17
)
