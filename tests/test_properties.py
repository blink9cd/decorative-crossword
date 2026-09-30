"""Grouped suite: property tests for cw_bank's untrusted-input contract.

`cw_bank.parse_bank` is the project's untrusted-input boundary: it stands
between an operator's hand-edited `bank.json` and every downstream module,
none of which re-checks a `Bank`'s shape. Example tests in `tests/test_bank.py`
can walk every validation branch; that says nothing about the input space a
hand-edited JSON file can actually contain. This module supplies that: a
Hypothesis property, paired with the `# fuzz-target` marker on
`cw_bank.parse_bank`, asserting the parser never crashes and never accepts a
malformed record. It stays a file of its own because each parser that reads
untrusted input is marked `# fuzz-target` and has a property test named
`test_fuzz_<name>` in a sibling `*_properties.py` module. The strategies
several property suites share live in `property_strategies/`; this one's are
about bank payloads and are built below.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, or by a fuzzing campaign, which imports this file by
location. The bootstrap below puts the project root and `src/` on `sys.path`
itself, so this file's imports resolve the same way whichever of the two
loads it.
"""

from __future__ import annotations

import string
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "src"))

import cw_answer  # noqa: E402 - import follows the sys.path bootstrap above
import cw_bank  # noqa: E402 - same bootstrap
import cw_grid  # noqa: E402 - same bootstrap

# A REGISTERED profile, loaded at import, never an `@settings` decorator on the
# test itself. A `@given` test snapshots its settings when decorated, so a
# profile loaded later would be a no-op -- this has to run before the class body
# below executes. And a decorator would pin the property's settings where no
# campaign runner could re-stamp them: Hypothesis refuses a second settings
# object on a function that already carries one, so the decorator would pass
# every in-suite run and then break the first campaign anyone actually ran.
# `derandomize=True` fixes the example sequence so the in-suite run is
# reproducible; `deadline=None` because `parse_bank` is pure CPU work with no
# I/O, but a per-example wall-clock deadline is still a flakiness source under
# load rather than a correctness signal -- what should bound a genuinely wedged
# run is a timeout on the whole run, not Hypothesis's.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_bank_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_bank_properties")


# --- Strategies: arbitrary JSON-shaped garbage -------------------------------

#: Every scalar json.loads can ever hand back.
_JSON_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=10),
)

#: Arbitrary JSON-compatible values, containers included. `max_leaves` keeps the
#: recursion shallow and generation fast -- nothing about parse_bank's own
#: behavior depends on nesting depth, since it only ever looks one level into
#: `entries` and `themes`, so a deep tree would slow the campaign for no gain.
_JSON_LIKE = st.recursive(
    _JSON_SCALAR,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=8), children, max_size=5),
    ),
    max_leaves=10,
)

# --- Strategies: near-miss bank shapes ---------------------------------------
#
# Pure garbage above mostly lands on "payload is not even a mapping". These
# strategies build bank-shaped payloads with individual fields deliberately
# right or wrong, so the campaign also reaches the deeper per-entry branches
# (answer casing/length/charset, undeclared theme, non-string clue, a rating
# that is not a whole number from 1 to 5).

_FREE_ANSWER = st.text(
    alphabet=string.ascii_uppercase, min_size=cw_grid.MIN_RUN, max_size=8
)

#: Answers drawn from a pool small enough that one generated entries list
#: repeats one of them often. Free-form A-Z text of two to eight letters
#: collides so rarely that without this the duplicate-answer assertion below is
#: reached only by accident -- measured by deleting `parse_bank`'s duplicate
#: check and watching the property pass anyway.
_REPEATED_ANSWER = st.sampled_from(("AB", "ABC", "ZZ", "QQ"))

#: Answers written with a space, a hyphen or an apostrophe. `A B` closes up to
#: `AB`, which `_REPEATED_ANSWER` also draws, so two spellings of one answer --
#: a repeat by its letters but not by its text -- are reached as well.
_SPELLED_ANSWER = st.sampled_from(("A B", "AB-CD", "O'ZZ", "ROCK 'N' ROLL"))

#: `st.one_of` weights its branches evenly, so naming the free-form strategy
#: twice is what biases a draw toward a distinct answer while still repeating
#: often enough to exercise the duplicate check.
_VALID_ANSWER = st.one_of(_FREE_ANSWER, _FREE_ANSWER, _REPEATED_ANSWER, _SPELLED_ANSWER)

