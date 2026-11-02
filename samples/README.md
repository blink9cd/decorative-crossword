# Samples: grids, a hidden word and a gap report, all regenerable by hand

Every `grid_source.json` and `.svg` in this folder is an output the tool produced, by the
command printed under its heading, from the inputs that command names. None was hand-edited, and
none may be: `tests/test_samples.py` and `tests/test_samples_read.py` re-run every command into a
temporary folder and compare the result byte for byte, so a sample that drifts from the tool
fails the build rather than sitting here quietly lying about what the tool does.

Run the commands from this project's root. Each writes its files into its own sample folder
and prints a report to stdout.

## What each sample is for

The `fill` samples are chosen so the set demonstrates `fill`'s options rather than exercising one
path several times: a square grid at every default, a grid whose two dimensions differ *and* whose
density is not the default, a large grid with a featured answer, a name grid whose answers are
pinned at chosen cells, and the same pins on a larger grid choosing among grids with `--prefer` and
laying island letters, a bank whose ratings choose between grids that tie on everything else, the
same pins again kept by `--prefer-symmetry` for the most balanced of their tied grids, and a
partial grid that `--source` finishes without moving a letter of it, half-written word included,
a small source `--rows` and `--cols` grow into a larger grid, a small bank of names a second
`--bank` merges with a main bank, a source entry `--absorb-entries` grows in place, a bank
whose answers are written as more than one word, and a `--mask` picture that forbids a letter in
half the grid so the fill comes out in the shape of a heart. No two
share a size, and no two
land on the same blocked percentage. Note that `heart_mask`'s percentage in the *report* is
over the cells its picture leaves, while the percentage this set keeps apart is the whole grid's. The `shade`, `gaps` and `silhouette` samples each read
`large_square`'s grid rather than carrying one of their own, and only the `fill` samples owe
that shape-and-density rule, which is why a drawing option is shown by reading a grid rather than
by searching for another one.

## Why every command below pins `--time-budget 0 --max-steps 50000`

Because a sample is only worth pasting if you get the committed bytes back, and on the CLI
defaults you would not. The default budget is a wall-clock limit with no node cap (`fill --help`
prints both), so the search stops when *your machine* runs out of time rather than when it runs
out of moves: `wide` and `large_square` each take about four seconds here, so a machine roughly
seven times busier returns a different (and non-conforming) grid. `--time-budget 0` drops the
clock, and `--max-steps` then supplies the bound (the tool refuses both at zero). What comes back
is a function of the bank and the seed alone, on any machine, which is the whole promise of
comparing your output with what is committed.

The cap is far above what any case needs (the largest spends about ten thousand nodes) because
it is there to stop a runaway, not to catch drift. Drift is caught by the comparison itself.
These commands are duplicated in `tests/test_samples.py`. Nothing compares the two copies, so
change one and change the other.

### `small_square`: 7 x 7, every optional at its default

The baseline: apart from the pinned budget above, the only options given are the ones that have
no default. It is the one to read first, and the one to copy when writing a bank of your own.

```bash
python decorative_crossword.py fill --bank samples/small_square/bank.json --out samples/small_square/grid_source.json --preview samples/small_square/preview.svg --seed 11 --rows 7 --cols 7 --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. Nine answers, nine entries, every one of them placed; the report's
*Unplaced answers* line reads `none`. Achieved density is 40.8% blocked, inside the default window.

### `wide`: 7 x 13, and a density that is not the default

The one that matters most. Two different dimensions and a non-default density in the same
sample is what proves neither `--rows`/`--cols` is a single size parameter wearing two names, and
that `--min-blocked` / `--max-blocked` are really consulted.

```bash
python decorative_crossword.py fill --bank samples/wide/bank.json --out samples/wide/grid_source.json --preview samples/wide/preview.svg --seed 23 --rows 7 --cols 13 --min-blocked 40 --max-blocked 60 --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. The grid is 7 rows by 13 columns and 52.7% blocked, outside the
default window at both ends of the request, which is the point of giving the two bounds.

### `large_square`: 13 x 13, with a featured answer

`--feature LEARNING` makes one answer a hard constraint: the search seeds with it, and a run
that cannot place it fails rather than quietly returning a grid without it. The render shades its
cells and the report names them in 0-based `(row, column)` coordinates.

