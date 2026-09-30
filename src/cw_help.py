"""cw_help: how `--help` renders -- its formatter, its option prose, and its epilogs.

The entry point parses; this module holds what `--help` SAYS: the epilogs under
each subcommand's options, the formatter every parser renders with, and an option's
own help wherever that help runs to prose. All of it lives here so the entry point
stays a table of option declarations, under the 500 lines this project keeps every
Python file to: its `add_argument` calls stay there, where the whole command-line
surface reads in one place, and the prose that would spend its lines on paragraphs
comes here. A ONE-LINE help stays at its call, where the flag and its description can
still be read together.

Nothing `--help` prints from here states a Python version floor, and nothing should:
the floor is `requires-python` in `pyproject.toml`, and the linter and type-checker
targets in that file follow it. Should prose ever state it, it belongs in the entry
point's module docstring, which describes the script itself, not in help text the
script imports from here.

`%(prog)s` in these strings is expanded by argparse when the help is formatted,
wherever the string was defined.
"""

from __future__ import annotations

import argparse


class HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
):
    """Render each optional's live default, and leave the epilog as written.

    Two stock formatters composed. `ArgumentDefaultsHelpFormatter` keeps each
    default auto-derived from the live `default=` rather than typed into help
    text that drifts. `RawDescriptionHelpFormatter` stops argparse reflowing
    the epilog, which would rewrap its worked invocation into something nobody
    can paste.

    Its behavior of its own is leaving two defaults unstated. A `None` one: to
    argparse `None` means "not given", so `(default: None)` tells the reader
    nothing. The defaults stay `None` rather than becoming `[]` or `()` because
    measured on this floor, a tuple on an `append` option raises the moment
    the flag is given, and a list is handed back by reference when it is not.

    And a required option's, whatever it is: no run can ever fall back to it.
    argparse itself stopped stamping one only in 3.13, and this project's
    floor, stated in pyproject.toml's requires-python, is below that -- so
    without this the same parser would render differently on the floor.
    """

    def _get_help_string(self, action: argparse.Action) -> str | None:
        """Return *action*'s help, with the default suffix unless none is owed."""
        if action.default is None or action.required:
            return action.help
        return super()._get_help_string(action)


#: Each subcommand's epilog, passed to its subparser by `build_parser`.
FILL_EPILOG = """\
Run order: write a bank.json first (one "themes" map, one "entries" list),
then fill a grid from it. --preview draws the result in the same run; the
preview subcommand re-draws any grid_source.json later, including one this
tool did not write.

Worked example -- a 13x13 grid at the default density, with a picture:

  %(prog)s --bank bank.json --out grid_source.json --seed 1 \\
      --rows 13 --cols 13 --min-blocked 30 --max-blocked 45 \\
      --preview preview.svg

Size is required and has no default: the caller states it, with --rows and
--cols or with a --source grid or --mask picture that already has one, because
any default would be a guess at what the consumer of the grid wants. Density is
the two bounds above, in percent BLOCKED cells -- raise --min-blocked for a
sparser grid, lower --max-blocked for a denser one. A denser grid is a demand
on the bank rather than on search effort: it needs LONGER answers, not more
time.

--bank repeats: a bank every puzzle shares and a small bank of words only one
grid needs merge, in the order given, into the one bank the run draws on. An
identical record in two banks is kept once; an answer or theme two banks
record differently is refused, naming both files.

A bank answer may be written as it is said -- "HELLO THERE", "ATTA-BOY",
"JACK-O'-LANTERN" -- and is laid, and named by every flag, by its letters
alone: HELLOTHERE. A clued one's clue ends with its word lengths, as
"Greeting (5,5)". Two spellings of one answer are refused, naming both.

Start from a grid you already have with --source grid_source.json: every
letter and entry of it stays where it is, a half-written word a bank answer
can finish is finished, and the fill grows into its blocked cells. The grid
is the source's size unless --rows or --cols grows it: the source sits at the
top-left, so each of its cells keeps its (row, column), and a size under the
source's own is refused. With --absorb-entries a source entry the bank holds
may also grow into a longer bank answer covering it, as JANE into JANET; every
pin, and every entry only the source declares, still stays exactly as it is.

The report also names every pair of placed answers that joins, either way
round, into a bank answer or a line of a --phrases list, which may be written
with spaces or hyphens: "atta-boy" joins ATTA and BOY. The pairs are there
for you to judge; they never take part in choosing the grid. Given
--excluded-terms, it also WARNS about any two placed answers that join,
either way round, into a barred term; the grid and the exit code stay the
same.

Exit codes: 0 a conforming grid, 1 a best-effort grid that missed a constraint
(still written, and still drawn), 2 the run could not happen -- including two
--bank files that disagree or are one file, a --phrases list that cannot be
read or holds no usable line, and an --out or
--preview that is a directory, is in a directory that does not exist, or names
a file the run reads or the other output writes.
"""

