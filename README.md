# decorative-crossword

An offline decorative crossword generator. It fills a grid of the size you ask for from a word
bank you curate, and draws the result as a self-contained SVG, which is the product. Every fill
also writes `grid_source.json`, the machine-readable grid the picture is drawn from, so a later
run can redraw it. The tool reads a finished grid back as well: to draw it, to find the hidden
words it can carry, or to ask what a letter in each of its blocked cells would demand of the bank.

Every answer the search may place is one somebody put in the bank on purpose. There is no
dictionary fallback and no word-frequency filter: a filter drops good words, and no filter admits
junk. The bank is curated and additive instead, and the one screen the tool offers,
`--excluded-terms`, names every answer it drops.

**The one rule the whole tool follows from.** Every maximal run of two or more letters, across or
down, must be a distinct answer from the bank; under `fill --source`, a run the source grid declares
for itself counts as a bank answer too. Two words cannot lie in adjacent parallel lines
unless every pair they create is itself an unused bank answer, so the tool cannot construct filler
and never emits any, and a denser grid is a demand on the bank, for longer answers, rather than on
search effort. A run of one cell is no entry and needs no answer, as in any printed crossword, but
a letter standing alone in both directions belongs to no entry at all: `fill` never lays one except
as an opt-in island (`--island-letters`), and the subcommands that read a grid warn about any
such letter that is not an island. The search may pass through a board that breaks the rule on
its way to a grid that keeps it, but no such board is ever accepted or written: whatever comes
back, conforming or best-effort, obeys the rule in full.

## Install

Needs Python 3.12 or newer. Install into a virtual
environment, because Homebrew and Debian Python refuse a
system-wide `pip install`:

```bash
python3 -m venv .venv
# shellcheck source=/dev/null # the activate script exists only once the line above has run
source .venv/bin/activate
pip install '.[test]'
```

The commands below assume the venv is active, so `python`
is the venv's interpreter.

On a system whose `python3` is older than 3.12, such as stock macOS, create the venv
with `python3.12 -m venv .venv` instead.

The tool itself uses only the standard library, and `dependencies` in `pyproject.toml` is
empty; the `test` extra installs Hypothesis, which only the tests need. It runs offline: it
opens no network connection, and the SVG it draws references no external font, image,
stylesheet or script.

## Quickstart

From the repository root:

```bash
python decorative_crossword.py fill --bank samples/small_square/bank.json --out grid_source.json --preview preview.svg --seed 11 --rows 7 --cols 7 --time-budget 0 --max-steps 50000
```

It prints a report, exits `0`, and writes `grid_source.json` and `preview.svg` into the current
directory. Both are byte for byte the committed `samples/small_square/grid_source.json` and
`samples/small_square/preview.svg`:

```bash
cmp grid_source.json samples/small_square/grid_source.json
cmp preview.svg samples/small_square/preview.svg
```

Open `preview.svg` in a browser; it needs no network.

## The four subcommands

### `fill`

Searches for a grid and writes it to `--out` as `grid_source.json`, and draws it to `--preview` as
an SVG when that is given. The search is a depth-first backtracking walk whose order `--seed`
fixes. It starts from an empty board, or with `--source` from a grid you already have: every
letter of that grid stays where it is, a half-written word a bank answer can finish is finished,
and the fill grows into its blocked cells. `--rows` and `--cols` state the size, at most 25 each,
and have no default, because any default would be a guess at what the grid's consumer wants; a
`--source` grid or a `--mask` picture supplies them when they are left off. Density is two bounds
in percent *blocked* cells: lower `--max-blocked` for a denser grid, raise `--min-blocked` for a
sparser one. The theme floor (`--min-themes`, `--min-entries-per-theme`) asks for that many themes
each carrying that many placed entries. `--feature` names an answer every accepted grid must hold,
and `ANSWER@ROW,COL,DIR` pins it to a cell. The search keeps the best conforming grid it finds
within `--look-ahead` nodes of the first one, most letters first. When the budget runs out before
any grid conforms, it writes the best grid it saw anyway, with a report naming each missed
constraint and what would clear it. A request no search could meet, such as a bank too
thin for the theme floor, is refused before the search starts rather than after the budget.
The full option reference, every default included:
`python decorative_crossword.py fill --help`.

### `preview`

