"""cw_pairs: pairs of entries that join into another word -- reported, never scored.

Two entries can be better together than apart: `WEB` meeting `SITE` reads *web
site*, and `ATTA` above `BOY` reads *atta boy*. No measure of a single word sees
either, so nothing here tries to score them. What a tool can do is NAME them --
every pair of entries whose two texts, joined, spell a word the operator already
vouched for, a bank answer or a line of a `--phrases` list -- and leave the
judgment to the person reading the report.

Three rulings shape it, each measured against those two pairs rather than chosen
in the abstract:

- **Anywhere in the grid.** On the grid they came from, both pairs touch only at
  a corner: neither crosses and neither shares a line, so a rule looking for
  crossings or line neighbors misses both. There is no position rule at all;
  each line prints where its two entries start, and whether they read together
  is the reader's call.
- **Either order.** `SITE` sits a row above `WEB`, so reading order spells
  `SITEWEB`. A join that reads the same both ways (`AB` beside `AB`) is one line.
- **A curated vocabulary only.** A join may spell only what the operator's own
  files hold. No dictionary is consulted: an uncurated word source is what
  admits junk, and this tool's bank exists to keep it out.

It is a REPORT by construction: what it returns is pairs and text, never a
number, so there is nothing a search could rank a grid by.

The same joins are read once more against the opposite kind of list: the terms
`--excluded-terms` bars. That screen reads each bank entry alone, so two clean
entries can still spell a barred term together; `barred_lines` names every such
join as a WARNING, and a `--phrases` line that is itself a term is skipped, so
the report never offers a barred word as wordplay. A join matches only when it
IS a term once the term's spaces close up -- the screen's whole-word rule as it
reads an answer, because a join is shaped like one -- so a term buried inside a
longer join warns nothing, the over-reach whole-word matching exists to
prevent. It warns and never refuses: what to do about a join is the operator's
call, and a refusal would take the grid away before they could see it.

Output order is `cw_grid.runs_from_rows` order -- each entry against every entry
after it, its own join first -- so two runs print byte-identical blocks. Every
vocabulary is a frozenset used for membership only and never iterated.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import cw_answer
import cw_grid
import cw_text

#: Detail lines sit one indent under their heading, as in every report block.
_INDENT = "  "

#: What a join must spell. Named once because the heading and the "none"
#: sentence both say it, and the two must not come to disagree.
_JOIN_TARGET = "a bank answer or a --phrases entry"

#: Opens the warning block. It says WARNING where the pairs block does not
#: because a barred join is the one thing the operator asked never to see.
_BARRED_HEADING = (
    "WARNING - entries that join into an --excluded-terms term (0-based row, column):"
)

#: Why a `--phrases` line that is itself a barred term is skipped.
BARRED_REASON = "is an --excluded-terms term"


@dataclass(frozen=True)
class Phrases:
    """Every usable `--phrases` line, the lines skipped, and the barred terms.

    `words` is for membership only and is never iterated, so its hash order
    cannot reach output. `skipped` is `(line, reason)` pairs list by list: each
    list's own skips in file order, then its lines the barred terms dropped.
    `barred` is the `--excluded-terms` terms closed up, empty when none were
    given, and like `words` is for membership only.
    """

    words: frozenset[str]
    skipped: tuple[tuple[str, str], ...]
    barred: frozenset[str] = frozenset()


#: No `--phrases` given: nothing to join into beyond the bank, nothing skipped.
NO_PHRASES = Phrases(frozenset(), ())


@dataclass(frozen=True)
class Pair:
    """Two entries whose texts, `first` then `second`, spell one vocabulary word."""

    first: cw_grid.Run
    second: cw_grid.Run

    @property
    def joined(self) -> str:
        """The word the pair spells: `first`'s text, then `second`'s."""
        return self.first.text + self.second.text


def closed_up_terms(terms: Iterable[str]) -> frozenset[str]:
    """`terms` the way a join is compared with them: closed up, uppercased.

    A phrase closes up to meet a join -- `web site` meets `WEB` and `SITE` -- so
    a barred term has to close up the same way, by the same rule
    (`cw_answer.grid_form`), or a term written with a space or a hyphen could
    never match the join it names.
    """
    return frozenset(cw_answer.grid_form(term).upper() for term in terms)


def screen_phrases(
    listed: Sequence[str], barred: frozenset[str]
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """`listed` split into the lines kept and the barred ones, each with its reason.

    A line is barred when it IS a term, the rule a join is held to, so a phrase
    that merely holds a barred word is kept. Both halves keep `listed`'s order.
    """
    kept = tuple(line for line in listed if line not in barred)
    dropped = tuple((line, BARRED_REASON) for line in listed if line in barred)
    return kept, dropped


def _orders(one: cw_grid.Run, other: cw_grid.Run) -> tuple[Pair, ...]:
    """Both ways round, or one way when the two orders spell the same word.

    `AB` beside `AB`, or `AB` beside `ABAB`, joins identically either way, and
    two lines naming the same join would read as two findings.
    """
    if one.text + other.text == other.text + one.text:
        return (Pair(one, other),)
    return (Pair(one, other), Pair(other, one))


def _pairs_among(
    runs: Sequence[cw_grid.Run], vocabulary: frozenset[str]
) -> tuple[Pair, ...]:
    """Every pair of distinct `runs` whose join is in `vocabulary`, in run order."""
    return tuple(
        pair
        for index, one in enumerate(runs)
        for other in runs[index + 1 :]
        for pair in _orders(one, other)
        if pair.joined in vocabulary
    )


# fuzz-target
def find_pairs(rows: Sequence[str], vocabulary: frozenset[str]) -> tuple[Pair, ...]:
    """Every pair of entries in `rows` that joins, either way round, into `vocabulary`.

    The entries are the grid's own runs, so a lone letter -- an island, or a
    stray in a hand-edited grid -- belongs to no entry and never pairs.
    """
    return _pairs_among(cw_grid.runs_from_rows(rows), vocabulary)


def _entry(run: cw_grid.Run) -> str:
    """One entry as a pair line names it: its text, direction and start cell."""
    return f"{run.text}, {run.direction} from ({run.row}, {run.col})"


def _pair_line(pair: Pair) -> str:
    """One pair as a detail line: both entries, and the word they spell."""
    return f"{_INDENT}{_entry(pair.first)} + {_entry(pair.second)} = {pair.joined}"


def _found_lines(pairs: Sequence[Pair]) -> list[str]:
    """The pairs under their heading, or the one sentence saying there are none."""
    if not pairs:
        return [f"Answer pairs: none join into {_JOIN_TARGET}."]
    heading = (
        f"Answer pairs that join into {_JOIN_TARGET}, never scored "
        "(0-based row, column):"
    )
    return [heading] + [_pair_line(pair) for pair in pairs]


def _skipped_lines(skipped: Sequence[tuple[str, str]]) -> list[str]:
    """The phrase lines that could not be used, each with its reason."""
    if not skipped:
        return []
    return [f"--phrases lines skipped ({len(skipped)}):"] + [
        f"{_INDENT}{cw_text.visible(line)} - {reason}" for line, reason in skipped
    ]


def pair_lines(
    rows: Sequence[str], answers: Iterable[str], phrases: Phrases
) -> list[str]:
    """The answer-pairs report block, joining against `answers` and `phrases`.

    A grid holding no entries gets no sentence about pairs: "none join" is
    vacuously true of an empty grid and would read as a finding. Its skipped
    phrase lines are still named, because a line dropped silently is how an
    operator comes to believe a list was read when it was not.
    """
    runs = cw_grid.runs_from_rows(rows)
    vocabulary = frozenset(answers) | phrases.words
    found = _found_lines(_pairs_among(runs, vocabulary)) if runs else []
    return found + _skipped_lines(phrases.skipped)


def barred_lines(rows: Sequence[str], phrases: Phrases) -> list[str]:
    """The warning block: every pair of entries in `rows` joining into a barred term.

    Empty when no join is barred, with no "none" sentence: a check that reads
    only whole joins cannot vouch for the grid, and a line saying nothing was
    barred would read as though it had.
    """
    pairs = find_pairs(rows, phrases.barred)
    if not pairs:
        return []
    return [_BARRED_HEADING] + [_pair_line(pair) for pair in pairs]
