"""cw_emit: builds and writes grid_source.json, the file this tool exists to produce.

The consumer -- whatever publishes the grid, embedding the document in a page --
lives outside this tool, and the dependency runs consumer to producer, so
nothing here may reach toward it. (`cw_grid_document` reads the file back too,
for this tool's own `preview` and `fill --source`; it is not the consumer.)
Two properties therefore matter more than they usually would:

* **The bytes are the contract.** Key ordering, indent, `ensure_ascii=False`
  and a trailing newline are all pinned, because the output is
  committed as a golden sample -- so every one of those is spelled out at the
  single `json.dumps` call rather than left to a library default that may move
  between releases.
* **Nothing emitted may break the consumer's inline data block.** The document
  is embedded in a page, so all four of the operator-supplied strings it
  carries -- each clue, each theme KEY, each theme label and each theme SUMMARY
  -- go through `cw_config.forbidden_clue_fragment` on the way in.
  The key needs it as much as the label does: both are operator text, and
  `build_document` accepts a Bank that never passed `cw_bank`'s own screen.
  Two kinds of emitted text are deliberately NOT screened, because no input
  could make the check fire: the `rows`, and the answers keying `clues`, both
  of which are built from A-Z letters and `cw_grid.BLOCK` -- `cw_bank`
  restricts an answer to A-Z at the parse boundary, and the grid holds nothing
  else. The screen refuses `</script`, but not `<!--` followed by `<script`,
  which puts the block into a state its own closing tag no longer ends; so
  `dumps_document` also writes every `<` as its JSON escape, and no `<` at all
  reaches the page raw.

`build_document` derives the document's entries from the grid's RUNS rather
than from `outcome.placed`: one placement can create more than one entry and an
entry can arrive for free from a crossing, and it is the runs that the consumer
will demand a clue for.
"""

from __future__ import annotations

import itertools
import json
import os
import secrets
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

import cw_answer
import cw_bank
import cw_config
import cw_grid
import cw_search
import cw_text

#: Spaces per JSON nesting level. Named because it is part of the emitted
#: contract rather than a formatting preference: the
#: committed hand-verification sample is diffed against this exact rendering.
_JSON_INDENT = 2

#: The JSON escape for LESS-THAN SIGN, a backslash then `u003c`, which the
#: emitted text carries in place of every `<`. Spelled from the backslash's
#: name so that no escape sequence is written inside this literal.
_ESCAPED_LESS_THAN = "\N{REVERSE SOLIDUS}u003c"

#: What a plain `open(path, "w")` asks the kernel for on a NEW file, before the
#: umask is subtracted from it. Handed to `os.open` so a first `--out` run gets
#: exactly the mode the operator would have got writing the file themselves,
#: rather than the private 0600 mode `tempfile` creates and `os.replace` would
#: then carry onto the output.
_NEW_FILE_MODE = 0o666

#: Bytes of randomness in a staging file's name: enough that nothing can plant a
#: path at it in advance, and `O_EXCL` refuses any that somehow exists.
_STAGING_NAME_BYTES = 8

#: The longest name, in bytes, a staging file is given: a Linux volume's limit.
#: An APFS volume counts its limit of the same number in UTF-16 units instead,
#: and a name within this bound is within that one too, because no character
#: takes fewer UTF-8 bytes than UTF-16 units.
_NAME_MAX_BYTES = 255


class EmitError(ValueError):
    """Raised when a document cannot be built or written safely."""


def _screened(text: str, description: str) -> str:
    """Return `text`, or raise EmitError naming what makes it unsafe to emit.

    Rejects rather than sanitizes, for the same reason `cw_bank` rejects such
    text at its own parse boundary: silently stripping or replacing operator
    content would hide a defect in the bank behind output that looks fine, and
    one hazard should not get two different answers. `description` names the
    offending string in the operator's own vocabulary, so the message points at
    the record to fix.
    """
    fragment = cw_config.forbidden_clue_fragment(text)
    if fragment is not None:
        raise EmitError(
            f"{description} must not contain {fragment}, got {cw_text.shown(text)}"
        )
    return text


