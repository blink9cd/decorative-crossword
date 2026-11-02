"""What the picture says about itself: the caption's two tiers.

Kept apart from `cw_svg` along a real seam, with its own suite
(`tests/test_svg_caption.py`): everything here turns values into text, and
nothing here knows a rect from a viewBox.

The caption has two tiers, and the division is the whole point of the module:

- **Derivable from the grid**: its size, its achieved blocked percentage, its
  per-theme counts. Present on every render, however it was reached, because
  the grid alone supplies them.
- **Configuration**: the seed, the requested density range, the theme floor.
  These live nowhere in `grid_source.json`, so a bare `preview` cannot know
  them and stamps none of them. Inventing or defaulting them would put a number
  on the picture that nothing checked, which is worse than an absent field.

Three lines sit in neither tier (the featured answer, the hidden word and
the count of fixed letters) because each is supplied directly to the render
and each names something actually marked on it.

These functions take plain values rather than a `cw_svg.RenderRequest`: the
dependency runs one way, `cw_svg` to here, and taking the request would make it
run both. Entry point assumptions: imported by bare name after `src/` is on
`sys.path`, like every other module in this folder.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import cw_grid
import cw_svg_style

#: The caption's field separator and its percentage form. Both ASCII, so a
#: committed golden sample is not hostage to an encoding round-trip.
SEPARATOR = " | "
_PERCENT_FORMAT = ".1f"

_FEATURE_PREFIX = "Featured: "
_FEATURE_ABSENT_SUFFIX = " (not in this grid)"

_HIDDEN_PREFIX = "Hidden: "

#: Names the flag, as the `fill` report's own "From --source:" line does: only
#: a `fill --source` run hands the render fixed letters, so the picture and the
#: report use one word for one thing.
_FIXED_PREFIX = "Fixed from --source: "
_FIXED_SUFFIX = " letter(s), in bold"


def theme_counts(
    runs: Sequence[cw_grid.Run],
    entry_themes: Mapping[str, str],
    styles: Mapping[str, cw_svg_style.ThemeStyle],
) -> dict[str, int]:
    """Placed entries per declared theme, in the legend's own order.

    A declared theme with no placed entry counts zero rather than vanishing: it
    is still listed in the legend beside the caption, and a caption that
    quietly dropped it would disagree with the picture it describes.
    """
    counts = dict.fromkeys(styles, 0)
    for run in runs:
        theme_id = entry_themes.get(run.text)
        if theme_id is not None and theme_id in counts:
            counts[theme_id] += 1
    return counts


def derivable_line(
    rows: Sequence[str],
    entry_themes: Mapping[str, str],
    styles: Mapping[str, cw_svg_style.ThemeStyle],
    runs: Sequence[cw_grid.Run],
) -> str:
    """Size, achieved blocked percentage and per-theme counts.

    All three are readable off the grid alone, which is why this tier is on
    every render however the render was reached. The percentage is `cw_grid`'s,
    not a second implementation of the density arithmetic.

    A `--mask` is deliberately not consulted, so under one this figure and the
    `fill` report's differ: the report measures over the cells the picture
    leaves and says so, while this measures the whole grid. That is the point.
    A caption is drawn by `preview` as much as by `fill`, from a
    `grid_source.json` that records no mask, so a mask-aware caption would
    either be a lie on the standalone path or a reason to write the mask into
    the emitted grid, and the picture is an input, not a property of the grid
    it shaped.
    """
    cols = max((len(row) for row in rows), default=0)
    blocked = cw_grid.blocked_percent(rows)
    parts = [
        f"{len(rows)}x{cols} grid",
        f"{blocked:{_PERCENT_FORMAT}}% blocked",
    ]
    parts.extend(
        f"{styles[theme_id].label}: {count}"
        for theme_id, count in theme_counts(runs, entry_themes, styles).items()
    )
    return SEPARATOR.join(parts)


def feature_line(answer: str, run: cw_grid.Run | None) -> str:
    """Name the featured answer, saying so when the grid does not hold it.

    Naming it unconditionally would let the caption disagree with the picture:
    a line claiming a feature above a grid with nothing shaded. Saying which of
    the two is missing is the honest form of the absent field, which is
    preferred over an invented one.
    """
    if run is None:
        return f"{_FEATURE_PREFIX}{answer}{_FEATURE_ABSENT_SUFFIX}"
    return f"{_FEATURE_PREFIX}{answer}"


def hidden_line(word: str) -> str:
    """Name the hidden word whose scattered cells this render shades.

    No absent case to state, unlike `feature_line`: a hidden word arrives with
    its cells already chosen off this very grid, so there is no lookup here
    that could come back empty.
    """
    return f"{_HIDDEN_PREFIX}{word}"


def fixed_line(count: int) -> str:
    """Say what bold means on this picture, and how many letters carry it.

    Without it the weight would be a mark with no key: the legend explains
    tints and markers, and nothing else on the picture says why some letters
    are heavier. `count` is of letters drawn bold, so the line cannot claim
    more than the grid shows.
    """
    return f"{_FIXED_PREFIX}{count}{_FIXED_SUFFIX}"


def configuration_line(settings: Mapping[str, str]) -> str:
    """The tier the grid cannot supply: what the caller configured.

    Sorted by key so the same settings render identically however the caller
    assembled the mapping.
    """
    return SEPARATOR.join(f"{key}: {settings[key]}" for key in sorted(settings))