```bash
python decorative_crossword.py fill --bank samples/large_square/bank.json --out samples/large_square/grid_source.json --preview samples/large_square/preview.svg --seed 5 --rows 13 --cols 13 --max-blocked 60 --feature LEARNING --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. Its bank is deliberately richer than the grid needs, so this is the
sample whose report exercises the *Unplaced answers* and *Shortage by word length* blocks: the
two an operator reads when a run of their own comes back at exit 1.

The 13-column width is deliberate: this sample proves the tool fills a grid exactly that wide.

### `name_grid`: 7 x 9, two answers pinned at chosen cells

A decorative name grid: `JANE` across the top-left corner and `DOE` hanging down from a cell
chosen for it, with the rest of the fill grown around them. Each `--feature ANSWER@ROW,COL,DIR`
pins an answer's first letter to a 0-based cell, and the search starts from the board those pins
form rather than from a centered opening word. The names are placeholders, as every name in a
sample should be.

```bash
python decorative_crossword.py fill --bank samples/name_grid/bank.json --out samples/name_grid/grid_source.json --preview samples/name_grid/preview.svg --seed 1 --rows 7 --cols 9 --max-blocked 55 --min-entries-per-theme 2 --feature JANE@0,0,across --feature DOE@1,4,down --phrases samples/name_grid/phrases.txt --look-ahead 450 --time-budget 0 --max-steps 50000
```

Expected exit code: **0**, and the report reads both pins back out of the grid, exactly where the
command put them:

```text
Featured answer JANE: across, (0, 0) to (0, 3).
  Shaded cells, 0-based (row, column): (0, 0), (0, 1), (0, 2), (0, 3)
Featured answer DOE: down, (1, 4) to (3, 4).
  Shaded cells, 0-based (row, column): (1, 4), (2, 4), (3, 4)
```

Its phrase list, `phrases.txt`, holds one line, `Jane Doe`, and the report names the two pins
as the pair it spells. The grid and the picture are the bytes a run without the list produces,
because a pair is reported and never scored:

```text
Answer pairs that join into a bank answer or a --phrases entry, never scored (0-based row, column):
  JANE, across from (0, 0) + DOE, down from (1, 4) = JANEDOE