def _clue_for(answer: str, entry: cw_bank.BankEntry | None) -> str:
    """The bank's clue for `answer`, or the empty string where none was written.

    `entry` is None for a run the bank does not hold, and its clue is None for
    a held answer the operator left unclued. Both emit an empty clue: the
    consumer's readout leads with the theme SUMMARY and shows a clue only where
    one exists, so there is nothing to invent. `fill` never reaches the first
    case -- every run of a grid it writes is an answer of the bank it searched,
    which holds each entry kept from `--source` -- but `build_document` takes
    any bank, so a run that bank lacks still gets a record.

    A multi-word answer's clue ends with its enumeration, `Greeting (5,5)`,
    because the grid shows only its letters; `cw_answer.with_enumeration` says
    when it is left off.
    """
    if entry is not None and entry.clue is not None:
        clue = cw_answer.with_enumeration(entry.clue, entry.spelling)
        return _screened(clue, f"the bank clue for {cw_text.shown(answer)}")
    return ""


def _screened_theme_key(entry: cw_bank.BankEntry | None) -> str | None:
    """The screened theme key `entry` contributes, or None where it has no theme.

    A theme key is emitted TWICE -- as a key of the `themes` map and as each
    record's `"theme"` value -- and it is as operator-supplied as the label
    beside it: nothing restricts which characters it may hold beyond the
    clue-safety screen, and a Bank built in code never passed through
    `cw_bank`, where that screen first runs.

    Screening it here, once, is what makes the two emitted spots incapable of
    disagreeing: they consume one screened value rather than each re-deriving
    it from `entry.theme` under a check one of them might lose.
    """
    if entry is None or entry.theme is None:
        return None
    return _screened(entry.theme, "an entry's theme key")


def _clue_record(
    answer: str, entry: cw_bank.BankEntry | None, theme: str | None
) -> dict[str, str]:
    """One `clues` value: a clue, plus a theme key only where the bank gave one.

    `theme` is the already-screened key from `_screened_theme_key`, never
    `entry.theme` re-read. The key is omitted rather than emitted as null: the
    document's shape has no null theme, and an absent key is what the consumer
    reads as "unthemed".
    """
    record = {"clue": _clue_for(answer, entry)}
    if theme is not None:
        record["theme"] = theme
    return record


def build_document(
    outcome: cw_search.SearchOutcome, bank: cw_bank.Bank, config: cw_config.FillConfig
) -> dict[str, object]:
    """Assemble the `grid_source.json` document for one search outcome.

    Emitted for a best-effort grid as readily as for a conforming one: exit 1
    still writes the grid. Only themes an emitted entry
    actually carries reach `themes`, so the map is a function of the grid
    rather than of the bank -- an unused declared theme is noise the consumer
    would have to ignore.

    Building that map here also keeps `bank.themes` itself out of the document:
    `cw_bank.parse_bank` hands back a `MappingProxyType`, which `json.dumps`
    refuses outright.
    """
    by_answer = bank.by_answer()
    clues: dict[str, dict[str, str]] = {}
    themes: dict[str, dict[str, str]] = {}
    for run in cw_grid.runs_from_rows(outcome.rows):
        entry = by_answer.get(run.text)
        theme = _screened_theme_key(entry)
        clues[run.text] = _clue_record(run.text, entry, theme)
        if theme is not None:
            # parse_bank rejects an entry naming an undeclared theme, so this
            # lookup cannot miss for any Bank that came through it.
            #
            # BOTH fields are screened here even though parse_bank screened
            # them too, and that is deliberate rather than redundant:
            # `build_document` accepts ANY Bank, including one constructed
            # directly and never passed through the parse boundary, and it is
            # the last thing between operator text and emitted bytes.
            # Screening one field and trusting the other would leave exactly
            # the half-covered seam this screen exists to close.
            info = bank.themes[theme]
            themes[theme] = {
                "label": _screened(
                    info.label, f"the label for theme {cw_text.shown(theme)}"
                ),
                "summary": _screened(
                    info.summary, f"the summary for theme {cw_text.shown(theme)}"
                ),
            }
    return {"rows": list(outcome.rows), "themes": themes, "clues": clues}


