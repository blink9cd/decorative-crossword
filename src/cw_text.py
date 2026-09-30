"""cw_text: the characters no output of this tool can carry, and how the report shows text.

This tool writes operator text to three sinks: the report on a terminal, the
SVG, and the grid file. A terminal reads a C0 or C1 control, or DEL, as a
command rather than text -- an escape sequence can retitle the window, erase
lines already printed, or wrap a name in a hyperlink pointing anywhere. XML 1.0
admits none of the C0 block but tab, line feed and carriage return, no
surrogate and neither U+FFFE nor U+FFFF, however they are written, so one in a
theme label leaves an SVG no parser will open. And a lone surrogate has no
UTF-8 encoding, so it cannot be written at all.

Those characters are the refusal set, with two answers chosen by who owns the
text's shape. A bank and a grid file follow a schema this tool defines, so a
string in one that holds such a character is refused where it is read
(`unsafe_character`, through `cw_config.forbidden_clue_fragment`). A word list
is free text whose unusable lines are skipped and named in the report, so a
skipped line is printed with each such character escaped (`visible`): escaped
rather than dropped, so the reader can see the line held something odd instead
of taking a silently shortened line for the real one.

What `visible` escapes is the refusal set plus the bidi controls. A bidi
control is legal text in a label, so it is not refused. In the SVG it reaches
no further than the line of text that holds it: in the legend, the label
alone; in the caption, the rest of that line, since the grid's size and
blocked percentage come before every label. Printed, it reorders the rest of
the report line, which could then show the reader something other than what
it holds -- so the report escapes one wherever it prints a skipped line or a
bank theme label.

A refusal names the value at fault, and quotes one read from a file with
`shown`: as `repr` writes it, which escapes every one of those characters, and
cut short past `SHOWN_MAX_CHARS`. The cut is there because such a value is as
long as the file made it, and a quote of a label a megabyte long is a megabyte
of stderr burying the one sentence that says what is wrong. An option's value
may be named as given instead: the command line already bounds its length.
Whatever a refusal names, its message is printed through `visible`
(`cw_command_base.refuse`, and argparse's own error line alike), so a path or
an argument holding a character a terminal would obey is shown escaped.
"""

from __future__ import annotations

import re

#: The refusal set, as the body of a regular-expression character class: the
#: C0 controls, DEL and the C1 controls, the surrogates, and U+FFFE/U+FFFF. A
#: format character such as a soft hyphen or a bidi control is not in it: each
#: is legitimate in a label.
_REFUSAL_SET = r"\x00-\x1f\x7f-\x9f\U0000d800-\U0000dfff\U0000fffe\U0000ffff"

#: The bidi controls, as a character-class body: the Arabic letter mark, the
#: left-to-right and right-to-left marks, the embeddings and overrides, and
#: the isolates.
_BIDI_CONTROLS = (
    r"\U0000061c\U0000200e\U0000200f"
    r"\U0000202a-\U0000202e\U00002066-\U00002069"
)

#: The most characters of a value a refusal quotes: enough for the start of
#: any value an operator must find in a file -- a label, a clue, the opening
#: of a list where an object belongs -- and few enough that a huge one cannot
#: bury the sentence around it.
SHOWN_MAX_CHARS = 200

#: One character of the refusal set.
_REFUSED = re.compile(f"[{_REFUSAL_SET}]")

#: One character `visible` escapes: the refusal set plus the bidi controls,
#: built from the two bodies above rather than listed again.
_ESCAPED_BY_VISIBLE = re.compile(f"[{_REFUSAL_SET}{_BIDI_CONTROLS}]")


def unsafe_character(text: str) -> str | None:
    """Name the first character of `text` no output can carry, or None if none is there."""
    found = _REFUSED.search(text)
    if found is None:
        return None
    return f"the character U+{ord(found.group()):04X}"


def visible(text: str) -> str:
    r"""`text` with each character a report must not print raw written as an escape.

    Those are the refusal set plus the bidi controls, each written as Python
    writes it in `ascii`, as `\x1b`. Every other character is left as it is,
    accents, soft hyphens and all: the rule is about what a terminal would
    obey rather than show, not about what is not ASCII.
    """
    return _ESCAPED_BY_VISIBLE.sub(lambda found: ascii(found.group())[1:-1], text)


def shown(value: object) -> str:
    """`value` as a refusal quotes it: its `repr`, cut after `SHOWN_MAX_CHARS` characters.

    `repr` because it already writes every character a terminal would obey --
    a C0 or C1 control, a bidi control, a lone surrogate -- as an escape, so the
    quote is safe to print whatever the value holds; a cut that falls inside an
    escape leaves printable text all the same. A repr past the cap keeps its
    first `SHOWN_MAX_CHARS` characters and states the whole one's length, as
    `... (1000005 characters)`, so a cut quote is never taken for the value.
    Not `reprlib`, which shortens even a short list or object: a refusal about
    a short value keeps the words it had.
    """
    whole = repr(value)
    if len(whole) <= SHOWN_MAX_CHARS:
        return whole
    return f"{whole[:SHOWN_MAX_CHARS]}... ({len(whole)} characters)"
