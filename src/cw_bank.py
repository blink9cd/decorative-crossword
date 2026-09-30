"""cw_bank: parses and validates bank.json, the operator-supplied word bank.

This is the project's untrusted-input boundary: `parse_bank` is what stands
between an operator's hand-edited JSON file and every downstream module, none
of which re-validates the shape of a `Bank` it receives.
Everything reachable from `parse_bank` must therefore fail with `BankError`
rather than crash, no matter how malformed the payload is -- see
`tests/test_properties.py` for the property test that holds it to that.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import cw_answer
import cw_config
import cw_input
import cw_json
import cw_text
from cw_grid import MIN_RUN

#: The scale an answer's optional rating is written on, both ends included. A
#: rating is the operator's own judgment of how good a word is: the one quality
#: signal `fill` reads, because a dictionary or a frequency floor is the filter
#: this project rejects, and commonness is not quality anyway.
MIN_RATING = 1
MAX_RATING = 5

#: What an UNRATED answer counts as: the middle of the scale. A bank that rates
#: nothing therefore ties every grid on the rating level, so ratings choose
#: nothing for it.
NEUTRAL_RATING = (MIN_RATING + MAX_RATING) // 2


class BankError(ValueError):
    """Raised when bank.json, a companion term list, or a parsed payload is unusable.

    One type for the whole input boundary this module owns, so a caller
    reporting exit 2 catches one name rather than three.
    """


@dataclass(frozen=True)
class ThemeInfo:
    """One declared theme: its display label and its one-line summary.

    A record rather than two maps keyed by slug, because two parallel maps can
    disagree and a record cannot.

    The summary is REQUIRED because it is what the consumer's readout leads
    with, and it is enforced here, at the untrusted-input boundary, rather
    than left to the consumer: a theme declared with nothing to say renders an
    empty readout on the page, and nothing downstream can notice -- the
    document is well-formed, the renderer throws nothing, and the grid draws.
    """

    label: str
    summary: str


@dataclass(frozen=True)
class BankEntry:
    """One word-bank record: an answer, and its optional theme, clue, rating and spelling.

    `answer` is the GRID form, letters only, and is what every comparison in
    this project reads. `spelling` is how the bank wrote it when that says
    more -- `HELLO THERE` for `HELLOTHERE` -- and None when the letters are
    all there is.

    `rating` and `spelling` have defaults, None, because a bank assembled in
    code has no reason to rate or spell anything; `parse_bank` is where both are
    read.
    """

    answer: str
    theme: str | None
    clue: str | None
    rating: int | None = None
    spelling: str | None = None

    @property
    def written(self) -> str:
        """The answer as the bank wrote it: its spelling, or its letters alone."""
        return self.answer if self.spelling is None else self.spelling


@dataclass(frozen=True)
class Bank:
    """A validated word bank: its declared theme labels and its unique entries."""

    themes: Mapping[str, ThemeInfo]
    entries: tuple[BankEntry, ...]

    def by_answer(self) -> dict[str, BankEntry]:
        """Index entries by answer.

        A plain dict build is safe here (no last-write-wins collision hiding a
        dropped entry) because `parse_bank` already rejects a repeated answer
        before a Bank is ever constructed.
        """
        return {entry.answer: entry for entry in self.entries}


def _require_bank_mapping(payload: object) -> Mapping[str, object]:
    """Raise BankError unless `payload` is a JSON object."""
    if not isinstance(payload, Mapping):
        raise BankError(f"bank must be a JSON object, got {cw_text.shown(payload)}")
    return payload


def _require_entries_list(payload: Mapping[str, object]) -> list[object]:
    """Raise BankError unless payload['entries'] is a non-empty list."""
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise BankError(
            f"bank 'entries' must be a non-empty list, got {cw_text.shown(raw_entries)}"
        )
    return raw_entries


def _parse_theme_field(record: Mapping[str, object], key: str, field: str) -> str:
    """One required non-empty string field of a theme record, or BankError.

    Both fields are required and both are screened. Empty is rejected as firmly
    as absent: a theme carrying `"summary": ""` says exactly as little as one
    that omits it, and a theme must have something to say.
    """
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise BankError(
            f"theme {cw_text.shown(key)} needs a non-empty string "
            f"{cw_text.shown(field)}, got {cw_text.shown(value)}"
        )
    return _screened(value, f"the {field} for theme {cw_text.shown(key)}")


def _parse_themes(payload: Mapping[str, object]) -> dict[str, ThemeInfo]:
    """Validate payload['themes'] into a key-to-ThemeInfo dict.

    Required even when empty -- "may be empty" is not the same as "may be
    absent" -- so a missing key fails here just like a themes value of the
    wrong type.

    A bare label string is REJECTED rather than read as a label with no
    summary. This is the project's untrusted-input boundary, and accepting
    that shape would push a theme with nothing to say all the way to the
    published page.
    """
    raw_themes = payload.get("themes")
    if not isinstance(raw_themes, Mapping):
        raise BankError(
            f"bank 'themes' must be a JSON object, got {cw_text.shown(raw_themes)}"
        )
    themes: dict[str, ThemeInfo] = {}
    for key, record in raw_themes.items():
        if not isinstance(key, str):
            raise BankError(f"theme key {cw_text.shown(key)} must be a string")
        if not isinstance(record, Mapping):
            raise BankError(
                f"theme {cw_text.shown(key)} must be an object with 'label' and "
                f"'summary', got {cw_text.shown(record)}"
            )
        # The KEY is screened as well as the record's strings, and it is the
        # half nothing else in this project constrains: `_parse_answer`
        # restricts an answer to `cw_answer.SPELLING_RULE`, but a theme key
        # arrives from the operator's file unrestricted and the emitter writes
        # it twice -- as a key of `themes` and as each record's "theme" value.
        _screened(key, "a theme key")
        themes[key] = ThemeInfo(
            label=_parse_theme_field(record, key, "label"),
            summary=_parse_theme_field(record, key, "summary"),
        )
    return themes


def _parse_answer(raw_entry: Mapping[str, object]) -> tuple[str, str | None]:
    """Validate one entry's answer; return its grid form, and its spelling where that differs.

    The shape is checked before the length, so a malformed answer is told the
    rule rather than a letter count taken of characters that are not letters.
    The length is the grid form's: `JACK-O'-LANTERN` lays twelve letters.
    """
    answer = raw_entry.get("answer")
    if not isinstance(answer, str):
        raise BankError(f"entry 'answer' must be a string, got {cw_text.shown(answer)}")
    if not cw_answer.is_spelling(answer):
        raise BankError(
            f"answer {cw_text.shown(answer)} must be {cw_answer.SPELLING_RULE}"
        )
    letters = cw_answer.grid_form(answer)
    if len(letters) < MIN_RUN:
        raise BankError(
            f"answer {cw_text.shown(answer)} must be at least {MIN_RUN} letters long"
        )
    return letters, (None if letters == answer else answer)


def _parse_theme(
    raw_entry: Mapping[str, object], answer: str, themes: Mapping[str, ThemeInfo]
) -> str | None:
    """Validate one entry's optional theme: absent, or a declared key.

    Two separate checks, not one compound condition, so a wrong-type theme and
    an undeclared one get their own diagnosis: collapsing them reports a
    `theme: 5` as "undeclared", which sends an operator who typed a number
    instead of a key looking for a missing declaration that was never the
    problem. The isinstance check still has to
    run FIRST, though, and not merely for a clearer message: an unhashable
    theme value (a list or dict submitted where a string belongs) would
    otherwise make `theme not in themes` raise TypeError -- a crash, not a
    BankError -- which is exactly the failure mode the property test in
    tests/test_properties.py exists to catch.
    """
    theme = raw_entry.get("theme")
    if theme is None:
        return None
    if not isinstance(theme, str):
        raise BankError(
            f"entry {cw_text.shown(answer)} theme must be a string, "
            f"got {cw_text.shown(theme)}"
        )
    if theme not in themes:
        raise BankError(
            f"entry {cw_text.shown(answer)} names undeclared theme "
            f"{cw_text.shown(theme)}"
        )
    return theme


def _screened(text: str, description: str) -> str:
    """Return `text`, or raise BankError naming what makes it unsafe to emit.

    The clue-safety screen, applied at the PARSE boundary so a clue carrying a
    `</script` is refused on the exit-2 line, before a search that may spend the
    whole time budget. The rule itself is not restated here: it is
    `cw_config.forbidden_clue_fragment`, the project's single statement of what
    no output of this tool may carry.

    The emitter keeps its own call to the same rule. That is not a second copy
    of the screen but the same one at a second boundary: `cw_emit.build_document`
    accepts any `Bank`, including one assembled in code that never came through
    here, and it is the last thing between operator text and emitted bytes.
    """
    fragment = cw_config.forbidden_clue_fragment(text)
    if fragment is not None:
        raise BankError(
            f"{description} must not contain {fragment}, got {cw_text.shown(text)}"
        )
    return text


def _parse_clue(raw_entry: Mapping[str, object], answer: str) -> str | None:
    """Validate one entry's optional clue: absent, or a safely emittable string."""
    clue = raw_entry.get("clue")
    if clue is None:
        return None
    if not isinstance(clue, str):
        raise BankError(
            f"entry {cw_text.shown(answer)} clue must be a string, "
            f"got {cw_text.shown(clue)}"
        )
    return _screened(clue, f"the clue for {cw_text.shown(answer)}")


def _parse_rating(raw_entry: Mapping[str, object], answer: str) -> int | None:
    """Validate one entry's optional rating: absent, or a whole number on the scale.

    A rating ranks grids and never removes an answer, so this refusal is the
    only thing a rating can do to a run. `bool` is refused by name, ahead of the
    integer check, because it is a subclass of `int`: `isinstance(True, int)`
    holds, and a JSON `true` would otherwise read as a rating of 1. A float is
    refused even when whole -- JSON keeps `3` and `3.0` apart, and `3.0`
    suggests a finer scale than this field has.
    """
    rating = raw_entry.get("rating")
    if rating is None:
        return None
    if (
        isinstance(rating, bool)
        or not isinstance(rating, int)
        or not MIN_RATING <= rating <= MAX_RATING
    ):
        raise BankError(
            f"entry {cw_text.shown(answer)} rating must be a whole number from "
            f"{MIN_RATING} to {MAX_RATING}, got {cw_text.shown(rating)}"
        )
    return rating


def _parse_entry(raw_entry: object, themes: Mapping[str, ThemeInfo]) -> BankEntry:
    """Validate one bank record into a BankEntry.

    Pure with respect to duplicate detection on purpose: whether an answer
    repeats depends on every OTHER entry too, which is state this function has
    no business holding, so `parse_bank` checks it once per entry after this
    returns.
    """
    if not isinstance(raw_entry, Mapping):
        raise BankError(
            f"bank entry must be a JSON object, got {cw_text.shown(raw_entry)}"
        )
    answer, spelling = _parse_answer(raw_entry)
    # Every later refusal names the answer as the operator wrote it, which is
    # what they will search the file for.
    written = answer if spelling is None else spelling
    theme = _parse_theme(raw_entry, written, themes)
    clue = _parse_clue(raw_entry, written)
    rating = _parse_rating(raw_entry, written)
    return BankEntry(
        answer=answer, theme=theme, clue=clue, rating=rating, spelling=spelling
    )


def parse_themes(payload: object) -> Mapping[str, ThemeInfo]:
    """Validate a bank payload's own `themes` map, and nothing past it.

    What `cw_bank_merge` reads from every file before any entry, so an entry in
    one bank may name a theme another declares. The payload's shape and its
    entries list are checked first, in `parse_bank`'s own order, so a fault
    reached here reads exactly as `parse_bank` would have worded it.
    """
    bank_payload = _require_bank_mapping(payload)
    _require_entries_list(bank_payload)
    return _parse_themes(bank_payload)


# fuzz-target
def parse_bank(
    payload: object, declared: Mapping[str, ThemeInfo] | None = None
) -> Bank:
    """Validate an already-parsed JSON payload into a Bank.

    Split from `load_bank` so the whole validation surface is reachable without
    touching the filesystem, which is what lets the property test in
    tests/test_properties.py hammer it with generated payloads.

    `declared` is the themes an entry may name when this payload is one of
    several banks merged into one run: every theme any of them declares, as
    `cw_bank_merge` builds it from `parse_themes`. It then becomes the returned
    bank's theme map, so no entry names a theme its bank lacks. The payload's
    own `themes` map is validated either way.
    """
    bank_payload = _require_bank_mapping(payload)
    raw_entries = _require_entries_list(bank_payload)
    own_themes = _parse_themes(bank_payload)
    themes = own_themes if declared is None else dict(declared)

    entries: list[BankEntry] = []
    written_as: dict[str, str] = {}
    for raw_entry in raw_entries:
        entry = _parse_entry(raw_entry, themes)
        # Not silently deduplicated: two records for
        # one answer is asking a question the tool cannot answer without
        # guessing which record was meant. Compared by the grid form, so two
        # spellings of one answer are one answer.
        if entry.answer in written_as:
            raise BankError(_repeat_message(entry, written_as[entry.answer]))
        written_as[entry.answer] = entry.written
        entries.append(entry)

    # frozen=True on Bank only stops rebinding the `themes` attribute; the
    # dict it would otherwise hold is still mutable in place. Wrapping it in
    # a MappingProxyType makes the freeze real -- a view, not a copy, so it
    # still satisfies the declared `Mapping[str, ThemeInfo]` field type and
    # costs nothing extra to build.
    return Bank(themes=MappingProxyType(themes), entries=tuple(entries))


def _repeat_message(entry: BankEntry, first: str) -> str:
    """The refusal for `entry` repeating an answer first written as `first`.

    Both spellings are named when they differ, because the operator searching
    the file for the one they see would otherwise never find the other.
    """
    message = f"answer {cw_text.shown(entry.answer)} appears more than once in the bank"
    if entry.written == first:
        return message
    return (
        f"{message}, written {cw_text.shown(first)} and {cw_text.shown(entry.written)}"
    )


def load_bank(path: Path) -> Bank:
    """Read and validate bank.json at `path`; `read_bank_payload` says what reading refuses."""
    return parse_bank(read_bank_payload(path))


# fuzz-target
def read_bank_payload(path: Path) -> object:
    """Read bank.json at `path` as parsed JSON, not yet validated.

    Its own function so `cw_bank_merge` can read every bank of a run before it
    validates any of them. Wraps `OSError`, `UnicodeDecodeError` and whatever
    `cw_json.loads` refuses into `BankError`, so callers have one exception
    type to catch, whether the file was unreadable, mis-encoded or unparsable.

    `UnicodeDecodeError` has to be named separately because it is a
    `ValueError`, NOT an `OSError` -- the mirror image of the reason
    `cw_emit.write_atomically` names `UnicodeError` beside `OSError` on the way
    out. Without it a bank saved from an editor in a legacy code page escapes
    the CLI's refusal set entirely and surfaces as a traceback and exit 1,
    where exit 2 and a diagnostic are required.
    """
    try:
        text = cw_input.read_input_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise BankError(f"could not read bank file {path}: {exc}") from exc
    try:
        return cw_json.loads(text)
    except cw_json.RepeatedKeyError as exc:
        raise BankError(f"bank file {path} {exc}") from exc
    except ValueError as exc:
        raise BankError(f"bank file {path} is not valid JSON: {exc}") from exc
