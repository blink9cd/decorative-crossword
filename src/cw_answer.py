"""cw_answer: what an answer's written form may be, and the letters it lays in the grid.

A bank answer may be written as more than one word (`HELLO THERE`,
`ATTA-BOY`, `JACK-O'-LANTERN`), but a grid holds letters only, so every
comparison in this project reads an answer's grid form, the letters left once
its spaces, hyphens and apostrophes close up. `grid_form` is that one
normalization, applied wherever an operator types an answer: the bank, and
`--feature`, `--prefer`, `--phrases` and `--excluded-terms`. Keeping it in one
function is the point: a second copy that closed up one character fewer would
let the same answer match in one place and miss in another.

`is_spelling` is the shape a bank answer must have, and `enumeration` the word
lengths a multi-word answer's clue carries, as a crossword prints them.

Pure and dependency-free, so `cw_bank`, `cw_feature` and the command modules
can all import it without a cycle.
"""

from __future__ import annotations

import re

#: The characters that close up besides whitespace: a hyphen joins two words,
#: and an apostrophe sits inside one.
_JOINERS = str.maketrans("", "", "-'")

#: What each word break prints as in an enumeration: a space between words is
#: a comma, a hyphen stays a hyphen. The apostrophe is absent on purpose: it
#: separates no words, and the letters either side of it count as one word.
_ENUMERATION_BREAKS = {" ": ",", "-": "-"}

_APOSTROPHE = "'"

#: One written word: capital letters, with an apostrophe allowed between two
#: runs of them or at either end, never two together. `'TIS`, `O'`, `'N'`.
_WORD = r"'?[A-Z]+(?:'[A-Z]+)*'?"

#: A whole written answer: words joined by exactly one space or one hyphen.
#: Anchored by `fullmatch`, so nothing may lead or trail.
_SPELLING = re.compile(rf"{_WORD}(?:[ -]{_WORD})*")

#: The rule `_SPELLING` enforces, in the words a refusal quotes to the operator.
SPELLING_RULE = (
    "letters A-Z in words joined by single spaces or hyphens, with an "
    "apostrophe allowed inside or at either end of a word but never two together"
)


# fuzz-target
def grid_form(text: str) -> str:
    """`text` with its whitespace, hyphens and apostrophes removed, and nothing else.

    Case is left alone on purpose: `--feature` and `--prefer` take an answer
    verbatim, so `--feature chalk` names `chalk`, not `CHALK`. A caller that
    folds (`--phrases`, the barred terms) does so itself. All whitespace, not
    only the space, so a tab or doubled space inside a `--phrases` line closes
    up too.
    """
    return "".join(text.split()).translate(_JOINERS)


# fuzz-target
def is_spelling(text: str) -> bool:
    """Whether `text` is a well-formed written answer; `SPELLING_RULE` says what that is.

    Shape only: whether enough letters are left once it closes up is
    `cw_grid.MIN_RUN`, which `cw_bank` checks.
    """
    return _SPELLING.fullmatch(text) is not None


def enumeration(spelling: str) -> str | None:
    """The word lengths of a multi-word `spelling`, as `(5,5)` or `(4-1-7)`, else None.

    A single word (`CHEMEX`, and `O'CLOCK` too) has none, since only a word
    break makes an answer's letters read as more than one word. Letters are
    counted; an apostrophe is neither counted nor a break.
    """
    lengths: list[str] = []
    count = 0
    for char in spelling:
        if char in _ENUMERATION_BREAKS:
            lengths.append(f"{count}{_ENUMERATION_BREAKS[char]}")
            count = 0
        elif char != _APOSTROPHE:
            count += 1
    if not lengths:
        return None
    return f"({''.join(lengths)}{count})"


def with_enumeration(clue: str, spelling: str | None) -> str:
    """`clue` ending with `spelling`'s enumeration, where it has a clue and one.

    An empty clue stays empty: the page then shows the theme summary alone, and
    a bare `(5,5)` there would be a clue nobody wrote. A clue already ending in
    the enumeration is left as written rather than given it twice.
    """
    lengths = None if spelling is None else enumeration(spelling)
    if not clue or lengths is None or clue.endswith(lengths):
        return clue
    return f"{clue} {lengths}"
