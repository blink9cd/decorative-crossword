"""cw_svg_gaps: a layer that exists for a single subcommand.

`gaps --out` marks blocked cells, and a block is the one thing the shading path
cannot reach: `cw_svg._cell_class` resolves `BLOCK_CLASS` before it consults
`shaded_cells`, deliberately, because shading IS the cell fill and a block's
fill is the block. So the mark has to be drawn OVER the
block in a layer of its own.

Its own module rather than another function in `cw_svg`: this layer belongs to
one subcommand, and it needs nothing from the render plan beyond the cells and
the geometry.
"""

from __future__ import annotations

from collections.abc import Sequence

import cw_svg_style


def gap_layer(cells: Sequence[tuple[int, int]], geometry: cw_svg_style.Geometry) -> str:
    """The ring on every gap this render was asked to mark, in the given order.

    Drawn centered rather than in the bottom-right corner where a theme marker
    sits: a gap's cell is empty, so there is no letter to keep clear of, and
    the center is where a reader scanning for one looks.

    Returns "" -- and is then dropped from the document rather than emitted as
    an empty group -- when nothing is marked. That is a deliberate departure
    from `cw_svg_style.group`'s "an empty layer is still emitted" rule: only
    `gaps --out` ever has a gap to draw, so every other render carries no empty
    gap group.
    """
    if not cells:
        return ""
    size = geometry.cell * cw_svg_style.GAP_MARKER_RATIO
    inset = (geometry.cell - size) / 2
    marks = [
        cw_svg_style.gap_mark(
            geometry.margin + col_index * geometry.cell + inset,
            geometry.margin + row_index * geometry.cell + inset,
            size,
        )
        for row_index, col_index in cells
    ]
    return cw_svg_style.group(cw_svg_style.GAP_LAYER, marks)