def dumps_document(document: Mapping[str, object]) -> str:
    """Serialize `document` exactly as the emitted contract requires.

    Every argument is load-bearing: `sort_keys` fixes the key order,
    `indent` fixes the shape, `ensure_ascii=False` keeps a non-ASCII theme
    label readable as itself instead of as escapes, and the appended newline
    makes the file end the way every other text file in the tree does.

    Every `<` is then written as its JSON escape (`_ESCAPED_LESS_THAN`), so
    the value a reader parses is unchanged and only those bytes differ. A
    replace over the whole text is exact: JSON's own syntax holds no `<`, so
    each one is inside a string, a key or a value, and never follows a
    backslash that opens an escape -- a backslash in the value is written
    doubled. Escaped rather than refused, because `<` is ordinary clue text.
    """
    body = json.dumps(document, indent=_JSON_INDENT, ensure_ascii=False, sort_keys=True)
    return f"{body.replace('<', _ESCAPED_LESS_THAN)}\n"


def _existing_mode(path: Path) -> int | None:
    """`path`'s permission bits, or None when there is no file there whose bits to keep.

    A symbolic link there counts as no file at all, dangling or not. The
    rename replaces the LINK and never touches its target, so the target's
    bits belong to a file this run does not write, and carrying them over
    would let a link planted at the output choose the output's permissions.
    The link's own bits describe the link, not a file, so the output takes
    what a new file takes. Hence `os.lstat`, which reads the link itself
    rather than following it.

    `FileNotFoundError` alone, deliberately: a run that may not stat its own
    output at all is a run that will not be able to write it either, and that
    belongs in the caller's `EmitError` rather than silently taking the
    umask's answer for a file that does exist.
    """
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(status.st_mode):
        return None
    return stat.S_IMODE(status.st_mode)


def _staging_name(name: str, token: str) -> str:
    """The staging file's name for an output called `name`: `.{name}.{token}.tmp`.

    The dots, the token and the suffix make it longer than the output's own
    name, so an output name close to the filesystem's limit would otherwise be
    refused at the staging open though the output itself could be written.
    Where the whole name would exceed `_NAME_MAX_BYTES`, `name` is cut short
    from the end, a whole character at a time, until it fits: splitting a
    multi-byte character would leave a fragment some volumes refuse outright.
    A name that fits is kept exactly as it is, and the token is never cut,
    because it is what leaves nothing to plant at the name in advance.

    Measured with `os.fsencode`, the bytes the open hands the kernel: UTF-8,
    with a byte no UTF-8 decoder reads -- which a POSIX command line delivers
    as a lone surrogate -- counted as that one byte rather than refused.
    """
    # The staging name with an empty stem: everything the name has to fit beside.
    budget = _NAME_MAX_BYTES - len(os.fsencode(f"..{token}.tmp"))
    widths = (len(os.fsencode(character)) for character in name)
    ends = itertools.accumulate(widths)
    kept = sum(1 for _ in itertools.takewhile(lambda end: end <= budget, ends))
    return f".{name[:kept]}.{token}.tmp"


def _stage(path: Path) -> tuple[int, Path]:
    """Open a fresh staging file beside `path`; its descriptor and its path.

    In the destination's OWN directory because `os.replace` is one atomic
    rename only within a filesystem -- staging under the system temp directory
    would turn the final step into a copy. `O_EXCL` refuses any path already
    at that name, a symlink included, so nothing can make the picture be
    written THROUGH a planted link, and the random name leaves nothing to
    plant one at.

    `_NEW_FILE_MODE` rather than `tempfile.mkstemp`, which has no mode
    parameter and creates its file readable by its creator alone. Asking the
    kernel for the mode a plain `open` asks for is what makes a new file
    umask-correct WITHOUT reading the umask: `os.umask` can only be read by
    setting it, which is a process-wide race inside the operator's own run.

    Named by `_staging_name`, which keeps the name within the filesystem's
    limit wherever the output's own name is.
    """
    name = _staging_name(path.name, secrets.token_hex(_STAGING_NAME_BYTES))
    # O_BINARY exists only on Windows, where a descriptor opened without it is in
    # text mode and the C runtime writes each "\n" as "\r\n" under `newline=`.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    staged = path.parent / name
    return os.open(staged, flags, _NEW_FILE_MODE), staged


