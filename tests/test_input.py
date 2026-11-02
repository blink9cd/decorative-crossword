"""Tests for cw_input: which paths are read as an input file, and what comes back.

A path on a command line can name a FIFO, a device, a pipe or a directory as
easily as a file, and each would misbehave if read like one: a FIFO waits for a
writer that may never come, and `/dev/zero` never runs out. So only a regular
file is read, and only one within `MAX_INPUT_BYTES`. What comes back from a
file that is read must be exactly what `Path.read_text(encoding="utf-8")`
returns, because every reader switched to this one from that. The one file
that reads otherwise is one that begins with a byte-order mark, which is
refused rather than returned.

The oversized cases use sparse files, made with `os.truncate`, so a file past
the cap costs no disk and, where the cap is enforced before reading, no memory.

No case here opens a FIFO in this process. Opened as a file, a FIFO with no
writer blocks, so a reader that regressed would hang the whole suite rather
than fail a case; `tests/test_cli_input.py` gives every reader a FIFO in a
child under a timeout instead. The cases here are chosen so that no single
regression can make one wait: `/dev/zero` is still stopped by the cap, and the
pipe holds its bytes with no writer left, so a read of it ends.

Entry point assumptions: run through the parent aggregator's `load_tests` hook,
which puts the project root and `src/` on `sys.path`.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

import cw_input

# A registered profile loaded at import, never an `@settings` decorator, as the
# project's other property suites do. Derandomized so the in-suite run is
# reproducible; no deadline, because each example writes a file and a
# per-example wall clock would measure the disk rather than the reader.
# too_slow is suppressed as well: on a cold .hypothesis cache the first draw also
# pays Hypothesis's one-time setup (the unicode tables a text strategy needs, a scan
# of the local modules for constants), which under load outlasts even the limit
# left without a deadline.
settings.register_profile(
    "crossword_input_properties",
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("crossword_input_properties")

#: The character a byte-order mark decodes to.
_BOM = "\U0000feff"

#: The pieces the newline translation and the decode are about, drawn far more
#: often than arbitrary text would reach them: both line ends and the pair, and
#: U+FEFF, which a UTF-8 decode must keep rather than strip anywhere after the
#: first character.
_EDGES = ("\r", "\n", "\r\n", _BOM)

#: Text assembled from arbitrary characters and the edges above, never
#: beginning with U+FEFF: that is the one text read back as a refusal, which
#: `TestByteOrderMark` covers. Surrogates are left out, as `st.characters` does
#: by default: no UTF-8 file holds one.
_TEXT = (
    st.lists(st.one_of(st.text(max_size=4), st.sampled_from(_EDGES)))
    .map("".join)
    .filter(lambda text: not text.startswith(_BOM))
)

#: Why a test that needs one of these paths is skipped where it is absent.
_NO_DEV_ZERO = "this platform has no /dev/zero"
_NO_DEV_FD = "this platform has no /dev/fd to name a pipe by"
_NO_POSIX_DIRECTORY_OPEN = "only POSIX opens a directory for reading"


def _sparse(folder: str, size: int) -> Path:
    """A file of `size` zero bytes in `folder` that occupies no disk."""
    path = Path(folder) / "input.txt"
    path.touch()
    os.truncate(path, size)
    return path


@contextlib.contextmanager
def _descriptors_seen() -> Iterator[tuple[list[int], list[int]]]:
    """The descriptors `cw_input` opens, and those it closes, inside the block.

    Both calls are recorded as they happen rather than inferred afterward:
    a descriptor number freed by a close can be handed straight back out by
    the next open, so probing the old number later proves nothing.
    """
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def recording_open(path: Path, flags: int) -> int:
        descriptor = real_open(path, flags)
        opened.append(descriptor)
        return descriptor

    def recording_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    with (
        mock.patch.object(cw_input.os, "open", recording_open),
        mock.patch.object(cw_input.os, "close", recording_close),
    ):
        yield opened, closed


class TestReadBack(unittest.TestCase):
    """A regular file within the cap reads exactly as `Path.read_text` reads it.

    Unless it begins with a byte-order mark, which `TestByteOrderMark` covers.
    """

    @given(_TEXT)
    @example("")
    @example("a\r\nb\rc\n")
    @example("\r\r\n\r")
    @example("BOM\U0000feff\r\n")
    def test_reads_what_read_text_reads(self, text: str) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(text.encode("utf-8"))
            self.assertEqual(
                cw_input.read_input_text(path), path.read_text(encoding="utf-8")
            )

    def test_a_file_that_is_not_utf_8_raises_the_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(b"CAF\xff\n")
            with self.assertRaises(UnicodeDecodeError):
                cw_input.read_input_text(path)

    def test_a_missing_file_raises_the_open_error(self) -> None:
        # Not an UnreadableInput: a missing file keeps the error every reader
        # already turned into its own refusal.
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                cw_input.read_input_text(Path(folder) / "absent.txt")

    def test_a_link_to_a_regular_file_is_read_as_the_file(self) -> None:
        # The kind is judged on what the name opens, so a link to a regular
        # file is that file, not a thing refused for being a link.
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "target.txt"
            target.write_bytes(b"CAT\n")
            link = Path(folder) / "link.txt"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(
                    "this host may not create a symbolic link, as Windows may not "
                    f"without the symlink privilege: {exc}"
                )
            self.assertEqual(cw_input.read_input_text(link), "CAT\n")


class TestByteOrderMark(unittest.TestCase):
    """A U+FEFF that opens the file is refused; one anywhere after it is text."""

    def test_a_file_that_begins_with_one_is_refused(self) -> None:
        # The bytes an editor writes when it saves "UTF-8 with BOM".
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(b"\xef\xbb\xbfCAT\n")
            with self.assertRaises(cw_input.UnreadableInput) as caught:
                cw_input.read_input_text(path)
        self.assertEqual(
            str(caught.exception),
            f"{path} begins with a byte-order mark (U+FEFF); "
            "save it as UTF-8 without one",
        )

    def test_one_after_the_first_character_is_kept(self) -> None:
        # Left for each reader's own rules to judge, as any other character is.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(f"CAT\n{_BOM}DOG\n".encode("utf-8"))
            self.assertEqual(cw_input.read_input_text(path), f"CAT\n{_BOM}DOG\n")


class TestNotARegularFile(unittest.TestCase):
    """Anything but a regular file is refused, without waiting and without reading."""

    def _assert_refused(self, path: Path) -> None:
        """`path` is refused as not a regular file, naming it."""
        with self.assertRaises(cw_input.UnreadableInput) as caught:
            cw_input.read_input_text(path)
        self.assertEqual(str(caught.exception), f"{path} is not a regular file")

    @unittest.skipUnless(Path("/dev/zero").exists(), _NO_DEV_ZERO)
    def test_a_device_that_never_ends_is_refused(self) -> None:
        self._assert_refused(Path("/dev/zero"))

    @unittest.skipUnless(Path("/dev/fd").is_dir(), _NO_DEV_FD)
    def test_a_pipe_is_refused(self) -> None:
        # The shape of `/dev/stdin` fed from another command: the same
        # descriptor check refuses it, with no rule about the path's name.
        # The bytes are written and the writer closed first, so a reader that
        # stopped checking would read them and return rather than wait.
        reading, writing = os.pipe()
        self.addCleanup(os.close, reading)
        with os.fdopen(writing, "wb") as sink:
            sink.write(b"CAT\n")
        self._assert_refused(Path(f"/dev/fd/{reading}"))

    @unittest.skipUnless(os.name == "posix", _NO_POSIX_DIRECTORY_OPEN)
    def test_a_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self._assert_refused(Path(folder))


class TestSizeCap(unittest.TestCase):
    """A regular file is read only up to `MAX_INPUT_BYTES`."""

    def _assert_too_large(self, path: Path) -> None:
        """`path` is refused as larger than the cap, stated in MiB and naming it."""
        with self.assertRaises(cw_input.UnreadableInput) as caught:
            cw_input.read_input_text(path)
        self.assertEqual(
            str(caught.exception),
            f"{path} is larger than the "
            f"{cw_input.MAX_INPUT_BYTES // (1024 * 1024)} MiB an input file may be",
        )

    def test_the_cap_is_thirty_two_mebibytes(self) -> None:
        self.assertEqual(cw_input.MAX_INPUT_BYTES, 32 * 1024 * 1024)

    def test_a_file_exactly_at_the_cap_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _sparse(folder, cw_input.MAX_INPUT_BYTES)
            self.assertEqual(
                len(cw_input.read_input_text(path)), cw_input.MAX_INPUT_BYTES
            )

    def test_a_file_past_the_cap_is_refused_without_being_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _sparse(folder, cw_input.MAX_INPUT_BYTES + 1)
            with mock.patch.object(cw_input.os, "read", wraps=os.read) as reading:
                self._assert_too_large(path)
            reading.assert_not_called()

    def test_a_file_that_grows_past_the_cap_while_open_is_refused(self) -> None:
        # The file is small when its status is taken and past the cap by the
        # time it is read, which is what a file still being written looks like.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(b"CAT\n")
            real_fstat = os.fstat

            def fstat_then_grow(descriptor: int) -> os.stat_result:
                status = real_fstat(descriptor)
                os.truncate(path, cw_input.MAX_INPUT_BYTES + 1)
                return status

            with mock.patch.object(cw_input.os, "fstat", fstat_then_grow):
                self._assert_too_large(path)

    def test_a_file_that_grows_past_the_cap_is_read_to_one_byte_past_it(self) -> None:
        # Reading such a file whole before refusing it would refuse it all the
        # same, so the refusal cannot tell a bounded read from an unbounded one:
        # what the reads asked for can. One byte past the cap is the byte that
        # shows the file is too long, and the file grows to twice the cap, so a
        # read to its end asks for far more than that.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(b"CAT\n")
            real_fstat = os.fstat

            def fstat_then_grow(descriptor: int) -> os.stat_result:
                status = real_fstat(descriptor)
                os.truncate(path, 2 * cw_input.MAX_INPUT_BYTES)
                return status

            with (
                mock.patch.object(cw_input.os, "fstat", fstat_then_grow),
                mock.patch.object(cw_input.os, "read", wraps=os.read) as reading,
            ):
                self._assert_too_large(path)
        asked = sum(call.args[1] for call in reading.call_args_list)
        self.assertLessEqual(asked, cw_input.MAX_INPUT_BYTES + 1)


class TestDescriptorIsClosed(unittest.TestCase):
    """The descriptor the reader opens is closed however the read ends."""

    def _assert_closed(self, seen: tuple[list[int], list[int]]) -> None:
        """Exactly one descriptor was opened, and exactly that one was closed."""
        opened, closed = seen
        self.assertEqual(len(opened), 1)
        self.assertEqual(closed, opened)

    def test_after_a_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(b"CAT\n")
            with _descriptors_seen() as seen:
                cw_input.read_input_text(path)
            self._assert_closed(seen)

    @unittest.skipUnless(Path("/dev/zero").exists(), _NO_DEV_ZERO)
    def test_after_refusing_what_is_not_a_regular_file(self) -> None:
        with _descriptors_seen() as seen:
            with self.assertRaises(cw_input.UnreadableInput):
                cw_input.read_input_text(Path("/dev/zero"))
        self._assert_closed(seen)

    def test_after_refusing_a_file_past_the_cap(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _sparse(folder, cw_input.MAX_INPUT_BYTES + 1)
            with _descriptors_seen() as seen:
                with self.assertRaises(cw_input.UnreadableInput):
                    cw_input.read_input_text(path)
            self._assert_closed(seen)

    def test_after_a_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.txt"
            path.write_bytes(b"\xff")
            with _descriptors_seen() as seen:
                with self.assertRaises(UnicodeDecodeError):
                    cw_input.read_input_text(path)
            self._assert_closed(seen)


if __name__ == "__main__":
    unittest.main()
