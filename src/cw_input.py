r"""cw_input: reads an input file's text, refusing what is not one, and splits its lines.

Every file this tool reads -- a bank, a grid file, an excluded-terms list, a
mask, a word or phrase list -- is read here, because a path on a command line
can name a FIFO, a device or a terminal as easily as a file, and each is a
hazard read as one: a FIFO waits for a writer that may never come, and a device
such as `/dev/zero` never runs out, so the run would hang, or grow until memory
ran out, instead of stopping with a diagnostic. So only a regular file is read,
and only one no larger than `MAX_INPUT_BYTES`.

`/dev/stdin` gets no rule of its own. It is judged by what it names, like any
other path: a terminal or a pipe is not a regular file and is refused, while
stdin redirected from a file IS that file, and is read and capped like one.

The file's type and size are taken from the open descriptor, never from a
second look at the path, which a file swapped in between the look and the open
would get past. That is why the open cannot wait: opening a FIFO for reading
normally blocks until a writer arrives, before any check could run, so the
file is opened non-blocking. It is also opened so that a terminal it names
does not become this process's controlling terminal.

What comes back is exactly what opening the file as UTF-8 text and reading it
returns: a strict decode, with each `\r\n` and each lone `\r` read as `\n`.
The one exception is a file that begins with a byte-order mark, which is
refused instead. UTF-8 has no byte order to mark, so the mark is an editor's
signature rather than text, and read as text it becomes part of the first
line: the first term of a barred-term list would then match nothing, and
nothing would say so. It is refused rather than dropped, as a byte that is not
UTF-8 is: the fix is one save away, and a reader that quietly repaired the
file would be reading something other than what the operator wrote.

`editor_lines` splits text into the lines an editor shows. It ends a line at
`\r` itself rather than relying on the translation above, because a parser
may be handed text that never passed through this reader.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

#: Bytes in a mebibyte, the unit the cap is stated in.
_MIB = 1024 * 1024

#: The largest input file this tool reads, in bytes. A ceiling far above any
#: curated input -- a full dictionary word list is a few megabytes, a real bank
#: far less -- whose job is to put an end to a read that would otherwise have
#: none.
MAX_INPUT_BYTES = 32 * _MIB

#: How much one read asks for, so a small file costs a small buffer rather
#: than one the size of the cap.
_CHUNK_BYTES = _MIB

#: How an input is opened: read-only; non-blocking, so opening a FIFO returns at
#: once; never as the controlling terminal; and in binary mode where the
#: platform has a text mode, so the only newline handling is the one below. A
#: flag the platform lacks is 0, which leaves it out.
_OPEN_FLAGS: int = (
    os.O_RDONLY
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_NOCTTY", 0)
    | getattr(os, "O_BINARY", 0)
)


#: The character a byte-order mark decodes to.
_BYTE_ORDER_MARK = "\U0000feff"


class UnreadableInput(OSError):
    """A path this tool will not read, or a file whose text it will not take.

    Not a regular file, past the size cap, or text that begins with a
    byte-order mark. An `OSError`, so each reader's existing `except OSError`
    turns it into that reader's own refusal, exactly as it does a missing file.
    """


def read_input_text(path: Path) -> str:
    """The text of the input file at `path`, read as strict UTF-8.

    Raises `UnreadableInput` when `path` is not a regular file, is larger
    than `MAX_INPUT_BYTES` or begins with a byte-order mark, any other
    `OSError` the open or the read raises (a missing file, a permission
    error), and `UnicodeDecodeError` for bytes that are not UTF-8.
    """
    descriptor = os.open(path, _OPEN_FLAGS)
    try:
        data = _capped_contents(path, descriptor)
    finally:
        os.close(descriptor)
    text = data.decode("utf-8")
    if text.startswith(_BYTE_ORDER_MARK):
        raise UnreadableInput(
            f"{path} begins with a byte-order mark (U+FEFF); "
            "save it as UTF-8 without one"
        )
    return _universal_newlines(text)


def editor_lines(text: str) -> tuple[str, ...]:
    r"""The lines of `text`, each without its line end, split where an editor splits.

    A line ends at `\n`, `\r\n` or a lone `\r`, and nowhere else, so a line
    number a reader reports is the one the operator's editor shows. Not
    `str.splitlines`, which also ends a line at `\v`, `\f`, `\x1c` to `\x1e`,
    `\x85`, U+2028 and U+2029: split there, a mask's line numbers run ahead
    of the editor's, and one word list line becomes two words. Such a
    character stays inside its line, for the reader's own rules to judge.

    Otherwise it is what `str.splitlines` returns: a final line end closes the
    last line rather than opening an empty one, and an empty text has no
    lines.
    """
    lines = _universal_newlines(text).split("\n")
    # `split` always leaves an element after the last `\n`; it is a line only
    # if the text goes on past that line end.
    if not lines[-1]:
        lines.pop()
    return tuple(lines)


def _capped_contents(path: Path, descriptor: int) -> bytes:
    """Every byte of the file open at `descriptor`, if it may be read at all.

    The size is checked twice. The descriptor's own status refuses an
    oversized file before a byte of it is read; reading one byte past the cap
    refuses a file that grew after that status was taken.
    """
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode):
        raise UnreadableInput(f"{path} is not a regular file")
    if status.st_size > MAX_INPUT_BYTES:
        raise UnreadableInput(_too_large(path))
    data = _read_at_most(descriptor, MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise UnreadableInput(_too_large(path))
    return data


def _too_large(path: Path) -> str:
    """The refusal for a file past the cap, stated in the unit the cap is set in."""
    return (
        f"{path} is larger than the {MAX_INPUT_BYTES // _MIB} MiB an input file may be"
    )


def _read_at_most(descriptor: int, limit: int) -> bytes:
    """Up to `limit` bytes from `descriptor`, fewer if the file ends first."""
    chunks: list[bytes] = []
    remaining = limit
    while remaining:
        chunk = os.read(descriptor, min(remaining, _CHUNK_BYTES))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _universal_newlines(text: str) -> str:
    r"""`text` with each `\r\n`, and then each lone `\r`, read as `\n`.

    What reading in text mode does. The pair goes first: translating every
    `\r` first would turn one `\r\n` into two line ends.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")
