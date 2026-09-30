"""Tests for the grid document reader, `cw_grid_document`, and the shared text write.

The reader's cases read a document back, most of them one this tool would never
write: `preview` is useful on a hand-authored `grid_source.json`, so a
malformed one is refused rather than trusted. The shared text write,
`cw_emit.write_atomically`, is the one every output (the grid and each SVG)
goes through, so its cases here (the atomic replace, the mode a written file
keeps, the Windows facts it depends on) exercise it on its own terms rather
than through any one format; the name it stages under, and a link planted at
the output, are `test_emit_write_path.py`'s. `test_emit.py` builds a document
and pins the bytes it serializes to, and it reaches the write too: the grid's
replace and cleanup through `write_document`, and the encoder's refusal through
`write_atomically` itself.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cw_bank
import cw_emit
import cw_grid_document

_DOCUMENT: dict[str, object] = {
    "rows": ["CAT", "O..", "WET"],
    "themes": {"pets": {"label": "Pets", "summary": "Two cats and a lot of hair"}},
    "clues": {"CAT": {"clue": "Sleeps on the keyboard", "theme": "pets"}},
}


def _written(folder: str, payload: object) -> Path:
    """Write `payload` as JSON into `folder` and return its path."""
    path = Path(folder) / "grid_source.json"
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    return path


def _mode_of(path: Path) -> int:
    """The permission bits `path` carries, as the filesystem stores them."""
    return stat.S_IMODE(path.stat().st_mode)


class TestLoadDocument(unittest.TestCase):
    """A grid_source.json is read, or refused with a reason -- never guessed at."""

    def test_reads_the_documented_shape(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            document = cw_grid_document.load_document(_written(folder, _DOCUMENT))
            self.assertEqual(document.rows, ("CAT", "O..", "WET"))
            self.assertEqual(
                dict(document.themes),
                {"pets": cw_bank.ThemeInfo("Pets", "Two cats and a lot of hair")},
            )
            self.assertEqual(dict(document.entry_themes), {"CAT": "pets"})

    def test_round_trips_what_the_emitter_writes(self) -> None:
        # The two halves of the document format pinned against each other: a
        # document this tool wrote must be one this tool can read.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            cw_emit.write_document(path, _DOCUMENT)
            self.assertEqual(
                cw_grid_document.load_document(path).rows, ("CAT", "O..", "WET")
            )

    def test_an_absent_theme_map_reads_as_no_themes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, {"rows": ["CAT", "O..", "WET"]})
            document = cw_grid_document.load_document(path)
            self.assertEqual(dict(document.themes), {})
            self.assertEqual(dict(document.entry_themes), {})

    def test_a_clue_record_with_no_theme_contributes_none(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(
                folder,
                {"rows": ["CAT", "O..", "WET"], "clues": {"CAT": {"clue": "x"}}},
            )
            self.assertEqual(
                dict(cw_grid_document.load_document(path).entry_themes), {}
            )

    def test_an_entry_with_no_clue_is_read_without_complaint(self) -> None:
        # Questionable CONTENT is for whatever consumes the grid to judge, not
        # this loader.
        with tempfile.TemporaryDirectory() as folder:
            path = _written(
                folder, {"rows": ["CAT", "O..", "WET"], "clues": {"CAT": {}}}
            )
            self.assertEqual(cw_grid_document.load_document(path).rows[0], "CAT")

    def test_a_theme_used_but_not_declared_is_read_without_complaint(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(
                folder,
                {
                    "rows": ["CAT", "O..", "WET"],
                    "themes": {},
                    "clues": {"CAT": {"clue": "x", "theme": "ghost"}},
                },
            )
            self.assertEqual(
                dict(cw_grid_document.load_document(path).entry_themes),
                {"CAT": "ghost"},
            )

    def test_reports_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_emit.EmitError):
                cw_grid_document.load_document(Path(folder) / "absent.json")

    def test_reports_a_directory_where_a_file_is_expected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_emit.EmitError):
                cw_grid_document.load_document(Path(folder))

    def test_reports_a_file_that_is_not_valid_utf_8(self) -> None:
        # UnicodeDecodeError is a ValueError and NOT an OSError. Uncaught, it
        # escapes the CLI's refusal set and gives `preview` an exit 1 it does
        # not have.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            path.write_bytes(b'{"rows": ["CA\xff"]}')
            with self.assertRaises(cw_emit.EmitError):
                cw_grid_document.load_document(path)

    def test_reports_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid_source.json"
            path.write_text("{not json", encoding="utf-8", newline="\n")
            with self.assertRaises(cw_emit.EmitError):
                cw_grid_document.load_document(path)

    def test_rejects_a_payload_that_is_not_an_object(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(cw_emit.EmitError):
                cw_grid_document.load_document(_written(folder, [1, 2, 3]))

    def test_rejects_an_incoherent_grid(self) -> None:
        for label, rows in (
            ("ragged", ["CAT", "WETS"]),
            ("empty", []),
            ("no columns", ["", ""]),
            ("bad cell", ["CA?", "O..", "WET"]),
            ("not strings", [["C", "A", "T"]]),
            ("absent", None),
        ):
            with self.subTest(label), tempfile.TemporaryDirectory() as folder:
                payload: dict[str, object] = {"themes": {}, "clues": {}}
                if rows is not None:
                    payload["rows"] = rows
                with self.assertRaises(cw_emit.EmitError):
                    cw_grid_document.load_document(_written(folder, payload))

    def test_rejects_a_themes_value_of_the_wrong_type(self) -> None:
        # The last two are the record's own FIELDS being wrong, which the
        # record-shape check above them cannot reach: a well-formed object
        # whose label or summary is not a string.
        cases: list[object] = [
            [],
            {"pets": 5},
            {"pets": "Pets"},
            {"pets": {"label": 5, "summary": "s"}},
            {"pets": {"label": "Pets", "summary": 5}},
        ]
        for themes in cases:
            with self.subTest(repr(themes)), tempfile.TemporaryDirectory() as folder:
                path = _written(
                    folder, {"rows": ["CAT", "O..", "WET"], "themes": themes}
                )
                with self.assertRaises(cw_emit.EmitError):
                    cw_grid_document.load_document(path)

    def test_rejects_a_clues_value_of_the_wrong_type(self) -> None:
        cases: list[object] = [[], {"CAT": "a clue"}, {"CAT": {"theme": 5}}]
        for clues in cases:
            with self.subTest(repr(clues)), tempfile.TemporaryDirectory() as folder:
                path = _written(folder, {"rows": ["CAT", "O..", "WET"], "clues": clues})
                with self.assertRaises(cw_emit.EmitError):
                    cw_grid_document.load_document(path)

    def test_rejects_a_non_string_key_reached_without_json(self) -> None:
        # Unreachable through a FILE -- JSON object keys are always strings --
        # but `parse_document` is public and takes any payload, exactly as
        # `cw_bank.parse_bank` does, so the guard is tested where it can fire.
        with self.assertRaises(cw_emit.EmitError):
            cw_grid_document.parse_document(
                {
                    "rows": ["CAT", "O..", "WET"],
                    "themes": {5: {"label": "P", "summary": "s"}},
                }
            )

    def test_parses_a_payload_that_never_touched_a_file(self) -> None:
        # The path `fill --preview` takes: it narrows the document it just
        # built through this same function, so every caller of the renderer
        # holds a value derived exactly one way.
        view = cw_grid_document.parse_document(_DOCUMENT)
        self.assertEqual(view.entry_themes["CAT"], "pets")

    def test_the_message_names_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = _written(folder, [1, 2, 3])
            with self.assertRaises(cw_emit.EmitError) as caught:
                cw_grid_document.load_document(path)
            self.assertIn(path.name, str(caught.exception))


class TestWriteAtomically(unittest.TestCase):
    """The atomic writer both outputs share, exercised on its own terms."""

    def test_writes_the_text_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preview.svg"
            cw_emit.write_atomically(path, "<svg/>\n")
            self.assertEqual(path.read_bytes(), b"<svg/>\n")

    def test_replaces_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preview.svg"
            cw_emit.write_atomically(path, "first\n")
            cw_emit.write_atomically(path, "second\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "second\n")

    def test_reports_an_unusable_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preview.svg"
            path.mkdir()
            with self.assertRaises(cw_emit.EmitError):
                cw_emit.write_atomically(path, "<svg/>\n")

    def test_leaves_no_temporary_file_behind_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preview.svg"
            path.mkdir()
            with self.assertRaises(cw_emit.EmitError):
                cw_emit.write_atomically(path, "<svg/>\n")
            self.assertEqual(
                [entry.name for entry in Path(folder).iterdir()], ["preview.svg"]
            )


class TestWriteAtomicallyMode(unittest.TestCase):
    """The permission bits a written file comes back with.

    `os.replace` carries the STAGING file's mode onto the target, and a staging
    file made by `tempfile` is readable by its creator alone -- so without a
    carry-over every file this writer touches would come back 0600, execute
    bit gone. Both losses are quiet: git records only the executable bit, and
    `git checkout --` restores a mode only on a run that rewrites the content
    too, so a narrowed file stays narrowed in that working tree indefinitely.

    A rewrite keeps the file's OWN bits. A NEW file gets what a plain write
    would have given it under the current umask, because there is no template
    to copy from -- and a new file is the ORDINARY case here, not an edge:
    `--out` names wherever the operator wants the picture, and `cw_paths`
    never requires that the file already exist.

    Every assertion compares a mode READ BACK from disk against another read
    back the same way, never against a literal. Windows' `chmod` only toggles
    the read-only flag, so a literal would pin the author's platform instead of
    asserting the relationship on the running one.
    """

    def setUp(self) -> None:
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def seeded(self, name: str, mode: int) -> tuple[Path, int]:
        """A file at `name` carrying `mode`, and that mode as the filesystem stored it."""
        path = self.folder / name
        path.write_text("before\n", encoding="utf-8", newline="\n")
        os.chmod(path, mode)
        return path, _mode_of(path)

    def plainly_written(self, name: str) -> Path:
        """A file written the way a caller would have written it without this tool."""
        path = self.folder / name
        path.write_text("plain\n", encoding="utf-8", newline="\n")
        return path

    def test_a_rewrite_keeps_a_world_readable_mode(self) -> None:
        """The common case: a picture redrawn over yesterday's is still readable."""
        path, before = self.seeded("preview.svg", 0o644)
        cw_emit.write_atomically(path, "<svg/>\n")
        self.assertEqual(_mode_of(path), before)

    def test_a_rewrite_keeps_the_execute_bit(self) -> None:
        """The sharper loss, and the one git WOULD have reported had it survived.

        Nothing this tool writes today is runnable, which is a fact about its
        outputs rather than about the writer -- and it is the writer that has to
        hold, because a shared one acquires call sites.
        """
        path, before = self.seeded("regenerate.sh", 0o755)
        cw_emit.write_atomically(path, "#!/bin/sh\n")
        self.assertEqual(_mode_of(path), before)

    def test_a_rewrite_keeps_a_mode_that_is_neither_default(self) -> None:
        """0640 is neither what a plain write gives nor what a flat 0644 would be.

        Without it, a fix that stamped every rewrite 0644 would satisfy the case
        above while still discarding whatever the file actually said.
        """
        path, before = self.seeded("group.svg", 0o640)
        cw_emit.write_atomically(path, "<svg/>\n")
        self.assertEqual(_mode_of(path), before)

    def test_a_rewrite_keeps_a_mode_that_is_already_owner_only(self) -> None:
        """Keeping a file's bits means keeping them in both directions.

        The case is here for the opposite mistake: widening every output to
        whatever the umask gives is as much a decision about the operator's
        directory as narrowing it, and this tool has no business taking either.
        Its bite comes from the create asking for 0o666 -- drop the carry-over
        and a private file comes back 0644, not 0600.
        """
        path, before = self.seeded("private.svg", 0o600)
        cw_emit.write_atomically(path, "<svg/>\n")
        self.assertEqual(_mode_of(path), before)

    def test_a_new_file_matches_what_a_plain_write_gives(self) -> None:
        """A first `--out` run has no template, so the honest answer is the umask's.

        The oracle is a file written beside it in the same directory and the same
        process rather than a number, which is what makes this hold at whatever
        umask the operator happens to be running under.
        """
        fresh = self.folder / "fresh.svg"
        cw_emit.write_atomically(fresh, "<svg/>\n")
        self.assertEqual(_mode_of(fresh), _mode_of(self.plainly_written("plain.svg")))

    def test_a_new_file_follows_the_umask_in_both_directions(self) -> None:
        """The same comparison under two umasks chosen to discriminate, not to decorate.

        A umask separates a creation mode from a literal only where it does not
        already strip the bits the two disagree on: `0o002` leaves group-write
        standing, which is what tells asking for `0o666` apart from asking for a
        hardcoded `0o644`. `0o077` then catches the opposite mistake -- a mode
        stamped on AFTER creation, which bypasses the umask rather than being
        filtered by it.

        A single typical umask such as `0o022` cannot tell the two apart:
        `0o666` and a hardcoded `0o644` both come out `0o644` under it.
        """
        for mask in (0o002, 0o077):
            with self.subTest(umask=oct(mask)):
                previous = os.umask(mask)
                try:
                    fresh = self.folder / f"masked-{mask:03o}.svg"
                    cw_emit.write_atomically(fresh, "<svg/>\n")
                    plain = self.plainly_written(f"plain-{mask:03o}.svg")
                    self.assertEqual(_mode_of(fresh), _mode_of(plain))
                finally:
                    os.umask(previous)


