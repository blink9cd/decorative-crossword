"""cw_excluded_terms: reads an --excluded-terms list and screens a bank against it.

`load_excluded_terms` reads the list, one barred term to a line, and
`screen_excluded` drops every bank entry a term matches, handing back what it
dropped for the report to name rather than failing on it. A list that cannot
be read is refused as `cw_bank.BankError`, the bank's own error type, so a
caller has one name to catch for the bank and the list that screens it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import cw_answer
import cw_input
import cw_text
from cw_bank import Bank, BankEntry, BankError

#: A line whose first non-blank character is this is a comment in a term list.
#: Only the FIRST character: a trailing-comment rule would silently truncate a
#: term that legitimately contains a hash.
_COMMENT_PREFIX = "#"


# fuzz-target
def load_excluded_terms(path: Path) -> frozenset[str]:
    """Read a barred-term list: one term per line, lowercased.

    A line ends where an editor ends one (`cw_input.editor_lines`), so a term
    holding a character that only some programs break at is still one term.
    Blank lines and lines whose first non-blank character is `#` are ignored,
    so an operator can annotate the list. Every surviving line is stripped and
    lowercased, because `screen_excluded` matches case-insensitively and doing
    the fold once here keeps the matcher from having to remember to.

    Wraps `OSError` and `UnicodeDecodeError` into `BankError` for the reason
    `cw_bank.read_bank_payload` does, including why the second is named
    separately: it is a `ValueError` rather than an `OSError`, so a
    mis-encoded term list would otherwise escape the CLI's refusal set as a
    traceback.
    """
    try:
        text = cw_input.read_input_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise BankError(f"could not read excluded-terms file {path}: {exc}") from exc
    return frozenset(
        stripped.lower()
        for line in cw_input.editor_lines(text)
        if (stripped := line.strip()) and not stripped.startswith(_COMMENT_PREFIX)
    )


def _term_pattern(term: str) -> re.Pattern[str]:
    r"""A whole-word, case-insensitive matcher for one barred term.

    `re.escape` because a term is a WORD the operator typed, not a pattern: an
    unescaped `.` in "b.oom" would screen BLOOM and every other five-letter
    answer shaped like it, silently over-reaching the list the operator wrote.

    `(?<!\w)` / `(?!\w)` rather than `\b`: a term may legitimately start or end
    with a non-word character (a hyphen, a quote), and `\b` flips its meaning
    at exactly those edges, so a term like "-ish" would match nothing.
    """
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def _drop_reason(entry: BankEntry, terms: Mapping[str, re.Pattern[str]]) -> str | None:
    """Why `entry` is barred, or None if no term matches it.

    `terms` is walked in the order its caller built it -- sorted -- so which
    term a two-match entry is reported under is fixed rather than decided by a
    `frozenset`'s hash-seeded iteration order, which must never reach output.

    An answer is read twice: as written, whole-word, so `there` bars
    `HELLO THERE`; and closed up, so `hello-there` and `hellothere` bar it too,
    as `web site` bars `WEBSITE`. For a letters-only answer and term the two
    readings coincide.
    """
    for term, pattern in terms.items():
        if (
            pattern.search(entry.written)
            or cw_answer.grid_form(term).upper() == entry.answer
        ):
            return f"its answer matches the excluded term {cw_text.shown(term)}"
        if entry.clue is not None and pattern.search(entry.clue):
            return f"its clue matches the excluded term {cw_text.shown(term)}"
    return None


# fuzz-target
def screen_excluded(
    bank: Bank, terms: frozenset[str]
) -> tuple[Bank, tuple[tuple[str, str], ...]]:
    """Drop every entry a term matches; return the survivors and what was dropped.

    Whole-word and case-insensitive, against both the answer and its clue.

    It never raises. A drop is REPORTED, not fatal: the pairs come back for the
    report to list by name and count, because a screen that silently removed
    part of the bank would make "placed 24 of 61" a lie about a number the
    operator supplied.

    The declared themes survive untouched even when a theme's last entry is
    dropped: screening removes entries, not declarations, and a label that
    vanished would strand anything still holding that key.

    An empty term is skipped rather than compiled: it would match every entry,
    which is never what a blank line in a list meant. `load_excluded_terms`
    cannot produce one, but this function is public.
    """
    patterns = {term: _term_pattern(term) for term in sorted(terms) if term}
    kept: list[BankEntry] = []
    dropped: list[tuple[str, str]] = []
    for entry in bank.entries:
        reason = _drop_reason(entry, patterns)
        if reason is None:
            kept.append(entry)
        else:
            dropped.append((entry.answer, reason))
    return replace(bank, entries=tuple(kept)), tuple(dropped)
