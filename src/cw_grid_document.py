"""cw_grid_document: reads a grid_source.json back, narrowed to what a render needs.

`cw_emit` writes the document; this module reads one back, from a file
(`load_document`) or from a payload already parsed (`parse_document`). A
document that cannot be used is refused as `cw_emit.EmitError`, the writer's
own error type, so a caller has one name to catch whether a document failed
on its way out or on its way back in. A theme label or summary read here
passes the writer's own screen, `cw_emit._screened`, so each is refused on
the way in exactly as it would be on the way out.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import cw_bank
import cw_grid
import cw_input
import cw_json
import cw_text
from cw_emit import EmitError, _screened


@dataclass(frozen=True)
class GridDocument:
    """A `grid_source.json` narrowed to what a render, and `fill --source`, need.

    A typed struct rather than the raw `dict[str, object]` `json.loads` hands
    back: genuinely-untyped external data is modeled rather than left dynamic.
    The alternative pushes a cast into every caller, and the caller here is the
    CLI -- the one place where a wrong narrowing would surface as a traceback
    instead of as exit 2.

    `entry_themes` is flattened out of the `clues` map because that is the
    shape `cw_svg.RenderRequest` asks for; deriving it once here is what keeps
    `fill --preview` and `preview` from each deriving it their own way.

    `clues` maps EVERY key of the `clues` map to its clue text, `""` where the
    record has none. `fill --source` needs it for two things: a key is how a
    source DECLARES a run the bank lacks, and the text is the clue that run
    keeps.
    """

    rows: tuple[str, ...]
    themes: Mapping[str, cw_bank.ThemeInfo]
    entry_themes: Mapping[str, str]
    clues: Mapping[str, str]


def _string_map(payload: object, field: str) -> Mapping[str, object]:
    """Narrow one of the document's optional object fields, or raise EmitError.

    Absent reads as empty: this tool emits `themes` and `clues` always, but
    `preview` is documented to work on a hand-authored file, and a grid
    with no themes at all is a legitimate one rather than a malformed one.
    """
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise EmitError(
            f"document {cw_text.shown(field)} must be a JSON object, "
            f"got {cw_text.shown(payload)}"
        )
    for key in payload:
        if not isinstance(key, str):
            raise EmitError(
                f"document {cw_text.shown(field)} key {cw_text.shown(key)} "
                "must be a string"
            )
    return payload


def _theme_field(record: Mapping[str, object], key: str, field: str) -> str:
    """One required, screened string field of a document theme record, or EmitError.

    Screened because a label is drawn: a character the SVG cannot carry would
    leave a picture no parser opens. The summary gets the same screen as the
    label beside it, as it does in the bank, so the two cannot drift apart.
    """
    value = record.get(field)
    if not isinstance(value, str):
        raise EmitError(
            f"theme {cw_text.shown(key)} {field} must be a string, "
            f"got {cw_text.shown(value)}"
        )
    return _screened(value, f"the {field} for theme {cw_text.shown(key)}")


def _parse_themes(payload: object) -> dict[str, cw_bank.ThemeInfo]:
    """The declared themes, or EmitError naming the bad one.

    Reuses `cw_bank.ThemeInfo` rather than defining a parallel struct: the
    document's theme record IS the bank's, minus the themes no entry placed,
    and two identical dataclasses in one project are two things to keep in
    step. Emptiness is NOT enforced here -- unlike the bank, which is the
    operator's input boundary, `preview` is documented to work on a
    hand-authored file, and a thin summary is for whatever consumes the grid to
    judge rather than a reason to refuse to draw.
    """
    themes: dict[str, cw_bank.ThemeInfo] = {}
    for key, record in _string_map(payload, "themes").items():
        if not isinstance(record, Mapping):
            raise EmitError(
                f"theme {cw_text.shown(key)} must be a JSON object, "
                f"got {cw_text.shown(record)}"
            )
        themes[key] = cw_bank.ThemeInfo(
            label=_theme_field(record, key, "label"),
            summary=_theme_field(record, key, "summary"),
        )
    return themes


def _clue_records(payload: object) -> dict[str, Mapping[str, object]]:
    """The document's `clues` map with every record narrowed to an object, or EmitError.

    Checked once, here, rather than by each reader of the records: the theme
    parser and the clue parser both walk this map, and a shape check in each
    would leave whichever runs second unable to fire.
    """
    records: dict[str, Mapping[str, object]] = {}
    for answer, record in _string_map(payload, "clues").items():
        if not isinstance(record, Mapping):
            raise EmitError(
                f"clue record for {cw_text.shown(answer)} must be a JSON object"
            )
        records[answer] = record
    return records


def _parse_entry_themes(records: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    """Each clued answer's theme key, skipping the answers that carry none.

    A record with no clue, or naming a theme nothing declared, is accepted
    without complaint: those are for whatever consumes the grid to judge, and a
    preview that refused to draw because of them would be useless at exactly
    the moment it is most wanted.
    """
    entry_themes: dict[str, str] = {}
    for answer, record in records.items():
        theme = record.get("theme")
        if theme is None:
            continue
        if not isinstance(theme, str):
            raise EmitError(
                f"clue record for {cw_text.shown(answer)} has a non-string theme"
            )
        entry_themes[answer] = theme
    return entry_themes


def _parse_entry_clues(records: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    """Each declared answer's clue text, "" where its record carries none.

    Every key counts, clued or not: `fill --source` keeps a run the bank lacks
    only when the source DECLARES it, and a declaration is a key of this map.
    A non-string clue is refused as a non-string theme already is, because a
    kept entry would otherwise lose its clue without a word.
    """
    clues: dict[str, str] = {}
    for answer, record in records.items():
        clue = record.get("clue")
        if clue is None:
            clue = ""
        if not isinstance(clue, str):
            raise EmitError(
                f"clue record for {cw_text.shown(answer)} has a non-string clue"
            )
        clues[answer] = clue
    return clues


def parse_document(payload: object) -> GridDocument:
    """Validate an already-parsed `grid_source.json` payload.

    Split from `load_document` for the reason `cw_bank.parse_bank` is split
    from `load_bank`: the whole validation surface stays reachable without
    touching the filesystem -- and `fill --preview` narrows the document it
    just BUILT through here, so every caller of the renderer reaches it holding
    a value derived exactly one way.

    The grid's own coherence -- ragged rows, an empty grid, a cell that is
    neither a letter nor a block -- is `cw_grid.validate_rows`, not a second
    statement of it here.
    """
    if not isinstance(payload, Mapping):
        raise EmitError(f"document must be a JSON object, got {cw_text.shown(payload)}")
    try:
        rows = cw_grid.validate_rows(payload.get("rows"))
    except ValueError as exc:
        raise EmitError(f"document has no coherent grid: {exc}") from exc
    # Themes before clue records, so a document wrong in both is named for its
    # themes first: a clue record's `theme` is a key into that map.
    themes = _parse_themes(payload.get("themes"))
    records = _clue_records(payload.get("clues"))
    return GridDocument(
        rows=rows,
        themes=MappingProxyType(themes),
        entry_themes=MappingProxyType(_parse_entry_themes(records)),
        clues=MappingProxyType(_parse_entry_clues(records)),
    )


# fuzz-target
def load_document(path: Path) -> GridDocument:
    """Read and validate the `grid_source.json` at `path`.

    Wraps `OSError`, `UnicodeDecodeError` and whatever `cw_json.loads` refuses
    into `EmitError` so the CLI has one exception type to catch whether the file
    was unreadable, mis-encoded, unparsable or incoherent -- all four are
    `preview`'s single exit-2 case, and `preview` has no exit 1 at all.

    `UnicodeDecodeError` is named separately because it is a `ValueError` and
    not an `OSError`: the exact reverse of `cw_emit.write_atomically`, which
    names `UnicodeError` beside `OSError` for the encoder's failure on the way
    out.
    """
    try:
        text = cw_input.read_input_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise EmitError(f"could not read grid file {path}: {exc}") from exc
    try:
        payload = cw_json.loads(text)
    except cw_json.RepeatedKeyError as exc:
        raise EmitError(f"grid file {path} {exc}") from exc
    except ValueError as exc:
        raise EmitError(f"grid file {path} is not valid JSON: {exc}") from exc
    try:
        return parse_document(payload)
    except EmitError as exc:
        raise EmitError(f"grid file {path}: {exc}") from exc
