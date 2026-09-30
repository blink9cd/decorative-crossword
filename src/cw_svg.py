"""The render: one filled grid drawn as a self-contained SVG, the tool's product.

A filled grid is unreadable as JSON, so the tool draws one, and the picture
exists to answer three questions at a glance -- does this read as a crossword,
is the density right, and are the themes spread or bunched.

Three properties of the output are load-bearing rather than cosmetic.

*Self-contained.* No font, image, stylesheet or script is referenced. A
`<text>` element names a generic font family and nothing is fetched, so the
file opens from a `file://` path on a machine with no network -- which keeps
the grid's content off any hosted service and is also what makes a preview
convenient.

*Escaped.* Theme labels are operator-supplied and will eventually carry an
ampersand or an angle bracket. An unescaped one produces a malformed document
that renders as a blank page with no error at all -- a failure that "the file
was written" cannot see. Every caller-supplied string reaches the document
through `cw_svg_style.text_node`, escaped, as element text.

*Byte-identical.* Fixed geometry, one fixed number format, and orderings taken
from sorted keys or from `cw_grid`'s documented run order rather than from a
caller's mapping-insertion order.

Rendering has a single home, and this is it: every picture the tool writes
reaches it through `render_svg`, and no entry point carries drawing logic of
its own. `shade --word` hands in a hidden word's cells, which no `--feature`
can express, as `HiddenShading`; `gaps --out` marks blocked cells in a layer
over their fill; `fill --source` hands in the letters it started from, drawn
bold in a layer of their own. `empty_blocks` is the one optional field every
caller sets, because it asks about the DRAWING rather than about what its
caller found. What the render is allowed to LOOK like -- classes, palette,
markers, geometry, element primitives -- lives in `cw_svg_style`, and what it
SAYS about itself -- the caption's two tiers -- lives in `cw_svg_caption`,
whose own suite is `tests/test_svg_caption.py`. What a request IS, and
everything derived from it before drawing, lives in `cw_svg_plan`. This module
keeps the layers and the assembly.
"""

from __future__ import annotations

import cw_grid
import cw_svg_gaps
import cw_svg_plan
import cw_svg_style
from cw_svg_plan import HiddenShading, RenderRequest
from cw_svg_style import (
    BLOCK_CLASS,
    CAPTION_LAYER,
    CELL_LAYER,
    EMPTY_BLOCK_CLASS,
    FEATURE_TOKEN,
    LEGEND_LAYER,
    LEGEND_MARKER_LAYER,
    LETTER_LAYER,
    MARKER_LAYER,
    PAGE_CLASS,
    PLAIN_CLASS,
    SVG_NAMESPACE,
    SWATCH_LAYER,
    marker_element_name,
    theme_class,
)

#: Re-exported so a caller needs one import to render and to read the result.
#: These are aliases of the single definitions in `cw_svg_style` and
#: `cw_svg_plan`, not copies.
__all__ = [
    "BLOCK_CLASS",
    "CAPTION_LAYER",
    "CELL_LAYER",
    "EMPTY_BLOCK_CLASS",
    "FEATURE_CLASS",
    "FEATURE_TOKEN",
    "HiddenShading",
    "LEGEND_LAYER",
    "LEGEND_MARKER_LAYER",
    "LETTER_LAYER",
    "MARKER_LAYER",
    "PAGE_CLASS",
    "PLAIN_CLASS",
    "SVG_NAMESPACE",
    "SWATCH_LAYER",
    "RenderRequest",
    "marker_element_name",
    "render_svg",
    "theme_class",
]

#: The rendered `class=` attribute of a shaded cell. Exposed as the whole
#: attribute rather than the bare token because the token also appears in the
#: stylesheet's own selector: counting the token reports one more shaded cell
#: than the grid holds, while counting this attribute is exactly the count.
FEATURE_CLASS = f'class="{FEATURE_TOKEN}"'

_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'

#: The viewBox origin. Emitted through the same formatter as every other
#: number rather than written as a bare "0", so the whole attribute is in
#: the one fixed form every number renders in.
_VIEWBOX_ORIGIN = 0.0


