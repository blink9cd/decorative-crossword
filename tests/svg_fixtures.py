"""Fixtures and parse helpers shared by the suites that build or read a render.

Named `*_fixtures.py` rather than `test_*.py` on purpose: the aggregator
discovers `test_*.py` only, so this module carries no floor of its own and is
never miscounted as a suite -- like every `*_fixtures.py` module here.

The wide fixture is deliberately NON-SQUARE and MULTI-THEME. A square,
single-themed default hides two whole input shapes from every test built on
it: a row/column transposition renders identically on a square grid, and a
one-theme grid never exercises the tint cycle, the marker cycle, or the
tie-break at a crossing where two entries carry different themes.

The helpers below parse the render rather than string-matching it, because the
failure this module's subject exists to prevent -- a malformed document that
renders as a blank page -- is invisible to a substring check.
"""

import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping
from typing import cast

import cw_config
import cw_svg

#: The `--cell` default, taken from `cw_config.DEFAULTS`, the one place that
#: owns it. A literal here would be a second copy of it, and the fixture's
#: point is only that every suite renders at one known size -- not at one
#: particular number. `cast` because `DEFAULTS` is a `Mapping[str, object]`.
DEFAULT_CELL = cast(int, cw_config.DEFAULTS["cell"])

#: A 3x3 single-theme grid. ACROSS: CAT, WET. DOWN: COW. Small enough that a
#: hand-computed geometry assertion stays readable, and the shape the featured
#: answer (COW, three cells) is pinned against.
SMALL_ROWS = ("CAT", "O..", "WET")
SMALL_THEMES: Mapping[str, str] = {"pets": "Pets"}
SMALL_ENTRY_THEMES: Mapping[str, str] = {"CAT": "pets", "COW": "pets"}

#: A 4-row x 5-column grid, so a rows/cols transposition is visible.
#: ACROSS: PLUMS (0,0), ARENA (2,0). DOWN: PEAR (0,0), SOAR (0,4).
#: Six of its twenty cells are blocked, which is exactly 30.0%.
WIDE_ROWS = ("PLUMS", "E...O", "ARENA", "R...R")

#: Five declared themes against four marker shapes, so the marker cycle wraps
#: inside one fixture; "water" has no placed entry, so the zero-count path for
#: a declared theme is exercised by the default wide render rather than by a
#: special case somebody has to remember to write.
WIDE_THEMES: Mapping[str, str] = {
    "flight": "Flight",
    "fruit": "Fruit",
    "places": "Places",
    "trees": "Trees",
    "water": "Water",
}

#: PLUMS (ACROSS) and PEAR (DOWN) cross at (0, 0) carrying DIFFERENT themes,
#: which is what makes the crossing tie-break observable at all.
WIDE_ENTRY_THEMES: Mapping[str, str] = {
    "PLUMS": "fruit",
    "PEAR": "trees",
    "ARENA": "places",
    "SOAR": "flight",
}

#: Cells the wide grid's themed entries own, keyed by theme id, under the
#: documented ACROSS-before-DOWN tie-break. Written out rather than computed so
#: the expectation is an independent statement instead of a second copy of the
#: rule it checks.
WIDE_THEME_CELLS: Mapping[str, tuple[tuple[int, int], ...]] = {
    "fruit": ((0, 0), (0, 1), (0, 2), (0, 3), (0, 4)),
    "places": ((2, 0), (2, 1), (2, 2), (2, 3), (2, 4)),
    "trees": ((1, 0), (3, 0)),
    "flight": ((1, 4), (3, 4)),
}


def request(
    *,
    rows: tuple[str, ...] = SMALL_ROWS,
    themes: Mapping[str, str] = SMALL_THEMES,
    entry_themes: Mapping[str, str] = SMALL_ENTRY_THEMES,
    feature: str | None = None,
    features: tuple[str, ...] = (),
    cell: int = DEFAULT_CELL,
    settings: Mapping[str, str] | None = None,
    hidden: cw_svg.HiddenShading | None = None,
    gaps: tuple[tuple[int, int], ...] = (),
    fixed: tuple[tuple[int, int], ...] = (),
    empty_blocks: bool = False,
) -> cw_svg.RenderRequest:
    """The small single-theme request, with any field overridden by keyword.

    Keyword parameters rather than a `**overrides` dict so every override stays
    type-checked; an untyped splat would need a suppression to pass mypy.
    """
    return cw_svg.RenderRequest(
        rows=rows,
        themes=themes,
        entry_themes=entry_themes,
        # `feature` is the one-answer spelling most suites use; it goes ahead
        # of any explicit `features`, and passes an empty string straight
        # through so the renderer's own normalization is what gets tested.
        features=features if feature is None else (feature, *features),
        cell=cell,
        settings=settings,
        hidden=hidden,
        gaps=gaps,
        fixed=fixed,
        empty_blocks=empty_blocks,
    )


