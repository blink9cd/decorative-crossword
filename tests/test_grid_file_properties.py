r"""Grouped suite: what reading a grid file returns, held to an oracle, whatever its bytes hold.

`load_document` is the one reader of a grid file -- `preview`, `shade`, `gaps`
and `fill --source` all come through it -- and a grid file is one this tool
may never have written. `test_loader_properties.py` holds it to returning or
refusing and nothing else; this holds what it RETURNS to a coherent grid
re-derived here -- every row as long as the first, every cell a letter A-Z or a
block -- and to the rows the standard library alone reads from the same bytes.
The draw is the whole file: bytes that are not UTF-8, a byte-order mark,
JSON's `NaN` and `Infinity`, a `\udXXX` escape that reads back as a lone
surrogate, a key written twice, and documents of drawn rows, often enough
coherent to reach the validators behind the parse.

Run through test_decorative_crossword.py's `load_tests` hook, or imported by
location by a campaign runner, which is why the bootstrap below names the
project root and `src/` itself.
"""

from __future__ import annotations

import json
import string
import sys
import tempfile
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_emit  # noqa: E402 - import follows the sys.path bootstrap above
import cw_grid  # noqa: E402 - same bootstrap
import cw_grid_document  # noqa: E402 - same bootstrap
from tests import loader_fixtures  # noqa: E402 - same bootstrap

# A registered profile loaded at import, never an `@settings` decorator, which
# would pin the property's settings where no campaign runner could re-stamp
# them. Derandomized so the in-suite run is reproducible; no deadline, because
# a per-example wall clock measures machine load rather than correctness.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_grid_file_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_grid_file_properties")

#: Any character at all, surrogates included, or a cell a row can hold.
_CHARACTER = st.one_of(
    st.characters(exclude_categories=()),
    st.sampled_from(("A", "B", cw_grid.BLOCK, "\x00", "\U0000feff")),
)

_TEXT = st.text(alphabet=_CHARACTER, max_size=6)

#: A row of cells, as a grid's rows are drawn: mostly letters and blocks.
_ROW = st.text(alphabet="AB" + cw_grid.BLOCK, min_size=1, max_size=4)

#: Every JSON scalar, every float among them, and rows often enough.
_SCALAR = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), _TEXT, _ROW)

#: The keys a grid document uses, so drawn objects often take its shape.
_KEY = st.one_of(
    st.sampled_from(("rows", "themes", "clues", "label", "summary", "clue")),
    st.sampled_from(("theme", "AB", "BA")),
    _TEXT,
)


def _document(rows: list[str]) -> dict[str, object]:
    """A grid document of `rows`, with one theme and a clue record for its first row."""
    return {
        "rows": rows,
        "themes": {"t": {"label": "Label", "summary": "Summary"}},
        "clues": {rows[0]: {"theme": "t", "clue": "Clue"}},
    }


#: A file: a document of drawn rows, or it with one field replaced; JSON text
#: in a grid document's shape; each as saved, behind a byte-order mark, or any
#: bytes at all. The rows are drawn rather than fixed, so an accepted document
#: holds rows of every shape the draw makes, not one grid over and over.
_FILE = st.one_of(
    st.lists(_ROW, min_size=1, max_size=4).flatmap(
        lambda rows: loader_fixtures.json_files(_document(rows))
    ),
    loader_fixtures.input_files(loader_fixtures.json_texts(_SCALAR, _KEY)),
)

#: What a cell of a coherent grid may hold.
_CELLS = frozenset(string.ascii_uppercase + cw_grid.BLOCK)

#: A document the reader takes whole: two rows, a theme, and clue records
#: beside them, one clued and one empty. It carries the property past the parse
#: with themes and clues to narrow, which a drawn document seldom brings.
_WHOLE_DOCUMENT = json.dumps(
    {
        "rows": ["AB", "BA"],
        "themes": {"t": {"label": "Label", "summary": "Summary"}},
        "clues": {"AB": {"theme": "t", "clue": "Clue"}, "BA": {}},
    }
).encode()


class TestReadingAGridFile(unittest.TestCase):
    """Any file reads as a coherent document or an `EmitError` naming it."""

    @given(_FILE)
    @example(_WHOLE_DOCUMENT)
    @example(b'{"rows": ["AB"], "rows": ["BA"]}')
    @example(b'{"rows": ["AB"], "themes": {"t": {"label": NaN, "summary": "s"}}}')
    @example(
        json.dumps({"rows": ["AB"], "themes": {"t": {"label": "\U0000dc80"}}}).encode()
    )
    @example(b'{"rows": ["AB"], "clues": {"AB": {"clue": Infinity}}}')
    @example(b"\xef\xbb\xbf{}")
    # Refusals the draw reaches only now and then, pinned because the property
    # sees each one lost or crashing: a cell no grid holds (a lowercase letter,
    # and a capital outside A-Z), a grid of no cells, and a number where an
    # object belongs.
    @example(b'{"rows": ["ab"]}')
    @example(json.dumps({"rows": ["\U000000c9A"]}).encode())
    @example(b'{"rows": [""]}')
    @example(b'{"rows": ["AB"], "clues": 5}')
    def test_fuzz_load_document(self, data: bytes) -> None:
        """A coherent document, or a refusal naming the file."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            path.write_bytes(data)
            try:
                document = cw_grid_document.load_document(path)
            except cw_emit.EmitError as exc:
                self.assertIn(str(path), str(exc))
                return
        widths = {len(row) for row in document.rows}
        self.assertEqual(len(widths), 1)
        self.assertGreater(widths.pop(), 0)
        self.assertLessEqual(set("".join(document.rows)), _CELLS)
        # A reader that dropped or rewrote a row could still hand back a
        # coherent grid, so the rows are held to the ones the standard library
        # alone reads from the same bytes.
        self.assertEqual(list(document.rows), json.loads(data.decode("utf-8"))["rows"])


if __name__ == "__main__":
    unittest.main()
