# Changelog

Notable changes to this project, newest first.

## 0.1.3 - 2026-11-10

### Changed

- The license is now two files. `LICENSE` holds the GNU AGPL v3 text exactly as the Free
  Software Foundation publishes it, so GitHub and other tools recognize it. `NOTICE` holds
  the copyright line and the "or any later version" grant. The terms are unchanged:
  AGPL-3.0-or-later.

## 0.1.2 - 2026-11-02

### Changed

- Report lines, refusal messages, and `--help` text use a colon, a comma, a period, or
  parentheses where they used a spaced double hyphen, and `--help` drops its all-caps
  emphasis. No figure, exit code, or line order changed, but a script matching a report's
  exact sentences may need updating:
  `Worst rating in the grid: 3 -- 12 unrated answer(s), which count as 3.` now reads
  `Worst rating in the grid: 3 (12 unrated answer(s), which count as 3).`, and the two
  island lines read `Islands: none, since ...` and `Islands: none laid, since ...`.
- `--help` no longer prints `(default: False)` beside the on/off flags
  (`--absorb-entries`, `--exclude-grid-answers`, `--include-absorbing`, and
  `--empty-blocks`). Each is still off unless given.
- `pyproject.toml` declares a build backend, so `pip install '.[test]'` works from a
  clone. It installs the project's metadata and the Hypothesis pin the tests need; the
  tool still runs from the clone with the standard library alone.
- The bundled `stdio_utf8` library gains `spell_unsafe`, which spells each control
  character, direction mark, embedding, override, isolate, and line or paragraph separator
  in a string as its escape. This tool does not call it yet, and nothing it prints changes.

### Documentation

- The README's Requirements section is now an Install section that sets up a virtual
  environment, and the README says what the `# fuzz-target` and
  `# reliability: ignore[...]` comments in the source are for.
- `samples/README.md` quotes the `rated_grid` report as the tool prints it: the best of
  80 conforming grids, not 50.

## 0.1.1 - 2026-10-12

### Fixed

- `--help` for `preview`, `shade` and `gaps` now names both ways those commands refuse a
  grid file (exit 2): a grid wider or taller than 25 cells, and one whose theme label or
  summary holds a character a bank refuses. The commands always refused both; the help
  text left them out.

## 0.1.0 - 2026-09-30

- Initial release.
