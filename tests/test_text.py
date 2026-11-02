"""Tests for which characters operator text may carry, and where that is enforced.

A bank's theme keys, labels, summaries and clues, and a grid file's theme
labels and summaries, reach a terminal through the report, the SVG through the
legend, or the grid file through the emitter. None of those sinks can take a
C0 or C1 control, DEL, a lone surrogate or U+FFFE/U+FFFF: a terminal obeys a
control character as a command, XML 1.0 admits none of the C0 block, the
surrogates or those two however they are written, and a lone surrogate has no
UTF-8 encoding at all. So each is refused where the text enters, naming the
field and the character, rather than stripped on the way out.

The same fields refuse the literal `</script`, which would end the inline
data block a page embeds the grid file in. It is looked for in the case-folded
text, because an HTML parser matches an end tag's name without regard to ASCII
case.

Text the report only echoes (a skipped word-list line) is escaped instead,
and so is a bank label where the report prints it. The set escaped there is the
refusal set plus the bidi controls. A bidi control is legal in a label: in the
SVG it reaches no further than the line of text that holds it: the label alone
in the legend, and in the caption the rest of that line, since the grid's size
and blocked percentage come before every label. Printed, it reorders the rest
of the report line, which could then show the reader something other than what
it holds.

A refusal quotes the value at fault through `cw_text.shown`: its repr,
which writes each of those characters as an escape, cut at 200 characters
so that a huge value cannot bury the sentence around it.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cw_bank
import cw_config
import cw_emit
import cw_grid_document
import cw_pairs
import cw_text

#: One character from each refused range, and both ends of each range.
_REFUSED = (
    "\x00",
    "\x1b",
    "\x1f",
    "\x7f",
    "\x80",
    "\x9b",
    "\x9f",
    "\U0000d800",
    "\U0000dfff",
    "\U0000fffe",
    "\U0000ffff",
)

#: The neighbors of each refused range, and a soft hyphen: a format character,
#: legitimate in a label, and not a control.
_ACCEPTED = (
    " ",
    "~",
    "\xa0",
    "\xad",
    "\U0000d7ff",
    "\U0000e000",
    "\U0000fffd",
    "\U00010000",
)

#: Every bidi control: the Arabic letter mark, the left-to-right and
#: right-to-left marks, the embeddings and overrides, and the isolates.
_BIDI = (
    "\U0000061c",
    "\U0000200e",
    "\U0000200f",
    "\U0000202a",
    "\U0000202b",
    "\U0000202c",
    "\U0000202d",
    "\U0000202e",
    "\U00002066",
    "\U00002067",
    "\U00002068",
    "\U00002069",
)

#: The characters either side of each bidi range (a zero-width joiner and a
#: paragraph separator among them), and an accented letter. `visible` escapes
#: none of them.
_NOT_ESCAPED = (
    "\U0000061b",
    "\U0000061d",
    "\U0000200d",
    "\U00002010",
    "\U00002029",
    "\U0000202f",
    "\U00002065",
    "\U0000206a",
    "\xe9",
) + _ACCEPTED

#: How the rule names the one fragment it refuses that is longer than a character.
_SCRIPT_REFUSAL = "the literal '</script'"


def _code_point(char: str) -> str:
    """How a refusal names `char`: `U+` and four or more hex digits."""
    return f"U+{ord(char):04X}"


def _escape(char: str) -> str:
    r"""How the report shows `char`: `\x` and two hex digits, or `\u` and four."""
    if ord(char) <= 0xFF:
        return f"\\x{ord(char):02x}"
    return f"\\u{ord(char):04x}"


def _bank_carrying(field: str, text: str) -> dict[str, object]:
    """A one-entry bank payload whose theme key, label, summary or clue ends with `text`."""
    key = "k" + text if field == "key" else "k"
    record = {"label": "Label", "summary": "Summary"}
    entry = {"answer": "BLOOM", "theme": key}
    if field in record:
        record[field] += text
    if field == "clue":
        entry["clue"] = "Clue" + text
    return {"themes": {key: record}, "entries": [entry]}


def _visible_skipped(line: str) -> str:
    """The report block naming `line` as a skipped `--phrases` line."""
    phrases = cw_pairs.Phrases(frozenset(), ((line, "a reason"),))
    return "\n".join(cw_pairs.pair_lines((), (), phrases))


class TestTheRule(unittest.TestCase):
    """`cw_config.forbidden_clue_fragment`, the one statement of the rule."""

    def test_names_each_refused_character_by_code_point(self) -> None:
        for char in _REFUSED:
            with self.subTest(char=ascii(char)):
                self.assertEqual(
                    cw_config.forbidden_clue_fragment(f"a{char}b"),
                    f"the character {_code_point(char)}",
                )

    def test_accepts_the_neighbors_of_each_range(self) -> None:
        for char in _ACCEPTED:
            with self.subTest(char=ascii(char)):
                self.assertIsNone(cw_config.forbidden_clue_fragment(f"a{char}b"))

    def test_accepts_the_bidi_controls(self) -> None:
        # Legal text in a label, and kept in the grid file and the SVG as
        # written: the report shows one escaped rather than refusing it.
        for char in _BIDI:
            with self.subTest(char=ascii(char)):
                self.assertIsNone(cw_config.forbidden_clue_fragment(f"a{char}b"))

    def test_a_newline_keeps_its_own_description(self) -> None:
        self.assertEqual(cw_config.forbidden_clue_fragment("a\nb"), "a newline")

    def test_case_folds_before_looking_for_the_script_close_tag(self) -> None:
        # An HTML parser matches an end tag's name without regard to ASCII
        # case, so each of these closes the consumer's data block.
        for text in ("x </SCRIPT> y", "x </Script", "x </sCrIpT>"):
            with self.subTest(text=text):
                self.assertEqual(
                    cw_config.forbidden_clue_fragment(text), _SCRIPT_REFUSAL
                )

    def test_case_folding_refuses_letters_lowering_leaves_alone(self) -> None:
        # A long s folds to "s", and a t with dieresis to "t" and a combining
        # dieresis; lowering leaves each as written, so these pin folding
        # rather than lowering. A parser ends the block on ASCII letters only,
        # so neither spelling would end it: refusing them is the safe side.
        for text in ("x </\U0000017fcript>", "x </scrip\U00001e97>"):
            with self.subTest(text=ascii(text)):
                self.assertEqual(
                    cw_config.forbidden_clue_fragment(text), _SCRIPT_REFUSAL
                )


class TestBankText(unittest.TestCase):
    """`parse_bank` refuses each such character in every field it screens."""

    def test_refuses_each_in_every_screened_field(self) -> None:
        for field in ("key", "label", "summary", "clue"):
            for char in _REFUSED:
                with self.subTest(field=field, char=ascii(char)):
                    with self.assertRaises(cw_bank.BankError) as caught:
                        cw_bank.parse_bank(_bank_carrying(field, char))
                    self.assertIn(_code_point(char), str(caught.exception))

    def test_refuses_a_script_close_tag_that_case_folds_to_it(self) -> None:
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank(_bank_carrying("clue", " </SCRIPT> "))
        self.assertIn(_SCRIPT_REFUSAL, str(caught.exception))


class TestGridText(unittest.TestCase):
    """`load_document` refuses each such character in a theme label or summary."""

    def test_refuses_each_in_both_theme_fields(self) -> None:
        for field in ("label", "summary"):
            for char in _REFUSED:
                with self.subTest(field=field, char=ascii(char)):
                    record = {"label": "Pets", "summary": "Two cats"}
                    record[field] += char
                    payload = {"rows": ["CAT", "O..", "WET"], "themes": {"p": record}}
                    with tempfile.TemporaryDirectory() as folder:
                        path = Path(folder) / "grid_source.json"
                        path.write_text(
                            json.dumps(payload), encoding="utf-8", newline="\n"
                        )
                        with self.assertRaises(cw_emit.EmitError) as caught:
                            cw_grid_document.load_document(path)
                    message = str(caught.exception)
                    self.assertIn(path.name, message)
                    self.assertIn(f"the {field} for theme 'p'", message)
                    self.assertIn(_code_point(char), message)

    def test_refuses_the_script_close_tag_in_a_theme_label(self) -> None:
        # A hand-written grid file meets the bank's rule, case and all.
        for tag in ("</script", "</SCRIPT"):
            with self.subTest(tag=tag):
                record = {"label": f"Pets {tag}>", "summary": "Two cats"}
                payload = {"rows": ["CAT", "O..", "WET"], "themes": {"p": record}}
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "grid_source.json"
                    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
                    with self.assertRaises(cw_emit.EmitError) as caught:
                        cw_grid_document.load_document(path)
                message = str(caught.exception)
                self.assertIn("the label for theme 'p'", message)
                self.assertIn(_SCRIPT_REFUSAL, message)


class TestVisibleText(unittest.TestCase):
    """A skipped line is printed with the refusal set and the bidi controls escaped.

    Read through `cw_pairs.pair_lines`, a public printer of skipped lines, so
    the rule is tested where a line actually reaches the report.
    """

    def test_escapes_each_refused_character_and_bidi_control(self) -> None:
        for char in _REFUSED + _BIDI:
            with self.subTest(char=ascii(char)):
                block = _visible_skipped(f"A{char}B")
                self.assertIn(f"A{_escape(char)}B", block)
                self.assertNotIn(char, block)

    def test_prints_every_other_character_as_written(self) -> None:
        for char in _NOT_ESCAPED:
            with self.subTest(char=ascii(char)):
                self.assertIn(f"A{char}B", _visible_skipped(f"A{char}B"))

    def test_keeps_the_zero_width_space_and_non_joiner(self) -> None:
        # Each is text a label may need (the space marks where a word may
        # break, the non-joiner keeps two letters apart), and neither is a
        # control a terminal obeys: kept by the rule and printed as written.
        for char in ("\U0000200b", "\U0000200c"):
            with self.subTest(char=ascii(char)):
                self.assertIsNone(cw_config.forbidden_clue_fragment(f"a{char}b"))
                self.assertIn(f"A{char}B", _visible_skipped(f"A{char}B"))


class TestQuotedValue(unittest.TestCase):
    """`cw_text.shown`, how a refusal quotes a value: its repr, cut at 200 characters.

    Each value below is a string of x's, so its repr is its length plus two
    quotes: 197 x's make a repr of 199 characters.
    """

    def test_a_repr_of_199_characters_is_shown_whole(self) -> None:
        value = "x" * 197
        self.assertEqual(cw_text.shown(value), repr(value))

    def test_a_repr_of_200_characters_is_shown_whole(self) -> None:
        value = "x" * 198
        self.assertEqual(len(repr(value)), 200)
        self.assertEqual(cw_text.shown(value), repr(value))

    def test_a_repr_of_201_characters_is_cut_at_200(self) -> None:
        value = "x" * 199
        self.assertEqual(
            cw_text.shown(value), repr(value)[:200] + "... (201 characters)"
        )

    def test_the_cut_is_named_by_the_whole_repr_length(self) -> None:
        value = [0] * 1000
        quoted = cw_text.shown(value)
        self.assertTrue(quoted.startswith("[0, 0, 0, "))
        self.assertTrue(quoted.endswith(f"... ({len(repr(value))} characters)"))

    def test_the_cap_is_the_named_constant(self) -> None:
        self.assertEqual(cw_text.SHOWN_MAX_CHARS, 200)

    def test_escapes_each_refused_character_and_bidi_control(self) -> None:
        # A quote goes to the terminal as the rest of a refusal does, so no
        # character a terminal would obey may reach it raw.
        for char in _REFUSED + _BIDI:
            with self.subTest(char=ascii(char)):
                self.assertNotIn(char, cw_text.shown(f"A{char}B"))


if __name__ == "__main__":
    unittest.main()
