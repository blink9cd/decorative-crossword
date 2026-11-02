"""Tests for cw_emit: the grid_source.json document and its stability."""

import json
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest import mock

import cw_bank
import cw_emit
import cw_grid

# The configuration is built by the shared fixture, not re-spelled here: a suite
# that writes its own copy of the defaults cannot notice the real ones changing
# underneath it.
from tests.emit_fixtures import (
    _ROWS,
    _bank,
    _bank_clued,
    _bank_keyed,
    _bank_labeled,
    _bank_without,
    _clues,
    _outcome,
    _outcome_with_a_free_run,
)
from tests.search_fixtures import config as _config

#: What `dumps_document` must produce for the standard outcome and bank below,
#: written out by hand rather than by calling the subject: the point of pinning
#: bytes is to fail when key order, indent, escaping or the trailing newline
#: move, and an expectation built by the code under test would move with them.
#: The committed hand-verification sample freezes this same shape.
_EXPECTED_JSON = """{
  "clues": {
    "CAT": {
      "clue": "Sleeps on the keyboard",
      "theme": "pets"
    },
    "COW": {
      "clue": "",
      "theme": "pets"
    },
    "WET": {
      "clue": ""
    }
  },
  "rows": [
    "CAT",
    "O..",
    "WET"
  ],
  "themes": {
    "pets": {
      "label": "Pets",
      "summary": "Two cats and a lot of hair"
    }
  }
}
"""


class TestRatingsStayOutOfTheDocument(unittest.TestCase):
    """A rating ranks grids inside `fill`; `grid_source.json` never carries one."""

    def test_a_rated_bank_emits_the_pinned_unrated_bytes(self) -> None:
        # A rating ranks grids inside `fill` and is no part of the document
        # format, so rating every answer must change no byte of it.
        bank = _bank()
        rated = cw_bank.Bank(
            themes=bank.themes,
            entries=tuple(
                cw_bank.BankEntry(entry.answer, entry.theme, entry.clue, rating=1)
                for entry in bank.entries
            ),
        )
        document = cw_emit.build_document(_outcome(), rated, _config())
        self.assertEqual(cw_emit.dumps_document(document), _EXPECTED_JSON)


class TestBuildDocument(unittest.TestCase):
    """The emitted document has the documented `grid_source.json` shape."""

    def test_carries_rows_themes_and_clues(self) -> None:
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        self.assertEqual(sorted(document), ["clues", "rows", "themes"])
        self.assertEqual(document["rows"], ["CAT", "O..", "WET"])

    def test_keeps_the_bank_clue(self) -> None:
        clues = _clues(cw_emit.build_document(_outcome(), _bank(), _config()))
        self.assertEqual(clues["CAT"]["clue"], "Sleeps on the keyboard")

    def test_an_unclued_answer_emits_an_empty_clue(self) -> None:
        """An unclued answer emits an empty clue: nothing is invented for one.

        A clue is optional. The record keeps the key with an empty value rather
        than omitting it: uniform keys, and `""` is falsy, so a consumer's "has
        a clue?" test stays a plain truthiness check.
        """
        clues = _clues(cw_emit.build_document(_outcome(), _bank(), _config()))
        self.assertEqual(clues["COW"], {"clue": "", "theme": "pets"})

    def test_every_entry_has_a_clue_key(self) -> None:
        # The key, not a non-empty value: a clue is optional, but the record
        # shape is uniform, so a missing key (as opposed to an empty one) is
        # a defect.
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        for run in cw_grid.runs_from_rows(_ROWS):
            self.assertIn(run.text, _clues(document))

    def test_clues_a_run_the_bank_never_declared(self) -> None:
        # `fill` never writes a run its bank lacks, but `build_document` takes
        # any bank, and a run that bank does not hold still gets a record,
        # with an empty clue, because there is no bank entry to have written
        # one and nothing invents one.
        document = cw_emit.build_document(_outcome(), _bank_without("WET"), _config())
        self.assertEqual(_clues(document)["WET"], {"clue": ""})

    def test_clues_a_run_no_placement_produced(self) -> None:
        outcome = _outcome_with_a_free_run()
        self.assertNotIn("WET", [placement.answer for placement in outcome.placed])
        document = cw_emit.build_document(outcome, _bank(), _config())
        self.assertIn("WET", _clues(document))

    def test_emits_only_themes_actually_used(self) -> None:
        # "unused" is declared in the bank and placed by nothing.
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        self.assertEqual(
            document["themes"],
            {"pets": {"label": "Pets", "summary": "Two cats and a lot of hair"}},
        )

    def test_keeps_the_theme_of_a_themed_entry(self) -> None:
        clues = _clues(cw_emit.build_document(_outcome(), _bank(), _config()))
        self.assertEqual(clues["CAT"]["theme"], "pets")

    def test_omits_the_theme_key_for_an_unthemed_entry(self) -> None:
        clues = _clues(cw_emit.build_document(_outcome(), _bank(), _config()))
        self.assertNotIn("theme", clues["WET"])


