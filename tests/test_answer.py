"""Tests for cw_answer: the one rule for what an answer's written form may be.

`grid_form` is the normalization every answer comparison goes through,
`is_spelling` the shape a bank answer may take, and `enumeration` /
`with_enumeration` what a multi-word answer's clue carries. All pure, so this
suite holds the examples and tests/test_answer_properties.py the input space.

Entry point assumptions: run through `test_decorative_crossword.py`'s
`load_tests` hook, which puts the project root and `src/` on `sys.path`.
"""

import unittest

import cw_answer

#: Written forms the bank accepts, each for a reason of its own: a space, a
#: hyphen, an apostrophe beside a hyphen, apostrophes at both ends of a word,
#: one opening and one closing a whole answer, one inside a word, and a plain
#: word.
ACCEPTED = (
    "HELLO THERE",
    "ATTA-BOY",
    "JACK-O'-LANTERN",
    "ROCK 'N' ROLL",
    "'TIS",
    "PLAYIN'",
    "O'CLOCK",
    "CHEMEX",
)

#: Written forms still refused, one per shape: a period, an ampersand, a digit,
#: lowercase, a typographic apostrophe, a tab, a doubled space, a hyphen beside
#: a space either way round, a separator opening or closing the answer, two
#: apostrophes together, an apostrophe alone, and nothing at all.
REFUSED = (
    "ST. ELMO",
    "R&B",
    "V60",
    "hello there",
    "HELLO\N{RIGHT SINGLE QUOTATION MARK}S",
    "HELLO\tTHERE",
    "HELLO  THERE",
    "ATTA -BOY",
    "ATTA- BOY",
    "-ISH",
    "ISH-",
    " HELLO",
    "HELLO ",
    "O''CLOCK",
    "'",
    "",
)


class TestGridForm(unittest.TestCase):
    """`grid_form` closes up spaces, hyphens and apostrophes, and nothing else."""

    def test_a_space_closes_up(self) -> None:
        self.assertEqual(cw_answer.grid_form("HELLO THERE"), "HELLOTHERE")

    def test_a_hyphen_closes_up(self) -> None:
        self.assertEqual(cw_answer.grid_form("ATTA-BOY"), "ATTABOY")

    def test_an_apostrophe_closes_up(self) -> None:
        self.assertEqual(cw_answer.grid_form("JACK-O'-LANTERN"), "JACKOLANTERN")

    def test_any_whitespace_closes_up_as_the_phrase_reader_always_did(self) -> None:
        # `--phrases` closes up any whitespace `str.split()` splits on, so a
        # tab inside a phrase line closes up rather than being skipped.
        self.assertEqual(cw_answer.grid_form("web\tsite"), "website")

    def test_case_is_left_alone(self) -> None:
        # `--feature chalk` names a lowercase answer no bank holds; folding
        # here would quietly change that (cw_feature.parse_feature).
        self.assertEqual(cw_answer.grid_form("atta-boy"), "attaboy")

    def test_any_other_character_is_kept(self) -> None:
        self.assertEqual(cw_answer.grid_form("R&B ST."), "R&BST.")

    def test_a_letters_only_answer_is_unchanged(self) -> None:
        self.assertEqual(cw_answer.grid_form("CHEMEX"), "CHEMEX")


class TestIsSpelling(unittest.TestCase):
    """`is_spelling`: words of A-Z joined by one space or hyphen, apostrophes within."""

    def test_every_accepted_shape(self) -> None:
        for text in ACCEPTED:
            with self.subTest(text=text):
                self.assertTrue(cw_answer.is_spelling(text))

    def test_every_refused_shape(self) -> None:
        for text in REFUSED:
            with self.subTest(text=text):
                self.assertFalse(cw_answer.is_spelling(text))

    def test_the_rule_names_every_allowed_character(self) -> None:
        # The refusal quotes this sentence, so it is the operator's only
        # statement of what may be written.
        for word in ("A-Z", "space", "hyphen", "apostrophe"):
            with self.subTest(word=word):
                self.assertIn(word, cw_answer.SPELLING_RULE)


class TestEnumeration(unittest.TestCase):
    """`enumeration`: the word lengths a multi-word answer's clue carries."""

    def test_a_space_separates_with_a_comma(self) -> None:
        self.assertEqual(cw_answer.enumeration("HELLO THERE"), "(5,5)")

    def test_a_hyphen_separates_with_a_hyphen(self) -> None:
        self.assertEqual(cw_answer.enumeration("ATTA-BOY"), "(4-3)")

    def test_an_apostrophe_neither_counts_nor_separates(self) -> None:
        self.assertEqual(cw_answer.enumeration("JACK-O'-LANTERN"), "(4-1-7)")

    def test_mixed_separators_keep_their_order(self) -> None:
        self.assertEqual(cw_answer.enumeration("ROCK 'N' ROLL"), "(4,1,4)")

    def test_one_word_with_an_apostrophe_has_none(self) -> None:
        # A single word carries no enumeration, the same as CHEMEX does.
        self.assertIsNone(cw_answer.enumeration("O'CLOCK"))

    def test_a_letters_only_answer_has_none(self) -> None:
        self.assertIsNone(cw_answer.enumeration("CHEMEX"))


class TestWithEnumeration(unittest.TestCase):
    """`with_enumeration`: a clued multi-word answer's clue, ending in its lengths."""

    def test_a_clue_gains_the_enumeration(self) -> None:
        self.assertEqual(
            cw_answer.with_enumeration("Greeting", "HELLO THERE"), "Greeting (5,5)"
        )

    def test_an_enumeration_typed_by_hand_is_not_added_twice(self) -> None:
        # A bank may type the enumeration into the clue itself.
        self.assertEqual(
            cw_answer.with_enumeration("Greeting (5,5)", "HELLO THERE"),
            "Greeting (5,5)",
        )

    def test_an_empty_clue_stays_empty(self) -> None:
        # An unclued answer shows the theme summary alone on the page; a bare
        # "(5,5)" there would be a clue nobody wrote.
        self.assertEqual(cw_answer.with_enumeration("", "HELLO THERE"), "")

    def test_a_letters_only_answer_leaves_its_clue_alone(self) -> None:
        self.assertEqual(cw_answer.with_enumeration("Greeting", None), "Greeting")

    def test_one_word_with_an_apostrophe_leaves_its_clue_alone(self) -> None:
        self.assertEqual(
            cw_answer.with_enumeration("On the hour", "O'CLOCK"), "On the hour"
        )


if __name__ == "__main__":
    unittest.main()