PREVIEW_EPILOG = """\
Renders an existing grid_source.json and runs no search, so it takes no seed,
no size and no density -- the grid it is handed already carries all three.

  %(prog)s --source grid_source.json --out preview.svg --cell 64

The caption stamps what the grid itself says: its size, its achieved blocked
percentage and its per-theme counts. The seed and the requested density are
absent, because a file this tool did not generate cannot honestly report them.

Exit codes: 0 on a render, 2 on a --cell out of range, 2 on a --feature that
carries a position, names one answer twice, or names an answer the grid does
not hold, and 2 on a source it cannot read, cannot decode as UTF-8, cannot
parse, or that is not a coherent grid, and 2 on an --out that is the source, a
directory, or in a directory that does not exist. There is no exit 1 --
preview has no constraint to miss, and a grid whose CONTENT is questionable is
drawn rather than refused.
"""


SHADE_EPILOG = """\
Runs on a grid that already exists, so it takes no bank, no seed and no size.
It has two modes, and exactly one of --words / --word selects which:

  %(prog)s --source grid_source.json --words words.txt --min-length 6
  %(prog)s --source grid_source.json --word NOTEBOOK --out hidden.svg

--words RANKS every word of a plain text list (one word per line, blank lines
and #-comments ignored, case-folded) that this grid can spell by shading cells
whose letters, read in normal reading order, give that word. Each candidate is
reported with its length, the rows it spans, and its CLUSTERING -- the number
that matters. Low is good: 0 means one letter per row, the way a real
crossword's shaded squares scatter. High means the letters bunch inside one
answer, and the shading would read as a corrupted entry rather than as a bonus.
An answer already standing in the grid is a repeat rather than a bonus, and
--exclude-grid-answers drops those, naming every one it drops.

Candidacy alone is a weak filter -- most short words match on any real grid --
so --min-length is the lever that makes the list readable, and the ranking then
puts the best of what is left on top. --top caps the printed list; 0 prints all.

--word emits ONE named word's chosen cells, in 0-based (row, column) and in a
paste-ready JSON form, and with --out draws the grid with exactly those cells
shaded. --cell sizes that render and is consulted only when --out is given.

Refused rather than accepted and ignored: neither or both of --words / --word,
and --out in the ranked-search mode, which has no single word to draw.

Exit codes: 0 candidates were found (or the named word was placed), 1 the
search ran and found none, 2 the run could not happen -- an unreadable or
incoherent grid, an unreadable word list, one holding no usable word at all, a
contradictory configuration, a --word this grid cannot spell, or an --out
that is the grid, a directory, or in a directory that does not exist.
"""


GAPS_EPILOG = """\
Runs on a grid that already exists, so it takes no seed and no size. It writes
nothing into the grid: a blocked cell only ever becomes a letter the ordinary
way, by an answer joining the bank and `fill` running again.

  %(prog)s --source grid_source.json --bank bank.json
  %(prog)s --source grid_source.json --words filler_2.txt --out gaps.svg

For every blocked cell it derives the FULL runs a letter there would create --
welding included, so a gap between two answers demands the whole joined line
rather than its two neighbors -- and reports the pattern each run must match,
with the new cell written as `?`. Both axes must be satisfied by ONE letter
when a cell creates a run in each, which is what makes such a gap a bigger ask.

--bank and --words are optional and UNION into one vocabulary; a bank is the
JSON `fill` takes, a word list the plain one-per-line file `shade` takes.
--bank repeats too, and its banks merge exactly as `fill`'s do.
Given them, each gap is sorted into one you can already pay for -- the letter
and the answers are named -- or one needing a new answer of a stated pattern.
Without them every demand is reported as unmet, which is honest but far less
useful.

A gap whose fill would WELD two runs retires the answers it swallows, so those
are counted and left out unless --include-absorbing asks for them. A gap whose
letter would join no entry at all is excluded outright and counted.

Given --bank or --phrases, the report also names every pair of the grid's
entries that joins, either way round, into a bank answer or a phrase-list line;
--words is filler for a gap and joins nothing.

--top caps the listed gaps; 0 lists every one. --out draws exactly the gaps
this run listed, marking each blocked cell with a ring, and --cell sizes it.

Adding an answer to the bank may change NOTHING on its own: `fill` keeps the
densest grid it finds within --look-ahead nodes of the first one inside its
density window, and a grid you are reading gaps from is already in one. The
report derives the --max-blocked ceiling that makes the search reach for a gap;
re-run `fill` with it.

Exit codes: 0 this grid has a gap worth reporting, 1 the analysis ran and it
has none, 2 the run could not happen -- an unreadable or incoherent grid; an
unreadable bank, word list, phrase list or --mask picture; two banks that
disagree or are one file; a list holding no usable line; a --mask picture with
a blank line, no rows, a ragged row or a character other than '.' and 'X', or
one that masks every cell, is not the grid's size, or forbids a letter the
grid already holds; a contradictory configuration; or an --out naming a file
the run reads, a directory, or a path in a directory that does not exist.
"""


