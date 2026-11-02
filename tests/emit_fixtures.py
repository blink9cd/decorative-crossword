"""Shared fixtures for the cw_emit suites: one outcome, and the banks around it.

Shared by the emit suites: every builder here is scaffolding rather than an
assertion, and each suite would otherwise have to copy them.

Every bank here is constructed directly rather than through `parse_bank`. That
is deliberate and is what several of the screening tests depend on:
`build_document` accepts any Bank, including one that never crossed the parse
boundary, and it is the last thing between operator text and emitted bytes.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import cast

import cw_bank
import cw_grid
import cw_place
import cw_search

#: The grid every document test emits from. Its runs are CAT and WET across,
#: COW down, so column 0 spells a third entry no ACROSS row contains.
_ROWS = ("CAT", "O..", "WET")


def _outcome() -> cw_search.SearchOutcome:
    """A conforming 3x3 result whose three placements produce three runs."""
    return cw_search.SearchOutcome(
        rows=_ROWS,
        placed=(
            cw_place.Placement("CAT", 0, 0, cw_grid.ACROSS),
            cw_place.Placement("COW", 0, 0, cw_grid.DOWN),
            cw_place.Placement("WET", 2, 0, cw_grid.ACROSS),
        ),
        conforming=True,
        missed=(),
        steps=3,
    )


def _outcome_with_a_free_run() -> cw_search.SearchOutcome:
    """The same grid, with WET arriving as a crossing rather than a placement.

    The input shape a `placed`-driven emitter gets wrong: one placement can
    create more than one entry, so the grid's runs, not the placement
    history, are what the document must cover.
    """
    return dataclasses.replace(_outcome(), placed=_outcome().placed[:2])


def _bank() -> cw_bank.Bank:
    """Two themes declared, one of them placed by nothing; one clue supplied."""
    return cw_bank.Bank(
        themes={
            "pets": cw_bank.ThemeInfo("Pets", "Two cats and a lot of hair"),
            "unused": cw_bank.ThemeInfo("Unused", "Placed by nothing"),
        },
        entries=(
            cw_bank.BankEntry("CAT", "pets", "Sleeps on the keyboard"),
            cw_bank.BankEntry("COW", "pets", None),
            cw_bank.BankEntry("WET", None, None),
        ),
    )


def _bank_clued(answer: str, clue: str) -> cw_bank.Bank:
    """The standard bank with one answer's clue replaced."""
    base = _bank()
    return cw_bank.Bank(
        themes=base.themes,
        entries=tuple(
            dataclasses.replace(entry, clue=clue) if entry.answer == answer else entry
            for entry in base.entries
        ),
    )


def _bank_keyed(key: str) -> cw_bank.Bank:
    """The standard bank with the placed theme's key replaced.

    Constructed directly, like every bank here: `parse_bank` screens a theme
    key, so a hostile key cannot reach the emitter that way, and the emitter's
    own screen exists for a Bank that never crossed the parse boundary.
    """
    return cw_bank.Bank(
        themes={
            key: cw_bank.ThemeInfo("Pets", "Two cats and a lot of hair"),
            "unused": cw_bank.ThemeInfo("Unused", "Placed by nothing"),
        },
        entries=(
            cw_bank.BankEntry("CAT", key, "Sleeps on the keyboard"),
            cw_bank.BankEntry("COW", key, None),
            cw_bank.BankEntry("WET", None, None),
        ),
    )


def _bank_labeled(label: str) -> cw_bank.Bank:
    """The standard bank with the placed theme's label replaced."""
    base = _bank()
    return cw_bank.Bank(
        themes={
            "pets": cw_bank.ThemeInfo(label, "Two cats and a lot of hair"),
            "unused": cw_bank.ThemeInfo("Unused", "Placed by nothing"),
        },
        entries=base.entries,
    )


def _bank_without(answer: str) -> cw_bank.Bank:
    """The standard bank with one answer removed from it entirely."""
    base = _bank()
    return cw_bank.Bank(
        themes=base.themes,
        entries=tuple(entry for entry in base.entries if entry.answer != answer),
    )


def _clues(document: Mapping[str, object]) -> Mapping[str, Mapping[str, str]]:
    """The document's clue table, narrowed once for the assertions below.

    A single cast rather than a `# type: ignore` on every subscript:
    `build_document` returns the loose `dict[str, object]` that `json.dumps`
    accepts, and narrowing here keeps mypy checking the assertions themselves.
    `TestDocumentShape` pins the runtime shape this cast asserts, so the
    narrowing is verified rather than assumed.
    """
    return cast(Mapping[str, Mapping[str, str]], document["clues"])