Draws an existing `grid_source.json` (`--source`) as a self-contained SVG (`--out`). It runs no
search, so it takes no seed, no size and no density, and it works on a grid this tool never wrote:
a hand-authored one, or one already in use. `--feature` shades whole answers, found by their text
in the grid; it takes no position. `--cell` sets the cell edge, and `--empty-blocks`, which every
subcommand that draws accepts, draws each blocked cell as a hole so the grid's outline reads as a
shape. A letter in no entry that is not a corner island is named on stderr as a warning, and the
grid is drawn all the same. The full option reference:
`python decorative_crossword.py preview --help`.

### `shade`

Finds the hidden words a filled grid can carry: cells to shade whose letters, read in normal
reading order with blocks skipped, spell one more word. Exactly one of two modes is required.
`--words` ranks every word of a plain list that the grid can spell, best first. `--word` places one
word, prints its cells as 0-based `(row, column)` pairs and as paste-ready JSON, and with `--out`
draws the grid with those cells shaded. Each word is scored by how much its cells cluster, and low
is good: `0` is one letter per row, the way a printed crossword's shaded squares scatter. The cells
are chosen by a shortest path that minimizes that score, not by taking the first occurrence of each
letter, which bunches them inside one answer so the shading reads as a corrupted entry.
`--min-length` keeps out the short words almost any grid can spell, and `--exclude-grid-answers`
drops the words the grid already answers, naming each. The full option reference:
`python decorative_crossword.py shade --help`.

### `gaps`

Names the blocked cells a letter could still occupy, and what each would demand of the bank. It
writes nothing into any grid: a blocked cell becomes a letter only by an answer joining the bank
and `fill` running again. A letter between two runs does not make a short word of its neighbors, it
joins them, so each gap is reported with the full run it would create, the new cell written `?`,
and a cell that makes a run both ways must satisfy both with one letter. `--bank` (the JSON `fill`
takes) and `--words` (a plain list) are optional and repeatable, and union into one vocabulary;
given either, each gap is sorted into one you can fill already, with the letter and the answers
named, or one needing a new answer of a stated pattern. A gap whose letter would lengthen or weld
existing answers, retiring them, is counted and left out unless `--include-absorbing` asks for
it, and one whose letter would join no entry is counted and never listed. The list is grouped by
the pattern a gap needs, `--top` caps it, and `--out` draws the grid with a ring on each gap
listed. `fill` keeps the densest grid within `--look-ahead` nodes of the first one inside its
density window, so a new answer may change nothing on its own: the report names the
`--max-blocked` ceiling that makes the search reach for a gap. Re-run `fill` with it, as
`fill --source` on this grid, and every letter already there stays. The full option reference:
`python decorative_crossword.py gaps --help`.

## Determinism

`fill` is the only subcommand that reads a clock. Its default budget is wall-clock seconds
(`--time-budget`), and where a clock cuts a search off depends on how fast the machine ran, not
on the inputs: a slower or busier machine may keep a different grid, or none that conforms. With
`--time-budget 0` the clock is dropped and `--max-steps` bounds the search in nodes instead, so
the same bank, seed and options produce the same bytes on any machine. Both at zero is refused,
since that search could run forever. Every `fill` command in `samples/README.md` pins
`--time-budget 0 --max-steps 50000` for this reason. `preview`, `shade` and `gaps` run no
search and read no clock.

## Input files

### The word bank

```json
{
  "themes": {
    "people": {"label": "People", "summary": "Placeholder names, standing in for whoever the grid is for"},
    "sayings": {"label": "Sayings", "summary": "Things said out loud, written as more than one word"}
  },
  "entries": [
    {"answer": "JANE", "theme": "people", "clue": "Placeholder first name on a sample form"},
    {"answer": "NED", "theme": "people", "clue": "Short form of Edward", "rating": 1},
    {"answer": "HELLO THERE", "theme": "sayings", "clue": "Friendly greeting"},
    {"answer": "OX"}
  ]
}
```

- **`themes`** is required and may be empty. Each theme is a record with a `label` and a
  `summary`, both required and non-empty; a bare string in place of the record is refused. A bank
  with no themes can reach no positive theme floor, so run it with `--min-themes 0`.
- **`entries`** is a non-empty list. `answer` is required; `theme`, `clue` and `rating` are
  optional. A theme must be one the bank declares, or, when `--bank` is given more than once, one
  any of the banks declares. An answer repeated inside one bank is refused.
