"""Tests for cw_bank: schema acceptance, and every rejection it can make."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cw_bank
import cw_excluded_terms

_VALID = {
    "themes": {"coffee": {"label": "Coffee", "summary": "Pour-over every morning"}},
    "entries": [
        {"answer": "CHEMEX", "theme": "coffee", "clue": "Hourglass and a filter"},
        {"answer": "BLOOM", "theme": "coffee"},
        {"answer": "LATHE"},
    ],
}


#: Seconds the ordering child gets. It imports two modules and screens one
#: entry, so anything approaching this is a hang rather than slow work.
_ORDER_CHILD_TIMEOUT = 60

#: Hash seeds the ordering test runs under. `PYTHONHASHSEED` decides a
#: `frozenset`'s iteration order, so an unsorted walk gives a different answer
#: per seed, which is why it runs in child processes: an in-process test
#: would kill an unsorted mutant on most seeds and let it live on the
#: rest. Both values below were measured, not guessed: under seed 0 the raw
#: set order puts "zeta" first (so an unsorted walk is observable, and the
#: mutant dies here every time), and under seed 5 it puts "alpha" first (so
#: the test cannot be passing merely because every seed it tries is the easy
#: one).
_ORDER_SEEDS = ("0", "5")

#: Screens one entry two terms both match, and writes the reason (and the raw
#: iteration order the child's own frozenset had), where the parent can read
#: them. Two lines rather than JSON so the parent needs no narrowing cast for a
#: payload it wrote itself. No capture_output, matching tests/test_search.py's own
#: child: a timeout on a capturing call kills only the direct child and then
#: blocks re-reading pipes a grandchild still holds.
# Raw, so the `newline="\n"` below reaches the child as an escape rather than
# being turned into a real newline by this module's own parser, which makes
# the child source a syntax error and every seed an unexplained exit 1.
_ORDER_CHILD_PROGRAM = r"""
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
import cw_bank
import cw_excluded_terms