#: An answer long enough to clear `parse_bank`'s LENGTH check and still fail its
#: charset check. Its own branch because the other wrong-charset branches below
#: mostly do not reach that check: the lowercase one shrinks toward a single
#: letter, which is rejected for length first, so an answer that is the RIGHT
#: length and the wrong charset was a rare draw. Widening the space is all this
#: does; what makes that rejection reachable on every run is the pinned
#: `@example` below.
_WRONG_CHARSET_ANSWER = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-_ ",
    min_size=cw_grid.MIN_RUN,
    max_size=6,
)

_INVALID_ANSWER = st.one_of(
    _WRONG_CHARSET_ANSWER,
    st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6),
    st.text(alphabet=string.ascii_uppercase, max_size=cw_grid.MIN_RUN - 1),
    st.text(alphabet=string.digits, min_size=cw_grid.MIN_RUN, max_size=4),
    st.integers(),
    st.none(),
)
_ANSWER = st.one_of(_VALID_ANSWER, _INVALID_ANSWER)

_THEME_KEY = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6)
_THEME_VALUE = st.one_of(_THEME_KEY, st.integers(), st.none())
_CLUE_VALUE = st.one_of(st.text(max_size=20), st.integers(), st.none())

#: How far past either end of the rating scale a drawn integer may land -- far
#: enough to reach both refusals, near enough that on-scale values still turn up.
_RATING_OVERSHOOT = 3

#: Every shape a hand-typed rating takes, on the scale or off it. Booleans are
#: their own branch because `bool` is an `int` subclass in Python.
_RATING_VALUE = st.one_of(
    st.integers(
        min_value=cw_bank.MIN_RATING - _RATING_OVERSHOOT,
        max_value=cw_bank.MAX_RATING + _RATING_OVERSHOOT,
    ),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=3),
    st.none(),
)

_ENTRY_SHAPE = st.one_of(
    st.fixed_dictionaries(
        {"answer": _ANSWER},
        optional={
            "theme": _THEME_VALUE,
            "clue": _CLUE_VALUE,
            "rating": _RATING_VALUE,
        },
    ),
    st.text(max_size=10),
    st.integers(),
    st.none(),
)

_THEMES_SHAPE = st.one_of(
    st.dictionaries(
        _THEME_KEY, st.one_of(st.text(max_size=10), st.integers()), max_size=4
    ),
    st.integers(),
    st.none(),
)

_BANK_LIKE = st.fixed_dictionaries(
    {},
    optional={
        "themes": _THEMES_SHAPE,
        "entries": st.one_of(
            st.lists(_ENTRY_SHAPE, max_size=6), st.integers(), st.none(), st.text()
        ),
    },
)

#: The theme keys a well-formed payload may declare, plus one it never does --
#: so an entry naming an undeclared theme is drawn deliberately, not by luck.
_DECLARED_KEYS = ("a", "b", "c")
_UNDECLARED_KEY = "z"


def _theme_record(key: str) -> dict[str, str]:
    """A theme record `parse_bank` accepts: an object with a label and a summary.

    Every theme record in this file that is meant to parse is built here; the
    near-miss strategy's bare values are meant to be refused. A record of the
    wrong shape is refused before any entry is read, so a payload holding a
    stale copy of the shape never reaches the entry check it was written for --
    and the property still passes, because a refusal is an allowed outcome.

    The text is fixed, letters and spaces only, because the parser screens both
    fields: text drawn freely would sometimes be refused, and a payload built to
    parse must not be.
    """
    return {"label": key.upper(), "summary": f"Words filed under {key.upper()}"}


