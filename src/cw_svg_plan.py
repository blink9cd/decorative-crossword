"""What one render is asked for, and everything derived from it before drawing.

Kept apart from `cw_svg` along a real seam: everything here turns a request
into values (which cell shows which theme, which cells are shaded, what the
caption says, where everything sits), and nothing here emits an element.
`cw_svg` paints a `Plan`; it never re-derives one.

The request types live here rather than in `cw_svg` because the plan is built
from them and `cw_svg` imports this module, so the reverse import would be a
cycle. `cw_svg` re-exports both, so a caller still needs one import to render.

Entry point assumptions: imported by bare name after `src/` is on `sys.path`,
like every other module in this folder.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import cw_grid
import cw_svg_caption
import cw_svg_style


@dataclass(frozen=True)
class HiddenShading:
    """A hidden word, and the already-chosen cells that spell it.

    The cells arrive rather than being located, which is the whole difference
    from `features`: a hidden word's letters are scattered across several
    entries on purpose, so there is no run to find and nothing this module
    could derive them from. Choosing them is `cw_shade`'s job.

    Declared here and not imported from `cw_shade`, even though that module's
    `Placement` carries the same two fields plus a score: the renderer draws
    cells and has no business depending on the module that scores them. The
    caller builds one of these from a `Placement`, which is a two-field
    projection and not a conversion anyone has to think about.

    Nothing is validated. A coordinate outside the grid, or on a block, simply
    never matches a cell the grid actually draws: the cell layer asks each of
    its own cells whether it is shaded, rather than walking these. Validating
    the source is the CLI's job, and the shape of that
    lookup is what makes not repeating it safe here.
    """

    word: str
    cells: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class RenderRequest:
    """One render's inputs.

    `settings` is the caption's configuration tier: the seed, the requested
    density range, the theme floor. It is None under a bare `preview`, which
    has no honest way to know any of them, and the tier is then absent from the
    picture rather than defaulted.

    `hidden` is `shade --word`'s, and is independent of `features`: the two
    shade the same way and a request carrying both draws the union, because a
    rule that let one silently erase the other would be a surprise waiting for
    whoever first supplies them together.
    """

    rows: tuple[str, ...]
    themes: Mapping[str, str]
    entry_themes: Mapping[str, str]
    #: Every answer to shade and to name, in the order the caller gave them,
    #: the order the caption lists them in. Empty means none.
    features: tuple[str, ...]
    cell: int
    settings: Mapping[str, str] | None
    hidden: HiddenShading | None
    #: The blocked cells `gaps --out` is marking, in the order it ranked them.
    #: Defaulted, since only `gaps --out` supplies it. Unlike `hidden`, these
    #: are cells the grid draws as blocks, which is why they cannot travel
    #: through `shaded_cells`: a block resolves its class before the shading is
    #: consulted, so the mark is drawn over the fill in a layer of its own
    #: instead of replacing it.
    gaps: tuple[tuple[int, int], ...] = ()
    #: The cells whose letters `fill --source` was handed, in any order.
    #: Defaulted like `gaps`. Only `fill` can supply them: a finished
    #: `grid_source.json` records no such thing, so `preview` never does.
    fixed: tuple[tuple[int, int], ...] = ()
    #: Draw every blocked cell as a hole rather than a black square, so the
    #: grid's outline reads as a shape. Defaulted like the two above. It is a
    #: property of the drawing and not of the grid: the same `grid_source.json`
    #: renders either way, and the caption's blocked percentage stays true of
    #: the grid whichever is chosen.
    empty_blocks: bool = False


@dataclass(frozen=True)
class Plan:
    """Everything derived from a request before a single string is emitted."""

    request: RenderRequest
    styles: Mapping[str, cw_svg_style.ThemeStyle]
    theme_by_cell: Mapping[tuple[int, int], str]
    #: Every cell the render shades, whichever of the two reasons put it there.
    #: One membership set rather than two, because the cell layer asks one
    #: question ("is this cell shaded"), and a second set would let the two
    #: reasons produce two different shadings of the same cell.
    shaded_cells: frozenset[tuple[int, int]]
    #: The fixed cells that hold a letter in this grid. Narrowed once, here,
    #: because the letter layers and the caption both ask it: a coordinate on a
    #: block or off the grid draws nothing, so it must count for nothing too.
    fixed_cells: frozenset[tuple[int, int]]
    caption_lines: tuple[str, ...]
    geometry: cw_svg_style.Geometry


def _theme_by_cell(
    runs: Sequence[cw_grid.Run],
    entry_themes: Mapping[str, str],
    styles: Mapping[str, cw_svg_style.ThemeStyle],
) -> dict[tuple[int, int], str]:
    """The theme each themed cell displays, keyed by (row, col).

    A crossing cell sits in two entries that may carry different themes, and it
    can show only one tint and one marker. The tie-break is run order, which
    `cw_grid.runs_from_rows` documents as every ACROSS run before every DOWN
    one, so the across reading wins, always, rather than whichever entry
    happened to be visited last.

    An entry whose theme is not declared renders plain: there is no label to
    legend it with, and a grid whose content is questionable is drawn rather
    than refused.
    """
    theme_at: dict[tuple[int, int], str] = {}
    for run in runs:
        theme_id = entry_themes.get(run.text)
        if theme_id is None or theme_id not in styles:
            continue
        for cell in run.cells:
            theme_at.setdefault(cell, theme_id)
    return theme_at


def _featured_answers(request: RenderRequest) -> tuple[str, ...]:
    """The answers to shade and to name, in the order given.

    An empty answer is dropped here, once. Both the shading and the caption
    ask this question, and asking it twice is how they would come to disagree:
    a caller assembling the flags conditionally must not be able to get a
    caption line that names nothing above a grid with nothing shaded.
    """
    return tuple(answer for answer in request.features if answer)


def _feature_runs(
    rows: tuple[str, ...], answers: tuple[str, ...]
) -> tuple[cw_grid.Run | None, ...]:
    """The run each answer occupies, None where the grid holds no such entry."""
    return tuple(cw_grid.find_answer(rows, answer) for answer in answers)


def _caption_lines(
    request: RenderRequest,
    styles: Mapping[str, cw_svg_style.ThemeStyle],
    runs: Sequence[cw_grid.Run],
    answers: tuple[str, ...],
    feature_runs: tuple[cw_grid.Run | None, ...],
    fixed_cells: frozenset[tuple[int, int]],
) -> tuple[str, ...]:
    """The caption: one line per tier this render actually knows.

    An empty `settings` mapping carries no configuration and is treated as
    absent, so a caller building one conditionally cannot emit a blank line
    where a tier was meant to be.

    The hidden word's line, and then the fixed letters' line, sit between the
    feature and the configuration for the same reason the feature's does: each
    names something marked on the picture, and the configuration tier is the
    one a bare `preview` cannot know at all.
    """
    lines = [
        cw_svg_caption.derivable_line(request.rows, request.entry_themes, styles, runs)
    ]
    lines.extend(
        cw_svg_caption.feature_line(answer, run)
        for answer, run in zip(answers, feature_runs, strict=True)
    )
    if request.hidden is not None:
        lines.append(cw_svg_caption.hidden_line(request.hidden.word))
    if fixed_cells:
        lines.append(cw_svg_caption.fixed_line(len(fixed_cells)))
    if request.settings:
        lines.append(cw_svg_caption.configuration_line(request.settings))
    return tuple(lines)


def _shaded_cells(
    feature_runs: tuple[cw_grid.Run | None, ...], hidden: HiddenShading | None
) -> frozenset[tuple[int, int]]:
    """Every cell to shade, from either reason a render has to shade one.

    A union rather than a precedence: the reasons are independent, they
    produce the same fill, and there is nothing for one to win over. Two
    features crossing share a cell, and a set makes it one cell.
    """
    from_features = (
        cell for run in feature_runs if run is not None for cell in run.cells
    )
    from_hidden = () if hidden is None else hidden.cells
    return frozenset(from_features) | frozenset(from_hidden)


def _fixed_cells(request: RenderRequest) -> frozenset[tuple[int, int]]:
    """The requested fixed cells that hold a letter in this grid.

    Nothing is refused, as with `HiddenShading`: a coordinate on a block or off
    the grid is simply not a letter this grid draws, so it drops out here
    rather than reaching the caption's count.
    """
    letters = {
        (row_index, col_index)
        for row_index, row in enumerate(request.rows)
        for col_index, char in enumerate(row)
        if char != cw_grid.BLOCK
    }
    return frozenset(request.fixed) & letters


def plan(request: RenderRequest) -> Plan:
    """Derive everything the layers need, before a single string is emitted."""
    styles = cw_svg_style.theme_styles(request.themes)
    runs = cw_grid.runs_from_rows(request.rows)
    answers = _featured_answers(request)
    feature_runs = _feature_runs(request.rows, answers)
    fixed_cells = _fixed_cells(request)
    caption_lines = _caption_lines(
        request, styles, runs, answers, feature_runs, fixed_cells
    )
    labels = [style.label for style in styles.values()]
    return Plan(
        request=request,
        styles=styles,
        theme_by_cell=_theme_by_cell(runs, request.entry_themes, styles),
        shaded_cells=_shaded_cells(feature_runs, request.hidden),
        fixed_cells=fixed_cells,
        caption_lines=caption_lines,
        geometry=cw_svg_style.geometry_for(
            request.rows, request.cell, labels, caption_lines
        ),
    )
