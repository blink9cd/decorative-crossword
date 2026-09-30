"""cw_command_base: what every subcommand handler shares.

Each is shared because a second copy of it would be a way for two subcommands
to disagree about the same contract: the refusal type no other module owns, the
set of exceptions that mean *the run could not happen* and the one way to
report them, the one call any handler makes to the renderer, the one reader of
`--phrases`, which `fill` and `gaps` both take, and the one reader of a
`--source` grid, which every subcommand takes.

Its own module rather than the top of `cw_commands` because every handler
module needs these, and reaching into a sibling handler module's privates to
get them would make the refusal contract something two files could drift on.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

import cw_bank
import cw_config
import cw_emit
import cw_excluded_terms
import cw_grid
import cw_grid_document
import cw_island
import cw_mask
import cw_pairs
import cw_shade
import cw_source
import cw_svg
import cw_text


class UsageError(ValueError):
    """A refusal on the exit-2 line that no other module owns.

    Every case is about which FLAGS were supplied, or about a flag naming
    something the given input does not contain -- neither of which belongs to
    the bank, the config or the emitter, so none of them has an existing error
    type to borrow.
    """


#: Every exception whose meaning is "the run could not happen", which is exit
#: 2. Named once so every handler refuses exactly the same set, and
#: listed by type rather than collapsed into `ValueError`: every one IS a
#: ValueError subclass, and catching the base would swallow a genuine bug in
#: the search or the renderer and report it as an operator's mistake.
#: `cw_source.SourceError` is the `fill --source` grid no fill can start from.
#: `cw_mask.MaskError` is a `--mask` file that is not a picture of a grid.
REFUSALS = (
    cw_bank.BankError,
    cw_config.ConfigError,
    cw_emit.EmitError,
    cw_mask.MaskError,
    cw_shade.ShadeError,
    cw_source.SourceError,
    UsageError,
)


def refuse(tool: str, exc: Exception) -> int:
    """Report `exc` on stderr as `tool`'s own diagnostic; return exit 2.

    stderr, and no report: exit 2 has an error channel and nothing else,
    because there is no run to describe. The message is escaped by
    `cw_text.visible`, as the parser's own refusals are (`ArgumentParser`): a
    refusal names a file by its path as written, and a file's name can hold a
    character a terminal would obey. A value quoted with `cw_text.shown` is
    escaped already, so the escape changes only what a refusal names as given.
    """
    print(f"{tool}: {cw_text.visible(str(exc))}", file=sys.stderr)
    return 2


class ArgumentParser(argparse.ArgumentParser):
    """argparse's parser, with its error line escaped as `refuse` escapes one.

    argparse quotes an argument as it was typed in some of its refusals -- one
    it does not recognize, or an abbreviation matching more than one option --
    so its error line could hand the terminal a control character or a bidi
    control. A refusal that quotes with `repr` is escaped already.

    Every subcommand's parser is one too, because `add_subparsers` builds each
    of its parent's class. The name stays argparse's, so the entry point still
    reads as the construction of an `ArgumentParser` to a reader, or a tool,
    looking for where the command line is built.
    """

    def error(self, message: str) -> NoReturn:
        """Print the usage, then `prog: error:` and `message`, escaped.

        Exits 2, as argparse's own does, so it never returns.
        """
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {cw_text.visible(message)}\n")


def load_phrases(
    paths: Sequence[Path] | None, excluded_terms: Path | None = None
) -> cw_pairs.Phrases:
    """Every usable line of the `--phrases` lists, closed up, and those skipped.

    `None` is the flag not given, which is `cw_pairs.NO_PHRASES`. The lists
    union, and each is read by `cw_shade.load_word_list`, which raises
    `cw_shade.ShadeError` for a list that cannot be read at all.

    A list holding nothing usable is refused, for the reason `gaps` refuses
    such a `--words` list: a report saying no pair joined would describe a list
    the operator believes was read. The test runs BEFORE the barred terms
    screen the list, so a list they empty is not refused: every line of it is
    still named, under the reason it was skipped.

    `excluded_terms` is an `--excluded-terms` list, or `None`. Its terms travel
    closed up in the result, whether or not any phrase was given, because the
    warning about barred joins reads them; `cw_pairs` says why a line that is
    a term is skipped rather than joined against.

    The words are gathered in a set and handed back frozen, for membership only.
    """
    barred = (
        frozenset()
        if excluded_terms is None
        else cw_pairs.closed_up_terms(
            cw_excluded_terms.load_excluded_terms(excluded_terms)
        )
    )
    words: set[str] = set()
    skipped: list[tuple[str, str]] = []
    for path in paths or ():
        listed, list_skipped = cw_shade.load_word_list(path, close_up=True)
        if not listed:
            raise UsageError(
                f"--phrases file {path} holds no usable phrases: every line was "
                "blank, a comment, or not letters A-Z once its spaces, hyphens "
                "and apostrophes close up"
            )
        kept, dropped = cw_pairs.screen_phrases(listed, barred)
        words.update(kept)
        skipped.extend((*list_skipped, *dropped))
    return cw_pairs.Phrases(frozenset(words), tuple(skipped), barred)


def load_source(tool: str, path: Path) -> cw_grid_document.GridDocument:
    """Read the `--source` grid at `path`, warning on stderr about each stray letter.

    Raises `cw_emit.EmitError` exactly as `cw_grid_document.load_document` does, and for
    a grid larger than `cw_grid.MAX_SIDE` either way -- here, the one reader of
    a grid file, and before the stray scan, whose work grows with the grid.

    The one reader `preview`, `shade`, `gaps` and `fill` share, because each
    takes a grid this tool may never have written, and a hand edit can leave a
    letter in no entry. An island is such a letter on purpose and says nothing;
    any other is named, one line each, as
    `<tool>: warning: cell <row>,<col> (<letter>) belongs to no entry: <reason>`,
    its row and column counted from 0.

    WARNED, never refused. A consumer's acceptance check is the gate, not this
    tool; `preview` is wanted most on a broken grid; and `gaps` is the
    subcommand that finds a letter to join a stray into a word. So the warning
    changes nothing else about the run. `fill` judges a stray separately, at
    acceptance: a grid it accepts has none left.
    """
    document = cw_grid_document.load_document(path)
    height, width = len(document.rows), len(document.rows[0])
    too_big = cw_grid.oversize(height, width)
    if too_big is not None:
        raise cw_emit.EmitError(
            f"grid file {path}: the grid is {height}x{width}, {too_big}"
        )
    for row, col, letter, reason in cw_island.stray_letters(document.rows):
        print(
            f"{tool}: warning: cell {row},{col} ({letter}) belongs to no entry: "
            f"{reason}",
            file=sys.stderr,
        )
    return document


def render(
    document: cw_grid_document.GridDocument,
    features: tuple[str, ...],
    cell: int,
    settings: Mapping[str, str] | None,
    hidden: cw_svg.HiddenShading | None,
    *,
    gaps: tuple[tuple[int, int], ...] = (),
    fixed: tuple[tuple[int, int], ...] = (),
    empty_blocks: bool = False,
) -> str:
    """Draw one grid. The ONLY place any handler reaches the renderer.

    Every caller hands in a `GridDocument`, so `fill --preview`, a standalone
    `preview` of the file that fill just wrote, and every other caller render
    the same value derived the same way; they differ only in the render options
    each passes.

    `empty_blocks` is the one keyword option every caller passes, because it is
    a property of the drawing rather than of what that caller found.
    """
    return cw_svg.render_svg(
        cw_svg.RenderRequest(
            rows=document.rows,
            # Narrowed to labels here rather than teaching cw_svg about
            # ThemeInfo: the preview legend draws a theme's NAME and never its
            # summary, so carrying the record into the renderer would add a
            # dependency edge from the SVG layer to the bank layer for a field
            # it does not use.
            themes={key: info.label for key, info in document.themes.items()},
            entry_themes=document.entry_themes,
            features=features,
            cell=cell,
            settings=settings,
            hidden=hidden,
            gaps=gaps,
            fixed=fixed,
            empty_blocks=empty_blocks,
        )
    )