# --------------------------------------------------------------------------
# The layers, painted in order: backgrounds, markers, letters, then the legend
# and caption beneath the grid.
# --------------------------------------------------------------------------


def _cell_class(plan: cw_svg_plan.Plan, position: tuple[int, int], char: str) -> str:
    """Which background one cell gets: block, shading, theme tint, or plain.

    Feature shading outranks the tint because the shading IS the cell fill.
    Nothing is lost by the override: the theme survives as the marker the next
    layer draws over it, so a cell that is both featured and themed keeps both
    readings.
    """
    if char == cw_grid.BLOCK:
        return EMPTY_BLOCK_CLASS if plan.request.empty_blocks else BLOCK_CLASS
    if position in plan.shaded_cells:
        return FEATURE_TOKEN
    theme_id = plan.theme_by_cell.get(position)
    if theme_id is None:
        return PLAIN_CLASS
    return plan.styles[theme_id].css_class


def _cell_layer(plan: cw_svg_plan.Plan) -> str:
    """One background rect per cell, row-major."""
    geometry = plan.geometry
    rects = [
        cw_svg_style.rect(
            geometry.margin + col_index * geometry.cell,
            geometry.margin + row_index * geometry.cell,
            geometry.cell,
            geometry.cell,
            _cell_class(plan, (row_index, col_index), char),
        )
        for row_index, row in enumerate(plan.request.rows)
        for col_index, char in enumerate(row)
    ]
    return cw_svg_style.group(CELL_LAYER, rects)


def _marker_layer(plan: cw_svg_plan.Plan) -> str:
    """The non-color theme marker on every themed cell.

    Drawn after the backgrounds and before the letters, in the bottom-right
    corner, so it sits over the fill (including a feature's shading) without
    reaching the letter in the middle of the cell.
    """
    geometry = plan.geometry
    size = geometry.cell * cw_svg_style.MARKER_RATIO
    inset = geometry.cell * cw_svg_style.MARKER_INSET_RATIO
    marks = [
        plan.styles[theme_id].marker.draw(
            geometry.margin + (col_index + 1) * geometry.cell - inset - size,
            geometry.margin + (row_index + 1) * geometry.cell - inset - size,
            size,
        )
        for (row_index, col_index), theme_id in plan.theme_by_cell.items()
    ]
    return cw_svg_style.group(MARKER_LAYER, marks)


def _letter_nodes(plan: cw_svg_plan.Plan, *, fixed: bool) -> list[str]:
    """One centered letter for every filled cell that is, or is not, fixed.

    Asked of each cell the grid draws rather than of each requested
    coordinate, so every letter lands in exactly one of the two letter
    layers: a letter drawn twice, bold over regular, would smear at its edges.
    """
    geometry = plan.geometry
    half = geometry.cell / 2
    return [
        cw_svg_style.text_node(
            geometry.margin + col_index * geometry.cell + half,
            geometry.margin + row_index * geometry.cell + half,
            char,
        )
        for row_index, row in enumerate(plan.request.rows)
        for col_index, char in enumerate(row)
        if char != cw_grid.BLOCK
        and ((row_index, col_index) in plan.fixed_cells) == fixed
    ]


def _letter_layer(plan: cw_svg_plan.Plan) -> str:
    """Every letter the fill placed: all of them, for a grid with nothing fixed."""
    return cw_svg_style.group(LETTER_LAYER, _letter_nodes(plan, fixed=False))


def _fixed_letter_layer(plan: cw_svg_plan.Plan) -> str:
    """Every letter `fill --source` was handed, which the stylesheet draws bold.

    Returns "" when nothing is fixed, and is then dropped from the document the
    way `cw_svg_gaps.gap_layer` is, so a render made without a source carries
    no empty fixed-letter group.
    """
    if not plan.fixed_cells:
        return ""
    return cw_svg_style.group(
        cw_svg_style.FIXED_LETTER_LAYER, _letter_nodes(plan, fixed=True)
    )