def _write_via_temp_file(path: Path, text: str) -> None:
    r"""Write `text` to a sibling temporary file, then rename it onto `path`.

    A reader (any consumer of the file) may open the destination at any
    moment, so it is replaced in one rename rather than truncated and
    refilled -- a half-written grid would be read as a corrupt one. The
    temporary file is created in the DESTINATION's directory because a rename
    is only atomic within one filesystem, and is removed again unless the
    rename succeeded, so a failed run leaves the directory as it found it.
    The cleanup is a `finally` keyed on that success rather than an `except`
    naming a type: the write raises `UnicodeEncodeError` -- a ValueError, not
    an OSError -- on text the encoder rejects, and an `except OSError` cleanup
    would have walked past it leaving a stray temp file behind.
    `newline="\n"` pins the line ending: the platform default would rewrite
    every newline on Windows and break the byte-identical claim.

    The file keeps its permissions across the rename. `os.replace` carries the
    STAGING file's mode onto the destination, so an existing file's bits have
    to be put back on the staging file before the rename or they are gone --
    the execute bit with them, which is the one loss git would have reported.
    A file that does not exist yet has no bits to keep, and takes what a plain
    write would have given it (`_stage`); so does a symbolic link, which the
    rename replaces rather than writes through (`_existing_mode`). Both are
    read BEFORE the staging file is opened, because a `--out` naming this
    run's own staging file could not otherwise be told from the destination.

    `os.fchmod` on the DESCRIPTOR rather than `os.chmod` on the name, so the
    bits land on the file just opened and never on whatever else the name
    might be pointing at by then. Never on Windows, which has no POSIX mode
    bits to carry and, before Python 3.13, no `os.fchmod` at all: there a bare
    call raises AttributeError, not the OSError that becomes an EmitError.
    """
    mode = _existing_mode(path)
    handle, temp_path = _stage(path)
    replaced = False
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            # Skipped on Windows: no POSIX mode bits, and no os.fchmod before 3.13.
            if sys.platform != "win32" and mode is not None:
                os.fchmod(stream.fileno(), mode)  # pragma: only-on posix
            stream.write(text)
        os.replace(temp_path, path)
        replaced = True
    finally:
        if not replaced:
            temp_path.unlink(missing_ok=True)


def write_atomically(path: Path, text: str) -> None:
    r"""Write `text` to `path` atomically, as EmitError or not at all.

    Two unrelated exception types can come out of the write, and the caller
    reporting exit 2 should have to catch neither:
    `OSError` for an unusable path or a full disk, and `UnicodeError` for text
    the UTF-8 encoder refuses: `json.loads` turns a `\udXXX` escape into a lone
    surrogate, which `ensure_ascii=False` would emit raw. Every bank and grid
    string is screened for one on the way in, but this takes any text, so the
    wrap stays. Wrapping both mirrors `cw_bank.read_bank_payload`.

    Public, and not only used for the grid: the CLI's `--preview` SVG is
    written through here too, so the atomic-replace discipline and the
    error-wrapping have one home rather than one per output format.

    Named for what it does rather than `write_text`, which is `pathlib`'s own
    non-atomic method: a wrapper wearing that name reads at every call site as
    the very thing this one exists to replace.
    """
    try:
        _write_via_temp_file(path, text)
    except (OSError, UnicodeError) as exc:
        raise EmitError(f"could not write {path}: {exc}") from exc


def write_document(path: Path, document: Mapping[str, object]) -> None:
    """Serialize `document`, then write it to `path` atomically.

    The WRITE half is `EmitError` or nothing, as `write_atomically` promises.
    The SERIALIZE half is not, and the two are deliberately not merged:
    `dumps_document` is evaluated before `write_atomically` is entered, so a
    document this module did not build -- one holding a value `json` cannot
    encode -- comes out as a bare `TypeError`. That is a caller's bug rather
    than an operator's, and dressing it as an operator-facing error would put
    a wrong diagnosis on stderr. `test_emit.py`'s
    `test_touches_the_filesystem_only_after_serializing` pins that, and that
    nothing is left on disk when it happens.
    """
    write_atomically(path, dumps_document(document))
