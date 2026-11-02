r"""Strategies for the loader property suites: every kind of file an operator could hand over.

Each file strategy draws the bytes of one input file. A property writes them to
a real file and hands its path to the loader under test, which reads it exactly
as it reads the operator's own. The draws deliberately include the classes a
narrower strategy leaves out, because those are the ones a hand-edited file
has turned out to hold:

* arbitrary bytes, which need not be UTF-8 at all, and text behind a
  byte-order mark;
* characters no output can carry: lone surrogates, and the C0 and C1
  controls. In a JSON string a surrogate is written as the `\udXXX` escape
  JSON allows; in a plain text file it is written as the three bytes a
  careless encoder produces, which strict UTF-8 does not accept;
* NaN and both infinities, which `json.dumps` writes as the `NaN`, `Infinity`
  and `-Infinity` tokens `json.loads` reads back;
* an integer literal one digit past the interpreter's limit on turning digits
  into an int;
* nesting deep enough that the parser, or a later `repr` of what it built,
  runs out of stack;
* a well-formed file with exactly one field, or one line, replaced by any of
  the above: a file wrong in one place and right everywhere else is a narrow
  target that garbage alone rarely hits.

It also holds what the oracle suites re-derive without the readers: which
bytes every reader must read, a text's lines as an editor ends them, and what
a list file lists.

Named `*_fixtures.py` rather than `test_*.py` so the aggregator's discovery
skips it and it carries no floor of its own, like every `*_fixtures.py` module
here.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from hypothesis import strategies as st

#: The character a byte-order mark decodes to.
BYTE_ORDER_MARK = "\U0000feff"

#: The three line ends an editor writes.
LINE_ENDS = ("\n", "\r\n", "\r")

#: Any character, a third of the time a lone surrogate and a third of the time
#: a control character: `st.characters()` alone almost never draws a surrogate.
ANY_CHARACTER = st.one_of(
    st.characters(),
    st.characters(categories=["Cs"]),
    st.characters(categories=["Cc"]),
)

#: A short string of any characters at all, each drawn from `ANY_CHARACTER`.
#: Joined from a list rather than drawn with `st.text`, which merges the three
#: alphabets into one range of code points and loses the weighting. Measured,
#: it drew a surrogate in none of a hundred derandomized strings and in about
#: one of seven hundred random ones, where this draws one in more than half.
ANY_TEXT = st.lists(ANY_CHARACTER, max_size=8).map("".join)

#: An integer literal one digit past the limit this interpreter enforces when
#: turning digits into an int; `json.loads` raises a plain ValueError for it.
#: Read from the running interpreter rather than written as a number, because
#: the limit can be raised or switched off from the environment.
LONG_NUMBER = "9" * (sys.get_int_max_str_digits() + 1)

#: Nesting `json.loads` parses but `repr` cannot walk, and nesting the parser
#: itself cannot finish, where it raises RecursionError. Measured on CPython
#: 3.14: ten thousand levels quote cleanly and a hundred thousand overflow the
#: stack, while a million overflow it inside the parser.
DEEP = 100_000
DEEPER = 1_000_000

#: Stands in for the field `spliced` replaces. No document here holds it, and
#: `json.dumps` writes it as one quoted token that appears nowhere else.
_SLOT = "\x00slot\x00"

#: One step down a JSON document: a key into an object or an index into an array.
Step = str | int


def nested(depth: int) -> str:
    """A JSON array nested `depth` levels deep, holding nothing else."""
    return "[" * depth + "]" * depth


def encoded(text: str) -> bytes:
    """`text` as UTF-8, a lone surrogate written as the bytes a careless encoder writes."""
    return text.encode("utf-8", "surrogatepass")


def written(folder: str, content: bytes) -> Path:
    """Write `content` to a file in `folder`, byte for byte, and return its path."""
    path = Path(folder) / "input"
    path.write_bytes(content)
    return path


def _array_text(items: list[str]) -> str:
    """The JSON text of an array whose items are the JSON texts `items`."""
    return "[" + ",".join(items) + "]"


def _object_text(members: list[tuple[str, str]]) -> str:
    """The JSON text of an object with `members`, a key and a value's text each.

    A key may repeat: that is a file the reader must refuse, not one to avoid.
    """
    return "{" + ",".join(f"{json.dumps(key)}:{value}" for key, value in members) + "}"


#: Any JSON scalar, as `json.dumps` writes it. `st.floats()` draws NaN and the
#: infinities too, if rarely.
_SCALAR = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), ANY_TEXT).map(
    json.dumps
)

#: A JSON string of nothing but lone surrogates and control characters, which
#: no output of the tool can carry.
_UNCARRIED = st.text(
    st.characters(categories=["Cs", "Cc"]), min_size=1, max_size=4
).map(json.dumps)

#: The values a narrower strategy never drew, each as JSON text: NaN and the
#: infinities, a string of surrogates and controls, the long number, and the
#: two depths of nesting. Drawn as often as every other scalar together, since
#: they are what this module is for.
_EDGE = st.one_of(
    st.sampled_from((math.nan, math.inf, -math.inf)).map(json.dumps),
    _UNCARRIED,
    st.just(LONG_NUMBER),
    st.sampled_from((DEEP, DEEPER)).map(nested),
)

#: The text of any JSON value, built from the values above and from arrays and
#: objects of them. Built as text rather than dumped from a value, because the
#: long number and the deep nesting cannot make the trip: `json.dumps` can no
#: more write them than the reader can take them.
JSON_TEXT = st.recursive(
    st.one_of(_SCALAR, _EDGE),
    lambda inner: st.one_of(
        st.lists(inner, max_size=3).map(_array_text),
        st.lists(st.tuples(ANY_TEXT, inner), max_size=3).map(_object_text),
    ),
    max_leaves=4,
)


def _members(
    value: object, path: tuple[Step, ...] = ()
) -> Iterator[tuple[tuple[Step, ...], object]]:
    """`value` and every value inside it, each with its path, depth first."""
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _members(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _members(child, (*path, index))


def _slotted(value: object, path: tuple[Step, ...]) -> object:
    """A copy of `value` with whatever lies at `path` replaced by `_SLOT`."""
    if not path:
        return _SLOT
    head, rest = path[0], path[1:]
    if isinstance(value, dict):
        return {
            key: _slotted(child, rest) if key == head else child
            for key, child in value.items()
        }
    # Every path `_members` yields runs through objects and arrays alone, so a
    # value that is not an object here is an array.
    items = cast(list[object], value)
    return [
        _slotted(child, rest) if index == head else child
        for index, child in enumerate(items)
    ]


def spliced(document: object, path: tuple[Step, ...], fragment: str) -> str:
    """The JSON text of `document` with the value at `path` written as `fragment`.

    `fragment` is JSON text, so it can be a value `json.dumps` could never
    write, such as the long number or the deep nesting.
    """
    return json.dumps(_slotted(document, path)).replace(json.dumps(_SLOT), fragment)


def json_files(document: dict[str, object]) -> st.SearchStrategy[bytes]:
    """A JSON input file: `document`, `document` with one field replaced, or any value.

    The whole document is never the replaced field: that is the any-value
    branch already. A string field gets a branch of its own, replaced by one
    no output can carry: drawing a field and a value independently, from
    every field and every kind of value, reaches that pairing only by luck.
    """
    members = tuple(_members(document))[1:]
    paths = tuple(path for path, _ in members)
    text_paths = tuple(path for path, value in members if isinstance(value, str))
    return input_files(
        st.one_of(
            st.just(json.dumps(document)),
            st.builds(spliced, st.just(document), st.sampled_from(paths), JSON_TEXT),
            st.builds(
                spliced, st.just(document), st.sampled_from(text_paths), _UNCARRIED
            ),
            JSON_TEXT,
        )
    )


@st.composite
def _one_line_wrong(draw: st.DrawFn, lines: tuple[str, ...]) -> str:
    """`lines` as a file, one of them replaced by any text, every line end alike."""
    index = draw(st.integers(min_value=0, max_value=len(lines) - 1))
    changed = list(lines)
    changed[index] = draw(ANY_TEXT)
    end = draw(st.sampled_from(LINE_ENDS))
    return end.join(changed) + end


def line_files(lines: tuple[str, ...]) -> st.SearchStrategy[bytes]:
    """A line-by-line input file: `lines`, `lines` with one replaced, any text, or JSON.

    The JSON branch is a file of the wrong kind altogether, and brings the
    long and deep values with it as lines far longer than any real one.
    """
    return input_files(
        st.one_of(
            st.just("\n".join(lines) + "\n"),
            _one_line_wrong(lines),
            _one_line_wrong(lines),
            ANY_TEXT,
            JSON_TEXT,
        )
    )


#: The three ways an input file is made from its text, and how often each is
#: drawn: the text as written four times in six, and once each behind a
#: byte-order mark and replaced by any bytes at all, because those two are
#: mostly refused before the reader parses a thing. Hypothesis's search does
#: not run the draws in those proportions: beside a JSON body it reaches the
#: any-bytes form in only a few examples of a hundred, which is why every file
#: property also pins a file that is not UTF-8 as an `@example`.
_AS_WRITTEN = "as written"
_BEHIND_A_MARK = "behind a byte-order mark"
_ANY_BYTES = "any bytes"
_FORMS = (_AS_WRITTEN,) * 4 + (_BEHIND_A_MARK, _ANY_BYTES)


@st.composite
def input_files(draw: st.DrawFn, text: st.SearchStrategy[str]) -> bytes:
    """The bytes of an input file: `text`, `text` behind a byte-order mark, or any bytes.

    The form is drawn first, from `_FORMS`, rather than by `st.one_of` over the
    three: `st.one_of` lifts every branch of a mapped `st.one_of` into its own,
    so the branches of `text` would outnumber the other two and the weights
    above would not hold.
    """
    form = draw(st.sampled_from(_FORMS))
    if form == _ANY_BYTES:
        return draw(st.binary(max_size=64))
    body = draw(text)
    return encoded(BYTE_ORDER_MARK + body if form == _BEHIND_A_MARK else body)


def json_texts(
    scalars: st.SearchStrategy[object], keys: st.SearchStrategy[str]
) -> st.SearchStrategy[str]:
    """JSON text built from `scalars` and from arrays and objects of them.

    `keys` name the members of the objects, drawn independently, so an object
    can write one key twice. A suite passes the keys its format uses, so the
    objects drawn often take that format's shape.
    """
    return st.recursive(
        scalars.map(json.dumps),
        lambda inner: st.one_of(
            st.lists(inner, max_size=4).map(_array_text),
            st.lists(st.tuples(keys, inner), max_size=4).map(_object_text),
        ),
        max_leaves=12,
    )


def line_lists(lines: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    """A list's text: up to six drawn lines, each closed by a line end an editor writes."""
    closed = st.tuples(lines, st.sampled_from(LINE_ENDS))
    return st.lists(closed, max_size=6).map(
        lambda drawn: "".join(line + end for line, end in drawn)
    )


#: The three line ends as one pattern, the pair first so it is never read as a
#: carriage return followed by an empty line. Written here rather than read from
#: the code under test, so an oracle splitting with it checks the reader's split.
_LINE_END = re.compile("|".join(sorted(LINE_ENDS, key=len, reverse=True)))


def editor_lines(text: str) -> list[str]:
    """`text` split where an editor ends a line, and nowhere else."""
    return _LINE_END.split(text)


def readable(data: bytes) -> bool:
    """Whether every reader must read a small regular file holding `data`.

    Decided from the bytes alone: UTF-8, with no byte-order mark before the
    text. What a reader then makes of the text is its own rule. Kind and size
    are the other reasons a reader refuses a file, and a file a suite writes
    itself is a regular one far under the size cap.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not text.startswith(BYTE_ORDER_MARK)


def listed_lines(data: bytes) -> list[str]:
    """What a list file holding `data` lists, re-derived without the readers.

    Its editor lines, each stripped, leaving out a line that is then blank or
    opens with `#`, the comment prefix every list reader shares.
    """
    lines = (line.strip() for line in editor_lines(data.decode("utf-8")))
    return [line for line in lines if line and not line.startswith("#")]
