"""Grouped suite: how `parse_bank` validates a declared theme record.

`TestParseBankThemes` covers the `themes` map's own shape (the two required
fields, the rejected bare-label form, and the screen both fields go through),
and `TestThemesDeclaredElsewhere` the themes an entry may name when several
banks merge. Nothing is shared with `test_bank.py` but `cw_bank` itself.

Entry point assumptions: run through the root aggregator
(`../test_decorative_crossword.py`), which puts `src/` on `sys.path` before
discovering this directory. This suite imports its subject by bare name on
that basis rather than bootstrapping its own path.
"""

from __future__ import annotations

import unittest

import cw_bank


class TestParseBankThemes(unittest.TestCase):
    """The `themes` map's own shape, at the untrusted-input boundary."""

    def test_rejects_a_theme_with_no_summary(self) -> None:
        """The consumer's readout leads with the summary.

        A theme declared without one renders an empty readout on the page and
        nothing downstream can notice: the document is well-formed, the
        renderer throws nothing, the grid draws. Rejecting it here, at the
        untrusted-input boundary, is what makes that unreachable.
        """
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank(
                {
                    "themes": {"coffee": {"label": "Coffee"}},
                    "entries": [{"answer": "BLOOM"}],
                }
            )
        self.assertIn("summary", str(caught.exception))

    def test_rejects_a_theme_with_no_label(self) -> None:
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_bank(
                {
                    "themes": {"coffee": {"summary": "Pour-over"}},
                    "entries": [{"answer": "BLOOM"}],
                }
            )
        self.assertIn("label", str(caught.exception))

    def test_rejects_an_empty_theme_field(self) -> None:
        """An empty field is refused as firmly as an absent one: it says as little."""
        for field in ("label", "summary"):
            with self.subTest(field=field):
                record = {"label": "Coffee", "summary": "Pour-over", field: ""}
                with self.assertRaises(cw_bank.BankError) as caught:
                    cw_bank.parse_bank(
                        {"themes": {"coffee": record}, "entries": [{"answer": "BLOOM"}]}
                    )
                self.assertIn(f"non-empty string '{field}'", str(caught.exception))

    def test_rejects_a_bare_string_theme_record(self) -> None:
        """The bare `slug: "Label"` shape is rejected, not coerced.

        The bank is this project's untrusted-input boundary, so that shape
        fails loudly here rather than being read as a label with no summary,
        which would push a theme with nothing to say all the way to the page.
        """
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(
                {"themes": {"coffee": "Coffee"}, "entries": [{"answer": "BLOOM"}]}
            )

    def test_screens_a_theme_summary_for_the_script_close(self) -> None:
        """A summary reaches the consumer's document exactly as a clue does."""
        with self.assertRaises(cw_bank.BankError):
            cw_bank.parse_bank(
                {
                    "themes": {
                        "coffee": {"label": "Coffee", "summary": "a </script b"}
                    },
                    "entries": [{"answer": "BLOOM"}],
                }
            )


class TestThemesDeclaredElsewhere(unittest.TestCase):
    """The themes an entry may name, when several banks are merged into one run."""

    def test_declared_themes_let_an_entry_name_a_theme_its_file_does_not(self) -> None:
        """A names bank may use a theme the site-wide bank beside it declares."""
        declared = {"coffee": cw_bank.ThemeInfo(label="Coffee", summary="Pour-over")}
        bank = cw_bank.parse_bank(
            {"themes": {}, "entries": [{"answer": "BLOOM", "theme": "coffee"}]},
            declared,
        )
        self.assertEqual(bank.entries[0].theme, "coffee")
        self.assertEqual(dict(bank.themes), declared)

    def test_parse_themes_reads_a_files_own_declarations(self) -> None:
        payload = {
            "themes": {"coffee": {"label": "Coffee", "summary": "Pour-over"}},
            "entries": [{"answer": "BLOOM", "theme": "tea"}],
        }
        self.assertEqual(
            dict(cw_bank.parse_themes(payload)),
            {"coffee": cw_bank.ThemeInfo(label="Coffee", summary="Pour-over")},
        )

    def test_parse_themes_checks_the_payload_in_parse_banks_order(self) -> None:
        """An empty entries list is named before a malformed theme, as parse_bank names it."""
        payload = {"themes": {"coffee": "Coffee"}, "entries": []}
        with self.assertRaises(cw_bank.BankError) as expected:
            cw_bank.parse_bank(payload)
        with self.assertRaises(cw_bank.BankError) as caught:
            cw_bank.parse_themes(payload)
        self.assertEqual(str(caught.exception), str(expected.exception))


if __name__ == "__main__":
    unittest.main()