def _legend_layers(plan: cw_svg_plan.Plan) -> list[str]:
    """The legend's three layers: swatches, markers, labels.

    One row per declared theme, mapping its tint AND its marker to its display
    label -- both, because tint alone does not survive a monochrome print or a
    color-vision difference. The marker comes from the
    theme's own builder, so the legend cannot advertise a shape the grid does
    not draw.
    """
    geometry = plan.geometry
    marker_size = geometry.swatch * cw_svg_style.LEGEND_MARKER_RATIO
    swatches: list[str] = []
    marks: list[str] = []
    labels: list[str] = []
    for style in plan.styles.values():
        row_top = geometry.legend_top + style.order * geometry.legend_row
        swatch_top = row_top + (geometry.legend_row - geometry.swatch) / 2
        swatches.append(
            cw_svg_style.rect(
                geometry.margin,
                swatch_top,
                geometry.swatch,
                geometry.swatch,
                style.css_class,
            )
        )
        marks.append(
            style.marker.draw(
                geometry.margin + (geometry.swatch - marker_size) / 2,
                swatch_top + (geometry.swatch - marker_size) / 2,
                marker_size,
            )
        )
        labels.append(
            cw_svg_style.text_node(
                geometry.margin + geometry.swatch + geometry.swatch_gap,
                row_top + geometry.legend_row / 2,
                style.label,
            )
        )
    return [
        cw_svg_style.group(SWATCH_LAYER, swatches),
        cw_svg_style.group(LEGEND_MARKER_LAYER, marks),
        cw_svg_style.group(LEGEND_LAYER, labels),
    ]


def _caption_layer(plan: cw_svg_plan.Plan) -> str:
    """The caption lines, one under the other, beneath the legend."""
    geometry = plan.geometry
    lines = [
        cw_svg_style.text_node(
            geometry.margin,
            geometry.caption_top
            + index * geometry.caption_row
            + geometry.caption_row / 2,
            line,
        )
        for index, line in enumerate(plan.caption_lines)
    ]
    return cw_svg_style.group(CAPTION_LAYER, lines)


def render_svg(request: RenderRequest) -> str:
    """Render one SVG for `request`.

    The result is a complete, self-contained document and is byte-identical for
    the same request. No width or height attribute is emitted: a viewBox alone
    scales to whatever opens the file, while a fixed width would pin the render
    to one display size.

    Raises ValueError, from `cw_grid.runs_from_rows`, if `rows` is ragged --
    run derivation cannot transpose a grid whose rows differ in length.
    Validating the source is the CLI's job, so this does not repeat it.
    """
    plan = cw_svg_plan.plan(request)
    body = [
        cw_svg_style.stylesheet(
            plan.geometry,
            list(plan.styles.values()),
            gaps=bool(request.gaps),
            fixed=bool(plan.fixed_cells),
            empty_blocks=request.empty_blocks,
        ),
        # The page, drawn before anything else so everything else is drawn on
        # it. It covers the viewBox exactly, which is what lets a reader -- and
        # a test -- identify it by geometry rather than by trusting its class.
        cw_svg_style.rect(
            _VIEWBOX_ORIGIN,
            _VIEWBOX_ORIGIN,
            plan.geometry.width,
            plan.geometry.height,
            PAGE_CLASS,
        ),
        _cell_layer(plan),
        _marker_layer(plan),
        cw_svg_gaps.gap_layer(request.gaps, plan.geometry),
        _letter_layer(plan),
        _fixed_letter_layer(plan),
        *_legend_layers(plan),
        _caption_layer(plan),
    ]
    # An empty gap layer or fixed-letter layer drops out entirely rather than
    # joining as a blank line; every other layer is always non-empty, so this
    # filter changes only the two that are documented to be optional.
    body = [part for part in body if part]
    origin = cw_svg_style.fmt(_VIEWBOX_ORIGIN)
    opening = (
        f'<svg xmlns="{SVG_NAMESPACE}" viewBox="{origin} {origin} '
        f"{cw_svg_style.fmt(plan.geometry.width)} "
        f'{cw_svg_style.fmt(plan.geometry.height)}">'
    )
    return "\n".join([_XML_DECLARATION, opening, *body, "</svg>"]) + "\n"