```

The grid is 42.9% blocked, with fourteen entries:

```text
JANE.....
..E.D..P.
..S.ONION
NUT.E..N.
O..T.SODA
ROSE....N
AN.A.OVEN
```

Two things in it are the point of the sample. **Neither pin moved:** `DOE` starts at `(1, 4)`,
diagonally below `JANE`'s last letter, and the search grew `NEST` down from `JANE`'s `N` and
`ONION` across `DOE`'s `O` rather than shifting either name somewhere easier. And the bank was
written for the pins. A name is usually short, and a short answer seldom wins a place on its
own against a large bank (which is why it is pinned rather than merely added), but a pin only
fixes where the name goes; a bank with plenty of words crossing its letters is what lets the
fill grow around it. Built that way, a pinned search is one of the cheapest this tool runs,
because every letter already on the board is somewhere the next word can cross.

It is also the sample the look-ahead changed. The first grid the search reached here held 30
letters; `fill` kept walking past it and kept a denser one with 36, and the report says so in the
line *Chosen as the best of 70 conforming grid(s)*. Its window is 450 nodes rather than the
default: the nodes past 450 reach a 37-letter grid at 41.3% blocked, which rounds to the same
whole percentage as `small_square`'s 40.8%, and no two samples here may share one. The pins held
through every one of those grids, which is the other half of what a pin promises.

### `best_grid`: 9 x 9, the best of many grids, with island letters

The same bank and the same two pins as `name_grid`, on a larger grid, with the two flags that decide
what `fill` keeps. `fill` keeps looking past its first conforming grid and keeps the best, and
here more than one fill ties on letters, so the preference decides: `--prefer JOE`. Then
`--island-letters AIX` lays a lone letter in each blocked cell that touches the grid's letters only
at a corner.

```bash
python decorative_crossword.py fill --bank samples/best_grid/bank.json --out samples/best_grid/grid_source.json --preview samples/best_grid/preview.svg --seed 1 --rows 9 --cols 9 --max-blocked 55 --min-entries-per-theme 2 --feature JANE@0,0,across --feature DOE@1,4,down --prefer JOE --island-letters AIX --time-budget 0 --max-steps 50000
```

Expected exit code: **0**, and three lines of the report are the point of the sample:

```text
Chosen as the best of 70 conforming grid(s) found within 500 node(s) of the first: most letters, then --prefer answers, then themed entries.
Preferred answers placed: JOE (1 of 1).
Islands (lone letters in no entry, laid after the grid was chosen): A at (0, 6), A at (0, 8).
```

```text
JANE..A.A
O.E.DO.P.
E.S.ONION
..T.E..N.
SO...SODA
A.ROSE...
L..V.ENID
TREE.D..A
...NO.PAN
```

**The preference decided.** Run the same command without `--prefer JOE` and the first column reads
`JAR` instead of `JOE`. The two grids tie on everything the tool measures: 47 letters each, and one
themed entry each (`JAR` for the kitchen, `JOE` for people), so without a preference the tie keeps
the grid the search happened to find first. With it, `JOE` hangs from the pinned `JANE`'s `J`
beside `DOE`. Which of the two reads better is a judgment, and the flag is how you state it.
`tests/test_samples_content.py` re-runs the command without the flag to prove the grid really changes.

**The two `A`s in the top row are islands.** Each of those blocked cells has no letter beside it and
a letter at a corner (`O` and `P` in the row below), so each takes the first of `AIX` its corners
do not already show. They belong to no entry, and are islands by rule: a lone letter from the
island set, `A`, `I`, `X`, `U` or `Y`, at the corner of an entry's letter. `preview`, `shade` and
`gaps` read them the same way, so none of the three warns about a stray on this grid.

### `rated_grid`: 6 x 8, one rating choosing between two tied grids

The same bank and the same two pins as `name_grid`, on a smaller grid, with exactly one change to
the bank: `NED` carries `"rating": 1`. Nothing else is rated, so every other answer counts as the
middle of the scale, `3`, and the rating is the only thing that can separate two grids the search
finds equally good. The rating is a placeholder for the demonstration, not a verdict on the word.

```bash
python decorative_crossword.py fill --bank samples/rated_grid/bank.json --out samples/rated_grid/grid_source.json --preview samples/rated_grid/preview.svg --seed 1 --rows 6 --cols 8 --max-blocked 55 --min-entries-per-theme 2 --feature JANE@0,0,across --feature DOE@1,4,down --time-budget 0 --max-steps 50000
```

Expected exit code: **0**, and two lines of the report are the point of the sample:

```text
Chosen as the best of 80 conforming grid(s) found within 500 node(s) of the first: most letters, then --prefer answers, then worst rating, then themed entries.
Worst rating in the grid: 3 (12 unrated answer(s), which count as 3).
```

```text
JANE.PAN
....DO.O
.ONION.R
.V..EDNA
LEAF..U.
.N..DATE
```

**The rating decided.** Remove the one rating and run the same command, and the bottom-right corner
reads `NED` down and `SODA` across in place of `NUT` and `DATE`:

```text
LEAF..E.
.N..SODA
```

The two grids tie on everything else the tool measures: 31 filled cells each, no `--prefer`, and
eleven themed entries each, so without the rating the tie keeps the grid the search found first.
With it, that grid's worst entry is `NED` at `1` while the other grid's is `3`, and the other grid
wins. The chosen grid holds no rated answer at all, which is why its report line counts twelve
unrated answers rather than naming one: a rating can decide in favor of a grid it never appears in.
`tests/test_samples_content.py` re-runs the command without the rating to prove the grid really changes.

### `symmetric_grid`: 8 x 8, a symmetry preference choosing among tied grids

The same bank and the same two pins as `name_grid`, on an 8 x 8 grid, with
`--prefer-symmetry rotational`: of the grids the search finds, it keeps the one whose pattern of
letters and blocks best survives a half turn about the grid's center.

```bash
python decorative_crossword.py fill --bank samples/symmetric_grid/bank.json --out samples/symmetric_grid/grid_source.json --preview samples/symmetric_grid/preview.svg --seed 2 --rows 8 --cols 8 --max-blocked 55 --min-entries-per-theme 2 --feature JANE@0,0,across --feature DOE@1,4,down --prefer-symmetry rotational --time-budget 0 --max-steps 50000
```

Expected exit code: **0**, and two lines of the report are the point of the sample:

```text
Chosen as the best of 182 conforming grid(s) found within 500 node(s) of the first: most letters, then --prefer answers, then rotational symmetry, then themed entries.
Rotational symmetry: 19 of 32 cell pairs match.
```

```text
JANE.P..
....DATE
.ONION.D
..E.E..N
ROSE.TEA
E.T.OR..
E..I.E..
DEAN.EGG
```

**The preference decided.** Run the same command without `--prefer-symmetry` and the bottom-right
corner reads `SEED` across and `DO` down in place of `OR`, `IN` and `EGG`:

```text
E.T..R..
E...SEED
DEAN.E.O
```

The two grids tie on every other level: 39 filled cells each, no `--prefer`, no rated answer, and
thirteen themed entries each, so without the flag the tie keeps the grid the search found first.
With it, 19 of the 32 rotated cell pairs match against 13, and the corner opposite the pinned
`JANE` fills to answer it. The search compares the same 182 grids either way: the flag changes
which one is kept, never the walk that found them. `tests/test_samples_content.py` re-runs the
command without the flag to prove the grid really changes.

### `partial_grid`: 11 x 7, finishing a grid you already have

`--source` hands `fill` a grid to start from instead of an empty board;
`python decorative_crossword.py fill --help` states the rules under `--source`. `source.json` is in
the shape `fill` writes and holds four things: `TEAPOT`, an entry the bank holds; `PUDDLE`, an
entry the bank does not hold, declared in the source's own `clues` map; `MIS` down column 0, a
half-written word that neither the bank nor that map holds; and a lone `S` at `(6, 4)` that belongs
to no entry. The grid's size is the source's, so the command gives no `--rows` or `--cols`.

```bash
python decorative_crossword.py fill --bank samples/partial_grid/bank.json --source samples/partial_grid/source.json --out samples/partial_grid/grid_source.json --preview samples/partial_grid/preview.svg --seed 3 --max-blocked 55 --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. Reading the source warns about the stray on stderr:

