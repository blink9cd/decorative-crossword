"""cw_bank_merge: merges every `--bank` file of one run into the one bank it searches.

`fill` and `gaps` take `--bank` more than once, so a run can draw on a
site-wide bank and a small per-grid bank of names without a hand-built copy
holding both. Several curated banks are still a curated vocabulary: nothing
here adds a word the operator did not write into one of their own files.

**The order the banks are given is the order of their themes and entries**:
the first file's, then whatever each later file adds. That order reaches every
report block that lists the bank. It does not reach the grid: the search sorts
its candidates on a seeded hash of each placement (`cw_order`), and the emitted
document follows the grid's own runs.

Every file is validated by `cw_bank.parse_bank`, so each meets every rule a
lone bank meets, with one widening: an entry may name a theme any file of the
set declares. A names bank then need not copy the site-wide bank's theme
record, a copy that would disagree with its original the first time that
record was edited.

Two files may hold the same answer, or declare the same theme, only in the same
words. An identical record is kept once, where it first appears; a record that
differs is refused, naming both files and the fields that differ, because
keeping either would silently drop the other. Themes are merged before any
entry is parsed, since an entry is checked against them, and each of the two
refusals names the first `_LISTED_MAX` differing records of its kind and
counts the rest.

A lone bank reads exactly as `cw_bank.parse_bank` reads it, refusals word for
word: a refusal names its file only when there are several files to tell apart.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

import cw_bank
import cw_text

#: One bank file: the name its refusals use, and its payload as parsed JSON.
BankFile = tuple[str, object]

#: Whatever one file of the set parses into: its own themes, or its bank.
_Parsed = TypeVar("_Parsed")

#: Whatever two files may both carry under one key: an entry, or a theme record.
_Record = TypeVar("_Record")

#: The fields two records of one answer must agree on, read off the record type
#: so a field added to it is compared without anyone remembering to add it here.
_ENTRY_FIELDS = tuple(
    field.name for field in fields(cw_bank.BankEntry) if field.name != "answer"
)

#: The fields two declarations of one theme must agree on, read off the same way.
_THEME_FIELDS = tuple(field.name for field in fields(cw_bank.ThemeInfo))

#: The most differing records one refusal names; the rest are counted. Two
#: banks may share every answer, so a refusal naming each would grow with the
#: files: two banks of a hundred thousand answers rated differently made one
#: of megabytes. Ten show whether the disagreement is one slip or a whole
#: column edited in one file, and are few enough to fix by hand before the
#: next run names the next ten.
_LISTED_MAX = 10


@dataclass(frozen=True)
class BankSet:
    """The merged bank, and each file it came from with the entries that file holds.

    `files` counts each file's own entries, an identical record counted once in
    every file holding it: it describes the operator's files, while `bank` holds
    each answer once.
    """

    bank: cw_bank.Bank
    files: tuple[tuple[str, int], ...]


def _parse_each(
    files: Sequence[BankFile], parse: Callable[[object], _Parsed]
) -> list[tuple[str, _Parsed]]:
    """`parse` applied to each file's payload, in order, or the first BankError.

    The refusal names its file when there are several, and is `parse`'s own
    message otherwise.
    """
    parsed: list[tuple[str, _Parsed]] = []
    for name, payload in files:
        try:
            parsed.append((name, parse(payload)))
        except cw_bank.BankError as exc:
            if len(files) > 1:
                raise cw_bank.BankError(f"bank file {name}: {exc}") from exc
            raise
    return parsed


def _first_records(
    records: Iterable[tuple[str, str, _Record]], kind: str, compared: Sequence[str]
) -> dict[str, _Record]:
    """The first record for each key, in order of first appearance, or BankError.

    `records` are (file, key, record) triples in file order. A later record
    equal to the first is dropped; one that differs is a fault naming the key,
    both files and each field in `compared` that differs, and the faults are
    reported in one refusal (`_faults_message`). A dict, because its insertion
    order is the order of first appearance, so no hash-seeded order can reach
    the merged bank.
    """
    first: dict[str, _Record] = {}
    first_in: dict[str, str] = {}
    faults: list[str] = []
    for name, key, record in records:
        if key not in first:
            first[key] = record
            first_in[key] = name
        elif record != first[key]:
            differ = ", ".join(
                field
                for field in compared
                if getattr(record, field) != getattr(first[key], field)
            )
            faults.append(
                f"{kind} {cw_text.shown(key)} differs between the bank files "
                f"{first_in[key]} and {name}, in its {differ}: each {kind} needs "
                "one record"
            )
    if faults:
        raise cw_bank.BankError(_faults_message(faults))
    return first


def _faults_message(faults: Sequence[str]) -> str:
    """The first `_LISTED_MAX` faults, in order, and a count of any left unnamed."""
    listed = list(faults[:_LISTED_MAX])
    if len(faults) > _LISTED_MAX:
        listed.append(f"and {len(faults) - _LISTED_MAX} more")
    return "; ".join(listed)


def _merged_themes(
    declared: Sequence[tuple[str, Mapping[str, cw_bank.ThemeInfo]]],
) -> dict[str, cw_bank.ThemeInfo]:
    """Every theme the files declare, in order, or BankError naming each declared two ways."""
    return _first_records(
        ((name, key, info) for name, own in declared for key, info in own.items()),
        "theme",
        _THEME_FIELDS,
    )


# fuzz-target
def parse_banks(files: Sequence[BankFile]) -> BankSet:
    """Validate every bank file and merge them, in the order given, into one bank.

    Raises BankError for a file `cw_bank.parse_bank` refuses, a theme two files
    declare differently, or an answer two files record differently, checked
    in that order, the themes before any entry, since every entry is checked
    against the merged themes.
    """
    themes = _merged_themes(_parse_each(files, cw_bank.parse_themes))
    banks = _parse_each(files, lambda payload: cw_bank.parse_bank(payload, themes))
    entries = _first_records(
        ((name, entry.answer, entry) for name, bank in banks for entry in bank.entries),
        "answer",
        _ENTRY_FIELDS,
    )
    return BankSet(
        bank=cw_bank.Bank(
            themes=MappingProxyType(themes), entries=tuple(entries.values())
        ),
        files=tuple((name, len(bank.entries)) for name, bank in banks),
    )


def load_banks(paths: Sequence[Path]) -> BankSet:
    """Read every bank file, in order, and merge them into one bank.

    Every file is read before any is validated, so an unreadable file is
    refused ahead of a malformed one wherever each sits in the order;
    `cw_bank.read_bank_payload` says what reading refuses. Each file is named
    as given, which is how the report and every refusal name it.
    """
    return parse_banks(
        tuple((str(path), cw_bank.read_bank_payload(path)) for path in paths)
    )