class TestDocumentShape(unittest.TestCase):
    """The runtime types the rest of this suite narrows to with a cast."""

    def test_clues_map_answers_to_string_valued_mappings(self) -> None:
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        clues = document["clues"]
        self.assertIsInstance(clues, Mapping)
        for answer, record in cast(Mapping[str, object], clues).items():
            self.assertIsInstance(answer, str)
            self.assertIsInstance(record, Mapping)
            for key, value in cast(Mapping[str, object], record).items():
                self.assertIsInstance(key, str)
                self.assertIsInstance(value, str)


class TestClueScreen(unittest.TestCase):
    """No emitted text may break the consumer's inline data block."""

    def test_rejects_a_bank_clue_carrying_the_script_close_tag(self) -> None:
        # `build_document` accepts any Bank, including one built in code that
        # never crossed the loader's screen, so this is the last boundary
        # before an operator's paste of markup would reach the page.
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_emit.build_document(
                _outcome(), _bank_clued("CAT", "See </script> below"), _config()
            )
        # Which fragment, not merely that one fired: both descriptions come
        # from one helper, so a swap between them would otherwise send an
        # operator who pasted markup hunting for a newline.
        #
        # Not `assertIn("</script", ...)`, which is the obvious assertion and
        # cannot fail: the message ends `got {text!r}`, echoing the very input
        # that contains the fragment, so it passes under the swap it is meant
        # to catch. The structural fact is general (any assertion on a
        # substring of the input is free), so this one reads the half of the
        # message only the description can supply, and denies the other.
        self.assertIn("CAT", str(caught.exception))
        self.assertIn("the literal", str(caught.exception))
        self.assertNotIn("a newline", str(caught.exception))

    def test_rejects_a_bank_clue_carrying_a_newline(self) -> None:
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_emit.build_document(
                _outcome(), _bank_clued("CAT", "First line\nsecond line"), _config()
            )
        self.assertIn("CAT", str(caught.exception))
        self.assertIn("a newline", str(caught.exception))

    def test_rejects_a_theme_label_carrying_the_script_close_tag(self) -> None:
        # A label is operator-supplied free text landing in the same data block
        # as the clues, and the emitter screens it again because a Bank built in
        # code never crossed the loader.
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_emit.build_document(
                _outcome(), _bank_labeled("Pets </script>"), _config()
            )
        self.assertIn("pets", str(caught.exception))

    def test_rejects_a_theme_key_carrying_the_script_close_tag(self) -> None:
        # A key is emitted twice (as the themes map's key and as each
        # record's "theme" value), so a Bank that reaches the emitter
        # unscreened would put the fragment in the page three times.
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_emit.build_document(_outcome(), _bank_keyed("pets</script>x"), _config())
        self.assertIn("theme key", str(caught.exception))
        self.assertIn("</script", str(caught.exception))

    def test_rejects_a_theme_key_carrying_a_newline(self) -> None:
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_emit.build_document(_outcome(), _bank_keyed("pets\nx"), _config())
        self.assertIn("theme key", str(caught.exception))
        self.assertIn("a newline", str(caught.exception))

    def test_rejects_a_theme_label_carrying_a_control_character(self) -> None:
        # A Bank built in code never met parse_bank's screen, so this is the
        # emitter's own copy of the same rule refusing the same character.
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_emit.build_document(_outcome(), _bank_labeled("Pets\x1b[2J"), _config())
        self.assertIn("the label for theme 'pets'", str(caught.exception))
        self.assertIn("U+001B", str(caught.exception))

    def test_screens_the_key_that_reaches_both_emitted_places(self) -> None:
        # The screened key is what lands in the themes map and in every record,
        # so neither place can carry a spelling the other rejected.
        document = cw_emit.build_document(_outcome(), _bank_keyed("pets"), _config())
        self.assertEqual(
            document["themes"],
            {"pets": {"label": "Pets", "summary": "Two cats and a lot of hair"}},
        )
        self.assertEqual(_clues(document)["CAT"]["theme"], "pets")
        self.assertEqual(_clues(document)["COW"]["theme"], "pets")