```text
decorative_crossword: warning: cell 6,4 (S) belongs to no entry: S is not an island letter (A, I, X, U, Y)
```

Three lines of the report say what the run started from, what it kept and what it finished:

```text
From --source: 16 fixed letter(s) in 2 entry(s), 1 partial run(s), 1 lone letter(s).
Kept from --source, not in the bank (1): PUDDLE.
Completed from --source (1): MIS as MIST down at (4, 0).
```

The grid is 45.5% blocked:

```text
TO.....
.V.S.S.
TEAPOT.
.N.O.O.
M.SO.R.
I.ON.M.
S.I.S.S
TULIP.L
....A.E
.PUDDLE
....E.T
```

**Nothing of the source moved.** `TEAPOT` still runs across row 2 and `PUDDLE` across row 9, and
the fill grew around them: `OVEN`, `SPOON` and `STORM` cross `TEAPOT`, and `SPADE` and `SLEET`
cross `PUDDLE`.

**The half-written word was finished.** `MIS` is no bank answer and the source does not declare it,
but the bank's `MIST` can be laid over it, so the fill had to lay it: a placement along a partial
run is tried before any other, and `MIST` now runs down column 0 into `TULIP`. Had nothing finished
it, the run would have ended at exit `1` with an empty board, because a grid still holding `MIS`
breaks the one rule.

**The stray was covered.** The lone `S` is now the first letter of `SPADE`, which runs down from
`(6, 4)` through `PUDDLE`'s second `D`. `fill` accepts no grid in which a stray is still lone, so a
fill that left it alone would have come back a near miss at exit `1` rather than this grid.

**`PUDDLE` was kept.** No bank answer supplies it, so it keeps the source's clue and its `weather`
theme, and it counts toward that theme's floor: the report's `Weather: 4 placed` is `MIST`, `STORM`,
`SLEET` and `PUDDLE`. The headline, *Placed 12 of 34 bank entries*, does not count it, because that
line describes the bank file. `tests/test_samples_source.py` checks that every source letter sits unchanged
in the grid, that the stray is covered, that `MIS` is finished, and that `PUDDLE` carries the
source's record.

**The source's letters are bold in `preview.svg`.** The sixteen letters `source.json` held
(`TEAPOT`, `MIS`, the `S` and `PUDDLE`) are drawn bold, every letter the fill added is regular, and the
caption's second line says what the weight means:

```text
Fixed from --source: 16 letter(s), in bold
```

A `preview` of `grid_source.json` draws every letter regular, because the grid file does not
record which letters were given.

### `grown_grid`: 8 x 10, a small source grown into a larger grid

`--rows` and `--cols` beside `--source` grow the grid a source is placed on;
`python decorative_crossword.py fill --help` states the rules under `--rows`, `--cols` and
`--source`. `source.json` is a 3 x 4 corner someone already started: `JANE` across the top and
`JOE` down the left, sharing the `J`. The command asks for an 8 x 10 grid around it, pins `DOE` to
that grid's bottom-right corner, and gives the run its own density window, 35-50% blocked.