- **An answer** is capital letters `A`-`Z`, at least two of them once it closes up. It may be
  written the way it is said, `HELLO THERE`, `ATTA-BOY`, `JACK-O'-LANTERN`: words joined by a
  single space or hyphen, with an apostrophe inside a word or at either end of one, never two
  together. The grid holds only its letters, `HELLOTHERE`; `--feature`, `--prefer` and
  `--phrases` close up spaces, hyphens and apostrophes the same way, so either spelling names it.
  Its clue gains the word lengths as it is written, as `Friendly greeting (5,5)`. `HELLO THERE`
  and `HELLOTHERE` in one bank are one answer written twice, and are refused.
- **`rating`** is your own judgment of a word, a whole number from `1` to `5`. When `fill` chooses
  among grids it judges each by its worst-rated entry, never the average, and an unrated answer
  counts as `3`. A rating never removes an answer and is never written to the grid file.
- **Several banks.** `fill` and `gaps` take `--bank` more than once and merge the banks in the
  order given. The same answer or theme in two banks is kept once when its records agree, and
  refused, naming both files, when they differ; one file given twice is refused.

### The mask picture

`fill --mask` and `gaps --mask` read a plain-text picture of the grid, one line per row, that
forbids a letter in every cell it marks, so the fill comes out in the shape of whatever is left:

```text
# A heart, 8 rows by 11 columns.
XX..XXX..XX
X.........X
X.........X
X.........X
XX.......XX
XXX.....XXX
XXXX...XXXX
XXXXX.XXXXX
```

`.` is a cell the grid may use as it likes, `X` one that may never hold a letter, and a line whose
first character is `#` is an annotation rather than a row. Note the inversion: `.` means *free*
here and *blocked* in `grid_source.json`, because a picture is read as ink on paper. A mask only
ever forbids: inside the shape the fill is as freeform as without one, and nothing promises the
shape comes out full. The picture is exactly the size of the final grid, a `--source` grid grown
by `--rows` or `--cols` included; it supplies the size when `--rows` and `--cols` are left off,
and must agree with them when they are given. Under a mask, `fill` and `gaps` measure density over
the cells the picture leaves, and the report names that basis; the SVG caption, which a later
`preview` draws without the picture, gives the whole grid's. Nothing in the grid file or the SVG
marks a masked cell: the grid file records it as the blocked cell it is. `--mask` does not imply
`--empty-blocks`; give both to see the shape drawn.

What a mask refuses and what it merely declines follows authorship. Something you wrote is
refused, because silently dropping it would hand you a grid that is not the one you asked for.
Something the tool chose for itself is simply ineligible.

| The overlap with a masked cell | What happens |
| --- | --- |
| A `--feature` pin puts a letter there | Refused at exit `2`, naming the pin and the cell |
| A `--source` grid holds a letter there, under `fill` or `gaps` | Refused at exit `2`, naming the letter and the cell |
| An island `--island-letters` would lay there | Not laid; no refusal and no warning |
| `gaps` would report the cell as a gap | Not a gap: counted apart, on a line of its own |

The search checks every placement against the mask, so no answer it lays, a source entry grown
under `--absorb-entries` included, ever covers a masked cell.

### Word lists

`shade --words`, `gaps --words`, `--phrases` (on `fill` and `gaps`) and `fill --excluded-terms`
each read a plain list, one item per line. Blank lines and lines whose first non-blank character
is `#` are ignored, and case is folded. `--phrases` lists what two of the grid's entries may spell
together, which the report names and never scores; its spaces, hyphens and apostrophes close up,
so `atta boy` joins `ATTA` and `BOY`. `--excluded-terms` drops every bank entry whose answer or
clue holds a listed term as a whole word, case-insensitively, and names each one it drops.

### What each kind of input refuses

What each kind refuses differs, because each is used differently. Every refusal is exit `2`
and names the input:

- **A bank**: a theme key, label or summary, or a clue, holding a newline or any other C0 or C1
  control character, DEL, a lone surrogate, U+FFFE or U+FFFF, or the literal `</script` in any
  mix of case, is refused, naming the field and the character. **A grid file** holds its theme
  labels and summaries to the same screen, whichever subcommand reads it, and `fill --source`
  holds each run the grid declares for itself, clue included, to a bank's rules.
  A bidi control (U+061C, U+200E, U+200F, U+202A to U+202E, U+2066 to U+2069), a Unicode line or
  paragraph separator, a soft hyphen, the zero-width space, joiner and non-joiner, and accented
  letters are accepted. The grid file and the SVG keep a bidi control as written, and the report
  shows one escaped wherever it prints a label.
