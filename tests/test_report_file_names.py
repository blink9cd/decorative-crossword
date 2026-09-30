"""Tests: a file name a report prints is shown the way a refusal shows it.

Three report lines on stdout name a file the operator gave: the merge line
naming each `--bank`, and the `--mask` line in `fill`'s report and in `gaps`'.
A file name can hold a control character, a bidi control included, and on a
POSIX host a byte that is not UTF-8 reaches Python as a lone surrogate.
Printed raw, an override makes the line display text other than the name it
holds, and a surrogate cannot be written to the strict UTF-8 stdout at all, so
the run would end in a traceback after the grid is written. Each such
character is escaped where the line is built, as a refusal escapes it, and
every other character, accents included, is printed as it is.

The render functions are tested directly, because a file name holding a byte
that is not UTF-8 cannot be created on every file system; one `fill` run then
shows the escape reaching stdout.

Run through test_decorative_crossword.py's `load_tests` hook.
"""

import json
import tempfile
import unittest
from typing import cast

import cw_config
import cw_gaps
import cw_gaps_report
import cw_report
import decorative_crossword
from tests import cli_fixtures
from tests.report_fixtures import line as _line
from tests.report_fixtures import make_bank as _bank
from tests.report_fixtures import make_config as _config
from tests.report_fixtures import make_outcome as _outcome
from tests.test_cli_banks import NAMES_BANK

#: RIGHT-TO-LEFT OVERRIDE, which a file name can hold: the text after it is
#: displayed right to left, so the line shows other text than the name it holds.
_OVERRIDE = "\U0000202e"

#: What Python makes of the byte 0xFF in a path on a POSIX host: a lone
#: surrogate, which a strict UTF-8 stream cannot write.
_SURROGATE = "\U0000dcff"

#: Each name a report must escape, the name as the report shows it, and the
#: character that must not reach the line raw. The shown forms are spelled out
#: rather than derived, so the tests do not restate how an escape is built.
_ESCAPED = (
    (f"names{_OVERRIDE}osj.json", "names\\u202eosj.json", _OVERRIDE),
    (f"names{_SURROGATE}.json", "names\\udcff.json", _SURROGATE),
)

#: Names a report prints as they are: a plain one, and one with an accent,
#: since the escape is for what a terminal cannot take, not for what is not
#: ASCII.
_ORDINARY = ("names.json", "caf\U000000e9.json")

#: The one cell of the report fixtures' 3x3 grid each mask below draws out:
#: blocked in that grid, so the grid a picture forbids it in is the same grid.
_MASKED = frozenset({(1, 1)})

#: The rows the `gaps` report is rendered over: the report fixtures' grid.
_ROWS = ("CAT", "O..", "WET")


def _merged_line(name: str) -> str:
    """The merge line of a `fill` report over a first bank and one named `name`."""
    files = (("bank.json", 5), (name, 2))
    text = cw_report.render_report(_outcome(), _bank(), _config(), [], files=files)
    return _line(text, "Merged ")


def _fill_mask_line(name: str) -> str:
    """The `--mask` line of a `fill` report whose picture is named `name`."""
    config = _config(masked=_MASKED, mask_size=(3, 3))
    text = cw_report.render_report(
        _outcome(config=config), _bank(), config, [], mask_file=name
    )
    return _line(text, "From --mask ")


def _gaps_mask_line(name: str) -> str:
    """The `--mask` line of a `gaps` report whose picture is named `name`."""
    config = cw_config.GapsConfig(
        top=cast(int, cw_config.DEFAULTS["top"]),
        include_absorbing=False,
        cell=cast(int, cw_config.DEFAULTS["cell"]),
        masked=_MASKED,
    )
    search = cw_gaps.search_gaps(_ROWS, frozenset(), config.masked)
    text = cw_gaps_report.render_report(_ROWS, search, config, (), mask_file=name)
    return _line(text, "From --mask ")


def _mask_sentence(shown: str) -> str:
    """The `--mask` line either report prints for a picture shown as `shown`."""
    return f"From --mask {shown}: 1 of 9 cells may never hold a letter."


def _merged_sentence(shown: str) -> str:
    """The merge line for a second bank shown as `shown`."""
    return (
        "Merged 2 bank files, in the order given: bank.json (5 entries), "
        f"{shown} (2 entries)."
    )


class TestTheMergeLine(unittest.TestCase):
    """`fill`'s report lists each `--bank` of a merge, each name escaped."""

    def test_a_name_no_terminal_can_take_is_escaped(self) -> None:
        for name, shown, raw in _ESCAPED:
            with self.subTest(name=ascii(name)):
                printed = _merged_line(name)
                self.assertNotIn(raw, printed)
                self.assertEqual(printed, _merged_sentence(shown))

    def test_an_ordinary_name_is_printed_as_it_is(self) -> None:
        for name in _ORDINARY:
            with self.subTest(name=ascii(name)):
                self.assertEqual(_merged_line(name), _merged_sentence(name))


class TestTheFillMaskLine(unittest.TestCase):
    """`fill`'s report names its `--mask` picture, the name escaped."""

    def test_a_name_no_terminal_can_take_is_escaped(self) -> None:
        for name, shown, raw in _ESCAPED:
            with self.subTest(name=ascii(name)):
                printed = _fill_mask_line(name)
                self.assertNotIn(raw, printed)
                self.assertEqual(printed, _mask_sentence(shown))

    def test_an_ordinary_name_is_printed_as_it_is(self) -> None:
        for name in _ORDINARY:
            with self.subTest(name=ascii(name)):
                self.assertEqual(_fill_mask_line(name), _mask_sentence(name))


class TestTheGapsMaskLine(unittest.TestCase):
    """`gaps`' report names its `--mask` picture, the name escaped."""

    def test_a_name_no_terminal_can_take_is_escaped(self) -> None:
        for name, shown, raw in _ESCAPED:
            with self.subTest(name=ascii(name)):
                printed = _gaps_mask_line(name)
                self.assertNotIn(raw, printed)
                self.assertEqual(printed, _mask_sentence(shown))

    def test_an_ordinary_name_is_printed_as_it_is(self) -> None:
        for name in _ORDINARY:
            with self.subTest(name=ascii(name)):
                self.assertEqual(_gaps_mask_line(name), _mask_sentence(name))


class TestAFillRun(cli_fixtures.QuietCase):
    """The escape reaches stdout: a real run's report shows the name escaped."""

    def test_a_bank_named_with_an_override_is_printed_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            space = cli_fixtures.Workspace(folder)
            names = space.root / f"names{_OVERRIDE}osj.json"
            # The file system may refuse the name (OSError), or the encoding Python
            # names files in may have no way to encode the override
            # (UnicodeEncodeError, which is no OSError): either way, no such file here.
            try:
                names.write_text(json.dumps(NAMES_BANK), encoding="utf-8", newline="\n")
            except (OSError, UnicodeEncodeError) as exc:
                self.skipTest(f"this file system refuses the name: {exc}")
            code = decorative_crossword.main(space.fill("--bank", str(names)))
            shown = f"{space.root / 'names'}\\u202eosj.json"
            expected = (
                f"Merged 2 bank files, in the order given: {space.bank} (9 entries), "
                f"{shown} (2 entries)."
            )
        self.assertEqual(code, 0)
        self.assertNotIn(_OVERRIDE, self.printed)
        self.assertIn(expected, self.printed.splitlines())
