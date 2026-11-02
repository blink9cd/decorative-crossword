"""The render's visual vocabulary: classes, palette, markers, geometry, elements.

Kept apart from `cw_svg` so that module holds one concern (turning a grid
into a document), while this one holds the other: what that document is
allowed to look like. Names are public rather than underscore-private wherever
`cw_svg` or the suites that pin the render need to read them; a value nobody
outside this file reads stays private.

Two rules govern everything below.

*Nothing is fetched.* Colors are literals, the font is a generic family, and
no element carries a URL. That is what lets the render open from a `file://`
path on a machine with no network.

*Every number renders in one fixed form.* A bare float repr varies in digit
count between values, so a coordinate computed as `48 * 1.5` would not render
like one that landed on a round number, and one document would mix number
forms.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape

#: The SVG namespace. It is an identifier rather than a fetch, but a document
#: without it parses as XML and renders as nothing at all, which is the same
#: blank page an escaping bug produces, so it is never optional.
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

#: Layer classes. Every layer is homogeneous (one kind of element each), so a
#: reader, and a test, can address one concern without filtering.
CELL_LAYER = "cw-cells"
MARKER_LAYER = "cw-marks"
LETTER_LAYER = "cw-letters"

#: The layer the letters `fill --source` was handed are drawn in, bold. Its own
#: layer rather than a class on each `<text>`, so every layer stays one kind of
#: element with one rule, and a reader, and a test, can ask which letters were
#: fixed by reading one layer.
FIXED_LETTER_LAYER = "cw-fixed-letters"

#: The layer `gaps --out` draws its marks in. Its own layer rather than a cell
#: class, because a gap is a BLOCK and `cw_svg._cell_class` resolves a block
#: before it ever consults the shading, so the mark has to sit over the
#: block's fill instead of replacing it.
GAP_LAYER = "cw-gaps"
SWATCH_LAYER = "cw-swatches"
LEGEND_MARKER_LAYER = "cw-legend-marks"
LEGEND_LAYER = "cw-legend"
CAPTION_LAYER = "cw-caption"

#: Cell background classes for the two states that carry no theme.
BLOCK_CLASS = "cw-block"
PLAIN_CLASS = "cw-cell"

#: The class a block carries under `--empty-blocks`, where it paints nothing
#: and the page shows through. Its rect is still emitted, so the change is a
#: paint and never a geometry, but its rule has to cancel the shared cell
#: stroke as well as the fill, and `.{EMPTY_BLOCK_CLASS}` alone would lose
#: that contest: a bare class ranks below `.{CELL_LAYER} rect`, which is why
#: `stylesheet` spells the descendant form rather than this token alone.
EMPTY_BLOCK_CLASS = "cw-block-empty"

#: The class on the one rect that covers the whole canvas. SVG has no
#: background property a root element can carry (`svg{fill:...}` sets the
#: fill of the shapes inside it, not the paper), so the only portable way to
#: paint the page is to draw it. Without one, the legend and the caption sit
#: outside the grid on whatever the viewer paints, which is near-black in a
#: dark-mode browser and a checkerboard in some image viewers, and near-black
#: ink on it is invisible while the markup stays perfect.
PAGE_CLASS = "cw-page"

#: The class token on a shaded (featured) cell.
FEATURE_TOKEN = "cw-feature"

_THEME_CLASS_PREFIX = "cw-theme-"

_NUMBER_FORMAT = ".1f"

#: Generic families only: naming a font file would be an external reference.
_FONT_STACK = "sans-serif"

_INK = "#1a1a1a"
_PAPER = "#ffffff"

#: The gray-square convention a setter uses to mark a theme entry.
_FEATURE_FILL = "#c9c9c9"

#: Cell tints, cycled by a theme's position in sorted order. Light enough that
#: the ink letter drawn over one stays legible.
_TINTS: tuple[str, ...] = ("#cfe0f4", "#d9ecd2", "#f7e0cf", "#e7dcf2", "#f3f0cd")

_INDENT = "  "


def fmt(value: float) -> str:
    """One number, in the single fixed form every coordinate in the file uses."""
    return f"{value:{_NUMBER_FORMAT}}"


def theme_class(order: int) -> str:
    """The cell and swatch class for the theme at `order` in sorted theme order.

    One class per theme rather than one per tint: two themes can share a tint
    while their markers differ, and giving each its own class keeps the
    stylesheet readable when that happens.
    """
    return f"{_THEME_CLASS_PREFIX}{order}"


# --------------------------------------------------------------------------
# Non-color markers
#
# Tint alone cannot carry the grouping: it has to survive a monochrome print
# and a color-vision difference. Each theme also gets a
# shape, drawn in the bottom-right corner of every cell it owns and repeated in
# its legend row, from the same builder, so the legend cannot advertise a
# shape the grid does not draw.
# --------------------------------------------------------------------------

MARKER_RATIO = 0.22

#: The gap mark's diameter as a share of the cell edge. Larger than a theme
#: marker because it is the only thing on its cell and is read at a glance,
#: and well short of the edge so a marked block still reads as a block.
GAP_MARKER_RATIO = 0.34
MARKER_INSET_RATIO = 0.08
LEGEND_MARKER_RATIO = 0.5
_BAR_HEIGHT_RATIO = 0.34


def gap_mark(left: float, top: float, size: float) -> str:
    """An open ring inscribed in the mark box, for one gap `gaps --out` listed.

    An outline rather than a filled shape, and deliberately not any of the
    theme markers: it must not be mistaken for a theme at a glance, and the
    non-color rule means the difference has to be a shape rather than a tint.
    Its fill and stroke come from the layer, as every other marker's do.
    """
    radius = size / 2
    return (
        f'<circle cx="{fmt(left + radius)}" cy="{fmt(top + radius)}" '
        f'r="{fmt(radius)}"/>'
    )


def _marker_dot(left: float, top: float, size: float) -> str:
    """A filled circle inscribed in the marker box."""
    radius = size / 2
    return (
        f'<circle cx="{fmt(left + radius)}" cy="{fmt(top + radius)}" '
        f'r="{fmt(radius)}"/>'
    )


def _marker_bar(left: float, top: float, size: float) -> str:
    """A horizontal bar across the middle of the marker box."""
    height = size * _BAR_HEIGHT_RATIO
    return (
        f'<rect x="{fmt(left)}" y="{fmt(top + (size - height) / 2)}" '
        f'width="{fmt(size)}" height="{fmt(height)}"/>'
    )


def _marker_triangle(left: float, top: float, size: float) -> str:
    """An upward triangle filling the marker box."""
    points = " ".join(
        (
            f"{fmt(left)},{fmt(top + size)}",
            f"{fmt(left + size)},{fmt(top + size)}",
            f"{fmt(left + size / 2)},{fmt(top)}",
        )
    )
    return f'<polygon points="{points}"/>'


def _marker_square(left: float, top: float, size: float) -> str:
    """A filled square filling the marker box."""
    return (
        f'<rect x="{fmt(left)}" y="{fmt(top)}" '
        f'width="{fmt(size)}" height="{fmt(size)}"/>'
    )


@dataclass(frozen=True)
class Marker:
    """One marker: the element it draws as, and how to draw it.

    The element name sits beside its builder rather than in a parallel table,
    so a caller asking which shape a theme uses and the code that draws it
    cannot disagree.
    """

    element: str
    draw: Callable[[float, float, float], str]


#: The marker cycle. Its length is deliberately not the tint palette's, so a
#: tint/marker pair repeats far later than either sequence alone does.
_MARKERS: tuple[Marker, ...] = (
    Marker("circle", _marker_dot),
    Marker("rect", _marker_bar),
    Marker("polygon", _marker_triangle),
    Marker("rect", _marker_square),
)


def marker_element_name(order: int) -> str:
    """The SVG element name the theme at `order` draws its marker as."""
    return _MARKERS[order % len(_MARKERS)].element


@dataclass(frozen=True)
class ThemeStyle:
    """How one declared theme is drawn: its label, its tint and its marker."""

    order: int
    label: str
    tint: str
    marker: Marker

    @property
    def css_class(self) -> str:
        """The class its cells and its legend swatch carry."""
        return theme_class(self.order)


def theme_styles(themes: Mapping[str, str]) -> dict[str, ThemeStyle]:
    """Each declared theme's drawing style, keyed by theme id.

    Ordered by sorted theme id rather than by the mapping's own iteration
    order: the ordering is fixed, so two callers that assembled the same themes
    in a different order must get the same bytes out.
    """
    return {
        theme_id: ThemeStyle(
            order=order,
            label=themes[theme_id],
            tint=_TINTS[order % len(_TINTS)],
            marker=_MARKERS[order % len(_MARKERS)],
        )
        for order, theme_id in enumerate(sorted(themes))
    }


# --------------------------------------------------------------------------
# Geometry: every length is a multiple of the cell edge, so the whole picture
# scales with `--cell` and nothing carries an absolute size.
# --------------------------------------------------------------------------

_MARGIN_RATIO = 0.5
_GAP_RATIO = 0.35
_LEGEND_ROW_RATIO = 0.55
_CAPTION_ROW_RATIO = 0.45
_SWATCH_RATIO = 0.4
_SWATCH_GAP_RATIO = 0.22
_LETTER_FONT_RATIO = 0.6
_LABEL_FONT_RATIO = 0.3
_CAPTION_FONT_RATIO = 0.26
_STROKE_RATIO = 0.03

#: Approximate width of one glyph as a fraction of its font size. Exact text
#: metrics need the font file, which an offline renderer deliberately does not
#: have; this over-estimates a proportional sans-serif slightly, so the caption
#: and legend end up padded rather than clipped.
_GLYPH_WIDTH_RATIO = 0.6


@dataclass(frozen=True)
class Geometry:
    """Where everything sits, in user units, for one cell size."""

    cell: float
    margin: float
    grid_height: float
    legend_top: float
    legend_row: float
    caption_top: float
    caption_row: float
    width: float
    height: float
    swatch: float
    swatch_gap: float


def _text_width(text: str, font_size: float) -> float:
    """An estimate of how wide `text` draws at `font_size`."""
    return len(text) * font_size * _GLYPH_WIDTH_RATIO


def geometry_for(
    rows: Sequence[str],
    cell: int,
    labels: Sequence[str],
    caption_lines: Sequence[str],
) -> Geometry:
    """Lay the grid, then the legend, then the caption down one column.

    The document is as wide as its widest content, not as wide as its grid: a
    narrow grid under a long caption would otherwise have that caption clipped
    away, and the caption is what makes a saved render self-describing.
    """
    margin = cell * _MARGIN_RATIO
    gap = cell * _GAP_RATIO
    legend_row = cell * _LEGEND_ROW_RATIO
    caption_row = cell * _CAPTION_ROW_RATIO
    swatch = cell * _SWATCH_RATIO
    swatch_gap = cell * _SWATCH_GAP_RATIO
    # max(..., default=0) rather than rows[0]: an empty grid has no first row,
    # and the renderer must not be the thing that crashes on one: rejecting it
    # is the CLI's job.
    grid_width = max((len(row) for row in rows), default=0) * cell
    grid_height = len(rows) * cell
    legend_top = margin + grid_height + gap
    caption_top = legend_top + legend_row * len(labels) + gap
    # Annotated: grid_width is an int (a column count times an int cell), so an
    # inferred list[int] would reject the float text-width estimates below.
    content: list[float] = [grid_width]
    content.extend(
        swatch + swatch_gap + _text_width(label, cell * _LABEL_FONT_RATIO)
        for label in labels
    )
    content.extend(
        _text_width(line, cell * _CAPTION_FONT_RATIO) for line in caption_lines
    )
    return Geometry(
        cell=cell,
        margin=margin,
        grid_height=grid_height,
        legend_top=legend_top,
        legend_row=legend_row,
        caption_top=caption_top,
        caption_row=caption_row,
        width=max(content) + 2 * margin,
        height=caption_top + caption_row * len(caption_lines) + margin,
        swatch=swatch,
        swatch_gap=swatch_gap,
    )


# --------------------------------------------------------------------------
# Element primitives
# --------------------------------------------------------------------------


def rect(left: float, top: float, width: float, height: float, css_class: str) -> str:
    """One classed `<rect>`.

    The class is required rather than optional. Every caller has one, and an
    optional arm here would be dead code that a coverage report cannot flag:
    coverage.py's arc-based branch analysis does not see a same-line
    conditional expression, so a `None` default would have sat unexercised
    inside a folder reporting 100%. The marker builders emit their own rects
    because their fill is inherited from the layer, not set per element.
    """
    return (
        f'<rect class="{css_class}" x="{fmt(left)}" y="{fmt(top)}" '
        f'width="{fmt(width)}" height="{fmt(height)}"/>'
    )


def text_node(left: float, baseline: float, content: str) -> str:
    """One `<text>`, with `content` XML-escaped.

    Caller-supplied strings reach the document only through here, as element
    text and never as an attribute value, which is why plain `escape` covers
    the whole surface and attribute quoting is never needed.
    """
    return f'<text x="{fmt(left)}" y="{fmt(baseline)}">{escape(content)}</text>'


def group(css_class: str, children: Sequence[str]) -> str:
    """One layer. An empty layer is still emitted, self-closed.

    Emitting it either way keeps the document's shape independent of whether a
    particular grid happens to have themes, so a reader (and a parser) finds
    the same layers every time.
    """
    if not children:
        return f'<g class="{css_class}"/>'
    inner = "".join(f"\n{_INDENT}{child}" for child in children)
    return f'<g class="{css_class}">{inner}\n</g>'


def _rule(selector: str, declarations: str) -> str:
    """One CSS rule, assembled by concatenation.

    A literal brace inside an f-string has to be doubled, which turns every
    rule in the stylesheet into something a reader has to decode first.
    """
    return selector + "{" + declarations + "}"


def _font(size: float) -> str:
    """The shared font declarations at one size."""
    return f"font-family:{_FONT_STACK};font-size:{fmt(size)}px;fill:{_INK}"


def _letter_declarations(geometry: Geometry) -> str:
    """The declarations every grid letter is drawn with, fixed or filled in.

    One source for both letter layers, so a fixed letter differs from a
    filled-in one by the weight appended to it and by nothing else: the same
    ink and the same size, which is what keeps the mark readable in a
    monochrome print.
    """
    return (
        f"{_font(geometry.cell * _LETTER_FONT_RATIO)};"
        "text-anchor:middle;dominant-baseline:central"
    )


def stylesheet(
    geometry: Geometry,
    styles: Sequence[ThemeStyle],
    *,
    gaps: bool = False,
    fixed: bool = False,
    empty_blocks: bool = False,
) -> str:
    """The one inline `<style>` block the whole document is painted from.

    Class rules rather than per-element attributes: the file stays small, and
    counting one class attribute in the raw text counts the cells carrying it.
    Counting the bare token would not: the selector below spells it too,
    which is why `cw_svg.FEATURE_CLASS` exposes the whole attribute.
    """
    stroke = f"stroke:{_INK};stroke-width:{fmt(geometry.cell * _STROKE_RATIO)}"
    # One rule or the other, in one slot: a block is painted in ink, or it is
    # not painted at all. Chosen here rather than appended the way the gaps and
    # fixed rules are, because those add a layer that did not exist, while this
    # replaces a paint: appending would leave a document declaring a block
    # fill that nothing in it carries. Keeping the slot also means the flag
    # moves no other rule out of its place, by construction rather than by care.
    block_rule = (
        _rule(f".{CELL_LAYER} rect.{EMPTY_BLOCK_CLASS}", "fill:none;stroke:none")
        if empty_blocks
        else _rule(f".{BLOCK_CLASS}", f"fill:{_INK}")
    )
    rules = [
        # First rule for the first thing drawn: the page the whole document is
        # read against. Its own class rather than the plain cell's, so the two
        # can be told apart, and so a test asking what color the page is has
        # something to read that the grid does not also answer for.
        _rule(f".{PAGE_CLASS}", f"fill:{_PAPER}"),
        _rule(f".{CELL_LAYER} rect", stroke),
        _rule(f".{SWATCH_LAYER} rect", stroke),
        _rule(f".{PLAIN_CLASS}", f"fill:{_PAPER}"),
        block_rule,
        _rule(f".{FEATURE_TOKEN}", f"fill:{_FEATURE_FILL}"),
        # Two rules rather than one selector list: each marker layer's ink is
        # then readable back out of the stylesheet on its own, which is what
        # lets a test prove the marker is visible and not merely present.
        _rule(f".{MARKER_LAYER}", f"fill:{_INK}"),
        _rule(f".{LEGEND_MARKER_LAYER}", f"fill:{_INK}"),
        _rule(f".{LETTER_LAYER} text", _letter_declarations(geometry)),
        _rule(
            f".{LEGEND_LAYER} text",
            f"{_font(geometry.cell * _LABEL_FONT_RATIO)};dominant-baseline:central",
        ),
        _rule(
            f".{CAPTION_LAYER} text",
            f"{_font(geometry.cell * _CAPTION_FONT_RATIO)};dominant-baseline:central",
        ),
    ]
    if gaps:
        # Added only for a render that actually draws gaps, so no other
        # document declares a rule for a layer it does not carry, the same
        # reason `cw_svg` omits the layer itself. The ring takes whatever its
        # own cell does not: a mark on an ink block has to be the page color or
        # it is black on black, and a mark on an empty block has to be ink or
        # it is white on white. Either way the contrast is with the block, so
        # the two cases cannot share one color.
        rules.append(
            _rule(
                f".{GAP_LAYER}",
                f"fill:none;stroke:{_INK if empty_blocks else _PAPER};"
                f"stroke-width:{fmt(geometry.cell * _STROKE_RATIO)}",
            )
        )
    if fixed:
        # Added only for a render that marks fixed letters, for the gap rule's
        # reason. The keyword `bold` rather than a number: a generic family may
        # carry only a regular and a bold face, and a weight between them lands
        # on one or the other depending on the viewer's font.
        rules.append(
            _rule(
                f".{FIXED_LETTER_LAYER} text",
                f"{_letter_declarations(geometry)};font-weight:bold",
            )
        )
    rules.extend(_rule(f".{style.css_class}", f"fill:{style.tint}") for style in styles)
    return "<style>" + "".join(f"\n{_INDENT}{rule}" for rule in rules) + "\n</style>"