- **A word or phrase list** refuses no line. A line still holding such a character once it is
  read (a phrase list first closes up its whitespace, control whitespace included) is skipped,
  like any line with a character outside `A`-`Z` or shorter than two letters, and the report names
  it with its reason, each such character and each bidi control escaped, as `\x1b`. A list with
  no usable line at all is refused.
- **An excluded-terms list** refuses no character, since a term is only compared, and a message
  that quotes a term shows it escaped.
- **A mask**: any character in a picture row other than the two marks, trailing whitespace aside,
  is refused as unknown, naming its line and column; a lowercase `x` is refused too. A `#` comment
  line may hold anything. A picture is also refused when it holds no rows, has a blank line, has
  rows of different widths, or masks every cell. Line numbers count comment lines, as an editor
  does.

Then the limits every input meets, whatever it is:

- A grid is at most 25 x 25 on every route: `--rows` and `--cols`, a `--source` grid or the size
  it is grown to, a `--mask` picture, and any grid file `preview`, `shade` or `gaps` reads.
- An answer has at least two letters. One longer than the grid's longest line is never laid, and
  a bank none of whose answers fits the grid is stopped before the search starts, at exit `1`,
  with the report saying so.
- Every input must be a regular file of at most 32 MiB. A pipe, a device, a directory, or
  `/dev/stdin` fed by a pipe or a terminal is refused before any of it is read, and so is a file
  already past the cap; one that grows past it while it is read is refused too.
- Every input is read as strict UTF-8. A file that begins with a byte-order mark is refused: save
  it as UTF-8 without one. A line ends only at `\n`, `\r\n` or `\r`, so a line number in a refusal
  is the one an editor shows.
- A JSON object that writes one key twice is refused, naming the key and the object holding it:
  that is grammatical JSON, but Python's `json` module would keep whichever came last without a
  word. So is JSON nested more than 64 levels deep, or holding an integer longer than the
  interpreter's digit limit.
- A number option given `nan`, `inf` or a value too large to be finite is refused while the
  command line is parsed.
- A refusal quotes each value it read from a file as Python writes it, cut after 200 characters
  and followed by the whole quote's length, and every control character or bidi control in a
  refusal, a file name's and an argument's included, is shown escaped.

## Output files

**`grid_source.json`** is `{"rows": [...], "themes": {...}, "clues": {...}}`. Each row is a
string of capital letters with `.` for a blocked cell. `clues` has one record per entry in the
grid, keyed by its letters, holding its `clue`, empty when the bank gave none, and its `theme`
key when it has one. `themes` holds only the themes a placed entry carries, each with its `label`
and `summary`. Its keys are sorted and its layout fixed, so the same grid from the same bank is
always written as the same bytes, and it is what `preview`, `shade`, `gaps` and `fill --source`
read back.

**The SVG** (`fill --preview`, `preview --out`, `shade --out`, `gaps --out`) is self-contained: no
external reference of any kind, so it opens from a `file://` path on a machine with no network.
A themed entry carries a marker that is not a color as well as a tint, so the grouping survives a
monochrome print. The caption stamps what the grid itself says (its size, blocked percentage and
per-theme counts) on every render; the seed, the requested density and the theme floor are
stamped only when `fill` draws it, since the grid file records none of them.

An output is written whole or not at all, to a temporary file beside it and renamed into place.
Before anything is written, an output that names an input, however the path is spelled, or that
is a directory or sits in a directory that does not exist, is refused at exit `2`, as is `fill`'s
`--preview` naming its `--out`.

A grid this tool writes at exit `0` is a candidate, and the page that publishes it owns the rest.
It should enforce what this tool deliberately does not, such as numbering, clue coverage and
barred terms, and it escapes `grid_source.json` for wherever in the page it places it. The tool
keeps one hazard out on its own side: `</script` is refused in every theme field and clue a bank
gives it, in the theme labels and summaries of every grid file it reads, and in every entry
`fill --source` keeps from a grid file, so nothing it writes can end a page's inline data block
early. Every `<` in `grid_source.json` is also written as its JSON escape, a backslash followed by
`u003c`, which a reader parses back to the same `<`: so `<!--` followed by `<script` cannot reach
a page raw either.

## Exit codes

| Code | Meaning | Files | Output |
| --- | --- | --- | --- |
| `0` | The run succeeded | Every output asked for is written | The report on stdout; `preview` prints none |
| `1` | The run happened and did not succeed | Every output asked for is still written: `fill` writes its best-effort grid | The report on stdout, naming what was missed |
| `2` | The run could not happen | None | One diagnostic line on stderr |

What success means differs by subcommand:

