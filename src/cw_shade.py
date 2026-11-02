"""cw_shade: which cells to shade so their letters spell a hidden word.

A finished decorative crossword can shade some of its cells gray so that those
letters, read in normal reading order, spell one more answer: a bonus threaded
through the puzzle rather than lying along a line of it. This module answers the
two questions that go with that: *which words can this grid spell at all*, and
*which cells should be shaded for one of them*.

**The first question is nearly free, and is therefore not the product.** A word
is spellable when its letters appear, in order, as a subsequence of the grid's
letters read row-major with blocks skipped. On a real 9x9 that admits a couple
of hundred words out of a thousand, so candidacy alone filters almost nothing:
a tool that stopped there would hand back a list its reader could not act on.

**The second question is the load-bearing one, and the obvious answer to it is
wrong.** Taking the first occurrence of each letter (greedy, shorter, and
apparently correct) clusters the picks inside whichever answer happens to
carry them, and the result reads as a corrupted entry rather than as a hidden
word; on a real grid it shaded four consecutive letters of a nine-letter across
answer. So the cells are chosen by a shortest path over `(letter index, cell)`
minimizing the clustering penalty below, which charges a step for looking like
part of an existing entry. `tests/test_shade.py`'s `TestGreedyIsNotEnough`
fails against greedy on the cells rather than on the score, because greedy is
what a later reader reaches for.

The penalty is the tool's opinion and the thing a person cannot eyeball. A
score of 0 means one letter per row, which is how a real crossword's shaded
squares scatter; a high one means the letters bunch, and is the tool saying
*do not use this word*: an answer already standing in the grid scores in the
dozens or the hundreds, exactly as it should.

Nothing here reads a bank, a network or any other project's data: the inputs
are a grid's rows and a list of words, and that is the whole of it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import cw_answer
import cw_grid
import cw_input

#: A step whose two cells share a row and sit one column apart. The heaviest
#: term by a wide margin, and the reason the whole module exists: consecutive
#: cells of one row are what make shading read as a corrupted answer instead of
#: as a hidden word. Such a step is orthogonally touching as well, so it pays
#: TOUCHING_PENALTY on top: two separate observations about one step rather
#: than a fourth number to keep in step with these three.
SAME_ROW_ADJACENT_PENALTY = 10

#: A step whose two cells merely share a row, however far apart. Much lighter:
#: two shaded squares on one line of a real puzzle are ordinary, and only
#: become a problem when they are neighbors.
SAME_ROW_PENALTY = 3

#: A step whose two cells are orthogonally touching: Manhattan distance at
#: most TOUCHING_DISTANCE. It catches the vertical version of the same fault,
#: which the two row terms above cannot see at all.
TOUCHING_PENALTY = 6

#: The Manhattan distance at or under which two cells count as touching. Named
#: so the comparison and the docstring above cannot drift apart.
TOUCHING_DISTANCE = 1

#: The column gap that makes two cells in one row neighbors.
ADJACENT_COLUMN_GAP = 1

#: What a single same-row neighboring step costs: the worst thing one step
#: can be. Derived from the two terms it pays rather than written out again, so
#: it is the readable threshold between "these cells scatter" and "these cells
#: bunch" without being a fourth tunable number. The threshold is the tool's
#: judgment on a placement's whole clustering, not a detector of that one step:
#: lighter steps reach it between them (three vertically touching steps do,
#: with no same-row pair at all), and a placement that clusters that much is
#: called bunched whichever steps paid for it.
NEIGHBORING_STEP_PENALTY = SAME_ROW_ADJACENT_PENALTY + TOUCHING_PENALTY

#: A line of the word list whose first non-blank character is this is a note,
#: not a word. Mirrors `cw_bank`'s own comment convention for `--excluded-terms`
#: so one text-file format is not read two different ways in one tool.
_COMMENT_PREFIX = "#"


class ShadeError(ValueError):
    """Raised when a word list cannot be read.

    Its own type rather than a borrowed `cw_bank.BankError`: a word list is not
    a bank, shares none of its schema, and a diagnostic that named the bank
    would point the operator at the wrong file.
    """


@dataclass(frozen=True)
class Placement:
    """One word, the cells chosen to shade for it, and what that choice costs.

    `cells` is in reading order and holds exactly one cell per letter: the
    letters are picked as a subsequence, so no cell can serve two of them and
    the cell count is identically the word's length. It is reported as the
    letter count alone rather than as two columns of the same number.
    """

    word: str
    cells: tuple[tuple[int, int], ...]
    clustering: int

    @property
    def rows_spanned(self) -> int:
        """How many distinct rows the shaded cells lie in.

        The plain-language companion to `clustering`: a reader who does not
        want to reason about the penalty can read this instead, and a hidden
        word worth using generally spans about as many rows as it has letters.
        """
        return len({row for row, _ in self.cells})


@dataclass(frozen=True)
class HiddenWordSearch:
    """One search over a word list: what ranked, and what did not, and why.

    The three non-candidate counts exist so the headline is never a silent
    one. A word list that produced two candidates out of a thousand has said
    something about the list, and a report that showed only the two would
    leave the operator unable to tell a thin list from a tight grid.
    """

    candidates: tuple[Placement, ...]
    too_short: int
    excluded_answers: tuple[str, ...]
    unspellable: int


def lettered_cells(rows: Sequence[str]) -> tuple[tuple[int, int, str], ...]:
    """Every lettered cell of `rows` as `(row, column, letter)`, in reading order.

    Row-major with blocks skipped, which is the order a solver reads a shaded
    message in and therefore the order the whole subsequence test is against.
    """
    return tuple(
        (row_index, col_index, char)
        for row_index, row in enumerate(rows)
        for col_index, char in enumerate(row)
        if char != cw_grid.BLOCK
    )


def clustering_penalty(previous: tuple[int, int], current: tuple[int, int]) -> int:
    """What one step between two shaded cells costs; 0 is a clean scatter.

    Three observations, scored independently of the order of the pair:

    * the cells share a row and are one column apart: the fault this whole
      module exists to avoid, and the heaviest term;
    * failing that, they merely share a row: much lighter, because two shaded
      squares on one line are ordinary until they are neighbors;
    * separately, they orthogonally touch, which is the only term that sees the
      vertical version of the same bunching.

    The first two are alternatives of one question ("how do these two sit in
    their row"), so a same-row neighboring step pays the heavier of them and
    not both; the touching term is a different question and adds to whichever
    answered the first.
    """
    row_gap = abs(previous[0] - current[0])
    col_gap = abs(previous[1] - current[1])
    penalty = 0
    if row_gap == 0:
        penalty += (
            SAME_ROW_ADJACENT_PENALTY
            if col_gap == ADJACENT_COLUMN_GAP
            else SAME_ROW_PENALTY
        )
    if row_gap + col_gap <= TOUCHING_DISTANCE:
        penalty += TOUCHING_PENALTY
    return penalty


def _positions_for(
    cells: Sequence[tuple[int, int, str]], word: str
) -> list[list[int]] | None:
    """Each letter's candidate cell indices, or None if some letter has none.

    Returning None up front saves building a table whose first empty column
    would end the walk anyway, and it is what makes the "grid cannot spell this
    at all" case a single cheap answer rather than a dynamic-programming run.
    """
    positions = [
        [index for index, (_, _, char) in enumerate(cells) if char == letter]
        for letter in word
    ]
    return None if any(not column for column in positions) else positions


def _cheapest_reachable(
    cells: Sequence[tuple[int, int, str]],
    reached: dict[int, tuple[int, int | None]],
    candidates: Sequence[int],
) -> dict[int, tuple[int, int | None]]:
    """One step of the walk: the cheapest way to reach each of `candidates`.

    `reached` maps a cell index to `(cost so far, the index it came from)`.
    Both loops run in ascending index order and improve on a strict `<`, so a
    tie keeps the earliest predecessor and the earliest cell: two runs must
    produce byte-identical output, and a tie broken by a mapping's iteration
    order would not.
    """
    step: dict[int, tuple[int, int | None]] = {}
    for index in candidates:
        best: tuple[int, int | None] | None = None
        for previous, (cost_so_far, _) in reached.items():
            if previous >= index:
                continue
            cost = cost_so_far + clustering_penalty(
                cells[previous][:2], cells[index][:2]
            )
            if best is None or cost < best[0]:
                best = (cost, previous)
        if best is not None:
            step[index] = best
    return step


# fuzz-target
def place_word(rows: Sequence[str], word: str) -> Placement | None:
    """The cheapest cells to shade so they spell `word`, or None if they cannot.

    A shortest path over `(letter index, cell index)`: the letters must be
    taken as a subsequence of `lettered_cells(rows)`, so each chosen cell comes
    strictly later in reading order than the one before it, and the path's
    length is the sum of `clustering_penalty` over its steps.

    Returns None when the grid cannot spell `word` in reading order at all,
    including for an empty word, which spells nothing and would otherwise come
    back as a placement of no cells.

    Coordinates are 0-based `(row, column)` from the top-left cell, indexing
    `rows[r][c]`, which is the convention the rest of this project reports
    shaded cells in.
    """
    cells = lettered_cells(rows)
    if not word:
        return None
    positions = _positions_for(cells, word)
    if positions is None:
        return None
    table: list[dict[int, tuple[int, int | None]]] = [
        {index: (0, None) for index in positions[0]}
    ]
    for column in positions[1:]:
        step = _cheapest_reachable(cells, table[-1], column)
        if not step:
            return None
        table.append(step)
    end = min(table[-1], key=lambda index: (table[-1][index][0], index))
    chosen: list[tuple[int, int]] = []
    index: int | None = end
    for level in reversed(table):
        # `index` is not None on any level of a table built above: every entry
        # after the first records the predecessor it was reached from, and the
        # first level's None ends the walk after its own cell is taken.
        assert index is not None
        chosen.append(cells[index][:2])
        index = level[index][1]
    return Placement(
        word=word,
        cells=tuple(reversed(chosen)),
        clustering=table[-1][end][0],
    )


def grid_answers(rows: Sequence[str]) -> frozenset[str]:
    """Every answer already standing in `rows`, in either direction.

    A word the grid already holds is a repeat rather than a bonus, so this is
    what `--exclude-grid-answers` screens against. Derived through
    `cw_grid.runs_from_rows` rather than re-scanned here, so this module cannot
    disagree with the rest of the project about what an entry is.

    A frozenset because every caller asks only whether a word is in it; nothing
    iterates it, so no hash-seeded order can reach output.
    """
    return frozenset(run.text for run in cw_grid.runs_from_rows(rows))


def _ranking_key(placement: Placement) -> tuple[int, int, str]:
    """Best first: least clustered, then longest, then alphabetical.

    Length breaks the clustering tie because a longer hidden word is a better
    bonus, and on a real grid the cheap end of the ranking is a large block of
    words that all score zero. The alphabetical last resort is what makes the
    order total, and therefore reproducible.
    """
    return (placement.clustering, -len(placement.word), placement.word)


def search_hidden_words(
    rows: Sequence[str],
    words: Iterable[str],
    *,
    min_length: int,
    exclude_grid_answers: bool,
) -> HiddenWordSearch:
    """Rank every word of `words` this grid can spell, and count what it cannot.

    The three exclusions are checked in the order they are cheapest and most
    informative, and each word is counted under the first that applies: a word
    below `min_length` is counted short even if it is also an answer in the
    grid, because the floor is the operator's own filter and reporting one word
    under two headings would make the counts fail to add up.

    `exclude_grid_answers` names what it removed rather than only counting it:
    an answer already in the grid is the exclusion an operator most often wants
    to see, since it is usually the word they were about to choose.
    """
    answers = grid_answers(rows) if exclude_grid_answers else frozenset()
    placements: list[Placement] = []
    excluded: list[str] = []
    too_short = 0
    unspellable = 0
    for word in words:
        if len(word) < min_length:
            too_short += 1
            continue
        if word in answers:
            excluded.append(word)
            continue
        placement = place_word(rows, word)
        if placement is None:
            unspellable += 1
            continue
        placements.append(placement)
    return HiddenWordSearch(
        candidates=tuple(sorted(placements, key=_ranking_key)),
        too_short=too_short,
        excluded_answers=tuple(excluded),
        unspellable=unspellable,
    )


def _screen_word(word: str) -> str | None:
    """Why `word` cannot be a hidden word, or None when it can be one.

    The same two rules `cw_bank` applies to a bank answer (at least
    `cw_grid.MIN_RUN` letters, and A-Z only) because a hidden word is read
    off the same grid and the grid holds nothing else.
    """
    if len(word) < cw_grid.MIN_RUN:
        return f"shorter than the {cw_grid.MIN_RUN}-letter minimum"
    if not all("A" <= letter <= "Z" for letter in word):
        return "holds a character outside A-Z"
    return None


# fuzz-target
def load_word_list(
    path: Path, *, close_up: bool = False
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Read the candidate word list at `path`: `(usable words, skipped pairs)`.

    One word per line, a line ending where an editor ends one
    (`cw_input.editor_lines`). Blank lines, and lines whose first non-blank
    character is `#`, are ignored silently: they are how an operator
    annotates a list, and reporting them as skipped words would bury the
    reports that matter. Every other line is stripped and uppercased, so a
    list typed in lower case works without a conversion step, and duplicates
    collapse to their first appearance.

    With `close_up`, a line's whitespace, hyphens and apostrophes are removed
    before it is screened (`cw_answer.grid_form`, the one rule every answer
    comparison reads), so `atta boy` and `atta-boy` read as `ATTABOY`. That is
    how `--phrases` is read:
    a phrase is written the way it is said, and two entries join with nothing
    between them. Off by default, because a hidden word or a gap's filler is
    one word, and welding a line's two words into one would quietly answer a
    question the operator did not ask.

    A line that is not a usable word after that (too short, or holding
    anything outside A-Z) is skipped and returned by name and reason rather
    than failing the run: fail only the bad item, never drop an ineligible one
    silently, report its specific reason and count it. A list nobody
    hand-curated will eventually carry a hyphen or a space, and refusing the
    whole run over one of them would be hostile.

    Not modeled on `--excluded-terms`: `cw_excluded_terms.load_excluded_terms`
    screens no lines at all, and this tool's malformed-input handler,
    `cw_bank._parse_answer`, raises.

    Nothing is dropped quietly (the report names every skipped line), and a
    list that yields no usable word at all is the caller's refusal to make, not
    this reader's.

    Wraps `OSError` and `UnicodeDecodeError` into `ShadeError` for the reason
    `cw_excluded_terms.load_excluded_terms` does, including why the second is
    named: it is a `ValueError` rather than an `OSError`, so a list saved in a
    legacy code page would otherwise escape the CLI's refusal set as a
    traceback.
    """
    try:
        text = cw_input.read_input_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise ShadeError(f"could not read word list {path}: {exc}") from exc
    words: dict[str, None] = {}
    skipped: list[tuple[str, str]] = []
    for line in cw_input.editor_lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith(_COMMENT_PREFIX):
            continue
        word = (cw_answer.grid_form(stripped) if close_up else stripped).upper()
        reason = _screen_word(word)
        if reason is not None:
            skipped.append((word, reason))
            continue
        # A dict keyed by the word, not a list plus a membership set: it
        # collapses duplicates and keeps first-seen order in one structure,
        # and insertion order is a language guarantee rather than a hash one.
        words[word] = None
    return tuple(words), tuple(skipped)
