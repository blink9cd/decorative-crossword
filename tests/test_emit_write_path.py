"""Tests for what the atomic writer makes of the output path it is handed.

Two properties of the PATH rather than of the text, each driven through
`preview --out` end to end, because `--out` is how an operator hands one over:

* **A symbolic link at the output** is replaced, never written through, and
  the file that takes its place gets the mode a new file gets. The link's
  target is some other file, so its bits are no template for this one, and
  copying them would let a link planted at the output choose the output's
  permissions.
* **An output name near the filesystem's limit** is written like any other,
  although the staging file beside it would carry a longer name.

The staging name's bound is then swept over every length a file name may have,
through `cw_emit._stage` on a real directory, so the filesystem judges each
name as well as the byte count does. Neither is enough alone: an APFS volume
refuses a split character outright, but counts its own limit in UTF-16 units,
so only the byte count holds a multi-byte name to the bound a Linux volume
sets.

Modes are compared against a file written plainly beside them rather than
against a literal, as in `test_emit_load.py`: Windows' `chmod` only toggles
the read-only flag, so a literal would pin one platform instead of asserting
the relationship on the running one.

Entry point assumptions: run through the parent aggregator's `load_tests` hook,
which puts the project root and `src/` on `sys.path`.
"""

import json
import os
import secrets
import stat
import tempfile
import unittest
from pathlib import Path

import cw_emit
import decorative_crossword
from tests import cli_fixtures

#: The umask the link cases run under, pinned rather than inherited so that
#: the mode a new file gets under it, 0o644, is known to differ from
#: `_TARGET_MODE`.
_UMASK = 0o022

#: The mode a link's target carries: executable, and so no mode a new file
#: gets under any umask, since a new file is never asked for an execute bit.
_TARGET_MODE = 0o711

#: The longest file name, in UTF-8 bytes, a Linux volume accepts. Stated here
#: rather than read from the writer, so the writer's bound is checked against
#: the number and not against itself.
_NAME_MAX_BYTES = 255

#: One character of each UTF-8 width, one byte through four.
_CHARACTERS = ("a", "é", "€", "🧩")

#: Every (character, size in bytes) the staging sweep names a file with.
_SWEEP = tuple(
    (character, size)
    for character in _CHARACTERS
    for size in range(1, _NAME_MAX_BYTES + 1)
)

#: A grid document for `preview` to draw.
_GRID = {"rows": ["CAT..", ".A...", "..T..", "DOG.."], "themes": {}, "clues": {}}

#: Why the link cases do not run everywhere.
_NO_LINKS = "creating a symbolic link needs a privilege most Windows accounts lack"


def _mode_of(path: Path) -> int:
    """The permission bits `path` carries, as the filesystem stores them."""
    return stat.S_IMODE(path.stat().st_mode)