```bash
python decorative_crossword.py fill --bank samples/grown_grid/bank.json --source samples/grown_grid/source.json --out samples/grown_grid/grid_source.json --preview samples/grown_grid/preview.svg --seed 4 --rows 8 --cols 10 --min-blocked 35 --max-blocked 50 --feature DOE@7,7,across --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. The source block says where the source went:

```text
From --source: 6 fixed letter(s) in 2 entry(s), 0 lone letter(s).
Grown from --source: its 3x4 grid sits at (0, 0) of this 8x10 grid.
```

The grid is 37.5% blocked:

```text
JANE.SEED.
O.E..A..E.
E.SOIL.PAN
..T..TO.N.
.O..E..P.D
IVY.D.SODA
.E.ONION.T
.NORA..DOE
```

**The source did not move.** `JANE` still runs across from `(0, 0)` and `JOE` down from it, so every
position in `source.json` names the same cell here and nothing had to be translated. The fill grew
right and down from them: `NEST` crosses `JANE`, and `SOIL` crosses `NEST`. A source meant to grow up
or to the left is given blocked rows or columns on that side first.

**The pin lies in cells only the grown grid has.** `DOE@7,7,across` names row 7, columns 7 to 9,
which a 3 x 4 source does not have: `--feature` takes the grown grid's coordinates, which for every
source cell are the source's own. The report places it there:

```text
Featured answer DOE: across, (7, 7) to (7, 9).
```

**The source's letters are bold in `preview.svg`**: the six letters of `JANE` and `JOE`, with the
caption line `Fixed from --source: 6 letter(s), in bold`.

**The seed was chosen with a consumer's two-letter limit in mind.** Seed 1 conforms here too, but
its grid holds seven two-letter entries, and a consumer that caps them by width holds a grown grid
to a different limit than its source. `--max-two-letter` states such a cap to `fill` directly.
`tests/test_samples_source.py` checks that every source letter sits unchanged and that the pin
lies outside the source.

### `two_banks`: 7 x 8, a names bank merged with a main bank

`--bank` repeats; `python decorative_crossword.py fill --help` states how several banks merge.
`bank.json` is `name_grid`'s bank without its two placeholder names, and `names.json` holds only
those two, `JANE` and `DOE`: the shape of a bank every puzzle shares beside a small bank of one
grid's names. `names.json` declares no theme of its own: both its answers use `people`, which only
`bank.json` declares.

```bash
python decorative_crossword.py fill --bank samples/two_banks/bank.json --bank samples/two_banks/names.json --out samples/two_banks/grid_source.json --preview samples/two_banks/preview.svg --seed 2 --rows 7 --cols 8 --feature JANE --feature DOE --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. The headline counts the merged bank, and the line under it counts each
file, in the order the flags gave them:

```text
Placed 15 of 51 bank entries.
Merged 2 bank files, in the order given: samples/two_banks/bank.json (49 entries), samples/two_banks/names.json (2 entries).
```

The grid is 35.7% blocked. `JANE` runs down and `DOE` across, sharing `JANE`'s `E`, and every other
entry comes from `bank.json`:

```text
POT.SODA
O..J..E.
NORA..AS
D.ONION.
.DOE.V..
OAT.REED
.N...N.O
```

**Neither bank runs this command alone.** Without `names.json` both features name answers the bank
does not hold; without `bank.json`, `names.json` names a theme nothing declares. Each is exit `2`
before any search. `tests/test_samples_content.py` checks that both names are entries of the grid, and that
each bank alone is refused.

### `absorbed_grid`: 3 x 5, a source entry grown in place

`--absorb-entries` beside `--source` lets a source entry the bank holds grow into a longer bank
answer; `python decorative_crossword.py fill --help` states the rules under `--absorb-entries`.
`source.json` is a 3 x 5 corner someone already started: `JANE` across the top and `JOE` down the
left, sharing the `J`. The bank is `grown_grid`'s with one answer added, `JANET`, which lies along
all of `JANE`.

```bash
python decorative_crossword.py fill --bank samples/absorbed_grid/bank.json --source samples/absorbed_grid/source.json --out samples/absorbed_grid/grid_source.json --preview samples/absorbed_grid/preview.svg --seed 1 --min-blocked 20 --max-blocked 50 --min-themes 1 --min-entries-per-theme 2 --absorb-entries --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. The report names the entry the grid grew:

```text
From --source: 6 fixed letter(s) in 2 entry(s), 0 lone letter(s).
Absorbed from --source (1): JANE into JANET across at (0, 0).
```

The grid is 20.0% blocked:

```text
JANET
ON..O
ENID.
```

**`JANE` grew; nothing moved.** Its four letters sit where the source put them, and the `T` beside
them makes the entry `JANET`, which `grid_source.json` writes with the bank's clue. `JOE` still runs
down from the `J`, and the fill crossed both: `ON` and `ENID` across, `TO` down from the new `T`.

**Without the flag, the same command keeps `JANE`.** Drop `--absorb-entries` and every source entry
is held as its exact run, as *Starting from a partial grid* describes, and the fill returns one
letter fewer:

```text
JANE.
O.E.I
E.DAN
```

**The chosen-grid line names the new level last**, because keeping an entry only breaks a tie:

```text
Chosen as the best of 57 conforming grid(s) found within 500 node(s) of the first: most letters, then --prefer answers, then themed entries, then fewest absorbed --source entries.
```

**The source's letters are bold in `preview.svg`**: the six letters of `JANE` and `JOE`, with the
`T` the fill added drawn regular. `tests/test_samples_source.py` checks that every source letter sits
unchanged and that `JANE` lies inside a longer bank answer.

### `phrase_grid`: 10 x 11, answers written as more than one word

A bank answer may be written the way it is said; `python decorative_crossword.py fill --help`
states how such an answer is laid and clued. The bank is `name_grid`'s plus a `sayings` theme
holding an answer of each shape the bank accepts beyond plain letters: `HELLO THERE` (a space),
`ATTA-BOY` (a hyphen), `O'CLOCK` (an apostrophe) and `ROCK 'N' ROLL` (a space beside apostrophes),
plus `NO-ONE`, a second hyphen and the one answer left unclued. The command features the first two
as written, spaces and hyphens included.

