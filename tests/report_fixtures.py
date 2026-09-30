"""Fixtures and line-scoping helpers shared by the report and answer-pairs suites.

Defined once here rather than in any one suite, the arrangement
`search_fixtures` uses for the search suites: a fixture copied into a second
file drifts from the first the moment either is updated, and the
report's expectations are arithmetic on this exact bank.

The builders are `make_*` so that `make_outcome` can take `bank` and `config`
parameters without shadowing them.
"""

import re

import cw_accept
import cw_bank
import cw_config
import cw_feature
import cw_place
import cw_search

#: Matches one "(row, col)" pair in a rendered cell list.
_CELL_RE = re.compile(r"\((\d+), (\d+)\)")

#: The 3x3 board most tests report on. CAT runs ACROSS and COW runs DOWN from
#: the same corner, so ONE grid exercises both orientations -- the axis a
#: single-orientation fixture leaves unpinned.
DEFAULT_ROWS = ("CAT", "O..", "WET")


def make_bank() -> cw_bank.Bank:
    """Five answers over two declared themes, one too long for a small grid.

    Two themes, not one, so the report's "N of M declared themes" denominator
    is pinned to something other than the theme floor, and so one theme can
    render `met` while the other renders `short` in the same block. "Food"
    carries an answer the default grid does not hold, which is also what
    exercises the zero-count path for a declared theme.
    """
    return cw_bank.Bank(
        themes={
            "pets": cw_bank.ThemeInfo("Pets", "Two cats and a lot of hair"),
            "food": cw_bank.ThemeInfo("Food", "Mostly pie"),
        },
        entries=(
            cw_bank.BankEntry("CAT", "pets", None),
            cw_bank.BankEntry("COW", "pets", None),
            cw_bank.BankEntry("WET", None, None),
            cw_bank.BankEntry("PIE", "food", None),
            cw_bank.BankEntry("ELEPHANTINE", None, None),
        ),
    )


def make_config(
    *,
    rows: int = 3,
    cols: int = 3,
    min_blocked: float = 10.0,
    max_blocked: float = 45.0,
    min_themes: int = 1,
    min_entries_per_theme: int = 1,
    feature: str | None = None,
    features: tuple[cw_feature.Feature, ...] = (),
    start: tuple[str, ...] = (),
    max_two_letter: int | None = None,
    masked: frozenset[tuple[int, int]] = frozenset(),
    mask_size: tuple[int, int] = (0, 0),
) -> cw_config.FillConfig:
    """A `fill` config for the report tests, overridable field by field.

    Spelled out as keyword parameters rather than a dict merged into the
    dataclass: a dict of `object` values needs a type-checker suppression at
    the call, and a suppression is exactly what hides the next fixture that
    passes a field the dataclass does not have.

    """
    return cw_config.FillConfig(
        rows=rows,
        cols=cols,
        seed=1,
        min_blocked=min_blocked,
        max_blocked=max_blocked,
        min_themes=min_themes,
        min_entries_per_theme=min_entries_per_theme,
        time_budget=5.0,
        max_steps=100,
        look_ahead=0,
        prefer=(),
        island_letters=(),
        # A bare `feature` goes first, ahead of any pins passed explicitly:
        # the report prints features in the order the flags were given.
        features=(
            features
            if feature is None
            else (cw_feature.Feature(feature, None), *features)
        ),
        start=start,
        # A `start` stands for a source at its own size, as `fill --source`
        # places one given no size flag; a grown-grid case replaces this.
        source_size=(len(start), len(start[0])) if start else (0, 0),
        max_two_letter=max_two_letter,
        masked=masked,
        mask_size=mask_size,
    )


def make_outcome(
    rows: tuple[str, ...] = DEFAULT_ROWS,
    *,
    placed: tuple[cw_place.Placement, ...] | None = None,
    bank: cw_bank.Bank | None = None,
    config: cw_config.FillConfig | None = None,
) -> cw_search.SearchOutcome:
    """A SearchOutcome whose verdict is DERIVED from `rows`, never hand-written.

    `missed` and `conforming` come from `cw_accept.missed_constraints`, the
    same function the real search uses, so a fixture can never assert against a
    sentence the producer does not actually emit -- nor claim a grid misses a
    constraint it plainly meets.

    `placed` defaults to EMPTY and is never kept in step with `rows`: the report
    must read the grid, so a record that agreed with it would hide the bug.
    """
    resolved_bank = make_bank() if bank is None else bank
    resolved_config = make_config() if config is None else config
    missed = cw_accept.missed_constraints(rows, resolved_bank, resolved_config)
    return cw_search.SearchOutcome(
        rows=rows,
        placed=() if placed is None else placed,
        conforming=not missed,
        missed=missed,
        steps=12,
    )


def line(text: str, prefix: str) -> str:
    """The single line of `text` starting with `prefix`.

    Raises AssertionError (a test failure) when the prefix matches none or
    more than one line, so a test can never silently assert against the wrong
    section of the report.
    """
    matches = [row for row in text.splitlines() if row.startswith(prefix)]
    if len(matches) != 1:
        raise AssertionError(f"expected one line starting {prefix!r}, got {matches!r}")
    return matches[0]


def lines(text: str, prefix: str) -> list[str]:
    """Every line of `text` starting with `prefix`, in report order."""
    return [row for row in text.splitlines() if row.startswith(prefix)]


def block_after(text: str, header: str, count: int) -> list[str]:
    """The `count` lines immediately following the line equal to `header`.

    The only honest way to assert an ORDER: a test that collects its expected
    lines by prefix and concatenates them reconstructs the order it then
    asserts, and passes just as happily when the writer emits them reversed.
    """
    body = text.splitlines()
    return body[body.index(header) + 1 : body.index(header) + 1 + count]


def cells(rendered: str) -> tuple[tuple[int, int], ...]:
    """Every "(row, col)" pair rendered on one line, as integers."""
    return tuple((int(row), int(col)) for row, col in _CELL_RE.findall(rendered))
