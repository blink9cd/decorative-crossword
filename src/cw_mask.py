"""cw_mask: the cells a grid may never letter, drawn as a plain-text picture.

A mask is how a grid takes a SHAPE. The operator draws the silhouette they want
-- a heart, a diamond, the outline of a letter -- one line per grid row, and
every cell they mark is one no letter may ever occupy. What is left over fills
as any grid does: the fill stays freeform inside the mask, so every run of two
or more is still an answer the bank supplied. A mask only ever FORBIDS; it
never obliges a cell to be filled, which is what separates it from a block
pattern.

The picture's alphabet is two characters and a comment:

- `FREE` (".") -- the grid may do as it likes here.
- `MASKED` ("X") -- never a letter.
- a line whose first character is `#` is an annotation and not a row, so an
  operator can title the shape and label its parts.

`.` reads as "free" here and as a BLOCKED cell in an emitted grid
(`cw_grid.BLOCK`), which is the one inversion in the file and is deliberate: a
picture is read as ink on paper, where the marked cells are the shape and the
unmarked ones are the paper. A JSON mirror of `grid_source.json` was rejected
for the same reason -- a shape is unreadable through quotes, and `.` already
means something else there -- and `#` was rejected as the marked character
because it is this project's comment prefix in every line reader it has.

Every refusal is exit 2 and names the line of the FILE at fault, comments
counted, because that is the number the operator's editor shows. The picture is
held to being rectangular, non-empty, no more than `cw_grid.MAX_SIDE` cells
either way, and not wholly masked; the last of those is refused because a mask
that forbids every cell forbids every letter, and it is also the one picture
that would leave the density denominator at zero.

The result is a size and a set of cells, never a third cell state: `cw_grid.Grid`
is strictly two-valued and the search mutates one of them, so the mask travels
on `FillConfig` as an immutable set of coordinates and is consulted, never
stored in a board. The one place a masked cell is momentarily spelled as a
character is a line view derived for `cw_place._fits_line`, and `STAMP` is the
character it takes there.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import cw_grid
import cw_input
import cw_text

#: A cell the grid may use as it likes.
FREE = "."

#: A cell that may never hold a letter.
MASKED = "X"

#: A line whose FIRST character is this is an annotation rather than a row.
#: Only the first character, and never a trailing one, for the reason
#: `cw_excluded_terms._COMMENT_PREFIX` gives: a trailing-comment rule would
#: silently truncate a row.
_COMMENT_PREFIX = "#"

#: The character a masked cell takes in a row or column string derived for
#: `cw_place._fits_line`, which accepts a cell only when it is `cw_grid.BLOCK`
#: or the letter wanted there. So any character that is neither of those
#: rejects a placement with no new logic, and this is the one that reads as
#: struck out. It must NOT be `MASKED`: "X" is a letter a bank may legitimately
#: want, and a stamp a placement could match would forbid nothing.
STAMP = "#"

#: The size `FillConfig.mask_size` carries when no mask was given. No real
#: mask can spell it -- a picture with no rows is refused -- which is what lets
#: one field answer both "was a mask given" and "how big was the picture".
#: Named here, where the refusal that guarantees it lives, so the config's check
#: and the CLI's construction cannot come to disagree about what "no mask"
#: looks like.
NO_MASK_SIZE = (0, 0)


class MaskError(ValueError):
    """Raised when a mask file cannot be read, or is not a picture.

    One type for the whole input boundary this module owns, the way
    `cw_bank.BankError` covers the bank's: a caller reporting exit 2 catches
    one name rather than one per refusal.
    """


@dataclass(frozen=True)
class Mask:
    """One read picture: the grid it describes, and the cells it forbids.

    `rows` and `cols` are the picture's own size, which `cells` alone cannot
    tell -- a mask forbidding nothing is a legal picture, and an empty set says
    nothing about how big it was. The size is the FINAL grid's, growth
    included: a mask sizes the grid a fill ends on, never the source it starts
    from.

    `cells` is for membership only. It is frozen, and the search consults it at
    every node, so nothing downstream may iterate it on a path that reaches
    emitted output -- a set's iteration order is `PYTHONHASHSEED`-dependent and
    this tool's output is byte-identical across runs.
    """

    rows: int
    cols: int
    cells: frozenset[tuple[int, int]]


def _read_picture(path: Path) -> str:
    """The text of the mask file at `path`, or raise MaskError.

    `UnicodeDecodeError` is named beside `OSError` for the reason
    `cw_excluded_terms.load_excluded_terms` names it: it is a `ValueError`
    rather than an `OSError`, so a mis-encoded picture would otherwise escape
    the CLI's refusal set as a traceback.
    """
    try:
        return cw_input.read_input_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise MaskError(f"could not read mask file {path}: {exc}") from exc


def _picture_rows(name: str, lines: Iterable[str]) -> tuple[tuple[int, str], ...]:
    """Each row of the picture with its 1-based FILE line number, comments dropped.

    Trailing whitespace is trimmed, so an invisible trailing space and a
    carriage return left by another host's line endings cannot change a row's
    width. Leading whitespace is NOT trimmed: it would shift the row, so it is
    left to be reported as the unknown character it is.

    A blank line is refused wherever it appears, rather than only between two
    rows. A blank line in a picture could mean a row of no cells or a
    separator, and a reader guessing between them is how a picture silently
    becomes a different shape; a comment line gives the operator the visual
    break without the ambiguity.
    """
    rows: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if line.startswith(_COMMENT_PREFIX):
            continue
        row = line.rstrip()
        if not row:
            raise MaskError(
                f"mask file {name} line {number} is blank: every line is either a "
                f"{_COMMENT_PREFIX} comment or one grid row, and a blank line could "
                "mean either a row of no cells or a separator"
            )
        rows.append((number, row))
    return tuple(rows)


def _masked_columns(name: str, number: int, row: str) -> tuple[int, ...]:
    """The 0-based columns `row` masks, refusing any character that is neither mark.

    The column in the message is 1-based, like the line number, because both
    are there to be found in an editor.
    """
    masked: list[int] = []
    for index, char in enumerate(row):
        if char == MASKED:
            masked.append(index)
        elif char != FREE:
            raise MaskError(
                f"mask file {name} line {number} column {index + 1} holds "
                f"{cw_text.shown(char)}: a row holds only {cw_text.shown(FREE)} "
                f"(free) or {cw_text.shown(MASKED)} (never a letter)"
            )
    return tuple(masked)


def _cells(
    name: str, rows: Sequence[tuple[int, str]], cols: int
) -> frozenset[tuple[int, int]]:
    """Every masked cell of `rows`, holding each row to the width `cols`.

    The width is checked before the characters, so a ragged picture is reported
    as that rather than as whichever stray character the short row happens to
    end near -- the width is the fault, and fixing it is what the operator
    must do first.
    """
    found: set[tuple[int, int]] = set()
    for index, (number, row) in enumerate(rows):
        if len(row) != cols:
            raise MaskError(
                f"mask file {name} line {number} is {len(row)} cells wide but the "
                f"picture's first row is {cols}: every row is one grid row, so a "
                "ragged picture has no size"
            )
        found.update((index, col) for col in _masked_columns(name, number, row))
    return frozenset(found)


# fuzz-target
def parse_mask(text: str, name: str) -> Mask:
    """The picture `text` draws, or raise MaskError naming `name` and the line.

    `name` is what a refusal calls the input -- the file's path, as the
    operator wrote it on the command line. Separate from `load_mask` so the
    parse is exercised without a file, which is what lets the property suite
    feed it arbitrary text.

    The lines are split where an editor splits them (`cw_input.editor_lines`),
    so the line number a refusal names is the one the operator's editor shows.
    """
    rows = _picture_rows(name, cw_input.editor_lines(text))
    if not rows:
        raise MaskError(
            f"mask file {name} holds no rows: a mask is a picture of the grid, one "
            f"line per row, so a file of nothing but {_COMMENT_PREFIX} comments "
            "describes no grid"
        )
    cols = len(rows[0][1])
    # Before `_cells`, so an oversize picture costs no work per cell.
    too_big = cw_grid.oversize(len(rows), cols)
    if too_big is not None:
        raise MaskError(f"mask file {name} draws a {len(rows)}x{cols} grid, {too_big}")
    cells = _cells(name, rows, cols)
    if len(cells) == len(rows) * cols:
        raise MaskError(
            f"mask file {name} masks every cell of its {len(rows)}x{cols} picture: "
            "that forbids every letter, so no grid could be filled"
        )
    return Mask(rows=len(rows), cols=cols, cells=cells)


# fuzz-target
def load_mask(path: Path) -> Mask:
    """The picture at `path`, or raise MaskError.

    The one reader of a `--mask` file, for `fill` and `gaps` alike, so the two
    subcommands cannot come to disagree about what a picture means.
    """
    return parse_mask(_read_picture(path), str(path))


def stamped_rows(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]]
) -> tuple[str, ...]:
    """`rows` with every masked cell spelled `STAMP`, for a derived line view.

    The one place a masked cell is a CHARACTER rather than a coordinate.
    `cw_place.crossing_candidates` judges a placement against a row or column
    string through `cw_place._fits_line`, which accepts a cell only when it is
    `cw_grid.BLOCK` or the letter wanted there -- so a stamped cell rejects the
    placement with no change to that predicate. The view is derived and thrown
    away; nothing stamped may reach `cw_grid.runs_from_rows`, which would read
    the stamp as a filled cell and invent an entry out of it.

    An unmasked call returns the rows themselves. `crossing_candidates` asks
    this of nearly every node of a search, so a run without `--mask` must pay
    nothing for the flag's existence -- which is what `walk_equivalence` is
    pointed at to confirm.

    A coordinate outside `rows` is ignored rather than refused: the
    size-agreement check makes one unreachable from a command line, and this is
    a view builder rather than a place to re-litigate the size.
    """
    if not masked:
        return tuple(rows)
    return tuple(
        "".join(
            STAMP if (row, col) in masked else cell for col, cell in enumerate(line)
        )
        for row, line in enumerate(rows)
    )


def size_disagreement(mask_size: tuple[int, int], grid: tuple[int, int]) -> str | None:
    """Why a picture of `mask_size` cannot shape a `grid`-sized grid, or None.

    A message rather than an exception, so the caller raises in its own currency.
    `fill`, its one caller (through `cw_config._validate_mask_size`), refuses this
    as a contradictory configuration (`cw_config.ConfigError`), because the size
    it is checked against is the configured one. `gaps` asks the same question of
    its `--source` grid without calling this: `cw_gaps_command._require_mask_agrees`
    words its own refusal, as a flag naming something that file does not contain.
    Routing `gaps` through here was weighed and declined: the reason below is a
    fill's, the grid a fill ends on, which `gaps` never has, and a parameter for
    each clause would leave only the comparison shared.

    The grid a picture must match is the FINAL one, growth included: a mask
    shapes what a fill ends on, so a picture sized to a `--source` would strand
    the shape in the top-left. Exactly, never merely large enough -- a smaller
    picture leaves cells no part of the drawing decides, and a larger one draws
    cells the grid does not have. Both sizes are named, because which of them is
    wrong is the operator's to decide.
    """
    if mask_size in (NO_MASK_SIZE, grid):
        return None
    return (
        f"--mask draws a {mask_size[0]}x{mask_size[1]} picture but the grid is "
        f"{grid[0]}x{grid[1]}: a mask shapes the grid a fill ends on, so the two "
        "must be the same size"
    )


def forbidden_letter(
    rows: Sequence[str], masked: AbstractSet[tuple[int, int]]
) -> str | None:
    """Why `rows` cannot be laid under `masked`, or None when no letter is forbidden.

    For a `--source` grid, whose letters are the one kind that reaches a board
    without passing a placement seam: `cw_board.pinned_board` writes each one
    straight on with `set_letter`, which asks nothing. So a letter the operator
    handed over and a picture that forbids it can only be caught before the
    board is built -- the alternative is silently discarding their own grid.

    `rows` must be the source as PLACED on the grid, which is the frame the
    mask's coordinates are in.
    """
    for row, line in enumerate(rows):
        for col, cell in enumerate(line):
            if cell != cw_grid.BLOCK and (row, col) in masked:
                return (
                    f"--source puts the letter {cell} in cell {row},{col}, which "
                    "--mask forbids a letter"
                )
    return None


def _supplied(given: int | None, from_mask: int, own: int) -> int | None:
    """`given` where the operator wrote it, else the mask's dimension.

    The mask declines to supply a dimension SMALLER than `own`, the
    `--source` grid's own. Supplied, `cw_source.resolve_size` would refuse it
    naming `--rows` or `--cols` -- flags the operator never wrote, since the
    value came from the picture. Left absent, the source's own size stands and
    the size-agreement check refuses instead, naming both sizes. Both refuse;
    only one of them names something the operator can act on.
    """
    if given is not None:
        return given
    return None if from_mask < own else from_mask


def requested_size(
    rows: int | None, cols: int | None, own: tuple[int, int], mask: Mask | None
) -> tuple[int | None, int | None]:
    """`--rows` and `--cols` with the mask's own size filling in whichever is absent.

    Read before `cw_source.resolve_size`, which settles the size: the mask's
    job here is only to stand in for a flag that was not given, exactly as a
    `--source` grid does. `own` is the source's own size, or `(0, 0)` without
    one.

    Whether the size the mask asked for is the size the grid ended up at is a
    separate question, and `cw_config.validate_fill_config` answers it -- a
    picture must match the final grid exactly, and that check sees the grown
    size this function cannot.
    """
    if mask is None:
        return rows, cols
    return (
        _supplied(rows, mask.rows, own[0]),
        _supplied(cols, mask.cols, own[1]),
    )