class TestDumpsDocument(unittest.TestCase):
    """Serialization is stable, so a committed sample can be pinned."""

    def test_is_byte_identical_across_calls(self) -> None:
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        self.assertEqual(
            cw_emit.dumps_document(document), cw_emit.dumps_document(document)
        )

    def test_ends_with_a_single_newline(self) -> None:
        text = cw_emit.dumps_document(
            cw_emit.build_document(_outcome(), _bank(), _config())
        )
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))

    def test_round_trips_through_json(self) -> None:
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        self.assertEqual(json.loads(cw_emit.dumps_document(document)), document)

    def test_emits_the_pinned_bytes(self) -> None:
        # Key order, indent and the trailing newline in one assertion: all
        # three are part of the emitted contract, and the committed samples are
        # diffed against this same rendering.
        document = cw_emit.build_document(_outcome(), _bank(), _config())
        self.assertEqual(cw_emit.dumps_document(document), _EXPECTED_JSON)

    def test_keeps_a_non_ascii_theme_label_as_itself(self) -> None:
        # ensure_ascii=False: a label must survive as its own characters, not
        # as \\uXXXX escapes that make the committed sample unreadable.
        document = cw_emit.build_document(
            _outcome(), _bank_labeled("Câlins"), _config()
        )
        text = cw_emit.dumps_document(document)
        self.assertIn('"Câlins"', text)
        self.assertNotIn("\\u", text)

    def test_dumps_a_document_built_from_a_parsed_bank(self) -> None:
        # parse_bank hands back a MappingProxyType, which json.dumps refuses;
        # the emitted themes map must therefore be a map this module built.
        payload = {
            "themes": {
                "pets": {"label": "Pets", "summary": "Two cats and a lot of hair"}
            },
            "entries": [
                {"answer": "CAT", "theme": "pets", "clue": "Sleeps on the keyboard"},
                {"answer": "COW", "theme": "pets"},
                {"answer": "WET"},
            ],
        }
        bank = cw_bank.parse_bank(payload)
        document = cw_emit.build_document(_outcome(), bank, _config())
        self.assertEqual(cw_emit.dumps_document(document), _EXPECTED_JSON)


#: The JSON escape for LESS-THAN SIGN: a backslash, then `u003c`. Spelled from
#: the backslash's name so that no escape sequence is written inside a string
#: literal here, where it would be read as the character it stands for.
_ESCAPED_LESS_THAN = "\N{REVERSE SOLIDUS}u003c"

#: An HTML comment opener, then a script tag. Neither is refused on the way in,
#: and inside a page's inline data block the pair written raw moves the parser
#: into a state where the block's own closing tag no longer ends it.
_COMMENT_THEN_SCRIPT = "<!--<script"

#: A `<` straight after a backslash: the one place an escape could be misread,
#: since the value's backslash is written doubled and the `<` must still be
#: escaped on its own, not taken as the end of an escape the backslash opened.
_BACKSLASH_THEN_LESS_THAN = "x\N{REVERSE SOLIDUS}<y"


def _bank_holding_less_than() -> cw_bank.Bank:
    """A bank whose theme key, label, summary and two clues each hold a `<`."""
    return cw_bank.Bank(
        themes={"a<b": cw_bank.ThemeInfo("<Pets>", "Two < three")},
        entries=(
            cw_bank.BankEntry("CAT", "a<b", _COMMENT_THEN_SCRIPT),
            cw_bank.BankEntry("COW", "a<b", _BACKSLASH_THEN_LESS_THAN),
            cw_bank.BankEntry("WET", None, None),
        ),
    )


