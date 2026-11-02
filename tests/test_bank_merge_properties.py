"""Grouped suite: the property test for merging several bank files.

`cw_bank_merge.parse_banks` is untrusted input a second time over: each bank
is an operator's hand-edited file, and the merge decides what happens when two
of them talk about the same answer or the same theme. `tests/test_bank_merge.py`
proves each rule by a hand-worked case; this module asserts the whole rule at
once over generated sets of banks, and carries the `test_fuzz_parse_banks`
paired with the `# fuzz-target` marker on `parse_banks`.

The property is a biconditional, because either half alone cannot fail on the
defect that matters most. A merge that silently kept the first of two
different records never raises, so "every raise is a BankError" passes it; a
merge that refused every repeat is never wrong about what it returns, so "every
returned bank is consistent" passes that. Here a set of well-formed banks is
accepted exactly when it is consistent (no answer recorded two ways, no theme
declared two ways, no entry naming a theme no bank declares), and what comes
back holds each record once, in the order the banks were given.

The oracle restates the rule rather than calling the subject, so the
hand-worked cases in `tests/test_bank_merge.py` stay the rule's authority.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location, so, as `tests/test_properties.py` explains, the bootstrap below
names both the project root and `src/`.
"""

from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_bank  # noqa: E402 - import follows the sys.path bootstrap above
import cw_bank_merge  # noqa: E402 - same bootstrap

# A registered profile under this module's own name, for the reasons
# `tests/test_properties.py` gives: a decorator would stop a campaign runner
# re-stamping its own.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_bank_merge_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_bank_merge_properties")

#: Small pools on purpose: two banks only disagree about an answer or a theme
#: when they both draw it, so a wide pool would make the refusals rare.
_KEYS = ("a", "b")
_ANSWERS = ("AB", "CD", "EF")

#: Two records for one theme key, differing in the summary alone.
_THEME_RECORDS = (
    {"label": "A", "summary": "One"},
    {"label": "A", "summary": "Two"},
)

#: Payloads no merge may accept, whatever sits beside them: not an object, an
#: empty entries list, no themes map, and one answer twice in a single file.
_MALFORMED: tuple[object, ...] = (
    None,
    {"themes": {}, "entries": []},
    {"entries": [{"answer": "AB"}]},
    {"themes": {}, "entries": [{"answer": "AB"}, {"answer": "AB"}]},
)

#: A bank file as the merge receives it: the name it is refused under, and its payload.
BankFile = tuple[str, object]


@st.composite
def _payloads(draw: st.DrawFn) -> object:
    """One bank payload: usually a well-formed one, sometimes a malformed one."""
    if draw(st.integers(min_value=0, max_value=5)) == 0:
        return draw(st.sampled_from(_MALFORMED))
    keys = draw(st.lists(st.sampled_from(_KEYS), unique=True, max_size=2))
    themes = {key: draw(st.sampled_from(_THEME_RECORDS)) for key in keys}
    answers = draw(
        st.lists(st.sampled_from(_ANSWERS), unique=True, min_size=1, max_size=3)
    )
    entries: list[dict[str, object]] = []
    for answer in answers:
        record: dict[str, object] = {"answer": answer}
        theme = draw(st.sampled_from((None, *_KEYS)))
        if theme is not None:
            record["theme"] = theme
        if draw(st.booleans()):
            record["clue"] = "x"
        entries.append(record)
    return {"themes": themes, "entries": entries}


def _named(payloads: list[object]) -> tuple[BankFile, ...]:
    """Each payload under a distinct file name, in the order drawn."""
    return tuple(
        (f"bank{index}.json", payload) for index, payload in enumerate(payloads)
    )


#: One to three banks, merged in the order drawn.
_BANK_SETS = st.lists(_payloads(), min_size=1, max_size=3).map(_named)


def _well_formed(payload: object) -> bool:
    """Whether `payload` is shaped as `_payloads` builds a valid bank."""
    if not isinstance(payload, Mapping):
        return False
    themes = payload.get("themes")
    entries = payload.get("entries")
    if not isinstance(themes, Mapping) or not isinstance(entries, list) or not entries:
        return False
    answers = [entry["answer"] for entry in entries]
    return len(set(answers)) == len(answers)