def _name_of_bytes(size: int, character: str) -> str:
    """A name exactly `size` UTF-8 bytes long: `character` repeated, after ASCII padding.

    The padding varies with `size`, so across the sweep the point where a
    staging name has to be cut falls both between characters and inside one.
    """
    width = len(character.encode("utf-8"))
    return "a" * (size % width) + character * (size // width)


def _longest_fitting(name: str, token: str) -> str:
    """The longest leading part of `name` a staging name holding `token` can carry.

    The slow, obvious way -- one character off the end until it fits -- kept
    here as the oracle the writer's own answer is compared with.
    """
    kept = name
    while len(f".{kept}.{token}.tmp".encode("utf-8")) > _NAME_MAX_BYTES:
        kept = kept[:-1]
    return kept


class _PreviewCase(cli_fixtures.QuietCase):
    """A quiet case holding a grid document for `preview` to draw at an output."""

    def setUp(self) -> None:
        """Write the grid document into a folder of this case's own."""
        super().setUp()
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "grid.json"
        self.source.write_text(json.dumps(_GRID), encoding="utf-8", newline="\n")

    def preview(self, out: Path) -> int:
        """`main`'s exit code for drawing the grid document at `out`."""
        return decorative_crossword.main(
            ["preview", "--source", str(self.source), "--out", str(out)]
        )


@unittest.skipUnless(os.name == "posix", _NO_LINKS)
class TestALinkAtTheOutput(_PreviewCase):
    """A symbolic link at `--out` is replaced by a new file, and its target kept."""

    def setUp(self) -> None:
        """Pin the umask for this case, restoring the process's own afterwards."""
        super().setUp()
        self.addCleanup(os.umask, os.umask(_UMASK))

    def plain_mode(self) -> int:
        """The mode a file written plainly in this case's folder gets."""
        plain = self.root / "plain.svg"
        plain.write_text("plain\n", encoding="utf-8", newline="\n")
        return _mode_of(plain)

    def test_a_link_to_a_file_is_replaced_by_a_file_with_a_new_files_mode(
        self,
    ) -> None:
        """The planted case: the output must not take its mode from the target.

        The link's own bits are no answer either -- they describe the link,
        not a file -- so the output has to come back exactly as a file written
        there for the first time would.
        """
        target = self.root / "target.svg"
        target.write_text("target\n", encoding="utf-8", newline="\n")
        os.chmod(target, _TARGET_MODE)
        before = _mode_of(target)
        out = self.root / "preview.svg"
        out.symlink_to(target)
        self.assertEqual(self.preview(out), 0, self.errors)
        self.assertFalse(out.is_symlink())
        self.assertEqual(_mode_of(out), self.plain_mode())
        self.assertEqual(target.read_text(encoding="utf-8"), "target\n")
        self.assertEqual(_mode_of(target), before)

    def test_a_dangling_link_is_replaced_by_a_file_with_a_new_files_mode(
        self,
    ) -> None:
        """A link to nothing is no file either, and nothing is created through it."""
        missing = self.root / "missing.svg"
        out = self.root / "preview.svg"
        out.symlink_to(missing)
        self.assertEqual(self.preview(out), 0, self.errors)
        self.assertFalse(out.is_symlink())
        self.assertEqual(_mode_of(out), self.plain_mode())
        self.assertFalse(missing.exists())


class TestALongOutputName(_PreviewCase):
    """An output name the filesystem accepts is one `--out` writes."""

    def assert_written(self, name: str) -> None:
        """Draw at `name`, and find it written with nothing else left beside it."""
        out = self.root / name
        self.assertEqual(self.preview(out), 0, self.errors)
        self.assertGreater(out.stat().st_size, 0)
        self.assertEqual(
            sorted(entry.name for entry in self.root.iterdir()),
            sorted([self.source.name, name]),
        )

    def test_a_name_of_the_longest_length_is_written(self) -> None:
        self.assert_written(_name_of_bytes(_NAME_MAX_BYTES, "a"))

    def test_a_long_name_ending_in_a_two_byte_character_is_written(self) -> None:
        # One byte short of the limit, so the name ends on the whole character.
        self.assert_written(_name_of_bytes(_NAME_MAX_BYTES - 3, "a") + "é")


class TestStagingName(unittest.TestCase):
    """A staging name fits wherever the output's own name does."""

    def setUp(self) -> None:
        """A folder of this case's own, for the staging files to be opened in."""
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def staged(self, name: str) -> tuple[str, str]:
        """Open the staging file for an output called `name`; its stem and token.

        The stem is what the staging name keeps of `name`, and the token its
        random part. The file is opened for real, so the filesystem judges the
        name, and is removed again at once.
        """
        handle, path = cw_emit._stage(self.folder / name)
        os.close(handle)
        path.unlink()
        self.assertEqual(path.parent, self.folder)
        stem, token = path.name.removeprefix(".").removesuffix(".tmp").rsplit(".", 1)
        return stem, token

    def test_no_staging_name_is_longer_than_a_file_name_may_be(self) -> None:
        for character, size in _SWEEP:
            with self.subTest(character=character, size=size):
                stem, token = self.staged(_name_of_bytes(size, character))
                staged = f".{stem}.{token}.tmp"
                self.assertLessEqual(len(staged.encode("utf-8")), _NAME_MAX_BYTES)
                self.assertEqual(len(token), 2 * cw_emit._STAGING_NAME_BYTES)

    def test_a_name_is_cut_only_as_far_as_it_must_be(self) -> None:
        """A name that fits whole is kept byte for byte; one that does not is cut
        at the last whole character that fits.
        """
        for character, size in _SWEEP:
            with self.subTest(character=character, size=size):
                name = _name_of_bytes(size, character)
                stem, token = self.staged(name)
                self.assertEqual(stem, _longest_fitting(name, token))

    def test_an_undecodable_byte_is_measured_as_the_byte_the_kernel_gets(
        self,
    ) -> None:
        """A POSIX command line hands over a byte no UTF-8 decoder reads as a surrogate.

        A name holding one opens today wherever the filesystem takes any bytes,
        so it has to be measured as the bytes the open sends rather than as
        UTF-8 proper, which refuses the surrogate -- and, fitting, it is left
        exactly as it is.
        """
        name = "caf\udce9.svg"
        token = secrets.token_hex(cw_emit._STAGING_NAME_BYTES)
        self.assertEqual(cw_emit._staging_name(name, token), f".{name}.{token}.tmp")


if __name__ == "__main__":
    unittest.main()