class TestLessThanIsEscaped(unittest.TestCase):
    """Every `<` is written as its JSON escape, and the value read back is unchanged."""

    def _dumped(self) -> tuple[dict[str, object], str]:
        """The `<`-holding document, and the text `dumps_document` makes of it."""
        document = cw_emit.build_document(
            _outcome(), _bank_holding_less_than(), _config()
        )
        return document, cw_emit.dumps_document(document)

    def test_no_raw_less_than_sign_is_written(self) -> None:
        _, text = self._dumped()
        self.assertNotIn("<", text)

    def test_the_value_read_back_is_the_value_written(self) -> None:
        document, text = self._dumped()
        self.assertEqual(json.loads(text), document)

    def test_only_the_less_than_signs_change(self) -> None:
        # Every escape stands for one `<`, and nothing else moves: put the
        # characters back and the text is the plain rendering, key order,
        # indent, non-ASCII handling and trailing newline included.
        document, text = self._dumped()
        plain = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True)
        self.assertEqual(text.replace(_ESCAPED_LESS_THAN, "<"), f"{plain}\n")
        self.assertEqual(text.count(_ESCAPED_LESS_THAN), plain.count("<"))

    def test_a_comment_opener_before_a_script_tag_is_written_escaped(self) -> None:
        _, text = self._dumped()
        self.assertNotIn("<!--", text)
        self.assertNotIn("<script", text)
        self.assertIn(_COMMENT_THEN_SCRIPT.replace("<", _ESCAPED_LESS_THAN), text)


class TestWriteDocument(unittest.TestCase):
    """Writing is atomic, so a concurrent reader never sees half a file."""

    def test_writes_the_serialized_document(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            document = cw_emit.build_document(_outcome(), _bank(), _config())
            cw_emit.write_document(path, document)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), document)

    def test_writes_exactly_the_serialized_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            document = cw_emit.build_document(_outcome(), _bank(), _config())
            cw_emit.write_document(path, document)
            self.assertEqual(path.read_bytes(), _EXPECTED_JSON.encode("utf-8"))

    def test_replaces_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            path.write_text(
                "stale content that must not survive",
                encoding="utf-8",
                newline="\n",
            )
            document = cw_emit.build_document(_outcome(), _bank(), _config())
            cw_emit.write_document(path, document)
            self.assertEqual(path.read_text(encoding="utf-8"), _EXPECTED_JSON)

    def test_leaves_no_temporary_file_behind(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            cw_emit.write_document(
                path, cw_emit.build_document(_outcome(), _bank(), _config())
            )
            self.assertEqual(
                [item.name for item in Path(folder).iterdir()], [path.name]
            )

    def test_a_failed_replace_leaves_the_previous_file_intact(self) -> None:
        # The whole reason for the temp-file-then-replace dance: a write that
        # dies partway must not leave the operator with a truncated grid, and
        # must not litter the directory with the attempt either.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            path.write_text("previous grid", encoding="utf-8", newline="\n")
            document = cw_emit.build_document(_outcome(), _bank(), _config())
            with mock.patch.object(
                cw_emit.os, "replace", side_effect=OSError("no space left")
            ):
                with self.assertRaises(cw_emit.EmitError):
                    cw_emit.write_document(path, document)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous grid")
            self.assertEqual(
                [item.name for item in Path(folder).iterdir()], [path.name]
            )

    def test_reports_text_the_encoder_refuses(self) -> None:
        # A lone surrogate has no UTF-8 encoding, so stream.write raises
        # UnicodeEncodeError, a ValueError rather than an OSError. No bank or
        # grid file can carry one this far (each refuses it on the way in),
        # but `write_atomically` takes any text, so the wrap is tested here,
        # where it can still fire.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_emit.write_atomically(path, "lone \U0000d800 surrogate\n")
            self.assertIn(path.name, str(caught.exception))
            # No destination, and no stray temp file either: the cleanup runs
            # on every failure, not only the ones the wrap names.
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_touches_the_filesystem_only_after_serializing(self) -> None:
        # A document this module did not build can be unserializable. Nothing
        # wraps that (it is a caller's bug, not an operator's), but it must
        # not leave a temp file behind, which it would if the file were opened
        # before json.dumps ran.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            with self.assertRaises(TypeError):
                cw_emit.write_document(path, {"rows": object()})
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_reports_an_unusable_destination(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "no-such-directory" / "grid_source.json"
            document = cw_emit.build_document(_outcome(), _bank(), _config())
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_emit.write_document(path, document)
            self.assertIn(path.name, str(caught.exception))