# ------------------------------------------------------------------------
# Each option's help text, for the options whose help runs to prose.
#
# A ONE-LINE help stays at its own `add_argument` call, where a reader meets
# the flag and its description together; only prose long enough to need a
# paragraph comes here, so the entry point stays a table of option
# declarations. `tests/test_cli_help_prose.py` holds that line, and pins each
# constant below to exactly one option, since a constant here does not sit
# beside the flag it describes.
#
# No string below states a default, and none should: `HelpFormatter` stamps
# the live one wherever one is owed.
# ------------------------------------------------------------------------

#: `fill`'s prose options, in the order `--help` lists them.
FILL_SOURCE_HELP = (
    "Existing grid_source.json to start from: its letters stay exactly as "
    "they are, and so do its entries unless --absorb-entries, and the fill "
    "grows into its blocked cells. It "
    "sits at the grid's top-left, and the grid is its size unless --rows "
    "or --cols grows it."
)
FILL_ABSORB_ENTRIES_HELP = (
    "Beside --source, let a source entry the bank holds grow into a longer "
    "bank answer lying along all of it, at either end or welded to another "
    "entry; pins, and entries only the source declares, stay exact."
)
FILL_PREVIEW_HELP = (
    "Path for the grid's SVG, the finished picture; omitted writes only "
    "--out, which preview can draw later."
)
FILL_FEATURE_HELP = (
    "Answer that must be placed, and is shaded in the render; repeat it "
    "for several. ANSWER@ROW,COL,DIR pins its first letter to that "
    "0-based cell, running across or down."
)
FILL_TIME_BUDGET_HELP = (
    "Wall-clock seconds before a best-effort return; 0 drops the clock "
    "and needs --max-steps, giving a run that repeats on any machine."
)
FILL_EXCLUDED_TERMS_HELP = (
    "Path to a barred-term list; matching bank entries are dropped, and "
    "two placed answers joining into a term are reported as a warning."
)
FILL_LOOK_AHEAD_HELP = (
    "Nodes to keep searching past the first conforming grid for a better "
    "one: more letters, then more --prefer answers, then a better worst "
    "bank rating, then more matching pairs under --prefer-symmetry, then "
    "more themed entries, then fewer grown --absorb-entries source "
    "entries; 0 keeps the first."
)
FILL_PREFER_SYMMETRY_HELP = (
    "Rank grids that tie on letters, --prefer answers and worst rating by "
    "how many cell pairs match, letter or block, under this symmetry. A "
    "preference, never a filter: no grid is refused for its balance."
)
FILL_ISLAND_LETTERS_HELP = (
    "Lay a lone letter, from A I X U Y in the order given, in each blocked "
    "cell that touches a letter only at a corner. Off unless given."
)
FILL_PHRASES_HELP = (
    "Plain list of words and phrases two placed answers may join into; "
    "the report names each pair, and nothing is placed or scored by it. "
    "Repeatable."
)

#: `preview --feature`. Deliberately not shared with FILL_FEATURE_HELP:
#: `fill` takes an ANSWER@ROW,COL,DIR position and `preview` refuses one,
#: so one string serving both would document a syntax one of them rejects.
PREVIEW_FEATURE_HELP = (
    "Answer whose cells are shaded, located in the given grid; repeat it "
    "for several. It takes no @ROW,COL,DIR position."
)

#: `gaps --phrases`, whose wording is its own for the same reason.
GAPS_PHRASES_HELP = (
    "Plain list of words and phrases two entries may join into; the "
    "report names each pair. Repeatable."
)

#: `fill --mask`. Prefixed, and deliberately NOT shared with the `gaps` one
#: below: only `fill` chooses a grid size, so only here can a picture supply
#: one. A single string serving both would tell a `gaps` reader about two flags
#: that subcommand does not have -- the reason `PREVIEW_FEATURE_HELP` is its own
#: string too.
FILL_MASK_HELP = (
    "Path to a plain-text picture of the grid, one line per row: '.' a "
    "free cell, 'X' one that may never hold a letter, a #-prefixed line "
    "an annotation. It must be exactly the size of the grid, and "
    "supplies --rows and --cols when neither is given."
)

#: `gaps --mask`, whose wording is its own for that reason: the size is the
#: --source grid's, and a masked cell is counted rather than listed as a gap.
GAPS_MASK_HELP = (
    "Path to a plain-text picture of the grid, one line per row: '.' a "
    "free cell, 'X' one that may never hold a letter, a #-prefixed line "
    "an annotation. It must be exactly the --source grid's size; those "
    "cells are counted apart rather than reported as gaps."
)

#: `--empty-blocks`, registered on all four renderers at once and so
#: carrying no subcommand prefix: the flag means the same in each.
EMPTY_BLOCKS_HELP = (
    "Draw every blocked cell as a hole rather than a black square, "
    "so the grid's outline reads as a shape. Changes the drawing "
    "only: the grid, its density and the caption are unaffected."
)
