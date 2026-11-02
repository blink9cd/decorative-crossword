r"""Grouped suite: what reading a bank file returns, held to an oracle, whatever its bytes hold.

`test_loader_properties.py` holds `cw_bank.read_bank_payload` to returning or
refusing and nothing else. This holds what it returns: the value the standard
library alone reads from the same bytes, nested no deeper than the ceiling,
so a reader that quietly changed a value on the way through would fail here,
where never crashing says nothing about it. The draw is the whole file: bytes
that are not UTF-8, a byte-order mark, JSON's `NaN` and `Infinity`, a
`\udXXX` escape that reads back as a lone surrogate, a key written twice,
nesting past the ceiling. Whatever it reads goes on to `parse_bank`, so all of
`load_bank` is reached.

Run through test_decorative_crossword.py's `load_tests` hook, or imported by
location by a campaign runner, which is why the bootstrap below names the
project root and `src/` itself.
"""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_json  # noqa: E402 - same bootstrap
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
    "crossword_bank_file_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_bank_file_properties")

#: Any character at all, surrogates included, or one of those this read is
#: about: a control, the two line ends `str.splitlines` adds, the mark, and
#: the two characters JSON escapes.
_CHARACTER = st.one_of(
    st.characters(exclude_categories=()),
    st.sampled_from(("\x00", "\x1b", "\x85", "\U00002028", "\U0000feff", '"', "\\")),
)

_TEXT = st.text(alphabet=_CHARACTER, max_size=6)

#: Every JSON scalar, every float among them: `NaN` and both infinities are
#: what JSON writes for them, and what `json.loads` reads back.
_SCALAR = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), _TEXT)

#: The keys a bank uses, so drawn objects often take a bank's shape.
_KEY = st.one_of(
    st.sampled_from(("themes", "entries", "answer", "theme", "clue", "rating")),
    st.sampled_from(("label", "summary")),
    _TEXT,
)

#: A bank `parse_bank` takes whole, every optional field present, so the
#: property reaches the far side of the parse as well as its refusals: a bank
#: drawn at random is almost never one.
_WHOLE_BANK: dict[str, object] = {
    "themes": {"t": {"label": "Label", "summary": "Summary"}},
    "entries": [{"answer": "CAT", "theme": "t", "clue": "Clue", "rating": 3}],
}

#: A file: that bank, or it with one field replaced; JSON text in a bank's
#: shape; each as saved, behind a byte-order mark, or any bytes at all.
_FILE = st.one_of(
    loader_fixtures.json_files(_WHOLE_BANK),
    loader_fixtures.input_files(loader_fixtures.json_texts(_SCALAR, _KEY)),
)

#: A theme key that reads back as a lone surrogate, in a bank otherwise whole,
#: so the parse reaches the screen that refuses it rather than an earlier fault.
_SURROGATE_KEY = json.dumps(
    {
        "themes": {"\U0000d800": {"label": "Label", "summary": "Summary"}},
        "entries": [{"answer": "CAT"}],
    }
).encode()

#: One level past the ceiling, which nothing drawn at random nests.
_TOO_DEEP = b"[" * (cw_json.MAX_DEPTH + 1) + b"]" * (cw_json.MAX_DEPTH + 1)


def _depth(value: object) -> int:
    """How many objects and arrays `value` nests, counted without the subject."""
    if isinstance(value, dict):
        return 1 + max(map(_depth, value.values()), default=0)
    if isinstance(value, list):
        return 1 + max(map(_depth, value), default=0)
    return 0


class TestReadingABankFile(unittest.TestCase):
    """Any file reads as the value the standard library reads, or a `BankError` naming it."""

    @given(_FILE)
    @example(json.dumps(_WHOLE_BANK).encode())
    @example(b'{"themes": {}, "entries": [{"answer": "CAT", "answer": "DOG"}]}')
    @example(b'{"themes": {}, "entries": [{"answer": "CAT", "rating": NaN}]}')
    @example(_SURROGATE_KEY)
    @example(_TOO_DEEP)
    @example(b"\xef\xbb\xbf{}")
    @example(b"\xff")
    def test_fuzz_read_bank_payload(self, data: bytes) -> None:
        """A value `parse_bank` then takes or refuses, or a refusal naming the file."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.json"
            path.write_bytes(data)
            try:
                payload = cw_bank.read_bank_payload(path)
            except cw_bank.BankError as exc:
                self.assertIn(str(path), str(exc))
                return
        self.assertLessEqual(_depth(payload), cw_json.MAX_DEPTH)
        # The value the standard library alone reads from the same bytes,
        # compared as JSON text because a NaN is not equal to itself.
        self.assertEqual(
            json.dumps(payload), json.dumps(json.loads(data.decode("utf-8")))
        )
        with contextlib.suppress(cw_bank.BankError):
            cw_bank.parse_bank(payload)


if __name__ == "__main__":
    unittest.main()