- **`fill`**: `0` is a conforming grid. `1` is none within the budget, or a request that was
  well-formed but that this bank could never meet at this size, which is refused before the
  search and writes an empty board, or the `--source` grid it was given when it holds no
  half-written word.
- **`preview`**: `0` is the SVG drawn. There is no exit `1`: `preview` has no constraint to miss.
- **`shade`**: `0` is candidates found, or the `--word` placed; `1` is a grid that spells none of
  the listed words.
- **`gaps`**: `0` is a grid with at least one gap worth reporting; `1` is one with none.

Exit `2` covers an input that cannot be read or is refused, a contradictory configuration, a flag
naming something its input does not hold (a `--feature` the bank lacks, a `--word` the grid cannot
spell), and a refused output path. Its one line is prefixed with the tool's name, and, with the
one exception below, it leaves no file behind: every refusal that can be decided before a write
is decided before one, so only a write failing for a filesystem reason, such as a full disk,
comes after any output. When `fill --preview` writes its grid and the SVG write then fails, the
grid stays on disk, because `preview` can draw it again and nothing turns a picture back into a
grid. A malformed option prints the usage first, and running the tool with no subcommand prints
the usage and exits `2`.

Reports go to stdout, and diagnostics and the warning about a stray letter go to stderr, so a
script reading the report sees neither. Both streams are forced to UTF-8. stdout is strict, so
the report never prints text other than what the tool meant; stderr escapes a character it
cannot encode, so a diagnostic naming a path that is not UTF-8 is still printed, and the run
still exits `2`, rather than ending in a traceback.

## Samples

Each folder under `samples/` holds worked inputs and the outputs they produce, and
[samples/README.md](samples/README.md) gives the exact command for each. The tests regenerate
every output and compare it byte for byte.

| Sample | What it shows |
| --- | --- |
| `small_square` | A 7 x 7 baseline: only the options that have no default, plus the pinned budget. |
| `wide` | A 7 x 13 grid at a density that is not the default. |
| `large_square` | A 13 x 13 grid with a featured answer, and why a big grid needs a looser ceiling. |
| `name_grid` | A 7 x 9 name grid: two answers pinned at chosen cells, and a phrase list joining them. |
| `best_grid` | A 9 x 9 grid where `--prefer` breaks a tie and `--island-letters` lays corner letters. |
| `rated_grid` | A 6 x 8 grid where one rating in the bank decides between two tied grids. |
| `symmetric_grid` | An 8 x 8 grid where `--prefer-symmetry rotational` keeps the most balanced tied grid. |
| `partial_grid` | `fill --source` finishing an 11 x 7 grid it was handed, source letters drawn bold. |
| `grown_grid` | `fill --source` growing a 3 x 4 source into an 8 x 10 grid. |
| `two_banks` | Two `--bank` files merged in one 7 x 8 run. |
| `absorbed_grid` | `--absorb-entries` growing a source entry in place, `JANE` into `JANET`. |
| `phrase_grid` | Answers written as more than one word, `HELLO THERE` and `ATTA-BOY`, in a 10 x 11 grid. |
| `heart_mask` | A `--mask` picture shaping an 8 x 11 grid into a heart, drawn with `--empty-blocks`. |
| `hidden_word` | `shade` reading `large_square`'s grid: a ranked list, and one word drawn. |
| `gaps` | `gaps` reading `large_square`'s grid against its own bank. |
| `silhouette` | `preview --empty-blocks` drawing `large_square`'s grid as a free shape. |

`KNOWN_TRADEOFFS.md` records behavior that was seen, judged and deliberately kept: read it
before reporting one of those as a defect.

## Running the tests

From the repository root, in the venv [Install](#install) set up:

```bash
python test_decorative_crossword.py
```

`pip install '.[test]'` installed the Hypothesis pin `pyproject.toml` declares as the `test`
extra, and nothing at runtime imports it. `test_decorative_crossword.py` runs every suite under
`tests/`, the byte-for-byte sample comparisons included. The two libraries beside it carry their
own: `python property_strategies/test_property_strategies.py` and
`python stdio_utf8/test_stdio_utf8.py`.

Two kinds of comment in the source are read by checks run before each release, and nothing
here reads them. A `# fuzz-target` line marks a function that parses untrusted input, which
must have a Hypothesis property test beside it. A `# reliability: ignore[RLnnn]` comment is a
waiver for a reliability check, with its reason on the same line.

## License

AGPL-3.0-or-later; see `LICENSE`.