```bash
python decorative_crossword.py fill --bank samples/phrase_grid/bank.json --out samples/phrase_grid/grid_source.json --preview samples/phrase_grid/preview.svg --seed 3 --rows 10 --cols 11 --max-blocked 60 --feature "HELLO THERE" --feature ATTA-BOY --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. The report names each placed answer the bank spells otherwise, beside
the enumeration its clue now ends with:

```text
Written forms, as the bank spells them (the enumeration ends a clued answer's clue):
  NOONE - NO-ONE (2-3)
  OCLOCK - O'CLOCK
  ATTABOY - ATTA-BOY (4-3)
  ROCKNROLL - ROCK 'N' ROLL (4,1,4)
  HELLOTHERE - HELLO THERE (5,5)
```

The grid is 47.3% blocked, and every answer lies in it by its letters alone:

```text
NEST.H.A..J
.NOONE.SODA
.I...L..A.N
.D.OCLOCK.E
.....O.....
.O.ATTABOY.
ANN..H.....
.I...E..EGG
ROCKNROLL..
.N...E..M..
```

**Only the clue shows the words.** `grid_source.json` keys each answer by its letters and writes
`Friendly greeting (5,5)`, `Well done (4-3)` and `Music of the fifties (4,1,4)`.
`O'CLOCK` is one word, so `On the hour` gains nothing, and `NO-ONE` has no clue to add `(2-3)` to.
`--max-blocked 60` is here for the reason `large_square` loosens it: at the default ceiling the same
command returns this grid at exit `1`, and the report names the ceiling as the knob.
`tests/test_samples_content.py` checks that every saying is an entry of the grid and that each clue
ends as above.

### `heart_mask`: 8 x 11, a shape file forbidding a letter in 41 cells

The only sample whose grid is a shape. `shape.txt` is a picture of the grid, one line per row,
and every `X` in it is a cell no letter may ever occupy:

```text
# A heart, 8 rows by 11 columns. Every X is a cell that may never hold a
# letter, so the shape is what the fill writes in the cells left over.
XX..XXX..XX
X.........X
X.........X
X.........X
XX.......XX
XXX.....XXX
XXXX...XXXX
XXXXX.XXXXX
```

```bash
python decorative_crossword.py fill --bank samples/heart_mask/bank.json --out samples/heart_mask/grid_source.json --preview samples/heart_mask/preview.svg --mask samples/heart_mask/shape.txt --seed 5 --min-blocked 20 --max-blocked 50 --min-entries-per-theme 2 --feature PROMISE@1,5,down --empty-blocks --time-budget 0 --max-steps 50000
```

Expected exit code: **0**. Achieved density is 46.8% blocked, and that figure is over 47 cells
rather than 88, which is the part to read carefully:

```text
From --mask samples/heart_mask/shape.txt: 41 of 88 cells may never hold a letter.
Grid 8x11: 25 filled cells, 46.8% blocked of 47 unmasked cells (requested 20.0-50.0%).
```

**The one thing to check by hand is a negative**: not one of those 41 cells holds a letter. Lay the
grid over the picture above and every `X` lines up with a `.`:

```text
...R...R...
.TIE.P.ODE.
...G.R.S...
...ADORE...
...R.M.....
...D.INK...
.....S.....
.....E.....
```

**`--feature PROMISE@1,5,down` is what draws the point.** Column 5 is the one column free the whole
way down the heart, so a seven-letter answer pinned there reaches the bottom cell; without it the
search fills the lobes and leaves the tip empty, and the silhouette stops reading as a heart. A pin
into a masked cell is refused instead.

**`--empty-blocks` is given, and is not implied.** This is the one `fill` sample that draws its
blocks as holes, because it is the one whose point is the outline: with them inked the picture is a
rectangle with a heart inside it rather than a heart. `--mask` deliberately does not turn it on, so
adding a mask to a command line never silently repaints every block.

### `hidden_word`: `shade` reading the grid `large_square` produced

The one that shows the third subcommand, and the first sample whose input is another sample's
output: it reads `large_square/grid_source.json` rather than carrying a copy of that grid,
because the demonstration is the whole chain and a second copy would be a second thing to keep
in step with the tool. **Run `large_square` above first.**

Two commands. The first ranks a word list:

```bash
python decorative_crossword.py shade --source samples/large_square/grid_source.json --words samples/hidden_word/words.txt --exclude-grid-answers
```

Expected exit code: **0**, and this report:

```text
Grid 13x13: 69 lettered cells.
Word list: 20 distinct words, 1 skipped as unusable.
Candidates: 6 of 20 words spell a hidden word in this grid.

Did not qualify:
  12 not spellable by this grid in reading order

Already answers in this grid (2) - excluded by --exclude-grid-answers:
  ANTELOPE
  LEARNING

Hidden-word candidates, best first - one shaded cell per letter:
  LANTERN - 7 letters, 6 row(s) spanned, clustering 3
  ORANGE - 6 letters, 5 row(s) spanned, clustering 3
  SILENT - 6 letters, 5 row(s) spanned, clustering 3
  ENGINE - 6 letters, 6 row(s) spanned, clustering 6
  PLANET - 6 letters, 4 row(s) spanned, clustering 6
  MEANING - 7 letters, 6 row(s) spanned, clustering 27

Skipped word-list lines (1):
  WELL-KNOWN - holds a character outside A-Z
```

Four things in that output are the point of the sample. `LEARNING` (`large_square`'s own
featured answer) is excluded because the grid already answers it, which is a repeat rather
than a bonus; `antelope` shows the same thing plus the case fold; `well-known` shows an unusable
line being skipped and named rather than failing a run; and the clustering column is the
tool's opinion. `LANTERN` at 3 is the word to use. `MEANING` at 27 is the word not to,
and the second command shows why:

```bash
python decorative_crossword.py shade --source samples/large_square/grid_source.json --word LANTERN --out samples/hidden_word/hidden.svg
```

Expected exit code: **0**, with the cells on stdout and `hidden.svg` written beside `words.txt`:

```text
Hidden word LANTERN: 7 cells across 6 row(s), clustering 3.
  Shaded cells, 0-based (row, column): (2, 6), (3, 12), (4, 7), (6, 7), (6, 12), (8, 2), (11, 8)
  Paste form: [[2, 6], [3, 12], [4, 7], [6, 7], [6, 12], [8, 2], [11, 8]]
  Clustering 3: the shaded cells scatter - this reads as a hidden word.
```

Open `hidden.svg` and the seven shaded squares are scattered across six rows, reading as a
hidden message. Now run the same command with `--word MEANING` and no `--out`:

```text
Hidden word MEANING: 7 cells across 6 row(s), clustering 27.
  Shaded cells, 0-based (row, column): (3, 9), (4, 9), (6, 3), (6, 6), (7, 6), (8, 6), (9, 6)
  Paste form: [[3, 9], [4, 9], [6, 3], [6, 6], [7, 6], [8, 6], [9, 6]]
  Clustering 27: the shaded cells bunch - this will read as a corrupted answer, not a hidden word.
```

Four of those seven cells run consecutively down column 6: they are the last four letters of
`LEARNING`, this grid's own featured answer. Shading them would not read as a hidden message; it
would read as a damaged entry. Nothing can fix that: it is the cheapest reading `MEANING` has on
this grid, which is precisely what the number is telling you.

`LANTERN` is where the *chooser* earns its keep, and it is worth seeing directly. Take the first
occurrence of each of its letters (the obvious approach) and you get
`(2, 6), (3, 12), (4, 7), (6, 7), (6, 8), (8, 2), (8, 6)`, which costs 19: `(6, 7)` and
`(6, 8)` sit side by side inside `ANTELOPE`. The shortest path above costs 3 and puts no two
cells together. Same word, same grid, and the difference between a hidden message and a typo.

### `gaps`: what `large_square`'s own bank cannot pay for

The `gaps` sample, and the second whose input is another sample's output: it reads
`large_square/grid_source.json` against `large_square/bank.json`, so the question it answers is
the one an operator actually has after a run comes back sparser than they wanted: *which words
would have helped?* **Run `large_square` above first.**

```bash
python decorative_crossword.py gaps --source samples/large_square/grid_source.json --bank samples/large_square/bank.json --out samples/gaps/gaps.svg
```

Expected exit code: **0**. The headline splits all 100 blocked cells into tiers that add up,
and the answer is blunt: **`0 ready now`**. This fourteen-answer bank pays for none of the sixty
gaps, which is the same shortage *Why `large_square` loosens the blocked ceiling* works out
below, stated as specific words rather than as a total.

What the list adds is *which* words. It is grouped by the pattern a gap demands, not by the cell,
because the operator's unit of work is the word they have to think of:

```text
Needs one new answer - by pattern:
  ?C - 3 gaps: (4, 0), (10, 4), (10, 5)
  ?U - 2 gaps: (1, 2), (6, 0)
  S? - 2 gaps: (1, 5), (2, 4)
```

Three separate blocked cells all want the same thing: a two-letter answer ending in C.
That is one idea, not three. Ungrouped, this report would be sixty coordinates nobody could act
on, which is the lesson `shade` already paid for at 224 candidates.

Two things the report does that a bare list would not. It says what filling a gap would cost
where that cost is an existing answer: **17 gaps would weld two runs together**, retiring what
they swallow, and those are counted but left out until `--include-absorbing` asks for them. And
it closes the loop:

```text
Filling any one gap takes this grid to 58.6% blocked.
`fill` looks only a little past the first grid inside its window, so a new
answer in the bank may change nothing on its own: re-run with
--max-blocked 58.6 as well.
```

That last line is the part worth knowing. Adding an answer to the bank may do nothing by
itself: the search keeps the densest grid it finds only a short way past the first one inside
its density window, and a grid you are reading gaps from is already in one. The ceiling is derived, not guessed: `fill` accepts at
`blocked <= --max-blocked`, so the denser grid's own percentage, rounded up to a tenth, accepts
that grid and rejects today's. Here the two figures agree; they differ only where rounding up
moves the tenth.

`gaps.svg` is the same grid with a ring on every gap the report listed: the picture and the
text come from one function, so they cannot disagree about which cells are being discussed.

### `silhouette`: the same grid with nothing drawn in its blocked cells

The third sample that reads another sample's grid, and the one that shows a drawing option
rather than a search. It runs no search at all: `--empty-blocks` changes what a blocked cell
paints, so demonstrating it through `fill` would have put a seed and a density in the way of the
one thing being shown. **Run `large_square` above first.**

```bash
python decorative_crossword.py preview --source samples/large_square/grid_source.json --out samples/silhouette/shape.svg --empty-blocks
```

Expected exit code: **0**, with nothing on stdout and `shape.svg` written.

Open `shape.svg` beside `large_square/preview.svg` and the pair is the whole feature: one grid,
one `grid_source.json`, the same 59.2% blocked in both captions, and two pictures. The black
field is gone and what is left reads as a free shape: the kriss-kross look, where the outline
is not drawn by anything. It is the edge the lettered cells already stroke, which is why a
hole that touches the border simply shortens the silhouette there instead of leaving a gap in a
frame.

The caption still reports `59.2% blocked`, and that is deliberate rather than an oversight: the
percentage describes the grid, which the flag does not touch. Only the drawing changed.

## Why `large_square` loosens the blocked ceiling

`--max-blocked 60` is the one option here that is not just a size or a seed, and it is not
decoration. Ask a 13 x 13 for the default window (30-45% blocked, as the report below prints
it) and you are asking for 93 or more filled cells: more than half the grid. Now count
what this bank could possibly supply:

- Its answers hold 95 letters between them.
- Every placement after the first has to cross a letter already on the board, so each one
  after the first shares at least one cell with what is there.
- A connected grid drawn from all fourteen therefore covers at most `95 - 13 = 82` cells.

Eighty-two is short of ninety-three, so the default window is out of reach for this bank
before any search argument is considered. It is short of letters, not short of time, and no
budget buys the difference. The tool says as much rather than grinding:

```text
NOT CONFORMING - missed:
  blocked 59.2% is outside the requested 30.0-45.0% window
What would clear each:
  loosen --max-blocked to 59.2 or higher, or shrink --rows / --cols
```

The option in the command above is that remedy, taken from the tool's own report. The other
remedy is the bank: more answers, or longer ones, until the letters outnumber the cells the
window demands. Reading a report and turning the knob it names is the whole loop this tool is
built around, and `large_square` is the sample that walks through it.

## What a consumer still checks

The grids here are *candidates*: whatever consumes them should enforce the invariants this
generator deliberately does not (numbering, clue coverage, barred terms).

## Keeping these honest

`tests/test_samples.py` and `tests/test_samples_read.py` hold the same commands, and compare
what they produce with what is committed here. The duplication between those files and this one
is deliberate: this README is prose nothing executes, so the commands are pinned once more
where a machine can run them. **Change one and you must change the other**, and regenerate the
artifacts, since the tests compare bytes.