def _records(files: Sequence[BankFile], field: str) -> list[Mapping[str, object]]:
    """Every entry record, or every theme record keyed in, across well-formed files."""
    found: list[Mapping[str, object]] = []
    for _, payload in files:
        assert isinstance(payload, Mapping)
        if field == "entries":
            found.extend(payload["entries"])
        else:
            found.extend(
                {"key": key, **record} for key, record in payload["themes"].items()
            )
    return found


def _first_by(
    records: Sequence[Mapping[str, object]], key: str
) -> dict[object, Mapping[str, object]]:
    """The first record for each value of `key`, in order of first appearance."""
    first: dict[object, Mapping[str, object]] = {}
    for record in records:
        first.setdefault(record[key], record)
    return first


def _consistent(files: Sequence[BankFile]) -> bool:
    """Whether a set of well-formed banks agrees with itself, restated from the rule."""
    entries = _records(files, "entries")
    themes = _records(files, "themes")
    first_entry = _first_by(entries, "answer")
    first_theme = _first_by(themes, "key")
    return (
        all(record == first_entry[record["answer"]] for record in entries)
        and all(record == first_theme[record["key"]] for record in themes)
        and all(
            "theme" not in record or record["theme"] in first_theme
            for record in entries
        )
    )


class TestBankMergeProperties(unittest.TestCase):
    """parse_banks accepts exactly the consistent sets, and returns each record once."""

    # Each `@example` is a set the rule decides by name, pinned so no assertion
    # below is reachable only by the luck of the draw: an identical record
    # kept once, a record that differs, a theme declared two ways, and an entry
    # naming a theme only another bank declares.
    @given(_BANK_SETS)
    @example(
        (
            ("bank0.json", {"themes": {}, "entries": [{"answer": "AB"}]}),
            ("bank1.json", {"themes": {}, "entries": [{"answer": "AB"}]}),
        )
    )
    @example(
        (
            ("bank0.json", {"themes": {}, "entries": [{"answer": "AB"}]}),
            ("bank1.json", {"themes": {}, "entries": [{"answer": "AB", "clue": "x"}]}),
        )
    )
    @example(
        (
            (
                "bank0.json",
                {"themes": {"a": _THEME_RECORDS[0]}, "entries": [{"answer": "AB"}]},
            ),
            (
                "bank1.json",
                {"themes": {"a": _THEME_RECORDS[1]}, "entries": [{"answer": "CD"}]},
            ),
        )
    )
    @example(
        (
            ("bank0.json", {"themes": {}, "entries": [{"answer": "AB", "theme": "a"}]}),
            (
                "bank1.json",
                {"themes": {"a": _THEME_RECORDS[0]}, "entries": [{"answer": "CD"}]},
            ),
        )
    )
    def test_fuzz_parse_banks(self, files: tuple[BankFile, ...]) -> None:
        """Accepted exactly when consistent; what is accepted holds each record once, in order.

        The try/except is the crash-freedom half: any exception other than
        BankError escapes it and fails the test.
        """
        try:
            merged = cw_bank_merge.parse_banks(files)
        except cw_bank.BankError:
            self.assertFalse(
                all(_well_formed(payload) for _, payload in files)
                and _consistent(files),
                "a consistent set of well-formed banks was refused",
            )
            return
        self.assertTrue(all(_well_formed(payload) for _, payload in files))
        self.assertTrue(_consistent(files), "an inconsistent set of banks was accepted")
        first_entry = _first_by(_records(files, "entries"), "answer")
        self.assertEqual(
            [(entry.answer, entry.theme, entry.clue) for entry in merged.bank.entries],
            [
                (record["answer"], record.get("theme"), record.get("clue"))
                for record in first_entry.values()
            ],
        )
        self.assertEqual(
            list(merged.bank.themes), list(_first_by(_records(files, "themes"), "key"))
        )
        self.assertEqual(
            merged.files,
            tuple(
                (name, len(_records(((name, payload),), "entries")))
                for name, payload in files
            ),
        )


if __name__ == "__main__":
    unittest.main()