class TestWriteAtomicallyOnWindows(unittest.TestCase):
    """Two facts of a Windows host at the oldest interpreter this project supports.

    Neither holds on a POSIX host, so each case fakes exactly the one fact the
    writer depends on and runs the real write around it.
    """

    def setUp(self) -> None:
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_a_rewrite_where_fchmod_does_not_exist_still_writes(self) -> None:
        # `os.fchmod` reached Windows only in Python 3.13, and a mode is carried
        # only onto a file that already exists -- so overwriting a grid is the one
        # run a bare call breaks there, with an AttributeError no caller reports.
        # patch.dict restores os's namespace on exit; pop's default keeps this
        # runnable on a host that has no fchmod to remove.
        path = self.folder / "grid_source.json"
        path.write_text("before\n", encoding="utf-8", newline="\n")
        with mock.patch.dict(vars(os)), mock.patch.object(sys, "platform", "win32"):
            vars(os).pop("fchmod", None)
            cw_emit.write_atomically(path, "after\n")
        self.assertEqual(path.read_bytes(), b"after\n")

    def test_the_staging_file_is_opened_in_binary_mode(self) -> None:
        # Without O_BINARY a Windows descriptor is in text mode, and the C runtime
        # writes every "\n" as "\r\n" underneath `newline="\n"`, so no committed
        # sample would come out byte-identical there. The flag exists only on
        # Windows, so it is faked -- at Windows' own value -- and stripped again
        # before the real open, since on this host that bit may mean something else.
        # The host's own flag, read before the patch, is put back: on Windows it IS
        # 0x8000, and an open with it stripped would write CRLF and fail the byte check.
        fake_binary = 0x8000
        host_binary = getattr(os, "O_BINARY", 0)
        seen: list[int] = []
        real_open = os.open

        def recording_open(path: Path, flags: int, mode: int = 0o777) -> int:
            seen.append(flags)
            return real_open(path, (flags & ~fake_binary) | host_binary, mode)

        with (
            mock.patch.object(os, "O_BINARY", fake_binary, create=True),
            mock.patch.object(os, "open", recording_open),
        ):
            cw_emit.write_atomically(self.folder / "preview.svg", "<svg/>\n")
        self.assertEqual([flags & fake_binary for flags in seen], [fake_binary])
        self.assertEqual((self.folder / "preview.svg").read_bytes(), b"<svg/>\n")


class TestDeclaredClues(unittest.TestCase):
    """A document names each declared answer's clue, so `fill --source` can keep it."""

    def test_every_clues_key_is_declared_with_its_text(self) -> None:
        document = cw_grid_document.parse_document(
            {
                "rows": ["OX"],
                "themes": {},
                "clues": {"OX": {"clue": "Hay eater"}, "NO": {}, "AN": {"clue": None}},
            }
        )
        self.assertEqual(dict(document.clues), {"OX": "Hay eater", "NO": "", "AN": ""})

    def test_a_non_string_clue_is_refused_like_a_non_string_theme(self) -> None:
        with self.assertRaises(cw_emit.EmitError) as caught:
            cw_grid_document.parse_document(
                {"rows": ["OX"], "clues": {"OX": {"clue": 7}}}
            )
        self.assertIn("non-string clue", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