def wide_request(
    *,
    rows: tuple[str, ...] = WIDE_ROWS,
    themes: Mapping[str, str] = WIDE_THEMES,
    entry_themes: Mapping[str, str] = WIDE_ENTRY_THEMES,
    feature: str | None = None,
    features: tuple[str, ...] = (),
    cell: int = DEFAULT_CELL,
    settings: Mapping[str, str] | None = None,
    hidden: cw_svg.HiddenShading | None = None,
    fixed: tuple[tuple[int, int], ...] = (),
    empty_blocks: bool = False,
) -> cw_svg.RenderRequest:
    """The non-square multi-theme request, with any field overridden by keyword."""
    return request(
        rows=rows,
        themes=themes,
        entry_themes=entry_themes,
        feature=feature,
        features=features,
        cell=cell,
        settings=settings,
        hidden=hidden,
        fixed=fixed,
        empty_blocks=empty_blocks,
    )


def _tag(local_name: str) -> str:
    """The namespace-qualified ElementTree tag for one SVG element name.

    Built from the subject's own namespace constant so the suites never restate
    the URL -- restating it is how a namespace change passes a green suite.
    """
    return f"{{{cw_svg.SVG_NAMESPACE}}}{local_name}"


def parse(rendered: str) -> ElementTree.Element:
    """The rendered document as an element tree, raising on a malformed one."""
    return ElementTree.fromstring(rendered)


def layers(rendered: str) -> dict[str, ElementTree.Element]:
    """Every `<g>` in the document, keyed by its class attribute.

    A missing layer surfaces as a KeyError at the point of use, which is a loud
    local failure -- so there is no lookup-failed branch here to leave uncovered.
    """
    return {str(group.get("class")): group for group in parse(rendered).iter(_tag("g"))}


def children(
    rendered: str, layer_class: str, local_name: str
) -> list[ElementTree.Element]:
    """Every `local_name` element inside the layer carrying `layer_class`."""
    return list(layers(rendered)[layer_class].iter(_tag(local_name)))


def cell_classes(rendered: str) -> list[str]:
    """The class of every cell background rect, in emitted order."""
    return [
        str(rect.get("class")) for rect in children(rendered, cw_svg.CELL_LAYER, "rect")
    ]


def caption_lines(rendered: str) -> list[str]:
    """The text of every caption line, in emitted order."""
    return [str(node.text) for node in children(rendered, cw_svg.CAPTION_LAYER, "text")]


def legend_labels(rendered: str) -> list[str]:
    """The label text of every legend row, in emitted order."""
    return [str(node.text) for node in children(rendered, cw_svg.LEGEND_LAYER, "text")]


def marker_tags(rendered: str, layer_class: str) -> list[str]:
    """The element name of every marker in `layer_class`, in emitted order.

    Markers are direct children of their layer, so this reads the shapes that
    were drawn without also picking up anything nested beneath them.
    """
    return [element.tag.rpartition("}")[2] for element in layers(rendered)[layer_class]]


def stylesheet(rendered: str) -> str:
    """The text of the document's `<style>` element(s)."""
    return "".join(str(node.text) for node in parse(rendered).iter(_tag("style")))


def rule_values(rendered: str, prop: str, *selectors: str) -> list[str]:
    """The value each selector declares for `prop`, read out of the stylesheet.

    An ink that renders invisibly -- shading, marker or text in the paper
    color, a grid rule the color of the cells it separates -- is present in
    the markup and absent from the picture, so it can only be caught by
    comparing the VALUES the document declares.

    `selectors` are given without their leading `.`, and may be descendant
    selectors ("cw-letters text"). A selector that declares no such property
    contributes no entry, which a length assertion at the call site turns into
    a loud failure.

    Scoped to `stylesheet(rendered)` rather than the whole document, so the
    search really is over the stylesheet this docstring claims -- there is no
    element text anywhere else that could satisfy the pattern by accident.
    """
    style = stylesheet(rendered)
    return [
        match.group(1)
        for selector in selectors
        for match in re.finditer(
            rf"\.{re.escape(selector)}\{{[^}}]*(?<![-\w]){re.escape(prop)}:([^;}}]+)",
            style,
        )
    ]