#: The wrong value to substitute into one field of one otherwise-good entry --
#: the shape a hand-edited bank.json actually takes when an operator mistypes.
#: One branch per distinct rejection that field can reach, weighted evenly,
#: rather than one grab-bag: in a grab-bag the charset rejection came out at one
#: draw in six, and a `parse_bank` with its charset check deleted passed this
#: property unchanged.
_CORRUPTIONS = {
    "answer": st.one_of(
        _WRONG_CHARSET_ANSWER,
        st.text(alphabet=string.ascii_uppercase, max_size=cw_grid.MIN_RUN - 1),
        st.one_of(st.integers(), st.none(), st.lists(st.text())),
    ),
    "theme": st.one_of(
        st.just(_UNDECLARED_KEY),
        st.integers(),
        # Unhashable, so a `theme not in themes` run before the type check
        # raises TypeError rather than BankError -- the crash this property
        # exists to catch, and the reason those two checks are ordered.
        st.lists(st.text()),
    ),
    "clue": st.one_of(
        st.integers(),
        st.just("a </script tag"),
        st.just("two\nlines"),
    ),
    "rating": st.one_of(
        st.integers(max_value=cw_bank.MIN_RATING - 1),
        st.integers(min_value=cw_bank.MAX_RATING + 1),
        # `bool` is an `int` subclass, so a type check that forgets it reads a
        # JSON `true` as a rating of 1.
        st.booleans(),
        st.one_of(
            st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=3)
        ),
    ),
}


def _widened(record: Mapping[str, object]) -> dict[str, object]:
    """A drawn entry as a mutable dict whose values are typed `object`.

    `st.fixed_dictionaries` types its result from the field strategies, so a
    drawn entry is a `dict[str, str | None]` and no corruption of another type
    can be written into it. Widening has to copy rather than re-label, because
    `dict` is invariant in its value type -- a `dict[str, str | None]` is not a
    `dict[str, object]`. Doing it once here keeps the composite below honest
    without a cast.
    """
    return dict(record)


@st.composite
def _conforming_payloads(draw: st.DrawFn) -> dict[str, object]:
    """A payload built to PARSE, with room for exactly one thing to be wrong.

    The two strategies above are near-misses and garbage. Measured over a
    thousand examples they returned a Bank ONCE, so every assertion this
    property makes about a returned bank was unreachable and the property was
    really only asserting "raises BankError". This branch is what reaches the
    other half: it always supplies a `themes` map of records `parse_bank`
    accepts and a non-empty `entries` list of the right shape, draws each
    entry's fields from values `parse_bank` accepts, and only then optionally
    corrupts ONE field of ONE entry. Because its theme records parse, a
    returned bank can be a themed one.

    Answers still repeat, because `_VALID_ANSWER` draws from a small pool on
    one of its branches, and one of its written spellings closes up to an
    answer that pool holds -- that is what makes the duplicate-answer
    rejection, and this property's assertion about it, reachable at all.
    """
    # A unique LIST, not a set: it keeps the order Hypothesis drew it in, so the
    # declared theme map is the same map on every run of the same example.
    keys = draw(st.lists(st.sampled_from(_DECLARED_KEYS), unique=True, max_size=3))
    entry = st.fixed_dictionaries(
        {"answer": _VALID_ANSWER},
        optional={
            "theme": st.sampled_from((*keys, None)) if keys else st.none(),
            "clue": st.one_of(st.text(max_size=20), st.none()),
            "rating": st.one_of(
                st.integers(min_value=cw_bank.MIN_RATING, max_value=cw_bank.MAX_RATING),
                st.none(),
            ),
        },
    ).map(_widened)
    entries = draw(st.lists(entry, min_size=1, max_size=5))
    field = draw(st.one_of(st.none(), st.sampled_from(sorted(_CORRUPTIONS))))
    if field is not None:
        index = draw(st.integers(min_value=0, max_value=len(entries) - 1))
        entries[index][field] = draw(_CORRUPTIONS[field])
    return {
        "themes": {key: _theme_record(key) for key in keys},
        "entries": entries,
    }


#: The full payload space this property explores: pure JSON garbage, payloads
#: shaped enough like a bank to exercise the per-entry validators, and payloads
#: built to parse so the assertions about a returned Bank are reachable at all.
_PAYLOAD = st.one_of(_JSON_LIKE, _BANK_LIKE, _conforming_payloads())