terms = frozenset({"zeta", "alpha"})
bank = cw_bank.parse_bank(
    {"themes": {}, "entries": [{"answer": "BLOOM", "clue": "zeta alpha"}]}
)
_, dropped = cw_excluded_terms.screen_excluded(bank, terms)
pathlib.Path(sys.argv[2]).write_text(
    dropped[0][1] + "\n" + ",".join(terms), encoding="utf-8", newline="\n"
)
"""


def _screen_under_seed(hash_seed: str) -> tuple[str, str]:
    """The drop reason, and the raw set order the child saw, under one seed.

    In a child process because `PYTHONHASHSEED` is read once at interpreter
    start: a test cannot change the hash seed of the interpreter it is already
    running in, so the only way to hold an order-independence claim to account
    is to run it under more than one.

    The raw order comes back as well as the reason because the seeds
    themselves are what the caller has to check: two seeds that both happen to
    walk the set in sorted order would leave an unsorted mutant alive with the
    test green.
    """
    source = str(Path(cw_bank.__file__).resolve().parent)
    with tempfile.TemporaryDirectory() as scratch:
        reason_path = Path(scratch) / "reason.txt"
        subprocess.run(
            [sys.executable, "-c", _ORDER_CHILD_PROGRAM, source, str(reason_path)],
            timeout=_ORDER_CHILD_TIMEOUT,
            check=True,
            env=dict(os.environ, PYTHONHASHSEED=hash_seed),
        )
        reason, raw_order = reason_path.read_text(encoding="utf-8").split("\n")
        return reason, raw_order


class TestParseBank(unittest.TestCase):
    """parse_bank accepts the documented schema and rejects everything else."""

    def test_accepts_the_documented_shape(self) -> None:
        bank = cw_bank.parse_bank(_VALID)
        self.assertEqual(
            bank.themes,
            {
                "coffee": cw_bank.ThemeInfo(
                    label="Coffee", summary="Pour-over every morning"
                )
            },
        )
        self.assertEqual(
            [entry.answer for entry in bank.entries], ["CHEMEX", "BLOOM", "LATHE"]
        )

    def test_clue_and_theme_are_optional(self) -> None:
        bank = cw_bank.parse_bank(_VALID)
        plain = bank.by_answer()["LATHE"]
        self.assertIsNone(plain.clue)
        self.assertIsNone(plain.theme)

    def test_rejects_a_non_object_payload(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank([1, 2, 3])

    def test_rejects_an_empty_entries_list(self) -> None:
        # Exit 2, not a failed search: a bank with nothing in it is a mistake in
        # the file, and "searched and found nothing" would be a false sentence.
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": []})

    def test_rejects_a_lowercase_answer(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": [{"answer": "chemex"}]})

    def test_rejects_a_one_letter_answer(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": [{"answer": "A"}]})

    def test_rejects_a_non_letter_answer(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": [{"answer": "V60"}]})

    def test_rejects_an_undeclared_theme(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(
                {"themes": {}, "entries": [{"answer": "BLOOM", "theme": "coffee"}]}
            )

    def test_rejects_a_repeated_answer(self) -> None:
        # Not silently deduplicated: two records for one answer is asking a
        # question the tool cannot answer without guessing.
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(
                {"themes": {}, "entries": [{"answer": "BLOOM"}, {"answer": "BLOOM"}]}
            )

    def test_rejects_an_entry_that_is_not_an_object(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": ["BLOOM"]})

    def test_error_names_the_offending_answer(self) -> None:
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank({"themes": {}, "entries": [{"answer": "v60"}]})
        self.assertIn("v60", str(caught.exception))

    # The tests below close every remaining branch in cw_bank.py with a
    # deterministic example, rather than leaning on tests/test_properties.py's
    # generated inputs to reach them: a branch covered only by a property test
    # has no guaranteed coverage anywhere, since example generation is
    # sensitive to the surrounding working tree.

    def test_rejects_an_entries_value_that_is_not_a_list(self) -> None:
        # A string is iterable, so "entries": "BLOOM" would still fail (each
        # character reaching _parse_entry and raising there) even with the
        # isinstance guard deleted, passing for the wrong reason. An int is
        # not iterable at all: without the
        # guard, `for raw_entry in raw_entries` itself raises TypeError, a
        # crash straight through this project's untrusted-input boundary.
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": 5})

    def test_rejects_a_themes_value_that_is_not_an_object(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": ["coffee"], "entries": [{"answer": "BLOOM"}]})

    def test_rejects_a_bank_with_no_themes_key(self) -> None:
        # themes is required even when it would be empty: "may be empty" is
        # not "may be absent". Every other test in
        # this file supplies the key, so without this one, loosening
        # payload.get("themes") into payload.get("themes", {}) (silently
        # making a required key optional) passes the whole suite.
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"entries": [{"answer": "BLOOM"}]})

    def test_rejects_a_non_string_theme_key(self) -> None:
        # Reachable only through a payload handed over as a Python object, never
        # one read from a file: a real JSON object can never have a non-string
        # key. Reachable all the same, and checked apart from its record, so it
        # needs its own test, and a sound record, because a non-object one is
        # refused by the record-shape check even with the key's check deleted,
        # leaving only the message to tell that refusal from this one.
        themes = {1: {"label": "One", "summary": "The first"}}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank({"themes": themes, "entries": [{"answer": "BLOOM"}]})
        self.assertIn("must be a string", str(caught.exception))

    def test_rejects_a_non_string_theme_label(self) -> None:
        themes = {"coffee": {"label": 5, "summary": "Pour-over"}}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank({"themes": themes, "entries": [{"answer": "BLOOM"}]})
        self.assertIn("string 'label'", str(caught.exception))

    def test_rejects_a_non_string_answer(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank({"themes": {}, "entries": [{"answer": 5}]})

    def test_rejects_a_non_string_theme_on_an_entry(self) -> None:
        # A list is unhashable, so an entry theme of this shape would raise
        # TypeError out of "theme not in themes" if the isinstance check were
        # ever dropped from that guard's first half: a crash, not a
        # BankError. This is the short-circuit itself under test, not merely
        # a type mismatch.
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(
                {"themes": {}, "entries": [{"answer": "BLOOM", "theme": [1, 2]}]}
            )

    def test_rejects_a_non_string_clue(self) -> None:
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(
                {"themes": {}, "entries": [{"answer": "BLOOM", "clue": 5}]}
            )


class TestLoadBank(unittest.TestCase):
    """load_bank reads a file and reports an unusable one as a BankError."""

    def test_round_trips_a_written_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.json"
            path.write_text(json.dumps(_VALID), encoding="utf-8", newline="\n")
            self.assertEqual(len(cw_bank.load_bank(path).entries), 3)

    def test_reports_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.json"
            path.write_text("{not json", encoding="utf-8", newline="\n")
            with self.assertRaises(cw_bank.BankError):
                cw_bank.load_bank(path)

    def test_reports_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_bank.BankError):
                cw_bank.load_bank(Path(folder) / "absent.json")

    def test_reports_a_directory_where_a_file_is_expected(self) -> None:
        # A directory is refused with an OSError that is not a
        # FileNotFoundError: without this test, narrowing load_bank's
        # `except OSError` down to `except FileNotFoundError` still passes
        # every other test in this file.
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_bank.BankError):
                cw_bank.load_bank(Path(folder))

    def test_reports_a_file_that_is_not_valid_utf_8(self) -> None:
        # The reverse of the directory case above: UnicodeDecodeError is a
        # ValueError and not an OSError, so an `except OSError` seam lets it
        # escape as a bare traceback rather than a BankError.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.json"
            path.write_bytes(b'{"themes": {}, "entries": [{"answer": "CAF\xff"}]}')
            with self.assertRaises(cw_bank.BankError):
                cw_bank.load_bank(path)


class TestClueAndThemeScreen(unittest.TestCase):
    """The clue-safety screen runs at the parse boundary, not at emit time.

    A bank whose clue or theme key would break the consumer's inline data block
    is a schema violation, and a schema violation belongs on the exit-2 line,
    before the search, not after thirty seconds of one. The rule itself stays
    single-sourced in `cw_config.forbidden_clue_fragment`; this suite is about
    the boundary it is applied at.
    """

    def test_rejects_a_clue_carrying_a_script_close_tag(self) -> None:
        payload = {
            "themes": {},
            "entries": [{"answer": "BLOOM", "clue": "a </script> clue"}],
        }
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(payload)

    def test_rejects_a_clue_carrying_a_newline(self) -> None:
        payload = {"themes": {}, "entries": [{"answer": "BLOOM", "clue": "a\nb"}]}
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(payload)

    def test_rejects_a_theme_key_carrying_a_script_close_tag(self) -> None:
        # The key, not the label: nothing else constrains a theme key's
        # characters, and the emitter writes it twice (as a `themes` key and as
        # each record's "theme" value).
        themes = {"a</script>b": {"label": "Fine", "summary": "Also fine"}}
        entries = [{"answer": "BLOOM", "theme": "a</script>b"}]
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank({"themes": themes, "entries": entries})
        self.assertIn("a theme key", str(caught.exception))

    def test_rejects_a_theme_label_carrying_a_newline(self) -> None:
        themes = {"a": {"label": "one\ntwo", "summary": "Fine"}}
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank({"themes": themes, "entries": [{"answer": "BLOOM"}]})
        self.assertIn("the label for theme", str(caught.exception))

    def test_the_message_names_the_offending_field(self) -> None:
        payload = {
            "themes": {},
            "entries": [{"answer": "BLOOM", "clue": "a </script> clue"}],
        }
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank(payload)
        self.assertIn("BLOOM", str(caught.exception))


class TestLoadExcludedTerms(unittest.TestCase):
    """One term per line, lowercased, blanks and comments ignored."""

    def _written(self, folder: str, text: str) -> Path:
        """Write `text` as an excluded-terms file in `folder`."""
        path = Path(folder) / "excluded.txt"
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def test_reads_one_term_per_line_lowercased(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = self._written(folder, "Alpha\nBRAVO\n")
            self.assertEqual(
                cw_excluded_terms.load_excluded_terms(path),
                frozenset({"alpha", "bravo"}),
            )

    def test_ignores_blank_lines_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = self._written(folder, "\n  \n# a comment\n  alpha  \n")
            self.assertEqual(
                cw_excluded_terms.load_excluded_terms(path), frozenset({"alpha"})
            )

    def test_a_hash_after_text_is_part_of_the_term(self) -> None:
        # Only a line whose first non-blank character is `#` is a comment; a
        # trailing-comment rule would silently truncate a term containing one.
        with tempfile.TemporaryDirectory() as folder:
            path = self._written(folder, "alpha # not a comment\n")
            self.assertEqual(
                cw_excluded_terms.load_excluded_terms(path),
                frozenset({"alpha # not a comment"}),
            )

    def test_reports_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_bank.BankError):
                cw_excluded_terms.load_excluded_terms(Path(folder) / "absent.txt")

    def test_reports_a_directory_where_a_file_is_expected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_bank.BankError):
                cw_excluded_terms.load_excluded_terms(Path(folder))

    def test_reports_a_file_that_is_not_valid_utf_8(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "excluded.txt"
            path.write_bytes(b"caf\xff\n")
            with self.assertRaises(cw_bank.BankError):
                cw_excluded_terms.load_excluded_terms(path)


class TestScreenExcluded(unittest.TestCase):
    """The screen drops whole-word matches and reports every one by name."""

    def _bank(self) -> cw_bank.Bank:
        """A fresh parsed bank, so one test's screen cannot reach another."""
        return cw_bank.parse_bank(_VALID)

    def test_drops_an_answer_matching_a_term(self) -> None:
        screened, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"bloom"})
        )
        self.assertEqual(
            [entry.answer for entry in screened.entries], ["CHEMEX", "LATHE"]
        )
        self.assertEqual([answer for answer, _ in dropped], ["BLOOM"])

    def test_drops_an_entry_whose_clue_matches(self) -> None:
        screened, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"hourglass"})
        )
        self.assertEqual([answer for answer, _ in dropped], ["CHEMEX"])
        self.assertNotIn("CHEMEX", [entry.answer for entry in screened.entries])

    def test_the_reason_names_the_term_and_the_field(self) -> None:
        _, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"hourglass"})
        )
        self.assertIn("hourglass", dropped[0][1])
        self.assertIn("clue", dropped[0][1])

    def test_an_answer_match_is_reported_as_an_answer_match(self) -> None:
        _, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"bloom"})
        )
        self.assertIn("answer", dropped[0][1])

    def test_matching_is_whole_word(self) -> None:
        screened, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"blo"})
        )
        self.assertEqual(dropped, ())
        self.assertEqual(len(screened.entries), 3)

    def test_matching_is_case_insensitive_in_both_directions(self) -> None:
        _, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"BLOOM"})
        )
        self.assertEqual([answer for answer, _ in dropped], ["BLOOM"])

    def test_a_term_carrying_a_regex_metacharacter_is_matched_literally(self) -> None:
        # "b.oom" must not match BLOOM: a term is a word, not a pattern, and an
        # unescaped one would silently over-screen the operator's bank.
        _, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"b.oom"})
        )
        self.assertEqual(dropped, ())

    def test_a_multi_word_term_matches_across_the_space(self) -> None:
        _, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"hourglass and"})
        )
        self.assertEqual([answer for answer, _ in dropped], ["CHEMEX"])

    def test_an_empty_term_bars_nothing(self) -> None:
        # `load_excluded_terms` never yields one, but the function is public.
        #
        # The clue here ends in a period deliberately. An empty term compiles
        # to a pair of bare lookarounds, and against an all-word-character
        # string those cannot match anywhere, so a clue like "Hourglass and
        # a filter" makes this test pass with the empty-term guard deleted. A
        # trailing non-word character gives the empty pattern a position it
        # does match, which is what puts the guard under test.
        bank = cw_bank.parse_bank(
            {"themes": {}, "entries": [{"answer": "BLOOM", "clue": "A filter."}]}
        )
        screened, dropped = cw_excluded_terms.screen_excluded(bank, frozenset({""}))
        self.assertEqual(dropped, ())
        self.assertEqual(len(screened.entries), 1)

    def test_no_terms_leaves_the_bank_untouched(self) -> None:
        original = self._bank()
        screened, dropped = cw_excluded_terms.screen_excluded(original, frozenset())
        self.assertEqual(screened.entries, original.entries)
        self.assertEqual(dropped, ())

    def test_the_surviving_bank_keeps_every_declared_theme(self) -> None:
        # Screening removes entries, not declarations: a theme whose only entry
        # was dropped must still resolve for anything that reads a label.
        screened, _ = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"bloom"})
        )
        self.assertEqual(
            dict(screened.themes),
            {"coffee": cw_bank.ThemeInfo("Coffee", "Pour-over every morning")},
        )

    def test_the_dropped_order_follows_the_bank_not_the_term_set(self) -> None:
        # A frozenset's iteration order is hash-seeded, and that must never
        # reach output. Two answers dropped by two different terms must
        # come back in bank order every run.
        _, dropped = cw_excluded_terms.screen_excluded(
            self._bank(), frozenset({"bloom", "lathe"})
        )
        self.assertEqual([answer for answer, _ in dropped], ["BLOOM", "LATHE"])

    def test_two_matching_terms_report_the_first_in_sorted_order(self) -> None:
        # Two terms both match this entry, so which one the reason names is
        # decided by the order the screen walks them in. Walking a frozenset's
        # own order makes that answer hash-seeded, which must never reach
        # output; sorting pins it.
        #
        # Run under measured hash seeds, in child processes, for the reason
        # `_ORDER_SEEDS` gives.
        raw_orders: list[str] = []
        for seed in _ORDER_SEEDS:
            with self.subTest(seed):
                reason, raw_order = _screen_under_seed(seed)
                raw_orders.append(raw_order)
                self.assertIn("alpha", reason)
                self.assertNotIn("zeta", reason)
        # The seeds above must be discriminating, and that is asserted here
        # rather than trusted. Two seeds that both put "alpha" first let the
        # unsorted mutant survive with everything green, and PYTHONHASHSEED
        # fixes siphash's key, not its algorithm, which CPython has changed
        # before (siphash24 to siphash13 in 3.11), so a future interpreter can
        # make that happen without anyone touching this file. Asserting the raw
        # orders disagree turns that into a failure at the seam it happens at.
        self.assertEqual(len(set(raw_orders)), len(raw_orders))