def page_rect(rendered: str) -> ElementTree.Element:
    """The rect that covers the whole viewBox: the page the document paints.

    Found by GEOMETRY among the root's own children, not by a class name the
    suite and the subject would otherwise share -- the question is what this
    document actually paints behind everything it draws, and a name proves
    nothing about coverage. A document that paints no page has no such rect and
    this raises KeyError, which is the point: an assertion fed from here must
    not keep passing once the background is deleted.
    """
    root = parse(rendered)
    _, _, width, height = str(root.get("viewBox")).split()
    covering = {
        (str(node.get("width")), str(node.get("height"))): node
        for node in root.findall(_tag("rect"))
    }
    return covering[(width, height)]


def page_fill(rendered: str) -> str:
    """The color the document paints behind everything it draws."""
    (fill,) = rule_values(rendered, "fill", str(page_rect(rendered).get("class")))
    return fill


def cell_boxes(
    rendered: str,
) -> dict[tuple[int, int], tuple[float, float, float, float]]:
    """Each cell's (left, top, width, height), keyed by (row, col).

    Rows and columns are recovered from the distinct y and x values the
    document itself carries, not from the emission order and not from the
    geometry formula -- so a caller asking "which cell is this point in" gets
    an answer derived from the picture rather than from the code that drew it.
    """
    boxes = [
        (
            float(str(node.get("y"))),
            float(str(node.get("x"))),
            float(str(node.get("width"))),
            float(str(node.get("height"))),
        )
        for node in children(rendered, cw_svg.CELL_LAYER, "rect")
    ]
    tops = sorted({top for top, _, _, _ in boxes})
    lefts = sorted({left for _, left, _, _ in boxes})
    return {
        (tops.index(top), lefts.index(left)): (left, top, width, height)
        for top, left, width, height in boxes
    }


def _circle_anchor(node: ElementTree.Element) -> tuple[float, float]:
    """A circle's center."""
    return float(str(node.get("cx"))), float(str(node.get("cy")))


def _rect_anchor(node: ElementTree.Element) -> tuple[float, float]:
    """A rect's center."""
    return (
        float(str(node.get("x"))) + float(str(node.get("width"))) / 2,
        float(str(node.get("y"))) + float(str(node.get("height"))) / 2,
    )


def _polygon_anchor(node: ElementTree.Element) -> tuple[float, float]:
    """A polygon's centroid, which for a triangle lies inside it."""
    pairs = [point.split(",") for point in str(node.get("points")).split()]
    return (
        sum(float(pair[0]) for pair in pairs) / len(pairs),
        sum(float(pair[1]) for pair in pairs) / len(pairs),
    )


#: A point known to lie inside each marker shape, by element name.
_ANCHORS = {
    "circle": _circle_anchor,
    "rect": _rect_anchor,
    "polygon": _polygon_anchor,
}


def marker_cells(rendered: str, layer_class: str) -> dict[tuple[int, int], str]:
    """Which grid cell each marker sits inside, and what shape it is.

    Located by containment of ONE ANCHOR POINT -- a circle's center, a rect's
    center, a triangle's centroid -- in the cell boxes read out of the
    document, rather than by recomputing the marker's own offsets: the question
    a placement test has to answer is whether the marker landed on the right
    cell, not whether it reproduces one particular formula. A marker whose
    anchor lands outside every cell contributes no entry, so it shows up as a
    missing key.

    The limit is worth stating, because it is easy to over-read: this locates
    the anchor, not the shape. A marker whose anchor stays home while its
    outline bleeds into the neighboring cell is NOT caught here. Pinning the
    outline is the golden sample's job; this bounds gross misplacement only.
    """
    boxes = cell_boxes(rendered)
    found: dict[tuple[int, int], str] = {}
    for node in layers(rendered)[layer_class]:
        name = node.tag.rpartition("}")[2]
        point_x, point_y = _ANCHORS[name](node)
        for cell, (left, top, width, height) in boxes.items():
            if left <= point_x <= left + width and top <= point_y <= top + height:
                found[cell] = name
    return found


def letter_cells(rendered: str, layer_class: str) -> dict[tuple[int, int], str]:
    """Which grid cell each letter in `layer_class` is drawn in, and the letter.

    Located the way `marker_cells` locates a marker: the text's own anchor
    point, contained in the cell boxes read out of the document. So the answer
    to "which cells did this layer letter" comes from the picture, not from the
    geometry formula that drew it. A letter centered outside every cell
    contributes no entry, and shows up as a missing key.
    """
    boxes = cell_boxes(rendered)
    found: dict[tuple[int, int], str] = {}
    for node in children(rendered, layer_class, "text"):
        point_x, point_y = float(str(node.get("x"))), float(str(node.get("y")))
        for cell, (left, top, width, height) in boxes.items():
            if left <= point_x <= left + width and top <= point_y <= top + height:
                found[cell] = str(node.text)
    return found