class TestBankProperties(unittest.TestCase):
    """parse_bank's untrusted-input contract: never crash, never accept junk."""

    # The `@example` payloads are not redundant with the generated ones, and
    # they are not a second copy of test_bank.py's rejection tests either. The
    # themed bank is the one that PARSES. Between its entries it sets every
    # optional field (a theme, a clue, a rating, and a spelling the bank keeps),
    # so on every run it reaches every assertion about a returned bank. Each of
    # the rest is a payload the real `parse_bank` REJECTS but a plausible broken
    # one would accept, so each pins one assertion below as reachable. Left to
    # the draw they are reached only by luck: a payload that is wrong in
    # exactly one place and right everywhere else is a narrow target for a
    # strategy that must also explore garbage, and whether an in-suite run
    # draws one changes with any edit to the test's code, from which Hypothesis
    # derives that run's fixed example sequence. `@example` is not `@settings`
    # -- it leaves the property bare for a campaign runner to re-stamp (see the
    # profile note above).
    @given(_PAYLOAD)
    @example({"themes": {}, "entries": []})
    @example(
        {
            "themes": {"a": _theme_record("a"), "b": _theme_record("b")},
            "entries": [
                {"answer": "ALPHA", "theme": "a", "clue": "The first one"},
                {"answer": "BRAVO", "theme": "b", "rating": 3},
                {"answer": "CEDAR"},
                {"answer": "ICE CREAM"},
            ],
        }
    )
    @example({"themes": {}, "entries": [{"answer": "AB"}, {"answer": "AB"}]})
    @example({"themes": {}, "entries": [{"answer": "A B"}, {"answer": "AB"}]})
    @example(
        {
            "themes": {"a": _theme_record("a")},
            "entries": [{"answer": "AB", "theme": "z"}],
        }
    )
    @example(
        {
            "themes": {"a": _theme_record("a")},
            "entries": [{"answer": "AB", "theme": ["a"]}],
        }
    )
    @example({"themes": {}, "entries": [{"answer": "ab"}]})
    @example({"themes": {}, "entries": [{"answer": "A"}]})
    @example({"themes": {}, "entries": [{"answer": "AB", "clue": 7}]})
    @example({"themes": {}, "entries": [{"answer": "AB", "rating": True}]})
    @example({"themes": {}, "entries": [{"answer": "AB", "rating": 6}]})
    def test_fuzz_parse_bank(self, payload: object) -> None:
        """Every payload yields a Bank or a BankError, never any other exception,
        and a returned Bank is never itself malformed.

        The try/except below is the crash-freedom half of the property: any
        exception other than BankError escapes the `except` clause and fails
        the test. The assertions after it are the "never accepts a malformed
        record" half -- without them a `parse_bank` that skipped a check (an
        unenforced duplicate, an undeclared theme let through) would still
        satisfy "returns a Bank or raises", so checking only for a crash would
        not catch the very defect this property exists to catch.
        """
        try:
            bank = cw_bank.parse_bank(payload)
        except cw_bank.BankError:
            return

        self.assertIsInstance(bank, cw_bank.Bank)
        self.assertTrue(bank.entries, "parse_bank must reject an empty entries list")
        seen: set[str] = set()
        for entry in bank.entries:
            self.assertIsInstance(entry.answer, str)
            self.assertGreaterEqual(len(entry.answer), cw_grid.MIN_RUN)
            self.assertTrue(
                all("A" <= letter <= "Z" for letter in entry.answer),
                f"answer {entry.answer!r} contains a non A-Z character",
            )
            self.assertNotIn(
                entry.answer, seen, f"answer {entry.answer!r} is not unique"
            )
            if entry.spelling is not None:
                # The written form is kept only where it differs, and it
                # always closes up to the key every comparison reads.
                self.assertNotEqual(entry.spelling, entry.answer)
                self.assertEqual(cw_answer.grid_form(entry.spelling), entry.answer)
            seen.add(entry.answer)
            if entry.theme is not None:
                self.assertIn(entry.theme, bank.themes)
            if entry.clue is not None:
                self.assertIsInstance(entry.clue, str)
            if entry.rating is not None:
                # `type(...) is int`, not isinstance: a bool is an int too.
                self.assertIs(type(entry.rating), int)
                self.assertGreaterEqual(entry.rating, cw_bank.MIN_RATING)
                self.assertLessEqual(entry.rating, cw_bank.MAX_RATING)
        for key, info in bank.themes.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(info, cw_bank.ThemeInfo)
            for field, text in (("label", info.label), ("summary", info.summary)):
                self.assertIsInstance(text, str, f"theme {key!r} {field}")
                self.assertTrue(text, f"theme {key!r} has an empty {field}")


if __name__ == "__main__":
    unittest.main()
