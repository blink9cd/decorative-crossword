"""cw_json: parses the JSON text of a file the operator wrote, or says why it cannot.

Both JSON inputs this tool reads (a word bank and a grid file) are parsed
here, because `json.loads` fails in more ways than `json.JSONDecodeError` names
and a reader catching only that one lets the rest escape as a traceback. That
exits 1, which this tool also uses for "no conforming grid was found", so a
crash would read as a verdict about the grid. Three failures are reachable
from a file anyone can hand-edit:

* malformed text, as `json.JSONDecodeError`;
* an integer literal longer than the interpreter's digit limit, as a plain
  `ValueError` raised from inside the parser;
* nesting deep enough to exhaust the stack while parsing, as `RecursionError`,
  which is not a `ValueError` at all.

A fourth is not a parse failure at all. Nesting a little shallower parses, and
then overflows the stack as soon as a refusal quotes the value, and every
refusal in the bank and grid validators quotes the value at fault. A quote
keeps only the start of the value, but it is cut from the whole `repr`, which
recurses once per level however little of it the message keeps. So the depth
is bounded here, once, where an untrusted payload is born, rather than at each
refusal downstream.

A fifth the parser does not report at all: a key written twice in one object.
That is grammatical JSON (RFC 8259 leaves which one counts to each reader)
and Python's `json` keeps the last and says nothing, so a hand edit that leaves
an old line behind (a clue or a label written twice) would be overruled
silently. It is refused as a `RepeatedKeyError`, naming the key and the object
that repeats it, as a path from the top of the file, so a repeat among hundreds
of bank entries can be found. The parser reports no position, so the path is
found by walking the parsed value once the parse is done, and only when a
repeat was seen: a walk bounded by the nesting, like the depth check's.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Iterator

import cw_text

#: The deepest a file may nest, counting every object and array on the way
#: down. Neither format needs more than three (the document, a map or list in
#: it, and a record in that), so anything deeper is malformed somewhere. The
#: margin lets a merely misshapen file reach the validator that names its
#: actual fault, and the ceiling keeps quoting any parsed value far inside the
#: interpreter's recursion limit.
MAX_DEPTH = 64

#: The one refusal both depth failures share: the fix is the same whichever of
#: them a file happened to reach.
_TOO_DEEP = (
    f"it nests more than {MAX_DEPTH} objects and arrays deep, and neither a "
    "bank nor a grid file needs more than three"
)

#: What `_deeper_than` reads from an iterator it has used up. Its own object,
#: because every value a JSON member can hold, `None` included, is a member.
_EXHAUSTED = object()

#: One step from a value to a member of it: an object's key or an array's index.
type _Step = str | int

#: Each object that writes a key twice, by identity: the object itself, held so
#: that no later object can be given its identity while the parse runs on, and
#: the first key it repeats.
type _Repeats = dict[int, tuple[dict[str, object], str]]


class RepeatedKeyError(ValueError):
    """A file writes one key more than once in an object: grammatical JSON, refused.

    Its own type so a reader can word it apart from a parse failure: calling
    such a file invalid would send a person hunting for a syntax error that is
    not there. The message is a predicate, "writes the key ...", for the reader
    to put its file's name in front of.
    """


def loads(text: str) -> object:
    """`text` parsed as JSON, or ValueError saying why it cannot be used.

    Every failure is a `ValueError`, so each reader wraps one type into its own
    refusal. A decode error and the digit limit already are one and pass
    through as they are; a repeated key is the subclass `RepeatedKeyError`.
    The depth is judged first, so the walk that locates a repeat only ever
    meets a value this module has bounded.
    """
    repeats: _Repeats = {}
    hook = functools.partial(_members, repeats)
    try:
        payload: object = json.loads(text, object_pairs_hook=hook)
    except RecursionError as exc:
        raise ValueError(_TOO_DEEP) from exc
    if _deeper_than(payload, MAX_DEPTH):
        raise ValueError(_TOO_DEEP)
    if repeats:
        raise RepeatedKeyError(_repeat_refusal(payload, repeats))
    return payload


def _members(repeats: _Repeats, pairs: list[tuple[str, object]]) -> dict[str, object]:
    """One JSON object's members, recording in `repeats` a key written twice in it.

    The parser calls this for every object in the file, innermost first, with
    the members in the order the file writes them. Filling the dict in that
    same order is what keeps an object of distinct keys exactly the dict
    `json.loads` alone would build, key order included.

    Left to `json.loads`, the last of two same-named members would win: a bank
    entry written with two answers would be read as the second. Which one the
    operator meant is a guess, so the file is refused instead, but not from
    here, which sees the object's members and not where the object sits. It is
    recorded by identity, holding the object too. The same key in two
    different objects (an `answer` in every entry) is what every file
    holds, and is not a repeat.
    """
    members: dict[str, object] = {}
    for key, value in pairs:
        if key in members and id(members) not in repeats:
            repeats[id(members)] = (members, key)
        members[key] = value
    return members


def _repeat_refusal(payload: object, repeats: _Repeats) -> str:
    """The refusal for the first object in `payload` that `repeats` records.

    First in the order the file writes them. An object a repeated key threw
    away is recorded too, but no path reaches it. The object whose repeat
    threw it away is recorded as well, and so on outward to one that is still
    in `payload`, so the walk always finds one.
    """
    key, path = _first_recorded(payload, repeats)
    return (
        f"writes the key {cw_text.shown(key)} more than once in {_described(path)}, "
        "and which one counts would be a guess"
    )


def _first_recorded(
    payload: object, repeats: _Repeats
) -> tuple[str, tuple[_Step, ...]]:
    """The key and the path of the first object `repeats` records that `payload` holds.

    A depth-first walk in the order the file writes its members, holding one
    iterator for each level it is inside and never a list of the values: its
    stack is as deep as the nesting, which `loads` has bounded before this
    runs, so a file that is one long array costs no more to walk than to
    parse. Only objects and arrays are entered, and the walk stops at the
    first recorded one. `payload` is walked as the one member of a list, whose
    index is dropped from the path returned.
    """
    pending: list[tuple[tuple[_Step, ...], Iterator[tuple[_Step, object]]]] = [
        ((), iter(((0, payload),)))
    ]
    while True:
        path, members = pending[-1]
        for step, child in members:
            if isinstance(child, (dict, list)):
                reached = (*path, step)
                if id(child) in repeats:
                    return repeats[id(child)][1], reached[1:]
                pending.append((reached, _members_of(child)))
                break
        else:
            pending.pop()


def _members_of(
    value: dict[str, object] | list[object],
) -> Iterator[tuple[_Step, object]]:
    """Each member of an object or an array, with the key or index reaching it."""
    if isinstance(value, dict):
        return iter(value.items())
    return enumerate(value)


def _described(path: tuple[_Step, ...]) -> str:
    """Where `path` leads, for a person: each key quoted, each index from 0.

    Every step is quoted through `cw_text.shown`, as the repeated key itself
    is, so a key holding a control character or a bidi override prints
    escaped.
    """
    if not path:
        return "the top-level object"
    return "the object at " + "".join(f"[{cw_text.shown(step)}]" for step in path)


def _deeper_than(payload: object, limit: int) -> bool:
    """Whether `payload` nests more than `limit` objects and arrays deep.

    An explicit stack rather than recursion, because its whole job is to
    measure a value that may be too deep for recursion to walk. The stack
    holds one iterator per object or array still open on the way down, so its
    length is the depth reached and its cost is the nesting's, never the
    width's: an entry kept for each sibling cost about twice what parsing did
    on a long array of containers, and several times that on one of numbers.
    The bottom iterator yields `payload` alone, so the top-level value is met
    at depth one like any other.
    """
    open_levels: list[Iterator[object]] = [iter((payload,))]
    while open_levels:
        child = next(open_levels[-1], _EXHAUSTED)
        if child is _EXHAUSTED:
            open_levels.pop()
        elif isinstance(child, (dict, list)):
            if len(open_levels) > limit:
                return True
            members = child.values() if isinstance(child, dict) else child
            open_levels.append(iter(members))
    return False
