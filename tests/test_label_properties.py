"""Grouped suite: property test for a theme label on its way into the drawn SVG.

A theme label is the one piece of operator text the renderer draws, and every
subcommand that draws reaches it through `cw_grid_document.parse_document`: `preview`,
`shade` and `gaps` read a grid file through it, and `fill --preview` narrows
the document it has just built through the same function. So the property is
stated there. Whatever label `parse_document` accepts renders into an SVG an
XML parser reads back with the label intact, and whatever it does not accept
it refuses as an `EmitError`, never as a crash.

The draw is weighted toward the characters at stake -- the controls, the
surrogates, U+FFFE/U+FFFF, the XML metacharacters and the neighbors of each --
because arbitrary text rarely lands on one, and it includes the surrogates,
which a plain text strategy never draws.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_command_base  # noqa: E402 - import follows the sys.path bootstrap above
import cw_emit  # noqa: E402 - same bootstrap
import cw_grid_document  # noqa: E402 - same bootstrap
import cw_svg  # noqa: E402 - same bootstrap
from tests import svg_fixtures  # noqa: E402 - same bootstrap

# A registered profile loaded at import, never an `@settings` decorator, which
# would pin the property's settings where no campaign runner could re-stamp
# them. Derandomized so the in-suite run is reproducible; no deadline, because
# a per-example wall clock measures machine load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_label_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_label_properties")

#: The characters the property is about, the ones either side of each range,
#: and the XML metacharacters. Written as escapes, one to a string, so no
#: editor can fuse two surrogates into one astral character on the way in.
_CONTROLS = ("\x00", "\t", "\n", "\r", "\x1b", "\x1f", "\x7f", "\x80", "\x85", "\x9f")
_NEIGHBORS = ("\xa0", "\xad", "\U0000d7ff", "\U0000e000", "\U0000fffd")
_NONCHARACTERS = ("\U0000d800", "\U0000dfff", "\U0000fffe", "\U0000ffff")
_MARKUP = ("&", "<", ">", "]", "'", '"')
_EDGES = _CONTROLS + _NEIGHBORS + _NONCHARACTERS + _MARKUP

#: Any character at all, surrogates included, or one of the edges above.
_CHARACTER = st.one_of(st.characters(exclude_categories=()), st.sampled_from(_EDGES))

_LABEL = st.text(alphabet=_CHARACTER, max_size=8)


def _document(label: str) -> dict[str, object]:
    """A 3x3 grid document whose one theme carries `label`."""
    return {
        "rows": list(svg_fixtures.SMALL_ROWS),
        "themes": {"pets": {"label": label, "summary": "Two cats"}},
        "clues": {"CAT": {"clue": "", "theme": "pets"}},
    }


def _drawn_labels(document: cw_grid_document.GridDocument) -> list[str]:
    """The text of every label the legend draws for `document`."""
    rendered = cw_command_base.render(
        document, (), svg_fixtures.DEFAULT_CELL, None, None
    )
    drawn = svg_fixtures.children(rendered, cw_svg.LEGEND_LAYER, "text")
    return [node.text or "" for node in drawn]


class TestDrawnLabels(unittest.TestCase):
    """A label the reader accepts is one the SVG can carry."""

    @given(_LABEL)
    @example("Cats & <dogs> ]]>")
    @example("")
    @example("Pets\x01")
    @example("Pets\x1b]0;x\x07")
    @example("Pets\x85")
    @example("Pets\U0000d800")
    @example("Pets\U0000fffe")
    def test_an_accepted_label_draws_into_a_parseable_svg(self, label: str) -> None:
        try:
            document = cw_grid_document.parse_document(_document(label))
        except cw_emit.EmitError:
            return
        self.assertEqual(_drawn_labels(document), [label])

    def test_accepts_and_draws_markup_and_a_bidi_control(self) -> None:
        # The property returns early on a refusal, so a reader that refused
        # every label would pass it. This label must be read and drawn intact.
        label = "Cats & <dogs> ]]>\U0000202e"
        document = cw_grid_document.parse_document(_document(label))
        self.assertEqual(_drawn_labels(document), [label])


if __name__ == "__main__":
    unittest.main()
