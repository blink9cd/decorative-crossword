"""cw_paths: decides which output paths a run may write to.

Every subcommand that writes a file (`fill`'s `--out` and `--preview`, and the
`--out` render of `preview`, `shade` and `gaps`) hands its output flags and its
input flags to `refuse_unusable_outputs` before it searches anything, and before
it reads any input but the `--mask` picture `gaps` loads first. A refusal there
is exit 2, for two kinds of fault:

- **An output no file can be written at**: a directory, or a path whose
  directory does not exist. Left to the write, either would fail only once the
  rest of the run was spent: after `fill`'s search, after `gaps` printed its
  report, and after `fill` had written its grid beside a `--preview` that could
  not be written.
- **An output naming a file the run touches**: an input it reads, or the file
  another of its outputs writes. Left alone, the write would replace a bank, a
  grid or a word list at exit 0 or 1, and a `--preview` on `--out`'s path would
  replace the grid with its own picture.

**Every refusal here names every offender**, never the first. An output is
checked for a usable location first, and one without is refused for that alone:
calling a directory "the --bank file" as well would be a false sentence about
the operator's path.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import cw_config

#: A command line's path flags, as (flag, path) pairs; None is a flag not given.
FlagPaths = Sequence[tuple[str, Path | None]]


def same_file(path: Path, other: Path) -> bool:
    """Whether `path` and `other` name one file, however either is spelled.

    Where both exist the filesystem decides, through `os.path.samefile`: one
    device and inode is one file, whether it is reached through another case, a
    symlink, a hard link or `..`. Resolved strings alone are not enough, because
    `resolve()` canonicalizes links and `..` but never case, so on a
    case-insensitive filesystem `BANK.JSON` resolves to a different string that
    opens `bank.json` itself.

    Where either is missing there is no file identity to read, so the resolved
    spellings are compared. An output that does not exist yet cannot be an
    existing input; an input that does not exist is still named as that
    output's target, because this check runs before that input is read.
    """
    if path.exists() and other.exists():
        return os.path.samefile(path, other)
    return path.resolve() == other.resolve()


def _location_fault(flag: str, path: Path) -> str | None:
    """Why no file can be written at `path`, or None when one can.

    `is_dir` on the parent rather than `exists`: a parent that is a file is no
    directory either, and the sentence stays true of it.
    """
    if path.is_dir():
        return f"{flag} names a directory, {path}: give the path of a file to write"
    if not path.parent.is_dir():
        return f"{flag} {path} is in a directory that does not exist: {path.parent}"
    return None


def _clash_faults(
    flag: str, path: Path, inputs: FlagPaths, earlier: Sequence[tuple[str, Path]]
) -> list[str]:
    """Every input, and every earlier output, that the output `path` names.

    Two outputs exist only under `fill`, whose second is the picture of its
    first, which is what the second sentence says.
    """
    reads = [
        f"{flag} names the {name} file {other}: a run never writes over a file it reads"
        for name, other in inputs
        if other is not None and same_file(path, other)
    ]
    writes = [
        f"{flag} names the {name} file {other}: the grid and its picture need two files"
        for name, other in earlier
        if same_file(path, other)
    ]
    return reads + writes


def refuse_unusable_outputs(outputs: FlagPaths, inputs: FlagPaths) -> None:
    """Raise ConfigError naming every output this run may not write to.

    `outputs` are in the order the run writes them, so a later output that
    names an earlier one is refused under its own flag. `inputs` are every file
    the run reads, one pair per path of a repeatable flag.
    """
    faults: list[str] = []
    usable: list[tuple[str, Path]] = []
    for flag, path in outputs:
        if path is None:
            continue
        location = _location_fault(flag, path)
        if location is not None:
            faults.append(location)
            continue
        faults.extend(_clash_faults(flag, path, inputs, usable))
        usable.append((flag, path))
    if faults:
        raise cw_config.ConfigError("; ".join(faults))


def refuse_repeated_inputs(flag: str, paths: Sequence[Path]) -> None:
    """Raise ConfigError naming every file the repeatable input `flag` names twice.

    Used for `--bank`, whose files merge: a bank given twice is merged with
    itself, which adds nothing, and every record in it agrees with itself, so
    no later check would ever notice the slip. Compared by `same_file`, so a
    second spelling of one file is caught too, and before either is read.
    """
    faults = [
        f"{flag} names the same file twice, {first} and {later}: "
        "a file given twice adds nothing"
        for index, later in enumerate(paths)
        for first in paths[:index]
        if same_file(first, later)
    ]
    if faults:
        raise cw_config.ConfigError("; ".join(faults))
